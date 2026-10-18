"""LOCAL_FAKE_IDP session binding: shared authorizer vectors, strict token checks, live server.

The key is a committed test vector, not a credential. Identity and authentication stay NOT_BOUND.
"""
import base64
import hashlib
import hmac
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from email.message import Message
from http.client import HTTPConnection
from pathlib import Path

from capital import idp_fake
from capital.auth import ALL_PERMISSIONS, LocalRoleAuthorizer, Principal, ROLES
from capital.idp_fake import FakeIdpAuthorizer, IdpTokenError, mint, verify
from capital.ports import AuthorizerPort, run_authorizer_vectors
from capital.server import make_server
from capital.service import ApiError

ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000
MARKERS = ('alice@example.com', 'Alice Example', 'SYNTHETIC-SUBJECT-PLACEHOLDER')


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def sign(header, payload, key=idp_fake.TEST_VECTOR_KEY):
    """Hand-sign raw JSON text so duplicate keys and odd shapes can be built."""
    head = b64(header if isinstance(header, bytes) else json.dumps(header).encode())
    body = b64(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    mac = hmac.new(key, f'{head}.{body}'.encode(), hashlib.sha256).digest()
    return f'{head}.{body}.{b64(mac)}'


def good_header():
    return {'alg': 'HS256', 'kid': idp_fake.KID, 'typ': 'JWT'}


def good_claims(**over):
    claims = {'iss': idp_fake.ISSUER, 'aud': idp_fake.AUDIENCE, 'sub': idp_fake.SUBJECT,
              'role': 'auditor', 'exp': NOW + 300, 'nbf': NOW}
    claims.update(over)
    return claims


def headers(**pairs):
    message = Message()
    for name, value in pairs.items():
        message[name.replace('_', '-')] = value
    return message


class SharedVectorTests(unittest.TestCase):
    def test_both_authorizers_pass_the_same_vectors(self):
        run_authorizer_vectors(LocalRoleAuthorizer)
        run_authorizer_vectors(FakeIdpAuthorizer)

    def test_fake_is_a_structural_authorizer_port(self):
        self.assertIsInstance(FakeIdpAuthorizer(), AuthorizerPort)

    def test_vectors_reject_a_header_trusting_authorizer(self):
        class Trusting(LocalRoleAuthorizer):
            def authenticate(self, headers):
                from capital.auth import Principal
                return Principal(headers.get('X-Capital-Role') or 'organizer')

        with self.assertRaises(AssertionError):
            run_authorizer_vectors(Trusting)

    def test_vectors_reject_an_allow_everything_authorizer(self):
        class Open(LocalRoleAuthorizer):
            def authorize(self, principal, permission):
                from capital.auth import Decision
                return Decision(True, 'open')

        with self.assertRaises(AssertionError):
            run_authorizer_vectors(Open)

    def test_fake_describe_is_labelled_and_still_not_bound(self):
        view = FakeIdpAuthorizer().describe(Principal('auditor'))
        self.assertEqual(view['mode'], 'LOCAL_FAKE_IDP')
        self.assertEqual((view['identity'], view['authentication']), ('NOT_BOUND', 'NOT_BOUND'))


class TokenTests(unittest.TestCase):
    def test_known_answer(self):
        token = mint('auditor', now=NOW)
        head = b64(b'{"alg":"HS256","kid":"fake-idp-test-vector-1","typ":"JWT"}')
        body = b64(json.dumps(good_claims(), sort_keys=True, separators=(',', ':')).encode())
        mac = hmac.new(idp_fake.TEST_VECTOR_KEY, f'{head}.{body}'.encode(), hashlib.sha256).digest()
        self.assertEqual(token, f'{head}.{body}.{b64(mac)}')
        self.assertEqual(token, mint('auditor', now=NOW))

    def test_every_role_round_trips(self):
        for role in ROLES:
            self.assertEqual(verify(mint(role, now=NOW), now=NOW), role)

    def test_mint_refuses_unknown_role_and_bad_ttl(self):
        for bad in ('root', None, 'Organizer'):
            with self.assertRaises(ValueError):
                mint(bad, now=NOW)
        for ttl in (0, -1, idp_fake.MAX_LIFETIME_S + 1, 1.5, True):
            with self.assertRaises(ValueError):
                mint('auditor', now=NOW, ttl=ttl)

    def reason(self, token, now=NOW):
        with self.assertRaises(IdpTokenError) as ctx:
            verify(token, now=now)
        self.assertIn(ctx.exception.reason, idp_fake.REASONS)
        return ctx.exception.reason

    def test_rejections(self):
        good = mint('auditor', now=NOW)
        head, body, sig = good.split('.')
        dup_header = b'{"alg":"HS256","alg":"none","kid":"%s","typ":"JWT"}' % idp_fake.KID.encode()
        claims = good_claims()
        dup_claims = json.dumps(claims).encode()[:-1] + b',"role":"organizer"}'
        cases = [
            ('alg none', sign({**good_header(), 'alg': 'none'}, claims), 'ALG'),
            ('alg HS384', sign({**good_header(), 'alg': 'HS384'}, claims), 'ALG'),
            ('alg lowercase', sign({**good_header(), 'alg': 'hs256'}, claims), 'ALG'),
            ('none, empty signature', f'{head}.{body}.', 'MALFORMED'),
            ('unknown kid', sign({**good_header(), 'kid': 'other'}, claims), 'KID'),
            ('bad signature', f'{head}.{body}.{b64(bytes(32))}', 'SIGNATURE'),
            ('truncated signature', f'{head}.{body}.{sig[:-4]}', None),
            ('wrong key', sign(good_header(), claims, key=b'x' * 32), 'SIGNATURE'),
            ('expired', sign(good_header(), good_claims(exp=NOW, nbf=NOW - 10)), 'EXPIRED'),
            ('not yet valid', sign(good_header(), good_claims(nbf=NOW + 1, exp=NOW + 100)), 'NOT_YET_VALID'),
            ('wrong iss', sign(good_header(), good_claims(iss='https://evil.invalid')), 'ISSUER'),
            ('wrong aud', sign(good_header(), good_claims(aud='other')), 'AUDIENCE'),
            ('wrong sub', sign(good_header(), good_claims(sub='alice')), 'CLAIMS'),
            ('bad role', sign(good_header(), good_claims(role='admin')), 'ROLE'),
            ('non-string role', sign(good_header(), good_claims(role=['auditor'])), 'ROLE'),
            ('duplicate header key', sign(dup_header, claims), 'MALFORMED'),
            ('duplicate claim', sign(good_header(), dup_claims), 'MALFORMED'),
            ('extra email claim', sign(good_header(), good_claims(email='alice@example.com')), 'CLAIMS'),
            ('extra name claim', sign(good_header(), good_claims(name='Alice Example')), 'CLAIMS'),
            ('extra header key', sign({**good_header(), 'jku': 'x'}, claims), 'MALFORMED'),
            ('float exp', sign(good_header(), good_claims(exp=float(NOW + 300))), 'CLAIMS'),
            ('bool exp', sign(good_header(), good_claims(exp=True)), 'CLAIMS'),
            ('string exp', sign(good_header(), good_claims(exp=str(NOW + 300))), 'CLAIMS'),
            ('exp before nbf', sign(good_header(), good_claims(exp=NOW - 5)), 'CLAIMS'),
            ('lifetime too long', sign(good_header(), good_claims(exp=NOW + idp_fake.MAX_LIFETIME_S + 1)), 'CLAIMS'),
            ('NaN constant', sign(good_header(), json.dumps(claims).replace(str(NOW + 300), 'NaN').encode()), 'MALFORMED'),
            ('payload not an object', sign(good_header(), b'[1]'), 'MALFORMED'),
            ('deep nesting', sign(good_header(), b'[' * 1400), 'MALFORMED'),
            ('two segments', f'{head}.{body}', 'MALFORMED'),
            ('four segments', f'{good}.x', 'MALFORMED'),
            ('padding', f'{head}=.{body}.{sig}', 'MALFORMED'),
            ('standard alphabet', f'{head}.{body}+/.{sig}', 'MALFORMED'),
            ('non-canonical bits', f'{head}.{body[:-1]}{"B" if body[-1] != "B" else "C"}.{sig}', None),
            ('oversize', 'a' * (idp_fake.MAX_TOKEN_BYTES + 1), 'SIZE'),
            ('empty', '', 'MALFORMED'),
            ('non-ascii', good + 'é', 'MALFORMED'),
        ]
        for label, token, expected in cases:
            with self.subTest(label):
                reason = self.reason(token)
                if expected is not None:
                    self.assertEqual(reason, expected)

    def test_validity_window_has_no_leeway(self):
        token = mint('observer', now=NOW, ttl=60)
        self.assertEqual(verify(token, now=NOW), 'observer')
        self.assertEqual(verify(token, now=NOW + 59), 'observer')
        self.assertEqual(self.reason(token, now=NOW + 60), 'EXPIRED')
        self.assertEqual(self.reason(token, now=NOW - 1), 'NOT_YET_VALID')

    def test_non_string_tokens_are_malformed(self):
        for value in (None, 7, b'abc', ['a']):
            self.assertEqual(self.reason(value), 'MALFORMED')


class SessionRouteTests(unittest.TestCase):
    """Authorizer-level checks on `session_role`, with an injectable clock."""

    def role(self, **pairs):
        return FakeIdpAuthorizer(clock=lambda: NOW).session_role(headers(**pairs))

    def code(self, **pairs):
        with self.assertRaises(ApiError) as ctx:
            self.role(**pairs)
        return ctx.exception.code, ctx.exception.status, ctx.exception.detail

    def test_bearer_forms(self):
        self.assertEqual(self.role(Authorization='Bearer ' + mint('observer', now=NOW)), 'observer')
        self.assertEqual(self.code(), ('IDP_TOKEN_REQUIRED', 401, None))
        for value in ('Basic abc', 'bearer ' + mint('observer', now=NOW), mint('observer', now=NOW), 'Bearer '):
            self.assertEqual(self.code(Authorization=value)[:2], ('IDP_TOKEN_INVALID', 401))

    def test_duplicate_authorization_headers_are_rejected(self):
        message = Message()
        token = 'Bearer ' + mint('observer', now=NOW)
        message['Authorization'] = token
        message['Authorization'] = token
        with self.assertRaises(ApiError) as ctx:
            FakeIdpAuthorizer(clock=lambda: NOW).session_role(message)
        self.assertEqual(ctx.exception.code, 'IDP_TOKEN_INVALID')

    def test_detail_is_only_a_reason_slug(self):
        _, _, detail = self.code(Authorization='Bearer ' + sign(good_header(), good_claims(email='alice@example.com')))
        self.assertEqual(detail, {'reason': 'CLAIMS'})


class LiveBase:
    authorizer_factory = FakeIdpAuthorizer

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / 'ws'
        self.event_log = Path(self.tmp.name) / 'events.jsonl'
        self.start(self.authorizer_factory())

    def start(self, authorizer):
        self.server = make_server(0, authorizer=authorizer, workspace=str(self.workspace), event_log=str(self.event_log))
        self.port = self.server.server_port
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            worker.join(timeout=2)
        self.addCleanup(stop)

    def call(self, method, path, body=None, token=None, extra=None):
        hdrs = dict(extra or {})
        payload = None
        if body is not None:
            hdrs['Content-Type'] = 'application/json'
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        if token is not None:
            hdrs['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=payload, headers=hdrs)
        response = client.getresponse()
        raw = response.read()
        client.close()
        return response.status, json.loads(raw.decode())

    def bootstrap(self):
        return self.call('GET', '/api/state')[1]['local_token']

    def session(self, role, bearer=None, **kw):
        extra = {'Authorization': f'Bearer {bearer}'} if bearer is not None else {}
        return self.call('POST', '/api/session', {'role': role}, token=self.bootstrap(), extra=extra)

    def fingerprint(self):
        state = self.call('GET', '/api/state')[1]
        files = sorted(self.workspace.glob('*.json')) if self.workspace.exists() else []
        return (state.get('operation_count'), state.get('state_digest'),
                [path.read_bytes() for path in files])


class LiveFakeTests(LiveBase, unittest.TestCase):
    def test_each_role_binds_from_its_claim(self):
        for role in ROLES:
            status, body = self.session(role, mint(role))
            self.assertEqual(status, 200, body)
            self.assertEqual(body['role'], role)
            self.assertEqual(body['mode'], 'LOCAL_FAKE_IDP')
            for key in ('identity', 'authentication', 'idp', 'kyc', 'agent_grant', 'action_permit'):
                self.assertEqual(body[key], 'NOT_BOUND')
            self.assertEqual(body['role_provenance'], 'SYNTHETIC_LOCAL_ROLE')
            self.assertEqual(self.server.authorizer.token_for(role), body['local_token'])

    def test_later_requests_keep_the_loopback_token(self):
        _, body = self.session('auditor', mint('auditor'))
        token = body['local_token']
        status, state = self.call('GET', '/api/state', token=token)
        self.assertEqual(status, 200)
        self.assertEqual(state['auth']['role'], 'auditor')
        self.assertEqual(state['auth']['mode'], 'LOCAL_FAKE_IDP')
        # the IdP token is not a loopback token
        status, err = self.call('GET', '/api/state', extra={'X-Capital-Token': mint('auditor')})
        self.assertEqual((status, err['error']), (403, 'LOCAL_TOKEN_REQUIRED'))

    def test_body_role_differing_from_claim_is_403_and_mints_nothing(self):
        status, body = self.session('organizer', mint('auditor'))
        self.assertEqual((status, body['error']), (403, 'ROLE_MISMATCH'))
        self.assertEqual(body['role'], 'auditor')
        self.assertIsNone(self.server.authorizer.token_for('auditor'))
        self.assertIsNone(self.server.authorizer.token_for('observer'))

    def test_missing_token_is_401(self):
        status, body = self.session('auditor')
        self.assertEqual((status, body), (401, {'error': 'IDP_TOKEN_REQUIRED'}))
        self.assertIsNone(self.server.authorizer.token_for('auditor'))

    def test_rejected_tokens_are_401_and_write_nothing(self):
        good = mint('auditor')
        head, body, sig = good.split('.')
        now = idp_fake.time.time()
        claims = good_claims(exp=int(now) + 300, nbf=int(now))
        bad = {
            'none': sign({**good_header(), 'alg': 'none'}, claims),
            'hs384': sign({**good_header(), 'alg': 'HS384'}, claims),
            'signature': f'{head}.{body}.{b64(bytes(32))}',
            'expired': mint('auditor', now=int(now) - 600, ttl=60),
            'future': mint('auditor', now=int(now) + 3000),
            'iss': sign(good_header(), {**claims, 'iss': 'x'}),
            'aud': sign(good_header(), {**claims, 'aud': 'x'}),
            'kid': sign({**good_header(), 'kid': 'x'}, claims),
            'missing': sign(good_header(), {k: v for k, v in claims.items() if k != 'nbf'}),
            'email': sign(good_header(), {**claims, 'email': 'alice@example.com', 'name': 'Alice Example'}),
            'dup': sign(good_header(), json.dumps(claims).encode()[:-1] + b',"role":"organizer"}'),
            'oversize': 'a' * 3000,
        }
        before = self.fingerprint()
        for label, token in bad.items():
            with self.subTest(label):
                status, err = self.session('auditor', token)
                self.assertEqual(status, 401, err)
                self.assertEqual(err['error'], 'IDP_TOKEN_INVALID')
                self.assertEqual(set(err), {'error', 'reason'})
                self.assertNotIn(token, json.dumps(err))
        self.assertEqual(self.fingerprint(), before)
        self.assertIsNone(self.server.authorizer.token_for('auditor'))

    def test_authorization_header_elsewhere_changes_nothing(self):
        token = self.bootstrap()
        for bearer in (mint('auditor'), 'garbage'):
            status, state = self.call('GET', '/api/state', token=token, extra={'Authorization': f'Bearer {bearer}'})
            self.assertEqual((status, state['auth']['role']), (200, 'organizer'))
            status, _ = self.call('POST', '/api/commands', {}, token=token, extra={'Authorization': f'Bearer {bearer}'})
            self.assertNotEqual(status, 401)

    def test_no_subject_name_or_email_is_persisted_or_observed(self):
        for role in ROLES:
            self.assertEqual(self.session(role, mint(role))[0], 200)
        leaky = sign(good_header(), good_claims(email='alice@example.com', name='Alice Example'))
        self.assertEqual(self.session('auditor', leaky)[0], 401)
        self.assertEqual(self.session('auditor', 'a' * 3000)[0], 401)
        # force a workspace write, then read everything back
        token = self.bootstrap()
        self.call('GET', '/api/metrics', token=token)
        surfaces = [json.dumps(self.call('GET', path, token=token)[1])
                    for path in ('/api/state', '/api/metrics', '/api/export')]
        surfaces += [path.read_text() for path in self.workspace.rglob('*') if path.is_file() and path.name != 'export-dev.key']
        if self.event_log.exists():
            log = self.event_log.read_text()
            surfaces.append(log)
            for line in log.splitlines():
                row = json.loads(line)
                if row.get('path') == '/api/session' and row.get('status') == 401:
                    self.assertEqual(row.get('code'), 'IDP_TOKEN_INVALID')
        issued = [mint(role) for role in ROLES] + [leaky]
        for text in surfaces:
            for needle in (*MARKERS, *issued):
                self.assertNotIn(needle, text)
            self.assertIsNone(re.search(r'eyJ[A-Za-z0-9_-]{10,}', text))


class DefaultModeTests(LiveBase, unittest.TestCase):
    """Default authorizer: Authorization is ignored and the session path is unchanged."""
    authorizer_factory = LocalRoleAuthorizer

    def test_default_session_ignores_authorization(self):
        for bearer in (None, 'garbage', mint('observer')):
            status, body = self.session('auditor', bearer)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['mode'], 'LOCAL_SYNTHETIC_ROLES')

    def test_default_body_role_is_self_selected(self):
        self.assertEqual(self.session('observer', mint('auditor'))[1]['role'], 'observer')


class ScriptAndServerTests(unittest.TestCase):
    def test_script_mints_each_role(self):
        for role in ROLES:
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'fake_idp.py'), '--role', role, '--now', str(NOW)],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), mint(role, now=NOW))
            self.assertIn('LOCAL_FAKE_IDP', done.stderr)
            self.assertNotIn('LOCAL_FAKE_IDP', done.stdout)

    def test_script_all_and_bad_arguments(self):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'fake_idp.py'), '--all', '--now', str(NOW)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(done.stdout), {role: mint(role, now=NOW) for role in ROLES})
        for args in (['--role', 'admin'], ['--role', 'auditor', '--ttl', '0'], []):
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'fake_idp.py'), *args],
                                  capture_output=True, text=True, timeout=30)
            self.assertNotEqual(done.returncode, 0)

    def test_server_flag_and_startup_line(self):
        source = (ROOT / 'capital' / 'server.py').read_text()
        self.assertIn("'--authorizer'", source)
        self.assertIn('authorizer LOCAL_FAKE_IDP', source)
        done = subprocess.run([sys.executable, '-m', 'capital.server', '--help'], cwd=ROOT,
                              capture_output=True, text=True, timeout=30)
        self.assertIn('--authorizer', done.stdout)

    def test_modules_have_no_network_imports_or_key_sources(self):
        for path in (ROOT / 'capital' / 'idp_fake.py', ROOT / 'scripts' / 'fake_idp.py'):
            text = path.read_text()
            for needle in ('import socket', 'import http', 'import urllib', 'import ssl', 'import requests',
                           'os.environ', 'getenv', 'open('):
                self.assertNotIn(needle, text, f'{path.name}: {needle}')

    def test_mint_has_no_key_or_kid_parameter(self):
        import inspect
        self.assertEqual(list(inspect.signature(mint).parameters), ['role', 'now', 'ttl'])


if __name__ == '__main__':
    unittest.main()
