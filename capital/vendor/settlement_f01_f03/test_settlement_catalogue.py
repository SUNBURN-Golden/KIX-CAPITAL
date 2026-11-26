"""Settlement §9 labels and offline agreement with the contract-only catalogue."""

import json
import unittest
from pathlib import Path

from settlement_fsm import REPLAYABLE, SettlementMachine

ROOT = Path(__file__).resolve().parents[2]


class SettlementCatalogueTests(unittest.TestCase):
    def test_view_lifecycle_authority_is_in_memory_fsm(self):
        for end in ("COMMITTED", "FAILED"):
            with self.subTest(end=end):
                machine = SettlementMachine()
                opened = machine.initiate(
                    "claim-1", idempotency_key="init-1", trade_id="trade-1", gross=100_000,
                    debtor_role="fixture-merchant", policy={
                        "kind": "PRIMARY_FEE_BPS", "fee_bps": 500,
                        "residual_payee": "organizer", "fee_payee": "platform",
                    },
                )
                self.assertEqual(opened["settlement"]["lifecycle_authority"], "IN_MEMORY_FSM")
                self.assertEqual(machine.view("claim-1")["phase"], "INITIATED")
                self.assertEqual(machine.view("claim-1")["lifecycle_authority"], "IN_MEMORY_FSM")
                authorized = machine.authorize("claim-1", idempotency_key="auth-1")
                self.assertEqual(authorized["settlement"]["lifecycle_authority"], "IN_MEMORY_FSM")
                if end == "FAILED":
                    result = machine.fail("claim-1", idempotency_key="fail-1", reason="FIXTURE_DECLINE")
                else:
                    captured = machine.capture("claim-1", idempotency_key="cap-1")
                    self.assertEqual(captured["settlement"]["lifecycle_authority"], "IN_MEMORY_FSM")
                    result = machine.commit(
                        "claim-1", idempotency_key="commit-1", movement_id="move-1",
                        gross=100_000, amount=97_000, fee=3_000, tax=0, held=0, adjustment=0,
                    )
                self.assertEqual(result["settlement"]["lifecycle_authority"], "IN_MEMORY_FSM")
                self.assertEqual(machine.view("claim-1")["phase"], end)
                self.assertEqual(machine.view("claim-1")["lifecycle_authority"], "IN_MEMORY_FSM")

    def test_replayable_names_match_the_contract_only_catalogue(self):
        openapi = json.loads((ROOT / "docs/contracts/openapi/kix-protocol.contract-only.openapi.json").read_text())
        fsm = json.loads((ROOT / "docs/contracts/openapi/fsm-command-contract.json").read_text())
        protocol = json.loads((ROOT / "reference/v0.3-rc1/protocol_contract.json").read_text())
        body_names = {name for name in openapi["x-kix-action-body-map"] if name.startswith("settlement_")}
        local_names = {op["operationId"] for op in openapi["x-kix-local-call-operations"]
                       if op["operationId"].startswith("settlement_")}
        expected = {"settlement_" + op for op in REPLAYABLE}
        self.assertEqual(body_names, expected)
        self.assertEqual(local_names, expected)
        self.assertEqual(set(fsm["machines"]["settlement"]["replayable"]), REPLAYABLE)
        self.assertEqual({c["op"] for c in fsm["commands"].values() if c["machine"] == "settlement"}, REPLAYABLE)
        self.assertEqual({name for name, c in fsm["commands"].items() if c["machine"] == "settlement"}, expected)
        self.assertEqual(len(protocol["commands"]), 40)
        self.assertFalse(any(name.startswith("settlement_") for name in protocol["commands"]))
        self.assertTrue({"capture", "settle_capture"} <= protocol["commands"].keys())
        excluded = {"settlement_" + op for op in ("reconcile", "reject_external", "view", "export_journal", "restore")}
        self.assertTrue(excluded.isdisjoint(body_names | local_names | fsm["commands"].keys()))


if __name__ == "__main__":
    unittest.main()
