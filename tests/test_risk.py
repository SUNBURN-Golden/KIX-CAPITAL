"""Portfolio risk analytics: exposure buckets, concentration, reserve and refund-shock stress.

SIMULATED. Expected values are recomputed here from the CAPITAL-TERMS-V1 block with Fraction
arithmetic, never read back from the code under test, except the one literal table
(150/500/2500/10000 bps) that pins the note itself.
"""
import ast
import json
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

from capital import risk
from capital.auth import ROLES
from capital.server import make_server
from capital.service import CapitalService
from capital.store import FileWorkspace
from capital.terms import DecisionNoteTermsPolicy
from tests.facade_schema import load_contract, validate
from tests.test_margin import BASE, drawn_then_refunded
from tests.test_overlay import draw_book, row, seed, terms_value, tick

ROOT = Path(__file__).resolve().parents[1]
RISK_PY = ROOT / 'capital' / 'risk.py'
APP_JS = ROOT / 'capital' / 'static' / 'app.js'
RESERVE = terms_value('reserve')['provision_bps_of_outstanding']
CAPS = terms_value('underwriting_depth')
STANDARD = terms_value('term')['standard_term_days']
SHOCKS = [500, 1000, 2500, 5000]
EXPECTED_LITERALS = {0, 1, 2, 30, 60, 90, 500, 1000, 2500, 5000}


def by_id(rows, key='id'):
    return {item[key]: item for item in rows}


def fake_subject(advance_id, outstanding, role='organizer-a', phase='DRAWN', gate='MOCK_COMMIT_OBSERVED',
                 amount=None, draw_day=0):
    """A drawn subject shaped like CapitalService._overlay_subjects, on a synthetic claim."""
    return {
        'advance_id': advance_id, 'gate': gate, 'draw_day': draw_day, 'principal': outstanding,
        'case': {'phase': phase, 'amount': outstanding if amount is None else amount,
                 'beneficiary_role': role, 'outstanding_exposure': outstanding},
        'claim': {'refund_face': 0, 'obligations': [{'payee': 'organizer', 'outstanding': 100_000}]},
    }


def margin_subject(subject, rate=8500):
    return {**subject, 'margin': {'payees': ['organizer'], 'advance_rate_bps': rate}}


def build(subjects, sim_day=0, projection=None, margins=None):
    terms = DecisionNoteTermsPolicy()
    total = sum(item['principal'] for item in subjects)
    return risk.build(subjects, [] if margins is None else margins, terms=terms, sim_day=sim_day,
                      projection_outstanding_krw=total if projection is None else projection)


class NoteLiteralTests(unittest.TestCase):
    def test_reserve_table_and_caps_are_the_decided_note_values(self):
        self.assertEqual(RESERVE, {'T1_COMMIT_OBSERVED': 150, 'T2_UNBOUND': 500,
                                   'PAST_DUE_ANY_TIER': 2500, 'DEFAULTED': 10000})
        self.assertEqual(STANDARD, 60)


class BucketTests(unittest.TestCase):
    def test_maturity_bucket_edges(self):
        table = {0: '0-30', 1: '0-30', 30: '0-30', 31: '31-60', 60: '31-60', 61: '61-90', 90: '61-90',
                 91: '>90', 400: '>90'}
        for remaining, bucket in table.items():
            self.assertEqual(risk.maturity_bucket(remaining), bucket, remaining)

    def test_aging_edges_are_exclusive_classes(self):
        table = {(60, 60): 'NOT_DUE', (0, 60): 'NOT_DUE', (61, 60): '1-30', (90, 60): '1-30', (91, 60): '31-60',
                 (120, 60): '31-60', (121, 60): '61-90', (150, 60): '61-90', (151, 60): '>90'}
        for (day, maturity), bucket in table.items():
            self.assertEqual(risk.aging_class(day, maturity, 'DRAWN'), bucket, (day, maturity))
        self.assertEqual(risk.aging_class(0, 60, 'DEFAULTED'), 'DEFAULTED')
        self.assertEqual(risk.aging_class(999, 60, 'DEFAULTED'), 'DEFAULTED')

    def test_every_bucket_sums_to_the_total_for_a_mixed_book(self):
        # draw days spread the maturities over every edge when read on sim_day 100
        subjects = [fake_subject(f'sim-{index}', 1000 + index, draw_day=day)
                    for index, day in enumerate((0, 10, 40, 41, 60, 100, 130, 200))]
        body = build(subjects, sim_day=100)
        total = sum(item['principal'] for item in subjects)
        self.assertEqual(body['totals']['outstanding_krw'], total)
        for section in (body['maturity_buckets'], body['overdue_aging']):
            self.assertEqual(sum(item['outstanding_krw'] for item in section['rows']), total)
        self.assertEqual(sum(item['outstanding_krw'] for item in body['by_tier']), total)
        self.assertTrue(body['reconciliation']['matched'])
        maturity = by_id(body['maturity_buckets']['rows'])
        # remaining = draw_day + 60 - 100 clamped at zero: -40,-30,0,1,20,60,90,160
        self.assertEqual([maturity[name]['advances'] for name in ('0-30', '31-60', '61-90', '>90')], [5, 1, 1, 1])
        aging = by_id(body['overdue_aging']['rows'])
        # late = 40,30,0 | not due | 31-60 once
        self.assertEqual(aging['1-30']['advances'], 1)
        self.assertEqual(aging['31-60']['advances'], 1)
        self.assertEqual(aging['NOT_DUE']['advances'], 6)

    def test_projection_mismatch_is_reported_not_hidden(self):
        body = build([fake_subject('sim-a', 1000)], projection=999)
        self.assertFalse(body['reconciliation']['matched'])


