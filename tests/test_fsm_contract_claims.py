"""FSM contract-claim table, mutation, drift, and vendor-hash checks."""
import copy
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.upstream_claims import ClaimTableError, PINNED_SHA, REQUIRED_FIELDS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'fsm_contract_claims_check.py'
PROFILE_TOKEN = 'SEMANTIC' + '_CONFORMANCE'
DOCS = (
    'docs/contracts/CREDIT_ADVANCE_F04.md',
    'docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md',
)


def _module():
    spec = importlib.util.spec_from_file_location('fsm_contract_claims_check', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _flip(value):
    if value is False:
        return True
    if value is True:
        return False
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return value + 'X'
    if value is None:
        return 0
    if type(value) is list:
        return list(reversed(value))
    if type(value) is dict:
        return {key: _flip(item) for key, item in value.items()}
    raise AssertionError(repr(value))


def _write_table(directory, table):
    path = Path(directory) / 'claims.json'
    path.write_text(json.dumps(table), encoding='utf-8')
    return path


def _protocol_tree(root, table):
    grouped = {}
    for claim in table['claims']:
        grouped.setdefault(claim['source_doc'], []).append(claim['section'])
        grouped[claim['source_doc']].append(claim['needle'])
    written = []
    for rel, parts in grouped.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(parts) + '\n', encoding='utf-8')
        written.append(path)
    return written


def _snapshot(root):
    found = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            found[str(path.relative_to(root))] = path.read_bytes()
    return found


def _unique_needle(table):
    by_doc = {}
    for claim in table['claims']:
        by_doc.setdefault(claim['source_doc'], []).append(claim)
    for claims in by_doc.values():
        for claim in claims:
            others = []
            for other in claims:
                if other['id'] == claim['id']:
                    continue
                others.append(other['section'])
                others.append(other['needle'])
            blob = '\n'.join(others)
            if claim['needle'] not in blob and claim['needle'] not in claim['section']:
                return claim
    raise AssertionError('no unique needle')


class FsmContractClaimsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _module()

    def test_table_has_required_fields_and_every_claim_passes(self):
        table = self.module.load_table()
        self.assertGreaterEqual(len(table['claims']), 30)
        self.assertEqual(table['pinned_sha'], PINNED_SHA)
        self.assertEqual(table['label'], 'CLAIM_CONFORMANCE')
        seen = set()
        for claim in table['claims']:
            for field in REQUIRED_FIELDS:
                self.assertIsInstance(claim[field], str)
                self.assertTrue(claim[field].strip())
            self.assertIn('expected', claim)
            self.assertTrue(claim['needle'])
            self.assertEqual(claim['pinned_sha'], PINNED_SHA)
            self.assertIn(claim['source_doc'], DOCS)
            self.assertIn(claim['check_id'], self.module.CHECKS)
            self.assertNotIn(claim['id'], seen)
            seen.add(claim['id'])
            self.assertNotIn(PROFILE_TOKEN, claim['claim'])
        result = self.module.run_claims(table)
        self.assertTrue(result['ok'])
        self.assertEqual(result['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(result['passed'], result['total'])
        self.assertGreaterEqual(result['total'], 30)
        self.assertEqual(result['failed'], [])
        for row in result['rows']:
            self.assertFalse(row['unmapped'])

    def test_missing_field_rejects_the_table(self):
        table = copy.deepcopy(self.module.load_table())
        del table['claims'][0]['section']
        with self.assertRaises(ClaimTableError):
            self.module.validate_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            with self.assertRaises(ClaimTableError):
                self.module.load_table(path)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('CLAIM_CONFORMANCE passed=', proc.stdout)

    def test_unmapped_check_fails_only_that_claim(self):
        table = copy.deepcopy(self.module.load_table())
        table['claims'].append({
            'id': 'mut-unmapped',
            'source_doc': 'docs/contracts/CREDIT_ADVANCE_F04.md',
            'section': '1. 공통 한계',
            'pinned_sha': PINNED_SHA,
            'claim': 'This id is not a registered check.',
            'check_id': 'not.a.real.check',
            'needle': 'funds_executed',
            'expected': None,
        })
        result = self.module.run_claims(table)
        failed = [row for row in result['rows'] if not row['ok']]
        self.assertEqual([row['id'] for row in failed], ['mut-unmapped'])
        self.assertTrue(failed[0]['unmapped'])
        self.assertIsNone(failed[0]['observed'])
        self.assertEqual(result['passed'], result['total'] - 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertEqual(proc.stderr.strip(), 'FAIL mut-unmapped observed=None expected=None')

    def test_flipping_one_expected_fails_exactly_that_claim(self):
        original = self.module.load_table()
        samples = (
            'f04-shared-face-exceeds',
            'f04-shared-face-reserved',
            'f04-restore-digest',
            'settlement-partial-bearer',
            'settlement-recovery-per-line',
            'vendor-commit',
        )
        for claim_id in samples:
            table = copy.deepcopy(original)
            target = next(claim for claim in table['claims'] if claim['id'] == claim_id)
            target['expected'] = _flip(target['expected'])
            with tempfile.TemporaryDirectory() as tmp:
                path = _write_table(tmp, table)
                loaded = self.module.load_table(path)
            result = self.module.run_claims(loaded)
            failed = [row for row in result['rows'] if not row['ok']]
            self.assertEqual([row['id'] for row in failed], [claim_id], claim_id)
            self.assertFalse(failed[0]['unmapped'])
            self.assertNotEqual(failed[0]['observed'], failed[0]['expected'])
        table = copy.deepcopy(original)
        target = next(claim for claim in table['claims'] if claim['id'] == 'f04-shared-face-exceeds')
        target['expected'] = 'ILLEGAL_TRANSITION'
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertEqual(
            proc.stderr.strip(),
            "FAIL f04-shared-face-exceeds observed='ADVANCE_EXCEEDS_OPEN_FACE' "
            "expected='ILLEGAL_TRANSITION'",
        )

    def test_no_args_is_skipped_and_not_a_success_line(self):
        for args in ((), ('--protocol-dir', ''), ('--protocol-dir', '   ')):
            proc = _run(list(args))
            self.assertEqual(proc.returncode, 0, args)
            lines = proc.stdout.splitlines()
            self.assertEqual(lines[0], 'SKIPPED')
            payload = json.loads(lines[1])
            self.assertEqual(payload['status'], 'SKIPPED')
            self.assertEqual(payload['label'], 'CLAIM_CONFORMANCE')
            self.assertNotIn('passed', payload)
            self.assertNotIn('passed', proc.stdout)
            self.assertNotIn(PROFILE_TOKEN, proc.stdout)

    def test_protocol_dir_verifies_citations_without_writing(self):
        table = self.module.load_table()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _protocol_tree(root, table)
            files = [path for path in root.rglob('*') if path.is_file()]
            for path in files:
                path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            root.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            try:
                proc = _run(['--protocol-dir', str(root)])
                report = self.module.check_protocol(root, table)
            finally:
                root.chmod(stat.S_IRWXU)
                for path in files:
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), f"CLAIM_DRIFT verified={report['total']} total={report['total']}")
        self.assertNotIn('passed', proc.stdout)
        self.assertNotIn('SKIPPED', proc.stdout)
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['verified'], report['total'])
        self.assertGreaterEqual(report['total'], 30)

        claim = _unique_needle(table)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _protocol_tree(root, table)
            target = root / claim['source_doc']
            original = target.read_text(encoding='utf-8')
            self.assertIn(claim['needle'], original)
            target.write_text(original.replace(claim['needle'], 'NEEDLE_REMOVED', 1), encoding='utf-8')
            before = _snapshot(root)
            proc = _run(['--protocol-dir', str(root)])
            after = _snapshot(root)
        self.assertEqual(before, after)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn('SKIPPED', proc.stdout)
        self.assertNotIn('passed', proc.stdout)
        self.assertIn(f"DRIFT {claim['id']} missing needle", proc.stderr)
        self.assertEqual(proc.stderr.count('missing needle'), 1)

    def test_missing_section_is_drift(self):
        table = copy.deepcopy(self.module.load_table())
        claim = _unique_needle(table)
        removed = None
        for row in table['claims']:
            if row['id'] == claim['id']:
                removed = row['section']
                row['section'] = 'SECTION_THAT_IS_NOT_THERE'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grouped = {}
            for row in table['claims']:
                if row['id'] == claim['id']:
                    grouped.setdefault(row['source_doc'], []).append(removed)
                else:
                    grouped.setdefault(row['source_doc'], []).append(row['section'])
                grouped[row['source_doc']].append(row['needle'])
            for rel, parts in grouped.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('\n'.join(parts) + '\n', encoding='utf-8')
            proc = _run(['--protocol-dir', str(root), '--table', str(_write_table(tmp, table))])
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"DRIFT {claim['id']} missing section", proc.stderr)
        self.assertEqual(proc.stderr.count('missing section'), 1)

    def test_non_directory_protocol_path_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / 'notes.md'
            file_path.write_text('heading', encoding='utf-8')
            missing = Path(tmp) / 'missing-checkout'
            file_proc = _run(['--protocol-dir', str(file_path)])
            missing_proc = _run(['--protocol-dir', str(missing)])
        for proc in (file_proc, missing_proc):
            self.assertEqual(proc.returncode, 1)
            self.assertNotIn('SKIPPED', proc.stdout)
            self.assertNotIn('passed', proc.stdout)
            self.assertIn('verified=0', proc.stdout)
            self.assertIn('protocol dir is not a directory', proc.stderr)

    def test_execute_prints_the_count_line(self):
        total = len(self.module.load_table()['claims'])
        proc = _run(['--execute'])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, f'CLAIM_CONFORMANCE passed={total} total={total} failed=0\n')
        self.assertEqual(proc.stderr, '')
        self.assertNotIn(PROFILE_TOKEN, proc.stdout)

    def test_vendor_hash_gate(self):
        self.assertTrue(self.module.vendor_hashes())
        self.assertEqual(self.module._vendor_report(), [])
        with tempfile.TemporaryDirectory() as tmp:
            mirror = Path(tmp) / 'vendor'
            shutil.copytree(ROOT / 'capital' / 'vendor', mirror)
            target = mirror / 'credit_advance_f04' / 'credit_fsm.py'
            blob = bytearray(target.read_bytes())
            blob[0] ^= 0xFF
            target.write_bytes(bytes(blob))
            self.assertFalse(self.module.vendor_hashes(mirror))
            self.assertEqual(
                self.module._vendor_report(mirror),
                ['credit_advance_f04/credit_fsm.py'],
            )

    def test_no_profile_token_in_module_output(self):
        self.assertNotIn(PROFILE_TOKEN, self.module.LABEL)
        for name in self.module.CHECKS:
            self.assertNotIn(PROFILE_TOKEN, name)


if __name__ == '__main__':
    unittest.main()
