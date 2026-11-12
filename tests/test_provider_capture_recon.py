"""Recorded SIMULATED provider-capture facts: organizer write path, fold, recon, export isolation."""
import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from capital import facts, observation, overlay
from capital.audit import audit_workspace
from capital.observation_record import (
    CHECK_ID, CLASS, KIND, OP, FactError, load_policy, project_fake, validate_payload)
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, canonical_bytes, section_checksum
from capital.verify import verify_manifest
from test_overlay import draw_book, tick

ROOT = Path(__file__).resolve().parents[1]
EMPTY_GOLDEN = json.loads((ROOT / 'tests/golden/overlay_empty.json').read_text())
DAY = 7
CLAIM = 'sim-committed'
REF = 'ab' * 32


def payload(**kw):
    base = {
        'fact_class': CLASS, 'claim_id': CLAIM, 'order_ref': 'sim-order-1',
        'amount_krw': 100000, 'claimed_provider_ref': REF,
        'sim_day': DAY, 'effective_sim_day': DAY, 'captured_sim_day': DAY,
        'authority': {'role': 'organizer', 'approvals': []},
        'label': 'SIMULATED', 'verification': 'UNVERIFIED_ASSERTED',
        'funds_executed': False, 'provider_call_made': False,
        'legal_effect': 'NOT_ASSESSED',
    }
    base.update(kw)
    return base


def command(service, key, body=None, at_sim_day=DAY):
    return {'instance_id': service.instance_id, 'operation_id': key, 'op': OP,
            'at_sim_day': at_sim_day, 'payload': body if body is not None else payload()}


def book(storage=None):
    service = CapitalService(storage)
    draw_book(service)
    tick(service, 'observe-tick', 0, DAY)
    return service


def gross(service, claim=CLAIM):
    return service.fixtures.view(claim)['claim']['gross']


def recon_check(service):
    return next((c for c in service.reconciliation()['checks'] if c['id'] == CHECK_ID), None)


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.service = book()

    def assert_code(self, code, status, call):
        before = len(self.service.overlay_entries)
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual((caught.exception.code, caught.exception.status), (code, status))
        self.assertEqual(before, len(self.service.overlay_entries), 'rejection wrote an entry')

    def record(self, key='fact-1', body=None, role='organizer', **kw):
        return self.service.overlay_command(
            {**command(self.service, key, body), 'payload': body or payload(**kw)}, role=role)


class AuthorityTests(ServiceCase):
    def test_organizer_records_and_roles_are_refused(self):
        for role, code in (('agent', 'FACT_AGENT_FORBIDDEN'),
                           ('auditor', 'FACT_ROLE_FORBIDDEN'),
                           ('observer', 'FACT_ROLE_FORBIDDEN'),
                           ('nobody', 'FACT_ROLE_FORBIDDEN')):
            with self.subTest(role=role):
                self.assert_code(code, 403, lambda: self.record(role=role))
        result = self.record()
        self.assertEqual(result['outcome'], 'APPLIED')
        self.assertEqual(result['entry']['recorded_by_role'], 'organizer')
        self.assertIs(result['funds_executed'], False)
        self.assertIs(result['f04_journal_written'], False)

    def test_fact_role_check_runs_before_permission_matrix(self):
        self.assert_code('FACT_AGENT_FORBIDDEN', 403, lambda: self.record(role='agent'))
        self.assert_code('ROLE_FORBIDDEN', 403, lambda: self.service.overlay_command(
            {'instance_id': self.service.instance_id, 'operation_id': 'clock-2', 'op': 'advance_day',
             'from_sim_day': DAY, 'to_sim_day': DAY + 1, 'reason': 'x'}, role='auditor'))


