"""Offline, source-informed probes. Synthetic amounts; policy stays UNDETERMINED."""

from copy import deepcopy
import unittest

from credit_fsm import CreditError, CreditMachine
from credit_property_support import make_face

ERROR = CreditError

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


class CreditRestoreFingerprintClassATests(unittest.TestCase):
    """CREDIT_ADVANCE_F04 §§7.3–7.4: normalized replay and restart duplicate."""

    def test_offer_product_omitted_or_none(self):
        face, ceiling = make_face("claim", (100,), (0,), "plain")
        body = dict(face=face, amount=ceiling, beneficiary_role="beneficiary")
        variants = [command("offer", "advance", **body),
                    command("offer", "advance", **body, product=None)]
        for first in variants:
            probe(self, CreditMachine, CreditMachine.restore, first,
                  [(retry, DUPLICATE) for retry in variants])
        machine = CreditMachine()
        invoke(machine, variants[1])
        self.assertNotIn("product", machine.export_journal()[-1]["body"])


if __name__ == "__main__":
    unittest.main()
