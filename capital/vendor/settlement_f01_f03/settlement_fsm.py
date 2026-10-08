"""In-memory acceptance machine for the F01–F03 settlement mock.

The machine decides which lifecycle commands are accepted and replays
that journal deterministically. Arithmetic stays in mock_settlement.py.
Nothing here calls a bank, a payment provider, the network, or the disk.

Provenance remains MOCK_SETTLEMENT_ONLY. A matched replay is equality of
this process's journal and views, not bank exactly-once or chain finality.
"""

from __future__ import annotations

import hashlib
import json

from mock_settlement import (
    PROVENANCE,
    MockSettlement,
    SettlementError,
    _canonical,
    _ident,
    _money,
    _policy,
    _require,
)

INITIATED = "INITIATED"
AUTHORIZED = "AUTHORIZED"
CAPTURED = "CAPTURED"
COMMITTED = "COMMITTED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

TERMINAL_PHASES = frozenset({FAILED, CANCELLED})
OPEN_CLAIM_PHASES = frozenset({CAPTURED, COMMITTED})
PRE_CAPTURE_PHASES = frozenset({INITIATED, AUTHORIZED})
REFUND_PHASES = frozenset({CAPTURED, COMMITTED})

REPLAYABLE = frozenset(
    {
        "initiate",
        "authorize",
        "capture",
        "commit",
        "fail",
        "cancel",
        "observe_statement",
        "distribute",
        "bind_refund",
        "observe_mock_cancel_acceptance",
    }
)

_JOURNAL_KEYS = frozenset({"op", "idempotency_key", "settlement_id", "body"})
_UNSTORED_REJECTION = frozenset({"MOCK_INVARIANT", "IDEMPOTENCY_CONFLICT", "INVALID_JOURNAL"})


def _copy(value: object) -> object:
    return json.loads(_canonical(value))


def _statement_body(
    movement_id: object,
    gross: object,
    amount: object,
    fee: object,
    tax: object,
    held: object,
    adjustment: object,
    adjustment_reason: object,
) -> dict:
    movement_id = _ident(movement_id)
    gross = _money(gross, positive=True)
    amount = _money(amount, positive=False)
    fee = _money(fee, positive=False)
    tax = _money(tax, positive=False)
    held = _money(held, positive=False)
    adjustment = _money(adjustment, positive=False)
    if adjustment:
        _require(
            type(adjustment_reason) is str
            and 0 < len(adjustment_reason) <= 100
            and adjustment_reason.strip() == adjustment_reason,
            "ADJUSTMENT_REASON_REQUIRED",
        )
        reason = adjustment_reason
    else:
        _require(adjustment_reason is None, "ADJUSTMENT_REASON_UNEXPECTED")
        reason = None
    _require(amount + fee + tax + held + adjustment == gross, "SETTLEMENT_COMPONENT_MISMATCH")
    return {
        "movement_id": movement_id,
        "gross": gross,
        "amount": amount,
        "fee": fee,
        "tax": tax,
        "held": held,
        "adjustment": adjustment,
        "adjustment_reason": reason,
    }


