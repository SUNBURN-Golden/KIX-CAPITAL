"""Hand-derived SIMULATED transitions, endpoint parity and read-only failure paths."""
import builtins
import copy
from contextlib import ExitStack
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import portfolio_compare as compare, portfolio_migrations as migrations
from capital.evidence import offline_service
from capital.service import CapitalService
from capital.store import FILE_NAME, FileWorkspace, InMemoryStorage, canonical_bytes, _checksum
from tests.test_overlay import draw_book, run, tick
from tests.test_portfolio_compare import tree

ROOT = Path(__file__).resolve().parents[1]


def cell(matrix, before, after):
    return next(c for c in matrix['cells']
                if (c['before_category'], c['after_category']) == (before, after))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.before, self.after = self.root / 'before', self.root / 'after'
        self.service = CapitalService()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.service.observability.close)

    def save(self, directory, service=None):
        service = service or self.service
        service._persist()
        document = copy.deepcopy(service.storage.load())
        directory.mkdir(exist_ok=True)
        (directory / FILE_NAME).write_bytes(canonical_bytes(document))
        return document

    def report(self, expected='COMPARABLE'):
        captured = tree(self.root)
        report = migrations.report_workspaces(self.before, self.after)
        self.assertEqual(tree(self.root), captured)
        self.assertEqual(report['status'], expected, report)
        self.assertEqual(report, migrations.report_workspaces(self.before, self.after))
        self.assertEqual(report['format'], 'KIX_CAPITAL_PORTFOLIO_MIGRATIONS_V1')
        self.assertEqual(report['label'], 'SIMULATED')
        for name in ('historical_policy_provenance', 'authentication', 'common_ownership', 'actual_payments'):
            self.assertEqual(report[name], 'NOT_BOUND')
        self.assertIs(report['funds_executed'], False)
        self.assertIs(report['workspace_mutated'], False)
        if expected == 'COMPARABLE':
            self.assertTrue(report['reconciliation']['matched'])
            self.assertTrue(all(c['matched'] for c in report['reconciliation']['checks']))
        else:
            self.assertIsNone(report['matrices'])
        return report

    def mixed_book(self):
        for key, fixture in (('partial', 'sim-committed'), ('aging', 'demo-alpha-arena'),
                             ('default', 'demo-beta-festival'), ('closed', 'demo-alpha-arena')):
            draw_book(self.service, 'sim-' + key, fixture=fixture, amount=10000, prefix=key)
        tick(self.service, 'day60', 0, 60)
        self.save(self.before)
        run(self.service, 'repay', 'sim-partial', 'partial-repay', amount=4000, sequence=1)
        run(self.service, 'default', 'sim-default', 'default')
        run(self.service, 'repay', 'sim-closed', 'closed-repay', amount=10000, sequence=1)
        self.assertEqual(run(self.service, 'close', 'sim-closed', 'close')['outcome'], 'ACCEPTED')
        tick(self.service, 'day61', 60, 61)
        draw_book(self.service, 'sim-new', fixture='demo-beta-festival', amount=10000, prefix='new')
        self.save(self.after)

    def assert_measures(self, value, count, before, after, before_open, after_open):
        self.assertEqual({key: value[key] for key in migrations.MEASURES}, dict(zip(
            migrations.MEASURES, (count, before, after, before_open, after_open))))

    def test_hand_derived_combined_transitions_and_beneficiary_allocations(self):
        self.mixed_book()
        report = self.report()
        matrices = report['matrices']
        aging, watch = (matrices['portfolio'][d] for d in ('aging', 'watch_status'))
        self.assert_measures(cell(aging, 'NOT_DUE', '1-30'), 3, 30000, 16000, 3, 2)
        self.assert_measures(cell(aging, 'NOT_DUE', 'DEFAULTED'), 1, 10000, 10000, 1, 1)
        self.assert_measures(cell(aging, 'ABSENT_BEFORE', 'NOT_DUE'), 1, 0, 10000, 0, 1)
        self.assert_measures(cell(watch, 'WATCH', 'BREACH'), 3, 30000, 26000, 3, 3)
        self.assert_measures(cell(watch, 'WATCH', 'CLEAR'), 1, 10000, 0, 1, 0)
        self.assert_measures(cell(watch, 'ABSENT_BEFORE', 'CLEAR'), 1, 0, 10000, 0, 1)
        self.assert_measures(aging['grand_totals'], 5, 40000, 36000, 4, 4)
        self.assertEqual(aging['grand_totals'], watch['grand_totals'])
        beneficiaries = matrices['beneficiaries']
        self.assertEqual([b['beneficiary_role'] for b in beneficiaries],
                         ['demo-org-alpha', 'demo-org-beta', 'fixture-organizer'])
        alpha, beta, organizer = beneficiaries
        self.assert_measures(cell(alpha['aging'], 'NOT_DUE', '1-30'), 2, 20000, 10000, 2, 1)
        self.assert_measures(cell(alpha['watch_status'], 'WATCH', 'CLEAR'), 1, 10000, 0, 1, 0)
        self.assert_measures(cell(beta['aging'], 'NOT_DUE', 'DEFAULTED'), 1, 10000, 10000, 1, 1)
        self.assert_measures(cell(beta['aging'], 'ABSENT_BEFORE', 'NOT_DUE'), 1, 0, 10000, 0, 1)
        self.assert_measures(cell(organizer['aging'], 'NOT_DUE', '1-30'), 1, 10000, 6000, 1, 1)
        # Every remaining dense cell is explicitly zero, including absence-after.
        for matrix in (aging, watch):
            self.assertEqual(sum(c['advance_count'] > 0 for c in matrix['cells']), 3)
            for c in matrix['cells']:
                if c['advance_count'] == 0:
                    self.assert_measures(c, 0, 0, 0, 0, 0)

    def test_empty_and_identical_snapshots_with_dense_zero_cells(self):
        self.save(self.before)
        self.save(self.after)
        report = self.report()
        self.assertEqual(report['matrices']['beneficiaries'], [])
        for dim, expected_size in (('aging', 49), ('watch_status', 16)):
            matrix = report['matrices']['portfolio'][dim]
            self.assertEqual(len(matrix['cells']), expected_size)
            self.assert_measures(matrix['grand_totals'], 0, 0, 0, 0, 0)
        draw_book(self.service, amount=10000)
        run(self.service, 'repay', 'sim-a', 'all', amount=10000, sequence=1)
        self.save(self.before)
        self.save(self.after)
        report = self.report()
        self.assert_measures(cell(report['matrices']['portfolio']['aging'], 'NOT_DUE', 'NOT_DUE'),
                             1, 0, 0, 0, 0)
        self.assert_measures(cell(report['matrices']['portfolio']['watch_status'], 'CLEAR', 'CLEAR'),
                             1, 0, 0, 0, 0)

    def test_clock_only_aging_boundaries_preserve_principal(self):
        draw_book(self.service, amount=10000)
        start, before_category = 0, 'NOT_DUE'
        for day, after_category in ((60, 'NOT_DUE'), (61, '1-30'), (90, '1-30'),
                                    (91, '31-60'), (120, '31-60'), (121, '61-90'),
                                    (150, '61-90'), (151, '>90')):
            with self.subTest(day=day):
                self.save(self.before)
                tick(self.service, 'day' + str(day), start, day)
                self.save(self.after)
                report = self.report()
                self.assertEqual(report['inputs']['before']['state_digest'], report['inputs']['after']['state_digest'])
                self.assert_measures(cell(report['matrices']['portfolio']['aging'], before_category, after_category),
                                     1, 10000, 10000, 1, 1)
                start, before_category = day, after_category

    def test_endpoint_and_componentwise_beneficiary_sums_independently(self):
        self.mixed_book()
        source = compare.compare_workspaces(self.before, self.after)
        report = migrations.compose(source)
        # Independent sums over returned cells; counts exclude absence at endpoints.
        for dimension, field in (('aging', 'aging'), ('watch_status', 'covenant_status')):
            matrix = report['matrices']['portfolio'][dimension]
            for side in ('before', 'after'):
                endpoints = [r[side] for r in source['changes']['advances'] if r[side] is not None]
                for category in matrix[side + '_categories'][:-1]:
                    cells = [c for c in matrix['cells'] if c[side + '_category'] == category]
                    rows = [r for r in endpoints if r[field] == category]
                    self.assertEqual(sum(c['advance_count'] for c in cells), len(rows))
                    self.assertEqual(sum(c[side + '_principal_krw'] for c in cells), sum(r['outstanding_krw'] for r in rows))
                    self.assertEqual(sum(c[side + '_open_advance_count'] for c in cells), sum(r['outstanding_krw'] > 0 for r in rows))
            for section in ('cells', 'row_totals', 'column_totals'):
                for index, item in enumerate(matrix[section]):
                    for key in migrations.MEASURES:
                        self.assertEqual(item[key], sum(b[dimension][section][index][key]
                                                       for b in report['matrices']['beneficiaries']))

    def test_synthetic_before_only_exit_is_absence_without_payment_inference(self):
        # Prefix-compatible real snapshots retain draws. Only this explicitly
        # synthetic joined-row helper case represents disappearance arithmetic.
        endpoint = {'aging': '1-30', 'covenant_status': 'BREACH', 'outstanding_krw': 6000,
                    'beneficiary_role': 'SIMULATED-role'}
        rows = [{'before': endpoint, 'after': None}]
        for dim, category in (('aging', '1-30'), ('watch_status', 'BREACH')):
            matrix = migrations._aggregate(rows, dim)
            self.assert_measures(cell(matrix, category, 'ABSENT_AFTER'), 1, 6000, 0, 1, 0)
            self.assert_measures(matrix['grand_totals'], 1, 6000, 0, 1, 0)

    def test_comparator_is_called_once_and_composition_is_pure(self):
        self.mixed_book()
        source = compare.compare_workspaces(self.before, self.after)
        original = copy.deepcopy(source)
        with patch.object(compare, 'compare_workspaces', return_value=source) as gate:
            report = migrations.report_workspaces(self.before, self.after)
        gate.assert_called_once_with(self.before, self.after)
        self.assertEqual(source, original)
        self.assertEqual(report['inputs'], source['inputs'])
        self.assertEqual(report['comparability'], source['comparability'])
        report['comparability']['checks'].clear()
        self.assertEqual(source, original)

    def reject(self):
        with patch.object(migrations, '_aggregate', side_effect=AssertionError('must not aggregate')):
            return self.report('NON_COMPARABLE')

    def test_corrupt_and_missing_snapshots_never_aggregate(self):
        self.before.mkdir()
        self.save(self.after)
        for raw in (None, b'{', b'{"x":1,"x":2}', b'{}', b'\xff'):
            with self.subTest(raw=raw):
                if raw is not None:
                    (self.before / FILE_NAME).write_bytes(raw)
                report = self.reject()
                self.assertFalse(report['inputs']['before']['audit']['ok'])
                self.assertTrue(report['inputs']['after']['audit']['ok'])
        document = self.save(self.before)
        document['payload_sha256'] = '0' * 64
        (self.before / FILE_NAME).write_bytes(canonical_bytes(document))
        self.reject()

    def test_incompatible_clock_histories_gates_and_policy_never_aggregate(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        tick(self.service, 'day1', 0, 1)
        self.save(self.after)
        self.before, self.after = self.after, self.before
        self.reject()  # reversed clock / overlay prefix
        self.before, self.after = self.after, self.before
        self.save(self.before)
        run(self.service, 'repay', 'sim-a', 'partial', amount=1000, sequence=1)
        self.save(self.after)
        self.before, self.after = self.after, self.before
        self.reject()  # truncated F04 journal
        self.before, self.after = self.after, self.before
        other = CapitalService()
        self.addCleanup(other.observability.close)
        draw_book(other, 'sim-other', amount=10000)
        self.save(self.after, other)
        self.reject()  # divergent F04 journal
        document = self.save(self.after)
        document['payload']['receipts']['a-draw']['receipt']['result'] = {}
        document['payload_sha256'] = _checksum(document['payload'])
        (self.after / FILE_NAME).write_bytes(canonical_bytes(document))
        self.reject()
        self.save(self.after)
        def unusable(document):
            service = offline_service(document)
            service.terms.items['reserve'] = {'mark': 'NOT_BOUND', 'value': None}
            return service
        with patch.object(compare, 'offline_service', unusable):
            self.reject()

    def test_reconciliation_failure_suppresses_matrices_without_changing_gate(self):
        self.mixed_book()
        source = compare.compare_workspaces(self.before, self.after)
        aggregate = migrations._aggregate
        for section, key in (('cells', 'after_principal_krw'), ('row_totals', 'advance_count'),
                             ('column_totals', 'before_open_advance_count'), ('grand_totals', 'before_principal_krw')):
            def corrupt(rows, dimension):
                matrix = aggregate(rows, dimension)
                target = matrix[section] if section == 'grand_totals' else matrix[section][0]
                target[key] += 1
                return matrix
            with self.subTest(section=section), patch.object(migrations, '_aggregate', corrupt):
                report = migrations.compose(source)
            self.assertEqual(report['status'], 'NON_COMPARABLE')
            self.assertEqual(report['reason'], 'MATRIX_RECONCILIATION_FAILED')
            self.assertIsNone(report['matrices'])
            self.assertFalse(report['reconciliation']['matched'])
            self.assertEqual(report['comparability'], source['comparability'])

    def test_no_storage_locks_or_write_opens_and_each_snapshot_read_once(self):
        self.mixed_book()
        for corrupt in (False, True):
            if corrupt:
                (self.after / FILE_NAME).write_bytes(b'{')
            captured, reads = tree(self.root), []
            read_bytes = Path.read_bytes
            def read(path):
                if path.name == FILE_NAME:
                    reads.append(path)
                return read_bytes(path)
            def readonly_open(original):
                def guarded(file, mode='r', *args, **kwargs):
                    self.assertFalse(any(flag in mode for flag in 'wax+'), mode)
                    self.assertFalse(str(file).endswith('.lock'), file)
                    return original(file, mode, *args, **kwargs)
                return guarded
            with ExitStack() as stack:
                stack.enter_context(patch.object(Path, 'read_bytes', read))
                stack.enter_context(patch.object(builtins, 'open', readonly_open(builtins.open)))
                stack.enter_context(patch.object(io, 'open', readonly_open(io.open)))
                for target, name in ((FileWorkspace, 'open'), (FileWorkspace, 'save'),
                                     (InMemoryStorage, 'save'), (os, 'open'), (os, 'mkdir'),
                                     (os, 'replace'), (fcntl, 'flock')):
                    stack.enter_context(patch.object(target, name, side_effect=AssertionError('no writes/locks')))
                report = migrations.report_workspaces(self.before, self.after)
            self.assertEqual(report['status'], 'NON_COMPARABLE' if corrupt else 'COMPARABLE')
            self.assertEqual(reads, [self.before / FILE_NAME, self.after / FILE_NAME])
            self.assertEqual(tree(self.root), captured)

    def test_cli_determinism_exit_codes_and_held_workspace_locks(self):
        self.mixed_book()
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'capital.portfolio_migrations', *map(str, args)],
                                  cwd=ROOT, capture_output=True, timeout=60)
        held = [FileWorkspace.open(path) for path in (self.before, self.after)]
        try:
            captured = tree(self.root)
            args = ('--before', self.before, '--after', self.after)
            first, second = cli(*args), cli(*args)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(second.returncode, 0, second.stderr)
            report = json.loads(first.stdout)
            self.assertEqual(first.stdout, canonical_bytes(report) + b'\n')
            self.assertEqual(tree(self.root), captured)
            failure = cli('--before', self.after, '--after', self.before)
            self.assertEqual(failure.returncode, 1, failure.stderr)
            self.assertIsNone(json.loads(failure.stdout)['matrices'])
            self.assertEqual(tree(self.root), captured)
            for args in ((), ('--before', self.before), ('--after', self.after), ('--unknown',)):
                self.assertEqual(cli(*args).returncode, 2)
        finally:
            for storage in held:
                storage.close()


if __name__ == '__main__':
    unittest.main()
