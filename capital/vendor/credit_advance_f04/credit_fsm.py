"""In-memory acceptance machine for the F04 credit-advance mock.

The machine decides which offer, draw, and repayment commands are accepted
and replays that journal deterministically. Open-face reservation stays in
mock_credit.py. Draw and repay here are mock exposure-ledger transitions.
They do not call attempt_execution and they do not move bank funds.

A bound draw reads an injected settlement machine's view before it changes
outstanding exposure. It does not call settlement commands. An optional
ownership source is read only through canonical_state, so this machine does
not transfer a ticket. economic_finality_claimed, funds_executed, and
bank_debit_observed stay false.

Provenance remains MOCK_CREDIT_F04_ONLY. A matched replay is equality of
this process's journal and views, not a loan, a bank debit, or chain
finality. Limit races here are ordered commands in one process.
"""

from __future__ import annotations

import hashlib
import json

from mock_credit import (
    FACE_PROVENANCE,
    MONEY_MAX,
    PROVENANCE,
    CreditMockError,
    MockCredit,
    _canonical,
    _flags,
    _ident,
    _money,
    _parse_face,
    open_terms,
)

AUTHORITY = "IN_MEMORY_FSM"

OFFERED = "OFFERED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
DRAWN = "DRAWN"
CLOSED = "CLOSED"
DEFAULTED = "DEFAULTED"
CANCELLED = "CANCELLED"

TERMINAL_PHASES = frozenset({REJECTED, CLOSED, DEFAULTED, CANCELLED})
EXPOSURE_PHASES = frozenset({DRAWN, CLOSED, DEFAULTED})

REPLAYABLE = frozenset(
    {
        "offer",
        "approve",
        "reject",
        "cancel",
        "bind_settlement",
        "draw",
        "repay",
        "close",
        "default",
    }
)

_JOURNAL_KEYS = frozenset({"op", "idempotency_key", "advance_id", "body"})
_UNSTORED_REJECTION = frozenset({"MOCK_INVARIANT", "IDEMPOTENCY_CONFLICT", "INVALID_JOURNAL"})
_REAL_FUNDS = frozenset({"DISBURSE", "REPAY", "DEBIT", "DISBURSE_TO_BANK"})
_UNDEFINED_PRODUCT = frozenset(
    {
        "ACCRUE",
        "LICENSE",
        "FORECLOSE",
        "PRIORITY",
        "PERFECT",
        "INTEREST",
        "FEE",
        "KYC",
        "AML",
        "KYC_AML",
        "RISK_SCORE",
        "UNDERWRITE",
    }
)
_REQUIRED_SETTLEMENT_FLAGS = (
    "funds_executed",
    "bank_debit_observed",
    "legal_debtor_bound",
    "admission_granted",
    "durable",
)
_OPTIONAL_FALSE_FLAGS = (
    "external_return_closed",
    "right_cancelled",
    "license_granted",
    "regulated_product",
    "collateral_perfected",
    "priority_bound",
    "disposal_controlled",
    "revenue_assigned",
    "repayment_observed",
    "interest_defined",
)

_ALLOWED = {
    "approve": frozenset({OFFERED}),
    "reject": frozenset({OFFERED}),
    "cancel": frozenset({OFFERED, APPROVED}),
    "bind_settlement": frozenset({OFFERED, APPROVED}),
    "draw": frozenset({APPROVED}),
    "repay": frozenset({DRAWN}),
    "close": frozenset({DRAWN}),
    "default": frozenset({DRAWN}),
}


class CreditError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise CreditError(code)


