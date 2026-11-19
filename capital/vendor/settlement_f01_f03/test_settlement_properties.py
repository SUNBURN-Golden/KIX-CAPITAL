"""Seeded property suite for the F01-F03 settlement mock and its FSM.

Author-side harness. The author is the builder, so a green run here is not an
independent PASS, not an accounting or legal treatment, and not a payment.
Fixtures are synthetic KRW integers, not policy. No wall clock, no os.urandom,
no network, no files. Seeds are fixed in settlement_property_support.SEEDS.

Oracles are re-derived from docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md
sections 1-6 and 9. The mapping to existing tests and the section 8 classes
are in validation/2026-10-16-settlement-seeded-property-suite/README.md.

This suite does not implement or close the pending fin-multi-payee-refund-proof
node. It asserts no waterfall, remainder-unit payee, tax or reserve rate, or
refund bearer. Those stay UNDETERMINED (contract section 7, adopted L0..P0).

Properties:
  (a) split faces sum to gross, fee is floor(gross * bps / 10000)
  (b) face = distributed + cancelled_unpaid + outstanding, claims share no cash
  (c) a call that raises SettlementError leaves every view byte-identical
  (d) identical binding repeats are duplicates, a changed binding conflicts
  (e) rejected FSM commands move nothing, restore reproduces, keys replay
"""

import unittest
from unittest import mock

import mock_settlement
from mock_settlement import MockSettlement, SettlementError
from settlement_fsm import SettlementMachine
from settlement_property_support import (
    ALWAYS_FALSE_FLAGS,
    BPS_GRID,
    CONTRACT_MONEY_MAX,
    FEE,
    GROSS_GRID,
    RESIDUAL,
    SEEDS,
    MachineDriver,
    Mirror,
    MockDriver,
    canon,
    check_claim_view,
    oracle_split,
    policy,
    rng,
    split_money,
    statement_kwargs,
)


