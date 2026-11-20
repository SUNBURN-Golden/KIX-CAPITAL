"""Builder-authored, source-informed, in-memory EV-SET evidence.

Replay assertions implement contract §§9.3–9.4. Copying and retained-object
lifetime outside those replay predicates are class B characterizations.
"""

from copy import deepcopy
import unittest

from settlement_fsm import SettlementMachine
from test_settlement_fsm import policy


def commands():
    return [
        ("initiate", dict(trade_id="trade-1", gross=100_000,
                          debtor_role="fixture-merchant", policy=policy())),
        ("authorize", {}),
        ("capture", {}),
        ("commit", dict(movement_id="move-1", gross=100_000, amount=97_000,
                        fee=3_000, tax=0, held=0, adjustment=0)),
        ("distribute", dict(order=["platform", "organizer"])),
        ("bind_refund", dict(refund_id="refund-1", amount=40_000,
                             beneficiary_role="buyer", reason="PARTIAL")),
    ]


def call(machine, command):
    op, body = command
    return getattr(machine, op)("claim-1", idempotency_key=op, **deepcopy(body))


def assert_observables_equal(test, subject, control):
    test.assertEqual(subject.view("claim-1"), control.view("claim-1"))
    test.assertEqual(subject.canonical_state(), control.canonical_state())
    test.assertEqual(subject.state_digest(), control.state_digest())
    test.assertEqual(subject.export_journal(), control.export_journal())


def mutate(test, value, mutation):
    before = deepcopy(value)
    mutation(value)
    test.assertNotEqual(value, before, "mutation must change the returned object")


# Each case starts with a fresh subject/control pair. These deliberately invalid
# edits affect only returned test objects; they are never submitted as commands.
VIEW_MUTATIONS = (
    ("policy-value", 0, lambda v: v["policy"].__setitem__("fee_bps", -1)),
    ("policy-delete", 0, lambda v: v["policy"].pop("kind")),
    ("policy-replace", 0, lambda v: v.__setitem__("policy", {})),
    ("obligation-entry", 2, lambda v: v["claim"]["obligations"][0].__setitem__("face", -1)),
    ("obligation-delete", 2, lambda v: v["claim"]["obligations"][0].pop("payee")),
    ("obligation-list", 2, lambda v: v["claim"]["obligations"].clear()),
    ("distribution-order", 4, lambda v: v["claim"]["distribution_order"].reverse()),
    ("distribution-append", 4, lambda v: v["claim"]["distribution_order"].append("caller-only")),
)


class ReturnedResultReplayTests(unittest.TestCase):
    """Contract-defined immutable first results, including restored replay."""

    def test_mutated_first_and_duplicate_results_preserve_original_replay(self):
        cases = [
            (name, index, lambda r, edit=edit: edit(r["settlement"]))
            for name, index, edit in VIEW_MUTATIONS
        ] + [
            ("effect-value", 4, lambda r: r["effect"].__setitem__("platform", -1)),
            ("effect-delete", 4, lambda r: r["effect"].pop("organizer")),
            ("effect-replace", 4, lambda r: r.__setitem__("effect", {})),
        ]
        for name, index, edit in cases:
            with self.subTest(mutation=name):
                subject, control = SettlementMachine(), SettlementMachine()
                sequence = commands()
                for command in sequence[:index + 1]:
                    returned = call(subject, command)
                    untouched = call(control, command)
                    self.assertEqual(returned, untouched)
                first = deepcopy(untouched)
                self.assertFalse(first["duplicate"])
                self.assertEqual(first["applied"], sequence[index][0])
                expected = deepcopy(first)
                expected.update(duplicate=True, applied=None)
                mutate(self, returned, edit)
                assert_observables_equal(self, subject, control)

                duplicate = call(subject, sequence[index])
                self.assertEqual(duplicate, expected)
                self.assertEqual(call(control, sequence[index]), expected)
                mutate(self, duplicate, edit)
                self.assertEqual(call(subject, sequence[index]), expected)
                assert_observables_equal(self, subject, control)

                for command in sequence[index + 1:]:
                    self.assertEqual(call(subject, command), call(control, command))
                    assert_observables_equal(self, subject, control)
                self.assertNotEqual(subject.view("claim-1"), first["settlement"])
                self.assertEqual(call(subject, sequence[index]), expected)
                self.assertEqual(call(control, sequence[index]), expected)
                restored = SettlementMachine.restore(subject.export_journal())
                restored_control = SettlementMachine.restore(control.export_journal())
                for machine in (restored, restored_control):
                    assert_observables_equal(self, machine, control)
                    response = call(machine, sequence[index])
                    self.assertEqual(response, expected)
                    mutate(self, response, edit)
                    self.assertEqual(call(machine, sequence[index]), expected)
                    assert_observables_equal(self, machine, control)
                self.assertEqual(untouched, first)


class CopyIsolationCharacterizationTests(unittest.TestCase):
    """Class B: public views/exports and retained objects are detached today."""

    def test_nested_views_are_detached(self):
        for name, _, edit in VIEW_MUTATIONS:
            with self.subTest(mutation=name):
                subject, control = SettlementMachine(), SettlementMachine()
                for command in commands()[:5]:
                    call(subject, command)
                    call(control, command)
                returned = subject.view("claim-1")
                mutate(self, returned, edit)
                assert_observables_equal(self, subject, control)
                restored = SettlementMachine.restore(subject.export_journal())
                assert_observables_equal(self, restored, control)

    def test_nested_journal_bodies_and_metadata_are_detached(self):
        edits = (
            ("policy", lambda j: j[0]["body"]["policy"].__setitem__("fee_bps", -1)),
            ("policy-delete", lambda j: j[0]["body"]["policy"].pop("kind")),
            ("order", lambda j: j[4]["body"]["order"].reverse()),
            ("order-append", lambda j: j[4]["body"]["order"].append("caller-only")),
            ("metadata", lambda j: j[0].__setitem__("idempotency_key", "caller-only")),
            ("entry-delete", lambda j: j[0].pop("op")),
            ("list-remove", lambda j: j.pop(0)),
        )
        for name, edit in edits:
            with self.subTest(mutation=name):
                subject, control = SettlementMachine(), SettlementMachine()
                for command in commands()[:5]:
                    call(subject, command)
                    call(control, command)
                exported = subject.export_journal()
                for entry in exported:
                    self.assertEqual(set(entry), {"op", "idempotency_key", "settlement_id", "body"})
                mutate(self, exported, edit)
                assert_observables_equal(self, subject, control)
                # Restore only a fresh export, never the deliberately corrupt one.
                restored = SettlementMachine.restore(subject.export_journal())
                assert_observables_equal(self, restored, control)

    def test_previously_returned_snapshots_survive_later_transitions(self):
        subject, control = SettlementMachine(), SettlementMachine()
        retained = []
        for command in commands():
            for value, baseline in retained:
                self.assertEqual(value, baseline)
            result = call(subject, command)
            self.assertEqual(result, call(control, command))
            assert_observables_equal(self, subject, control)
            for value, baseline in retained:
                self.assertEqual(value, baseline)
            for value in (result, subject.view("claim-1"), subject.export_journal()):
                retained.append((value, deepcopy(value)))
        self.assertEqual(subject.view("claim-1")["accepted_entries"], 6)
        self.assertNotEqual(retained[1][0], subject.view("claim-1"))
