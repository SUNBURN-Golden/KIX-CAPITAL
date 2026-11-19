"""Strict local JSON input; optional real local settlement replay, no defaults."""

import json
import math
import sys
from pathlib import Path

from credit_session import CreditSession
from mock_credit import PROVENANCE

_SETTLEMENT_DIR = Path(__file__).resolve().parents[1] / "settlement_f01_f03"
if str(_SETTLEMENT_DIR) not in sys.path:
    sys.path.insert(1, str(_SETTLEMENT_DIR))

from settlement_fsm import SettlementError, SettlementMachine  # noqa: E402


class FixtureError(ValueError):
    """Malformed local input; not a protocol/domain error code."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            # The pairs hook runs before Unicode validation; escape untrusted keys.
            raise FixtureError(f"duplicate JSON key: {json.dumps(key, ensure_ascii=True)}")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise FixtureError("non-finite JSON number")
    return number


def _constant(value):
    raise FixtureError(f"non-finite JSON constant: {value}")


def validate_json(value):
    """Also protect importable dispatch from non-JSON Python values."""
    def walk(item):
        if item is None or type(item) in (bool, int):
            return
        if type(item) is str:
            # Reject lone surrogates before hashing or emitting UTF-8.
            item.encode("utf-8")
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                walk(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for key, child in item.items():
                walk(key)
                walk(child)
            return
        raise FixtureError("value must be finite JSON data")

    try:
        walk(value)
    except (RecursionError, UnicodeError) as error:
        raise FixtureError("invalid JSON nesting or Unicode") from error


def decode_json(text):
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_constant=_constant,
                           parse_float=_finite_float)
        validate_json(value)
        return value
    except (ValueError, TypeError, RecursionError) as error:
        raise FixtureError(str(error)) from error


def exact_fields(value, required, context, optional=()):
    if (type(value) is not dict or not set(required) <= set(value)
            or not set(value) <= set(required) | set(optional)):
        raise FixtureError(
            f"{context} requires: {', '.join(sorted(required))}; "
            f"optional: {', '.join(sorted(optional))}")


# Explicit local setup selectors on the real settlement FSM, never a
# protocol-command catalogue. Required fields, optional fields.
_SETUP = {
    "initiate": ({"trade_id", "gross", "debtor_role", "policy"}, {"currency"}),
    "authorize": (set(), set()),
    "capture": (set(), set()),
    "commit": ({"movement_id", "gross", "amount", "fee", "tax", "held", "adjustment"},
               {"adjustment_reason"}),
    "fail": ({"reason"}, set()),
    "cancel": ({"reason"}, set()),
}


def _replay_settlement(setup):
    if type(setup) is not list:
        raise FixtureError("settlement_setup must be null or an array")
    book = SettlementMachine()
    for entry in setup:
        exact_fields(entry, {"operation", "settlement_id", "idempotency_key", "body"},
                     "settlement_setup entry")
        operation = entry["operation"]
        if type(operation) is not str or operation not in _SETUP:
            raise FixtureError("unsupported settlement_setup operation")
        required, optional = _SETUP[operation]
        exact_fields(entry["body"], required, f"settlement {operation} body", optional)
        getattr(book, operation)(
            entry["settlement_id"],
            idempotency_key=entry["idempotency_key"],
            **entry["body"],
        )
    return book


def load_fixture(path: str | Path) -> CreditSession:
    """Build a fresh session; FSM setup rejections propagate unchanged."""
    fixture = decode_json(Path(path).read_text(encoding="utf-8"))
    exact_fields(fixture, {"fixture_version", "provenance", "settlement_setup"}, "fixture")
    if type(fixture["fixture_version"]) is not int or fixture["fixture_version"] != 1:
        raise FixtureError("unsupported fixture_version")
    if fixture["provenance"] != PROVENANCE:
        raise FixtureError(f"fixture provenance must be {PROVENANCE}")
    setup = fixture["settlement_setup"]
    source = None if setup is None else _replay_settlement(setup)
    return CreditSession(source)