class ShapeTests(ServiceCase):
    def test_strict_envelope(self):
        good = command(self.service, 'fact-1')
        self.assert_code('INVALID_COMMAND', 400, lambda: self.service.overlay_command(
            {**good, 'extra': 1}))
        self.assert_code('INVALID_COMMAND', 400, lambda: self.service.overlay_command(
            {k: v for k, v in good.items() if k != 'payload'}))
        self.assert_code('INVALID_COMMAND', 400, lambda: self.service.overlay_command('text'))

    def test_strict_payload_fields(self):
        for mutant in (
            lambda p: p.update(recorded_by_role='organizer'),
            lambda p: p.update(spare=1),
            lambda p: p.pop('claim_id'),
            lambda p: p.update(amount_krw=True),
            lambda p: p.update(amount_krw='100'),
            lambda p: p.update(amount_krw=0),
            lambda p: p.update(amount_krw=1_000_000_000_001),
            lambda p: p.update(sim_day=-1),
            lambda p: p.update(sim_day=True),
            lambda p: p.update(order_ref='not-synthetic'),
            lambda p: p.update(order_ref='sim-' + 'x' * 61),
            lambda p: p.update(claimed_provider_ref='zz' * 32),
            lambda p: p.update(claimed_provider_ref=12),
            lambda p: p.update(authority={'role': 'auditor', 'approvals': []}),
            lambda p: p.update(authority={'role': 'organizer',
                                          'approvals': [{'approver_label': 'a b'}]}),
            lambda p: p.update(authority={'role': 'organizer', 'approvals': [], 'extra': 1}),
            lambda p: p.update(label='REAL'),
            lambda p: p.update(funds_executed=True),
            lambda p: p.update(provider_call_made=True),
            lambda p: p.update(legal_effect='ASSESSED'),
            lambda p: p.update(verification='ASSERTED'),
        ):
            with self.subTest(mutant=mutant):
                body = payload()
                mutant(body)
                self.assert_code('INVALID_ARGUMENTS', 400, lambda: self.record(body=body))

    def test_valid_claimed_ref_forms(self):
        self.record('f1', body=payload(claimed_provider_ref='cd' * 32))
        self.record('f2', body=payload(claimed_provider_ref='sim-ref-1'))

    def test_session_and_day_checks(self):
        self.assert_code('SESSION_CHANGED', 409, lambda: self.service.overlay_command(
            {**command(self.service, 'fact-1'), 'instance_id': 'other'}))
        self.assert_code('INVALID_OPERATION_ID', 400, lambda: self.service.overlay_command(
            command(self.service, 'bad key')))
        self.assert_code('INVALID_ARGUMENTS', 400, lambda: self.service.overlay_command(
            command(self.service, 'fact-1', at_sim_day='7')))
        stale = payload(sim_day=DAY - 1, effective_sim_day=DAY - 1, captured_sim_day=DAY - 1)
        self.assert_code('SIM_CLOCK_STALE', 409, lambda: self.service.overlay_command(
            command(self.service, 'fact-1', body=stale, at_sim_day=DAY - 1)))
        self.assert_code('INVALID_ARGUMENTS', 400, lambda: self.service.overlay_command(
            command(self.service, 'fact-1', body=payload(
                sim_day=DAY - 1, effective_sim_day=DAY - 1, captured_sim_day=DAY - 1))))


class LabelAndClassTests(ServiceCase):
    def test_confirmed_labels_are_not_bound(self):
        for label in ('PROVIDER_CONFIRMED', 'BANK_MATCHED', 'CHAIN_CONFIRMED'):
            with self.subTest(label=label):
                self.assert_code('FACT_VERIFICATION_NOT_BOUND', 409,
                                 lambda: self.record(body=payload(verification=label)))

    def test_adopted_but_unrecorded_classes_are_not_bound(self):
        for fact_class in ('SETTLEMENT_CASH_ARRIVAL', 'REFUND_EVENT_OBSERVED'):
            with self.subTest(fact_class=fact_class):
                self.assert_code('NOT_BOUND', 409, lambda: self.record(
                    body=payload(fact_class=fact_class)))

    def test_unadopted_classes_fail_400(self):
        for fact_class in ('BANK_STATEMENT_LINE', 'KYC_EVENT', 'CHAIN_TX_OBSERVED',
                           'PROVIDER_WEBHOOK_RECEIPT', 'anything'):
            with self.subTest(fact_class=fact_class):
                self.assert_code('FACT_CLASS_NOT_ADOPTED', 400, lambda: self.record(
                    body=payload(fact_class=fact_class)))

    def test_future_and_inconsistent_days(self):
        self.assert_code('FACT_FUTURE_DAY', 409, lambda: self.record(
            body=payload(effective_sim_day=DAY + 1)))
        self.assert_code('FACT_FUTURE_DAY', 409, lambda: self.record(
            body=payload(captured_sim_day=DAY + 1)))
        self.assert_code('INVALID_ARGUMENTS', 400, lambda: self.record(
            body=payload(effective_sim_day=DAY - 1)))

    def test_unknown_claim_is_a_409_not_a_silent_write(self):
        self.assert_code('FACT_CLAIM_UNKNOWN', 409, lambda: self.record(
            body=payload(claim_id='no-such-claim')))


