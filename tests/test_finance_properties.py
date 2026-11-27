"""SIMULATED arithmetic acceptance: pinned random cases and one-won mutants."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import random
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from capital import finance_properties as props, forecast, overlay, risk
from capital.terms import BPS_SCALE, DecisionNoteTermsPolicy

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('finance_properties_cli', ROOT / 'scripts/finance_properties.py')
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def accrual_one_won(original):
    def mutated(*args, **kwargs):
        postings = original(*args, **kwargs)
        for posting in postings:
            posting['cumulative_contract_exact'] = overlay.exact_text(
                Fraction(posting['cumulative_contract_exact']) + 1)
            posting['posted_contract_krw'] += 1
        return postings
    return mutated


def allocation_one_won(original):
    def mutated(*args, **kwargs):
        result = original(*args, **kwargs)
        if result['status'] == 'BOUND':
            result['to_interest'] += 1
        return result
    return mutated


def cap_one_won(original, field):
    def mutated(policy, subject, *args, **kwargs):
        row = original(policy, subject, *args, **kwargs)
        if row['status'] == 'BOUND':
            cost, cap, days = props.exact_cost(policy, subject, row['term_days'])
            if field == 'cap_check':
                row[field] = 'PASS' if cost + 1 <= cap else 'FAIL'
            else:
                extra = Fraction(BPS_SCALE * days, subject['principal'] * row['term_days'])
                row[field] = overlay.exact_text(Fraction(row[field]) + extra)
        return row
    return mutated


class FinancePropertiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terms = DecisionNoteTermsPolicy()

    def test_200_pinned_cases_each(self):
        report = props.run_all(200, self.terms)
        self.assertEqual(report['format'], props.FORMAT)
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual([p['property'] for p in report['properties']], list(props.PROPERTIES))
        for prop in report['properties']:
            with self.subTest(property=prop['property']):
                self.assertEqual(prop['cases_run'], 200)
                self.assertEqual(prop['seeds'], [74820000, 74820199])
                self.assertEqual(prop['violations'], [], '\n'.join(
                    props.violation_message(prop['property'], v) for v in prop['violations']))
        self.assertEqual(report['violations'], 0)

    def test_reports_deterministic(self):
        state = random.getstate()
        self.assertEqual(props.run_all(3, self.terms), props.run_all(3, self.terms))
        self.assertEqual(random.getstate(), state)
        for name in props.PROPERTIES:
            self.assertEqual(props.generate(name, props.SEED_BASE, self.terms),
                             props.generate(name, props.SEED_BASE, self.terms))

    def test_generator_coverage_and_validity(self):
        coverage = {key: set() for key in ('tiers', 'gate', 'draw', 'settlement', 'probe')}
        repayments = accelerations = 0
        for seed in range(props.SEED_BASE, props.SEED_BASE + 200):
            spec = props.generate('accrual_additivity', seed, self.terms)
            case = props.materialize(spec, self.terms)
            self.assertEqual(props.valid(case), [], f'seed={seed} inputs={spec}')
            for subject in spec['subjects']:
                coverage['tiers'].add(subject['tier_idx'])
                coverage['gate'].add(subject['gate_match'])
                coverage['draw'].add(subject['draw_day'])
            coverage['settlement'].add(spec['settlement_day'])
            coverage['probe'].add(spec['probe'])
            repayments += sum(len(s['repayments']) for s in case['segments'])
            accelerations += any(s['acceleration'] is not None for s in case['segments'])
        self.assertEqual(coverage['tiers'], set(range(len(self.terms.items['interest_rate']['value']['tiers']))))
        self.assertEqual(coverage['gate'], {False, True})
        self.assertIn(None, coverage['settlement'])
        self.assertEqual(coverage['probe'], {0, 1, 2, 3})
        self.assertGreater(len(coverage['draw']), 1)
        self.assertGreater(repayments, 0)
        self.assertGreater(accelerations, 0)

    def test_cap_boundary_case_present(self):
        bound = 0
        original_items = copy.deepcopy(self.terms.items)
        for offset in range(200):
            spec = props.generate('rollup_cap_check', props.SEED_BASE + offset, self.terms)
            if spec['probe'] != 2:
                continue
            case = props.materialize(spec, self.terms)
            subject = case['subjects'][0]
            interest = self.terms.items['interest_rate']['value']
            tier = interest['tiers'][spec['subjects'][0]['tier_idx']]
            annual = tier['all_in_bps_annual'] + interest['default_interest_add_bps_annual']
            probe = props.probe_terms(self.terms, annual, 0)
            cost, cap, _ = props.exact_cost(probe, subject, subject['terms']['term_days'])
            self.assertEqual(cost, cap)
            self.assertIn('SYNTHETIC_PROBE', probe.version)
            bound += 1
        self.assertEqual(bound, 50)
        self.assertEqual(original_items, self.terms.items)

    def test_shrink_keeps_valid_and_same_code(self):
        name = 'accrual_additivity'
        spec = props.generate(name, props.SEED_BASE, self.terms)
        actual_check = props.check
        visited = []
        def audited(name, case, terms):
            self.assertEqual(props.valid(case), [])
            result = actual_check(name, case, terms)
            visited.append(result)
            return result
        with mock.patch.object(overlay, 'accrual_postings', accrual_one_won(overlay.accrual_postings)), \
                mock.patch.object(props, 'check', side_effect=audited):
            initial = props.check(name, props.materialize(spec, self.terms), self.terms)
            codes = {v['code'] for v in initial}
            self.assertIn('ACCRUAL', codes)
            shrunk = props.shrink(spec, name, self.terms, codes)
            self.assertEqual(props.valid(shrunk['case']), [])
            self.assertTrue(codes.intersection(v['code'] for v in actual_check(name, shrunk['case'], self.terms)))
            self.assertTrue(shrunk['locally_minimal'])
            self.assertFalse(shrunk['exhausted'])
            # Verify the reported local minimum against every remaining valid candidate.
            for candidate in props._candidates(shrunk['spec']):
                case = props.materialize(candidate, self.terms)
                if not props.valid(case):
                    self.assertFalse(codes.intersection(v['code'] for v in actual_check(name, case, self.terms)))
        self.assertGreater(len(visited), 1)
        self.assertLess(len(json.dumps(shrunk['spec'])), len(json.dumps(spec)))

    def test_shrink_budget_reports_exhausted(self):
        name = 'accrual_additivity'
        spec = props.generate(name, props.SEED_BASE, self.terms)
        with mock.patch.object(overlay, 'accrual_postings', accrual_one_won(overlay.accrual_postings)):
            shrunk = props.shrink(spec, name, self.terms, {'ACCRUAL'}, budget=1)
        self.assertTrue(shrunk['exhausted'])
        self.assertFalse(shrunk['locally_minimal'])
        violation = {'seed': props.SEED_BASE, 'code': 'ACCRUAL', 'detail': 'one won',
                     'inputs': shrunk['spec'], 'shrink': shrunk}
        self.assertIn('not proven minimal', props.violation_message(name, violation))

    def test_violation_message_shape(self):
        with mock.patch.object(overlay, 'accrual_postings', accrual_one_won(overlay.accrual_postings)):
            first = props.run_property('accrual_additivity', 1, self.terms)
            second = props.run_property('accrual_additivity', 1, self.terms)
        self.assertEqual(first, second)
        self.assertTrue(first['violations'])
        line = props.violation_message('accrual_additivity', first['violations'][0])
        for needle in ('accrual_additivity', 'seed=74820000', 'code=ACCRUAL', 'minimal inputs=',
                       'attempts=', 'locally_minimal=', 'exhausted='):
            self.assertIn(needle, line)

    def test_valid_case_fold_rejection_is_a_violation(self):
        case = props.materialize(props.generate('accrual_additivity', props.SEED_BASE, self.terms), self.terms)
        self.assertEqual(props.valid(case), [])
        with mock.patch.object(overlay, 'advance_entries', side_effect=overlay.OverlayError('one won')):
            self.assertEqual(props.check('accrual_additivity', case, self.terms),
                             [{'code': 'FOLD_REJECTED:OverlayError', 'detail': 'one won'}])

    def test_no_tree_writes(self):
        def snapshot():
            return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for directory in ('tests/golden', 'tests/vectors', 'docs/decisions', 'capital/vendor')
                    for p in (ROOT / directory).rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts}
        before = snapshot()
        self.assertEqual(props.run_all(3, self.terms)['violations'], 0)
        self.assertEqual(before, snapshot())
        manifest = json.loads((ROOT / 'capital/vendor/manifest.json').read_text())
        for filename, expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'capital/vendor' / filename).read_bytes()).hexdigest(), expected)

    def test_cli_success_and_bad_arguments(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/finance_properties.py'),
                                 '--seeds', '5', '--check'], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'finance properties ok SIMULATED: 6 properties, 5 cases each, 0 violations\n')
        for args in (['--seeds', '0', '--check'], ['--seeds', '-1', '--check'],
                     ['--seeds', 'x', '--check'], ['--seeds', '5']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    cli.main(args)
                self.assertEqual(raised.exception.code, 2)

    def test_cli_mutation_fails_with_seed_on_stderr(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(overlay, 'accrual_postings', accrual_one_won(overlay.accrual_postings)), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(cli.main(['--seeds', '1', '--check']), 1)
        self.assertIn('seed=74820000', errors.getvalue())
        self.assertIn('minimal inputs=', errors.getvalue())
        self.assertEqual(output.getvalue(), '')

    def test_terms_not_bound_fails(self):
        missing = DecisionNoteTermsPolicy(ROOT / 'docs/decisions/NO_SUCH_NOTE.md')
        with self.assertRaisesRegex(ValueError, 'terms not bound'):
            props.run_all(1, missing)
        errors = io.StringIO()
        with mock.patch.object(props, 'DecisionNoteTermsPolicy', return_value=missing), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(cli.main(['--check', '--seeds', '1']), 1)
        self.assertIn('terms not bound', errors.getvalue())


class MutationTests(unittest.TestCase):
    def detect(self, name, code, target, attribute, mutation, cases=1):
        with mock.patch.object(target, attribute, mutation):
            result = props.run_property(name, cases)
        self.assertTrue(result['violations'], name)
        self.assertIn(code, {v['code'] for v in result['violations']}, result)

    def test_accrual_one_won(self):
        self.detect('accrual_additivity', 'ACCRUAL', overlay, 'accrual_postings',
                    accrual_one_won(overlay.accrual_postings))

    def test_allocation_one_won(self):
        self.detect('allocation_conservation', 'ALLOCATION', DecisionNoteTermsPolicy, '_repay_allocation',
                    allocation_one_won(DecisionNoteTermsPolicy._repay_allocation))

    def test_cap_one_won(self):
        for field, code in (('cap_check', 'CAP'), ('annualized_all_in_bps', 'CAP_ANNUALIZED')):
            with self.subTest(field=field):
                self.detect('rollup_cap_check', code, DecisionNoteTermsPolicy, '_portfolio_row',
                            cap_one_won(DecisionNoteTermsPolicy._portfolio_row, field), cases=3)

    def test_risk_one_won(self):
        original = risk._tally
        def mutated(*args, **kwargs):
            result = original(*args, **kwargs)
            next(iter(result.values()))['outstanding_krw'] += 1
            return result
        self.detect('risk_bucket_sums', 'RISK_BUCKET', risk, '_tally', mutated)

    def test_forecast_one_won(self):
        original = forecast._floor
        self.detect('forecast_bucket_sums', 'FORECAST_BUCKET', forecast, '_floor', lambda x: original(x) + 1)

    def test_stress_one_won(self):
        original = risk._stress_row
        def mutated(shock, subjects):
            result = original(shock, subjects)
            if shock == 0:
                result['shortfall_krw'] += 1
            return result
        self.detect('stress_monotone', 'STRESS', risk, '_stress_row', mutated)


if __name__ == '__main__':
    unittest.main()
