"""Cash-ladder forecast: per-advance legs, 0-7/8-30/31-60/61-90/91+ buckets, exact floor once per bucket.

SIMULATED. Expected values are recomputed here from the CAPITAL-TERMS-V1 block with Fraction
arithmetic, never read back from the code under test.
"""
import copy
import importlib.util
import json
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

from capital import forecast, risk
from capital.auth import ROLES, route_permission
from capital.server import make_server, route_label
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace
from capital.terms import DecisionNoteTermsPolicy
from tests.facade_schema import load_contract, validate
from tests.test_overlay import TERMS_NOTE, draw_book, seed, terms_value, tier, tick
from tests.test_risk import fake_subject

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'forecast_vectors.py'
ARTIFACT = ROOT / 'tests' / 'vectors' / 'forecast_vectors.json'

_spec = importlib.util.spec_from_file_location('forecast_vectors', SCRIPT)
vectors_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vectors_script)

TERM = terms_value('term')
INTEREST = terms_value('interest_rate')
DAY_COUNT = int(INTEREST['day_count'].split('_')[1])


def expected_legs(outstanding, draw_day, expected, bps):
    """Independent recomputation of the three legs for one drawn advance."""
    if expected is None:
        term_days = TERM['standard_term_days']
    else:
        raw = expected - draw_day + TERM['settlement_slack_days']
        term_days = min(max(raw, TERM['min_term_days']), TERM['max_term_days'])
    maturity = draw_day + term_days
    interest = Fraction(outstanding * term_days * bps, 10000 * DAY_COUNT)
    return term_days, maturity, interest


def legs_of(row):
    return {leg['kind']: leg for leg in row['legs']}


class BucketEdgeTests(unittest.TestCase):
    def test_offsets_land_in_the_fixed_buckets(self):
        table = {0: '0-7', 1: '0-7', 7: '0-7', 8: '8-30', 30: '8-30', 31: '31-60',
                 60: '31-60', 61: '61-90', 90: '61-90', 91: '91+', 400: '91+'}
        for offset, name in table.items():
            self.assertEqual(forecast.bucket_id(100 + offset, 100), name, offset)
        # A leg dated in the past counts as zero days ahead.
        self.assertEqual(forecast.bucket_id(40, 100), '0-7')

    def test_empty_and_unusable_books(self):
        body = forecast.build([], terms=DecisionNoteTermsPolicy(), sim_day=0)
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual(body['advances'], [])
        self.assertTrue(all(row['legs'] == 0 for row in body['buckets']['rows']))
        self.assertTrue(body['reconciliation']['matched'])
        self.assertEqual(body['reconciliation']['outstanding_principal_krw'], 0)

        skipped = forecast.build([fake_subject('sim-paid', 0), fake_subject('sim-none', 7, gate='NOPE')],
                                 terms=DecisionNoteTermsPolicy(), sim_day=0)
        for row, reason in zip(skipped['advances'],
                               ('NO_OUTSTANDING_PRINCIPAL', 'tier not applicable')):
            self.assertEqual((row['status'], row['reason']), ('NOT_APPLICABLE', reason))
            self.assertEqual(sorted(row), ['advance_id', 'phase', 'reason', 'status'])
        self.assertEqual(skipped['reconciliation']['outstanding_principal_krw'], 0)


