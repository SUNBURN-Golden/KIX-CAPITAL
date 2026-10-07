"""Offline F04 credit-advance mock.

Deterministic and in-memory. No network, files, bank, or payment provider.
A note reserves fixture capacity against a Wave 3 settlement face snapshot.
It does not disburse funds, price a credit product, or perfect collateral.

Lifecycle acceptance (offer, approve, reject, draw, repay, close, default,
cancel, reconcile) lives in credit_fsm.py. This module remains the open-face
reservation predicate. attempt_execution is unchanged.

Contract: docs/contracts/CREDIT_ADVANCE_F04.md
"""

from __future__ import annotations

import json

MONEY_MAX = 10**12
PROVENANCE = "MOCK_CREDIT_F04_ONLY"
FACE_PROVENANCE = "MOCK_SETTLEMENT_ONLY"

FACE_FALSE_FLAGS = (
    "legal_debtor_bound",
    "admission_granted",
    "right_cancelled",
    "bank_debit_observed",
    "external_return_closed",
    "funds_executed",
)

REQUIRED_FACE_KEYS = frozenset(
    {
        "provenance",
        "claim_id",
        "trade_id",
        "currency",
        "gross",
        "obligations",
        "refund_face",
        "fixture_reclassified",
        "refund_bearer_policy",
        "confirmed_cash",
        "recovery_due",
        *FACE_FALSE_FLAGS,
    }
)

OBLIGATION_KEYS = ("payee", "face", "distributed", "cancelled_unpaid", "outstanding")

EXECUTION_KINDS = {
    "DISBURSE": "REAL_FUNDS_FORBIDDEN",
    "REPAY": "REAL_FUNDS_FORBIDDEN",
    "DEBIT": "REAL_FUNDS_FORBIDDEN",
    "ACCRUE": "CREDIT_PRODUCT_UNDEFINED",
    "LICENSE": "CREDIT_PRODUCT_UNDEFINED",
    "FORECLOSE": "CREDIT_PRODUCT_UNDEFINED",
    "PRIORITY": "CREDIT_PRODUCT_UNDEFINED",
    "PERFECT": "CREDIT_PRODUCT_UNDEFINED",
}


class CreditMockError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise CreditMockError(code)


def _ident(value: object, code: str = "INVALID_ID") -> str:
    _require(type(value) is str and 0 < len(value) <= 100 and value.strip() == value, code)
    return value


def _money(value: object) -> int:
    _require(type(value) is int and 0 < value <= MONEY_MAX, "INVALID_AMOUNT")
    return value


def _face_money(value: object, *, positive: bool) -> int:
    _require(type(value) is int, "SETTLEMENT_FACE_MISMATCH")
    if positive:
        _require(0 < value <= MONEY_MAX, "SETTLEMENT_FACE_MISMATCH")
    else:
        _require(0 <= value <= MONEY_MAX, "SETTLEMENT_FACE_MISMATCH")
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise CreditMockError("SETTLEMENT_FACE_TYPE") from None


def _flags() -> dict:
    return {
        "funds_executed": False,
        "license_granted": False,
        "regulated_product": False,
        "collateral_perfected": False,
        "priority_bound": False,
        "disposal_controlled": False,
        "revenue_assigned": False,
        "admission_granted": False,
        "legal_debtor_bound": False,
        "bank_debit_observed": False,
        "external_pledge_complete": False,
        "durable": False,
        "repayment_observed": False,
        "interest_defined": False,
    }


