"""CAPITAL-DEMO-BOOK-V1 fixtures: pinned-FSM provenance and U1-U6 cap binding.

Every demo claim view is replayed through a fresh pinned SettlementMachine in
this file and byte-compared to the stored fixture: a hand-set field or a table
that drifts from the parsed decision note fails. Cap, threshold and rate values
are always read from CAPITAL_FINANCIAL_TERMS.md at runtime, never from literals.
"""
import json
import re
import unittest
from pathlib import Path

from capital.producer import DEMO_BOOK, DEMO_BOOK_PROFILE, FixtureViews
from capital.protocol import SettlementMachine
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
BOOK_NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_DEMO_BOOK.md'
TERMS_NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)

_U2 = 'U2_REFUND_EXPOSURE'
_U4 = 'U4_CONCENTRATION'
_U5 = 'U5_DECISION_AUTHORITY'


def note_block(path):
    blocks = _FENCE.findall(path.read_text(encoding='utf-8'))
    assert len(blocks) == 1
    return json.loads(blocks[0])


def book_claims():
    return note_block(BOOK_NOTE)['entries']['fixture_face_values']['value']


def terms_value(name):
    return note_block(TERMS_NOTE)['entries'][name]['value']


def depth():
    return terms_value('underwriting_depth')


def check_of(record, check_id):
    return next(row for row in record['checks'] if row['id'] == check_id)


def replay(fixture_id, gross, tier, refund_face):
    """Independent pinned replay of one demo claim. Never sets a view field."""
    book = SettlementMachine()
    book.initiate(fixture_id, idempotency_key='init', trade_id='sim-trade-' + fixture_id,
                  gross=gross, debtor_role='fixture-merchant',
                  policy={'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
                          'residual_payee': 'organizer', 'fee_payee': 'platform'})
    book.authorize(fixture_id, idempotency_key='authorize')
    book.capture(fixture_id, idempotency_key='capture')
    if tier == 'T1':
        fee = gross * 3 // 100
        book.commit(fixture_id, idempotency_key='commit', movement_id='sim-movement',
                    gross=gross, amount=gross - fee, fee=fee, tax=0, held=0, adjustment=0)
    if refund_face:
        book.bind_refund(fixture_id, idempotency_key='refund', refund_id='demo-fixture-refund',
                         amount=refund_face, beneficiary_role='demo-buyer',
                         reason='SYNTHETIC_FIXTURE')
    return book.view(fixture_id)


class DemoBookProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = FixtureViews()

    def test_table_matches_the_parsed_decision_note(self):
        claims = book_claims()
        self.assertEqual(claims['label'], 'SYNTHETIC_FIXTURE_PROFILE')
        self.assertEqual(claims['profile_version'], DEMO_BOOK_PROFILE)
        self.assertEqual(claims['policy'], {'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
                                          'residual_payee': 'organizer', 'fee_payee': 'platform'})
        expected = []
        for row in claims['claims']:
            tier = 'T1' if row['tier'] == 'T1_COMMIT_OBSERVED' else 'T2'
            expected.append((row['claim_id'], row['gross_krw'], row['beneficiary'], tier,
                             row.get('open_refund_face_krw', 0)))
        self.assertEqual(list(DEMO_BOOK), expected)
        self.assertEqual(claims['total_gross_krw'], sum(row[1] for row in DEMO_BOOK))
        tiers = note_block(BOOK_NOTE)['entries']['tier_coverage']['value']
        self.assertEqual(sorted(tiers['T1_COMMIT_OBSERVED']),
                         sorted(row[0] for row in DEMO_BOOK if row[3] == 'T1'))
        self.assertEqual(sorted(tiers['T2_UNBOUND']),
                         sorted(row[0] for row in DEMO_BOOK if row[3] == 'T2'))
        payee_map = note_block(BOOK_NOTE)['entries']['beneficiary_payee_map']['value']['map']
        for _id, _gross, beneficiary, _tier, _refund in DEMO_BOOK:
            self.assertEqual(payee_map[beneficiary], ['organizer'])
        self.assertEqual(payee_map['demo-venue-east'], ['venue'])
        self.assertEqual(payee_map['demo-agency-south'], ['agency'])

    def test_views_come_only_from_pinned_replay(self):
        for fixture_id, gross, _beneficiary, tier, refund_face in DEMO_BOOK:
            with self.subTest(fixture=fixture_id):
                self.assertEqual(self.fixtures.view(fixture_id),
                                 replay(fixture_id, gross, tier, refund_face))
                view = self.fixtures.rows[fixture_id]
                expected_entries = 3 + (tier == 'T1') + bool(refund_face)
                self.assertEqual(view['accepted_entries'], expected_entries)
                self.assertEqual(view['phase'], 'COMMITTED' if tier == 'T1' else 'CAPTURED')
                self.assertEqual(view['claim']['refund_face'], refund_face)
                self.assertIs(view['funds_executed'], False)
        # The three v1 views stay byte-identical to their own pinned replay.
        for fixture_id in self.fixtures.projection_ids:
            before = self.fixtures.rows[fixture_id]
            self.assertEqual(before, self.fixtures.view(fixture_id))
        self.assertEqual([self.fixtures.profile(key) for key in self.fixtures.rows],
                         [_V1_or_demo(key) for key in self.fixtures.rows])

    def test_row_count_and_profiles(self):
        self.assertEqual(len(self.fixtures.rows), 13)
        self.assertEqual(len(self.fixtures.projection_ids), 3)
        for fixture_id, _gross, beneficiary, _tier, _refund in DEMO_BOOK:
            self.assertEqual(self.fixtures.beneficiary(fixture_id), beneficiary)
            self.assertEqual(self.fixtures.profile(fixture_id), DEMO_BOOK_PROFILE)
        for fixture_id in self.fixtures.projection_ids:
            self.assertEqual(self.fixtures.beneficiary(fixture_id), 'fixture-organizer')
            self.assertEqual(self.fixtures.profile(fixture_id), 'fixture-v1')


