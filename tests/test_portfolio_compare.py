"""Hand-derived SIMULATED movements, fail-closed compatibility and offline IO."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import portfolio_compare as compare, portfolio_snapshot
from capital.audit import audit_workspace, audit_workspace_bytes
from capital.evidence import offline_service
from capital.service import CapitalService
from capital.store import FILE_NAME, FileWorkspace, canonical_bytes, _checksum
from capital.terms import DecisionNoteTermsPolicy, read_decision_block
from tests.test_overlay import draw_book, run, tick, TERMS_NOTE

ROOT = Path(__file__).resolve().parents[1]


def tree(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
            for p in [root, *sorted(root.rglob('*'))]}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.before, self.after = self.root / 'before', self.root / 'after'
        self.service = CapitalService()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.service.observability.close)

    def save(self, directory, service=None, *, legacy=False):
        service = service or self.service
        service._persist()
        document = copy.deepcopy(service.storage.load())
        if legacy:
            del document['overlay']
            del document['envelope_version']
        directory.mkdir(exist_ok=True)
        (directory / FILE_NAME).write_bytes(canonical_bytes(document))
        return document

    def compare(self, expected='COMPARABLE'):
        before = tree(self.root)
        result = compare.compare_workspaces(self.before, self.after)
        self.assertEqual(result['status'], expected, result['comparability'])
        self.assertEqual(tree(self.root), before)
        self.assertEqual(result, compare.compare_workspaces(self.before, self.after))
        if expected == 'COMPARABLE':
            self.assertTrue(result['changes']['reconciliation']['matched'])
        else:
            self.assertIsNone(result['changes'])
        return result

    def reason(self, result, reason):
        self.assertIn(reason, [r['reason'] for r in result['comparability']['checks']])

    def test_new_draw_and_empty_book(self):
        self.save(self.before, legacy=True)
        self.save(self.after)
        result = self.compare()
        self.assertEqual(result['changes']['advances'], [])
        self.assertEqual(result['changes']['totals']['delta']['outstanding_krw'], 0)
        self.assertEqual(result['changes']['totals']['after']['reserve_requirement_krw'], 0)
        draw_book(self.service, amount=10000)
        self.save(self.after)
        result = self.compare()
        row = result['changes']['advances'][0]
        self.assertEqual(row['presence'], 'AFTER_ONLY')
        self.assertIsNone(row['before'])
        self.assertEqual(row['after']['beneficiary_role'], 'fixture-organizer')
        self.assertEqual(row['delta']['outstanding_krw'], 10000)
        self.assertEqual(row['delta']['reserve_requirement_krw'], 150)
        self.assertEqual(row['after']['aging'], 'NOT_DUE')
        self.assertEqual(result['changes']['totals']['delta'], row['delta'])

    def test_partial_principal_reduction(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        run(self.service, 'repay', 'sim-a', 'repay', amount=4000, sequence=1)
        self.save(self.after)
        result = self.compare()
        row = result['changes']['advances'][0]
        self.assertEqual((row['before']['outstanding_krw'], row['after']['outstanding_krw']), (10000, 6000))
        self.assertEqual((row['before']['reserve_requirement_krw'], row['after']['reserve_requirement_krw']), (150, 90))
        self.assertEqual(row['delta']['reserve_requirement_krw'], -60)
        for key in ('authentication', 'common_ownership', 'historical_policy_provenance', 'actual_payments'):
            self.assertEqual(result[key], 'NOT_BOUND')
        self.assertFalse(result['funds_executed'])
        self.assertFalse(result['workspace_mutated'])
        self.assertNotIn('payment', row)
        self.assertNotIn('cause', row)

    def test_clock_only_aging_and_full_reduction_watch_exit(self):
        draw_book(self.service, amount=10000)
        tick(self.service, 'day60', 0, 60)
        self.save(self.before)
        tick(self.service, 'day61', 60, 61)
        self.save(self.after)
        result = self.compare()
        row = result['changes']['advances'][0]
        self.assertEqual(result['inputs']['before']['state_digest'], result['inputs']['after']['state_digest'])
        self.assertEqual(row['delta']['outstanding_krw'], 0)
        self.assertEqual((row['before']['reserve_requirement_krw'], row['after']['reserve_requirement_krw']), (150, 2500))
        self.assertEqual((row['before']['aging'], row['after']['aging']), ('NOT_DUE', '1-30'))
        self.assertEqual(row['after']['days_past_maturity'], 1)
        self.assertTrue(row['watch_change']['reasons_changed'])
        self.save(self.before)
        run(self.service, 'repay', 'sim-a', 'all', amount=10000, sequence=1)
        self.save(self.after)
        row = self.compare()['changes']['advances'][0]
        self.assertTrue(row['watch_change']['exited'])
        self.assertEqual(row['after']['covenant_status'], 'CLEAR')
        self.assertEqual(row['delta']['outstanding_krw'], -10000)
        self.assertEqual(row['delta']['reserve_requirement_krw'], -2500)

    def test_default_before_maturity_retains_exposure(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        run(self.service, 'default', 'sim-a', 'default')
        self.save(self.after)
        row = self.compare()['changes']['advances'][0]
        self.assertEqual(row['after']['phase'], 'DEFAULTED')
        self.assertEqual(row['after']['aging'], 'DEFAULTED')
        self.assertEqual(row['delta']['outstanding_krw'], 0)
        self.assertEqual(row['delta']['reserve_requirement_krw'], 10000 - 150)
        self.assertTrue(row['watch_change']['entered'])
        self.assertIn('DEFAULTED', [r['code'] for r in row['after']['reasons']])

    def test_combined_book_independent_deltas_and_per_advance_rounding(self):
        # All old draws are day 0. Day 60->61 ages them; the new draw is day 61.
        for key, fixture, amount in (
            ('partial', 'sim-committed', 10000), ('aging', 'demo-alpha-arena', 10000),
            ('default', 'demo-beta-festival', 10000), ('round1', 'demo-alpha-hall', 101),
            ('round2', 'demo-alpha-hall', 101)):
            draw_book(self.service, 'sim-' + key, fixture=fixture, amount=amount, prefix=key)
        tick(self.service, 'day60', 0, 60)
        self.save(self.before)
        run(self.service, 'repay', 'sim-partial', 'partial-repay', amount=4000, sequence=1)
        run(self.service, 'default', 'sim-default', 'default')
        tick(self.service, 'day61', 60, 61)
        draw_book(self.service, 'sim-new', fixture='demo-beta-festival', amount=10000, prefix='new')
        self.save(self.after)
        changes = self.compare()['changes']
        expected = {'sim-partial': (-4000, 1500-150), 'sim-aging': (0, 2500-150),
                    'sim-default': (0, 10000-150), 'sim-round1': (0, 25-1),
                    'sim-round2': (0, 25-1), 'sim-new': (10000, 150)}
        for row in changes['advances']:
            self.assertEqual((row['delta']['outstanding_krw'], row['delta']['reserve_requirement_krw']), expected[row['advance_id']])
        totals = changes['totals']
        self.assertEqual(totals['delta']['outstanding_krw'], 6000)
        self.assertEqual(totals['delta']['reserve_requirement_krw'], sum(r[1] for r in expected.values()))
        self.assertEqual(sum(b['delta']['reserve_requirement_krw'] for b in changes['beneficiaries']), sum(r[1] for r in expected.values()))
        self.assertEqual(len(changes['beneficiaries']), 3)
        self.assertEqual(totals['before']['reserve_requirement_krw'], 452)  # floor per advance
        self.assertEqual(totals['delta']['aging_exposure_krw']['1-30'], 16202)
        self.assertEqual(totals['delta']['aging_exposure_krw']['DEFAULTED'], 10000)

    def test_aging_boundaries(self):
        draw_book(self.service, amount=10000)
        start = 0
        for day, maturity, aging in ((30, '0-30', 'NOT_DUE'), (60, '0-30', 'NOT_DUE'),
                                    (61, '0-30', '1-30'), (90, '0-30', '1-30'),
                                    (91, '0-30', '31-60'), (120, '0-30', '31-60'),
                                    (121, '0-30', '61-90'), (150, '0-30', '61-90'),
                                    (151, '0-30', '>90')):
            self.save(self.before)
            tick(self.service, 'day' + str(day), start, day)
            self.save(self.after)
            row = self.compare()['changes']['advances'][0]['after']
            self.assertEqual((row['maturity_bucket'], row['aging']), (maturity, aging))
            start = day

    def test_view_digests_match_existing_snapshot_recipes(self):
        draw_book(self.service, amount=10000)
        tick(self.service, 'day12', 0, 12)
        self.save(self.before)
        self.save(self.after)
        info = self.compare()['inputs']['after']
        expected = self.service.portfolio_snapshot(self.service.instance_id)
        for key, value in expected['cut'].items():
            if key != 'kind':
                self.assertEqual(info[key], value, key)
        self.assertEqual(info['risk_digest'], expected['risk']['risk_digest'])
        self.assertEqual(info['covenant_digest'], expected['covenants']['covenant_digest'])
        self.assertEqual(info['workspace_sha256'], hashlib.sha256((self.after / FILE_NAME).read_bytes()).hexdigest())

    def test_missing_and_unusable_required_policy_even_on_empty_books(self):
        self.save(self.before)
        self.save(self.after)
        for name in compare.REQUIRED_TERMS:
            for missing in (True, False):
                def restore(document):
                    service = offline_service(document)
                    if missing:
                        del service.terms.items[name]
                    else:
                        service.terms.items[name] = {'mark': 'NOT_BOUND', 'value': None}
                    return service
                with self.subTest(name=name, missing=missing), patch.object(compare, 'offline_service', restore):
                    result = self.compare('NON_COMPARABLE')
                    reason = 'REQUIRED_POLICY_ENTRY_MISSING' if missing else 'REQUIRED_POLICY_ENTRY_UNUSABLE'
                    self.reason(result, reason)
                    self.assertEqual(result['inputs']['before']['policy_inputs_digest'], result['inputs']['after']['policy_inputs_digest'])
                    self.assertEqual([r['entries'] for r in result['comparability']['checks'] if r['id'] == 'policy'],
                                     [[{'name': name, 'reason': reason}]] * 2)

    def test_unusable_loaded_temporary_note_and_no_forecast_or_fees_gate(self):
        self.save(self.before)
        self.save(self.after)
        block = read_decision_block(TERMS_NOTE)
        block['entries']['additional_margin']['value'] = {}
        note = self.root / 'temporary-policy.md'
        note.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
        def restore(document):
            service = offline_service(document)
            service.terms = DecisionNoteTermsPolicy(note)
            return service
        with patch.object(compare, 'offline_service', restore):
            self.reason(self.compare('NON_COMPARABLE'), 'REQUIRED_POLICY_ENTRY_UNUSABLE')
        def no_fees(document):
            service = offline_service(document)
            del service.terms.items['fees']
            return service
        with patch.object(compare, 'offline_service', no_fees), patch.object(portfolio_snapshot, 'compose', side_effect=AssertionError('no compose')):
            self.compare()
        # A valid historical overlay binding may be BOUND while comparison-time
        # fees are unusable/PARTIAL. Fees are outside the required six entries.
        draw_book(self.service, amount=10000)
        tick(self.service, 'day1', 0, 1)
        self.save(self.before)
        self.save(self.after)
        block = read_decision_block(TERMS_NOTE)
        block['entries']['fees']['value'] = {}
        note.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
        with patch.object(compare, 'offline_service', restore):
            self.compare()

    def test_missing_margin_policy_cannot_hide_behind_bound_nonempty_views(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        self.save(self.after)
        del self.service.terms.items['additional_margin']
        self.assertEqual(self.service.terms.top, 'BOUND')
        self.assertEqual(self.service.risk()['status'], 'BOUND')
        self.assertEqual(self.service.covenants()['status'], 'BOUND')
        def restore(document):
            service = offline_service(document)
            del service.terms.items['additional_margin']
            return service
        with patch.object(compare, 'offline_service', restore):
            result = self.compare('NON_COMPARABLE')
        self.reason(result, 'REQUIRED_POLICY_ENTRY_MISSING')
        self.assertEqual(result['inputs']['before']['policy_inputs_digest'], result['inputs']['after']['policy_inputs_digest'])

    def test_applicable_margin_requires_cure_rate_and_payee_inputs(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        self.save(self.after)
        for field in ('cure_window_days', 'cure_options_ordered', 'advance_rate_bps_by_tier', 'beneficiary_payee_map'):
            block = read_decision_block(TERMS_NOTE)
            value = block['entries']['additional_margin']['value']
            if field == 'advance_rate_bps_by_tier':
                del value[field]['T1_COMMIT_OBSERVED']
            elif field == 'beneficiary_payee_map':
                del value[field]['fixture-organizer']
            else:
                del value[field]
            note = self.root / 'margin-policy.md'
            note.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
            def restore(document):
                service = offline_service(document)
                service.terms = DecisionNoteTermsPolicy(note)
                self.assertTrue(service.terms._ready(*compare.REQUIRED_TERMS))
                return service
            with self.subTest(field=field), patch.object(compare, 'offline_service', restore):
                self.reason(self.compare('NON_COMPARABLE'), 'APPLICABLE_MARGIN_TERMS_UNUSABLE')

    def test_no_matching_tier_preserves_not_applicable_zero_exposure_row(self):
        draw_book(self.service, amount=10000)
        run(self.service, 'repay', 'sim-a', 'full', amount=10000, sequence=1)
        self.save(self.before)
        self.save(self.after)
        # Patch the tier selector, keeping the real margin and reserve rules.
        with patch.object(DecisionNoteTermsPolicy, '_tier', return_value=None):
            row = self.compare()['changes']['advances'][0]['after']
        self.assertEqual(row['tier'], 'NOT_APPLICABLE')
        self.assertIsNone(row['reserve_class'])
        self.assertIsNone(row['reserve_requirement_krw'])
        self.assertEqual(row['margin']['state'], 'NOT_APPLICABLE')

    def test_unrated_nonzero_exposure_fails_reserve_coverage(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        self.save(self.after)
        with patch.object(DecisionNoteTermsPolicy, '_tier', return_value=None):
            self.reason(self.compare('NON_COMPARABLE'), 'VIEW_COVERAGE_OR_RECONCILIATION_FAILED')

    def test_reversed_clock_truncated_divergent_journal_and_overlay_prefix(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        tick(self.service, 'day1', 0, 1)
        self.save(self.after)
        result = compare.compare_workspaces(self.after, self.before)
        self.reason(result, 'SIM_DAY_DECREASED')
        self.reason(result, 'OVERLAY_JOURNAL_NOT_PREFIX')
        self.save(self.before)
        run(self.service, 'repay', 'sim-a', 'partial', amount=1000, sequence=1)
        self.save(self.after)
        self.reason(compare.compare_workspaces(self.after, self.before), 'F04_JOURNAL_NOT_PREFIX')
        other = CapitalService()
        self.addCleanup(other.observability.close)
        draw_book(other, 'sim-other', amount=10000)
        self.save(self.after, other)
        self.reason(self.compare('NON_COMPARABLE'), 'F04_JOURNAL_NOT_PREFIX')

    def test_retroactive_overlay_cut_is_auditable_but_not_comparable(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        # An alternate history ticks before the same F04 journal was written.
        other = CapitalService()
        self.addCleanup(other.observability.close)
        tick(other, 'early', 0, 1)
        draw_book(other, amount=10000)
        self.save(self.after, other)
        self.assertTrue(audit_workspace(self.after)['ok'])
        self.reason(self.compare('NON_COMPARABLE'), 'RETROACTIVE_OVERLAY_ENTRY')

    def test_comparison_time_input_mismatch_and_binding_compatibility(self):
        draw_book(self.service, amount=10000)
        tick(self.service, 'day1', 0, 1)
        self.save(self.before)
        self.save(self.after)
        for kind, reason in (('policy', 'POLICY_INPUTS_MISMATCH'), ('profile', 'FIXTURE_INPUTS_MISMATCH'),
                             ('beneficiary', 'FIXTURE_INPUTS_MISMATCH'), ('binding', 'TERMS_BINDING_INCOMPATIBLE')):
            calls = []
            def restore(document):
                service = offline_service(document)
                calls.append(service)
                if len(calls) % 2 == 0:
                    if kind == 'policy':
                        service.terms.items['reserve']['value']['provision_bps_of_outstanding']['T1_COMMIT_OBSERVED'] += 1
                    elif kind == 'profile':
                        service.fixtures.profiles['sim-committed'] = 'CHANGED'
                    elif kind == 'beneficiary':
                        service.fixtures.beneficiaries['sim-committed'] = 'CHANGED'
                    else:
                        service.terms.version = 'OTHER_VERSION'
                return service
            with self.subTest(kind=kind), patch.object(compare, 'offline_service', restore):
                self.reason(self.compare('NON_COMPARABLE'), reason)

    def test_changed_mapping_and_draw_gates_fail_closed(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        document = self.save(self.after)
        for kind in ('mapping', 'gate'):
            changed = copy.deepcopy(document)
            if kind == 'mapping':
                changed['payload']['case_fixtures']['sim-a'] = 'sim-pending'
            else:
                changed['payload']['receipts']['a-draw']['receipt']['result']['credit']['settlement_gate'] = 'OTHER_GATE'
            changed['payload_sha256'] = _checksum(changed['payload'])
            (self.after / FILE_NAME).write_bytes(canonical_bytes(changed))
            self.compare('NON_COMPARABLE')

    def test_audited_draw_receipts_with_missing_or_malformed_gates(self):
        draw_book(self.service, amount=10000)
        self.save(self.before)
        document = self.save(self.after)
        for result in (None, [], {}, {'credit': None}, {'credit': []}, {'credit': {}},
                       {'credit': {'settlement_gate': ''}},
                       {'credit': {'settlement_gate': 1}}):
            with self.subTest(result=result):
                changed = copy.deepcopy(document)
                changed['payload']['receipts']['a-draw']['receipt']['result'] = result
                changed['payload_sha256'] = _checksum(changed['payload'])
                (self.after / FILE_NAME).write_bytes(canonical_bytes(changed))
                self.assertTrue(audit_workspace(self.after)['ok'])
                report = self.compare('NON_COMPARABLE')
                self.reason(report, 'DRAW_RECEIPT_GATE_MISSING')
                gate = next(row for row in report['comparability']['checks']
                            if row['id'] == 'draw_gates' and row['side'] == 'after')
                self.assertEqual(gate['entries'], ['sim-a'])
                self.assertEqual(next(row for row in report['comparability']['checks']
                                      if row['id'] == 'views' and row['side'] == 'after')['status'],
                                 'NOT_CHECKED')

    def test_pair_checks_identify_mapping_gates_and_dependent_overlay_failure(self):
        draw_book(self.service, amount=10000)
        tick(self.service, 'day1', 0, 1)
        self.save(self.before)
        checks = []
        info, frozen = compare._capture(self.before, 'before', checks)
        before = compare._prepare(frozen, info, 'before', checks)
        for field, reason in (('mapping', 'ADVANCE_MAPPING_CHANGED'), ('gates', 'DRAW_RECEIPT_GATE_CHANGED')):
            after = copy.deepcopy(before)
            after[field]['sim-a'] = 'OTHER'
            pair_checks = []
            compare._compatible(before, after, pair_checks)
            self.assertIn(reason, [r['reason'] for r in pair_checks])
        after = copy.deepcopy(before)
        after['entries'][0]['operation_id'] = 'DIVERGENT'
        pair_checks = []
        compare._compatible(before, after, pair_checks)
        self.assertEqual(next(r for r in pair_checks if r['id'] == 'overlay_append_cut')['status'], 'NOT_CHECKED')

    def test_capture_reads_each_workspace_once_and_never_opens_file_storage(self):
        self.save(self.before)
        self.save(self.after)
        read_bytes = Path.read_bytes
        reads = []
        def read(path):
            if path.name == FILE_NAME:
                reads.append(path)
            return read_bytes(path)
        with patch.object(Path, 'read_bytes', read), patch.object(FileWorkspace, 'open', side_effect=AssertionError('offline only')):
            result = compare.compare_workspaces(self.before, self.after)
        self.assertEqual(result['status'], 'COMPARABLE')
        self.assertEqual(reads, [self.before / FILE_NAME, self.after / FILE_NAME])

    def test_missing_corrupt_duplicate_json_and_checksum_audit_both_sides(self):
        self.before.mkdir()
        self.after.mkdir()
        for raw in (None, b'{', b'{"x":1,"x":2}', b'{}', b'\xff'):
            if raw is not None:
                (self.before / FILE_NAME).write_bytes(raw)
            result = self.compare('NON_COMPARABLE')
            self.assertFalse(result['inputs']['before']['audit']['ok'])
            self.assertFalse(result['inputs']['after']['audit']['ok'])
            self.assertTrue(all(r['status'] == 'NOT_CHECKED' for r in result['comparability']['checks'] if r['side'] == 'pair'))
        doc = self.save(self.before)
        doc['payload_sha256'] = '0' * 64
        (self.before / FILE_NAME).write_bytes(canonical_bytes(doc))
        self.assertEqual(self.compare('NON_COMPARABLE')['inputs']['before']['audit']['failed_check'], 'payload_sha256')

    def test_nonregular_workspace_file_is_rejected_without_reading(self):
        self.save(self.after)
        self.before.mkdir()
        os.mkfifo(self.before / FILE_NAME)
        result = compare.compare_workspaces(self.before, self.after)
        self.assertEqual(result['status'], 'NON_COMPARABLE')
        self.assertEqual(result['inputs']['before']['audit']['failed_check'], 'workspace_file')
        self.assertTrue(result['inputs']['after']['audit']['ok'])

    def test_capture_bytes_replacement_does_not_change_audited_calculations(self):
        self.save(self.before)
        self.save(self.after)
        original = (self.before / FILE_NAME).read_bytes()
        audit_bytes = audit_workspace_bytes
        def replace(raw, *, workspace):
            (Path(workspace) / FILE_NAME).write_bytes(b'{}')
            return audit_bytes(raw, workspace=workspace)
        with patch.object(compare.audit, 'audit_workspace_bytes', replace):
            result = compare.compare_workspaces(self.before, self.after)
        self.assertEqual(result['status'], 'COMPARABLE')
        self.assertEqual(result['inputs']['before']['workspace_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual((self.before / FILE_NAME).read_bytes(), b'{}')

    def test_cli_success_failures_arguments_determinism_and_held_lock(self):
        self.save(self.before)
        draw_book(self.service, amount=10000)
        self.save(self.after)
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'capital.portfolio_compare', *map(str, args)],
                                  cwd=ROOT, capture_output=True, timeout=60)
        held = FileWorkspace.open(self.before)
        try:
            captured = tree(self.root)
            args = ('--before', self.before, '--after', self.after)
            first, second = cli(*args), cli(*args)
            self.assertEqual((first.returncode, first.stderr), (0, b''))
            self.assertEqual(first.stdout, second.stdout)
            result = json.loads(first.stdout)
            self.assertEqual(result['status'], 'COMPARABLE')
            self.assertEqual(first.stdout, canonical_bytes(result) + b'\n')
            self.assertEqual(tree(self.root), captured)
        finally:
            held.close()
        self.assertEqual(cli().returncode, 2)
        self.assertEqual(cli('--before', self.before).returncode, 2)
        self.assertEqual(cli('--before', self.before, '--after', self.root / 'missing').returncode, 1)
        document = json.loads((self.after / FILE_NAME).read_bytes())
        document['payload']['receipts']['a-draw']['receipt']['result'] = None
        document['payload_sha256'] = _checksum(document['payload'])
        (self.after / FILE_NAME).write_bytes(canonical_bytes(document))
        captured = tree(self.root)
        failed = cli(*args)
        self.assertEqual((failed.returncode, failed.stderr), (1, b''))
        result = json.loads(failed.stdout)
        self.assertEqual(result['status'], 'NON_COMPARABLE')
        self.assertIsNone(result['changes'])
        self.reason(result, 'DRAW_RECEIPT_GATE_MISSING')
        self.assertEqual(failed.stdout, cli(*args).stdout)
        self.assertEqual(tree(self.root), captured)


if __name__ == '__main__':
    unittest.main()
