"""Offline settlement-variance observer across the F01-F03 / F04 boundary.

The observer reads two caller-supplied, already-captured mock views and reports
one arithmetic gap:

    variance = sum(settlement_view["obligations"][i]["outstanding"])
               - credit_view["open_face"]

It never calls either machine, never derives a face, never repairs the gap and
never authorizes exposure.  A non-zero or out-of-tolerance observation maps to
``NOT_BOUND``: no existing FSM phase or error code describes a pure
cross-contract observation, so no new state, command, error table entry or
policy value is added.  Tolerance is always caller-supplied and has no default.

Contract: docs/contracts/CREDIT_ADVANCE_F04.md §7.11.
Provenance is synthetic on both sides: ``MOCK_SETTLEMENT_ONLY`` and
``MOCK_CREDIT_F04_ONLY``.  Numbers and identifiers are caller-owned literals,
not product policy.  Nothing here establishes durability, finality, bank
exactly-once, live funds, accounting treatment or production readiness.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

SCHEMA = "kix.settlement_variance.v1"
PROVENANCE = "MOCK_SETTLEMENT_ONLY+MOCK_CREDIT_F04_ONLY"
SETTLEMENT_PROVENANCE = "MOCK_SETTLEMENT_ONLY"
CREDIT_PROVENANCE = "MOCK_CREDIT_F04_ONLY"
CONTRACT = "docs/contracts/CREDIT_ADVANCE_F04.md#7.11"
FIXTURE = _HERE / "fixtures" / "settlement_variance_v1.json"
MONEY_MAX = 10**12

# Byte pin of fixtures/settlement_variance_v1.json.  Regenerate only through
# this module; never hand-edit the fixture.
FIXTURE_SHA256 = "f2db31f337bc44d5931e97f0e5c57d529e8f1f444339366b50178c304df38b76"

SIGNS = ("POSITIVE", "ZERO", "NEGATIVE")

# Reference-only disposition.  ``code`` is not a protocol code and is not in
# any contract error table; it is a local label on the observation record.
MAPPING = {
    "code": "SETTLEMENT_VARIANCE_NOT_BOUND",
    "contract_status": "NOT_BOUND",
    "repair": "NONE",
}

SETTLEMENT_VIEW_KEYS = frozenset(
    {
        "provenance",
        "claim_id",
        "trade_id",
        "currency",
        "obligations",
        "confirmed_cash",
        "recovery_due",
    }
)
CREDIT_VIEW_KEYS = frozenset(
    {
        "provenance",
        "claim_id",
        "trade_id",
        "currency",
        "open_face",
        "confirmed_cash_on_face",
        "recovery_due_on_face",
        "snapshot_frozen",
    }
)
SCENARIO_KEYS = frozenset(
    {
        "id",
        "claim_id",
        "trade_id",
        "settlement_view",
        "credit_view",
        "tolerance",
        "expected",
    }
)
EXPECTED_KEYS = frozenset(
    {"variance", "sign", "within_tolerance", "mapping", "refund_component"}
)
FIXTURE_KEYS = frozenset(
    {"schema", "provenance", "contract", "sign_convention", "mapping", "scenarios"}
)

_MISSING = object()


class VarianceObservationError(Exception):
    """Reference-only input error; the code is not a protocol code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise VarianceObservationError(code)


def _ident(value: object) -> str:
    _require(
        type(value) is str and 0 < len(value) <= 100 and value.strip() == value,
        "VIEW_INVALID",
    )
    return value


def _amount(value: object) -> int:
    _require(type(value) is int and 0 <= value <= MONEY_MAX, "VIEW_INVALID")
    return value


def canonical(value: object) -> bytes:
    """Return canonical JSON bytes: sorted keys, compact, UTF-8, one newline."""
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise VarianceObservationError("FIXTURE_INVALID") from error
    return (text + "\n").encode("utf-8")


