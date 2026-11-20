"""Builder-authored PF-C02 boundary evidence, not an independent PASS.

Contract: docs/contracts/MOVE_PRIMARY_ISSUANCE_PRICE_FEE.md section 3 PF-C02
and section 5. Numbers are synthetic, not policy; the 100000/500 fixtures
are not used. Complements test_settlement_properties.SplitPropertyTests:
that suite already covers a Fraction oracle, broad boundaries and eight seeds.
Here the gaps are hand-written goldens, section 5 roles/zero lines, additional
bool/float inputs and a direct integer-formula grid with different seeds.
No chain execution or policy/enforcement-location decision is asserted.
"""

import ast
import random
import sys
import unittest
from pathlib import Path

import mock_settlement
import settlement_property_support
from mock_settlement import MockSettlement, SettlementError
from settlement_property_support import CONTRACT_MONEY_MAX, FEE, RESIDUAL, policy

PF_SEEDS = (11, 17, 23, 29)


def pf_c02(amount, bps):
    fee = amount * bps // 10000
    return fee, amount - fee


def lines(view):
    return {item["payee"]: item["face"] for item in view["obligations"]}


def code_of(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


class PrimaryFeeSplitPfC02Tests(unittest.TestCase):
    def check_split(self, amount, bps, fee, residual):
        book = MockSettlement()
        book.recognize_claim(
            "claim", trade_id="trade", gross=amount,
            debtor_role="fixture-debtor", policy=policy(bps),
        )
        obligations = book.view("claim")["obligations"]
        actual = lines(book.view("claim"))
        expected = {payee: face for payee, face in ((FEE, fee), (RESIDUAL, residual)) if face}
        self.assertEqual(actual, expected)
        self.assertEqual(len(obligations), len(expected))
        self.assertTrue(all(item["face"] > 0 for item in obligations))
        self.assertEqual(sum(item["face"] for item in obligations), amount)
        self.assertEqual(fee + residual, amount)
        self.assertEqual(pf_c02(amount, bps), (fee, residual))
        actual_fee = actual.get(FEE, 0)
        self.assertLessEqual(actual_fee * 10000, amount * bps)
        self.assertLess(amount * bps, (actual_fee + 1) * 10000)

    def test_boundary_goldens(self):
        # Expected outputs are hand-written, separate from the formula helper.
        rows = (
            (1, 0, 0, 1),
            (1, 1, 0, 1),
            (1, 9999, 0, 1),
            (1, 10000, 1, 0),
            (10**12, 0, 0, 10**12),
            (10**12, 1, 100_000_000, 999_900_000_000),
            (10**12, 9999, 999_900_000_000, 100_000_000),
            (10**12, 10000, 10**12, 0),
        )
        for amount, bps, fee, residual in rows:
            with self.subTest(amount=amount, bps=bps):
                self.check_split(amount, bps, fee, residual)

    def test_contract_section5_examples(self):
        for amount, bps, fee, residual in (
            (999, 333, 33, 966), (1, 1, 0, 1), (4, 0, 0, 4), (4, 10000, 4, 0),
        ):
            with self.subTest(amount=amount, bps=bps):
                self.check_split(amount, bps, fee, residual)

    def test_invalid_bps_rejected_with_contract_code(self):
        for bps in (True, False, 0.0, 1.0, 10000.0, -1, 10001):
            with self.subTest(bps=bps, input_type=type(bps).__name__):
                book = MockSettlement()
                self.assertEqual(code_of(lambda: book.recognize_claim(
                    "claim", trade_id="trade", gross=7, debtor_role="fixture-debtor",
                    policy=policy(bps),
                )), "POLICY_FEE_BPS")
                self.assertEqual(code_of(lambda: book.view("claim")), "UNKNOWN_CLAIM")

    def test_invalid_amount_rejected_with_contract_code(self):
        for amount in (True, False, 1.0, float(CONTRACT_MONEY_MAX), 0, -1, CONTRACT_MONEY_MAX + 1):
            with self.subTest(amount=amount, input_type=type(amount).__name__):
                book = MockSettlement()
                self.assertEqual(code_of(lambda: book.recognize_claim(
                    "claim", trade_id="trade", gross=amount, debtor_role="fixture-debtor",
                    policy=policy(1),
                )), "INVALID_AMOUNT")
                self.assertEqual(code_of(lambda: book.view("claim")), "UNKNOWN_CLAIM")

    def test_seeded_grid(self):
        for seed in PF_SEEDS:
            r = random.Random(seed)
            for _ in range(50):
                amount = r.randint(1, 10**r.randint(0, 12))
                bps = r.choice((0, 1, 9999, 10000, r.randint(0, 10000)))
                with self.subTest(seed=seed, amount=amount, bps=bps):
                    self.check_split(amount, bps, *pf_c02(amount, bps))


class SiblingImportPathTests(unittest.TestCase):
    def test_imports_resolve_from_suite(self):
        suite = Path(__file__).resolve().parent
        self.assertEqual(Path(mock_settlement.__file__).resolve().parent, suite)
        self.assertEqual(Path(settlement_property_support.__file__).resolve().parent, suite)
        frozen = suite.parent / "v0.3-rc1"
        self.assertNotIn(frozen, {Path(entry).resolve() for entry in sys.path})


class V03CoreDifferentialStatusTests(unittest.TestCase):
    def test_core_comparison_not_made_core_is_not_standalone_importable(self):
        """Class B characterization; reason the executable differential was not made.

        File-path loading does not resolve bare sibling imports. Read AST only;
        do not execute core or inject sibling modules into sys.path/sys.modules.
        This records an import-layout constraint, not cross-layer equivalence.
        """
        frozen = Path(__file__).resolve().parents[1] / "v0.3-rc1"
        tree = ast.parse((frozen / "core.py").read_text(encoding="utf-8"))
        imports = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
        siblings = {"common", "finance", "lifecycle", "observations", "contracts", "dispatch"}
        self.assertTrue(siblings <= imports)
        for name in sorted(siblings):
            with self.subTest(module=name):
                self.assertTrue((frozen / f"{name}.py").is_file())
                self.assertNotIn(name, sys.stdlib_module_names)
        core = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Core")
        commit = next(node for node in core.body if isinstance(node, ast.FunctionDef) and node.name == "_commit_trade")
        self.assertIn("primaryFeeBps", {
            node.value for node in ast.walk(commit) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        })


if __name__ == "__main__":
    unittest.main()
