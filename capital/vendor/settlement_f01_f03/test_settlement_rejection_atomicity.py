"""Rejection-atomicity audit for the settlement state machine and its mock.

Existing coverage map: test_settlement_fsm.py and test_mock_settlement.py
already exercise nearly every settlement rejection code, and
test_contract_error_codes.py pins the code set. Their ``canonical_state``
before/after checks are same-machine comparisons. This file adds what
they cannot see: an untouched control machine, the
``restore(export_journal())`` round trip on both sides, one later valid
command on both sides, and a test-owned late-failure seam.

Each ``*_leaves_no_trace`` case drives one rejection code at one mutation
boundary of one REPLAYABLE command, then compares the machine that saw
the rejected call with the control: state_digest, canonical_state,
export_journal and the restore round trip. A stored rejection (same key,
same canonical arguments, same error replayed) is the only trace the
comparison allows; ``_idempotency`` sits outside canonical_state.

Mutation boundaries, per command (the mock is mutated at, and only at,
these points):

* ``initiate``: ``_cases[id]`` insert, then ``_phase_book_invariant``,
  then ``_accept`` (journal append).
* ``authorize``/``fail``/``cancel``: case field and phase write, then
  ``_phase_book_invariant``, then ``_accept``.
* ``capture``: ``MockSettlement.recognize_claim`` (claim insert, after its
  own ``_invariant``), then phase write, ``_phase_book_invariant``,
  ``_accept``.
* ``commit``: ``MockSettlement.observe_settlement_statement`` (statement
  insert, then its ``_invariant``), ``commit_movement_id`` and phase write,
  ``_phase_book_invariant``, ``_accept``.
* ``observe_statement``, ``distribute``, ``bind_refund``,
  ``observe_mock_cancel_acceptance``: one mock mutation each, then its
  ``_invariant``, then ``_phase_book_invariant``, ``_accept``.

Every deterministic rejection code is raised before the first mutation
of its command. The only points a rejection could still fire after a
mutation are the ``MOCK_INVARIANT`` checks, which no caller input
reaches, so those get fault injection instead (``test_fault_*`` and
``test_mock_fault_*``).

Not-applicable rows: ``view``, ``export_journal``, ``canonical_state`` and
``state_digest`` are read-only. ``CLAIM_BINDING_CONFLICT`` in
``capture`` is unreachable: a claim exists only in CAPTURED/COMMITTED and
``capture`` runs once, from AUTHORIZED. The ``duplicate is False``
``MOCK_INVARIANT`` checks in ``capture``/``commit`` have no caller input.

Contract status: SETTLEMENT_DISTRIBUTION_F01_F03.md defines the error
codes but states no rejection-atomicity clause for this machine, and
defines ``MOCK_INVARIANT`` only as an implementation error. The
deterministic cases pin observed behavior; the fault cases are class B
characterizations. Neither invents semantics, and nothing here edits the
machine or the mock.

Fault seams: neither machine keeps a rollback wrapper. A fault at
``SettlementMachine._phase_book_invariant`` therefore leaves the
mutation applied but unjournaled (journal equal to the control,
canonical_state divergent, ``restore(export_journal())`` equal to the
control). A fault at ``MockSettlement._invariant`` leaves what the mock had
written by then; ``capture`` fails before its claim insert and leaves no
trace. Each outcome is pinned as observed, not as a requirement.
"""

import unittest
from unittest import mock

from mock_settlement import MockSettlement
from settlement_fsm import (
    REPLAYABLE,
    SettlementError,
    SettlementMachine,
)
from test_settlement_fsm import codes, policy

SID = "claim-1"


