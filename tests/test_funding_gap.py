"""Audited SIMULATED funding sources, contractual dues and independent reconciliation."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from capital import funding_gap, overlay, portfolio_snapshot, recovery, resources, store
from capital.evidence import offline_service
from scripts import funding_gap_vectors as vectors
from scripts import seed_overlay_slices

ROOT = Path(__file__).resolve().parents[1]
HALL = 'demo-alpha-hall'
ARENA = 'demo-alpha-arena'
ADVANCE = vectors.ADVANCE
EVALUATED = 'EVALUATED_HYPOTHETICAL'


def command(service, op, key, *, ref=ADVANCE, **args):
    result = service.execute({'instance_id': service.instance_id, 'operation_id': key,
                              'op': op, 'advance_id': ref, 'args': args})
    if result['outcome'] != 'ACCEPTED':
        raise AssertionError(result)
    return result


def tick(service, start, end):
    return service.overlay_command({'instance_id': service.instance_id, 'operation_id': f'day-{end}',
                                    'op': 'advance_day', 'from_sim_day': start, 'to_sim_day': end,
                                    'reason': 'funding gap test'})


def overlay_action(service, op, key, **args):
    return service.overlay_command({'instance_id': service.instance_id, 'operation_id': key,
                                    'op': op, 'advance_ref': ADVANCE,
                                    'at_sim_day': overlay.fold(service.overlay_entries)['sim_day'], **args})


def day(report, number):
    return next(row for row in report['daily'] if row['sim_day'] == number)


def dues(report):
    return {row['obligation_id']: row['amount_krw'] for row in report['obligations']}


def opening(*lots, cut=0):
    return {'origin': 'EXPLICIT_SYNTHETIC_ASSUMPTION', 'as_of_sim_day': cut,
            'total_krw': sum(lot['amount_krw'] for lot in lots), 'lots': list(lots)}


def received(kind, ref, lot_id, offset, amount):
    return {'kind': 'SETTLEMENT_RECEIPT', 'lot_id': lot_id, 'amount_krw': amount,
            'reference': {'kind': kind, 'id': ref}, 'received_offset_krw': offset}


def distributed_hall(view):
    """Detached-only fixture evidence, used because the workspace pins immutable views."""
    claim = view['claim']
    claim['distribution_order'] = ['organizer', 'platform']
    claim['obligations'][0]['distributed'] = 200
    claim['obligations'][0]['outstanding'] -= 200
    claim['distributed_cash'] = 200
    claim['undistributed_cash'] -= 200


class FundingGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((vectors.VECTOR_DIR / store.FILE_NAME).read_bytes())
        cls.baseline = json.loads((vectors.VECTOR_DIR / 'timely.schedule.json').read_bytes())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.workspace_path = self.workspace / store.FILE_NAME
        self.schedule_path = self.workspace / 'schedule.json'

    def write(self, envelope=None, **changes):
        spec = vectors.schedule(envelope, **changes) if envelope is not None else {**self.baseline, **changes}
        self.workspace_path.write_bytes(vectors.dump(envelope if envelope is not None else self.base))
        self.schedule_path.write_bytes(vectors.dump(spec))

    def report(self, envelope=None, **changes):
        self.write(envelope, **changes)
        return funding_gap.report_workspace(self.workspace, self.schedule_path)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/funding_gap.py'), *map(str, args)],
                              capture_output=True, cwd=self.workspace, timeout=10)

    def assert_unavailable(self, report, status, reason):
        self.assertEqual(report['status'], status, report['issues'])
        self.assertIn(reason, [issue['reason'] for issue in report['issues']])
        for key in ('daily', 'metrics', 'outside_horizon'):
            self.assertIsNone(report[key])

    def assert_reconciles(self, report):
        daily = report['daily']
        end = daily[-1]['sim_day']
        for source in report['sources']:
            received = sum(row['amount_krw'] for row in source['releases'] if row['available_sim_day'] <= end)
            later = sum(row['amount_krw'] for row in source['releases'] if row['available_sim_day'] > end)
            self.assertEqual(source['budget_krw'], received + later + source['unscheduled_budget_krw'])
        resources = report['opening_cash']['total_krw'] + sum(row['source_inflows_krw'] for row in daily)
        covered = sum(row['covered_krw'] for row in daily)
        scheduled_dues = sum(row['amount_krw'] for row in report['obligations'] if row['due_sim_day'] <= end)
        self.assertEqual(resources, covered + daily[-1]['closing_carry_krw'])
        self.assertEqual(scheduled_dues, covered + daily[-1]['shortage_krw'])
        for row in daily:
            self.assertEqual(row['resources_krw'], row['covered_krw'] + row['closing_carry_krw'])
            self.assertEqual(row['opening_shortage_krw'] + row['new_dues_krw'],
                             row['covered_krw'] + row['shortage_krw'])

    def test_pinned_scenarios_cli_bytes_and_unchanged_forecast_and_workspace(self):
        before = vectors.dump(self.base)
        service = offline_service(self.base)
        forecast_before = service.forecast(service.instance_id)
        self.workspace_path.write_bytes(before)
        for case, expected in (('timely', (0, 0, None)), ('late', (10_115, 0, 60)),
                               ('insufficient', (1, 1, 60)), ('post-setoff', None)):
            with self.subTest(case=case):
                args = ('--workspace', self.workspace, '--schedule', vectors.VECTOR_DIR / f'{case}.schedule.json')
                first, second = self.cli(*args), self.cli(*args)
                self.assertEqual(first.stderr, b'')
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(first.stdout, (vectors.VECTOR_DIR / f'{case}.report.json').read_bytes())
                report = json.loads(first.stdout)
                self.assertEqual(first.returncode, int(expected is None))
                if expected is None:
                    self.assert_unavailable(report, 'UNEVALUATED', 'PRE_SETOFF_ALLOCATION_UNVERIFIED')
                    continue
                self.assertEqual(report['assumptions']['forecast_digest'], forecast_before['forecast_digest'])
                self.assertEqual(dues(report), {'PRINCIPAL': 10_000, 'CONTRACT_INTEREST': 115})
                self.assertEqual([report['metrics'][key] for key in
                                  ('peak_shortage_krw', 'terminal_shortage_krw', 'first_shortage_sim_day')],
                                 list(expected))
                self.assertEqual((day(report, 60)['new_dues_krw'], day(report, 61)['source_inflows_krw']),
                                 (10_115, 0))
                if case == 'late':
                    self.assertEqual((day(report, 60)['covered_krw'], day(report, 62)['covered_krw']), (0, 10_115))
                self.assert_reconciles(report)
        self.assertEqual(self.workspace_path.read_bytes(), before)
        self.assertEqual(offline_service(json.loads(before)).forecast(service.instance_id), forecast_before)
        self.assertEqual(self.cli('--workspace', self.workspace).returncode, 2)
        self.assertEqual(list(self.workspace.iterdir()), [self.workspace_path])
        pledged = vectors.VECTOR_DIR / 'pledged'
        result = self.cli('--workspace', pledged, '--schedule', pledged / 'hall.schedule.json')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, (pledged / 'hall.report.json').read_bytes())
        self.assert_unavailable(json.loads(result.stdout), 'UNEVALUATED', 'UNSELECTED_ADVANCE_COMMITMENT')

    def test_capture_pins_audit_and_read_once(self):
        for pin, wrong in (('workspace_id', 'sha256:' + 'a'*64), ('snapshot_digest', 'a'*64)):
            with self.subTest(pin=pin):
                report = self.report(**{pin: wrong})
                self.assert_unavailable(report, 'INVALID_INPUT', 'CAPTURE_PIN_MISMATCH')
                self.assertEqual(report['issues'], [{'pin': pin, 'reason': 'CAPTURE_PIN_MISMATCH'}])
        self.write()
        with patch.object(funding_gap, '_read_regular', wraps=funding_gap._read_regular) as read:
            report = funding_gap.report_workspace(self.workspace, self.schedule_path)
            self.assertEqual(report['status'], EVALUATED)
            self.assertEqual(sum(call.args[0] == self.workspace_path for call in read.call_args_list), 1)
        self.assertEqual(report['workspace_id'], 'sha256:' + hashlib.sha256(self.workspace_path.read_bytes()).hexdigest())
        self.assertEqual(report['schedule_sha256'], hashlib.sha256(self.schedule_path.read_bytes()).hexdigest())
        service = offline_service(self.base)
        snapshot = service.portfolio_snapshot(service.instance_id)
        digest = hashlib.sha256(store.canonical_bytes({key: snapshot[key] for key in
            ('format', 'cut', 'assumptions', 'completeness', *portfolio_snapshot.SECTIONS)})).hexdigest()
        self.assertEqual(report['snapshot_digest'], digest)
        self.assertEqual(report['cut'], snapshot['cut'])
        self.assertEqual(report['policy_digest'], portfolio_snapshot.digest(report['policies']))
        for note, policy in report['policies'].items():
            self.assertEqual(policy['note_sha256'], hashlib.sha256(resources.note_path(note).read_bytes()).hexdigest())
        self.assertEqual((report['label'], report['source_label'], report['mode'], report['production']),
                         ('SIMULATED', 'READ_ONLY_FIXTURE', 'HYPOTHETICAL_FUNDING_GAP', 'NOT_AUTHORIZED'))
        self.assertTrue(report['provisional'] and report['non_posting'])
        self.assertFalse(report['funds_executed'])
        tampered = copy.deepcopy(self.base)
        tampered['payload_sha256'] = '0'*64
        self.workspace_path.write_bytes(vectors.dump(tampered))
        report = funding_gap.report_workspace(self.workspace, self.schedule_path)
        self.assert_unavailable(report, 'UNEVALUATED', 'WORKSPACE_UNREADABLE')
        self.assertEqual(report['audit']['failed_check'], 'payload_sha256')

    def test_unique_source_and_obligation_keys_across_aliases(self):
        service = vectors.book()
        vectors.draw(service, amount=60)
        vectors.draw(service, 'sim-shared-hall', HALL, 50)
        repeated = [vectors.source('FIXTURE', HALL, amount=100), vectors.source('CLAIM', HALL, amount=100),
                    vectors.source('ADVANCE', 'sim-shared-hall', amount=100)]
        report = self.report(vectors.document(service), advance_ids=[ADVANCE, 'sim-shared-hall', ADVANCE],
                             sources=repeated)
        self.assertEqual(report['status'], EVALUATED, report['issues'])
        self.assertEqual(len(report['sources']), 1)
        source = report['sources'][0]
        self.assertEqual(len(source['references']), 3)
        self.assertEqual(source['source_key'], {'workspace_id': report['workspace_id'], 'beneficiary_id': 'demo-org-alpha',
                         'claim_id': HALL, 'settlement_entitlement_id': 'organizer', 'currency': 'KRW'})
        self.assertEqual(len(report['obligations']), 4)
        self.assertEqual(report['assumptions']['raw_event_rows'], 9)
        self.assertEqual((day(report, 60)['source_inflows_krw'], day(report, 60)['new_dues_krw'],
                          day(report, 60)['covered_krw'], day(report, 60)['shortage_krw']), (100, 110, 100, 10))
        evidence = source['evidence']
        self.assertEqual(evidence['claim_cash_krw'], {'gross': 1_200_000_000, 'confirmed_cash': 1_164_000_000,
                         'non_cash_accounted': 36_000_000, 'distributed_cash': 0, 'undistributed_cash': 1_164_000_000})
        self.assertEqual(evidence['payee_lines_krw']['platform']['outstanding'], 60_000_000)
        self.assertEqual(evidence['prospective_allocation_krw'], {'organizer': 1_140_000_000, 'platform': 24_000_000})
        self.assertEqual(evidence['application'], 'SHADOW_NOT_APPLIED')
        self.assert_reconciles(report)

    def test_unselected_commitment_and_beneficiary_boundaries(self):
        service = vectors.book()
        vectors.draw(service)
        vectors.draw(service, 'sim-pledged-hall', HALL, 300)
        vectors.draw(service, 'sim-beta', 'demo-beta-festival', 300)
        envelope = vectors.document(service)
        report = self.report(envelope)
        self.assert_unavailable(report, 'UNEVALUATED', 'UNSELECTED_ADVANCE_COMMITMENT')
        report = self.report(envelope, advance_ids=[ADVANCE, 'sim-beta'])
        self.assert_unavailable(report, 'UNEVALUATED', 'ADVANCE_BENEFICIARY_OR_FIXTURE_UNVERIFIED')
        report = self.report(envelope, sources=[vectors.source('ADVANCE', 'sim-beta')])
        self.assert_unavailable(report, 'UNEVALUATED', 'ADVANCE_BENEFICIARY_OR_FIXTURE_UNVERIFIED')
        report = self.report(envelope, sources=[vectors.source('CLAIM', 'sim-missing')])
        self.assert_unavailable(report, 'UNEVALUATED', 'CLAIM_ALIAS_UNRESOLVED')

    def test_raw_bounds_and_outside_horizon_before_deduplication(self):
        source = vectors.source(day=63)
        for n in (1022, 1023):
            with self.subTest(n=n):
                candidate = {**source, 'releases': source['releases'] * n}
                report = self.report(sources=[candidate], horizon_days=1)
                if n == 1023:
                    self.assert_unavailable(report, 'INVALID_INPUT', 'RAW_EVENT_ROW_LIMIT')
                    continue
                self.assertEqual(report['status'], EVALUATED)
                self.assertEqual(report['outside_horizon'], {
                    'releases': {'count': 1, 'amount_krw': 10_115, 'first_sim_day': 63},
                    'obligations': {'count': 2, 'amount_krw': 10_115, 'first_sim_day': 60}})
                self.assert_reconciles(report)
        exact = self.report(horizon_days=60)
        self.assertEqual(exact['outside_horizon']['obligations']['count'], 0)
        self.assertEqual(exact['outside_horizon']['releases']['count'], 0)
        self.assert_unavailable(self.report(advance_ids=[ADVANCE] * 513), 'INVALID_INPUT', 'RAW_EVENT_ROW_LIMIT')
        self.assert_unavailable(self.report(advance_ids=[f'sim-{i}' for i in range(33)]),
                                'INVALID_INPUT', 'UNIQUE_ADVANCE_LIMIT')
        self.assert_unavailable(self.report(advance_ids=[]), 'INVALID_INPUT', 'UNIQUE_ADVANCE_LIMIT')
        self.assertEqual(len(self.report(horizon_days=365)['daily']), 365)
        self.assertEqual(len(self.report(horizon_days=1)['daily']), 1)
        self.assertEqual(len(self.report()['daily']), 62)
        self.write()
        spec = json.loads(self.schedule_path.read_bytes())
        self.schedule_path.write_bytes(vectors.dump({k: v for k, v in spec.items() if k != 'horizon_days'}))
        self.assertEqual(len(funding_gap.report_workspace(self.workspace, self.schedule_path)['daily']), 30)

    def test_invalid_amounts_dates_shapes_and_conflicts(self):
        initial = vectors.source()
        cases = [
            ({'horizon_days': True}, 'HORIZON_OUT_OF_BOUNDS'),
            ({'horizon_days': 366}, 'HORIZON_OUT_OF_BOUNDS'),
            ({'extra': 1}, 'UNEXPECTED_OR_MISSING_FIELDS'),
            ({'sources': [{**initial, 'budget_krw': 12000.0}]}, 'AMOUNT_OUT_OF_BOUNDS'),
            ({'sources': [{**initial, 'budget_krw': 1_000_000_000_001}]}, 'AMOUNT_OUT_OF_BOUNDS'),
            ({'sources': [vectors.source(amount=True)]}, 'AMOUNT_OUT_OF_BOUNDS'),
            ({'sources': [vectors.source(amount=-1)]}, 'AMOUNT_OUT_OF_BOUNDS'),
            ({'sources': [vectors.source(day=0)]}, 'RELEASE_ON_OR_BEFORE_CUT'),
            ({'sources': [vectors.source(day=2**31-1, delay=1)]}, 'SIM_DAY_OUT_OF_BOUNDS'),
            ({'sources': [vectors.source(delay=-1)]}, 'DELAY_OUT_OF_BOUNDS'),
            ({'sources': [vectors.source(amount=12_001)]}, 'RELEASES_EXCEED_SOURCE_BUDGET'),
            ({'sources': [{**initial, 'budget_krw': 1_140_000_001}]}, 'SOURCE_BUDGET_EXCEEDS_ENTITLEMENT'),
            ({'sources': [initial, vectors.source('CLAIM', HALL, day=61)]}, 'CONFLICTING_RELEASE'),
            ({'sources': [initial, {**initial, 'budget_krw': 12_001}]}, 'CONFLICTING_SOURCE_BUDGET_DELAY_OR_BASIS'),
        ]
        for kwargs, reason in cases:
            with self.subTest(reason=reason):
                self.assert_unavailable(self.report(**kwargs), 'INVALID_INPUT', reason)
        valid = self.report(sources=[vectors.source(day=2**31-1)])
        self.assertEqual(valid['outside_horizon']['releases']['first_sim_day'], 2**31-1)
        self.assertEqual(self.report(sources=[])['metrics']['terminal_shortage_krw'], 10_115)
        self.write()
        spec = json.loads(self.schedule_path.read_bytes())
        del spec['sources']
        self.schedule_path.write_bytes(vectors.dump(spec))
        self.assert_unavailable(funding_gap.report_workspace(self.workspace, self.schedule_path),
                                'INVALID_INPUT', 'UNEXPECTED_OR_MISSING_FIELDS')

    def test_local_regular_schedule_size_and_strict_decoding(self):
        self.write()
        raw = self.schedule_path.read_bytes()
        self.schedule_path.write_bytes(raw.ljust(funding_gap.SCHEDULE_MAX_BYTES, b' '))
        self.assertEqual(funding_gap.report_workspace(self.workspace, self.schedule_path)['status'], EVALUATED)
        self.schedule_path.write_bytes(raw.ljust(funding_gap.SCHEDULE_MAX_BYTES + 1, b' '))
        self.assert_unavailable(funding_gap.report_workspace(self.workspace, self.schedule_path),
                                'INVALID_INPUT', 'SCHEDULE_TOO_LARGE')
        for malformed in (b'{"a":1,"a":1}', b'{"a":NaN}', b'\xef\xbb\xbf' + raw, b'\xff'):
            self.schedule_path.write_bytes(malformed)
            self.assert_unavailable(funding_gap.report_workspace(self.workspace, self.schedule_path),
                                    'INVALID_INPUT', 'SCHEDULE_UNREADABLE')
        fifo = self.workspace / 'schedule.fifo'
        os.mkfifo(fifo)
        self.assert_unavailable(funding_gap.report_workspace(self.workspace, fifo),
                                'INVALID_INPUT', 'SCHEDULE_UNREADABLE')

    def test_opening_endowment_and_traced_received_portions(self):
        default = self.report()
        self.assertEqual(default['opening_cash_origin'], 'DEFAULT_ZERO')
        endowment = {'kind': 'INDEPENDENT_SYNTHETIC_ENDOWMENT', 'lot_id': 'endowment', 'amount_krw': 20}
        report = self.report(opening_cash=opening(endowment))
        self.assertEqual(report['opening_cash_origin'], 'EXPLICIT_SYNTHETIC_ASSUMPTION')
        self.assertEqual((day(report, 1)['opening_carry_krw'], day(report, 62)['closing_carry_krw']), (20, 20))
        self.assert_reconciles(report)
        self.assert_unavailable(self.report(opening_cash=opening(endowment, cut=1)),
                                'INVALID_INPUT', 'OPENING_CASH_CUT_MISMATCH')
        self.assert_unavailable(self.report(opening_cash={**opening(endowment), 'total_krw': 21}),
                                'INVALID_INPUT', 'OPENING_CASH_TOTAL_MISMATCH')
        self.assert_unavailable(self.report(opening_cash=opening(endowment, {**endowment, 'lot_id': 'alias'})),
                                'UNEVALUATED', 'INDEPENDENT_ENDOWMENT_OVERLAP_UNVERIFIED')
        first = received('FIXTURE', HALL, 'first', 0, 100)
        second = received('CLAIM', HALL, 'second', 100, 100)
        self.assert_unavailable(self.report(opening_cash=opening(first)), 'UNEVALUATED', 'OPENING_RECEIPT_PORTION_UNVERIFIED')
        original = funding_gap.Capture.fixture

        def fixture(capture, ref, beneficiary):
            view, _ = original(capture, ref, beneficiary)
            view = copy.deepcopy(view)
            if ref == HALL:
                distributed_hall(view)
            return view, view['claim']

        with patch.object(funding_gap.Capture, 'fixture', fixture):
            report = self.report(opening_cash=opening(first, second))
            self.assertEqual(report['status'], EVALUATED, report['issues'])
            self.assertEqual(report['sources'][0]['evidence']['remaining_entitlement_krw'], 1_139_999_800)
            self.assertEqual(report['opening_cash']['lots'][0]['source_key'], report['opening_cash']['lots'][1]['source_key'])
            self.assert_reconciles(report)
            self.assert_unavailable(self.report(opening_cash=opening(first, {**second, 'received_offset_krw': 99})),
                                    'UNEVALUATED', 'OVERLAPPING_OPENING_RECEIPT_PORTIONS')

    def test_partial_repayment_preserves_fractional_carry_and_excludes_paid_interest(self):
        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 17)
        p = overlay_action(service, 'post_repayment', 'partial-pay', amount_krw=333)
        self.assertEqual(p['allocation']['interest_krw'], 32)
        self.assertEqual(p['allocation']['principal_krw'], 301)
        report = self.report(vectors.document(service))
        # Independent calculation from exact borrowed days before and after repayment.
        terms = service.terms.ledger_terms(service.machine.view(ADVANCE), service.fixtures.view(ARENA)['claim'],
                                           gate='MOCK_COMMIT_OBSERVED', draw_day=0)
        first = Fraction(10_000 * 17 * terms['contract_bps'], terms['denominator'])
        remaining = Fraction(9_699 * 43 * terms['contract_bps'], terms['denominator'])
        self.assertEqual(int(first + remaining) - int(first), 80)
        self.assertEqual(int(remaining), 79)
        self.assertEqual(dues(report), {'PRINCIPAL': 9_699, 'CONTRACT_INTEREST': 80})
        self.assertEqual(report['status'], EVALUATED)
        self.assert_reconciles(report)

    def test_closed_residual_interest_is_dated_and_cut_day_due_is_unevaluated(self):
        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 17)
        command(service, 'repay', 'principal-only', amount=10_000, sequence=1)
        command(service, 'close', 'advisory-close')
        future = self.report(vectors.document(service), sources=[])
        self.assertEqual(future['status'], EVALUATED)
        self.assertEqual(dues(future), {'PRINCIPAL': 0, 'CONTRACT_INTEREST': 32})
        self.assertEqual(day(future, 60)['new_dues_krw'], 32)

        tick(service, 17, 60)
        report = self.report(vectors.document(service), sources=[])
        self.assert_unavailable(report, 'UNEVALUATED', 'UNPAID_OBLIGATION_ON_OR_BEFORE_CUT')
        self.assertEqual(report['obligations'][1]['amount_krw'], 32)

    def test_unpaid_cut_day_principal_and_cut_day_release(self):
        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 60)
        envelope = vectors.document(service)
        self.assert_unavailable(self.report(envelope, sources=[]),
                                'UNEVALUATED', 'UNPAID_OBLIGATION_ON_OR_BEFORE_CUT')
        self.assert_unavailable(self.report(envelope), 'INVALID_INPUT', 'RELEASE_ON_OR_BEFORE_CUT')

    def test_later_draw_uses_recorded_day_and_release_delay_only_moves_availability(self):
        service = vectors.book()
        tick(service, 0, 9)
        vectors.draw(service)
        report = self.report(vectors.document(service), sources=[vectors.source(day=67, delay=2)])
        self.assertEqual(report['status'], EVALUATED)
        self.assertEqual((report['daily'][0]['sim_day'], day(report, 69)['source_inflows_krw'],
                          day(report, 69)['new_dues_krw']), (10, 10_115, 10_115))
        self.assertEqual(dues(report), {'PRINCIPAL': 10_000, 'CONTRACT_INTEREST': 115})
        self.assert_reconciles(report)

    def test_called_advance_with_acceleration_in_horizon_is_not_bound(self):
        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 1)
        envelope = vectors.document(service)
        ledger = service.terms.margin_terms(service.machine.view(ADVANCE), service.fixtures.view(ARENA)['claim'],
                                            gate='MOCK_COMMIT_OBSERVED', draw_day=0)
        deadline = 1 + ledger['cure_window_days']
        call = {'kind': overlay.KIND_MARGIN_CALL, 'overlay_id': 'scheduled-acceleration-test',
                'sim_day': 1, 'after_journal_index': len(service.machine.export_journal()),
                'payload': {
                    'advance_id': ADVANCE, 'outstanding_krw': 10_000, 'base_krw': 9_000,
                    'eligible_face_krw': 9_000 * 10_000 // ledger['advance_rate_bps'],
                    'tier': ledger['tier'], 'advance_rate_bps': ledger['advance_rate_bps'],
                    'cure_window_days': ledger['cure_window_days'], 'cure_deadline': deadline,
                    'cure_option': ledger['cure_options'][0], 'maturity_day': ledger['maturity_day'],
                    'terms_version': ledger['terms_version'],
                }}
        envelope['overlay'] = overlay.build_section([*envelope['overlay']['journal'], call])
        self.assertEqual(self.report(envelope, horizon_days=deadline - 1)['status'], EVALUATED)
        self.assert_unavailable(self.report(envelope, horizon_days=deadline),
                                'UNEVALUATED', 'ACCELERATION_WITHIN_HORIZON')

    def test_incompatible_binding_missing_record_and_unapplied_cash(self):
        service = vectors.book()
        vectors.draw(service)
        self.assert_unavailable(self.report(vectors.document(service, bind_day_zero=False)),
                                'UNEVALUATED', 'RECORDED_TERMS_BINDING_MISSING_OR_INCOMPATIBLE')
        tick(service, 0, 17)
        overlay_action(service, 'post_repayment', 'excess', amount_krw=20_000)
        self.assert_unavailable(self.report(vectors.document(service)), 'UNEVALUATED', 'UNAPPLIED_REPAYMENT_CASH_HELD')
        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 17)
        command(service, 'repay', 'principal-only', amount=10_000, sequence=1)
        command(service, 'close', 'advisory-close')
        envelope = vectors.document(service)
        old = envelope['overlay']['journal']
        altered = copy.deepcopy(old)
        next(row for row in altered if row['kind'] == overlay.KIND_INTEREST)['payload']['maturity_day'] += 1
        envelope['overlay'] = overlay.build_section(altered)
        self.assert_unavailable(self.report(envelope, sources=[]),
                                'UNEVALUATED', 'RECORDED_INTEREST_TERMS_OR_MATURITY_MISMATCH')
        envelope['overlay'] = overlay.build_section([row for row in old if row['kind'] != overlay.KIND_INTEREST])
        self.assert_unavailable(self.report(envelope, sources=[]), 'UNEVALUATED', 'RECORDED_ACCRUAL_INCOMPLETE')

    def test_restricted_slice_default_acceleration_and_writeoff(self):
        service = vectors.book()
        vectors.draw(service)
        seed_overlay_slices.register(service, 'sim-hall-slice', 50_000, HALL)
        seed_overlay_slices.open_slice(service, 'sim-hall-slice')
        self.assert_unavailable(self.report(vectors.document(service)), 'UNEVALUATED', 'SLICE_ENCUMBRANCE_OR_PRIOR_USE')

        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 1)
        overlay_action(service, 'record_acceleration', 'accel', event='BENEFICIARY_INSOLVENCY_NOTICE')
        self.assert_unavailable(self.report(vectors.document(service)), 'UNEVALUATED', 'ACCELERATED_OBLIGATION')

        service = vectors.book()
        vectors.draw(service)
        tick(service, 0, 1)
        command(service, 'default', 'default')
        self.assert_unavailable(self.report(vectors.document(service)), 'UNEVALUATED', 'DEFAULT_RECOVERY_OR_WRITEOFF')
        until = 1 + service.terms._value('default_loss_treatment')['writeoff_days_after_default']
        tick(service, 1, until)
        overlay_action(service, 'post_writeoff', 'writeoff', setoff_declined_reason='SIMULATED_TEST')
        self.assert_unavailable(self.report(vectors.document(service), sources=[]),
                                'UNEVALUATED', 'DEFAULT_RECOVERY_OR_WRITEOFF')

    def test_dispute_refund_and_prior_source_use_fail_closed(self):
        original = funding_gap.Capture.fixture

        def changed(capture, ref, beneficiary):
            view, _ = original(capture, ref, beneficiary)
            view = copy.deepcopy(view)
            if ref == HALL:
                view['claim'].update(changes)
            return view, view['claim']

        for changes in ({'disputed': True}, {'refund_outstanding': 1}, {'pg_adjustment_outstanding': 1}):
            with patch.object(funding_gap.Capture, 'fixture', changed):
                self.assert_unavailable(self.report(), 'UNEVALUATED', 'REFUND_DISPUTE_OR_RESTRICTED_RESIDUAL')
        initialize = funding_gap.Capture.__init__

        def prior_use(capture, *args):
            initialize(capture, *args)
            capture.used_sources.add(recovery.source_key(HALL, 'organizer'))

        with patch.object(funding_gap.Capture, '__init__', prior_use):
            self.assert_unavailable(self.report(), 'UNEVALUATED', 'PRIOR_SETTLEMENT_SOURCE_USE')

    def test_missing_required_policy_is_not_bound(self):
        read = resources.read_note

        def deferred(path, **kwargs):
            note = read(path, **kwargs)
            if path.name == funding_gap.REPAYMENT_NOTE:
                note['block']['entries']['close_gate_enforcement'].update(status='DEFERRED', value=None)
            return note

        with patch.object(resources, 'read_note', deferred):
            report = self.report()
        self.assert_unavailable(report, 'UNEVALUATED', 'REQUIRED_POLICY_NOT_ADOPTED')
        self.assertEqual(report['policies'][funding_gap.REPAYMENT_NOTE]['entries']['close_gate_enforcement']['status'],
                         'DEFERRED')

    def test_vector_checker_reports_missing_changed_and_unexpected(self):
        shutil.copytree(vectors.VECTOR_DIR, self.workspace, dirs_exist_ok=True)
        (self.workspace / 'timely.report.json').unlink()
        (self.workspace / 'late.schedule.json').write_text('{}\n')
        (self.workspace / 'extra.json').write_text('{}\n')
        check = subprocess.run([sys.executable, str(ROOT / 'scripts/funding_gap_vectors.py'),
                                '--check', '--dir', str(self.workspace)], capture_output=True, text=True, timeout=10)
        self.assertEqual(check.returncode, 1)
        for error in ('missing timely.report.json', 'changed late.schedule.json', 'unexpected extra.json'):
            self.assertIn(error, check.stderr)


if __name__ == '__main__':
    unittest.main()
