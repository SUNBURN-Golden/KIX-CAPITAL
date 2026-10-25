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
    def test_bundled_policy_runtime_is_documented_with_provenance_and_override_failure(self):
        handbook = HANDBOOK.read_text(encoding='utf-8')
        start = handbook.index('<!-- handbook-section:artifact-docs-bundling -->')
        section = handbook[start:handbook.index('<!-- /handbook-section -->', start)]
        for word in ('### artifact-docs-bundling', 'docs/decisions/*.md',
                     'docs/CAP_COVERAGE.md', 'scripts/decision_ledger.py',
                     'RELEASE-MANIFEST.json', 'notes_source', 'note_sha256',
                     'CAPITAL_FINANCIAL_TERMS.md', 'CAPITAL_SETTLEMENT_POLICY.md',
                     'CHECKOUT', 'BUNDLED_IN_ARTIFACT', 'OVERRIDE_FILE', 'NONE',
                     'PENDING', 'INVALID', '--terms-note', '--policy-note',
                     'signed:false', 'published:false', 'sim_day'):
            self.assertIn(word, section)
        for path in (README, ROOT / 'docs' / 'INTEGRATION.md', HANDBOOK,
                     ROOT / 'docs' / 'RELEASES.md'):
            text = path.read_text(encoding='utf-8')
            self.assertIn('note_sha256', text, path)
            self.assertIn('빌드 시점' if path in (README, HANDBOOK) else 'build-time', text, path)
            self.assertNotIn('zipapp does not bundle', text, path)
            self.assertNotIn('zipapp은 `docs/`를 담지 않아', text, path)

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

    def test_role_table_names_every_agent_lane_route(self):
        section = _section(HANDBOOK.read_text(encoding='utf-8'), '## 역할')
        table = json.loads((ROOT / 'tests' / 'auth_matrix.json').read_text(encoding='utf-8'))
        routes = [row['route'] for row in table['routes']
                  if row['method'] == 'POST' and row['route'].startswith('/api/agent/')]
        self.assertEqual(len(routes), 6)
        for route in routes:
            self.assertIn(f'`POST {route}`', section, route)
        agent_row = next(line for line in section.splitlines()
                         if line.startswith('| agent'))
        self.assertIn('403 ROLE_FORBIDDEN', agent_row)

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


    def test_role_table_names_the_overlay_surface(self):
        text = (Path(__file__).resolve().parent.parent / 'docs' / 'OPERATOR_HANDBOOK_KO.md').read_text(encoding='utf-8')
        start = text.index('## 역할')
        table = text[start:text.index('\n## ', start + 1)]
        rows = {line.split('|')[1].strip(): line.split('|') for line in table.splitlines() if line.startswith('| ')}
        self.assertIn('overlay:command', rows['organizer'][2])
        self.assertIn('POST /api/overlay/commands', rows['organizer'][2])
        self.assertIn('GET /api/overlay', rows['auditor'][2])
        self.assertIn('/api/overlay', rows['observer'][3])
        self.assertNotIn('/api/overlay', rows['observer'][2])
        self.assertNotIn('overlay:command', rows['auditor'][2] + rows['observer'][2])

    def test_handbook_has_overlay_node_sections(self):
        text = (Path(__file__).resolve().parent.parent / 'docs' / 'OPERATOR_HANDBOOK_KO.md').read_text(encoding='utf-8')
        self.assertEqual(text.count('<!-- handbook-section:'), text.count('<!-- /handbook-section -->'))
        needed = {
            'shadow-refund-resale': ('SHADOW_NOT_APPLIED', 'SHADOW_DEFERRED'),
            'caps-binding-fixtures': ('CAPITAL-DEMO-BOOK-V1', 'portfolio_cap_krw'),
            'sim-clock-ledger': ('SIM_CLOCK_STALE', 'SIM_CLOCK_STEP', 'SIM_CLOCK_NOT_ADVANCING', 'WORKSPACE_UNREADABLE'),
            'margin-cure-default': ('FIXTURE_VIEWS_IMMUTABLE', 'DEFAULT_ELIGIBLE', 'f04_default_called'),
            'audit70-fix1': ('interest_rebased', 'overlay-recovery-writeoff', 'overlay-repayment-posting', 'CAPITAL_DEFAULT_RECOVERY.md', 'CAPITAL_REPAYMENT_POSTING.md'),
            'coa-candidate-projection': ('GET /api/projection?mode=coa-candidate', 'GET /api/reconciliation?mode=coa-candidate', 'SIMULATION_FIXED_V2', 'SYNTHETIC_UNADOPTED', '9790', 'coa_candidate_totals_vs_v1', 'interest_ledger_vs_projection'),
            'audit60-fix2': ('KIX_CAPITAL_EXPORT_MANIFEST_V2', 'KIX_CAPITAL_EXPORT_MANIFEST_V3', 'overlaypart', 'SECTION_SET', 'overlay_fold_digest_equals_persisted', 'tests/golden/overlay_demo.json'),
        }
        for name, words in needed.items():
            start = text.index(f'<!-- handbook-section:{name} -->')
            body = text[start:text.index('<!-- /handbook-section -->', start)]
            self.assertIn(f'### {name}', body)
            for word in words:
                self.assertIn(word, body)

    def test_handbook_has_audit90_fix1_node_sections(self):
        text = HANDBOOK.read_text(encoding='utf-8')
        needed = {
            'covenant-watch': (
                'GET /api/risk/covenants', 'SIMULATED_COVENANT_WATCH', 'projection:read',
                '403 ROLE_FORBIDDEN', 'CLEAR', 'WATCH', 'BREACH', 'MATURITY_WINDOW',
                'U4_CAP_BREACHED', 'applied', 'enforced', 'GET /api/risk',
                'reconciliation.matched', 'NOT_BOUND', 'tests/test_covenant_watch.py'),
            'gate-fake-fault-corpus': (
                'tests/vectors/gate_faults.json', 'KIX_CAPITAL_GATE_FAULTS_V1',
                'scripts/fake_gate.py', 'gate_faults.py --check', 'LOCAL_FAKE_GATE',
                'GATE_FAILED', 'INVALID_JSON', 'UNKNOWN', 'retry_authorized',
                'IDEMPOTENCY_CONFLICT', 'NOT_BOUND', 'tests/test_gate_faults.py'),
            'crash-replay-matrix': (
                'tests/crash_matrix.py', 'tests/vectors/workspace_crash.json',
                'KIX_CAPITAL_WORKSPACE_CRASH_V1', '--check', 'WORKSPACE_UNREADABLE',
                'SIGKILL', 'overlay_state_digest_one_of', 'journal-append',
                'overlay-entry', 'storage-conformance', 'LOCAL_FILE_WORKSPACE',
                'NOT_BOUND', 'tests/test_crash_replay.py', 'SIMULATED'),
            'decision-binding-fence': (
                'tests/decision_bindings.json', 'capital-decision-bindings-v1',
                'scripts/decision_bindings.py --check', 'ADOPTED', 'CONSUMED',
                'PENDING_CONSUMER', 'consumer_node', 'reason', 'unit',
                'python3 -m unittest discover -s tests -v',
                'tests/test_decision_bindings.py'),
            'fsm-contract-claims': (
                'tests/fsm_contract_claims.json', 'KIX_CAPITAL_FSM_CONTRACT_CLAIMS_V1',
                'scripts/fsm_contract_claims_check.py --execute', 'CLAIM_CONFORMANCE',
                'CreditMachine', 'SettlementMachine', 'capital/vendor/manifest.json',
                'VENDOR_HASH_MISMATCH', '--protocol-dir', 'SKIPPED',
                'tests/test_fsm_contract_claims.py', 'upstream-claims'),
            'ce1-canonical-claims': (
                'tests/ce1_claims.json', 'KIX_CAPITAL_CE1_CLAIMS_V1',
                'scripts/ce1_claims_check.py --execute', 'CLAIM_CONFORMANCE',
                'CANONICAL_ENCODING_V1', 'DOCUMENTED_DIVERGENCE', 'ensure_ascii',
                'capital/ce1_claims.py', 'capital/store.py',
                '--protocol-dir', 'SKIPPED', 'tests/test_ce1_claims.py',
                'upstream-claims'),
        }
        for name, words in needed.items():
            start = text.index(f'<!-- handbook-section:{name} -->')
            body = text[start:text.index('<!-- /handbook-section -->', start)]
            self.assertIn(f'### {name}', body)
            for word in words:
                self.assertIn(word, body, (name, word))

    def test_docs_name_the_checkers_and_their_stage_placement(self):
        plan = {stage['id']: stage for stage in acceptance_ladder.build_plan()}
        unit_commands = [' '.join(map(str, argv)) for argv in plan['unit']['commands']]
        upstream_commands = [
            ' '.join(map(str, argv)) for argv in plan['upstream-claims']['commands']]
        self.assertTrue(any('unittest' in argv and 'discover' in argv for argv in unit_commands))
        fence = [argv for argv in unit_commands if 'decision_bindings.py' in argv]
        self.assertEqual(len(fence), 1)
        self.assertIn('--check', fence[0])
        self.assertLess(
            unit_commands.index(next(c for c in unit_commands if 'discover' in c)),
            unit_commands.index(fence[0]))
        self.assertEqual(len(upstream_commands), 4)
        for argv in upstream_commands:
            self.assertIn('--execute', argv)
            self.assertIn('_claims_check.py', argv)
        for doc in (README.read_text(encoding='utf-8'),
                    HANDBOOK.read_text(encoding='utf-8')):
            self.assertIn('python3 scripts/decision_bindings.py --check', doc)
            self.assertIn('python3 scripts/fsm_contract_claims_check.py --execute', doc)
            for argv in upstream_commands:
                needle = argv[argv.index('scripts/'):]
                self.assertIn(needle, doc)
            needles = [
                'python3 ' + argv[argv.index('scripts/'):] for argv in upstream_commands]
            positions = [doc.index(needle) for needle in needles]
            self.assertEqual(positions, sorted(positions))
            self.assertIn('추가 명령', doc)
            self.assertIn('네 번째', doc)
            self.assertIn('tests/test_fsm_contract_claims.py', doc)
            self.assertIn('SKIPPED', doc)


if __name__ == '__main__':
    unittest.main()