def _settlement_values(settlement_view: object) -> dict:
    _require(type(settlement_view) is dict, "VIEW_INVALID")
    _require(SETTLEMENT_VIEW_KEYS <= set(settlement_view), "VIEW_INVALID")
    _require(
        settlement_view["provenance"] == SETTLEMENT_PROVENANCE, "VIEW_INVALID"
    )
    claim_id = _ident(settlement_view["claim_id"])
    trade_id = _ident(settlement_view["trade_id"])
    _require(settlement_view["currency"] == "KRW", "VIEW_BINDING_CONFLICT")
    obligations = settlement_view["obligations"]
    _require(type(obligations) is list, "VIEW_INVALID")
    outstanding = 0
    for item in obligations:
        _require(type(item) is dict and "outstanding" in item, "VIEW_INVALID")
        outstanding += _amount(item["outstanding"])
    _require(outstanding <= MONEY_MAX, "VIEW_INVALID")
    return {
        "claim_id": claim_id,
        "trade_id": trade_id,
        "outstanding": outstanding,
        "confirmed_cash": _amount(settlement_view["confirmed_cash"]),
        "recovery_due": _amount(settlement_view["recovery_due"]),
    }


def _credit_values(credit_view: object) -> dict:
    _require(type(credit_view) is dict, "VIEW_INVALID")
    _require(CREDIT_VIEW_KEYS <= set(credit_view), "VIEW_INVALID")
    _require(credit_view["provenance"] == CREDIT_PROVENANCE, "VIEW_INVALID")
    claim_id = _ident(credit_view["claim_id"])
    trade_id = _ident(credit_view["trade_id"])
    _require(credit_view["currency"] == "KRW", "VIEW_BINDING_CONFLICT")
    _require(credit_view["snapshot_frozen"] is True, "VIEW_NOT_FROZEN")
    return {
        "claim_id": claim_id,
        "trade_id": trade_id,
        "open_face": _amount(credit_view["open_face"]),
        "confirmed_cash": _amount(credit_view["confirmed_cash_on_face"]),
        "recovery_due": _amount(credit_view["recovery_due_on_face"]),
    }


def _tolerance(value: object) -> int:
    if value is _MISSING:
        raise VarianceObservationError("TOLERANCE_REQUIRED")
    _require(type(value) is int and value >= 0, "TOLERANCE_INVALID")
    return value


def observe_settlement_variance(
    settlement_view: object,
    credit_view: object,
    *,
    tolerance: object = _MISSING,
) -> dict:
    """Return one deterministic variance observation; never mutates state.

    ``tolerance`` is a required keyword.  Omission is a caller error, not a
    default.  ``within_tolerance`` reports only ``abs(variance) <= tolerance``;
    it is not an acceptance, a reconciliation completion or an exposure
    authorization.  Every observation remains fail-closed and maps to
    ``NOT_BOUND``.
    """
    tolerance = _tolerance(tolerance)
    settlement = _settlement_values(settlement_view)
    credit = _credit_values(credit_view)
    _require(
        settlement["claim_id"] == credit["claim_id"]
        and settlement["trade_id"] == credit["trade_id"],
        "VIEW_BINDING_CONFLICT",
    )

    variance = settlement["outstanding"] - credit["open_face"]
    if variance > 0:
        sign = "POSITIVE"
    elif variance < 0:
        sign = "NEGATIVE"
    else:
        sign = "ZERO"

    return {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "claim_id": settlement["claim_id"],
        "trade_id": settlement["trade_id"],
        "observable": {
            "settlement_outstanding": settlement["outstanding"],
            "credit_open_face": credit["open_face"],
        },
        "variance": variance,
        "sign": sign,
        "tolerance": tolerance,
        "within_tolerance": abs(variance) <= tolerance,
        "fail_closed": True,
        "mapping": dict(MAPPING),
        "companion": {
            "cash_delta": settlement["confirmed_cash"] - credit["confirmed_cash"],
            "recovery_delta": settlement["recovery_due"] - credit["recovery_due"],
            "note": (
                "diagnostic only; excluded from the variance formula and the "
                "tolerance gate"
            ),
        },
        "refund_component": "NOT_BOUND",
        "mutates_state": False,
        "authorizes_exposure": False,
    }


def _read_canonical(path: object, label: str) -> tuple[object, bytes]:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise VarianceObservationError("FIXTURE_INVALID") from error
    try:
        text = raw.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VarianceObservationError("FIXTURE_INVALID") from error
    if canonical(value) != raw:
        raise VarianceObservationError("FIXTURE_INVALID")
    return value, raw


