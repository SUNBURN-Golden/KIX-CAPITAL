"""Route-by-role authorization matrix, pinned in tests/auth_matrix.json and replayed live.

The table is SIMULATED and built from the dispatcher and capital.auth by
scripts/auth_matrix.py. These tests (1) recompute the allow/deny outcome of every
cell from the role matrix without the generator, (2) send every cell to a real
loopback server, and (3) keep docs/INTEGRATION.md and the handbook block in step.
No permission or route behavior is changed here. Roles are synthetic and
identity and authentication stay NOT_BOUND.
"""
import contextlib
import http.client
import importlib.util
import io
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from capital.auth import (
    ALL_PERMISSIONS, COMMAND_SUBMIT, MATRIX, OP_PERMISSIONS, ROLES, ROUTE_PERMISSIONS,
    Decision, LocalRoleAuthorizer, route_permission,
)
from capital.server import ASSETS, GET_DISPATCH, POST_DISPATCH, make_server, route_label
from capital.service import OPS

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / 'tests' / 'auth_matrix.json'
INTEGRATION = ROOT / 'docs' / 'INTEGRATION.md'
HANDBOOK = ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md'
CALLERS = (*ROLES, 'no-token')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth_matrix = _load('auth_matrix', ROOT / 'scripts' / 'auth_matrix.py')


def load_table():
    return json.loads(TABLE.read_text(encoding='utf-8'))


def http_send(port, method, path, headers=None, body=None):
    client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        payload = None
        sent = dict(headers or {})
        if body is not None:
            payload = json.dumps(body)
            sent['Content-Type'] = 'application/json'
        client.request(method, path, body=payload, headers=sent)
        response = client.getresponse()
        return response.status, response.getheader('Content-Type', ''), response.read()
    finally:
        client.close()


def quiet_main(argv):
    with contextlib.redirect_stderr(io.StringIO()):
        return auth_matrix.main(argv)


class ShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = load_table()
        cls.routes = {(row['method'], row['route']): row for row in cls.table['routes']}

    def test_labels_and_callers(self):
        table = self.table
        self.assertEqual(table['format'], 'KIX_CAPITAL_AUTH_MATRIX_V1')
        self.assertEqual(table['label'], 'SIMULATED')
        self.assertEqual(table['provenance'], 'SYNTHETIC_LOCAL_ROLE')
        self.assertEqual(table['identity'], 'NOT_BOUND')
        self.assertEqual(table['authentication'], 'NOT_BOUND')
        self.assertEqual(table['callers'], list(CALLERS))
        self.assertEqual(table['no_token_principal'], 'organizer')

    def test_table_is_the_canonical_regeneration(self):
        self.assertEqual(TABLE.read_text(encoding='utf-8'), auth_matrix.dump(auth_matrix.build()))

    def test_no_instance_id_token_or_clock_is_pinned(self):
        text = TABLE.read_text(encoding='utf-8')
        self.assertIsNone(UUID.search(text))
        self.assertNotIn('local_token', text)
        self.assertNotIn('instance_id=' + 'sim', text)

    def test_routes_are_exactly_the_registered_routes(self):
        expected = (
            [('GET', prefix) for prefix, _children, _name in GET_DISPATCH]
            + [('POST', prefix) for prefix, _permission in POST_DISPATCH]
            + [('GET', path) for path in ASSETS]
        )
        self.assertEqual([(row['method'], row['route']) for row in self.table['routes']], expected)
        self.assertEqual(len(expected), len(set(expected)))

    def test_every_route_is_crossed_with_every_caller_once(self):
        keys = [(cell['method'], cell['route'], cell['caller']) for cell in self.table['cells']]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), {(m, r, c) for (m, r) in self.routes for c in CALLERS})
        for cell in self.table['cells']:
            self.assertIn(cell['outcome'], ('ALLOW', 'DENY', 'PUBLIC'))
            self.assertIn('status', cell['expect'])

    def test_dispatcher_and_route_permissions_agree(self):
        self.assertEqual(
            [(prefix, children) for prefix, children, _name in GET_DISPATCH],
            [(prefix, children) for prefix, _permission, children in ROUTE_PERMISSIONS])
        server = make_server(0)
        try:
            handler = server.RequestHandlerClass
            for prefix, children, name in GET_DISPATCH:
                self.assertTrue(callable(getattr(handler, f'_get_{name}', None)), name)
                row = self.routes[('GET', prefix)]
                self.assertEqual(row['handler'], f'_get_{name}')
                self.assertEqual(row['children'], children)
        finally:
            server.server_close()
        for prefix, permission, _children in ROUTE_PERMISSIONS:
            self.assertEqual(self.routes[('GET', prefix)]['permission'], permission, prefix)
            self.assertIn(permission, ALL_PERMISSIONS)
        for prefix, permission in POST_DISPATCH:
            self.assertEqual(self.routes[('POST', prefix)]['permission'], permission, prefix)
            self.assertIn(permission, ALL_PERMISSIONS)
            self.assertIsNone(route_permission(prefix), prefix)
        for path in ASSETS:
            self.assertIsNone(self.routes[('GET', path)]['permission'], path)

    def test_probes_land_on_their_own_route(self):
        for (method, prefix), row in self.routes.items():
            if method != 'GET' or row['permission'] is None:
                continue
            self.assertTrue(row['probes'], prefix)
            for probe in row['probes']:
                path = urlsplit(probe).path
                self.assertEqual(route_label(path), prefix, probe)
                self.assertEqual(route_permission(path), row['permission'], probe)

    def test_cells_follow_the_role_matrix_without_the_generator(self):
        for cell in self.table['cells']:
            row = self.routes[(cell['method'], cell['route'])]
            where = (cell['method'], cell['route'], cell['caller'])
            role = 'organizer' if cell['caller'] == 'no-token' else cell['caller']
            permission = row['permission']
            expect = cell['expect']
            if permission is None:
                self.assertEqual((cell['outcome'], expect), ('PUBLIC', {'status': 200}), where)
            elif cell['method'] == 'POST' and cell['caller'] == 'no-token':
                self.assertEqual(cell['outcome'], 'DENY', where)
                self.assertEqual(expect, {'status': 403, 'error': 'LOCAL_TOKEN_REQUIRED'}, where)
            elif permission in MATRIX[role]:
                self.assertEqual(cell['outcome'], 'ALLOW', where)
                if cell['route'] == '/api/agent/execute':
                    self.assertEqual(expect, {'status': 403, 'error': 'EXECUTE_AUTHORITY_DISABLED'}, where)
                else:
                    self.assertEqual(expect, {'status': 200}, where)
            else:
                self.assertEqual(cell['outcome'], 'DENY', where)
                self.assertEqual(expect, {
                    'status': 403, 'error': 'ROLE_FORBIDDEN', 'permission': permission, 'role': role}, where)

    def test_agent_lane_is_reachable_only_by_agent(self):
        lane = [cell for cell in self.table['cells'] if cell['route'].startswith('/api/agent/')]
        self.assertEqual(len(lane), 6 * len(CALLERS))
        for cell in lane:
            self.assertEqual(cell['outcome'] == 'ALLOW', cell['caller'] == 'agent', cell)
        for cell in self.table['cells']:
            if cell['caller'] == 'agent' and not cell['route'].startswith('/api/agent/') \
                    and cell['route'] not in ASSETS:
                self.assertEqual(cell['outcome'], 'DENY', cell)

    def test_role_permissions_snapshot_is_the_matrix(self):
        self.assertEqual(list(self.table['role_permissions']), list(ROLES))
        for role in ROLES:
            self.assertEqual(set(self.table['role_permissions'][role]), set(MATRIX[role]), role)

    def test_command_permissions_match_the_service_and_the_matrix(self):
        commands = self.table['command_permissions']
        self.assertEqual(commands['submit_gate'], COMMAND_SUBMIT)
        self.assertEqual(commands['unmapped_op_permission'], COMMAND_SUBMIT)
        self.assertEqual(set(commands['ops']), set(OPS))
        self.assertEqual({op: row['permission'] for op, row in commands['ops'].items()}, OP_PERMISSIONS)
        for op, row in commands['ops'].items():
            self.assertEqual(row['permission'], f'command:{op}')
            self.assertEqual(row['roles'], [role for role in ROLES if f'command:{op}' in MATRIX[role]], op)
        keys = [(cell['op'], cell['caller']) for cell in self.table['command_cells']]
        self.assertEqual(keys, [(op, caller) for op in commands['ops'] for caller in CALLERS])
        for cell in self.table['command_cells']:
            role = 'organizer' if cell['caller'] == 'no-token' else cell['caller']
            if cell['caller'] == 'no-token':
                self.assertEqual(cell['expect'], {'status': 403, 'error': 'LOCAL_TOKEN_REQUIRED'}, cell)
            elif cell['op'] == 'default' and role == 'agent':
                self.assertEqual(cell['expect'], {'status': 403, 'error': 'RECOVERY_AGENT_FORBIDDEN'}, cell)
            elif COMMAND_SUBMIT in MATRIX[role]:
                self.assertEqual(cell['expect'], {'status': 400, 'error': 'INVALID_ARGUMENTS'}, cell)
            else:
                self.assertEqual(cell['expect'], {
                    'status': 403, 'error': 'ROLE_FORBIDDEN', 'permission': COMMAND_SUBMIT, 'role': role}, cell)

    def test_every_permission_is_covered_by_a_route_or_a_command(self):
        covered = {row['permission'] for row in self.table['routes'] if row['permission']}
        covered |= {row['permission'] for row in self.table['command_permissions']['ops'].values()}
        self.assertEqual(covered, set(ALL_PERMISSIONS))

    def test_edges_pin_the_named_boundary_cases(self):
        edges = self.table['edges']
        codes = {edge['expect'].get('error') for edge in edges}
        for code in ('NOT_FOUND', 'ROLE_MISMATCH', 'SESSION_REQUIRED', 'ROLE_UNKNOWN', 'LOCAL_TOKEN_REQUIRED'):
            self.assertIn(code, codes)
        for method in ('GET', 'POST'):
            tokens = {edge['token'] for edge in edges if edge['method'] == method and edge['path'] == '/api/no-such-route'}
            self.assertTrue(tokens >= {*ROLES, 'none'}, method)
        for edge in edges:
            self.assertIn(edge['token'], (*ROLES, 'none', 'bogus'))
            self.assertEqual(edge['method'] == 'POST', 'body' in edge, edge)


