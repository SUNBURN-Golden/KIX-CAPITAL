"""Read-only decision binding fence and isolated drift mutations."""
import ast
import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load('decision_bindings', ROOT / 'scripts/decision_bindings.py')
acceptance = load('binding_acceptance', ROOT / 'scripts/acceptance.py')


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = checker.read_json(ROOT / 'tests/decision_bindings.json')

    def setUp(self):
        self.data = copy.deepcopy(self.mapping)

    def findings(self, root=ROOT):
        return checker.collect_findings(root, self.data)

    def assertDrift(self, needle, root=ROOT):
        found = self.findings(root)
        self.assertTrue(any(needle in finding for finding in found), found)
        self.assertEqual(found, sorted(set(found)))

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for folder in ('docs', 'capital', 'scripts'):
            shutil.copytree(ROOT / folder, root / folder,
                            ignore=shutil.ignore_patterns('vendor', '__pycache__'))
        (root / 'tests').mkdir()
        for path in (ROOT / 'tests').glob('test_*.py'):
            shutil.copy2(path, root / 'tests' / path.name)
        return root

    def test_real_tree_and_sorted_inventory(self):
        self.assertEqual(self.findings(), [])
        identities = [(row['decision_id'], row['entry']) for row in self.data['entries']]
        self.assertEqual(identities, sorted(set(identities)))

    def test_each_parked_entry_is_pending_with_node_and_anchor(self):
        nodes = {'repayment-posting-decision': 'overlay-repayment-posting',
                 'default-recovery-decision': 'overlay-recovery-writeoff',
                 'claim-slice-registry-decision': 'claim-slice-registry',
                 'closeout-artifact-decision': 'closeout-evidence-vector'}
        for row in self.data['entries']:
            if row['decision_id'] in nodes:
                for binding in row['bindings']:
                    self.assertEqual(binding['status'], 'PENDING_CONSUMER')
                    self.assertEqual(binding['consumer_node'], nodes[row['decision_id']])
                    self.assertTrue(binding['reason'])
                    self.assertTrue((ROOT / binding['path']).is_file())

    def test_bundling_is_consumed_while_future_seed_budget_stays_pending(self):
        consumed = {
            'artifact_digest_policy': 'scripts/build_release.py',
            'build_reproducibility': 'tests/test_release.py',
            'handbook_and_release_docs': 'tests/test_handbook.py',
            'not_bound_labeling': 'tests/test_release.py',
            'notes_bundling_scope': 'scripts/build_release.py',
            'version_source_disclosure': 'tests/test_release.py',
        }
        found = set()
        for row in self.data['entries']:
            if row['decision_id'] == 'artifact-docs-bundling-decision':
                found.add(row['entry'])
                self.assertEqual(len(row['bindings']), 1)
                binding, = row['bindings']
                self.assertEqual(binding['status'], 'CONSUMED')
                self.assertEqual(binding['path'], consumed[row['entry']])
                self.assertNotIn('reason', binding)
                self.assertNotIn('consumer_node', binding)
            elif (row['decision_id'], row['entry']) == ('demo-book-profile-decision', 'portfolio_scale_target'):
                self.assertTrue(all(binding['status'] == 'PENDING_CONSUMER'
                                    and binding['consumer_node'] == 'demo-book-seed'
                                    for binding in row['bindings']))
        self.assertEqual(found, set(consumed))

    def test_missing_entry(self):
        self.data['entries'].pop()
        self.assertDrift('ADOPTED entry lacks binding')

    def test_empty_bindings(self):
        self.data['entries'][0]['bindings'] = []
        self.assertDrift('requires bindings')

    def test_stale_entry(self):
        self.data['entries'][0]['entry'] = 'unknown'
        self.assertDrift('not an ADOPTED entry')

    def test_duplicate_entry_and_binding(self):
        self.data['entries'].append(copy.deepcopy(self.data['entries'][0]))
        self.data['entries'][0]['bindings'] *= 2
        self.assertDrift('duplicate binding entry')
        self.assertDrift('duplicate binding')

    def test_wrong_provenance(self):
        self.data['entries'][0]['note'] = 'docs/decisions/OTHER.md'
        self.assertDrift('mismatched note')

    def test_strict_shapes(self):
        for value in (None, [], {}, {'schema': 'wrong', 'entries': []}):
            with self.subTest(value=value):
                self.assertIn('invalid binding map schema', checker.collect_findings(ROOT, value))
        self.data['entries'][0]['extra'] = True
        self.assertDrift('invalid binding entry shape')

    def test_invalid_binding_shapes(self):
        original = copy.deepcopy(self.data['entries'][0]['bindings'][0])
        for patch in ({'kind': 'document'}, {'status': 'ADOPTED'}, {'extra': 'x'}, {'path': []}):
            with self.subTest(patch=patch):
                self.data['entries'][0]['bindings'] = [dict(original, **patch)]
                self.assertDrift('invalid binding shape')

    def test_pending_metadata_required(self):
        row = next(row for row in self.data['entries'] if row['decision_id'] == 'repayment-posting-decision')
        for key in ('consumer_node', 'reason'):
            old = row['bindings'][0].pop(key)
            self.assertDrift('pending consumer metadata')
            row['bindings'][0][key] = old

    def test_bad_paths_and_kinds(self):
        binding = self.data['entries'][0]['bindings'][0]
        for path in ('capital/missing.py', '../capital/coa.py', '/etc/passwd',
                     'tests/test_terms.py', 'capital/static/app.js', 'capital/vendor/credit_advance_f04/credit_fsm.py'):
            with self.subTest(path=path):
                binding['path'] = path
                self.assertDrift('missing or invalid module')
        binding.update(kind='test_module', path='capital/coa.py')
        self.assertDrift('missing or invalid test_module')

    def test_deleted_target_and_escaping_symlink(self):
        root = self.fixture()
        target = root / 'capital/coa.py'
        target.unlink()
        self.assertDrift('missing or invalid module capital/coa.py', root)
        target.symlink_to(ROOT / 'capital/coa.py')
        self.assertDrift('missing or invalid module capital/coa.py', root)

    def test_route_method_and_exact_id(self):
        binding = next(row['bindings'][0] for row in self.data['entries'] if row['entry'] == 'production_authorization')
        for method, route in (('POST', '/api/readiness'), ('GET', '/api/underwrite/{advance_id}')):
            binding.update(method=method, route_id=route)
            self.assertDrift('missing route')
        binding.update(method='GET', route_id='/api/underwrite/')
        self.assertEqual(self.findings(), [])

    def test_removed_route_and_permission_drift(self):
        root = self.fixture()
        path = root / 'capital/server.py'
        text = path.read_text()
        path.write_text(text.replace("    ('/api/readiness', False, 'readiness'),\n", ''))
        self.assertDrift('route registry invalid', root)
        path = root / 'capital/auth.py'
        text = path.read_text()
        path.write_text('\n'.join(line for line in text.splitlines() if "('/api/readiness'," not in line))
        self.assertDrift('missing route', root)

    def test_new_adopted_entry_and_duplicate_identity(self):
        root = self.fixture()
        path = root / 'docs/decisions/CAPITAL_FINANCIAL_TERMS.md'
        text = path.read_text()
        block = checker.ledger.extract_blocks(text)[0]
        block['entries']['new_entry'] = copy.deepcopy(block['entries']['fees'])
        path.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
        self.assertDrift('financial-terms-decision/new_entry: ADOPTED entry lacks binding', root)
        (path.parent / 'DUPLICATE.md').write_text(path.read_text())
        self.assertDrift('duplicate decision_id financial-terms-decision', root)

    def test_invalid_note(self):
        root = self.fixture()
        (root / 'docs/decisions/CAPITAL_FINANCIAL_TERMS.md').write_text('not a block')
        self.assertDrift('expected exactly one', root)

    def test_discovered_consumers_cannot_be_removed_or_pending(self):
        row = next(row for row in self.data['entries'] if row['entry'] == 'interest_rate')
        row['bindings'] = [{'kind': 'test_module', 'path': 'tests/test_terms.py', 'status': 'CONSUMED'}]
        self.assertDrift('unlisted CONSUMED module capital/terms.py')
        row['bindings'] = [{'kind': 'module', 'path': 'capital/terms.py', 'status': 'PENDING_CONSUMER',
                            'consumer_node': 'fake', 'reason': 'not consumed'}]
        self.assertDrift('unlisted CONSUMED module capital/terms.py')

    def test_new_recognized_consumer_is_unlisted(self):
        root = self.fixture()
        (root / 'capital/new_consumer.py').write_text(
            "NOTE = 'docs/decisions/CAPITAL_FINANCIAL_TERMS.md'\ndef consume(entries):\n    return entries['fees']['value']\n")
        self.assertDrift('financial-terms-decision/fees: unlisted CONSUMED module capital/new_consumer.py', root)

    def test_recognizer_covers_current_idioms_not_generic_enumeration(self):
        rows = checker.ledger.build_index(ROOT / 'docs/decisions', [])
        found = checker.discover_consumers(checker.inventory(ROOT, []), rows)
        for decision, entry, path in (
                ('financial-terms-decision', 'fees', 'capital/terms.py'),
                ('settlement-policy-decision', 'allocation_order', 'capital/policy.py'),
                ('settlement-policy-decision', 'refund_bearer', 'capital/shadow.py'),
                ('overlay-state-decision', 'overlay_capacity_bounds', 'capital/overlay.py'),
                ('overlay-digest-export-decision', 'clock_command_authority', 'capital/overlay.py')):
            self.assertIn((decision, entry, path), found)
        self.assertFalse(any(path == 'capital/decisions.py' for _, _, path in found))
        tree = ast.parse("NOTE='CAPITAL_FINANCIAL_TERMS.md'\ndef consume(self):\n return self._value('fees'), self._ready('term')\n")
        self.assertEqual(checker.discover_consumers({'capital/new.py': tree}, rows), {
            ('financial-terms-decision', 'fees', 'capital/new.py'),
            ('financial-terms-decision', 'term', 'capital/new.py')})

    def test_cli_read_only_and_malformed_json(self):
        root = self.fixture()
        path = root / 'tests/decision_bindings.json'
        path.write_text(json.dumps(self.data))
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(checker.main(['--check', '--root', str(root)]), 0)
        proc = subprocess.run([sys.executable, str(root / 'scripts/decision_bindings.py'), '--check',
                               '--root', str(root)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})
        for text in ('{', '{"schema":1,"schema":2}', 'null'):
            path.write_text(text)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(checker.main(['--check', '--root', str(root)]), 1)

    def test_acceptance_wiring_and_failure_propagation(self):
        stage = acceptance.build_plan()[0]
        self.assertEqual(stage['commands'], [
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
            [sys.executable, 'scripts/decision_bindings.py', '--check']])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(acceptance, 'run_argv', side_effect=[(0, 'Ran 1 test\nOK', ''), (1, '', 'drift')]), \
                mock.patch.object(acceptance, 'head_sha', return_value=('fixture', None)), \
                mock.patch.object(acceptance, 'tool_versions', return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            evidence = Path(tmp) / 'evidence.json'
            self.assertEqual(acceptance.execute_plan([stage], root=ROOT, evidence_path=evidence, required=('unit',)), 1)
            data = json.loads(evidence.read_text())
            self.assertFalse(data['ok'])
            self.assertEqual(data['stages'][0]['status'], 'failed')
            self.assertEqual(data['stages'][0]['commands'][1]['exit_code'], 1)


if __name__ == '__main__':
    unittest.main()