class VolatileKeyTests(ServiceCase):
    def test_recursive_volatile_and_personal_keys_write_nothing(self):
        for key in ('created_at', 'saved_at', 'timestamp', 'timestamps', 'occurred_at',
                    'received_at', 'offset', 'transmission', 'raw_evidence_ref',
                    'account_number', 'customer_name', 'email', 'credentials'):
            with self.subTest(key=key):
                self.assert_code('OVERLAY_VOLATILE_KEY', 400, lambda: self.record(
                    body=payload(nested={'inner': {key: 'x'}})))
        self.assert_code('OVERLAY_VOLATILE_KEY', 400, lambda: self.service.overlay_command(
            {'instance_id': self.service.instance_id, 'operation_id': 'fact-1', 'op': OP,
             'at_sim_day': DAY, 'payload': {'instance_id': 'nested'}}))


class DedupAndClockTests(ServiceCase):
    def test_identical_retry_after_clock_and_conflict_reuses(self):
        first = self.record('fact-1')
        tick(self.service, 'clock-again', DAY, DAY + 1)
        n = len(self.service.overlay_entries)
        again = self.service.overlay_command(command(self.service, 'fact-1'))
        self.assertTrue(again['transport_duplicate'])
        self.assertEqual(first['entry'], again['entry'])
        self.assertEqual(n, len(self.service.overlay_entries))
        self.assert_code('FACT_IDEMPOTENCY_CONFLICT', 409, lambda: self.service.overlay_command(
            command(self.service, 'fact-1', body=payload(amount_krw=1))))
        self.assert_code('FACT_IDEMPOTENCY_CONFLICT', 409, lambda: self.service.overlay_command(
            command(self.service, 'observe-tick')))
        self.assert_code('FACT_IDEMPOTENCY_CONFLICT', 409, lambda: self.service.overlay_command(
            command(self.service, 'a-draw')))

    def test_restart_replays_the_same_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ws'
            port = FileWorkspace.open(path)
            service = book(port)
            first = service.overlay_command(command(service, 'fact-1'))
            port.close()
            restored = CapitalService(FileWorkspace.open(path))
            again = restored.overlay_command(command(restored, 'fact-1'))
            self.assertTrue(again['transport_duplicate'])
            self.assertEqual(first['entry'], again['entry'])
            with self.assertRaises(ApiError) as caught:
                restored.overlay_command(command(restored, 'fact-1', body=payload(amount_krw=2)))
            self.assertEqual(caught.exception.code, 'FACT_IDEMPOTENCY_CONFLICT')

    def test_recording_never_advances_the_clock_or_touches_f04(self):
        before = (self.service.machine.state_digest(), self.service.machine.export_journal(),
                  len(self.service.receipts))
        self.record('fact-1')
        self.assertEqual(before, (self.service.machine.state_digest(),
                                  self.service.machine.export_journal(),
                                  len(self.service.receipts)))
        self.assertEqual(overlay.fold(self.service.overlay_entries)['sim_day'], DAY)

    def test_operation_lookup_rebuilds_the_recorded_receipt(self):
        self.record('fact-1')
        operation = self.service.overlay_state('fact-1')['operation']
        self.assertEqual(operation['outcome'], 'APPLIED')
        self.assertEqual(operation['entry']['fact_class'], CLASS)
        self.assertEqual(operation['entry']['recorded_by_role'], 'organizer')
        self.assertEqual(self.service.overlay_state('absent')['operation']['outcome'], 'UNKNOWN')


