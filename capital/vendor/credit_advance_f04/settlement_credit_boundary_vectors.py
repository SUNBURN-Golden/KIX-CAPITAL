"""Consumer-replay driver for the synthetic settlement-to-F04-credit pack.

The pack crosses one boundary only: a caller copies the F01-F03 settlement
view's ``claim`` object literally into ``CreditMachine.offer(face=...)``.  This
driver never derives, reshapes, or re-reads that face.  It dispatches the
fixture's explicit steps to the two *existing* in-memory machines through their
public methods, records every exact result, and compares the record with the
JSON vector file byte-for-byte (canonical JSON value equality).

Provenance is synthetic on both sides: ``MOCK_SETTLEMENT_ONLY`` and
``MOCK_CREDIT_F04_ONLY``.  There is no adapter, console, subprocess client,
protocol command, filesystem write, network call, real funds, credential, or
policy value here.  All numbers and identifiers are caller-owned fixture
literals.

Run from the repository root with only the standard library::

    python3 -B reference/credit_advance_f04/settlement_credit_boundary_vectors.py

It is read-only: it prints the canonical actual vectors on success and exits 1
on the first mismatch.  Input or usage problems exit 2.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SETTLEMENT_DIR = _HERE.parent / "settlement_f01_f03"
for _path in (_HERE, _SETTLEMENT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(1, str(_path))

from credit_fixture import FixtureError, decode_json, exact_fields  # noqa: E402
from credit_fsm import CreditError, CreditMachine  # noqa: E402
from settlement_fsm import SettlementError, SettlementMachine  # noqa: E402

FIXTURE_VERSION = "settlement-credit-boundary/1"
VECTOR_VERSION = FIXTURE_VERSION
FIXTURE_KIND = "SYNTHETIC_CROSS_BOUNDARY_VECTORS"
SETTLEMENT_PROVENANCE = "MOCK_SETTLEMENT_ONLY"
CREDIT_PROVENANCE = "MOCK_CREDIT_F04_ONLY"
PROVENANCE = {"settlement": SETTLEMENT_PROVENANCE, "credit": CREDIT_PROVENANCE}
TARGETS = ("settlement", "credit")
ERROR_TYPES = ("SettlementError", "CreditError")

FIXTURE_PATH = _HERE / "fixtures" / "settlement_credit_boundary_v1.json"
VECTORS_PATH = _HERE / "fixtures" / "settlement_credit_boundary_vectors_v1.json"

# Explicit public-method selectors; never arbitrary attribute access.
_SETTLEMENT_OPERATIONS = frozenset(
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
        "reconcile",
        "view",
        "export_journal",
        "canonical_state",
        "state_digest",
    }
)
_CREDIT_OPERATIONS = frozenset(
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
        "reconcile",
        "view",
        "view_claim",
        "export_journal",
        "canonical_state",
        "state_digest",
    }
)
_OPERATIONS = {"settlement": _SETTLEMENT_OPERATIONS, "credit": _CREDIT_OPERATIONS}


class VectorMismatch(AssertionError):
    """The machines' actual output differs from the JSON vectors."""


