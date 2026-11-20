"""Negative tests for contract error codes (section 6) that no other test names.

Added by plan-contract-error-code-coverage. Each test expects one code from the
offline settlement mock; synthetic ids only, no policy value beyond the sibling
tests' fixture.
"""

import unittest

from mock_settlement import MockSettlement, SettlementError


def policy(**changes):
    base = {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": 500,
        "residual_payee": "organizer",
        "fee_payee": "platform",
    }
    base.update(changes)
    return base


def codes(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


class SettlementErrorCodeGapTests(unittest.TestCase):
    def setUp(self):
        self.book = MockSettlement()

    def recognize(self, **changes):
        body = dict(
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        body.update(changes)
        return lambda: self.book.recognize_claim("claim-1", **body)

    def open_claim(self):
        self.recognize()()
        return self.book.view("claim-1")

    def statement(self, **changes):
        body = dict(
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        body.update(changes)
        return lambda: self.book.observe_settlement_statement("claim-1", **body)

    def test_negative_component_is_invalid_nonnegative(self):
        before = self.open_claim()
        self.assertEqual(codes(self.statement(tax=-1)), "INVALID_NONNEGATIVE")
        self.assertEqual(codes(self.statement(held=True)), "INVALID_NONNEGATIVE")
        self.assertEqual(self.book.view("claim-1"), before)

    def test_policy_not_a_dict_is_policy_type(self):
        self.assertEqual(codes(self.recognize(policy=[("kind", "PRIMARY_FEE_BPS")])), "POLICY_TYPE")
        with self.assertRaises(SettlementError):
            self.book.view("claim-1")

    def test_policy_key_set_must_match_is_policy_fields(self):
        extra = policy(extra_key=1)
        missing = policy()
        del missing["fee_payee"]
        self.assertEqual(codes(self.recognize(policy=extra)), "POLICY_FIELDS")
        self.assertEqual(codes(self.recognize(policy=missing)), "POLICY_FIELDS")

    def test_bad_payee_identifier_is_policy_payee(self):
        self.assertEqual(codes(self.recognize(policy=policy(residual_payee=""))), "POLICY_PAYEE")
        self.assertEqual(codes(self.recognize(policy=policy(fee_payee=7))), "POLICY_PAYEE")

    def test_reason_without_adjustment_is_adjustment_reason_unexpected(self):
        before = self.open_claim()
        self.assertEqual(
            codes(self.statement(adjustment_reason="not needed")),
            "ADJUSTMENT_REASON_UNEXPECTED",
        )
        self.assertEqual(self.book.view("claim-1"), before)


if __name__ == "__main__":
    unittest.main()
