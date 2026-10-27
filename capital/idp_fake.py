"""Fake IdP session binding. LOCAL_FAKE_IDP, SIMULATED. Not an identity provider.

`mint` signs a compact HS256 token for one of the four synthetic roles with a
committed test-vector key. That key is not a credential and protects nothing.
`FakeIdpAuthorizer` only changes how `POST /api/session` learns the role: the
verified `role` claim replaces self-selection. Later requests keep the
role-scoped loopback `X-Capital-Token`. Identity and authentication stay
NOT_BOUND. No OAuth or OIDC flow, JWKS, account, password, KYC, or network
call. The subject is one fixed placeholder, the verifier returns only the role,
and no subject, name or email can enter the workspace, event log or metrics.
A token has no `jti`, so it can be replayed until `exp`.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time

from capital.auth import LocalRoleAuthorizer, ROLES

LABEL = 'LOCAL_FAKE_IDP'
ISSUER = 'https://fake-idp.invalid/kix-capital-local'
AUDIENCE = 'kix-capital-local-facade'
KID = 'fake-idp-test-vector-1'
SUBJECT = 'SYNTHETIC-SUBJECT-PLACEHOLDER'
# Test vector, not a credential. Committed on purpose and distinct from export-dev.key.
TEST_VECTOR_KEY = b'kix-capital-fake-idp-test-vector-key-NOT-A-CREDENTIAL'
MAX_TOKEN_BYTES = 2048
MAX_LIFETIME_S = 3600
DEFAULT_TTL_S = 300
REASONS = (
    'MALFORMED', 'SIZE', 'ALG', 'KID', 'SIGNATURE', 'EXPIRED', 'NOT_YET_VALID',
    'ISSUER', 'AUDIENCE', 'CLAIMS', 'ROLE',
)
_HEADER_KEYS = frozenset(('alg', 'kid', 'typ'))
_CLAIM_KEYS = frozenset(('iss', 'aud', 'sub', 'role', 'exp', 'nbf'))
_SEGMENT = re.compile(r'[A-Za-z0-9_-]+')


class IdpTokenError(Exception):
    """Closed-set rejection. `reason` is one of REASONS and never echoes token content."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _b64e(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64d(segment):
    try:
        raw = base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4))
    except (binascii.Error, ValueError):
        raise IdpTokenError('MALFORMED')
    if _b64e(raw) != segment:  # rejects non-canonical trailing bits
        raise IdpTokenError('MALFORMED')
    return raw


def _strict_object(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate key')
    return dict(pairs)


def _load(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_strict_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise IdpTokenError('MALFORMED')
    if type(value) is not dict:
        raise IdpTokenError('MALFORMED')
    return value


def _sign(signing_input):
    return hmac.new(TEST_VECTOR_KEY, signing_input.encode('ascii'), hashlib.sha256).digest()


def _compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('ascii')


def mint(role, *, now=None, ttl=DEFAULT_TTL_S):
    """Deterministic HS256 token for a synthetic role. No key, kid or claim parameters."""
    if role not in ROLES:
        raise ValueError('unknown synthetic role')
    if type(ttl) is not int or not 0 < ttl <= MAX_LIFETIME_S:
        raise ValueError('ttl out of range')
    issued = int(time.time()) if now is None else now
    if type(issued) is not int:
        raise ValueError('now must be an int')
    header = _b64e(_compact({'alg': 'HS256', 'kid': KID, 'typ': 'JWT'}))
    payload = _b64e(_compact({
        'aud': AUDIENCE, 'exp': issued + ttl, 'iss': ISSUER, 'nbf': issued,
        'role': role, 'sub': SUBJECT,
    }))
    signing_input = f'{header}.{payload}'
    return f'{signing_input}.{_b64e(_sign(signing_input))}'


def verify(token, *, now):
    """Return the verified role claim. Raise IdpTokenError(reason) otherwise."""
    if not isinstance(token, str) or not token.isascii():
        raise IdpTokenError('MALFORMED')
    if len(token) > MAX_TOKEN_BYTES:
        raise IdpTokenError('SIZE')
    parts = token.split('.')
    if len(parts) != 3 or not all(_SEGMENT.fullmatch(part) for part in parts):
        raise IdpTokenError('MALFORMED')
    header_raw, payload_raw, signature_raw = (_b64d(part) for part in parts)
    header = _load(header_raw)
    if set(header) != _HEADER_KEYS or header['typ'] != 'JWT':
        raise IdpTokenError('MALFORMED')
    if header['alg'] != 'HS256':
        raise IdpTokenError('ALG')
    if header['kid'] != KID:
        raise IdpTokenError('KID')
    if not hmac.compare_digest(_sign(f'{parts[0]}.{parts[1]}'), signature_raw):
        raise IdpTokenError('SIGNATURE')
    claims = _load(payload_raw)
    if set(claims) != _CLAIM_KEYS:
        raise IdpTokenError('CLAIMS')
    exp, nbf = claims['exp'], claims['nbf']
    if type(exp) is not int or type(nbf) is not int or exp <= nbf or exp - nbf > MAX_LIFETIME_S:
        raise IdpTokenError('CLAIMS')
    if claims['iss'] != ISSUER:
        raise IdpTokenError('ISSUER')
    if claims['aud'] != AUDIENCE:
        raise IdpTokenError('AUDIENCE')
    if claims['sub'] != SUBJECT:
        raise IdpTokenError('CLAIMS')
    role = claims['role']
    if type(role) is not str or role not in ROLES:
        raise IdpTokenError('ROLE')
    if now < nbf:
        raise IdpTokenError('NOT_YET_VALID')
    if now >= exp:
        raise IdpTokenError('EXPIRED')
    return role


class FakeIdpAuthorizer(LocalRoleAuthorizer):
    """Local role authorizer whose session binding takes the role from a fake IdP claim.

    `authenticate` and `authorize` are inherited unchanged. Identity and
    authentication stay NOT_BOUND.
    """

    def __init__(self, clock=time.time):
        super().__init__()
        self._clock = clock

    def describe(self, principal) -> dict:
        return {**super().describe(principal), 'mode': LABEL}

    def session_role(self, headers):
        """Return the verified role from exactly one `Authorization: Bearer` header."""
        from capital.service import ApiError  # lazy, like auth._fail
        values = headers.get_all('Authorization')
        if not values:
            raise ApiError('IDP_TOKEN_REQUIRED', 401)
        if len(values) != 1 or not values[0].startswith('Bearer '):
            raise ApiError('IDP_TOKEN_INVALID', 401, {'reason': 'MALFORMED'})
        try:
            return verify(values[0][len('Bearer '):], now=int(self._clock()))
        except IdpTokenError as exc:
            raise ApiError('IDP_TOKEN_INVALID', 401, {'reason': exc.reason})