class DocSyncTests(unittest.TestCase):
    def setUp(self):
        self.table = load_table()
        self.integration = INTEGRATION.read_text(encoding='utf-8')
        self.handbook = HANDBOOK.read_text(encoding='utf-8')

    def test_generated_blocks_match_the_table(self):
        self.assertEqual(
            auth_matrix.extract_generated(self.integration), auth_matrix.render_integration(self.table))
        self.assertEqual(
            auth_matrix.extract_generated(self.handbook), auth_matrix.render_handbook(self.table))

    def test_blocks_name_every_route_and_permission(self):
        for row in self.table['routes']:
            self.assertIn(f"`{auth_matrix._route_text(row)}`", auth_matrix.extract_generated(self.integration))
        handbook = auth_matrix.extract_generated(self.handbook)
        for permission in ALL_PERMISSIONS:
            self.assertIn(f'`{permission}`', handbook)

    def test_handbook_block_sits_in_its_node_section(self):
        start = self.handbook.index('<!-- handbook-section:auth-matrix-freeze -->')
        end = self.handbook.index('<!-- /handbook-section -->', start)
        self.assertIn(auth_matrix.BEGIN, self.handbook[start:end])
        self.assertIn('### auth-matrix-freeze', self.handbook[start:end])
        self.assertIn('## 역할', self.handbook)

    def test_integration_block_sits_in_the_authorization_section(self):
        heading = self.integration.index('## Local authorization boundary v1')
        self.assertLess(heading, self.integration.index(auth_matrix.BEGIN))

    def test_check_passes_on_the_repository(self):
        self.assertEqual(quiet_main(['--check']), 0)

    def test_check_fails_on_each_drifted_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            table, integration, handbook = (Path(tmp) / name for name in ('t.json', 'i.md', 'h.md'))
            table.write_text(TABLE.read_text(encoding='utf-8'), encoding='utf-8')
            integration.write_text(self.integration, encoding='utf-8')
            handbook.write_text(self.handbook, encoding='utf-8')
            args = ['--check', '--table', str(table), '--integration', str(integration), '--handbook', str(handbook)]
            self.assertEqual(quiet_main(args), 0)
            for path, original, find, replace in (
                (integration, self.integration, '| GET | `/api/state` | `state:read` | 200 | 200 | 200 |',
                 '| GET | `/api/state` | `state:read` | 200 | 200 | 403 ROLE_FORBIDDEN |'),
                (handbook, self.handbook, '| `metrics:read` | 허용 | 허용 | 거절 |', '| `metrics:read` | 허용 | 허용 | 허용 |'),
                (table, TABLE.read_text(encoding='utf-8'), '"label": "SIMULATED"', '"label": "REAL"'),
            ):
                self.assertIn(find, original)
                path.write_text(original.replace(find, replace, 1), encoding='utf-8')
                self.assertEqual(quiet_main(args), 1, path.name)
                path.write_text(original, encoding='utf-8')
                self.assertEqual(quiet_main(args), 0, path.name)

    def test_check_fails_when_markers_or_files_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / 'bare.md'
            bare.write_text('no markers\n', encoding='utf-8')
            self.assertEqual(quiet_main(['--check', '--integration', str(bare)]), 1)
            self.assertEqual(quiet_main(['--check', '--table', str(Path(tmp) / 'missing.json')]), 1)

    def test_write_regenerates_all_three_artifacts_and_only_the_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            table, integration, handbook = (Path(tmp) / name for name in ('t.json', 'i.md', 'h.md'))
            table.write_text('{}\n', encoding='utf-8')
            stale = auth_matrix.BEGIN + '\nstale\n' + auth_matrix.END
            integration.write_text('before\n' + stale + '\nafter\n', encoding='utf-8')
            handbook.write_text('머리\n' + stale + '\n꼬리\n', encoding='utf-8')
            args = ['--table', str(table), '--integration', str(integration), '--handbook', str(handbook)]
            self.assertEqual(quiet_main(['--check', *args]), 1)
            self.assertEqual(quiet_main(['--write', *args]), 0)
            self.assertEqual(quiet_main(['--check', *args]), 0)
            self.assertEqual(table.read_text(encoding='utf-8'), TABLE.read_text(encoding='utf-8'))
            self.assertTrue(integration.read_text(encoding='utf-8').startswith('before\n' + auth_matrix.BEGIN))
            self.assertTrue(integration.read_text(encoding='utf-8').endswith(auth_matrix.END + '\nafter\n'))
            self.assertTrue(handbook.read_text(encoding='utf-8').endswith(auth_matrix.END + '\n꼬리\n'))

    def test_docs_still_carry_the_prose_around_the_blocks(self):
        # Regeneration must not have eaten the surrounding sections.
        self.assertIn('## Local authorization boundary v1', self.integration)
        self.assertIn('Real IdP, KYC, and credential flows stay **NOT_BOUND**', self.integration)
        self.assertIn('`X-Capital-Role` cannot switch it', self.integration)
        self.assertIn('<!-- handbook-section:decision-status-surface -->', self.handbook)


