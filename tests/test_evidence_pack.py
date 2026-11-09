"""Offline audit evidence pack: deterministic composition and its verifier.

Every file in tests/vectors/pack/ is run through `scripts/evidence_pack.py
--verify` and must report its exact expected reason. The pack and the corpus
are SIMULATED and LOCAL_ONLY: remote attestation, stage7 authenticated export,
and retention enforcement stay NOT_BOUND, and no DEV_ONLY key or token is ever
copied into the pack.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital import evidence
from capital.evidence import (
    OFFLINE_INSTANCE, PACK_FILE, PACK_FORMAT, PACK_SECTION_IDS, pack_material,
)
from capital.export import VOLATILE_KEYS, sha256_hex

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'scripts' / 'seed_demo.py'
SCRIPT = ROOT / 'scripts' / 'evidence_pack.py'
VECTORS_SCRIPT = ROOT / 'scripts' / 'pack_vectors.py'
VECTORS = ROOT / 'tests' / 'vectors'
PACKS = VECTORS / 'pack'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
DEV_KEY = VECTORS / 'export-dev.key'

ALL_MATCHED = {name: 'MATCHED' for name in PACK_SECTION_IDS}
NONE_CHECKED = {name: 'NOT_CHECKED' for name in PACK_SECTION_IDS}


def stopped_at(name):
    """The verifier walks sections in order and stops at the first bad hash."""
    index = PACK_SECTION_IDS.index(name)
    return {
        other: 'MATCHED' if position < index else 'SECTION_HASH_MISMATCH' if position == index else 'NOT_CHECKED'
        for position, other in enumerate(PACK_SECTION_IDS)
    }


def expect(reason, sections, volatile, digest_status, embedded):
    return {
        'reason': reason, 'sections': sections, 'volatile': volatile,
        'content_digest': digest_status, 'embedded_manifest': embedded,
    }


# Written by hand on purpose: the generator must not be its own oracle.
EXPECTED = {
    'clean.json': expect(None, ALL_MATCHED, 'MATCHED', 'MATCHED', 'MATCHED'),
    **{
        f'section-{name}.json': expect(
            f'SECTION_HASH_MISMATCH:{name}', stopped_at(name), 'NOT_CHECKED',
            'NOT_CHECKED', 'NOT_CHECKED')
        for name in PACK_SECTION_IDS
    },
    'volatile.json': expect(
        'VOLATILE_HASH_MISMATCH', ALL_MATCHED, 'VOLATILE_HASH_MISMATCH',
        'NOT_CHECKED', 'NOT_CHECKED'),
    'content-digest.json': expect(
        'CONTENT_DIGEST_MISMATCH', ALL_MATCHED, 'MATCHED',
        'CONTENT_DIGEST_MISMATCH', 'NOT_CHECKED'),
    'truncated.json': expect(
        'PACK_UNREADABLE', NONE_CHECKED, 'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED'),
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack_vectors = _load('pack_vectors', VECTORS_SCRIPT)


def run_script(*argv):
    """Call pack_vectors.main with its status lines swallowed; return (exit code, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = pack_vectors.main(list(argv))
    return code, err.getvalue()


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


class PackCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / 'ws'
        self.out = Path(self.tmp.name) / 'out'

    def _cli(self, *argv):
        return subprocess.run(
            [sys.executable, os.fspath(SCRIPT), *argv],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)

    def _pack(self, out=None, workspace=None):
        proc = self._cli(
            '--workspace', os.fspath(workspace or self.dir),
            '--out', os.fspath(out or self.out))
        self.assertEqual(proc.stderr, '')
        return proc.returncode, json.loads(proc.stdout)

    def _verify(self, path):
        proc = self._cli('--verify', os.fspath(path))
        self.assertEqual(proc.stderr, '')
        return proc.returncode, json.loads(proc.stdout)

    def test_seeded_workspace_packs_complete_and_verifies(self):
        seed_workspace(self.dir)
        code, report = self._pack()
        self.assertEqual(code, 0, report)
        self.assertTrue(report['ok'])
        self.assertEqual(report['pack_status'], 'COMPLETE')
        self.assertEqual(report['incomplete_reasons'], [])
        self.assertEqual(sorted(report['sections']), sorted(PACK_SECTION_IDS))
        self.assertTrue(report['verified'])
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual(report['locality'], 'LOCAL_ONLY')
        self.assertEqual(report['format'], PACK_FORMAT)
        self.assertIs(report['funds_executed'], False)
        self.assertEqual(report['authentication'], 'NOT_BOUND')
        path = Path(report['pack'])
        self.assertEqual(path.name, PACK_FILE)
        pack = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(pack['format'], PACK_FORMAT)
        self.assertEqual(pack['label'], 'SIMULATED')
        self.assertEqual(pack['diagnostic'], 'READ_ONLY')
        self.assertEqual(pack['locality'], 'LOCAL_ONLY')
        self.assertEqual(pack['status'], 'COMPLETE')
        self.assertEqual(pack['signature'], 'NOT_BOUND')
        self.assertEqual(set(pack['sections']), set(PACK_SECTION_IDS))
        for name, section in pack['sections'].items():
            self.assertEqual(set(section), {'sha256', 'body'})
            self.assertEqual(section['sha256'], sha256_hex(section['body']))
            self.assertEqual(set(section['body']), {'part_tag', 'document'})
        self.assertEqual(pack['volatile']['sha256'], sha256_hex(pack['volatile']['body']))
        self.assertEqual(pack['content_digest'], evidence.content_digest(pack))
        bound = {row['id']: row['status'] for row in pack['not_bound']}
        self.assertEqual(bound['remote_attestation'], 'NOT_BOUND')
        self.assertEqual(bound['stage7_authenticated_export'], 'NOT_BOUND')
        self.assertEqual(bound['retention_enforcement'], 'NOT_BOUND')
        self.assertEqual(bound['event_log'], 'EXCLUDED')
        code, verify = self._verify(path)
        self.assertEqual(code, 0, verify)
        self.assertTrue(verify['ok'])
        self.assertEqual(verify['sections'], ALL_MATCHED)
        self.assertEqual(verify['volatile'], 'MATCHED')
        self.assertEqual(verify['content_digest'], 'MATCHED')
        self.assertEqual(verify['embedded_manifest'], 'MATCHED')
        self.assertEqual(verify['pack_status'], 'COMPLETE')

    def test_two_runs_on_one_workspace_emit_identical_bytes(self):
        seed_workspace(self.dir)
        first = Path(self.tmp.name) / 'one'
        second = Path(self.tmp.name) / 'two'
        code, _ = self._pack(out=first)
        self.assertEqual(code, 0)
        code, _ = self._pack(out=second)
        self.assertEqual(code, 0)
        self.assertEqual(
            (first / PACK_FILE).read_bytes(), (second / PACK_FILE).read_bytes())

    def test_pack_does_not_touch_the_workspace(self):
        seed_workspace(self.dir)
        before = snapshot(self.dir)
        code, _ = self._pack()
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.dir), before)

    def test_embedded_manifest_matches_the_golden_book(self):
        seed_workspace(self.dir)
        code, _ = self._pack()
        self.assertEqual(code, 0)
        pack = json.loads((self.out / PACK_FILE).read_text(encoding='utf-8'))
        embedded = pack['sections']['export_manifest']['body']['document']
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(embedded['content_digest'], golden['content_digest'])
        self.assertEqual(embedded['status'], 'COMPLETE')
        self.assertEqual(embedded['signature']['status'], 'NOT_BOUND')
        self.assertEqual(embedded['signature']['alg'], 'UNSIGNED')
        audit = pack['sections']['workspace_audit']['body']['document']
        self.assertEqual(audit['state_digest'], golden['state_digest'])
        self.assertEqual(audit['recon_status'], 'MATCHED')
        recon = pack['sections']['reconciliation']['body']['document']
        self.assertEqual(recon['status'], 'MATCHED')
        self.assertEqual(recon['state_digest'], golden['state_digest'])

    def test_volatile_fields_stay_out_of_the_content_digest(self):
        seed_workspace(self.dir)
        code, _ = self._pack()
        self.assertEqual(code, 0)
        pack = json.loads((self.out / PACK_FILE).read_text(encoding='utf-8'))
        material = pack_material(pack)
        found = []

        def walk(node):
            if type(node) is dict:
                for key, item in node.items():
                    if key in VOLATILE_KEYS:
                        found.append(key)
                    walk(item)
            elif type(node) is list:
                for item in node:
                    walk(item)

        walk(material)
        self.assertEqual(found, [])
        self.assertIn('saved_at', pack['volatile']['body'])
        self.assertNotIn('volatile', material)
        self.assertNotIn('content_digest', material)
        # Stored section bytes keep the volatile fields; only the digest skips them.
        self.assertEqual(
            pack['sections']['reconciliation']['body']['document']['instance_id'],
            OFFLINE_INSTANCE)

    def test_dev_key_in_the_workspace_is_never_copied(self):
        seed_workspace(self.dir)
        key = DEV_KEY.read_bytes()[len(b'DEV_ONLY\n'):]
        (self.dir / 'export-dev.key').write_bytes(DEV_KEY.read_bytes())
        code, _ = self._pack()
        self.assertEqual(code, 0)
        raw = (self.out / PACK_FILE).read_bytes()
        self.assertNotIn(key, raw)
        self.assertNotIn(key.hex().encode(), raw)
        self.assertNotIn(b'DEV_ONLY\n', raw)
        pack = json.loads(raw.decode('utf-8'))
        self.assertEqual(
            pack['sections']['export_manifest']['body']['document']['signature']['status'],
            'NOT_BOUND')
        self.assertNotIn('export-dev.key', raw.decode('utf-8'))

    def test_unreadable_workspace_packs_incomplete_and_exits_1(self):
        self.dir.mkdir(parents=True)
        code, report = self._pack()
        self.assertEqual(code, 1)
        self.assertFalse(report['ok'])
        self.assertEqual(report['pack_status'], 'INCOMPLETE')
        self.assertEqual(report['incomplete_reasons'], ['WORKSPACE_AUDIT:WORKSPACE_UNREADABLE'])
        pack = json.loads((self.out / PACK_FILE).read_text(encoding='utf-8'))
        self.assertEqual(pack['status'], 'INCOMPLETE')
        audit = pack['sections']['workspace_audit']['body']['document']
        self.assertFalse(audit['ok'])
        self.assertEqual(audit['reason'], 'WORKSPACE_UNREADABLE')
        for name in ('export_manifest', 'reconciliation', 'decisions'):
            body = pack['sections'][name]['body']['document']
            self.assertEqual(body['status'], 'UNAVAILABLE', name)
        code, verify = self._verify(self.out / PACK_FILE)
        self.assertEqual(code, 0, verify)
        self.assertTrue(verify['ok'])
        self.assertEqual(verify['embedded_manifest'], 'NOT_APPLICABLE')
        self.assertEqual(verify['pack_status'], 'INCOMPLETE')

    def test_tampered_pack_file_fails_verification(self):
        seed_workspace(self.dir)
        code, _ = self._pack()
        self.assertEqual(code, 0)
        path = self.out / PACK_FILE
        raw = bytearray(path.read_bytes())
        index = bytes(raw).index(b'exportmanifestblock')
        raw[index] = ord('X')
        path.write_bytes(bytes(raw))
        code, report = self._verify(path)
        self.assertEqual(code, 1)
        self.assertFalse(report['ok'])
        self.assertEqual(report['reason'], 'SECTION_HASH_MISMATCH:export_manifest')

    def test_argument_errors_exit_2(self):
        proc = self._cli()
        self.assertEqual(proc.returncode, 2)
        proc = self._cli('--workspace', os.fspath(self.dir))
        self.assertEqual(proc.returncode, 2)
        proc = self._cli(
            '--workspace', os.fspath(self.dir), '--out', os.fspath(self.out),
            '--verify', 'pack.json')
        self.assertEqual(proc.returncode, 2)


