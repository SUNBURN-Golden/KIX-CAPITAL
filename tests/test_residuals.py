"""Audited SIMULATED fixtures and independent residual conservation checks."""
import copy
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from capital import audit, evidence, overlay, recovery, residuals, store
from capital.service import CapitalService
from tests.test_overlay import draw_book, run, tick, terms_value
from tests.test_repayment_posting import pay
from tests.test_recovery import book, cmd, recover, seed as recovery_seed
from tests.test_claim_slices import seed as slice_seed

ROOT = Path(__file__).resolve().parents[1]


class ResidualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.path = self.directory / store.FILE_NAME

    def service(self):
        s = CapitalService()
        self.addCleanup(s.observability.close)
        return s

    def capture(self, s, document=None):
        if document is None:
            s._persist()
            document = s.storage._document
        self.path.write_bytes(store.canonical_bytes(document))
        self.path.chmod(0o600)
        checked = audit.audit_workspace(self.directory)
        self.assertTrue(checked['ok'], checked)
        return self.path.read_bytes()

    def report(self, s):
        self.capture(s)
        result = residuals.report_workspace(self.directory)
        self.assertNotEqual(result['status'], 'AUDIT_FAILED', result['reasons'])
        return result

    def closed(self, s=None, ref='sim-a', amount=90000, cash=None):
        s = s or self.service()
        draw_book(s, advance=ref, amount=amount, prefix=ref)
        day = overlay.fold(s.overlay_entries)['sim_day']
        tick(s, ref + '-tick', day, day + 5)
        self.assertEqual(run(s, 'repay', ref, ref + '-principal', amount=amount, sequence=1)['outcome'], 'ACCEPTED')
        self.assertEqual(run(s, 'close', ref, ref + '-close')['outcome'], 'ACCEPTED')
        if cash is not None:
            gate = overlay.advance_gate(overlay.fold(s.overlay_entries), ref)
            pay(s, ref + '-cash', sum(gate[k] for k in ('interest_due_krw', 'default_interest_due_krw')) + cash, advance=ref)
        return s

    def default(self):
        source, s = book()
        self.addCleanup(s.observability.close)
        self.assertEqual(run(s, 'default', 'sim-a', 'default')['outcome'], 'ACCEPTED')
        recovery_seed.distribute(source, 'sim-committed')
        return source, s

    def writeoff(self):
        source, s = self.default()
        s.overlay_command(recover(s, 5000, 'early'))
        eligible = recovery.anchor(overlay.fold(s.overlay_entries), 'sim-a')['writeoff_eligible_sim_day']
        tick(s, 'writeoff-tick', 10, eligible + 1)
        s.overlay_command(cmd(s, 'post_writeoff', 'writeoff',
                             setoff_declined_reason='SIMULATED_FIXTURE_DECLINE'))
        s.overlay_command(recover(s, 1000, 'late'))
        return source, s

    def impaired(self):
        source, s = slice_seed.book()
        self.addCleanup(s.observability.close)
        claim = 'demo-delta-small'
        face = s.slice_policy['threshold'] // 5
        slice_seed.register(s, 'sim-slice', face, claim)
        slice_seed.open_slice(s, 'sim-slice')
        line = next(r for r in source.view(claim)['claim']['obligations'] if r['payee'] == 'organizer')
        slice_seed.refund(source, claim, line['outstanding'])
        slice_seed.post(s, 'impair_slice', 'impair', slice_id='sim-slice', reason='REFUND_REDUCED_LINE')
        return source, s, face

    def test_closed_principal_does_not_extinguish_interest_and_fractional_carry(self):
        result = self.report(self.closed())
        row = result['sections']['closed_unpaid_interest']['rows'][0]
        bps = terms_value('interest_rate')['tiers'][0]['all_in_bps_annual']
        exact = Fraction(90000 * 5 * bps, 365 * 10000)
        self.assertEqual(row['amounts'], {'interest_due_krw': int(exact), 'default_interest_due_krw': 0})
        self.assertEqual(Fraction(row['remainders']['contract_subwon']), exact - int(exact))
        self.assertEqual(row['lifecycle_status'], 'CLOSED')
        self.assertEqual(row['evidence_status'], 'BOUND')
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['sections']['unapplied_cash']['totals']['unapplied_cash_krw']['total_krw'], 0)

    def test_closed_cash_keeps_identity_and_validated_zero_interest(self):
        result = self.report(self.closed(cash=500))
        cash = result['sections']['unapplied_cash']
        self.assertEqual(cash['rows'][0]['amounts'], {'unapplied_cash_krw': 500})
        self.assertEqual(cash['rows'][0]['lifecycle_status'], 'CLOSED')
        self.assertEqual(result['sections']['closed_unpaid_interest']['rows'][0]['amounts']['interest_due_krw'], 0)
        self.assertTrue(cash['reconciliation']['matched'])

    def test_cash_is_never_netted_against_another_closed_case(self):
        s = self.closed(ref='sim-cash', amount=9000, cash=500)
        self.closed(s, ref='sim-interest', amount=9000)
        result = self.report(s)
        interest = result['sections']['closed_unpaid_interest']['totals']['interest_due_krw']['total_krw']
        self.assertGreater(interest, 0)
        self.assertLess(interest, 500)
        self.assertEqual(result['sections']['unapplied_cash']['totals']['unapplied_cash_krw']['total_krw'], 500)
        self.assertNotIn('total_krw', result)

    def test_default_before_writeoff_includes_components_after_recovery(self):
        _, s = self.default()
        s.overlay_command(recover(s, 1000))
        result = self.report(s)
        row = result['sections']['defaulted_unwritten']['rows'][0]
        amounts = row['amounts']
        # 10 days of contractual interest, then a recovery paying interest first.
        interest = 90000 * 10 * 700 // (365 * 10000)
        self.assertEqual(amounts, {'principal_krw': 90000 - (1000 - interest),
                                  'interest_krw': 0, 'default_interest_krw': 0,
                                  'claim_krw': 90000 + interest - 1000})
        self.assertEqual(result['sections']['post_writeoff_residual_claims']['rows'], [])
        self.assertTrue(result['sections']['defaulted_unwritten']['reconciliation']['matched'])

    def test_default_without_recovery_retains_positive_principal_and_interest(self):
        _, s = self.default()
        result = self.report(s)
        row = result['sections']['defaulted_unwritten']['rows'][0]
        self.assertGreater(row['amounts']['principal_krw'], 0)
        self.assertGreater(row['amounts']['interest_krw'], 0)
        self.assertEqual(row['amounts']['claim_krw'], sum(row['amounts'][k] for k in
                         ('principal_krw', 'interest_krw', 'default_interest_krw')))

    def test_late_recovery_is_subtracted_once_without_f04_exposure_addition(self):
        _, s = self.writeoff()
        result = self.report(s)
        row = result['sections']['post_writeoff_residual_claims']['rows'][0]
        writeoff = next(e['payload'] for e in s.overlay_entries if e['kind'] == 'WRITEOFF')
        self.assertEqual(row['amounts'], {'residual_claim_krw': writeoff['residual_claim_krw'] - 1000})
        self.assertEqual(s.machine.view('sim-a')['outstanding_exposure'], 90000)
        self.assertEqual(row['lifecycle_status'], 'DEFAULTED')
        self.assertEqual(result['sections']['defaulted_unwritten']['rows'], [])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertTrue(result['sections']['post_writeoff_residual_claims']['reconciliation']['matched'])

    def test_impaired_slice_uses_recorded_cut_and_keeps_shortfall_separate(self):
        _, s, face = self.impaired()
        result = self.report(s)
        row = result['sections']['impaired_slice_residuals']['rows'][0]
        self.assertEqual(row['amounts'], {'slice_face_krw': face, 'recourse_received_krw': 0,
                         'served_krw': 0, 'outstanding_krw': face, 'eligible_line_krw': 0, 'shortfall_krw': face})
        self.assertEqual(row['basis'], 'LAST_RECORDED_OBSERVATION')
        self.assertEqual(row['slice_id'], 'sim-slice')
        self.assertEqual(row['claim_id'], 'demo-delta-small')
        self.assertEqual(row['holder_role'], 'KIX_CAPITAL_LENDER')
        self.assertRegex(row['fold_values']['observation']['claim_view_sha'], r'^[0-9a-f]{64}$')
        self.assertEqual(result['status'], 'COMPLETE')

    def test_slice_partial_recourse_and_later_recorded_witness(self):
        source, s, face = self.impaired()
        slice_seed.distribute(source, 'demo-delta-mid')
        q = next(q for q in s.overlay_slices()['slices'][0]['quotes']
                 if q['source_ref']['claim_id'] == 'demo-delta-mid')
        slice_seed.post(s, 'post_slice_recourse', 'recourse', slice_id='sim-slice',
                        source_ref=q['source_ref'], quote_ref=q['quote_ref'], amount_krw=100)
        result = self.report(s)
        row = result['sections']['impaired_slice_residuals']['rows'][0]
        self.assertEqual(row['amounts']['outstanding_krw'], face - 100)
        self.assertEqual(row['amounts']['recourse_received_krw'], 100)
        self.assertTrue(result['sections']['impaired_slice_residuals']['reconciliation']['matched'])
        self.assertIn('recourse', [r['entry_id'] for r in row['references']])

    def test_legacy_closed_missing_accrual_is_not_zero(self):
        s = self.service()
        draw_book(s)
        run(s, 'repay', 'sim-a', 'principal', amount=90000, sequence=1)
        run(s, 'close', 'sim-a', 'close')
        s._persist()
        doc = copy.deepcopy(s.storage._document)
        del doc['overlay'], doc['envelope_version']
        self.capture(s, doc)
        result = residuals.report_workspace(self.directory)
        self.assertEqual(result['status'], 'INCOMPLETE')
        for category in ('closed_unpaid_interest', 'unapplied_cash'):
            row = result['sections'][category]['rows'][0]
            self.assertEqual(row['evidence_status'], 'NOT_BOUND')
            self.assertTrue(all(v is None for v in row['amounts'].values()))
            for total in result['sections'][category]['totals'].values():
                self.assertEqual(total, {'known_subtotal_krw': 0, 'total_krw': None, 'unknown_rows': 1})

    def test_missing_anchor_is_explicit_on_a_valid_audited_legacy_default(self):
        s = self.service()
        draw_book(s)
        run(s, 'default', 'sim-a', 'default')
        s.overlay_entries = []  # Valid legacy F04 history, without overlay evidence.
        result = self.report(s)
        row = result['sections']['defaulted_unwritten']['rows'][0]
        self.assertIn('DEFAULT_ANCHOR_NOT_BOUND', row['reasons'])
        self.assertEqual(row['amounts']['claim_krw'], None)
        self.assertEqual(result['status'], 'INCOMPLETE')

    def test_known_subtotal_is_retained_with_unknown_cash_row(self):
        s = self.closed(cash=500)
        draw_book(s, advance='sim-unknown', amount=9000, prefix='unknown')
        result = self.report(s)
        total = result['sections']['unapplied_cash']['totals']['unapplied_cash_krw']
        self.assertEqual(total, {'known_subtotal_krw': 500, 'total_krw': None, 'unknown_rows': 1})
        self.assertEqual(result['sections']['unapplied_cash']['coverage']['bound'], 1)

    def test_empty_recorded_population_is_complete_without_claiming_real_payments(self):
        result = self.report(self.service())
        self.assertEqual(result['status'], 'COMPLETE')
        for section in result['sections'].values():
            self.assertEqual(section['rows'], [])
            self.assertTrue(section['reconciliation']['matched'])
            self.assertTrue(all(t['total_krw'] == 0 for t in section['totals'].values()))
        self.assertEqual(result['actual_payments'], 'NOT_BOUND')
        self.assertEqual(result['authentication'], 'NOT_BOUND')
        self.assertEqual(result['legal_collectability'], 'NOT_BOUND')

    def test_identical_duplicate_overlay_entries_are_counted_once(self):
        _, s = self.writeoff()
        s.overlay_entries.append(copy.deepcopy(s.overlay_entries[-1]))
        result = self.report(s)
        row = result['sections']['post_writeoff_residual_claims']['rows'][0]
        self.assertEqual(sum(r['entry_id'] == 'late' for r in row['references']), 1)
        self.assertTrue(result['sections']['post_writeoff_residual_claims']['reconciliation']['matched'])

    def test_references_resolve_to_original_journals_and_schema_is_fixed(self):
        s = self.closed(cash=500)
        result = self.report(s)
        self.assertEqual(set(result), {'format', 'label', 'mode', 'status', 'reasons', 'source', 'sections',
                                      'interpretation', 'authentication', 'actual_payments',
                                      'legal_collectability', 'funds_executed', 'workspace_mutated'})
        self.assertEqual(set(result['source']), {'workspace_sha256', 'payload_sha256', 'state_digest',
                                               'overlay_state_digest', 'sim_day', 'audit'})
        self.assertEqual(result['source']['audit'], audit.audit_workspace(self.directory))
        self.assertEqual(result['source']['workspace_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        for category, section in result['sections'].items():
            self.assertEqual(set(section), {'rows', 'coverage', 'totals', 'reconciliation'})
            for row in section['rows']:
                self.assertEqual(set(row), {'advance_id', 'slice_id', 'claim_id', 'beneficiary_role',
                                 'payee_label', 'holder_role', 'lifecycle_status', 'evidence_status', 'reasons',
                                 'basis', 'amounts', 'fold_values', 'remainders', 'references'})
                self.assertEqual(set(row['amounts']), set(residuals.METRICS[category]))
                self.assertEqual(set(row['fold_values']), {'accrual', 'repayment', 'recovery', 'position',
                                                          'slice', 'derived', 'observation'})
                refs = row['references']
                self.assertEqual(refs, sorted(refs, key=lambda r: (r['journal'], r['index'])))
                for ref in refs:
                    self.assertEqual(set(ref), {'journal', 'index', 'entry_id', 'kind', 'after_journal_index', 'sim_day'})
                    e = (s.machine.export_journal() if ref['journal'] == 'F04' else s.overlay_entries)[ref['index']]
                    self.assertEqual(ref['entry_id'], e.get('overlay_id', e.get('idempotency_key')))
                    if ref['journal'] == 'F04': self.assertIsNone(ref['sim_day'])

    def test_repeat_reads_and_cli_preserve_bytes_modes_and_directory(self):
        s = self.closed(cash=500)
        original = self.capture(s)
        mode = self.path.stat().st_mode
        paths = sorted(self.directory.iterdir())
        first = residuals.report_workspace(self.directory)
        self.assertEqual(first, residuals.report_workspace(self.directory))
        command = [sys.executable, '-m', 'capital.residuals', '--workspace', str(self.directory)]
        runs = [subprocess.run(command, capture_output=True, cwd=ROOT) for _ in range(2)]
        self.assertEqual([r.returncode for r in runs], [0, 0])
        self.assertEqual(runs[0].stdout, store.canonical_bytes(first) + b'\n')
        self.assertEqual(runs[0].stdout, runs[1].stdout)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_mode, mode)
        self.assertEqual(sorted(self.directory.iterdir()), paths)

    def test_capture_is_not_reread_after_audit_even_if_path_is_replaced(self):
        self.capture(self.closed())
        original = residuals.report_workspace(self.directory)
        real_audit = audit.audit_workspace_bytes
        def replace(raw, **kw):
            self.path.write_bytes(b'changed after capture')
            return real_audit(raw, **kw)
        with patch.object(audit, 'audit_workspace_bytes', side_effect=replace):
            self.assertEqual(residuals.report_workspace(self.directory), original)

    def test_no_workspace_lock_save_signer_or_network_and_restoration_is_closed(self):
        self.capture(self.closed())
        real = evidence.offline_service
        restored = []
        def track(doc):
            s = real(doc)
            s.observability.close = unittest.mock.Mock(wraps=s.observability.close)
            restored.append(s)
            return s
        with patch.object(store.FileWorkspace, 'open', side_effect=AssertionError('lock')), \
             patch.object(evidence._DocumentStorage, 'save', side_effect=AssertionError('save')), \
             patch.object(socket.socket, 'connect', side_effect=AssertionError('network')), \
             patch.object(evidence, 'offline_service', side_effect=track):
            result = residuals.report_workspace(self.directory)
        self.assertEqual(result['status'], 'COMPLETE')
        restored[0].observability.close.assert_called_once_with()

    def test_corrupt_missing_and_inactive_restore_fail_closed(self):
        result = residuals.report_workspace(self.directory)
        self.assertEqual(result['status'], 'AUDIT_FAILED')
        self.assertIsNone(result['sections'])
        self.path.write_bytes(b'{"x":1,"x":2}')
        self.assertEqual(residuals.report_workspace(self.directory)['status'], 'AUDIT_FAILED')
        self.capture(self.closed())
        s = evidence.offline_service(json.loads(self.path.read_bytes()))
        s.workspace_status = 'WORKSPACE_UNREADABLE'
        with patch.object(evidence, 'offline_service', return_value=s), \
             patch.object(s.observability, 'close', wraps=s.observability.close) as close:
            result = residuals.report_workspace(self.directory)
            self.assertEqual(result['reasons'], ['RESTORE_NOT_ACTIVE'])
            self.assertIsNone(result['sections'])
            close.assert_called_once_with()

    def test_injected_reader_reconciliation_failure_is_incomplete(self):
        self.capture(self.closed(cash=500))
        real = overlay.advance_gate
        def wrong(state, ref):
            return {**real(state, ref), 'interest_due_krw': 1}
        # Composition only: do not bypass or alter the workspace audit.
        real_compose = residuals._compose
        def compose(*args):
            with patch.object(overlay, 'advance_gate', side_effect=wrong):
                return real_compose(*args)
        with patch.object(residuals, '_compose', side_effect=compose):
            result = residuals.report_workspace(self.directory)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertIn('RECONCILIATION_FAILED', result['reasons'])
        self.assertFalse(result['sections']['closed_unpaid_interest']['reconciliation']['matched'])

    def test_missing_slice_evidence_never_calls_derived_or_uses_older_cut(self):
        _, s, _ = self.impaired()
        self.capture(s)  # All source fixtures must pass the real audit first.
        state = overlay.fold(s.overlay_entries)
        for missing in ('claim', 'payee', 'baseline'):
            with self.subTest(missing=missing):
                entries = copy.deepcopy(s.overlay_entries)
                detached = copy.deepcopy(state)
                if missing == 'claim':
                    for e in entries:
                        if e['kind'] in ('SLICE_PROPOSE', 'SLICE_OPEN', 'SLICE_IMPAIR'):
                            e['payload']['witness']['observations'].pop('demo-delta-small', None)
                elif missing == 'payee':
                    entries[-1]['payload']['witness']['observations']['demo-delta-small']['lines'].pop('organizer')
                else:
                    detached['claim_slices']['slices']['sim-slice'].pop('baseline_distributed_krw')
                # Exercise conservative composition on detached reader inputs, not an invalid workspace.
                with patch.object(residuals.slices, 'derived', side_effect=AssertionError('missing line')):
                    section = residuals._compose(s, detached, s.machine.export_journal(), entries)['impaired_slice_residuals']
                row = section['rows'][0]
                self.assertEqual(row['evidence_status'], 'NOT_BOUND')
                self.assertIsNone(row['amounts']['outstanding_krw'])
                self.assertEqual(section['totals']['outstanding_krw']['unknown_rows'], 1)
                self.assertIsNone(section['reconciliation']['matched'])

    def test_invalid_resealed_slice_witness_is_rejected_by_actual_audit(self):
        _, s, _ = self.impaired()
        self.capture(s)
        doc = json.loads(self.path.read_bytes())
        doc['overlay']['journal'][-1]['payload']['witness']['observations']['demo-delta-small']['lines'].pop('organizer')
        doc['overlay']['section_sha256'] = store.section_checksum(doc['overlay'])
        self.path.write_bytes(store.canonical_bytes(doc))
        result = residuals.report_workspace(self.directory)
        self.assertEqual(result['status'], 'AUDIT_FAILED')
        self.assertIsNone(result['sections'])

    def test_mixed_case_claims_and_cash_have_independent_totals(self):
        s = self.closed(amount=9000, cash=500)
        for ref in ('sim-default', 'sim-written'):
            draw_book(s, advance=ref, amount=9000, prefix=ref)
        tick(s, 'second-tick', 5, 10)
        for ref in ('sim-default', 'sim-written'):
            self.assertEqual(run(s, 'default', ref, ref + '-default')['outcome'], 'ACCEPTED')
        eligible = recovery.anchor(overlay.fold(s.overlay_entries), 'sim-written')['writeoff_eligible_sim_day']
        tick(s, 'writeoff-tick', 10, eligible + 1)
        s.overlay_command(cmd(s, 'post_writeoff', 'writeoff', ref='sim-written',
                             setoff_declined_reason='SIMULATED_FIXTURE_DECLINE'))
        result = self.report(s)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual([r['advance_id'] for r in result['sections']['defaulted_unwritten']['rows']], ['sim-default'])
        self.assertEqual([r['advance_id'] for r in result['sections']['post_writeoff_residual_claims']['rows']], ['sim-written'])
        self.assertEqual(result['sections']['unapplied_cash']['totals']['unapplied_cash_krw']['total_krw'], 500)
        self.assertEqual(result['sections']['post_writeoff_residual_claims']['totals']['residual_claim_krw']['total_krw'],
                         recovery.recovered(overlay.fold(s.overlay_entries), 'sim-written')['residual_claim_krw'])
        self.assertTrue(all(section['reconciliation']['matched'] for section in result['sections'].values()))

    def test_repayment_alone_binds_recorded_cash_but_not_interest_coverage(self):
        s = self.service()
        # Bind terms on an empty overlay: the clock creates no accrual posting
        # because no advance is a subject yet, so only the repayment supplies
        # per-advance cash evidence below.
        self.assertEqual(tick(s, 'bind', 0, 1)['outcome'], 'APPLIED')
        draw_book(s)
        pay(s, 'day-zero-cash', 90500)
        run(s, 'close', 'sim-a', 'close')
        result = self.report(s)
        self.assertEqual(result['sections']['unapplied_cash']['rows'][0]['amounts']['unapplied_cash_krw'], 500)
        self.assertEqual(result['sections']['unapplied_cash']['rows'][0]['evidence_status'], 'BOUND')
        self.assertEqual(result['sections']['closed_unpaid_interest']['rows'][0]['evidence_status'], 'NOT_BOUND')
        self.assertEqual(result['status'], 'INCOMPLETE')

    def test_closed_default_interest_has_separate_metric(self):
        s = self.service()
        draw_book(s)
        tick(s, 'overdue', 0, 75)
        run(s, 'repay', 'sim-a', 'principal', amount=90000, sequence=1)
        run(s, 'close', 'sim-a', 'close')
        result = self.report(s)
        row = result['sections']['closed_unpaid_interest']['rows'][0]
        # The adopted 60-day contractual term is followed by 15 default days.
        self.assertEqual(row['amounts'], {'interest_due_krw': 90000 * 60 * 700 // 3650000,
                                         'default_interest_due_krw': 90000 * 15 * 1000 // 3650000})

    def test_recovery_and_slice_reads_are_repeatable_and_detached(self):
        for build in (self.writeoff, self.impaired):
            with self.subTest(fixture=build.__name__):
                built = build()
                s = built[1]
                original = self.capture(s)
                first = residuals.report_workspace(self.directory)
                second = residuals.report_workspace(self.directory)
                self.assertEqual(store.canonical_bytes(first), store.canonical_bytes(second))
                row = next(row for section in first['sections'].values() for row in section['rows'])
                row['fold_values'].clear()
                self.assertEqual(residuals.report_workspace(self.directory), second)
                self.assertEqual(self.path.read_bytes(), original)

    def test_cli_failure_and_argument_exit_codes(self):
        command = [sys.executable, '-m', 'capital.residuals']
        for args, expected in (([], 2), (['--workspace', str(self.directory)], 1)):
            result = subprocess.run(command + args, capture_output=True, cwd=ROOT)
            self.assertEqual(result.returncode, expected)
        self.capture(self.closed())
        doc = json.loads(self.path.read_bytes())
        doc['overlay'] = overlay.empty_section()
        self.path.write_bytes(store.canonical_bytes(doc))
        self.assertTrue(audit.audit_workspace(self.directory)['ok'])
        result = subprocess.run(command + ['--workspace', str(self.directory)], capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
