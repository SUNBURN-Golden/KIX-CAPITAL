"""Real checkout-free zipapp relocation, with explicit business/session boundaries."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import overlay, recovery
from capital.keyset import DEV_KEYSET_NAME
from capital.store import FILE_NAME, canonical_bytes, verify_document
from scripts import relocation_rehearsal as rehearsal

ROOT = Path(__file__).resolve().parents[1]


class RelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.starts = []
        cls.servers = []
        cls.stable = []
        cls.captures = []
        cls.staged_keysets = []
        cls.sessions = []
        start = rehearsal.release._start
        evidence = rehearsal.evidence
        audit = rehearsal.audit

        def observed_start(pyz, workspace, cwd, env, *, dev_keyset=False):
            cls.starts.append((Path(pyz), Path(workspace), Path(cwd), dict(env), dev_keyset,
                               rehearsal.inventory(Path(workspace))))
            if dev_keyset:
                key = Path(workspace) / DEV_KEYSET_NAME
                cls.staged_keysets.append((key.read_bytes(), key.stat().st_mode & 0o777))
            server = start(pyz, workspace, cwd, env, dev_keyset=dev_keyset)
            cls.servers.append(server)
            return server

        def observed_evidence(*args):
            cls.sessions.append((args[2]['instance_id'], args[2]['local_token']))
            value = evidence(*args)
            cls.stable.append(copy.deepcopy(value))
            return value

        def observed_audit(raw, stable):
            # The captured bytes are audited only after every writer is reaped.
            if any(server.proc.poll() is None for server in cls.servers):
                raise AssertionError('audit ran before writer exit')
            cls.captures.append(raw)
            return audit(raw, stable)

        with patch.object(rehearsal.release, '_start', side_effect=observed_start), \
             patch.object(rehearsal, 'evidence', side_effect=observed_evidence), \
             patch.object(rehearsal, 'audit', side_effect=observed_audit), \
             patch.dict(os.environ, {'PYTHONPATH': '/SIMULATED-checkout-must-not-be-used'}):
            cls.report = rehearsal.rehearse()

    def test_both_modes_complete_independently(self):
        self.assertEqual([c['case'] for c in self.report['cases']], list(rehearsal.CASES))
        for case in self.report['cases']:
            self.assertEqual(case['status'], 'PASSED', case)
            for key in ('writer_stopped_before_capture', 'actual_directory_move', 'old_path_absent',
                        'source_capture_unchanged', 'children_reaped', 'explicit_runtime_inputs_only'):
                self.assertIs(case['checks'][key], True)
            self.assertEqual(case['checks']['capture_audit'], 'MATCHED')
            self.assertEqual(case['checks']['final_audit'], 'MATCHED')

    def test_required_economic_history_and_audits_are_nonempty(self):
        self.assertEqual(len(self.captures), 4)
        for case in self.report['cases']:
            ev = case['evidence']
            self.assertTrue({'repayment', 'default_anchor', 'WRITEOFF', 'SLICE_PROPOSE', 'SLICE_OPEN'}
                            <= set(ev['history_kinds']))
            self.assertEqual(ev['journal_entries'], 6)  # offer, approve, bind, draw, principal, default
            self.assertGreater(ev['overlay_entries'], 6)
            self.assertEqual(ev['receipt_count'], 6)
            self.assertEqual(ev['statement_totals']['exposure']['repaid'], 1000)
            self.assertEqual(ev['statement_totals']['exposure']['outstanding'], 59000)
            self.assertEqual(len(ev['reconciliation']), 7)
            self.assertTrue(all(c['status'] == 'MATCHED' for c in ev['reconciliation']))
        self.assertEqual(self.captures[0], self.captures[1])
        self.assertEqual(self.captures[2], self.captures[3])

    def test_real_subprocesses_use_only_staged_inputs_and_are_reaped(self):
        self.assertEqual(len(self.starts), 10)  # source, relocation, three corrupt copies, per mode
        for pyz, workspace, cwd, env, signed, files in self.starts:
            self.assertNotIn('PYTHONPATH', env)
            self.assertNotEqual(cwd, workspace)
            self.assertNotEqual(cwd, pyz.parent)
            self.assertNotIn(ROOT, cwd.parents)
            expected = {DEV_KEYSET_NAME} if signed else set()
            if workspace.name != 'workspace' or workspace.parent.name == 'relocated-runtime':
                expected.add(FILE_NAME)
            self.assertEqual(set(files), expected)
            self.assertFalse(workspace.exists())  # TemporaryDirectory cleanup, including on failure
            self.assertFalse(cwd.exists())
            self.assertFalse(pyz.exists())
        self.assertTrue(all(server.proc.poll() is not None for server in self.servers))
        self.assertTrue(all(not thread.is_alive() for server in self.servers for thread in server.threads))
        self.assertTrue(all(server.proc.args[1] == '-B' for server in self.servers))
        self.assertTrue(all(('--dev-keyset' in server.proc.args) == start[4]
                            for server, start in zip(self.servers, self.starts)))

    def test_old_sessions_fenced_and_first_results_retained(self):
        for case in self.report['cases']:
            checks = case['session_checks']
            self.assertEqual(checks['old_token'], '403 LOCAL_TOKEN_REQUIRED')
            self.assertEqual(checks['stale_commands'], '409 SESSION_CHANGED')
            self.assertEqual(checks['stale_lookup'], '409 SESSION_CHANGED')
            self.assertEqual(checks['conflicting_bodies'], '409 IDEMPOTENCY_CONFLICT')
            self.assertEqual(checks['replayed_commands'], 11)
            self.assertTrue(checks['instance_changed'] and checks['token_changed'])
            self.assertTrue(checks['first_results_preserved'] and checks['workspace_bytes_unchanged'])
        self.assertEqual(len(self.stable), 6)
        for offset in (0, 3):
            self.assertEqual(self.stable[offset], self.stable[offset + 1])
            self.assertEqual(self.stable[offset], self.stable[offset + 2])
            receipts = self.stable[offset]['receipts']
            writers = {row['receipt']['instance_id'] for row in receipts.values()}
            self.assertEqual(len(writers), 1)

    def test_all_corruptions_fail_closed_and_are_never_repaired(self):
        for case in self.report['cases']:
            checks = case['corruption_checks']
            self.assertEqual(set(checks), {'truncated', 'payload-checksum', 'resealed-f04-link'})
            self.assertEqual(checks['truncated']['failed_check'], 'strict_json')
            self.assertEqual(checks['payload-checksum']['failed_check'], 'payload_sha256')
            self.assertEqual(checks['resealed-f04-link']['failed_check'], 'service_restore')
            for result in checks.values():
                self.assertEqual(result['runtime'], 'WORKSPACE_UNREADABLE')
                self.assertEqual(result['both_command_routes'], 503)
                self.assertTrue(result['bytes_unchanged'] and result['child_reaped'])

    def test_resealed_corruption_passes_checksums_and_fold_but_breaks_f04_link(self):
        raw = rehearsal.corruptions(self.captures[0])['resealed-f04-link']
        doc = verify_document(json.loads(raw))
        journal = doc['payload']['journal']
        entries = overlay.restore(doc['overlay'], len(journal))
        with self.assertRaisesRegex(ValueError, 'default link'):
            recovery.validate_links(entries, journal)

    def test_sensitive_material_is_not_in_public_report(self):
        report = canonical_bytes(self.report)
        self.assertEqual(len(self.staged_keysets), 5)
        for raw, mode in self.staged_keysets:
            self.assertEqual(mode, 0o600)
            self.assertNotIn(raw, report)
            for entry in json.loads(raw)['keys']:
                self.assertNotIn(entry['key_hex'].encode(), report)
                self.assertNotIn(bytes.fromhex(entry['key_hex']), report)
        for instance, token in self.sessions:
            self.assertNotIn(instance.encode(), report)
            self.assertNotIn(token.encode(), report)
        for word in (b'"local_token":', b'key_hex', b'saved_by_instance', b'/tmp/', b'traceback', b'stderr'):
            self.assertNotIn(word, report.lower())
        self.assertEqual(self.report['cases'][0]['evidence']['signature_check'], 'NOT_BOUND')
        self.assertEqual(self.report['cases'][1]['evidence']['signature_check'],
                         'VERIFIED_DEV_ONLY_INTEGRITY')
        self.assertEqual(self.report['cases'][1]['checks']['insecure_keyset'],
                         'SIGNATURE_KEYSET_MODE; unchanged')

    def test_scope_labels_remain_honest(self):
        self.assertEqual(self.report['format'], rehearsal.FORMAT)
        self.assertEqual(self.report['label'], 'SIMULATED')
        self.assertEqual(self.report['workspace_kind'], 'LOCAL_FILE_WORKSPACE')
        self.assertFalse(self.report['funds_executed'])
        self.assertFalse(self.report['stage7_authenticated_export'])
        self.assertEqual(self.report['authentication'], 'NOT_BOUND')
        self.assertEqual(self.report['stage5_durable_transactions'], 'NOT_BOUND')
        limitations = ' '.join(self.report['limitations'])
        for phrase in ('backup service', 'live snapshot', 'automatic repair', 'cross-host fencing',
                       'disaster-recovery certification', 'not observed cash recovery'):
            self.assertIn(phrase, limitations)

    def test_evidence_comparison_catches_economic_drift(self):
        original = self.stable[0]
        mutations = [
            lambda x: x.update(state_digest='0' * 64),
            lambda x: x.update(overlay_state_digest='0' * 64),
            lambda x: x.update(content_digest='0' * 64),
            lambda x: x['receipts']['sim-offer']['receipt'].update(instance_id='wrong-writer'),
            lambda x: x['receipts']['sim-offer'].update(fingerprint='0' * 64),
            lambda x: x['statement']['categories'][0].update(total=0),
            lambda x: x['reconciliation']['checks'][0].update(status='RECON_MISMATCH'),
            lambda x: x['overlay_journal'][0].update(after_journal_index=99),
            lambda x: x['policy'].update(note_sha256='0' * 64),
        ]
        for index, mutate in enumerate(mutations):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.subTest(index=index), self.assertRaisesRegex(
                    rehearsal.RehearsalFailure, 'BUSINESS_EVIDENCE_DRIFT'):
                rehearsal.compare_evidence(original, changed)


class CliAndFailureTests(unittest.TestCase):
    def test_cli_runs_selected_cases_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as cwd:
            for case in rehearsal.CASES:
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/relocation_rehearsal.py'),
                                         '--case', case], cwd=cwd, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stderr, b'')
                report = json.loads(result.stdout)
                self.assertEqual([c['case'] for c in report['cases']], [case])
                self.assertEqual(report['cases'][0]['status'], 'PASSED')
            self.assertEqual(list(Path(cwd).iterdir()), [])

    def test_cli_rejects_live_workspace_and_unknown_case(self):
        for args in (['--workspace', '/never-open-this'], ['--case', 'real']):
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/relocation_rehearsal.py'),
                                     *args], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')

    def test_failures_are_sanitized_and_cleanup_always_runs(self):
        roots = []
        def fail(pyz, case, root):
            roots.extend((pyz.parent.parent, root))
            raise AssertionError('SIMULATED_SECRET_TOKEN raw subprocess diagnostics')
        with patch.object(rehearsal, 'run_case', side_effect=fail):
            result = rehearsal.rehearse()
        self.assertTrue(all(not path.exists() for path in roots))
        self.assertEqual([c['failure_code'] for c in result['cases']], ['REHEARSAL_FAILED'] * 2)
        self.assertNotIn('SIMULATED_SECRET_TOKEN', json.dumps(result))
        output = io.StringIO()
        with patch.object(rehearsal, 'rehearse', return_value=result), contextlib.redirect_stdout(output):
            self.assertEqual(rehearsal.main([]), 1)
        self.assertNotIn('raw subprocess', output.getvalue())
        with patch.object(rehearsal.build_release, 'build', side_effect=OSError('SECRET_BUILD_PATH')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(rehearsal.main([]), 1)
        self.assertEqual(json.loads(output.getvalue())['failure_code'], 'BUILD_FAILED')
        self.assertEqual(json.loads(output.getvalue())['workspace_kind'], 'LOCAL_FILE_WORKSPACE')
        self.assertFalse(json.loads(output.getvalue())['funds_executed'])
        self.assertNotIn('SECRET_BUILD_PATH', output.getvalue())

    def test_failure_after_writer_start_stops_and_reaps_it(self):
        servers = []
        start = rehearsal.release._start
        def observed(*args, **kwargs):
            server = start(*args, **kwargs)
            servers.append(server)
            return server
        with patch.object(rehearsal.release, '_start', side_effect=observed), \
             patch.object(rehearsal, 'populate', side_effect=RuntimeError('SECRET_RUNTIME_BODY')):
            report = rehearsal.rehearse(('unsigned',))
        self.assertEqual(report['cases'][0]['failure_code'], 'REHEARSAL_FAILED')
        self.assertEqual(len(servers), 1)
        self.assertIsNotNone(servers[0].proc.poll())
        self.assertTrue(all(not t.is_alive() for t in servers[0].threads))
        self.assertNotIn('SECRET_RUNTIME_BODY', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