class DivergenceTests(unittest.TestCase):
    """A change to the dispatcher, ROUTE_PERMISSIONS or the role matrix must fail the suite."""

    @classmethod
    def setUpClass(cls):
        cls.committed = TABLE.read_text(encoding='utf-8')

    def test_a_route_dropped_from_route_permissions_is_refused(self):
        with mock.patch.object(auth_matrix, 'ROUTE_PERMISSIONS', ROUTE_PERMISSIONS[:-1]):
            with self.assertRaises(auth_matrix.MatrixError):
                auth_matrix.build()
            self.assertEqual(quiet_main(['--check']), 1)

    def test_a_route_added_to_the_dispatcher_alone_is_refused(self):
        extra = (*GET_DISPATCH, ('/api/new-surface', False, 'state'))
        with mock.patch.object(auth_matrix, 'GET_DISPATCH', extra):
            with self.assertRaises(auth_matrix.MatrixError):
                auth_matrix.build()
            self.assertEqual(quiet_main(['--check']), 1)

    def test_a_route_added_to_both_registries_still_needs_a_probe(self):
        dispatch = (*GET_DISPATCH, ('/api/new-surface', False, 'state'))
        permissions = (*ROUTE_PERMISSIONS, ('/api/new-surface', 'state:read', False))
        with mock.patch.object(auth_matrix, 'GET_DISPATCH', dispatch), \
                mock.patch.object(auth_matrix, 'ROUTE_PERMISSIONS', permissions):
            with self.assertRaises(auth_matrix.MatrixError):
                auth_matrix.build()

    def test_a_permission_swapped_on_one_route_changes_the_table(self):
        swapped = tuple(
            (prefix, 'state:read' if prefix == '/api/metrics' else permission, children)
            for prefix, permission, children in ROUTE_PERMISSIONS)
        with mock.patch.object(auth_matrix, 'ROUTE_PERMISSIONS', swapped):
            self.assertNotEqual(auth_matrix.dump(auth_matrix.build()), self.committed)
            self.assertEqual(quiet_main(['--check']), 1)

    def test_a_permission_granted_to_a_role_changes_the_table(self):
        widened = {role: frozenset(permissions) for role, permissions in MATRIX.items()}
        widened['observer'] = widened['observer'] | {'projection:read'}
        with mock.patch.object(auth_matrix, 'MATRIX', widened):
            self.assertNotEqual(auth_matrix.dump(auth_matrix.build()), self.committed)
            self.assertEqual(quiet_main(['--check']), 1)

    def test_a_route_mapped_to_an_unknown_permission_is_refused(self):
        bogus = tuple(
            (prefix, 'admin:write' if prefix == '/api/health' else permission, children)
            for prefix, permission, children in ROUTE_PERMISSIONS)
        with mock.patch.object(auth_matrix, 'ROUTE_PERMISSIONS', bogus):
            with self.assertRaises(auth_matrix.MatrixError):
                auth_matrix.build()


