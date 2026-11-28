"""SIMULATED local integrity evidence; no authentication or funds execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import signature_inventory as inventory
from capital.export import SECTION_IDS_V3, UnsignedSigner, build_manifest
from capital.keyset import load_dev_keyset
from capital.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests/vectors'
MANIFESTS = VECTORS / 'manifest'


class SignatureInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.keyset = self.directory / 'snapshot.json'
        self.copy_keyset()
        self.active = MANIFESTS / 'dev-keyset-kid-1.json'

    def copy_keyset(self, name='dev-keyset-active.json'):
        shutil.copyfile(VECTORS / name, self.keyset)
        self.keyset.chmod(0o600)

    def audit(self, paths=None):
        return inventory.inventory_manifests(paths or [self.active], keyset_file=self.keyset)

    def save(self, raw, name='input.json'):
        path = self.directory / name
        path.write_bytes(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        return path

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'capital.signature_inventory', *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)

    def test_ordered_outcome_matrix_and_exact_verifier_reports(self):
        names = ['dev-keyset-kid-1.json', 'dev-keyset-kid-2.json', 'unknown-kid.json',
                 'unsigned.json', 'dev-hmac.json', 'section-journal.json',
                 'content-digest.json', 'signature.json']
        paths = [MANIFESTS / name for name in names]
        result = self.audit(paths)
        expected = [None, None, 'UNKNOWN_KID', None, 'SIGNATURE_KEY_REQUIRED',
                    'SECTION_HASH_MISMATCH:journal', 'CONTENT_DIGEST_MISMATCH',
                    'SIGNATURE_KEY_REQUIRED']
        snapshot = load_dev_keyset(self.keyset)
        for index, (row, path, reason) in enumerate(zip(result['files'], paths, expected), 1):
            document = json.loads(path.read_bytes())
            self.assertEqual(row['index'], index)
            self.assertEqual(row['path'], str(path))
            self.assertEqual(row['content_digest'], document['content_digest'])
            self.assertEqual(row['kid'], document['signature'].get('kid'))
            self.assertIsNone(row['input_error'])
            self.assertEqual(row['verification'], verify_manifest(document, keyset=snapshot))
            self.assertEqual(row['verification']['reason'], reason)
            self.assertEqual(row['verification']['authentication'], 'NOT_BOUND')
            self.assertFalse(row['verification']['stage7_authenticated_export'])
        self.assertEqual(result['summary'], dict(requested=8, verified=8, failed=5,
                         skipped=0, complete=True, all_valid=False, all_dev_signatures_verified=False))
        self.assertEqual(result['authentication'], 'NOT_BOUND')
        self.assertEqual(result['label'], 'DEV_ONLY')
        self.assertFalse(result['funds_executed'])
        self.assertFalse(result['stage7_authenticated_export'])

    def test_retirement_and_active_key(self):
        self.copy_keyset('dev-keyset-retired.json')
        result = self.audit([self.active, MANIFESTS / 'dev-keyset-kid-2.json'])
        self.assertEqual([r['verification']['reason'] for r in result['files']], ['KEY_RETIRED', None])
        self.assertFalse(result['summary']['all_valid'])

    def test_unsigned_success_is_not_signature_verification(self):
        result = self.audit([MANIFESTS / 'unsigned.json'])
        self.assertTrue(result['summary']['all_valid'])
        self.assertEqual(result['files'][0]['verification']['signature'], 'NOT_BOUND')
        self.assertFalse(result['summary']['all_dev_signatures_verified'])
        self.assertTrue(self.audit()['summary']['all_dev_signatures_verified'])

    def test_v3_and_v2_are_supported(self):
        from capital import overlay
        sections = {name: {} for name in SECTION_IDS_V3}
        sections['overlay'] = overlay.export_section([], 0)
        sections['journal'] = {'entries': []}
        document = build_manifest(sections=sections, instance_id='SIMULATED',
                                  signer=UnsignedSigner(), status='COMPLETE', incomplete_reasons=[])
        result = self.audit([self.active, self.save(document)])
        self.assertTrue(result['summary']['all_valid'])
        self.assertEqual([r['verification']['format'] for r in result['files']],
                         ['KIX_CAPITAL_EXPORT_MANIFEST_V2', 'KIX_CAPITAL_EXPORT_MANIFEST_V3'])

    def test_missing_keyset_and_corruption_precedence(self):
        self.keyset.unlink()
        result = self.audit([self.active, MANIFESTS / 'unsigned.json',
                             MANIFESTS / 'section-journal.json', MANIFESTS / 'content-digest.json'])
        self.assertEqual(result['keyset_error'], 'SIGNATURE_KEYSET_UNREADABLE')
        self.assertEqual([r['verification']['reason'] for r in result['files']],
                         ['SIGNATURE_KEYSET_UNREADABLE', 'SIGNATURE_KEYSET_UNREADABLE',
                          'SECTION_HASH_MISMATCH:journal', 'CONTENT_DIGEST_MISMATCH'])
        self.assertFalse(result['summary']['all_valid'])
        self.assertFalse(self.keyset.exists())

    def test_snapshot_loaded_once_despite_replace_retire_or_delete(self):
        original = inventory.verify_manifest
        for change in ('replace', 'retire', 'delete'):
            with self.subTest(change=change):
                self.copy_keyset()
                calls = []

                def verify(document, **kwargs):
                    calls.append(kwargs['keyset'])
                    if len(calls) == 1:
                        if change == 'delete':
                            self.keyset.unlink()
                        elif change == 'retire':
                            self.copy_keyset('dev-keyset-retired.json')
                        else:
                            replacement = json.loads(self.keyset.read_bytes())
                            replacement['keys'][0]['key_hex'] = '03' * 32
                            self.save(replacement, 'replacement.json').replace(self.keyset)
                            self.keyset.chmod(0o600)
                    return original(document, **kwargs)

                with patch.object(inventory, 'load_dev_keyset', wraps=load_dev_keyset) as loader:
                    with patch.object(inventory, 'verify_manifest', side_effect=verify):
                        result = self.audit([self.active, self.active])
                loader.assert_called_once_with(self.keyset, create=False)
                self.assertIs(calls[0], calls[1])
                self.assertTrue(result['summary']['all_dev_signatures_verified'])
                reason = self.audit()['files'][0]['verification']['reason']
                self.assertEqual(reason, {'replace': 'SIGNATURE_MISMATCH', 'retire': 'KEY_RETIRED',
                                          'delete': 'SIGNATURE_KEYSET_UNREADABLE'}[change])

    def test_failed_snapshot_is_also_loaded_once(self):
        self.keyset.unlink()
        original = inventory.verify_manifest

        def verify(document, **kwargs):
            self.copy_keyset()
            return original(document, **kwargs)

        with patch.object(inventory, 'load_dev_keyset', wraps=load_dev_keyset) as loader:
            with patch.object(inventory, 'verify_manifest', side_effect=verify):
                result = self.audit([self.active, self.active])
        self.assertEqual(loader.call_count, 1)
        self.assertEqual([r['verification']['reason'] for r in result['files']],
                         ['SIGNATURE_KEYSET_UNREADABLE'] * 2)

    def test_count_limits_precede_any_open_and_duplicates_count(self):
        with patch.object(inventory, 'load_dev_keyset') as loader:
            with patch.object(inventory, '_open_regular') as opener:
                for paths in ([], [self.active] * 101):
                    with self.assertRaisesRegex(ValueError, '^INVENTORY_INPUT_COUNT$'):
                        inventory.inventory_manifests(paths, keyset_file=self.keyset)
                loader.assert_not_called()
                opener.assert_not_called()
        result = self.audit([self.active] * 100)
        self.assertEqual(result['summary']['verified'], 100)
        self.assertTrue(result['summary']['all_valid'])
        self.assertEqual([r['index'] for r in result['files']], list(range(1, 101)))

    def test_real_per_file_byte_boundary(self):
        raw = self.active.read_bytes()
        exact = self.save(raw + b' ' * (inventory.MAX_MANIFEST_BYTES - len(raw)))
        self.assertTrue(self.audit([exact])['summary']['all_valid'])
        with exact.open('ab') as stream:
            stream.write(b' ')
        result = self.audit([exact, self.active])
        self.assertEqual(result['files'][0]['input_error'], 'INVENTORY_MANIFEST_BYTES_LIMIT')
        self.assertEqual(result['summary']['verified'], 1)
        self.assertFalse(result['summary']['all_valid'])

    def test_aggregate_exact_boundary_and_explicit_skips(self):
        size = self.active.stat().st_size
        with patch.object(inventory, 'MAX_TOTAL_BYTES', size * 2):
            self.assertTrue(self.audit([self.active] * 2)['summary']['all_valid'])
            result = self.audit([self.active] * 4)
        self.assertEqual([r['input_error'] for r in result['files']],
                         [None, None, 'INVENTORY_TOTAL_BYTES_LIMIT', 'INVENTORY_SKIPPED_TOTAL_BYTES_LIMIT'])
        self.assertEqual(result['summary'], dict(requested=4, verified=2, failed=1, skipped=1,
                         complete=False, all_valid=False, all_dev_signatures_verified=False))

    def test_invalid_json_also_consumes_aggregate_budget(self):
        bad = self.save(b'{' * self.active.stat().st_size)
        with patch.object(inventory, 'MAX_TOTAL_BYTES', bad.stat().st_size):
            result = self.audit([bad, self.active, self.active])
        self.assertEqual([r['input_error'] for r in result['files']],
                         ['INVENTORY_DOCUMENT_INVALID', 'INVENTORY_TOTAL_BYTES_LIMIT',
                          'INVENTORY_SKIPPED_TOTAL_BYTES_LIMIT'])
        self.assertFalse(result['summary']['all_valid'])

    def test_growth_after_stat_is_bounded(self):
        raw = self.active.read_bytes()
        original = os.read
        for total_limit in (False, True):
            with self.subTest(total_limit=total_limit):
                path = self.save(raw)
                calls = []

                def read(fd, count):
                    calls.append(count)
                    if len(calls) == 1:
                        with path.open('ab') as stream:
                            stream.write(b' ' * 1000)
                    return original(fd, count)

                target = 'MAX_TOTAL_BYTES' if total_limit else 'MAX_MANIFEST_BYTES'
                with patch.object(inventory, target, len(raw)):
                    # Patch only manifest reads, after the real strict keyset load.
                    with patch.object(inventory, 'load_dev_keyset', return_value=load_dev_keyset(self.keyset)):
                        with patch.object(inventory.os, 'read', side_effect=read):
                            result = self.audit([path])
                self.assertEqual(result['files'][0]['input_error'],
                                 'INVENTORY_TOTAL_BYTES_LIMIT' if total_limit else 'INVENTORY_MANIFEST_BYTES_LIMIT')
                self.assertLessEqual(max(calls), len(raw) + 1)
                self.assertFalse(result['summary']['all_valid'])

    def test_bad_json_bytes_are_closed_errors_and_batch_continues(self):
        bad = [b'{"x":1,"x":2}', b'\xff', b'\xef\xbb\xbf{}', b'\x00{}', b'{',
               b'[' * 2000 + b']' * 2000, b'{"x":NaN}']
        paths = [self.save(raw, f'bad-{i}.json') for i, raw in enumerate(bad)]
        result = self.audit(paths + [self.active])
        for row in result['files'][:-1]:
            self.assertEqual(row['input_error'], 'INVENTORY_DOCUMENT_INVALID')
            self.assertIsNone(row['verification'])
        self.assertTrue(result['files'][-1]['verification']['ok'])
        self.assertFalse(result['summary']['complete'])
        # Escaped surrogates are accepted by the existing canonical JSON path;
        # preserve its content-corruption outcome rather than inventing a result.
        document = json.loads(self.active.read_bytes())
        document['sections']['journal']['body'] = {'bad': '\ud800'}
        row = self.audit([self.save(document)])['files'][0]
        self.assertIsNone(row['input_error'])
        self.assertEqual(row['verification']['reason'], 'SECTION_HASH_MISMATCH:journal')

    def test_document_depth_boundary(self):
        for depth in (inventory.MAX_JSON_DEPTH, inventory.MAX_JSON_DEPTH + 1):
            row = self.audit([self.save(b'[' * depth + b'0' + b']' * depth)])['files'][0]
            if depth == inventory.MAX_JSON_DEPTH:
                self.assertIsNone(row['input_error'])
                self.assertEqual(row['verification']['reason'], 'MANIFEST_SHAPE')
            else:
                self.assertEqual(row['input_error'], 'INVENTORY_DOCUMENT_INVALID')

    def test_keyset_signature_mismatch_retains_existing_outcome(self):
        document = json.loads(self.active.read_bytes())
        document['signature']['value'] = '0' * 64
        row = self.audit([self.save(document)])['files'][0]
        self.assertEqual(row['verification']['reason'], 'SIGNATURE_MISMATCH')

    def test_shape_failures_and_metadata_allowlist(self):
        document = json.loads(self.active.read_bytes())
        for digest, kid in [('A' * 64, 'x' * 129), ([], ['bad']), ('123', 'newline\nkid')]:
            document['content_digest'] = digest
            document['signature']['kid'] = kid
            row = self.audit([self.save(document)])['files'][0]
            self.assertIsNone(row['content_digest'])
            self.assertIsNone(row['kid'])
            self.assertIsNotNone(row['verification'])
        for value in ([], None, 'SIMULATED', 123):
            row = self.audit([self.save(value)])['files'][0]
            self.assertEqual(row['verification']['reason'], 'MANIFEST_SHAPE')
            self.assertIsNone(row['input_error'])

    def test_filesystem_rejections_and_no_link_component_normalization(self):
        link = self.directory / 'link.json'
        link.symlink_to(self.active)
        parent = self.directory / 'linked-directory'
        parent.symlink_to(MANIFESTS, target_is_directory=True)
        fifo = self.directory / 'fifo'
        os.mkfifo(fifo)
        paths = [link, parent / self.active.name, str(parent) + '/../manifest/dev-keyset-kid-1.json',
                 self.directory, fifo, self.directory / 'missing.json']
        result = self.audit(paths + [self.active])
        self.assertTrue(all(r['input_error'] in ('INVENTORY_INPUT_UNREADABLE', 'INVENTORY_INPUT_NOT_REGULAR')
                            for r in result['files'][:-1]))
        self.assertEqual(result['summary']['failed'], 6)
        self.assertEqual(result['summary']['verified'], 1)
        self.assertFalse(result['summary']['all_valid'])

    def test_read_error_closes_descriptor_and_continues(self):
        opened = []
        original = inventory._open_regular
        original_read = os.read

        def opener(path):
            fd = original(path)
            opened.append(fd)
            return fd

        def read(fd, count):
            if len(opened) == 1:
                raise OSError('SENSITIVE ERROR MUST NOT APPEAR')
            return original_read(fd, count)

        with patch.object(inventory, 'load_dev_keyset', return_value=load_dev_keyset(self.keyset)):
            with patch.object(inventory, '_open_regular', side_effect=opener):
                with patch.object(inventory.os, 'read', side_effect=read):
                    result = self.audit([self.active, self.active])
        self.assertEqual(result['files'][0]['input_error'], 'INVENTORY_INPUT_UNREADABLE')
        self.assertTrue(result['files'][1]['verification']['ok'])
        self.assertNotIn('SENSITIVE', json.dumps(result))
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_unsupported_secure_open_platform_fails_closed(self):
        with patch.object(inventory.os, 'supports_dir_fd', set()):
            result = self.audit()
        self.assertEqual(result['files'][0]['input_error'], 'INVENTORY_SECURE_OPEN_UNSUPPORTED')
        self.assertFalse(result['summary']['all_valid'])

    def test_exact_keyset_modes_and_invalid_keysets(self):
        original = self.keyset.read_bytes()
        for mode in (0o644, 0o400, 0o1600, 0o2600, 0o4600):
            with self.subTest(mode=oct(mode)):
                self.keyset.chmod(mode)
                result = self.audit()
                self.assertEqual(result['keyset_error'], 'SIGNATURE_KEYSET_MODE')
                self.assertEqual(self.keyset.stat().st_mode & 0o7777, mode)
                self.assertEqual(self.keyset.read_bytes(), original)
        self.keyset.chmod(0o600)
        for raw in (b'{}', b'{"x":1,"x":2}', b'\xff', b' ' * 65537):
            self.keyset.write_bytes(raw)
            self.assertEqual(self.audit()['keyset_error'], 'SIGNATURE_KEYSET_INVALID')
            self.assertEqual(self.keyset.read_bytes(), raw)

    def test_cli_determinism_exit_codes_and_no_disclosure(self):
        args = ['--keyset-file', self.keyset, self.active, self.active]
        first, second = self.cli(*args), self.cli(*args)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr + second.stderr, '')
        report = json.loads(first.stdout)
        self.assertEqual(first.stdout, json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
        keyset = load_dev_keyset(self.keyset)
        for entry in keyset['keys']:
            self.assertNotIn(entry['key_hex'], first.stdout)
            self.assertNotIn(bytes.fromhex(entry['key_hex']).decode('latin1'), first.stdout)
        for paths in ([MANIFESTS / 'unknown-kid.json'], [self.directory / 'missing'],
                      [self.save(b'{"key_hex":"SENSITIVE_RAW_DOCUMENT"')]):
            proc = self.cli('--keyset-file', self.keyset, *paths)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, '')
            self.assertNotIn('SENSITIVE_RAW_DOCUMENT', proc.stdout)
        for args in ([], [str(self.active)], ['--keyset-file', str(self.keyset)],
                     ['--keyset-file', str(self.keyset)] + [str(self.active)] * 101):
            proc = self.cli(*args)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, '')
            self.assertNotIn('Traceback', proc.stderr)

    def test_no_input_mutation_success_or_failure(self):
        good = self.save(self.active.read_bytes(), 'good.json')
        bad = self.save(b'{', 'bad.json')
        paths = [good, bad, self.keyset]
        before = [(p.read_bytes(), p.stat().st_mode) for p in paths]
        self.audit([good, bad, self.directory / 'missing'])
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mode) for p in paths])
        self.assertEqual(set(self.directory.iterdir()), set(paths))


if __name__ == '__main__':
    unittest.main()
