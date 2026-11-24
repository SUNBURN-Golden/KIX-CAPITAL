"""One fresh, synthetic, in-memory credit desk; no restoration or execution."""

from __future__ import annotations

from credit_fsm import CreditMachine


class CreditSession:
    """Forward explicit caller inputs to an unchanged CreditMachine.

    Optional None sources have exactly the machine's existing meaning. This
    wrapper supplies no policy values, source facts, approvals or automation.
    """

    def __init__(self, settlement_source: object | None = None, ownership_source: object | None = None) -> None:
        self._machine = CreditMachine(settlement_source, ownership_source)

    def offer(
        self,
        advance_id: object,
        *,
        idempotency_key: object,
        face: object,
        amount: object,
        beneficiary_role: object,
        product: object = None,
    ) -> dict:
        return self._machine.offer(
            advance_id,
            idempotency_key=idempotency_key,
            face=face,
            amount=amount,
            beneficiary_role=beneficiary_role,
            product=product,
        )

    def approve(self, advance_id: object, *, idempotency_key: object) -> dict:
        return self._machine.approve(advance_id, idempotency_key=idempotency_key)

    def reject(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        return self._machine.reject(advance_id, idempotency_key=idempotency_key, reason=reason)

    def cancel(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        return self._machine.cancel(advance_id, idempotency_key=idempotency_key, reason=reason)

    def bind_settlement(
        self,
        advance_id: object,
        *,
        idempotency_key: object,
        settlement_id: object,
    ) -> dict:
        return self._machine.bind_settlement(
            advance_id, idempotency_key=idempotency_key, settlement_id=settlement_id)

    def draw(self, advance_id: object, *, idempotency_key: object, draw_id: object) -> dict:
        return self._machine.draw(advance_id, idempotency_key=idempotency_key, draw_id=draw_id)

    def repay(
        self,
        advance_id: object,
        *,
        idempotency_key: object,
        repay_id: object,
        sequence: object,
        amount: object,
    ) -> dict:
        return self._machine.repay(
            advance_id,
            idempotency_key=idempotency_key,
            repay_id=repay_id,
            sequence=sequence,
            amount=amount,
        )

    def close(self, advance_id: object, *, idempotency_key: object) -> dict:
        return self._machine.close(advance_id, idempotency_key=idempotency_key)

    def default(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        return self._machine.default(advance_id, idempotency_key=idempotency_key, reason=reason)

    def reconcile(self, advance_id: object, *, idempotency_key: object) -> dict:
        return self._machine.reconcile(advance_id, idempotency_key=idempotency_key)

    def view(self, advance_id: object) -> dict:
        return self._machine.view(advance_id)

    def view_claim(self, claim_id: object) -> dict:
        return self._machine.view_claim(claim_id)
