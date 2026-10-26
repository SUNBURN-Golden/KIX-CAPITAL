"""Independent SIMULATED recovery amounts, replay, authority and failure fences."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from capital import margin, overlay, recovery
from capital.audit import audit_workspace
from capital.producer import PinnedFsmProducer
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, InMemoryStorage, WorkspaceError, canonical_bytes, section_checksum
from capital.terms import DecisionNoteTermsPolicy, read_decision_block
from capital.verify import verify_manifest
from test_overlay import draw_book, formula, run, tick, terms_value, tier

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seed_overlay_recovery', ROOT / 'scripts/seed_overlay_recovery.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
DELAY = terms_value('default_loss_treatment')['writeoff_days_after_default']
THRESHOLD = terms_value('underwriting_depth')['two_person_threshold_krw']


def book(amount=90000, fixture='sim-committed', storage=None, source=None):
    source = source or margin.ScenarioReplaySource()
    s = CapitalService(storage, producer=PinnedFsmProducer(fixtures=source))
    draw_book(s, amount=amount, fixture=fixture)
    tick(s, 'day10', 0, 10)
    return source, s


def cmd(s, op, key, *, day=None, ref='sim-a', **kw):
    return {'instance_id': s.instance_id, 'operation_id': key, 'op': op, 'advance_ref': ref,
            'at_sim_day': overlay.fold(s.overlay_entries)['sim_day'] if day is None else day, **kw}


def quote(s, ref='sim-a', claim='sim-committed'):
    return next(q for r in s.overlay_state()['recovery']['advances'] if r['advance_id'] == ref
                for q in r['quotes'] if q['source_ref']['claim_id'] == claim)


def recover(s, amount, key='recover', ref='sim-a', claim='sim-committed', **kw):
    q = quote(s, ref, claim)
    return cmd(s, 'post_recovery', key, ref=ref, amount_krw=amount, source_ref=q['source_ref'], quote_ref=q['quote_ref'], **kw)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.source, self.s = book()
        run(self.s, 'default', 'sim-a', 'default')
        seed.distribute(self.source, 'sim-committed')

    def assert_code(self, code, callback):
        with self.assertRaises(ApiError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_recovery_allocation_reduces_loss_without_touching_terminal_f04(self):
        tick(self.s, 'day20', 10, 20)
        before = self.s.machine.state_digest(), self.s.machine.export_journal()
        result = self.s.overlay_command(recover(self.s, 10000))
        interest = formula(90000 * 10, 700)
        default = formula(90000 * 10, 1000)
        self.assertEqual(result['entry']['allocation'], {'default_interest_krw': default,
                         'interest_krw': interest, 'principal_krw': 10000 - interest - default})
        row = self.s.overlay_state()['recovery']['advances'][0]
        self.assertEqual(row['outstanding_loss_krw'], 80000 + interest + default)
        self.assertEqual(before, (self.s.machine.state_digest(), self.s.machine.export_journal()))
        self.assertEqual(run(self.s, 'repay', 'sim-a', 'terminal', amount=1, sequence=1)['error'], 'TERMINAL_IMMUTABLE')
        self.assertEqual(self.s.machine.view('sim-a')['phase'], 'DEFAULTED')

    def test_duplicate_returns_recorded_receipt_after_clock_moves_and_conflicts_do_not_write(self):
        body = recover(self.s, 1000)
        first = self.s.overlay_command(body)
        tick(self.s, 'later', 10, 11)
        n = len(self.s.overlay_entries)
        again = self.s.overlay_command(body)
        self.assertEqual(first['entry'], again['entry'])
        self.assertTrue(again['transport_duplicate'])
        self.assertEqual(n, len(self.s.overlay_entries))
        self.assert_code('IDEMPOTENCY_CONFLICT', lambda: self.s.overlay_command({**body, 'amount_krw': 1001}))
        self.assert_code('IDEMPOTENCY_CONFLICT', lambda: self.s.overlay_command({**body, 'approvals': [{'approver_label': 'sim-a'}]}))
        self.assertEqual(self.s.overlay_state('absent')['operation']['outcome'], 'UNKNOWN')
        self.assertFalse(self.s.overlay_state('absent')['operation']['retry_authorized'])

    def test_claim_and_source_caps_and_stale_quote(self):
        p = recovery.position(overlay.fold(self.s.overlay_entries), 'sim-a')
        self.assert_code('RECOVERY_EXCEEDS_CLAIM', lambda: self.s.overlay_command(recover(self.s, p['claim_krw'] + 1)))
        old = recover(self.s, 1)
        tick(self.s, 'later', 10, 11)
        self.assert_code('RECOVERY_QUOTE_STALE', lambda: self.s.overlay_command({**old, 'at_sim_day': 11}))
        # Two advances share one observed source, not one source each.
        source, s = book(amount=45000)
        draw_book(s, advance='sim-b', amount=45000, prefix='b')
        run(s, 'default', 'sim-a', 'def-a'); run(s, 'default', 'sim-b', 'def-b')
        seed.distribute(source, 'sim-committed')
        s.overlay_command(recover(s, 40000, 'a-first'))
        q = quote(s, 'sim-b')
        self.assertEqual(q['available_krw'], 92000 - 40000)
        s.overlay_command(recover(s, 40000, 'b-first', ref='sim-b'))
        self.assertEqual(quote(s)['available_krw'], 12000)

    def test_source_cap_after_default_interest_outgrows_cash(self):
        tick(self.s, 'late', 10, 100)
        self.s.overlay_command(recover(self.s, 91000))
        self.assert_code('RECOVERY_SOURCE_EXCEEDED', lambda: self.s.overlay_command(recover(self.s, 1001, 'exceeded')))

    def test_available_source_requires_decline_before_writeoff(self):
        tick(self.s, 'stop', 10, 100)
        self.assert_code('WRITEOFF_SETOFF_AVAILABLE', lambda: self.s.overlay_command(cmd(self.s, 'post_writeoff', 'wo')))
        result = self.s.overlay_command(cmd(self.s, 'post_writeoff', 'wo', setoff_declined_reason='SIMULATED_DECLINED'))['entry']
        self.assertEqual(result['writeoff_principal_krw'], 90000)
        self.assertEqual(result['accrued_interest_reversed_krw'], formula(90000 * 10, 700))
        self.assertEqual(result['suspended_interest_released_krw'], formula(90000 * 90, 1000))
        self.assertEqual(result['waterfall_trace'][2], {'step': 'LOSS_RESERVE', 'status': 'NOT_BOUND', 'absorbed_krw': 0})
        self.assertEqual(result['loss_krw'], 90000)
        self.assertEqual(result['reserve_step_version'], 'UNBUILT_V1')
        self.assertEqual(result['loss_bearer'], terms_value('default_loss_treatment')['loss_bearer_v1'])

    def test_interest_stops_at_actual_default_day_plus_delay_even_without_writeoff(self):
        tick(self.s, 'before-stop', 10, 99)
        self.assert_code('WRITEOFF_NOT_ELIGIBLE', lambda: self.s.overlay_command(cmd(self.s, 'post_writeoff', 'early')))
        tick(self.s, 'stop', 99, 100)
        exact = self.s.overlay_state()['advances'][0]['cumulative_exact_default']
        tick(self.s, 'after', 100, 130)
        row = self.s.overlay_state()['advances'][0]
        self.assertEqual(row['cumulative_exact_default'], exact)
        self.assertEqual(row['accrued_through_sim_day'], 100)
        self.assertEqual(self.s.overlay_state()['recovery']['entries'], [])
        p = self.s.overlay_command(cmd(self.s, 'post_writeoff', 'late-wo', setoff_declined_reason='SIMULATED_DECLINED'))['entry']
        self.assertEqual(p['writeoff_effective_sim_day'], 100)
        self.assertEqual(p['sim_day'], 130)

    def test_late_recovery_only_changes_residual_no_interest_or_revival(self):
        tick(self.s, 'stop', 10, 100)
        self.s.overlay_command(cmd(self.s, 'post_writeoff', 'wo', setoff_declined_reason='SIMULATED_DECLINED'))
        before = self.s.overlay_state()['recovery']['advances'][0]['residual_claim_krw']
        p = self.s.overlay_command(recover(self.s, 1000))['entry']
        self.assertEqual(p['phase'], 'POST_WRITEOFF')
        self.assertNotIn('allocation', p)
        self.assertEqual(p['residual_claim_krw'], before - 1000)
        tick(self.s, 'more', 100, 300)
        r = self.s.overlay_state()['advances'][0]
        self.assertEqual((r['principal_outstanding_krw'], r['interest_due_krw'], r['default_interest_due_krw']), (0, 0, 0))
        self.assertEqual(self.s.machine.view('sim-a')['note_status'], 'NOTED')
        self.assert_code('WRITEOFF_NOT_ELIGIBLE', lambda: self.s.overlay_command(cmd(self.s, 'post_writeoff', 'again')))

    def test_tick_directive_is_atomic_and_canonical_idempotent(self):
        body = {'instance_id': self.s.instance_id, 'operation_id': 'tickwo', 'op': 'advance_day',
                'from_sim_day': 10, 'to_sim_day': 100, 'reason': 'SIMULATED', 'writeoff': {
                    'operation_id': 'wo', 'advance_ref': 'sim-a', 'at_sim_day': 100}}
        before = copy.deepcopy(self.s.overlay_entries)
        self.assert_code('WRITEOFF_SETOFF_AVAILABLE', lambda: self.s.overlay_command(body))
        self.assertEqual(before, self.s.overlay_entries)
        body['writeoff']['setoff_declined_reason'] = 'SIMULATED_DECLINED'
        self.s.overlay_command(body)
        self.assertTrue(self.s.overlay_command(body)['transport_duplicate'])
        self.assert_code('IDEMPOTENCY_CONFLICT', lambda: self.s.overlay_command({k: v for k, v in body.items() if k != 'writeoff'}))
        self.assertEqual(self.s.overlay_state('wo')['operation']['op'], 'post_writeoff')

    def test_other_claim_sources_require_same_beneficiary(self):
        source, s = book()
        run(s, 'default', 'sim-a', 'default')
        seed.distribute(source, 'sim-pending')
        seed.distribute(source, 'demo-alpha-arena')
        quotes = s.overlay_state()['recovery']['advances'][0]['quotes']
        self.assertNotIn('demo-alpha-arena', {q['source_ref']['claim_id'] for q in quotes})
        p = s.overlay_command(recover(s, 1000, claim='sim-pending'))['entry']
        self.assertEqual(p['waterfall_step'], 'SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY')

    def test_secondary_recovery_waits_for_primary_exhaustion_before_and_after_writeoff(self):
        for after_writeoff in (False, True):
            with self.subTest(after_writeoff=after_writeoff):
                source, s = book(amount=95000)
                run(s, 'default', 'sim-a', 'default')
                seed.distribute(source, 'sim-committed')
                seed.distribute(source, 'sim-pending')
                if after_writeoff:
                    tick(s, 'stop', 10, 100)
                    s.overlay_command(cmd(s, 'post_writeoff', 'wo', setoff_declined_reason='SIMULATED_DECLINED'))
                primary = quote(s)
                secondary = recover(s, 1000, 'secondary', claim='sim-pending')
                before = s._frozen()
                self.assert_code('RECOVERY_WATERFALL_ORDER', lambda: s.overlay_command(secondary))
                self.assertEqual(before, s._frozen())
                s.overlay_command(recover(s, 1000, 'partial-primary'))
                self.assert_code('RECOVERY_WATERFALL_ORDER', lambda: s.overlay_command(
                    recover(s, 1000, 'secondary', claim='sim-pending')))
                s.overlay_command(recover(s, primary['available_krw'] - 1000, 'exhaust-primary'))
                self.assert_code('RECOVERY_QUOTE_STALE', lambda: s.overlay_command(secondary))
                result = s.overlay_command(recover(s, 1000, 'secondary', claim='sim-pending'))['entry']
                self.assertEqual(result['waterfall_step'], 'SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY')
                self.assertEqual(result['phase'], 'POST_WRITEOFF' if after_writeoff else 'POST_DEFAULT')
                self.assertTrue(verify_manifest(s.export_manifest())['ok'])
                # Replaying a secondary entry with an observed primary balance is invalid.
                forged = copy.deepcopy(s.overlay_entries)
                forged[-1]['payload']['source_quotes'].append({
                    'source_ref': primary['source_ref'], 'quote_ref': primary['quote_ref'],
                    'available_krw': 1, 'waterfall_step': primary['waterfall_step']})
                with self.assertRaises(overlay.OverlayError):
                    overlay.fold(forged)

    def test_capacity_and_failed_save_do_not_append(self):
        before = copy.deepcopy(self.s.overlay_entries)
        self.s.overlay_bounds['OVERLAY_MAX_ENTRIES'] = len(before)
        self.assert_code('SIMULATION_CAPACITY', lambda: self.s.overlay_command(recover(self.s, 100)))
        self.assertEqual(before, self.s.overlay_entries)
        self.s.overlay_bounds['OVERLAY_MAX_ENTRIES'] += 10
        with patch.object(self.s.storage, 'save', side_effect=WorkspaceError('WORKSPACE_WRITE_FAILED')):
            self.assert_code('WORKSPACE_WRITE_FAILED', lambda: self.s.overlay_command(recover(self.s, 100)))
        self.assertEqual(before, self.s.overlay_entries)
        self.assertEqual(self.s.overlay_state('recover')['operation']['outcome'], 'UNKNOWN')

    def test_semantic_resealed_allocation_tampering_is_rejected(self):
        self.s.overlay_command(recover(self.s, 1000))
        entries = copy.deepcopy(self.s.overlay_entries)
        entries[-1]['payload']['allocation']['principal_krw'] += 1
        with self.assertRaises(overlay.OverlayError): overlay.fold(entries)
        manifest = self.s.export_manifest()
        from capital.export import build_manifest
        bodies = {k: {field: copy.deepcopy(value) for field, value in v['body'].items() if field != 'part_tag'} for k, v in manifest['sections'].items()}
        bodies['overlay']['journal'] = entries
        forged = build_manifest(sections=bodies, instance_id='SIMULATED', signer=self.s.signer, status='COMPLETE', incomplete_reasons=[])
        self.assertEqual(verify_manifest(forged)['reason'], 'OVERLAY_FOLD_MISMATCH')

    def test_full_recovery_claim_cap_and_post_repayment_cannot_bypass_ledger(self):
        pos = recovery.position(overlay.fold(self.s.overlay_entries), 'sim-a')
        self.assert_code('REPAYMENT_ADVANCE_STATE', lambda: self.s.overlay_command(cmd(self.s, 'post_repayment', 'wrong-route', amount_krw=1)))
        self.s.overlay_command(recover(self.s, pos['claim_krw']))
        row = self.s.overlay_state()['recovery']['advances'][0]
        self.assertEqual((row['claim_krw'], row['outstanding_loss_krw']), (0, 0))
        self.assert_code('RECOVERY_EXCEEDS_CLAIM', lambda: self.s.overlay_command(recover(self.s, 1, 'overflow')))
        tick(self.s, 'later', 10, 100)
        self.assert_code('WRITEOFF_NOT_ELIGIBLE', lambda: self.s.overlay_command(cmd(self.s, 'post_writeoff', 'wo')))

    def test_anchored_default_repayment_stays_blocked_without_available_sources(self):
        source, s = book()
        run(s, 'default', 'sim-a', 'default')
        self.assertEqual(s.overlay_state()['recovery']['advances'][0]['quotes'], [])
        before = s._frozen()
        self.assert_code('REPAYMENT_ADVANCE_STATE', lambda: s.overlay_command(
            cmd(s, 'post_repayment', 'before-source', amount_krw=1)))
        self.assertEqual(before, s._frozen())
        seed.distribute(source, 'sim-committed')
        tick(s, 'stop', 10, 100)
        s.overlay_command(recover(s, quote(s)['available_krw'], 'exhaust'))
        self.assertEqual(s.overlay_state()['recovery']['advances'][0]['quotes'], [])
        self.assertGreater(s.overlay_state()['recovery']['advances'][0]['claim_krw'], 0)
        for after_writeoff in (False, True):
            with self.subTest(after_writeoff=after_writeoff):
                if after_writeoff:
                    s.overlay_command(cmd(s, 'post_writeoff', 'wo'))
                before = s._frozen()
                exc = self.assert_code('REPAYMENT_ADVANCE_STATE', lambda: s.overlay_command(
                    cmd(s, 'post_repayment', 'double-interest', amount_krw=1)))
                self.assertEqual(exc.detail['reason'], 'RECOVERY_LEDGER_ONLY')
                self.assertEqual(before, s._frozen())
                row = s.overlay_state()['advances'][0]
                self.assertEqual((row['interest_due_krw'], row['default_interest_due_krw']), (0, 0))
                self.assertEqual(s.machine.view('sim-a')['phase'], 'DEFAULTED')

    def test_fold_refuses_legacy_interest_payment_after_default_anchor(self):
        state = overlay.fold(self.s.overlay_entries)
        entry = overlay.repayment_entry('bypass', state, journal_index=len(self.s.machine.export_journal()),
            advance_ref='sim-a', amount=1, denominator=self.s.terms.ledger_denominator(),
            principal_before=90000, terms_version=state['terms_binding']['terms_version'],
            split={'to_default_interest': 0, 'to_interest': 1, 'to_principal': 0, 'unapplied_cash': 0})
        # The same payment remains replayable on the historical, unanchored path.
        overlay.fold([e for e in self.s.overlay_entries if e['kind'] != 'default_anchor'] + [entry])
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(self.s.overlay_entries + [entry])

    def test_default_anchor_link_is_checked_even_when_the_fold_is_resealed(self):
        entries = copy.deepcopy(self.s.overlay_entries)
        anchor = next(e for e in entries if e['kind'] == 'default_anchor')
        anchor['payload']['principal_krw'] += 1
        overlay.fold(entries)
        with self.assertRaises(overlay.OverlayError):
            recovery.validate_links(entries, self.s.machine.export_journal())
        section = overlay.build_section(entries)
        from capital.recon import build_reconciliation
        # The unchanged reconciliation check id reports the broken F04 link.
        with patch.object(self.s, '_subject_payload', return_value=({
                'receipts': self.s.receipts, 'journal': self.s.machine.export_journal(),
                'case_fixtures': self.s.case_fixtures, 'state_digest': self.s.machine.state_digest()}, None, section)):
            original = self.s.overlay_entries
            try:
                self.s.overlay_entries = entries
                check = next(x for x in self.s.reconciliation()['checks'] if x['id'] == 'overlay_fold_digest_equals_persisted')
                self.assertEqual(check['status'], 'RECON_MISMATCH')
                self.assertEqual(check['detail'], 'recovery_default_link')
            finally:
                self.s.overlay_entries = original

    def test_agent_refusal_precedes_receipt_and_malformed_inputs(self):
        body = recover(self.s, 100)
        self.s.overlay_command(body)
        before = self.s._frozen()
        exc = self.assert_code('RECOVERY_AGENT_FORBIDDEN', lambda: self.s.overlay_command(body, role='agent'))
        self.assertEqual(exc.status, 403)
        self.assert_code('RECOVERY_AGENT_FORBIDDEN', lambda: self.s.execute({'instance_id': '', 'operation_id': 'default', 'op': 'default', 'advance_id': 'sim-a', 'args': {}}, role='agent'))
        self.assertEqual(before, self.s._frozen())
        self.assert_code('OVERLAY_VOLATILE_KEY', lambda: self.s.overlay_command({**body, 'timestamp': 'bad'}))
        for value in (True, 0, -1, '100'):
            self.assert_code('INVALID_ARGUMENTS', lambda value=value: self.s.overlay_command({**body, 'amount_krw': value}))


class AuthorityAndRebaseTests(unittest.TestCase):
    def assert_code(self, code, callback):
        with self.assertRaises(ApiError) as caught: callback()
        self.assertEqual(caught.exception.code, code)

    def test_default_threshold_uses_fsm_principal_including_empty_overlay(self):
        for amount in (THRESHOLD, THRESHOLD + 1):
            s = CapitalService(); draw_book(s, fixture='demo-alpha-arena', amount=amount)
            body = {'instance_id': s.instance_id, 'operation_id': 'def', 'op': 'default', 'advance_id': 'sim-a', 'args': {}}
            if amount > THRESHOLD:
                self.assert_code('TWO_PERSON_REQUIRED', lambda: s.execute(body))
                self.assert_code('TWO_PERSON_REQUIRED', lambda: s.execute({**body, 'approvals': [{'approver_label': 'sim-1'}] * 2}))
                self.assertEqual(s.machine.view('sim-a')['phase'], 'DRAWN')
                body['approvals'] = [{'approver_label': 'sim-2'}, {'approver_label': 'sim-1'}]
            first = s.execute(body)
            self.assertEqual(first['outcome'], 'ACCEPTED')
            self.assertEqual(s.overlay_entries, [])
            self.assertTrue(s.execute(body)['transport_duplicate'])
            if amount > THRESHOLD:
                self.assertEqual(first['approvals'], [{'approver_label': 'sim-1'}, {'approver_label': 'sim-2'}])
                self.assertTrue(s.execute({**body, 'approvals': list(reversed(body['approvals']))})['transport_duplicate'])
                self.assert_code('IDEMPOTENCY_CONFLICT', lambda: s.execute({**body, 'approvals': []}))

    def test_cumulative_recovery_and_writeoff_thresholds(self):
        source, s = book(amount=150000000, fixture='demo-alpha-arena')
        labels = [{'approver_label': 'sim-1'}, {'approver_label': 'sim-2'}]
        s.execute({'instance_id': s.instance_id, 'operation_id': 'def', 'op': 'default', 'advance_id': 'sim-a', 'args': {}, 'approvals': labels})
        seed.distribute(source, 'demo-alpha-arena')
        s.overlay_command(recover(s, THRESHOLD, 'first', claim='demo-alpha-arena'))
        self.assert_code('TWO_PERSON_REQUIRED', lambda: s.overlay_command(recover(s, 1, 'split', claim='demo-alpha-arena')))
        s.overlay_command(recover(s, 1, 'split', claim='demo-alpha-arena', approvals=labels))
        tick(s, 'stop', 10, 100)
        body = cmd(s, 'post_writeoff', 'wo', setoff_declined_reason='SIMULATED_DECLINED')
        self.assert_code('TWO_PERSON_REQUIRED', lambda: s.overlay_command(body))
        s.overlay_command({**body, 'approvals': labels})

    def test_default_save_failure_and_capacity_roll_back_f04_and_receipt(self):
        for capacity in (False, True):
            _, s = book()
            before = s._frozen()
            if capacity:
                s.overlay_bounds['OVERLAY_MAX_ENTRIES'] = len(s.overlay_entries)
                self.assert_code('SIMULATION_CAPACITY', lambda: run(s, 'default', 'sim-a', 'def'))
            else:
                with patch.object(s.storage, 'save', side_effect=WorkspaceError('WORKSPACE_WRITE_FAILED')):
                    self.assert_code('WORKSPACE_WRITE_FAILED', lambda: run(s, 'default', 'sim-a', 'def'))
            self.assertEqual(before, s._frozen())

    def test_approved_default_receipt_fingerprint_survives_workspace_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            _, s = book(amount=THRESHOLD + 1, fixture='demo-alpha-arena', storage=FileWorkspace.open(directory))
            self.addCleanup(s.storage.close)
            body = {'instance_id': s.instance_id, 'operation_id': 'def', 'op': 'default',
                    'advance_id': 'sim-a', 'args': {},
                    'approvals': [{'approver_label': 'sim-z'}, {'approver_label': 'sim-a'}]}
            s.execute(body)
            self.assertTrue(audit_workspace(directory)['ok'])
            s.recovery_policy = None
            self.assertTrue(s.execute(body)['transport_duplicate'])

    def test_predefault_and_historical_unanchored_default_fail_closed(self):
        _, s = book()
        self.assert_code('RECOVERY_NOT_DEFAULTED', lambda: s.overlay_command(cmd(s, 'post_writeoff', 'wo')))
        old = CapitalService();draw_book(old);run(old, 'default', 'sim-a', 'def');tick(old, 'clock', 0, 100)
        self.assert_code('DEFAULT_DAY_UNKNOWN', lambda: old.overlay_command(cmd(old, 'post_writeoff', 'wo')))
        self.assertNotIn('recovery', overlay.fold(old.overlay_entries))

    def test_acceleration_split_and_jump_use_same_daily_amounts(self):
        def prepare():
            source, s = book(amount=48000)
            source.replay('sim-committed', 'partial-before')
            tick(s, 'call', 10, 20)
            return s
        a, b = prepare(), prepare()
        tick(a, 'jump', 20, 40)
        for start in range(20, 40):tick(b, 'split-' + str(start), start, start + 1)
        x, y = a.overlay_state()['advances'][0], b.overlay_state()['advances'][0]
        for key in ('cumulative_exact_contract', 'cumulative_exact_default', 'interest_due_krw', 'default_interest_due_krw', 'maturity_day'):
            self.assertEqual(x[key], y[key], key)
        self.assertEqual(x['maturity_day'], 25)
        self.assertEqual(x['interest_due_krw'], formula(48000 * 25, 700))
        self.assertEqual(x['default_interest_due_krw'], formula(48000 * 15, 1000))
        self.assertEqual(x['interest_rebase']['default_interest_from_sim_day'], 26)

    def test_non_margin_acceleration_is_monotone_and_human_only(self):
        _, s = book()
        body = cmd(s, 'record_acceleration', 'event', event='BENEFICIARY_INSOLVENCY_NOTICE')
        self.assert_code('RECOVERY_AGENT_FORBIDDEN', lambda: s.overlay_command(body, role='agent'))
        result = s.overlay_command(body)
        self.assertEqual(result['entry']['maturity_after'], 10)
        tick(s, 'later', 10, 20)
        s.overlay_command(cmd(s, 'record_acceleration', 'event2', event='EVIDENCE_FRAUD_FINDING'))
        row = s.overlay_state()['advances'][0]
        self.assertEqual(row['maturity_day'], 10)
        self.assertEqual(row['interest_rebase']['status'], 'REBASED')
        self.assertEqual(row['default_interest_due_krw'], formula(90000 * 10, 1000))

    def test_missing_policy_entries_and_missing_terms_are_not_bound(self):
        terms = DecisionNoteTermsPolicy()
        note = read_decision_block(ROOT / 'docs/decisions' / recovery.NOTE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'note.md'
            for name in recovery.ITEMS:
                changed = copy.deepcopy(note);changed['entries'][name]['status'] = 'UNDETERMINED'
                path.write_text('```capital-decision-v1\n' + json.dumps(changed) + '\n```')
                self.assertIsNone(recovery.load_policy(terms, path))
            self.assertIsNone(recovery.load_policy(DecisionNoteTermsPolicy(Path(directory) / 'missing')))


class ReplayJourneyTests(unittest.TestCase):
    def test_disposable_golden_and_independent_first_allocation(self):
        service, result = seed.build()
        self.assertEqual(result, json.loads((ROOT / 'tests/golden/overlay_recovery.json').read_text()))
        contract, default = formula(48000 * 8, 700), formula(48000 * 11, 1000)
        self.assertEqual(result['first_allocation'], {'interest_krw': contract, 'default_interest_krw': default,
                                                    'principal_krw': 5000 - contract - default})
        principal = 48000 - (5000 - contract - default)
        suspended = (48000 * 11 * 1000 + principal * 90 * 1000) // 3650000 - default
        self.assertEqual(result['late_residual_claim_krw'], principal + suspended - 1000)
        self.assertEqual(result['overlay_fold_check'], 'MATCHED')
        self.assertFalse(result['funds_executed'])

    def test_historical_t05_replays_original_overlay_and_f04_digests(self):
        history = json.loads((ROOT / 'tests/historical/t05_replay.json').read_text())
        state = overlay.fold(history['overlay']['journal'], len(history['journal']))
        self.assertEqual(overlay.state_digest(state), history['overlay']['overlay_state']['digest'])
        self.assertEqual(state, history['overlay']['overlay_state']['state'])
        source = margin.ScenarioReplaySource()
        for event in history['source_replay']:source.replay(event['fixture_id'], event['scenario_id'])
        self.assertEqual(source.rows, history['final_source_views'])
        producer = PinnedFsmProducer(fixtures=source).restored(history['journal'])
        self.assertEqual(producer.state_digest(), history['f04_digest'])
        self.assertNotIn('recovery', state)
        # Pin the preserved pre-rebase bytes independently of the current golden and git HEAD.
        historical_bytes = (ROOT / 'tests/historical/journey_t05_sim.json').read_bytes()
        self.assertEqual(hashlib.sha256(historical_bytes).hexdigest(),
                         'db705e134214c09d4f3d6ca23538124eab46d1fca5baa56d3b48b8739bc24cb4')
        journey = json.loads(historical_bytes)
        self.assertEqual(journey['digest'], hashlib.sha256(canonical_bytes(journey['steps'])).hexdigest())
        final = next(step for step in journey['steps'] if step['name'] == 'final phases')
        self.assertEqual(final['facts']['state_digest'], history['f04_digest'])

    def test_file_restart_receipts_and_offline_manifest_workspace_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            source, s = book(storage=FileWorkspace.open(directory))
            run(s, 'default', 'sim-a', 'def')
            seed.distribute(source, 'sim-committed')
            body = recover(s, 1000)
            receipt = s.overlay_command(body)
            digest_before = overlay.state_digest(overlay.fold(s.overlay_entries))
            s.storage.close()
            restored = CapitalService(FileWorkspace.open(directory), producer=PinnedFsmProducer(fixtures=source))
            self.addCleanup(restored.storage.close)
            self.assertEqual(restored.workspace_status, 'ACTIVE')
            self.assertEqual(digest_before, overlay.state_digest(overlay.fold(restored.overlay_entries)))
            body['instance_id'] = restored.instance_id
            self.assertEqual(restored.overlay_command(body)['entry'], receipt['entry'])
            manifest = Path(directory) / 'manifest.json';manifest.write_text(json.dumps(restored.export_manifest()))
            result = subprocess.run(['python3', '-m', 'capital.verify', str(manifest)], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = audit_workspace(directory)
            self.assertTrue(report['ok'], report)
            result = subprocess.run(['python3', '-m', 'capital.verify', '--workspace', directory], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_http_agent_posting_refusal_and_recovery_schema(self):
        from capital.server import make_server
        from facade_schema import load_contract, validate
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            s = server.service
            agent = s.authorizer.bind_role('agent')
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            body = cmd(s, 'post_writeoff', 'deny')
            client.request('POST', '/api/overlay/commands', json.dumps(body), {'Content-Type': 'application/json', 'X-Capital-Token': agent, 'Origin': 'http://127.0.0.1:' + str(server.server_port)})
            response = client.getresponse();payload = json.loads(response.read());client.close()
            self.assertEqual((response.status, payload['error']), (403, 'RECOVERY_AGENT_FORBIDDEN'))
            doc = load_contract()
            validate(body, doc['definitions']['overlay_command_request'], doc)
            validate(s.overlay_state(), doc['definitions']['overlay_state'], doc)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)
