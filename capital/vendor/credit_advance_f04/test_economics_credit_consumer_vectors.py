"""Offline EconomicsSession → frozen F04 → observation composition evidence.

All replay/reader code is test-only. See the field guide for the pre-change
coverage map and the three deliberately separate synthetic histories. Golden
snapshots characterize public outputs; the arithmetic oracle is a separate set
of reviewed fixture literals, never computed by the observers under test.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from reference.economics import EconomicsLocalError, FLAGS, quotes, support  # noqa: E402
from credit_fixture import decode_json, exact_fields  # noqa: E402
from credit_fsm import CreditMachine  # noqa: E402
from settlement_credit_boundary_vectors import canonical  # noqa: E402
from settlement_variance import observe_settlement_variance  # noqa: E402
from shared_exposure import observe_shared_exposure  # noqa: E402

FIXTURE_PATH = HERE / 'fixtures/economics_credit_consumer_v1.json'
VECTORS_PATH = HERE / 'fixtures/economics_credit_consumer_vectors_v1.json'
FIXTURE_SHA256 = '19af14b0a788a7d82cc5afce7f0f3a41e28ee0b15409442580ecaec5995eb098'
VECTORS_SHA256 = '7f452e69347e9fab0b0197f6636eb765d6d85a4c9d230bd829a6fe214e894904'
SOURCE_PATHS = (
    'reference/economics/__init__.py',
    'reference/economics/authentication.py',
    'reference/economics/quotes.py',
    'reference/economics/captures.py',
    'reference/economics/refunds.py',
    'reference/economics/payouts.py',
    'reference/economics/session.py',
    'reference/economics/support.py',
    'reference/economics/fixtures/partial_refund.json',
    'durable/model.py', 'durable/budgets.py',
    'reference/v0.3-rc1/assets.py',
    'reference/v0.3-rc1/commerce.py',
    'reference/v0.3-rc1/lifecycle.py',
    'reference/v0.3-rc1/finance.py',
    'reference/payment_effects/payment_effect_session.py',
    'reference/settlement_f01_f03/mock_settlement.py',
    'reference/settlement_f01_f03/settlement_fsm.py',
    'reference/credit_advance_f04/mock_credit.py',
    'reference/credit_advance_f04/credit_fsm.py',
    'reference/credit_advance_f04/open_terms.py',
    'reference/credit_advance_f04/credit_fixture.py',
    'reference/credit_advance_f04/settlement_credit_boundary_vectors.py',
    'reference/credit_advance_f04/settlement_variance.py',
    'reference/credit_advance_f04/shared_exposure.py',
    'docs/contracts/CREDIT_ADVANCE_F04.md',
    'docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md',
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load(path):
    raw = path.read_bytes()
    value = decode_json(raw.decode('utf-8'))
    if canonical(value) != raw:
        raise AssertionError(f'{path.name} is not canonical JSON')
    return value


class _CapturedSettlementReader:
    """Test-only reader of explicitly captured public envelopes, unchanged."""

    def __init__(self, snapshots):
        self._snapshots = copy.deepcopy(snapshots)

    def view(self, settlement_id):
        return copy.deepcopy(self._snapshots[settlement_id])


def _credit_snapshot(credit, advance_ids, claim_id):
    return {
        'views': [credit.view(advance_id) for advance_id in advance_ids],
        'claim': credit.view_claim(claim_id),
        'journal': credit.export_journal(),
        'state_digest': credit.state_digest(),
    }


def _replay(scenario):
    """Run one bounded history using only the existing public APIs."""
    inputs = scenario['inputs']
    base = support.load_fixture('partial_refund.json')
    order_id, group_id = inputs['order_id'], inputs['group_id']
    steps = []

    def record(step_id, value):
        steps.append({'step_id': step_id, 'result': {'ok': value}})
        return value

    with support.make_session() as session:
        lines = [support.krw_line(row['lineId'], row['atoms']) for row in base['lines']]
        legs = [support.krw_leg('leg-1', base['legAmount'])]
        record('create', session.create_order(
            order_id, order_version=base['orderVersion'], scope=base['scope'],
            groups=[support.group(lines, legs, group_id=group_id)], now_ms=base['nowMs']))
        record('capture_confirm', support.capture_and_confirm(
            session, order_id, group_id, 'leg-1', inputs['capture_id'], base['legAmount']))
        record('settle', support.settle(session, order_id, group_id,
                                       movement_id=inputs['movement_id'], key=inputs['settle_key']))

        def group_view():
            return session.view(order_id)['orders'][order_id]['groups'][group_id]

        public_settlement = group_view()['settlement']
        face = public_settlement['claim']
        claim_id = face['claim_id']
        reader = _CapturedSettlementReader({public_settlement['settlement_id']: public_settlement})
        credit = CreditMachine(settlement_source=reader)
        advance_ids = [item['advance_id'] for item in inputs['advances']]
        for item in inputs['advances']:
            aid = item['advance_id']
            record(aid + ':offer', credit.offer(
                aid, idempotency_key=aid + ':offer', face=face, amount=item['amount'],
                beneficiary_role=inputs['beneficiary_role']))
            record(aid + ':approve', credit.approve(aid, idempotency_key=aid + ':approve'))
            record(aid + ':bind', credit.bind_settlement(
                aid, idempotency_key=aid + ':bind', settlement_id=public_settlement['settlement_id']))
            record(aid + ':draw', credit.draw(aid, idempotency_key=aid + ':draw', draw_id=item['draw_id']))

        # Capture both advance views AFTER both draws, at the same observation point.
        def checkpoint(name):
            group = group_view()
            frozen = _credit_snapshot(credit, advance_ids, claim_id)
            before = canonical({'group': group, 'credit': frozen})
            variance = observe_settlement_variance(
                group['settlement']['claim'], frozen['claim'], tolerance=inputs['tolerance'])
            exposure = observe_shared_exposure(
                inputs['exposure_group_id'], frozen['views'], limit=inputs['limit'])
            # Include complete snapshots as well as pure-observer input immutability.
            assert before == canonical({'group': group, 'credit': frozen})
            assert before == canonical({
                'group': group_view(), 'credit': _credit_snapshot(credit, advance_ids, claim_id)})
            record(name, {'group': group, 'credit': frozen,
                          'variance': variance, 'shared_exposure': exposure})

        checkpoint('frozen')
        for action in inputs['history']:
            if action == 'refund':
                group = group_view()
                proposal = quotes.propose_line_refund(
                    support.make_assets(), group['quote'], group['plan'], inputs['refund_lines'],
                    group['plan']['planHash'])
                record('refund', session.refund_lines(
                    order_id, group_id, line_ids=inputs['refund_lines'],
                    refund_id=inputs['refund_id'], authorization=support.authorization(proposal),
                    refund_policy_ref=base['refund']['refundPolicyRef'], reason=inputs['refund_reason'],
                    idempotency_key=inputs['refund_key'], route_profile=inputs['route_profile'],
                    effect_id=inputs['effect_id']))
            elif action == 'distribute':
                try:
                    result = session.distribute_group(
                        order_id, group_id, order=inputs['distribution_order'],
                        idempotency_key=inputs['distribution_key'])
                except EconomicsLocalError as error:
                    steps.append({'step_id': 'distribute', 'result': {
                        'error': {'type': type(error).__name__, 'code': str(error)}}})
                else:
                    record('distribute', result)
            elif action == 'accept':
                record('accept', session.observe_refund_acceptance(
                    order_id, group_id, source_id=inputs['acceptance_source_id'],
                    amount=inputs['acceptance_amount'], idempotency_key=inputs['acceptance_key']))
            else:
                raise AssertionError(f'Unknown test history action: {action}')
            checkpoint('after_' + action)
    return {'scenario_id': scenario['scenario_id'], 'steps': steps}


def _actual_vectors(fixture):
    return {
        'vector_version': 'economics-credit-consumer/1',
        'fixture_sha256': _sha(FIXTURE_PATH.read_bytes()),
        'source_pins': [{'path': path, 'sha256': _sha((ROOT / path).read_bytes())}
                        for path in SOURCE_PATHS],
        'scenarios': [_replay(scenario) for scenario in fixture['scenarios']],
    }


class EconomicsCreditConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = _load(FIXTURE_PATH)
        cls.vectors = _load(VECTORS_PATH)
        cls.actual = _actual_vectors(cls.fixture)

    def _checkpoints(self):
        for scenario, actual in zip(self.fixture['scenarios'], self.actual['scenarios']):
            steps = {step['step_id']: step['result'] for step in actual['steps']}
            for name, expected in scenario['expected_arithmetic']['checkpoints'].items():
                yield scenario, name, steps[name]['ok'], expected

    def test_public_snapshot_bytes_and_pins(self):
        exact_fields(self.fixture, {'fixture_version', 'fixture_kind', 'synthetic_only',
                                   'provenance', 'scenarios'}, 'fixture')
        self.assertEqual(self.fixture['fixture_version'], 'economics-credit-consumer/1')
        self.assertEqual(self.fixture['fixture_kind'], 'SYNTHETIC_CROSS_BOUNDARY_VECTORS')
        self.assertIs(self.fixture['synthetic_only'], True)
        self.assertEqual(self.fixture['provenance'], {
            'economics': 'SYNTHETIC_REFERENCE', 'settlement': 'MOCK_SETTLEMENT_ONLY',
            'credit': 'MOCK_CREDIT_F04_ONLY'})
        self.assertEqual(_sha(FIXTURE_PATH.read_bytes()), FIXTURE_SHA256)
        self.assertEqual(_sha(VECTORS_PATH.read_bytes()), VECTORS_SHA256)
        self.assertEqual(canonical(self.actual), VECTORS_PATH.read_bytes())
        self.assertEqual(self.vectors['source_pins'], self.actual['source_pins'])
        for actual in self.actual['scenarios']:
            steps = {step['step_id']: step['result'] for step in actual['steps']}
            frozen = steps['frozen']['ok']
            settlement = frozen['group']['settlement']
            reader = _CapturedSettlementReader({settlement['settlement_id']: settlement})
            self.assertEqual(canonical(reader.view(settlement['settlement_id'])), canonical(settlement))
            detached = reader.view(settlement['settlement_id'])
            detached['claim']['obligations'][0]['face'] = -1
            self.assertEqual(canonical(reader.view(settlement['settlement_id'])), canonical(settlement))
            for entry in frozen['credit']['journal']:
                if entry['op'] == 'offer':
                    self.assertEqual(canonical(entry['body']['face']), canonical(settlement['claim']))
                    receipt = steps[entry['advance_id'] + ':offer']['ok']
                    if entry['advance_id'] == frozen['credit']['views'][0]['advance_id']:
                        self.assertFalse(receipt['credit']['snapshot_frozen'])
            self.assertTrue(all(view['snapshot_frozen'] for view in frozen['credit']['views']))
            self.assertTrue(frozen['credit']['claim']['snapshot_frozen'])

    def test_frozen_credit_bytes_survive_all_economics_actions(self):
        for actual in self.actual['scenarios']:
            checkpoints = [step['result']['ok'] for step in actual['steps']
                           if step['step_id'] == 'frozen' or step['step_id'].startswith('after_')]
            baseline = canonical(checkpoints[0]['credit'])
            for checkpoint in checkpoints:
                self.assertEqual(canonical(checkpoint['credit']), baseline)
                for view in checkpoint['credit']['views']:
                    self.assertEqual(view['phase'], 'DRAWN')
                    self.assertEqual(view['note_status'], 'NOTED')
                    self.assertEqual(view['exposure_ledger'], 'MOCK_EXPOSURE')
                    self.assertEqual(view['repaid_exposure'], 0)
                    self.assertEqual(view['repayments'], [])
                    self.assertTrue(view['mock_settlement_commit_observed'])
                claim = checkpoint['credit']['claim']
                self.assertEqual([claim[key] for key in (
                    'open_face', 'reserved_open', 'residual_unreserved',
                    'confirmed_cash_on_face', 'recovery_due_on_face')], [10000, 10000, 0, 10000, 0])
                self.assertNotIn('refund_face', claim)

    def test_independently_stated_arithmetic(self):
        for scenario, name, result, expected in self._checkpoints():
            with self.subTest(scenario=scenario['scenario_id'], checkpoint=name):
                group = result['group']
                claim = group['settlement']['claim']
                for field, value in expected['claim'].items():
                    self.assertEqual(claim[field], value, field)
                self.assertEqual(group['phase'], expected['group_phase'])
                self.assertEqual(group['settlement']['phase'], 'COMMITTED')
                self.assertEqual(group['refundReserved'], expected['refund_reserved'])
                self.assertEqual(group['refundedLines'], expected['refunded_lines'])
                self.assertEqual(
                    [{key: row[key] for key in expected['obligations'][0]}
                     for row in claim['obligations']], expected['obligations'])
                variance = result['variance']
                self.assertEqual(variance['variance'], expected['variance'])
                self.assertEqual(variance['sign'], 'ZERO' if expected['variance'] == 0 else 'NEGATIVE')
                self.assertEqual(variance['observable'], {
                    'settlement_outstanding': expected['settlement_outstanding'], 'credit_open_face': 10000})
                self.assertEqual(variance['companion']['cash_delta'], 0)
                self.assertEqual(variance['companion']['recovery_delta'], expected['recovery_delta'])
                self.assertEqual(result['shared_exposure']['observable'],
                                 scenario['expected_arithmetic']['shared_exposure'])
                self.assertEqual(result['shared_exposure']['advance_count'], 2)
                self.assertEqual(result['shared_exposure']['claim_count'], 1)
                self.assertEqual(len(result['shared_exposure']['claims']), 1)

    def test_partial_requester_and_explicit_distribution(self):
        actual = self.actual['scenarios'][0]
        steps = {step['step_id']: step['result'] for step in actual['steps']}
        refund = steps['refund']['ok']
        self.assertEqual((refund['kind'], refund['bearer'], refund['effectId']),
                         ('PARTIAL', 'REQUESTER', None))
        self.assertFalse(refund['distributionBlocked'])
        self.assertEqual(steps['distribute']['ok']['effect'], {'organizer-1': 9700, 'platform': 300})
        self.assertEqual(steps['after_distribute']['ok']['group']['settlement']['claim']['distribution_order'],
                         ['organizer-1', 'platform'])

    def test_full_refund_before_and_after_distribution_are_distinct(self):
        for actual in self.actual['scenarios'][1:]:
            steps = {step['step_id']: step['result'] for step in actual['steps']}
            refund = steps['refund']['ok']
            self.assertEqual((refund['kind'], refund['bearer']), ('FULL', 'FIXTURE_FULL_GROSS_RECLASS'))
            self.assertIsNotNone(refund['effectId'])
            self.assertEqual(refund['proposal']['lineIds'], ['line-1', 'line-2'])
            if actual['scenario_id'] == 'F_full_before_distribution':
                self.assertEqual(steps['distribute'], {
                    'error': {'type': 'EconomicsLocalError', 'code': 'GROUP_NOT_SETTLED'}})
                self.assertEqual(canonical(steps['after_refund']['ok']['group']),
                                 canonical(steps['after_distribute']['ok']['group']))
            else:
                self.assertEqual(steps['distribute']['ok']['effect'], {'organizer-1': 9700, 'platform': 300})

    def test_observers_authorize_nothing_and_acceptance_is_not_repayment(self):
        for scenario, name, result, expected in self._checkpoints():
            for observation in (result['variance'], result['shared_exposure']):
                self.assertEqual(observation['mapping']['contract_status'], 'NOT_BOUND')
                self.assertEqual(observation['mapping']['repair'], 'NONE')
                self.assertEqual(observation['refund_component'], 'NOT_BOUND')
                self.assertIs(observation['fail_closed'], True)
                self.assertIs(observation['mutates_state'], False)
                self.assertIs(observation['authorizes_exposure'], False)
            self.assertEqual(result['variance']['tolerance'], scenario['inputs']['tolerance'])
            self.assertEqual(result['variance']['within_tolerance'], expected['variance'] == 0)
            self.assertEqual(result['shared_exposure']['limit'], scenario['inputs']['limit'])
            self.assertIs(result['shared_exposure']['within_limit'], True)
            self.assertIs(result['shared_exposure']['legal_debtor_bound'], False)
            claim = result['group']['settlement']['claim']
            for view in [claim, result['group']['settlement'], result['credit']['claim'],
                         *result['credit']['views']]:
                for flag in ('funds_executed', 'bank_debit_observed', 'economic_finality_claimed',
                             'repayment_observed', 'legal_debtor_bound', 'durable'):
                    if flag in view:
                        self.assertIs(view[flag], False)
            if name == 'after_accept':
                self.assertEqual(claim['refund_accepted'], scenario['inputs']['acceptance_amount'])
                self.assertEqual(claim['refund_outstanding'], 0)
                self.assertEqual(claim['pg_adjustment_outstanding'], scenario['inputs']['acceptance_amount'])
        for scenario, actual in zip(self.fixture['scenarios'], self.actual['scenarios']):
            steps = {step['step_id']: step['result'] for step in actual['steps']}
            previous = 'after_' + scenario['inputs']['history'][-2]
            before_accept = steps[previous]['ok']['group']['settlement']['claim']
            accepted = steps['after_accept']['ok']['group']['settlement']['claim']
            changed = {key for key in accepted if canonical(accepted[key]) != canonical(before_accept[key])}
            self.assertEqual(changed, {'refund_accepted', 'refund_outstanding', 'pg_adjustment_outstanding'})
            receipt = steps['refund']['ok']
            self.assertIs(receipt['proposal']['executionAuthorized'], False)
            for flag in FLAGS:
                self.assertIs(receipt[flag], False)


if __name__ == '__main__':
    unittest.main()
