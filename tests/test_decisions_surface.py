"""GET /api/decisions: the machine-readable summary of the capital-decision-v1 notes."""
import http.client
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from capital.auth import ROUTE_PERMISSIONS, LocalRoleAuthorizer, Principal, route_permission
from capital.decisions import DECISIONS_NOT_BOUND, DecisionIndex
from capital.readiness import GROUPS, NOTE_STATUS_PREFIX, TERMS_NOTE
from capital.server import GET_DISPATCH, make_server
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
NOTES = DOCS / 'decisions'
TERMS_LINE = 'PROVISIONAL_PRODUCT_DECISION per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_COVERAGE_NOTE = re.compile(r'docs/decisions/[A-Za-z0-9][A-Za-z0-9_.-]*\.md')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_schema = _load('facade_schema_decisions', ROOT / 'tests' / 'facade_schema.py')


def _block(path):
    """The note's machine block parsed straight from the fence, without the ledger."""
    blocks = _FENCE.findall(path.read_text(encoding='utf-8'))
    assert len(blocks) == 1, path
    return json.loads(blocks[0])


def _version(block):
    for key in sorted(block):
        if (key == 'version' or key.endswith('_version')) and type(block[key]) is str:
            return block[key]
    return None


def _has_number(value):
    if type(value) is bool:
        return False
    if type(value) in (int, float):
        return True
    if type(value) is dict:
        return any(_has_number(item) for item in value.values())
    if type(value) is list:
        return any(_has_number(item) for item in value)
    return False


def _note_text(decision_id, status='PROVISIONAL_PRODUCT_DECISION', version=None, entry_status='ADOPTED'):
    entry = {'status': entry_status, 'cap_rows': ['CAP-01'], 'rationale': 'synthetic', 'provisional': True}
    if entry_status == 'ADOPTED':
        entry.update(value={'k': 1}, provided_by='tester', date='2026-10-08')
    block = {'schema': 'capital-decision-v1', 'decision_id': decision_id, 'provisional': True,
             'status': status, 'entries': {'item': entry}}
    if version is not None:
        block['terms_version'] = version
    return '# synthetic\n\n```capital-decision-v1\n' + json.dumps(block, indent=2) + '\n```\n'


def _docs(root, notes):
    """A throwaway docs/ tree: coverage cites every note, `notes` maps file name -> text or None."""
    docs = Path(root) / 'docs'
    (docs / 'decisions').mkdir(parents=True)
    (docs / 'CAP_COVERAGE.md').write_text(
        '\n'.join(f'| CAP-01 | x | docs/decisions/{name} | SIMULATED | y |' for name in notes) + '\n',
        encoding='utf-8')
    for name, text in notes.items():
        if text is not None:
            (docs / 'decisions' / name).write_text(text, encoding='utf-8')
    return docs


class DecisionRowsTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def test_one_row_per_note_matching_each_machine_block(self):
        body = self.service.decisions()
        self.assertEqual(body['status'], 'BOUND')
        self.assertIsNone(body['reason'])
        self.assertEqual(body['mode'], 'READ_ONLY_DECISION_INDEX')
        files = sorted(path.name for path in NOTES.glob('*.md'))
        self.assertEqual(len(body['rows']), len(files))
        self.assertEqual(sorted(Path(row['note']).name for row in body['rows']), files)
        for row in body['rows']:
            block = _block(ROOT / row['note'])
            self.assertEqual(set(row), {'note', 'decision_id', 'status', 'provisional', 'version', 'entries'})
            self.assertEqual(row['decision_id'], block['decision_id'], row['note'])
            self.assertEqual(row['status'], block['status'], row['note'])
            self.assertIs(row['provisional'], block['provisional'], row['note'])
            self.assertEqual(row['version'], _version(block), row['note'])
            self.assertEqual(
                row['entries'], {name: entry['status'] for name, entry in block['entries'].items()}, row['note'])

    def test_the_four_decided_notes(self):
        rows = {row['decision_id']: row for row in self.service.decisions()['rows']}
        self.assertEqual(set(rows), {
            'financial-terms-decision', 'settlement-policy-decision',
            'upstream-binding-decision', 'accounts-tax-legal-decision'})
        for row in rows.values():
            self.assertEqual(row['status'], 'PROVISIONAL_PRODUCT_DECISION')
            self.assertIs(row['provisional'], True)
        self.assertEqual(rows['financial-terms-decision']['version'], 'CAPITAL-TERMS-V1')
        self.assertEqual(rows['settlement-policy-decision']['version'], 'CAPITAL-SETTLEMENT-POLICY-V1')
        self.assertIsNone(rows['upstream-binding-decision']['version'])
        self.assertIsNone(rows['accounts-tax-legal-decision']['version'])
        upstream = rows['upstream-binding-decision']['entries']
        self.assertEqual(upstream['producer_sdk_tuple'], 'DEFERRED')
        self.assertEqual(upstream['identity_provider_kyc'], 'NOT_ADOPTED')
        self.assertEqual(upstream['ai_agent_grant_action_permit'], 'ADOPTED')
        self.assertEqual(set(rows['financial-terms-decision']['entries'].values()), {'ADOPTED'})

    def test_rows_follow_the_ledger_index(self):
        ledger = _load('ledger_for_surface', ROOT / 'scripts' / 'decision_ledger.py')
        coverage = (DOCS / 'CAP_COVERAGE.md').read_text(encoding='utf-8')
        expected = ledger.build_index(NOTES, ledger.expected_note_paths(coverage))
        self.assertEqual(self.service.decisions()['rows'], expected)

    def test_envelope_is_read_only_and_does_not_touch_the_book(self):
        before = (self.service.machine.state_digest(), len(self.service.receipts))
        body = self.service.decisions()
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertIs(body['write_authorized'], False)
        self.assertEqual(body['instance_id'], self.service.instance_id)
        self.assertEqual(body['observed_state_digest'], before[0])
        self.assertIn('not an adoption', body['label'])
        self.assertEqual(before, (self.service.machine.state_digest(), len(self.service.receipts)))
        body['rows'][0]['entries'].clear()
        self.assertTrue(self.service.decisions()['rows'][0]['entries'])

    def test_body_matches_the_facade_schema(self):
        contract = _schema.load_contract()
        route = next(r for r in contract['routes'] if r['path'] == '/api/decisions')
        self.assertEqual(route['permission'], 'reference:read')
        _schema.validate(self.service.decisions(), route['response'], contract)
        unbound = CapitalService(decisions=DecisionIndex(Path('/nonexistent-docs'))).decisions()
        _schema.validate(unbound, route['response'], contract)
        tainted = dict(unbound, rows=[{'note': 'x', 'decision_id': None, 'status': 'PENDING',
                                       'provisional': None, 'version': None, 'entries': {}}])
        with self.assertRaises(_schema.SchemaError):
            _schema.validate(tainted, route['response'], contract)
        with self.assertRaises(_schema.SchemaError):
            _schema.validate(dict(unbound, extra=1), route['response'], contract)


class DecisionIndexEdgeTests(unittest.TestCase):
    def test_pending_invalid_and_live_status_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = _docs(tmp, {
                'GOOD.md': _note_text('good', version='GOOD-V3'),
                'WITHDRAWN.md': _note_text('withdrawn', status='WITHDRAWN'),
                'BROKEN.md': '# no machine block\n',
                'ABSENT.md': None,
            })
            rows = {Path(row['note']).name: row for row in DecisionIndex(docs).rows()}
        self.assertEqual(list(rows['GOOD.md'].values())[1:], ['good', 'PROVISIONAL_PRODUCT_DECISION', True, 'GOOD-V3', {'item': 'ADOPTED'}])
        self.assertEqual(rows['WITHDRAWN.md']['status'], 'WITHDRAWN')
        self.assertEqual(rows['BROKEN.md']['status'], 'INVALID')
        self.assertEqual((rows['BROKEN.md']['provisional'], rows['BROKEN.md']['version']), (None, None))
        self.assertEqual(rows['ABSENT.md']['status'], 'PENDING')
        self.assertIsNone(rows['ABSENT.md']['decision_id'])
        self.assertEqual(rows['ABSENT.md']['entries'], {})

    def test_unbindable_inputs_are_not_bound_with_a_reason_and_no_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            no_notes = Path(tmp) / 'docs-only'
            no_notes.mkdir()
            (no_notes / 'CAP_COVERAGE.md').write_text('docs/decisions/A.md\n', encoding='utf-8')
            no_coverage = Path(tmp) / 'no-coverage'
            (no_coverage / 'decisions').mkdir(parents=True)
            good = _docs(Path(tmp) / 'good', {'A.md': _note_text('a')})
            cases = {
                'missing docs': DecisionIndex(Path(tmp) / 'absent'),
                'no decisions dir': DecisionIndex(no_notes),
                'no coverage': DecisionIndex(no_coverage),
                'no ledger script': DecisionIndex(good, ledger_path=Path(tmp) / 'missing.py'),
            }
            for label, index in cases.items():
                self.assertIsNone(index.rows(), label)
                body = CapitalService(decisions=index).decisions()
                self.assertEqual(body['status'], 'NOT_BOUND', label)
                self.assertEqual(body['reason'], DECISIONS_NOT_BOUND, label)
                self.assertEqual(body['rows'], [], label)
                self.assertFalse(_has_number(body), label)
            self.assertEqual(len(DecisionIndex(good).rows()), 1)