class SubmitOnlyAuthorizer(LocalRoleAuthorizer):
    """Holds command:submit but no per-operation command permission.

    A test seam only: it shows which permission the service names for each op.
    It is not a role and is never used outside this module.
    """

    def authorize(self, principal, permission):
        if permission.startswith('command:') and permission != COMMAND_SUBMIT:
            return Decision(False, 'test seam: submit only')
        return super().authorize(principal, permission)


class LiveBase(unittest.TestCase):
    server = None

    @classmethod
    def boot(cls, authorizer=None):
        cls.server = make_server(0, authorizer=authorizer)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.service = cls.server.service

    @classmethod
    def tearDownClass(cls):
        if cls.server is not None:
            cls.server.shutdown()
            cls.server.server_close()
            cls.worker.join()

    def send(self, method, path, headers=None, body=None):
        return http_send(self.port, method, path, headers, body)

    def writes(self):
        service = self.service
        return {
            'receipts': len(service.receipts),
            'digest': service.machine.state_digest(),
            'proposals': len(service.agent_lane.proposals),
        }


class LiveMatrixTests(LiveBase):
    @classmethod
    def setUpClass(cls):
        cls.table = load_table()
        cls.routes = {(row['method'], row['route']): row for row in cls.table['routes']}
        cls.boot()
        status, _kind, raw = http_send(cls.port, 'GET', '/api/state')
        state = json.loads(raw)
        cls.instance = state['instance_id']
        cls.tokens = {'organizer': state['local_token']}
        for role in ('auditor', 'observer', 'agent'):
            status, _kind, raw = http_send(
                cls.port, 'POST', '/api/session', {'X-Capital-Token': cls.tokens['organizer']}, {'role': role})
            assert status == 200, (role, raw)
            cls.tokens[role] = json.loads(raw)['local_token']
        # The one seeded write: an offer for the GET probes (preview, terms, operations) to read.
        status, _kind, raw = http_send(cls.port, 'POST', '/api/commands', {
            'X-Capital-Token': cls.tokens['organizer']}, {
                'instance_id': cls.instance, 'operation_id': auth_matrix.OFFER_OPERATION, 'op': 'offer',
                'advance_id': auth_matrix.ADVANCE, 'args': {'fixture_id': 'sim-committed', 'amount': 90000}})
        assert status == 200 and json.loads(raw)['outcome'] == 'ACCEPTED', raw
        # A drawn advance, so the credit_claim read probe finds a noted mock claim.
        for op, args in (('offer', {'fixture_id': auth_matrix.DRAWN_FIXTURE, 'amount': 1000}),
                         ('approve', {}), ('bind_settlement', {}), ('draw', {})):
            status, _kind, raw = http_send(cls.port, 'POST', '/api/commands', {
                'X-Capital-Token': cls.tokens['organizer']}, {
                    'instance_id': cls.instance, 'operation_id': f'sim-mtx-drawn-{op.replace("_", "")}',
                    'op': op, 'advance_id': auth_matrix.DRAWN_ADVANCE, 'args': args})
            assert status == 200 and json.loads(raw)['outcome'] == 'ACCEPTED', (op, raw)

    def fill(self, value):
        if isinstance(value, str):
            return value.replace(auth_matrix.INSTANCE, self.instance)
        if isinstance(value, list):
            return [self.fill(item) for item in value]
        if isinstance(value, dict):
            return {key: self.fill(item) for key, item in value.items()}
        return value

    def token_headers(self, who):
        if who in ('no-token', 'none'):
            return {}
        if who == 'bogus':
            return {'X-Capital-Token': 'not-a-token'}
        return {'X-Capital-Token': self.tokens[who]}

    def assert_result(self, expect, status, kind, raw, where):
        self.assertEqual(status, expect['status'], (where, raw[:200]))
        if kind.startswith('application/json'):
            body = json.loads(raw)
            for key, value in expect.items():
                if key != 'status':
                    self.assertEqual(body.get(key), value, (where, key))
            if 'error' not in expect and isinstance(body, dict):
                self.assertNotIn('error', body, where)
        else:
            self.assertNotIn('error', expect, where)
            self.assertTrue(raw, where)

    def test_every_cell(self):
        before = self.writes()
        swept = 0
        for cell in self.table['cells']:
            route = self.routes[(cell['method'], cell['route'])]
            headers = self.token_headers(cell['caller'])
            if cell['method'] == 'GET':
                probes = route['probes'] if route['permission'] is not None else [route['route']]
                for probe in probes:
                    where = (cell['method'], probe, cell['caller'])
                    with self.subTest(where):
                        self.assert_result(cell['expect'], *self.send('GET', self.fill(probe), headers), where)
                        swept += 1
            else:
                where = (cell['method'], cell['route'], cell['caller'])
                with self.subTest(where):
                    self.assert_result(
                        cell['expect'], *self.send('POST', cell['route'], headers, self.fill(route['body'])), where)
                    swept += 1
        self.assertGreaterEqual(swept, len(self.table['cells']))
        after = self.writes()
        # Exactly the pinned writes: the organizer reconcile receipt and the agent proposals
        # (sim-matrix is proposed and later withdrawn in place; sim-matrix-change is a memo).
        self.assertEqual(after['receipts'], before['receipts'] + 1)
        self.assertEqual(after['proposals'], before['proposals'] + 2)
        self.assertEqual(after['digest'], before['digest'])
        self.assertIn('sim-mtx-reconcile', self.service.receipts)
        self.assertIn('sim-matrix', self.service.agent_lane.proposals)

    def test_agent_lane_posts_stay_proposal_only(self):
        before = self.writes()
        agent = self.token_headers('agent')
        bodies = {
            '/api/agent/propose_action': {
                **self.routes[('POST', '/api/agent/propose_action')]['body'],
                'proposal_id': 'sim-matrix-lane'},
            '/api/agent/withdraw_proposal': {
                **self.routes[('POST', '/api/agent/withdraw_proposal')]['body'],
                'proposal_id': 'sim-matrix-lane'},
            '/api/agent/propose_grant_change': {
                **self.routes[('POST', '/api/agent/propose_grant_change')]['body'],
                'proposal_id': 'sim-matrix-lane-change'},
        }
        paths = (
            '/api/agent/query_grant', '/api/agent/query_subject', '/api/agent/propose_action',
            '/api/agent/withdraw_proposal', '/api/agent/propose_grant_change', '/api/agent/execute')
        for path in paths:
            row = self.routes[('POST', path)]
            status, _kind, raw = self.send('POST', path, agent, bodies.get(path, row['body']))
            body = json.loads(raw)
            if path == '/api/agent/execute':
                self.assertEqual((status, body['error']), (403, 'EXECUTE_AUTHORITY_DISABLED'))
            else:
                self.assertEqual(status, 200, raw)
                self.assertNotIn('error', body)
        # The withdrawn proposal replays as a duplicate that reports its stored phase.
        status, _kind, raw = self.send('POST', '/api/agent/propose_action', agent, bodies['/api/agent/propose_action'])
        body = json.loads(raw)
        self.assertEqual(status, 200, raw)
        self.assertIs(body['duplicate'], True)
        proposal = body['proposal']
        self.assertEqual(proposal['phase'], 'WITHDRAWN')
        self.assertIs(proposal['effects_executed'], False)
        change = self.service.agent_lane.proposals['sim-matrix-lane-change']
        self.assertEqual((change['kind'], change['phase']), ('GRANT_CHANGE', 'HUMAN_PENDING'))
        self.assertIs(change['effects_executed'], False)
        self.assertIsNone(change['amount'])
        for role in ('organizer', 'auditor', 'observer'):
            for path in paths:
                row = self.routes[('POST', path)]
                status, _kind, raw = self.send(
                    'POST', path, self.token_headers(role), bodies.get(path, row['body']))
                body = json.loads(raw)
                self.assertEqual((status, body['error'], body['permission']),
                                 (403, 'ROLE_FORBIDDEN', row['permission']), (role, path))
        after = self.writes()
        self.assertEqual(after['receipts'], before['receipts'])
        self.assertEqual(after['digest'], before['digest'])
        self.assertEqual(after['proposals'], before['proposals'] + 2)

    def test_command_cells(self):
        commands = self.table['command_permissions']
        before = self.writes()
        for cell in self.table['command_cells']:
            where = ('POST /api/commands', cell['op'], cell['caller'])
            body = {
                'instance_id': self.instance, 'operation_id': 'sim-mtx-probe-' + cell['op'].replace('_', '-'), 'op': cell['op'],
                'advance_id': commands['probe']['advance_id'], 'args': commands['probe']['args'],
            }
            with self.subTest(where):
                self.assert_result(
                    cell['expect'], *self.send('POST', '/api/commands', self.token_headers(cell['caller']), body), where)
        # The organizer probes pass the gate and are rejected for their arguments. Nothing is stored.
        self.assertEqual(self.writes(), before)

    def test_edges(self):
        before = self.writes()
        for edge in self.table['edges']:
            headers = {**self.token_headers(edge['token']), **edge.get('headers', {})}
            where = (edge['name'], edge['method'], edge['path'], edge['token'], edge.get('headers'))
            with self.subTest(where):
                body = self.fill(edge['body']) if 'body' in edge else None
                self.assert_result(edge['expect'], *self.send(edge['method'], self.fill(edge['path']), headers, body), where)
        self.assertEqual(self.writes(), before)

    def test_role_header_cannot_change_what_a_token_may_do(self):
        # Spot check beyond the pinned edges: a role claim never widens a token.
        for token_role in ('observer', 'agent'):
            for claimed in (role for role in ROLES if role != token_role):
                headers = {**self.token_headers(token_role), 'X-Capital-Role': claimed}
                status, _kind, raw = self.send('GET', '/api/health', headers)
                self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_MISMATCH'), (token_role, claimed))

    def test_unmapped_paths_are_404_for_every_caller(self):
        unmapped = (
            '/api/no-such-route', '/api/commands/extra', '/api/session/x', '/api/export/manifest/x',
            '/api/state/x', '/api/metrics/', '/api/health/x', '/api', '/api/', '/api/agent', '/api/agent/',
            '/api/agent/query_grant/x',
        )
        for path in unmapped:
            self.assertIsNone(route_permission(path), path)
            for caller in CALLERS:
                with self.subTest((path, caller)):
                    status, _kind, raw = self.send('GET', path, self.token_headers(caller))
                    self.assertEqual((status, json.loads(raw)['error']), (404, 'NOT_FOUND'))
        self.assertEqual(route_label('/api/no-such-route'), 'other')


