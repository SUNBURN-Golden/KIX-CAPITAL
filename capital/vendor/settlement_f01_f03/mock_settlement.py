"""Offline F01–F03 settlement mock.

Deterministic and in-memory. No network, files, bank, or payment provider.
Fixture role labels are not legal persons.

This module is the economic predicate. Lifecycle acceptance
(initiate, authorize, capture, commit, fail, cancel, reconcile)
lives in settlement_fsm.py and is the only writer for that path.

Contract: docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md
"""

from __future__ import annotations

import json

MONEY_MAX = 10**12
PROVENANCE = "MOCK_SETTLEMENT_ONLY"
POLICY_KEYS = frozenset({"kind", "fee_bps", "residual_payee", "fee_payee"})


class SettlementError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise SettlementError(code)


def _ident(value: object, code: str = "INVALID_ID") -> str:
    _require(type(value) is str and 0 < len(value) <= 100 and value.strip() == value, code)
    return value


def _money(value: object, *, positive: bool) -> int:
    code = "INVALID_AMOUNT" if positive else "INVALID_NONNEGATIVE"
    _require(type(value) is int, code)
    if positive:
        _require(0 < value <= MONEY_MAX, code)
    else:
        _require(0 <= value <= MONEY_MAX, code)
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _outstanding(obligation: dict) -> int:
    return obligation["face"] - obligation["distributed"] - obligation["cancelled_unpaid"]


def _policy(policy: object) -> dict:
    _require(type(policy) is dict, "POLICY_TYPE")
    _require(set(policy) == POLICY_KEYS, "POLICY_FIELDS")
    _require(policy["kind"] == "PRIMARY_FEE_BPS", "POLICY_KIND")
    fee_bps = policy["fee_bps"]
    _require(type(fee_bps) is int and 0 <= fee_bps <= 10000, "POLICY_FEE_BPS")
    residual = _ident(policy["residual_payee"], "POLICY_PAYEE")
    fee_payee = _ident(policy["fee_payee"], "POLICY_PAYEE")
    _require(residual != fee_payee, "POLICY_PAYEE_COLLISION")
    return {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": fee_bps,
        "residual_payee": residual,
        "fee_payee": fee_payee,
    }


def _split(gross: int, policy: dict) -> dict:
    fee = gross * policy["fee_bps"] // 10000
    residual = gross - fee
    lines = {}
    if residual:
        lines[policy["residual_payee"]] = _line(policy["residual_payee"], residual)
    if fee:
        lines[policy["fee_payee"]] = _line(policy["fee_payee"], fee)
    _require(sum(line["face"] for line in lines.values()) == gross, "MOCK_INVARIANT")
    return lines


def _line(payee: str, face: int) -> dict:
    return {
        "payee": payee,
        "face": face,
        "distributed": 0,
        "cancelled_unpaid": 0,
        "recovery_due": 0,
    }