def load_fixture(path: object = None) -> dict:
    """Load, canonicalise, pin-check and validate the variance fixture."""
    path = FIXTURE if path is None else path
    value, raw = _read_canonical(path, "fixture")
    _require(
        hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256,
        "FIXTURE_PIN_MISMATCH",
    )
    _require(type(value) is dict, "FIXTURE_INVALID")
    _require(set(value) == FIXTURE_KEYS, "FIXTURE_INVALID")
    _require(value["schema"] == SCHEMA, "FIXTURE_INVALID")
    _require(value["provenance"] == PROVENANCE, "FIXTURE_INVALID")
    _require(value["contract"] == CONTRACT, "FIXTURE_INVALID")
    _require(value["mapping"] == MAPPING, "FIXTURE_INVALID")
    _require(type(value["sign_convention"]) is dict, "FIXTURE_INVALID")
    _require(
        set(value["sign_convention"]) == set(SIGNS), "FIXTURE_INVALID"
    )
    scenarios = value["scenarios"]
    _require(type(scenarios) is list and scenarios, "FIXTURE_INVALID")
    seen: set[str] = set()
    for index, scenario in enumerate(scenarios):
        where = "scenarios[%d]" % index
        _require(type(scenario) is dict, "FIXTURE_INVALID")
        _require(set(scenario) == SCENARIO_KEYS, "FIXTURE_INVALID")
        scenario_id = _ident(scenario["id"])
        _require(scenario_id not in seen, "FIXTURE_INVALID")
        seen.add(scenario_id)
        _require(scenario["claim_id"] == _ident(scenario["claim_id"]), "FIXTURE_INVALID")
        _require(scenario["trade_id"] == _ident(scenario["trade_id"]), "FIXTURE_INVALID")
        expected = scenario["expected"]
        _require(type(expected) is dict, "FIXTURE_INVALID")
        _require(set(expected) == EXPECTED_KEYS, "FIXTURE_INVALID")
        _require(expected["sign"] in SIGNS, "FIXTURE_INVALID")
        _require(type(expected["variance"]) is int, "FIXTURE_INVALID")
        _require(type(expected["within_tolerance"]) is bool, "FIXTURE_INVALID")
        _require(expected["mapping"] == MAPPING, "FIXTURE_INVALID")
        _require(expected["refund_component"] == "NOT_BOUND", "FIXTURE_INVALID")
        # Validate the literal view structures without trusting the expected
        # values; the replay below does the arithmetic comparison.
        _settlement_values(scenario["settlement_view"])
        _credit_values(scenario["credit_view"])
        _tolerance(scenario["tolerance"])
        _require(
            scenario["settlement_view"]["claim_id"] == scenario["claim_id"],
            "FIXTURE_INVALID",
        )
        _require(
            scenario["credit_view"]["claim_id"] == scenario["claim_id"],
            "FIXTURE_INVALID",
        )
        _require(
            scenario["settlement_view"]["trade_id"] == scenario["trade_id"],
            "FIXTURE_INVALID",
        )
        _require(
            scenario["credit_view"]["trade_id"] == scenario["trade_id"],
            "FIXTURE_INVALID",
        )
    return value


def run_scenarios(fixture: dict) -> list:
    """Replay every fixture scenario and report actual versus expected."""
    results = []
    for scenario in fixture["scenarios"]:
        record = observe_settlement_variance(
            scenario["settlement_view"],
            scenario["credit_view"],
            tolerance=scenario["tolerance"],
        )
        actual = {
            "variance": record["variance"],
            "sign": record["sign"],
            "within_tolerance": record["within_tolerance"],
            "mapping": record["mapping"],
            "refund_component": record["refund_component"],
        }
        results.append(
            {
                "id": scenario["id"],
                "expected": scenario["expected"],
                "actual": actual,
                "match": actual == scenario["expected"],
                "record": record,
            }
        )
    return results


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments not in ([], ["--check"]):
        print(
            "usage: settlement_variance.py [--check]",
            file=sys.stderr,
        )
        return 2
    try:
        fixture = load_fixture()
        results = run_scenarios(fixture)
    except VarianceObservationError as error:
        print("input error: " + error.code, file=sys.stderr)
        return 2
    mismatches = [result for result in results if not result["match"]]
    if mismatches:
        for result in mismatches:
            print(
                "scenario mismatch: %s expected %r actual %r"
                % (result["id"], result["expected"], result["actual"]),
                file=sys.stderr,
            )
        return 1
    output = {
        "schema": SCHEMA,
        "provenance": PROVENANCE,
        "contract": CONTRACT,
        "fixture_sha256": FIXTURE_SHA256,
        "scenarios": [
            {"id": result["id"], "actual": result["actual"]}
            for result in results
        ],
    }
    sys.stdout.buffer.write(canonical(output))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
