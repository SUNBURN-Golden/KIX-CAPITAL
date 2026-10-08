"""Decision-ledger validator and the index of capital-decision-v1 notes."""
import ast
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location('decision_ledger', ROOT / 'scripts' / 'decision_ledger.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger = _load()

ENTRY_NAMES = (
    'interest_rate',
    'fees',
    'term',
    'default_loss_treatment',
    'underwriting_depth',
    'external_collateral_completeness',
    'additional_margin',
    'collateral_execution',
    'reserve',
)


def _entry(status='ADOPTED', **overrides):
    body = {
        'status': status,
        'cap_rows': ['CAP-02'],
        'rationale': 'synthetic rationale',
        'provisional': True,
    }
    if status == 'ADOPTED':
        body['value'] = {'example': 1}
        body['provided_by'] = 'tester'
        body['date'] = '2026-10-08'
    body.update(overrides)
    return body


def _note(entries, blocks=1, raw=None):
    if raw is not None:
        fence = f'```capital-decision-v1\n{raw}\n```\n'
    else:
        payload = {
            'schema': 'capital-decision-v1',
            'decision_id': 'sample-decision',
            'entries': entries,
        }
        fence = '```capital-decision-v1\n' + json.dumps(payload, indent=2) + '\n```\n'
    if blocks == 0:
        return '# no block\n'
    return fence * blocks


class DecisionTests(unittest.TestCase):
    def test_script_does_not_import_capital(self):
        tree = ast.parse((ROOT / 'scripts' / 'decision_ledger.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            for name in names:
                self.assertFalse(name == 'capital' or name.startswith('capital.'), name)

    def test_real_notes_pass_and_the_index_lists_entries(self):
        note = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
        errors, summary = ledger.validate_note(note)
        self.assertEqual(errors, [])
        self.assertEqual(summary['decision_id'], 'financial-terms-decision')
        self.assertEqual(summary['status'], 'PROVISIONAL_PRODUCT_DECISION')
        self.assertEqual(list(summary['entries']), list(ENTRY_NAMES))
        self.assertTrue(all(status == 'ADOPTED' for status in summary['entries'].values()))
        coverage = (ROOT / 'docs' / 'CAP_COVERAGE.md').read_text(encoding='utf-8')
        expected = ledger.expected_note_paths(coverage)
        rows = ledger.build_index(ROOT / 'docs' / 'decisions', expected)
        by_note = {row['note']: row for row in rows}
        self.assertEqual(by_note['docs/decisions/CAPITAL_FINANCIAL_TERMS.md']['entries'], summary['entries'])
        self.assertEqual(by_note['docs/decisions/revenue-participation.md']['status'], 'PENDING')
        self.assertEqual(by_note['docs/decisions/claim-purchase.md']['status'], 'PENDING')
        self.assertEqual(by_note['docs/decisions/revenue-participation.md']['entries'], {})
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = ledger.main([])
        self.assertEqual(code, 0)
        printed = buffer.getvalue()
        self.assertIn('interest_rate=ADOPTED', printed)
        self.assertIn('PENDING', printed)
        self.assertIn('revenue-participation.md', printed)

    def test_adopted_and_undetermined_rules(self):
        cases = [
            (_entry(provided_by=''), 'provided_by'),
            (_entry(), 'provided_by'),
            (_entry(date='2026-13-40'), 'date'),
            (_entry(status='UNDETERMINED', value={'no': True}), 'value'),
            (_entry(status='UNDETERMINED', provided_by='someone', date='2026-10-08'), 'provided_by'),
            (_entry(status='MAYBE'), 'status'),
        ]
        # The second case drops provided_by after construction.
        cases[1][0].pop('provided_by')
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index, (entry, needle) in enumerate(cases):
                path = directory / f'case-{index}.md'
                path.write_text(_note({'item': entry}), encoding='utf-8')
                errors, summary = ledger.validate_note(path)
                self.assertTrue(errors, needle)
                self.assertTrue(any(needle in error for error in errors), (needle, errors))
                self.assertEqual(summary['status'], 'INVALID')

    def test_bad_json_and_block_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            bad = directory / 'bad.md'
            bad.write_text(_note({}, raw='{'), encoding='utf-8')
            errors, summary = ledger.validate_note(bad)
            self.assertTrue(any('JSON' in error for error in errors))
            self.assertEqual(summary['status'], 'INVALID')
            duplicate = directory / 'dup.md'
            duplicate.write_text(_note({}, raw='{"schema":"capital-decision-v1","schema":"other"}'), encoding='utf-8')
            errors, _summary = ledger.validate_note(duplicate)
            self.assertTrue(any('duplicate key' in error for error in errors))
            empty = directory / 'empty.md'
            empty.write_text(_note({}, blocks=0), encoding='utf-8')
            errors, _summary = ledger.validate_note(empty)
            self.assertTrue(any('found 0' in error for error in errors))
            two = directory / 'two.md'
            two.write_text(_note({'item': _entry()}, blocks=2), encoding='utf-8')
            errors, _summary = ledger.validate_note(two)
            self.assertTrue(any('found 2' in error for error in errors))

    def test_missing_expected_note_is_pending_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = root / 'docs' / 'decisions'
            decisions.mkdir(parents=True)
            coverage = root / 'CAP_COVERAGE.md'
            coverage.write_text('see docs/decisions/missing-note.md\n', encoding='utf-8')
            rows = ledger.build_index(decisions, ['docs/decisions/missing-note.md'])
            self.assertEqual(rows[0]['status'], 'PENDING')
            self.assertEqual(rows[0]['decision_id'], None)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = ledger.main(['--coverage', str(coverage), '--decisions', str(decisions)])
            self.assertEqual(code, 0)
            self.assertIn('PENDING', buffer.getvalue())
            invalid = decisions / 'missing-note.md'
            invalid.write_text(_note({}, blocks=0), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = ledger.main(['--coverage', str(coverage), '--decisions', str(decisions)])
            self.assertEqual(code, 1)

    def test_valid_undetermined_entry_is_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'open.md'
            path.write_text(_note({'priority': _entry(status='UNDETERMINED')}), encoding='utf-8')
            errors, summary = ledger.validate_note(path)
            self.assertEqual(errors, [])
            self.assertEqual(summary['entries'], {'priority': 'UNDETERMINED'})
            self.assertEqual(summary['status'], 'UNDETERMINED')


if __name__ == '__main__':
    unittest.main()
