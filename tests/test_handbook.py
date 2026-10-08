"""Operator handbook, acceptance checklist, and the generated NOT_BOUND block."""
import ast
import http.client
import importlib.util
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path

from capital.server import make_server
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / 'docs' / 'ACCEPTANCE_KO.md'
HANDBOOK = ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md'
README = ROOT / 'README.md'
DOCS = (
    'docs/OPERATOR_HANDBOOK_KO.md',
    'docs/CAP_COVERAGE.md',
    'docs/ACCEPTANCE_KO.md',
)
_STEP = re.compile(r'^\d+\.\s')
_VERIFY = re.compile(r'검증:\s*(tests/\S+?\.py|tests/browser/\S+?\.cjs)::(.+?)\s*$')
_EVIDENCE = re.compile(
    r'evidence\.((?:\*|[A-Za-z_][A-Za-z0-9_]*(?:\[\*])?)(?:\.(?:\*|[A-Za-z_][A-Za-z0-9_]*(?:\[\*])?))*)')
_TITLE = re.compile(r"""\btest\(\s*(['"])(.*?)\1""", re.DOTALL)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acceptance_ladder = _load('acceptance_ladder', ROOT / 'scripts' / 'acceptance.py')
checklist = _load('not_bound_checklist', ROOT / 'scripts' / 'not_bound_checklist.py')


def _section(text, heading):
    """Body under heading, up to the next heading of the same or higher level."""
    if text.startswith(heading):
        start = 0
    else:
        found = text.find('\n' + heading)
        if found < 0:
            return ''
        start = found + 1
    level = len(heading) - len(heading.lstrip('#'))
    rest = text[start + len(heading):]
    nxt = re.search(r'\n#{1,%d} ' % level, rest)
    if nxt:
        rest = rest[:nxt.start()]
    return rest


