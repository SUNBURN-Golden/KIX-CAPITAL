"""Deterministic tests for the settlement-variance observation contract.

The tests are source-informed, not clean-room: they rebuild the same literal
snapshots with the existing ``MockSettlement`` and ``MockCredit`` machines and
require the fixture bytes to match those machine outputs exactly.

The new coverage is only the cross-contract observation defined in
``docs/contracts/CREDIT_ADVANCE_F04.md`` §7.11.  It adds no protocol command,
FSM phase, error-table entry, OpenAPI byte or product policy value.  Every
number and identifier is a caller-owned fixture literal; provenance is
``MOCK_SETTLEMENT_ONLY`` / ``MOCK_CREDIT_F04_ONLY``.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTLEMENT_DIR = HERE.parent / "settlement_f01_f03"
for _path in (HERE, SETTLEMENT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(1, str(_path))

import settlement_variance as variance  # noqa: E402
from mock_credit import MockCredit  # noqa: E402
from mock_settlement import MockSettlement  # noqa: E402

FIXTURE = HERE / "fixtures" / "settlement_variance_v1.json"
ROOT = HERE.parents[1]

POLICY = {
    "kind": "PRIMARY_FEE_BPS",
    "fee_bps": 500,
    "residual_payee": "organizer",
    "fee_payee": "platform",
}
GROSS = 100000
AMOUNT = 40000


class _BufferOut:
    """Minimal stdout stand-in exposing the binary buffer ``main`` writes."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


def _recognize(claim_id: str, trade_id: str) -> MockSettlement:
    book = MockSettlement()
    book.recognize_claim(
        claim_id,
        trade_id=trade_id,
        gross=GROSS,
        debtor_role="fixture-debtor",
        policy=POLICY,
    )
    return book


def _settle_partial(book: MockSettlement, claim_id: str) -> None:
    book.observe_settlement_statement(
        claim_id,
        movement_id="movement-" + claim_id,
        gross=AMOUNT,
        amount=AMOUNT,
        fee=0,
        tax=0,
        held=0,
        adjustment=0,
    )
    book.apply_distribution(claim_id, order=["organizer", "platform"])


def _note(credit: MockCredit, advance_id: str, face: dict) -> dict:
    credit.note_advance(
        advance_id,
        face=face,
        amount=AMOUNT,
        beneficiary_role="fixture-lender",
    )
    return credit.view_claim(face["claim_id"])


def capture_views() -> dict:
    """Rebuild every fixture scenario with the two existing machines."""
    captured = {}

    book = _recognize("claim-v1", "trade-v1")
    settlement_view = book.view("claim-v1")
    credit = MockCredit()
    captured["V1_face_snapshot_zero"] = (
        settlement_view,
        _note(credit, "advance-v1", settlement_view),
    )

    book = _recognize("claim-v2", "trade-v2")
    before = book.view("claim-v2")
    credit = MockCredit()
    _note(credit, "advance-v2", before)
    _settle_partial(book, "claim-v2")
    after = book.view("claim-v2")
    captured["V2_distribution_after_snapshot_negative"] = (
        after,
        credit.view_claim("claim-v2"),
    )

    book = _recognize("claim-v3", "trade-v3")
    before = book.view("claim-v3")
    credit = MockCredit()
    _note(credit, "advance-v3", before)
    book.bind_refund(
        "claim-v3",
        refund_id="refund-v3",
        amount=GROSS,
        beneficiary_role="fixture-buyer",
        reason="fixture-full-reclassification",
    )
    captured["V3_refund_not_reflected_not_bound"] = (
        book.view("claim-v3"),
        credit.view_claim("claim-v3"),
    )

    book = _recognize("claim-v4", "trade-v4")
    before = book.view("claim-v4")
    _settle_partial(book, "claim-v4")
    after = book.view("claim-v4")
    credit = MockCredit()
    captured["V4_positive_observation_sign"] = (
        before,
        _note(credit, "advance-v4", after),
    )

    pair = captured["V2_distribution_after_snapshot_negative"]
    captured["V5_exact_tolerance_boundary_within"] = pair
    captured["V6_boundary_plus_one_out_of_tolerance"] = pair
    return captured


class SettlementVarianceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = FIXTURE.read_bytes()
        cls.fixture = variance.load_fixture(FIXTURE)
        cls.results = variance.run_scenarios(cls.fixture)
        cls.by_id = {result["id"]: result for result in cls.results}
        cls.scenarios = {
            scenario["id"]: scenario for scenario in cls.fixture["scenarios"]
        }

    # -- fixture integrity ------------------------------------------------

    def test_fixture_is_canonical_and_pinned(self) -> None:
        value = json.loads(self.raw.decode("utf-8"))
        self.assertEqual(self.raw, variance.canonical(value))
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(), variance.FIXTURE_SHA256
        )
        self.assertEqual(value["schema"], variance.SCHEMA)
        self.assertEqual(value["provenance"], variance.PROVENANCE)
        self.assertEqual(value["contract"], variance.CONTRACT)
        self.assertEqual(value["mapping"], variance.MAPPING)
        self.assertEqual(
            value["sign_convention"]["ZERO"],
            "equal at the observed values only",
        )

    def test_fixture_views_are_literal_machine_snapshots(self) -> None:
        captured = capture_views()
        self.assertEqual(set(captured), set(self.scenarios))
        for scenario_id, (settlement_view, credit_view) in captured.items():
            scenario = self.scenarios[scenario_id]
            self.assertEqual(
                scenario["settlement_view"], settlement_view, scenario_id
            )
            self.assertEqual(
                scenario["credit_view"], credit_view, scenario_id
            )
            self.assertEqual(scenario["claim_id"], settlement_view["claim_id"])
            self.assertEqual(scenario["trade_id"], settlement_view["trade_id"])

    def test_all_scenarios_replay_to_expected(self) -> None:
        self.assertEqual(len(self.results), 6)
        self.assertEqual(
            sorted(self.by_id),
            sorted(
                [
                    "V1_face_snapshot_zero",
                    "V2_distribution_after_snapshot_negative",
                    "V3_refund_not_reflected_not_bound",
                    "V4_positive_observation_sign",
                    "V5_exact_tolerance_boundary_within",
                    "V6_boundary_plus_one_out_of_tolerance",
                ]
            ),
        )
        for result in self.results:
            self.assertTrue(result["match"], result["id"])

    # -- formula and sign -------------------------------------------------

    def test_formula_and_sign_convention(self) -> None:
        for scenario in self.fixture["scenarios"]:
            expected = sum(
                item["outstanding"]
                for item in scenario["settlement_view"]["obligations"]
            ) - scenario["credit_view"]["open_face"]
            result = self.by_id[scenario["id"]]
            self.assertEqual(result["record"]["variance"], expected)
            self.assertEqual(
                result["record"]["observable"],
                {
                    "settlement_outstanding": sum(
                        item["outstanding"]
                        for item in scenario["settlement_view"]["obligations"]
                    ),
                    "credit_open_face": scenario["credit_view"]["open_face"],
                },
            )
        self.assertEqual(self.by_id["V1_face_snapshot_zero"]["actual"]["sign"], "ZERO")
        self.assertEqual(
            self.by_id["V2_distribution_after_snapshot_negative"]["actual"][
                "sign"
            ],
            "NEGATIVE",
        )
        self.assertEqual(
            self.by_id["V4_positive_observation_sign"]["actual"]["sign"],
            "POSITIVE",
        )

    # -- tolerance --------------------------------------------------------

    def test_tolerance_is_required_with_no_default(self) -> None:
        scenario = self.scenarios["V1_face_snapshot_zero"]
        with self.assertRaises(variance.VarianceObservationError) as caught:
            variance.observe_settlement_variance(
                copy.deepcopy(scenario["settlement_view"]),
                copy.deepcopy(scenario["credit_view"]),
            )
        self.assertEqual(caught.exception.code, "TOLERANCE_REQUIRED")

    def test_tolerance_rejects_bool_negative_float_string_and_none(self) -> None:
        scenario = self.scenarios["V1_face_snapshot_zero"]
        for value in (True, False, -1, 1.0, 0.5, "10", None):
            with self.subTest(tolerance=value):
                with self.assertRaises(variance.VarianceObservationError) as caught:
                    variance.observe_settlement_variance(
                        copy.deepcopy(scenario["settlement_view"]),
                        copy.deepcopy(scenario["credit_view"]),
                        tolerance=value,
                    )
                self.assertEqual(caught.exception.code, "TOLERANCE_INVALID")

    def test_tolerance_boundary_is_inclusive_and_out_of_tolerance_is_fail_closed(
        self,
    ) -> None:
        scenario = self.scenarios["V2_distribution_after_snapshot_negative"]
        magnitude = abs(scenario["expected"]["variance"])
        at_boundary = variance.observe_settlement_variance(
            copy.deepcopy(scenario["settlement_view"]),
            copy.deepcopy(scenario["credit_view"]),
            tolerance=magnitude,
        )
        beyond = variance.observe_settlement_variance(
            copy.deepcopy(scenario["settlement_view"]),
            copy.deepcopy(scenario["credit_view"]),
            tolerance=magnitude - 1,
        )
        self.assertTrue(at_boundary["within_tolerance"])
        self.assertFalse(beyond["within_tolerance"])
        for record in (at_boundary, beyond):
            self.assertTrue(record["fail_closed"])
            self.assertFalse(record["authorizes_exposure"])
            self.assertFalse(record["mutates_state"])
            self.assertEqual(record["mapping"], variance.MAPPING)
            self.assertEqual(record["refund_component"], "NOT_BOUND")

    # -- view validation --------------------------------------------------

    def test_view_binding_conflict_is_rejected(self) -> None:
        scenario = self.scenarios["V1_face_snapshot_zero"]
        mutations = []
        credit = copy.deepcopy(scenario["credit_view"])
        credit["claim_id"] = "claim-other"
        mutations.append((scenario["settlement_view"], credit))
        credit = copy.deepcopy(scenario["credit_view"])
        credit["trade_id"] = "trade-other"
        mutations.append((scenario["settlement_view"], credit))
        settlement = copy.deepcopy(scenario["settlement_view"])
        settlement["currency"] = "USD"
        mutations.append((settlement, scenario["credit_view"]))
        for settlement_view, credit_view in mutations:
            with self.assertRaises(variance.VarianceObservationError) as caught:
                variance.observe_settlement_variance(
                    settlement_view, credit_view, tolerance=0
                )
            self.assertEqual(caught.exception.code, "VIEW_BINDING_CONFLICT")

    def test_view_must_be_frozen(self) -> None:
        scenario = self.scenarios["V1_face_snapshot_zero"]
        credit = copy.deepcopy(scenario["credit_view"])
        credit["snapshot_frozen"] = False
        with self.assertRaises(variance.VarianceObservationError) as caught:
            variance.observe_settlement_variance(
                scenario["settlement_view"], credit, tolerance=0
            )
        self.assertEqual(caught.exception.code, "VIEW_NOT_FROZEN")

    def test_malformed_and_non_mock_views_are_rejected(self) -> None:
        scenario = self.scenarios["V1_face_snapshot_zero"]
        cases = []
        settlement = copy.deepcopy(scenario["settlement_view"])
        del settlement["obligations"]
        cases.append((settlement, scenario["credit_view"]))
        settlement = copy.deepcopy(scenario["settlement_view"])
        settlement["provenance"] = "SOME_OTHER_PROVENANCE"
        cases.append((settlement, scenario["credit_view"]))
        settlement = copy.deepcopy(scenario["settlement_view"])
        settlement["confirmed_cash"] = 0.0
        cases.append((settlement, scenario["credit_view"]))
        settlement = copy.deepcopy(scenario["settlement_view"])
        settlement["obligations"][0]["outstanding"] = True
        cases.append((settlement, scenario["credit_view"]))
        credit = copy.deepcopy(scenario["credit_view"])
        credit["provenance"] = "SOME_OTHER_PROVENANCE"
        cases.append((scenario["settlement_view"], credit))
        credit = copy.deepcopy(scenario["credit_view"])
        credit["open_face"] = -1
        cases.append((scenario["settlement_view"], credit))
        for settlement_view, credit_view in cases:
            with self.subTest(case=(settlement_view, credit_view)):
                with self.assertRaises(variance.VarianceObservationError) as caught:
                    variance.observe_settlement_variance(
                        settlement_view, credit_view, tolerance=0
                    )
                self.assertEqual(caught.exception.code, "VIEW_INVALID")

    # -- read-only and mapping --------------------------------------------

    def test_observation_is_read_only_and_deterministic(self) -> None:
        scenario = self.scenarios["V2_distribution_after_snapshot_negative"]
        settlement_view = copy.deepcopy(scenario["settlement_view"])
        credit_view = copy.deepcopy(scenario["credit_view"])
        before = copy.deepcopy((settlement_view, credit_view))
        first = variance.observe_settlement_variance(
            settlement_view, credit_view, tolerance=50000
        )
        second = variance.observe_settlement_variance(
            settlement_view, credit_view, tolerance=50000
        )
        self.assertEqual((settlement_view, credit_view), before)
        self.assertEqual(first, second)

    def test_mapping_is_not_bound_and_companions_are_diagnostic(self) -> None:
        for result in self.results:
            record = result["record"]
            self.assertEqual(record["mapping"], variance.MAPPING)
            self.assertTrue(record["fail_closed"])
            self.assertFalse(record["authorizes_exposure"])
            self.assertFalse(record["mutates_state"])
            self.assertEqual(record["refund_component"], "NOT_BOUND")
            self.assertIn("excluded", record["companion"]["note"])
        scenario = self.scenarios["V2_distribution_after_snapshot_negative"]
        record = variance.observe_settlement_variance(
            scenario["settlement_view"], scenario["credit_view"], tolerance=0
        )
        self.assertEqual(record["companion"]["cash_delta"], 40000)
        self.assertEqual(record["companion"]["recovery_delta"], 0)
        self.assertEqual(
            record["variance"],
            sum(
                item["outstanding"]
                for item in scenario["settlement_view"]["obligations"]
            )
            - scenario["credit_view"]["open_face"],
        )
        changed_settlement = copy.deepcopy(scenario["settlement_view"])
        changed_credit = copy.deepcopy(scenario["credit_view"])
        changed_settlement["confirmed_cash"] = 999999
        changed_credit["confirmed_cash_on_face"] = 888888
        changed = variance.observe_settlement_variance(
            changed_settlement, changed_credit, tolerance=0
        )
        self.assertEqual(changed["variance"], record["variance"])
        self.assertNotEqual(
            changed["companion"]["cash_delta"],
            record["companion"]["cash_delta"],
        )

    # -- fixture loader and driver ---------------------------------------

    def test_fixture_loader_rejects_noncanonical_and_pinned_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            value = json.loads(self.raw.decode("utf-8"))
            value["sign_convention"]["ZERO"] = "changed"
            path.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(variance.VarianceObservationError) as caught:
                variance.load_fixture(path)
            self.assertEqual(caught.exception.code, "FIXTURE_INVALID")
            path.write_bytes(variance.canonical(value))
            with self.assertRaises(variance.VarianceObservationError) as caught:
                variance.load_fixture(path)
            self.assertEqual(caught.exception.code, "FIXTURE_PIN_MISMATCH")

    def test_driver_check_exits_zero_and_prints_canonical_json(self) -> None:
        output = _BufferOut()
        original = sys.stdout
        try:
            sys.stdout = output
            code = variance.main(["--check"])
        finally:
            sys.stdout = original
        self.assertEqual(code, 0)
        body = output.buffer.getvalue()
        printed = json.loads(body.decode("utf-8"))
        self.assertEqual(body, variance.canonical(printed))
        self.assertEqual(printed["fixture_sha256"], variance.FIXTURE_SHA256)
        self.assertEqual(
            [item["id"] for item in printed["scenarios"]],
            [result["id"] for result in self.results],
        )
        self.assertEqual(variance.main(["bogus"]), 2)

    # -- contract text ----------------------------------------------------

    def test_contract_clause_and_settlement_cross_reference(self) -> None:
        credit_contract = (
            ROOT / "docs/contracts/CREDIT_ADVANCE_F04.md"
        ).read_text(encoding="utf-8")
        self.assertIn("### 7.11 정산 잔차(settlement variance)", credit_contract)
        self.assertIn("obligations", credit_contract)
        self.assertIn("open_face", credit_contract)
        self.assertIn("tolerance", credit_contract)
        self.assertIn("NOT_BOUND", credit_contract)
        self.assertIn("no default", credit_contract)
        settlement_contract = (
            ROOT / "docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md"
        ).read_text(encoding="utf-8")
        self.assertIn("CREDIT_ADVANCE_F04.md §7.11", settlement_contract)
        self.assertIn("정산 잔차", settlement_contract)


if __name__ == "__main__":
    unittest.main()