def _mock(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CreditMockError as error:
        raise CreditError(error.code) from error


def _copy(value: object) -> object:
    return json.loads(_mock(_canonical, value))


def _source(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CreditError:
        raise
    except Exception as error:
        code = getattr(error, "code", None)
        if type(code) is str and code:
            raise CreditError(code) from error
        raise


def _sequence(value: object) -> int:
    _require(type(value) is int and value >= 1, "REPAYMENT_ORDER")
    return value


class CreditMachine:
    def __init__(self, settlement_source: object | None = None, ownership_source: object | None = None) -> None:
        self._credit = MockCredit()
        self._settlement = settlement_source
        self._ownership = ownership_source
        self._cases: dict[str, dict] = {}
        self._journal: list[dict] = []
        self._idempotency: dict[str, dict] = {}

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
        raw = {
            "face": face,
            "amount": amount,
            "beneficiary_role": beneficiary_role,
            "product": product,
        }

        def execute(key: str, request: str) -> dict:
            if product is not None:
                raise CreditError("CREDIT_PRODUCT_UNDEFINED")
            normalized_id = _mock(_ident, advance_id)
            beneficiary = _mock(_ident, beneficiary_role)
            normalized_amount = _mock(_money, amount)
            parsed = _mock(_parse_face, face)
            if parsed["refund_face"] and not parsed["fixture_reclassified"]:
                raise CreditError("REFUND_OBLIGATION_OPEN")
            frozen_face = _copy(face)
            binding = _mock(
                _canonical,
                {
                    "advance_id": normalized_id,
                    "amount": normalized_amount,
                    "beneficiary_role": beneficiary,
                    "face": parsed["canon"],
                },
            )
            current = self._cases.get(normalized_id)
            if current is not None:
                _require(current["binding"] == binding, "ADVANCE_BINDING_CONFLICT")
                raise CreditError("ILLEGAL_TRANSITION")
            case = {
                "binding": binding,
                "advance_id": normalized_id,
                "claim_id": parsed["claim_id"],
                "trade_id": parsed["trade_id"],
                "gross": parsed["gross"],
                "open_face": parsed["open_face"],
                "confirmed_cash": parsed["confirmed_cash"],
                "recovery_due": parsed["recovery_due"],
                "face": frozen_face,
                "amount": normalized_amount,
                "beneficiary_role": beneficiary,
                "phase": OFFERED,
                "settlement_id": None,
                "mock_settlement_commit_observed": False,
                "draw_id": None,
                "outstanding": 0,
                "drawn": 0,
                "repaid": 0,
                "repay_notes": {},
                "repay_order": [],
                "reject_reason": None,
                "cancel_reason": None,
                "default_reason": None,
            }
            self._cases[normalized_id] = case
            self._invariant()
            return self._accept(
                key,
                request,
                "offer",
                case,
                {
                    "face": frozen_face,
                    "amount": normalized_amount,
                    "beneficiary_role": beneficiary,
                },
            )

        return self._call("offer", advance_id, idempotency_key, raw, execute)

    def approve(self, advance_id: object, *, idempotency_key: object) -> dict:
        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            self._enter(case, "approve")
            case["phase"] = APPROVED
            self._invariant()
            return self._accept(key, request, "approve", case, {})

        return self._call("approve", advance_id, idempotency_key, {}, execute)

    def reject(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        raw = {"reason": reason}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            body = {"reason": _mock(_ident, reason)}
            self._enter(case, "reject")
            case["reject_reason"] = body["reason"]
            case["phase"] = REJECTED
            self._invariant()
            return self._accept(key, request, "reject", case, body)

        return self._call("reject", advance_id, idempotency_key, raw, execute)

    def cancel(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        raw = {"reason": reason}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            body = {"reason": _mock(_ident, reason)}
            self._enter(case, "cancel")
            case["cancel_reason"] = body["reason"]
            case["phase"] = CANCELLED
            self._invariant()
            return self._accept(key, request, "cancel", case, body)

        return self._call("cancel", advance_id, idempotency_key, raw, execute)

    def bind_settlement(
        self,
        advance_id: object,
        *,
        idempotency_key: object,
        settlement_id: object,
    ) -> dict:
        raw = {"settlement_id": settlement_id}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            settlement_key = _mock(_ident, settlement_id)
            self._enter(case, "bind_settlement")
            if case["settlement_id"] is not None:
                _require(case["settlement_id"] == settlement_key, "SETTLEMENT_BINDING_CONFLICT")
                raise CreditError("ILLEGAL_TRANSITION")
            case["settlement_id"] = settlement_key
            self._invariant()
            return self._accept(key, request, "bind_settlement", case, {"settlement_id": settlement_key})

        return self._call("bind_settlement", advance_id, idempotency_key, raw, execute)

    def draw(self, advance_id: object, *, idempotency_key: object, draw_id: object) -> dict:
        raw = {"draw_id": draw_id}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            normalized_draw = _mock(_ident, draw_id)
            if case["draw_id"] is not None:
                if case["draw_id"] == normalized_draw:
                    return self._duplicate(key, request, case)
                if case["phase"] in TERMINAL_PHASES:
                    raise CreditError("TERMINAL_IMMUTABLE")
                raise CreditError("DUPLICATE_DRAW")
            self._enter(case, "draw")
            observed = self._settlement_commit_observed(case)
            noted = _mock(
                self._credit.note_advance,
                case["advance_id"],
                face=case["face"],
                amount=case["amount"],
                beneficiary_role=case["beneficiary_role"],
            )
            _require(noted["duplicate"] is False, "MOCK_INVARIANT")
            _require(noted["advance"]["funds_executed"] is False, "MOCK_INVARIANT")
            _require(noted["advance"]["repayment_observed"] is False, "MOCK_INVARIANT")
            case["draw_id"] = normalized_draw
            case["drawn"] = case["amount"]
            case["outstanding"] = case["amount"]
            case["mock_settlement_commit_observed"] = observed
            case["phase"] = DRAWN
            self._invariant()
            return self._accept(
                key,
                request,
                "draw",
                case,
                {"draw_id": normalized_draw},
                effect={
                    "draw_id": normalized_draw,
                    "outstanding_exposure": case["outstanding"],
                    "note_status": "NOTED",
                },
            )

        return self._call("draw", advance_id, idempotency_key, raw, execute)

    def repay(
        self,
        advance_id: object,
        *,
        idempotency_key: object,
        repay_id: object,
        sequence: object,
        amount: object,
    ) -> dict:
        raw = {"repay_id": repay_id, "sequence": sequence, "amount": amount}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            normalized_repay = _mock(_ident, repay_id)
            normalized_amount = _mock(_money, amount)
            normalized_sequence = _sequence(sequence)
            binding = _mock(
                _canonical,
                {
                    "advance_id": case["advance_id"],
                    "amount": normalized_amount,
                    "repay_id": normalized_repay,
                    "sequence": normalized_sequence,
                },
            )
            prior = case["repay_notes"].get(normalized_repay)
            if prior is not None:
                _require(prior == binding, "REPAY_BINDING_CONFLICT")
                return self._duplicate(key, request, case)
            if case["phase"] in TERMINAL_PHASES:
                raise CreditError("TERMINAL_IMMUTABLE")
            self._enter(case, "repay")
            expected = len(case["repay_order"]) + 1
            _require(normalized_sequence == expected, "REPAYMENT_ORDER")
            _require(normalized_amount <= case["outstanding"], "REPAYMENT_EXCEEDS_OUTSTANDING")
            case["repay_notes"][normalized_repay] = binding
            case["repay_order"].append(
                {
                    "repay_id": normalized_repay,
                    "sequence": normalized_sequence,
                    "amount": normalized_amount,
                }
            )
            case["repaid"] += normalized_amount
            case["outstanding"] -= normalized_amount
            self._invariant()
            return self._accept(
                key,
                request,
                "repay",
                case,
                {
                    "repay_id": normalized_repay,
                    "sequence": normalized_sequence,
                    "amount": normalized_amount,
                },
                effect={
                    "repay_id": normalized_repay,
                    "sequence": normalized_sequence,
                    "amount": normalized_amount,
                    "outstanding_exposure": case["outstanding"],
                },
            )

        return self._call("repay", advance_id, idempotency_key, raw, execute)

    def close(self, advance_id: object, *, idempotency_key: object) -> dict:
        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            self._enter(case, "close")
            _require(case["outstanding"] == 0, "OUTSTANDING_REMAINS")
            released = _mock(self._credit.release_note, case["advance_id"])
            _require(released["duplicate"] is False, "MOCK_INVARIANT")
            _require(released["advance"]["status"] == "RELEASED", "MOCK_INVARIANT")
            _require(released["advance"]["repayment_observed"] is False, "MOCK_INVARIANT")
            _require(released["advance"]["funds_executed"] is False, "MOCK_INVARIANT")
            case["phase"] = CLOSED
            self._invariant()
            return self._accept(
                key,
                request,
                "close",
                case,
                {},
                effect={"note_status": "RELEASED", "outstanding_exposure": 0},
            )

        return self._call("close", advance_id, idempotency_key, {}, execute)

    def default(self, advance_id: object, *, idempotency_key: object, reason: object) -> dict:
        raw = {"reason": reason}

        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            body = {"reason": _mock(_ident, reason)}
            self._enter(case, "default")
            _require(case["outstanding"] > 0, "DEFAULT_REQUIRES_EXPOSURE")
            case["default_reason"] = body["reason"]
            case["phase"] = DEFAULTED
            self._invariant()
            return self._accept(
                key,
                request,
                "default",
                case,
                body,
                effect={
                    "outstanding_exposure": case["outstanding"],
                    "note_status": "NOTED",
                },
            )

        return self._call("default", advance_id, idempotency_key, raw, execute)

    def reconcile(self, advance_id: object, *, idempotency_key: object) -> dict:
        def execute(key: str, request: str) -> dict:
            case = self._case(advance_id)
            restored = CreditMachine.restore(
                self.export_journal(),
                settlement_source=self._settlement,
                ownership_source=self._ownership,
            )
            _require(restored.canonical_state() == self.canonical_state(), "MOCK_INVARIANT")
            result = self._envelope(
                case,
                duplicate=False,
                applied="reconcile",
                effect=None,
                matched=True,
                entry_count=len(self._journal),
            )
            self._idempotency[key] = {"request": request, "result": _mock(_canonical, result), "error": None}
            return _copy(result)

        return self._call("reconcile", advance_id, idempotency_key, {}, execute)

    def reject_unsupported(self, kind: object) -> None:
        """Refuse an undefined credit product or a real-funds attempt.

        This does not dispatch offer, draw, repay, or any other accepted
        command. KYC, risk-score, interest, and foreclosure labels stop here.
        """

        before = self._witness()
        digest = self.canonical_state()
        try:
            _require(type(kind) is str, "EXECUTION_KIND")
            if kind in _REAL_FUNDS:
                raise CreditError("REAL_FUNDS_FORBIDDEN")
            if kind in _UNDEFINED_PRODUCT:
                raise CreditError("CREDIT_PRODUCT_UNDEFINED")
            raise CreditError("EXECUTION_KIND")
        finally:
            _require(self.canonical_state() == digest, "MOCK_INVARIANT")
            self._guard(before)

    def attempt_execution(self, advance_id: object, *, kind: object) -> None:
        """Wave 5 execution refusal. The inner note is not changed."""

        before = self._witness()
        digest = self.canonical_state()
        try:
            try:
                self._credit.attempt_execution(advance_id, kind=kind)
            except CreditMockError as error:
                code = error.code
            else:
                raise CreditError("MOCK_INVARIANT")
            raise CreditError(code)
        finally:
            _require(self.canonical_state() == digest, "MOCK_INVARIANT")
            self._guard(before)

    def view(self, advance_id: object) -> dict:
        before = self._witness()
        try:
            return self._view(self._case(advance_id))
        finally:
            self._guard(before)

    def view_claim(self, claim_id: object) -> dict:
        before = self._witness()
        try:
            normalized = _mock(_ident, claim_id)
            claim = self._mock_claim(normalized)
            _require(claim is not None, "UNKNOWN_CLAIM")
            return claim
        finally:
            self._guard(before)

    def export_journal(self) -> list:
        return _copy(self._journal)

    def canonical_state(self) -> str:
        payload = {
            "cases": [self._view(self._cases[advance_id]) for advance_id in sorted(self._cases)],
            "journal": self._journal,
        }
        return _mock(_canonical, payload)

    def state_digest(self) -> str:
        return hashlib.sha256(self.canonical_state().encode("utf-8")).hexdigest()

    @classmethod
    def restore(
        cls,
        journal: object,
        settlement_source: object | None = None,
        ownership_source: object | None = None,
    ) -> CreditMachine:
        _require(type(journal) is list, "INVALID_JOURNAL")
        machine = cls(settlement_source, ownership_source)
        for entry in journal:
            _require(type(entry) is dict and set(entry) == _JOURNAL_KEYS, "INVALID_JOURNAL")
            op = entry["op"]
            _require(type(op) is str and op in REPLAYABLE, "INVALID_JOURNAL")
            body = entry["body"]
            _require(type(body) is dict, "INVALID_JOURNAL")
            method = getattr(machine, op)
            try:
                method(entry["advance_id"], idempotency_key=entry["idempotency_key"], **body)
            except TypeError as error:
                raise CreditError("INVALID_JOURNAL") from error
        return machine

    def _case(self, advance_id: object) -> dict:
        normalized = _mock(_ident, advance_id)
        case = self._cases.get(normalized)
        _require(case is not None, "UNKNOWN_ADVANCE")
        return case

    def _enter(self, case: dict, op: str) -> None:
        phase = case["phase"]
        if phase in _ALLOWED[op]:
            return
        if phase in TERMINAL_PHASES:
            raise CreditError("TERMINAL_IMMUTABLE")
        raise CreditError("ILLEGAL_TRANSITION")

    def _settlement_commit_observed(self, case: dict) -> bool:
        if case["settlement_id"] is None:
            return False
        _require(self._settlement is not None, "SETTLEMENT_SOURCE_REQUIRED")
        view = _source(self._settlement.view, case["settlement_id"])
        _require(type(view) is dict, "SETTLEMENT_NOT_COMMITTED")
        _require(view.get("phase") == "COMMITTED", "SETTLEMENT_NOT_COMMITTED")
        _require(view.get("settlement_id") == case["claim_id"], "SETTLEMENT_BINDING_CONFLICT")
        gross = view.get("gross")
        _require(
            view.get("currency") == "KRW" and type(gross) is int and gross == case["gross"],
            "SETTLEMENT_AMOUNT_MISMATCH",
        )
        _require(view.get("economic_finality_claimed", False) is False, "SETTLEMENT_VIEW_REJECTED")
        for name in _REQUIRED_SETTLEMENT_FLAGS:
            _require(view.get(name) is False, "SETTLEMENT_VIEW_REJECTED")
        for name in _OPTIONAL_FALSE_FLAGS:
            if name in view:
                _require(view[name] is False, "SETTLEMENT_VIEW_REJECTED")
        claim = view.get("claim")
        _require(type(claim) is dict, "SETTLEMENT_VIEW_REJECTED")
        _require(claim.get("provenance") == FACE_PROVENANCE, "SETTLEMENT_VIEW_REJECTED")
        _require(claim.get("claim_id") == case["claim_id"], "SETTLEMENT_BINDING_CONFLICT")
        _require(claim.get("currency") == "KRW", "SETTLEMENT_VIEW_REJECTED")
        claim_gross = claim.get("gross")
        _require(type(claim_gross) is int and claim_gross == case["gross"], "SETTLEMENT_AMOUNT_MISMATCH")
        _require(claim.get("funds_executed") is False, "SETTLEMENT_VIEW_REJECTED")
        _require(claim.get("bank_debit_observed") is False, "SETTLEMENT_VIEW_REJECTED")
        _require(claim.get("economic_finality_claimed", False) is False, "SETTLEMENT_VIEW_REJECTED")
        return True

    def _mock_claim(self, claim_id: str) -> dict | None:
        try:
            return self._credit.view_claim(claim_id)
        except CreditMockError as error:
            if error.code == "UNKNOWN_CLAIM":
                return None
            raise CreditError(error.code) from error

    def _note_status(self, advance_id: str) -> str | None:
        try:
            return self._credit.view(advance_id)["status"]
        except CreditMockError as error:
            if error.code == "UNKNOWN_ADVANCE":
                return None
            raise CreditError(error.code) from error

    def _call(self, op: str, advance_id: object, idempotency_key: object, raw: dict, execute) -> dict:
        before = self._witness()
        try:
            key = _mock(_ident, idempotency_key)
            request = self._fingerprint(op, advance_id, raw)
            if request is not None:
                replayed = self._replay_if_known(key, request)
                if replayed is not None:
                    return replayed
            try:
                return execute(key, request)
            except CreditError as error:
                if (
                    request is not None
                    and error.code not in _UNSTORED_REJECTION
                    and key not in self._idempotency
                ):
                    self._idempotency[key] = {"request": request, "result": None, "error": error.code}
                raise
        finally:
            self._guard(before)

    def _fingerprint(self, op: str, advance_id: object, body: dict) -> str | None:
        try:
            return _canonical({"advance_id": advance_id, "body": body, "op": op})
        except (CreditMockError, TypeError, ValueError):
            return None

    def _replay_if_known(self, key: str, request: str) -> dict | None:
        prior = self._idempotency.get(key)
        if prior is None:
            return None
        _require(prior["request"] == request, "IDEMPOTENCY_CONFLICT")
        if prior["error"] is not None:
            raise CreditError(prior["error"])
        result = json.loads(prior["result"])
        result["duplicate"] = True
        result["applied"] = None
        self._force_false(result)
        return result

    def _accept(
        self,
        key: str,
        request: str,
        op: str,
        case: dict,
        body: dict,
        *,
        effect: object = None,
    ) -> dict:
        self._journal.append(
            {
                "op": op,
                "idempotency_key": key,
                "advance_id": case["advance_id"],
                "body": _copy(body),
            }
        )
        result = self._envelope(case, duplicate=False, applied=op, effect=effect)
        self._idempotency[key] = {"request": request, "result": _mock(_canonical, result), "error": None}
        return _copy(result)

    def _duplicate(self, key: str, request: str, case: dict) -> dict:
        result = self._envelope(case, duplicate=True, applied=None, effect=None)
        self._idempotency[key] = {"request": request, "result": _mock(_canonical, result), "error": None}
        return _copy(result)

    def _envelope(
        self,
        case: dict,
        *,
        duplicate: bool,
        applied: str | None,
        effect: object,
        matched: bool | None = None,
        entry_count: int | None = None,
    ) -> dict:
        body = {
            "duplicate": duplicate,
            "applied": applied,
            "effect": None if effect is None else _copy(effect),
            "provenance": PROVENANCE,
            "lifecycle_authority": AUTHORITY,
            "external_credit": "UNSUPPORTED",
            "economic_finality_claimed": False,
            "funds_executed": False,
            "bank_debit_observed": False,
            "repayment_observed": False,
            "interest_defined": False,
            "underwriting_executed": False,
            "kyc_executed": False,
            "credit": self._view(case),
        }
        if matched is not None:
            body["matched"] = matched
            body["state_digest"] = self.state_digest()
            body["entry_count"] = entry_count
        self._force_false(body)
        return body

    def _force_false(self, result: dict) -> None:
        result["economic_finality_claimed"] = False
        result["funds_executed"] = False
        result["bank_debit_observed"] = False
        result["repayment_observed"] = False
        result["interest_defined"] = False
        result["external_credit"] = "UNSUPPORTED"
        result["underwriting_executed"] = False
        result["kyc_executed"] = False
        credit = result.get("credit")
        if type(credit) is dict:
            credit["economic_finality_claimed"] = False
            credit["funds_executed"] = False
            credit["bank_debit_observed"] = False
            credit["repayment_observed"] = False
            credit["interest_defined"] = False
            credit["underwriting_executed"] = False
            credit["kyc_executed"] = False
            credit["ownership_mutated"] = False
            credit["ticket_ownership_authoritative"] = False
            for name in _flags():
                credit[name] = False

    def _view(self, case: dict) -> dict:
        phase = case["phase"]
        claim = self._mock_claim(case["claim_id"])
        if claim is None:
            open_face = case["open_face"]
            reserved = 0
            residual = open_face
            confirmed = case["confirmed_cash"]
            recovery = case["recovery_due"]
        else:
            open_face = claim["open_face"]
            reserved = claim["reserved_open"]
            residual = claim["residual_unreserved"]
            confirmed = claim["confirmed_cash_on_face"]
            recovery = claim["recovery_due_on_face"]
        next_sequence = None
        if phase == DRAWN and case["outstanding"] > 0:
            next_sequence = len(case["repay_order"]) + 1
        body = {
            "provenance": PROVENANCE,
            "lifecycle_authority": AUTHORITY,
            "exposure_ledger": "MOCK_EXPOSURE",
            "advance_id": case["advance_id"],
            "phase": phase,
            "terminal": phase in TERMINAL_PHASES,
            "claim_id": case["claim_id"],
            "trade_id": case["trade_id"],
            "currency": "KRW",
            "amount": case["amount"],
            "beneficiary_role": case["beneficiary_role"],
            "open_face": open_face,
            "reserved_open": reserved,
            "residual_unreserved": residual,
            "confirmed_cash_on_face": confirmed,
            "recovery_due_on_face": recovery,
            "snapshot_frozen": claim is not None,
            "note_status": self._note_status(case["advance_id"]),
            "draw_id": case["draw_id"],
            "drawn_exposure": case["drawn"],
            "repaid_exposure": case["repaid"],
            "outstanding_exposure": case["outstanding"],
            "repayments": [dict(item) for item in case["repay_order"]],
            "next_repayment_sequence": next_sequence,
            "settlement_id": case["settlement_id"],
            "settlement_gate": self._settlement_gate(case),
            "mock_settlement_commit_observed": case["mock_settlement_commit_observed"],
            "reject_reason": case["reject_reason"],
            "cancel_reason": case["cancel_reason"],
            "default_reason": case["default_reason"],
            "external_credit": "UNSUPPORTED",
            "economic_finality_claimed": False,
            "underwriting_executed": False,
            "kyc_executed": False,
            "ownership_mutated": False,
            "ticket_ownership_authoritative": False,
            "accepted_entries": sum(
                1 for entry in self._journal if entry["advance_id"] == case["advance_id"]
            ),
            "open_terms": open_terms(),
        }
        body.update(_flags())
        return body

    def _settlement_gate(self, case: dict) -> str:
        if case["mock_settlement_commit_observed"]:
            return "MOCK_COMMIT_OBSERVED"
        if case["settlement_id"] is None:
            return "UNBOUND"
        return "BOUND"

    def _witness(self) -> object:
        source = self._ownership
        if source is None:
            return None
        fn = getattr(source, "canonical_state", None)
        if fn is None:
            return None
        return fn()

    def _guard(self, before: object) -> None:
        _require(self._witness() == before, "MOCK_INVARIANT")

    def _invariant(self) -> None:
        seen: set[str] = set()
        for case in self._cases.values():
            phase = case["phase"]
            _require(
                phase in {OFFERED, APPROVED, REJECTED, DRAWN, CLOSED, DEFAULTED, CANCELLED},
                "MOCK_INVARIANT",
            )
            _require(case["outstanding"] + case["repaid"] == case["drawn"], "MOCK_INVARIANT")
            _require(0 <= case["outstanding"] <= case["drawn"] <= case["amount"] <= MONEY_MAX, "MOCK_INVARIANT")
            _require(0 < case["amount"] <= MONEY_MAX, "MOCK_INVARIANT")
            _require(len(case["repay_order"]) == len(case["repay_notes"]), "MOCK_INVARIANT")
            repaid = 0
            for index, note in enumerate(case["repay_order"], start=1):
                _require(note["sequence"] == index, "MOCK_INVARIANT")
                _require(case["repay_notes"].get(note["repay_id"]) is not None, "MOCK_INVARIANT")
                repaid += note["amount"]
            _require(repaid == case["repaid"], "MOCK_INVARIANT")
            noted = self._note_status(case["advance_id"])
            if phase in {DRAWN, DEFAULTED}:
                _require(noted == "NOTED", "MOCK_INVARIANT")
                _require(case["drawn"] == case["amount"] and case["draw_id"] is not None, "MOCK_INVARIANT")
            elif phase == CLOSED:
                _require(noted == "RELEASED", "MOCK_INVARIANT")
                _require(case["outstanding"] == 0 and case["drawn"] == case["amount"], "MOCK_INVARIANT")
            else:
                _require(noted is None, "MOCK_INVARIANT")
                _require(case["drawn"] == 0 and case["outstanding"] == 0 and case["repaid"] == 0, "MOCK_INVARIANT")
                _require(case["draw_id"] is None and case["repay_order"] == [], "MOCK_INVARIANT")
            if phase == DEFAULTED:
                _require(case["outstanding"] > 0 and case["default_reason"] is not None, "MOCK_INVARIANT")
            if case["mock_settlement_commit_observed"]:
                _require(case["settlement_id"] is not None, "MOCK_INVARIANT")
                _require(phase in EXPOSURE_PHASES, "MOCK_INVARIANT")
            view = self._view(case)
            _require(view["economic_finality_claimed"] is False, "MOCK_INVARIANT")
            _require(view["funds_executed"] is False, "MOCK_INVARIANT")
            _require(view["bank_debit_observed"] is False, "MOCK_INVARIANT")
            _require(view["repayment_observed"] is False, "MOCK_INVARIANT")
            _require(view["interest_defined"] is False, "MOCK_INVARIANT")
            _require(view["underwriting_executed"] is False, "MOCK_INVARIANT")
            _require(view["kyc_executed"] is False, "MOCK_INVARIANT")
            _require(view["ownership_mutated"] is False, "MOCK_INVARIANT")
            _require(view["exposure_ledger"] == "MOCK_EXPOSURE", "MOCK_INVARIANT")
            _require(view["provenance"] == PROVENANCE, "MOCK_INVARIANT")
            terms = view["open_terms"]
            _require(terms == open_terms(), "MOCK_INVARIANT")
            _require(terms["decided_value"] is None, "MOCK_INVARIANT")
            _require(terms["adopted_option"] == "A", "MOCK_INVARIANT")
            _require(terms["policy_number_status"] == "UNDETERMINED", "MOCK_INVARIANT")
            _require(view["priority_bound"] is False, "MOCK_INVARIANT")
            _require(view["collateral_perfected"] is False, "MOCK_INVARIANT")
            _require(view["legal_debtor_bound"] is False, "MOCK_INVARIANT")
            if case["claim_id"] in seen:
                continue
            seen.add(case["claim_id"])
            claim = self._mock_claim(case["claim_id"])
            if claim is None:
                continue
            _require(0 <= claim["reserved_open"] <= claim["open_face"] <= MONEY_MAX, "MOCK_INVARIANT")
            _require(claim["funds_executed"] is False and claim["repayment_observed"] is False, "MOCK_INVARIANT")
