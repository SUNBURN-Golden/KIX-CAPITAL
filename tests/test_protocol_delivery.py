"""Capital consumers of the pinned Protocol reference. SIMULATED, read-only observations."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from capital.gate_producer import GateHttpProducer, GateProtocolError, _OPENER, load_fake_gate
from capital.margin import ScenarioReplaySource
from capital.protocol import (
    CreditMachine, SharedExposureError, VarianceObservationError,
    observe_settlement_variance, observe_shared_exposure,
)
from capital.protocol_delivery import COMMIT, read_delivery
from test_gate_producer import _offer, _raw

ROOT = Path(__file__).resolve().parents[1]


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

    def assert_observation_flags(self, result):
        self.assertEqual(result['mapping']['contract_status'], 'NOT_BOUND')
        self.assertEqual(result['refund_component'], 'NOT_BOUND')
        self.assertIs(result['fail_closed'], True)
        self.assertIs(result['mutates_state'], False)
        self.assertIs(result['authorizes_exposure'], False)
