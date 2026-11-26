"""Explicit refund obligation followed by separate synthetic acceptance facts."""

import json

from cancel_acceptance_adapter import CancelAcceptanceAdapter
from fake_cancel_acceptance_source import FakeCancelAcceptanceSource
from fake_statement_source import FakeStatementSource
from mock_settlement import PROVENANCE
from settlement_fsm import SettlementError, SettlementMachine
from statement_adapter import StatementAdapter


def run_example(*, policy: dict, order: list) -> dict:
    """Caller provides fixture inputs; this journey performs no external action."""
    machine = SettlementMachine()
    sid = "fixture-settlement"
    statements = FakeStatementSource(recordings={
        (sid, "fixture-statement"): json.dumps(dict(
            settlement_id=sid, movement_id="fixture-statement", gross=100_000,
            amount=97_000, fee=3_000, tax=0, held=0, adjustment=0,
            adjustment_reason=None,
        )),
    })
    source = FakeCancelAcceptanceSource(recordings={
        (sid, source_id): json.dumps(dict(settlement_id=sid, source_id=source_id, amount=amount))
        for source_id, amount in (("fixture-acceptance-1", 10_000), ("fixture-acceptance-2", 5_000))
    })
    machine.initiate(sid, idempotency_key="fixture-initiate", trade_id="fixture-trade",
                     gross=100_000, debtor_role="fixture-merchant", policy=policy)
    machine.authorize(sid, idempotency_key="fixture-authorize")
    machine.capture(sid, idempotency_key="fixture-capture")
    initial = StatementAdapter(machine, statements).apply(
        operation="commit", settlement_id=sid, movement_id="fixture-statement",
        idempotency_key="fixture-commit",
    )
    # Creating an obligation is a separate explicit caller action.
    refund = machine.bind_refund(
        sid, idempotency_key="fixture-refund", refund_id="fixture-refund",
        amount=40_000, beneficiary_role="fixture-buyer", reason="fixture-reason",
    )
    adapter = CancelAcceptanceAdapter(machine, source)
    first = adapter.apply(settlement_id=sid, source_id="fixture-acceptance-1",
                          idempotency_key="fixture-observe-1")
    later = adapter.apply(settlement_id=sid, source_id="fixture-acceptance-2",
                          idempotency_key="fixture-observe-2")
    for receipt, adjustment in ((refund, 0), (first, 10_000), (later, 15_000)):
        claim = receipt["settlement"]["claim"]
        assert claim["confirmed_cash"] == 97_000
        assert claim["pg_adjustment_outstanding"] == adjustment
        assert claim["refund_outstanding"] == 40_000 - adjustment
        assert claim["refund_bearer_policy"] == "REQUESTER"
        for flag in ("funds_executed", "bank_debit_observed", "external_return_closed", "durable"):
            assert receipt["settlement"][flag] is False
    # Separate caller action; observations never select a distribution/burden.
    # B5 (SET-POLICY-DRAFT-0.4): an open partial refund reports REQUESTER and
    # no longer blocks distribution.
    distribution = machine.distribute(sid, idempotency_key="fixture-distribute", order=order)
    return dict(
        provenance=PROVENANCE, durable=False, funds_executed=False,
        bank_debit_observed=False, external_return_closed=False,
        initial=initial, refund=refund, first=first, later=later,
        distribution=distribution, journal=machine.export_journal(),
        statement_calls=statements.calls, source_calls=source.calls,
    )


if __name__ == "__main__":
    print(json.dumps(run_example(
        policy=dict(kind="PRIMARY_FEE_BPS", fee_bps=500,
                    residual_payee="fixture-organizer", fee_payee="fixture-platform"),
        order=["fixture-platform", "fixture-organizer"],
    ), indent=2, sort_keys=True))