class MockSettlement:
    def __init__(self) -> None:
        self._claims: dict[str, dict] = {}

    def recognize_claim(
        self,
        claim_id: object,
        *,
        trade_id: object,
        gross: object,
        debtor_role: object,
        policy: object,
        currency: object = "KRW",
    ) -> dict:
        claim_id = _ident(claim_id)
        trade_id = _ident(trade_id)
        debtor_role = _ident(debtor_role, "INVALID_ID")
        _require(currency == "KRW", "CURRENCY_UNSUPPORTED")
        gross = _money(gross, positive=True)
        frozen = _policy(policy)
        binding = {
            "claim_id": claim_id,
            "trade_id": trade_id,
            "gross": gross,
            "currency": "KRW",
            "debtor_role": debtor_role,
            "policy": frozen,
        }
        canon = _canonical(binding)
        current = self._claims.get(claim_id)
        if current is not None:
            _require(current["binding"] == canon, "CLAIM_BINDING_CONFLICT")
            return {"duplicate": True, "applied": None, "claim": self._view(current)}
        claim = {
            "binding": canon,
            "claim_id": claim_id,
            "trade_id": trade_id,
            "currency": "KRW",
            "gross": gross,
            "debtor_role": debtor_role,
            "policy": frozen,
            "obligations": _split(gross, frozen),
            "statements": {},
            "refunds": {},
            "acceptances": {},
            "refund_face": 0,
            "refund_accepted": 0,
            "refund_beneficiary": None,
            "fixture_reclassified": False,
            "confirmed_cash": 0,
            "statement_gross": 0,
            "non_cash": 0,
            "distribution_order": None,
        }
        self._invariant(claim)
        self._claims[claim_id] = claim
        return {"duplicate": False, "applied": None, "claim": self._view(claim)}

    def observe_settlement_statement(
        self,
        claim_id: object,
        *,
        movement_id: object,
        gross: object,
        amount: object,
        fee: object,
        tax: object,
        held: object,
        adjustment: object,
        adjustment_reason: object = None,
    ) -> dict:
        claim = self._get(claim_id)
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
        binding = {
            "movement_id": movement_id,
            "gross": gross,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "held": held,
            "adjustment": adjustment,
            "adjustment_reason": reason,
        }
        canon = _canonical(binding)
        previous = claim["statements"].get(movement_id)
        if previous is not None:
            _require(previous == canon, "STATEMENT_BINDING_CONFLICT")
            return {"duplicate": True, "applied": None, "claim": self._view(claim)}
        _require(claim["statement_gross"] + gross <= claim["gross"], "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE")
        claim["statements"][movement_id] = canon
        claim["statement_gross"] += gross
        claim["confirmed_cash"] += amount
        claim["non_cash"] += fee + tax + held + adjustment
        self._invariant(claim)
        return {"duplicate": False, "applied": None, "claim": self._view(claim)}

    def apply_distribution(self, claim_id: object, *, order: object) -> dict:
        claim = self._get(claim_id)
        _require(type(order) is list, "DISTRIBUTION_ORDER_TYPE")
        payees = [_ident(payee) for payee in order]
        _require(len(payees) == len(set(payees)), "DISTRIBUTION_ORDER_DUPLICATE")
        _require(set(payees) == set(claim["obligations"]), "DISTRIBUTION_ORDER_MISMATCH")
        if claim["distribution_order"] is not None:
            _require(payees == claim["distribution_order"], "DISTRIBUTION_ORDER_FROZEN")
        if claim["refund_face"] and not claim["fixture_reclassified"]:
            raise SettlementError("DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED")
        if claim["distribution_order"] is None:
            claim["distribution_order"] = list(payees)
        remaining = claim["confirmed_cash"] - sum(line["distributed"] for line in claim["obligations"].values())
        applied = {}
        for payee in payees:
            line = claim["obligations"][payee]
            take = min(_outstanding(line), remaining)
            line["distributed"] += take
            remaining -= take
            applied[payee] = take
        self._invariant(claim)
        return {"duplicate": False, "applied": applied, "claim": self._view(claim)}

    def bind_refund(
        self,
        claim_id: object,
        *,
        refund_id: object,
        amount: object,
        beneficiary_role: object,
        reason: object,
    ) -> dict:
        claim = self._get(claim_id)
        refund_id = _ident(refund_id)
        amount = _money(amount, positive=True)
        beneficiary = _ident(beneficiary_role)
        reason = _ident(reason)
        binding = {
            "refund_id": refund_id,
            "amount": amount,
            "beneficiary_role": beneficiary,
            "reason": reason,
        }
        canon = _canonical(binding)
        previous = claim["refunds"].get(refund_id)
        if previous is not None:
            _require(previous == canon, "REFUND_BINDING_CONFLICT")
            return {"duplicate": True, "applied": None, "claim": self._view(claim)}
        _require(claim["refund_face"] + amount <= claim["gross"], "REFUND_CEILING")
        if claim["refund_beneficiary"] not in (None, beneficiary):
            raise SettlementError("REFUND_BENEFICIARY_CONFLICT")
        full = amount == claim["gross"] and claim["refund_face"] == 0
        claim["refunds"][refund_id] = canon
        claim["refund_face"] += amount
        claim["refund_beneficiary"] = beneficiary
        if full:
            for line in claim["obligations"].values():
                line["cancelled_unpaid"] += _outstanding(line)
                line["recovery_due"] = line["distributed"]
            claim["fixture_reclassified"] = True
        self._invariant(claim)
        return {"duplicate": False, "applied": None, "claim": self._view(claim)}

    def observe_mock_cancel_acceptance(self, claim_id: object, *, source_id: object, amount: object) -> dict:
        claim = self._get(claim_id)
        source_id = _ident(source_id)
        amount = _money(amount, positive=True)
        binding = {"source_id": source_id, "amount": amount}
        canon = _canonical(binding)
        previous = claim["acceptances"].get(source_id)
        if previous is not None:
            _require(previous == canon, "ACCEPTANCE_BINDING_CONFLICT")
            return {"duplicate": True, "applied": None, "claim": self._view(claim)}
        _require(claim["refund_face"] > 0, "REFUND_OBLIGATION_REQUIRED")
        _require(amount <= claim["refund_face"] - claim["refund_accepted"], "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION")
        claim["acceptances"][source_id] = canon
        claim["refund_accepted"] += amount
        self._invariant(claim)
        return {"duplicate": False, "applied": None, "claim": self._view(claim)}

    def view(self, claim_id: object) -> dict:
        return self._view(self._get(claim_id))

    def _get(self, claim_id: object) -> dict:
        claim_id = _ident(claim_id)
        claim = self._claims.get(claim_id)
        _require(claim is not None, "UNKNOWN_CLAIM")
        return claim

    def _view(self, claim: dict) -> dict:
        obligations = []
        for payee in sorted(claim["obligations"]):
            line = claim["obligations"][payee]
            obligations.append(
                {
                    "payee": payee,
                    "face": line["face"],
                    "distributed": line["distributed"],
                    "cancelled_unpaid": line["cancelled_unpaid"],
                    "recovery_due": line["recovery_due"],
                    "outstanding": _outstanding(line),
                }
            )
        distributed = sum(line["distributed"] for line in claim["obligations"].values())
        if claim["fixture_reclassified"]:
            bearer = "FIXTURE_FULL_GROSS_RECLASS"
        elif claim["refund_face"]:
            bearer = "UNDEFINED"
        else:
            bearer = "NONE"
        return {
            "provenance": PROVENANCE,
            "claim_id": claim["claim_id"],
            "trade_id": claim["trade_id"],
            "currency": claim["currency"],
            "gross": claim["gross"],
            "debtor_role": claim["debtor_role"],
            "legal_debtor_bound": False,
            "admission_granted": False,
            "right_cancelled": False,
            "bank_debit_observed": False,
            "external_return_closed": False,
            "funds_executed": False,
            "policy": dict(claim["policy"]),
            "obligations": obligations,
            "receivable_open": claim["gross"] - claim["statement_gross"],
            "confirmed_cash": claim["confirmed_cash"],
            "non_cash_accounted": claim["non_cash"],
            "distributed_cash": distributed,
            "undistributed_cash": claim["confirmed_cash"] - distributed,
            "distribution_order": None if claim["distribution_order"] is None else list(claim["distribution_order"]),
            "refund_face": claim["refund_face"],
            "refund_accepted": claim["refund_accepted"],
            "refund_outstanding": claim["refund_face"] - claim["refund_accepted"],
            "refund_beneficiary": claim["refund_beneficiary"],
            "fixture_reclassified": claim["fixture_reclassified"],
            "refund_bearer_policy": bearer,
            "distribution_blocked": bool(claim["refund_face"]) and not claim["fixture_reclassified"],
            "pg_adjustment_outstanding": claim["refund_accepted"],
            "recovery_due": sum(line["recovery_due"] for line in claim["obligations"].values()),
        }

    def _invariant(self, claim: dict) -> None:
        lines = list(claim["obligations"].values())
        _require(sum(line["face"] for line in lines) == claim["gross"], "MOCK_INVARIANT")
        distributed = 0
        for line in lines:
            outstanding = _outstanding(line)
            _require(line["distributed"] >= 0 and line["cancelled_unpaid"] >= 0 and line["recovery_due"] >= 0, "MOCK_INVARIANT")
            _require(outstanding >= 0 and line["recovery_due"] <= line["distributed"], "MOCK_INVARIANT")
            distributed += line["distributed"]
        _require(claim["confirmed_cash"] + claim["non_cash"] == claim["statement_gross"], "MOCK_INVARIANT")
        _require(0 <= claim["statement_gross"] <= claim["gross"], "MOCK_INVARIANT")
        _require(0 <= distributed <= claim["confirmed_cash"], "MOCK_INVARIANT")
        _require(0 <= claim["refund_accepted"] <= claim["refund_face"] <= claim["gross"], "MOCK_INVARIANT")
        outstanding_sum = sum(_outstanding(line) for line in lines)
        if claim["fixture_reclassified"]:
            _require(claim["refund_face"] == claim["gross"], "MOCK_INVARIANT")
            for line in lines:
                _require(_outstanding(line) == 0 and line["recovery_due"] == line["distributed"], "MOCK_INVARIANT")
        else:
            for line in lines:
                _require(line["cancelled_unpaid"] == 0 and line["recovery_due"] == 0, "MOCK_INVARIANT")
            _require(claim["confirmed_cash"] - distributed <= outstanding_sum, "MOCK_INVARIANT")