def _parse_face(face: object) -> dict:
    _require(type(face) is dict, "SETTLEMENT_FACE_TYPE")
    _require(REQUIRED_FACE_KEYS <= set(face), "SETTLEMENT_FACE_FIELDS")
    canon = _canonical(face)
    _require(face["provenance"] == FACE_PROVENANCE, "SETTLEMENT_FACE_NOT_MOCK")
    for flag in FACE_FALSE_FLAGS:
        _require(face[flag] is False, "SETTLEMENT_FACE_NOT_MOCK")
    _require(face["currency"] == "KRW", "CURRENCY_UNSUPPORTED")
    claim_id = _ident(face["claim_id"])
    trade_id = _ident(face["trade_id"])
    gross = _face_money(face["gross"], positive=True)
    obligations = face["obligations"]
    _require(type(obligations) is list, "SETTLEMENT_FACE_FIELDS")
    lines = []
    seen: set[str] = set()
    for item in obligations:
        _require(type(item) is dict, "SETTLEMENT_FACE_FIELDS")
        _require(all(key in item for key in OBLIGATION_KEYS), "SETTLEMENT_FACE_FIELDS")
        payee = _ident(item["payee"])
        _require(payee not in seen, "SETTLEMENT_FACE_MISMATCH")
        seen.add(payee)
        face_amount = _face_money(item["face"], positive=True)
        distributed = _face_money(item["distributed"], positive=False)
        cancelled = _face_money(item["cancelled_unpaid"], positive=False)
        stated = _face_money(item["outstanding"], positive=False)
        _require(distributed + cancelled <= face_amount, "SETTLEMENT_FACE_MISMATCH")
        outstanding = face_amount - distributed - cancelled
        _require(stated == outstanding, "SETTLEMENT_FACE_MISMATCH")
        lines.append({"cancelled_unpaid": cancelled, "outstanding": outstanding, "face": face_amount})
    _require(sum(line["face"] for line in lines) == gross, "SETTLEMENT_FACE_MISMATCH")
    refund_face = _face_money(face["refund_face"], positive=False)
    _require(refund_face <= gross, "SETTLEMENT_FACE_MISMATCH")
    reclassified = face["fixture_reclassified"]
    _require(type(reclassified) is bool, "SETTLEMENT_FACE_MISMATCH")
    bearer = face["refund_bearer_policy"]
    _require(type(bearer) is str, "SETTLEMENT_FACE_MISMATCH")
    if reclassified:
        _require(refund_face == gross, "SETTLEMENT_FACE_MISMATCH")
        _require(bearer == "FIXTURE_FULL_GROSS_RECLASS", "SETTLEMENT_FACE_MISMATCH")
        _require(all(line["outstanding"] == 0 for line in lines), "SETTLEMENT_FACE_MISMATCH")
    elif refund_face:
        _require(bearer == "UNDEFINED", "SETTLEMENT_FACE_MISMATCH")
        _require(all(line["cancelled_unpaid"] == 0 for line in lines), "SETTLEMENT_FACE_MISMATCH")
    else:
        _require(bearer == "NONE", "SETTLEMENT_FACE_MISMATCH")
        _require(all(line["cancelled_unpaid"] == 0 for line in lines), "SETTLEMENT_FACE_MISMATCH")
    return {
        "canon": canon,
        "claim_id": claim_id,
        "trade_id": trade_id,
        "gross": gross,
        "refund_face": refund_face,
        "fixture_reclassified": reclassified,
        "open_face": sum(line["outstanding"] for line in lines),
        "confirmed_cash": _face_money(face["confirmed_cash"], positive=False),
        "recovery_due": _face_money(face["recovery_due"], positive=False),
    }


