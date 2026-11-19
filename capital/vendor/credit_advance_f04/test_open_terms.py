"""Draft 0.2 keeps the adopted F04 mock boundary unfilled.

JunTae adopted option A on 2026-10-09. Policy numbers stay UNDETERMINED.
Existing suites already cover product refusal, unordered reservation, and
the frozen face snapshot. This module checks the adoption table against
that behavior and the command names this revision does not add.
"""

import json
import unittest
from pathlib import Path

import test_credit_fsm
import test_mock_credit
from credit_fsm import REPLAYABLE, CreditMachine
from mock_credit import MockCredit
from open_terms import (
    ADOPTED_OPTION,
    ADOPTION_DATE,
    ADOPTION_DECIDER,
    CONTRACT_VERSION,
    FORBIDDEN_COMMANDS,
    ITEMS,
    MOCK_BOUNDARY,
    POLICY_NUMBER_STATUS,
    REVISION,
    boundary,
    forbidden_commands,
    item,
)
from test_credit_fsm import codes as fsm_codes
from test_credit_fsm import settlement_book

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "contracts" / "CREDIT_ADVANCE_F04.md"
PROTOCOL = ROOT / "reference" / "v0.3-rc1" / "protocol_contract.json"
OPENAPI = ROOT / "docs" / "contracts" / "openapi" / "kix-protocol.contract-only.openapi.json"

CITED = {
    "test_mock_credit": test_mock_credit,
    "test_credit_fsm": test_credit_fsm,
}

REPLAYABLE_NOW = frozenset(
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


class OpenTermDraftTests(unittest.TestCase):
    def test_revision_is_unfilled_and_named_in_the_contract(self):
        text = CONTRACT.read_text(encoding="utf-8")
        section = text.split("### 5.1 초안 0.2", 1)[1].split("## 6. 비청구", 1)[0]
        self.assertEqual(REVISION, "F04-MOCK-TERMS-DRAFT-0.2")
        self.assertEqual(CONTRACT_VERSION, "0.2")
        self.assertEqual(MOCK_BOUNDARY, "UNFILLED")
        self.assertEqual(ADOPTED_OPTION, "A")
        self.assertEqual(ADOPTION_DECIDER, "JunTae")
        self.assertEqual(ADOPTION_DATE, "2026-10-09")
        self.assertEqual(POLICY_NUMBER_STATUS, "UNDETERMINED")
        self.assertIn(REVISION, text)
        self.assertIn("계약 버전 `0.2`", text)
        self.assertIn("2026-10-09 소유자 결정(JunTae)이 선택지 A를 목 경계로 채택했다", text)
        self.assertNotIn("DECISION_REQUIRED", section)
        self.assertEqual(
            [row["id"] for row in ITEMS],
            [
                "legal-parties",
                "interest-apr-schedule",
                "seniority",
                "perfection",
                "limit-recalculation",
            ],
        )
        record = boundary()
        self.assertIsNone(record["decided_value"])
        self.assertEqual(record["policy_number_status"], "UNDETERMINED")
        for row in ITEMS:
            self.assertIn("`%s`" % row["id"], text)
            self.assertIsNone(row["decided_value"])
            self.assertEqual(row["mock_boundary"], "UNFILLED")
            self.assertEqual(row["adopted_option"], "A")
            self.assertEqual(row["adoption_decider"], "JunTae")
            self.assertEqual(row["adoption_date"], "2026-10-09")
            self.assertEqual(row["policy_number_status"], "UNDETERMINED")
            self.assertEqual(row["recommendation"], "A")
            self.assertIn("A", row["options"])
            self.assertNotIn("apr_bps", row["options"]["A"])
            projected = record["terms"][row["id"]]
            self.assertEqual(projected["mock_effect"], row["mock_effect"])
            self.assertIsNone(projected["decided_value"])
            for pending in row["undetermined"]:
                self.assertEqual(pending["status"], "UNDETERMINED")
                self.assertGreater(len(pending["owner"].strip()), 0)
                self.assertIn(pending["owner"], text)
        ceiling = item("limit-recalculation")["observed_fixture"]
        self.assertIs(ceiling["snapshot_frozen"], True)
        self.assertIs(ceiling["confirmed_cash_counts_toward_ceiling"], False)
        self.assertIs(ceiling["recovery_due_counts_toward_ceiling"], False)

    def test_cited_tests_exist(self):
        for row in ITEMS:
            self.assertGreater(len(row["covered_by"]), 0)
            for ref in row["covered_by"]:
                module_name, class_name, method_name = ref.split(".")
                owner = getattr(CITED[module_name], class_name)
                self.assertTrue(callable(getattr(owner, method_name)))

    def test_command_surface_does_not_grow(self):
        names = forbidden_commands()
        self.assertEqual(names, FORBIDDEN_COMMANDS)
        for surface in (MockCredit, CreditMachine):
            public = {name for name in dir(surface) if not name.startswith("_")}
            self.assertTrue(names.isdisjoint(public), surface.__name__)
        self.assertEqual(REPLAYABLE, REPLAYABLE_NOW)
        catalogue = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual(len(catalogue["commands"]), 40)
        self.assertTrue(names.isdisjoint(catalogue["commands"]))
        openapi = json.loads(OPENAPI.read_text(encoding="utf-8"))
        wire = set(openapi["x-kix-action-body-map"])
        self.assertTrue(names.isdisjoint(wire))

    def test_live_refusals_match_the_unfilled_table(self):
        book, face = settlement_book("COMMITTED")
        machine = CreditMachine(book)
        self.assertEqual(
            fsm_codes(lambda: machine.offer(
                "priced",
                idempotency_key="offer-priced",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={"apr_bps": 1200, "schedule": [{"day": 30, "amount": 1}]},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertIn("CREDIT_PRODUCT_UNDEFINED", item("interest-apr-schedule")["current_refusal"])
        self.assertEqual(machine.export_journal(), [])
        offered = machine.offer(
            "adv-1",
            idempotency_key="offer-1",
            face=face,
            amount=100_000,
            beneficiary_role="lender",
        )
        view = offered["credit"]
        self.assertEqual(view["open_face"], 100_000)
        self.assertEqual(view["confirmed_cash_on_face"], 97_000)
        self.assertEqual(view["open_terms"], boundary())
        for row in ITEMS:
            for flag in row["non_claim_flags"]:
                self.assertIs(view[flag], False)
        digest = machine.state_digest()
        self.assertEqual(len(machine.export_journal()), 1)
        self.assertEqual(fsm_codes(lambda: machine.reject_unsupported("INTEREST")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(fsm_codes(lambda: machine.reject_unsupported("PRIORITY")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(fsm_codes(lambda: machine.reject_unsupported("PERFECT")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(machine.state_digest(), digest)
        self.assertEqual(len(machine.export_journal()), 1)
        self.assertIs(machine.view("adv-1")["interest_defined"], False)
        self.assertIs(machine.view("adv-1")["priority_bound"], False)
        self.assertIs(machine.view("adv-1")["collateral_perfected"], False)
        self.assertIs(machine.view("adv-1")["legal_debtor_bound"], False)
