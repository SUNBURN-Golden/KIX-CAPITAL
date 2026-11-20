"""Offline shared-exposure observer across claims sharing a debtor or pool.

The observer reads a caller-supplied group label and a non-empty list of
already-captured ``CreditMachine.view`` snapshots and reports the group's
aggregated mock exposure over already-exposed values only:

    group_outstanding_exposure = sum(view["outstanding_exposure"])
    group_drawn_exposure       = sum(view["drawn_exposure"])
    group_repaid_exposure      = sum(view["repaid_exposure"])

Claim-level capacity is counted once per distinct ``claim_id``:

    group_open_face           = sum(claim open_face)
    group_reserved_open       = sum(claim reserved_open)
    group_residual_unreserved = group_open_face - group_reserved_open

It never calls any machine, never recomputes a frozen face, never repairs a
gap and never authorizes exposure.  Grouping is caller-supplied: the mock has
no legal debtor identity (``legal_debtor_bound`` stays false), so a group
label is a caller label, not a legal party.  The limit is always
caller-supplied and has no default; ``within_limit`` is not an acceptance.
Every observation maps to ``NOT_BOUND``: no existing FSM phase or error code
describes a pure cross-claim observation, so no new state, command, error
table entry or policy value is added.

Contract: docs/contracts/CREDIT_ADVANCE_F04.md §7.12.
Provenance is synthetic: ``MOCK_CREDIT_F04_ONLY``; the exposure ledger is
``MOCK_EXPOSURE``.  Numbers and identifiers are caller-owned literals, not
product policy.  Nothing here establishes durability, finality, bank
exactly-once, live funds, accounting treatment or production readiness.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

SCHEMA = "kix.shared_exposure.v1"
PROVENANCE = "MOCK_CREDIT_F04_ONLY"
EXPOSURE_LEDGER = "MOCK_EXPOSURE"
CONTRACT = "docs/contracts/CREDIT_ADVANCE_F04.md#7.12"
FIXTURE = _HERE / "fixtures" / "shared_exposure_v1.json"
MONEY_MAX = 10**12

# Byte pin of fixtures/shared_exposure_v1.json.  Regenerate only through
# this module; never hand-edit the fixture.
FIXTURE_SHA256 = "cdb001701376c02cd3515bcdd939193922c960bdcaebf80ca8d3f0d7732c1c03"

# Observation is defined over frozen, drawn advances only.  Pre-draw grouping
# is undefined in this revision; an unfrozen view is a caller error.
EXPOSURE_PHASES = ("DRAWN", "CLOSED", "DEFAULTED")

# Reference-only disposition.  ``code`` is not a protocol code and is not in
# any contract error table; it is a local label on the observation record.
MAPPING = {
    "code": "SHARED_EXPOSURE_NOT_BOUND",
    "contract_status": "NOT_BOUND",
    "repair": "NONE",
}

VIEW_KEYS = frozenset(
    {
        "provenance",
        "exposure_ledger",
        "advance_id",
        "claim_id",
        "trade_id",
        "currency",
        "phase",
        "open_face",
        "reserved_open",
        "residual_unreserved",
        "drawn_exposure",
        "repaid_exposure",
        "outstanding_exposure",
        "snapshot_frozen",
    }
)
# Views sharing one claim_id must agree on these claim-level fields; they are
# read from the claim, not from the advance, so a disagreement means the
# caller mixed observation points.
CLAIM_FIELDS = ("trade_id", "open_face", "reserved_open", "residual_unreserved")
AMOUNT_FIELDS = (
    "open_face",
    "reserved_open",
    "residual_unreserved",
    "drawn_exposure",
    "repaid_exposure",
    "outstanding_exposure",
)
SCENARIO_KEYS = frozenset({"id", "group_id", "credit_views", "limit", "expected"})
EXPECTED_KEYS = frozenset(
    {
        "observable",
        "claims",
        "advance_count",
        "claim_count",
        "within_limit",
        "mapping",
        "refund_component",
    }
)
OBSERVABLE_KEYS = frozenset(
    {
        "group_outstanding_exposure",
        "group_drawn_exposure",
        "group_repaid_exposure",
        "group_open_face",
        "group_reserved_open",
        "group_residual_unreserved",
    }
)
CLAIM_ENTRY_KEYS = frozenset(
    {
        "claim_id",
        "trade_id",
        "open_face",
        "reserved_open",
        "residual_unreserved",
        "advance_ids",
    }
)
FIXTURE_KEYS = frozenset({"schema", "provenance", "contract", "mapping", "scenarios"})

_MISSING = object()


class SharedExposureError(Exception):
    """Reference-only input error; the code is not a protocol code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise SharedExposureError(code)


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
        raise SharedExposureError("FIXTURE_INVALID") from error
    return (text + "\n").encode("utf-8")


