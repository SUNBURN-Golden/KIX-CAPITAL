"""SIMULATED same-cut origination inventory; existing readers remain advisory."""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from capital import audit, evidence, origination, overlay, store
from capital.service import CapitalService, digest
from capital.terms import DecisionNoteTermsPolicy
from tests.test_claim_slices import seed
from tests.test_underwriting import write_note

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / 'tests/vectors/origination.json'


def command(service, op, aid, **args):
    result = service.execute({'instance_id': service.instance_id,
                              'operation_id': aid + '-' + op.replace('_', '-'),
                              'advance_id': aid, 'op': op, 'args': args})
    assert result['outcome'] == 'ACCEPTED', result
    return result


def add_case(service, aid, fixture, amount, phase='APPROVED'):
    command(service, 'offer', aid, fixture_id=fixture, amount=amount)
    if phase != 'OFFERED':
        command(service, 'approve', aid)
        command(service, 'bind_settlement', aid)


def workspace(directory, mixed=True):
    """Use immutable built-in fixtures so ordinary offline audit can replay it."""
    service = CapitalService()
    try:
        if mixed:
            spec = json.loads(VECTOR.read_bytes())
            face = service.slice_policy['threshold'] // 10
            seed.register(service, 'review-slice', face, 'demo-delta-small')
            seed.open_slice(service, 'review-slice')
            for row in spec['scenarios']:
                base = service.underwrite(row['fixture_id'], service.instance_id, 'auditor', amount=1)['borrowing_base']
                amounts = {'one': 1}
                if base:
                    amounts.update(half_base=base['base_krw'] // 2,
                                   base_plus_one=base['base_krw'] + 1,
                                   reduced_base_plus_one=base['base_krw'] + 1)
                add_case(service, row['advance_id'], row['fixture_id'], amounts[row['amount_rule']], row['phase'])
            for aid in spec['excluded']:
                add_case(service, aid, 'demo-alpha-arena', 1, 'OFFERED' if aid == 'sim-rejected' else 'APPROVED')
                if aid in ('sim-rejected', 'sim-cancelled'):
                    command(service, 'reject' if aid == 'sim-rejected' else 'cancel', aid)
                else:
                    command(service, 'draw', aid)
                    if aid in ('sim-repaid-unclosed', 'sim-closed'):
                        command(service, 'repay', aid, amount=1, sequence=1)
                    if aid == 'sim-closed':
                        command(service, 'close', aid)
                    if aid == 'sim-defaulted':
                        command(service, 'default', aid)
            service.overlay_command({'instance_id': service.instance_id, 'operation_id': 'review-day',
                                     'op': 'advance_day', 'from_sim_day': 0, 'to_sim_day': 3,
                                     'reason': 'SIMULATED review cut'})
        document = store.envelope('simulated-origination-fixture', {
            'journal': service.machine.export_journal(), 'receipts': service.receipts,
            'case_fixtures': service.case_fixtures, 'state_digest': service.machine.state_digest(),
        }, overlay.build_section(service.overlay_entries))
        document['saved_at'] = 'SIMULATED_FIXED_CAPTURE'
        path = Path(directory) / store.FILE_NAME
        path.write_bytes(store.canonical_bytes(document))
        path.chmod(0o600)
        return document
    finally:
        service.observability.close()


def disk_cut(directory):
    return {str(p.relative_to(directory)): (stat.S_IMODE(p.stat().st_mode), p.read_bytes() if p.is_file() else None)
            for p in Path(directory).rglob('*')}


class OriginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.document = workspace(self.directory)

    def report(self):
        return origination.report_workspace(self.directory)

    def restored(self):
        service = evidence.offline_service(self.document)
        self.addCleanup(service.observability.close)
        return service

    def test_vector_population_and_reader_parity(self):
        report = self.report()
        self.assertEqual(report['status'], 'COMPLETE', report['reasons'])
        self.assertEqual(report['format'], origination.FORMAT)
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual(report['mode'], 'READ_ONLY_ORIGINATION_REVIEW')
        spec = json.loads(VECTOR.read_bytes())
        self.assertEqual(spec['label'], 'SIMULATED')
        rows = {r['advance_id']: r for r in report['cases']}
        self.assertEqual(list(rows), sorted(r['advance_id'] for r in spec['scenarios']))
        self.assertTrue(set(spec['excluded']).isdisjoint(rows))
        direct = self.restored()
        for expected in spec['scenarios']:
            with self.subTest(case=expected['advance_id']):
                row = rows[expected['advance_id']]
                self.assertEqual(row['phase'], expected['phase'])
                self.assertEqual(row['fsm_preview']['outcome'], expected['preview'])
                self.assertEqual(row['underwriting']['proposal'], expected['proposal'])
                self.assertEqual(row['underwriting']['failed_check'], expected['failed_check'])
                self.assertEqual(row['amount'], direct.machine.view(row['advance_id'])['amount'])
                self.assertEqual(row['fsm_preview'], direct.preview_draw(row['advance_id'], direct.instance_id))
                self.assertEqual(row['underwriting'], direct.underwrite(row['advance_id'], direct.instance_id, 'auditor', sim_day=3))
                self.assertEqual(len(row['underwriting']['checks']), 6)
                for body in (row['fsm_preview'], row['underwriting']):
                    self.assertEqual(body['observed_state_digest'], report['source']['state_digest'])
                self.assertNotIn('score', row)
                self.assertNotIn('approved', row)
        self.assertEqual(rows['sim-proposed']['fsm_preview']['reason'], 'APPROVED_PHASE_REQUIRED')
        self.assertEqual(rows['sim-fsm-refusal']['fsm_preview']['reason'], 'SETTLEMENT_NOT_COMMITTED')
        self.assertEqual(report['source']['recorded_sim_day'], 3)
        self.assertEqual(report['authentication'], 'NOT_BOUND')
        self.assertEqual(report['historical_policy_provenance'], 'NOT_BOUND')
        self.assertIn('Individually acceptable previews do not establish simultaneous fundability. Underwriting remains advisory.', report['limitations'])
        self.assertTrue(any('slice draw guard' in text for text in report['limitations']))
        self.assertTrue(all(report[k] is False for k in ('funds_executed', 'workspace_mutated', 'write_authorized')))

    def test_slice_base_and_caps_keep_existing_constraints(self):
        report = self.report()
        row = next(r for r in report['cases'] if r['advance_id'] == 'sim-slice-constrained')
        record = row['underwriting']
        service = self.restored()
        face = service.slice_policy['threshold'] // 10
        claim = service.fixtures.view(row['fixture_id'])['claim']
        payees = service.terms.items['additional_margin']['value']['beneficiary_payee_map']['demo-org-delta']
        eligible = sum(l['outstanding'] for l in claim['obligations'] if l['payee'] in payees) - claim['refund_face']
        base = record['borrowing_base']
        self.assertEqual(base['slice_encumbered_krw'], face)
        self.assertEqual(base['eligible_face'], eligible - face)
        self.assertEqual(base['base_krw'], (eligible - face) * base['advance_rate_bps'] // 10000)
        self.assertEqual(row['amount'], base['base_krw'] + 1)
        self.assertLessEqual(row['amount'], eligible * base['advance_rate_bps'] // 10000)
        caps = service.terms.items['underwriting_depth']['value']
        outstanding = sum(service.machine.view(a)['outstanding_exposure'] for a in service.case_fixtures)
        self.assertEqual(record['caps_remaining']['portfolio_krw'], caps['portfolio_cap_krw'] - outstanding - row['amount'] - face)
        self.assertEqual(record['caps_remaining']['beneficiary_aggregate_krw'], caps['beneficiary_aggregate_cap_krw'] - row['amount'] - face)
        self.assertEqual(row['fsm_preview']['outcome'], 'WOULD_ACCEPT')

    def test_source_references_cover_full_portfolio_and_overlay(self):
        report = self.report()
        source = report['source']
        self.assertEqual(source['captured_sha256'], hashlib.sha256((self.directory / store.FILE_NAME).read_bytes()).hexdigest())
        self.assertEqual(source['payload_sha256'], self.document['payload_sha256'])
        self.assertEqual(source['vendor_pin']['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        refs = source['references']
        for ref in refs['f04']:
            self.assertEqual(ref['sha256'], digest(self.document['payload']['journal'][ref['index']]))
        for ref in refs['overlay']:
            self.assertEqual(ref['sha256'], digest(self.document['overlay']['journal'][ref['index']]))
        self.assertEqual([r['advance_id'] for r in refs['portfolio']], sorted(self.document['payload']['case_fixtures']))
        service = self.restored()
        for row in report['cases']:
            links = row['source_references']
            self.assertEqual([refs['f04'][i]['advance_id'] for i in links['f04_indexes']], [row['advance_id']] * len(links['f04_indexes']))
            fixture = refs['fixtures'][links['fixture_index']]
            self.assertEqual(fixture['fixture_id'], row['fixture_id'])
            self.assertEqual(fixture['claim_sha256'], digest(service.fixtures.view(row['fixture_id'])['claim']))
            self.assertEqual(links['portfolio_indexes'], list(range(len(refs['portfolio']))))
            self.assertEqual(links['overlay_indexes'], list(range(len(refs['overlay']))))
            self.assertEqual(links['policy_note_sha256'], source['loaded_policy']['terms']['note_sha256'])

    def test_reordered_enumeration_and_repeated_report_are_identical(self):
        first = self.report()
        restore = evidence.offline_service
        def reverse(document):
            service = restore(document)
            service.case_fixtures = dict(reversed(list(service.case_fixtures.items())))
            return service
        with patch.object(evidence, 'offline_service', side_effect=reverse):
            self.assertEqual(first, self.report())
        self.assertEqual(first, self.report())
        rows = {r['advance_id']: r for r in first['cases']}
        # Both share a face, and their sum exceeds it; both preview independently.
        face = self.restored().machine.view('sim-ready')['open_face']
        self.assertGreater(rows['sim-ready']['amount'] + rows['sim-policy-decline']['amount'], face)
        self.assertEqual([rows[a]['fsm_preview']['outcome'] for a in ('sim-ready', 'sim-policy-decline')], ['WOULD_ACCEPT'] * 2)

    def test_no_commands_saves_locks_or_disk_mutation(self):
        before = disk_cut(self.directory)
        restored = self.restored()
        original = origination._cut(restored)
        close = Mock(wraps=restored.observability.close)
        with patch.object(evidence, 'offline_service', return_value=restored), \
                patch.object(CapitalService, 'execute', side_effect=AssertionError('command')), \
                patch.object(CapitalService, 'overlay_command', side_effect=AssertionError('overlay command')), \
                patch.object(evidence._DocumentStorage, 'save', side_effect=AssertionError('save')), \
                patch.object(audit._DocumentStorage, 'save', side_effect=AssertionError('audit save')), \
                patch.object(store.FileWorkspace, 'open', side_effect=AssertionError('lock')), \
                patch.object(restored.observability, 'close', close):
            self.assertEqual(self.report()['status'], 'COMPLETE')
        close.assert_called_once()
        self.assertEqual(origination._cut(restored), original)
        self.assertEqual(disk_cut(self.directory), before)

    def test_one_capture_even_if_file_changes_after_audit(self):
        original = audit.audit_workspace_bytes
        raw = (self.directory / store.FILE_NAME).read_bytes()
        def audited(capture, **kwargs):
            self.assertEqual(capture, raw)
            (self.directory / store.FILE_NAME).write_bytes(b'broken newer workspace')
            return original(capture, **kwargs)
        with patch.object(audit, 'audit_workspace_bytes', side_effect=audited) as call:
            report = self.report()
        call.assert_called_once()
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertEqual(report['source']['captured_sha256'], hashlib.sha256(raw).hexdigest())

    def test_existing_workspace_lock_is_not_disturbed(self):
        held = store.FileWorkspace.open(self.directory)
        try:
            before = disk_cut(self.directory)
            self.assertEqual(self.report()['status'], 'COMPLETE')
            self.assertEqual(disk_cut(self.directory), before)
            with self.assertRaises(store.WorkspaceError) as caught:
                store.FileWorkspace.open(self.directory)
            self.assertEqual(caught.exception.code, 'WORKSPACE_LOCKED')
        finally:
            held.close()

    def test_missing_or_unusable_policy_retains_not_bound_without_numeric_outputs(self):
        for kind in ('missing', 'unusable'):
            with self.subTest(kind=kind):
                note = self.directory / 'absent.md'
                if kind == 'unusable':
                    note = write_note(self.directory, lambda b: b['entries']['underwriting_depth'].update(status='UNDETERMINED'))
                # Evidence is absent during construction, not removed after a
                # successful restore with an already-bound slice policy.
                with patch('capital.terms.default_note_path', return_value=note):
                    report = self.report()
                self.assertTrue(report['source']['audit']['ok'])
                self.assertIsNone(report['source']['loaded_policy']['slice_policy'])
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertEqual(report['reasons'], ['POLICY_EVIDENCE_NOT_BOUND'])
                for row in report['cases']:
                    record = row['underwriting']
                    self.assertEqual(record['status'], 'NOT_BOUND')
                    for key in ('checks', 'borrowing_base', 'caps_remaining', 'proposal', 'inputs_digest'):
                        self.assertNotIn(key, record)
                with patch.object(origination, 'report_workspace', return_value=report), patch('sys.stdout', Mock(buffer=io.BytesIO())):
                    self.assertEqual(origination.main(['--workspace', str(self.directory)]), 1)

    def test_missing_slice_policy_alone_retains_unbound_records(self):
        with patch('capital.slices.load_policy', return_value=None):
            report = self.report()
        self.assertTrue(report['source']['audit']['ok'])
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['reasons'], ['POLICY_EVIDENCE_NOT_BOUND'])
        self.assertEqual(report['source']['loaded_policy']['terms']['status'], 'BOUND')
        self.assertEqual(len(report['cases']), 5)
        for row in report['cases']:
            self.assertEqual(row['underwriting']['status'], 'NOT_BOUND')
            self.assertNotIn('checks', row['underwriting'])
            self.assertNotIn('borrowing_base', row['underwriting'])

    def test_invariant_failure_suppresses_every_row(self):
        for kind in ('receipt', 'mapping', 'overlay', 'fixture', 'draw', 'observed_digest'):
            with self.subTest(kind=kind):
                service = self.restored()
                preview = service.preview_draw
                def mutate(aid, instance):
                    body = preview(aid, instance)
                    if kind == 'receipt': service.receipts['intruder'] = {}
                    if kind == 'mapping': service.case_fixtures['sim-intruder'] = 'sim-committed'
                    if kind == 'overlay': service.overlay_entries.append({})
                    if kind == 'fixture': service.fixtures.rows['intruder'] = {}
                    if kind == 'draw': service.producer.apply('draw', aid, idempotency_key='intruder', args={}, bound_settlement_id=None)
                    if kind == 'observed_digest': body['observed_state_digest'] = '0' * 64
                    return body
                service.preview_draw = mutate
                with patch.object(evidence, 'offline_service', return_value=service):
                    report = self.report()
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertEqual(report['reasons'], ['READ_ONLY_INVARIANT'])
                self.assertIsNone(report['cases'])

    def test_failed_restore_and_reader_error_close_and_suppress(self):
        for kind in ('inactive', 'reader'):
            service = self.restored()
            close = Mock(wraps=service.observability.close)
            if kind == 'inactive': service.workspace_status = 'WORKSPACE_UNREADABLE'
            else: service.underwrite = Mock(side_effect=RuntimeError('failed reader'))
            with patch.object(evidence, 'offline_service', return_value=service), patch.object(service.observability, 'close', close):
                report = self.report()
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertIsNone(report['cases'])
            close.assert_called_once()
        with patch.object(evidence, 'offline_service', side_effect=ValueError('restore')):
            self.assertEqual(self.report()['reasons'], ['WORKSPACE_RESTORE_FAILED'])

    def test_underwriting_mutation_after_preview_suppresses_prior_rows(self):
        service = self.restored()
        record = service.underwrite
        calls = []
        def mutate(*args, **kwargs):
            body = record(*args, **kwargs)
            calls.append(args[0])
            if len(calls) == 2:
                service.case_fixtures['sim-ready'] = 'sim-pending'
            return body
        service.underwrite = mutate
        with patch.object(evidence, 'offline_service', return_value=service):
            report = self.report()
        self.assertEqual(len(calls), 2)
        self.assertEqual(report['reasons'], ['READ_ONLY_INVARIANT'])
        self.assertIsNone(report['cases'])

    def test_empty_and_legacy_inventory(self):
        workspace(self.directory, mixed=False)
        empty = self.report()
        self.assertEqual((empty['status'], empty['cases']), ('COMPLETE', []))
        # Use an empty legacy payload: no overlay-dependent fixtures or links.
        legacy = json.loads((self.directory / store.FILE_NAME).read_bytes())
        del legacy['overlay']
        del legacy['envelope_version']
        (self.directory / store.FILE_NAME).write_bytes(store.canonical_bytes(legacy))
        report = self.report()
        self.assertEqual((report['status'], report['cases']), ('COMPLETE', []))
        self.assertEqual(report['source']['recorded_sim_day'], 0)

    def test_empty_inventory_with_missing_policy_is_incomplete(self):
        document = workspace(self.directory, mixed=False)
        service = evidence.offline_service(document)
        self.addCleanup(service.observability.close)
        service.terms = DecisionNoteTermsPolicy(self.directory / 'missing.md')
        service.underwriting.terms = service.terms
        with patch.object(evidence, 'offline_service', return_value=service):
            report = self.report()
        self.assertEqual((report['status'], report['cases']), ('INCOMPLETE', []))
        self.assertEqual(report['reasons'], ['POLICY_EVIDENCE_NOT_BOUND'])

    def test_slice_only_workspace_with_missing_slice_policy_is_incomplete(self):
        document = workspace(self.directory, mixed=False)
        service = CapitalService()
        self.addCleanup(service.observability.close)
        seed.register(service, 'slice-only', service.slice_policy['threshold'] // 10, 'demo-delta-small')
        seed.open_slice(service, 'slice-only')
        document['overlay'] = overlay.build_section(service.overlay_entries)
        (self.directory / store.FILE_NAME).write_bytes(store.canonical_bytes(document))
        with patch('capital.slices.load_policy', return_value=None):
            report = self.report()
        self.assertTrue(report['source']['audit']['ok'])
        self.assertEqual((report['status'], report['cases']), ('INCOMPLETE', []))
        self.assertEqual(report['reasons'], ['POLICY_EVIDENCE_NOT_BOUND'])

    def test_audit_failures_suppress_all_conclusions(self):
        def sealed(doc):
            doc['payload_sha256'] = digest(doc['payload'])
            return store.canonical_bytes(doc)
        bad_checksum = copy.deepcopy(self.document)
        bad_checksum['payload_sha256'] = '0' * 64
        bad_state = copy.deepcopy(self.document)
        bad_state['payload']['state_digest'] = '0' * 64
        bad_replay = copy.deepcopy(self.document)
        bad_replay['payload']['journal'][0]['op'] = 'unknown'
        bad_overlay = copy.deepcopy(self.document)
        bad_overlay['overlay']['overlay_state']['digest'] = '0' * 64
        bad_overlay['overlay']['section_sha256'] = store.section_checksum(bad_overlay['overlay'])
        bad_recon = copy.deepcopy(self.document)
        bad_recon['payload']['receipts']['sim-ready-offer']['receipt']['result']['credit']['amount'] += 1
        bad_fingerprint = copy.deepcopy(self.document)
        bad_fingerprint['payload']['receipts']['sim-ready-offer']['fingerprint'] = '0' * 64
        cases = [(b'{', 'strict_json'), (b'{"x":1,"x":2}', 'strict_json'),
                 (store.canonical_bytes(bad_checksum), 'payload_sha256'),
                 (sealed(bad_state), 'state_digest'), (sealed(bad_replay), 'journal_replay'),
                 (store.canonical_bytes(bad_overlay), 'service_restore'),
                 (sealed(bad_fingerprint), 'receipt_journal_fingerprints'), (sealed(bad_recon), 'recon')]
        for raw, failed_check in cases:
            with self.subTest(check=failed_check), patch.object(evidence, 'offline_service', side_effect=AssertionError('must not restore')):
                (self.directory / store.FILE_NAME).write_bytes(raw)
                report = self.report()
                self.assertEqual(report['status'], 'AUDIT_FAILED')
                self.assertIsNone(report['cases'])
                self.assertEqual(report['source']['audit']['failed_check'], failed_check)
                self.assertEqual((self.directory / store.FILE_NAME).read_bytes(), raw)

    def test_cli_canonical_json_exit_codes_and_argument_misuse(self):
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'capital.origination', *args], cwd=ROOT,
                                  capture_output=True, timeout=60)
        first = cli('--workspace', str(self.directory))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stderr, b'')
        self.assertEqual(first.stdout, store.canonical_bytes(self.report()) + b'\n')
        self.assertEqual(first.stdout, cli('--workspace', str(self.directory)).stdout)
        missing = self.directory / 'absent'
        failed = cli('--workspace', str(missing))
        self.assertEqual(failed.returncode, 1)
        report = json.loads(failed.stdout)
        self.assertEqual(report['status'], 'AUDIT_FAILED')
        self.assertIsNone(report['cases'])
        self.assertFalse(missing.exists())
        self.assertEqual(cli().returncode, 2)
        self.assertEqual(cli('--workspace', str(self.directory), '--amount', '1').returncode, 2)


if __name__ == '__main__':
    unittest.main()