class ConcentrationTests(unittest.TestCase):
    def test_hhi_matches_an_independent_fraction_recompute(self):
        book = {'role-a': [3000, 1500], 'role-b': [2500], 'role-c': [1000, 500, 250]}
        subjects = [fake_subject(f'sim-{role}-{index}', value, role=role)
                    for role, values in book.items() for index, value in enumerate(values)]
        body = build(subjects)
        groups = [sum(values) for values in book.values()]
        total = sum(groups)
        expected = sum(Fraction(group, total) ** 2 for group in groups) * 1000
        self.assertEqual(body['concentration']['hhi_permille'], expected.numerator // expected.denominator)
        shares = by_id(body['concentration']['beneficiaries'], 'role')
        for role, values in book.items():
            self.assertEqual(shares[role]['share_permille'], sum(values) * 1000 // total)

    def test_single_holder_is_one_thousand_and_empty_book_has_no_hhi(self):
        self.assertEqual(build([fake_subject('sim-a', 500)])['concentration']['hhi_permille'], 1000)
        empty = build([])
        self.assertIsNone(empty['concentration']['hhi_permille'])
        self.assertEqual(empty['totals']['outstanding_krw'], 0)

    def test_cap_utilization_reads_the_u4_caps_from_the_note(self):
        single, beneficiary, portfolio = (CAPS['single_advance_cap_krw'], CAPS['beneficiary_aggregate_cap_krw'],
                                          CAPS['portfolio_cap_krw'])
        # one beneficiary over its aggregate cap, no single advance over its cap
        big = single
        count = beneficiary // single + 1
        subjects = [fake_subject(f'sim-{index}', big, role='role-a') for index in range(count)]
        subjects.append(fake_subject('sim-other', 7, role='role-b'))
        caps = by_id(build(subjects)['concentration']['caps']['rows'], 'cap')
        self.assertEqual(caps['single_advance_cap_krw']['used_krw'], big)
        self.assertEqual(caps['single_advance_cap_krw']['utilization_permille'], big * 1000 // single)
        self.assertFalse(caps['single_advance_cap_krw']['breached'])
        used = big * count
        self.assertEqual(caps['beneficiary_aggregate_cap_krw']['used_krw'], used)
        self.assertEqual(caps['beneficiary_aggregate_cap_krw']['utilization_permille'], used * 1000 // beneficiary)
        self.assertTrue(caps['beneficiary_aggregate_cap_krw']['breached'])
        self.assertEqual(caps['beneficiary_aggregate_cap_krw']['remaining_krw'], beneficiary - used)
        self.assertEqual(caps['portfolio_cap_krw']['used_krw'], used + 7)
        self.assertEqual(caps['portfolio_cap_krw']['cap_krw'], portfolio)
        self.assertEqual(caps['portfolio_cap_krw']['utilization_permille'], (used + 7) * 1000 // portfolio)


class ReserveTests(unittest.TestCase):
    def test_requirement_is_the_sum_of_per_advance_floors(self):
        subjects = [fake_subject('sim-t1', 10_001, gate='MOCK_COMMIT_OBSERVED'),
                    fake_subject('sim-t2', 3_999, gate='UNBOUND'),
                    fake_subject('sim-def', 7_777, phase='DEFAULTED')]
        body = build(subjects)
        expected = 10_001 * 150 // 10000 + 3_999 * 500 // 10000 + 7_777 * 10000 // 10000
        self.assertEqual(body['reserve']['requirement_krw'], expected)
        self.assertTrue(body['reserve']['complete'])
        self.assertFalse(body['reserve']['applied'])
        self.assertIn('not an accounting policy', body['reserve']['label'])
        self.assertEqual(sum(item['provision_krw'] for item in body['reserve']['rows']), expected)

    def test_sum_of_floors_differs_from_floor_of_sum(self):
        subjects = [fake_subject(f'sim-{index}', 19, gate='UNBOUND') for index in range(3)]
        body = build(subjects)
        self.assertEqual(body['reserve']['requirement_krw'], 0)
        self.assertEqual(57 * 500 // 10000, 2)

    def test_past_due_class_and_aging_follow_the_clock(self):
        service = CapitalService()
        draw_book(service, amount=90_000)
        before = service.risk()
        self.assertEqual(before['reserve']['requirement_krw'], 90_000 * 150 // 10000)
        tick(service, 't-1', 0, 61)
        late = service.risk()
        self.assertEqual(late['reserve']['requirement_krw'], 90_000 * 2500 // 10000)
        self.assertEqual(by_id(late['reserve']['rows'], 'bucket')['PAST_DUE_ANY_TIER']['outstanding_krw'], 90_000)
        self.assertEqual(by_id(late['overdue_aging']['rows'])['1-30']['outstanding_krw'], 90_000)
        self.assertEqual(by_id(late['maturity_buckets']['rows'])['0-30']['outstanding_krw'], 90_000)
        tick(service, 't-2', 61, 151)
        self.assertEqual(by_id(service.risk()['overdue_aging']['rows'])['>90']['outstanding_krw'], 90_000)

    def test_unrated_exposure_is_reported_and_incomplete(self):
        subjects = [fake_subject('sim-none', 1234, gate='SOME_UNKNOWN_GATE')]
        body = build(subjects)
        self.assertEqual(by_id(body['by_tier'], 'tier')['NOT_APPLICABLE']['outstanding_krw'], 1234)
        self.assertEqual(body['reserve']['unrated_outstanding_krw'], 1234)
        self.assertFalse(body['reserve']['complete'])
        self.assertEqual(body['reserve']['requirement_krw'], 0)


class StressTests(unittest.TestCase):
    def stress(self, outstandings):
        subjects = [fake_subject(f'sim-{index}', value) for index, value in enumerate(outstandings)]
        return build(subjects, margins=[margin_subject(item) for item in subjects])['stress']

    def test_fixed_shocks_and_stepwise_counts(self):
        stress = self.stress([90_000, 80_000, 70_000, 50_000])
        self.assertEqual(stress['shocks_bps'], SHOCKS)
        self.assertEqual([row['shock_bps'] for row in stress['rows']], SHOCKS)
        self.assertEqual(stress['baseline']['shock_bps'], 0)
        self.assertEqual(stress['baseline']['margin_call_count'], 1)
        self.assertEqual([row['margin_call_count'] for row in stress['rows']], [1, 2, 3, 4])
        self.assertTrue(stress['monotone'])
        self.assertFalse(stress['applied'])
        # eligible 100,000 each: floor(95,000*8500/10000) = 80,750 base after a 5% shock
        first = stress['rows'][0]
        self.assertEqual(first['shocked_eligible_face_krw'], 4 * 95_000)
        self.assertEqual(first['shortfall_krw'], 90_000 - 95_000 * 8500 // 10000)
        self.assertEqual(stress['rows'][3]['called_outstanding_krw'], 90_000 + 80_000 + 70_000 + 50_000)

    def test_count_is_non_decreasing_over_a_grid(self):
        for outstanding in range(0, 100_001, 1_250):
            for rate in (0, 5000, 8500, 10000):
                subject = fake_subject('sim-a', outstanding)
                stress = build([subject], margins=[margin_subject(subject, rate)])['stress']
                counts = [stress['baseline']['margin_call_count']] + [r['margin_call_count'] for r in stress['rows']]
                self.assertEqual(counts, sorted(counts), (outstanding, rate))
                self.assertTrue(stress['monotone'])
                shortfalls = [r['shortfall_krw'] for r in stress['rows']]
                self.assertEqual(shortfalls, sorted(shortfalls))

    def test_defaulted_and_unassessable_advances_are_counted_not_guessed(self):
        live = fake_subject('sim-live', 60_000)
        stress = build([live, fake_subject('sim-def', 30_000, phase='DEFAULTED'),
                        fake_subject('sim-blind', 20_000)], margins=[margin_subject(live)])['stress']
        self.assertEqual(stress['coverage'], {'drawn_open_advances': 2, 'assessed': 1, 'unassessed': 1})

    def test_baseline_equals_the_overlay_margin_breach_on_a_disposable_book(self):
        _, breached = drawn_then_refunded(amount=BASE + 1)
        stress = breached.risk()['stress']
        self.assertEqual(stress['baseline']['margin_call_count'], 1)
        self.assertEqual(breached.overlay_state()['advances'][0]['margin']['state'], 'BREACH_AWAITING_TICK')
        _, healthy = drawn_then_refunded(amount=BASE)
        stress = healthy.risk()['stress']
        self.assertEqual(stress['baseline']['margin_call_count'], 0)
        self.assertEqual(healthy.overlay_state()['advances'][0]['margin']['state'], 'WITHIN_BASE')
        self.assertEqual([row['margin_call_count'] for row in stress['rows']], [1, 1, 1, 1])
        # a hypothetical call never reaches the overlay
        self.assertEqual([e['kind'] for e in healthy.overlay_entries if e['kind'].startswith('margin')], [])


class DemoBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = seed.build_service()
        cls.body = cls.service.risk()

    def test_seeded_demo_matches_hand_derivation_and_the_projection(self):
        body = self.body
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual(body['totals']['outstanding_krw'], 45_000)
        tiers = by_id(body['by_tier'], 'tier')
        self.assertEqual((tiers['T1']['outstanding_krw'], tiers['T2']['outstanding_krw']), (30_000, 15_000))
        projected = sum(item['outstanding'] for item in self.service.projection()['read_model']['advances'])
        self.assertEqual(body['reconciliation']['projection_outstanding_krw'], projected)
        self.assertEqual(sum(item['outstanding_krw'] for item in body['maturity_buckets']['rows']), projected)
        self.assertTrue(body['reconciliation']['matched'])
        self.assertEqual(body['reserve']['requirement_krw'], 30_000 * 10000 // 10000 + 15_000 * 500 // 10000)
        self.assertEqual(body['concentration']['hhi_permille'], 1000)
        self.assertEqual(by_id(body['overdue_aging']['rows'])['DEFAULTED']['outstanding_krw'], 30_000)
        self.assertEqual(body['sim_day'], 0)
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['policy_adopted'], False)
        self.assertEqual(body['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        self.assertIn('SIMULATED', body['label'])

    def test_maturity_matches_the_overlay_row_and_the_clock_moves_buckets(self):
        service = CapitalService()
        draw_book(service, amount=50_000)
        maturity = row(service)['maturity_day']
        self.assertEqual(maturity, STANDARD)
        place = lambda: next(item['id'] for item in service.risk()['maturity_buckets']['rows']
                             if item['outstanding_krw'] == 50_000)
        self.assertEqual(place(), '31-60')
        tick(service, 'm-1', 0, maturity - 31)
        self.assertEqual(place(), '31-60')
        tick(service, 'm-2', maturity - 31, maturity - 30)
        self.assertEqual(place(), '0-30')

    def test_digest_is_stable_and_instance_independent(self):
        other = seed.build_service()
        self.assertNotEqual(other.instance_id, self.service.instance_id)
        self.assertEqual(other.risk()['risk_digest'], self.body['risk_digest'])
        pinned = json.loads((ROOT / 'tests' / 'golden' / 'demo.json').read_text(encoding='utf-8'))['risk']
        self.assertEqual(pinned, risk.pin(self.body))
        self.assertNotIn('instance_id', json.dumps(pinned))


class ReadOnlyTests(unittest.TestCase):
    def test_reading_risk_changes_no_state_and_no_workspace_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileWorkspace.open(tmp)
            try:
                service = seed.build_service(storage)
                tick(service, 'r-1', 0, 5)
                path = next(Path(tmp).iterdir())
                frozen = (path.read_bytes(), service.machine.state_digest(), len(service.receipts),
                          json.dumps(service.overlay_entries, sort_keys=True), service.machine.canonical_state())
                for _ in range(2):
                    service.risk()
                after = (path.read_bytes(), service.machine.state_digest(), len(service.receipts),
                         json.dumps(service.overlay_entries, sort_keys=True), service.machine.canonical_state())
                self.assertEqual(frozen, after)
            finally:
                storage.close()

    def test_missing_note_is_not_bound_and_carries_no_numbers(self):
        service = CapitalService(terms=DecisionNoteTermsPolicy(ROOT / 'docs' / 'decisions' / 'NO_SUCH_NOTE.md'))
        body = service.risk()
        self.assertEqual(body['status'], 'NOT_BOUND')
        self.assertIsNone(body['risk_digest'])
        for section in ('totals', 'by_tier', 'maturity_buckets', 'concentration', 'reserve', 'stress'):
            self.assertNotIn(section, body)


class SourceTests(unittest.TestCase):
    def test_module_is_integer_only_with_a_closed_literal_set(self):
        tree = ast.parse(RISK_PY.read_text(encoding='utf-8'))
        literals = set()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.Div)
            if isinstance(node, ast.Name):
                self.assertNotEqual(node.id, 'float')
            if isinstance(node, ast.Constant):
                self.assertNotIsInstance(node.value, float)
                if type(node.value) is int:
                    literals.add(node.value)
        self.assertEqual(literals - EXPECTED_LITERALS, set())
        for value in (150, 8500, 5000 + 3500, 700, 1300):
            self.assertNotIn(value, literals)
        for value in CAPS.values():
            if type(value) is int:
                self.assertNotIn(value, literals)

    def test_ui_never_uses_innerhtml_and_names_the_risk_panel(self):
        source = APP_JS.read_text(encoding='utf-8')
        self.assertNotIn('innerHTML', source)
        self.assertIn('renderRisk', source)
        self.assertIn('id="risk"', (ROOT / 'capital' / 'static' / 'index.html').read_text(encoding='utf-8'))


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        _, state = cls.call('GET', '/api/state')
        cls.tokens = {'organizer': state['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.call('POST', '/api/session', {'role': role}, cls.tokens['organizer'])[1]['local_token']
        cls.contract = load_contract()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, method, path, body=None, token=None):
        headers = {}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            client.request(method, path, body=payload, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read().decode('utf-8'))
        finally:
            client.close()

    def test_roles_and_schema(self):
        schema = next(route for route in self.contract['routes'] if route['method'] == 'GET' and route['path'] == '/api/risk')
        for role in ('organizer', 'auditor'):
            status, payload = self.call('GET', '/api/risk', token=self.tokens[role])
            self.assertEqual(status, 200, role)
            validate(payload, schema['response'], self.contract)
            self.assertEqual(payload['mode'], 'SIMULATED_RISK_ANALYTICS')
        for role in ('observer', 'agent'):
            status, payload = self.call('GET', '/api/risk', token=self.tokens[role])
            self.assertEqual((status, payload['error'], payload['permission']), (403, 'ROLE_FORBIDDEN', 'projection:read'), role)
        self.assertEqual(self.call('GET', '/api/risk')[0], 200)  # no token is the default organizer

    def test_the_read_changes_nothing_and_cannot_be_posted(self):
        before = self.call('GET', '/api/state')[1]
        self.call('GET', '/api/risk', token=self.tokens['organizer'])
        self.call('GET', '/api/risk?unused=1', token=self.tokens['auditor'])
        self.call('GET', '/api/risk', token=self.tokens['observer'])
        after = self.call('GET', '/api/state')[1]
        self.assertEqual(before['state_digest'], after['state_digest'])
        self.assertEqual(before['cases'], after['cases'])
        status, _payload = self.call('POST', '/api/risk', {}, self.tokens['organizer'])
        self.assertIn(status, (404, 405))

    def test_unknown_field_in_a_response_is_rejected_by_the_schema(self):
        from tests.facade_schema import SchemaError
        schema = next(route for route in self.contract['routes'] if route['method'] == 'GET' and route['path'] == '/api/risk')
        _, payload = self.call('GET', '/api/risk', token=self.tokens['organizer'])
        tainted = json.loads(json.dumps(payload))
        tainted['totals']['extra'] = 1
        with self.assertRaises(SchemaError):
            validate(tainted, schema['response'], self.contract)


if __name__ == '__main__':
    unittest.main()
