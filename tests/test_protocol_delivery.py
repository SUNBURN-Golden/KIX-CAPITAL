"""Capital consumers of the pinned Protocol reference. SIMULATED, read-only observations."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import protocol
from capital.gate_producer import GateHttpProducer, GateProtocolError, _OPENER, load_fake_gate
from capital.margin import ScenarioReplaySource
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.protocol import (
    CreditError, CreditMachine, SettlementMachine, SharedExposureError, VarianceObservationError,
    observe_settlement_variance, observe_shared_exposure,
)
from capital.protocol_delivery import COMMIT, read_delivery
from test_gate_producer import _offer, _raw

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'capital/vendor/credit_advance_f04/fixtures'


def fixture_scenarios(filename):
    return json.loads((FIXTURES / filename).read_text(encoding='utf-8'))['scenarios']


class DeliveryTests(unittest.TestCase):
    def test_bootstrap_delivery_and_fake_gate_agree_before_post(self):
        producer = GateHttpProducer()
        self.addCleanup(producer.close)
        self.assertEqual(producer.delivery, read_delivery(ROOT))
        self.assertEqual(producer.gate.host, '127.0.0.1')
        self.assertEqual(producer.delivery['commit'], COMMIT)
        self.assertFalse(producer.semantic_conformance)
        self.assertEqual(_offer(producer)['credit']['phase'], 'OFFERED')

    def test_stale_gate_is_refused_before_any_command_post(self):
        gate = load_fake_gate().start()
        self.addCleanup(gate.close)
        producer = GateHttpProducer(base_url=gate.url)
        self.addCleanup(producer.close)
        gate.delivery['commit'] = '0' * 40
        with patch.object(_OPENER, 'open', wraps=_OPENER.open) as http:
            with self.assertRaises(GateProtocolError) as caught:
                _offer(producer)
            self.assertEqual(caught.exception.code, 'PROTOCOL_DELIVERY_MISMATCH')
            self.assertEqual([call.args[0].get_method() for call in http.call_args_list], ['GET'])
        self.assertEqual(gate.post_count('offer-1'), 0)

    def test_direct_commands_require_the_pin_header(self):
        gate = load_fake_gate().start()
        self.addCleanup(gate.close)
        status, result = _raw('POST', gate.url + '/v1/commands', {}, pin='0' * 40)
        self.assertEqual((status, result['error']), (409, 'PROTOCOL_DELIVERY_MISMATCH'))
        self.assertFalse(result['funds_executed'])
        self.assertEqual(gate.counters(), {})

    def test_point_f4_pool_simulator_label(self):
        label = 'POINT_F4 pool simulator — NOT an accounting ledger'
        self.assertIn(label, protocol.__doc__)
        for doc in ('INTEGRATION.md', 'SEAMS.md'):
            with self.subTest(doc=doc):
                self.assertIn(label, (ROOT / 'docs' / doc).read_text(encoding='utf-8'))


class SettlementCreditBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {row['scenario_id']: row['steps'] for row in
                      fixture_scenarios('settlement_credit_boundary_v1.json')}
        cls.vectors = {row['scenario_id']: row['steps'] for row in
                       fixture_scenarios('settlement_credit_boundary_vectors_v1.json')}

    def replay(self, scenario):
        settlement = SettlementMachine()
        fixtures = FixtureViews()
        producer = PinnedFsmProducer(fixtures)
        steps = self.inputs[scenario]
        # The local facade derives draw IDs from its idempotency keys.
        draw_ids = {step['arguments']['draw_id']: 'draw-' + step['arguments']['idempotency_key']
                    for step in steps if step['operation'] == 'draw'}
        expected = {step['step_id']: step['result'] for step in self.vectors[scenario]}
        for step in steps:
            with self.subTest(step=step['step_id']):
                op = step['operation']
                args = step['arguments']
                result = expected[step['step_id']]
                if step['target'] == 'settlement':
                    self.assertEqual(getattr(settlement, op)(**args), result['ok'])
                    key = args['settlement_id']
                    fixtures.rows[key] = settlement.view(key)
                    continue
                digest = settlement.state_digest()
                self.check_credit_step(producer, op, args, result, draw_ids)
                self.assertEqual(settlement.state_digest(), digest)
        return producer

    def check_credit_step(self, producer, op, args, result, draw_ids):
        if op == 'view_claim':
            self.assertEqual(producer.machine.view_claim(args['claim_id']), result['ok'])
            return

        if op == 'view':
            actual = producer.view(args['advance_id'])
        elif op == 'offer':
            face = args['face']
            key = face['claim_id']
            view = producer.fixtures.view(key)
            self.assertEqual({field: face[field] for field in view['claim']}, view['claim'])
            producer.fixtures.beneficiaries[key] = args['beneficiary_role']
            # S3 adds a caller field to the literal face while the bound draw
            # still reads the unchanged SettlementMachine view.
            with patch.dict(producer.fixtures.rows, {key: {**view, 'claim': face}}):
                actual = producer.apply(op, args['advance_id'], idempotency_key=args['idempotency_key'],
                                        args={'fixture_id': key, 'amount': args['amount']},
                                        bound_settlement_id=None)
            self.assertEqual(producer.export_journal()[-1]['body']['face'], face)
        else:
            apply = dict(idempotency_key=args['idempotency_key'], args={},
                         bound_settlement_id=args.get('settlement_id'))
            if 'error' in result:
                self.assert_credit_rejection(producer, op, args['advance_id'], result['error']['code'], **apply)
                return
            actual = producer.apply(op, args['advance_id'], **apply)

        expected = copy.deepcopy(result['ok'])
        view = expected.get('credit', expected)
        if view['draw_id'] is not None:
            view['draw_id'] = draw_ids[view['draw_id']]
        if op == 'draw':
            expected['effect']['draw_id'] = view['draw_id']
        self.assertEqual(actual, expected)

    def assert_credit_rejection(self, producer, op, advance_id, code, **kwargs):
        before = producer.state_digest(), producer.export_journal()
        with self.assertRaises(CreditError) as caught:
            producer.apply(op, advance_id, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual((producer.state_digest(), producer.export_journal()), before)

    def test_bound_draw_waits_for_commit_and_freezes_the_offered_face(self):
        self.replay('S1_captured_face_no_derivation')

    def test_changed_face_is_rejected_and_settlement_refund_leaves_claim_frozen(self):
        self.replay('S3_face_snapshot_frozen_and_stable_view_claim')

    def test_requester_refund_face_blocks_offer_after_mock_partial_acceptance(self):
        scenario = 'S4_refund_obligation_partial_acceptance'
        producer = self.replay(scenario)
        offer = next(step['arguments'] for step in self.inputs[scenario] if step['operation'] == 'offer')
        key = offer['face']['claim_id']
        face = producer.fixtures.view(key)['claim']
        self.assertEqual(face['refund_bearer_policy'], 'REQUESTER')
        self.assertGreater(face['refund_outstanding'], 0)
        self.assert_credit_rejection(
            producer, 'offer', 'advance-after-refund', 'REFUND_OBLIGATION_OPEN',
            idempotency_key='offer-after-refund', args={'fixture_id': key, 'amount': offer['amount']},
            bound_settlement_id=None,
        )


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.source = ScenarioReplaySource()
        self.credit = CreditMachine()
        for advance, amount in (('sim-a', 30_000), ('sim-b', 20_000)):
            self.credit.offer(advance, idempotency_key=advance + '-offer',
                              face=self.source.view('sim-committed')['claim'], amount=amount,
                              beneficiary_role='organizer')
            self.credit.approve(advance, idempotency_key=advance + '-approve')
            self.credit.draw(advance, idempotency_key=advance + '-draw', draw_id=advance + '-draw')

    def test_variance_uses_same_claim_and_explicit_tolerance(self):
        digest = self.credit.state_digest()
        claim = self.credit.view_claim('sim-committed')
        settlement = self.source.view('sim-committed')['claim']
        observe = observe_settlement_variance
        self.assertTrue(observe(settlement, claim, tolerance=0)['within_tolerance'])
        with self.assertRaisesRegex(VarianceObservationError, '^TOLERANCE_REQUIRED$'):
            observe(settlement, claim)
        outcomes = self.source.replay('sim-committed', 'partial-before')
        self.assertTrue(all(row['matched'] for row in outcomes))
        settlement = self.source.view('sim-committed')['claim']
        before = copy.deepcopy((settlement, claim))
        result = observe(settlement, claim, tolerance=97_000)
        self.assertEqual(result['variance'], -97_000)
        self.assertTrue(result['within_tolerance'])
        self.assertFalse(observe(settlement, claim, tolerance=96_999)['within_tolerance'])
        self.assertEqual((settlement, claim), before)
        self.assertEqual(self.credit.state_digest(), digest)
        self.assert_observation_flags(result)
        self.assertFalse(self.credit.view('sim-a')['durable'])
        self.assertFalse(settlement['funds_executed'])

    def test_shared_exposure_counts_each_advance_and_each_claim_once(self):
        views = [self.credit.view(name) for name in ('sim-b', 'sim-a')]
        before = copy.deepcopy(views)
        digest = self.credit.state_digest()
        with self.assertRaisesRegex(SharedExposureError, '^LIMIT_REQUIRED$'):
            observe_shared_exposure('sim-group', views)
        result = observe_shared_exposure('sim-group', views, limit=50_000)
        self.assertTrue(result['within_limit'])
        for limit in (49_999, 0):
            self.assertFalse(observe_shared_exposure('sim-group', views, limit=limit)['within_limit'])
        self.assertEqual((result['advance_count'], result['claim_count']), (2, 1))
        self.assertEqual(result['observable'], {
            'group_outstanding_exposure': 50_000, 'group_drawn_exposure': 50_000,
            'group_repaid_exposure': 0, 'group_open_face': 100_000,
            'group_reserved_open': 50_000, 'group_residual_unreserved': 50_000,
        })
        self.assertEqual(views, before)
        self.assertEqual(self.credit.state_digest(), digest)
        self.assert_observation_flags(result)

    def test_variance_matches_all_pinned_cases(self):
        for case in fixture_scenarios('settlement_variance_v1.json'):
            with self.subTest(case=case['id']):
                views = case['settlement_view'], case['credit_view']
                before = copy.deepcopy(views)
                result = observe_settlement_variance(*views, tolerance=case['tolerance'])
                self.assertEqual({key: result[key] for key in case['expected']}, case['expected'])
                self.assertEqual(views, before)
                self.assert_observation_flags(result)

    def test_shared_exposure_matches_all_pinned_cases(self):
        for case in fixture_scenarios('shared_exposure_v1.json'):
            with self.subTest(case=case['id']):
                views = case['credit_views']
                before = copy.deepcopy(views)
                result = observe_shared_exposure(case['group_id'], views, limit=case['limit'])
                self.assertEqual({key: result[key] for key in case['expected']}, case['expected'])
                self.assertEqual(views, before)
                self.assertIs(result['legal_debtor_bound'], False)
                self.assert_observation_flags(result)

    def test_observers_reject_invalid_thresholds(self):
        variance = fixture_scenarios('settlement_variance_v1.json')[0]
        exposure = fixture_scenarios('shared_exposure_v1.json')[0]
        for invalid in (-1, True, 0.0, '0', None):
            with self.subTest(threshold=invalid):
                with self.assertRaisesRegex(VarianceObservationError, '^TOLERANCE_INVALID$'):
                    observe_settlement_variance(variance['settlement_view'], variance['credit_view'],
                                                tolerance=invalid)
                with self.assertRaisesRegex(SharedExposureError, '^LIMIT_INVALID$'):
                    observe_shared_exposure(exposure['group_id'], exposure['credit_views'], limit=invalid)

    def test_variance_rejects_mismatched_or_unfrozen_views(self):
        case = fixture_scenarios('settlement_variance_v1.json')[0]
        for field, replacement, code in (
            ('claim_id', 'other-claim', 'VIEW_BINDING_CONFLICT'),
            ('trade_id', 'other-trade', 'VIEW_BINDING_CONFLICT'),
            ('snapshot_frozen', False, 'VIEW_NOT_FROZEN'),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(VarianceObservationError, f'^{code}$'):
                observe_settlement_variance(case['settlement_view'], {**case['credit_view'], field: replacement},
                                            tolerance=case['tolerance'])

    def test_shared_exposure_rejects_duplicate_conflicting_or_unfrozen_views(self):
        case = fixture_scenarios('shared_exposure_v1.json')[0]
        first, second = case['credit_views']
        for invalid, code in (
            (first, 'VIEW_INVALID'),
            ({**second, 'trade_id': 'other-trade'}, 'VIEW_BINDING_CONFLICT'),
            ({**second, 'snapshot_frozen': False}, 'VIEW_NOT_FROZEN'),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(SharedExposureError, f'^{code}$'):
                observe_shared_exposure(case['group_id'], [first, invalid], limit=case['limit'])

    def assert_observation_flags(self, result):
        self.assertEqual(result['mapping']['contract_status'], 'NOT_BOUND')
        self.assertEqual(result['mapping']['repair'], 'NONE')
        self.assertEqual(result['refund_component'], 'NOT_BOUND')
        self.assertIs(result['fail_closed'], True)
        self.assertIs(result['mutates_state'], False)
        self.assertIs(result['authorizes_exposure'], False)
