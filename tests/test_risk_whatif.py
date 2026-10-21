"""Read-only named what-if scenarios over the risk and covenant folds.

SIMULATED_WHATIF. The fixed catalog re-folds the same integer inputs as GET /api/risk
under one stated assumption; nothing is applied, enforced or written.
"""
import importlib.util
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital import margin, risk, risk_whatif
from capital.auth import ROLES, route_permission
from capital.server import make_server, route_label
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace
from capital.terms import DecisionNoteTermsPolicy, TERMS_NOT_BOUND
from tests.facade_schema import load_contract, validate
from tests.test_margin import drawn_then_refunded
from tests.test_overlay import seed, tick

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'risk_scenario_vectors.py'
ARTIFACT = ROOT / 'tests' / 'vectors' / 'risk_scenarios.json'

_spec = importlib.util.spec_from_file_location('risk_scenario_vectors', SCRIPT)
vectors_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vectors_script)

IDS = tuple(risk_whatif.CATALOG)
MISSING_NOTE = ROOT / 'docs' / 'decisions' / 'NO_SUCH_NOTE.md'


class CatalogTests(unittest.TestCase):
    def test_fixed_named_set_is_static_text_only(self):
        self.assertEqual(IDS, ('largest-advance-default', 'refund-shock',
                               'all-watch-breach', 'concentration-cap-hit'))
        rows = risk_whatif.catalog()
        self.assertEqual([row['scenario_id'] for row in rows], list(IDS))
        for row in rows:
            self.assertIs(row['applied'], False)
            self.assertIs(row['enforced'], False)


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = seed.build_service()
        cls.baseline_risk = cls.service.risk()
        cls.baseline_cov = cls.service.covenants()
        cls.bodies = {name: cls.service.risk_scenarios(name) for name in IDS}

    def test_envelope_marks_the_whatif_and_never_applies(self):
        for name in IDS:
            body = self.bodies[name]
            self.assertEqual(body['mode'], 'SIMULATED_WHATIF')
            self.assertEqual(body['scenario']['scenario_id'], name)
            self.assertIn('SIMULATED', body['label'])
            for flag in ('applied', 'enforced', 'policy_adopted',
                         'funds_executed', 'workspace_mutated', 'write_authorized'):
                self.assertIs(body[flag], False, (name, flag))
            self.assertEqual(body['accounting_policy'], 'SYNTHETIC_UNADOPTED')
            self.assertTrue(body['whatif_digest'])
            for row in body['covenants']['advances']:
                self.assertIs(row['applied'], False)
                self.assertIs(row['enforced'], False)

    def test_reconciles_scenario_totals_back_to_the_live_risk_read(self):
        for name in IDS:
            body = self.bodies[name]
            recon = body['reconciliation']
            self.assertEqual(recon['baseline_outstanding_krw'],
                             self.baseline_risk['totals']['outstanding_krw'], name)
            self.assertEqual(recon['baseline_risk_digest'], self.baseline_risk['risk_digest'], name)
            self.assertEqual(recon['baseline_covenant_digest'],
                             self.baseline_cov['covenant_digest'], name)
            self.assertEqual(body['risk']['totals']['outstanding_krw'],
                             recon['scenario_outstanding_krw'], name)
            self.assertEqual(recon['scenario_outstanding_krw'],
                             recon['baseline_outstanding_krw'] + recon['assumption_delta_krw'], name)
            self.assertIs(recon['matched'], True, name)
            self.assertIs(body['risk']['reconciliation']['matched'], True, name)
            self.assertIs(body['covenants']['reconciliation']['matched'], True, name)

    def test_deterministic_across_instances(self):
        other = seed.build_service()
        self.assertNotEqual(other.instance_id, self.service.instance_id)
        for name in IDS:
            self.assertEqual(other.risk_scenarios(name)['whatif_digest'],
                             self.bodies[name]['whatif_digest'], name)
        self.assertEqual(other.risk_scenarios()['scenarios'],
                         self.service.risk_scenarios()['scenarios'])

    def test_largest_advance_default_marks_the_biggest_open_advance(self):
        body = self.bodies['largest-advance-default']
        self.assertIs(body['evaluated'], True)
        self.assertEqual(body['target'], {'advance_id': 'sim-unbound', 'outstanding_krw': 15_000})
        self.assertEqual(body['reconciliation']['assumption_delta_krw'], 0)
        row = next(item for item in body['covenants']['advances']
                   if item['advance_id'] == 'sim-unbound')
        self.assertEqual(row['status'], 'BREACH')
        self.assertIn('DEFAULTED', [item['code'] for item in row['reasons']])
        self.assertIn('RESERVE_CLASS_ESCALATED', [item['code'] for item in row['reasons']])
        aging = {item['id']: item for item in body['risk']['overdue_aging']['rows']}
        self.assertEqual(aging['DEFAULTED']['outstanding_krw'], 45_000)
        # The live fold is untouched: the real advance stays DRAWN.
        live = next(item for item in self.service.covenants()['advances']
                    if item['advance_id'] == 'sim-unbound')
        self.assertEqual(live['phase'], 'DRAWN')

    def test_refund_shock_reuses_the_pinned_shock_set(self):
        body = self.bodies['refund-shock']
        self.assertIs(body['evaluated'], True)
        detail = body['assumption_detail']
        self.assertEqual(detail['shock_bps'], risk.SHOCKS_BPS[-1])
        self.assertEqual(detail['shock_set'], risk.SHOCK_SET)
        self.assertEqual(detail['shifted_advances'], 1)  # only sim-unbound is DRAWN and assessed
        self.assertEqual(body['reconciliation']['assumption_delta_krw'], 0)

    def test_refund_shock_files_hypothetical_calls_on_a_breaching_book(self):
        _source, service = drawn_then_refunded()
        self.assertEqual(service.risk()['stress']['baseline']['margin_call_count'], 1)
        body = service.risk_scenarios('refund-shock')
        self.assertIs(body['evaluated'], True)
        self.assertEqual(body['assumption_detail']['hypothetical_calls'], 1)
        row = next(item for item in body['covenants']['advances']
                   if item['advance_id'] == 'sim-a')
        self.assertIn('MARGIN_CALL_ACTIVE', [item['code'] for item in row['reasons']])
        self.assertEqual(row['margin']['state'], margin.CALLED)
        # The hypothetical call is never recorded: the real row still awaits a tick.
        self.assertEqual(service.overlay_state()['advances'][0]['margin']['state'],
                         'BREACH_AWAITING_TICK')
        self.assertEqual(
            [entry['kind'] for entry in service.overlay_entries
             if entry['kind'].startswith('margin')], [])

    def test_all_watch_breach_flags_every_open_advance_past_maturity(self):
        body = self.bodies['all-watch-breach']
        self.assertIs(body['evaluated'], True)
        self.assertEqual(body['assumption_detail']['projected_sim_day'], 61)
        self.assertEqual(body['risk']['sim_day'], 61)
        watch = {row['advance_id']: row for row in body['covenants']['watch_list']}
        self.assertEqual(set(watch), {'sim-defaulted', 'sim-unbound'})
        for row in watch.values():
            codes = [item['code'] for item in row['reasons']]
            self.assertIn('PAST_MATURITY', codes)
            self.assertIn('RESERVE_CLASS_ESCALATED', codes)
            self.assertEqual(row['status'], 'BREACH')

    def test_concentration_cap_hit_breaches_the_tightest_cap(self):
        body = self.bodies['concentration-cap-hit']
        self.assertIs(body['evaluated'], True)
        caps = self.baseline_risk['concentration']['caps']
        self.assertEqual(caps['status'], 'BOUND')
        tightest = min(caps['rows'], key=lambda row: row['remaining_krw'])
        detail = body['assumption_detail']
        self.assertEqual(detail['cap'], tightest['cap'].removesuffix('_cap_krw'))
        row = next(item for item in body['covenants']['advances']
                   if item['advance_id'] == 'sim-whatif-cap')
        self.assertIn('U4_CAP_BREACHED', [item['code'] for item in row['reasons']])
        scenario_caps = {item['cap']: item
                         for item in body['risk']['concentration']['caps']['rows']}
        self.assertTrue(scenario_caps[tightest['cap']]['breached'])
        self.assertEqual(body['reconciliation']['assumption_delta_krw'],
                         row['outstanding_krw'])
        self.assertEqual(detail['injected_outstanding_krw'], row['outstanding_krw'])

    def test_unevaluated_scenarios_still_fold_and_reconcile(self):
        service = CapitalService()
        for name in IDS:
            body = service.risk_scenarios(name)
            self.assertIs(body['evaluated'], False, name)
            self.assertIsNotNone(body['unevaluated_reason'], name)
            self.assertIsNone(body['target'], name)
            self.assertIs(body['reconciliation']['matched'], True, name)
            self.assertEqual(body['reconciliation']['scenario_outstanding_krw'], 0)


