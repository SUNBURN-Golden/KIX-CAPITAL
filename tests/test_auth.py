import json
import http.client
import threading
import unittest
from email.message import Message

from capital.auth import (
    ALL_PERMISSIONS, COMMAND_SUBMIT, DEFAULT_ROLE, MATRIX, OP_PERMISSIONS, PROVENANCE,
    ROLES, AuthorizerPort, Decision, LocalRoleAuthorizer, Principal, require, route_permission,
)
from capital.server import make_server
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
            '/api/preview/sim-a': 'projection:read',
            '/api/operations/op-1': 'receipt:read',
            '/api/export': 'export:read',
            '/api/reconciliation': 'reconciliation:read',
        }
        for path, permission in routes.items():
            self.assertEqual(route_permission(path), permission, path)
            self.assertIn(permission, ALL_PERMISSIONS)
        self.assertIsNone(route_permission('/api/projection/extra'))
        self.assertIsNone(route_permission('/api/commands'))
        self.assertIsNone(route_permission('/api/unknown'))
        self.assertIsNone(route_permission('/'))

    def test_matrix_fails_closed_and_splits_the_three_roles(self):
        authorizer = LocalRoleAuthorizer()
        organizer, auditor, observer = (Principal(role) for role in ROLES)
        for permission in ALL_PERMISSIONS:
            self.assertTrue(authorizer.authorize(organizer, permission).allowed, permission)
        for permission in ALL_PERMISSIONS:
            decision = authorizer.authorize(auditor, permission)
            self.assertEqual(decision.allowed, permission.endswith(':read'), permission)
        for permission in ('export:read', 'reconciliation:read', COMMAND_SUBMIT, 'command:draw'):
            self.assertFalse(authorizer.authorize(observer, permission).allowed, permission)
        for permission in ('state:read', 'reference:read', 'projection:read', 'receipt:read'):
            self.assertTrue(authorizer.authorize(observer, permission).allowed, permission)
        self.assertFalse(authorizer.authorize(organizer, 'admin:write').allowed)
        self.assertFalse(authorizer.authorize(Principal('named-person'), 'state:read').allowed)
        self.assertEqual(MATRIX['auditor'].isdisjoint(OP_PERMISSIONS.values()), True)
        self.assertNotIn(COMMAND_SUBMIT, MATRIX['auditor'])
        self.assertNotIn(COMMAND_SUBMIT, MATRIX['observer'])

    def test_missing_role_is_organizer_and_unknown_or_duplicate_is_rejected(self):
        authorizer = LocalRoleAuthorizer()
        self.assertEqual(authorizer.authenticate(headers_of()).role, DEFAULT_ROLE)
        self.assertEqual(authorizer.authenticate(headers_of(('X-Capital-Role', 'auditor'))).role, 'auditor')
        self.assertEqual(authorizer.authenticate(headers_of()).provenance, PROVENANCE)
        for pairs in (
            (('X-Capital-Role', 'admin'),),
            (('X-Capital-Role', 'Auditor'),),
            (('X-Capital-Role', ''),),
            (('X-Capital-Role', 'organizer,auditor'),),
            (('X-Capital-Role', 'auditor'), ('X-Capital-Role', 'observer')),
            (('X-Capital-Role', 'organizer'), ('X-Capital-Role', 'organizer')),
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
        self.assertTrue(observer['auth']['permissions']['projection:read']['allowed'])

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

    def state(self, role=None):
        headers = {'X-Capital-Role': role} if role else {}
        status, raw = self.request('GET', '/api/state', headers=headers)
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def post(self, body, role='organizer', token=True, content_type='application/json'):
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        if token:
            headers['X-Capital-Token'] = self.state()['local_token']
        if role is not None:
            headers['X-Capital-Role'] = role
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
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.putrequest('GET', '/api/export')
        client.putheader('X-Capital-Role', 'auditor')
        client.putheader('X-Capital-Role', 'observer')
        client.endheaders()
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_UNKNOWN'))

    def test_sensitive_reads_follow_the_matrix(self):
        view = self.state()
        instance = view['instance_id']
        preview = f"/api/preview/sim-http-auth?instance_id={instance}"
        operation = f"/api/operations/auth-offer?instance_id={instance}"
        for role in (None, 'organizer', 'auditor', 'observer'):
            headers = {'X-Capital-Role': role} if role else {}
            for path in ('/api/state', '/api/evidence', '/api/projection', preview, operation):
                status, raw = self.request('GET', path, headers=headers)
                self.assertEqual(status, 200, (role, path, raw[:200]))
        for role, expected in (('organizer', 200), ('auditor', 200), ('observer', 403)):
            for path in ('/api/export', '/api/reconciliation'):
                status, raw = self.request('GET', path, headers={'X-Capital-Role': role})
                payload = json.loads(raw)
                self.assertEqual(status, expected, (role, path, payload))
                if expected == 200 and path == '/api/reconciliation':
                    self.assertEqual(payload['mode'], 'READ_ONLY_RECONCILIATION')
                    self.assertTrue(payload['replay_matched'])
                    self.assertEqual(payload['bank_reconciliation'], 'NOT_BOUND')
                    self.assertFalse(payload['funds_executed'])
                if expected == 403:
                    self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
                    self.assertEqual(payload['role'], 'observer')
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