class FoldTests(ServiceCase):
    def test_observations_keyed_by_fact_id_with_derived_status(self):
        self.record('fact-1')
        self.record('fact-2', body=payload(amount_krw=9, supersedes_fact_id='fact-1'))
        state = overlay.fold(self.service.overlay_entries)
        facts_map = state['observations']
        self.assertEqual(set(facts_map), {'fact-1', 'fact-2'})
        self.assertEqual(facts_map['fact-1']['status'], 'SUPERSEDED')
        self.assertEqual(facts_map['fact-2']['status'], 'ACTIVE')
        self.assertEqual(self.service.overlay_state()['observations'], facts_map)

    def test_absent_fold_key_keeps_schema_one_and_empty_golden(self):
        service = CapitalService()
        state = overlay.fold(service.overlay_entries)
        self.assertNotIn('observations', state)
        self.assertEqual(overlay.SCHEMA, 1)
        self.assertEqual(overlay.state_digest(state), EMPTY_GOLDEN['overlay_state_digest'])
        self.assertEqual(EMPTY_GOLDEN['overlay_schema'], 1)
        self.assertNotIn('observations', service.overlay_state())

    def test_clock_only_overlay_has_no_observations(self):
        service = CapitalService()
        tick(service, 'only-clock', 0, 2)
        self.assertNotIn('observations', overlay.fold(service.overlay_entries))
        self.assertNotIn('observations', service.overlay_state())
        self.assertIsNone(recon_check(service))

    def test_replay_is_deterministic_and_conflicting_ids_reject(self):
        self.record('fact-1')
        state = overlay.fold(self.service.overlay_entries)
        again = overlay.fold(copy.deepcopy(self.service.overlay_entries))
        self.assertEqual(state, again)
        entries = copy.deepcopy(self.service.overlay_entries) + [
            copy.deepcopy(self.service.overlay_entries[-1])]
        self.assertEqual(state, overlay.fold(entries))
        conflict = copy.deepcopy(entries)
        conflict[-1]['payload'] = copy.deepcopy(conflict[-1]['payload'])
        conflict[-1]['payload']['amount_krw'] += 1
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(conflict)


class SupersedeTests(ServiceCase):
    def test_reference_must_be_an_earlier_active_fact_of_the_same_claim(self):
        self.record('f1')
        self.assert_code('FACT_SUPERSEDE_INVALID', 409, lambda: self.record(
            'f2', body=payload(supersedes_fact_id='missing')))
        self.assert_code('FACT_SUPERSEDE_INVALID', 409, lambda: self.record(
            'f2', body=payload(supersedes_fact_id='f1', claim_id='sim-pending')))
        self.assert_code('FACT_SUPERSEDE_INVALID', 409, lambda: self.record(
            'f2', body=payload(supersedes_fact_id='f2')))
        self.record('f2', body=payload(supersedes_fact_id='f1'))
        self.assert_code('FACT_SUPERSEDE_INVALID', 409, lambda: self.record(
            'f3', body=payload(supersedes_fact_id='f1')))
        self.record('f3', body=payload(supersedes_fact_id='f2'))

    def test_chain_depth_is_bounded_by_the_note(self):
        bound = load_policy()['bounds']['max_supersede_chain_depth']
        self.assertEqual(bound, 4)
        self.record('f0')
        previous = 'f0'
        for index in range(1, bound + 1):
            self.record(f'f{index}', body=payload(supersedes_fact_id=previous))
            previous = f'f{index}'
        self.assert_code('FACT_SUPERSEDE_DEPTH', 409, lambda: self.record(
            f'f{bound + 1}', body=payload(supersedes_fact_id=previous)))


class CapacityTests(ServiceCase):
    def test_per_claim_cap_scopes_external_facts(self):
        bound = load_policy()['bounds']
        self.assertEqual((bound['max_fact_entries'], bound['max_facts_per_claim']), (128, 16))
        for index in range(bound['max_facts_per_claim']):
            self.record(f'cap-{index}')
        with self.assertRaises(ApiError) as caught:
            self.record('cap-overflow')
        self.assertEqual((caught.exception.code, caught.exception.detail),
                         ('SIMULATION_CAPACITY', {'scope': 'external_facts'}))

    def test_entry_cap_scopes_external_facts(self):
        service = CapitalService()
        tick(service, 'tick-x', 0, DAY)
        claims = sorted(service.fixtures.rows)
        for index in range(load_policy()['bounds']['max_fact_entries']):
            service.overlay_command(command(service, f'e{index}', body=payload(
                claim_id=claims[index % len(claims)])))
        self.assertEqual(128, sum(e['kind'] == KIND for e in service.overlay_entries))
        with self.assertRaises(ApiError) as caught:
            service.overlay_command(command(service, 'e-overflow'))
        self.assertEqual((caught.exception.code, caught.exception.detail),
                         ('SIMULATION_CAPACITY', {'scope': 'external_facts'}))