class PackVectorTests(unittest.TestCase):
    def _cli(self, name):
        return subprocess.run(
            [sys.executable, os.fspath(SCRIPT), '--verify', os.fspath(PACKS / name)],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)

    def test_corpus_holds_exactly_the_pinned_files(self):
        self.assertEqual(sorted(path.name for path in PACKS.iterdir()), sorted(EXPECTED))

    def test_every_vector_reports_its_pinned_reason(self):
        for name, want in sorted(EXPECTED.items()):
            with self.subTest(vector=name):
                proc = self._cli(name)
                self.assertEqual(proc.stderr, '')
                report = json.loads(proc.stdout)
                self.assertEqual(proc.returncode, 0 if want['reason'] is None else 1)
                self.assertIs(report['ok'], want['reason'] is None)
                self.assertEqual(report['reason'], want['reason'])
                self.assertEqual(report['sections'], want['sections'])
                self.assertEqual(report['volatile'], want['volatile'])
                self.assertEqual(report['content_digest'], want['content_digest'])
                self.assertEqual(report['embedded_manifest'], want['embedded_manifest'])
                self.assertEqual(report['format'], PACK_FORMAT)
                self.assertEqual(report['label'], 'SIMULATED')
                self.assertEqual(report['locality'], 'LOCAL_ONLY')
                self.assertEqual(report['authentication'], 'NOT_BOUND')
                self.assertEqual(report['remote_attestation'], 'NOT_BOUND')
                self.assertIs(report['funds_executed'], False)

    def test_tampered_variants_differ_from_the_clean_pack_by_one_byte(self):
        clean = (PACKS / 'clean.json').read_bytes()
        for name in sorted(EXPECTED):
            if name in ('clean.json', 'truncated.json'):
                continue
            with self.subTest(vector=name):
                variant = (PACKS / name).read_bytes()
                self.assertEqual(len(variant), len(clean))
                self.assertEqual(sum(a != b for a, b in zip(clean, variant)), 1)
        truncated = (PACKS / 'truncated.json').read_bytes()
        self.assertLess(len(truncated), len(clean))
        self.assertEqual(truncated, clean[:len(truncated)])
        with self.assertRaises(ValueError):
            json.loads(truncated)

    def test_clean_pack_has_no_secret_or_per_run_field(self):
        pack = json.loads((PACKS / 'clean.json').read_text(encoding='utf-8'))
        raw = (PACKS / 'clean.json').read_bytes()
        key = DEV_KEY.read_bytes()[len(b'DEV_ONLY\n'):]
        self.assertNotIn(key, raw)
        self.assertNotIn(key.hex().encode(), raw)
        self.assertNotIn(b'export-dev.key', raw)
        self.assertEqual(pack['volatile']['body']['workspace'], pack_vectors.WORKSPACE_LABEL)
        self.assertEqual(pack['volatile']['body']['saved_by_instance'], pack_vectors.INSTANCE_ID)
        self.assertEqual(pack['volatile']['body']['saved_at'], pack_vectors.SAVED_AT)
        embedded = pack['sections']['export_manifest']['body']['document']
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(embedded['content_digest'], golden['content_digest'])
        self.assertEqual(embedded['signature']['status'], 'NOT_BOUND')

    def test_pack_decision_provenance_hashes_the_actual_notes(self):
        pack = json.loads((PACKS / 'clean.json').read_bytes())
        decisions = pack['sections']['decisions']['body']['document']
        self.assertEqual(decisions['notes_source'], 'CHECKOUT')
        anchor = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
        self.assertEqual(decisions['note_sha256'], hashlib.sha256(anchor.read_bytes()).hexdigest())
        for row in decisions['rows']:
            self.assertEqual(row['notes_source'], 'CHECKOUT')
            self.assertEqual(row['note_sha256'], hashlib.sha256((ROOT / row['note']).read_bytes()).hexdigest())


class PackRegenerationTests(unittest.TestCase):
    def committed(self):
        """Every file this script owns: everything under pack/."""
        found = {}
        for path in sorted(VECTORS.rglob('*')):
            relative = path.relative_to(VECTORS)
            if path.is_file() and relative.parts[0] == PACKS.name:
                found[relative.as_posix()] = path.read_bytes()
        return found

    def test_regeneration_reproduces_the_committed_bytes(self):
        first = pack_vectors.build_vectors()
        self.assertEqual(first, pack_vectors.build_vectors())
        self.assertEqual(first, self.committed())

    def test_check_passes_on_the_committed_corpus(self):
        proc = subprocess.run(
            [sys.executable, os.fspath(VECTORS_SCRIPT), '--check'],
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

            victim = target / 'pack' / 'clean.json'
            original = victim.read_bytes()
            changed = original.replace(b'exportmanifestblock', b'exportmanifestblocl', 1)
            self.assertNotEqual(changed, original)
            victim.write_bytes(changed)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            victim.write_bytes(original)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            extra = target / 'pack' / 'extra.json'
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
