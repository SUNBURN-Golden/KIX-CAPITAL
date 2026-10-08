"""Pinned FSM adapter for ProducerPort.

This wraps the byte-pinned CreditMachine and the immutable settlement
fixtures. It is not a live producer, not a Commerce binding, and not
SEMANTIC_CONFORMANCE. CAP-16 exact tuple stays NOT_BOUND.
"""
from __future__ import annotations

import copy

from capital.protocol import CreditError, CreditMachine, SettlementMachine

# Re-exported so command vectors and the service share one error type.
__all__ = ('CreditError', 'FixtureViews', 'PinnedFsmProducer')


class FixtureViews:
    """No commands exposed to the credit adapter; snapshots cannot be advanced."""

    def __init__(self):
        self.rows = {}
        for fixture_id, phase, refund in (
            ('sim-committed', 'COMMITTED', False),
            ('sim-pending', 'CAPTURED', False),
            ('sim-refund', 'COMMITTED', True),
        ):
            book = SettlementMachine()
            book.initiate(fixture_id, idempotency_key='init', trade_id='sim-trade-' + fixture_id,
                          gross=100_000, debtor_role='fixture-merchant',
                          policy={'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
                                  'residual_payee': 'organizer', 'fee_payee': 'platform'})
            book.authorize(fixture_id, idempotency_key='authorize')
            book.capture(fixture_id, idempotency_key='capture')
            if phase == 'COMMITTED':
                book.commit(fixture_id, idempotency_key='commit', movement_id='sim-movement',
                            gross=100_000, amount=97_000, fee=3_000, tax=0, held=0, adjustment=0)
            # Adverse fixture: one synthetic partial refund through the pinned FSM, so
            # bearer UNDEFINED and the distribution block are derived, never hand-set.
            if refund:
                book.bind_refund(fixture_id, idempotency_key='refund', refund_id='sim-fixture-refund',
                                 amount=10_000, beneficiary_role='fixture-buyer', reason='SYNTHETIC_FIXTURE')
            self.rows[fixture_id] = book.view(fixture_id)

    def view(self, key):
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return copy.deepcopy(self.rows[key])


class PinnedFsmProducer:
    """Local ProducerPort. Command bytes go to the pinned credit FSM only."""

    def __init__(self, fixtures=None, machine=None):
        self.fixtures = fixtures if fixtures is not None else FixtureViews()
        self.machine = machine if machine is not None else CreditMachine(self.fixtures)

    def reset(self):
        self.machine = CreditMachine(self.fixtures)

    def restored(self, journal):
        """New producer, same settlement fixtures, book restored from `journal`."""
        return PinnedFsmProducer(self.fixtures, CreditMachine.restore(journal, self.fixtures))

    def view(self, advance_id):
        return self.machine.view(advance_id)

    def export_journal(self):
        return self.machine.export_journal()

    def state_digest(self) -> str:
        return self.machine.state_digest()

    def canonical_state(self) -> str:
        return self.machine.canonical_state()

    def preview_draw(self, advance_id):
        """Disposable draw. The idempotency key and draw id stay the diagnostic pair."""
        scratch = CreditMachine.restore(self.machine.export_journal(), self.fixtures)
        return scratch.draw(advance_id, idempotency_key='diagnostic:draw', draw_id='diagnostic:draw')

    def apply(self, op, advance_id, *, idempotency_key, args, bound_settlement_id):
        """Same kwargs the facade used to pass straight into CreditMachine."""
        method = getattr(self.machine, op)
        kwargs = {'idempotency_key': idempotency_key}
        if op == 'offer':
            fixture_id = args['fixture_id']
            if type(fixture_id) is not str or fixture_id not in self.fixtures.rows:
                raise CreditError('UNKNOWN_SETTLEMENT')
            kwargs.update(face=self.fixtures.view(fixture_id)['claim'],
                          amount=args['amount'], beneficiary_role='fixture-organizer')
        elif op == 'bind_settlement':
            if bound_settlement_id is None:
                raise CreditError('UNKNOWN_ADVANCE')
            kwargs['settlement_id'] = bound_settlement_id
        elif op == 'draw':
            kwargs['draw_id'] = 'draw-' + idempotency_key
        elif op == 'repay':
            kwargs.update(amount=args['amount'], sequence=args['sequence'], repay_id='repay-' + idempotency_key)
        elif op in {'reject', 'cancel', 'default'}:
            kwargs['reason'] = 'synthetic-operator-scenario'
        return method(advance_id, **kwargs)