class SettlementMachine:
    def __init__(self) -> None:
        self._book = MockSettlement()
        self._cases: dict[str, dict] = {}
        self._journal: list[dict] = []
        self._idempotency: dict[str, dict] = {}

    def initiate(
        self,
        settlement_id: object,
        *,
        idempotency_key: object,
        trade_id: object,
        gross: object,
        debtor_role: object,
        policy: object,
        currency: object = "KRW",
    ) -> dict:
        raw = {
            "trade_id": trade_id,
            "gross": gross,
            "debtor_role": debtor_role,
            "policy": policy,
            "currency": currency,
        }

        def execute(key: str, request: str) -> dict:
            normalized_id = _ident(settlement_id)
            _require(currency == "KRW", "CURRENCY_UNSUPPORTED")
            body = {
                "trade_id": _ident(trade_id),
                "gross": _money(gross, positive=True),
                "debtor_role": _ident(debtor_role),
                "policy": _policy(policy),
                "currency": "KRW",
            }
            current = self._cases.get(normalized_id)
            if current is not None:
                if current["phase"] in TERMINAL_PHASES:
                    raise SettlementError("TERMINAL_IMMUTABLE")
                raise SettlementError("ILLEGAL_TRANSITION")
            case = {
                "settlement_id": normalized_id,
                "phase": INITIATED,
                "trade_id": body["trade_id"],
                "gross": body["gross"],
                "currency": "KRW",
                "debtor_role": body["debtor_role"],
                "policy": body["policy"],
                "mock_authorized": False,
                "failure_reason": None,
                "cancel_reason": None,
                "commit_movement_id": None,
            }
            self._cases[normalized_id] = case
            self._phase_book_invariant(case)
            return self._accept(key, request, "initiate", case, body, effect=None)

        return self._call("initiate", settlement_id, idempotency_key, raw, execute)

    def authorize(self, settlement_id: object, *, idempotency_key: object) -> dict:
        return self._transition(
            "authorize",
            settlement_id,
            idempotency_key,
            {},
            {},
            allowed=frozenset({INITIATED}),
            apply=self._mark_authorized,
            next_phase=AUTHORIZED,
        )

    def capture(self, settlement_id: object, *, idempotency_key: object) -> dict:
        def apply(case: dict) -> None:
            result = self._book.recognize_claim(
                case["settlement_id"],
                trade_id=case["trade_id"],
                gross=case["gross"],
                debtor_role=case["debtor_role"],
                policy=case["policy"],
                currency=case["currency"],
            )
            _require(result["duplicate"] is False, "MOCK_INVARIANT")

        return self._transition(
            "capture",
            settlement_id,
            idempotency_key,
            {},
            {},
            allowed=frozenset({AUTHORIZED}),
            apply=apply,
            next_phase=CAPTURED,
        )

    def commit(
        self,
        settlement_id: object,
        *,
        idempotency_key: object,
        movement_id: object,
        gross: object,
        amount: object,
        fee: object,
        tax: object,
        held: object,
        adjustment: object,
        adjustment_reason: object = None,
    ) -> dict:
        raw = {
            "movement_id": movement_id,
            "gross": gross,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "held": held,
            "adjustment": adjustment,
            "adjustment_reason": adjustment_reason,
        }

        def execute(key: str, request: str) -> dict:
            body = _statement_body(
                movement_id, gross, amount, fee, tax, held, adjustment, adjustment_reason
            )

            def apply(case: dict) -> None:
                result = self._book.observe_settlement_statement(case["settlement_id"], **body)
                _require(result["duplicate"] is False, "MOCK_INVARIANT")
                case["commit_movement_id"] = body["movement_id"]

            return self._apply(
                key,
                request,
                "commit",
                settlement_id,
                body,
                allowed=frozenset({CAPTURED}),
                apply=apply,
                next_phase=COMMITTED,
            )

        return self._call("commit", settlement_id, idempotency_key, raw, execute)

    def fail(self, settlement_id: object, *, idempotency_key: object, reason: object) -> dict:
        raw = {"reason": reason}

        def execute(key: str, request: str) -> dict:
            body = {"reason": _ident(reason)}

            def apply(case: dict) -> None:
                case["failure_reason"] = body["reason"]

            return self._apply(
                key,
                request,
                "fail",
                settlement_id,
                body,
                allowed=PRE_CAPTURE_PHASES,
                apply=apply,
                next_phase=FAILED,
            )

        return self._call("fail", settlement_id, idempotency_key, raw, execute)

    def cancel(self, settlement_id: object, *, idempotency_key: object, reason: object) -> dict:
        raw = {"reason": reason}

        def execute(key: str, request: str) -> dict:
            body = {"reason": _ident(reason)}

            def apply(case: dict) -> None:
                case["cancel_reason"] = body["reason"]

            return self._apply(
                key,
                request,
                "cancel",
                settlement_id,
                body,
                allowed=PRE_CAPTURE_PHASES,
                apply=apply,
                next_phase=CANCELLED,
            )

        return self._call("cancel", settlement_id, idempotency_key, raw, execute)

    def observe_statement(
        self,
        settlement_id: object,
        *,
        idempotency_key: object,
        movement_id: object,
        gross: object,
        amount: object,
        fee: object,
        tax: object,
        held: object,
        adjustment: object,
        adjustment_reason: object = None,
    ) -> dict:
        raw = {
            "movement_id": movement_id,
            "gross": gross,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "held": held,
            "adjustment": adjustment,
            "adjustment_reason": adjustment_reason,
        }

        def execute(key: str, request: str) -> dict:
            body = _statement_body(
                movement_id, gross, amount, fee, tax, held, adjustment, adjustment_reason
            )

            def apply(case: dict) -> None:
                self._book.observe_settlement_statement(case["settlement_id"], **body)

            return self._apply(
                key,
                request,
                "observe_statement",
                settlement_id,
                body,
                allowed=frozenset({COMMITTED}),
                apply=apply,
                next_phase=None,
            )

        return self._call("observe_statement", settlement_id, idempotency_key, raw, execute)

    def distribute(self, settlement_id: object, *, idempotency_key: object, order: object) -> dict:
        # A non-list is not a formed command. Reject it before the key is bound
        # so a later list with the same key can still be accepted.
        _require(type(order) is list, "DISTRIBUTION_ORDER_TYPE")
        raw = {"order": order}
        applied: dict[str, int] = {}

        def execute(key: str, request: str) -> dict:
            _require(type(order) is list, "DISTRIBUTION_ORDER_TYPE")
            body = {"order": [_ident(payee) for payee in order]}

            def apply(case: dict) -> None:
                result = self._book.apply_distribution(case["settlement_id"], order=list(body["order"]))
                applied.clear()
                applied.update(result["applied"])

            return self._apply(
                key,
                request,
                "distribute",
                settlement_id,
                body,
                allowed=frozenset({COMMITTED}),
                apply=apply,
                next_phase=None,
                effect_box=applied,
            )

        return self._call("distribute", settlement_id, idempotency_key, raw, execute)

    def bind_refund(
        self,
        settlement_id: object,
        *,
        idempotency_key: object,
        refund_id: object,
        amount: object,
        beneficiary_role: object,
        reason: object,
    ) -> dict:
        raw = {
            "refund_id": refund_id,
            "amount": amount,
            "beneficiary_role": beneficiary_role,
            "reason": reason,
        }

        def execute(key: str, request: str) -> dict:
            body = {
                "refund_id": _ident(refund_id),
                "amount": _money(amount, positive=True),
                "beneficiary_role": _ident(beneficiary_role),
                "reason": _ident(reason),
            }

            def apply(case: dict) -> None:
                self._book.bind_refund(case["settlement_id"], **body)

            return self._apply(
                key,
                request,
                "bind_refund",
                settlement_id,
                body,
                allowed=REFUND_PHASES,
                apply=apply,
                next_phase=None,
            )

        return self._call("bind_refund", settlement_id, idempotency_key, raw, execute)

    def observe_mock_cancel_acceptance(
        self,
        settlement_id: object,
        *,
        idempotency_key: object,
        source_id: object,
        amount: object,
    ) -> dict:
        raw = {"source_id": source_id, "amount": amount}

        def execute(key: str, request: str) -> dict:
            body = {"source_id": _ident(source_id), "amount": _money(amount, positive=True)}

            def apply(case: dict) -> None:
                self._book.observe_mock_cancel_acceptance(case["settlement_id"], **body)

            return self._apply(
                key,
                request,
                "observe_mock_cancel_acceptance",
                settlement_id,
                body,
                allowed=REFUND_PHASES,
                apply=apply,
                next_phase=None,
            )

        return self._call("observe_mock_cancel_acceptance", settlement_id, idempotency_key, raw, execute)

    def reject_external(self, kind: object) -> None:
        """Refuse a live bank or payment-provider attempt.

        The kind is an external-attempt label. This method never dispatches
        initiate, capture, commit, or any other accepted command.
        """

        _ident(kind)
        raise SettlementError("EXTERNAL_PAYMENT_UNSUPPORTED")

    def reconcile(self, settlement_id: object, *, idempotency_key: object) -> dict:
        """Replay the economic journal and require the views to match.

        The receipt is process-local. Crash recovery uses export_journal and
        restore; those rebuild economic commands and do not store this receipt.
        """

        def execute(key: str, request: str) -> dict:
            normalized_id = _ident(settlement_id)
            case = self._cases.get(normalized_id)
            _require(case is not None, "UNKNOWN_SETTLEMENT")
            restored = SettlementMachine.restore(self.export_journal())
            _require(restored.canonical_state() == self.canonical_state(), "MOCK_INVARIANT")
            result = {
                "duplicate": False,
                "applied": "reconcile",
                "effect": None,
                "matched": True,
                "state_digest": self.state_digest(),
                "entry_count": len(self._journal),
                "provenance": PROVENANCE,
                "external_payment": "UNSUPPORTED",
                "funds_executed": False,
                "settlement": self._view(case),
            }
            self._idempotency[key] = {"request": request, "result": _canonical(result), "error": None}
            return _copy(result)

        return self._call("reconcile", settlement_id, idempotency_key, {}, execute)

    def view(self, settlement_id: object) -> dict:
        settlement_id = _ident(settlement_id)
        case = self._cases.get(settlement_id)
        _require(case is not None, "UNKNOWN_SETTLEMENT")
        return self._view(case)

    def export_journal(self) -> list:
        return _copy(self._journal)

    def canonical_state(self) -> str:
        payload = {
            "cases": [self._view(self._cases[sid]) for sid in sorted(self._cases)],
            "journal": self._journal,
        }
        return _canonical(payload)

    def state_digest(self) -> str:
        return hashlib.sha256(self.canonical_state().encode("utf-8")).hexdigest()

    @classmethod
    def restore(cls, journal: object) -> SettlementMachine:
        _require(type(journal) is list, "INVALID_JOURNAL")
        machine = cls()
        for entry in journal:
            _require(type(entry) is dict and set(entry) == _JOURNAL_KEYS, "INVALID_JOURNAL")
            op = entry["op"]
            _require(type(op) is str and op in REPLAYABLE, "INVALID_JOURNAL")
            body = entry["body"]
            _require(type(body) is dict, "INVALID_JOURNAL")
            method = getattr(machine, op)
            try:
                method(entry["settlement_id"], idempotency_key=entry["idempotency_key"], **body)
            except TypeError as error:
                raise SettlementError("INVALID_JOURNAL") from error
        return machine

    def _transition(
        self,
        op: str,
        settlement_id: object,
        idempotency_key: object,
        raw: dict,
        normalized: dict,
        *,
        allowed: frozenset,
        apply,
        next_phase: str | None,
        effect_box: dict | None = None,
    ) -> dict:
        def execute(key: str, request: str) -> dict:
            return self._apply(
                key,
                request,
                op,
                settlement_id,
                normalized,
                allowed=allowed,
                apply=apply,
                next_phase=next_phase,
                effect_box=effect_box,
            )

        return self._call(op, settlement_id, idempotency_key, raw, execute)

    def _apply(
        self,
        key: str,
        request: str,
        op: str,
        settlement_id: object,
        body: dict,
        *,
        allowed: frozenset,
        apply,
        next_phase: str | None,
        effect_box: dict | None = None,
    ) -> dict:
        normalized_id = _ident(settlement_id)
        case = self._cases.get(normalized_id)
        _require(case is not None, "UNKNOWN_SETTLEMENT")
        if case["phase"] in TERMINAL_PHASES:
            raise SettlementError("TERMINAL_IMMUTABLE")
        _require(case["phase"] in allowed, "ILLEGAL_TRANSITION")
        apply(case)
        if next_phase is not None:
            case["phase"] = next_phase
        self._phase_book_invariant(case)
        effect = None if effect_box is None else _copy(effect_box)
        return self._accept(key, request, op, case, body, effect=effect)

    def _call(self, op: str, settlement_id: object, idempotency_key: object, raw: dict, execute) -> dict:
        key = _ident(idempotency_key)
        request = self._fingerprint(op, settlement_id, raw)
        if request is not None:
            replayed = self._replay_if_known(key, request)
            if replayed is not None:
                return replayed
        try:
            return execute(key, request)
        except SettlementError as error:
            if (
                request is not None
                and error.code not in _UNSTORED_REJECTION
                and key not in self._idempotency
            ):
                self._idempotency[key] = {"request": request, "result": None, "error": error.code}
            raise

    def _mark_authorized(self, case: dict) -> None:
        case["mock_authorized"] = True

    def _fingerprint(self, op: str, settlement_id: object, body: dict) -> str | None:
        try:
            return _canonical({"body": body, "op": op, "settlement_id": settlement_id})
        except (TypeError, ValueError):
            return None

    def _replay_if_known(self, key: str, request: str) -> dict | None:
        prior = self._idempotency.get(key)
        if prior is None:
            return None
        _require(prior["request"] == request, "IDEMPOTENCY_CONFLICT")
        if prior["error"] is not None:
            raise SettlementError(prior["error"])
        result = json.loads(prior["result"])
        result["duplicate"] = True
        result["applied"] = None
        return result

    def _accept(
        self,
        key: str,
        request: str,
        op: str,
        case: dict,
        body: dict,
        *,
        effect: object,
    ) -> dict:
        self._journal.append(
            {
                "op": op,
                "idempotency_key": key,
                "settlement_id": case["settlement_id"],
                "body": _copy(body),
            }
        )
        result = {
            "duplicate": False,
            "applied": op,
            "effect": effect,
            "provenance": PROVENANCE,
            "external_payment": "UNSUPPORTED",
            "funds_executed": False,
            "settlement": self._view(case),
        }
        self._idempotency[key] = {"request": request, "result": _canonical(result), "error": None}
        return _copy(result)

    def _view(self, case: dict) -> dict:
        phase = case["phase"]
        claim = self._book.view(case["settlement_id"]) if phase in OPEN_CLAIM_PHASES else None
        return {
            "provenance": PROVENANCE,
            "lifecycle_authority": "IN_MEMORY_FSM",
            "settlement_id": case["settlement_id"],
            "phase": phase,
            "terminal": phase in TERMINAL_PHASES,
            "trade_id": case["trade_id"],
            "currency": case["currency"],
            "gross": case["gross"],
            "debtor_role": case["debtor_role"],
            "policy": dict(case["policy"]),
            "mock_authorized": case["mock_authorized"],
            "provider_authorization_executed": False,
            "commit_movement_id": case["commit_movement_id"],
            "failure_reason": case["failure_reason"],
            "cancel_reason": case["cancel_reason"],
            "external_payment": "UNSUPPORTED",
            "legal_debtor_bound": False,
            "admission_granted": False,
            "right_cancelled": False,
            "bank_debit_observed": False,
            "external_return_closed": False,
            "funds_executed": False,
            "durable": False,
            "accepted_entries": sum(
                1 for entry in self._journal if entry["settlement_id"] == case["settlement_id"]
            ),
            "claim": claim,
        }

    def _claim_open(self, settlement_id: str) -> bool:
        try:
            self._book.view(settlement_id)
        except SettlementError as error:
            if error.code == "UNKNOWN_CLAIM":
                return False
            raise
        return True

    def _phase_book_invariant(self, case: dict) -> None:
        open_claim = self._claim_open(case["settlement_id"])
        if case["phase"] in OPEN_CLAIM_PHASES:
            _require(open_claim, "MOCK_INVARIANT")
        else:
            _require(not open_claim, "MOCK_INVARIANT")