class MockCredit:
    def __init__(self) -> None:
        self._advances: dict[str, dict] = {}
        self._claims: dict[str, dict] = {}

    def note_advance(
        self,
        advance_id: object,
        *,
        face: object,
        amount: object,
        beneficiary_role: object,
        product: object = None,
    ) -> dict:
        if product is not None:
            raise CreditMockError("CREDIT_PRODUCT_UNDEFINED")
        advance_id = _ident(advance_id)
        beneficiary = _ident(beneficiary_role)
        amount = _money(amount)
        parsed = _parse_face(face)
        binding = _canonical(
            {
                "advance_id": advance_id,
                "amount": amount,
                "beneficiary_role": beneficiary,
                "face": parsed["canon"],
            }
        )
        current = self._advances.get(advance_id)
        if current is not None:
            _require(current["binding"] == binding, "ADVANCE_BINDING_CONFLICT")
            return {"duplicate": True, "applied": None, "advance": self._view_advance(current)}
        if parsed["refund_face"] and not parsed["fixture_reclassified"]:
            raise CreditMockError("REFUND_OBLIGATION_OPEN")
        claim = self._claims.get(parsed["claim_id"])
        if claim is None:
            claim = {
                "claim_id": parsed["claim_id"],
                "trade_id": parsed["trade_id"],
                "canon": parsed["canon"],
                "open_face": parsed["open_face"],
                "confirmed_cash": parsed["confirmed_cash"],
                "recovery_due": parsed["recovery_due"],
            }
        else:
            _require(claim["canon"] == parsed["canon"], "FACE_SNAPSHOT_FROZEN")
        reserved = self._reserved(parsed["claim_id"])
        _require(amount <= claim["open_face"] - reserved, "ADVANCE_EXCEEDS_OPEN_FACE")
        self._claims[parsed["claim_id"]] = claim
        row = {
            "binding": binding,
            "advance_id": advance_id,
            "claim_id": parsed["claim_id"],
            "amount": amount,
            "beneficiary_role": beneficiary,
            "status": "NOTED",
        }
        self._advances[advance_id] = row
        self._invariant()
        return {"duplicate": False, "applied": None, "advance": self._view_advance(row)}

    def release_note(self, advance_id: object) -> dict:
        advance_id = _ident(advance_id)
        row = self._advances.get(advance_id)
        _require(row is not None, "UNKNOWN_ADVANCE")
        if row["status"] == "RELEASED":
            return {"duplicate": True, "applied": None, "advance": self._view_advance(row)}
        row["status"] = "RELEASED"
        self._invariant()
        return {"duplicate": False, "applied": None, "advance": self._view_advance(row)}

    def attempt_execution(self, advance_id: object, *, kind: object) -> None:
        advance_id = _ident(advance_id)
        _require(type(kind) is str and kind in EXECUTION_KINDS, "EXECUTION_KIND")
        _require(advance_id in self._advances, "UNKNOWN_ADVANCE")
        raise CreditMockError(EXECUTION_KINDS[kind])

    def view(self, advance_id: object) -> dict:
        advance_id = _ident(advance_id)
        row = self._advances.get(advance_id)
        _require(row is not None, "UNKNOWN_ADVANCE")
        return self._view_advance(row)

    def view_claim(self, claim_id: object) -> dict:
        claim_id = _ident(claim_id)
        claim = self._claims.get(claim_id)
        _require(claim is not None, "UNKNOWN_CLAIM")
        return self._view_claim(claim)

    def _reserved(self, claim_id: str) -> int:
        return sum(
            row["amount"]
            for row in self._advances.values()
            if row["claim_id"] == claim_id and row["status"] == "NOTED"
        )

    def _view_advance(self, row: dict) -> dict:
        claim = self._claims[row["claim_id"]]
        body = self._view_claim(claim)
        body.update(
            {
                "advance_id": row["advance_id"],
                "amount": row["amount"],
                "beneficiary_role": row["beneficiary_role"],
                "status": row["status"],
            }
        )
        return body

    def _view_claim(self, claim: dict) -> dict:
        reserved = self._reserved(claim["claim_id"])
        body = {
            "provenance": PROVENANCE,
            "claim_id": claim["claim_id"],
            "trade_id": claim["trade_id"],
            "currency": "KRW",
            "open_face": claim["open_face"],
            "reserved_open": reserved,
            "residual_unreserved": claim["open_face"] - reserved,
            "confirmed_cash_on_face": claim["confirmed_cash"],
            "recovery_due_on_face": claim["recovery_due"],
            "snapshot_frozen": True,
        }
        body.update(_flags())
        return body

    def _invariant(self) -> None:
        for claim in self._claims.values():
            reserved = self._reserved(claim["claim_id"])
            _require(0 <= reserved <= claim["open_face"] <= MONEY_MAX, "MOCK_INVARIANT")
        for row in self._advances.values():
            _require(row["status"] in ("NOTED", "RELEASED"), "MOCK_INVARIANT")
            _require(row["claim_id"] in self._claims, "MOCK_INVARIANT")
            _require(0 < row["amount"] <= MONEY_MAX, "MOCK_INVARIANT")
