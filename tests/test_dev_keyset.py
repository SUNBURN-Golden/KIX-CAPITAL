import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from capital.export import ExportError, SignerConfigError, build_manifest, SECTION_IDS, SECTION_IDS_V3
from capital.keyset import DEV_KEYSET_NAME, DevKeysetSigner, build_signer, load_dev_keyset
from capital.verify import verify_manifest, verify_path


class DevKeysetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.signer = DevKeysetSigner(self.directory)
        self.path = self.directory / DEV_KEYSET_NAME
        self.keyset = load_dev_keyset(self.path)

    def save(self):
        self.path.write_text(json.dumps(self.keyset))
        self.path.chmod(0o600)

    def manifest(self, signer=None, v3=False):
        sections = {name: {} for name in (SECTION_IDS_V3 if v3 else SECTION_IDS)}
        if v3:
            from capital import overlay
            sections['overlay'] = overlay.export_section([], 0)
            sections['journal'] = {'entries': []}
        return build_manifest(sections=sections,
                              instance_id='SIMULATED', signer=signer or self.signer,
                              status='COMPLETE', incomplete_reasons=[])

    def check(self, manifest, reason=None):
        report = verify_manifest(manifest, keyset=self.keyset)
        self.assertEqual(report['reason'], reason)
        self.assertEqual(report['ok'], reason is None)
        self.assertFalse(report['stage7_authenticated_export'])
        self.assertEqual(report['authentication'], 'NOT_BOUND')
        return report

    def test_creation_restart_and_disclosure(self):
        before = self.path.read_bytes()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        other = DevKeysetSigner(self.directory)
        self.assertEqual(before, self.path.read_bytes())
        for v3 in (False, True):
            manifest = self.manifest(other, v3)
            self.check(manifest)
            self.assertEqual(manifest['external_key'], 'NOT_BOUND')
            self.assertFalse(manifest['stage7_authenticated_export'])
            self.assertEqual(manifest['signature']['kid'], 'kid-1')
            key = self.keyset['keys'][0]['key_hex']
            self.assertNotIn(key, json.dumps(manifest) + repr(other))
            self.assertNotIn(bytes.fromhex(key).decode('latin1'), repr(other))

    def test_rotation_and_identity_binding(self):
        old = self.manifest()
        entry = {**self.keyset['keys'][0], 'kid': 'kid-2'}
        self.keyset['keys'].append(entry)
        self.keyset['active_kid'] = 'kid-2'
        self.save()
        new = self.manifest(DevKeysetSigner(self.directory))
        self.check(old)
        self.check(new)
        forged = copy.deepcopy(old)
        forged['signature']['kid'] = 'kid-2'
        self.check(forged, 'SIGNATURE_MISMATCH')
        forged['signature']['kid'] = 'missing'
        self.check(forged, 'UNKNOWN_KID')
        self.keyset['keys'][0]['status'] = 'RETIRED'
        self.save()
        self.assertEqual(self.check(old, 'KEY_RETIRED')['signature'], 'KEY_RETIRED')
        self.check(new)
        manifest_path = self.directory / 'manifest.json'
        manifest_path.write_text(json.dumps(old))
        proc = subprocess.run([sys.executable, '-m', 'capital.verify', str(manifest_path),
                               '--keyset-file', str(self.path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(json.loads(proc.stdout)['reason'], 'KEY_RETIRED')
        self.assertNotIn(entry['key_hex'], proc.stdout)

    def test_secure_files_and_no_repair(self):
        original = self.path.read_bytes()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ExportError, 'SIGNATURE_KEYSET_MODE'):
            DevKeysetSigner(self.directory)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.path.chmod(0o600)
        link = self.directory / 'link'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ExportError, 'SIGNATURE_KEYSET_UNREADABLE'):
            load_dev_keyset(link)
        fifo = self.directory / 'fifo'
        os.mkfifo(fifo, 0o600)
        with self.assertRaisesRegex(ExportError, 'SIGNATURE_KEYSET_MODE'):
            load_dev_keyset(fifo)
        for raw in (b'{}', b'{"label":1,"label":2}', b'\xef\xbb\xbf{}', b'\xff', b' ' * 65537):
            with self.subTest(raw_length=len(raw)):
                self.path.write_bytes(raw)
                with self.assertRaisesRegex(ExportError, 'SIGNATURE_KEYSET_INVALID'):
                    DevKeysetSigner(self.directory)
                self.assertEqual(self.path.read_bytes(), raw)
        self.path.write_bytes(original)

    def test_strict_schema(self):
        variants = []
        for field, value in [('format', 'wrong'), ('label', 'SIMULATED'), ('active_kid', []), ('keys', [])]:
            variants.append({**self.keyset, field: value})
        for field, value in [('kid', []), ('kid', ''), ('alg', 'wrong'), ('status', []),
                             ('status', 'RETIRED'), ('key_hex', 'A' * 64), ('key_hex', None)]:
            variants.append({**self.keyset, 'keys': [{**self.keyset['keys'][0], field: value}]})
        variants.append({**self.keyset, 'keys': self.keyset['keys'] * 2})
        variants.append({**self.keyset, 'extra': 'forbidden'})
        for value in variants:
            self.path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ExportError, 'SIGNATURE_KEYSET_INVALID'):
                load_dev_keyset(self.path)

    def test_signature_shape_order_and_missing_keyset(self):
        manifest = self.manifest()
        self.assertEqual(verify_manifest(manifest)['reason'], 'SIGNATURE_KEYSET_REQUIRED')
        for field, value, reason in [('label', 'REAL', 'SIGNATURE_LABEL'), ('key_hex', 'secret', 'SIGNATURE_SHAPE'),
                                     ('alg', 'unknown', 'SIGNATURE_ALG'), ('kid', [], 'SIGNATURE_SHAPE')]:
            changed = copy.deepcopy(manifest)
            changed['signature'][field] = value
            self.check(changed, reason)
        manifest['sections']['journal']['body']['tampered'] = True
        self.assertEqual(verify_manifest(manifest, keyset_error='SIGNATURE_KEYSET_INVALID')['reason'],
                         'SECTION_HASH_MISMATCH:journal')
        path = self.directory / 'manifest.json'
        path.write_text(json.dumps(self.manifest()))
        self.assertEqual(verify_path(path, keyset_file=self.directory / 'missing')['reason'],
                         'SIGNATURE_KEYSET_UNREADABLE')

    def test_http_export_and_event_log_do_not_disclose_keys(self):
        import contextlib
        import io
        import threading
        from http.client import HTTPConnection
        from capital.server import make_server
        log = self.directory / 'events.jsonl'
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            server = make_server(0, workspace=self.directory, signer=self.signer, event_log=log)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', '/api/export/manifest')
                response = client.getresponse()
                raw = response.read()
                client.close()
                self.assertEqual(response.status, 200)
                self.check(json.loads(raw))
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        surfaces = raw + output.getvalue().encode() + (log.read_bytes() if log.exists() else b'')
        surfaces += (self.directory / 'workspace.json').read_bytes() if (self.directory / 'workspace.json').exists() else b''
        for entry in self.keyset['keys']:
            self.assertNotIn(entry['key_hex'].encode(), surfaces)
            self.assertNotIn(bytes.fromhex(entry['key_hex']), surfaces)

    def test_opt_in_and_cli_errors(self):
        self.assertEqual(build_signer(None).sign('a' * 64)['alg'], 'UNSIGNED')
        with self.assertRaises(SignerConfigError):
            build_signer(None, dev_keyset=True)
        with self.assertRaises(SignerConfigError):
            build_signer(self.directory, True, True)
        for module, args in [('capital.server', ['--dev-keyset']),
                             ('capital.server', ['--dev-keyset', '--dev-hmac']),
                             ('capital.verify', ['x', '--key-file', 'x', '--keyset-file', 'x']),
                             ('capital.verify', ['--workspace', 'x', '--keyset-file', 'x'])]:
            proc = subprocess.run([sys.executable, '-m', module, *args], capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn(self.keyset['keys'][0]['key_hex'], proc.stdout + proc.stderr)
