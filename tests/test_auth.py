import json
import http.client
import threading
import unittest
from email.message import Message

from capital.auth import (
    ALL_PERMISSIONS, COMMAND_SUBMIT, DEFAULT_ROLE, MATRIX, OP_PERMISSIONS, PROVENANCE,
    ROLES, ROUTE_PERMISSIONS, SESSION_BIND, AuthorizerPort, Decision, LocalRoleAuthorizer,
    Principal, require, route_permission,
)
from capital.server import GET_DISPATCH, POST_DISPATCH, make_server
from capital.service import OPS, ApiError, CapitalService, digest


def headers_of(*pairs):
    message = Message()
    for name, value in pairs:
        message[name] = value
    return message


class MatrixTests(unittest.TestCase):
    def test_every_command_and_sensitive_read_is_mapped(self):
        self.assertEqual(set(OP_PERMISSIONS), set(OPS))
        self.assertEqual(set(OP_PERMISSIONS.values()), {f'command:{op}' for op in OPS})
        routes = {
            '/api/state': 'state:read',
            '/api/scenarios': 'reference:read',
            '/api/scenarios/full-after': 'reference:read',
            '/api/readiness': 'reference:read',
            '/api/evidence': 'projection:read',
            '/api/projection': 'projection:read',
            '/api/terms': 'projection:read',
            '/api/terms/sim-a': 'projection:read',
            '/api/policy': 'projection:read',
            '/api/policy/simulation': 'projection:read',
            '/api/preview/sim-a': 'projection:read',
            '/api/operations/op-1': 'receipt:read',
            '/api/export': 'export:read',
            '/api/reconciliation': 'reconciliation:read',
            '/api/statement': 'statement:read',
        }
        for path, permission in routes.items():
            self.assertEqual(route_permission(path), permission, path)
            self.assertIn(permission, ALL_PERMISSIONS)
        self.assertIsNone(route_permission('/api/projection/extra'))
        self.assertIsNone(route_permission('/api/commands'))
        self.assertIsNone(route_permission('/api/session'))
        self.assertIsNone(route_permission('/api/unknown'))
        self.assertIsNone(route_permission('/'))
        self.assertEqual(
            [(path, children) for path, children, _name in GET_DISPATCH],
            [(path, children) for path, _permission, children in ROUTE_PERMISSIONS],
        )
        self.assertEqual([path for path, _permission in POST_DISPATCH], ['/api/commands', '/api/session'])
        for path, permission in POST_DISPATCH:
            self.assertIn(permission, ALL_PERMISSIONS, path)
            self.assertIsNone(route_permission(path), path)

    def test_matrix_fails_closed_and_splits_the_three_roles(self):
        authorizer = LocalRoleAuthorizer()
        organizer, auditor, observer = (Principal(role) for role in ROLES)
        for permission in ALL_PERMISSIONS:
            self.assertTrue(authorizer.authorize(organizer, permission).allowed, permission)
        for permission in ALL_PERMISSIONS:
            decision = authorizer.authorize(auditor, permission)
            financial_write = permission == COMMAND_SUBMIT or permission.startswith('command:')
            self.assertEqual(decision.allowed, not financial_write, permission)
        for permission in ('export:read', 'reconciliation:read', 'statement:read', 'projection:read', COMMAND_SUBMIT, 'command:draw'):
            self.assertFalse(authorizer.authorize(observer, permission).allowed, permission)
        for permission in ('state:read', 'reference:read', 'receipt:read', SESSION_BIND):
            self.assertTrue(authorizer.authorize(observer, permission).allowed, permission)
        self.assertTrue(authorizer.authorize(auditor, 'projection:read').allowed)
        self.assertTrue(authorizer.authorize(auditor, 'export:read').allowed)
        self.assertFalse(authorizer.authorize(organizer, 'admin:write').allowed)
        self.assertFalse(authorizer.authorize(Principal('named-person'), 'state:read').allowed)
        self.assertTrue(MATRIX['auditor'].isdisjoint(OP_PERMISSIONS.values()))
        self.assertNotIn(COMMAND_SUBMIT, MATRIX['auditor'])
        self.assertNotIn(COMMAND_SUBMIT, MATRIX['observer'])
        self.assertNotIn('projection:read', MATRIX['observer'])

    def test_role_is_bound_to_the_loopback_token(self):
        authorizer = LocalRoleAuthorizer()
        organizer_token = authorizer.token_for(DEFAULT_ROLE)
        self.assertEqual(authorizer.authenticate(headers_of()).role, DEFAULT_ROLE)
        self.assertEqual(authorizer.authenticate(headers_of()).provenance, PROVENANCE)
        self.assertEqual(authorizer.bind_role('organizer'), organizer_token)
        auditor_token = authorizer.bind_role('auditor')
        self.assertNotEqual(auditor_token, organizer_token)
        self.assertEqual(authorizer.bind_role('auditor'), auditor_token)
        self.assertEqual(authorizer.authenticate(headers_of(('X-Capital-Token', auditor_token))).role, 'auditor')
        self.assertEqual(
            authorizer.authenticate(headers_of(
                ('X-Capital-Token', organizer_token), ('X-Capital-Role', 'organizer'))).role,
            'organizer')
        with self.assertRaises(ApiError) as claimed:
            authorizer.authenticate(headers_of(('X-Capital-Role', 'auditor')))
        self.assertEqual((claimed.exception.code, claimed.exception.status), ('SESSION_REQUIRED', 403))
        with self.assertRaises(ApiError) as mismatched:
            authorizer.authenticate(headers_of(
                ('X-Capital-Token', organizer_token), ('X-Capital-Role', 'auditor')))
        self.assertEqual(mismatched.exception.code, 'ROLE_MISMATCH')
        for pairs in (
            (('X-Capital-Role', 'admin'),),
            (('X-Capital-Role', 'Auditor'),),
            (('X-Capital-Role', ''),),
            (('X-Capital-Role', 'organizer,auditor'),),
            (('X-Capital-Role', 'auditor'), ('X-Capital-Role', 'observer')),
            (('X-Capital-Role', 'organizer'), ('X-Capital-Role', 'organizer')),
            (('X-Capital-Token', auditor_token), ('X-Capital-Role', 'nope')),
        ):
            with self.assertRaises(ApiError) as caught:
                authorizer.authenticate(headers_of(*pairs))
            self.assertEqual((caught.exception.code, caught.exception.status), ('ROLE_UNKNOWN', 403))

    def test_require_reports_role_permission_and_reason(self):
        authorizer = LocalRoleAuthorizer()
        with self.assertRaises(ApiError) as caught:
            require(authorizer, Principal('observer'), 'export:read')
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.detail['role'], 'observer')
        self.assertEqual(caught.exception.detail['permission'], 'export:read')
        self.assertIn('observer', caught.exception.detail['reason'])
        described = authorizer.describe(Principal('auditor'))
        self.assertEqual(described['port'], 'AuthorizerPort')
        self.assertEqual(described['mode'], 'LOCAL_SYNTHETIC_ROLES')
        self.assertEqual(described['identity'], 'NOT_BOUND')
        self.assertEqual(described['roles'], list(ROLES))
        self.assertFalse(described['permissions']['command:offer']['allowed'])
        self.assertTrue(described['permissions']['reconciliation:read']['allowed'])
        self.assertTrue(described['permissions']['statement:read']['allowed'])


class ServiceAuthTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def body(self, op='offer', key='op-1', **args):
        if not args and op == 'offer':
            args = {'fixture_id': 'sim-committed', 'amount': 100}
        return dict(instance_id=self.service.instance_id, operation_id=key, op=op,
                    advance_id='sim-auth', args=args)

    def test_snapshot_auth_does_not_change_machine_digest(self):
        organizer = self.service.snapshot()
        auditor = self.service.snapshot(role='auditor')
        observer = self.service.snapshot(role='observer')
        self.assertEqual(organizer['state_digest'], self.service.machine.state_digest())
        self.assertEqual(organizer['state_digest'], auditor['state_digest'])
        self.assertEqual(auditor['state_digest'], observer['state_digest'])
        self.assertEqual(organizer['auth']['role'], 'organizer')
        self.assertTrue(organizer['auth']['permissions']['command:draw']['allowed'])
        self.assertFalse(auditor['auth']['permissions']['command:draw']['allowed'])
        self.assertTrue(auditor['auth']['permissions']['export:read']['allowed'])
        self.assertFalse(observer['auth']['permissions']['export:read']['allowed'])
        self.assertFalse(observer['auth']['permissions']['reconciliation:read']['allowed'])
        self.assertFalse(observer['auth']['permissions']['statement:read']['allowed'])
        self.assertTrue(auditor['auth']['permissions']['statement:read']['allowed'])
        self.assertTrue(auditor['auth']['permissions']['projection:read']['allowed'])
        self.assertFalse(observer['auth']['permissions']['projection:read']['allowed'])
        self.assertEqual(observer['auth']['authentication'], 'NOT_BOUND')

    def test_denied_role_never_reaches_idempotency_or_writes(self):
        first = self.service.execute(self.body())
        self.assertEqual(first['outcome'], 'ACCEPTED')
        self.assertEqual(first['role'], 'organizer')
        self.assertEqual(first['role_provenance'], PROVENANCE)
        stored = self.service.receipts['op-1']
        body = self.body()
        identity = {'operation_id': body['operation_id'], 'op': body['op'],
                    'advance_id': body['advance_id'], 'args': body['args']}
        self.assertEqual(stored['fingerprint'], digest(identity))
        self.assertNotEqual(stored['fingerprint'], digest(body))
        self.assertNotIn('role', identity)
        self.assertNotIn('role_provenance', identity)
        count = len(self.service.receipts)
        digest_before = self.service.machine.state_digest()
        replay = self.body()
        replay['instance_id'] = 'someone-else'
        for op in OPS:
            probe = self.body(op, key='op-1')
            with self.assertRaises(ApiError) as caught:
                self.service.execute(probe, role='auditor')
            self.assertEqual((caught.exception.code, caught.exception.status), ('ROLE_FORBIDDEN', 403))
            self.assertEqual(caught.exception.detail['permission'], f'command:{op}')
        with self.assertRaises(ApiError) as caught:
            self.service.execute(replay, role='observer')
        self.assertEqual(caught.exception.code, 'ROLE_FORBIDDEN')
        self.assertNotEqual(caught.exception.code, 'SESSION_CHANGED')
        self.assertEqual(len(self.service.receipts), count)
        self.assertEqual(self.service.machine.state_digest(), digest_before)
        duplicate = self.service.execute(self.body())
        self.assertTrue(duplicate['transport_duplicate'])
        self.assertEqual(duplicate['role'], 'organizer')
        self.assertEqual(duplicate['role_provenance'], PROVENANCE)
        self.assertEqual(duplicate['result'], first['result'])
        self.assertEqual(len(self.service.receipts), count)

    def test_unmapped_operation_stays_unsupported_only_for_submitters(self):
        with self.assertRaisesRegex(ApiError, 'UNSUPPORTED_OPERATION'):
            self.service.execute(self.body('DISBURSE', key='nope', ignored=True) | {'args': {}})
        before = len(self.service.receipts)
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body('DISBURSE', key='nope') | {'args': {}}, role='auditor')
        self.assertEqual(caught.exception.code, 'ROLE_FORBIDDEN')
        self.assertEqual(len(self.service.receipts), before)

    def test_reconciliation_is_read_only(self):
        self.service.execute(self.body())
        count = len(self.service.receipts)
        digest_before = self.service.machine.state_digest()
        report = self.service.reconciliation()
        self.assertEqual(report['mode'], 'READ_ONLY_RECONCILIATION')
        self.assertTrue(report['replay_matched'])
        self.assertGreaterEqual(report['entry_count'], 1)
        self.assertEqual(report['state_digest'], digest_before)
        self.assertEqual(report['bank_reconciliation'], 'NOT_BOUND')
        self.assertFalse(report['funds_executed'])
        self.assertFalse(report['durable'])
        self.assertEqual(len(self.service.receipts), count)
        self.assertEqual(self.service.machine.state_digest(), digest_before)
        self.assertTrue(self.service.export()['replay_matched'])


