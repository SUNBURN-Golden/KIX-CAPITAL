"""Acceptance ladder evidence, missing stages, and an injected failure."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location('acceptance', ROOT / 'scripts' / 'acceptance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acceptance = _load()


def _ok_stage(stage_id, passed=2):
    script = f'print("Ran {passed} tests in 0.001s\\n\\nOK")'
    return {
        'id': stage_id,
        'timeout': 20,
        'commands': [[sys.executable, '-c', script]],
    }


class AcceptanceTests(unittest.TestCase):
    def test_default_plan_is_the_six_required_stages(self):
        plan = acceptance.build_plan(ROOT)
        self.assertEqual([stage['id'] for stage in plan], list(acceptance.REQUIRED_STAGES))
        commands = {stage['id']: stage['commands'] for stage in plan}
        self.assertEqual(commands['unit'][0][1:5], ['-m', 'unittest', 'discover', '-s'])
        self.assertEqual(commands['unit'][0][5], 'tests')
        self.assertIn('test_mock_credit.py', commands['pinned-vendor'][0])
        self.assertEqual(commands['node-check'][0][1:], ['--check', 'capital/static/app.js'])
        self.assertEqual(commands['browser'][0], ['npm', 'run', 'test:browser'])
        self.assertEqual(commands['packaged-smoke'][0][1:], ['scripts/build_release.py', '--out', 'build/acceptance-dist'])
        self.assertEqual(commands['seeded-demo'][0][1:], ['scripts/seed_demo.py'])
        workflow = (ROOT / '.github' / 'workflows' / 'verify.yml').read_text(encoding='utf-8')
        self.assertIn('python3 scripts/acceptance.py', workflow)
        self.assertIn('acceptance-evidence', workflow)
        self.assertIn('build/', (ROOT / '.gitignore').read_text(encoding='utf-8'))
        spec = (ROOT / 'tests' / 'browser' / 'acceptance-views.spec.cjs').read_text(encoding='utf-8')
        for name in (
            'portfolio', 'case', 'projection', 'statement', 'reconciliation',
            'readiness', 'role-organizer', 'role-auditor', 'role-observer',
        ):
            self.assertIn(name, spec)
        self.assertIn('375', spec)
        self.assertIn('console', spec)

    def test_injected_failing_stage_writes_evidence_and_exits_nonzero(self):
        plan = acceptance.inject_failure([_ok_stage(stage_id) for stage_id in acceptance.REQUIRED_STAGES], 'node-check')
        node = next(stage for stage in plan if stage['id'] == 'node-check')
        self.assertTrue(node['injected'])
        self.assertEqual(node['commands'], [[sys.executable, '-c', 'import sys; sys.exit(1)']])
        unit = next(stage for stage in plan if stage['id'] == 'unit')
        self.assertNotIn('injected', unit)
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'acceptance-evidence.json'
            code = acceptance.execute_plan(
                plan, root=ROOT, evidence_path=evidence, required=acceptance.REQUIRED_STAGES)
            self.assertEqual(code, 1)
            data = json.loads(evidence.read_text(encoding='utf-8'))
        self.assertFalse(data['ok'])
        self.assertEqual(data['label'], 'SIMULATED')
        self.assertFalse(data['funds_executed'])
        self.assertEqual(data['head_sha'], acceptance.head_sha(ROOT)[0])
        self.assertTrue(data['vendor_hashes']['verified'])
        self.assertEqual(data['vendor_hashes']['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertEqual(data['golden_digests']['status'], 'recorded')
        self.assertEqual(len(data['golden_digests']['state_digest']), 64)
        self.assertEqual(len(data['golden_digests']['content_digest']), 64)
        self.assertIn('debit', data['golden_digests']['projection_totals'])
        self.assertIn('python', data['tool_versions'])
        failed = next(stage for stage in data['stages'] if stage['id'] == 'node-check')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['exit_code'], 1)
        self.assertEqual(failed['commands'][0]['exit_code'], 1)
        self.assertTrue(failed['injected'])
        passed = next(stage for stage in data['stages'] if stage['id'] == 'unit')
        self.assertEqual(passed['status'], 'passed')
        self.assertEqual(passed['exit_code'], 0)
        self.assertEqual(passed['test_count']['passed'], 2)

    def test_missing_stage_is_unrun_and_fails(self):
        plan = [_ok_stage(stage_id) for stage_id in acceptance.REQUIRED_STAGES if stage_id != 'browser']
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'acceptance-evidence.json'
            code = acceptance.execute_plan(
                plan, root=ROOT, evidence_path=evidence, required=acceptance.REQUIRED_STAGES)
            self.assertEqual(code, 1)
            data = json.loads(evidence.read_text(encoding='utf-8'))
        browser = next(stage for stage in data['stages'] if stage['id'] == 'browser')
        self.assertEqual(browser['status'], 'unrun')
        self.assertIsNone(browser['exit_code'])
        self.assertEqual(browser['commands'], [])
        self.assertFalse(data['ok'])

    def test_seed_and_smoke_lines_count_as_checks(self):
        seed = acceptance.parse_test_count('seed demo ok SIMULATED state_digest=abc\n')
        self.assertEqual(seed, {'ran': 1, 'passed': 1, 'failed': 0})
        smoke = acceptance.parse_test_count('smoke ok: version-flag, state-version\n')
        self.assertEqual(smoke, {'ran': 2, 'passed': 2, 'failed': 0})
        mixed = acceptance.parse_test_count('seed demo ok SIMULATED\nRan 4 tests in 0.1s\n\nOK\n')
        self.assertEqual(mixed, {'ran': 4, 'passed': 4, 'failed': 0})

    def test_unknown_inject_target_exits_two(self):
        self.assertEqual(acceptance.main(['--inject-fail', 'not-a-stage', '--evidence', '/tmp/unused-acceptance.json']), 2)


if __name__ == '__main__':
    unittest.main()
