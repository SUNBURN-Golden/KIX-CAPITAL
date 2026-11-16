"""SIMULATED recorded-interest evidence, authoritative fold parity and HTTP fences."""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from capital import interest_trace, overlay, recovery
from capital.auth import ROUTE_PERMISSIONS
from capital.export import VOLATILE_KEYS
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, canonical_bytes
from capital.terms import DecisionNoteTermsPolicy
from tests.facade_schema import SchemaError, load_contract, validate
from tests.test_overlay import draw_book, formula, row, run, tick
from tests.test_repayment_posting import pay
from tests.test_agent_lane import _propose
from test_recovery import book, cmd, recover, seed


def read(s):
    return s.interest_trace('sim-a', s.instance_id)


def numbers(value):
    if type(value) is int:
        return [value]
    if type(value) is dict:
        return [n for v in value.values() for n in numbers(v)]
    if type(value) is list:
        return [n for v in value for n in numbers(v)]
    return []


class InterestTraceTests(unittest.TestCase):
    def check_schema(self, body):
        validate(body, {'$ref': '#/definitions/interest_trace'}, load_contract())

    def check_fold(self, s):
        body = read(s)
        state = overlay.fold(s.overlay_entries, len(s.machine.export_journal()))
        totals = body['totals']
        self.assertEqual(totals['status'], 'COMPUTED')
        self.assertTrue(totals['reconciled'])
        self.assertEqual(body['cut']['state_digest'], s.machine.state_digest())
        self.assertEqual(body['cut']['overlay_state_digest'], overlay.state_digest(state))
        self.assertEqual(body['cut']['terms_binding'], state['terms_binding'])
        self.assertEqual(body['cut']['journal_length'], len(s.machine.export_journal()))
        self.assertEqual(body['cut']['overlay_journal_length'], len(s.overlay_entries))
        for bucket in ('contract', 'default'):
            self.assertEqual(totals['posted_krw'][bucket],
                             state['advances'].get('sim-a', {}).get(f'posted_{bucket}_krw', 0))
            prior = Fraction(0)
            for segment in body['segments']:
                p = segment['recorded_payload']
                self.assertEqual(p, s.overlay_entries[segment['overlay_index']]['payload'])
                for k in ('overlay_id', 'after_journal_index', 'sim_day'):
                    self.assertEqual(segment[k], s.overlay_entries[segment['overlay_index']][k])
                c = segment['components'][bucket]
                exact = Fraction(p[f'cumulative_{bucket}_exact'])
                self.assertEqual(Fraction(c['cumulative_before']), prior)
                self.assertEqual(Fraction(c['cumulative_after']), exact)
                self.assertEqual(Fraction(c['exact_increment']), exact - prior)
                self.assertEqual(Fraction(c['remainder_before']), prior - int(prior))
                self.assertEqual(Fraction(c['remainder_after']), exact - int(exact))
                self.assertEqual(c['posted_krw'], int(exact) - int(prior))
                self.assertEqual(c['rate_bps'], p[f'{bucket}_bps'])
                self.assertEqual(c['days'], p['contractual_days' if bucket == 'contract' else 'default_days'])
                for field in ('cumulative_before', 'cumulative_after', 'exact_increment',
                              'remainder_before', 'remainder_after'):
                    value = Fraction(c[field])
                    self.assertEqual(c[field], f'{value.numerator}/{value.denominator}')
                prior = exact
            self.assertEqual(Fraction(totals['cumulative_exact'][bucket]), prior)
        self.assertEqual(totals['repayment'], overlay._payments(state, 'sim-a'))
        self.assertEqual(totals['recovery_fold'], recovery.recovered(state, 'sim-a'))
        for key in totals['recovery_paid']:
            self.assertEqual(totals['recovery_paid'][key], recovery.recovered(state, 'sim-a')[key])
        sibling = row(s)
        for key in ('interest_due_krw', 'default_interest_due_krw'):
            self.assertEqual(totals['due_reader'][key], sibling[key])
        if recovery.anchor(state, 'sim-a'):
            self.assertEqual(totals['due_reader']['recovery_position'], recovery.position(state, 'sim-a'))
        self.check_schema(body)
        return body

    def test_partial_repayment_and_stored_witnesses_receipts_and_citations(self):
        s = CapitalService(); draw_book(s)
        tick(s, 'first', 0, 3)
        s.agent_propose(_propose(proposal_id='SIMULATED-proposal', surface='capital:repay', amount=5000), role='agent')
        pay(s, 'partial', 5000, evidence_ref='SIMULATED-receipt', proposal_id='SIMULATED-proposal')
        tick(s, 'second', 3, 9)
        body = self.check_fold(s)
        payment = body['payments'][0]
        original = s.overlay_entries[payment['overlay_index']]['payload']
        self.assertEqual(payment['recorded_payload'], original)
        self.assertEqual(payment['payment_basis'], 'UNVERIFIED_ASSERTED')
        self.assertEqual(payment['f04_receipt'], s.receipts[original['f04_operation_id']]['receipt'])
        linked = payment['f04_journal_row']
        self.assertEqual(linked['entry'], s.machine.export_journal()[linked['journal_index']])
        self.assertEqual(linked['entry']['body']['repay_id'], original['f04_receipt_ref'])
        first, second = body['segments']
        principal = 90000 - original['allocation']['principal_krw']
        self.assertEqual(second['recorded_payload']['principal'], principal)
        self.assertEqual(body['totals']['posted_krw']['contract'], formula(90000 * 3 + principal * 6, 700))
        self.assertEqual(first['recorded_payload']['principal'], 90000)

    def test_same_day_empty_history_and_interest_only_payments(self):
        s = CapitalService(); tick(s, 'bind-before-draw', 0, 1); draw_book(s)
        body = self.check_fold(s)
        self.assertEqual(body['segments'], [])
        self.assertEqual(body['diagnostics'][0]['reason'], 'NO_POSTINGS_YET')
        pay(s, 'same-day', 100)
        self.assertEqual(self.check_fold(s)['segments'], [])
        tick(s, 'clock', 1, 4)
        before = s.machine.export_journal()
        pay(s, 'interest-only', row(s)['interest_due_krw'])
        body = self.check_fold(s)
        self.assertEqual(s.machine.export_journal(), before)
        payment = body['payments'][-1]
        self.assertIsNone(payment['f04_receipt'])
        self.assertIsNone(payment['f04_journal_row'])
        self.assertIsNone(payment['recorded_payload']['f04_operation_id'])
        self.assertEqual(len(body['segments']), 1)

    def test_sub_won_zero_postings_and_bucket_carry(self):
        s = CapitalService(); draw_book(s, amount=100)
        for start in range(0, 70):
            tick(s, 'tick-' + str(start), start, start + 1)
        body = self.check_fold(s)
        self.assertTrue(any(seg['components']['contract']['posted_krw'] == 0 for seg in body['segments']))
        self.assertEqual(body['totals']['posted_krw']['contract'], formula(100 * 60, 700))
        self.assertEqual(body['totals']['posted_krw']['default'], formula(100 * 10, 1000))
        self.assertNotEqual(body['segments'][0]['components']['contract']['remainder_after'], '0/1')

    def test_acceleration_jump_and_daily_histories_reconcile(self):
        def prepare():
            source, s = book(amount=48000)
            source.replay('sim-committed', 'partial-before')
            tick(s, 'call', 10, 20)
            return s
        a, b = prepare(), prepare()
        tick(a, 'jump', 20, 40)
        for day in range(20, 40):
            tick(b, 'daily-' + str(day), day, day + 1)
        x, y = self.check_fold(a), self.check_fold(b)
        self.assertEqual(x['totals']['posted_krw'], y['totals']['posted_krw'])
        self.assertEqual(x['totals']['cumulative_exact'], y['totals']['cumulative_exact'])
        self.assertEqual(x['totals']['posted_krw'], {'contract': formula(48000 * 25, 700),
                                                   'default': formula(48000 * 15, 1000)})
        self.assertIn('margin_acceleration', [e['kind'] for e in x['events']])
        _, s = book()
        s.overlay_command(cmd(s, 'record_acceleration', 'acceleration', event='BENEFICIARY_INSOLVENCY_NOTICE'))
        tick(s, 'after-acceleration', 10, 20)
        body = self.check_fold(s)
        self.assertIn('acceleration_event', [e['kind'] for e in body['events']])
        self.assertEqual(body['segments'][-1]['recorded_payload']['maturity_day'], 10)

    def test_default_recovery_writeoff_stop_and_late_residual_recovery(self):
        source, s = book()
        run(s, 'default', 'sim-a', 'default')
        seed.distribute(source, 'sim-committed')
        tick(s, 'day20', 10, 20)
        s.overlay_command(recover(s, 5000, 'pre-writeoff'))
        before = self.check_fold(s)
        self.assertEqual(before['totals']['repayment']['paid_interest_krw'], 0)
        self.assertGreater(before['totals']['recovery_paid']['paid_interest_krw'], 0)
        anchor = recovery.anchor(overlay.fold(s.overlay_entries), 'sim-a')
        stop = anchor['writeoff_eligible_sim_day']
        tick(s, 'beyond-stop', 20, stop + 20)
        frozen = self.check_fold(s)
        self.assertEqual(frozen['segments'][-1]['recorded_payload']['to_day'], stop)
        self.assertEqual(frozen['segments'][-1]['recorded_payload']['recovery_witness']['stop_day'], stop)
        s.overlay_command(cmd(s, 'post_writeoff', 'writeoff', setoff_declined_reason='SIMULATED_DECLINED'))
        posted = self.check_fold(s)
        tick(s, 'later', stop + 20, stop + 30)
        s.overlay_command(recover(s, 1000, 'late'))
        body = self.check_fold(s)
        self.assertEqual(body['segments'], frozen['segments'])
        self.assertEqual(body['totals']['posted_krw'], frozen['totals']['posted_krw'])
        self.assertEqual(body['totals']['recovery_paid'], posted['totals']['recovery_paid'])
        self.assertEqual(body['totals']['residual_recovery_krw'], 1000)
        self.assertNotIn('allocation', body['payments'][-1]['recorded_payload'])
        for payment in body['payments']:
            self.assertEqual(payment['recorded_payload'], s.overlay_entries[payment['overlay_index']]['payload'])
            self.assertIn('quote_witness', payment['recorded_payload'])
            self.assertIn('policy', payment['recorded_payload'])
        writeoff = next(e['recorded_payload'] for e in body['events'] if e['kind'] == 'WRITEOFF')
        for key, value in body['totals']['writeoff_adjustments'].items():
            self.assertEqual(value, writeoff[key])
        self.assertEqual(writeoff['writeoff_effective_sim_day'], stop)
        self.assertGreater(writeoff['sim_day'], stop)
        self.assertEqual(body['totals']['due_reader']['interest_due_krw'], 0)

    def test_missing_terms_mismatched_binding_missing_gate_and_default_anchor(self):
        for failure in ('missing-terms', 'mismatch', 'gate', 'anchor'):
            with self.subTest(failure=failure):
                s = CapitalService(); draw_book(s)
                if failure == 'anchor':
                    run(s, 'default', 'sim-a', 'legacy-default')
                tick(s, 'clock', 0, 3)
                if failure == 'missing-terms':
                    s.terms = DecisionNoteTermsPolicy(Path('/NO_SUCH_TERMS.md'))
                elif failure == 'mismatch':
                    original = s._overlay_terms()
                    s._overlay_terms = lambda: {**original, 'terms_version': 'INCOMPATIBLE'}
                elif failure == 'gate':
                    del s.receipts['a-draw']['receipt']['result']['credit']['settlement_gate']
                body = read(s)
                self.assertEqual(body['totals']['status'], 'NOT_BOUND')
                self.assertEqual(numbers(body['totals']), [])
                self.assertEqual(body['diagnostics'][0]['status'], 'NOT_BOUND')
                self.assertTrue(body['segments'])
                for segment in body['segments']:
                    self.assertEqual(numbers(segment['components']), [])
                    self.assertEqual(segment['recorded_payload'], s.overlay_entries[segment['overlay_index']]['payload'])
                self.check_schema(body)
        s = CapitalService(); run(s, 'offer', 'sim-a', 'offer', fixture_id='sim-committed', amount=100)
        body = read(s)
        self.assertEqual(body['totals'], {'status': 'NOT_APPLICABLE', 'reason': 'NOT_DRAWN'})
        self.check_schema(body)

    def test_direct_f04_repayments_are_never_inferred_as_interest_payments(self):
        s = CapitalService(); draw_book(s); tick(s, 't', 0, 3)
        run(s, 'repay', 'sim-a', 'direct', amount=100, sequence=1)
        body = self.check_fold(s)
        self.assertEqual(body['payments'], [])
        self.assertEqual(body['totals']['repayment']['principal_krw'], 0)
        self.assertIn('DIRECT_F04_REPAYMENTS_NOT_INTEREST_WITNESSES', [d['reason'] for d in body['diagnostics']])

    def test_duplicate_entries_and_dangling_or_conflicting_evidence_fail_through_fold(self):
        s = CapitalService(); draw_book(s); tick(s, 't', 0, 3)
        baseline = read(s)
        s.overlay_entries.append(copy.deepcopy(s.overlay_entries[-1]))
        repeated = read(s)
        self.assertEqual(repeated['segments'], baseline['segments'])
        self.assertEqual(repeated['totals'], baseline['totals'])
        self.assertEqual(repeated['cut']['overlay_state_digest'], baseline['cut']['overlay_state_digest'])
        s.overlay_entries[-1]['payload']['principal'] += 1
        with self.assertRaisesRegex(overlay.OverlayError, 'conflicting overlay_id'):
            read(s)
        s.overlay_entries.pop()
        s.overlay_entries[-1]['after_journal_index'] = len(s.machine.export_journal()) + 1
        with self.assertRaisesRegex(overlay.OverlayError, 'dangling'):
            read(s)

    def test_unexpected_reader_errors_propagate_and_guard_detects_mutation(self):
        s = CapitalService(); draw_book(s)
        with patch.object(s, 'overlay_state', side_effect=ApiError('READ_ONLY_INVARIANT', 500)):
            with self.assertRaisesRegex(ApiError, 'READ_ONLY_INVARIANT'):
                read(s)
        with patch('capital.interest_trace.build', side_effect=lambda *args: s.receipts.clear()):
            with self.assertRaisesRegex(ApiError, 'READ_ONLY_INVARIANT'):
                read(s)

    def test_duplicate_old_clock_does_not_change_default_link_validation(self):
        _, s = book()
        old_clock = copy.deepcopy(next(e for e in s.overlay_entries if e['kind'] == 'clock'))
        tick(s, 'before-default', 10, 20)
        run(s, 'default', 'sim-a', 'default')
        tick(s, 'after-default', 20, 30)
        before = self.check_fold(s)
        s.overlay_entries.append(old_clock)
        after = self.check_fold(s)
        for key in ('segments', 'payments', 'events', 'totals'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after['cut']['overlay_state_digest'], before['cut']['overlay_state_digest'])

    def test_digest_detachment_restart_and_byte_preservation_without_accrual_generation(self):
        with tempfile.TemporaryDirectory() as tmp, FileWorkspace.open(tmp) as storage:
            s = CapitalService(storage); draw_book(s); tick(s, 't', 0, 3); pay(s, 'p', 1000)
            def frozen():
                return (s._frozen(), s.machine.canonical_state(), s.machine.export_journal(),
                        s.dossier('sim-a', s.instance_id), s.export(), s.export_manifest(),
                        {p.name: p.read_bytes() for p in Path(tmp).iterdir()})
            before = frozen()
            with patch.object(storage, 'save', side_effect=AssertionError('must not save')), \
                 patch.object(overlay, 'accrual_postings', side_effect=AssertionError('must not generate')), \
                 patch.object(overlay, 'advance_entries', side_effect=AssertionError('must not generate')):
                first, second = read(s), read(s)
            self.assertEqual(first, second)
            self.assertEqual(before, frozen())
            first['segments'][0]['recorded_payload']['principal'] = 0
            first['payments'][0]['recorded_payload']['witness']['denominator'] = 1
            first['payments'][0]['f04_receipt']['outcome'] = 'tainted'
            self.assertEqual(read(s), second)
            def stable(v):
                if type(v) is dict:
                    return {k: stable(x) for k, x in v.items() if k not in VOLATILE_KEYS}
                return [stable(x) for x in v] if type(v) is list else v
            material = stable({k: v for k, v in second.items() if k != 'trace_digest'})
            self.assertEqual(second['trace_digest'], hashlib.sha256(canonical_bytes(material)).hexdigest())
            tainted = copy.deepcopy(second); tainted['totals']['posted_krw']['contract'] += 1
            self.assertNotEqual(interest_trace.digest(tainted), second['trace_digest'])
            restored = CapitalService(storage)
            self.assertEqual(read(restored)['trace_digest'], second['trace_digest'])

    def test_one_lock_serializes_composition_and_clock_writer(self):
        s = CapitalService(); draw_book(s)
        before = read(s)
        entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
        results, errors = {}, []
        original = interest_trace.build
        def held(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError('reader not released')
            return original(*args)
        def reader():
            try: results['read'] = read(s)
            except BaseException as exc: errors.append(exc)
        def writer():
            attempted.set()
            try: results['write'] = tick(s, 'concurrent', 0, 1)
            except BaseException as exc: errors.append(exc)
        with patch('capital.interest_trace.build', side_effect=held):
            a, b = threading.Thread(target=reader), threading.Thread(target=writer)
            a.start()
            try:
                self.assertTrue(entered.wait(5)); b.start()
                self.assertTrue(attempted.wait(5)); self.assertNotIn('write', results)
            finally:
                release.set(); a.join(5)
                if b.ident is not None: b.join(5)
                self.assertFalse(a.is_alive()); self.assertFalse(b.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results['read'], before)
        self.assertEqual(read(s)['sim_day'], 1)

    def test_closed_schema_rejects_unknown_derived_and_repayment_fields(self):
        s = CapitalService(); draw_book(s); tick(s, 't', 0, 3); pay(s, 'p', 1000)
        for path in ((), ('cut',), ('totals',), ('segments', 0),
                     ('segments', 0, 'components', 'contract'), ('segments', 0, 'recorded_payload'),
                     ('payments', 0), ('payments', 0, 'recorded_payload', 'witness')):
            body = read(s); node = body
            for key in path: node = node[key]
            node['unexpected'] = True
            with self.assertRaises(SchemaError): self.check_schema(body)


class InterestTraceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.s = self.server.service
        draw_book(self.s); tick(self.s, 't', 0, 3)
        for role in ('auditor', 'observer', 'agent'): self.s.authorizer.bind_role(role)
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(5)
        self.assertFalse(self.worker.is_alive())

    def request(self, path, role='organizer'):
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.request('GET', path, headers={'X-Capital-Token': self.s.authorizer.token_for(role)})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_dossier_permission_catalog_and_roles(self):
        self.assertIn(('/api/cases/', 'projection:read', True), ROUTE_PERMISSIONS)
        _, catalog = self.request('/api/permissions')
        self.assertIn({'method': 'GET', 'route': '/api/cases/', 'children': True,
                       'permission': 'projection:read'}, catalog['routes'])
        path = '/api/cases/sim-a/interest-trace?instance_id=' + self.s.instance_id
        for role, expected in (('organizer', 200), ('auditor', 200), ('observer', 403), ('agent', 403)):
            status, body = self.request(path, role)
            self.assertEqual(status, expected)
            if status == 200:
                self.assertEqual(body, read(self.s))
                validate(body, {'$ref': '#/definitions/interest_trace'}, load_contract())
            else:
                self.assertEqual(body['error'], 'ROLE_FORBIDDEN')
                self.assertEqual(body['permission'], 'projection:read')

    def test_strict_path_session_case_and_query_errors(self):
        path = '/api/cases/sim-a/interest-trace'
        suffix = '?instance_id=' + self.s.instance_id
        for target, status, error in (
            (path, 409, 'SESSION_CHANGED'), (path + '?instance_id=', 409, 'SESSION_CHANGED'),
            (path + '?instance_id=stale', 409, 'SESSION_CHANGED'),
            (path + suffix + '&cash=1', 400, 'INVALID_ARGUMENTS'),
            (path + suffix + '&instance_id=x', 400, 'INVALID_ARGUMENTS'),
            (path.replace('sim-a', 'missing') + suffix, 404, 'CASE_NOT_FOUND'),
            (path + '/' + suffix, 404, 'NOT_FOUND'),
            (path.replace('/interest-trace', '/nested/interest-trace') + suffix, 404, 'NOT_FOUND')):
            code, body = self.request(target)
            self.assertEqual((code, body['error']), (status, error), target)