class ReconciliationTests(ServiceCase):
    def test_check_is_conditional_and_reports_match(self):
        self.assertIsNone(recon_check(self.service))
        self.record('fact-1', body=payload(amount_krw=gross(self.service)))
        report = self.service.reconciliation()
        self.assertEqual(report['status'], 'MATCHED')
        check = recon_check(self.service)
        self.assertEqual(check['status'], 'MATCH')
        self.assertEqual(check['diagnostics'], [])
        self.assertEqual(check['source_fact_ids'], ['fact-1'])
        self.assertIs(check['derived'], True)
        self.assertEqual(check['derivation'], CHECK_ID)
        self.assertEqual(check['provenance'], 'DERIVED_FROM_UNVERIFIED_ASSERTED')
        self.assertEqual(check['verification'], 'UNVERIFIED_ASSERTED')
        self.assertEqual(check['coverage']['completeness'], 'NOT_BOUND')
        row = next(r for r in check['claims'] if r['claim_id'] == CLAIM)
        self.assertEqual((row['status'], row['capture_sum_krw'],
                          row['expected_claim_gross_krw']), ('MATCH', 100000, 100000))
        self.assertEqual(row['settlement_diagnostics']['label'], 'READ_ONLY_FIXTURE')
        self.assertTrue(row['draw_diagnostics'])
        self.assertEqual(row['draw_diagnostics'][0]['label'], 'SIMULATED_F04_ACCEPTED_DRAW')
        unobserved = next(r for r in check['claims'] if r['claim_id'] == 'sim-pending')
        self.assertEqual(unobserved['status'], 'NO_FACTS')
        self.assertEqual(sorted(r['claim_id'] for r in check['claims']),
                         sorted(self.service.fixtures.rows))
        self.assertEqual([c['id'] for c in report['checks'] if c['id'] != CHECK_ID],
                         [c['id'] for c in report['checks']][:-1])

    def test_asserted_mismatch_is_diagnostic_only(self):
        self.record('fact-1', body=payload(amount_krw=1))
        report = self.service.reconciliation()
        self.assertEqual(report['status'], 'MATCHED')
        check = recon_check(self.service)
        self.assertEqual(check['status'], 'ASSERTED_MISMATCH')
        self.assertEqual(check['diagnostics'], ['OBSERVED_FACT_MISMATCH'])

    def test_superseded_facts_leave_the_sum(self):
        self.record('f1', body=payload(amount_krw=1))
        self.record('f2', body=payload(amount_krw=gross(self.service), supersedes_fact_id='f1'))
        check = recon_check(self.service)
        self.assertEqual(check['status'], 'MATCH')
        self.assertEqual(check['source_fact_ids'], ['f2'])

    def test_audit_computes_the_same_result_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ws'
            service = book(FileWorkspace.open(path))
            service.overlay_command(command(service, 'fact-1', body=payload(amount_krw=1)))
            report = audit_workspace(path)
            self.assertTrue(report['ok'])
            offline = next(c for c in report['recon']['checks'] if c['id'] == CHECK_ID)
            live = recon_check(service)
            self.assertEqual((offline['status'], offline['diagnostics'],
                              offline['source_fact_ids']),
                             ('ASSERTED_MISMATCH', ['OBSERVED_FACT_MISMATCH'], ['fact-1']))
            self.assertEqual(offline['claims'], live['claims'])
            self.assertEqual(report['recon']['status'], 'MATCHED')


