"""Independent table, execution, mutation and read-only drift checks."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import adapter_identity_claims as claims
from capital import observation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/adapter_identity_claims_check.py'


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT,
                          capture_output=True, text=True)


class AdapterIdentityClaimsTests(unittest.TestCase):
    def test_table_and_all_executable_checks(self):
        table = claims.load_table()
        self.assertEqual(len(table['claims']), 30)
        self.assertEqual(table['pinned_sha'], observation.CONTRACT_REVISION)
        self.assertEqual({r['check_id'] for r in table['claims']}, set(claims.CHECKS))
        result = claims.run_claims(table)
        self.assertTrue(result['ok'], result['failed'])
        self.assertEqual(result['passed'], 30)
        for row in result['rows']:
            if row['check_id'].startswith('case.'):
                self.assertEqual(row['observed']['label'], 'SIMULATED')
                self.assertTrue(row['observed']['isolation'])
                self.assertTrue(row['observed']['fake']['safe'])
                self.assertTrue(row['observed']['fake']['no_effects'])

    def test_every_matrix_case_and_scope_is_required(self):
        original = claims.load_table()
        for check in {c for _, checks in claims.CASE_MAP.values() for c in checks}:
            table = copy.deepcopy(original)
            table['claims'] = [r for r in table['claims'] if r['check_id'] != check]
            with self.subTest(check=check), self.assertRaises(claims.ClaimTableError):
                claims.validate_table(table)

    def test_invalid_table_mutations(self):
        original = claims.load_table()
        mutations = [
            lambda t: t.update(results='REAL'),
            lambda t: t.update(semantic_conformance=True),
            lambda t: t.update(pinned_sha='0' * 40),
            lambda t: t.update(label='SEMANTIC_CONFORMANCE'),
            lambda t: t['claims'].append(dict(t['claims'][0], id='unique-id')),
            lambda t: t['claims'][0].update(source_doc='../escape'),
            lambda t: t['claims'][0].update(section=claims.SECTIONS['identity.']),
            lambda t: t['claims'][0].update(needle='not in draft'),
            lambda t: t['claims'][0].update(case='lost-ack'),
            lambda t: t['claims'][0].update(case=[]),
            lambda t: t['claims'][0].pop('case'),
            lambda t: t['claims'][0]['expected'].update(case='lost-ack'),
            lambda t: t['claims'][0]['expected'].update(label='REAL'),
            lambda t: t['claims'][0]['expected']['facade'].update(evidence='AUTHENTICATED'),
            lambda t: t['claims'][0]['expected']['facade'].update(action=''),
            lambda t: t['claims'][0]['expected']['facade'].pop('boundary_note'),
            lambda t: t['claims'][0].pop('expected'),
        ]
        for mutate in mutations:
            table = copy.deepcopy(original)
            mutate(table)
            with self.subTest(mutation=mutate), self.assertRaises(claims.ClaimTableError):
                claims.validate_table(table)

    def test_excluded_kernel_and_semantic_claims(self):
        for term in (*claims.KERNEL_TERMS, 'SEMANTIC_CONFORMANCE'):
            table = claims.load_table()
            table['claims'][0]['claim'] = 'Implements ' + term
            with self.subTest(term=term), self.assertRaises(claims.ClaimTableError):
                claims.validate_table(table)

    def test_unmapped_check_fails_only_one_row(self):
        table = claims.load_table()
        reduced = dict(claims.CHECKS)
        del reduced['case.redelivery']
        result = claims.run_claims(table, checks=reduced)
        self.assertEqual([r['check_id'] for r in result['failed']], ['case.redelivery'])
        self.assertTrue(result['failed'][0]['unmapped'])
        row = copy.deepcopy(next(r for r in table['claims'] if r['check_id'] == 'identity.transmission'))
        row.update(id='unmapped', check_id='identity.x')
        table['claims'].append(row)
        result = claims.run_claims(table)
        self.assertEqual([r['id'] for r in result['failed']], ['unmapped'])

    def test_wrong_function_fails_case_even_for_equal_fake_outputs(self):
        checks = dict(claims.CHECKS, **{'case.redelivery': claims.check_lost_ack})
        result = claims.run_claims(claims.load_table(), checks=checks)
        self.assertEqual([r['check_id'] for r in result['failed']], ['case.redelivery'])
        self.assertEqual(result['failed'][0]['observed']['case'], 'lost-ack')

    def test_transmission_in_key_drift_fails(self):
        class TransmissionKey(observation.LocalFakeObservation):
            def fold(self, facts, *, bindings):
                facts = copy.deepcopy(facts)
                for fact in facts:
                    fact['item_key'] += fact['transmission']['id']
                return super().fold(facts, bindings=bindings)
        with patch.object(observation, 'LocalFakeObservation', TransmissionKey):
            value = claims.check_new_transmission()
        expected = next(r['expected'] for r in claims.load_table()['claims'] if r['check_id'] == 'case.new-transmission')
        self.assertNotEqual(value, expected)
        self.assertEqual(value['fake']['items'], 2)

    def test_overwritten_conflict_original_fails(self):
        class Overwrite(observation.LocalFakeObservation):
            def fold(self, facts, *, bindings):
                value = super().fold(facts, bindings=bindings)
                if value['conflicts']:
                    value['event_items'][0]['normalized_fact'] = value['conflicts'][0]['incoming']
                return value
        with patch.object(observation, 'LocalFakeObservation', Overwrite):
            value = claims.check_conflict()
        self.assertFalse(value['fake']['originals_preserved'])
        self.assertEqual(value['fake']['statuses'], ['CONFLICT'])
        self.assertEqual(value['fake']['duplicates'], [2])

    def test_method_added_to_scope_drift_fails(self):
        class MethodScope(observation.LocalFakeObservation):
            def fold(self, facts, *, bindings):
                facts = copy.deepcopy(facts)
                for fact in facts:
                    fact['item_key'] += fact['method']
                return super().fold(facts, bindings=bindings)
        with patch.object(observation, 'LocalFakeObservation', MethodScope):
            result = claims.run_claims(claims.load_table())
        self.assertIn('case.other-scope.method', [r['check_id'] for r in result['failed']])

    def test_fold_cannot_mutate_facade(self):
        service, bodies = claims._fresh()
        class Mutating(observation.LocalFakeObservation):
            def fold(self, facts, *, bindings):
                result = super().fold(facts, bindings=bindings)
                service.receipts.clear()
                return result
        with patch.object(claims, '_fresh', return_value=(service, bodies)), patch.object(observation, 'LocalFakeObservation', Mutating):
            value = claims.check_snapshot_repeat()
        self.assertFalse(value['isolation'])

    def test_scope_labels_and_documented_method_divergence(self):
        result = claims.run_claims(claims.load_table())
        rows = {r['check_id']: r['observed'] for r in result['rows']}
        for field in ('provider', 'account', 'profile-version'):
            self.assertEqual(rows['case.other-scope.' + field]['facade']['evidence'], 'ISOLATION_ONLY')
        method = rows['case.other-scope.method']['fake']
        self.assertEqual(method['fixture_divergence'], 'METHOD_IS_CONTENT_NOT_SCOPE_IN_LOCAL_PROFILE')
        self.assertEqual(method['statuses'], ['CONFLICT'])
        self.assertTrue(method['originals_preserved'])
        self.assertEqual(rows['case.unmatched']['fake']['binding_statuses'], ['UNMATCHED'])

    def test_safety_flag_drift_fails(self):
        class Unsafe(observation.LocalFakeObservation):
            def fold(self, facts, *, bindings):
                result = super().fold(facts, bindings=bindings)
                result['deliveries'][0]['applied'] = True
                return result
        with patch.object(observation, 'LocalFakeObservation', Unsafe):
            self.assertFalse(claims.check_redelivery()['fake']['safe'])

    def test_cli_bare_is_skipped_not_passed(self):
        for args in ((), ('--protocol-dir', '')):
            proc = run(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.startswith('SKIPPED\n'))
            self.assertNotIn('passed', proc.stdout)

    def test_cli_execute_is_simulated(self):
        proc = run('--execute')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('CLAIM_CONFORMANCE passed=30 total=30 failed=0', proc.stdout)
        self.assertIn('RESULTS SIMULATED', proc.stdout)
        self.assertNotIn('SEMANTIC_CONFORMANCE', proc.stdout)

    def test_cli_bad_table_and_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            for text in ('{', '{}'):
                path.write_text(text)
                self.assertEqual(run('--execute', '--table', str(path)).returncode, 2)
            self.assertEqual(run('--protocol-dir', str(path)).returncode, 1)
            self.assertEqual(run('--protocol-dir', str(path.parent / 'missing')).returncode, 1)

    def test_read_only_drift_and_missing_needle(self):
        table = claims.load_table()
        text = '\n'.join(dict.fromkeys(r[k] for r in table['claims'] for k in ('section', 'needle')))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / claims.SOURCE_DOC
            path.parent.mkdir(parents=True)
            path.write_text(text)
            path.chmod(0o444)
            before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            report = claims.check_protocol(tmp, table)
            self.assertEqual(report['status'], 'verified')
            proc = run('--protocol-dir', tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('verified=30 total=30', proc.stdout)
            # A synthetic citation document is not the complete pinned source.
            self.assertIn('SOURCE_SHA256 differs', proc.stdout)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode), before)
            path.chmod(0o600)
            path.write_text(text.replace('같은 전송이 다시 도착', 'removed'))
            report = claims.check_protocol(tmp, table)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['verified'], 29)
            self.assertEqual(run('--protocol-dir', tmp).returncode, 1)


if __name__ == '__main__':
    unittest.main()
