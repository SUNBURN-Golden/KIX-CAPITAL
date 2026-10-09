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
from capital.terms import TermsPolicyPort


@runtime_checkable
class StoragePort(Protocol):
    """Load and save one local workspace envelope. Not a database."""

    def load(self):
        """Return a verified envelope, or None when nothing has been saved."""

    def save(self, document):
        """Persist the payload. The local file adapter checksums and renames."""

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

    `PinnedFsmProducer` is the local implementation. A later producer adapter
    replaces that wrapper and must pass `tests/test_producer_port.py`. Passing
    those vectors is not SEMANTIC_CONFORMANCE. CAP-16 stays NOT_BOUND for the
    exact Protocol/Commerce producer tuple.
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
