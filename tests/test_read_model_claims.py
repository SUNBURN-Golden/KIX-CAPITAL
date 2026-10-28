"""READ_MODEL_QUERIES CLAIM_CONFORMANCE table: rows, mutation, scoped drift, acceptance stage."""
import copy
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.read_model_claims import (
    CHECKS,
    ERROR_CODES,
    KEYSET_SECTIONS,
    PINNED_SHA,
    REQUIRED_FIELDS,
    SOURCE_DOC,
    ClaimTableError,
    check_protocol,
    draft_flags,
    draft_keys,
    load_table,
    run_claims,
    section_text,
    validate_table,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'read_model_claims_check.py'
PROFILE_TOKEN = 'SEMANTIC' + '_CONFORMANCE'
REAL_DRAFT = Path('/workspace/capital-run/kixproto-ro')

ACCEPTANCE_IDS = {
    'rm-keyset-settlement',
    'rm-keyset-credit-advance',
    'rm-keyset-credit-claim',
    'rm-error-codes',
    'rm-envelope-version',
    'rm-envelope-fixture-mode',
    'rm-envelope-accepted-advance',
    'rm-envelope-visibility',
    'rm-non-mutation',
}
CHECK_PREFIXES = (
    'keyset.', 'field.credit_advance.', 'field.credit_claim.', 'field.settlement.',
    'error.unknown.', 'error.invalid.', 'error.codes', 'envelope.', 'body.unmodified',
    'claim.', 'advance.', 'settlement.', 'nonmutation.',
)


def _other_claim_total():
    from capital.ce1_claims import load_table as ce1
    from capital.adapter_identity_claims import load_table as identity
    from capital.lifecycle_claims import load_table as lifecycle
    return sum(len(load()['claims']) for load in (ce1, identity, lifecycle))


def _acceptance():
    spec = importlib.util.spec_from_file_location('acceptance_read_model', ROOT / 'scripts' / 'acceptance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(args, script=SCRIPT):
    return subprocess.run(
        [sys.executable, str(script), *args], cwd=ROOT, capture_output=True, text=True)


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
        return value + ['EXTRA']
    if type(value) is dict:
        return dict(value, code='BROKEN')
    raise AssertionError(repr(value))


def _write_table(directory, table):
    path = Path(directory) / 'claims.json'
    path.write_text(json.dumps(table), encoding='utf-8')
    return path


def _draft_text(table):
    """A small stand-in for the draft that has the shape the drift parser reads."""
    expected = {row['check_id']: row['expected'] for row in table['claims']
                if row['check_id'].startswith('keyset.')}
    flags = [row['check_id'].rsplit('.', 1)[1] for row in table['claims']
             if row['check_id'].startswith('field.credit_claim.')
             and row['check_id'].rsplit('.', 1)[1] not in ('provenance',)]
    advance_lead = ['provenance', 'lifecycle_authority', 'exposure_ledger']
    advance_keys = [k for k in expected['keyset.credit_advance'] if k not in advance_lead and k not in flags]
    claim_keys = [k for k in expected['keyset.credit_claim'] if k not in flags]

    def names(items):
        return ', '.join(f'`{item}`' for item in items)

    bullets = {
        KEYSET_SECTIONS['settlement']: (
            '- **노출 상태.** `SettlementMachine.view`의 `_view`를 그대로 쓴다.\n'
            f'  키: {names(expected["keyset.settlement"])}.'),
        KEYSET_SECTIONS['credit_advance']: (
            '- **노출 상태.** `CreditMachine.view`의 `_view`를 그대로 쓴다. '
            '`provenance`는 `MOCK_CREDIT_F04_ONLY`. `lifecycle_authority`는 `IN_MEMORY_FSM`. '
            '`exposure_ledger`는 `MOCK_EXPOSURE`.\n'
            f'  키: {names(advance_keys)}, 그리고 `mock_credit._flags`의 항상 거짓 플래그 ({names(flags)}).'),
        KEYSET_SECTIONS['credit_claim']: (
            '- **노출 상태.** `CreditMachine.view_claim`이 반환하는 `MockCredit._view_claim`을 그대로 쓴다.\n'
            f'  키: {names(claim_keys)}, 그리고 §2.12와 같은 `_flags`.'),
    }
    order = []
    for row in table['claims']:
        if row['section'] not in order:
            order.append(row['section'])
    out = ['# 조회·목록 쿼리 — 초안 0.1', '']
    for section in order:
        out.append(section)
        out.append('')
        if section in bullets:
            out.append(bullets[section])
            out.append('- **행위자 가시성.** 다음 항목.')
        for row in table['claims']:
            if row['section'] == section:
                out.append(f'- {row["needle"]}')
        out.append('')
    return '\n'.join(out)


def _tree(root, table, text=None):
    path = Path(root) / SOURCE_DOC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_draft_text(table) if text is None else text, encoding='utf-8')
    return path


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob('*')) if p.is_file()}


