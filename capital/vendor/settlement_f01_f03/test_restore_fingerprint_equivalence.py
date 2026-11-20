"""Builder-authored offline replay probes. All numbers are synthetic fixtures.

Owner policy values remain UNDETERMINED. No external execution or grade claim.
"""

from copy import deepcopy
import unittest

from settlement_fsm import SettlementMachine
from mock_settlement import SettlementError
from settlement_property_support import policy

ERROR = SettlementError

DUPLICATE = ("ok", True, None)
CONFLICT = ("error", "IDEMPOTENCY_CONFLICT")


def outcome(fn):
    try:
        result = fn()
    except ERROR as error:
        return ("error", error.code)
    return ("ok", result["duplicate"], result["applied"])


def invoke(machine, command):
    op, subject, body = deepcopy(command)
    return getattr(machine, op)(subject, **body)


def probe(test, factory, restore, first, retries):
    machine = factory()
    test.assertEqual(outcome(lambda: invoke(machine, first)), ("ok", False, first[0]))
    state, journal = machine.canonical_state(), machine.export_journal()
    for retry, expected in retries:
        with test.subTest(first=first, retry=retry):
            test.assertEqual(outcome(lambda: invoke(machine, retry)), expected)
            test.assertEqual(machine.canonical_state(), state)
            test.assertEqual(machine.export_journal(), journal)
            restored = restore(deepcopy(journal))
            test.assertEqual(restored.canonical_state(), state)
            test.assertEqual(restored.state_digest(), machine.state_digest())
            test.assertEqual(outcome(lambda: invoke(restored, retry)), expected)
            test.assertEqual(restored.canonical_state(), state)
            test.assertEqual(restored.export_journal(), journal)


def command(op, subject, **body):
    return op, subject, dict(idempotency_key="probe", **body)


def initiation():
    return dict(trade_id="trade", gross=100, debtor_role="merchant", policy=policy(0))


def statement(movement, amount):
    return dict(movement_id=movement, gross=amount, amount=amount,
                fee=0, tax=0, held=0, adjustment=0)


def captured():
    machine = SettlementMachine()
    machine.initiate("s", idempotency_key="init", **initiation())
    machine.authorize("s", idempotency_key="auth")
    machine.capture("s", idempotency_key="capture")
    return machine


def committed():
    machine = captured()
    machine.commit("s", idempotency_key="commit", **statement("m1", 60))
    return machine


class SettlementRestoreFingerprintClassATests(unittest.TestCase):
    """SETTLEMENT_DISTRIBUTION_F01_F03 §§9.3–9.4: normalized replay/restore."""

    def test_initiate_currency(self):
        self.check_variants(SettlementMachine, "initiate", initiation(), "currency", "KRW")

    def test_commit_adjustment_reason(self):
        self.check_variants(captured, "commit", statement("m1", 60), "adjustment_reason", None)

    def test_observe_statement_adjustment_reason(self):
        self.check_variants(committed, "observe_statement", statement("m2", 40), "adjustment_reason", None)

    def check_variants(self, factory, op, body, field, value):
        variants = [command(op, "s", **body), command(op, "s", **body, **{field: value})]
        for first in variants:
            probe(self, factory, SettlementMachine.restore, first,
                  [(retry, DUPLICATE) for retry in variants])


if __name__ == "__main__":
    unittest.main()
