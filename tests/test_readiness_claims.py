"""Readiness-boundary CLAIM_CONFORMANCE table, mutation, drift, divergence, and stage tests."""
import copy
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.readiness_claims import (
    CHECKS,
    DIVERGENCE_CHECKS,
    FORMAT,
    PINNED_SHA,
    REQUIRED_FIELDS,
    SOURCE_DOC,
    ClaimTableError,
    check_protocol,
    load_table,
    run_claims,
    validate_table,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'readiness_claims_check.py'
PROFILE_TOKEN = 'SEMANTIC' + '_CONFORMANCE'


def _acceptance():
    spec = importlib.util.spec_from_file_location('acceptance_readiness', ROOT / 'scripts' / 'acceptance.py')
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
    if type(value) is list:
        return [_flip(value[0])] + list(value[1:])
    if type(value) is dict:
        flipped = dict(value)
        key = next(iter(flipped))
        flipped[key] = _flip(flipped[key])
        return flipped
    raise AssertionError(repr(value))


class ReadinessClaimsTests(unittest.TestCase):
    def test_table_has_required_fields_and_every_claim_passes(self):
        table = load_table()
        self.assertEqual(table['format'], FORMAT)
        self.assertEqual(table['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(table['pinned_sha'], PINNED_SHA)
        self.assertEqual(table['pin_class'], 'EXECUTABLE_VENDOR')
        self.assertIn('consumption_scope', table)
        seen = set()
        divergence = 0
        for claim in table['claims']:
            for field in REQUIRED_FIELDS:
                self.assertIsInstance(claim[field], str)
                self.assertTrue(claim[field].strip())
            self.assertEqual(claim['source_doc'], SOURCE_DOC)
            self.assertEqual(claim['pinned_sha'], PINNED_SHA)
            self.assertIn('expected', claim)
            self.assertTrue(claim['needle'])
            self.assertIn(claim['check_id'], CHECKS)
            self.assertNotIn(claim['id'], seen)
            seen.add(claim['id'])
            self.assertNotIn(PROFILE_TOKEN, claim['claim'])
            if claim.get('disposition') == 'DOCUMENTED_DIVERGENCE':
                divergence += 1
                self.assertIn('divergence', claim)
        self.assertEqual(divergence, len(DIVERGENCE_CHECKS))
        result = run_claims(table)
        self.assertTrue(result['ok'], result['failed'])
        self.assertEqual(result['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(result['passed'], result['total'] - divergence)
        self.assertEqual(result['failed'], [])
        self.assertEqual(len(result['documented_divergences']), divergence)
        for row in result['rows']:
            self.assertFalse(row['unmapped'])

    def test_divergence_rows_record_divergence_and_cite_the_handbook(self):
        result = run_claims(load_table())
        rows = {
            row['id']: row for row in result['rows']
            if row['disposition'] == 'DOCUMENTED_DIVERGENCE'}
        self.assertEqual(set(rows), {'readiness-torn-tail', 'readiness-failed-save-lookup'})
        for row in rows.values():
            self.assertTrue(row['ok'], row['id'])
            self.assertTrue(row['observed']['divergent'], row['id'])
            self.assertTrue(row['observed']['note_cited'], row['id'])
        self.assertEqual(
            rows['readiness-torn-tail']['observed']['workspace_status'], 'WORKSPACE_UNREADABLE')
        self.assertEqual(
            rows['readiness-failed-save-lookup']['observed']['lookup_outcome'], 'ACCEPTED')

    def test_missing_field_rejects_the_table(self):
        for mutation in ('section', 'surface', 'expected', 'needle'):
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

    def test_source_doc_surface_and_disposition_are_validated(self):
        original = load_table()
        for mutate in (
                lambda claim: claim.update({'source_doc': 'docs/contracts/OTHER.md'}),
                lambda claim: claim.update({'surface': 'GET /api/nope'}),
                lambda claim: claim.update({'disposition': 'WAIVER'}),
        ):
            table = copy.deepcopy(original)
            mutate(table['claims'][0])
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
                lambda claim: claim['divergence'].pop('capital_behavior'),
                lambda claim: claim.update(
                    {'divergence': dict(claim['divergence'], capital_note='docs/OTHER.md')}),
                lambda claim: claim.update(
                    {'divergence': dict(claim['divergence'], note_section='### other-section')}),
                lambda claim: claim.update({'check_id': 'readiness.bind_loopback'}),
                lambda claim: (claim.pop('divergence'), claim.pop('disposition')),
        ):
            broken = copy.deepcopy(table)
            mutation(next(
                claim for claim in broken['claims']
                if claim['id'] == target['id']))
            with self.assertRaises(ClaimTableError):
                validate_table(broken)
        conforming = copy.deepcopy(load_table())
        target = next(
            claim for claim in conforming['claims']
            if claim.get('disposition') != 'DOCUMENTED_DIVERGENCE')
        target['divergence'] = {
            'capital_note': 'docs/OPERATOR_HANDBOOK_KO.md',
            'note_section': '### readiness-runtime-claims',
            'rationale_needle': 'x',
            'upstream_behavior': 'u',
            'capital_behavior': 'c',
        }
        with self.assertRaises(ClaimTableError):
            validate_table(conforming)

    def test_unmapped_check_fails_only_that_claim(self):
        table = copy.deepcopy(load_table())
        table['claims'].append({
            'id': 'mut-unmapped',
            'source_doc': SOURCE_DOC,
            'section': '## 파일 저널',
            'pinned_sha': PINNED_SHA,
            'claim': 'This id is not a registered check.',
            'check_id': 'readiness.not_a_check',
            'needle': '저널',
            'surface': 'GET /api/state',
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
        for claim in original['claims']:
            for predicate in claim['expected']:
                with self.subTest(claim=claim['id'], predicate=predicate):
                    table = copy.deepcopy(original)
                    # Each probe still executes the real live-server check.
                    # Unrelated rows are covered by the full-table test above.
                    table['claims'] = [copy.deepcopy(claim)]
                    target = table['claims'][0]
                    target['expected'][predicate] = _flip(target['expected'][predicate])
                    with tempfile.TemporaryDirectory() as tmp:
                        path = _write_table(tmp, table)
                        loaded = load_table(path)
                    result = run_claims(loaded)
                    failed = [row for row in result['rows'] if not row['ok']]
                    self.assertEqual([row['id'] for row in failed], [claim['id']])
                    self.assertFalse(failed[0]['unmapped'])
                    self.assertNotEqual(failed[0]['observed'], failed[0]['expected'])

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
            root.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IXOTH)
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
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0],
                         f'CLAIM_CONFORMANCE passed={total - 2} total={total} failed=0 documented_divergences=2')
        self.assertEqual(lines[1:3], [
            'DOCUMENTED_DIVERGENCE readiness-failed-save-lookup',
            'DOCUMENTED_DIVERGENCE readiness-torn-tail'])
        self.assertEqual(lines[3], 'SKIPPED')
        self.assertEqual(json.loads(lines[4])['status'], 'SKIPPED')
        self.assertEqual(proc.stderr, '')
        self.assertNotIn(PROFILE_TOKEN, proc.stdout)

    def test_acceptance_stage_runs_the_checker_fifth_and_last(self):
        from capital.agent_claims import load_table as load_agent
        from capital.ce1_claims import load_table as load_ce1
        from capital.read_model_claims import load_table as load_read_model
        from capital.upstream_claims import load_table as load_upstream
        acceptance = _acceptance()
        plan = [stage for stage in acceptance.build_plan(ROOT) if stage['id'] == 'upstream-claims']
        self.assertEqual(len(plan), 1)
        commands = plan[0]['commands']
        self.assertEqual(len(commands), 5)
        self.assertEqual(
            commands[4][1:], ['scripts/readiness_claims_check.py', '--execute'])
        expected_total = (
            len(load_upstream()['claims'])
            + len(load_agent()['claims'])
            + len(load_read_model()['claims'])
            + len(load_ce1()['claims'])
            + len(load_table()['claims']))
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
        self.assertEqual(stage['total'], expected_total)
        self.assertEqual(stage['passed'], stage['total'] - 2)
        self.assertEqual(stage['documented_divergences'], 2)
        self.assertEqual(stage['test_count']['failed'], 0)
        self.assertNotIn(PROFILE_TOKEN, json.dumps(data))
        for command in stage['commands']:
            self.assertNotIn(PROFILE_TOKEN, command['output_tail'])


if __name__ == '__main__':
    unittest.main()
