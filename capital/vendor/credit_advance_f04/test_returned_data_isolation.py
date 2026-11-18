"""Builder-authored, source-informed, in-memory EV-CREDIT evidence.

Replay assertions implement contract §§7.3–7.4. Copying and retained-object
lifetime outside those replay predicates are class B characterizations.
"""

from copy import deepcopy
import unittest

from credit_fsm import CreditMachine
from test_credit_fsm import settlement_book


def fixture():
    source, face = settlement_book("COMMITTED")
    return CreditMachine(source), source, [
        ("offer", dict(face=face, amount=25_000, beneficiary_role="fixture-label")),
        ("approve", {}),
        ("bind_settlement", dict(settlement_id="claim-1")),
        ("draw", dict(draw_id="draw-1")),
        ("repay", dict(repay_id="repay-1", sequence=1, amount=10_000)),
        ("repay", dict(repay_id="repay-2", sequence=2, amount=15_000)),
        ("close", {}),
    ]


def call(machine, command):
    op, body = command
    key = body.get("repay_id", op)
    return getattr(machine, op)("adv-1", idempotency_key=key, **deepcopy(body))


def source_observables(source):
    return deepcopy((source.view("claim-1"), source.canonical_state(),
                     source.state_digest(), source.export_journal()))


def assert_observables_equal(test, subject, control, sources, source_baseline, *, claim=True):
    test.assertEqual(subject.view("adv-1"), control.view("adv-1"))
    if claim:
        test.assertEqual(subject.view_claim("claim-1"), control.view_claim("claim-1"))
    test.assertEqual(subject.canonical_state(), control.canonical_state())
    test.assertEqual(subject.state_digest(), control.state_digest())
    test.assertEqual(subject.export_journal(), control.export_journal())
    for source in sources:
        test.assertEqual(source_observables(source), source_baseline)


def mutate(test, value, mutation):
    before = deepcopy(value)
    mutation(value)
    test.assertNotEqual(value, before, "mutation must change the returned object")


def interest_terms(view):
    return view["open_terms"]["terms"]["interest-apr-schedule"]


# Sentinel corruptions of detached objects, never selected product-policy values.
TERM_MUTATIONS = (
    ("term-status", lambda v: interest_terms(v).__setitem__("policy_number_status", "CALLER_CORRUPTION")),
    ("term-value", lambda v: interest_terms(v).__setitem__("decided_value", {"caller-only": []})),
    ("term-delete", lambda v: interest_terms(v).pop("adopted_option")),
    ("term-replace", lambda v: v["open_terms"]["terms"].__setitem__("interest-apr-schedule", {})),
)
REPAYMENT_MUTATIONS = (
    ("repayment-entry", lambda v: v["repayments"][0].__setitem__("amount", -1)),
    ("repayment-delete", lambda v: v["repayments"][0].pop("repay_id")),
    ("repayment-list", lambda v: v["repayments"].clear()),
    ("repayment-append", lambda v: v["repayments"].append({"caller-only": True})),
)


class ReturnedResultReplayTests(unittest.TestCase):
    """Contract-defined immutable first results, including bound-source restore."""

    def test_mutated_first_and_duplicate_results_preserve_original_replay(self):
        cases = [(name, 0, edit) for name, edit in TERM_MUTATIONS]
        cases += [(name, 4, edit) for name, edit in REPAYMENT_MUTATIONS]
        for name, index, edit_view in cases:
            with self.subTest(mutation=name):
                subject, source, sequence = fixture()
                control, control_source, control_sequence = fixture()
                self.assertEqual(sequence, control_sequence)
                sources = (source, control_source)
                baseline = source_observables(source)
                for command in sequence[:index + 1]:
                    returned = call(subject, command)
                    untouched = call(control, command)
                    self.assertEqual(returned, untouched)
                first = deepcopy(untouched)
                self.assertFalse(first["duplicate"])
                self.assertEqual(first["applied"], sequence[index][0])
                expected = deepcopy(first)
                expected.update(duplicate=True, applied=None)
                edit = lambda result: edit_view(result["credit"])
                mutate(self, returned, edit)
                assert_observables_equal(self, subject, control, sources, baseline, claim=index >= 3)

                duplicate = call(subject, sequence[index])
                self.assertEqual(duplicate, expected)
                self.assertEqual(call(control, sequence[index]), expected)
                mutate(self, duplicate, edit)
                self.assertEqual(call(subject, sequence[index]), expected)
                assert_observables_equal(self, subject, control, sources, baseline, claim=index >= 3)

                for position, command in enumerate(sequence[index + 1:], start=index + 1):
                    self.assertEqual(call(subject, command), call(control, command))
                    assert_observables_equal(self, subject, control, sources, baseline, claim=position >= 3)
                self.assertEqual(subject.view("adv-1")["phase"], "CLOSED")
                self.assertNotEqual(subject.view("adv-1"), first["credit"])
                self.assertEqual(call(subject, sequence[index]), expected)
                self.assertEqual(call(control, sequence[index]), expected)
                restored = CreditMachine.restore(subject.export_journal(), settlement_source=source)
                restored_control = CreditMachine.restore(
                    control.export_journal(), settlement_source=control_source)
                for machine in (restored, restored_control):
                    assert_observables_equal(self, machine, control, sources, baseline)
                    response = call(machine, sequence[index])
                    self.assertEqual(response, expected)
                    mutate(self, response, edit)
                    self.assertEqual(call(machine, sequence[index]), expected)
                    assert_observables_equal(self, machine, control, sources, baseline)
                self.assertEqual(untouched, first)


