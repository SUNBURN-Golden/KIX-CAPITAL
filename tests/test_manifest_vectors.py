"""Pinned tamper corpus for the offline export-manifest verifier.

Every file in tests/vectors/manifest/ is run through `python3 -m capital.verify`
and must report its exact expected reason. The corpus is SIMULATED, built from the
seed_demo story with a fixed instance id. The DEV_ONLY key is test vector
material, not a credential, and a shared HMAC key is integrity only, not
authentication.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.export import SECTION_IDS

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests' / 'vectors'
MANIFESTS = VECTORS / 'manifest'
KEY = VECTORS / 'export-dev.key'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
SCRIPT = ROOT / 'scripts' / 'manifest_vectors.py'

ALL_MATCHED = {name: 'MATCHED' for name in SECTION_IDS}
NONE_CHECKED = {name: 'NOT_CHECKED' for name in SECTION_IDS}


def stopped_at(name):
    """The verifier walks sections in order and stops at the first bad hash."""
    index = SECTION_IDS.index(name)
    return {
        other: 'MATCHED' if position < index else 'SECTION_HASH_MISMATCH' if position == index else 'NOT_CHECKED'
        for position, other in enumerate(SECTION_IDS)
    }


def expect(reason, sections, digest, signature):
    return {'reason': reason, 'sections': sections, 'content_digest': digest, 'signature': signature}


# Written by hand on purpose: the generator must not be its own oracle.
EXPECTED = {
    'unsigned.json': expect(None, ALL_MATCHED, 'MATCHED', 'NOT_BOUND'),
    'dev-hmac.json': expect(None, ALL_MATCHED, 'MATCHED', 'VERIFIED_DEV_ONLY_INTEGRITY'),
    **{
        f'section-{name}.json': expect(
            f'SECTION_HASH_MISMATCH:{name}', stopped_at(name), 'NOT_CHECKED', 'NOT_CHECKED')
        for name in SECTION_IDS
    },
    'content-digest.json': expect(
        'CONTENT_DIGEST_MISMATCH', ALL_MATCHED, 'CONTENT_DIGEST_MISMATCH', 'NOT_CHECKED'),
    'signature.json': expect('SIGNATURE_MISMATCH', ALL_MATCHED, 'MATCHED', 'SIGNATURE_MISMATCH'),
    'malformed.json': expect('MANIFEST_UNREADABLE', NONE_CHECKED, 'NOT_CHECKED', 'NOT_CHECKED'),
}


def _load_script():
    spec = importlib.util.spec_from_file_location('manifest_vectors', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


def run_script(*argv):
    """Call script.main with its status lines swallowed; return (exit code, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main(list(argv))
    return code, err.getvalue()


class ManifestVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # git stores the key at 0644 and the verifier insists on 0600.
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.key_path = Path(cls._tmp.name) / 'export-dev.key'
        shutil.copyfile(KEY, cls.key_path)
        os.chmod(cls.key_path, 0o600)
        cls.key = KEY.read_bytes()[len(b'DEV_ONLY\n'):]

    def _cli(self, path, key_file):
        command = [sys.executable, '-m', 'capital.verify', os.fspath(path)]
        if key_file is not None:
            command.extend(['--key-file', os.fspath(key_file)])
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)

    def _report(self, name, key_file):
        proc = self._cli(MANIFESTS / name, key_file)
        self.assertEqual(proc.stderr, '')
        self.assertNotIn(self.key.decode(), proc.stdout)
        self.assertNotIn(self.key.hex(), proc.stdout)
        return proc.returncode, json.loads(proc.stdout)

    def test_corpus_holds_exactly_the_pinned_files(self):
        self.assertEqual(sorted(path.name for path in MANIFESTS.iterdir()), sorted(EXPECTED))

    def test_every_vector_reports_its_pinned_reason(self):
        for name, want in sorted(EXPECTED.items()):
            with self.subTest(vector=name):
                code, report = self._report(name, self.key_path)
                self.assertEqual(code, 0 if want['reason'] is None else 1)
                self.assertIs(report['ok'], want['reason'] is None)
                self.assertEqual(report['reason'], want['reason'])
                self.assertEqual(report['sections'], want['sections'])
                self.assertEqual(report['content_digest'], want['content_digest'])
                self.assertEqual(report['signature'], want['signature'])
                self.assertEqual(report['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V2')
                self.assertEqual(report['authentication'], 'NOT_BOUND')
                self.assertIs(report['stage7_authenticated_export'], False)

    def test_unsigned_vector_verifies_without_a_key(self):
        code, report = self._report('unsigned.json', None)
        self.assertEqual(code, 0)
        self.assertTrue(report['ok'])
        self.assertEqual(report['signature'], 'NOT_BOUND')

    def test_signed_vector_needs_its_own_key(self):
        code, report = self._report('dev-hmac.json', None)
        self.assertEqual((code, report['reason'], report['content_digest']), (1, 'SIGNATURE_KEY_REQUIRED', 'MATCHED'))
        other = Path(self._tmp.name) / 'other.key'
        other.write_bytes(b'DEV_ONLY\n' + b'z' * 32)
        os.chmod(other, 0o600)
        code, report = self._report('dev-hmac.json', other)
        self.assertEqual((code, report['reason']), (1, 'SIGNATURE_MISMATCH'))

    def test_tampered_variants_differ_from_the_signed_manifest_by_one_byte(self):
        signed = (MANIFESTS / 'dev-hmac.json').read_bytes()
        flipped = ['content-digest.json', 'signature.json'] + [f'section-{name}.json' for name in SECTION_IDS]
        for name in flipped:
            with self.subTest(vector=name):
                variant = (MANIFESTS / name).read_bytes()
                self.assertEqual(len(variant), len(signed))
                self.assertEqual(sum(a != b for a, b in zip(signed, variant)), 1)
        malformed = (MANIFESTS / 'malformed.json').read_bytes()
        self.assertLess(len(malformed), len(signed))
        self.assertEqual(malformed, signed[:len(malformed)])
        with self.assertRaises(ValueError):
            json.loads(malformed)

    def test_both_clean_vectors_are_one_seeded_book(self):
        unsigned = json.loads((MANIFESTS / 'unsigned.json').read_text(encoding='ascii'))
        signed = json.loads((MANIFESTS / 'dev-hmac.json').read_text(encoding='ascii'))
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(unsigned['content_digest'], golden['content_digest'])
        self.assertEqual(signed['content_digest'], golden['content_digest'])
        self.assertEqual(unsigned['signature']['alg'], 'UNSIGNED')
        self.assertEqual(signed['signature']['alg'], 'DEV_HMAC_SHA256')
        unsigned.pop('signature')
        signed.pop('signature')
        self.assertEqual(unsigned, signed)
        self.assertEqual(signed['instance_id'], script.INSTANCE_ID)
        self.assertEqual(signed['label'], 'SIMULATED')
        self.assertIs(signed['funds_executed'], False)
        self.assertEqual(signed['status'], 'COMPLETE')

    def test_key_file_is_dev_only_and_stays_out_of_every_manifest(self):
        self.assertTrue(KEY.read_bytes().startswith(b'DEV_ONLY\n'))
        self.assertEqual(len(self.key), 32)
        for path in sorted(MANIFESTS.iterdir()):
            with self.subTest(vector=path.name):
                raw = path.read_bytes()
                self.assertNotIn(self.key, raw)
                self.assertNotIn(self.key.hex().encode(), raw)


class RegenerationTests(unittest.TestCase):
    def committed(self):
        found = {}
        for path in sorted(VECTORS.rglob('*')):
            if path.is_file():
                found[path.relative_to(VECTORS).as_posix()] = path.read_bytes()
        return found

    def test_regeneration_reproduces_the_committed_bytes(self):
        first = script.build_vectors()
        self.assertEqual(first, script.build_vectors())
        self.assertEqual(first, self.committed())

    def test_check_passes_on_the_committed_corpus(self):
        proc = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), '--check'],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_write_into_another_directory_matches_and_check_catches_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'vectors'
            self.assertEqual(run_script('--write', '--dir', os.fspath(target))[0], 0)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)
            written = {
                path.relative_to(target).as_posix(): path.read_bytes()
                for path in sorted(target.rglob('*')) if path.is_file()
            }
            self.assertEqual(written, self.committed())

            victim = target / 'manifest' / 'dev-hmac.json'
            original = victim.read_bytes()
            changed = original.replace(b'journalpart', b'journalpars', 1)
            self.assertNotEqual(changed, original)
            victim.write_bytes(changed)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            victim.write_bytes(original)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            extra = target / 'manifest' / 'extra.json'
            extra.write_bytes(b'{}\n')
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            self.assertEqual(run_script('--write', '--dir', os.fspath(target))[0], 0)
            self.assertFalse(extra.exists())
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            victim.unlink()
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)

    def test_check_writes_nothing(self):
        before = self.committed()
        self.assertEqual(run_script('--check'), (0, ''))
        self.assertEqual(self.committed(), before)


if __name__ == '__main__':
    unittest.main()