def canonical(value: object) -> bytes:
    """Return canonical JSON bytes: sorted keys, compact, UTF-8, trailing newline."""
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return (text + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise FixtureError("value is not finite JSON data") from error


def _read_canonical(path: object, label: str) -> tuple[object, bytes]:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise FixtureError(f"{label} cannot be read: {error}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FixtureError(f"{label} is not UTF-8") from error
    value = decode_json(text)
    if canonical(value) != raw:
        raise FixtureError(
            f"{label} must be canonical JSON (sorted keys, compact separators, "
            "UTF-8, single trailing newline)"
        )
    return value, raw


def _identifier(value: object, context: str) -> str:
    if type(value) is not str or not value or len(value) > 100 or value.strip() != value:
        raise FixtureError(f"{context} must be a trimmed non-empty string")
    return value


def _provenance(value: object, context: str) -> dict:
    exact_fields(value, {"settlement", "credit"}, context)
    if value["settlement"] != SETTLEMENT_PROVENANCE or value["credit"] != CREDIT_PROVENANCE:
        raise FixtureError(
            f"{context} must be {SETTLEMENT_PROVENANCE} / {CREDIT_PROVENANCE}"
        )
    return dict(PROVENANCE)


def _validate_step(step: object, context: str) -> None:
    exact_fields(step, {"step_id", "target", "operation", "arguments"}, context)
    _identifier(step["step_id"], f"{context}.step_id")
    target = step["target"]
    if target not in TARGETS:
        raise FixtureError(f"{context}.target must be 'settlement' or 'credit'")
    operation = step["operation"]
    if type(operation) is not str or operation not in _OPERATIONS[target]:
        raise FixtureError(f"{context}.operation is not an existing public {target} method")
    if type(step["arguments"]) is not dict:
        raise FixtureError(f"{context}.arguments must be an object")


def _validate_scenarios(value: object, context: str) -> list:
    if type(value) is not list or not value:
        raise FixtureError(f"{context}.scenarios must be a non-empty array")
    seen: set[str] = set()
    for index, scenario in enumerate(value):
        where = f"{context}.scenarios[{index}]"
        exact_fields(scenario, {"scenario_id", "acceptance", "steps"}, where)
        scenario_id = _identifier(scenario["scenario_id"], f"{where}.scenario_id")
        if scenario_id in seen:
            raise FixtureError(f"{where}.scenario_id is duplicated")
        seen.add(scenario_id)
        acceptance = scenario["acceptance"]
        if type(acceptance) is not list or not acceptance:
            raise FixtureError(f"{where}.acceptance must be a non-empty array")
        tags: set[str] = set()
        for tag in acceptance:
            name = _identifier(tag, f"{where}.acceptance item")
            if name in tags:
                raise FixtureError(f"{where}.acceptance item is duplicated")
            tags.add(name)
        steps = scenario["steps"]
        if type(steps) is not list or not steps:
            raise FixtureError(f"{where}.steps must be a non-empty array")
        step_ids: set[str] = set()
        for step_index, step in enumerate(steps):
            step_where = f"{where}.steps[{step_index}]"
            _validate_step(step, step_where)
            if step["step_id"] in step_ids:
                raise FixtureError(f"{step_where}.step_id is duplicated")
            step_ids.add(step["step_id"])
    return value


def load_fixture(path: object) -> dict:
    """Load and strictly validate the fixture pack."""
    value, _raw = _read_canonical(path, "fixture")
    exact_fields(
        value,
        {"fixture_version", "fixture_kind", "synthetic_only", "provenance", "scenarios"},
        "fixture",
    )
    if value["fixture_version"] != FIXTURE_VERSION:
        raise FixtureError(f"fixture_version must be {FIXTURE_VERSION}")
    if value["fixture_kind"] != FIXTURE_KIND:
        raise FixtureError(f"fixture_kind must be {FIXTURE_KIND}")
    if value["synthetic_only"] is not True:
        raise FixtureError("fixture synthetic_only must be true")
    _provenance(value["provenance"], "fixture.provenance")
    _validate_scenarios(value["scenarios"], "fixture")
    return value


def _validate_result(result: object, context: str) -> None:
    if type(result) is not dict:
        raise FixtureError(f"{context}.result must be an object")
    if set(result) == {"ok"}:
        return
    if set(result) != {"error"}:
        raise FixtureError(f"{context}.result must be {{ok}} or {{error}}")
    error = result["error"]
    exact_fields(error, {"type", "code"}, f"{context}.result.error")
    if error["type"] not in ERROR_TYPES:
        raise FixtureError(f"{context}.result.error.type must be a domain error")
    _identifier(error["code"], f"{context}.result.error.code")


def load_vectors(path: object) -> dict:
    """Load and strictly validate the expected-output vector pack."""
    value, _raw = _read_canonical(path, "vectors")
    exact_fields(
        value,
        {"vector_version", "fixture_version", "fixture_sha256", "provenance", "scenarios"},
        "vectors",
    )
    if value["vector_version"] != VECTOR_VERSION:
        raise FixtureError(f"vector_version must be {VECTOR_VERSION}")
    if value["fixture_version"] != FIXTURE_VERSION:
        raise FixtureError(f"fixture_version must be {FIXTURE_VERSION}")
    digest = value["fixture_sha256"]
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise FixtureError("fixture_sha256 must be 64 lowercase hex characters")
    _provenance(value["provenance"], "vectors.provenance")
    if type(value["scenarios"]) is not list or not value["scenarios"]:
        raise FixtureError("vectors.scenarios must be a non-empty array")
    for index, scenario in enumerate(value["scenarios"]):
        where = f"vectors.scenarios[{index}]"
        exact_fields(scenario, {"scenario_id", "steps"}, where)
        _identifier(scenario["scenario_id"], f"{where}.scenario_id")
        if type(scenario["steps"]) is not list or not scenario["steps"]:
            raise FixtureError(f"{where}.steps must be a non-empty array")
        for step_index, step in enumerate(scenario["steps"]):
            step_where = f"{where}.steps[{step_index}]"
            exact_fields(
                step, {"step_id", "target", "operation", "result"}, step_where
            )
            _validate_step(
                {
                    "step_id": step["step_id"],
                    "target": step["target"],
                    "operation": step["operation"],
                    "arguments": {},
                },
                step_where,
            )
            _validate_result(step["result"], step_where)
    return value


def _dispatch(step: dict, settlement: SettlementMachine, credit: CreditMachine) -> dict:
    target = step["target"]
    operation = step["operation"]
    machine = settlement if target == "settlement" else credit
    method = getattr(machine, operation)
    try:
        value = method(**step["arguments"])
    except (SettlementError, CreditError) as error:
        result = {"error": {"type": type(error).__name__, "code": error.code}}
    else:
        result = {"ok": value}
    return {
        "step_id": step["step_id"],
        "target": target,
        "operation": operation,
        "result": result,
    }


def _run_scenario(scenario: dict, observer=None) -> tuple[list, SettlementMachine, CreditMachine]:
    settlement = SettlementMachine()
    credit = CreditMachine(settlement)
    results = []
    for step in scenario["steps"]:
        if observer is not None:
            observer(step, settlement, credit)
        results.append(_dispatch(step, settlement, credit))
    return results, settlement, credit


def replay_scenario(scenario: dict, observer=None) -> list:
    """Replay one scenario on fresh machines and return its step records.

    ``observer(step, settlement, credit)`` runs before each dispatch.  It is a
    read-only test seam; it must not mutate the machines.
    """
    return _run_scenario(scenario, observer)[0]


def replay_scenario_with_state(scenario: dict, observer=None) -> tuple[list, SettlementMachine, CreditMachine]:
    """Like :func:`replay_scenario`, but also return the two machines."""
    return _run_scenario(scenario, observer)


def actual_vectors(fixture: dict, fixture_raw: bytes) -> dict:
    """Build the vector-shaped actual output for a validated fixture."""
    return {
        "vector_version": VECTOR_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "fixture_sha256": hashlib.sha256(fixture_raw).hexdigest(),
        "provenance": dict(PROVENANCE),
        "scenarios": [
            {"scenario_id": scenario["scenario_id"], "steps": replay_scenario(scenario)}
            for scenario in fixture["scenarios"]
        ],
    }


def _first_difference(expected: object, actual: object, path: str):
    if type(expected) is not type(actual):
        return path, expected, actual
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return path, expected, actual
        for key in sorted(expected):
            found = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return path, expected, actual
        for index, (left, right) in enumerate(zip(expected, actual)):
            found = _first_difference(left, right, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    if expected != actual:
        return path, expected, actual
    return None


def compare(expected: dict, actual: dict) -> None:
    """Raise VectorMismatch naming the first differing scenario and step."""
    for field in ("vector_version", "fixture_version", "fixture_sha256", "provenance"):
        if expected[field] != actual[field]:
            raise VectorMismatch(
                f"{field}: expected {expected[field]!r}, actual {actual[field]!r}"
            )
    expected_scenarios = expected["scenarios"]
    actual_scenarios = actual["scenarios"]
    if len(expected_scenarios) != len(actual_scenarios):
        raise VectorMismatch(
            f"scenario count: expected {len(expected_scenarios)}, "
            f"actual {len(actual_scenarios)}"
        )
    for expected_scenario, actual_scenario in zip(expected_scenarios, actual_scenarios):
        scenario_id = expected_scenario["scenario_id"]
        if scenario_id != actual_scenario["scenario_id"]:
            raise VectorMismatch(
                f"scenario order: expected {scenario_id!r}, "
                f"actual {actual_scenario['scenario_id']!r}"
            )
        expected_steps = expected_scenario["steps"]
        actual_steps = actual_scenario["steps"]
        if len(expected_steps) != len(actual_steps):
            raise VectorMismatch(
                f"scenario {scenario_id}: step count expected "
                f"{len(expected_steps)}, actual {len(actual_steps)}"
            )
        for expected_step, actual_step in zip(expected_steps, actual_steps):
            if expected_step == actual_step:
                continue
            difference = _first_difference(expected_step, actual_step, "step")
            path, left, right = difference
            raise VectorMismatch(
                f"scenario {scenario_id} step {expected_step['step_id']}: "
                f"{path} expected {left!r}, actual {right!r}"
            )


def replay_pack(fixture_path: object, vectors_path: object) -> list:
    """Replay the pack and require exact equality with the JSON vectors."""
    fixture = load_fixture(fixture_path)
    vectors = load_vectors(vectors_path)
    fixture_raw = Path(fixture_path).read_bytes()
    actual = actual_vectors(fixture, fixture_raw)
    compare(vectors, actual)
    return actual["scenarios"]


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else list(argv)
    if len(arguments) not in (0, 2):
        print(
            "usage: settlement_credit_boundary_vectors.py "
            "[FIXTURE_PATH VECTORS_PATH]",
            file=sys.stderr,
        )
        return 2
    fixture_path = Path(arguments[0]) if arguments else FIXTURE_PATH
    vectors_path = Path(arguments[1]) if arguments else VECTORS_PATH
    try:
        fixture = load_fixture(fixture_path)
        vectors = load_vectors(vectors_path)
        actual = actual_vectors(fixture, Path(fixture_path).read_bytes())
        compare(vectors, actual)
    except VectorMismatch as error:
        print(f"vector mismatch: {error}", file=sys.stderr)
        return 1
    except FixtureError as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(actual))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
