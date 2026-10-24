"""Lifecycle claims: table, real loopback behavior, citation provenance and CLI."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import lifecycle_claims as lc

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/lifecycle_claims_check.py'


class TableTests(unittest.TestCase):
    def test_table_covers_every_behavior_and_clause(self):
        table = lc.load_table()
        self.assertEqual(len(table['claims']), 12)
        self.assertEqual({r['check_id'] for r in table['claims']}, set(lc.CHECKS))
        self.assertEqual({r['clause'] for r in table['claims']}, {'LC-TERM', 'LC-CUT', 'LC-FACT'})

    def test_invalid_tables_fail_closed(self):
        mutations = [
            lambda t: t.update(funds_executed=0),
            lambda t: t.update(simulation='REAL'),
            lambda t: t.update(pinned_sha='0' * 40),
            lambda t: t['claims'].pop(),
            lambda t: t['claims'].append(copy.deepcopy(t['claims'][0])),
        ]
        for field, value in [('source_doc', '../escape'), ('source_doc', 'other.md'),
                             ('check_id', 'unmapped'), ('needle', ' '), ('mapping', ''),
                             ('clause', 'other'), ('pinned_sha', '0' * 40),
                             ('section', 'not a heading')]:
            mutations.append(lambda t, f=field, v=value: t['claims'][0].update({f: v}))
        for mutate in mutations:
            table = lc.load_table()
            mutate(table)
            with self.subTest(table=table['claims'][0]), self.assertRaises(lc.ClaimTableError):
                lc.validate_table(table)

    def test_load_uses_full_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'claims.json'
            for text in ('{', '[]', json.dumps({**lc.load_table(), 'funds_executed': True})):
                path.write_text(text)
                with self.assertRaises(lc.ClaimTableError):
                    lc.load_table(path)

    def test_nonexecution_flags_are_checked_recursively(self):
        for value in (True, 0, None, 'false'):
            with self.assertRaises(lc.ClaimTableError):
                lc._assert_no_funds({'nested': [{'funds_executed': value}]})
        lc._assert_no_funds({'nested': [{'funds_executed': False}]})

    def test_failure_reports_keep_labels_and_never_hide_unmapped_checks(self):
        with patch.dict(lc.CHECKS, {'first.accepted': lambda: {'wrong': True}}):
            # Execute only one check for this reporting regression; other checks
            # raise explicitly, so no fabricated loopback successes are reported.
            replacements = {key: lambda: (_ for _ in ()).throw(RuntimeError('SIMULATED failure'))
                            for key in lc.CHECKS if key != 'first.accepted'}
            with patch.dict(lc.CHECKS, replacements):
                report = lc.run_claims(lc.load_table())
        self.assertFalse(report['ok'])
        self.assertEqual(report['passed'], 0)
        for item in [report, *report['rows'], *report['failed']]:
            self.assertEqual(item['label'], 'CLAIM_CONFORMANCE')
            self.assertEqual(item['simulation'], 'SIMULATED')
            self.assertIs(item['funds_executed'], False)


class LoopbackTests(unittest.TestCase):
    def test_all_claims_execute_real_http(self):
        report = lc.run_claims(lc.load_table())
        self.assertTrue(report['ok'], json.dumps(report['failed'], indent=2))
        self.assertEqual(report['passed'], 12)
        for row in report['rows']:
            self.assertIs(row['funds_executed'], False)
            self.assertEqual(row['simulation'], 'SIMULATED')
            self.assertEqual(row['label'], 'CLAIM_CONFORMANCE')

    def test_cleanup_after_scenario_exception(self):
        server = None
        with self.assertRaisesRegex(RuntimeError, 'scenario failed'):
            with lc._facade() as client:
                server = client.server
                self.assertEqual(server.server_address[0], '127.0.0.1')
                raise RuntimeError('scenario failed')
        self.assertEqual(server.socket.fileno(), -1)


class CitationTests(unittest.TestCase):
    def test_no_checkout_is_explicitly_skipped(self):
        report = lc.check_protocol(None)
        self.assertEqual(report['status'], 'SKIPPED')
        self.assertEqual(report['verified'], 0)
        self.assertEqual(report['simulation'], 'SIMULATED')
        self.assertIs(report['funds_executed'], False)

    def test_fixture_checks_identity_and_section_local_needles(self):
        # Synthetic source blob supplied by a mocked read-only git show.
        # No commits, copied upstream document or modifications to Protocol.
        table = lc.load_table()
        sections = {}
        for row in table['claims']:
            sections.setdefault(row['section'], set()).add(row['needle'])
        text = '\n'.join(section + '\n' + '\n'.join(sorted(needles))
                         for section, needles in sections.items()) + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / lc.SOURCE_DOC
            source.parent.mkdir(parents=True)
            source.write_text(text)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            reply = subprocess.CompletedProcess([], 0, stdout=text.encode())
            with patch.object(lc.subprocess, 'run', return_value=reply) as show:
                self.assertEqual(lc.check_protocol(root, table)['status'], 'verified')
                show.assert_called_once_with(
                    ['git', '-C', str(root), 'show', f'{lc.PINNED_SHA}:{lc.SOURCE_DOC}'],
                    capture_output=True, check=True, timeout=10)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
                for field, value in [('needle', 'missing needle'), ('section', '## missing section'),
                                     ('needle', table['claims'][-1]['needle'])]:
                    changed = copy.deepcopy(table)
                    changed['claims'][0][field] = value
                    self.assertEqual(lc.check_protocol(root, changed)['status'], 'failed')
                source.write_text(text + '\ndrift\n')
                self.assertEqual(lc.check_protocol(root, table)['verified'], 0)
                source.unlink()
                outside = root / 'outside.md'
                outside.write_text(text)
                source.symlink_to(outside)
                # Symlink stays inside root here; content matches. Outside root
                # symlinks must fail independently of heading/needle matches.
                with tempfile.TemporaryDirectory() as other:
                    target = Path(other) / 'source.md'
                    target.write_text(text)
                    source.unlink()
                    source.symlink_to(target)
                    self.assertEqual(lc.check_protocol(root, table)['status'], 'failed')
            with patch.object(lc.subprocess, 'run', side_effect=subprocess.CalledProcessError(128, 'git')):
                self.assertEqual(lc.check_protocol(root, table)['verified'], 0)

    def test_missing_directory_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(lc.check_protocol(Path(tmp) / 'missing')['status'], 'failed')


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=30)

    def test_default_skips_citations_without_success_count(self):
        proc = self.run_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.startswith('SKIPPED\n'))
        self.assertNotIn('passed=', proc.stdout)
        self.assertIn('"funds_executed": false', proc.stdout)

    def test_execute_reports_behavior_and_citation_skip_separately(self):
        proc = self.run_cli('--execute')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('CLAIM_CONFORMANCE passed=12 total=12 failed=0', proc.stdout)
        self.assertIn('\nSKIPPED\n', proc.stdout)
        self.assertNotIn('local_token', proc.stdout)

    def test_invalid_table_exits_two_even_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.json'
            path.write_text('{}')
            proc = self.run_cli('--table', str(path))
        self.assertEqual(proc.returncode, 2)
        self.assertIn('"simulation": "SIMULATED"', proc.stderr)
        self.assertNotIn('passed=', proc.stdout)

    def test_behavior_mismatch_and_drift_exit_one(self):
        table = lc.load_table()
        table['claims'][0]['expected'] = 'DELIBERATE_FAILURE'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'claims.json'
            path.write_text(json.dumps(table))
            proc = self.run_cli('--execute', '--table', str(path))
            self.assertEqual(proc.returncode, 1)
            proc = self.run_cli('--protocol-dir', str(Path(tmp) / 'missing'))
            self.assertEqual(proc.returncode, 1)
            self.assertIn('verified=0', proc.stdout)


if __name__ == '__main__':
    unittest.main()