class LadderTests(unittest.TestCase):
    def build(self, subjects, sim_day=0, expected=None):
        return forecast.build(subjects, terms=DecisionNoteTermsPolicy(), sim_day=sim_day,
                              expected_settlement_cash_day=expected)

    def test_three_legs_match_an_independent_recompute(self):
        subjects = [fake_subject('sim-t1', 90_000), fake_subject('sim-t2', 15_000, gate='UNBOUND')]
        body = self.build(subjects, sim_day=10, expected=45)
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual(body['assumptions'], list(forecast.ASSUMPTIONS))
        rows = {row['advance_id']: row for row in body['advances']}
        bps = {'sim-t1': tier('T1')['all_in_bps_annual'], 'sim-t2': tier('T2')['all_in_bps_annual']}
        for advance_id, subject in zip(('sim-t1', 'sim-t2'), subjects):
            row = rows[advance_id]
            term_days, maturity, interest = expected_legs(subject['principal'], 0, 45, bps[advance_id])
            self.assertEqual((row['term_days'], row['term_source'], row['maturity_day']),
                             (term_days, 'settlement_linked', maturity))
            legs = legs_of(row)
            self.assertEqual(sorted(legs), ['CONTRACT_INTEREST', 'PRINCIPAL', 'SETTLEMENT_CASH_IN'])
            self.assertEqual((legs['SETTLEMENT_CASH_IN']['day'], legs['SETTLEMENT_CASH_IN']['status'],
                              legs['SETTLEMENT_CASH_IN']['bucket']),
                             (45, 'SCHEDULED', forecast.bucket_id(45, 10)))
            self.assertEqual(Fraction(legs['SETTLEMENT_CASH_IN']['exact']), subject['principal'])
            self.assertEqual(legs['SETTLEMENT_CASH_IN']['assumption'],
                             'SETTLEMENT_ARRIVES_IN_FULL_ON_EXPECTED_DAY')
            self.assertEqual((legs['PRINCIPAL']['day'], legs['PRINCIPAL']['bucket']),
                             (maturity, forecast.bucket_id(maturity, 10)))
            self.assertEqual(Fraction(legs['PRINCIPAL']['exact']), subject['principal'])
            self.assertEqual(Fraction(legs['CONTRACT_INTEREST']['exact']), interest)
            self.assertEqual(legs['CONTRACT_INTEREST']['day'], maturity)

    def test_standard_term_when_no_settlement_day_and_leg_unscheduled(self):
        body = self.build([fake_subject('sim-t1', 90_000)])
        row = body['advances'][0]
        self.assertEqual((row['term_days'], row['term_source']), (TERM['standard_term_days'], 'standard'))
        leg = legs_of(row)['SETTLEMENT_CASH_IN']
        self.assertEqual((leg['day'], leg['bucket'], leg['status']),
                         (None, None, 'EXPECTED_DAY_NOT_PROVIDED'))
        self.assertEqual(body['reconciliation']['settlement_exact'], '0/1')
        self.assertTrue(body['reconciliation']['matched'])

    def test_bucket_sums_floor_once_and_reconcile(self):
        subjects = [fake_subject('sim-a', 10_001, draw_day=0), fake_subject('sim-b', 7_777, draw_day=3)]
        body = self.build(subjects, sim_day=0, expected=20)
        buckets = {row['id']: row for row in body['buckets']['rows']}
        settlement = sum(Fraction(row['settlement_exact']) for row in buckets.values())
        repayment = sum(Fraction(row['repayment_exact']) for row in buckets.values())
        outstanding = sum(item['principal'] for item in subjects)
        interest = sum(expected_legs(item['principal'], item['draw_day'], 20,
                                   tier('T1')['all_in_bps_annual'])[2] for item in subjects)
        self.assertEqual(settlement, Fraction(outstanding))
        self.assertEqual(repayment, Fraction(outstanding) + interest)
        recon = body['reconciliation']
        self.assertEqual(recon['outstanding_principal_krw'], outstanding)
        self.assertEqual(Fraction(recon['contract_interest_exact']), interest)
        self.assertEqual(Fraction(recon['repayment_exact']), repayment)
        self.assertTrue(recon['matched'])
        # Each bucket floors its own summed exact once: the leg sum of floors is not the floor.
        for row in buckets.values():
            self.assertEqual(row['expected_cash_krw'],
                             Fraction(row['expected_exact']).numerator
                             // Fraction(row['expected_exact']).denominator)

    def test_past_maturity_lands_in_the_first_bucket(self):
        body = self.build([fake_subject('sim-old', 50_000, draw_day=0)], sim_day=200)
        row = body['advances'][0]
        self.assertEqual(row['maturity_day'], TERM['standard_term_days'])
        for leg in row['legs']:
            if leg['day'] is None:
                self.assertIsNone(leg['bucket'])
                continue
            self.assertEqual(leg['bucket'], '0-7', leg['kind'])

    def test_no_tier_and_no_principal_rows_carry_no_numbers(self):
        body = self.build([fake_subject('sim-x', 0), fake_subject('sim-y', 5, gate='UNKNOWN_GATE')])
        self.assertEqual(body['reconciliation']['outstanding_principal_krw'], 0)
        self.assertEqual([row['status'] for row in body['advances']],
                         ['NOT_APPLICABLE', 'NOT_APPLICABLE'])

    def test_posted_accrued_interest_is_informational(self):
        service = CapitalService()
        draw_book(service, amount=90_000)
        tick(service, 'f-1', 0, 6)
        body = service.forecast(service.instance_id)
        posted = body['reconciliation']['posted_accrued_interest_krw']
        # posted floor of the ACT/365 exact accrual over 6 days
        exact = Fraction(90_000 * 6 * tier('T1')['all_in_bps_annual'], 10000 * DAY_COUNT)
        self.assertEqual(posted, exact.numerator // exact.denominator)
        self.assertNotEqual(posted, Fraction(body['reconciliation']['contract_interest_exact']))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        draw_book(self.service, amount=60_000)

    def test_read_only_invariant_and_session_guard(self):
        before = (copy.deepcopy(self.service.receipts), self.service.machine.state_digest(),
                  json.dumps(self.service.overlay_entries, sort_keys=True))
        body = self.service.forecast(self.service.instance_id)
        self.assertEqual(body['status'], 'BOUND')
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertIs(body['write_authorized'], False)
        self.assertEqual(body['observed_state_digest'], before[1])
        self.assertEqual((self.service.receipts, self.service.machine.state_digest(),
                          json.dumps(self.service.overlay_entries, sort_keys=True)),
                         (before[0], before[1], before[2]))
        with self.assertRaises(ApiError) as caught:
            self.service.forecast('other')
        self.assertEqual(caught.exception.args[0], 'SESSION_CHANGED')
        for bad in (-1, 'x', 1.5, True, 1000000):
            with self.assertRaises(ApiError):
                self.service.forecast(self.service.instance_id, expected_settlement_cash_day=bad)

    def test_workspace_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileWorkspace.open(tmp)
            try:
                service = CapitalService(storage)
                draw_book(service, amount=50_000)
                tick(service, 'w-1', 0, 5)
                path = next(Path(tmp).iterdir())
                frozen = (path.read_bytes(), service.machine.state_digest(), len(service.receipts),
                          json.dumps(service.overlay_entries, sort_keys=True))
                service.forecast(service.instance_id, expected_settlement_cash_day=40)
                service.forecast(service.instance_id)
                self.assertEqual((path.read_bytes(), service.machine.state_digest(),
                                  len(service.receipts),
                                  json.dumps(service.overlay_entries, sort_keys=True)), frozen)
            finally:
                storage.close()

    def test_missing_note_is_not_bound_with_no_numeric_sections(self):
        service = CapitalService(terms=DecisionNoteTermsPolicy(ROOT / 'docs' / 'decisions' / 'NO_SUCH_NOTE.md'))
        body = service.forecast(service.instance_id, expected_settlement_cash_day=10)
        self.assertEqual((body['status'], body['reason']), ('NOT_BOUND', 'terms not bound'))
        self.assertIsNone(body['forecast_digest'])
        for key in ('advances', 'buckets', 'reconciliation', 'assumptions'):
            self.assertNotIn(key, body)
        validate(body, {'$ref': '#/definitions/terms_forecast'}, load_contract())


class DemoBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = seed.build_service()

    def test_seeded_book_pin_and_reconciliation(self):
        body = self.service.forecast(self.service.instance_id,
                                     expected_settlement_cash_day=vectors_script.EXPECTED_DAY)
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual([row['advance_id'] for row in body['advances']],
                         ['sim-closed', 'sim-defaulted', 'sim-unbound'])
        rows = {row['advance_id']: row for row in body['advances']}
        self.assertEqual(rows['sim-closed']['status'], 'NOT_APPLICABLE')
        self.assertEqual((rows['sim-defaulted']['tier'], rows['sim-unbound']['tier']), ('T1', 'T2'))
        self.assertEqual(rows['sim-defaulted']['phase'], 'DEFAULTED')  # NO_DEFAULT assumption covers it
        self.assertTrue(body['reconciliation']['matched'])
        self.assertEqual(body['reconciliation']['outstanding_principal_krw'], 45_000)
        artifact = json.loads(ARTIFACT.read_text(encoding='utf-8'))
        pinned = artifact['forecasts']['with_settlement_day']
        self.assertNotIn('instance_id', json.dumps(artifact))
        self.assertEqual(pinned['forecast_digest'], body['forecast_digest'])
        self.assertEqual(forecast.pin(body), forecast.pin(json.loads(json.dumps(pinned))))

    def test_artifact_is_regenerated_byte_identical(self):
        self.assertEqual(vectors_script.build_artifact(), ARTIFACT.read_bytes())


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        _, state = cls.call('/api/state')
        cls.instance = state['instance_id']
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

    def test_roles_params_and_schema(self):
        url = '/api/terms/portfolio/forecast'
        self.assertEqual(route_label(url), '/api/terms')
        self.assertEqual(route_permission(url), 'projection:read')
        route = next(item for item in self.contract['routes']
                     if item['path'] == url)
        for role in ('organizer', 'auditor'):
            status, body = self.call(f'{url}?instance_id={self.instance}&expected_settlement_cash_day=45',
                                     self.tokens[role])
            self.assertEqual(status, 200, role)
            validate(body, route['response'], self.contract)
            self.assertEqual(body['mode'], forecast.MODE)
        for role in ('observer', 'agent'):
            status, body = self.call(f'{url}?instance_id={self.instance}', self.tokens[role])
            self.assertEqual((status, body['error'], body['permission']),
                             (403, 'ROLE_FORBIDDEN', 'projection:read'), role)
        self.assertEqual(self.call(f'{url}?instance_id={self.instance}')[0], 200)

    def test_only_documented_query_parameters_are_accepted(self):
        url = '/api/terms/portfolio/forecast'
        for suffix in ('&extra=1', '&mode=simulation', '&expected_settlement_cash_day=x',
                       '&expected_settlement_cash_day=-1', '&expected_settlement_cash_day=1&expected_settlement_cash_day=2'):
            status, body = self.call(f'{url}?instance_id={self.instance}{suffix}', self.tokens['organizer'])
            self.assertEqual((status, body['error']), (400, 'INVALID_ARGUMENTS'), suffix)
        status, body = self.call(f'{url}?instance_id=other', self.tokens['organizer'])
        self.assertEqual((status, body['error']), (409, 'SESSION_CHANGED'))

    def test_literal_route_beats_the_advance_id_fallthrough(self):
        status, body = self.call('/api/terms/portfolio/forecast', self.tokens['auditor'])
        # missing instance_id is a session mismatch, never an advance lookup
        self.assertEqual((status, body['error']), (409, 'SESSION_CHANGED'))


if __name__ == '__main__':
    unittest.main()
