"""Crash-boundary replay matrix for the LOCAL_FILE_WORKSPACE.

The helper module is not named test*.py, matching tests/storage_conformance.py
and tests/facade_schema.py. Every pinned cell is replayed in a fresh directory:
a crash injected before or after each workspace write boundary (journal-append,
overlay-entry, temp-file rename), torn trailing files, a stale temp file, and
one real SIGKILL on the --workspace subprocess. Restart must restore the pinned
digests byte-identically or fail closed WORKSPACE_UNREADABLE — never a silent
empty book. SIMULATED; not SEMANTIC_CONFORMANCE; CAP-11 stays NOT_BOUND.
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    'crash_matrix', Path(__file__).resolve().with_name('crash_matrix.py'))
crash_matrix = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(crash_matrix)

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / 'tests' / 'vectors' / 'workspace_crash.json'


def _table():
    return json.loads(VECTOR.read_text(encoding='utf-8'))


def _run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = crash_matrix.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class VectorPinTests(unittest.TestCase):
    def test_committed_table_matches_the_generated_one(self):
        self.assertEqual(_table(), crash_matrix.build_table())
        self.assertEqual(VECTOR.read_bytes(), crash_matrix.serialize(crash_matrix.build_table()))

    def test_check_mode_exits_zero_on_the_committed_pin(self):
        code, out, err = _run_cli('--check')
        self.assertEqual(code, 0, err)
        self.assertIn('crash matrix vectors ok', out)
        self.assertEqual(err, '')

    def test_check_mode_via_cli_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, 'tests/crash_matrix.py', '--check'],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_check_writes_nothing(self):
        before = VECTOR.read_bytes()
        self.assertEqual(_run_cli('--check')[0], 0)
        self.assertEqual(VECTOR.read_bytes(), before)

    def test_labels_stay_honest(self):
        table = _table()
        self.assertEqual(table['label'], 'SIMULATED')
        self.assertEqual(table['durable'], 'LOCAL_FILE_WORKSPACE')
        self.assertEqual(table['stage5_durable_transactions'], 'NOT_BOUND')
        self.assertIs(table['semantic_conformance'], False)
        self.assertEqual(table['cross_host_fencing'], 'NOT_CLAIMED')
        text = VECTOR.read_text(encoding='utf-8')
        for volatile in ('instance_id', 'local_token', 'saved_at', 'saved_by_instance'):
            self.assertNotIn(volatile, text)

    def test_matrix_covers_every_write_boundary(self):
        table = _table()
        self.assertEqual(len(table['script']), 7)
        boundaries = {step['boundary'] for step in table['script']}
        self.assertEqual(boundaries, {'journal-append', 'overlay-entry'})
        cells = table['cells']
        for step in table['script']:
            saves = [cell for cell in cells
                     if cell['runner'] == 'save-boundary' and cell['save_index'] == step['step']]
            self.assertEqual(sorted(cell['position'] for cell in saves), ['after', 'before'],
                             step['operation_id'])
        renames = {(cell['position'], cell['rename_of']) for cell in cells if cell['runner'] == 'rename'}
        self.assertEqual(renames, {('before', 'journal-append'), ('after', 'journal-append'),
                                   ('before', 'overlay-entry'), ('after', 'overlay-entry')})
        runners = sorted({cell['runner'] for cell in cells})
        self.assertEqual(runners, ['rename', 'save-boundary', 'sigkill', 'stale-temp', 'torn'])
        self.assertEqual(len(cells), table['cell_count'])

    def test_pin_is_byte_stable_across_runs(self):
        self.assertEqual(crash_matrix.serialize(crash_matrix.build_table()),
                         crash_matrix.serialize(crash_matrix.build_table()))


class MatrixCellTests(unittest.TestCase):
    def _check(self, runner_names):
        cells = [cell for cell in _table()['cells'] if cell['runner'] in runner_names]
        self.assertTrue(cells)
        for cell in cells:
            with self.subTest(cell=cell['id']):
                observed = crash_matrix.cell_outcome(cell)
                problems = crash_matrix.outcome_problems(cell['expect'], observed)
                self.assertEqual(problems, [], f"{cell['id']}: {problems}; observed {observed}")

    def test_save_boundary_cells_restore_pinned_digests(self):
        """Crash before and after every journal-append and overlay-entry save."""
        self._check({'save-boundary'})

    def test_rename_cells_restore_pinned_digests(self):
        """Crash before the temp rename and after it inside _atomic_write."""
        self._check({'rename'})


class TornPayloadTests(unittest.TestCase):
    def test_torn_payloads_fail_closed_and_are_never_rewritten(self):
        table = _table()
        cells = [cell for cell in table['cells'] if cell['runner'] == 'torn']
        self.assertEqual(len(cells), 3)
        for cell in cells:
            with self.subTest(cell=cell['id']):
                observed = crash_matrix.cell_outcome(cell)
                problems = crash_matrix.outcome_problems(cell['expect'], observed)
                self.assertEqual(problems, [], f"{cell['id']}: {problems}; observed {observed}")
                # The fail-closed contract itself, beyond the pinned fields.
                self.assertEqual(observed['workspace_status'], 'WORKSPACE_UNREADABLE')
                self.assertEqual(observed['cases'], 0)
                self.assertEqual(observed['write_blocked'], 'WORKSPACE_UNREADABLE')
                self.assertIs(observed['file_unchanged'], True)

    def test_stale_temp_never_loaded(self):
        cell = next(cell for cell in _table()['cells'] if cell['runner'] == 'stale-temp')
        observed = crash_matrix.cell_outcome(cell)
        problems = crash_matrix.outcome_problems(cell['expect'], observed)
        self.assertEqual(problems, [], f"{cell['id']}: {problems}; observed {observed}")
        self.assertIs(observed['temp_cleared'], True)


class SigKillTests(unittest.TestCase):
    def test_sigkill_restart_restores_one_of_the_pinned_digests(self):
        cell = next(cell for cell in _table()['cells'] if cell['runner'] == 'sigkill')
        observed = crash_matrix.cell_outcome(cell)
        problems = crash_matrix.outcome_problems(cell['expect'], observed)
        self.assertEqual(problems, [], f"{cell['id']}: {problems}; observed {observed}")


if __name__ == '__main__':
    unittest.main()
