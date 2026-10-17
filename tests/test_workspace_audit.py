"""Offline workspace audit: staged read-only checks over workspace.json bytes.

The auditor never takes the flock, never writes, and never repairs. A live
server holding the lock is not disturbed. Reports stay SIMULATED/LOCAL_ONLY
and stage5_durable_transactions stays NOT_BOUND.
"""
import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from capital.audit import CHECK_ORDER, audit_workspace
from capital.recon import CHECK_IDS
from capital.server import make_server
from capital.store import FILE_NAME, FileWorkspace, WorkspaceError, canonical_bytes, section_checksum
from tests.test_overlay import seed, tick

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'scripts' / 'seed_demo.py'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'


def seed_workspace(directory):
    proc = subprocess.run(
        [sys.executable, os.fspath(SEED), '--workspace', os.fspath(directory)],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise AssertionError(f'seed_demo failed: {proc.stderr}')
    return directory


def snapshot(directory):
    root = Path(directory)
    return {path.name: path.read_bytes() for path in sorted(root.iterdir()) if path.is_file()}


class AuditCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / 'ws'

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self, directory=None):
        target = self.dir if directory is None else directory
        proc = subprocess.run(
            [sys.executable, '-m', 'capital.verify', '--workspace', os.fspath(target)],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(proc.stderr, '')
        return proc.returncode, json.loads(proc.stdout)

    def test_seeded_workspace_audits_all_matched(self):
        seed_workspace(self.dir)
        before = snapshot(self.dir)
        code, report = self.audit()
        self.assertEqual(code, 0)
        self.assertIs(report['ok'], True)
        self.assertIsNone(report['reason'])
        self.assertIsNone(report['failed_check'])
        self.assertEqual(report['checks'], {name: 'MATCHED' for name in CHECK_ORDER})
        self.assertEqual(report['recon_status'], 'MATCHED')
        self.assertEqual(
            [(row['id'], row['status']) for row in report['recon']['checks']],
            [(check_id, 'MATCHED') for check_id in CHECK_IDS])
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(report['state_digest'], golden['state_digest'])
        self.assertEqual(report['recon']['state_digest'], golden['state_digest'])
        self.assertEqual(report['mode'], 'OFFLINE_WORKSPACE_AUDIT')
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual(report['diagnostic'], 'LOCAL_ONLY')
        self.assertIs(report['lock_taken'], False)
        self.assertIs(report['writes'], False)
        self.assertIs(report['workspace_mutated'], False)
        self.assertIs(report['funds_executed'], False)
        self.assertEqual(report['repair'], 'NOT_IMPLEMENTED')
        self.assertEqual(report['stage5_durable_transactions'], 'NOT_BOUND')
        self.assertEqual(snapshot(self.dir), before)

    def test_audit_succeeds_while_the_file_lock_is_held(self):
        seed_workspace(self.dir)
        before = snapshot(self.dir)
        held = FileWorkspace.open(self.dir)
        try:
            code, report = self.audit()
            self.assertEqual(code, 0)
            self.assertTrue(report['ok'])
            self.assertIs(report['lock_taken'], False)
            in_process = audit_workspace(self.dir)
            self.assertTrue(in_process['ok'])
            # The audit did not disturb the lock: a second open still fails.
            with self.assertRaises(WorkspaceError) as caught:
                FileWorkspace.open(self.dir)
            self.assertEqual(caught.exception.code, 'WORKSPACE_LOCKED')
        finally:
            held.close()
        self.assertEqual(snapshot(self.dir), before)

    def test_audit_succeeds_while_a_live_server_holds_the_workspace(self):
        seed_workspace(self.dir)
        before = snapshot(self.dir)
        server = make_server(0, workspace=self.dir)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            client.request('GET', '/api/state')
            state = json.loads(client.getresponse().read().decode('utf-8'))
            client.close()
            self.assertEqual(state['workspace']['status'], 'ACTIVE')
            code, report = self.audit()
            self.assertEqual(code, 0)
            self.assertTrue(report['ok'])
            self.assertEqual(state['state_digest'], report['state_digest'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
        self.assertEqual(snapshot(self.dir), before)

    def test_tampered_file_fails_and_is_never_repaired(self):
        seed_workspace(self.dir)
        path = self.dir / FILE_NAME
        raw = bytearray(path.read_bytes())
        index = bytes(raw).index(b'"amount":') + len(b'"amount":')
        raw[index] = ord('3') if raw[index:index + 1] != b'3' else ord('4')
        path.write_bytes(bytes(raw))
        damaged = path.read_bytes()
        code, report = self.audit()
        self.assertEqual(code, 1)
        self.assertIs(report['ok'], False)
        self.assertEqual(report['reason'], 'WORKSPACE_UNREADABLE')
        self.assertEqual(report['failed_check'], 'payload_sha256')
        self.assertEqual(path.read_bytes(), damaged)
        self.assertEqual(sorted(snapshot(self.dir)), [FILE_NAME, 'workspace.json.lock'])

    def test_missing_empty_and_non_directory_fail_workspace_file(self):
        self.dir.mkdir(parents=True)
        code, report = self.audit()
        self.assertEqual((code, report['reason'], report['failed_check']),
                         (1, 'WORKSPACE_UNREADABLE', 'workspace_file'))
        self.assertEqual(report['checks']['strict_json'], 'NOT_CHECKED')
        absent = Path(self.tmp.name) / 'absent'
        code, report = self.audit(absent)
        self.assertEqual((code, report['failed_check']), (1, 'workspace_file'))
        file_path = Path(self.tmp.name) / 'a-file'
        file_path.write_bytes(b'{}')
        code, report = self.audit(file_path)
        self.assertEqual((code, report['failed_check']), (1, 'workspace_file'))

    def test_first_mismatch_stops_later_checks(self):
        seed_workspace(self.dir)
        path = self.dir / FILE_NAME
        document = json.loads(path.read_text())
        document['payload']['state_digest'] = '0' * 64
        document['payload_sha256'] = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
        path.write_bytes(canonical_bytes(document))
        code, report = self.audit()
        self.assertEqual(code, 1)
        self.assertEqual(report['failed_check'], 'state_digest')
        self.assertEqual(report['checks']['journal_replay'], 'MATCHED')
        self.assertEqual(report['checks']['recon'], 'NOT_CHECKED')
        self.assertIsNone(report['recon'])

    def test_intact_envelope_with_a_tampered_receipt_result_is_recon_mismatch(self):
        seed_workspace(self.dir)
        path = self.dir / FILE_NAME
        document = json.loads(path.read_text())
        stored = document['payload']['receipts']['op-closed-offer']
        stored['receipt']['result']['credit']['amount'] = 999
        document['payload_sha256'] = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
        path.write_bytes(canonical_bytes(document))
        damaged = path.read_bytes()
        code, report = self.audit()
        self.assertEqual((code, report['reason'], report['failed_check']),
                         (1, 'RECON_MISMATCH', 'recon'))
        self.assertEqual(report['checks']['receipt_journal_fingerprints'], 'MATCHED')
        self.assertEqual(report['recon_status'], 'RECON_MISMATCH')
        self.assertEqual(
            [row['status'] for row in report['recon']['checks']].count('RECON_MISMATCH'), 1)
        self.assertEqual(path.read_bytes(), damaged)


def seed_overlay_workspace(directory):
    port = seed.open_fresh(directory)
    try:
        tick(seed.build_service(port), 'audit-tick-1', 0, 60)
    finally:
        port.close()
    return directory


class AuditOverlayReconTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / 'ws'

    def tearDown(self):
        self.tmp.cleanup()

    def live(self, *paths):
        server = make_server(0, workspace=self.dir)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            bodies = []
            for path in paths:
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path)
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                bodies.append(json.loads(response.read().decode('utf-8')))
                client.close()
            return bodies
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)

    def assert_parity(self, audit_recon, live):
        self.assertEqual([c['id'] for c in audit_recon['checks']], [c['id'] for c in live['checks']])
        self.assertEqual([c['status'] for c in audit_recon['checks']], [c['status'] for c in live['checks']])
        for key in ('status', 'scope', 'checks', 'entry_count', 'state_digest'):
            if key in live:
                self.assertEqual(audit_recon[key], live[key], key)

    def test_non_empty_overlay_recon_matches_live_get(self):
        seed_overlay_workspace(self.dir)
        before = snapshot(self.dir)
        live, quote = self.live('/api/reconciliation', '/api/overlay')
        report = audit_workspace(self.dir)
        self.assertTrue(report['ok'])
        recon = report['recon']
        self.assertEqual(recon['status'], 'MATCHED')
        ids = [c['id'] for c in recon['checks']]
        self.assertEqual(ids, list(CHECK_IDS) + ['overlay_fold_digest_equals_persisted'])
        self.assertEqual(ids, [c['id'] for c in live['checks']])
        self.assertEqual(recon['scope']['overlay_state_digest'], quote['overlay_state_digest'])
        self.assert_parity(recon, live)
        self.assertEqual(snapshot(self.dir), before)

    def test_empty_overlay_recon_is_unchanged_and_matches_live_get(self):
        seed_workspace(self.dir)
        (live,) = self.live('/api/reconciliation')
        recon = audit_workspace(self.dir)['recon']
        self.assertEqual([c['id'] for c in recon['checks']], list(CHECK_IDS))
        self.assertNotIn('overlay_state_digest', recon['scope'])
        self.assert_parity(recon, live)

    def test_stale_overlay_digest_fails_at_service_restore_not_recon(self):
        seed_overlay_workspace(self.dir)
        path = self.dir / FILE_NAME
        document = json.loads(path.read_text(encoding='utf-8'))
        document['overlay']['overlay_state']['digest'] = '0' * 64
        section = document['overlay']
        section['section_sha256'] = section_checksum(section)
        path.write_bytes(canonical_bytes(document))
        report = audit_workspace(self.dir)
        self.assertFalse(report['ok'])
        self.assertEqual(report['failed_check'], 'service_restore')
        self.assertIsNone(report['recon'])


class AuditArgumentTests(unittest.TestCase):
    def cli(self, *argv):
        return subprocess.run(
            [sys.executable, '-m', 'capital.verify', *argv],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)

    def test_workspace_and_manifest_arguments_are_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'workspace.json').write_bytes(b'{}')
            proc = self.cli('some-file.json', '--workspace', os.fspath(directory))
            self.assertEqual(proc.returncode, 2)
            proc = self.cli('--workspace', os.fspath(directory), '--key-file', 'k')
            self.assertEqual(proc.returncode, 2)
            proc = self.cli()
            self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
