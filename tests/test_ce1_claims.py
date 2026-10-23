"""CE1 CLAIM_CONFORMANCE table, mutation, drift, divergence, and stage tests."""
import copy
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.ce1_claims import (
    CHECKS,
    FORMAT,
    PINNED_SHA,
    REQUIRED_FIELDS,
    SOURCE_DOC,
    ClaimTableError,
    InputRejected,
    check_protocol,
    decode_input,
    load_table,
    run_claims,
    validate_table,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'ce1_claims_check.py'
PROFILE_TOKEN = 'SEMANTIC' + '_CONFORMANCE'


def _acceptance():
    spec = importlib.util.spec_from_file_location('acceptance_ce1', ROOT / 'scripts' / 'acceptance.py')
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


def _write_table(directory, table):
    path = Path(directory) / 'claims.json'
    path.write_text(json.dumps(table), encoding='utf-8')
    return path


def _protocol_tree(root, table):
    grouped = {}
    for claim in table['claims']:
        grouped.setdefault(claim['source_doc'], []).append(claim['section'])
        grouped[claim['source_doc']].append(claim['needle'])
    for rel, parts in grouped.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(parts) + '\n', encoding='utf-8')


def _snapshot(root):
    found = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            found[str(path.relative_to(root))] = path.read_bytes()
    return found


def _flip(value):
    if value is False:
        return True
    if value is True:
        return False
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return value + 'X'
    if type(value) is dict:
        flipped = dict(value)
        flipped['capital_bytes'] = flipped['capital_bytes'] + 'X'
        return flipped
    raise AssertionError(repr(value))


