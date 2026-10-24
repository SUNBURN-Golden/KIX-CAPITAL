"""Read-model CLAIM_CONFORMANCE table, mutation, drift, and the acceptance stage."""
import copy
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.read_model_claims import (
    CHECKS,
    PINNED_SHA,
    REQUIRED_FIELDS,
    ROUTES,
    SECTION_ADVANCE,
    SECTION_CLAIM,
    SECTION_NONMUTATION,
    SOURCE_DOC,
    ClaimTableError,
    check_protocol,
    load_table,
    run_claims,
    validate_table,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'read_model_claims_check.py'
UPSTREAM_SCRIPT = ROOT / 'scripts' / 'upstream_claims_check.py'
PROFILE_TOKEN = 'SEMANTIC' + '_CONFORMANCE'

ACCEPTANCE_IDS = {
    'read-advance-phase',
    'read-claim-open-face',
    'read-advance-unknown',
    'read-claim-unknown',
    'read-readonly-state',
}
CHECK_PREFIXES = (
    'read.advance.',
    'read.claim.',
    'read.readonly.',
)
SECTIONS = (SECTION_ADVANCE, SECTION_CLAIM, SECTION_NONMUTATION)


def _acceptance():
    spec = importlib.util.spec_from_file_location('acceptance_claims', ROOT / 'scripts' / 'acceptance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(args, script=SCRIPT):
    return subprocess.run(
        [sys.executable, str(script), *args],
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


class ReadModelClaimsTests(unittest.TestCase):
    def test_table_has_required_fields_and_every_claim_passes(self):
        table = load_table()
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
            self.assertEqual(claim['source_doc'], SOURCE_DOC)
            self.assertIn(claim['route'], ROUTES)
            self.assertIn(claim['check_id'], CHECKS)
            self.assertNotIn(claim['id'], seen)
            seen.add(claim['id'])
            self.assertNotIn(PROFILE_TOKEN, claim['claim'])
        result = run_claims(table)
        self.assertTrue(result['ok'])
        self.assertEqual(result['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(result['passed'], result['total'])
        self.assertGreaterEqual(result['total'], 30)
        self.assertEqual(result['failed'], [])
        for row in result['rows']:
            self.assertFalse(row['unmapped'])

    def test_acceptance_rows_cover_the_required_queries(self):
        table = load_table()
        ids = {claim['id'] for claim in table['claims']}
        self.assertTrue(ACCEPTANCE_IDS <= ids, ACCEPTANCE_IDS - ids)
        check_ids = {claim['check_id'] for claim in table['claims']}
        for prefix in CHECK_PREFIXES:
            self.assertTrue(
                any(check_id.startswith(prefix) for check_id in check_ids), prefix)
        sections = {claim['section'] for claim in table['claims']}
        for section in SECTIONS:
            self.assertIn(section, sections)
        for route in ROUTES:
            self.assertIn(route, {claim['route'] for claim in table['claims']})
        rows = {row['id']: row for row in run_claims(table)['rows']}
        self.assertEqual(rows['read-advance-phase']['observed'], 'DRAWN')
        self.assertEqual(rows['read-claim-open-face']['observed'], 100000)
        self.assertEqual(rows['read-advance-unknown']['observed'], 'UNKNOWN_ADVANCE')
        self.assertEqual(rows['read-claim-unknown']['observed'], 'UNKNOWN_CLAIM')
        self.assertEqual(
            rows['read-readonly-state']['observed'],
            {'canonical_state': True, 'journal': True,
             'overlay_state_digest': True, 'operation_count': True})
        self.assertIs(rows['read-claim-no-lifecycle-key']['observed'], False)

    def test_missing_field_or_route_rejects_the_table(self):
        table = copy.deepcopy(load_table())
        del table['claims'][0]['section']
        with self.assertRaises(ClaimTableError):
            validate_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            with self.assertRaises(ClaimTableError):
                load_table(path)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('CLAIM_CONFORMANCE passed=', proc.stdout)
        for bad in (None, '', 'GET /api/evidence', 'get_credit_advance'):
            table = copy.deepcopy(load_table())
            table['claims'][0]['route'] = bad
            with self.assertRaises(ClaimTableError, msg=repr(bad)):
                validate_table(table)

    def test_wrong_format_label_or_pin_rejects_the_table(self):
        original = load_table()
        for field, value in (
            ('format', 'KIX_CAPITAL_UPSTREAM_CLAIMS_V1'),
            ('label', 'CLAIM_DRIFT'),
            ('pinned_sha', 'e2a029d8ac3af7575888dac22fc4bf173ebec232'),
        ):
            table = copy.deepcopy(original)
            table[field] = value
            with self.assertRaises(ClaimTableError, msg=field):
                validate_table(table)

    def test_unmapped_check_fails_only_that_claim(self):
        table = copy.deepcopy(load_table())
        table['claims'].append({
            'id': 'mut-unmapped',
            'source_doc': SOURCE_DOC,
            'section': SECTION_NONMUTATION,
            'pinned_sha': PINNED_SHA,
            'claim': 'This id is not a registered check.',
            'check_id': 'not.a.real.check',
            'needle': 'canonical_state()',
            'route': 'CreditMachine.view',
            'expected': None,
        })
        result = run_claims(table)
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
        original = load_table()
        samples = (
            'read-advance-phase',
            'read-advance-open-face',
            'read-claim-unknown',
            'read-advance-funds-executed-false',
            'read-claim-no-lifecycle-key',
        )
        for claim_id in samples:
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
        target = next(claim for claim in table['claims'] if claim['id'] == 'read-readonly-state')
        target['expected'] = dict(target['expected'], journal=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_table(tmp, table)
            proc = _run(['--execute', '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertIn('FAIL read-readonly-state', proc.stderr)

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

    def test_acceptance_stage_runs_all_claim_tables(self):
        from capital.agent_claims import load_table as load_agent
        from capital.upstream_claims import load_table as load_upstream
        acceptance = _acceptance()
        plan = [stage for stage in acceptance.build_plan(ROOT) if stage['id'] == 'upstream-claims']
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['commands'][0][1:], ['scripts/upstream_claims_check.py', '--execute'])
        self.assertEqual(plan[0]['commands'][1][1:], ['scripts/agent_claims_check.py', '--execute'])
        self.assertEqual(plan[0]['commands'][2][1:], ['scripts/read_model_claims_check.py', '--execute'])
        self.assertEqual(plan[0]['commands'][3][1:], ['scripts/ce1_claims_check.py', '--execute'])
        self.assertEqual(plan[0]['commands'][4][1:], ['scripts/adapter_identity_claims_check.py', '--execute'])
        from capital.adapter_identity_claims import load_table as load_identity
        from capital.ce1_claims import load_table as load_ce1
        from capital.lifecycle_claims import load_table as load_lifecycle
        self.assertEqual(plan[0]['commands'][5][1:], ['scripts/lifecycle_claims_check.py', '--execute'])
        expected_total = (
            len(load_lifecycle()['claims']) +
            len(load_upstream()['claims'])
            + len(load_agent()['claims'])
            + len(load_table()['claims'])
            + len(load_ce1()['claims'])
            + len(load_identity()['claims']))
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
        self.assertEqual(stage['passed'], stage['total'])
        self.assertEqual(stage['test_count']['failed'], 0)
        self.assertNotIn(PROFILE_TOKEN, json.dumps(data))
        for command in stage['commands']:
            self.assertNotIn(PROFILE_TOKEN, command['output_tail'])

    def test_read_model_script_and_upstream_script_report_separate_tables(self):
        read_total = len(load_table()['claims'])
        proc = _run(['--execute'])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, f'CLAIM_CONFORMANCE passed={read_total} total={read_total} failed=0\n')
        upstream = _run(['--execute'], script=UPSTREAM_SCRIPT)
        self.assertEqual(upstream.returncode, 0)
        self.assertNotEqual(proc.stdout, upstream.stdout)


if __name__ == '__main__':
    unittest.main()