class RestorationTests(unittest.TestCase):
    def build_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'ws'
        self.port = FileWorkspace.open(path)
        service = book(self.port)
        service.overlay_command(command(service, 'fact-1'))
        return path, service

    def write_doc(self, path, service, journal):
        document = json.loads((path / 'workspace.json').read_text())
        overlay_doc = document['overlay']
        overlay_doc['journal'] = journal
        state = overlay.fold(journal, len(service.machine.export_journal()))
        overlay_doc['overlay_state'] = {'digest': overlay.state_digest(state), 'state': state}
        overlay_doc['section_sha256'] = section_checksum(overlay_doc)
        (path / 'workspace.json').write_bytes(canonical_bytes(document))

    def assert_unreadable(self, path):
        self.port.close()
        restored = CapitalService(FileWorkspace.open(path))
        self.assertEqual(restored.workspace_status, 'WORKSPACE_UNREADABLE')
        report = audit_workspace(path)
        self.assertFalse(report['ok'])
        self.assertEqual(report['failed_check'], 'service_restore')

    def fact_entry(self, key, day, journal_length, **kw):
        return {'overlay_id': key, 'kind': KIND, 'after_journal_index': journal_length,
                'sim_day': day, 'payload': {**payload(), 'recorded_by_role': 'organizer', **kw}}

    def test_unknown_claim_closes_the_workspace(self):
        path, service = self.build_workspace()
        journal = copy.deepcopy(json.loads((path / 'workspace.json').read_text())['overlay']['journal'])
        journal[-1]['payload']['claim_id'] = 'ghost-claim'
        self.write_doc(path, service, journal)
        self.assert_unreadable(path)

    def test_chain_depth_closes_the_workspace(self):
        path, service = self.build_workspace()
        document = json.loads((path / 'workspace.json').read_text())
        journal = document['overlay']['journal']
        anchor = journal[-1]['after_journal_index']
        previous = 'fact-1'
        for index in range(5):
            journal = journal + [self.fact_entry(f'f{index}', DAY, anchor,
                                               supersedes_fact_id=previous)]
            previous = f'f{index}'
        self.write_doc(path, service, journal)
        self.assert_unreadable(path)

    def test_forward_and_self_supersession_close_the_workspace(self):
        for mutate in (
            lambda e: e['payload'].update(supersedes_fact_id='e-forward'),
            lambda e: e['payload'].update(supersedes_fact_id=e['overlay_id']),
        ):
            with self.subTest(mutate=mutate):
                path, service = self.build_workspace()
                document = json.loads((path / 'workspace.json').read_text())
                journal = document['overlay']['journal']
                journal = journal + [self.fact_entry('e-self', DAY,
                                                   journal[-1]['after_journal_index'])]
                mutate(journal[-1])
                document['overlay']['journal'] = journal
                document['overlay']['section_sha256'] = section_checksum(document['overlay'])
                (path / 'workspace.json').write_bytes(canonical_bytes(document))
                self.assert_unreadable(path)


