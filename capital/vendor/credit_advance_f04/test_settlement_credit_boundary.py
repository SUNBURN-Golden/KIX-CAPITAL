"""Cross-boundary settlement (F01-F03) to credit (F04) vector tests.

This module adds only the consumer-replay gap between the two existing
machines.  It does not re-tests behaviour that already has deterministic
coverage:

- captured-versus-committed settlement gate and the no-finality draw:
  ``reference/credit_advance_f04/fixtures/settlement_gates.jsonl`` and
  ``test_credit_fsm.py::CreditFsmTests.test_bound_draw_waits_for_mock_commit_and_does_not_claim_finality``.
- the Class B observation that the credit gate does not read the settlement
  view's refund fields:
  ``test_credit_properties.py::ClassBCharacterizationTests.test_b_the_gate_does_not_read_refund_fields_of_the_settlement_view``.

The new coverage is the literal, consumer-replayable boundary: a caller
embeds a settlement ``claim`` snapshot in ``CreditMachine.offer(face=...)``
without derivation, and the exact resulting step vectors are frozen in
``fixtures/settlement_credit_boundary_vectors_v1.json``.

All fixtures are synthetic (``MOCK_SETTLEMENT_ONLY`` /
``MOCK_CREDIT_F04_ONLY``).  Numbers and identifiers are caller-owned
literals, not product policy.  Nothing here asserts durability, finality,
bank exactly-once, or production readiness.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(1, str(HERE))

import settlement_credit_boundary_vectors as boundary  # noqa: E402
from credit_fsm import CreditMachine  # noqa: E402
from settlement_fsm import SettlementMachine  # noqa: E402

FIXTURE = HERE / "fixtures" / "settlement_credit_boundary_v1.json"
VECTORS = HERE / "fixtures" / "settlement_credit_boundary_vectors_v1.json"

S1 = "S1_captured_face_no_derivation"
S2 = "S2_committed_face_no_derivation"
S3 = "S3_face_snapshot_frozen_and_stable_view_claim"
S4 = "S4_refund_obligation_partial_acceptance"
S5 = "S5_shared_exposure_two_advances"
S6 = "S6_reconciliation_gap_reported_no_repair"

GAP_REPORT = {
    "code": "SETTLEMENT_REFUND_NOT_REFLECTED_IN_CREDIT_FACE",
    "contract_status": "UNDEFINED",
    "repair": "NONE",
}


class _BufferOut:
    """Minimal stdout stand-in exposing the binary buffer ``main`` writes."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


class SettlementCreditBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_raw = FIXTURE.read_bytes()
        cls.vectors_raw = VECTORS.read_bytes()
        cls.fixture = boundary.load_fixture(FIXTURE)
        cls.vectors = boundary.load_vectors(VECTORS)
        cls.actual = boundary.actual_vectors(cls.fixture, cls.fixture_raw)
        cls.scenarios = {
            scenario["scenario_id"]: scenario for scenario in cls.actual["scenarios"]
        }

    # -- helpers ---------------------------------------------------------

    def _steps(self, scenario_id: str) -> dict:
        return {
            step["step_id"]: step for step in self.scenarios[scenario_id]["steps"]
        }

    def _fixture_steps(self, scenario_id: str) -> dict:
        for scenario in self.fixture["scenarios"]:
            if scenario["scenario_id"] == scenario_id:
                return {step["step_id"]: step for step in scenario["steps"]}
        raise KeyError(scenario_id)

    def _ok(self, scenario_id: str, step_id: str) -> dict:
        result = self._steps(scenario_id)[step_id]["result"]
        self.assertIn("ok", result, f"{scenario_id} {step_id} unexpectedly failed")
        return result["ok"]

    def _error_code(self, scenario_id: str, step_id: str) -> str:
        result = self._steps(scenario_id)[step_id]["result"]
        self.assertIn("error", result, f"{scenario_id} {step_id} unexpectedly passed")
        return result["error"]["code"]

    def _offer_observations(self) -> dict:
        observations = {}
        for scenario in self.fixture["scenarios"]:
            scenario_id = scenario["scenario_id"]

            def observer(step, settlement, credit, scenario_id=scenario_id):
                if step["operation"] != "offer":
                    return
                face = step["arguments"]["face"]
                observations[(scenario_id, step["step_id"])] = {
                    "face": copy.deepcopy(face),
                    "settlement_claim": copy.deepcopy(
                        settlement.view(face["claim_id"])["claim"]
                    ),
                }

            boundary.replay_scenario(scenario, observer=observer)
        return observations

    # -- pack integrity --------------------------------------------------

    def test_pack_files_are_canonical_and_hash_pinned(self) -> None:
        self.assertEqual(boundary.canonical(self.fixture), self.fixture_raw)
        self.assertEqual(boundary.canonical(self.vectors), self.vectors_raw)
        self.assertTrue(self.fixture_raw.endswith(b"\n"))
        self.assertTrue(self.vectors_raw.endswith(b"\n"))
        self.assertEqual(
            self.vectors["fixture_sha256"],
            hashlib.sha256(self.fixture_raw).hexdigest(),
        )
        expected_provenance = {
            "settlement": "MOCK_SETTLEMENT_ONLY",
            "credit": "MOCK_CREDIT_F04_ONLY",
        }
        self.assertEqual(self.fixture["provenance"], expected_provenance)
        self.assertEqual(self.vectors["provenance"], expected_provenance)
        self.assertIs(self.fixture["synthetic_only"], True)

    def test_vector_pack_replays_exactly(self) -> None:
        self.assertEqual(
            boundary.replay_pack(FIXTURE, VECTORS), self.vectors["scenarios"]
        )
        out = _BufferOut()
        with mock.patch("sys.stdout", out):
            self.assertEqual(boundary.main([str(FIXTURE), str(VECTORS)]), 0)
        self.assertEqual(out.buffer.getvalue(), boundary.canonical(self.actual))

    def test_driver_reports_a_mismatch_and_exits_one(self) -> None:
        mutated = copy.deepcopy(self.vectors)
        last = mutated["scenarios"][0]["steps"][-1]
        last["result"]["ok"]["funds_executed"] = True
        with tempfile.TemporaryDirectory() as directory:
            bad_vectors = Path(directory) / "vectors.json"
            bad_vectors.write_bytes(boundary.canonical(mutated))
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                status = boundary.main([str(FIXTURE), str(bad_vectors)])
        self.assertEqual(status, 1)
        self.assertIn(S1, error.getvalue())
        self.assertIn(last["step_id"], error.getvalue())

    def test_every_acceptance_tag_has_a_scenario(self) -> None:
        required = {
            "captured_claim_snapshot_embedded_as_face",
            "committed_claim_snapshot_embedded_as_face",
            "no_face_derivation",
            "early_draw_rejected_not_committed",
            "frozen_face_kept_after_settlement_commit",
            "face_snapshot_frozen",
            "modified_face_draw_rejected",
            "view_claim_stable_after_settlement_refund",
            "refund_obligation_visible",
            "partial_acceptance_accounted",
            "credit_face_has_no_refund_fields",
            "funds_executed_false",
            "shared_exposure_two_advances",
            "caller_supplied_limits_only",
            "over_ceiling_rejected_without_state_change",
            "reservation_exhausted_exactly",
            "reconciliation_gap_reported",
            "no_automatic_repair",
            "settlement_refund_not_in_credit_face",
            "reconcile_matches_without_repair",
        }
        seen = set()
        for scenario in self.fixture["scenarios"]:
            seen.update(scenario["acceptance"])
        self.assertEqual(required - seen, set())
        self.assertEqual(
            {scenario["scenario_id"] for scenario in self.fixture["scenarios"]},
            {S1, S2, S3, S4, S5, S6},
        )

    def test_fixture_uses_only_existing_public_machine_methods(self) -> None:
        settlement = SettlementMachine()
        credit = CreditMachine(settlement)
        for scenario in self.fixture["scenarios"]:
            for step in scenario["steps"]:
                machine = settlement if step["target"] == "settlement" else credit
                operation = step["operation"]
                self.assertFalse(operation.startswith("_"))
                self.assertTrue(
                    callable(getattr(machine, operation)),
                    f"{operation} is not a public {step['target']} method",
                )
                if operation == "offer":
                    self.assertNotIn("product", step["arguments"])

    # -- embedded literal claim snapshot, no derivation ------------------

    def test_embedded_face_is_a_literal_claim_snapshot(self) -> None:
        observations = self._offer_observations()
        for scenario in self.fixture["scenarios"]:
            scenario_id = scenario["scenario_id"]
            offers = [
                step for step in scenario["steps"] if step["operation"] == "offer"
            ]
            self.assertTrue(offers, scenario_id)
            if scenario_id in (S1, S2, S4, S5):
                for step in offers:
                    observed = observations[(scenario_id, step["step_id"])]
                    self.assertEqual(
                        observed["face"],
                        observed["settlement_claim"],
                        f"{scenario_id} {step['step_id']} face was not copied "
                        "literally from the settlement claim",
                    )
            elif scenario_id == S3:
                frozen = observations[(scenario_id, "s3-offer-frozen")]
                self.assertEqual(frozen["face"], frozen["settlement_claim"])
                later = observations[(scenario_id, "s3-offer-later")]
                base = {
                    key: value
                    for key, value in later["face"].items()
                    if key != "caller_mark"
                }
                self.assertEqual(base, later["settlement_claim"])
                self.assertEqual(later["face"]["caller_mark"], "later")
            elif scenario_id == S6:
                first = observations[(scenario_id, "s6-offer-1")]
                second = observations[(scenario_id, "s6-offer-2")]
                self.assertEqual(first["face"], first["settlement_claim"])
                self.assertEqual(second["face"], first["face"])
                self.assertEqual(second["settlement_claim"]["refund_face"], 40000)
                self.assertEqual(second["face"]["refund_face"], 0)

    def test_credit_journal_stores_the_literal_face(self) -> None:
        for scenario in self.fixture["scenarios"]:
            _results, _settlement, credit = boundary.replay_scenario_with_state(
                scenario
            )
            journal = credit.export_journal()
            offers = {
                entry["advance_id"]: entry
                for entry in journal
                if entry["op"] == "offer"
            }
            for step in scenario["steps"]:
                if step["operation"] != "offer":
                    continue
                advance_id = step["arguments"]["advance_id"]
                self.assertIn(advance_id, offers)
                self.assertEqual(
                    offers[advance_id]["body"]["face"],
                    step["arguments"]["face"],
                    f"{scenario['scenario_id']} {step['step_id']} journal face "
                    "is not the fixture literal",
                )

    # -- scenario-specific acceptance ------------------------------------

    def test_s1_captured_face_is_frozen_when_settlement_commits(self) -> None:
        captured = self._ok(S1, "s1-settlement-captured")
        self.assertEqual(captured["phase"], "CAPTURED")
        self.assertEqual(captured["claim"]["confirmed_cash"], 0)

        self.assertEqual(
            self._error_code(S1, "s1-draw-early"), "SETTLEMENT_NOT_COMMITTED"
        )
        approved = self._ok(S1, "s1-view-approved")
        self.assertEqual(approved["phase"], "APPROVED")
        self.assertEqual(approved["outstanding_exposure"], 0)
        self.assertFalse(approved["mock_settlement_commit_observed"])

        drawn = self._ok(S1, "s1-view-drawn")
        self.assertEqual(drawn["phase"], "DRAWN")
        self.assertTrue(drawn["mock_settlement_commit_observed"])
        self.assertFalse(drawn["funds_executed"])
        self.assertFalse(drawn["economic_finality_claimed"])

        claim = self._ok(S1, "s1-view-claim")
        self.assertEqual(claim["open_face"], 100000)
        self.assertEqual(claim["confirmed_cash_on_face"], 0)
        self.assertTrue(claim["snapshot_frozen"])

        committed = self._ok(S1, "s1-settlement-committed")
        self.assertEqual(committed["phase"], "COMMITTED")
        self.assertEqual(committed["claim"]["confirmed_cash"], 97000)
        embedded = self._fixture_steps(S1)["s1-offer"]["arguments"]["face"]
        self.assertEqual(embedded["confirmed_cash"], 0)
        self.assertEqual(embedded["receivable_open"], 100000)

    def test_s2_committed_face_is_embedded_without_derivation(self) -> None:
        drawn = self._ok(S2, "s2-view-drawn")
        self.assertEqual(drawn["phase"], "DRAWN")
        self.assertTrue(drawn["mock_settlement_commit_observed"])
        self.assertFalse(drawn["funds_executed"])
        claim = self._ok(S2, "s2-view-claim")
        self.assertEqual(claim["confirmed_cash_on_face"], 97000)
        self.assertEqual(claim["open_face"], 100000)
        self.assertIsNone(claim["open_terms"]["decided_value"])
        self.assertEqual(claim["open_terms"]["policy_number_status"], "UNDETERMINED")
        self.assertNotIn("apr_bps", claim["open_terms"])
        settlement = self._ok(S2, "s2-settlement-after")
        self.assertEqual(settlement["phase"], "COMMITTED")
        self.assertEqual(settlement["claim"]["confirmed_cash"], 97000)
        embedded = self._fixture_steps(S2)["s2-offer"]["arguments"]["face"]
        self.assertEqual(embedded["confirmed_cash"], 97000)

    def test_s3_face_snapshot_is_frozen_and_view_claim_is_stable(self) -> None:
        before = self._ok(S3, "s3-view-claim-before")
        self.assertEqual(
            self._error_code(S3, "s3-draw-later"), "FACE_SNAPSHOT_FROZEN"
        )
        later = self._ok(S3, "s3-view-later")
        self.assertEqual(later["phase"], "APPROVED")
        self.assertEqual(later["outstanding_exposure"], 0)
        self.assertFalse(later["mock_settlement_commit_observed"])

        refunded = self._ok(S3, "s3-settlement-refunded")
        self.assertEqual(refunded["claim"]["refund_face"], 40000)
        self.assertEqual(refunded["claim"]["refund_accepted"], 15000)
        self.assertEqual(refunded["claim"]["refund_outstanding"], 25000)

        after = self._ok(S3, "s3-view-claim-after")
        self.assertEqual(before, after)
        self.assertTrue(after["snapshot_frozen"])
        self.assertEqual(after["reserved_open"], 10000)

    def test_s4_refund_obligation_and_partial_acceptance_are_visible(self) -> None:
        refunded = self._ok(S4, "s4-settlement-refunded")
        refund_claim = refunded["claim"]
        self.assertEqual(refund_claim["refund_face"], 40000)
        self.assertEqual(refund_claim["refund_accepted"], 0)
        self.assertEqual(refund_claim["refund_outstanding"], 40000)
        self.assertEqual(refund_claim["refund_bearer_policy"], "REQUESTER")
        self.assertFalse(refund_claim["distribution_blocked"])
        self.assertFalse(refunded["funds_executed"])
        self.assertFalse(refund_claim["funds_executed"])

        accepted = self._ok(S4, "s4-settlement-accepted")
        accepted_claim = accepted["claim"]
        self.assertEqual(accepted_claim["refund_accepted"], 15000)
        self.assertEqual(accepted_claim["refund_outstanding"], 25000)
        self.assertEqual(accepted_claim["pg_adjustment_outstanding"], 15000)
        self.assertFalse(accepted["funds_executed"])
        self.assertFalse(accepted_claim["funds_executed"])

        claim = self._ok(S4, "s4-view-claim")
        self.assertEqual([key for key in claim if "refund" in key], [])
        self.assertEqual(claim["confirmed_cash_on_face"], 97000)
        self.assertEqual(claim["reserved_open"], 10000)
        drawn = self._ok(S4, "s4-view-drawn")
        self.assertFalse(drawn["funds_executed"])
        self.assertFalse(drawn["repayment_observed"])

    def test_s5_shared_exposure_uses_only_caller_supplied_limits(self) -> None:
        partial = self._ok(S5, "s5-view-claim-partial")
        self.assertEqual(partial["open_face"], 100000)
        self.assertEqual(partial["reserved_open"], 70000)
        self.assertEqual(partial["residual_unreserved"], 30000)

        amounts = [
            self._fixture_steps(S5)[step_id]["arguments"]["amount"]
            for step_id in (
                "s5-offer-1",
                "s5-offer-2",
                "s5-offer-3",
                "s5-offer-4",
            )
        ]
        self.assertEqual(amounts, [40000, 30000, 30001, 30000])

        self.assertEqual(
            self._error_code(S5, "s5-draw-3"), "ADVANCE_EXCEEDS_OPEN_FACE"
        )
        rejected = self._ok(S5, "s5-view-3")
        self.assertEqual(rejected["phase"], "APPROVED")
        self.assertEqual(rejected["outstanding_exposure"], 0)
        self.assertFalse(rejected["mock_settlement_commit_observed"])

        full = self._ok(S5, "s5-view-claim-full")
        self.assertEqual(full["reserved_open"], 100000)
        self.assertEqual(full["residual_unreserved"], 0)
        self.assertFalse(full["priority_bound"])

    def test_s6_reconciliation_gap_is_reported_without_repair(self) -> None:
        refunded = self._ok(S6, "s6-settlement-refunded")
        self.assertEqual(refunded["claim"]["refund_face"], 40000)
        self.assertEqual(refunded["claim"]["refund_outstanding"], 40000)

        claim = self._ok(S6, "s6-view-claim")
        self.assertEqual(claim["open_face"], 100000)
        self.assertEqual(claim["reserved_open"], 20000)
        self.assertEqual([key for key in claim if "refund" in key], [])

        second_draw = self._ok(S6, "s6-draw-2")
        self.assertEqual(second_draw["credit"]["phase"], "DRAWN")
        self.assertTrue(second_draw["credit"]["mock_settlement_commit_observed"])

        observation = {
            "settlement_refund_outstanding": refunded["claim"]["refund_outstanding"],
            "credit_reserved_open": claim["reserved_open"],
            "credit_face_refund_face": self._fixture_steps(S6)["s6-offer-2"][
                "arguments"
            ]["face"]["refund_face"],
        }
        self.assertEqual(
            observation,
            {
                "settlement_refund_outstanding": 40000,
                "credit_reserved_open": 20000,
                "credit_face_refund_face": 0,
            },
        )
        self.assertEqual(GAP_REPORT["repair"], "NONE")
        self.assertEqual(GAP_REPORT["contract_status"], "UNDEFINED")

        settlement_result = self._ok(S6, "s6-settlement-reconcile")
        credit_result = self._ok(S6, "s6-credit-reconcile")
        self.assertTrue(settlement_result["matched"])
        self.assertTrue(credit_result["matched"])
        self.assertFalse(settlement_result["funds_executed"])
        self.assertFalse(credit_result["funds_executed"])

        scenario = next(
            item
            for item in self.fixture["scenarios"]
            if item["scenario_id"] == S6
        )
        results, settlement, credit = boundary.replay_scenario_with_state(scenario)
        self.assertEqual(
            settlement_result["state_digest"], settlement.state_digest()
        )
        self.assertEqual(credit_result["state_digest"], credit.state_digest())
        self.assertEqual(
            credit.view_claim("stl-s6"),
            self._ok(S6, "s6-view-claim"),
        )
        self.assertEqual(
            settlement.view("stl-s6")["claim"]["refund_outstanding"], 40000
        )
        self.assertEqual(
            [step["step_id"] for step in results],
            [step["step_id"] for step in scenario["steps"]],
        )
        # Reconcile is a replay check, not a repair: the reported match is a
        # process-local equality and the gap remains observable afterwards.
        self.assertEqual(
            settlement.view("stl-s6")["claim"]["refund_outstanding"], 40000
        )
        self.assertEqual(
            credit.view_claim("stl-s6"),
            self._ok(S6, "s6-view-claim"),
        )


if __name__ == "__main__":
    unittest.main()