class Ce1ClaimsTests(unittest.TestCase):
    def test_table_has_required_fields_and_every_claim_passes(self):
        table = load_table()
        self.assertEqual(table['format'], FORMAT)
        self.assertEqual(table['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(table['pinned_sha'], PINNED_SHA)
        self.assertGreaterEqual(len(table['claims']), 40)
        seen = set()
        divergence = 0
        for claim in table['claims']:
            for field in REQUIRED_FIELDS:
                self.assertIsInstance(claim[field], str)
                self.assertTrue(claim[field].strip())
            self.assertEqual(claim['source_doc'], SOURCE_DOC)
            self.assertEqual(claim['pinned_sha'], PINNED_SHA)
            self.assertIn('expected', claim)
            self.assertIn('input', claim)
            self.assertTrue(claim['needle'])
            self.assertIn(claim['check_id'], CHECKS)
            self.assertNotIn(claim['id'], seen)
            seen.add(claim['id'])
            self.assertNotIn(PROFILE_TOKEN, claim['claim'])
            if claim.get('disposition') == 'DOCUMENTED_DIVERGENCE':
                divergence += 1
                self.assertIn('divergence', claim)
        self.assertGreaterEqual(divergence, 3)
        result = run_claims(table)
        self.assertTrue(result['ok'])
        self.assertEqual(result['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(result['passed'], result['total'])
        self.assertEqual(result['failed'], [])
        self.assertEqual(len(result['documented_divergences']), divergence)
        for row in result['rows']:
            self.assertFalse(row['unmapped'])

    def test_reject_rows_never_hash_the_input(self):
        table = load_table()
        result = run_claims(table)
        rejected = [row for row in result['rows'] if row['check_id'] == 'ce1.reject']
        self.assertGreaterEqual(len(rejected), 15)
        for row in rejected:
            self.assertTrue(row['observed'].startswith('REJECTED:'), row['id'])
        codes = {row['observed'] for row in rejected}
        for required in (
                'REJECTED:DUPLICATE_KEY', 'REJECTED:NONSTANDARD_CONSTANT',
                'REJECTED:UNSAFE_INTEGER', 'REJECTED:INVALID_KEY'):
            self.assertIn(required, codes)

    def test_divergence_rows_pin_both_renderings_and_the_note(self):
        table = load_table()
        result = run_claims(table)
        rows = {
            row['id']: row for row in result['rows']
            if row['disposition'] == 'DOCUMENTED_DIVERGENCE'}
        for row in rows.values():
            self.assertTrue(row['ok'], row['id'])
            self.assertTrue(row['observed']['divergent'], row['id'])
            self.assertTrue(row['observed']['note_cited'], row['id'])
        latin = rows['ce1-divergence-ensure-ascii-latin']
        self.assertEqual(latin['observed']['capital_bytes'], '{"s":"caf\\u00e9"}')
        self.assertEqual(latin['observed']['ce1_bytes'], '{"s":"café"}')
        digest = rows['ce1-divergence-digest']
        self.assertNotEqual(
            digest['observed']['capital_sha256'],
            digest['observed']['ce1_bytes_sha256'])

    def test_gate_rejects_before_hashing_directly(self):
        for spec, code in (
                ({'payload': '{"a":1,"a":2}'}, 'DUPLICATE_KEY'),
                ({'payload': '{"n":NaN}'}, 'NONSTANDARD_CONSTANT'),
                ({'payload': '{"n":9007199254740992}'}, 'UNSAFE_INTEGER'),
                ({'payload': '{"é":1}'}, 'INVALID_KEY'),
                ({'payload_nest': 66}, 'MAX_DEPTH'),
        ):
            with self.assertRaises(InputRejected) as caught:
                decode_input(spec)
            self.assertEqual(caught.exception.code, code)

    def test_missing_field_rejects_the_table(self):
        for mutation in ('section', 'input', 'expected', 'needle'):
            table = copy.deepcopy(load_table())
            del table['claims'][0][mutation]
            with self.assertRaises(ClaimTableError):
                validate_table(table)
            with tempfile.TemporaryDirectory() as tmp:
                path = _write_table(tmp, table)
                with self.assertRaises(ClaimTableError):
                    load_table(path)
                proc = _run(['--execute', '--table', str(path)])
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn('CLAIM_CONFORMANCE passed=', proc.stdout)

    def test_wrong_format_label_or_pin_rejects(self):
        for field, value in (
                ('format', 'KIX_CAPITAL_UPSTREAM_CLAIMS_V1'),
                ('label', 'SEMANTIC_' + 'CONFORMANCE'),
                ('pinned_sha', 'e2a029d8ac3af7575888dac22fc4bf173ebec232')):
            table = copy.deepcopy(load_table())
            table[field] = value
            with self.assertRaises(ClaimTableError):
                validate_table(table)

    def test_divergence_shape_is_validated(self):
        table = copy.deepcopy(load_table())
        target = next(
            claim for claim in table['claims']
            if claim.get('disposition') == 'DOCUMENTED_DIVERGENCE')
        for mutation in (
                lambda claim: claim.pop('divergence'),
                lambda claim: claim['divergence'].pop('rationale_needle'),
                lambda claim: claim.update(
                    {'divergence': dict(claim['divergence'], binding_note='docs/OTHER.md')}),
                lambda claim: claim.update({'check_id': 'ce1.encode'}),
        ):
            broken = copy.deepcopy(table)
            mutation(next(
                claim for claim in broken['claims']
                if claim['id'] == target['id']))
            with self.assertRaises(ClaimTableError):
                validate_table(broken)
        conforming = copy.deepcopy(table)
        target = next(
            claim for claim in conforming['claims']
            if claim.get('disposition') != 'DOCUMENTED_DIVERGENCE')
        target['divergence'] = {
            'binding_note': 'docs/decisions/CAPITAL_UPSTREAM_BINDING.md',
            'binding_section': '### 3.4 stage7_authenticated_export',
            'rationale_needle': 'ensure_ascii',
        }
        with self.assertRaises(ClaimTableError):
            validate_table(conforming)

    def test_unmapped_check_fails_only_that_claim(self):
        table = copy.deepcopy(load_table())
        table['claims'].append({
            'id': 'mut-unmapped',
            'source_doc': SOURCE_DOC,
            'section': '## 바이트 규칙',
            'pinned_sha': PINNED_SHA,
            'claim': 'This id is not a registered check.',
            'check_id': 'ce1.not.a.check',
            'needle': 'BOM 없는 UTF-8 JSON',
            'input': {'value': None},
            'expected': None,
        })
        result = run_claims(table)
        failed = [row for row in result['rows'] if not row['ok']]
        self.assertEqual([row['id'] for row in failed], ['mut-unmapped'])
        self.assertTrue(failed[0]['unmapped'])
        self.assertIsNone(failed[0]['observed'])
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertIn('FAIL mut-unmapped', proc.stderr)

    def test_flipping_expected_fails_exactly_that_claim(self):
        original = load_table()
        for claim_id in (
                'ce1-compact-separators', 'ce1-reject-duplicate-key',
                'ce1-framed-digest-overlay', 'ce1-divergence-ensure-ascii-latin'):
            table = copy.deepcopy(original)
            target = next(claim for claim in table['claims'] if claim['id'] == claim_id)
            target['expected'] = _flip(target['expected'])
            with tempfile.TemporaryDirectory() as tmp:
                path = _write_table(tmp, table)
                loaded = load_table(path)
            result = run_claims(loaded)
            failed = [row for row in result['rows'] if not row['ok']]
            self.assertEqual([row['id'] for row in failed], [claim_id], claim_id)
            self.assertFalse(failed[0]['unmapped'])
            self.assertNotEqual(failed[0]['observed'], failed[0]['expected'])
        table = copy.deepcopy(original)
        target = next(claim for claim in table['claims'] if claim['id'] == 'ce1-compact-separators')
        target['expected'] = '{"b":1,"a":[true,null]}'
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertIn('FAIL ce1-compact-separators', proc.stderr)

    def test_missing_protocol_dir_is_skipped_and_not_a_success_line(self):
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
        table = load_table()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _protocol_tree(root, table)
            files = [path for path in root.rglob('*') if path.is_file()]
            for path in files:
                path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            root.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            try:
                proc = _run(['--protocol-dir', str(root)])
                report = check_protocol(root, table)
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

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _protocol_tree(root, table)
            target = root / SOURCE_DOC
            original = target.read_text(encoding='utf-8')
            claim = next(
                c for c in table['claims']
                if original.count(c['needle']) == 1)
            target.write_text(
                original.replace(claim['needle'], 'NEEDLE_REMOVED', 1), encoding='utf-8')
            before = _snapshot(root)
            proc = _run(['--protocol-dir', str(root)])
            after = _snapshot(root)
        self.assertEqual(before, after)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn('SKIPPED', proc.stdout)
        self.assertNotIn('passed', proc.stdout)
        self.assertIn(f"DRIFT {claim['id']} missing needle", proc.stderr)
        self.assertEqual(proc.stderr.count('missing needle'), 1)

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
        total = len(load_table()['claims'])
        proc = _run(['--execute'])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, f'CLAIM_CONFORMANCE passed={total} total={total} failed=0\n')
        self.assertEqual(proc.stderr, '')
        self.assertNotIn(PROFILE_TOKEN, proc.stdout)

    def test_acceptance_stage_runs_the_checker_last(self):
        acceptance = _acceptance()
        plan = [stage for stage in acceptance.build_plan(ROOT) if stage['id'] == 'upstream-claims']
        self.assertEqual(len(plan), 1)
        self.assertEqual(
            plan[0]['commands'][3][1:], ['scripts/ce1_claims_check.py', '--execute'])
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'acceptance-evidence.json'
            code = acceptance.execute_plan(
                plan, root=ROOT, evidence_path=evidence, required=('upstream-claims',))
            data = json.loads(evidence.read_text(encoding='utf-8'))
        self.assertEqual(code, 0)
        self.assertTrue(data['ok'])
        stage = data['stages'][0]
        self.assertEqual(stage['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(stage['status'], 'passed')
        self.assertEqual(stage['passed'], stage['total'])
        self.assertEqual(stage['test_count']['failed'], 0)
        self.assertNotIn(PROFILE_TOKEN, json.dumps(data))
        for command in stage['commands']:
            self.assertNotIn(PROFILE_TOKEN, command['output_tail'])


if __name__ == '__main__':
    unittest.main()
