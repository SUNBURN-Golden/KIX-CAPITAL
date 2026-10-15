"""Pinned tamper corpus for the offline workspace auditor.

Every file in tests/vectors/workspace/ is copied to a scratch directory as
workspace.json and run through `python3 -m capital.verify --workspace DIR`,
which must report its exact expected failing check. The corpus is SIMULATED,
built from the seed_demo story with a fixed instance id.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.audit import CHECK_ORDER

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests' / 'vectors'
WORKSPACE = VECTORS / 'workspace'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
SCRIPT = ROOT / 'scripts' / 'workspace_vectors.py'

# Written by hand on purpose: the generator must not be its own oracle.
EXPECTED = {
    'clean.json': (None, None),
    'truncated.json': ('WORKSPACE_UNREADABLE', 'strict_json'),
    'payload-byte.json': ('WORKSPACE_UNREADABLE', 'payload_sha256'),
    'digest.json': ('WORKSPACE_UNREADABLE', 'payload_sha256'),
    'duplicate-key.json': ('WORKSPACE_UNREADABLE', 'strict_json'),
    'stale-digest.json': ('WORKSPACE_UNREADABLE', 'state_digest'),
}


def _load_script():
    spec = importlib.util.spec_from_file_location('workspace_vectors', SCRIPT)
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


class WorkspaceVectorTests(unittest.TestCase):
    def _cli(self, name):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'workspace.json').write_bytes((WORKSPACE / name).read_bytes())
            proc = subprocess.run(
                [sys.executable, '-m', 'capital.verify', '--workspace', os.fspath(directory)],
                cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(proc.stderr, '')
            return proc.returncode, json.loads(proc.stdout)

    def test_corpus_holds_exactly_the_pinned_files(self):
        self.assertEqual(sorted(path.name for path in WORKSPACE.iterdir()), sorted(EXPECTED))

    def test_every_vector_reports_its_pinned_check(self):
        for name, (reason, failed_check) in sorted(EXPECTED.items()):
            with self.subTest(vector=name):
                code, report = self._cli(name)
                self.assertEqual(code, 0 if reason is None else 1)
                self.assertIs(report['ok'], reason is None)
                self.assertEqual(report['reason'], reason)
                self.assertEqual(report['failed_check'], failed_check)
                self.assertEqual(report['format'], 'KIX_CAPITAL_LOCAL_WORKSPACE_V1')
                self.assertEqual(report['mode'], 'OFFLINE_WORKSPACE_AUDIT')
                self.assertEqual(report['label'], 'SIMULATED')
                self.assertIs(report['lock_taken'], False)
                self.assertIs(report['workspace_mutated'], False)
                self.assertEqual(report['stage5_durable_transactions'], 'NOT_BOUND')
                position = CHECK_ORDER.index(failed_check) if failed_check else len(CHECK_ORDER)
                self.assertEqual(report['checks'], {
                    check: 'MATCHED' if index < position else
                           'MISMATCH' if failed_check and index == position else 'NOT_CHECKED'
                    for index, check in enumerate(CHECK_ORDER)
                })
                if failed_check is None:
                    self.assertEqual(report['recon_status'], 'MATCHED')
                else:
                    self.assertEqual(report['recon_status'], 'NOT_CHECKED')
                    self.assertIsNone(report['recon'])

    def test_clean_vector_is_the_seeded_book(self):
        clean = json.loads((WORKSPACE / 'clean.json').read_text(encoding='ascii'))
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(clean['format'], 'KIX_CAPITAL_LOCAL_WORKSPACE_V1')
        self.assertEqual(clean['payload']['state_digest'], golden['state_digest'])
        self.assertEqual(clean['saved_by_instance'], script.INSTANCE_ID)
        self.assertEqual(clean['saved_at'], script.SAVED_AT)

    def test_tampered_variants_differ_from_clean_by_one_byte(self):
        clean = (WORKSPACE / 'clean.json').read_bytes()
        for name in ('payload-byte.json', 'digest.json'):
            with self.subTest(vector=name):
                variant = (WORKSPACE / name).read_bytes()
                self.assertEqual(len(variant), len(clean))
                self.assertEqual(sum(a != b for a, b in zip(clean, variant)), 1)
        truncated = (WORKSPACE / 'truncated.json').read_bytes()
        self.assertLess(len(truncated), len(clean))
        self.assertEqual(truncated, clean[:len(truncated)])
        with self.assertRaises(ValueError):
            json.loads(truncated)
        doubled = (WORKSPACE / 'duplicate-key.json').read_bytes()
        self.assertEqual(doubled.count(b'"format":"KIX_CAPITAL_LOCAL_WORKSPACE_V1"'), 2)
        json.loads(doubled)  # plain JSON still parses; the strict reader rejects it

    def test_stale_digest_keeps_an_intact_envelope(self):
        document = json.loads((WORKSPACE / 'stale-digest.json').read_text(encoding='ascii'))
        import hashlib
        from capital.store import canonical_bytes
        actual = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
        self.assertEqual(document['payload_sha256'], actual)
        self.assertEqual(document['payload']['state_digest'], '0' * 64)


class RegenerationTests(unittest.TestCase):
    def committed(self):
        """Every file this script owns: everything under workspace/.

        Sibling artifacts in tests/vectors/ (manifest/, the dev key,
        finance_vectors.json) have their own generators and tests.
        """
        found = {}
        if WORKSPACE.is_dir():
            for path in sorted(WORKSPACE.iterdir()):
                if path.is_file():
                    found[f'{WORKSPACE.name}/{path.name}'] = path.read_bytes()
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

            victim = target / 'workspace' / 'clean.json'
            original = victim.read_bytes()
            changed = original.replace(b'"amount":2', b'"amount":9', 1)
            self.assertNotEqual(changed, original)
            victim.write_bytes(changed)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            victim.write_bytes(original)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            extra = target / 'workspace' / 'extra.json'
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