def code_of(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


def opened(gross, bps):
    book = MockSettlement()
    book.recognize_claim("c", trade_id="t", gross=gross, debtor_role="fixture-debtor", policy=policy(bps))
    return book


class SplitPropertyTests(unittest.TestCase):
    def check_split(self, gross, bps):
        view = opened(gross, bps).view("c")
        lines = {item["payee"]: item["face"] for item in view["obligations"]}
        self.assertEqual(sum(lines.values()), gross, (gross, bps))
        self.assertEqual(lines, oracle_split(gross, bps), (gross, bps))
        fee = lines.get(FEE, 0)
        # floor(gross * bps / 10000) written as its defining inequality
        self.assertLessEqual(fee * 10000, gross * bps, (gross, bps))
        self.assertGreater((fee + 1) * 10000, gross * bps, (gross, bps))
        self.assertNotIn(0, lines.values(), "a zero-face line is not an obligation")
        for item in view["obligations"]:
            self.assertEqual((item["distributed"], item["cancelled_unpaid"], item["recovery_due"]), (0, 0, 0))
            self.assertEqual(item["outstanding"], item["face"])
        self.assertEqual(view["confirmed_cash"], 0)
        check_claim_view(view)

    def test_a_contract_money_max_matches_the_mock_constant(self):
        self.assertEqual(mock_settlement.MONEY_MAX, CONTRACT_MONEY_MAX)

    def test_a_boundary_grid_of_gross_and_fee_bps(self):
        for gross in GROSS_GRID:
            for bps in BPS_GRID:
                with self.subTest(gross=gross, bps=bps):
                    self.check_split(gross, bps)

    def test_a_seeded_gross_and_fee_bps(self):
        for seed in SEEDS:
            r = rng(seed)
            for _ in range(40):
                gross = r.randint(1, 10 ** r.randint(1, 12))
                bps = r.choice((0, 1, 9999, 10000, r.randint(0, 10000)))
                with self.subTest(seed=seed, gross=gross, bps=bps):
                    self.check_split(gross, bps)

    def test_a_out_of_range_inputs_are_rejected_and_open_no_claim(self):
        book = MockSettlement()
        for bps in (-1, 10001, True, "5", None, 5.0):
            code = code_of(
                lambda: book.recognize_claim(
                    "c", trade_id="t", gross=100, debtor_role="d", policy=policy(bps)
                )
            )
            self.assertEqual(code, "POLICY_FEE_BPS", bps)
        for gross in (0, -1, CONTRACT_MONEY_MAX + 1, True, "5", None, 1.5):
            code = code_of(
                lambda: book.recognize_claim(
                    "c", trade_id="t", gross=gross, debtor_role="d", policy=policy(10)
                )
            )
            self.assertEqual(code, "INVALID_AMOUNT", gross)
        self.assertEqual(code_of(lambda: book.view("c")), "UNKNOWN_CLAIM")


class ConservationPropertyTests(unittest.TestCase):
    REQUIRED = (
        "ok:recognize_claim",
        "ok:observe_settlement_statement",
        "ok:apply_distribution",
        "ok:bind_refund",
        "ok:observe_mock_cancel_acceptance",
        "UNKNOWN_CLAIM",
        "CLAIM_BINDING_CONFLICT",
        "STATEMENT_BINDING_CONFLICT",
        "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        "DISTRIBUTION_ORDER_FROZEN",
        "DISTRIBUTION_ORDER_MISMATCH",
        "DISTRIBUTION_ORDER_DUPLICATE",
        "REFUND_CEILING",
        "REFUND_BINDING_CONFLICT",
        "REFUND_BENEFICIARY_CONFLICT",
        "REFUND_OBLIGATION_REQUIRED",
        "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        "ACCEPTANCE_BINDING_CONFLICT",
    )

    def test_b_c_seeded_sequences_conserve_and_rejections_change_nothing(self):
        total = {}
        reclassified = 0
        for seed in SEEDS:
            driver = MockDriver(seed)
            with self.subTest(seed=seed):
                driver.run()
            for name, count in driver.counts.items():
                total[name] = total.get(name, 0) + count
            reclassified += sum(m.reclassified for m in driver.mirrors.values())
        # Guard against a vacuous run: the generator must reach each family.
        for name in self.REQUIRED:
            self.assertGreater(total.get(name, 0), 0, name)
        self.assertGreater(reclassified, 0, "no seed reached a first full-gross refund")

    def test_b_claims_never_share_cash_even_with_the_same_payee_labels(self):
        for seed in SEEDS:
            r = rng(seed)
            book = MockSettlement()
            cash = {"a": 0, "b": 0}
            for cid in cash:
                book.recognize_claim(
                    cid, trade_id="t", gross=1000, debtor_role="d", policy=policy(r.randint(1, 9999))
                )
            for step in range(6):
                cid = r.choice(sorted(cash))
                amount = r.randint(1, 150)
                book.observe_settlement_statement(
                    cid, **statement_kwargs(f"m-{step}", (amount, amount, 0, 0, 0, 0, None))
                )
                cash[cid] += amount
                book.apply_distribution(cid, order=[RESIDUAL, FEE])
                for key in cash:
                    view = book.view(key)
                    self.assertEqual(view["confirmed_cash"], cash[key], (seed, key))
                    self.assertLessEqual(view["distributed_cash"], cash[key])
                    check_claim_view(view)

    def test_b_money_max_claim_runs_statement_distribution_refund_and_acceptance(self):
        gross = CONTRACT_MONEY_MAX
        book = opened(gross, 1)
        mirror = Mirror("c", "t", gross, "fixture-debtor", 1, RESIDUAL, FEE)
        vals = (gross, gross, 0, 0, 0, 0, None)
        book.observe_settlement_statement("c", **statement_kwargs("m-1", vals))
        mirror.apply_statement("m-1", vals)
        check_claim_view(book.view("c"), mirror)
        order = [FEE, RESIDUAL]
        applied = book.apply_distribution("c", order=order)["applied"]
        self.assertEqual(applied, mirror.apply_distribution(order))
        check_claim_view(book.view("c"), mirror)
        self.assertEqual(book.view("c")["undistributed_cash"], 0)
        book.bind_refund("c", refund_id="r", amount=gross, beneficiary_role="b", reason="why")
        mirror.apply_refund("r", (gross, "b", "why"))
        check_claim_view(book.view("c"), mirror)
        book.observe_mock_cancel_acceptance("c", source_id="a", amount=gross)
        mirror.apply_acceptance("a", gross)
        view = book.view("c")
        check_claim_view(view, mirror)
        self.assertEqual(view["recovery_due"], gross)
        self.assertEqual(view["refund_outstanding"], 0)
        self.assertEqual(code_of(lambda: book.bind_refund("c", refund_id="r2", amount=1, beneficiary_role="b", reason="why")), "REFUND_CEILING")
        for flag in ALWAYS_FALSE_FLAGS:
            self.assertIs(view[flag], False)


class BindingPropertyTests(unittest.TestCase):
    def assert_unchanged(self, book, before, label):
        self.assertEqual(canon(book.view("c")), before, label)

    def test_d_claim_binding(self):
        for seed in SEEDS:
            r = rng(seed)
            gross = r.choice((2, 1000, CONTRACT_MONEY_MAX - 1))
            bps = r.choice((1, 9999, r.randint(1, 9999)))
            book = MockSettlement()
            args = dict(trade_id="t", gross=gross, debtor_role="d", policy=policy(bps))
            book.recognize_claim("c", **args)
            before = canon(book.view("c"))
            again = book.recognize_claim("c", **args)
            self.assertEqual((again["duplicate"], again["applied"]), (True, None))
            self.assertEqual(canon(again["claim"]), before)
            self.assert_unchanged(book, before, seed)
            changes = {
                "trade_id": dict(args, trade_id="t-2"),
                "gross": dict(args, gross=gross + 1),
                "debtor_role": dict(args, debtor_role="d-2"),
                "fee_bps": dict(args, policy=policy(bps - 1)),
                "residual_payee": dict(args, policy=policy(bps, residual="other-residual")),
                "fee_payee": dict(args, policy=policy(bps, fee="other-fee")),
            }
            for field, changed in changes.items():
                with self.subTest(seed=seed, field=field):
                    self.assertEqual(code_of(lambda: book.recognize_claim("c", **changed)), "CLAIM_BINDING_CONFLICT")
                    self.assert_unchanged(book, before, field)

    def test_d_statement_binding(self):
        for seed in SEEDS:
            r = rng(seed)
            book = opened(CONTRACT_MONEY_MAX, r.randint(1, 9999))
            parts = [r.randint(1, 10**9) for _ in range(5)]
            amount, fee, tax, held, adjustment = parts
            gross = sum(parts)
            base = [gross, amount, fee, tax, held, adjustment, "reason-a"]
            book.observe_settlement_statement("c", **statement_kwargs("m-1", tuple(base)))
            before = canon(book.view("c"))
            again = book.observe_settlement_statement("c", **statement_kwargs("m-1", tuple(base)))
            self.assertEqual((again["duplicate"], again["applied"]), (True, None))
            self.assertEqual(canon(again["claim"]), before)
            self.assert_unchanged(book, before, seed)
            names = ("gross", "amount", "fee", "tax", "held", "adjustment", "adjustment_reason")
            for index, field in enumerate(names):
                changed = list(base)
                if field == "gross":
                    changed[0] += 1
                    changed[1] += 1  # keep the component identity
                elif field == "adjustment_reason":
                    changed[6] = "reason-b"
                elif field == "amount":
                    changed[1] += 1
                    changed[2] -= 1
                else:
                    changed[index] += 1
                    changed[1] -= 1
                with self.subTest(seed=seed, field=field):
                    code = code_of(lambda: book.observe_settlement_statement("c", **statement_kwargs("m-1", tuple(changed))))
                    self.assertEqual(code, "STATEMENT_BINDING_CONFLICT")
                    self.assert_unchanged(book, before, field)

    def test_d_refund_binding(self):
        # REFUND_BINDING_CONFLICT had no test before this suite (validation record, section 7).
        for seed in SEEDS:
            r = rng(seed)
            gross = r.choice((3, 1000, CONTRACT_MONEY_MAX))
            book = opened(gross, r.randint(0, 10000))
            amount = r.randint(1, gross - 1)
            args = dict(refund_id="r-1", amount=amount, beneficiary_role="buyer", reason="why")
            book.bind_refund("c", **args)
            before = canon(book.view("c"))
            again = book.bind_refund("c", **args)
            self.assertEqual((again["duplicate"], again["applied"]), (True, None))
            self.assertEqual(canon(again["claim"]), before)
            for field, value in (("amount", amount + 1), ("beneficiary_role", "buyer-2"), ("reason", "why-2")):
                with self.subTest(seed=seed, field=field):
                    changed = dict(args, **{field: value})
                    self.assertEqual(code_of(lambda: book.bind_refund("c", **changed)), "REFUND_BINDING_CONFLICT")
                    self.assert_unchanged(book, before, field)

    def test_d_acceptance_binding(self):
        for seed in SEEDS:
            r = rng(seed)
            book = opened(CONTRACT_MONEY_MAX, 100)
            book.bind_refund("c", refund_id="r-1", amount=CONTRACT_MONEY_MAX, beneficiary_role="b", reason="why")
            amount = r.randint(2, 10**9)
            book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=amount)
            before = canon(book.view("c"))
            again = book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=amount)
            self.assertEqual((again["duplicate"], again["applied"]), (True, None))
            self.assertEqual(canon(again["claim"]), before)
            for other in (amount + 1, amount - 1):
                with self.subTest(seed=seed, amount=other):
                    code = code_of(lambda: book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=other))
                    self.assertEqual(code, "ACCEPTANCE_BINDING_CONFLICT")
                    self.assert_unchanged(book, before, other)


