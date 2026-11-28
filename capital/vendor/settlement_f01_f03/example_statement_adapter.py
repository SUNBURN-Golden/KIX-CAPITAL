"""Runnable standard-library-only journey over synthetic statement recordings."""

import json

from fake_statement_source import FakeStatementSource
from mock_settlement import PROVENANCE
from settlement_fsm import SettlementMachine
from statement_adapter import StatementAdapter


def run_example(*, policy: dict, order: list) -> dict:
    """Caller supplies fixture policy/order; each transition is explicit."""
    machine = SettlementMachine()
    sid = "fixture-settlement"
    source = FakeStatementSource(recordings={
        (sid, "fixture-initial"): json.dumps(dict(
            settlement_id=sid, movement_id="fixture-initial", gross=60_000,
            amount=55_000, fee=2_000, tax=1_000, held=1_000, adjustment=1_000,
            adjustment_reason="fixture-adjustment",
        )),
        (sid, "fixture-later"): json.dumps(dict(
            settlement_id=sid, movement_id="fixture-later", gross=40_000,
            amount=38_000, fee=2_000, tax=0, held=0, adjustment=0,
            adjustment_reason=None,
        )),
    })
    adapter = StatementAdapter(machine, source)
    machine.initiate(
        sid, idempotency_key="fixture-initiate", trade_id="fixture-trade",
        gross=100_000, debtor_role="fixture-merchant", policy=policy,
    )
    machine.authorize(sid, idempotency_key="fixture-authorize")
    machine.capture(sid, idempotency_key="fixture-capture")
    initial = adapter.apply(
        operation="commit", settlement_id=sid, movement_id="fixture-initial",
        idempotency_key="fixture-commit",
    )
    later = adapter.apply(
        operation="observe_statement", settlement_id=sid, movement_id="fixture-later",
        idempotency_key="fixture-observe",
    )
    for receipt in (initial, later):
        assert receipt["settlement"]["claim"]["distributed_cash"] == 0
        assert receipt["settlement"]["claim"]["distribution_order"] is None
    assert later["settlement"]["claim"]["confirmed_cash"] == 93_000
    assert later["settlement"]["claim"]["non_cash_accounted"] == 7_000

    # Separate explicit caller action; the adapter never selects this operation.
    distributed = machine.distribute(sid, idempotency_key="fixture-distribute", order=order)
    claim = distributed["settlement"]["claim"]
    assert sum(line["face"] for line in claim["obligations"]) == 100_000
    assert all(line["face"] == line["distributed"] + line["outstanding"]
               + line["cancelled_unpaid"] for line in claim["obligations"])
    return dict(
        provenance=PROVENANCE, durable=False, funds_executed=False, chain_finality=False,
        initial=initial, later=later, distributed=distributed,
        journal=machine.export_journal(), source_calls=source.calls,
    )


if __name__ == "__main__":
    print(json.dumps(run_example(
        policy=dict(kind="PRIMARY_FEE_BPS", fee_bps=500,
                    residual_payee="fixture-organizer", fee_payee="fixture-platform"),
        order=["fixture-platform", "fixture-organizer"],
    ), indent=2, sort_keys=True))