class ReadModelClaimsTests(unittest.TestCase):
    def test_table_has_required_fields_and_every_claim_passes(self):
        table = load_table()
        self.assertGreaterEqual(len(table['claims']), 60)
        self.assertEqual(table['pinned_sha'], PINNED_SHA)
        self.assertEqual(PINNED_SHA, '244595db1524cbb1a01148baa07d6d28cd1b8dc6')
        self.assertEqual(table['format'], 'KIX_CAPITAL_READ_MODEL_CLAIMS_V1')
        self.assertEqual(table['label'], 'CLAIM_CONFORMANCE')
        seen = set()
        for claim in table['claims']:
            for field in REQUIRED_FIELDS:
                self.assertIsInstance(claim[field], str)
                self.assertTrue(claim[field].strip())
            self.assertIn('expected', claim)
            self.assertEqual(claim['pinned_sha'], PINNED_SHA)
            self.assertEqual(claim['source_doc'], SOURCE_DOC)
            self.assertIn(claim['check_id'], CHECKS)
            self.assertNotIn(claim['id'], seen)
            seen.add(claim['id'])
            self.assertNotIn(PROFILE_TOKEN, claim['claim'])
        result = run_claims(table)
        self.assertTrue(result['ok'], result['failed'])
        self.assertEqual(result['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(result['passed'], result['total'])
        for row in result['rows']:
            self.assertFalse(row['unmapped'])

    def test_acceptance_rows_pin_the_key_sets_flags_and_errors(self):
        table = load_table()
        ids = {claim['id'] for claim in table['claims']}
        self.assertTrue(ACCEPTANCE_IDS <= ids, ACCEPTANCE_IDS - ids)
        for prefix in CHECK_PREFIXES:
            self.assertTrue(any(c['check_id'].startswith(prefix) for c in table['claims']), prefix)
        rows = {row['id']: row for row in run_claims(table)['rows']}
        self.assertEqual(
            [len(rows[i]['observed']) for i in (
                'rm-keyset-settlement', 'rm-keyset-credit-advance', 'rm-keyset-credit-claim')],
            [25, 51, 24])
        self.assertEqual(rows['rm-error-codes']['observed'], ERROR_CODES)
        self.assertEqual(rows['rm-envelope-visibility']['observed'], [False, 'UNDETERMINED'])
        self.assertIs(rows['rm-non-mutation']['observed'], True)
        flag_rows = [c for c in table['claims'] if c['id'].startswith(('rm-advance-flag-', 'rm-claim-flag-'))]
        self.assertGreaterEqual(len(flag_rows), 33)
        for claim in flag_rows:
            self.assertIs(claim['expected'], False)

    def test_missing_field_rejects_the_table(self):
        table = copy.deepcopy(load_table())
        del table['claims'][0]['section']
        with self.assertRaises(ClaimTableError):
            validate_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(['--execute', '--table', str(_write_table(tmp, table))])
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('CLAIM_CONFORMANCE passed=', proc.stdout)

    def test_wrong_format_label_or_pin_rejects_the_table(self):
        original = load_table()
        for field, value in (
            ('format', 'KIX_CAPITAL_AGENT_CLAIMS_V1'),
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
            'id': 'mut-unmapped', 'source_doc': SOURCE_DOC, 'section': '## 8. 비변경',
            'pinned_sha': PINNED_SHA, 'claim': 'Not a registered check.',
            'route': 'CapitalService.read_query', 'check_id': 'not.a.real.check', 'needle': '`canonical_state()`', 'expected': None,
        })
        result = run_claims(table)
        failed = [row for row in result['rows'] if not row['ok']]
        self.assertEqual([row['id'] for row in failed], ['mut-unmapped'])
        self.assertTrue(failed[0]['unmapped'])
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(['--execute', '--table', str(_write_table(tmp, table))])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertEqual(proc.stderr.strip(), 'FAIL mut-unmapped observed=None expected=None')

    def test_flipping_one_expected_fails_exactly_that_claim(self):
        original = load_table()
        samples = (
            'rm-keyset-credit-advance', 'rm-keyset-credit-claim', 'rm-keyset-settlement',
            'rm-advance-flag-funds-executed', 'rm-claim-flag-interest-defined',
            'rm-settlement-flag-durable', 'rm-error-codes', 'rm-envelope-version',
            'rm-envelope-fixture-mode', 'rm-envelope-visibility', 'rm-non-mutation',
            'rm-claim-unknown-before-draw', 'rm-claim-no-lifecycle-authority',
            'rm-envelope-accepted-settlement',
        )
        for claim_id in samples:
            table = copy.deepcopy(original)
            target = next(c for c in table['claims'] if c['id'] == claim_id)
            target['expected'] = _flip(target['expected'])
            result = run_claims(table)
            failed = [row for row in result['rows'] if not row['ok']]
            self.assertEqual([row['id'] for row in failed], [claim_id], claim_id)
            self.assertFalse(failed[0]['unmapped'])
        table = copy.deepcopy(original)
        next(c for c in table['claims'] if c['id'] == 'rm-advance-flag-funds-executed')['expected'] = True
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(['--execute', '--table', str(_write_table(tmp, table))])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.strip(), 'FAIL rm-advance-flag-funds-executed observed=False expected=True')

    def test_a_dropped_or_added_body_key_would_fail_the_key_set_row(self):
        from capital import service as service_module
        real = service_module.CapitalService._read_body

        def extra(self, kind, ident):
            body = real(self, kind, ident)
            body['not_in_the_draft'] = False
            return body

        def short(self, kind, ident):
            body = real(self, kind, ident)
            del body['funds_executed']
            return body

        for patched in (extra, short):
            service_module.CapitalService._read_body = patched
            try:
                result = run_claims(load_table())
            finally:
                service_module.CapitalService._read_body = real
            failed = {row['id'] for row in result['failed']}
            self.assertTrue({'rm-keyset-settlement', 'rm-keyset-credit-advance',
                             'rm-keyset-credit-claim'} <= failed, patched.__name__)

    def test_missing_protocol_dir_is_skipped_and_not_a_success_line(self):
        for args in ((), ('--protocol-dir', ''), ('--protocol-dir', '   ')):
            proc = _run(list(args))
            self.assertEqual(proc.returncode, 0, args)
            lines = proc.stdout.splitlines()
            self.assertEqual(lines[0], 'SKIPPED')
            payload = json.loads(lines[1])
            self.assertEqual(payload['status'], 'SKIPPED')
            self.assertEqual(payload['label'], 'CLAIM_CONFORMANCE')
            self.assertEqual(payload['rows'], 'not-run')
            self.assertNotIn('passed', proc.stdout)
            self.assertNotIn('verified', proc.stdout)
            self.assertNotIn(PROFILE_TOKEN, proc.stdout)

    def test_execute_prints_the_count_line(self):
        total = len(load_table()['claims'])
        proc = _run(['--execute'])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, f'CLAIM_CONFORMANCE passed={total} total={total} failed=0\n')
        self.assertEqual(proc.stderr, '')


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.table = load_table()

    def test_stand_in_draft_is_parsed_into_the_pinned_key_lists(self):
        text = _draft_text(self.table)
        for kind in KEYSET_SECTIONS:
            row = next(c for c in self.table['claims'] if c['check_id'] == f'keyset.{kind}')
            self.assertEqual(draft_keys(text, kind), row['expected'], kind)
        self.assertEqual(len(draft_flags(text)), 14)

    def test_section_text_is_scoped_to_one_heading(self):
        text = '# t\n\n### 2.1 `a`\n\none\n\n### 2.2 `b`\n\ntwo\n\n## 3. next\n\nthree\n'
        self.assertEqual(section_text(text, '### 2.1 `a`').split(), ['one'])
        self.assertEqual(section_text(text, '### 2.2 `b`').split(), ['two'])
        self.assertIsNone(section_text(text, '### 2.9 `none`'))
        self.assertIsNone(section_text(text + '\n### 2.1 `a`\n', '### 2.1 `a`'))

    def test_protocol_dir_verifies_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _tree(root, self.table)
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            try:
                before = _snapshot(root)
                proc = _run(['--protocol-dir', str(root)])
                report = check_protocol(root, self.table)
                after = _snapshot(root)
            finally:
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(before, after)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        total = len(self.table['claims'])
        self.assertEqual(
            proc.stdout.splitlines(),
            [f'CLAIM_CONFORMANCE passed={total} total={total} failed=0',
             f'CLAIM_DRIFT verified={total} total={total}'])
        self.assertEqual(report['status'], 'verified')
        self.assertNotIn('SKIPPED', proc.stdout)

    def test_a_key_dropped_or_added_in_the_draft_fails_that_key_set_row(self):
        text = _draft_text(self.table)
        claim_at = text.index(KEYSET_SECTIONS['credit_claim'])
        mutations = {
            'rm-keyset-settlement': text.replace('`durable`, ', '', 1),
            'rm-keyset-credit-advance': text.replace('`next_repayment_sequence`, ', '', 1),
            'rm-keyset-credit-claim': text[:claim_at] + text[claim_at:].replace(
                '`snapshot_frozen`, ', '`snapshot_frozen`, `new_key`, ', 1),
        }
        for claim_id, mutated in mutations.items():
            self.assertNotEqual(mutated, text, claim_id)
            with tempfile.TemporaryDirectory() as tmp:
                _tree(tmp, self.table, mutated)
                report = check_protocol(tmp, self.table)
                proc = _run(['--protocol-dir', tmp])
            ids = {item['id'] for item in report['missing']}
            self.assertIn(claim_id, ids, claim_id)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(proc.returncode, 1)
            self.assertIn(f'DRIFT {claim_id} key list differs from the draft', proc.stderr)

    def test_a_flag_dropped_from_section_2_12_fails_both_flag_sharing_rows(self):
        text = _draft_text(self.table)
        mutated = text.replace('`interest_defined`', '', 1)
        with tempfile.TemporaryDirectory() as tmp:
            _tree(tmp, self.table, mutated)
            report = check_protocol(tmp, self.table)
        ids = {item['id'] for item in report['missing']}
        self.assertTrue({'rm-keyset-credit-advance', 'rm-keyset-credit-claim'} <= ids)

    def test_a_needle_found_only_in_another_section_is_missing(self):
        text = _draft_text(self.table)
        claim = next(c for c in self.table['claims'] if c['id'] == 'rm-claim-no-lifecycle-authority')
        needle = claim['needle']
        self.assertEqual(text.count(needle), 1)
        moved = text.replace(f'- {needle}\n', '', 1) + f'\n## 9. elsewhere\n\n- {needle}\n'
        with tempfile.TemporaryDirectory() as tmp:
            _tree(tmp, self.table, moved)
            report = check_protocol(tmp, self.table)
            proc = _run(['--protocol-dir', tmp])
        self.assertEqual([item['id'] for item in report['missing']], [claim['id']])
        self.assertEqual(report['missing'][0]['problem'], 'missing needle')
        self.assertIn(f"DRIFT {claim['id']} missing needle", proc.stderr)

    def test_a_missing_or_duplicated_heading_is_reported(self):
        text = _draft_text(self.table)
        heading = KEYSET_SECTIONS['credit_claim']
        ids = {c['id'] for c in self.table['claims'] if c['section'] == heading}
        for mutated in (text.replace(heading, '### 2.13 `renamed`', 1), text + f'\n{heading}\n'):
            with tempfile.TemporaryDirectory() as tmp:
                _tree(tmp, self.table, mutated)
                report = check_protocol(tmp, self.table)
            self.assertEqual(report['status'], 'failed')
            if heading in mutated and mutated.count(heading) > 1:
                self.assertTrue(ids <= {item['id'] for item in report['missing']})

    def test_non_directory_protocol_path_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / 'notes.md'
            file_path.write_text('heading', encoding='utf-8')
            for target in (file_path, Path(tmp) / 'missing-checkout'):
                proc = _run(['--protocol-dir', str(target)])
                self.assertEqual(proc.returncode, 1)
                self.assertNotIn('SKIPPED', proc.stdout)
                self.assertIn('verified=0', proc.stdout)
                self.assertIn('protocol dir is not a directory', proc.stderr)

    @unittest.skipUnless((REAL_DRAFT / SOURCE_DOC).is_file(), 'no read-only kix-protocol checkout here')
    def test_real_draft_matches_when_a_checkout_is_present(self):
        report = check_protocol(REAL_DRAFT, self.table)
        self.assertEqual(report['status'], 'verified', report['missing'])
        self.assertEqual(report['verified'], len(self.table['claims']))


