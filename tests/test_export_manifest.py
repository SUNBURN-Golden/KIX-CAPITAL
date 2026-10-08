import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.auth import route_permission
from capital.export import (
    FORMAT, PART_TAGS, SECTION_IDS, DevHmacSigner, ExportError, UnsignedSigner,
    build_signer, content_digest, load_dev_key, manifest_status, sha256_hex,
)
from capital.server import make_server
from capital.service import CapitalService, digest
from capital.store import StoragePort, canonical_bytes, envelope, verify_document
from capital.verify import main as verify_main
from capital.verify import verify_path

ROOT = Path(__file__).resolve().parents[1]
V1_KEYS = {
    'format', 'instance_id', 'provenance', 'source', 'fixtures_digest', 'journal',
    'state_digest', 'replay_matched', 'durable', 'funds_executed', 'note',
}
FLIP_REASONS = [f'SECTION_HASH_MISMATCH:{name}' for name in SECTION_IDS] + [
    'CONTENT_DIGEST_MISMATCH', 'SIGNATURE_MISMATCH',
]


def command(service, op, case, operation_id, **args):
    return service.execute({
        'instance_id': service.instance_id, 'operation_id': operation_id,
        'op': op, 'advance_id': case, 'args': args,
    })


def frozen(service):
    return (
        json.dumps(service.receipts, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode(),
        service.machine.state_digest(),
        len(service.receipts),
        service.machine.canonical_state(),
    )


def dump_manifest(manifest):
    return json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def contains_secret(blob, secret):
    if isinstance(blob, str):
        blob = blob.encode()
    return secret in blob or secret.hex().encode() in blob


class HoldStorage(StoragePort):
    durable_label = False

    def __init__(self):
        self.saves = 0
        self.document = None

    def load(self):
        if self.document is None:
            return None
        return verify_document(copy.deepcopy(self.document))

    def save(self, payload):
        self.saves += 1
        self.document = envelope(self.writer_instance, payload)


class ManifestTests(unittest.TestCase):
    def test_clean_manifest_hashes_sections_and_leaves_cuts_unbound(self):
        service = CapitalService()
        command(service, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=60_000)
        before = frozen(service)
        v1 = service.export()
        manifest = service.export_manifest()
        self.assertEqual(frozen(service), before)
        self.assertEqual(set(v1), V1_KEYS)
        self.assertEqual(v1['format'], 'KIX_CAPITAL_SIMULATION_V1')
        self.assertTrue(v1['replay_matched'])
        self.assertNotIn('sections', v1)
        self.assertNotIn('signature', v1)
        self.assertEqual(manifest['format'], FORMAT)
        self.assertEqual(manifest['label'], 'SIMULATED')
        self.assertEqual(manifest['diagnostic'], 'READ_ONLY')
        self.assertEqual(manifest['status'], 'COMPLETE')
        self.assertEqual(manifest['incomplete_reasons'], [])
        self.assertEqual(manifest['instance_id'], service.instance_id)
        self.assertIsNone(manifest['cursor'])
        self.assertIsNone(manifest['watermark'])
        self.assertIsNone(manifest['source_cut'])
        self.assertIsNone(manifest['timestamps'])
        gaps = {row['id']: row for row in manifest['not_bound']}
        for gap_id in ('cursor', 'watermark', 'source_cut', 'external_key', 'retention_policy', 'authentication'):
            self.assertEqual(gaps[gap_id]['status'], 'NOT_BOUND')
            self.assertIsNone(gaps[gap_id]['value'])
        self.assertFalse(manifest['stage7_authenticated_export'])
        self.assertEqual(manifest['authentication'], 'NOT_BOUND')
        self.assertEqual(manifest['external_key'], 'NOT_BOUND')
        self.assertEqual(manifest['retention_policy'], 'NOT_BOUND')
        self.assertEqual(manifest['import_endpoint'], 'NOT_PROVIDED')
        self.assertEqual(manifest['resume_endpoint'], 'NOT_PROVIDED')
        self.assertFalse(manifest['funds_executed'])
        self.assertIn('Not stage7 authenticated export', manifest['note'])
        self.assertIn('integrity only, not authentication', manifest['note'])
        self.assertIn('SignaturePort', manifest['note'])
        self.assertEqual(list(manifest['sections']), list(SECTION_IDS))
        for name in SECTION_IDS:
            section = manifest['sections'][name]
            self.assertEqual(set(section), {'sha256', 'body'})
            self.assertEqual(section['sha256'], sha256_hex(section['body']))
            self.assertEqual(section['body']['part_tag'], PART_TAGS[name])
        self.assertEqual(manifest['content_digest'], content_digest(manifest))
        self.assertEqual(manifest['signature']['status'], 'NOT_BOUND')
        self.assertEqual(manifest['signature']['alg'], 'UNSIGNED')
        self.assertIsNone(manifest['signature']['value'])
        self.assertEqual(manifest['signature']['port'], 'SignaturePort')
        self.assertNotIn('key', manifest['signature'])
        journal = copy.deepcopy(manifest['sections']['journal']['body'])
        journal.pop('part_tag')
        self.assertEqual(journal['entries'], v1['journal'])
        self.assertEqual(journal['label'], 'SIMULATED')
        projection = copy.deepcopy(manifest['sections']['projection']['body'])
        projection.pop('part_tag')
        self.assertEqual(projection, service.projection(None))
        self.assertEqual(projection['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        reconciliation = copy.deepcopy(manifest['sections']['reconciliation']['body'])
        reconciliation.pop('part_tag')
        self.assertEqual(reconciliation['status'], 'MATCHED')
        fixtures = copy.deepcopy(manifest['sections']['fixtures']['body'])
        fixtures.pop('part_tag')
        self.assertEqual(fixtures['label'], 'READ_ONLY_FIXTURE')
        self.assertEqual(fixtures['fixtures_digest'], digest(service.fixtures.rows))
        source = copy.deepcopy(manifest['sections']['source_pin']['body'])
        source.pop('part_tag')
        self.assertEqual(source['label'], 'READ_ONLY_FIXTURE')
        self.assertTrue(source['integrity']['all_matched'])
        self.assertEqual(source['commit'], service.source['commit'])

    def test_content_digest_excludes_instance_id_and_timestamps(self):
        manifest = CapitalService().export_manifest()
        mutated = copy.deepcopy(manifest)
        mutated['instance_id'] = 'other-instance'
        mutated['timestamps'] = '2020-01-01T00:00:00Z'
        mutated['created_at'] = '2020-01-01T00:00:00Z'
        mutated['sections']['receipts']['body']['saved_at'] = '1999-01-01T00:00:00Z'
        self._rewrite_instance_ids(mutated)
        self.assertEqual(content_digest(mutated), manifest['content_digest'])
        changed = copy.deepcopy(manifest)
        changed['sections']['journal']['body']['part_tag'] = 'journalparu'
        self.assertNotEqual(content_digest(changed), manifest['content_digest'])

    def test_fresh_instances_share_content_digest(self):
        left = CapitalService()
        right = CapitalService()
        self.assertNotEqual(left.instance_id, right.instance_id)
        left_manifest = left.export_manifest()
        right_manifest = right.export_manifest()
        self.assertNotEqual(
            left_manifest['sections']['projection']['sha256'],
            right_manifest['sections']['projection']['sha256'])
        self.assertEqual(left_manifest['content_digest'], right_manifest['content_digest'])
        self.assertEqual(left_manifest['sections']['projection']['sha256'], sha256_hex(left_manifest['sections']['projection']['body']))

    def test_status_is_incomplete_unless_reconciliation_and_workspace_are_clean(self):
        self.assertEqual(manifest_status('MATCHED', 'ACTIVE'), ('COMPLETE', []))
        status, reasons = manifest_status('RECON_MISMATCH', 'ACTIVE')
        self.assertEqual(status, 'INCOMPLETE')
        self.assertEqual(reasons, ['RECONCILIATION_NOT_CLEAN'])
        status, reasons = manifest_status('MATCHED', 'WORKSPACE_UNREADABLE')
        self.assertEqual(status, 'INCOMPLETE')
        self.assertIn('WORKSPACE_NOT_ACTIVE:WORKSPACE_UNREADABLE', reasons)
        self.assertNotIn('COMPLETE', (status,))
        status, reasons = manifest_status('WORKSPACE_UNREADABLE', 'WORKSPACE_LOCKED')
        self.assertEqual(status, 'INCOMPLETE')
        self.assertGreaterEqual(len(reasons), 2)

    def test_unreadable_or_dirty_workspace_is_not_silently_clean(self):
        original = CapitalService()
        command(original, 'offer', 'sim-a', 'op-1', fixture_id='sim-committed', amount=60_000)
        payload = copy.deepcopy(original.storage.load()['payload'])
        del payload['receipts']['op-1']
        storage = HoldStorage()
        storage.document = envelope('tamper-writer', payload)
        dirty = CapitalService(storage)
        self.assertEqual(dirty.workspace_status, 'WORKSPACE_UNREADABLE')
        before = frozen(dirty)
        manifest = dirty.export_manifest()
        self.assertEqual(storage.saves, 0)
        self.assertEqual(frozen(dirty), before)
        self.assertEqual(manifest['status'], 'INCOMPLETE')
        self.assertIn('RECONCILIATION_NOT_CLEAN', manifest['incomplete_reasons'])
        self.assertIn('WORKSPACE_NOT_ACTIVE:WORKSPACE_UNREADABLE', manifest['incomplete_reasons'])
        self.assertNotEqual(manifest['status'], 'COMPLETE')
        recon = copy.deepcopy(manifest['sections']['reconciliation']['body'])
        recon.pop('part_tag')
        self.assertEqual(recon['status'], 'RECON_MISMATCH')
        self.assertEqual(verify_path_bytes(manifest)['ok'], True)
        self.assertEqual(verify_path_bytes(manifest)['signature'], 'NOT_BOUND')

        with tempfile.TemporaryDirectory() as tmp:
            from capital.store import FileWorkspace
            directory = Path(tmp)
            port = FileWorkspace.open(directory)
            try:
                writer = CapitalService(port)
                command(writer, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
            finally:
                port.close()
            path = directory / 'workspace.json'
            document = json.loads(path.read_text())
            document['payload_sha256'] = '0' * 64
            path.write_bytes(canonical_bytes(document))
            port = FileWorkspace.open(directory)
            try:
                unreadable = CapitalService(port)
                manifest = unreadable.export_manifest()
            finally:
                port.close()
        self.assertEqual(unreadable.workspace_status, 'WORKSPACE_UNREADABLE')
        self.assertEqual(manifest['status'], 'INCOMPLETE')
        self.assertIn('WORKSPACE_NOT_ACTIVE:WORKSPACE_UNREADABLE', manifest['incomplete_reasons'])
        self.assertIn('RECONCILIATION_NOT_CLEAN', manifest['incomplete_reasons'])
        self.assertNotEqual(manifest['status'], 'COMPLETE')

    def test_manifest_read_does_not_save(self):
        storage = HoldStorage()
        service = CapitalService(storage)
        service.export_manifest()
        self.assertEqual(storage.saves, 0)

    def test_dev_hmac_key_is_mode_0600_and_stays_out_of_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            signer = DevHmacSigner(directory)
            key_path = directory / 'export-dev.key'
            self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)
            key = key_path.read_bytes()[len(b'DEV_ONLY\n'):]
            self.assertEqual(len(key), 32)
            self.assertTrue(key_path.read_bytes().startswith(b'DEV_ONLY\n'))
            self.assertFalse(contains_secret(repr(signer), key))
            again = DevHmacSigner(directory)
            service = CapitalService(signer=signer)
            manifest = service.export_manifest()
            repeat = service.export_manifest()
            self.assertEqual(manifest['content_digest'], repeat['content_digest'])
            self.assertEqual(manifest['signature']['value'], repeat['signature']['value'])
            self.assertEqual(
                signer.sign(manifest['content_digest'])['value'],
                again.sign(manifest['content_digest'])['value'],
            )
            self.assertEqual(manifest['signature']['label'], 'DEV_ONLY')
            self.assertEqual(manifest['signature']['status'], 'DEV_ONLY')
            self.assertEqual(manifest['signature']['purpose'], 'INTEGRITY_ONLY')
            self.assertEqual(manifest['signature']['authentication'], 'NOT_BOUND')
            self.assertEqual(manifest['signature']['alg'], 'DEV_HMAC_SHA256')
            self.assertNotIn('key', manifest['signature'])
            blob = dump_manifest(manifest)
            self.assertFalse(contains_secret(blob, key))
            report = verify_path(self._write(directory, manifest), key_path)
            self.assertTrue(report['ok'])
            self.assertIsNone(report['reason'])
            self.assertEqual(report['signature'], 'VERIFIED_DEV_ONLY_INTEGRITY')
            self.assertEqual(report['authentication'], 'NOT_BOUND')
            self.assertFalse(report['stage7_authenticated_export'])
            os.chmod(key_path, 0o644)
            refused = verify_path(self._write(directory, manifest), key_path)
            self.assertFalse(refused['ok'])
            self.assertEqual(refused['reason'], 'SIGNATURE_KEY_MODE')
            self.assertFalse(contains_secret(json.dumps(refused), key))
            with self.assertRaises(ExportError) as caught:
                load_dev_key(key_path, create=False)
            self.assertEqual(caught.exception.code, 'SIGNATURE_KEY_MODE')
            self.assertNotIn(key.hex(), str(caught.exception))

    def test_each_one_byte_flip_fails_with_its_own_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            signer = DevHmacSigner(directory)
            key = (directory / 'export-dev.key').read_bytes()[len(b'DEV_ONLY\n'):]
            manifest = CapitalService(signer=signer).export_manifest()
            raw = dump_manifest(manifest)
            path = directory / 'manifest.json'
            path.write_bytes(raw)
            intact = self._cli(path, directory / 'export-dev.key')
            self.assertEqual(intact.returncode, 0, intact.stderr)
            self.assertTrue(json.loads(intact.stdout)['ok'])
            self.assertFalse(contains_secret(intact.stdout + intact.stderr, key))
            seen = []
            for name in SECTION_IDS:
                token = f'"part_tag":"{PART_TAGS[name]}"'.encode()
                replacement = token.replace(b't"', b'u"', 1)
                self.assertEqual(len(token), len(replacement))
                flipped = self._flip_once(raw, token, replacement)
                reason = self._reason(directory, flipped, key)
                seen.append(reason)
                self.assertEqual(reason, f'SECTION_HASH_MISMATCH:{name}')
            digest_flip = self._flip_hex_field(raw, b'"content_digest":"')
            seen.append(self._reason(directory, digest_flip, key))
            self.assertEqual(seen[-1], 'CONTENT_DIGEST_MISMATCH')
            signature_flip = self._flip_signature(raw)
            seen.append(self._reason(directory, signature_flip, key))
            self.assertEqual(seen[-1], 'SIGNATURE_MISMATCH')
            self.assertEqual(seen, FLIP_REASONS)
            self.assertEqual(len(set(seen)), len(FLIP_REASONS))

    def test_unsigned_verifier_reports_not_bound_and_hmac_needs_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            unsigned = CapitalService().export_manifest()
            path = self._write(directory, unsigned)
            report = verify_path(path, None)
            self.assertTrue(report['ok'])
            self.assertEqual(report['signature'], 'NOT_BOUND')
            for name in SECTION_IDS:
                self.assertEqual(report['sections'][name], 'MATCHED')
            cli = self._cli(path, None)
            self.assertEqual(cli.returncode, 0)
            self.assertEqual(json.loads(cli.stdout)['signature'], 'NOT_BOUND')
            signer = DevHmacSigner(directory / 'keys')
            signed = CapitalService(signer=signer).export_manifest()
            signed_path = self._write(directory, signed)
            missing = verify_path(signed_path, None)
            self.assertEqual(missing['reason'], 'SIGNATURE_KEY_REQUIRED')
            self.assertEqual(missing['content_digest'], 'MATCHED')
            other = DevHmacSigner(directory / 'other')
            wrong = verify_path(signed_path, other.path)
            self.assertEqual(wrong['reason'], 'SIGNATURE_MISMATCH')
            self.assertEqual(wrong['authentication'], 'NOT_BOUND')

    def test_holder_of_the_dev_key_can_resign_and_it_is_still_not_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            signer = DevHmacSigner(tmp)
            manifest = CapitalService(signer=signer).export_manifest()
            manifest['sections']['journal']['body']['entries'].append({'op': 'tamper'})
            body = manifest['sections']['journal']['body']
            manifest['sections']['journal']['sha256'] = sha256_hex(body)
            manifest.pop('content_digest')
            manifest.pop('signature')
            manifest['content_digest'] = content_digest(manifest)
            manifest['signature'] = signer.sign(manifest['content_digest'])
            path = Path(tmp) / 'resigned.json'
            path.write_bytes(dump_manifest(manifest))
            report = verify_path(path, signer.path)
            self.assertTrue(report['ok'])
            self.assertEqual(report['signature'], 'VERIFIED_DEV_ONLY_INTEGRITY')
            self.assertEqual(report['authentication'], 'NOT_BOUND')
            self.assertFalse(report['stage7_authenticated_export'])

    def test_http_auditor_may_export_the_manifest_and_observer_may_not(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def request(method, path, body=None, headers=None):
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request(method, path, body=body, headers=headers or {})
                response = client.getresponse()
                raw, status = response.read(), response.status
                client.close()
                return status, raw

            status, raw = request('GET', '/api/state')
            self.assertEqual(status, 200)
            organizer = json.loads(raw)['local_token']
            before = server.service.snapshot()

            def session(role):
                status, raw = request(
                    'POST', '/api/session', json.dumps({'role': role}),
                    {'Content-Type': 'application/json', 'X-Capital-Token': organizer},
                )
                self.assertEqual(status, 200, raw)
                return json.loads(raw)['local_token']

            auditor = session('auditor')
            observer = session('observer')
            status, raw = request('GET', '/api/export/manifest', headers={'X-Capital-Token': auditor})
            self.assertEqual(status, 200, raw[:200])
            body = json.loads(raw)
            self.assertEqual(body['format'], FORMAT)
            self.assertEqual(body['signature']['status'], 'NOT_BOUND')
            status, raw = request('GET', '/api/export/manifest', headers={'X-Capital-Token': observer})
            denied = json.loads(raw)
            self.assertEqual(status, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['role'], 'observer')
            self.assertEqual(denied['permission'], 'export:read')
            status, raw = request('GET', '/api/export', headers={'X-Capital-Token': auditor})
            exported = json.loads(raw)
            self.assertEqual(status, 200)
            self.assertEqual(exported['format'], 'KIX_CAPITAL_SIMULATION_V1')
            self.assertEqual(set(exported), V1_KEYS)
            status, raw = request('GET', '/api/import')
            self.assertEqual(json.loads(raw)['error'], 'NOT_FOUND')
            status, raw = request(
                'POST', '/api/export/manifest', b'{}',
                {'Content-Type': 'application/json', 'X-Capital-Token': organizer},
            )
            self.assertEqual(json.loads(raw)['error'], 'NOT_FOUND')
            after = server.service.snapshot()
            self.assertEqual(after['operation_count'], before['operation_count'])
            self.assertEqual(after['state_digest'], before['state_digest'])
            self.assertEqual(route_permission('/api/export/manifest'), 'export:read')
            self.assertIsNone(route_permission('/api/export/manifest/extra'))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_dev_hmac_http_response_and_workspace_file_omit_the_key(self):
        from capital.store import FileWorkspace
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            signer = DevHmacSigner(directory)
            key = signer.path.read_bytes()[len(b'DEV_ONLY\n'):]
            port = FileWorkspace.open(directory)
            try:
                service = CapitalService(port, signer=signer)
                command(service, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
                saved = service.export_manifest()
                self.assertFalse(contains_secret(dump_manifest(saved), key))
            finally:
                port.close()
            self.assertFalse(contains_secret((directory / 'workspace.json').read_bytes(), key))
            server = make_server(0, workspace=directory, signer=signer)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', '/api/export/manifest')
                response = client.getresponse()
                raw = response.read()
                client.close()
                self.assertEqual(response.status, 200)
                self.assertFalse(contains_secret(raw, key))
                body = json.loads(raw)
                self.assertEqual(body['signature']['label'], 'DEV_ONLY')
                self.assertEqual(body['authentication'], 'NOT_BOUND')
                self.assertEqual(body['status'], 'COMPLETE')
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)

    def test_dev_hmac_flag_requires_a_workspace_and_does_not_listen(self):
        proc = subprocess.run(
            [sys.executable, '-m', 'capital.server', '--dev-hmac', '--port', '9'],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('DEV_HMAC_REQUIRES_WORKSPACE', proc.stderr)
        self.assertNotIn('KIX Capital simulation', proc.stdout)
        with self.assertRaises(Exception) as caught:
            build_signer(None, True)
        self.assertEqual(caught.exception.code, 'DEV_HMAC_REQUIRES_WORKSPACE')
        self.assertIsInstance(build_signer(None, False), UnsignedSigner)

    def test_readiness_says_this_is_not_stage7(self):
        notes = CapitalService().readiness()['requirement_notes']['CAP-15']
        self.assertIn('not stage7 authenticated export', notes)
        self.assertIn('SignaturePort', notes)
        self.assertIn('no external key', notes)
        group = next(row for row in CapitalService().readiness()['groups'] if row['id'] == 'durable-finance')
        self.assertEqual(group['status'], 'UPSTREAM_REQUIRED')
        self.assertIn('stage7 인증 아님', group['available'][-1])
        self.assertIn('외부 키', group['claim'])
        self.assertIn('stage7 source cut·watermark·인증 export·부분 자료 거절', group['blockers'])

    def _rewrite_instance_ids(self, value):
        if type(value) is dict:
            if 'instance_id' in value and type(value['instance_id']) is str:
                value['instance_id'] = 'changed-instance'
            for child in value.values():
                self._rewrite_instance_ids(child)
        elif type(value) is list:
            for child in value:
                self._rewrite_instance_ids(child)

    def _write(self, directory, manifest):
        path = Path(directory) / 'manifest.json'
        path.write_bytes(dump_manifest(manifest))
        return path

    def _flip_once(self, raw, token, replacement):
        self.assertEqual(raw.count(token), 1, token)
        flipped = raw.replace(token, replacement, 1)
        self.assertEqual(len(flipped), len(raw))
        json.loads(flipped)
        return flipped

    def _flip_hex_field(self, raw, marker):
        self.assertEqual(raw.count(marker), 1, marker)
        index = raw.index(marker) + len(marker)
        first = raw[index:index + 1]
        replacement = b'0' if first != b'0' else b'1'
        flipped = raw[:index] + replacement + raw[index + 1:]
        json.loads(flipped)
        return flipped

    def _flip_signature(self, raw):
        alg = raw.index(b'"alg":"DEV_HMAC_SHA256"')
        marker = b'"value":"'
        index = raw.index(marker, alg) + len(marker)
        first = raw[index:index + 1]
        replacement = b'a' if first != b'a' else b'b'
        flipped = raw[:index] + replacement + raw[index + 1:]
        self.assertEqual(len(flipped), len(raw))
        json.loads(flipped)
        return flipped

    def _reason(self, directory, raw, key):
        path = directory / 'flipped.json'
        path.write_bytes(raw)
        proc = self._cli(path, directory / 'export-dev.key')
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse(contains_secret(proc.stdout + proc.stderr, key))
        report = json.loads(proc.stdout)
        self.assertFalse(report['ok'])
        self.assertEqual(report['authentication'], 'NOT_BOUND')
        return report['reason']

    def _cli(self, path, key_file):
        command = [sys.executable, '-m', 'capital.verify', os.fspath(path)]
        if key_file is not None:
            command.extend(['--key-file', os.fspath(key_file)])
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)


def verify_path_bytes(manifest):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'manifest.json'
        path.write_bytes(dump_manifest(manifest))
        return verify_path(path)


class VerifyModuleTests(unittest.TestCase):
    def test_main_returns_zero_for_an_unsigned_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manifest.json'
            path.write_bytes(dump_manifest(CapitalService().export_manifest()))
            self.assertEqual(verify_main([os.fspath(path)]), 0)


if __name__ == '__main__':
    unittest.main()