class UnknownIdTests(unittest.TestCase):
    def test_unknown_id_is_400_named_with_the_catalog(self):
        service = CapitalService()
        with self.assertRaises(ApiError) as caught:
            service.risk_scenarios('no-such-scenario')
        self.assertEqual((caught.exception.code, caught.exception.status),
                         ('SCENARIO_UNKNOWN', 400))
        self.assertEqual(caught.exception.detail['scenarios'], list(IDS))

    def test_unknown_id_fails_before_the_terms_check(self):
        service = CapitalService(terms=DecisionNoteTermsPolicy(MISSING_NOTE))
        with self.assertRaises(ApiError) as caught:
            service.risk_scenarios('no-such-scenario')
        self.assertEqual((caught.exception.code, caught.exception.status),
                         ('SCENARIO_UNKNOWN', 400))


class NotBoundTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService(terms=DecisionNoteTermsPolicy(MISSING_NOTE))

    def test_missing_note_returns_not_bound_with_no_numbers(self):
        body = self.service.risk_scenarios('largest-advance-default')
        self.assertEqual((body['status'], body['reason']), ('NOT_BOUND', TERMS_NOT_BOUND))
        self.assertIs(body['evaluated'], False)
        self.assertIsNone(body['whatif_digest'])
        self.assertEqual(body['scenario']['scenario_id'], 'largest-advance-default')
        for key in ('risk', 'covenants', 'reconciliation', 'target',
                    'assumption_detail', 'scenarios', 'unevaluated_reason'):
            self.assertNotIn(key, body)
        validate(body, {'$ref': '#/definitions/whatif_scenario'}, load_contract())

    def test_index_still_names_the_fixed_set(self):
        body = self.service.risk_scenarios()
        self.assertEqual((body['status'], body['reason']), ('NOT_BOUND', TERMS_NOT_BOUND))
        self.assertEqual([row['scenario_id'] for row in body['scenarios']], list(IDS))