def _view_values(credit_view: object) -> dict:
    _require(type(credit_view) is dict, "VIEW_INVALID")
    _require(VIEW_KEYS <= set(credit_view), "VIEW_INVALID")
    _require(credit_view["provenance"] == PROVENANCE, "VIEW_INVALID")
    _require(credit_view["exposure_ledger"] == EXPOSURE_LEDGER, "VIEW_INVALID")
    advance_id = _ident(credit_view["advance_id"])
    claim_id = _ident(credit_view["claim_id"])
    trade_id = _ident(credit_view["trade_id"])
    _require(credit_view["currency"] == "KRW", "VIEW_BINDING_CONFLICT")
    _require(credit_view["snapshot_frozen"] is True, "VIEW_NOT_FROZEN")
    _require(credit_view["phase"] in EXPOSURE_PHASES, "VIEW_INVALID")
    amounts = {name: _amount(credit_view[name]) for name in AMOUNT_FIELDS}
    _require(
        amounts["outstanding_exposure"]
        == amounts["drawn_exposure"] - amounts["repaid_exposure"],
        "VIEW_INVALID",
    )
    _require(
        amounts["residual_unreserved"]
        == amounts["open_face"] - amounts["reserved_open"],
        "VIEW_INVALID",
    )
    return {
        "advance_id": advance_id,
        "claim_id": claim_id,
        "trade_id": trade_id,
        **amounts,
    }


def _limit(value: object) -> int:
    if value is _MISSING:
        raise SharedExposureError("LIMIT_REQUIRED")
    _require(type(value) is int and value >= 0, "LIMIT_INVALID")
    return value


def _group_values(credit_views: object) -> tuple[list, list]:
    """Validate the view list and return (per-view values, per-claim entries)."""
    _require(type(credit_views) is list and credit_views, "VIEW_INVALID")
    values = [_view_values(view) for view in credit_views]
    seen_advances: set[str] = set()
    claims: dict[str, dict] = {}
    for value in values:
        _require(value["advance_id"] not in seen_advances, "VIEW_INVALID")
        seen_advances.add(value["advance_id"])
        claim = claims.get(value["claim_id"])
        if claim is None:
            claims[value["claim_id"]] = {
                "claim_id": value["claim_id"],
                "trade_id": value["trade_id"],
                "open_face": value["open_face"],
                "reserved_open": value["reserved_open"],
                "residual_unreserved": value["residual_unreserved"],
                "advance_ids": [value["advance_id"]],
            }
            continue
        for field in CLAIM_FIELDS:
            _require(claim[field] == value[field], "VIEW_BINDING_CONFLICT")
        claim["advance_ids"].append(value["advance_id"])
    entries = []
    for claim_id in sorted(claims):
        entry = dict(claims[claim_id])
        entry["advance_ids"] = sorted(entry["advance_ids"])
        entries.append(entry)
    return values, entries


def observe_shared_exposure(
    group_id: object,
    credit_views: object,
    *,
    limit: object = _MISSING,
) -> dict:
    """Return one deterministic shared-exposure observation; never mutates state.

    ``group_id`` is a caller label for a debtor or pool, not a legal identity.
    ``limit`` is a required keyword.  Omission is a caller error, not a
    default.  ``within_limit`` reports only
    ``group_outstanding_exposure <= limit``; it is not an acceptance, an
    approval or an exposure authorization.  Every observation remains
    fail-closed and maps to ``NOT_BOUND``.
    """
    limit = _limit(limit)
    group_id = _ident(group_id)
    values, claims = _group_values(credit_views)

    # Per-view amounts stay bounded by MONEY_MAX; group sums may exceed it.
    outstanding = sum(value["outstanding_exposure"] for value in values)
    drawn = sum(value["drawn_exposure"] for value in values)
    repaid = sum(value["repaid_exposure"] for value in values)
    open_face = sum(claim["open_face"] for claim in claims)
    reserved = sum(claim["reserved_open"] for claim in claims)

    return {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "group_id": group_id,
        "advance_count": len(values),
        "claim_count": len(claims),
        "observable": {
            "group_outstanding_exposure": outstanding,
            "group_drawn_exposure": drawn,
            "group_repaid_exposure": repaid,
            "group_open_face": open_face,
            "group_reserved_open": reserved,
            "group_residual_unreserved": open_face - reserved,
        },
        "claims": claims,
        "limit": limit,
        "within_limit": outstanding <= limit,
        "fail_closed": True,
        "mapping": dict(MAPPING),
        "refund_component": "NOT_BOUND",
        "legal_debtor_bound": False,
        "mutates_state": False,
        "authorizes_exposure": False,
    }