class AcceptanceStageTests(unittest.TestCase):
    def stage(self, protocol_dir=None):
        acceptance = _acceptance()
        plan = [s for s in acceptance.build_plan(ROOT, protocol_dir) if s['id'] == 'upstream-claims']
        self.assertEqual(len(plan), 1)
        return acceptance, plan

    def run_stage(self, acceptance, plan):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'acceptance-evidence.json'
            code = acceptance.execute_plan(
                plan, root=ROOT, evidence_path=evidence, required=('upstream-claims',))
            return code, json.loads(evidence.read_text(encoding='utf-8'))

    def test_stage_runs_the_rows_skipped_without_a_protocol_dir(self):
        from capital.agent_claims import load_table as load_agent
        from capital.upstream_claims import load_table as load_upstream
        acceptance, plan = self.stage()
        commands = plan[0]['commands']
        self.assertEqual(commands[0][1:], ['scripts/upstream_claims_check.py', '--execute'])
        self.assertEqual(commands[1][1:], ['scripts/agent_claims_check.py', '--execute'])
        self.assertEqual(commands[2][1:], ['scripts/read_model_claims_check.py'])
        code, data = self.run_stage(acceptance, plan)
        self.assertEqual(code, 0)
        stage = data['stages'][0]
        self.assertEqual(stage['status'], 'passed')
        self.assertEqual(stage['label'], 'CLAIM_CONFORMANCE')
        self.assertEqual(stage['skipped'], ['scripts/read_model_claims_check.py'])
        self.assertEqual([c['skipped'] for c in stage['commands']], [False, False, True, False, False, False])
        total = len(load_upstream()['claims']) + len(load_agent()['claims']) + _other_claim_total()
        self.assertEqual((stage['passed'], stage['total']), (total, total))
        self.assertTrue(stage['commands'][2]['output_tail'].startswith('SKIPPED'))
        self.assertIsNone(stage['commands'][2]['test_count'])
        self.assertNotIn(PROFILE_TOKEN, json.dumps(data))

    def test_stage_counts_the_rows_when_a_protocol_dir_is_given(self):
        from capital.agent_claims import load_table as load_agent
        from capital.upstream_claims import load_table as load_upstream
        table = load_table()
        with tempfile.TemporaryDirectory() as tmp:
            _tree(tmp, table)
            acceptance, plan = self.stage(tmp)
            self.assertEqual(plan[0]['commands'][2][1:], ['scripts/read_model_claims_check.py',
                                                          '--protocol-dir', tmp])
            code, data = self.run_stage(acceptance, plan)
        self.assertEqual(code, 0)
        stage = data['stages'][0]
        self.assertEqual(stage['skipped'], [])
        total = len(load_upstream()['claims']) + len(load_agent()['claims']) + _other_claim_total() + len(table['claims'])
        self.assertEqual((stage['passed'], stage['total']), (total, total))

    def test_a_failing_row_fails_the_stage(self):
        table = copy.deepcopy(load_table())
        next(c for c in table['claims'] if c['id'] == 'rm-envelope-version')['expected'] = '9.9'
        with tempfile.TemporaryDirectory() as tmp:
            _tree(tmp, table)
            path = Path(tmp) / 'claims.json'
            path.write_text(json.dumps(table), encoding='utf-8')
            proc = _run(['--protocol-dir', tmp, '--table', str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('failed=1', proc.stdout)
        self.assertIn('FAIL rm-envelope-version', proc.stderr)


if __name__ == '__main__':
    unittest.main()
