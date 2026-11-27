"""Fetch one synthetic fact and forward to the unchanged local settlement FSM."""

from cancel_acceptance_source import (
    CancelAcceptanceIdentityMismatch,
    CancelAcceptanceNotFound,
    CancelAcceptanceRecord,
    CancelAcceptanceSource,
    InvalidCancelAcceptanceRecord,
)
from settlement_fsm import SettlementMachine


class CancelAcceptanceAdapter:
    def __init__(self, machine: SettlementMachine, source: CancelAcceptanceSource) -> None:
        self._machine = machine
        self._source = source

    def apply(self, *, settlement_id: str, source_id: str, idempotency_key: str) -> dict:
        record = self._source.fetch(settlement_id, source_id)
        if record is None:
            raise CancelAcceptanceNotFound((settlement_id, source_id))
        if type(record) is not dict or set(record) != CancelAcceptanceRecord.__required_keys__:
            raise InvalidCancelAcceptanceRecord("acceptance must contain exactly the existing FSM fields")
        if (type(record["settlement_id"]) is not str
                or type(record["source_id"]) is not str
                or record["settlement_id"] != settlement_id
                or record["source_id"] != source_id):
            raise CancelAcceptanceIdentityMismatch((settlement_id, source_id))
        return self._machine.observe_mock_cancel_acceptance(
            settlement_id, idempotency_key=idempotency_key,
            source_id=source_id, amount=record["amount"],
        )