def _read_canonical(path: object, label: str) -> tuple[object, bytes]:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise SharedExposureError("FIXTURE_INVALID") from error
    try:
        text = raw.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SharedExposureError("FIXTURE_INVALID") from error
    if canonical(value) != raw:
        raise SharedExposureError("FIXTURE_INVALID")
    return value, raw


def load_fixture(path: object = None) -> dict:
    """Load, canonicalise, pin-check and validate the shared-exposure fixture."""
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
    scenarios = value["scenarios"]
    _require(type(scenarios) is list and scenarios, "FIXTURE_INVALID")
    seen: set[str] = set()
    for index, scenario in enumerate(scenarios):
        _require(type(scenario) is dict, "FIXTURE_INVALID")
        _require(set(scenario) == SCENARIO_KEYS, "FIXTURE_INVALID")
        scenario_id = _ident(scenario["id"])
        _require(scenario_id not in seen, "FIXTURE_INVALID")
        seen.add(scenario_id)
        _require(scenario["group_id"] == _ident(scenario["group_id"]), "FIXTURE_INVALID")
        # Validate the literal view structures and group consistency without
        # trusting the expected values; the replay does the arithmetic
        # comparison.
        _group_values(scenario["credit_views"])
        _limit(scenario["limit"])
        expected = scenario["expected"]
        _require(type(expected) is dict, "FIXTURE_INVALID")
        _require(set(expected) == EXPECTED_KEYS, "FIXTURE_INVALID")
        _require(type(expected["advance_count"]) is int, "FIXTURE_INVALID")
        _require(type(expected["claim_count"]) is int, "FIXTURE_INVALID")
        _require(type(expected["within_limit"]) is bool, "FIXTURE_INVALID")
        _require(expected["mapping"] == MAPPING, "FIXTURE_INVALID")
        _require(expected["refund_component"] == "NOT_BOUND", "FIXTURE_INVALID")
        observable = expected["observable"]
        _require(type(observable) is dict, "FIXTURE_INVALID")
        _require(set(observable) == OBSERVABLE_KEYS, "FIXTURE_INVALID")
        for amount in observable.values():
            _require(type(amount) is int and amount >= 0, "FIXTURE_INVALID")
        claims = expected["claims"]
        _require(type(claims) is list and claims, "FIXTURE_INVALID")
        for entry in claims:
            _require(type(entry) is dict, "FIXTURE_INVALID")
            _require(set(entry) == CLAIM_ENTRY_KEYS, "FIXTURE_INVALID")
            _require(entry["claim_id"] == _ident(entry["claim_id"]), "FIXTURE_INVALID")
            _require(entry["trade_id"] == _ident(entry["trade_id"]), "FIXTURE_INVALID")
            for name in ("open_face", "reserved_open", "residual_unreserved"):
                _require(type(entry[name]) is int and entry[name] >= 0, "FIXTURE_INVALID")
            advance_ids = entry["advance_ids"]
            _require(type(advance_ids) is list and advance_ids, "FIXTURE_INVALID")
            for advance_id in advance_ids:
                _require(advance_id == _ident(advance_id), "FIXTURE_INVALID")
    return value


def run_scenarios(fixture: dict) -> list:
    """Replay every fixture scenario and report actual versus expected."""
    results = []
    for scenario in fixture["scenarios"]:
        record = observe_shared_exposure(
            scenario["group_id"],
            scenario["credit_views"],
            limit=scenario["limit"],
        )
        actual = {
            "observable": record["observable"],
            "claims": record["claims"],
            "advance_count": record["advance_count"],
            "claim_count": record["claim_count"],
            "within_limit": record["within_limit"],
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
            "usage: shared_exposure.py [--check]",
            file=sys.stderr,
        )
        return 2
    try:
        fixture = load_fixture()
        results = run_scenarios(fixture)
    except SharedExposureError as error:
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
