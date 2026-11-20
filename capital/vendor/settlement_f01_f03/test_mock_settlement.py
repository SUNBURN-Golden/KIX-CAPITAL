"""Deterministic checks for the F01–F03 offline settlement mock."""

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


def statement(book, claim="claim-1", movement="move-1", **changes):
    body = dict(
        movement_id=movement,
        gross=100_000,
        amount=97_000,
        fee=3_000,
        tax=0,
        held=0,
        adjustment=0,
    )
    body.update(changes)
    return book.observe_settlement_statement(claim, **body)


def line(view, payee):
    return next(item for item in view["obligations"] if item["payee"] == payee)


def codes(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


class SettlementMockTests(unittest.TestCase):
    def setUp(self):
        self.book = MockSettlement()

    def open_claim(self, **changes):
        body = dict(
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        body.update(changes)
        return self.book.recognize_claim("claim-1", **body)

    def test_f01_split_opens_obligations_without_cash_or_legal_binding(self):
        result = self.open_claim()
        claim = result["claim"]
        self.assertFalse(result["duplicate"])
        self.assertEqual(claim["provenance"], "MOCK_SETTLEMENT_ONLY")
        self.assertEqual(line(claim, "organizer")["face"], 95_000)
        self.assertEqual(line(claim, "platform")["face"], 5_000)
        self.assertEqual(claim["confirmed_cash"], 0)
        self.assertEqual(claim["receivable_open"], 100_000)
        self.assertEqual(claim["refund_bearer_policy"], "NONE")
        for flag in (
            "legal_debtor_bound",
            "admission_granted",
            "right_cancelled",
            "bank_debit_observed",
            "external_return_closed",
            "funds_executed",
        ):
            self.assertIs(claim[flag], False)
        again = self.open_claim()
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["claim"]["obligations"], claim["obligations"])
        self.assertEqual(
            codes(lambda: self.book.recognize_claim(
                "claim-1",
                trade_id="trade-1",
                gross=100_000,
                debtor_role="other-debtor",
                policy=policy(),
            )),
            "CLAIM_BINDING_CONFLICT",
        )

    def test_f01_fee_floor_zero_fee_and_rejected_policies(self):
        tiny = self.book.recognize_claim(
            "tiny",
            trade_id="trade-tiny",
            gross=1,
            debtor_role="fixture-merchant",
            policy=policy(),
        )["claim"]
        self.assertEqual([item["payee"] for item in tiny["obligations"]], ["organizer"])
        self.assertEqual(tiny["obligations"][0]["face"], 1)

        zero = self.book.recognize_claim(
            "zero-fee",
            trade_id="trade-zero",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=0),
        )["claim"]
        self.assertEqual([item["payee"] for item in zero["obligations"]], ["organizer"])

        whole = self.book.recognize_claim(
            "whole-fee",
            trade_id="trade-whole",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=10000),
        )["claim"]
        self.assertEqual([item["payee"] for item in whole["obligations"]], ["platform"])
        self.assertEqual(whole["obligations"][0]["face"], 100_000)

        self.assertEqual(codes(lambda: self.open_claim(policy=policy(kind="RESALE_BPS"))), "POLICY_KIND")
        self.assertEqual(codes(lambda: self.open_claim(currency="USD")), "CURRENCY_UNSUPPORTED")
        self.assertEqual(codes(lambda: self.open_claim(gross=True)), "INVALID_AMOUNT")
        self.assertEqual(codes(lambda: self.open_claim(policy=policy(residual_payee="platform"))), "POLICY_PAYEE_COLLISION")
        self.assertEqual(codes(lambda: self.book.view("missing")), "UNKNOWN_CLAIM")

    def test_f02_statement_does_not_infer_fee_or_shrink_faces(self):
        self.open_claim()
        posted = statement(self.book)["claim"]
        self.assertEqual(posted["confirmed_cash"], 97_000)
        self.assertEqual(posted["non_cash_accounted"], 3_000)
        self.assertEqual(posted["receivable_open"], 0)
        self.assertEqual(line(posted, "organizer")["face"], 95_000)
        self.assertEqual(line(posted, "platform")["face"], 5_000)
        self.assertEqual(posted["distributed_cash"], 0)
        self.assertEqual(
            codes(lambda: statement(self.book, movement="inferred", gross=100_000, amount=97_000, fee=0)),
            "SETTLEMENT_COMPONENT_MISMATCH",
        )
        self.assertEqual(
            codes(lambda: statement(self.book, movement="over", gross=1, amount=1, fee=0)),
            "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        )
        self.assertTrue(statement(self.book)["duplicate"])
        self.assertEqual(
            codes(lambda: statement(self.book, amount=100_000, fee=0)),
            "STATEMENT_BINDING_CONFLICT",
        )
        self.assertEqual(
            codes(lambda: statement(
                self.book,
                movement="adj",
                gross=1,
                amount=0,
                fee=0,
                adjustment=1,
                adjustment_reason=None,
            )),
            "ADJUSTMENT_REASON_REQUIRED",
        )

    def test_f02_caller_order_selects_shortfall_and_then_freezes(self):
        self.open_claim()
        statement(self.book)
        platform_first = self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(platform_first["applied"], {"platform": 5_000, "organizer": 92_000})
        claim = platform_first["claim"]
        self.assertEqual(line(claim, "platform")["outstanding"], 0)
        self.assertEqual(line(claim, "organizer")["outstanding"], 3_000)
        self.assertEqual(claim["undistributed_cash"], 0)
        self.assertEqual(line(claim, "organizer")["face"], 95_000)
        again = self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(again["applied"], {"platform": 0, "organizer": 0})
        self.assertEqual(
            codes(lambda: self.book.apply_distribution("claim-1", order=["organizer", "platform"])),
            "DISTRIBUTION_ORDER_FROZEN",
        )

        other = MockSettlement()
        other.recognize_claim(
            "claim-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        statement(other)
        organizer_first = other.apply_distribution("claim-1", order=["organizer", "platform"])["claim"]
        self.assertEqual(line(organizer_first, "organizer")["outstanding"], 0)
        self.assertEqual(line(organizer_first, "platform")["outstanding"], 3_000)
        self.assertEqual(
            codes(lambda: other.apply_distribution("claim-1", order=["platform", "platform"])),
            "DISTRIBUTION_ORDER_DUPLICATE",
        )
        self.assertEqual(codes(lambda: other.apply_distribution("claim-1", order="platform")), "DISTRIBUTION_ORDER_TYPE")
        self.assertEqual(codes(lambda: other.apply_distribution("claim-1", order=[])), "DISTRIBUTION_ORDER_MISMATCH")

        empty = MockSettlement()
        empty.recognize_claim(
            "claim-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        frozen = empty.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(frozen["applied"], {"platform": 0, "organizer": 0})
        self.assertEqual(frozen["claim"]["distribution_order"], ["platform", "organizer"])
        self.assertEqual(frozen["claim"]["confirmed_cash"], 0)

    def test_f02_later_cash_continues_on_the_frozen_order(self):
        self.open_claim()
        statement(
            self.book,
            movement="part-1",
            gross=60_000,
            amount=60_000,
            fee=0,
        )
        first = self.book.apply_distribution("claim-1", order=["platform", "organizer"])["claim"]
        self.assertEqual(line(first, "platform")["distributed"], 5_000)
        self.assertEqual(line(first, "organizer")["distributed"], 55_000)
        statement(
            self.book,
            movement="part-2",
            gross=40_000,
            amount=37_000,
            fee=3_000,
        )
        second = self.book.apply_distribution("claim-1", order=["platform", "organizer"])["claim"]
        self.assertEqual(line(second, "platform")["distributed"], 5_000)
        self.assertEqual(line(second, "organizer")["distributed"], 92_000)
        self.assertEqual(line(second, "organizer")["outstanding"], 3_000)
        self.assertEqual(second["confirmed_cash"], 97_000)
        self.assertEqual(second["undistributed_cash"], 0)

    def test_f03_partial_refund_keeps_requester_bearer_without_reclassifying(self):
        self.open_claim()
        statement(self.book)
        first = self.book.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=40_000,
            beneficiary_role="buyer",
            reason="PARTIAL",
        )["claim"]
        self.assertEqual(first["refund_face"], 40_000)
        self.assertEqual(first["refund_bearer_policy"], "REQUESTER")
        self.assertFalse(first["distribution_blocked"])
        self.assertEqual(line(first, "organizer")["face"], 95_000)
        self.assertEqual(line(first, "organizer")["cancelled_unpaid"], 0)
        self.assertEqual(first["recovery_due"], 0)
        self.assertIsNone(first["distribution_order"])
        # B5: the partial refund does not block distribution; the caller order
        # allocates the confirmed cash and then freezes.
        distributed = self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(distributed["applied"], {"platform": 5_000, "organizer": 92_000})
        self.assertEqual(distributed["claim"]["distribution_order"], ["platform", "organizer"])
        self.assertEqual(self.book.view("claim-1")["distribution_order"], ["platform", "organizer"])
        self.assertEqual(
            codes(lambda: self.book.bind_refund(
                "claim-1",
                refund_id="refund-4",
                amount=1,
                beneficiary_role="other",
                reason="OTHER",
            )),
            "REFUND_BENEFICIARY_CONFLICT",
        )
        self.assertEqual(self.book.view("claim-1")["refund_face"], 40_000)
        rest = self.book.bind_refund(
            "claim-1",
            refund_id="refund-2",
            amount=60_000,
            beneficiary_role="buyer",
            reason="REST",
        )["claim"]
        self.assertEqual(rest["refund_face"], 100_000)
        self.assertFalse(rest["fixture_reclassified"])
        self.assertEqual(rest["refund_bearer_policy"], "REQUESTER")
        self.assertEqual(line(rest, "platform")["outstanding"], 0)
        self.assertEqual(
            codes(lambda: self.book.bind_refund(
                "claim-1",
                refund_id="refund-3",
                amount=1,
                beneficiary_role="buyer",
                reason="OVER",
            )),
            "REFUND_CEILING",
        )
        self.assertTrue(self.book.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=40_000,
            beneficiary_role="buyer",
            reason="PARTIAL",
        )["duplicate"])

    def test_f03_partial_after_distribution_does_not_claw_back(self):
        self.open_claim()
        statement(self.book)
        self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        claim = self.book.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=40_000,
            beneficiary_role="buyer",
            reason="PARTIAL",
        )["claim"]
        self.assertEqual(claim["distributed_cash"], 97_000)
        self.assertEqual(line(claim, "organizer")["cancelled_unpaid"], 0)
        self.assertEqual(claim["recovery_due"], 0)
        self.assertEqual(claim["refund_bearer_policy"], "REQUESTER")
        self.assertFalse(claim["distribution_blocked"])
        # B5: a later distribution still succeeds; no cash remains, so it
        # applies zero and claws nothing back.
        again = self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(again["applied"], {"platform": 0, "organizer": 0})
        self.assertEqual(self.book.view("claim-1")["distributed_cash"], 97_000)

    def test_f03_full_refund_reclassifies_and_mock_acceptance_is_not_closure(self):
        self.open_claim()
        statement(self.book)
        self.book.apply_distribution("claim-1", order=["platform", "organizer"])
        refunded = self.book.bind_refund(
            "claim-1",
            refund_id="refund-full",
            amount=100_000,
            beneficiary_role="buyer",
            reason="FULL",
        )["claim"]
        self.assertTrue(refunded["fixture_reclassified"])
        self.assertEqual(refunded["refund_bearer_policy"], "FIXTURE_FULL_GROSS_RECLASS")
        self.assertEqual(line(refunded, "platform")["recovery_due"], 5_000)
        self.assertEqual(line(refunded, "platform")["outstanding"], 0)
        self.assertEqual(line(refunded, "organizer")["distributed"], 92_000)
        self.assertEqual(line(refunded, "organizer")["cancelled_unpaid"], 3_000)
        self.assertEqual(line(refunded, "organizer")["recovery_due"], 92_000)
        self.assertEqual(refunded["recovery_due"], 97_000)
        self.assertEqual(refunded["refund_outstanding"], 100_000)
        self.assertIs(refunded["right_cancelled"], False)

        accepted = self.book.observe_mock_cancel_acceptance("claim-1", source_id="accept-1", amount=40_000)["claim"]
        self.assertEqual(accepted["refund_outstanding"], 60_000)
        self.assertEqual(accepted["pg_adjustment_outstanding"], 40_000)
        self.assertEqual(accepted["confirmed_cash"], 97_000)
        self.assertIs(accepted["bank_debit_observed"], False)
        self.assertIs(accepted["external_return_closed"], False)
        self.assertIs(accepted["right_cancelled"], False)
        closed = self.book.observe_mock_cancel_acceptance("claim-1", source_id="accept-2", amount=60_000)["claim"]
        self.assertEqual(closed["refund_outstanding"], 0)
        self.assertEqual(closed["pg_adjustment_outstanding"], 100_000)
        self.assertIs(closed["external_return_closed"], False)
        self.assertTrue(self.book.observe_mock_cancel_acceptance("claim-1", source_id="accept-1", amount=40_000)["duplicate"])
        self.assertEqual(
            codes(lambda: self.book.observe_mock_cancel_acceptance("claim-1", source_id="accept-3", amount=1)),
            "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        )
        self.assertEqual(
            codes(lambda: self.book.observe_mock_cancel_acceptance("claim-1", source_id="accept-1", amount=1)),
            "ACCEPTANCE_BINDING_CONFLICT",
        )

    def test_f03_cash_after_reclass_is_not_applied_or_sent(self):
        self.open_claim()
        self.book.bind_refund(
            "claim-1",
            refund_id="refund-full",
            amount=100_000,
            beneficiary_role="buyer",
            reason="FULL",
        )
        statement(self.book, gross=100_000, amount=100_000, fee=0)
        claim = self.book.apply_distribution("claim-1", order=["platform", "organizer"])["claim"]
        self.assertEqual(claim["distributed_cash"], 0)
        self.assertEqual(claim["undistributed_cash"], 100_000)
        self.assertEqual(claim["recovery_due"], 0)
        self.assertEqual(line(claim, "organizer")["cancelled_unpaid"], 95_000)
        self.assertIs(claim["funds_executed"], False)
        fresh = MockSettlement()
        self.assertEqual(codes(lambda: fresh.observe_mock_cancel_acceptance("missing", source_id="accept-1", amount=1)), "UNKNOWN_CLAIM")
        fresh.recognize_claim(
            "claim-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        self.assertEqual(
            codes(lambda: fresh.observe_mock_cancel_acceptance("claim-1", source_id="accept-1", amount=1)),
            "REFUND_OBLIGATION_REQUIRED",
        )

    def test_claims_do_not_share_cash(self):
        self.open_claim()
        statement(self.book)
        self.book.recognize_claim(
            "claim-2",
            trade_id="trade-2",
            gross=10_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=0),
        )
        other = self.book.view("claim-2")
        first = self.book.view("claim-1")
        self.assertEqual(other["confirmed_cash"], 0)
        self.assertEqual(first["confirmed_cash"], 97_000)
        self.assertEqual(other["gross"], 10_000)


if __name__ == "__main__":
    unittest.main()
