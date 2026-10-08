"""Synthetic local roles and the port a real identity provider would replace.

This module does not import the service layer. It has no accounts, passwords,
personal data, token issuance, or network calls. Identity stays NOT_BOUND.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

ROLES = ('organizer', 'auditor', 'observer')
DEFAULT_ROLE = 'organizer'
PROVENANCE = 'SYNTHETIC_LOCAL_ROLE'
COMMAND_SUBMIT = 'command:submit'

# Keep this tuple aligned with CapitalService.OPS. The test locks the sets together.
OP_ORDER = (
    'offer', 'approve', 'reject', 'cancel', 'bind_settlement',
    'draw', 'repay', 'close', 'default', 'reconcile',
)
OP_PERMISSIONS = {op: f'command:{op}' for op in OP_ORDER}

READ_PERMISSIONS = (
    'state:read', 'reference:read', 'projection:read', 'receipt:read',
    'export:read', 'reconciliation:read',
)
OBSERVER_READ = ('state:read', 'reference:read', 'projection:read', 'receipt:read')
ALL_PERMISSIONS = (COMMAND_SUBMIT, *OP_PERMISSIONS.values(), *READ_PERMISSIONS)

# Placeholder matrix, not an entitlement policy. Real role-to-person mapping stays NOT_BOUND.
MATRIX = {
    'organizer': frozenset(ALL_PERMISSIONS),
    'auditor': frozenset(READ_PERMISSIONS),
    'observer': frozenset(OBSERVER_READ),
}

# Exact path or prefix. Unmapped paths are denied by the caller (HTTP 404).
ROUTE_PERMISSIONS = (
    ('/api/state', 'state:read', False),
    ('/api/scenarios', 'reference:read', True),
    ('/api/readiness', 'reference:read', False),
    ('/api/evidence', 'projection:read', False),
    ('/api/preview/', 'projection:read', True),
    ('/api/operations/', 'receipt:read', True),
    ('/api/export', 'export:read', False),
    ('/api/reconciliation', 'reconciliation:read', False),
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


def route_permission(path):
    """Return the permission for a GET path, or None when the path is unmapped."""
    for prefix, permission, children in ROUTE_PERMISSIONS:
        if children:
            if path == prefix or path.startswith(prefix if prefix.endswith('/') else prefix + '/'):
                return permission
        elif path == prefix:
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
    """Header role beside the unchanged loopback token. Missing header is organizer."""

    def authenticate(self, headers) -> Principal:
        values = headers.get_all('X-Capital-Role')
        if not values:
            return Principal(DEFAULT_ROLE)
        if len(values) != 1 or values[0] not in ROLES:
            _fail('ROLE_UNKNOWN', 403)
        return Principal(values[0])

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
            'role': principal.role,
            'roles': list(ROLES),
            'permissions': permissions,
        }
