"""F04 §7 command names agree with the pinned offline contract-only catalogue."""

import json
import unittest
from pathlib import Path

from credit_fsm import REPLAYABLE

ROOT = Path(__file__).resolve().parents[2]


class CreditCatalogueTests(unittest.TestCase):
    def test_replayable_names_match_the_contract_only_catalogue(self):
        openapi = json.loads((ROOT / "docs/contracts/openapi/kix-protocol.contract-only.openapi.json").read_text())
        fsm = json.loads((ROOT / "docs/contracts/openapi/fsm-command-contract.json").read_text())
        protocol = json.loads((ROOT / "reference/v0.3-rc1/protocol_contract.json").read_text())
        body_names = {name for name in openapi["x-kix-action-body-map"] if name.startswith("credit_")}
        local_names = {op["operationId"] for op in openapi["x-kix-local-call-operations"]
                       if op["operationId"].startswith("credit_")}
        expected = {"credit_" + op for op in REPLAYABLE}
        self.assertEqual(body_names, expected)
        self.assertEqual(local_names, expected)
        self.assertEqual(set(fsm["machines"]["credit"]["replayable"]), REPLAYABLE)
        self.assertEqual({c["op"] for c in fsm["commands"].values() if c["machine"] == "credit"}, REPLAYABLE)
        self.assertEqual({name for name, c in fsm["commands"].items() if c["machine"] == "credit"}, expected)
        self.assertEqual(len(protocol["commands"]), 40)
        self.assertFalse(any(name.startswith("credit_") for name in protocol["commands"]))
        excluded = {"credit_" + op for op in ("reconcile", "reject_external", "view", "export_journal", "restore")}
        self.assertTrue(excluded.isdisjoint(body_names | local_names | fsm["commands"].keys()))


if __name__ == "__main__":
    unittest.main()