class SettlementRejectionAtomicityTests(unittest.TestCase):
    # --- command helpers ------------------------------------------------------

    def initiate(self, machine, sid=SID, idem="init-1", **changes):
        body = dict(
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        body.update(changes)
        return machine.initiate(sid, idempotency_key=idem, **body)

    def authorize(self, machine, sid=SID, idem="auth-1"):
        return machine.authorize(sid, idempotency_key=idem)

    def capture(self, machine, sid=SID, idem="cap-1"):
        return machine.capture(sid, idempotency_key=idem)

    def commit(self, machine, sid=SID, idem="commit-1", **changes):
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
        return machine.commit(sid, idempotency_key=idem, **body)

    def commit_partial(self, machine, sid=SID, idem="commit-1"):
        return self.commit(
            machine, sid, idem, gross=60_000, amount=58_000, fee=2_000
        )

    def fail_case(self, machine, sid=SID, idem="fail-1", reason="fixture-fail"):
        return machine.fail(sid, idempotency_key=idem, reason=reason)

    def cancel_case(self, machine, sid=SID, idem="cancel-1", reason="fixture-cancel"):
        return machine.cancel(sid, idempotency_key=idem, reason=reason)

    def statement(self, machine, sid=SID, idem="stmt-1", **changes):
        body = dict(
            movement_id="move-2",
            gross=40_000,
            amount=40_000,
            fee=0,
            tax=0,
            held=0,
            adjustment=0,
        )
        body.update(changes)
        return machine.observe_statement(sid, idempotency_key=idem, **body)

    def distribute(self, machine, sid=SID, idem="dist-1", order=None):
        return machine.distribute(
            sid,
            idempotency_key=idem,
            order=["organizer", "platform"] if order is None else order,
        )

    def refund(self, machine, sid=SID, idem="refund-1", **changes):
        body = dict(
            refund_id="refund-1",
            amount=30_000,
            beneficiary_role="buyer",
            reason="fixture-refund",
        )
        body.update(changes)
        return machine.bind_refund(sid, idempotency_key=idem, **body)

    def accept(self, machine, sid=SID, idem="accept-1", **changes):
        body = dict(source_id="accept-src-1", amount=10_000)
        body.update(changes)
        return machine.observe_mock_cancel_acceptance(
            sid, idempotency_key=idem, **body
        )

    # --- later valid command per pair (run on both sides) ---------------------------

    def later_initiate(self, machine):
        return self.initiate(machine, "claim-2", "init-2")

    def later_authorize(self, machine):
        return self.authorize(machine, idem="auth-2")

    def later_capture(self, machine):
        return self.capture(machine, idem="cap-2")

    def later_commit(self, machine):
        return self.commit(machine, idem="commit-2")

    def later_distribute(self, machine):
        return self.distribute(machine, idem="dist-2")

    def later_statement(self, machine):
        return self.statement(machine, idem="stmt-2")

    def later_refund(self, machine):
        return self.refund(machine, idem="refund-2", refund_id="refund-2", amount=10_000)

    def later_accept(self, machine):
        return self.accept(machine, idem="accept-2", source_id="accept-src-2")

    # --- machine/control pair builders ---------------------------------------------

    def pair(self, *steps):
        machine, control = SettlementMachine(), SettlementMachine()
        for side in (machine, control):
            for step in steps:
                step(side)
        return machine, control

    def fresh_pair(self):
        return self.pair()

    def initiated_pair(self):
        return self.pair(self.initiate)

    def authorized_pair(self):
        return self.pair(self.initiate, self.authorize)

    def captured_pair(self):
        return self.pair(self.initiate, self.authorize, self.capture)

    def committed_pair(self):
        return self.pair(self.initiate, self.authorize, self.capture, self.commit)

    def partial_pair(self):
        return self.pair(
            self.initiate, self.authorize, self.capture, self.commit_partial
        )

    def failed_pair(self):
        return self.pair(self.initiate, self.fail_case)

    def cancelled_pair(self):
        return self.pair(self.initiate, self.cancel_case)

    def distributed_pair(self):
        return self.pair(
            self.initiate, self.authorize, self.capture, self.commit, self.distribute
        )

    def refunded_pair(self):
        return self.pair(
            self.initiate, self.authorize, self.capture, self.commit, self.refund
        )

    def accepted_pair(self):
        return self.pair(
            self.initiate,
            self.authorize,
            self.capture,
            self.commit,
            self.refund,
            self.accept,
        )

    # --- comparison harness -----------------------------------------------------------

    def assert_same_as(self, machine, control):
        self.assertEqual(machine.state_digest(), control.state_digest())
        self.assertEqual(machine.canonical_state(), control.canonical_state())
        self.assertEqual(machine.export_journal(), control.export_journal())
        for side in (machine, control):
            restored = SettlementMachine.restore(side.export_journal())
            self.assertEqual(restored.canonical_state(), side.canonical_state())
            self.assertEqual(restored.state_digest(), side.state_digest())

    def assert_unapplied_mutation(self, machine, control):
        """Pin the fault-seam characterization: mutation applied, not journaled."""
        self.assertEqual(machine.export_journal(), control.export_journal())
        self.assertNotEqual(machine.canonical_state(), control.canonical_state())
        self.assertNotEqual(machine.state_digest(), control.state_digest())
        restored = SettlementMachine.restore(machine.export_journal())
        self.assertEqual(restored.canonical_state(), control.canonical_state())
        self.assertNotEqual(restored.canonical_state(), machine.canonical_state())
        # reconcile replays the journal and notices the divergence.
        self.assertEqual(
            codes(lambda: machine.reconcile(SID, idempotency_key="recon-fault")),
            "MOCK_INVARIANT",
        )

    def reject(self, code, fn):
        self.assertEqual(codes(fn), code)
        # The same key with the same canonical arguments replays the stored
        # error; that idempotency record is the only trace a rejection may
        # leave, and it sits outside canonical_state.
        self.assertEqual(codes(fn), code)

    def check(self, code, pair, attempt, later):
        machine, control = pair
        self.reject(code, lambda: attempt(machine))
        self.assert_same_as(machine, control)
        self.assertEqual(later(machine), later(control))
        self.assert_same_as(machine, control)

    def phase_fault(self):
        return mock.patch.object(
            SettlementMachine,
            "_phase_book_invariant",
            side_effect=[SettlementError("MOCK_INVARIANT")],
        )

    def mock_fault(self):
        return mock.patch.object(
            MockSettlement,
            "_invariant",
            side_effect=[SettlementError("MOCK_INVARIANT")],
        )

    # --- initiate ------------------------------------------------------------------------

    def test_initiate_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.initiate(m, sid=" ", idem="bad-1"),
            self.later_initiate,
        )

    def test_initiate_invalid_trade_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", trade_id=""),
            self.later_initiate,
        )

    def test_initiate_invalid_debtor_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", debtor_role=" x"),
            self.later_initiate,
        )

    def test_initiate_currency_unsupported_leaves_no_trace(self):
        self.check(
            "CURRENCY_UNSUPPORTED",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", currency="USD"),
            self.later_initiate,
        )

    def test_initiate_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", gross=0),
            self.later_initiate,
        )

    def test_initiate_policy_type_leaves_no_trace(self):
        self.check(
            "POLICY_TYPE",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", policy=[]),
            self.later_initiate,
        )

    def test_initiate_policy_fields_leaves_no_trace(self):
        bad = policy()
        del bad["fee_payee"]
        self.check(
            "POLICY_FIELDS",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", policy=bad),
            self.later_initiate,
        )

    def test_initiate_policy_kind_leaves_no_trace(self):
        self.check(
            "POLICY_KIND",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", policy=policy(kind="OTHER")),
            self.later_initiate,
        )

    def test_initiate_policy_fee_bps_leaves_no_trace(self):
        self.check(
            "POLICY_FEE_BPS",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", policy=policy(fee_bps=10_001)),
            self.later_initiate,
        )

    def test_initiate_policy_payee_leaves_no_trace(self):
        self.check(
            "POLICY_PAYEE",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", policy=policy(fee_payee="")),
            self.later_initiate,
        )

    def test_initiate_policy_payee_collision_leaves_no_trace(self):
        self.check(
            "POLICY_PAYEE_COLLISION",
            self.fresh_pair(),
            lambda m: self.initiate(
                m, idem="bad-1", policy=policy(fee_payee="organizer")
            ),
            self.later_initiate,
        )

    def test_initiate_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.initiated_pair(),
            lambda m: self.initiate(m, idem="bad-1"),
            self.later_authorize,
        )

    def test_initiate_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.initiate(m, idem="bad-1"),
            self.later_initiate,
        )

    # --- authorize -------------------------------------------------------------------------

    def test_authorize_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.authorize(m, sid=" ", idem="bad-1"),
            self.later_authorize,
        )

    def test_authorize_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.initiated_pair(),
            lambda m: self.authorize(m, sid="ghost", idem="bad-1"),
            self.later_authorize,
        )

    def test_authorize_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.authorize(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_authorize_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.authorized_pair(),
            lambda m: self.authorize(m, idem="bad-1"),
            self.later_capture,
        )

    # --- capture ---------------------------------------------------------------------------

    def test_capture_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.authorized_pair(),
            lambda m: self.capture(m, sid="", idem="bad-1"),
            self.later_capture,
        )

    def test_capture_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.authorized_pair(),
            lambda m: self.capture(m, sid="ghost", idem="bad-1"),
            self.later_capture,
        )

    def test_capture_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.cancelled_pair(),
            lambda m: self.capture(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_capture_illegal_transition_before_authorize_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.initiated_pair(),
            lambda m: self.capture(m, idem="bad-1"),
            self.later_authorize,
        )

    def test_capture_illegal_transition_after_commit_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.committed_pair(),
            lambda m: self.capture(m, idem="bad-1"),
            self.later_distribute,
        )

    # --- commit ----------------------------------------------------------------------------

    def test_commit_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.captured_pair(),
            lambda m: self.commit(m, sid=" ", idem="bad-1"),
            self.later_commit,
        )

    def test_commit_invalid_movement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.captured_pair(),
            lambda m: self.commit(m, idem="bad-1", movement_id=""),
            self.later_commit,
        )

    def test_commit_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.captured_pair(),
            lambda m: self.commit(m, idem="bad-1", gross=0),
            self.later_commit,
        )

    def test_commit_invalid_nonnegative_leaves_no_trace(self):
        self.check(
            "INVALID_NONNEGATIVE",
            self.captured_pair(),
            lambda m: self.commit(m, idem="bad-1", fee=-1),
            self.later_commit,
        )

    def test_commit_adjustment_reason_required_leaves_no_trace(self):
        self.check(
            "ADJUSTMENT_REASON_REQUIRED",
            self.captured_pair(),
            lambda m: self.commit(
                m, idem="bad-1", amount=96_000, adjustment=1_000
            ),
            self.later_commit,
        )

    def test_commit_adjustment_reason_unexpected_leaves_no_trace(self):
        self.check(
            "ADJUSTMENT_REASON_UNEXPECTED",
            self.captured_pair(),
            lambda m: self.commit(m, idem="bad-1", adjustment_reason="stray"),
            self.later_commit,
        )

    def test_commit_component_mismatch_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_COMPONENT_MISMATCH",
            self.captured_pair(),
            lambda m: self.commit(m, idem="bad-1", amount=96_000),
            self.later_commit,
        )

    def test_commit_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.captured_pair(),
            lambda m: self.commit(m, sid="ghost", idem="bad-1"),
            self.later_commit,
        )

    def test_commit_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.commit(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_commit_illegal_transition_before_capture_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.authorized_pair(),
            lambda m: self.commit(m, idem="bad-1"),
            self.later_capture,
        )

    def test_commit_illegal_transition_after_commit_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.committed_pair(),
            lambda m: self.commit(m, idem="bad-1", movement_id="move-9"),
            self.later_distribute,
        )

    def test_commit_exceeds_open_receivable_leaves_no_trace(self):
        # Raised inside the mock before the statement insert.
        self.check(
            "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
            self.captured_pair(),
            lambda m: self.commit(
                m, idem="bad-1", gross=100_001, amount=97_001, fee=3_000
            ),
            self.later_commit,
        )

    # --- fail / cancel -----------------------------------------------------------------------

    def test_fail_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.fail_case(m, sid=" ", idem="bad-1"),
            self.later_authorize,
        )

    def test_fail_invalid_reason_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.fail_case(m, idem="bad-1", reason=""),
            self.later_authorize,
        )

    def test_fail_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.initiated_pair(),
            lambda m: self.fail_case(m, sid="ghost", idem="bad-1"),
            self.later_authorize,
        )

    def test_fail_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.fail_case(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_fail_illegal_transition_after_capture_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.captured_pair(),
            lambda m: self.fail_case(m, idem="bad-1"),
            self.later_commit,
        )

    def test_fail_illegal_transition_after_commit_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.committed_pair(),
            lambda m: self.fail_case(m, idem="bad-1"),
            self.later_distribute,
        )

    def test_cancel_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.cancel_case(m, sid=" ", idem="bad-1"),
            self.later_authorize,
        )

    def test_cancel_invalid_reason_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.cancel_case(m, idem="bad-1", reason=" "),
            self.later_authorize,
        )

    def test_cancel_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.initiated_pair(),
            lambda m: self.cancel_case(m, sid="ghost", idem="bad-1"),
            self.later_authorize,
        )

    def test_cancel_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.cancelled_pair(),
            lambda m: self.cancel_case(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_cancel_illegal_transition_after_capture_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.captured_pair(),
            lambda m: self.cancel_case(m, idem="bad-1"),
            self.later_commit,
        )

    def test_cancel_illegal_transition_after_commit_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.committed_pair(),
            lambda m: self.cancel_case(m, idem="bad-1"),
            self.later_distribute,
        )

    # --- observe_statement -----------------------------------------------------------------

    def test_observe_statement_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.partial_pair(),
            lambda m: self.statement(m, sid=" ", idem="bad-1"),
            self.later_statement,
        )

    def test_observe_statement_invalid_movement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", movement_id=""),
            self.later_statement,
        )

    def test_observe_statement_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", gross=0),
            self.later_statement,
        )

    def test_observe_statement_invalid_nonnegative_leaves_no_trace(self):
        self.check(
            "INVALID_NONNEGATIVE",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", tax=-1),
            self.later_statement,
        )

    def test_observe_statement_adjustment_reason_required_leaves_no_trace(self):
        self.check(
            "ADJUSTMENT_REASON_REQUIRED",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", amount=39_000, adjustment=1_000),
            self.later_statement,
        )

    def test_observe_statement_adjustment_reason_unexpected_leaves_no_trace(self):
        self.check(
            "ADJUSTMENT_REASON_UNEXPECTED",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", adjustment_reason="stray"),
            self.later_statement,
        )

    def test_observe_statement_component_mismatch_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_COMPONENT_MISMATCH",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", amount=39_000),
            self.later_statement,
        )

    def test_observe_statement_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.partial_pair(),
            lambda m: self.statement(m, sid="ghost", idem="bad-1"),
            self.later_statement,
        )

    def test_observe_statement_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.statement(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_observe_statement_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.captured_pair(),
            lambda m: self.statement(m, idem="bad-1"),
            self.later_commit,
        )

    def test_observe_statement_binding_conflict_leaves_no_trace(self):
        # movement-1 is already bound by the partial commit to a different body.
        self.check(
            "STATEMENT_BINDING_CONFLICT",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", movement_id="move-1"),
            self.later_statement,
        )

    def test_observe_statement_exceeds_open_receivable_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
            self.partial_pair(),
            lambda m: self.statement(m, idem="bad-1", gross=40_001, amount=40_001),
            self.later_statement,
        )

    # --- distribute --------------------------------------------------------------------------

    def test_distribute_order_type_leaves_no_trace(self):
        # Rejected before the key is bound, so nothing is stored either.
        self.check(
            "DISTRIBUTION_ORDER_TYPE",
            self.committed_pair(),
            lambda m: self.distribute(m, idem="bad-1", order="organizer"),
            self.later_distribute,
        )

    def test_distribute_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.distribute(m, sid=" ", idem="bad-1"),
            self.later_distribute,
        )

    def test_distribute_invalid_payee_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.distribute(m, idem="bad-1", order=["organizer", ""]),
            self.later_distribute,
        )

    def test_distribute_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.committed_pair(),
            lambda m: self.distribute(m, sid="ghost", idem="bad-1"),
            self.later_distribute,
        )

    def test_distribute_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.distribute(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_distribute_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.captured_pair(),
            lambda m: self.distribute(m, idem="bad-1"),
            self.later_commit,
        )

    def test_distribute_order_duplicate_leaves_no_trace(self):
        self.check(
            "DISTRIBUTION_ORDER_DUPLICATE",
            self.committed_pair(),
            lambda m: self.distribute(m, idem="bad-1", order=["organizer", "organizer"]),
            self.later_distribute,
        )

    def test_distribute_order_mismatch_leaves_no_trace(self):
        self.check(
            "DISTRIBUTION_ORDER_MISMATCH",
            self.committed_pair(),
            lambda m: self.distribute(m, idem="bad-1", order=["organizer"]),
            self.later_distribute,
        )

    def test_distribute_order_frozen_leaves_no_trace(self):
        self.check(
            "DISTRIBUTION_ORDER_FROZEN",
            self.distributed_pair(),
            lambda m: self.distribute(m, idem="bad-1", order=["platform", "organizer"]),
            self.later_distribute,
        )

    def test_distribute_order_mismatch_with_open_refund_leaves_no_trace(self):
        # B5 (SET-POLICY-DRAFT-0.4): an open partial refund reports REQUESTER
        # and no longer blocks apply_distribution. The order checks still fire
        # in that state, and the follow-up valid distribute succeeds on both
        # sides of the pair.
        pair = self.refunded_pair()
        for side in pair:
            claim = side.view(SID)["claim"]
            self.assertEqual(claim["refund_bearer_policy"], "REQUESTER")
            self.assertIs(claim["distribution_blocked"], False)
        self.check(
            "DISTRIBUTION_ORDER_MISMATCH",
            pair,
            lambda m: self.distribute(m, idem="bad-1", order=["organizer"]),
            self.later_distribute,
        )

    # --- bind_refund -------------------------------------------------------------------------

    def test_bind_refund_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.refund(m, sid=" ", idem="bad-1"),
            self.later_refund,
        )

    def test_bind_refund_invalid_refund_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.refund(m, idem="bad-1", refund_id=""),
            self.later_refund,
        )

    def test_bind_refund_invalid_beneficiary_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.refund(m, idem="bad-1", beneficiary_role=" "),
            self.later_refund,
        )

    def test_bind_refund_invalid_reason_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: self.refund(m, idem="bad-1", reason=""),
            self.later_refund,
        )

    def test_bind_refund_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.committed_pair(),
            lambda m: self.refund(m, idem="bad-1", amount=0),
            self.later_refund,
        )

    def test_bind_refund_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.committed_pair(),
            lambda m: self.refund(m, sid="ghost", idem="bad-1"),
            self.later_refund,
        )

    def test_bind_refund_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.refund(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_bind_refund_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.authorized_pair(),
            lambda m: self.refund(m, idem="bad-1"),
            self.later_capture,
        )

    def test_bind_refund_binding_conflict_leaves_no_trace(self):
        self.check(
            "REFUND_BINDING_CONFLICT",
            self.refunded_pair(),
            lambda m: self.refund(m, idem="bad-1", amount=20_000),
            self.later_refund,
        )

    def test_bind_refund_ceiling_leaves_no_trace(self):
        self.check(
            "REFUND_CEILING",
            self.refunded_pair(),
            lambda m: self.refund(m, idem="bad-1", refund_id="refund-9", amount=70_001),
            self.later_refund,
        )

    def test_bind_refund_beneficiary_conflict_leaves_no_trace(self):
        self.check(
            "REFUND_BENEFICIARY_CONFLICT",
            self.refunded_pair(),
            lambda m: self.refund(
                m, idem="bad-1", refund_id="refund-9", amount=10_000, beneficiary_role="seller"
            ),
            self.later_refund,
        )

    # --- observe_mock_cancel_acceptance -----------------------------------------------------

    def test_acceptance_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.refunded_pair(),
            lambda m: self.accept(m, sid=" ", idem="bad-1"),
            self.later_accept,
        )

    def test_acceptance_invalid_source_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.refunded_pair(),
            lambda m: self.accept(m, idem="bad-1", source_id=""),
            self.later_accept,
        )

    def test_acceptance_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.refunded_pair(),
            lambda m: self.accept(m, idem="bad-1", amount=0),
            self.later_accept,
        )

    def test_acceptance_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.refunded_pair(),
            lambda m: self.accept(m, sid="ghost", idem="bad-1"),
            self.later_accept,
        )

    def test_acceptance_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.failed_pair(),
            lambda m: self.accept(m, idem="bad-1"),
            self.later_initiate,
        )

    def test_acceptance_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.initiated_pair(),
            lambda m: self.accept(m, idem="bad-1"),
            self.later_authorize,
        )

    def test_acceptance_binding_conflict_leaves_no_trace(self):
        self.check(
            "ACCEPTANCE_BINDING_CONFLICT",
            self.accepted_pair(),
            lambda m: self.accept(m, idem="bad-1", amount=5_000),
            self.later_accept,
        )

    def test_acceptance_refund_obligation_required_leaves_no_trace(self):
        self.check(
            "REFUND_OBLIGATION_REQUIRED",
            self.committed_pair(),
            lambda m: self.accept(m, idem="bad-1"),
            self.later_distribute,
        )

    def test_acceptance_exceeds_obligation_leaves_no_trace(self):
        self.check(
            "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
            self.refunded_pair(),
            lambda m: self.accept(m, idem="bad-1", amount=30_001),
            self.later_accept,
        )

    # --- reconcile / reject_external (not journaled) -------------------------------------------

    def test_reconcile_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.committed_pair(),
            lambda m: m.reconcile("ghost", idempotency_key="bad-1"),
            self.later_distribute,
        )

    def test_reconcile_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.committed_pair(),
            lambda m: m.reconcile(" ", idempotency_key="bad-1"),
            self.later_distribute,
        )

    def test_reject_external_leaves_no_trace(self):
        machine, control = self.committed_pair()
        self.reject("EXTERNAL_PAYMENT_UNSUPPORTED", lambda: machine.reject_external("BANK_TRANSFER"))
        self.reject("INVALID_ID", lambda: machine.reject_external(""))
        self.assert_same_as(machine, control)
        self.assertEqual(self.later_distribute(machine), self.later_distribute(control))
        self.assert_same_as(machine, control)

    # --- idempotency boundaries ---------------------------------------------------------------------

    def test_invalid_idempotency_key_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.initiated_pair(),
            lambda m: self.authorize(m, idem=" "),
            self.later_authorize,
        )

    def test_idempotency_conflict_leaves_no_trace(self):
        self.check(
            "IDEMPOTENCY_CONFLICT",
            self.initiated_pair(),
            lambda m: self.initiate(m, gross=90_000),
            self.later_authorize,
        )

    def test_unfingerprintable_rejection_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.fresh_pair(),
            lambda m: self.initiate(m, idem="bad-1", gross=object()),
            lambda m: self.initiate(m, idem="bad-1"),
        )

    # --- restore boundary (classmethod; no live machine touched) -------------------------------------

    def test_restore_invalid_journal_variants(self):
        entry = {
            "op": "authorize",
            "idempotency_key": "k",
            "settlement_id": SID,
            "body": {},
        }
        bad = [
            {"op": "initiate"},
            [{"op": "initiate"}],
            [dict(entry, extra=1)],
            [dict(entry, op="bogus")],
            [dict(entry, op="reconcile")],
            [dict(entry, op=7)],
            [dict(entry, body=[])],
            [dict(entry, body={"unexpected": 1})],
        ]
        for journal in bad:
            self.assertEqual(
                codes(lambda: SettlementMachine.restore(journal)),
                "INVALID_JOURNAL",
            )
        self.assertNotIn("reconcile", REPLAYABLE)

    def test_restore_forgets_stored_rejections(self):
        machine, control = self.initiated_pair()
        self.reject("INVALID_AMOUNT", lambda: self.initiate(machine, sid="claim-9", idem="bad-1", gross=0))
        self.assert_same_as(machine, control)
        restored = SettlementMachine.restore(machine.export_journal())
        # The stored rejection is not journaled. On the live machine the same
        # key under different canonical arguments conflicts; on the restored
        # machine the key is free and the command re-executes to acceptance.
        self.assertEqual(
            codes(lambda: self.initiate(machine, sid="claim-9", idem="bad-1")),
            "IDEMPOTENCY_CONFLICT",
        )
        accepted = self.initiate(restored, sid="claim-9", idem="bad-1")
        self.assertFalse(accepted["duplicate"])

    # --- late-failure seam: SettlementMachine._phase_book_invariant (class B) -------------------

    def assert_phase_fault_unapplied(self, pair, attempt, retry, retry_code):
        machine, control = pair
        with self.phase_fault():
            self.assertEqual(codes(lambda: attempt(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        # A MOCK_INVARIANT rejection is not stored, so the same call may be
        # retried; the unjournaled mutation is still there.
        self.assertEqual(codes(lambda: retry(machine)), retry_code)
        return machine, control

    def test_fault_initiate_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.fresh_pair(),
            lambda m: self.initiate(m),
            lambda m: self.initiate(m),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(self.initiate(control)["settlement"]["phase"], "INITIATED")

    def test_fault_authorize_late_rejection_leaves_unapplied_mutation(self):
        self.assert_phase_fault_unapplied(
            self.initiated_pair(),
            lambda m: self.authorize(m),
            lambda m: self.authorize(m),
            "ILLEGAL_TRANSITION",
        )

    def test_fault_capture_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.authorized_pair(),
            lambda m: self.capture(m),
            lambda m: self.capture(m),
            "ILLEGAL_TRANSITION",
        )
        # The claim was recognized in the mock; the case is CAPTURED, unjournaled.
        self.assertEqual(machine.view(SID)["phase"], "CAPTURED")
        self.assertEqual(control.view(SID)["phase"], "AUTHORIZED")

    def test_fault_commit_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.captured_pair(),
            lambda m: self.commit(m),
            lambda m: self.commit(m),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(machine.view(SID)["claim"]["confirmed_cash"], 97_000)
        self.assertEqual(control.view(SID)["claim"]["confirmed_cash"], 0)

    def test_fault_fail_late_rejection_leaves_unapplied_mutation(self):
        self.assert_phase_fault_unapplied(
            self.initiated_pair(),
            lambda m: self.fail_case(m),
            lambda m: self.fail_case(m),
            "TERMINAL_IMMUTABLE",
        )

    def test_fault_cancel_late_rejection_leaves_unapplied_mutation(self):
        self.assert_phase_fault_unapplied(
            self.initiated_pair(),
            lambda m: self.cancel_case(m),
            lambda m: self.cancel_case(m),
            "TERMINAL_IMMUTABLE",
        )

    def test_fault_observe_statement_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.partial_pair(),
            lambda m: self.statement(m),
            # The mock recorded the statement, so a different statement over the
            # same remaining receivable is refused.
            lambda m: self.statement(m, movement_id="move-3"),
            "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        )
        self.assertEqual(machine.view(SID)["claim"]["receivable_open"], 0)
        self.assertEqual(control.view(SID)["claim"]["receivable_open"], 40_000)

    def test_fault_distribute_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.committed_pair(),
            lambda m: self.distribute(m),
            lambda m: self.distribute(m, order=["platform", "organizer"]),
            "DISTRIBUTION_ORDER_FROZEN",
        )
        self.assertEqual(machine.view(SID)["claim"]["distributed_cash"], 97_000)
        self.assertEqual(control.view(SID)["claim"]["distributed_cash"], 0)

    def test_fault_bind_refund_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.committed_pair(),
            lambda m: self.refund(m),
            lambda m: self.refund(m, amount=20_000),
            "REFUND_BINDING_CONFLICT",
        )
        self.assertEqual(machine.view(SID)["claim"]["refund_face"], 30_000)
        self.assertEqual(control.view(SID)["claim"]["refund_face"], 0)

    def test_fault_acceptance_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_phase_fault_unapplied(
            self.refunded_pair(),
            lambda m: self.accept(m),
            lambda m: self.accept(m, amount=5_000),
            "ACCEPTANCE_BINDING_CONFLICT",
        )
        self.assertEqual(machine.view(SID)["claim"]["refund_accepted"], 10_000)
        self.assertEqual(control.view(SID)["claim"]["refund_accepted"], 0)

    def test_fault_covers_every_replayable_command(self):
        covered = {
            name[len("test_fault_") : -len("_late_rejection_leaves_unapplied_mutation")]
            for name in dir(self)
            if name.startswith("test_fault_")
            and name.endswith("_late_rejection_leaves_unapplied_mutation")
        }
        self.assertEqual(
            covered,
            set(REPLAYABLE) - {"observe_mock_cancel_acceptance"} | {"acceptance"},
        )

    # --- late-failure seam: MockSettlement._invariant (class B) ---------------------------------

    def test_mock_fault_capture_rolls_back(self):
        # recognize_claim runs its _invariant before the claim insert, so a
        # fault there leaves neither the claim nor the phase change behind.
        machine, control = self.authorized_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.capture(machine)), "MOCK_INVARIANT")
        self.assert_same_as(machine, control)
        self.assertEqual(self.later_capture(machine), self.later_capture(control))
        self.assert_same_as(machine, control)

    def test_mock_fault_commit_leaves_unapplied_mutation(self):
        machine, control = self.captured_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.commit(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        # The statement is in the mock but the case never left CAPTURED.
        self.assertEqual(machine.view(SID)["phase"], "CAPTURED")
        self.assertEqual(machine.view(SID)["claim"]["receivable_open"], 0)
        self.assertEqual(control.view(SID)["claim"]["receivable_open"], 100_000)
        # Retrying the same commit meets the recorded statement as a duplicate,
        # which the commit path treats as MOCK_INVARIANT: the case cannot commit.
        self.assertEqual(codes(lambda: self.commit(machine)), "MOCK_INVARIANT")
        self.assertEqual(
            codes(lambda: self.commit(machine, movement_id="move-9")),
            "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        )
        self.assertEqual(machine.view(SID)["phase"], "CAPTURED")
        self.assertEqual(self.later_commit(control)["settlement"]["phase"], "COMMITTED")

    def test_mock_fault_observe_statement_leaves_unapplied_mutation(self):
        machine, control = self.partial_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.statement(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        self.assertEqual(machine.view(SID)["claim"]["receivable_open"], 0)
        # observe_statement accepts a duplicate statement, so the same retry is
        # journaled and the two machines converge.
        retried = self.statement(machine, idem="stmt-2")
        self.assertFalse(retried["duplicate"])
        self.later_statement(control)
        self.assert_same_as(machine, control)

    def test_mock_fault_distribute_leaves_unapplied_mutation(self):
        machine, control = self.committed_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.distribute(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        self.assertEqual(machine.view(SID)["claim"]["distributed_cash"], 97_000)
        # The retry journals the entry but reports a zero effect: the cash had
        # already moved in the faulted call.
        retried = self.distribute(machine, idem="dist-2")
        self.assertEqual(retried["effect"], {"organizer": 0, "platform": 0})
        self.assertEqual(
            self.later_distribute(control)["effect"],
            {"organizer": 95_000, "platform": 2_000},
        )
        self.assert_same_as(machine, control)

    def test_mock_fault_bind_refund_leaves_unapplied_mutation(self):
        machine, control = self.committed_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.refund(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        self.assertEqual(machine.view(SID)["claim"]["refund_face"], 30_000)
        # bind_refund treats the recorded refund as a duplicate and journals it.
        retried = self.refund(machine, idem="refund-2")
        self.assertFalse(retried["duplicate"])
        self.refund(control, idem="refund-2")
        self.assert_same_as(machine, control)

    def test_mock_fault_acceptance_leaves_unapplied_mutation(self):
        machine, control = self.refunded_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.accept(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        self.assertEqual(machine.view(SID)["claim"]["refund_accepted"], 10_000)
        retried = self.accept(machine, idem="accept-2")
        self.assertFalse(retried["duplicate"])
        self.accept(control, idem="accept-2")
        self.assert_same_as(machine, control)


if __name__ == "__main__":
    unittest.main()