class CommandMappingTests(LiveBase):
    """The route gate is command:submit. The service then names command:{op} per operation."""

    @classmethod
    def setUpClass(cls):
        cls.table = load_table()
        cls.boot(SubmitOnlyAuthorizer())
        status, _kind, raw = http_send(cls.port, 'GET', '/api/state')
        cls.instance = json.loads(raw)['instance_id']
        cls.token = json.loads(raw)['local_token']

    def body(self, op):
        probe = self.table['command_permissions']['probe']
        return {
            'instance_id': self.instance, 'operation_id': 'sim-mtx-map-' + op.replace('_', '-'), 'op': op,
            'advance_id': probe['advance_id'], 'args': probe['args'],
        }

    def test_each_operation_names_its_own_permission(self):
        before = self.writes()
        headers = {'X-Capital-Token': self.token}
        for op, row in self.table['command_permissions']['ops'].items():
            with self.subTest(op):
                status, _kind, raw = self.send('POST', '/api/commands', headers, self.body(op))
                body = json.loads(raw)
                self.assertEqual(status, 403, raw)
                self.assertEqual(body['error'], 'ROLE_FORBIDDEN')
                self.assertEqual(body['permission'], row['permission'])
                self.assertEqual(body['role'], 'organizer')
        self.assertEqual(self.writes(), before)

    def test_an_unmapped_operation_needs_only_the_submit_permission(self):
        before = self.writes()
        status, _kind, raw = self.send(
            'POST', '/api/commands', {'X-Capital-Token': self.token}, self.body('wire_transfer'))
        self.assertEqual((status, json.loads(raw)['error']), (400, 'UNSUPPORTED_OPERATION'))
        self.assertEqual(self.table['command_permissions']['unmapped_op_permission'], COMMAND_SUBMIT)
        self.assertEqual(self.writes()['digest'], before['digest'])


if __name__ == '__main__':
    unittest.main()