class CopyIsolationCharacterizationTests(unittest.TestCase):
    """Class B: public views/exports and retained objects are detached today."""

    def test_nested_advance_and_claim_views_are_detached(self):
        cases = [("advance-" + name, "view", edit) for name, edit in TERM_MUTATIONS + REPAYMENT_MUTATIONS]
        cases += [("claim-" + name, "view_claim", edit) for name, edit in TERM_MUTATIONS]
        for name, method, edit in cases:
            with self.subTest(mutation=name):
                subject, source, sequence = fixture()
                control, control_source, _ = fixture()
                sources = (source, control_source)
                baseline = source_observables(source)
                for command in sequence[:5]:
                    call(subject, command)
                    call(control, command)
                returned = getattr(subject, method)("adv-1" if method == "view" else "claim-1")
                mutate(self, returned, edit)
                assert_observables_equal(self, subject, control, sources, baseline)
                restored = CreditMachine.restore(subject.export_journal(), settlement_source=source)
                assert_observables_equal(self, restored, control, sources, baseline)

    def test_nested_journal_bodies_and_metadata_are_detached(self):
        edits = (
            ("face-entry", lambda j: j[0]["body"]["face"]["obligations"][0].__setitem__("face", -1)),
            ("face-delete", lambda j: j[0]["body"]["face"]["obligations"][0].pop("payee")),
            ("face-list", lambda j: j[0]["body"]["face"]["obligations"].clear()),
            ("metadata", lambda j: j[0].__setitem__("idempotency_key", "caller-only")),
            ("entry-delete", lambda j: j[0].pop("op")),
            ("list-remove", lambda j: j.pop(0)),
        )
        for name, edit in edits:
            with self.subTest(mutation=name):
                subject, source, sequence = fixture()
                control, control_source, _ = fixture()
                sources = (source, control_source)
                baseline = source_observables(source)
                for command in sequence[:5]:
                    call(subject, command)
                    call(control, command)
                exported = subject.export_journal()
                for entry in exported:
                    self.assertEqual(set(entry), {"op", "idempotency_key", "advance_id", "body"})
                mutate(self, exported, edit)
                assert_observables_equal(self, subject, control, sources, baseline)
                # Bound settlement fixtures stay unchanged and available to restore.
                restored = CreditMachine.restore(subject.export_journal(), settlement_source=source)
                assert_observables_equal(self, restored, control, sources, baseline)

    def test_previously_returned_snapshots_survive_later_transitions(self):
        subject, source, sequence = fixture()
        control, control_source, _ = fixture()
        sources = (source, control_source)
        baseline = source_observables(source)
        retained = []
        for position, command in enumerate(sequence):
            result = call(subject, command)
            self.assertEqual(result, call(control, command))
            assert_observables_equal(self, subject, control, sources, baseline, claim=position >= 3)
            for value, saved in retained:
                self.assertEqual(value, saved)
            values = [result, subject.view("adv-1"), subject.export_journal()]
            if position >= 3:
                values.append(subject.view_claim("claim-1"))
            retained.extend((value, deepcopy(value)) for value in values)
        self.assertEqual(subject.view("adv-1")["phase"], "CLOSED")
        self.assertEqual(subject.view_claim("claim-1")["reserved_open"], 0)
        self.assertNotEqual(retained[1][0], subject.view("adv-1"))