class ExportIsolationTests(ServiceCase):
    def test_fact_writes_never_move_the_seven_legacy_sections(self):
        baseline = self.service.export_manifest()
        self.assertEqual(baseline['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V3')
        self.record('fact-1', body=payload(amount_krw=gross(self.service)))
        manifest = self.service.export_manifest()
        self.assertEqual(manifest['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V3')
        self.assertEqual(set(manifest['sections']), set(baseline['sections']))
        for name, section in baseline['sections'].items():
            if name == 'overlay':
                continue
            self.assertEqual(manifest['sections'][name]['body'], section['body'], name)
        body = manifest['sections']['overlay']['body']
        self.assertEqual([e['kind'] for e in body['journal']].count(KIND), 1)
        self.assertIn('observations', body['state'])
        recon_ids = [c['id'] for c in
                     manifest['sections']['reconciliation']['body']['checks']]
        self.assertNotIn(CHECK_ID, recon_ids)
        self.assertIn('overlay_fold_digest_equals_persisted', recon_ids)
        self.assertNotEqual(manifest['sections']['overlay']['sha256'],
                            baseline['sections']['overlay']['sha256'])
        self.assertTrue(verify_manifest(manifest)['ok'])

    def test_manifest_status_uses_the_full_reconciliation(self):
        self.record('fact-1', body=payload(amount_krw=1))
        manifest = self.service.export_manifest()
        self.assertEqual(manifest['status'], 'COMPLETE')
        recon = manifest['sections']['reconciliation']['body']
        self.assertNotIn(CHECK_ID, [c['id'] for c in recon['checks']])
        self.assertEqual(recon['status'], 'MATCHED')

    def test_facts_export_verifies_offline_with_fact_rows(self):
        self.record('fact-1')
        with tempfile.TemporaryDirectory() as tmp:
            after, index = None, 0
            while True:
                query = f'instance_id={self.service.instance_id}&limit=500'
                if after:
                    query += f'&after={after}'
                page = self.service.export_facts(query)
                Path(tmp, f'page-{index:04d}.json').write_bytes(canonical_bytes(page))
                index += 1
                after = page['next_cursor']
                if after is None:
                    break
            report = facts.verify_dir(tmp)
            self.assertTrue(report['ok'], report)


class ProjectionTests(unittest.TestCase):
    BASE = {
        'provenance': 'SYNTHETIC_FIXTURE', 'provider': 'sim-provider', 'account': 'sim-mid',
        'environment': 'fixture', 'profile_version': 'sim-v1', 'item_key': 'sim-capture-1',
        'payment_key': 'sim-payment', 'order_id': 'sim-order', 'operation': 'sim-operation',
        'kind': 'capture', 'amount': 500, 'currency': 'KRW', 'method': 'sim-card',
        'status': 'DONE', 'occurred_at': '2026-10-01T12:00:00', 'offset': None,
        'api_version': 'sim-api-v1', 'product': 'sim-product',
        'transmission': {'id': 'sim-delivery-1', 'raw_evidence_ref': 'sim-raw-1',
                         'received_at': 'sim-receive-1'},
    }
    BINDING = {'provider': 'sim-provider', 'account': 'sim-mid', 'environment': 'fixture',
               'profile_version': 'sim-v1', 'operation': 'sim-operation',
               'payment_key': 'sim-payment', 'order_id': 'sim-order'}

    def fold(self, facts, bindings=None):
        return observation.LocalFakeObservation().fold(
            copy.deepcopy(facts),
            bindings=copy.deepcopy([self.BINDING] if bindings is None else bindings))

    def fact(self, **kw):
        row = copy.deepcopy(self.BASE)
        row.update(kw)
        return row

    def project(self, facts, bindings=None):
        return project_fake(self.fold(facts, bindings), claim_id=CLAIM, sim_day=DAY,
                            captured_sim_day=DAY, instance_id='sim-instance')

    def test_matched_capture_maps_to_a_full_command(self):
        result = self.project([self.fact()])
        self.assertEqual(result['label'], 'SIMULATED')
        self.assertEqual(result['diagnostics'], [])
        (cmd,) = result['commands']
        event = self.fold([self.fact()])['event_items'][0]['event_item_id']
        suffix = event.split('sim-event-', 1)[1]
        self.assertEqual(len(suffix), 64)
        self.assertEqual(cmd['operation_id'], suffix)
        self.assertEqual(cmd['op'], OP)
        self.assertEqual(cmd['payload']['claimed_provider_ref'], suffix)
        self.assertEqual(cmd['payload']['order_ref'], 'sim-order')
        self.assertEqual(cmd['payload']['amount_krw'], 500)
        self.assertEqual(cmd['payload']['fact_class'], CLASS)
        self.assertNotIn('recorded_by_role', cmd['payload'])
        validate_payload(cmd['payload'])

    def test_redelivery_folds_to_one_command(self):
        result = self.project([self.fact(), self.fact()])
        self.assertEqual(len(result['commands']), 1)
        self.assertEqual(result['diagnostics'], [])

    def test_conflicts_never_record_regardless_of_delivery_order(self):
        other = self.fact(amount=600, transmission={'id': 'd2', 'raw_evidence_ref': 'r2',
                                                    'received_at': 't2'})
        for facts_ in ([self.fact(), other], [other, self.fact()]):
            with self.subTest(order=facts_[0]['amount']):
                result = self.project(facts_)
                self.assertEqual(result['commands'], [])
                (diag,) = result['diagnostics']
                self.assertEqual(diag['reason'], 'CONFLICT')
                self.assertIs(diag['recordable'], False)
                self.assertEqual(diag['label'], 'SIMULATED')

    def test_unmatched_binding_conflict_and_non_captures_are_diagnostics(self):
        result = self.project([self.fact()], bindings=[])
        self.assertEqual(result['commands'], [])
        self.assertEqual(result['diagnostics'][0]['reason'], 'UNMATCHED')
        bad_binding = dict(self.BINDING, order_id='sim-other-order')
        result = self.project([self.fact()], bindings=[bad_binding])
        self.assertEqual(result['diagnostics'][0]['reason'], 'BINDING_CONFLICT')
        for kw in ({'kind': 'refund'}, {'status': 'CANCELED'}):
            with self.subTest(kw=kw):
                result = self.project([self.fact(**kw)])
                self.assertEqual(result['commands'], [])
                self.assertEqual(result['diagnostics'][0]['reason'], 'NON_CAPTURE_OR_NOT_DONE')

    def test_malformed_event_ids_and_output_shape_fail(self):
        output = self.fold([self.fact()])
        for event_id in ('sim-event-' + 'g' * 64, 'x' * 64, 'sim-event-', 12):
            with self.subTest(event_id=event_id):
                broken = copy.deepcopy(output)
                broken['event_items'][0]['event_item_id'] = event_id
                with self.assertRaises(FactError):
                    project_fake(broken, claim_id=CLAIM, sim_day=DAY,
                                 captured_sim_day=DAY, instance_id='i')
        for mutation in (lambda o: o.update(applied=True),
                         lambda o: o.update(identity_profile='other'),
                         lambda o: o.update(label='REAL')):
            with self.subTest(mutation=mutation):
                broken = copy.deepcopy(output)
                mutation(broken)
                with self.assertRaises(FactError):
                    project_fake(broken, claim_id=CLAIM, sim_day=DAY,
                                 captured_sim_day=DAY, instance_id='i')

    def test_string_boundaries_and_currency(self):
        long_ok = 'sim-' + 'x' * 60
        result = self.project([self.fact(order_id=long_ok)],
                              bindings=[dict(self.BINDING, order_id=long_ok)])
        self.assertEqual(len(result['commands']), 1)
        for order_id in ('sim-' + 'x' * 61, 'real-order', 'sim-'):
            with self.subTest(order_id=order_id):
                binding = [dict(self.BINDING, order_id=order_id)]
                with self.assertRaises(FactError):
                    self.project([self.fact(order_id=order_id)], bindings=binding)
        output = self.fold([self.fact()])
        output['event_items'][0]['normalized_fact']['currency'] = 'USD'
        with self.assertRaises(FactError):
            project_fake(output, claim_id=CLAIM, sim_day=DAY, captured_sim_day=DAY,
                         instance_id='i')


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def call(self, method, path, body=None, token=None):
        headers = {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if token is not None:
            headers['X-Capital-Token'] = token
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=json.dumps(body) if body is not None else None,
                       headers=headers)
        response = client.getresponse()
        raw = response.read()
        client.close()
        return response.status, json.loads(raw.decode())

    def token_for(self, role):
        status, body = self.call('GET', '/api/state')
        token = body['local_token']
        if role in (None, 'organizer'):
            return token
        status, body = self.call('POST', '/api/session', {'role': role}, token=token)
        self.assertEqual(status, 200, body)
        return body['local_token']

    def test_role_matrix_over_http(self):
        status, state = self.call('GET', '/api/state')
        instance = state['instance_id']
        body = {'instance_id': instance, 'operation_id': 'fact-http-1', 'op': OP,
                'at_sim_day': 0, 'payload': payload(
                    sim_day=0, effective_sim_day=0, captured_sim_day=0)}
        for role, expected in (('agent', 'FACT_AGENT_FORBIDDEN'),
                               ('auditor', 'FACT_ROLE_FORBIDDEN'),
                               ('observer', 'FACT_ROLE_FORBIDDEN')):
            with self.subTest(role=role):
                status, reply = self.call('POST', '/api/overlay/commands', body,
                                          token=self.token_for(role))
                self.assertEqual((status, reply['error']), (403, expected))
        status, reply = self.call('POST', '/api/overlay/commands', body,
                                  token=self.token_for('organizer'))
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply['entry']['fact_class'], CLASS)
        status, reply = self.call('GET', '/api/reconciliation',
                                  token=self.token_for('auditor'))
        self.assertEqual(status, 200)
        self.assertIn(CHECK_ID, [c['id'] for c in reply['checks']])


if __name__ == '__main__':
    unittest.main()