class ReadOnlyTests(unittest.TestCase):
    def test_reads_change_no_state_or_workspace_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileWorkspace.open(tmp)
            try:
                service = seed.build_service(storage)
                tick(service, 'w-1', 0, 5)
                path = next(Path(tmp).iterdir())
                frozen = (path.read_bytes(), service.machine.state_digest(),
                          len(service.receipts),
                          json.dumps(service.overlay_entries, sort_keys=True),
                          service.machine.canonical_state())
                service.risk_scenarios()
                for name in IDS:
                    service.risk_scenarios(name)
                after = (path.read_bytes(), service.machine.state_digest(),
                         len(service.receipts),
                         json.dumps(service.overlay_entries, sort_keys=True),
                         service.machine.canonical_state())
                self.assertEqual(frozen, after)
            finally:
                storage.close()


class VectorTests(unittest.TestCase):
    def test_artifact_is_regenerated_byte_identical(self):
        self.assertEqual(vectors_script.build_artifact(), ARTIFACT.read_bytes())

    def test_pinned_scenarios_match_the_live_service(self):
        artifact = json.loads(ARTIFACT.read_text(encoding='utf-8'))
        self.assertEqual(artifact['format'], 'KIX_CAPITAL_RISK_WHATIF_VECTORS_V1')
        self.assertNotIn('instance_id', json.dumps(artifact))
        service = seed.build_service()
        for name in IDS:
            live = service.risk_scenarios(name)
            self.assertEqual(artifact['scenarios'][name]['whatif_digest'],
                             live['whatif_digest'], name)
            self.assertEqual(artifact['scenarios'][name]['reconciliation']['matched'], True)


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        _, state = cls.call('/api/state')
        cls.tokens = {'organizer': state['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.session(role, cls.tokens['organizer'])
        cls.contract = load_contract()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, path, token=None):
        headers = {} if token is None else {'X-Capital-Token': token}
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request('GET', path, headers=headers)
        response = client.getresponse()
        body = json.loads(response.read())
        client.close()
        return response.status, body

    @classmethod
    def session(cls, role, token):
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request('POST', '/api/session', body=json.dumps({'role': role}).encode(),
                       headers={'Content-Type': 'application/json', 'X-Capital-Token': token})
        response = client.getresponse()
        result = json.loads(response.read())
        client.close()
        return result['local_token']

    def route(self, path):
        return next(item for item in self.contract['routes']
                    if item['method'] == 'GET' and item['path'] == path)

    def test_route_labels_and_permission(self):
        for path in ('/api/risk/scenarios', '/api/risk/scenarios/refund-shock',
                     '/api/risk/scenarios/a/b'):
            self.assertEqual(route_label(path), '/api/risk/scenarios', path)
            self.assertEqual(route_permission(path), 'projection:read', path)

    def test_route_role_gate(self):
        for role in ('organizer', 'auditor'):
            status, body = self.call('/api/risk/scenarios', self.tokens[role])
            self.assertEqual(status, 200, role)
            self.assertEqual([row['scenario_id'] for row in body['scenarios']], list(IDS))
            status, body = self.call('/api/risk/scenarios/largest-advance-default',
                                     self.tokens[role])
            self.assertEqual((status, body['mode']), (200, 'SIMULATED_WHATIF'), role)
        for role in ('observer', 'agent'):
            for path in ('/api/risk/scenarios', '/api/risk/scenarios/refund-shock'):
                status, body = self.call(path, self.tokens[role])
                self.assertEqual((status, body['error'], body['permission']),
                                 (403, 'ROLE_FORBIDDEN', 'projection:read'), (role, path))

    def test_unknown_id_is_a_400_with_the_catalog(self):
        status, body = self.call('/api/risk/scenarios/no-such', self.tokens['organizer'])
        self.assertEqual((status, body['error']), (400, 'SCENARIO_UNKNOWN'))
        self.assertEqual(body['scenarios'], list(IDS))
        validate(body, self.contract['definitions']['error_envelope'], self.contract)

    def test_responses_validate_against_the_facade_schema(self):
        status, body = self.call('/api/risk/scenarios', self.tokens['organizer'])
        self.assertEqual(status, 200)
        validate(body, self.route('/api/risk/scenarios')['response'], self.contract)
        for name in IDS:
            status, body = self.call(f'/api/risk/scenarios/{name}', self.tokens['organizer'])
            self.assertEqual(status, 200, name)
            validate(body, self.route('/api/risk/scenarios/{id}')['response'], self.contract)


if __name__ == '__main__':
    unittest.main()
