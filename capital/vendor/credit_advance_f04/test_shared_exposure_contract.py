"""Deterministic tests for the shared-exposure observation contract.

The tests are source-informed, not clean-room: they rebuild the same literal
snapshots with the existing ``MockSettlement`` and ``CreditMachine`` machines
and require the fixture bytes to match those machine outputs exactly.

The new coverage is only the caller-grouped observation defined in
``docs/contracts/CREDIT_ADVANCE_F04.md`` §7.12.  It adds no protocol command,
FSM phase, error-table entry, OpenAPI byte or product policy value.  Every
number and identifier is a caller-owned fixture literal; provenance is
``MOCK_CREDIT_F04_ONLY`` and the exposure ledger is ``MOCK_EXPOSURE``.

Existing per-claim ceiling and freeze coverage is cited, not duplicated:
``test_mock_credit.py::CreditAdvanceMockTests.test_claims_do_not_share_a_ceiling_and_the_snapshot_stays_frozen``,
``test_credit_properties.py::MachinePropertyTests.test_the_face_snapshot_stays_frozen_after_later_settlement_changes``
and the boundary pack's S5/S6 scenarios.
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

import shared_exposure as exposure  # noqa: E402
import settlement_variance as variance  # noqa: E402
from credit_fsm import CreditMachine  # noqa: E402
from mock_settlement import MockSettlement  # noqa: E402

FIXTURE = HERE / "fixtures" / "shared_exposure_v1.json"
ROOT = HERE.parents[1]

POLICY = {
    "kind": "PRIMARY_FEE_BPS",
    "fee_bps": 500,
    "residual_payee": "organizer",
    "fee_payee": "platform",
}
GROSS = 100000

SCENARIO_IDS = [
    "E1_two_advances_one_claim_exact_limit",
    "E2_two_claims_one_debtor_label_over_limit",
    "E3_pool_three_claims_default_still_aggregates",
    "E4_refund_after_freeze_face_unchanged",
    "E5_exact_limit_boundary_within",
    "E6_repay_then_close_reservation_released",
]


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


def _draw(machine: CreditMachine, advance_id: str, face: dict, amount: int) -> None:
    machine.offer(
        advance_id,
        idempotency_key="offer-" + advance_id,
        face=face,
        amount=amount,
        beneficiary_role="fixture-lender",
    )
    machine.approve(advance_id, idempotency_key="approve-" + advance_id)
    machine.draw(
        advance_id,
        idempotency_key="draw-" + advance_id,
        draw_id="draw-" + advance_id,
    )


def _e6_machine() -> CreditMachine:
    """Rebuild E6 through draw, partial repay, full repay and close."""
    book = _recognize("claim-e6", "trade-e6")
    face = book.view("claim-e6")
    machine = CreditMachine()
    _draw(machine, "adv-e6-1", face, 40000)
    _draw(machine, "adv-e6-2", face, 30000)
    machine.repay(
        "adv-e6-1",
        idempotency_key="repay-1-adv-e6-1",
        repay_id="rp-e6-1",
        sequence=1,
        amount=15000,
    )
    machine.repay(
        "adv-e6-1",
        idempotency_key="repay-2-adv-e6-1",
        repay_id="rp-e6-2",
        sequence=2,
        amount=25000,
    )
    machine.close("adv-e6-1", idempotency_key="close-adv-e6-1")
    return machine


def capture_views() -> dict:
    """Rebuild every fixture scenario with the existing machines.

    Returns ``{scenario_id: (group_id, credit_views, limit)}`` where each view
    is a literal ``CreditMachine.view`` snapshot.
    """
    captured = {}

    book = _recognize("claim-e1", "trade-e1")
    face = book.view("claim-e1")
    machine = CreditMachine()
    _draw(machine, "adv-e1-1", face, 40000)
    _draw(machine, "adv-e1-2", face, 30000)
    captured["E1_two_advances_one_claim_exact_limit"] = (
        "group-e1",
        [machine.view("adv-e1-1"), machine.view("adv-e1-2")],
        70000,
    )

    book_a = _recognize("claim-e2-a", "trade-e2-a")
    book_b = _recognize("claim-e2-b", "trade-e2-b")
    machine = CreditMachine()
    _draw(machine, "adv-e2-a", book_a.view("claim-e2-a"), 60000)
    _draw(machine, "adv-e2-b", book_b.view("claim-e2-b"), 50000)
    captured["E2_two_claims_one_debtor_label_over_limit"] = (
        "debtor-e2",
        [machine.view("adv-e2-a"), machine.view("adv-e2-b")],
        100000,
    )

    machine = CreditMachine()
    for claim_id, advance_id, amount in (
        ("claim-e3-a", "adv-e3-a", 40000),
        ("claim-e3-b", "adv-e3-b", 30000),
        ("claim-e3-c", "adv-e3-c", 20000),
    ):
        book = _recognize(claim_id, "trade-" + claim_id)
        _draw(machine, advance_id, book.view(claim_id), amount)
    machine.default(
        "adv-e3-b",
        idempotency_key="default-adv-e3-b",
        reason="fixture-default-label",
    )
    captured["E3_pool_three_claims_default_still_aggregates"] = (
        "pool-e3",
        [
            machine.view("adv-e3-a"),
            machine.view("adv-e3-b"),
            machine.view("adv-e3-c"),
        ],
        90000,
    )

    book = _recognize("claim-e4", "trade-e4")
    face = book.view("claim-e4")
    machine = CreditMachine()
    _draw(machine, "adv-e4", face, 40000)
    book.bind_refund(
        "claim-e4",
        refund_id="refund-e4",
        amount=GROSS,
        beneficiary_role="fixture-buyer",
        reason="fixture-full-reclassification",
    )
    captured["E4_refund_after_freeze_face_unchanged"] = (
        "group-e4",
        [machine.view("adv-e4")],
        40000,
    )

    group_id, views, _over = captured["E2_two_claims_one_debtor_label_over_limit"]
    captured["E5_exact_limit_boundary_within"] = (group_id, views, 110000)

    machine = _e6_machine()
    captured["E6_repay_then_close_reservation_released"] = (
        "group-e6",
        [machine.view("adv-e6-1"), machine.view("adv-e6-2")],
        30000,
    )
    return captured


class SharedExposureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = FIXTURE.read_bytes()
        cls.fixture = exposure.load_fixture(FIXTURE)
        cls.results = exposure.run_scenarios(cls.fixture)
        cls.by_id = {result["id"]: result for result in cls.results}
        cls.scenarios = {
            scenario["id"]: scenario for scenario in cls.fixture["scenarios"]
        }

    # -- fixture integrity ------------------------------------------------

    def test_fixture_is_canonical_and_pinned(self) -> None:
        value = json.loads(self.raw.decode("utf-8"))
        self.assertEqual(self.raw, exposure.canonical(value))
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(), exposure.FIXTURE_SHA256
        )
        self.assertEqual(value["schema"], exposure.SCHEMA)
        self.assertEqual(value["provenance"], exposure.PROVENANCE)
        self.assertEqual(value["contract"], exposure.CONTRACT)
        self.assertEqual(value["mapping"], exposure.MAPPING)
        self.assertEqual(
            [scenario["id"] for scenario in value["scenarios"]], SCENARIO_IDS
        )

    def test_fixture_views_are_literal_machine_snapshots(self) -> None:
        captured = capture_views()
        self.assertEqual(set(captured), set(self.scenarios))
        for scenario_id, (group_id, views, limit) in captured.items():
            scenario = self.scenarios[scenario_id]
            self.assertEqual(scenario["group_id"], group_id, scenario_id)
            self.assertEqual(scenario["credit_views"], views, scenario_id)
            self.assertEqual(scenario["limit"], limit, scenario_id)
            for view in views:
                self.assertEqual(view["provenance"], "MOCK_CREDIT_F04_ONLY")
                self.assertEqual(view["exposure_ledger"], "MOCK_EXPOSURE")
                self.assertIs(view["snapshot_frozen"], True)

    def test_all_scenarios_replay_to_expected(self) -> None:
        self.assertEqual(len(self.results), 6)
        self.assertEqual(sorted(self.by_id), sorted(SCENARIO_IDS))
        for result in self.results:
            self.assertTrue(result["match"], result["id"])

    # -- aggregation ------------------------------------------------------

    def test_aggregation_formulas_over_exposed_values_only(self) -> None:
        for scenario in self.fixture["scenarios"]:
            views = scenario["credit_views"]
            record = self.by_id[scenario["id"]]["record"]
            observable = record["observable"]
            self.assertEqual(
                observable["group_outstanding_exposure"],
                sum(view["outstanding_exposure"] for view in views),
            )
            self.assertEqual(
                observable["group_drawn_exposure"],
                sum(view["drawn_exposure"] for view in views),
            )
            self.assertEqual(
                observable["group_repaid_exposure"],
                sum(view["repaid_exposure"] for view in views),
            )
            claims = {}
            for view in views:
                claims.setdefault(view["claim_id"], view)
            self.assertEqual(
                observable["group_open_face"],
                sum(claim["open_face"] for claim in claims.values()),
            )
            self.assertEqual(
                observable["group_reserved_open"],
                sum(claim["reserved_open"] for claim in claims.values()),
            )
            self.assertEqual(
                observable["group_residual_unreserved"],
                observable["group_open_face"] - observable["group_reserved_open"],
            )
            self.assertEqual(record["advance_count"], len(views))
            self.assertEqual(record["claim_count"], len(claims))
            self.assertEqual(
                [entry["claim_id"] for entry in record["claims"]], sorted(claims)
            )
            for entry in record["claims"]:
                source = claims[entry["claim_id"]]
                for field in ("trade_id", "open_face", "reserved_open", "residual_unreserved"):
                    self.assertEqual(entry[field], source[field])
                self.assertEqual(
                    entry["advance_ids"],
                    sorted(
                        view["advance_id"]
                        for view in views
                        if view["claim_id"] == entry["claim_id"]
                    ),
                )

    def test_cross_claim_grouping_is_caller_supplied_and_not_machine_enforced(
        self,
    ) -> None:
        scenario = self.scenarios["E2_two_claims_one_debtor_label_over_limit"]
        record = self.by_id[scenario["id"]]["record"]
        self.assertEqual(scenario["group_id"], "debtor-e2")
        self.assertEqual(record["claim_count"], 2)
        self.assertEqual(record["advance_count"], 2)
        self.assertEqual(record["observable"]["group_outstanding_exposure"], 110000)
        self.assertFalse(record["within_limit"])
        self.assertTrue(record["fail_closed"])
        self.assertFalse(record["legal_debtor_bound"])
        # Both draws were accepted: the machine enforces only per-claim
        # ceilings (§3/§7.2), never the caller's group limit.
        self.assertEqual(
            {view["phase"] for view in scenario["credit_views"]}, {"DRAWN"}
        )
        for view in scenario["credit_views"]:
            self.assertNotIn("debtor_role", view)
            self.assertIs(view["legal_debtor_bound"], False)
            self.assertIs(view["priority_bound"], False)

    def test_defaulted_advance_still_aggregates(self) -> None:
        scenario = self.scenarios["E3_pool_three_claims_default_still_aggregates"]
        record = self.by_id[scenario["id"]]["record"]
        defaulted = [
            view for view in scenario["credit_views"] if view["phase"] == "DEFAULTED"
        ]
        self.assertEqual(len(defaulted), 1)
        self.assertEqual(defaulted[0]["outstanding_exposure"], 30000)
        self.assertEqual(defaulted[0]["note_status"], "NOTED")
        self.assertEqual(record["claim_count"], 3)
        self.assertEqual(record["observable"]["group_outstanding_exposure"], 90000)
        self.assertEqual(record["observable"]["group_reserved_open"], 90000)
        self.assertTrue(record["within_limit"])

    # -- limit --------------------------------------------------------------

    def test_limit_is_required_with_no_default(self) -> None:
        scenario = self.scenarios["E1_two_advances_one_claim_exact_limit"]
        with self.assertRaises(exposure.SharedExposureError) as caught:
            exposure.observe_shared_exposure(
                scenario["group_id"], copy.deepcopy(scenario["credit_views"])
            )
        self.assertEqual(caught.exception.code, "LIMIT_REQUIRED")

    def test_limit_rejects_bool_negative_float_string_and_none(self) -> None:
        scenario = self.scenarios["E1_two_advances_one_claim_exact_limit"]
        for value in (True, False, -1, 1.0, 0.5, "10", None):
            with self.subTest(limit=value):
                with self.assertRaises(exposure.SharedExposureError) as caught:
                    exposure.observe_shared_exposure(
                        scenario["group_id"],
                        copy.deepcopy(scenario["credit_views"]),
                        limit=value,
                    )
                self.assertEqual(caught.exception.code, "LIMIT_INVALID")

    def test_limit_boundary_is_inclusive_and_over_limit_is_fail_closed(self) -> None:
        scenario = self.scenarios["E5_exact_limit_boundary_within"]
        total = sum(
            view["outstanding_exposure"] for view in scenario["credit_views"]
        )
        self.assertEqual(scenario["limit"], total)
        at_boundary = exposure.observe_shared_exposure(
            scenario["group_id"],
            copy.deepcopy(scenario["credit_views"]),
            limit=total,
        )
        beyond = exposure.observe_shared_exposure(
            scenario["group_id"],
            copy.deepcopy(scenario["credit_views"]),
            limit=total - 1,
        )
        self.assertTrue(at_boundary["within_limit"])
        self.assertFalse(beyond["within_limit"])
        for record in (at_boundary, beyond):
            self.assertTrue(record["fail_closed"])
            self.assertFalse(record["authorizes_exposure"])
            self.assertFalse(record["mutates_state"])
            self.assertEqual(record["mapping"], exposure.MAPPING)
            self.assertEqual(record["refund_component"], "NOT_BOUND")

    # -- freeze and transitions ---------------------------------------------

    def test_frozen_face_unchanged_after_settlement_refund(self) -> None:
        book = _recognize("claim-e4", "trade-e4")
        face = book.view("claim-e4")
        machine = CreditMachine()
        _draw(machine, "adv-e4", face, 40000)
        before = machine.view("adv-e4")
        book.bind_refund(
            "claim-e4",
            refund_id="refund-e4",
            amount=GROSS,
            beneficiary_role="fixture-buyer",
            reason="fixture-full-reclassification",
        )
        after = machine.view("adv-e4")
        self.assertEqual(before, after)
        self.assertEqual(after["open_face"], GROSS)
        self.assertEqual(after["outstanding_exposure"], 40000)
        scenario = self.scenarios["E4_refund_after_freeze_face_unchanged"]
        self.assertEqual(scenario["credit_views"], [after])
        record = self.by_id[scenario["id"]]["record"]
        self.assertEqual(record["observable"]["group_open_face"], GROSS)
        self.assertEqual(record["observable"]["group_outstanding_exposure"], 40000)
        self.assertEqual(record["refund_component"], "NOT_BOUND")
        # The refund-driven per-claim gap stays §7.11 territory: the
        # settlement view now reports zero outstanding against the frozen
        # face, and that variance observation is NOT_BOUND, not a repair.
        gap = variance.observe_settlement_variance(
            book.view("claim-e4"), machine.view_claim("claim-e4"), tolerance=0
        )
        self.assertEqual(gap["variance"], -GROSS)
        self.assertFalse(gap["within_tolerance"])
        self.assertEqual(gap["mapping"]["contract_status"], "NOT_BOUND")

    def test_repay_then_close_moves_exposure_only_via_transitions(self) -> None:
        book = _recognize("claim-e6", "trade-e6")
        face = book.view("claim-e6")
        machine = CreditMachine()
        _draw(machine, "adv-e6-1", face, 40000)
        _draw(machine, "adv-e6-2", face, 30000)

        def observe() -> dict:
            return exposure.observe_shared_exposure(
                "group-e6",
                [machine.view("adv-e6-1"), machine.view("adv-e6-2")],
                limit=70000,
            )

        drawn = observe()
        self.assertEqual(drawn["observable"]["group_outstanding_exposure"], 70000)
        self.assertEqual(drawn["observable"]["group_reserved_open"], 70000)
        machine.repay(
            "adv-e6-1",
            idempotency_key="repay-1-adv-e6-1",
            repay_id="rp-e6-1",
            sequence=1,
            amount=15000,
        )
        partial = observe()
        self.assertEqual(partial["observable"]["group_outstanding_exposure"], 55000)
        # Partial repayment keeps the reservation (§7.2).
        self.assertEqual(partial["observable"]["group_reserved_open"], 70000)
        machine.repay(
            "adv-e6-1",
            idempotency_key="repay-2-adv-e6-1",
            repay_id="rp-e6-2",
            sequence=2,
            amount=25000,
        )
        machine.close("adv-e6-1", idempotency_key="close-adv-e6-1")
        final = observe()
        self.assertEqual(final["observable"]["group_outstanding_exposure"], 30000)
        self.assertEqual(final["observable"]["group_drawn_exposure"], 70000)
        self.assertEqual(final["observable"]["group_repaid_exposure"], 40000)
        # Only close releases the reservation, and only at zero exposure.
        self.assertEqual(final["observable"]["group_reserved_open"], 30000)
        self.assertEqual(final["observable"]["group_residual_unreserved"], 70000)
        scenario = self.scenarios["E6_repay_then_close_reservation_released"]
        self.assertEqual(
            scenario["credit_views"],
            [machine.view("adv-e6-1"), machine.view("adv-e6-2")],
        )
        self.assertEqual(
            self.by_id[scenario["id"]]["record"]["observable"], final["observable"]
        )

    # -- view validation ----------------------------------------------------

    def test_view_binding_conflict_is_rejected(self) -> None:
        scenario = self.scenarios["E1_two_advances_one_claim_exact_limit"]
        mutations = []
        views = copy.deepcopy(scenario["credit_views"])
        views[1]["reserved_open"] += 1
        views[1]["residual_unreserved"] -= 1
        mutations.append(views)
        views = copy.deepcopy(scenario["credit_views"])
        views[1]["trade_id"] = "trade-other"
        mutations.append(views)
        views = copy.deepcopy(scenario["credit_views"])
        views[1]["open_face"] += 1
        views[1]["residual_unreserved"] += 1
        mutations.append(views)
        views = copy.deepcopy(scenario["credit_views"])
        views[0]["currency"] = "USD"
        mutations.append(views)
        for views in mutations:
            with self.assertRaises(exposure.SharedExposureError) as caught:
                exposure.observe_shared_exposure(
                    scenario["group_id"], views, limit=0
                )
            self.assertEqual(caught.exception.code, "VIEW_BINDING_CONFLICT")

    def test_view_must_be_frozen(self) -> None:
        scenario = self.scenarios["E1_two_advances_one_claim_exact_limit"]
        views = copy.deepcopy(scenario["credit_views"])
        views[0]["snapshot_frozen"] = False
        with self.assertRaises(exposure.SharedExposureError) as caught:
            exposure.observe_shared_exposure(scenario["group_id"], views, limit=0)
        self.assertEqual(caught.exception.code, "VIEW_NOT_FROZEN")
        # A real pre-draw view is unfrozen: grouping it is undefined in this
        # revision and fails closed.
        book = _recognize("claim-pre", "trade-pre")
        machine = CreditMachine()
        machine.offer(
            "adv-pre",
            idempotency_key="offer-adv-pre",
            face=book.view("claim-pre"),
            amount=10000,
            beneficiary_role="fixture-lender",
        )
        machine.approve("adv-pre", idempotency_key="approve-adv-pre")
        pre_draw = machine.view("adv-pre")
        self.assertIs(pre_draw["snapshot_frozen"], False)
        with self.assertRaises(exposure.SharedExposureError) as caught:
            exposure.observe_shared_exposure("group-pre", [pre_draw], limit=0)
        self.assertEqual(caught.exception.code, "VIEW_NOT_FROZEN")

    def test_malformed_and_non_mock_views_are_rejected(self) -> None:
        scenario = self.scenarios["E1_two_advances_one_claim_exact_limit"]
        base = scenario["credit_views"]
        cases = []

        def mutated(**changes) -> list:
            views = copy.deepcopy(base)
            views[0].update(changes)
            return views

        view = copy.deepcopy(base[0])
        del view["outstanding_exposure"]
        cases.append([view])
        cases.append(mutated(provenance="SOME_OTHER_PROVENANCE"))
        cases.append(mutated(exposure_ledger="SOME_OTHER_LEDGER"))
        cases.append(mutated(outstanding_exposure=True))
        cases.append(mutated(drawn_exposure=-1))
        cases.append(mutated(repaid_exposure=1.0))
        cases.append(mutated(open_face=exposure.MONEY_MAX + 1))
        cases.append(mutated(outstanding_exposure=base[0]["outstanding_exposure"] + 1))
        cases.append(mutated(residual_unreserved=base[0]["residual_unreserved"] + 1))
        cases.append(mutated(phase="OFFERED"))
        cases.append(mutated(advance_id=" x"))
        cases.append([copy.deepcopy(base[0]), copy.deepcopy(base[0])])
        cases.append([])
        for views in cases:
            with self.subTest(case=views):
                with self.assertRaises(exposure.SharedExposureError) as caught:
                    exposure.observe_shared_exposure(
                        scenario["group_id"], views, limit=0
                    )
                self.assertEqual(caught.exception.code, "VIEW_INVALID")
        for group_id in ("", " x", 123, True, None):
            with self.subTest(group_id=group_id):
                with self.assertRaises(exposure.SharedExposureError) as caught:
                    exposure.observe_shared_exposure(
                        group_id, copy.deepcopy(base), limit=0
                    )
                self.assertEqual(caught.exception.code, "VIEW_INVALID")
        with self.assertRaises(exposure.SharedExposureError) as caught:
            exposure.observe_shared_exposure(
                scenario["group_id"], {"not": "a list"}, limit=0
            )
        self.assertEqual(caught.exception.code, "VIEW_INVALID")

    # -- read-only and mapping ----------------------------------------------

    def test_observation_is_read_only_and_deterministic(self) -> None:
        scenario = self.scenarios["E3_pool_three_claims_default_still_aggregates"]
        views = copy.deepcopy(scenario["credit_views"])
        before = copy.deepcopy(views)
        first = exposure.observe_shared_exposure(
            scenario["group_id"], views, limit=90000
        )
        second = exposure.observe_shared_exposure(
            scenario["group_id"], views, limit=90000
        )
        self.assertEqual(views, before)
        self.assertEqual(first, second)

    def test_mapping_is_not_bound_and_execution_flags_stay_false(self) -> None:
        for result in self.results:
            record = result["record"]
            self.assertEqual(record["mapping"], exposure.MAPPING)
            self.assertTrue(record["fail_closed"])
            self.assertFalse(record["authorizes_exposure"])
            self.assertFalse(record["mutates_state"])
            self.assertFalse(record["legal_debtor_bound"])
            self.assertEqual(record["refund_component"], "NOT_BOUND")
        flag_names = (
            "funds_executed",
            "bank_debit_observed",
            "repayment_observed",
            "interest_defined",
            "economic_finality_claimed",
            "underwriting_executed",
            "kyc_executed",
            "legal_debtor_bound",
            "priority_bound",
            "collateral_perfected",
            "durable",
            "ownership_mutated",
            "ticket_ownership_authoritative",
        )
        for scenario in self.fixture["scenarios"]:
            for view in scenario["credit_views"]:
                for name in flag_names:
                    self.assertIs(view[name], False, (scenario["id"], name))

    # -- fixture loader and driver ------------------------------------------

    def test_fixture_loader_rejects_noncanonical_and_pinned_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            value = json.loads(self.raw.decode("utf-8"))
            value["scenarios"][0]["limit"] += 1
            path.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(exposure.SharedExposureError) as caught:
                exposure.load_fixture(path)
            self.assertEqual(caught.exception.code, "FIXTURE_INVALID")
            path.write_bytes(exposure.canonical(value))
            with self.assertRaises(exposure.SharedExposureError) as caught:
                exposure.load_fixture(path)
            self.assertEqual(caught.exception.code, "FIXTURE_PIN_MISMATCH")

    def test_driver_check_exits_zero_and_prints_canonical_json(self) -> None:
        output = _BufferOut()
        original = sys.stdout
        try:
            sys.stdout = output
            code = exposure.main(["--check"])
        finally:
            sys.stdout = original
        self.assertEqual(code, 0)
        body = output.buffer.getvalue()
        printed = json.loads(body.decode("utf-8"))
        self.assertEqual(body, exposure.canonical(printed))
        self.assertEqual(printed["fixture_sha256"], exposure.FIXTURE_SHA256)
        self.assertEqual(
            [item["id"] for item in printed["scenarios"]],
            [result["id"] for result in self.results],
        )
        self.assertEqual(exposure.main(["bogus"]), 2)

    # -- contract text --------------------------------------------------------

    def test_contract_clause_and_settlement_cross_reference(self) -> None:
        credit_contract = (
            ROOT / "docs/contracts/CREDIT_ADVANCE_F04.md"
        ).read_text(encoding="utf-8")
        self.assertIn("### 7.12 공유 노출(shared exposure)", credit_contract)
        self.assertIn("group_outstanding_exposure", credit_contract)
        self.assertIn("MOCK_EXPOSURE", credit_contract)
        self.assertIn("snapshot_frozen", credit_contract)
        self.assertIn("limit", credit_contract)
        self.assertIn("no default", credit_contract)
        self.assertIn("NOT_BOUND", credit_contract)
        settlement_contract = (
            ROOT / "docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md"
        ).read_text(encoding="utf-8")
        self.assertIn("CREDIT_ADVANCE_F04.md §7.12", settlement_contract)
        self.assertIn("공유 노출", settlement_contract)


if __name__ == "__main__":
    unittest.main()
