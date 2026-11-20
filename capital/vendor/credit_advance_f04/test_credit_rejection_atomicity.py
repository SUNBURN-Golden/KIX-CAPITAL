"""Rejection-atomicity audit for the credit-advance state machine and its mock.

Existing coverage map: test_credit_fsm.py and test_mock_credit.py already
exercise nearly every credit rejection code, and test_credit_properties.py
runs seeded sequences. Their ``canonical_state`` before/after checks are
same-machine comparisons. This file adds what they cannot see: an untouched
control machine, the ``restore(export_journal())`` round trip on both
sides (with each side's own settlement source), one later valid command on
both sides, and test-owned late-failure seams.

Each ``*_leaves_no_trace`` case drives one rejection code at one mutation
boundary of one REPLAYABLE command, then compares the machine that saw the
rejected call with the control: state_digest, canonical_state,
export_journal and the restore round trip, plus the injected settlement
book's canonical_state where the source has one. A stored rejection (same
key, same canonical arguments, same error replayed) is the only trace the
comparison allows; ``_idempotency`` sits outside canonical_state.

Mutation boundaries, per command:

* ``offer``: ``_cases[id]`` insert, then ``_invariant``, then ``_accept``.
  ``offer`` never touches ``MockCredit``.
* ``approve``/``reject``/``cancel``/``bind_settlement``: case field and
  phase write, then ``_invariant``, then ``_accept``.
* ``draw``: source read (read-only), ``MockCredit.note_advance`` (claim
  freeze and note insert, then its ``_invariant``), case field and phase
  write, ``_invariant``, ``_accept``.
* ``repay``: ``repay_notes``/``repay_order`` writes and counters, then
  ``_invariant``, ``_accept``.
* ``close``: ``MockCredit.release_note`` (status write, then its
  ``_invariant``), phase write, ``_invariant``, ``_accept``.
* ``default``: reason and phase write, ``_invariant``, ``_accept``.

Every deterministic rejection code is raised before the first mutation of
its command. After a mutation only the ``MOCK_INVARIANT`` checks remain,
and no caller input reaches those; they get fault injection instead
(``test_fault_*``, ``test_mock_fault_*``, ``test_guard_*``).

Not-applicable rows: ``view``, ``view_claim``, ``export_journal``,
``canonical_state`` and ``state_digest`` are read-only. In ``draw`` the
``note_advance`` codes ``REFUND_OBLIGATION_OPEN``, ``ADVANCE_BINDING_CONFLICT``
and the face-parse codes are unreachable because ``offer`` already parsed
the same face and a note is inserted once. The ``duplicate is False`` and
flag checks after ``note_advance``/``release_note`` have no caller input.
``reject_unsupported`` and ``attempt_execution`` are self-guarded and mutate
nothing; each gets one no-boundary row.

Contract status: CREDIT_ADVANCE_F04.md defines the error codes but states no
rejection-atomicity clause for this machine, and defines ``MOCK_INVARIANT``
only as an implementation error. The deterministic cases pin observed
behavior; the fault cases are class B characterizations. Neither invents
semantics, and nothing here edits the machine or the mock.

Fault seams: neither layer keeps a rollback wrapper. A fault at
``CreditMachine._invariant`` leaves the case mutation applied but
unjournaled, and the mock note it wrote with it. A fault at
``MockCredit._invariant`` inside ``draw``/``close`` leaves the note
inserted/released while the case did not move, after which the machine's
own ``_invariant`` fails on every later accepting command. A drifting
ownership witness makes ``_guard`` raise after ``_accept`` already
journaled. Each outcome is pinned as observed, not as a requirement.
"""

import unittest
from unittest import mock

from credit_fsm import REPLAYABLE, CreditError, CreditMachine
from mock_credit import CreditMockError, MockCredit
# test_credit_fsm puts settlement_f01_f03 on sys.path and re-exports its machine.
from test_credit_fsm import SettlementMachine, codes, settlement_book

ADV = "adv-1"
CLAIM = "claim-1"
AMOUNT = 40_000


def committed_source():
    return settlement_book("COMMITTED")[0]


class StubView:
    """Read-only settlement source returning a fixed view."""

    def __init__(self, view):
        self._view = view

    def view(self, _settlement_id):
        return self._view


class DriftingWitness:
    """Ownership stand-in whose canonical_state differs on every read."""

    def __init__(self):
        self._reads = 0

    def canonical_state(self):
        self._reads += 1
        return self._reads


class CreditRejectionAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.book, self.face = settlement_book("COMMITTED")
        self.sources = {}

    # --- command helpers ---------------------------------------------------------------

    def offer_adv(self, machine, adv=ADV, idem="offer-1", **changes):
        body = dict(face=self.face, amount=AMOUNT, beneficiary_role="fixture-label")
        body.update(changes)
        return machine.offer(adv, idempotency_key=idem, **body)

    def approve_adv(self, machine, adv=ADV, idem="approve-1"):
        return machine.approve(adv, idempotency_key=idem)

    def reject_adv(self, machine, adv=ADV, idem="reject-1", reason="fixture-reject"):
        return machine.reject(adv, idempotency_key=idem, reason=reason)

    def cancel_adv(self, machine, adv=ADV, idem="cancel-1", reason="fixture-cancel"):
        return machine.cancel(adv, idempotency_key=idem, reason=reason)

    def bind_adv(self, machine, adv=ADV, idem="bind-1", settlement_id=CLAIM):
        return machine.bind_settlement(adv, idempotency_key=idem, settlement_id=settlement_id)

    def draw_adv(self, machine, adv=ADV, idem="draw-1", draw_id="draw-1"):
        return machine.draw(adv, idempotency_key=idem, draw_id=draw_id)

    def repay_adv(self, machine, adv=ADV, idem="repay-1", **changes):
        body = dict(repay_id="repay-1", sequence=1, amount=10_000)
        body.update(changes)
        return machine.repay(adv, idempotency_key=idem, **body)

    def repay_all(self, machine):
        return self.repay_adv(machine, amount=AMOUNT)

    def close_adv(self, machine, adv=ADV, idem="close-1"):
        return machine.close(adv, idempotency_key=idem)

    def default_adv(self, machine, adv=ADV, idem="default-1", reason="fixture-default"):
        return machine.default(adv, idempotency_key=idem, reason=reason)

    # --- later valid command per pair (run on both sides) ------------------------------------

    def later_offer(self, machine):
        return self.offer_adv(machine, "adv-2", "offer-2")

    def later_approve(self, machine):
        return self.approve_adv(machine, idem="approve-2")

    def later_bind(self, machine):
        return self.bind_adv(machine, idem="bind-2")

    def later_draw(self, machine):
        return self.draw_adv(machine, idem="draw-2")

    def later_repay(self, machine):
        return self.repay_adv(machine, idem="repay-2")

    def later_repay_next(self, machine):
        return self.repay_adv(machine, idem="repay-2", repay_id="repay-2", sequence=2)

    def later_close(self, machine):
        return self.close_adv(machine, idem="close-2")

    def later_default(self, machine):
        return self.default_adv(machine, idem="default-2")

    # --- machine/control pair builders --------------------------------------------------------

    def make(self, source=committed_source, ownership=None):
        built = source()
        machine = CreditMachine(built, ownership)
        self.sources[machine] = built
        return machine

    def pair(self, *steps, source=committed_source):
        machine, control = self.make(source), self.make(source)
        for side in (machine, control):
            for step in steps:
                step(side)
        return machine, control

    def fresh_pair(self, **kwargs):
        return self.pair(**kwargs)

    def offered_pair(self):
        return self.pair(self.offer_adv)

    def approved_pair(self, **kwargs):
        return self.pair(self.offer_adv, self.approve_adv, **kwargs)

    def bound_pair(self, **kwargs):
        return self.pair(self.offer_adv, self.approve_adv, self.bind_adv, **kwargs)

    def drawn_pair(self):
        return self.pair(self.offer_adv, self.approve_adv, self.draw_adv)

    def repaid_pair(self):
        return self.pair(self.offer_adv, self.approve_adv, self.draw_adv, self.repay_adv)

    def paid_off_pair(self):
        return self.pair(self.offer_adv, self.approve_adv, self.draw_adv, self.repay_all)

    def closed_pair(self):
        return self.pair(
            self.offer_adv, self.approve_adv, self.draw_adv, self.repay_all, self.close_adv
        )

    def defaulted_pair(self):
        return self.pair(self.offer_adv, self.approve_adv, self.draw_adv, self.default_adv)

    def rejected_pair(self):
        return self.pair(self.offer_adv, self.reject_adv)

    def cancelled_pair(self):
        return self.pair(self.offer_adv, self.cancel_adv)

    # --- comparison harness ---------------------------------------------------------------------

    def assert_same_as(self, machine, control):
        self.assertEqual(machine.state_digest(), control.state_digest())
        self.assertEqual(machine.canonical_state(), control.canonical_state())
        self.assertEqual(machine.export_journal(), control.export_journal())
        a, b = self.sources[machine], self.sources[control]
        if hasattr(a, "canonical_state"):
            # The credit machine reads the settlement book and never writes it.
            self.assertEqual(a.canonical_state(), b.canonical_state())
        for side in (machine, control):
            restored = CreditMachine.restore(
                side.export_journal(), settlement_source=self.sources[side]
            )
            self.assertEqual(restored.canonical_state(), side.canonical_state())
            self.assertEqual(restored.state_digest(), side.state_digest())

    def assert_unapplied_mutation(self, machine, control, adv=ADV):
        """Pin the fault-seam characterization: mutation applied, not journaled."""
        self.assertEqual(machine.export_journal(), control.export_journal())
        self.assertNotEqual(machine.canonical_state(), control.canonical_state())
        self.assertNotEqual(machine.state_digest(), control.state_digest())
        restored = CreditMachine.restore(
            machine.export_journal(), settlement_source=self.sources[machine]
        )
        self.assertEqual(restored.canonical_state(), control.canonical_state())
        self.assertNotEqual(restored.canonical_state(), machine.canonical_state())
        # reconcile replays the journal and notices the divergence.
        self.assertEqual(
            codes(lambda: machine.reconcile(adv, idempotency_key="recon-fault")),
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

    def machine_fault(self):
        return mock.patch.object(
            CreditMachine, "_invariant", side_effect=[CreditError("MOCK_INVARIANT")]
        )

    def mock_fault(self):
        return mock.patch.object(
            MockCredit, "_invariant", side_effect=[CreditMockError("MOCK_INVARIANT")]
        )

    # --- offer -----------------------------------------------------------------------------------

    def test_offer_product_undefined_leaves_no_trace(self):
        self.check(
            "CREDIT_PRODUCT_UNDEFINED",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", product="LOAN"),
            self.later_offer,
        )

    def test_offer_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, adv=" ", idem="bad-1"),
            self.later_offer,
        )

    def test_offer_invalid_beneficiary_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", beneficiary_role=""),
            self.later_offer,
        )

    def test_offer_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", amount=0),
            self.later_offer,
        )

    def test_offer_face_type_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_FACE_TYPE",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=[]),
            self.later_offer,
        )

    def test_offer_face_fields_leaves_no_trace(self):
        short = {k: v for k, v in self.face.items() if k != "trade_id"}
        self.check(
            "SETTLEMENT_FACE_FIELDS",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=short),
            self.later_offer,
        )

    def test_offer_face_not_mock_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_FACE_NOT_MOCK",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=dict(self.face, provenance="OTHER")),
            self.later_offer,
        )

    def test_offer_currency_unsupported_leaves_no_trace(self):
        self.check(
            "CURRENCY_UNSUPPORTED",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=dict(self.face, currency="USD")),
            self.later_offer,
        )

    def test_offer_invalid_face_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=dict(self.face, claim_id="")),
            self.later_offer,
        )

    def test_offer_face_mismatch_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_FACE_MISMATCH",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=dict(self.face, gross="100000")),
            self.later_offer,
        )

    def test_offer_refund_obligation_open_leaves_no_trace(self):
        book, _face = settlement_book("COMMITTED")
        book.bind_refund(
            CLAIM,
            idempotency_key="refund-1",
            refund_id="refund-1",
            amount=30_000,
            beneficiary_role="buyer",
            reason="fixture-refund",
        )
        refunded = book.view(CLAIM)["claim"]
        self.check(
            "REFUND_OBLIGATION_OPEN",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", face=refunded),
            self.later_offer,
        )

    def test_offer_advance_binding_conflict_leaves_no_trace(self):
        self.check(
            "ADVANCE_BINDING_CONFLICT",
            self.offered_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", amount=AMOUNT + 1),
            self.later_approve,
        )

    def test_offer_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.offered_pair(),
            lambda m: self.offer_adv(m, idem="bad-1"),
            self.later_approve,
        )

    def test_offer_terminal_reoffer_is_illegal_transition_leaves_no_trace(self):
        # Class B: re-offering the same binding after a terminal phase reports
        # ILLEGAL_TRANSITION, not TERMINAL_IMMUTABLE, because offer has no
        # terminal branch. Pinned as observed.
        self.check(
            "ILLEGAL_TRANSITION",
            self.rejected_pair(),
            lambda m: self.offer_adv(m, idem="bad-1"),
            self.later_offer,
        )

    # --- approve ---------------------------------------------------------------------------------

    def test_approve_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.offered_pair(),
            lambda m: self.approve_adv(m, adv=" ", idem="bad-1"),
            self.later_approve,
        )

    def test_approve_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.offered_pair(),
            lambda m: self.approve_adv(m, adv="ghost", idem="bad-1"),
            self.later_approve,
        )

    def test_approve_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.approved_pair(),
            lambda m: self.approve_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_approve_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.rejected_pair(),
            lambda m: self.approve_adv(m, idem="bad-1"),
            self.later_offer,
        )

    # --- reject / cancel -----------------------------------------------------------------------------

    def test_reject_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.offered_pair(),
            lambda m: self.reject_adv(m, adv=" ", idem="bad-1"),
            self.later_approve,
        )

    def test_reject_invalid_reason_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.offered_pair(),
            lambda m: self.reject_adv(m, idem="bad-1", reason=""),
            self.later_approve,
        )

    def test_reject_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.offered_pair(),
            lambda m: self.reject_adv(m, adv="ghost", idem="bad-1"),
            self.later_approve,
        )

    def test_reject_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.approved_pair(),
            lambda m: self.reject_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_reject_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.cancelled_pair(),
            lambda m: self.reject_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_cancel_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.cancel_adv(m, adv=" ", idem="bad-1"),
            self.later_draw,
        )

    def test_cancel_invalid_reason_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.cancel_adv(m, idem="bad-1", reason=" "),
            self.later_draw,
        )

    def test_cancel_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.approved_pair(),
            lambda m: self.cancel_adv(m, adv="ghost", idem="bad-1"),
            self.later_draw,
        )

    def test_cancel_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.drawn_pair(),
            lambda m: self.cancel_adv(m, idem="bad-1"),
            self.later_repay,
        )

    def test_cancel_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.rejected_pair(),
            lambda m: self.cancel_adv(m, idem="bad-1"),
            self.later_offer,
        )

    # --- bind_settlement -------------------------------------------------------------------------------

    def test_bind_settlement_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.bind_adv(m, adv=" ", idem="bad-1"),
            self.later_bind,
        )

    def test_bind_settlement_invalid_settlement_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.bind_adv(m, idem="bad-1", settlement_id=""),
            self.later_bind,
        )

    def test_bind_settlement_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.approved_pair(),
            lambda m: self.bind_adv(m, adv="ghost", idem="bad-1"),
            self.later_bind,
        )

    def test_bind_settlement_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.rejected_pair(),
            lambda m: self.bind_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_bind_settlement_illegal_transition_after_draw_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.drawn_pair(),
            lambda m: self.bind_adv(m, idem="bad-1"),
            self.later_repay,
        )

    def test_bind_settlement_rebind_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.bound_pair(),
            lambda m: self.bind_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_bind_settlement_binding_conflict_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_BINDING_CONFLICT",
            self.bound_pair(),
            lambda m: self.bind_adv(m, idem="bad-1", settlement_id="other-claim"),
            self.later_draw,
        )

    # --- draw ---------------------------------------------------------------------------------------------

    def test_draw_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.draw_adv(m, adv=" ", idem="bad-1"),
            self.later_draw,
        )

    def test_draw_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.approved_pair(),
            lambda m: self.draw_adv(m, adv="ghost", idem="bad-1"),
            self.later_draw,
        )

    def test_draw_invalid_draw_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.approved_pair(),
            lambda m: self.draw_adv(m, idem="bad-1", draw_id=""),
            self.later_draw,
        )

    def test_draw_duplicate_draw_leaves_no_trace(self):
        self.check(
            "DUPLICATE_DRAW",
            self.drawn_pair(),
            lambda m: self.draw_adv(m, idem="bad-1", draw_id="draw-9"),
            self.later_repay,
        )

    def test_draw_terminal_immutable_after_draw_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.closed_pair(),
            lambda m: self.draw_adv(m, idem="bad-1", draw_id="draw-9"),
            self.later_offer,
        )

    def test_draw_terminal_immutable_without_draw_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.cancelled_pair(),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.offered_pair(),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_approve,
        )

    def test_draw_settlement_source_required_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_SOURCE_REQUIRED",
            self.bound_pair(source=lambda: None),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_unknown_settlement_leaves_no_trace(self):
        self.check(
            "UNKNOWN_SETTLEMENT",
            self.bound_pair(source=SettlementMachine),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_settlement_not_committed_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_NOT_COMMITTED",
            self.bound_pair(source=lambda: settlement_book("CAPTURED")[0]),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_settlement_binding_conflict_leaves_no_trace(self):
        pair = self.pair(
            self.offer_adv,
            self.approve_adv,
            lambda m: self.bind_adv(m, settlement_id="claim-2"),
            source=lambda: settlement_book("COMMITTED", settlement_id="claim-2")[0],
        )
        self.check(
            "SETTLEMENT_BINDING_CONFLICT",
            pair,
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_settlement_amount_mismatch_leaves_no_trace(self):
        self.check(
            "SETTLEMENT_AMOUNT_MISMATCH",
            self.bound_pair(source=lambda: settlement_book("COMMITTED", gross=90_000)[0]),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_settlement_view_rejected_leaves_no_trace(self):
        forged = dict(self.book.view(CLAIM), economic_finality_claimed=True)
        self.check(
            "SETTLEMENT_VIEW_REJECTED",
            self.bound_pair(source=lambda: StubView(forged)),
            lambda m: self.draw_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_draw_face_snapshot_frozen_leaves_no_trace(self):
        other_face = dict(self.face, confirmed_cash=self.face["confirmed_cash"] - 1)
        pair = self.pair(
            self.offer_adv,
            self.approve_adv,
            self.draw_adv,
            lambda m: self.offer_adv(m, "adv-2", "offer-2", face=other_face, amount=10_000),
            lambda m: self.approve_adv(m, "adv-2", "approve-2"),
        )
        self.check(
            "FACE_SNAPSHOT_FROZEN",
            pair,
            lambda m: self.draw_adv(m, "adv-2", idem="bad-1", draw_id="draw-2"),
            self.later_repay,
        )

    def test_draw_advance_exceeds_open_face_leaves_no_trace(self):
        pair = self.pair(
            lambda m: self.offer_adv(m, amount=60_000),
            self.approve_adv,
            self.draw_adv,
            lambda m: self.offer_adv(m, "adv-2", "offer-2", amount=60_000),
            lambda m: self.approve_adv(m, "adv-2", "approve-2"),
        )
        self.check(
            "ADVANCE_EXCEEDS_OPEN_FACE",
            pair,
            lambda m: self.draw_adv(m, "adv-2", idem="bad-1", draw_id="draw-2"),
            self.later_repay,
        )

    # --- repay -----------------------------------------------------------------------------------------------

    def test_repay_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, adv=" ", idem="bad-1"),
            self.later_repay,
        )

    def test_repay_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, adv="ghost", idem="bad-1"),
            self.later_repay,
        )

    def test_repay_invalid_repay_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", repay_id=""),
            self.later_repay,
        )

    def test_repay_invalid_amount_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", amount=0),
            self.later_repay,
        )

    def test_repay_sequence_type_leaves_no_trace(self):
        self.check(
            "REPAYMENT_ORDER",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", sequence="1"),
            self.later_repay,
        )

    def test_repay_sequence_gap_leaves_no_trace(self):
        self.check(
            "REPAYMENT_ORDER",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", sequence=2),
            self.later_repay,
        )

    def test_repay_binding_conflict_leaves_no_trace(self):
        self.check(
            "REPAY_BINDING_CONFLICT",
            self.repaid_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", amount=9_999),
            self.later_repay_next,
        )

    def test_repay_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.closed_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", repay_id="repay-9", sequence=2),
            self.later_offer,
        )

    def test_repay_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.approved_pair(),
            lambda m: self.repay_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_repay_exceeds_outstanding_leaves_no_trace(self):
        self.check(
            "REPAYMENT_EXCEEDS_OUTSTANDING",
            self.drawn_pair(),
            lambda m: self.repay_adv(m, idem="bad-1", amount=AMOUNT + 1),
            self.later_repay,
        )

    # --- close -------------------------------------------------------------------------------------------------

    def test_close_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.paid_off_pair(),
            lambda m: self.close_adv(m, adv=" ", idem="bad-1"),
            self.later_close,
        )

    def test_close_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.paid_off_pair(),
            lambda m: self.close_adv(m, adv="ghost", idem="bad-1"),
            self.later_close,
        )

    def test_close_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.approved_pair(),
            lambda m: self.close_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_close_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.closed_pair(),
            lambda m: self.close_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_close_outstanding_remains_leaves_no_trace(self):
        self.check(
            "OUTSTANDING_REMAINS",
            self.repaid_pair(),
            lambda m: self.close_adv(m, idem="bad-1"),
            self.later_repay_next,
        )

    # --- default ------------------------------------------------------------------------------------------------

    def test_default_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.drawn_pair(),
            lambda m: self.default_adv(m, adv=" ", idem="bad-1"),
            self.later_default,
        )

    def test_default_invalid_reason_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.drawn_pair(),
            lambda m: self.default_adv(m, idem="bad-1", reason=""),
            self.later_default,
        )

    def test_default_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.drawn_pair(),
            lambda m: self.default_adv(m, adv="ghost", idem="bad-1"),
            self.later_default,
        )

    def test_default_illegal_transition_leaves_no_trace(self):
        self.check(
            "ILLEGAL_TRANSITION",
            self.approved_pair(),
            lambda m: self.default_adv(m, idem="bad-1"),
            self.later_draw,
        )

    def test_default_terminal_immutable_leaves_no_trace(self):
        self.check(
            "TERMINAL_IMMUTABLE",
            self.closed_pair(),
            lambda m: self.default_adv(m, idem="bad-1"),
            self.later_offer,
        )

    def test_default_requires_exposure_leaves_no_trace(self):
        self.check(
            "DEFAULT_REQUIRES_EXPOSURE",
            self.paid_off_pair(),
            lambda m: self.default_adv(m, idem="bad-1"),
            self.later_close,
        )

    # --- reconcile / unsupported attempts (not journaled) ------------------------------------------------------------

    def test_reconcile_unknown_advance_leaves_no_trace(self):
        self.check(
            "UNKNOWN_ADVANCE",
            self.drawn_pair(),
            lambda m: m.reconcile("ghost", idempotency_key="bad-1"),
            self.later_repay,
        )

    def test_reconcile_invalid_advance_id_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.drawn_pair(),
            lambda m: m.reconcile(" ", idempotency_key="bad-1"),
            self.later_repay,
        )

    def test_reject_unsupported_leaves_no_trace(self):
        machine, control = self.drawn_pair()
        for kind, code in (
            ("DISBURSE", "REAL_FUNDS_FORBIDDEN"),
            ("KYC", "CREDIT_PRODUCT_UNDEFINED"),
            ("SOMETHING_ELSE", "EXECUTION_KIND"),
            (7, "EXECUTION_KIND"),
        ):
            self.reject(code, lambda: machine.reject_unsupported(kind))
        self.assert_same_as(machine, control)
        self.assertEqual(self.later_repay(machine), self.later_repay(control))
        self.assert_same_as(machine, control)

    def test_attempt_execution_leaves_no_trace(self):
        machine, control = self.drawn_pair()
        for adv, kind, code in (
            (ADV, "DISBURSE", "REAL_FUNDS_FORBIDDEN"),
            (ADV, "ACCRUE", "CREDIT_PRODUCT_UNDEFINED"),
            (ADV, "SOMETHING_ELSE", "EXECUTION_KIND"),
            ("ghost", "DISBURSE", "UNKNOWN_ADVANCE"),
            (" ", "DISBURSE", "INVALID_ID"),
        ):
            self.reject(code, lambda: machine.attempt_execution(adv, kind=kind))
        self.assert_same_as(machine, control)
        self.assertEqual(self.later_repay(machine), self.later_repay(control))
        self.assert_same_as(machine, control)

    # --- idempotency boundaries ---------------------------------------------------------------------------------------

    def test_invalid_idempotency_key_leaves_no_trace(self):
        self.check(
            "INVALID_ID",
            self.offered_pair(),
            lambda m: self.approve_adv(m, idem=" "),
            self.later_approve,
        )

    def test_idempotency_conflict_leaves_no_trace(self):
        self.check(
            "IDEMPOTENCY_CONFLICT",
            self.offered_pair(),
            lambda m: self.offer_adv(m, amount=AMOUNT + 1),
            self.later_approve,
        )

    def test_unfingerprintable_rejection_leaves_no_trace(self):
        self.check(
            "INVALID_AMOUNT",
            self.fresh_pair(),
            lambda m: self.offer_adv(m, idem="bad-1", amount=object()),
            lambda m: self.offer_adv(m, idem="bad-1"),
        )

    # --- restore boundary (classmethod; no live machine touched) ------------------------------------------------------------

    def test_restore_invalid_journal_variants(self):
        entry = {
            "op": "approve",
            "idempotency_key": "k",
            "advance_id": ADV,
            "body": {},
        }
        bad = [
            {"op": "offer"},
            [{"op": "offer"}],
            [dict(entry, extra=1)],
            [dict(entry, op="bogus")],
            [dict(entry, op="reconcile")],
            [dict(entry, op=7)],
            [dict(entry, body=[])],
            [dict(entry, body={"unexpected": 1})],
        ]
        for journal in bad:
            self.assertEqual(
                codes(lambda: CreditMachine.restore(journal)),
                "INVALID_JOURNAL",
            )
        self.assertNotIn("reconcile", REPLAYABLE)

    def test_restore_forgets_stored_rejections(self):
        machine, control = self.offered_pair()
        self.reject(
            "INVALID_AMOUNT",
            lambda: self.offer_adv(machine, "adv-9", "bad-1", amount=0),
        )
        self.assert_same_as(machine, control)
        restored = CreditMachine.restore(machine.export_journal(), self.sources[machine])
        # The stored rejection is not journaled. On the live machine the same
        # key under different canonical arguments conflicts; on the restored
        # machine the key is free and the command re-executes to acceptance.
        self.assertEqual(
            codes(lambda: self.offer_adv(machine, "adv-9", "bad-1")),
            "IDEMPOTENCY_CONFLICT",
        )
        accepted = self.offer_adv(restored, "adv-9", "bad-1")
        self.assertFalse(accepted["duplicate"])

    # --- late-failure seam: CreditMachine._invariant (class B) ----------------------------------------------------------------

    def assert_machine_fault_unapplied(self, pair, attempt, retry, retry_code, adv=ADV):
        machine, control = pair
        with self.machine_fault():
            self.assertEqual(codes(lambda: attempt(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control, adv)
        # A MOCK_INVARIANT rejection is not stored, so the same call may be
        # retried; the unjournaled mutation is still there.
        if retry_code is None:
            return machine, control
        self.assertEqual(codes(lambda: retry(machine)), retry_code)
        return machine, control

    def test_fault_offer_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_machine_fault_unapplied(
            self.fresh_pair(),
            lambda m: self.offer_adv(m),
            lambda m: self.offer_adv(m),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(machine.view(ADV)["phase"], "OFFERED")
        self.assertEqual(codes(lambda: control.view(ADV)), "UNKNOWN_ADVANCE")

    def test_fault_approve_late_rejection_leaves_unapplied_mutation(self):
        self.assert_machine_fault_unapplied(
            self.offered_pair(),
            lambda m: self.approve_adv(m),
            lambda m: self.approve_adv(m),
            "ILLEGAL_TRANSITION",
        )

    def test_fault_reject_late_rejection_leaves_unapplied_mutation(self):
        self.assert_machine_fault_unapplied(
            self.offered_pair(),
            lambda m: self.reject_adv(m),
            lambda m: self.reject_adv(m),
            "TERMINAL_IMMUTABLE",
        )

    def test_fault_cancel_late_rejection_leaves_unapplied_mutation(self):
        self.assert_machine_fault_unapplied(
            self.offered_pair(),
            lambda m: self.cancel_adv(m),
            lambda m: self.cancel_adv(m),
            "TERMINAL_IMMUTABLE",
        )

    def test_fault_bind_settlement_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_machine_fault_unapplied(
            self.approved_pair(),
            lambda m: self.bind_adv(m),
            lambda m: self.bind_adv(m),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(machine.view(ADV)["settlement_gate"], "BOUND")
        self.assertEqual(control.view(ADV)["settlement_gate"], "UNBOUND")

    def test_fault_draw_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_machine_fault_unapplied(
            self.approved_pair(),
            lambda m: self.draw_adv(m),
            lambda m: self.draw_adv(m),
            None,
        )
        # The note and the DRAWN case are both there, with no journal entry.
        self.assertEqual(machine.view(ADV)["phase"], "DRAWN")
        self.assertEqual(machine.view(ADV)["note_status"], "NOTED")
        self.assertIsNone(control.view(ADV)["note_status"])
        # Retrying the same draw_id meets the unjournaled draw as a duplicate:
        # it succeeds and journals nothing, so the draw never enters the journal.
        again = self.draw_adv(machine, idem="draw-2")
        self.assertTrue(again["duplicate"])
        self.assertEqual(machine.export_journal(), control.export_journal())
        self.assertNotEqual(machine.canonical_state(), control.canonical_state())

    def test_fault_repay_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_machine_fault_unapplied(
            self.drawn_pair(),
            lambda m: self.repay_adv(m),
            lambda m: self.repay_adv(m),
            None,
        )
        self.assertEqual(machine.view(ADV)["outstanding_exposure"], AMOUNT - 10_000)
        self.assertEqual(control.view(ADV)["outstanding_exposure"], AMOUNT)
        # The same repay_id is a duplicate of the unjournaled note: success,
        # no journal entry.
        again = self.repay_adv(machine, idem="repay-2")
        self.assertTrue(again["duplicate"])
        self.assertEqual(machine.export_journal(), control.export_journal())
        # A fresh repay_id at sequence 1 is refused: the unjournaled repayment
        # already holds sequence 1.
        self.assertEqual(
            codes(lambda: self.repay_adv(machine, idem="repay-3", repay_id="repay-3")),
            "REPAYMENT_ORDER",
        )

    def test_fault_close_late_rejection_leaves_unapplied_mutation(self):
        machine, control = self.assert_machine_fault_unapplied(
            self.paid_off_pair(),
            lambda m: self.close_adv(m),
            lambda m: self.close_adv(m),
            "TERMINAL_IMMUTABLE",
        )
        self.assertEqual(machine.view(ADV)["phase"], "CLOSED")
        self.assertEqual(machine.view(ADV)["note_status"], "RELEASED")
        self.assertEqual(control.view(ADV)["note_status"], "NOTED")

    def test_fault_default_late_rejection_leaves_unapplied_mutation(self):
        self.assert_machine_fault_unapplied(
            self.drawn_pair(),
            lambda m: self.default_adv(m),
            lambda m: self.default_adv(m),
            "TERMINAL_IMMUTABLE",
        )

    def test_fault_covers_every_replayable_command(self):
        covered = {
            name[len("test_fault_") : -len("_late_rejection_leaves_unapplied_mutation")]
            for name in dir(self)
            if name.startswith("test_fault_")
            and name.endswith("_late_rejection_leaves_unapplied_mutation")
        }
        self.assertEqual(covered, set(REPLAYABLE))

    # --- late-failure seam: MockCredit._invariant (class B) --------------------------------------------------------------------

    def test_mock_fault_draw_leaves_unapplied_note(self):
        machine, control = self.approved_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.draw_adv(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        # The note was inserted but the case did not move.
        self.assertEqual(machine.view(ADV)["phase"], "APPROVED")
        self.assertEqual(machine.view(ADV)["note_status"], "NOTED")
        self.assertIsNone(control.view(ADV)["note_status"])
        # The same draw now meets the note as a duplicate, which draw treats as
        # MOCK_INVARIANT: the advance cannot be drawn again.
        self.assertEqual(codes(lambda: self.draw_adv(machine)), "MOCK_INVARIANT")
        # The machine's own _invariant now fails for any accepting command
        # (case APPROVED with a NOTED note). Cancel is refused before its
        # case write completes the journal entry, and leaves its own write.
        self.assertEqual(codes(lambda: self.cancel_adv(machine)), "MOCK_INVARIANT")
        self.assertEqual(machine.export_journal(), control.export_journal())
        self.assertEqual(machine.view(ADV)["phase"], "CANCELLED")
        self.assertEqual(self.later_draw(control)["credit"]["phase"], "DRAWN")

    def test_mock_fault_close_leaves_unapplied_release(self):
        machine, control = self.paid_off_pair()
        with self.mock_fault():
            self.assertEqual(codes(lambda: self.close_adv(machine)), "MOCK_INVARIANT")
        self.assert_unapplied_mutation(machine, control)
        # The note was released but the case stayed DRAWN.
        self.assertEqual(machine.view(ADV)["phase"], "DRAWN")
        self.assertEqual(machine.view(ADV)["note_status"], "RELEASED")
        self.assertEqual(control.view(ADV)["note_status"], "NOTED")
        # The same close now meets the release as a duplicate, which close
        # treats as MOCK_INVARIANT: the advance cannot be closed again.
        self.assertEqual(codes(lambda: self.close_adv(machine)), "MOCK_INVARIANT")
        self.assertEqual(machine.export_journal(), control.export_journal())
        self.assertEqual(self.later_close(control)["credit"]["phase"], "CLOSED")

    # --- late-failure seam: _guard on a drifting ownership witness (class B) ------------------------------------------------------

    def test_guard_drift_after_accept_reports_rejection_for_a_journaled_command(self):
        drifting = self.make(ownership=DriftingWitness())
        control = self.make()
        self.assertEqual(codes(lambda: self.offer_adv(drifting)), "MOCK_INVARIANT")
        self.offer_adv(control)
        # _guard runs after _accept: the entry is journaled and applied even
        # though the caller saw MOCK_INVARIANT.
        self.assert_same_as(drifting, control)
        self.assertEqual(len(drifting.export_journal()), 1)

    def test_guard_drift_replaces_a_deterministic_rejection_code(self):
        drifting = self.make(ownership=DriftingWitness())
        control = self.make()
        self.assertEqual(
            codes(lambda: self.approve_adv(drifting, adv="ghost")), "MOCK_INVARIANT"
        )
        self.assert_same_as(drifting, control)


if __name__ == "__main__":
    unittest.main()
