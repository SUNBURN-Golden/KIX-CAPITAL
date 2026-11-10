"""SIMULATED shared-cap accounting and local coherent-cut guarantees."""
import copy
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from capital import overlay, portfolio_snapshot, shared_caps, slices
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.protocol import CreditMachine
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace
from capital.terms import DecisionNoteTermsPolicy
from tests.facade_schema import SchemaError, load_contract, validate
from tests.test_claim_slices import advance, recourse, seed
from tests.test_overlay import draw_book, run, tick
from tests.test_portfolio_snapshot import ObservedLock, sha


def freeze(service):
    """Detach synthetic replay setup into the supported immutable adapter."""
    views = FixtureViews.__new__(FixtureViews)
    for key in ('rows', 'profiles', 'beneficiaries', 'projection_ids'):
        setattr(views, key, copy.deepcopy(getattr(service.fixtures, key)))
    producer = PinnedFsmProducer(views, CreditMachine.restore(service.machine.export_journal(), views))
    service.producer = producer
    return service


def synthetic_caps(service, **values):
    # Explicit test-only limits; no decision note or product policy is changed.
    service.terms.items['underwriting_depth']['value'].update(values)
    service.slice_policy['caps'].update(values)


class SharedCapsTests(unittest.TestCase):
    def schema(self, body):
        validate(body, {'$ref': '#/definitions/shared_caps'}, load_contract())

    def test_empty_bound_and_sorted_union_including_terminal_slices(self):
        s = CapitalService()
        body = s.shared_caps()
        self.assertEqual((body['status'], body['beneficiaries']), ('BOUND', []))
        self.assertEqual(body['portfolio']['combined_policy_exposure_krw'], 0)
        self.schema(body)
        source, s = seed.book()
        seed.register(s, 'terminal', 1000, 'demo-alpha-arena')
        seed.post(s, 'void_slice', 'void', slice_id='terminal', reason='OPERATOR_WITHDRAWN')
        seed.register(s, 'proposed', 1000, 'demo-beta-festival')
        seed.register(s, 'active', 3000, 'demo-gamma-annex')
        seed.open_slice(s, 'active')
        advance(s, 2000, 'demo-delta-small')
        body = freeze(s).shared_caps()
        self.assertEqual([r['beneficiary_role'] for r in body['beneficiaries']],
                         ['demo-org-alpha', 'demo-org-beta', 'demo-org-delta', 'demo-org-gamma'])
        self.assertEqual(body['portfolio']['advance_principal_krw'], 2000)
        self.assertEqual(body['portfolio']['counted_slice_face_krw'], 3000)
        for key in ('advance_principal_krw', 'counted_slice_face_krw', 'combined_policy_exposure_krw'):
            self.assertEqual(body['portfolio'][key], sum(r[key] for r in body['beneficiaries']))
        self.schema(body)

    def test_all_lifecycle_states_agree_with_registry_and_u4(self):
        source, s = seed.book()
        advance(s, 1000)
        seed.register(s, 'slice-a', 10000)
        for status in ('PROPOSED', 'OPEN', 'IMPAIRED', 'RESOLVED'):
            if status == 'OPEN':
                seed.open_slice(s, 'slice-a')
            elif status == 'IMPAIRED':
                seed.refund(source, 'demo-delta-small', source.view('demo-delta-small')['claim']['gross'])
                seed.post(s, 'impair_slice', 'impair', slice_id='slice-a', reason='REFUND_REDUCED_LINE')
            elif status == 'RESOLVED':
                seed.distribute(source, 'demo-delta-mid')
                recourse(s, 'slice-a', 10000)
                seed.post(s, 'resolve_slice', 'resolve', slice_id='slice-a', resolution='RECOURSE_SATISFIED')
            with self.subTest(status=status):
                # Keep the mutable source only for lifecycle setup, never projection reads.
                mutable_producer = s.producer
                freeze(s)
                risk_before = s.risk()
                report = s.shared_caps()
                self.assertEqual(report['status'], 'BOUND', report)
                expected = 10000 if status in ('OPEN', 'IMPAIRED') else 0
                self.assertEqual(report['portfolio']['counted_slice_face_krw'], expected)
                registry = s.overlay_slices()['slices'][0]
                self.assertEqual(registry['status'], status)
                self.assertEqual(registry['exposure_krw'], expected)
                record = s.underwrite('sim-slice', s.instance_id, 'organizer')
                own = report['beneficiaries'][0]
                self.assertEqual(record['caps_remaining']['beneficiary_aggregate_krw'], own['remaining_capacity_krw'])
                self.assertEqual(record['caps_remaining']['portfolio_krw'], report['portfolio']['remaining_capacity_krw'])
                self.assertEqual(s.risk(), risk_before)
                self.schema(report)
                s.producer = mutable_producer
        seed.register(s, 'void', 1000, 'demo-alpha-arena')
        seed.post(s, 'void_slice', 'void-it', slice_id='void', reason='OPERATOR_WITHDRAWN')
        self.assertEqual(freeze(s).shared_caps()['portfolio']['counted_slice_face_krw'], 0)

    def test_partial_service_recourse_late_distribution_and_defaulted_principal(self):
        source, s = seed.book()
        c = 'demo-delta-mid'
        gross = source.view(c)['claim']['gross']
        seed.replay(source, c, 'low-cash', 'commit_settlement', movement_id='sim-held',
                    gross=gross, amount=2000, fee=0, tax=0, held=gross-2000, adjustment=0)
        advance(s, 1000, c)
        seed.register(s, 'partial', 10000, c)
        seed.open_slice(s, 'partial')
        seed.replay(source, c, 'distribution', 'apply_distribution', order=['organizer', 'platform'])
        seed.refund(source, c, source.view(c)['claim']['obligations'][0]['outstanding'])
        seed.post(s, 'impair_slice', 'impair', slice_id='partial', reason='REFUND_REDUCED_LINE')
        self.assertEqual(run(s, 'default', 'sim-slice', 'default')['outcome'], 'ACCEPTED')
        seed.distribute(source, 'demo-delta-small')
        recourse(s, 'partial', 3000, source='demo-delta-small')
        row = s.overlay_slices()['slices'][0]
        self.assertEqual((row['served_krw'], row['exposure_krw']), (2000, 5000))
        report = freeze(s).shared_caps()
        self.assertEqual(report['status'], 'BOUND', report)
        self.assertEqual(report['portfolio']['advance_principal_krw'], 1000)
        self.assertEqual(report['portfolio']['counted_slice_face_krw'], 5000)
        # Pure helper regression: late service after recourse saturates at zero.
        obs = slices.observation(s.fixtures.view(c)['claim'], ['organizer'])
        obs['lines']['organizer']['distributed'] = 20000
        state = {'claim_slices': {'slices': {'partial': row}}}
        self.assertEqual(slices.exposures(state, {c: obs}, row['beneficiary_role'])['slice_exposure_portfolio_krw'], 0)
        self.schema(report)

    def test_exact_cap_and_one_won_over_match_admission_and_candidate_u4(self):
        for cap_name in ('beneficiary_aggregate_cap_krw', 'portfolio_cap_krw'):
            for cap in (11000, 10999):
                with self.subTest(cap_name=cap_name, cap=cap):
                    source, s = seed.book()
                    advance(s, 1000)
                    synthetic_caps(s, **{cap_name: cap})
                    seed.register(s, 'boundary', 10000)
                    if cap == 11000:
                        seed.open_slice(s, 'boundary')
                    else:
                        with self.assertRaises(ApiError) as caught:
                            seed.open_slice(s, 'boundary')
                        self.assertEqual(caught.exception.code, 'SLICE_CAP_EXCEEDED')
                        # A decided cap can change after admission. Synthetic only.
                        seed.post(s, 'void_slice', 'void-boundary', slice_id='boundary', reason='OPERATOR_WITHDRAWN')
                        synthetic_caps(s, **{cap_name: 11000})
                        seed.register(s, 'boundary-later', 10000)
                        seed.open_slice(s, 'boundary-later', 'open-later')
                        synthetic_caps(s, **{cap_name: cap})
                    body = freeze(s).shared_caps()
                    row = body['beneficiaries'][0] if cap_name.startswith('beneficiary') else body['portfolio']
                    self.assertEqual(row['combined_policy_exposure_krw'], 11000)
                    self.assertEqual(row['remaining_capacity_krw'], cap-11000)
                    self.assertEqual(row['cap_check'], 'PASS' if cap == 11000 else 'FAIL')
                    self.assertEqual(row['utilization_permille'], 11000*1000//cap)
                    record = s.underwrite('sim-slice', s.instance_id, 'organizer')
                    u4 = next(c for c in record['checks'] if c['id'] == 'U4_CONCENTRATION')
                    self.assertEqual(u4['outcome'], row['cap_check'])
                    # An offered candidate adds its incremental amount to this report.
                    advance(s, 1, 'demo-delta-small', name='sim-candidate', draw=False)
                    candidate = s.underwrite('sim-candidate', s.instance_id, 'organizer')
                    name = 'beneficiary_aggregate_krw' if cap_name.startswith('beneficiary') else 'portfolio_krw'
                    self.assertEqual(candidate['caps_remaining'][name], row['remaining_capacity_krw']-1)
                    self.schema(body)

    def test_missing_malformed_and_stale_policy_is_not_bound_even_empty(self):
        mutations = [lambda s: setattr(s, 'slice_policy', None),
                     lambda s: s.slice_policy['caps'].update(portfolio_cap_krw=0),
                     lambda s: s.slice_policy.update(payees={}),
                     lambda s: s.slice_policy.update(rates={'bad': True}),
                     lambda s: s.slice_policy.update(terms_version='stale'),
                     lambda s: s.terms.items['underwriting_depth'].update(mark='PENDING'),
                     lambda s: s.terms.items['underwriting_depth']['value'].update(portfolio_cap_krw=True),
                     lambda s: s.terms.items['underwriting_depth'].update(value=[]),
                     lambda s: s.terms.items['interest_rate']['value'].update(tiers=[{}]),
                     lambda s: s.slice_policy.update(bounds=None),
                     lambda s: setattr(s, 'overlay_bounds', None),
                     lambda s: setattr(s.terms, 'items', []),
                     lambda s: s.slice_policy.update(sizing_rates=None),
                     lambda s: s.slice_policy.update(sizing_rates={'unknown': 0}),
                     lambda s: s.fixtures.beneficiaries.update({'sim-committed': 'missing'})]
        for mutate in mutations:
            s = CapitalService()
            mutate(s)
            body = s.shared_caps()
            self.assertEqual(body['status'], 'NOT_BOUND', body)
            self.assertIsNone(body['beneficiaries'])
            self.assertIsNone(body['portfolio'])
            self.assertTrue(body['cut']['policy_inputs_digest'])
            self.schema(body)
        s = CapitalService(terms=DecisionNoteTermsPolicy('/tmp/kix-missing-shared-caps-note'))
        self.assertEqual(s.shared_caps()['status'], 'NOT_BOUND')

    def test_unsupported_adapters_are_rejected_without_calls(self):
        s = CapitalService()
        class Unsupported:
            def snapshot_inputs(self):
                raise AssertionError('unsupported adapter invoked')
        s.producer = Unsupported()
        self.assertEqual(s.shared_caps()['reasons'], ['COHERENT_SNAPSHOT_UNSUPPORTED'])
        s = CapitalService()
        s.producer.snapshot_inputs = None
        self.assertEqual(s.shared_caps()['reasons'], ['COHERENT_SNAPSHOT_UNSUPPORTED'])
        source, s = seed.book()
        self.assertEqual(s.shared_caps()['reasons'], ['IMMUTABLE_FIXTURES_REQUIRED'])
        s = CapitalService()
        s.terms = object()
        self.assertEqual(s.shared_caps()['reasons'], ['FROZEN_TERMS_UNSUPPORTED'])

    def test_read_only_file_workspace_and_damaged_storage(self):
        with tempfile.TemporaryDirectory() as tmp, FileWorkspace.open(tmp) as store:
            s = CapitalService(storage=store)
            draw_book(s)
            seed.register(s, 'persisted', 1000, 'demo-alpha-arena')
            seed.open_slice(s, 'persisted')
            tick(s, 'clock', 0, 3)
            before = copy.deepcopy((s._frozen(), s.case_fixtures, s.fixtures.__dict__, s.terms.__dict__, s.slice_policy))
            files = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            with patch.object(store, 'save', side_effect=AssertionError('read must never save')), patch.object(
                    s, 'risk', side_effect=AssertionError('must not call public risk')), patch.object(
                    s, 'underwrite', side_effect=AssertionError('must not call public underwriting')):
                bodies = [s.shared_caps() for _ in range(4)]
            self.assertEqual(bodies, [bodies[0]]*4)
            self.assertEqual(bodies[0]['status'], 'BOUND', bodies[0])
            self.assertEqual(files, {p.name: p.read_bytes() for p in Path(tmp).iterdir()})
            self.assertEqual(before, (s._frozen(), s.case_fixtures, s.fixtures.__dict__, s.terms.__dict__, s.slice_policy))
            self.assertEqual(CapitalService(storage=store).shared_caps(), bodies[0])
            store.path.write_text('{broken')
            body = s.shared_caps()
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertTrue(body['cut']['state_digest'])
            self.schema(body)

    def test_independent_digests_detachment_and_metadata_exclusion(self):
        s = CapitalService()
        draw_book(s)
        tick(s, 'clock', 0, 3)
        body = s.shared_caps()
        frozen = portfolio_snapshot.FrozenInputs.capture(s.producer.snapshot_inputs(), s.receipts,
                    s.case_fixtures, s.overlay_entries, s.terms, s.overlay_bounds)
        data = frozen.detached()
        cut = body['cut']
        self.assertEqual(cut['state_digest'], sha(json.loads(s.machine.canonical_state())))
        self.assertEqual(cut['fixtures_digest'], sha(s.fixtures.rows))
        self.assertEqual(cut['overlay_state_digest'], overlay.state_digest(overlay.fold(s.overlay_entries)))
        self.assertEqual(cut['policy_inputs_digest'], sha({'format': shared_caps.FORMAT, 'version': 1,
                            'underwriting': data['policy'], 'slice_policy': s.slice_policy}))
        self.assertEqual(cut['inputs_digest'], sha({'format': shared_caps.FORMAT, 'version': 1,
            'cut': {k:v for k,v in cut.items() if k != 'inputs_digest'}, 'fixtures': data['producer']['fixtures'],
            'case_fixtures': s.case_fixtures, 'overlay_entries': s.overlay_entries}))
        s.terms.path = Path('/tmp/unused-shared-cap-path')
        s.receipts['a-draw']['receipt']['instance_id'] = 'other-session'
        s._persist()
        self.assertEqual(s.shared_caps(), body)
        detached = frozen.detached()
        detached['producer']['fixtures']['rows'].clear()
        self.assertEqual(shared_caps.build(frozen, copy.deepcopy(s.slice_policy)), body)
        s.slice_policy['caps']['portfolio_cap_krw'] += 1
        after = s.shared_caps()
        self.assertNotEqual(cut['policy_inputs_digest'], after['cut']['policy_inputs_digest'])
        self.assertNotEqual(cut['inputs_digest'], after['cut']['inputs_digest'])

    def test_closed_schema_and_required_labels_in_both_alternatives_and_rows(self):
        s = CapitalService()
        draw_book(s)
        bound = s.shared_caps()
        s.slice_policy = None
        unbound = s.shared_caps()
        for body in (bound, unbound):
            self.schema(body)
            paths = [()] + ([('beneficiaries', 0), ('portfolio',)] if body['status'] == 'BOUND' else [])
            for path in paths:
                for key in slices.labels():
                    for remove in (True, False):
                        changed = copy.deepcopy(body)
                        node = changed
                        for part in path: node = node[part]
                        if remove: del node[key]
                        else: node[key] = 'invalid'
                        with self.subTest(path=path, key=key, remove=remove), self.assertRaises(SchemaError):
                            self.schema(changed)
                changed = copy.deepcopy(body)
                node = changed
                for part in path: node = node[part]
                node['unknown'] = 1
                with self.assertRaises(SchemaError): self.schema(changed)
        for changed in ({**unbound, 'portfolio': bound['portfolio']}, {**bound, 'beneficiaries': None}):
            with self.assertRaises(SchemaError): self.schema(changed)

    def test_reader_writer_cuts_are_entirely_before_or_after(self):
        for op in ('repay', 'clock'):
            for reader_first in (True, False):
                with self.subTest(op=op, reader_first=reader_first):
                    s = CapitalService()
                    draw_book(s)
                    before = s.shared_caps()
                    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
                    s.lock = ObservedLock(s.lock, 'writer' if reader_first else 'reader', attempted)
                    results, errors = {}, []
                    def writer():
                        return run(s, 'repay', 'sim-a', 'repay', amount=1, sequence=1) if op == 'repay' else tick(s, 'clock', 0, 3)
                    target, attr = (shared_caps, 'build') if reader_first else (s, '_persist')
                    original = getattr(target, attr)
                    def paused(*args, **kw):
                        result = original(*args, **kw)
                        entered.set()
                        if not release.wait(5): raise AssertionError('barrier timed out')
                        return result
                    def invoke(name, call):
                        try: results[name] = call()
                        except BaseException as exc: errors.append(exc)
                    with patch.object(target, attr, paused):
                        first_name = 'reader' if reader_first else 'writer'
                        second_name = 'writer' if reader_first else 'reader'
                        calls = {'reader': s.shared_caps, 'writer': writer}
                        first = threading.Thread(name=first_name, target=invoke, args=(first_name, calls[first_name]))
                        second = threading.Thread(name=second_name, target=invoke, args=(second_name, calls[second_name]))
                        try:
                            first.start()
                            self.assertTrue(entered.wait(5))
                            second.start()
                            self.assertTrue(attempted.wait(5))
                            self.assertNotIn(second_name, results)
                        finally:
                            release.set()
                            first.join(5)
                            if second.ident: second.join(5)
                        self.assertFalse(first.is_alive() or second.is_alive())
                    self.assertEqual(errors, [])
                    after = s.shared_caps()
                    self.assertNotEqual(before['cut']['inputs_digest'], after['cut']['inputs_digest'])
                    self.assertEqual(results['reader'], before if reader_first else after)


class SharedCapsRouteTests(unittest.TestCase):
    def test_authorization_precedes_query_and_strict_route_schema(self):
        server = make_server(0)
        s = server.service
        for role in ('auditor', 'observer', 'agent'): s.authorizer.bind_role(role)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        def request(suffix='', role=None):
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                headers = {} if role is None else {'X-Capital-Token': s.authorizer.token_for(role)}
                client.request('GET', '/api/risk/shared-caps' + suffix, headers=headers)
                response = client.getresponse()
                return response.status, json.loads(response.read())
            finally: client.close()
        try:
            for role in (None, 'organizer', 'auditor'):
                code, body = request(role=role)
                self.assertEqual((code, body['status']), (200, 'BOUND'))
                validate(body, {'$ref':'#/definitions/shared_caps'}, load_contract())
            for role in ('observer', 'agent'):
                code, body = request('?bad=1', role)
                self.assertEqual((code, body['error']), (403, 'ROLE_FORBIDDEN'))
            for suffix in ('?bad=1', '?a=&a=', '?bare', '?instance_id=x'):
                code, body = request(suffix)
                self.assertEqual((code, body['error']), (400, 'INVALID_ARGUMENTS'))
            self.assertEqual(request('/child')[0], 404)
            s.slice_policy = None
            code, body = request()
            self.assertEqual((code, body['status']), (200, 'NOT_BOUND'))
            validate(body, {'$ref':'#/definitions/shared_caps'}, load_contract())
        finally:
            server.shutdown(); server.server_close(); worker.join(5)
            self.assertFalse(worker.is_alive())


if __name__ == '__main__': unittest.main()
