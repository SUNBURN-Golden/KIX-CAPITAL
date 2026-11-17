"""Counterfactual fixtures: SIMULATED, handwritten values, no live cash."""
import copy
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import audit, export, repayment_compare as rc, residuals, store
from capital.producer import CreditError, PinnedFsmProducer
from capital.service import CapitalService
from tests.test_overlay import draw_book, run, tick

ROOT = Path(__file__).resolve().parents[1]


def payment(day, amount):
    return {'at_sim_day': day, 'amount_krw': amount}


def specification(a=(), b=(), horizon=10):
    return {'format': rc.SPEC_FORMAT, 'advance_id': 'sim-a', 'horizon_sim_day': horizon,
            'schedules': [{'id': 'earlier', 'payments': list(a)}, {'id': 'later', 'payments': list(b)}]}


class RepaymentCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.path = self.directory / store.FILE_NAME
        self.service = CapitalService()
        self.addCleanup(self.service.observability.close)
        draw_book(self.service)
        self.capture()

    def capture(self, document=None):
        if document is None:
            self.service._persist()
            document = self.service.storage.load()
        self.path.write_bytes(store.canonical_bytes(document))
        self.path.chmod(0o600)
        return document

    def compare(self, spec=None):
        return rc.compare_workspace(self.directory, specification() if spec is None else spec)

    def assertComparable(self, result):
        self.assertEqual(result['status'], 'COMPARABLE', result['comparability'])
        self.assertTrue(all(c['status'] == 'MATCHED' for c in result['comparability']['checks']))
        self.assertEqual(result['label'], 'SIMULATED')
        for key in ('applied', 'workspace_mutated', 'funds_executed'):
            self.assertIs(result[key], False)

    def assertRejected(self, result, reason):
        self.assertEqual(result['status'], 'NON_COMPARABLE')
        self.assertIsNone(result['comparison'])
        self.assertIn(reason, [c['reason'] for c in result['comparability']['checks']])

    def test_earlier_later_handwritten_partial_balances_and_exact_carry(self):
        report = self.compare(specification([payment(3, 45000)], [payment(6, 45000)]))
        self.assertComparable(report)
        a, b = [s['final']['values'] for s in report['branches']]
        # 90,000 at the adopted 700bps; day-3 interest floors to 51,
        # leaving 45,051; day-6 floors to 103, leaving 45,103.
        self.assertEqual(a, {'principal_outstanding_krw': 45051, 'interest_paid_krw': 51,
                            'default_interest_paid_krw': 0, 'interest_due_krw': 61,
                            'default_interest_due_krw': 0, 'unapplied_cash_krw': 0,
                            'cumulative_exact_contract': '4097499/36500',
                            'cumulative_exact_default': '0/1',
                            'carried_remainder_contract': '9499/36500', 'carried_remainder_default': '0/1'})
        self.assertEqual((b['principal_outstanding_krw'], b['interest_paid_krw'], b['interest_due_krw']), (45103, 103, 35))
        self.assertEqual(b['cumulative_exact_contract'], '1260721/9125')
        self.assertEqual(b['carried_remainder_contract'], '1471/9125')
        self.assertEqual(report['comparison']['delta'], {'principal_outstanding_krw': 52,
                         'interest_paid_krw': 52, 'default_interest_paid_krw': 0,
                         'interest_due_krw': -26, 'default_interest_due_krw': 0, 'unapplied_cash_krw': 0})
        self.assertEqual(report['target']['allocation_order'], ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL'])
        self.assertEqual(report['target']['denominator'], 3650000)
        self.assertEqual(report['target']['contract_bps'], 700)
        self.assertEqual(report['target']['term_source'], 'standard')

    def test_interest_only_then_partial_principal_at_same_day_preserves_order(self):
        report = self.compare(specification([payment(3, 20), payment(3, 40)], [payment(3, 40), payment(3, 20)], horizon=3))
        self.assertComparable(report)
        a, b = report['branches']
        self.assertEqual([s['command']['op'] for s in a['steps']], ['advance_day', 'post_repayment', 'post_repayment'])
        self.assertEqual([s['result']['allocation']['interest_krw'] for s in a['steps'][1:]], [20, 31])
        self.assertEqual([s['result']['allocation']['interest_krw'] for s in b['steps'][1:]], [40, 11])
        self.assertIsNone(a['steps'][1]['result']['f04'])
        self.assertEqual(a['steps'][2]['result']['allocation']['principal_krw'], 9)
        self.assertEqual(a['final']['values']['principal_outstanding_krw'], 89991)
        self.assertEqual(a['final']['values']['cumulative_exact_contract'], '3780/73')
        self.assertEqual(a['final']['values']['carried_remainder_contract'], '57/73')
        self.assertEqual(a['final']['values'], b['final']['values'])

    def test_overpayment_and_held_cash_zero_reposting_do_not_close(self):
        report = self.compare(specification([payment(3, 90151), payment(3, 0)], [payment(3, 90151)], horizon=10))
        self.assertComparable(report)
        for branch in report['branches']:
            final = branch['final']
            self.assertEqual(final['values']['unapplied_cash_krw'], 100)
            self.assertEqual(final['values']['principal_outstanding_krw'], 0)
            self.assertEqual(final['phase'], 'DRAWN')  # full principal payment does not close F04
            self.assertIs(final['close_advisory']['close_ready'], True)
            self.assertEqual(final['close_advisory']['close_gate']['status'], 'UNAPPLIED_HELD')
            self.assertEqual(final['residuals']['status'], 'COMPLETE')
            self.assertEqual(final['residuals']['sections']['unapplied_cash']['totals']['unapplied_cash_krw']['total_krw'], 100)
            self.assertNotIn('impaired_slice_residuals', final['residuals']['sections'])
            self.assertEqual(final['values']['carried_remainder_contract'], '57/73')

    def test_cross_maturity_handwritten_default_interest_and_fraction(self):
        report = self.compare(specification(horizon=62))
        self.assertComparable(report)
        for branch in report['branches']:
            v = branch['final']['values']
            self.assertEqual(v['cumulative_exact_contract'], '75600/73')
            self.assertEqual(v['cumulative_exact_default'], '3600/73')
            self.assertEqual((v['interest_due_krw'], v['default_interest_due_krw']), (1035, 49))
            self.assertEqual((v['carried_remainder_contract'], v['carried_remainder_default']), ('45/73', '23/73'))
            self.assertEqual(branch['final']['phase'], 'DRAWN')

    def test_multiple_tick_chunks_match_direct_handler_execution(self):
        spec = specification([payment(900, 10000)], [payment(901, 10000)], horizon=1000)
        report = self.compare(spec)
        self.assertComparable(report)
        for branch in report['branches']:
            self.assertGreater(sum(s['command']['op'] == 'advance_day' for s in branch['steps']), 2)
            direct = CapitalService(rc.CapturedMemoryStorage(self.service.storage.load()))
            self.addCleanup(direct.observability.close)
            for step in branch['steps']:
                command = step['command']
                if command['op'] == 'advance_day':
                    self.assertLessEqual(command['to_sim_day'] - command['from_sim_day'], direct.overlay_bounds['max_step_days'])
                direct.overlay_command({'instance_id': direct.instance_id, **command})
            final = rc._final(direct, 'sim-a')
            self.assertEqual(branch['final']['values'], final['values'])
            self.assertEqual(branch['final']['state_digest'], final['state_digest'])
            self.assertEqual(branch['final']['overlay_state_digest'], final['overlay_state_digest'])

    def test_empty_overlay_at_capture_is_not_inferred_zero(self):
        report = self.compare(specification(horizon=0))
        self.assertRejected(report, 'MONETARY_EVIDENCE_NOT_BOUND')
        for branch in report['branches']:
            self.assertEqual(branch['steps'], [])
            final = branch['final']
            self.assertEqual(final['evidence_status'], 'NOT_BOUND')
            self.assertIsNone(final['values']['interest_due_krw'])
            self.assertIsNone(final['values']['unapplied_cash_krw'])
            self.assertEqual(final['values']['principal_outstanding_krw'], 90000)
            self.assertEqual(final['close_advisory']['reason'], 'EMPTY_OVERLAY')
            self.assertEqual(final['residuals']['status'], 'INCOMPLETE')

    def test_payment_only_cash_evidence_does_not_invent_interest_coverage(self):
        s = CapitalService()
        self.addCleanup(s.observability.close)
        draw_book(s, advance='sim-b', prefix='b', amount=1000)
        tick(s, 'before-target-draw', 0, 3)
        draw_book(s)
        s._persist()
        self.capture(s.storage.load())
        report = self.compare(specification([payment(3, 100)], [payment(3, 200)], horizon=3))
        self.assertRejected(report, 'MONETARY_EVIDENCE_NOT_BOUND')
        for branch in report['branches']:
            final = branch['final']
            self.assertEqual(final['residuals']['status'], 'COMPLETE')
            self.assertEqual(final['values']['unapplied_cash_krw'], 0)
            self.assertIsNone(final['values']['interest_due_krw'])
            self.assertIsNone(final['values']['cumulative_exact_contract'])
            self.assertEqual(final['close_advisory']['status'], 'NOT_BOUND')
        self.assertComparable(self.compare(specification([payment(3, 100)], [payment(3, 200)], horizon=4)))

    def test_binding_required_for_capture_day_payment_but_positive_tick_can_bind(self):
        self.assertRejected(self.compare(specification([payment(0, 100)])), 'REPAYMENT_TERMS_NOT_BOUND')
        self.assertComparable(self.compare(specification([payment(1, 100)])))
        tick(self.service, 'captured-tick', 0, 3)
        self.capture()
        report = self.compare(specification([payment(3, 100)], horizon=3))
        self.assertComparable(report)
        self.assertEqual(report['branches'][0]['steps'][0]['command']['op'], 'post_repayment')

    def test_payment_and_horizon_validation_matrix(self):
        base = specification([payment(3, 100)])
        changes = [
            ('INVALID_SPECIFICATION_FIELDS', lambda s: s.update(extra=1)),
            ('INVALID_SPECIFICATION_FORMAT', lambda s: s.update(format='other')),
            ('INVALID_ADVANCE_ID', lambda s: s.update(advance_id='real-a')),
            ('INVALID_ADVANCE_ID', lambda s: s.update(advance_id='sim-' + 'a' * 61)),
            ('EXACTLY_TWO_SCHEDULES_REQUIRED', lambda s: s['schedules'].pop()),
            ('INVALID_OR_DUPLICATE_SCHEDULE_ID', lambda s: s['schedules'][1].update(id='earlier')),
            ('INVALID_OR_DUPLICATE_SCHEDULE_ID', lambda s: s['schedules'][1].update(id='한글')),
            ('INVALID_OR_DUPLICATE_SCHEDULE_ID', lambda s: s['schedules'][1].update(id='x' * 33)),
            ('INVALID_SCHEDULE_FIELDS', lambda s: s['schedules'][0].update(waiver=True)),
            ('INVALID_PAYMENT_FIELDS', lambda s: s['schedules'][0]['payments'][0].update(rate=1)),
        ]
        for value in (-1, 1000000000001, 1.0, True, float('inf'), float('nan'), '10', None):
            changes.append(('INVALID_PAYMENT_AMOUNT', lambda s, v=value: s['schedules'][0]['payments'][0].update(amount_krw=v)))
        for value in (-1, 11, 3.0, True, '2026-11-04', None):
            changes.append(('INVALID_PAYMENT_SIM_DAY', lambda s, v=value: s['schedules'][0]['payments'][0].update(at_sim_day=v)))
        for value in (-1, 1000001, 10.0, True, None):
            changes.append(('INVALID_HORIZON_SIM_DAY', lambda s, v=value: s.update(horizon_sim_day=v)))
        for reason, mutate in changes:
            with self.subTest(reason=reason, mutate=mutate):
                spec = copy.deepcopy(base)
                mutate(spec)
                with patch.object(CapitalService, 'overlay_command', side_effect=AssertionError('validation must precede execution')):
                    self.assertRejected(self.compare(spec), reason)
        self.assertRejected(self.compare(specification([payment(3, 1), payment(2, 1)])), 'INVALID_PAYMENT_SIM_DAY')
        tick(self.service, 'capture', 0, 5)
        self.capture()
        self.assertRejected(self.compare(specification([payment(4, 1)])), 'INVALID_PAYMENT_SIM_DAY')
        self.assertRejected(self.compare(specification(horizon=4)), 'INVALID_HORIZON_SIM_DAY')

    def test_payment_count_32_33_and_amount_upper_bound(self):
        self.assertComparable(self.compare(specification([payment(1, 1)] * 32, horizon=1)))
        self.assertRejected(self.compare(specification([payment(1, 1)] * 33, horizon=1)), 'SCHEDULE_PAYMENT_LIMIT')
        report = self.compare(specification([payment(1, 10**12)]))
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        self.assertEqual(report['branches'][0]['steps'][1]['result']['code'], 'REPAYMENT_UNAPPLIED_CAP')

    def test_zero_without_held_cash_rejects_and_stops_only_one_branch(self):
        report = self.compare(specification([payment(3, 0), payment(4, 100)], [payment(6, 100)]))
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        a, b = report['branches']
        self.assertEqual([s['status'] for s in a['steps']], ['APPLIED', 'REJECTED', 'NOT_ATTEMPTED', 'NOT_ATTEMPTED', 'NOT_ATTEMPTED'])
        self.assertEqual(a['steps'][1]['result'], {'code': 'REPAYMENT_AMOUNT', 'http_status': 400, 'detail': None})
        self.assertEqual(a['final']['reached_sim_day'], 3)
        self.assertEqual(b['final']['reached_sim_day'], 10)
        self.assertTrue(all(s['status'] == 'APPLIED' for s in b['steps']))

    def test_unsupported_and_unknown_advances(self):
        spec = specification()
        spec['advance_id'] = 'sim-unknown'
        self.assertRejected(self.compare(spec), 'UNKNOWN_ADVANCE')
        for phase in ('OFFERED', 'APPROVED', 'CLOSED', 'DEFAULTED'):
            with self.subTest(phase=phase):
                s = CapitalService()
                self.addCleanup(s.observability.close)
                if phase in ('OFFERED', 'APPROVED'):
                    run(s, 'offer', 'sim-a', 'offer', fixture_id='sim-committed', amount=90000)
                    if phase == 'APPROVED':
                        run(s, 'approve', 'sim-a', 'approve')
                else:
                    draw_book(s)
                    if phase == 'CLOSED':
                        run(s, 'repay', 'sim-a', 'repay', amount=90000, sequence=1)
                    if phase == 'CLOSED':
                        run(s, 'close', 'sim-a', 'close')
                    if phase == 'DEFAULTED':
                        run(s, 'default', 'sim-a', 'default')
                s._persist()
                self.capture(s.storage.load())
                self.assertRejected(self.compare(), 'UNSUPPORTED_ADVANCE_STATE')

    def test_malformed_unrelated_draw_gate_identifies_offending_advance(self):
        draw_book(self.service, advance='sim-b', prefix='b', amount=1000)
        document = self.capture()
        document['payload']['receipts']['b-draw']['receipt']['result'] = None
        document['payload_sha256'] = rc._digest(document['payload'])
        self.capture(document)
        self.assertTrue(audit.audit_workspace(self.directory)['ok'])
        report = self.compare()
        self.assertRejected(report, 'DRAW_RECEIPT_GATE_MISSING')
        self.assertEqual(report['comparability']['checks'][-1]['entries'], ['sim-b'])
        self.assertEqual(report['branches'], [])

    def test_required_policy_and_bounds_fail_explicitly_unrelated_sections_do_not_gate(self):
        original = rc._load_policy()
        for name in rc.REQUIRED_TERMS:
            with self.subTest(name=name):
                terms, bounds, repayments, info = copy.deepcopy(original)
                terms.items[name]['mark'] = 'NOT_BOUND'
                with patch.object(rc, '_load_policy', return_value=(terms, bounds, repayments, info)):
                    self.assertRejected(self.compare(), 'POLICY_INPUTS_UNUSABLE')
        for index in (1, 2):
            inputs = list(copy.deepcopy(original))
            inputs[index] = None
            with patch.object(rc, '_load_policy', return_value=inputs):
                self.assertRejected(self.compare(), 'POLICY_INPUTS_UNUSABLE')
        terms, bounds, repayments, info = copy.deepcopy(original)
        terms.top = 'PARTIAL'
        terms.items['fees'] = {'mark': 'NOT_BOUND', 'value': None}
        with patch.object(rc, '_load_policy', return_value=(terms, bounds, repayments, info)):
            self.assertComparable(self.compare())

    def test_incompatible_binding_and_target_tier_are_rejected(self):
        tick(self.service, 'captured', 0, 3)
        self.capture()
        terms, bounds, repayments, info = rc._load_policy()
        terms.version = 'CHANGED'
        with patch.object(rc, '_load_policy', return_value=(terms, bounds, repayments, info)):
            self.assertRejected(self.compare(), 'TERMS_BINDING_INCOMPATIBLE')
        with patch.object(CapitalService, '_ledger_terms', return_value=None):
            self.assertRejected(self.compare(), 'TARGET_LEDGER_TERMS_NOT_BOUND')

    def test_every_generated_id_namespace_is_reserved_including_other_draws(self):
        draw_book(self.service, advance='sim-b', prefix='b', amount=1000)
        self.capture()
        original = rc._service
        op = 'rc-b0-c0000'
        candidates = (op, op + ':terms', op + ':interest:sim-a', op + ':interest:sim-b',
                      'rp-' + hashlib.sha256(('KIX_CAPITAL_REPAY_F04_V1|' + op).encode()).hexdigest()[:32])
        # Inject each occupied namespace only after the real audit/restore. The
        # source fixture remains valid; the reservation check must catch all.
        for namespace in ('overlay', 'receipt', 'journal'):
            for ident in candidates:
                with self.subTest(namespace=namespace, ident=ident):
                    def service(*args, **kwargs):
                        s = original(*args, **kwargs)
                        if namespace == 'overlay':
                            s.overlay_entries.append({'overlay_id': ident})
                        elif namespace == 'receipt':
                            s.receipts[ident] = {}
                        else:
                            original_journal = s.machine.export_journal
                            s.machine.export_journal = lambda: [*original_journal(), {'idempotency_key': ident, 'op': 'offer'}]
                        return s
                    # Target preflight has already been separately verified;
                    # isolate reservation from fold readers over planted ids.
                    with patch.object(rc, '_service', side_effect=service), patch.object(rc, '_preflight', return_value={}):
                        self.assertRejected(self.compare(), 'GENERATED_ID_COLLISION')

    def test_real_restored_operation_collision_is_rejected_before_execution(self):
        s = CapitalService()
        self.addCleanup(s.observability.close)
        run(s, 'offer', 'sim-b', 'rc-b0-c0000', fixture_id='sim-committed', amount=100)
        draw_book(s)
        s._persist()
        self.capture(s.storage.load())
        with patch.object(CapitalService, 'overlay_command', side_effect=AssertionError('collision executed')):
            self.assertRejected(self.compare(), 'GENERATED_ID_COLLISION')

    def test_generated_ids_do_not_use_schedule_names(self):
        spec = specification([payment(1, 100)], horizon=1)
        spec['schedules'][0]['id'] = 'A' * 32
        spec['schedules'][1]['id'] = 'B' * 32
        report = self.compare(spec)
        self.assertComparable(report)
        self.assertEqual(report['branches'][0]['steps'][0]['command']['operation_id'], 'rc-b0-c0000')
        self.assertEqual(report['branches'][1]['steps'][0]['command']['operation_id'], 'rc-b1-c0000')

    def test_capacity_and_f04_refusal_remain_visible(self):
        terms, bounds, repayments, info = rc._load_policy()
        bounds['OVERLAY_MAX_ENTRIES'] = 1
        with patch.object(rc, '_load_policy', return_value=(terms, bounds, repayments, info)):
            report = self.compare()
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        self.assertEqual(report['branches'][0]['steps'][0]['result']['code'], 'SIMULATION_CAPACITY')
        apply = PinnedFsmProducer.apply
        def refuse(s, op, *args, **kwargs):
            if op == 'repay':
                raise CreditError('SYNTHETIC_F04_REFUSAL')
            return apply(s, op, *args, **kwargs)
        with patch.object(PinnedFsmProducer, 'apply', new=refuse):
            report = self.compare(specification([payment(3, 100)], [payment(4, 100)]))
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        result = report['branches'][0]['steps'][1]['result']
        self.assertEqual(result, {'code': 'REPAYMENT_ADVANCE_STATE', 'http_status': 409,
                                  'detail': {'reason': 'SYNTHETIC_F04_REFUSAL'}})

    def test_unexpected_transport_duplicate_fails(self):
        original = CapitalService.overlay_command
        def duplicate(s, *args, **kwargs):
            return {**original(s, *args, **kwargs), 'transport_duplicate': True}
        with patch.object(CapitalService, 'overlay_command', new=duplicate):
            report = self.compare(specification([payment(3, 100)]))
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        self.assertIs(report['branches'][0]['steps'][0]['result']['transport_duplicate'], True)
        self.assertEqual(report['branches'][0]['steps'][1]['status'], 'NOT_ATTEMPTED')

    def test_final_reader_failure_and_residual_incompleteness_fail_comparison(self):
        original = rc._final
        with patch.object(rc, '_final', side_effect=ValueError('synthetic reader failure')):
            report = self.compare()
        self.assertRejected(report, 'FINAL_READER_FAILED')
        self.assertEqual(len(report['branches']), 2)
        def incomplete(*args):
            result = original(*args)
            result['residuals']['status'] = 'INCOMPLETE'
            return result
        with patch.object(rc, '_final', side_effect=incomplete):
            self.assertRejected(self.compare(), 'RESIDUALS_INCOMPLETE')

    def test_unrelated_draw_malformed_during_final_read_is_non_comparable(self):
        draw_book(self.service, advance='sim-b', prefix='b', amount=1000)
        self.capture()
        original = rc._final
        def broken_final(s, ref):
            s.receipts['b-draw']['receipt']['result'] = None
            return original(s, ref)
        with patch.object(rc, '_final', side_effect=broken_final):
            report = self.compare()
        self.assertRejected(report, 'FINAL_READER_FAILED')
        self.assertEqual(len(report['branches']), 2)
        self.assertTrue(all(b['steps'][0]['status'] == 'APPLIED' for b in report['branches']))

    def test_resources_close_after_rejected_steps_and_failed_readers(self):
        with (patch.object(rc.CapturedMemoryStorage, 'close') as close,
              patch.object(rc, '_final', side_effect=ValueError('reader'))):
            report = self.compare(specification([payment(3, 0)]))
        self.assertRejected(report, 'SCHEDULE_STEP_REJECTED')
        self.assertRejected(report, 'FINAL_READER_FAILED')
        self.assertEqual(close.call_count, 3)  # preflight and both branches

    def test_selected_residuals_ignore_unrelated_unbound_cash_before_reconciliation(self):
        tick(self.service, 'before', 0, 3)
        # New draw has no accrual yet; same-day payments touch only sim-a.
        draw_book(self.service, advance='sim-b', prefix='b', amount=1000)
        self.capture()
        spec = specification([payment(3, 100)], horizon=3)
        report = self.compare(spec)
        self.assertComparable(report)
        self.assertEqual(residuals.report_workspace(self.directory)['status'], 'INCOMPLETE')
        for b in report['branches']:
            section = b['final']['residuals']['sections']['unapplied_cash']
            self.assertEqual(section['coverage']['candidates'], 1)
            self.assertEqual([r['advance_id'] for r in section['rows']], ['sim-a'])

    def test_only_allowed_handlers_are_called_in_independent_branches(self):
        original = CapitalService.overlay_command
        seen, services = [], []
        def command(s, body, role='organizer'):
            self.assertEqual(role, 'organizer')
            self.assertEqual(s.instance_id, s.storage.writer_instance)
            self.assertNotIn('writeoff', body)
            self.assertIn(body['op'], ('advance_day', 'post_repayment'))
            seen.append((s.instance_id, body['op']))
            if not any(s is other for other in services):
                services.append(s)
            return original(s, body, role=role)
        spec = specification([payment(3, 100)], [payment(6, 200)])
        with patch.object(CapitalService, 'overlay_command', new=command):
            self.assertComparable(self.compare(spec))
        self.assertEqual({identity for identity, _ in seen}, {'repayment-compare-b0', 'repayment-compare-b1'})
        self.assertEqual(len(services), 2)
        self.assertIsNot(services[0].storage, services[1].storage)
        self.assertIsNot(services[0].machine, services[1].machine)
        self.assertIsNot(services[0].terms, services[1].terms)
        self.assertIsNot(services[0].fixtures, services[1].fixtures)
        self.assertNotEqual(services[0].machine.state_digest(), services[1].machine.state_digest())

    def test_captured_source_is_not_reopened_for_restore(self):
        original = audit.audit_workspace_bytes
        raw = self.path.read_bytes()
        def audit_then_replace(captured, **kwargs):
            result = original(captured, **kwargs)
            self.path.write_bytes(b'changed after capture')
            return result
        with patch.object(audit, 'audit_workspace_bytes', side_effect=audit_then_replace):
            report = self.compare()
        self.assertComparable(report)
        self.assertEqual(report['source']['workspace_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(self.path.read_bytes(), raw)

    def test_memory_port_copies_verifies_and_saves_without_touching_source(self):
        document = self.service.storage.load()
        port = rc.CapturedMemoryStorage(document)
        document['payload']['journal'].clear()
        loaded = port.load()
        self.assertEqual(len(loaded['payload']['journal']), 4)
        loaded['payload']['journal'].clear()
        self.assertEqual(len(port.load()['payload']['journal']), 4)
        port.writer_instance = 'deterministic'
        port.save(self.service.storage.load()['payload'])
        self.assertEqual(port.load()['saved_by_instance'], 'deterministic')
        port.document['payload_sha256'] = '0' * 64
        with self.assertRaises(store.WorkspaceError):
            port.load()
        port.close()

    def test_determinism_preservation_and_no_filesystem_network_signing_writes(self):
        spec = specification([payment(3, 45000)], [payment(6, 45000)])
        snapshot = [(p.name, p.stat().st_mode, p.read_bytes()) for p in self.directory.iterdir()]
        frozen_spec = copy.deepcopy(spec)
        with (patch.object(store.FileWorkspace, 'open', side_effect=AssertionError('filesystem port')),
              patch.object(Path, 'write_bytes', side_effect=AssertionError('write')),
              patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir')),
              patch.object(socket, 'socket', side_effect=AssertionError('network')),
              patch.object(export.UnsignedSigner, 'sign', side_effect=AssertionError('signing'))):
            first = self.compare(spec)
            second = self.compare(spec)
        self.assertComparable(first)
        self.assertEqual(store.canonical_bytes(first), store.canonical_bytes(second))
        self.assertEqual(spec, frozen_spec)
        self.assertEqual(snapshot, [(p.name, p.stat().st_mode, p.read_bytes()) for p in self.directory.iterdir()])
        for field in ('workspace_sha256', 'payload_sha256', 'f04_journal_sha256', 'overlay_journal_sha256', 'fixtures_sha256'):
            self.assertRegex(first['source'][field], r'^[0-9a-f]{64}$')
        self.assertEqual(first['source']['vendor_pin']['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertRegex(first['policy']['policy_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(first['specification_sha256'], hashlib.sha256(store.canonical_bytes(spec)).hexdigest())
        self.assertEqual(first['historical_policy_provenance'], 'NOT_BOUND')

    def test_audit_and_restore_failures_are_explicit(self):
        self.path.write_bytes(b'broken')
        self.assertRejected(self.compare(), 'WORKSPACE_AUDIT_FAILED')
        self.capture()
        original = rc._service
        def inactive(*args, **kwargs):
            s = original(*args, **kwargs)
            s.workspace_status = 'WORKSPACE_UNREADABLE'
            return s
        with patch.object(rc, '_service', side_effect=inactive):
            self.assertRejected(self.compare(), 'RESTORE_NOT_ACTIVE')

    def test_cli_canonical_subprocess_bytes_exit_codes_and_strict_json(self):
        schedule = self.directory / 'schedules.json'
        schedule.write_bytes(store.canonical_bytes(specification([payment(3, 100)])))
        command = [sys.executable, '-m', 'capital.repayment_compare', '--workspace', str(self.directory), '--schedule', str(schedule)]
        first = subprocess.run(command, cwd=ROOT, capture_output=True)
        second = subprocess.run(command, cwd=ROOT, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, b'')
        self.assertEqual(first.stdout, store.canonical_bytes(json.loads(first.stdout)) + b'\n')
        for raw in (b'{"format":1,"format":2}', b'{"x":NaN}', b'{"x":Infinity}', b'not json'):
            with self.subTest(raw=raw):
                schedule.write_bytes(raw)
                result = subprocess.run(command, cwd=ROOT, capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)['reason'], 'INVALID_SCHEDULE_JSON')
                self.assertEqual(json.loads(result.stdout)['mode'], 'SIMULATED_REPAYMENT_COMPARISON')
        for value in (True, 1.0):
            spec = specification([payment(3, value)])
            schedule.write_bytes(store.canonical_bytes(spec))
            result = subprocess.run(command, cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertRejected(json.loads(result.stdout), 'INVALID_PAYMENT_AMOUNT')
        result = subprocess.run([sys.executable, '-m', 'capital.repayment_compare'], cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