class MachinePropertyTests(unittest.TestCase):
    REQUIRED = (
        "ok:initiate",
        "ok:authorize",
        "ok:capture",
        "ok:commit",
        "ok:observe_statement",
        "ok:distribute",
        "ok:bind_refund",
        "ok:observe_mock_cancel_acceptance",
        "ok:reconcile",
        "ok:fail",
        "ok:cancel",
        "reject:ILLEGAL_TRANSITION",
        "reject:TERMINAL_IMMUTABLE",
        "reject:UNKNOWN_SETTLEMENT",
        "reject:IDEMPOTENCY_CONFLICT",
        "reject:SETTLEMENT_COMPONENT_MISMATCH",
        "reject:SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        "reject:INVALID_AMOUNT",
        "replay:initiate",
        "replay:observe_statement",
        "restore-check",
    )

    def test_e_seeded_command_sequences(self):
        total = {}
        for seed in SEEDS:
            driver = MachineDriver(seed)
            with self.subTest(seed=seed):
                driver.run()
            for name, count in driver.counts.items():
                total[name] = total.get(name, 0) + count
        for name in self.REQUIRED:
            self.assertGreater(total.get(name, 0), 0, name)

    def test_e_every_journal_prefix_restores_to_itself(self):
        for seed in SEEDS[:3]:
            driver = MachineDriver(seed, steps=60)
            driver.run()
            journal = driver.m.export_journal()
            for length in range(len(journal) + 1):
                with self.subTest(seed=seed, prefix=length):
                    restored = SettlementMachine.restore(journal[:length])
                    self.assertEqual(restored.export_journal(), journal[:length])
                    self.assertEqual(SettlementMachine.restore(restored.export_journal()).state_digest(), restored.state_digest())

    def committed(self, gross=100, amount=100):
        machine = SettlementMachine()
        machine.initiate("s", idempotency_key="k-init", trade_id="t", gross=gross, debtor_role="d", policy=policy(500))
        machine.authorize("s", idempotency_key="k-auth")
        machine.capture("s", idempotency_key="k-cap")
        machine.commit(
            "s",
            idempotency_key="k-commit",
            **statement_kwargs("mv-1", (gross, amount, gross - amount, 0, 0, 0, None)),
        )
        return machine

    def test_e_rejected_key_is_bound_live_and_forgotten_after_restore(self):
        # Contract sections 9.3 and 9.4 (class A).
        machine = SettlementMachine()
        bad = dict(trade_id="t", gross=0, debtor_role="d", policy=policy(10))
        first = code_of(lambda: machine.initiate("s", idempotency_key="k-1", **bad))
        self.assertEqual(first, "INVALID_AMOUNT")
        self.assertEqual(code_of(lambda: machine.initiate("s", idempotency_key="k-1", **bad)), first)
        fixed = dict(bad, gross=100)
        self.assertEqual(code_of(lambda: machine.initiate("s", idempotency_key="k-1", **fixed)), "IDEMPOTENCY_CONFLICT")
        restored = SettlementMachine.restore(machine.export_journal())
        self.assertEqual(restored.initiate("s", idempotency_key="k-1", **fixed)["applied"], "initiate")

    def test_e_characterization_new_key_repeat_of_a_bound_statement_is_economically_inert(self):
        # Section 8 class B: the contract defines key replays (9.3) and binding
        # repeats (1) but not an FSM command that repeats a bound movement_id
        # under a new key. Observed: the FSM journals it. Only the economics are asserted.
        machine = self.committed(gross=100, amount=60)
        before = canon(machine.view("s")["claim"])
        machine.observe_statement(
            "s", idempotency_key="k-again", **statement_kwargs("mv-1", (100, 60, 40, 0, 0, 0, None))
        )
        self.assertEqual(canon(machine.view("s")["claim"]), before)
        machine.bind_refund("s", idempotency_key="k-rf", refund_id="rf", amount=10, beneficiary_role="b", reason="why")
        machine.observe_mock_cancel_acceptance("s", idempotency_key="k-ac", source_id="ac", amount=5)
        before = canon(machine.view("s")["claim"])
        machine.bind_refund("s", idempotency_key="k-rf2", refund_id="rf", amount=10, beneficiary_role="b", reason="why")
        machine.observe_mock_cancel_acceptance("s", idempotency_key="k-ac2", source_id="ac", amount=5)
        self.assertEqual(canon(machine.view("s")["claim"]), before)
        restored = SettlementMachine.restore(machine.export_journal())
        self.assertEqual(restored.state_digest(), machine.state_digest())

    def test_e_characterization_zero_cash_commit_then_distribute_conserves(self):
        # Section 8 class B: section 9.2 says the zero-cash order freeze is not
        # in this machine's accept path; a commit with amount 0 reaches it. Only
        # conservation is asserted. The freeze itself is not pinned here.
        machine = self.committed(gross=100, amount=0)
        result = machine.distribute("s", idempotency_key="k-dist", order=[RESIDUAL, FEE])
        self.assertEqual(sum(result["effect"].values()), 0)
        claim = machine.view("s")["claim"]
        check_claim_view(claim)
        self.assertEqual(claim["distributed_cash"], 0)
        self.assertEqual([item["outstanding"] for item in claim["obligations"]], [item["face"] for item in claim["obligations"]])


