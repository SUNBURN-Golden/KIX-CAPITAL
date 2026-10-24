"""Structural ports for the local Capital facade.

`typing.Protocol` definitions live here so a later adapter can replace one
seam without inheriting the local class. Local classes stay in their modules
and satisfy these protocols structurally. Nothing in this module is an
upstream adoption: see docs/SEAMS.md. CAP-16 exact producer/SDK tuple stays
NOT_BOUND. These protocols are not SEMANTIC_CONFORMANCE.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from capital.policy import SettlementPolicyPort
from capital.shadow import ShadowPolicyPort
from capital.setoff import SetoffQuotePort
from capital.terms import TermsPolicyPort
from capital.underwriting import UnderwritingPort


@runtime_checkable
class StoragePort(Protocol):
    """Load and save one local workspace envelope. Not a database."""

    def load(self):
        """Return a verified envelope, or None when nothing has been saved."""

    def save(self, document):
        """Persist the payload. The local file adapter checksums and renames.

        The service passes `overlay=<section>` as a keyword only when the overlay journal is
        non-empty; an adapter without that parameter still serves an empty overlay."""

    def close(self):
        """Release a process lock. In-memory storage does nothing."""


@runtime_checkable
class ProjectionPort(Protocol):
    """Fold a journal and settlement evidence into a read-only projection."""

    def project(self, journal, evidence):
        """Return entries, accounts, read_model, and conservation. Do not write."""


@runtime_checkable
class AuthorizerPort(Protocol):
    """Resolve a principal and allow or deny a permission. Not an identity provider."""

    def authenticate(self, headers):
        """Return a principal or raise a role error. Headers are not credentials."""

    def authorize(self, principal, permission):
        """Fail closed for an unknown role or an unknown permission."""

    def describe(self, principal) -> dict:
        """State `auth` block. Not a credential and not a person binding."""


@runtime_checkable
class SignaturePort(Protocol):
    """Sign a content digest. The default leaves the signature NOT_BOUND."""

    def sign(self, content_digest: str) -> dict:
        """Return a signature block. The block must not contain key material."""


@runtime_checkable
class ProducerPort(Protocol):
    """Command and read gateway in front of the pinned credit and settlement FSMs.

    `PinnedFsmProducer` is the local implementation. Opt-in `GateHttpProducer`
    talks to a loopback `LOCAL_FAKE_GATE` and is not an adoption. A later
    producer adapter replaces that wrapper and must pass
    `tests/test_producer_port.py`. Passing those vectors is not
    SEMANTIC_CONFORMANCE. CAP-16 stays NOT_BOUND for the exact
    Protocol/Commerce producer tuple.
    """

    def apply(self, op, advance_id, *, idempotency_key, args, bound_settlement_id):
        """Apply one local command. Domain refusal raises CreditError."""

    def view(self, advance_id):
        """Return the current credit case view."""

    def export_journal(self):
        """Return a copy of the accepted journal."""

    def state_digest(self) -> str:
        """Digest of the canonical book. Not a bank balance."""

    def canonical_state(self) -> str:
        """Canonical JSON of cases and journal."""

    def restored(self, journal):
        """Return a new port restored from `journal`. Do not mutate self."""

    def reset(self) -> None:
        """Replace the live book with an empty one. Keep settlement fixtures."""

    def preview_draw(self, advance_id):
        """Draw on a disposable copy. Diagnostic idempotency key only."""


@runtime_checkable
class ObservationPort(Protocol):
    """Read-only synthetic fact fold. No recording or provider authentication."""

    def fold(self, facts, *, bindings) -> dict:
        """Return detached SIMULATED diagnostics without applying any effects.

        Facts and explicit fixture bindings are lists. Calls are independent;
        transmission metadata never determines event identity or evidence hashes.
        A replacement must pass tests/test_observation_port.py's factory gate.
        """


def run_authorizer_vectors(factory):
    """Shared AuthorizerPort vectors. `factory()` returns a fresh authorizer.

    Collects every failure and raises one AssertionError. Passing is a local
    check of the role-scoped loopback contract. It is not an identity or
    authentication claim: both stay NOT_BOUND.
    """
    import json
    from email.message import Message

    from capital.auth import ALL_PERMISSIONS, DEFAULT_ROLE, MATRIX, ROLES, Principal
    from capital.service import ApiError

    failures = []

    def check(condition, label):
        if not condition:
            failures.append(label)

    def headers(**pairs):
        message = Message()
        for name, values in pairs.items():
            for value in (values if isinstance(values, list) else [values]):
                message[name.replace('_', '-')] = value
        return message

    def code_of(call):
        try:
            call()
        except ApiError as exc:
            return exc.code
        except Exception as exc:  # a vector never trusts the adapter's own exception type
            return f'RAISED:{type(exc).__name__}'
        return None

    try:
        authorizer = factory()
    except Exception as exc:
        raise AssertionError(f'authorizer factory failed: {type(exc).__name__}')
    check(isinstance(authorizer, AuthorizerPort), 'implements AuthorizerPort')

    for role in ROLES:
        for permission in ALL_PERMISSIONS:
            allowed = authorizer.authorize(Principal(role), permission).allowed
            check(allowed is (permission in MATRIX[role]), f'matrix {role} {permission}')
    for role in ('root', 'ORGANIZER', '', None):
        check(not authorizer.authorize(Principal(role), 'state:read').allowed, f'unknown role denied {role!r}')
    for permission in ('state:write', '', None, 7, ['state:read']):
        check(not authorizer.authorize(Principal('organizer'), permission).allowed,
              f'unknown permission denied {permission!r}')

    check(authorizer.authenticate(headers()).role == DEFAULT_ROLE, 'default principal is organizer')
    tokens = {role: authorizer.bind_role(role) for role in ROLES}
    check(all(isinstance(token, str) and token for token in tokens.values()), 'bind_role returns a token')
    check(len(set(tokens.values())) == len(ROLES), 'one distinct token per role')
    for role in ROLES:
        check(authorizer.bind_role(role) == tokens[role], f'bind_role idempotent {role}')
        check(authorizer.token_for(role) == tokens[role], f'token_for {role}')
        check(authorizer.role_for_token(tokens[role]) == role, f'role_for_token {role}')
        check(authorizer.authenticate(headers(X_Capital_Token=tokens[role])).role == role, f'token resolves {role}')
        check(authorizer.authenticate(
            headers(X_Capital_Token=tokens[role], X_Capital_Role=role)).role == role, f'matching role header {role}')
    check(authorizer.role_for_token('not-a-token') is None, 'unknown token has no role')
    check(authorizer.role_for_token(None) is None, 'non-string token has no role')

    check(code_of(lambda: authorizer.authenticate(
        headers(X_Capital_Token=tokens['auditor'], X_Capital_Role='observer'))) == 'ROLE_MISMATCH', 'ROLE_MISMATCH')
    check(code_of(lambda: authorizer.authenticate(headers(X_Capital_Role='auditor'))) == 'SESSION_REQUIRED',
          'SESSION_REQUIRED')
    check(code_of(lambda: authorizer.authenticate(headers(X_Capital_Role='root'))) == 'ROLE_UNKNOWN',
          'unknown role header')
    check(code_of(lambda: authorizer.authenticate(headers(X_Capital_Role=['organizer', 'organizer']))) == 'ROLE_UNKNOWN',
          'duplicate role header')
    check(code_of(lambda: authorizer.authenticate(headers(X_Capital_Token='nope'))) == 'LOCAL_TOKEN_REQUIRED',
          'unknown token')
    check(code_of(lambda: authorizer.authenticate(
        headers(X_Capital_Token=[tokens['organizer'], tokens['organizer']]))) == 'LOCAL_TOKEN_REQUIRED',
          'duplicate token')
    check(code_of(lambda: authorizer.bind_role('root')) == 'ROLE_UNKNOWN', 'bind_role unknown role')

    for role in ROLES:
        try:
            view = authorizer.describe(Principal(role))
            text = json.dumps(view)
        except Exception as exc:
            failures.append(f'describe {role} raised {type(exc).__name__}')
            continue
        check(view.get('port') == 'AuthorizerPort', 'describe port')
        check(view.get('identity') == 'NOT_BOUND' and view.get('authentication') == 'NOT_BOUND',
              'describe keeps identity and authentication NOT_BOUND')
        check(view.get('role') == role and view.get('roles') == list(ROLES), f'describe roles {role}')
        check(view.get('mode') in ('LOCAL_SYNTHETIC_ROLES', 'LOCAL_FAKE_IDP'), 'describe mode in closed set')
        check(set(view.get('permissions', {})) == set(ALL_PERMISSIONS), f'describe permissions {role}')
        check(all(token not in text for token in tokens.values()), 'describe carries no token')

    if failures:
        raise AssertionError('authorizer vectors failed: ' + '; '.join(failures))