class ReadinessCitesLiveNoteTests(unittest.TestCase):
    def _blockers(self, service):
        group = next(row for row in service.readiness()['groups'] if row['id'] == 'financial-contracts')
        return group['blockers']

    def test_blocker_is_derived_from_the_parsed_note(self):
        service = CapitalService()
        blockers = self._blockers(service)
        self.assertIn(TERMS_LINE, blockers)
        row = next(r for r in service.decisions()['rows'] if r['note'] == TERMS_NOTE)
        self.assertEqual(TERMS_LINE, f"{row['status']} per {row['note']} ({row['version']})")
        self.assertNotIn('PROVISIONAL per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)', blockers)
        for group in service.readiness()['groups']:
            self.assertFalse(any(item.startswith(NOTE_STATUS_PREFIX) for item in group['blockers']), group['id'])
        # The module constant is the placeholder only; it is never served.
        shared = next(row for row in GROUPS if row['id'] == 'financial-contracts')['blockers']
        self.assertIn(NOTE_STATUS_PREFIX + TERMS_NOTE, shared)
        self.assertEqual(self._blockers(service), blockers)

    def test_blocker_follows_a_changed_note_status_and_version(self):
        name = 'CAPITAL_FINANCIAL_TERMS.md'
        with tempfile.TemporaryDirectory() as tmp:
            docs = _docs(tmp, {name: _note_text('financial-terms-decision', version='CAPITAL-TERMS-V9')})
            service = CapitalService(decisions=DecisionIndex(docs))
            self.assertIn(
                'PROVISIONAL_PRODUCT_DECISION per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V9)',
                self._blockers(service))
            (docs / 'decisions' / name).write_text(
                _note_text('financial-terms-decision', status='SUPERSEDED'), encoding='utf-8')
            self.assertIn('SUPERSEDED per docs/decisions/CAPITAL_FINANCIAL_TERMS.md', self._blockers(service))
            (docs / 'decisions' / name).write_text('# gone\n', encoding='utf-8')
            self.assertIn('INVALID per docs/decisions/CAPITAL_FINANCIAL_TERMS.md', self._blockers(service))

    def test_unbound_notes_say_not_bound_and_keep_the_group_status(self):
        service = CapitalService(decisions=DecisionIndex(Path('/nonexistent-docs')))
        blockers = self._blockers(service)
        self.assertIn('NOT_BOUND per docs/decisions/CAPITAL_FINANCIAL_TERMS.md', blockers)
        self.assertFalse(any('PROVISIONAL' in item and 'docs/decisions' in item for item in blockers))
        group = next(row for row in service.readiness()['groups'] if row['id'] == 'financial-contracts')
        self.assertEqual(group['status'], 'DECISION_REQUIRED')
        self.assertFalse(service.readiness()['policy_adopted'])

    def test_live_groups_pass_the_coverage_check(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        try:
            import test_coverage
        finally:
            sys.path.remove(str(ROOT / 'tests'))
        coverage = test_coverage.COVERAGE.read_text(encoding='utf-8')
        requirements = test_coverage.REQUIREMENTS.read_text(encoding='utf-8')
        for service in (CapitalService(), CapitalService(decisions=DecisionIndex(Path('/nonexistent-docs')))):
            groups = service.readiness()['groups']
            self.assertEqual(test_coverage.check_coverage(coverage, requirements, groups), [])


class DecisionsRouteTests(unittest.TestCase):
    def test_dispatch_and_permissions_stay_in_parity(self):
        self.assertEqual(
            [(path, children) for path, children, _name in GET_DISPATCH],
            [(path, children) for path, _permission, children in ROUTE_PERMISSIONS])
        dispatch = [path for path, _children, _name in GET_DISPATCH]
        self.assertEqual(dispatch.count('/api/decisions'), 1)
        permissions = {path: permission for path, permission, _children in ROUTE_PERMISSIONS}
        self.assertEqual(permissions['/api/decisions'], 'reference:read')
        self.assertEqual(route_permission('/api/decisions'), 'reference:read')
        self.assertIsNone(route_permission('/api/decisions/extra'))
        self.assertEqual(
            next(name for path, _children, name in GET_DISPATCH if path == '/api/decisions'), 'decisions')

    def test_role_matrix(self):
        authorizer = LocalRoleAuthorizer()
        for role in ('organizer', 'auditor', 'observer'):
            self.assertTrue(authorizer.authorize(Principal(role), 'reference:read').allowed, role)
        self.assertFalse(authorizer.authorize(Principal('agent'), 'reference:read').allowed)


class DecisionsHttpTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, method, path, token=None, server=None):
        server = server or self.server
        headers = {'X-Capital-Token': token} if token else {}
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        client.request(method, path, headers=headers)
        response = client.getresponse()
        payload = json.loads(response.read().decode('utf-8'))
        status = response.status
        client.close()
        return status, payload

    def test_three_roles_read_the_same_rows_and_agent_is_forbidden(self):
        service = self.server.service
        before = (service.machine.state_digest(), len(service.receipts))
        code, organizer = self.request('GET', '/api/decisions')
        self.assertEqual(code, 200)
        self.assertEqual(organizer['status'], 'BOUND')
        self.assertEqual(len(organizer['rows']), 4)
        for role in ('auditor', 'observer'):
            token = self.server.authorizer.bind_role(role)
            code, body = self.request('GET', '/api/decisions', token)
            self.assertEqual(code, 200, role)
            self.assertEqual(body['rows'], organizer['rows'], role)
        code, denied = self.request('GET', '/api/decisions', self.server.authorizer.bind_role('agent'))
        self.assertEqual(code, 403)
        self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
        self.assertEqual(denied['permission'], 'reference:read')
        self.assertNotIn('rows', denied)
        self.assertEqual(before, (service.machine.state_digest(), len(service.receipts)))

    def test_only_the_exact_get_route_exists(self):
        self.assertEqual(self.request('GET', '/api/decisions?unused=1')[0], 200)
        self.assertEqual(self.request('GET', '/api/decisions/extra')[0], 404)
        token = self.request('GET', '/api/state')[1]['local_token']
        code, posted = self.request('POST', '/api/decisions', token)
        self.assertEqual((code, posted['error']), (404, 'NOT_FOUND'))

    def test_unbound_docs_answer_not_bound_over_http(self):
        server = make_server(0, decisions=DecisionIndex(Path('/nonexistent-docs')))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            code, body = self.request('GET', '/api/decisions', server=server)
            ready_code, ready = self.request('GET', '/api/readiness', server=server)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        self.assertEqual(code, 200)
        self.assertEqual((body['status'], body['reason'], body['rows']), ('NOT_BOUND', DECISIONS_NOT_BOUND, []))
        self.assertFalse(_has_number(body))
        group = next(row for row in ready['groups'] if row['id'] == 'financial-contracts')
        self.assertIn('NOT_BOUND per docs/decisions/CAPITAL_FINANCIAL_TERMS.md', group['blockers'])

    def test_metrics_label_the_route(self):
        self.request('GET', '/api/decisions')
        code, metrics = self.request('GET', '/api/metrics')
        self.assertEqual(code, 200)
        self.assertEqual(metrics['counters']['http_requests']['/api/decisions']['2xx'], 1)


