"""Internal synthetic acceptance interface; no provider or wire semantics."""

from typing import Protocol, TypedDict


class CancelAcceptanceRecord(TypedDict):
    """Exactly the existing FSM inputs; economic validation stays in the FSM."""

    settlement_id: str
    source_id: str
    amount: object


class CancelAcceptanceSource(Protocol):
    def fetch(self, settlement_id: str, source_id: str) -> dict | None:
        """Return one synthetic record or absence; never initiate cancellation."""
        ...


class CancelAcceptanceSourceError(Exception):
    """Local failure; no cancellation-absence or refund-completion meaning."""


class CancelAcceptanceNotFound(CancelAcceptanceSourceError):
    """The caller-selected synthetic recording is absent."""


class InvalidCancelAcceptanceRecord(CancelAcceptanceSourceError):
    """A record is not a document with exactly the required fields."""


class CancelAcceptanceIdentityMismatch(CancelAcceptanceSourceError):
    """A source returned non-string or mismatched identities."""
