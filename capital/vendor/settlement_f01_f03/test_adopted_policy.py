"""Observable lock for SET-POLICY-DRAFT-0.4.

The adopted rows are L0, W0, R0, S0, T0, B5, and P0.
B5 (owner decision 2026-11-10 17:43 KST) replaces B0 for partial refunds:
the requester bears them, distribution continues, payee faces stay untouched.
The other rows keep the current mock. They do not set legal parties, rates,
netting numbers, or a durable close.
Older tests keep the error matrices. This module binds the adopted posture
and the non-zero tax/held case those tests did not post.
"""

import unittest

from mock_settlement import MockSettlement, SettlementError
from settlement_fsm import FAILED, SettlementMachine


ABSENT = (
    "waterfall",
    "remainder_unit_payee",
    "resale_fee_bps",
    "tax_rate",
    "reserve_bps",
    "p04_closed",
)


def policy(**changes):
    base = {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": 500,
        "residual_payee": "organizer",
        "fee_payee": "platform",
    }
    base.update(changes)
    return base


def line(view, payee):
    return next(item for item in view["obligations"] if item["payee"] == payee)


def codes(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


class AdoptedPolicyTests(unittest.TestCase):
    def test_t0_tax_and_held_stay_non_cash(self):
        book = MockSettlement()
        book.recognize_claim(
            "claim-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        posted = book.observe_settlement_statement(
            "claim-1",
            movement_id="move-tax",
            gross=100_000,
            amount=80_000,
            fee=3_000,
            tax=7_000,
            held=10_000,
            adjustment=0,
        )["claim"]
        self.assertEqual(posted["confirmed_cash"], 80_000)
        self.assertEqual(posted["non_cash_accounted"], 20_000)
        self.assertEqual(posted["distributed_cash"], 0)
        self.assertEqual(line(posted, "organizer")["face"], 95_000)
        self.assertEqual(line(posted, "platform")["face"], 5_000)
        self.assertEqual(sum(item["face"] for item in posted["obligations"]), 100_000)
        for key in ABSENT:
            self.assertNotIn(key, posted)

    def test_adopted_policy_posture(self):
        book = MockSettlement()
        opened = book.recognize_claim(
            "claim-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )["claim"]
        self.assertEqual(opened["debtor_role"], "fixture-merchant")
        self.assertIs(opened["legal_debtor_bound"], False)
        self.assertEqual([item["payee"] for item in opened["obligations"]], ["organizer", "platform"])

        remainder = book.recognize_claim(
            "remainder",
            trade_id="trade-r",
            gross=3,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=5000),
        )["claim"]
        self.assertEqual(line(remainder, "platform")["face"], 1)
        self.assertEqual(line(remainder, "organizer")["face"], 2)
        self.assertEqual([item["payee"] for item in remainder["obligations"]], ["organizer", "platform"])

        self.assertEqual(
            codes(lambda: book.recognize_claim(
                "resale",
                trade_id="trade-s",
                gross=100_000,
                debtor_role="fixture-merchant",
                policy=policy(kind="RESALE_BPS"),
            )),
            "POLICY_KIND",
        )

        book.observe_settlement_statement(
            "claim-1",
            movement_id="move-1",
            gross=100_000,
            amount=90_000,
            fee=0,
            tax=5_000,
            held=5_000,
            adjustment=0,
        )
        distributed = book.apply_distribution("claim-1", order=["platform", "organizer"])["claim"]
        self.assertEqual(distributed["distribution_order"], ["platform", "organizer"])
        self.assertEqual(line(distributed, "platform")["distributed"], 5_000)
        self.assertEqual(line(distributed, "platform")["outstanding"], 0)
        self.assertEqual(line(distributed, "organizer")["distributed"], 85_000)
        self.assertEqual(line(distributed, "organizer")["outstanding"], 10_000)
        self.assertEqual(line(distributed, "organizer")["face"], 95_000)
        self.assertEqual(distributed["confirmed_cash"], 90_000)

        refunded = book.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=1_000,
            beneficiary_role="buyer",
            reason="PARTIAL",
        )["claim"]
        self.assertEqual(refunded["refund_bearer_policy"], "REQUESTER")
        self.assertIs(refunded["distribution_blocked"], False)
        self.assertEqual(refunded["distributed_cash"], 90_000)
        self.assertEqual(line(refunded, "organizer")["cancelled_unpaid"], 0)
        self.assertEqual(refunded["recovery_due"], 0)
        # B5: distribution proceeds with an open partial refund. All confirmed
        # cash is already allocated, so the frozen order applies zero and the
        # organizer's unpaid face stays as it was.
        again = book.apply_distribution("claim-1", order=["platform", "organizer"])
        self.assertEqual(again["applied"], {"platform": 0, "organizer": 0})
        self.assertEqual(again["claim"]["distributed_cash"], 90_000)
        self.assertEqual(line(again["claim"], "organizer")["outstanding"], 10_000)
        self.assertEqual(book.view("claim-1")["distributed_cash"], 90_000)
        for key in ABSENT:
            self.assertNotIn(key, book.view("claim-1"))

        machine = SettlementMachine()
        machine.initiate(
            "claim-p",
            idempotency_key="init-p",
            trade_id="trade-p",
            gross=10_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=0),
        )
        failed = machine.fail("claim-p", idempotency_key="fail-p", reason="FIXTURE_DECLINE")
        settlement = failed["settlement"]
        self.assertEqual(settlement["phase"], FAILED)
        self.assertIs(settlement["terminal"], True)
        self.assertIs(settlement["durable"], False)
        self.assertIs(settlement["funds_executed"], False)
        self.assertIs(settlement["legal_debtor_bound"], False)
        self.assertIs(settlement["external_return_closed"], False)
        self.assertIsNone(settlement["claim"])
        for key in ABSENT:
            self.assertNotIn(key, settlement)