class DecisionsZipappTests(unittest.TestCase):
    def test_zipapp_has_no_docs_so_the_route_is_not_bound(self):
        build = _load('build_release_decisions', ROOT / 'scripts' / 'build_release.py')
        with tempfile.TemporaryDirectory() as tmp:
            pyz = build.build(tmp, ROOT)
            code = (
                'import json, sys\n'
                'sys.path.insert(0, sys.argv[1])\n'
                'from capital.service import CapitalService\n'
                'service = CapitalService()\n'
                'group = next(g for g in service.readiness()["groups"] if g["id"] == "financial-contracts")\n'
                'print(json.dumps({"decisions": service.decisions(), "blockers": group["blockers"]}))\n'
            )
            proc = subprocess.run([sys.executable, '-c', code, str(pyz)],
                                  capture_output=True, text=True, check=False, cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        body = result['decisions']
        self.assertEqual((body['status'], body['reason'], body['rows']), ('NOT_BOUND', DECISIONS_NOT_BOUND, []))
        self.assertEqual(body['mode'], 'READ_ONLY_DECISION_INDEX')
        self.assertFalse(_has_number(body))
        self.assertIn('NOT_BOUND per docs/decisions/CAPITAL_FINANCIAL_TERMS.md', result['blockers'])
        self.assertFalse(any('PROVISIONAL' in item and 'docs/decisions' in item for item in result['blockers']))


if __name__ == '__main__':
    unittest.main()