class DenyPort(AuthorizerPort):
    def __init__(self):
        self.seen = []

    def authenticate(self, headers):
        self.seen.append('authenticate')
        return Principal('organizer')

    def authorize(self, principal, permission):
        self.seen.append(permission)
        return Decision(False, 'injected port denies every permission')

    def describe(self, principal):
        return {'port': 'AuthorizerPort', 'mode': 'LOCAL_SYNTHETIC_ROLES', 'identity': 'NOT_BOUND',
                'role': principal.role, 'roles': list(ROLES), 'permissions': {}}


class HttpAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def open_session(self, role, token=None):
        if token is None:
            status, raw = self.request('GET', '/api/state')
            self.assertEqual(status, 200, raw)
            token = json.loads(raw)['local_token']
        status, raw = self.request('POST', '/api/session', json.dumps({'role': role}), {
            'Content-Type': 'application/json', 'X-Capital-Token': token,
        })
        self.assertEqual(status, 200, raw)
        body = json.loads(raw)
        self.assertEqual(body['role'], role)
        self.assertEqual(body['role_provenance'], PROVENANCE)
        self.assertEqual(body['identity'], 'NOT_BOUND')
        self.assertEqual(body['authentication'], 'NOT_BOUND')
        self.assertEqual(body['idp'], 'NOT_BOUND')
        self.assertEqual(body['kyc'], 'NOT_BOUND')
        self.assertEqual(body['agent_grant'], 'NOT_BOUND')
        self.assertEqual(body['action_permit'], 'NOT_BOUND')
        self.assertIsInstance(body['local_token'], str)
        self.assertTrue(body['local_token'])
        return body

    def token_for(self, role):
        if role in (None, 'organizer'):
            status, raw = self.request('GET', '/api/state')
            self.assertEqual(status, 200, raw)
            return json.loads(raw)['local_token']
        return self.open_session(role)['local_token']

    def state(self, role=None):
        headers = {}
        if role is not None:
            headers['X-Capital-Token'] = self.token_for(role)
        status, raw = self.request('GET', '/api/state', headers=headers)
        self.assertEqual(status, 200, raw)
        body = json.loads(raw)
        if role is not None:
            self.assertEqual(body['auth']['role'], role)
            self.assertEqual(body['local_token'], headers['X-Capital-Token'])
        return body

    def post(self, body, role='organizer', token=True, content_type='application/json', role_header=None):
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        if token:
            headers['X-Capital-Token'] = self.token_for(role)
        if role_header is not None:
            headers['X-Capital-Role'] = role_header
        payload = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return self.request('POST', '/api/commands', payload, headers)

    def test_headerless_organizer_receipt_is_labeled(self):
        view = self.state()
        body = dict(instance_id=view['instance_id'], operation_id='auth-offer', op='offer',
                    advance_id='sim-http-auth', args={'fixture_id': 'sim-committed', 'amount': 100})
        status, raw = self.post(body, role=None)
        receipt = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        self.assertEqual(receipt['role'], 'organizer')
        self.assertEqual(receipt['role_provenance'], PROVENANCE)
        status, raw = self.post(body, role=None)
        duplicate = json.loads(raw)
        self.assertTrue(duplicate['transport_duplicate'])
        self.assertEqual(duplicate['role'], 'organizer')
        self.assertEqual(view['auth']['identity'], 'NOT_BOUND')
        self.assertEqual(view['auth']['authentication'], 'NOT_BOUND')
        self.assertEqual(self.state('auditor')['auth']['role'], 'auditor')

    def test_auditor_and_observer_posts_do_not_write(self):
        before = self.state()
        receipts = len(self.server.service.receipts)
        valid = dict(instance_id=before['instance_id'], operation_id='auth-offer', op='draw',
                     advance_id='sim-http-auth', args={})
        for role in ('auditor', 'observer'):
            for body in (valid, b'{', b'[]', b'{"op":1,"op":2}'):
                status, raw = self.post(body, role=role)
                payload = json.loads(raw)
                self.assertEqual(status, 403, (role, body, payload))
                self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
                self.assertEqual(payload['role'], role)
                self.assertEqual(payload['permission'], COMMAND_SUBMIT)
                self.assertIn(role, payload['reason'])
        after = self.state()
        self.assertEqual(after['operation_count'], before['operation_count'])
        self.assertEqual(after['state_digest'], before['state_digest'])
        self.assertEqual(len(self.server.service.receipts), receipts)

    def test_role_does_not_replace_loopback_boundary(self):
        status, raw = self.post(b'{}', role='auditor', token=False)
        self.assertEqual((status, json.loads(raw)['error']), (403, 'LOCAL_TOKEN_REQUIRED'))
        status, raw = self.request('GET', '/api/export', headers={'Host': 'evil.example', 'X-Capital-Role': 'auditor'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'LOOPBACK_HOST_REQUIRED'))
        status, raw = self.request('POST', '/api/commands', b'{}', {
            'Host': 'evil.example', 'Origin': 'https://evil.example', 'Content-Type': 'application/json',
            'X-Capital-Role': 'organizer'})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)['error'], 'LOOPBACK_HOST_REQUIRED')
        status, raw = self.request('GET', '/api/state', headers={'Origin': 'https://evil.example', 'X-Capital-Role': 'observer'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ORIGIN_REJECTED'))
        status, raw = self.request('GET', '/', headers={'X-Capital-Role': 'not-a-role'})
        self.assertEqual(status, 200)
        self.assertIn(b'KIX Capital', raw)

    def test_unknown_and_duplicate_role_headers(self):
        status, raw = self.request('GET', '/api/state', headers={'X-Capital-Role': 'admin'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_UNKNOWN'))
        status, raw = self.request('GET', '/api/no-such-route', headers={'X-Capital-Role': 'nope'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_UNKNOWN'))
        status, raw = self.request('GET', '/api/no-such-route')
        self.assertEqual((status, json.loads(raw)['error']), (404, 'NOT_FOUND'))
        status, raw = self.request('GET', '/api/state', headers={'X-Capital-Role': 'auditor'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'SESSION_REQUIRED'))
        organizer = self.token_for('organizer')
        status, raw = self.request('GET', '/api/export', headers={
            'X-Capital-Token': organizer, 'X-Capital-Role': 'observer'})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_MISMATCH'))
        status, raw = self.request('GET', '/api/session', headers={'X-Capital-Token': organizer})
        self.assertEqual((status, json.loads(raw)['error']), (404, 'NOT_FOUND'))
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.putrequest('GET', '/api/export')
        client.putheader('X-Capital-Role', 'auditor')
        client.putheader('X-Capital-Role', 'observer')
        client.endheaders()
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_UNKNOWN'))

    def test_session_binds_a_role_scoped_token_without_writing(self):
        before = self.state()
        organizer = before['local_token']
        opened = self.open_session('auditor', organizer)
        self.assertNotEqual(opened['local_token'], organizer)
        again = self.open_session('auditor', organizer)
        self.assertEqual(again['local_token'], opened['local_token'])
        status, raw = self.request('GET', '/api/state', headers={'X-Capital-Token': opened['local_token']})
        auditor = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(auditor['auth']['role'], 'auditor')
        self.assertEqual(auditor['local_token'], opened['local_token'])
        self.assertNotEqual(auditor['local_token'], organizer)
        self.assertTrue(auditor['auth']['permissions']['projection:read']['allowed'])
        self.assertTrue(auditor['auth']['permissions']['export:read']['allowed'])
        self.assertFalse(auditor['auth']['permissions']['command:offer']['allowed'])
        mismatch = dict(instance_id=before['instance_id'], operation_id='session-mismatch', op='offer',
                        advance_id='sim-http-auth', args={'fixture_id': 'sim-committed', 'amount': 100})
        status, raw = self.post(mismatch, role='organizer', role_header='auditor')
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_MISMATCH'))
        self.assertNotIn('session-mismatch', self.server.service.receipts)
        status, raw = self.request('POST', '/api/session', json.dumps({'role': 'clerk'}), {
            'Content-Type': 'application/json', 'X-Capital-Token': organizer})
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_UNKNOWN'))
        status, raw = self.request('POST', '/api/session', json.dumps({'role': 'auditor', 'extra': 1}), {
            'Content-Type': 'application/json', 'X-Capital-Token': organizer})
        self.assertEqual((status, json.loads(raw)['error']), (400, 'INVALID_SESSION'))
        after = self.state()
        self.assertEqual(after['operation_count'], before['operation_count'])
        self.assertEqual(after['state_digest'], before['state_digest'])
        self.assertEqual(after['local_token'], organizer)

    def test_sensitive_reads_follow_the_matrix(self):
        view = self.state()
        instance = view['instance_id']
        preview = f"/api/preview/sim-http-auth?instance_id={instance}"
        operation = f"/api/operations/auth-offer?instance_id={instance}"
        for role in (None, 'organizer', 'auditor'):
            headers = {'X-Capital-Token': self.token_for(role)} if role else {}
            for path in ('/api/state', '/api/evidence', '/api/projection', '/api/terms', '/api/policy', '/api/policy/simulation', preview, operation):
                status, raw = self.request('GET', path, headers=headers)
                self.assertEqual(status, 200, (role, path, raw[:200]))
        observer = {'X-Capital-Token': self.token_for('observer')}
        for path in ('/api/state', operation):
            status, raw = self.request('GET', path, headers=observer)
            self.assertEqual(status, 200, (path, raw[:200]))
        for path in ('/api/evidence', '/api/projection', '/api/terms', '/api/policy', '/api/policy/simulation', preview, '/api/export', '/api/reconciliation', '/api/statement'):
            status, raw = self.request('GET', path, headers=observer)
            payload = json.loads(raw)
            self.assertEqual(status, 403, (path, payload))
            self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(payload['role'], 'observer')
            if path in ('/api/evidence', '/api/projection', '/api/terms', '/api/policy', '/api/policy/simulation', preview):
                self.assertEqual(payload['permission'], 'projection:read')
            if path == '/api/statement':
                self.assertEqual(payload['permission'], 'statement:read')
            if path == '/api/reconciliation':
                self.assertEqual(payload['permission'], 'reconciliation:read')
        for role, expected in (('organizer', 200), ('auditor', 200), ('observer', 403)):
            headers = {'X-Capital-Token': self.token_for(role)}
            for path in ('/api/export', '/api/reconciliation', '/api/statement'):
                status, raw = self.request('GET', path, headers=headers)
                payload = json.loads(raw)
                self.assertEqual(status, expected, (role, path, payload))
                if expected == 200 and path == '/api/reconciliation':
                    self.assertEqual(payload['mode'], 'READ_ONLY_RECONCILIATION')
                    self.assertTrue(payload['replay_matched'])
                    self.assertEqual(payload['bank_reconciliation'], 'NOT_BOUND')
                    self.assertFalse(payload['funds_executed'])
                if expected == 200 and path == '/api/statement':
                    self.assertEqual(payload['mode'], 'READ_ONLY_STATEMENT')
                    self.assertIs(payload['sales_combined'], False)
                    self.assertEqual(payload['primary_and_resale'], 'NOT_SUMMED')
                    self.assertEqual([row['id'] for row in payload['not_bound']], ['primary_sales', 'resale_sales', 'actual_paid'])
                    self.assertTrue(all(row['status'] == 'NOT_BOUND' for row in payload['not_bound']))
                if expected == 403:
                    self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
                    self.assertEqual(payload['role'], 'observer')
        for path, children, _name in GET_DISPATCH:
            if children:
                continue
            status, raw = self.request('GET', path)
            payload = json.loads(raw)
            self.assertNotEqual(payload.get('error'), 'NOT_FOUND', path)
            self.assertEqual(status, 200, (path, payload))
        after = self.state()
        self.assertEqual(after['operation_count'], view['operation_count'])
        self.assertEqual(after['state_digest'], view['state_digest'])

    def test_injected_port_denies_before_the_local_matrix(self):
        port = DenyPort()
        server = make_server(0, authorizer=port)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            client.request('GET', '/')
            page = client.getresponse()
            self.assertEqual(page.status, 200)
            page.read()
            client.close()
            self.assertEqual(port.seen, [])
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            client.request('GET', '/api/state')
            denied = client.getresponse()
            payload = json.loads(denied.read())
            client.close()
            self.assertEqual(denied.status, 403)
            self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(payload['permission'], 'state:read')
            self.assertEqual(payload['reason'], 'injected port denies every permission')
            self.assertIn('authenticate', port.seen)
            self.assertIn('state:read', port.seen)
            body = dict(instance_id=server.service.instance_id, operation_id='port', op='offer',
                        advance_id='sim-port', args={'fixture_id': 'sim-committed', 'amount': 1})
            with self.assertRaises(ApiError) as caught:
                server.service.execute(body, role='organizer')
            self.assertEqual(caught.exception.detail['reason'], 'injected port denies every permission')
            self.assertEqual(server.service.snapshot()['cases'], [])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
