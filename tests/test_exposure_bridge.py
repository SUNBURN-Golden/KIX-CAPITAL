"""Independent SIMULATED journal arithmetic exercised through the workspace reader."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import audit, evidence, exposure_bridge, margin, overlay, recovery, store
from capital.producer import PinnedFsmProducer
from capital.service import CapitalService
from tests.test_overlay import draw_book, run, tick
from tests.test_recovery import cmd, recover, seed
from tests.test_repayment_posting import pay

ROOT = Path(__file__).resolve().parents[1]
VECTOR = json.loads((ROOT / 'tests/vectors/exposure_bridge.json').read_bytes())


class ExposureBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.path = self.directory / store.FILE_NAME

    def service(self, source=None):
        service = CapitalService(producer=PinnedFsmProducer(fixtures=source)) if source else CapitalService()
        self.addCleanup(service.observability.close)
        return service

    def capture(self, service, *, audited=True):
        service._persist()
        raw = store.canonical_bytes(service.storage._document)
        self.path.write_bytes(raw)
        self.path.chmod(0o600)
        if audited:
            checked = audit.audit_workspace(self.directory)
            self.assertTrue(checked['ok'], checked)
        return raw

    def defaulted(self, *, accrued=True):
        source = margin.ScenarioReplaySource()
        service = self.service(source)
        if not accrued:
            tick(service, 'bind-terms', 0, 1)
        draw_book(service)
        if accrued:
            tick(service, 'day10', 0, 10)
        self.assertEqual(run(service, 'default', 'sim-a', 'default')['outcome'], 'ACCEPTED')
        seed.distribute(source, 'sim-committed')
        return service

    def written_off(self, *, accrued=True):
        service = self.defaulted(accrued=accrued)
        if accrued:
            service.overlay_command(recover(service, 1000, 'early'))
            tick(service, 'day100', 10, 100)
            service.overlay_command(recover(service, 100, 'same-day-early'))
        else:
            tick(service, 'day100', 1, 100)
            # Model a ledger with a clock and terms binding but no accrual posting.
            service.overlay_entries = [e for e in service.overlay_entries if e['kind'] != overlay.KIND_INTEREST]
        service.overlay_command(cmd(service, 'post_writeoff', 'writeoff',
                                    setoff_declined_reason='SIMULATED_FIXTURE_DECLINE'))
        return service

    def closed(self, *, service=None, ref='sim-a', paid=False, accrued=True):
        service = service or self.service()
        draw_book(service, advance=ref, prefix=ref)
        if accrued:
            day = overlay.fold(service.overlay_entries)['sim_day']
            tick(service, ref + '-tick', day, day + 70)
        if paid:
            # 90,000 principal plus 1,035 contractual (60 days) and 246 default (10 days).
            pay(service, ref + '-all', 91281, advance=ref)
        else:
            self.assertEqual(run(service, 'repay', ref, ref + '-principal',
                                 amount=90000, sequence=1)['outcome'], 'ACCEPTED')
        self.assertEqual(run(service, 'close', ref, ref + '-close')['outcome'], 'ACCEPTED')
        return service

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'capital.exposure_bridge', *args], cwd=ROOT,
                              capture_output=True, timeout=30)

    def report(self, service=None):
        if service is not None:
            self.capture(service)
        return exposure_bridge.report_workspace(self.directory)

    def row(self, service=None, status='COMPLETE'):
        result = self.report(service)
        self.assertEqual(result['status'], status, result['reasons'])
        self.assertEqual(len(result['rows']), 1)
        return result['rows'][0]

    def checks(self, row):
        return {c['id']: c for c in row['checks']}

    def assert_amounts(self, row, expected):
        self.assertEqual({key: row['amounts'][key] for key in expected}, expected)
        for field, amount in expected.items():
            if amount is not None:
                check = self.checks(row)[field]
                self.assertEqual((check['status'], check['expected_krw'], check['observed_krw']),
                                 ('MATCHED', amount, amount))

    def test_offered_drawn_and_linked_repayment_use_only_f04_principal_once(self):
        service = self.service()
        self.assertEqual(run(service, 'offer', 'sim-z', 'z-offer', fixture_id='sim-committed',
                             amount=5000)['outcome'], 'ACCEPTED')
        draw_book(service)
        tick(service, 'day10', 0, 10)
        report = self.report(service)
        offered, = [row for row in report['rows'] if row['phase'] == 'OFFERED']
        drawn, = [row for row in report['rows'] if row['phase'] == 'DRAWN']
        self.assert_amounts(offered, {'f04_exposure_krw': 0})
        self.assert_amounts(drawn, {'f04_exposure_krw': 90000})
        pay(service, 'linked-pay', 1000)
        report = self.report(service)
        self.assertEqual([r['advance_id'] for r in report['rows']], ['sim-a', 'sim-z'])
        drawn = report['rows'][0]
        self.assert_amounts(drawn, {'f04_exposure_krw': 89172})
        f04 = self.checks(drawn)['f04_exposure_krw']
        self.assertEqual([r['kind'] for r in f04['references']], ['offer', 'draw', 'repay'])
        repayment = next(e for e in service.overlay_entries if e['kind'] == overlay.KIND_REPAYMENT)
        self.assertEqual(f04['references'][-1]['entry_id'], repayment['payload']['f04_operation_id'])
        self.assertTrue(any(r['entry_id'] == 'linked-pay' for r in drawn['references']))
        for row in report['rows']:
            self.assertEqual(row['recovery_basis'], 'NOT_APPLICABLE')
            self.assertIsNone(row['amounts']['recovery_principal_krw'])

    def test_anchor_accounts_for_accepted_f04_repayment_before_default(self):
        service = self.service()
        draw_book(service)
        tick(service, 'day10', 0, 10)
        pay(service, 'linked', 1000)
        self.assertEqual(run(service, 'default', 'sim-a', 'default')['outcome'], 'ACCEPTED')
        row = self.row(service)
        self.assert_amounts(row, {'f04_exposure_krw': 89172, 'default_anchor_principal_krw': 89172,
                                  'principal_recovered_krw': 0, 'recovery_claim_krw': 89172})
        refs = self.checks(row)['default_anchor_principal_krw']['references']
        default, anchor = refs[-2:]
        self.assertEqual((default['kind'], default['index'] + 1), ('default', anchor['after_journal_index']))

    def test_partial_and_full_recovery_leave_terminal_f04_unchanged(self):
        service = self.defaulted()
        self.assert_amounts(self.row(service), {'f04_exposure_krw': 90000, 'recovery_interest_krw': 172,
                                               'recovery_claim_krw': 90172})
        terminal = self.report()['source']['state_digest']
        service.overlay_command(recover(service, 1000, 'partial'))
        partial = self.row(service)
        self.assert_amounts(partial, VECTOR['partial_recovery'])
        self.assertEqual(partial['recovery_basis'], 'POST_DEFAULT')
        self.assertEqual(self.checks(partial)['f04_principal_bridge']['status'], 'MATCHED')
        service.overlay_command(recover(service, 89172, 'full'))
        self.assert_amounts(self.row(service), VECTOR['full_recovery'])
        self.assertEqual(self.report()['source']['state_digest'], terminal)

    def test_writeoff_separates_same_day_entries_by_original_index_and_deduplicates(self):
        service = self.written_off()
        at_writeoff = self.row(service)
        self.assertEqual(at_writeoff['recovery_basis'], 'POST_WRITEOFF')
        self.assert_amounts(at_writeoff, VECTOR['writeoff'])
        self.assertEqual(self.checks(at_writeoff)['writeoff_cutoff_principal_krw']['status'], 'MATCHED')
        terminal = self.report()['source']['state_digest']
        service.overlay_command(recover(service, 300, 'late-one'))
        service.overlay_command(recover(service, 700, 'late-two'))
        # Insert a duplicate before the writeoff to ensure reported indexes are original, not compacted.
        cut = next(i for i, e in enumerate(service.overlay_entries) if e['kind'] == 'WRITEOFF')
        service.overlay_entries.insert(cut, copy.deepcopy(service.overlay_entries[cut - 1]))
        service.overlay_entries.append(copy.deepcopy(service.overlay_entries[-1]))
        row = self.row(service)
        expected = VECTOR['late_recoveries']
        self.assert_amounts(row, {**VECTOR['writeoff'], 'recovery_claim_krw': expected['recovery_claim_krw'],
                                  'post_writeoff_residual_claim_krw': expected['post_writeoff_residual_claim_krw']})
        running = [c for c in row['checks'] if c['id'].startswith('running_residual_claim_krw:')]
        self.assertEqual([c['expected_krw'] for c in running], expected['running_residual_claims_krw'])
        self.assertTrue(all(c['status'] == 'MATCHED' for c in running))
        self.assertEqual([c['references'][-1]['entry_id'] for c in running], ['late-one', 'late-two'])
        self.assertEqual(running[0]['references'][0]['index'], cut + 1)
        same_day = [r for r in row['references'] if r['entry_id'] in
                    ('same-day-early', 'writeoff', 'late-one', 'late-two')]
        self.assertEqual([r['entry_id'] for r in same_day], ['same-day-early', 'writeoff', 'late-one', 'late-two'])
        self.assertEqual({(r['sim_day'], r['after_journal_index']) for r in same_day}, {(100, 5)})
        for check in running:
            e = service.overlay_entries[check['references'][-1]['index']]
            self.assertNotIn('allocation', e['payload'])
        self.assertEqual(row['fold_values']['position']['default_interest_krw'], 2098)
        self.assertEqual(self.report()['source']['state_digest'], terminal)

    def test_missing_accrual_preserves_verified_principal_and_raw_zero_buckets(self):
        service = self.defaulted(accrued=False)
        service.overlay_command(recover(service, 1000, 'early'))
        row = self.row(service, 'INCOMPLETE')
        self.assert_amounts(row, VECTOR['missing_accrual'])
        self.assertEqual(row['fold_values']['position'], {'principal_krw': 89000, 'interest_krw': 0,
                         'default_interest_krw': 0, 'claim_krw': 89000})
        for field in ('recovery_interest_krw', 'recovery_default_interest_krw', 'recovery_claim_krw'):
            check = self.checks(row)[field]
            self.assertEqual((check['status'], check['reason'], check['expected_krw']),
                             ('NOT_CHECKED', 'ACCRUAL_NOT_BOUND', None))

    def test_missing_accrual_at_writeoff_leaves_opening_and_late_claim_unverified(self):
        service = self.written_off(accrued=False)
        service.overlay_command(recover(service, 300, 'late'))
        row = self.row(service, 'INCOMPLETE')
        self.assert_amounts(row, {'written_off_principal_krw': 90000, 'recovery_principal_krw': 0})
        fields = ('writeoff_opening_claim_krw', 'post_writeoff_residual_claim_krw', 'recovery_claim_krw')
        self.assertTrue(all(row['amounts'][field] is None for field in fields))
        self.assertEqual([self.checks(row)[field]['reason'] for field in fields], ['ACCRUAL_NOT_BOUND'] * 3)
        running, = [c for c in row['checks'] if c['id'].startswith('running_residual_claim_krw:')]
        self.assertEqual((running['status'], running['observed_krw']), ('NOT_CHECKED', 89700))

    def test_legacy_default_without_anchor_retains_f04_and_exits_one(self):
        service = self.defaulted(accrued=False)
        service.overlay_entries = []
        row = self.row(service, 'INCOMPLETE')
        self.assert_amounts(row, {'f04_exposure_krw': 90000})
        self.assertEqual(row['recovery_basis'], 'NOT_BOUND')
        self.assertEqual(row['reasons'], ['DEFAULT_ANCHOR_NOT_BOUND'])
        self.assertIsNone(row['fold_values']['position'])
        self.assertTrue(all(v is None for k, v in row['amounts'].items() if k != 'f04_exposure_krw'))
        result = self.cli('--workspace', str(self.directory))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'INCOMPLETE')

    def test_closed_interest_is_separate_from_f04_and_has_evidenced_zeros(self):
        row = self.row(self.closed())
        self.assertEqual(row['phase'], 'CLOSED')
        self.assertEqual(row['recovery_basis'], 'NOT_APPLICABLE')
        self.assert_amounts(row, {'f04_exposure_krw': 0, 'closed_unpaid_interest_krw': 1035,
                                  'closed_unpaid_default_interest_krw': 246})
        row = self.row(self.closed(paid=True))
        self.assert_amounts(row, {'f04_exposure_krw': 0, 'closed_unpaid_interest_krw': 0,
                                  'closed_unpaid_default_interest_krw': 0})

    def test_closed_without_terms_or_accrual_stays_null_in_mixed_book(self):
        service = self.closed(ref='sim-early', accrued=False)
        report = self.report(service)
        self.assertEqual(report['rows'][0]['reasons'], ['TERMS_BINDING_NOT_BOUND', 'ACCRUAL_NOT_BOUND'])
        self.closed(service=service, ref='sim-later')
        report = self.report(service)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['coverage'], {'advances': 2, 'complete': 1, 'incomplete': 1})
        self.assertNotIn('totals', report)
        early, later = report['rows']
        self.assertEqual(early['reasons'], ['ACCRUAL_NOT_BOUND'])
        self.assert_amounts(early, {'f04_exposure_krw': 0, 'closed_unpaid_interest_krw': None,
                                    'closed_unpaid_default_interest_krw': None})
        self.assert_amounts(later, {'f04_exposure_krw': 0, 'closed_unpaid_interest_krw': 1035,
                                    'closed_unpaid_default_interest_krw': 246})

    def test_empty_book_has_counts_only(self):
        report = self.report(self.service())
        self.assertEqual((report['status'], report['rows']), ('COMPLETE', []))
        self.assertEqual(report['coverage'], {'advances': 0, 'complete': 0, 'incomplete': 0})
        self.assertEqual((report['authentication'], report['actual_payments']), ('NOT_BOUND', 'NOT_BOUND'))

    def test_individual_fold_mismatches_are_detected_after_the_real_audit(self):
        service = self.written_off()
        self.capture(service)
        checks = (
            ('anchor', 'principal_krw', 'default_anchor_principal_krw'),
            ('recovered', 'principal_recovered_krw', 'principal_recovered_krw'),
            ('recovered', 'written_off_krw', 'written_off_principal_krw'),
            ('recovered', 'residual_claim_krw', 'post_writeoff_residual_claim_krw'),
            ('position', 'principal_krw', 'recovery_principal_krw'),
            ('position', 'interest_krw', 'recovery_interest_krw'),
            ('position', 'default_interest_krw', 'recovery_default_interest_krw'),
            ('position', 'claim_krw', 'recovery_claim_krw'),
        )
        compose = exposure_bridge._compose
        state = overlay.fold(service.overlay_entries)
        for fold, field, check_id in checks:
            with self.subTest(fold=fold, field=field):
                raw_values = {name: getattr(recovery, name)(state, 'sim-a')
                              for name in ('anchor', 'recovered', 'position')}
                raw_values[fold] = {**raw_values[fold], field: raw_values[fold][field] + 1}

                def mismatched(*args):
                    with patch.multiple(recovery, **{name: lambda *_, value=value: value
                                                   for name, value in raw_values.items()}):
                        return compose(*args)

                with patch.object(exposure_bridge, '_compose', side_effect=mismatched):
                    row = self.row(status='INCOMPLETE')
                self.assertEqual(self.checks(row)[check_id]['status'], 'MISMATCH')
                self.assertIsNone(row['amounts'][check_id])
                self.assertEqual(row['amounts']['f04_exposure_krw'], 90000)

    def test_unanchored_f04_exposure_is_independently_checked(self):
        service = self.defaulted(accrued=False)
        service.overlay_entries = []
        self.capture(service)
        restore = evidence.offline_service

        def wrong_view(document):
            restored = restore(document)
            view = restored.machine.view
            restored.machine.view = lambda ref: {**view(ref), 'outstanding_exposure': 89999}
            return restored

        with patch.object(evidence, 'offline_service', side_effect=wrong_view):
            result = self.report()
        self.assertTrue(result['source']['audit']['ok'])
        self.assertEqual(result['reasons'], ['MONETARY_EVIDENCE_NOT_BOUND', 'RECONCILIATION_FAILED'])
        check = self.checks(result['rows'][0])['f04_exposure_krw']
        self.assertEqual((check['status'], check['expected_krw'], check['observed_krw']), ('MISMATCH', 90000, 89999))

    def test_stamped_cutoff_and_each_late_running_residual_have_independent_checks(self):
        service = self.written_off()
        service.overlay_command(recover(service, 300, 'late-one'))
        service.overlay_command(recover(service, 700, 'late-two'))
        self.capture(service)
        compose = exposure_bridge._compose
        first_late = next(i for i, e in enumerate(service.overlay_entries) if e['overlay_id'] == 'late-one')
        for entry_id, field, check_id in (
            ('writeoff', 'writeoff_principal_krw', 'writeoff_cutoff_principal_krw'),
            ('writeoff', 'residual_claim_krw', 'writeoff_opening_claim_krw'),
            ('late-one', 'residual_claim_krw', f'running_residual_claim_krw:{first_late}'),
        ):
            with self.subTest(field=field, entry_id=entry_id):
                def mismatched(restored, state, journal, entries):
                    entry = next(e for e in entries if e['overlay_id'] == entry_id)
                    entry['payload'][field] += 1
                    return compose(restored, state, journal, entries)

                with patch.object(exposure_bridge, '_compose', side_effect=mismatched):
                    row = self.row(status='INCOMPLETE')
                self.assertEqual(self.checks(row)[check_id]['status'], 'MISMATCH')
                self.assertEqual(row['amounts']['post_writeoff_residual_claim_krw'], 90270)

    def test_resealed_anchor_corruption_fails_semantics_and_leaves_source_untouched(self):
        service = self.defaulted()
        self.capture(service)
        document = copy.deepcopy(service.storage._document)
        entries = copy.deepcopy(service.overlay_entries)
        anchor = next(e for e in entries if e['kind'] == 'default_anchor')
        anchor['payload']['principal_krw'] -= 1
        document['overlay'] = overlay.build_section(entries)
        raw = store.canonical_bytes(document)
        self.path.write_bytes(raw)
        result = self.report()
        self.assertEqual(result['status'], 'AUDIT_FAILED')
        self.assertIsNone(result['rows'])
        self.assertEqual(result['source']['audit']['failed_check'], 'service_restore')
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_source_hashes_references_and_deterministic_read_only_cli(self):
        service = self.written_off()
        raw = self.capture(service)
        original_mode = self.path.stat().st_mode
        original_paths = sorted(self.directory.iterdir())
        report = self.report()
        source = report['source']
        self.assertEqual(source['workspace_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(source['payload_sha256'], hashlib.sha256(
            store.canonical_bytes(json.loads(raw)['payload'])).hexdigest())
        self.assertEqual(source['state_digest'], service.machine.state_digest())
        self.assertEqual(source['overlay_state_digest'], overlay.state_digest(overlay.fold(service.overlay_entries)))
        self.assertEqual(source['sim_day'], 100)
        self.assertEqual(source['audit'], audit.audit_workspace(self.directory))
        row = report['rows'][0]
        journals = {'F04': service.machine.export_journal(), 'OVERLAY': service.overlay_entries}
        for refs in [row['references'], *(c['references'] for c in row['checks'])]:
            for ref in refs:
                entry = journals[ref['journal']][ref['index']]
                self.assertEqual(ref['entry_id'], entry.get('overlay_id', entry.get('idempotency_key')))
                self.assertEqual(ref['kind'], entry.get('kind', entry.get('op')))
                self.assertEqual(ref['sim_day'], entry.get('sim_day'))
                self.assertEqual(ref['after_journal_index'], entry.get('after_journal_index'))
                self.assertIn(ref, row['references'])
        for _ in range(2):
            command = self.cli('--workspace', str(self.directory))
            self.assertEqual(command.returncode, 0, command.stderr)
            self.assertEqual(command.stdout, store.canonical_bytes(report) + b'\n')
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.path.stat().st_mode, original_mode)
        self.assertEqual(sorted(self.directory.iterdir()), original_paths)

    def test_no_lock_save_or_network_and_the_restored_service_closes(self):
        self.capture(self.closed())
        restored = evidence.offline_service(json.loads(self.path.read_bytes()))
        with patch.object(store.FileWorkspace, 'open', side_effect=AssertionError('lock')), \
             patch.object(evidence._DocumentStorage, 'save', side_effect=AssertionError('save')), \
             patch.object(socket.socket, 'connect', side_effect=AssertionError('network')), \
             patch.object(evidence, 'offline_service', return_value=restored), \
             patch.object(restored.observability, 'close', wraps=restored.observability.close) as close:
            self.assertEqual(self.report()['status'], 'COMPLETE')
            close.assert_called_once_with()

    def test_path_replaced_during_audit_still_emits_the_original_capture(self):
        self.capture(self.closed())
        original = self.report()
        real_audit = audit.audit_workspace_bytes
        replacement = self.directory / 'replacement'
        replacement.write_bytes(b'replaced workspace')

        def replace(raw, **kwargs):
            replacement.replace(self.path)
            return real_audit(raw, **kwargs)

        with patch.object(audit, 'audit_workspace_bytes', side_effect=replace):
            self.assertEqual(self.report(), original)
        self.assertEqual(self.path.read_bytes(), b'replaced workspace')

    def test_audit_failure_restore_failure_and_argument_misuse(self):
        report = self.report()
        self.assertEqual(report['status'], 'AUDIT_FAILED')
        self.assertIsNone(report['rows'])
        self.assertIsNone(report['coverage'])
        self.path.write_bytes(b'{"dup":1,"dup":2}')
        command = self.cli('--workspace', str(self.directory))
        self.assertEqual(command.returncode, 1)
        self.assertEqual(json.loads(command.stdout)['source']['audit']['failed_check'], 'strict_json')
        self.assertEqual(self.cli().returncode, 2)
        self.capture(self.closed())
        restored = evidence.offline_service(json.loads(self.path.read_bytes()))
        restored.workspace_status = 'WORKSPACE_UNREADABLE'
        with patch.object(evidence, 'offline_service', return_value=restored), \
             patch.object(restored.observability, 'close', wraps=restored.observability.close) as close:
            report = self.report()
            close.assert_called_once_with()
        self.assertEqual((report['status'], report['reasons'], report['rows']),
                         ('AUDIT_FAILED', ['RESTORE_NOT_ACTIVE'], None))