class NegativeControlTests(unittest.TestCase):
    """The property oracles must fail on a deliberately broken in-memory copy.

    Each control patches an attribute in memory with unittest.mock and never
    touches a source file. AssertionError is required: a SettlementError from
    the mock's own guard would mean the oracle did not see the fault.
    MockSettlement._invariant is silenced so the mock's guards cannot mask it.
    """

    def run_all(self, driver_factory):
        for seed in SEEDS:
            driver_factory(seed).run()

    def test_control_split_that_drops_one_won_is_caught(self):
        real = mock_settlement._split

        def drop_one(gross, pol):
            lines = real(gross, pol)
            biggest = max(sorted(lines), key=lambda payee: lines[payee]["face"])
            lines[biggest]["face"] -= 1
            return lines

        with mock.patch.object(mock_settlement, "_split", drop_one), mock.patch.object(
            MockSettlement, "_invariant", lambda self, claim: None
        ):
            with self.assertRaises(AssertionError):
                self.run_all(MockDriver)
            with self.assertRaises(AssertionError):
                SplitPropertyTests("test_a_contract_money_max_matches_the_mock_constant").check_split(1000, 500)
        self.assertIs(mock_settlement._split, real)

    def test_control_outstanding_that_ignores_cancelled_unpaid_is_caught(self):
        real = mock_settlement._outstanding

        def wrong(obligation):
            return obligation["face"] - obligation["distributed"]

        with mock.patch.object(mock_settlement, "_outstanding", wrong), mock.patch.object(
            MockSettlement, "_invariant", lambda self, claim: None
        ):
            with self.assertRaises(AssertionError):
                self.run_all(MockDriver)
        self.assertIs(mock_settlement._outstanding, real)

    def test_control_rejected_statement_that_mutates_state_is_caught(self):
        real = MockSettlement.observe_settlement_statement

        def mutate_then_raise(self, claim_id, **kwargs):
            try:
                return real(self, claim_id, **kwargs)
            except SettlementError:
                claim = self._claims.get(claim_id)
                if claim is not None:
                    claim["confirmed_cash"] += 1
                raise

        with mock.patch.object(MockSettlement, "observe_settlement_statement", mutate_then_raise):
            with self.assertRaisesRegex(AssertionError, "view changed after a rejected call"):
                self.run_all(MockDriver)
        self.assertIs(MockSettlement.observe_settlement_statement, real)

    def test_control_journal_export_that_drops_its_last_entry_is_caught(self):
        real = SettlementMachine.export_journal

        def short(self):
            return real(self)[:-1]

        with mock.patch.object(SettlementMachine, "export_journal", short):
            with self.assertRaises(AssertionError):
                self.run_all(MachineDriver)
        self.assertIs(SettlementMachine.export_journal, real)

    def test_control_restore_that_loses_a_key_binding_is_caught(self):
        real = SettlementMachine.restore.__func__

        def forget(cls, journal):
            machine = real(cls, journal)
            machine._idempotency.clear()
            return machine

        with mock.patch.object(SettlementMachine, "restore", classmethod(forget)):
            with self.assertRaises(AssertionError):
                self.run_all(MachineDriver)


if __name__ == "__main__":
    unittest.main()
