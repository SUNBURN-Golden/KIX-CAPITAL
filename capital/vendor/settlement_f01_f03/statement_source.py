"""Internal synthetic statement interface; no provider or wire semantics."""

from typing import Protocol, TypedDict


class StatementRecord(TypedDict):
    """Existing FSM fields. Component validation belongs to the FSM alone."""

    settlement_id: str
    movement_id: str
    gross: object
    amount: object
    fee: object
    tax: object
    held: object
    adjustment: object
    adjustment_reason: object


class StatementSource(Protocol):
    def fetch(self, settlement_id: str, movement_id: str) -> dict | None:
        """Return one synthetic record or absence; never infer a transition."""
        ...


class StatementSourceError(Exception):
    """Local source failure; no funds, finality or statement-absence meaning."""


class StatementNotFound(StatementSourceError):
    """The explicitly requested synthetic recording is absent."""


class InvalidStatementRecord(StatementSourceError):
    """A source record is not a document with exactly the required fields."""


class StatementIdentityMismatch(StatementSourceError):
    """A source returned a record for another settlement or movement."""