def _V1_or_demo(key):
    return 'fixture-v1' if key.startswith('sim-') else DEMO_BOOK_PROFILE


class DemoBookUnderwriteTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case, **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'demo-{self.counter}',
            'op': op, 'advance_id': case, 'args': args})

    def draw(self, case, fixture, amount, bound=True):
        self.assertEqual(
            self.command('offer', case, fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('approve', case)['outcome'], 'ACCEPTED')
        if bound:
            self.assertEqual(self.command('bind_settlement', case)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('draw', case)['outcome'], 'ACCEPTED')

    def record(self, advance_id, **kwargs):
        return self.service.underwrite(
            advance_id, self.service.instance_id, 'organizer', **kwargs)

    def test_single_advance_cap_decline_on_candidate(self):
        single = depth()['single_advance_cap_krw']
        body = self.record('demo-beta-festival', amount=single + 1)
        self.assertEqual(body['beneficiary_role'], 'demo-org-beta')
        for check_id in ('U1_SETTLEMENT_EVIDENCE', 'U2_REFUND_EXPOSURE', 'U3_BORROWING_BASE'):
            self.assertEqual(check_of(body, check_id)['outcome'], 'PASS', check_id)
        u4 = check_of(body, _U4)
        self.assertEqual(u4['outcome'], 'FAIL')
        self.assertEqual(u4['detail']['reason'], 'CAP_EXCEEDED')
        self.assertEqual(u4['detail']['cap'], 'single_advance_cap_krw')
        self.assertEqual(u4['detail']['cap_krw'], single)
        self.assertEqual(body['failed_check'], _U4)
        self.assertEqual(body['proposal'], 'DECLINE')
        self.assertIs(body['two_person_required'], True)
        # At the cap the same candidate passes every check.
        self.assertEqual(self.record('demo-beta-festival', amount=single)['proposal'], 'APPROVE')

    def test_beneficiary_aggregate_cap_decline_on_drawn_advances(self):
        caps = depth()
        single, aggregate = caps['single_advance_cap_krw'], caps['beneficiary_aggregate_cap_krw']
        # Each draw is exactly the single cap on the shared open face; the
        # beneficiary aggregate crosses its cap on the fifth.
        amount = single
        drawn = []
        for index in range(5):
            case = f'sim-beta-{index}'
            self.draw(case, 'demo-beta-festival', amount)
            drawn.append(case)
        body = self.record(drawn[-1])
        u4 = check_of(body, _U4)
        self.assertEqual(u4['outcome'], 'FAIL')
        self.assertEqual(u4['detail']['cap'], 'beneficiary_aggregate_cap_krw')
        self.assertEqual(u4['detail']['cap_krw'], aggregate)
        self.assertEqual(u4['detail']['required_krw'], 5 * amount)
        self.assertEqual(body['proposal'], 'DECLINE')
        # A beneficiary below its own aggregate still declines on portfolio only
        # when the book total crosses that cap, not earlier.
        beta_view = self.service.machine.view(drawn[0])
        self.assertEqual(beta_view['beneficiary_role'], 'demo-org-beta')

    def test_portfolio_cap_decline_on_drawn_advances(self):
        caps = depth()
        portfolio_cap = caps['portfolio_cap_krw']
        # Fill the book past the portfolio cap while each beneficiary stays
        # inside its own aggregate: alpha 3B, beta 4B, gamma 10.4B, epsilon 2B,
        # delta 1.04B. All faces come from DEMO_BOOK, never literals of caps.
        self.draw('sim-alpha-1', 'demo-alpha-arena', 1_500_000_000)
        self.draw('sim-alpha-2', 'demo-alpha-arena', 1_500_000_000)
        self.draw('sim-beta-big', 'demo-beta-festival', 4_000_000_000)
        self.draw('sim-gamma-1', 'demo-gamma-annex', 2_400_000_000)
        self.draw('sim-gamma-2', 'demo-gamma-tour', 8_000_000_000, bound=False)
        self.draw('sim-epsilon', 'demo-epsilon-clean', 2_000_000_000)
        self.draw('sim-delta-mid', 'demo-delta-mid', 1_000_000_000, bound=False)
        # The subject: a sub-threshold T1 draw on the smallest claim. Its
        # beneficiary stays inside the aggregate cap; only the portfolio trips.
        margin = terms_value('additional_margin')
        small_claim = self.service.fixtures.view('demo-delta-small')['claim']
        organizer = sum(line['outstanding'] for line in small_claim['obligations']
                        if line['payee'] == 'organizer')
        rate = margin['advance_rate_bps_by_tier']['T1_COMMIT_OBSERVED']
        amount = min(organizer * rate // 10000, caps['two_person_threshold_krw'])
        self.draw('sim-delta-small', 'demo-delta-small', amount)
        body = self.record('sim-delta-small')
        u4 = check_of(body, _U4)
        self.assertEqual(u4['outcome'], 'FAIL')
        self.assertEqual(u4['detail']['cap'], 'portfolio_cap_krw')
        self.assertEqual(u4['detail']['cap_krw'], portfolio_cap)
        self.assertEqual(body['failed_check'], _U4)
        self.assertEqual(body['proposal'], 'DECLINE')
        # Before saturation the same small draw under delta approves.
        fresh = CapitalService()
        fresh.execute({'instance_id': fresh.instance_id, 'operation_id': 'x1',
                       'op': 'offer', 'advance_id': 'sim-delta-small',
                       'args': {'fixture_id': 'demo-delta-small', 'amount': amount}})
        fresh.execute({'instance_id': fresh.instance_id, 'operation_id': 'x2',
                       'op': 'approve', 'advance_id': 'sim-delta-small', 'args': {}})
        fresh.execute({'instance_id': fresh.instance_id, 'operation_id': 'x3',
                       'op': 'bind_settlement', 'advance_id': 'sim-delta-small', 'args': {}})
        fresh.execute({'instance_id': fresh.instance_id, 'operation_id': 'x4',
                       'op': 'draw', 'advance_id': 'sim-delta-small', 'args': {}})
        ok = fresh.underwrite('sim-delta-small', fresh.instance_id, 'organizer')
        self.assertEqual(ok['proposal'], 'APPROVE')

    def test_two_person_threshold_and_tiers_come_from_the_note(self):
        threshold = depth()['two_person_threshold_krw']
        below = self.record('demo-delta-small', amount=threshold)
        self.assertIs(check_of(below, _U5)['detail']['two_person_required'], False)
        above = self.record('demo-delta-small', amount=threshold + 1)
        self.assertIs(check_of(above, _U5)['detail']['two_person_required'], True)
        rates = terms_value('additional_margin')['advance_rate_bps_by_tier']
        t1 = self.record('demo-beta-festival', amount=1)
        self.assertEqual(t1['borrowing_base']['advance_rate_bps'], rates['T1_COMMIT_OBSERVED'])
        t2 = self.record('demo-beta-club', amount=1)
        # A candidate on the CAPTURED fixture reads the BOUND gate: no tier.
        self.assertEqual(t2['tier'], 'NOT_APPLICABLE')
        # An unbound drawn case on the T2 claim resolves the T2 note rate.
        self.draw('sim-t2', 'demo-beta-club', 1, bound=False)
        unbound = self.record('sim-t2')
        self.assertEqual(unbound['tier'], 'T2')
        self.assertEqual(unbound['borrowing_base']['advance_rate_bps'], rates['T2_UNBOUND'])

    def test_open_refund_claim_declines_u2_and_offer_refused(self):
        refund_face = next(row[4] for row in DEMO_BOOK if row[0] == 'demo-epsilon-refund')
        body = self.record('demo-epsilon-refund', amount=1)
        u2 = check_of(body, _U2)
        self.assertEqual(u2['outcome'], 'FAIL')
        self.assertEqual(u2['detail']['reason'], 'REFUND_OBLIGATION_OPEN')
        self.assertEqual(u2['detail']['refund_face'], refund_face)
        self.assertEqual(body['proposal'], 'DECLINE')
        self.assertEqual(body['failed_check'], _U2)
        self.assertEqual(
            self.command('offer', 'sim-eps', fixture_id='demo-epsilon-refund', amount=1)['error'],
            'REFUND_OBLIGATION_OPEN')

    def test_evidence_rows_carry_the_profile_label(self):
        body = self.service.evidence()
        self.assertEqual(len(body['rows']), 13)
        for row in body['rows']:
            self.assertEqual(row['profile'], _V1_or_demo(row['claim_id']))
        self.assertIn('SYNTHETIC_FIXTURE_PROFILE', body['source_scope'])
        self.assertIs(body['funds_executed'], False)


if __name__ == '__main__':
    unittest.main()
