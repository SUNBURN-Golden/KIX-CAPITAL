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


_V1_PROFILE = 'fixture-v1'
DEMO_BOOK_PROFILE = 'CAPITAL-DEMO-BOOK-V1'
_POLICY = {'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
           'residual_payee': 'organizer', 'fee_payee': 'platform'}

# SYNTHETIC_FIXTURE_PROFILE claims of docs/decisions/CAPITAL_DEMO_BOOK.md
# (CAPITAL-DEMO-BOOK-V1): (fixture_id, gross, beneficiary_role, tier,
# open_refund_face). tests/test_demo_book.py pins this table to the parsed
# note block; a view field is never set by hand.
DEMO_BOOK = (
    ('demo-alpha-arena', 3_000_000_000, 'demo-org-alpha', 'T1', 0),
    ('demo-alpha-hall', 1_200_000_000, 'demo-org-alpha', 'T1', 0),
    ('demo-beta-festival', 4_000_000_000, 'demo-org-beta', 'T1', 0),
    ('demo-beta-club', 800_000_000, 'demo-org-beta', 'T2', 0),
    ('demo-gamma-tour', 8_000_000_000, 'demo-org-gamma', 'T2', 0),
    ('demo-gamma-annex', 2_400_000_000, 'demo-org-gamma', 'T1', 0),
    ('demo-delta-small', 50_000_000, 'demo-org-delta', 'T1', 0),
    ('demo-delta-mid', 1_000_000_000, 'demo-org-delta', 'T2', 0),
    ('demo-epsilon-refund', 400_000_000, 'demo-org-epsilon', 'T1', 60_000_000),
    ('demo-epsilon-clean', 2_000_000_000, 'demo-org-epsilon', 'T1', 0),
)


class FixtureViews:
    """No commands exposed to the credit adapter; snapshots cannot be advanced."""

    # The V1 projection keeps folding the original three views only, so its
    # pinned debit/credit totals are the evidence scope it always had.
    projection_ids = frozenset(('sim-committed', 'sim-pending', 'sim-refund'))

    def __init__(self):
        self.rows = {}
        self.profiles = {}
        self.beneficiaries = {}
        for fixture_id, phase, refund in (
            ('sim-committed', 'COMMITTED', False),
            ('sim-pending', 'CAPTURED', False),
            ('sim-refund', 'COMMITTED', True),
        ):
            book = SettlementMachine()
            book.initiate(fixture_id, idempotency_key='init', trade_id='sim-trade-' + fixture_id,
                          gross=100_000, debtor_role='fixture-merchant', policy=_POLICY)
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
            self._store(fixture_id, _V1_PROFILE, 'fixture-organizer', book)
        for fixture_id, gross, beneficiary, tier, refund_face in DEMO_BOOK:
            book = SettlementMachine()
            book.initiate(fixture_id, idempotency_key='init', trade_id='sim-trade-' + fixture_id,
                          gross=gross, debtor_role='fixture-merchant', policy=_POLICY)
            book.authorize(fixture_id, idempotency_key='authorize')
            book.capture(fixture_id, idempotency_key='capture')
            if tier == 'T1':
                # Same synthetic 97/3 commit split as the v1 fixtures.
                fee = gross * 3 // 100
                book.commit(fixture_id, idempotency_key='commit', movement_id='sim-movement',
                            gross=gross, amount=gross - fee, fee=fee, tax=0, held=0, adjustment=0)
            if refund_face:
                book.bind_refund(fixture_id, idempotency_key='refund', refund_id='demo-fixture-refund',
                                 amount=refund_face, beneficiary_role='demo-buyer',
                                 reason='SYNTHETIC_FIXTURE')
            self._store(fixture_id, DEMO_BOOK_PROFILE, beneficiary, book)

    def _store(self, fixture_id, profile, beneficiary, book):
        self.rows[fixture_id] = book.view(fixture_id)
        self.profiles[fixture_id] = profile
        self.beneficiaries[fixture_id] = beneficiary

    def view(self, key):
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return copy.deepcopy(self.rows[key])

    def beneficiary(self, key):
        """The beneficiary role a demo-book or v1 offer binds. Synthetic role."""
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return self.beneficiaries[key]

    def profile(self, key):
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return self.profiles[key]


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
                          amount=args['amount'], beneficiary_role=self.fixtures.beneficiary(fixture_id))
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