def _python_has(path, class_name, method_name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return True
    return False


def _titles(spec_text):
    return [match.group(2) for match in _TITLE.finditer(spec_text)]


def _resolve(node, parts):
    if not parts:
        return True
    part = parts[0]
    rest = parts[1:]
    if part == '*':
        if type(node) is not dict or not node:
            return False
        return all(_resolve(value, rest) for value in node.values())
    starred = part.endswith('[*]')
    key = part[:-3] if starred else part
    if type(node) is not dict or key not in node:
        return False
    child = node[key]
    if starred:
        if type(child) is not list or not child:
            return False
        return all(_resolve(item, rest) for item in child)
    return _resolve(child, rest)


def _sample_evidence():
    plan = []
    for stage_id in acceptance_ladder.REQUIRED_STAGES:
        script = 'print("Ran 2 tests in 0.001s\\n\\nOK")'
        plan.append({
            'id': stage_id,
            'timeout': 20,
            'commands': [[__import__('sys').executable, '-c', script]],
        })
    with tempfile.TemporaryDirectory() as tmp:
        evidence = Path(tmp) / 'acceptance-evidence.json'
        code = acceptance_ladder.execute_plan(
            plan, root=ROOT, evidence_path=evidence, required=acceptance_ladder.REQUIRED_STAGES)
        data = json.loads(evidence.read_text(encoding='utf-8'))
    return code, data


class HandbookTests(unittest.TestCase):
    def test_readme_links_the_three_docs(self):
        readme = README.read_text(encoding='utf-8')
        for doc in DOCS:
            self.assertRegex(readme, r'\[[^\]]+\]\(' + re.escape(doc) + r'\)')
            self.assertTrue((ROOT / doc).is_file(), doc)

    def test_handbook_has_operator_section_and_workspace_codes(self):
        text = HANDBOOK.read_text(encoding='utf-8')
        self.assertIn('<!-- handbook-section:operator-handbook-ko -->', text)
        self.assertIn('<!-- /handbook-section -->', text)
        for code in ('WORKSPACE_UNREADABLE', 'WORKSPACE_LOCKED', 'WORKSPACE_WRITE_FAILED'):
            self.assertIn(code, text)
        self.assertIn('python3 -m capital.server', text)
        self.assertIn('capital-<version>.pyz', text)
        self.assertIn('--workspace', text)

    def test_walkthrough_steps_name_real_tests(self):
        text = ACCEPTANCE.read_text(encoding='utf-8')
        steps = [line for line in text.splitlines() if _STEP.match(line.strip())]
        self.assertGreaterEqual(len(steps), 6)
        for line in steps:
            self.assertIn('검증:', line)
            match = _VERIFY.search(line.strip())
            self.assertIsNotNone(match, line)
            relative, target = match.group(1), match.group(2)
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            if relative.endswith('.py'):
                class_name, method_name = target.split('.')
                self.assertTrue(_python_has(path, class_name, method_name), target)
            else:
                titles = _titles(path.read_text(encoding='utf-8'))
                self.assertTrue(any(target in title for title in titles), (target, titles))
        for role in ('organizer', 'auditor', 'observer'):
            body = _section(text, f'### {role}')
            role_steps = [line for line in body.splitlines() if _STEP.match(line.strip())]
            self.assertGreaterEqual(len(role_steps), 1, role)

    def test_human_checklist_criteria_match_evidence_fields(self):
        text = ACCEPTANCE.read_text(encoding='utf-8')
        section = _section(text, '## 사람 점검표')
        items = []
        current = None
        for line in section.splitlines():
            if line.startswith('- [ ]') or line.startswith('- [x]'):
                current = [line]
                items.append(current)
            elif current is not None:
                current.append(line)
        self.assertGreaterEqual(len(items), 5)
        for stage_id in acceptance_ladder.REQUIRED_STAGES:
            self.assertIn(stage_id, section)
        paths = set()
        for item in items:
            blob = '\n'.join(item)
            self.assertIn('PASS:', blob)
            self.assertIn('FAIL:', blob)
            paths.update(_EVIDENCE.findall(blob))
        self.assertIn('ok', paths)
        self.assertIn('stages[*].status', paths)
        self.assertIn('tool_versions.*', paths)
        _code, evidence = _sample_evidence()
        self.assertEqual(evidence['label'], 'SIMULATED')
        self.assertIs(evidence['funds_executed'], False)
        self.assertEqual([stage['id'] for stage in evidence['stages']], list(acceptance_ladder.REQUIRED_STAGES))
        for path in sorted(paths):
            self.assertTrue(_resolve(evidence, path.split('.')), path)

    def test_not_bound_block_matches_readiness_and_drift_fails(self):
        document = ACCEPTANCE.read_text(encoding='utf-8')
        block = checklist.render()
        self.assertNotIn('instance_id', block)
        self.assertEqual(checklist.extract_generated(document), block)
        self.assertIn('upstream_binding: NOT_BOUND', block)
        self.assertIn('source_integrity.all_matched: true', block)
        mutated = document.replace('upstream_binding: NOT_BOUND', 'upstream_binding: BOUND', 1)
        self.assertNotEqual(checklist.extract_generated(mutated), block)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ACCEPTANCE_KO.md'
            path.write_text(mutated, encoding='utf-8')
            self.assertEqual(checklist.main(['--check', '--file', str(path)]), 1)
            path.write_text(document, encoding='utf-8')
            self.assertEqual(checklist.main(['--check', '--file', str(path)]), 0)

    def test_http_readiness_groups_match_in_process(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            client.request('GET', '/api/readiness')
            response = client.getresponse()
            payload = json.loads(response.read().decode('utf-8'))
            status = response.status
            client.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
        self.assertEqual(status, 200)
        in_process = CapitalService().readiness()
        self.assertEqual(payload['groups'], in_process['groups'])
        self.assertEqual(payload['upstream_binding'], 'NOT_BOUND')
        rendered = checklist.render(in_process)
        for group in payload['groups']:
            if group['status'] == 'AVAILABLE_LOCAL':
                self.assertNotIn(f"- [ ] {group['id']} (", rendered)
            else:
                self.assertIn(f"- [ ] {group['id']} ({group['status']};", rendered)


if __name__ == '__main__':
    unittest.main()
