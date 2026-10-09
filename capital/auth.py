"""Synthetic local roles and the port a real identity provider would replace.

This module does not import the service layer. It has no accounts, passwords,
personal data, or network calls. `LocalRoleAuthorizer` keeps one process-local
loopback token per synthetic role. That table is not an identity provider,
credential store, or AgentGrant. Identity stays NOT_BOUND.
"""
from __future__ import annotations

import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

ROLES = ('organizer', 'auditor', 'observer')
DEFAULT_ROLE = 'organizer'
PROVENANCE = 'SYNTHETIC_LOCAL_ROLE'
COMMAND_SUBMIT = 'command:submit'
SESSION_BIND = 'session:bind'

# Keep this tuple aligned with CapitalService.OPS. The test locks the sets together.
OP_ORDER = (
    'offer', 'approve', 'reject', 'cancel', 'bind_settlement',
    'draw', 'repay', 'close', 'default', 'reconcile',
)
OP_PERMISSIONS = {op: f'command:{op}' for op in OP_ORDER}

READ_PERMISSIONS = (
    'state:read', 'reference:read', 'projection:read', 'receipt:read',
    'export:read', 'reconciliation:read', 'statement:read',
)
# Observer may read state, reference, and receipts. Export, reconciliation,
# the five-category statement, and the local projection candidate stay with auditor.
OBSERVER_READ = ('state:read', 'reference:read', 'receipt:read')
ALL_PERMISSIONS = (COMMAND_SUBMIT, *OP_PERMISSIONS.values(), *READ_PERMISSIONS, SESSION_BIND)

# Placeholder matrix, not an entitlement policy. Real role-to-person mapping stays NOT_BOUND.
# session:bind only mints another synthetic loopback token. It is not a financial write.
MATRIX = {
    'organizer': frozenset(ALL_PERMISSIONS),
    'auditor': frozenset((*READ_PERMISSIONS, SESSION_BIND)),
    'observer': frozenset((*OBSERVER_READ, SESSION_BIND)),
}

# Receipts saved before this label existed. Not a session role and not in ROLES.
UNLABELED = 'UNLABELED'

# Exact path or prefix. Unmapped paths are denied by the caller (HTTP 404).
ROUTE_PERMISSIONS = (
    ('/api/state', 'state:read', False),
    ('/api/scenarios', 'reference:read', True),
    ('/api/readiness', 'reference:read', False),
    ('/api/evidence', 'projection:read', False),
    ('/api/projection', 'projection:read', False),
    ('/api/terms', 'projection:read', True),
    ('/api/policy', 'projection:read', True),
    ('/api/preview/', 'projection:read', True),
    ('/api/operations/', 'receipt:read', True),
    ('/api/export', 'export:read', False),
    ('/api/export/manifest', 'export:read', False),
    ('/api/reconciliation', 'reconciliation:read', False),
    ('/api/statement', 'statement:read', False),
)


@dataclass(frozen=True)
class Principal:
    role: str
    provenance: str = PROVENANCE


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


class AuthorizerPort(ABC):
    """Attach point for a future identity provider. The local adapter is synthetic only."""

    @abstractmethod
    def authenticate(self, headers) -> Principal:
        """Resolve a principal from request headers. Raises ApiError ROLE_UNKNOWN."""

    @abstractmethod
    def authorize(self, principal, permission) -> Decision:
        """Fail closed for an unknown role or an unknown permission."""

    @abstractmethod
    def describe(self, principal) -> dict:
        """State `auth` block for the requesting principal. Not a credential."""


def path_matches(prefix, children, path):
    """Exact path, or a registered prefix and its children. Unlisted paths do not match."""
    if children:
        base = prefix if prefix.endswith('/') else prefix + '/'
        return path == prefix or path.startswith(base)
    return path == prefix


def route_permission(path):
    """Return the permission for a GET path, or None when the path is unmapped."""
    for prefix, permission, children in ROUTE_PERMISSIONS:
        if path_matches(prefix, children, path):
            return permission
    return None


def _fail(code, status=403, detail=None):
    # Imported lazily so this module never loads the service at import time.
    from capital.service import ApiError
    raise ApiError(code, status, detail)


def require(authorizer, principal, permission):
    decision = authorizer.authorize(principal, permission)
    if not decision.allowed:
        _fail('ROLE_FORBIDDEN', 403, {
            'role': principal.role,
            'permission': permission,
            'reason': decision.reason,
        })
    return decision


class LocalRoleAuthorizer(AuthorizerPort):
    """Binds each synthetic role to one loopback token. The header cannot switch roles.

    A missing token is organizer, so existing same-origin callers keep working.
    Auditor and observer exist only after `bind_role` (POST /api/session). A token
    never authorizes a different role. This is self-selection, not authentication.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._by_role = {}
        self._by_token = {}
        self.bind_role(DEFAULT_ROLE)

    def bind_role(self, role):
        """Return the process-local token already bound to `role`, or mint one.

        One token per role keeps the table bounded by `ROLES`. The token is not a
        credential and is not written to the workspace.
        """
        if role not in ROLES:
            _fail('ROLE_UNKNOWN', 403)
        with self._lock:
            existing = self._by_role.get(role)
            if existing is not None:
                return existing
            token = secrets.token_urlsafe(32)
            self._by_role[role] = token
            self._by_token[token] = role
            return token

    def token_for(self, role):
        with self._lock:
            return self._by_role.get(role)

    def role_for_token(self, token):
        if not isinstance(token, str):
            return None
        with self._lock:
            return self._by_token.get(token)

    def authenticate(self, headers) -> Principal:
        values = headers.get_all('X-Capital-Role')
        if values and (len(values) != 1 or values[0] not in ROLES):
            _fail('ROLE_UNKNOWN', 403)
        claimed = values[0] if values else None
        tokens = headers.get_all('X-Capital-Token')
        if tokens:
            if len(tokens) != 1:
                _fail('LOCAL_TOKEN_REQUIRED', 403)
            role = self.role_for_token(tokens[0])
            if role is None:
                _fail('LOCAL_TOKEN_REQUIRED', 403)
            if claimed is not None and claimed != role:
                _fail('ROLE_MISMATCH', 403, {'role': role, 'claimed': claimed})
            return Principal(role)
        if claimed not in (None, DEFAULT_ROLE):
            _fail('SESSION_REQUIRED', 403, {'role': claimed})
        return Principal(DEFAULT_ROLE)

    def authorize(self, principal, permission) -> Decision:
        role = principal.role
        if not isinstance(permission, str) or permission not in ALL_PERMISSIONS:
            return Decision(False, f'{role} 역할에 매핑되지 않은 권한입니다.')
        granted = MATRIX.get(role)
        if granted is None or permission not in granted:
            return Decision(False, f'{role} 역할은 {permission} 권한이 없습니다.')
        return Decision(True, f'{role} 역할은 {permission} 권한이 있습니다.')

    def describe(self, principal) -> dict:
        permissions = {}
        for permission in ALL_PERMISSIONS:
            decision = self.authorize(principal, permission)
            permissions[permission] = {'allowed': decision.allowed, 'reason': decision.reason}
        return {
            'port': 'AuthorizerPort',
            'mode': 'LOCAL_SYNTHETIC_ROLES',
            'identity': 'NOT_BOUND',
            'authentication': 'NOT_BOUND',
            'role': principal.role,
            'roles': list(ROLES),
            'permissions': permissions,
        }
