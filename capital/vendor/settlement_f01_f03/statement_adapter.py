"""Explicit caller-selected dispatch to the existing local settlement FSM."""

from typing import Literal

from settlement_fsm import SettlementMachine
from statement_source import (
    InvalidStatementRecord,
    StatementIdentityMismatch,
    StatementNotFound,
    StatementRecord,
    StatementSource,
)


class StatementAdapter:
    def __init__(self, machine: SettlementMachine, source: StatementSource) -> None:
        self._machine = machine
        self._source = source

    def apply(
        self, *, operation: Literal["commit", "observe_statement"],
        settlement_id: str, movement_id: str, idempotency_key: str,
    ) -> dict:
        if operation not in ("commit", "observe_statement"):
            raise ValueError("operation must be commit or observe_statement")
        record = self._source.fetch(settlement_id, movement_id)
        if record is None:
            raise StatementNotFound((settlement_id, movement_id))
        if type(record) is not dict or set(record) != StatementRecord.__required_keys__:
            raise InvalidStatementRecord("statement must contain exactly the existing FSM fields")
        if (type(record["settlement_id"]) is not str
                or type(record["movement_id"]) is not str
                or record["settlement_id"] != settlement_id
                or record["movement_id"] != movement_id):
            raise StatementIdentityMismatch((settlement_id, movement_id))
        body = {key: value for key, value in record.items() if key != "settlement_id"}
        return getattr(self._machine, operation)(
            settlement_id, idempotency_key=idempotency_key, **body,
        )
