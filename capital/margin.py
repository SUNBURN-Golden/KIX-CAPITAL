"""Margin call, cure window, acceleration and default-eligible proposals on the overlay.

SIMULATED memo rules of CAPITAL-TERMS-V1 `additional_margin`. Nothing here is a payment,
a collateral action or a legal default. The F04 journal is never written and the FSM
`default` command is never called: an uncured, accelerated advance only produces a
DEFAULT_ELIGIBLE proposal for a human operator.

Pure functions plan overlay entries; the service decides whether to store them. Workspace
settlement views are immutable, so a margin call cannot fire there: those rows report
`checked` true and `triggered` false with the FIXTURE_VIEWS_IMMUTABLE limit. Rules run only
against a source that declares `settlement_views_mutable`, i.e. the disposable
ScenarioReplaySource below, which replays F01-F03 scenario steps on its own books.

All arithmetic is integer. Every integer literal is 0, 1 or 2; the rate, the cure window and
the grace come from the decision note through `terms.margin_terms`.

Accrual is not re-based: interest and write-off keep the standard maturity until the
financial-terms owner decides (NOT_REBASED / DECISION_REQUIRED, see `interest_rebased`).
"""
from __future__ import annotations

import copy
from typing import Protocol

from capital import overlay
from capital.producer import FixtureViews
from capital.protocol import SettlementError
from capital.terms import BPS_SCALE

LABEL = 'SIMULATED margin check — not a collateral action, not a default, not an F04 journal entry'
LIMIT_IMMUTABLE = 'FIXTURE_VIEWS_IMMUTABLE'
SOURCE_FIXTURE = 'READ_ONLY_FIXTURE'
SOURCE_DISPOSABLE = 'SIMULATED_DISPOSABLE_BOOK'
PROPOSAL_KIND = 'DEFAULT_ELIGIBLE'
PROPOSAL_AUTHORITY = 'HUMAN_OPERATOR_DECISION'
DRAWN = 'DRAWN'

CALLED = 'CALLED'
CURED = 'CURED'
ACCELERATED = 'ACCELERATED'

KIND_OF_RECORD = {
    overlay.KIND_MARGIN_CALL: 'MARGIN_CALL',
    overlay.KIND_MARGIN_CURE: 'MARGIN_CURE',
    overlay.KIND_MARGIN_ACCELERATION: 'MARGIN_ACCELERATION',
    overlay.KIND_DEFAULT_PROPOSAL: 'DEFAULT_ELIGIBLE_PROPOSAL',
}


# ---------------------------------------------------------------- measurement

def eligible_face(claim, payees):
    """Outstanding on the beneficiary's payee lines minus open refund face, never below zero.

    None when the claim is malformed. Same inputs and rule as terms._borrowing_base.
    """
    obligations = claim.get('obligations') if type(claim) is dict else None
    refund = claim.get('refund_face') if type(claim) is dict else None
    if type(obligations) is not list or type(refund) is not int or refund < 0:
        return None
    total = 0
    for line in obligations:
        if type(line) is not dict or line.get('payee') not in payees:
            continue
        outstanding = line.get('outstanding')
        if type(outstanding) is not int or outstanding < 0:
            return None
        total += outstanding
    return max(0, total - refund)


def measure(subject):
    """The base and the breach test for one subject, or None when terms or claim are not usable."""
    terms = subject.get('margin')
    outstanding = subject['principal']
    if terms is None or type(outstanding) is not int or outstanding < 0:
        return None
    eligible = eligible_face(subject['claim'], terms['payees'])
    if eligible is None:
        return None
    base = eligible * terms['advance_rate_bps'] // BPS_SCALE
    return {'eligible_face_krw': eligible, 'advance_rate_bps': terms['advance_rate_bps'],
            'base_krw': base, 'outstanding_krw': outstanding, 'headroom_krw': base - outstanding,
            'breach': outstanding > 0 and outstanding > base}


def _record(state, advance_id):
    return state.get('margin', {}).get('advances', {}).get(advance_id)


def _figures(measured):
    return {'outstanding_krw': measured['outstanding_krw'], 'eligible_face_krw': measured['eligible_face_krw'],
            'base_krw': measured['base_krw']}


def _entry(operation_id, kind, advance_id, after_journal_index, day, payload):
    return {'overlay_id': f'{operation_id}:margin:{advance_id}:{kind}', 'after_journal_index': after_journal_index,
            'sim_day': day, 'kind': kind, 'payload': {'advance_id': advance_id, **payload}}


# ---------------------------------------------------------------- rules

def acceleration_figures(maturity_day, cure_deadline, grace_days):
    """maturity := cure_deadline, never later than the standard maturity; default-eligible after grace."""
    maturity_after = min(maturity_day, cure_deadline)
    return maturity_after, maturity_after + grace_days + 1


def plan_cures(state, subjects, *, operation_id, journal_length, day):
    """Cure entries for open calls, evaluated at `day` (the folded sim_day, before the clock moves).

    F04 commands run at the folded day, so a repay since the last tick is dated correctly here.
    The cure deadline is inclusive. Acceleration is never reversed.
    """
    out = []
    for subject in sorted(subjects, key=lambda item: item['advance_id']):
        record = _record(state, subject['advance_id'])
        measured = measure(subject)
        if record is None or record['status'] != CALLED or measured is None:
            continue
        if day > record['cure_deadline'] or measured['breach']:
            continue
        out.append(_entry(operation_id, overlay.KIND_MARGIN_CURE, subject['advance_id'], journal_length, day, {
            **_figures(measured), 'cure_deadline': record['cure_deadline'],
            'cure_option': subject['margin']['cure_options'][0],
            'terms_version': subject['margin']['terms_version']}))
    return out


def plan_rules(state, subjects, *, operation_id, journal_length, day):
    """Call, acceleration and proposal entries evaluated at `day`, the tick's target day.

    One pass may chain acceleration into a proposal when the tick spans both days.
    """
    out = []
    for subject in sorted(subjects, key=lambda item: item['advance_id']):
        advance_id = subject['advance_id']
        measured = measure(subject)
        if measured is None:
            continue
        terms = subject['margin']
        record = _record(state, advance_id)
        status = None if record is None else record['status']
        deadline = None if record is None else record['cure_deadline']
        if subject['case']['phase'] == DRAWN and measured['breach'] and status in (None, CURED):
            deadline = day + terms['cure_window_days']
            out.append(_entry(operation_id, overlay.KIND_MARGIN_CALL, advance_id, journal_length, day, {
                **_figures(measured), 'tier': terms['tier'], 'advance_rate_bps': terms['advance_rate_bps'],
                'cure_window_days': terms['cure_window_days'], 'cure_deadline': deadline,
                'cure_option': terms['cure_options'][0], 'maturity_day': terms['maturity_day'],
                'terms_version': terms['terms_version']}))
            continue
        if status == CALLED and day > deadline and measured['breach']:
            maturity_after, eligible_day = acceleration_figures(
                record['maturity_day'], deadline, terms['grace_days'])
            out.append(_entry(operation_id, overlay.KIND_MARGIN_ACCELERATION, advance_id, journal_length, day, {
                **_figures(measured), 'cure_deadline': deadline, 'maturity_before': record['maturity_day'],
                'maturity_after': maturity_after, 'grace_days': terms['grace_days'],
                'default_eligible_day': eligible_day, 'terms_version': terms['terms_version']}))
            status, record = ACCELERATED, {**record, 'default_eligible_day': eligible_day, 'proposal_day': None}
        if (status == ACCELERATED and record['proposal_day'] is None and day >= record['default_eligible_day']
                and subject['case']['phase'] == DRAWN and measured['outstanding_krw'] > 0):
            out.append(_entry(operation_id, overlay.KIND_DEFAULT_PROPOSAL, advance_id, journal_length, day, {
                'proposal_kind': PROPOSAL_KIND, 'authority': PROPOSAL_AUTHORITY,
                'default_eligible_day': record['default_eligible_day'],
                'outstanding_krw': measured['outstanding_krw'], 'terms_version': terms['terms_version']}))
    return out


# ---------------------------------------------------------------- read model

def _cure_options(terms):
    options = [] if terms is None else terms['cure_options']
    return [{'option': name, 'status': 'AVAILABLE' if index == 0 else 'NOT_BOUND'}
            for index, name in enumerate(options)]


def _row(subject, record, *, mutable):
    measured = measure(subject)
    base = unbound_row(subject['advance_id'])
    if measured is None:
        return base
    figures = {key: measured[key] for key in ('eligible_face_krw', 'advance_rate_bps', 'base_krw',
                                              'outstanding_krw', 'headroom_krw')}
    if record is None:
        state = 'WITHIN_BASE'
        if not mutable:
            state = 'FIXTURE_LIMIT'
        elif measured['breach'] and subject['case']['phase'] == DRAWN:
            state = 'BREACH_AWAITING_TICK'
    else:
        state = record['status']
    live = mutable and record is not None and record['status'] in (CALLED, ACCELERATED)
    return {**base, **figures, 'state': state, 'checked': True, 'triggered': live,
            'cure_deadline': None if record is None else record['cure_deadline'],
            'effective_maturity_day': None if record is None else record['maturity_day'],
            'default_eligible_day': None if record is None else record.get('default_eligible_day')}


def unbound_row(advance_id):
    """A row without margin terms: no numeric fields, nothing checked."""
    return {'advance_id': advance_id, 'checked': False, 'triggered': False, 'state': 'NOT_APPLICABLE',
            'interest_rebased': False}


def row_blocks(state, subjects, *, mutable):
    """Per-advance margin rows keyed by advance_id. Read-only."""
    return {subject['advance_id']: _row(subject, _record(state, subject['advance_id']), mutable=mutable)
            for subject in subjects}


def status_block(state, rows, *, mutable, bound, cure_terms=None):
    """The `margin` block of GET /api/overlay. Read-only; nothing is evaluated into the journal."""
    rows = list(rows.values())
    names = set(KIND_OF_RECORD.values())
    events = [dict(item) for item in state['sections']['decision_records'] if item.get('record') in names]
    return {
        'label': LABEL,
        'source': SOURCE_DISPOSABLE if mutable else SOURCE_FIXTURE,
        'status': 'BOUND' if bound else 'NOT_BOUND',
        'reason': None if bound else 'terms not bound',
        'checked': bound,
        'triggered': any(row['triggered'] for row in rows),
        'limit': None if mutable else LIMIT_IMMUTABLE,
        'cure_window_days': None if cure_terms is None else cure_terms['cure_window_days'],
        'cure_options': _cure_options(cure_terms),
        'interest_rebased': False,
        'events': events,
        'proposals': [item for item in events if item['record'] == KIND_OF_RECORD[overlay.KIND_DEFAULT_PROPOSAL]],
        'f04_default_called': False,
        'proposal_only': True,
    }


# ---------------------------------------------------------------- settlement sources

class SettlementSource(Protocol):
    """What the margin rules read. `settlement_views_mutable` says whether the rules may journal."""

    settlement_views_mutable: bool
    projection_ids: frozenset
    rows: dict

    def view(self, key): ...

    def beneficiary(self, key): ...

    def profile(self, key): ...


def views_mutable(source):
    return getattr(source, 'settlement_views_mutable', False) is True


class ScenarioReplaySource(FixtureViews):
    """SIMULATED / DISPOSABLE_BOOK_ONLY. Replays F01-F03 scenario steps on its own books.

    Never a default code path: only a caller that builds it gets a source whose settlement
    views change. The pinned FixtureViews (and the workspace) stay immutable.
    """

    label = 'SIMULATED'
    scope = 'DISPOSABLE_BOOK_ONLY'
    settlement_views_mutable = True

    def __init__(self):
        self.books = {}
        super().__init__()

    def _store(self, fixture_id, profile, beneficiary, book):
        self.books[fixture_id] = book
        super()._store(fixture_id, profile, beneficiary, book)

    def replay(self, fixture_id, scenario_id, steps=None):
        """Apply a scenario's steps to one fixture's book. Outcomes are returned, never raised.

        `steps` defaults to the scenario's own steps. A scenario's first statement that equals the
        statement the fixture already committed is skipped as ALREADY_OBSERVED.
        """
        from capital import scenarios
        if fixture_id not in self.books:
            raise SettlementError('UNKNOWN_SETTLEMENT')
        if steps is None:
            found = {name: commands for name, _title, _text, commands in scenarios.definitions()}
            if scenario_id not in found:
                raise SettlementError('UNKNOWN_SCENARIO')
            steps = found[scenario_id]
        outcomes = []
        for ordinal, command in enumerate(steps, 1):
            outcomes.append(self._apply_step(fixture_id, scenario_id, ordinal, command))
        return outcomes

    def _apply_step(self, fixture_id, scenario_id, ordinal, command):
        book, op, args = self.books[fixture_id], command['op'], copy.deepcopy(command['args'])
        key = f'{scenario_id}:{ordinal}'
        error, skipped = None, False
        try:
            if op == 'observe_settlement_statement':
                skipped = self._already_observed(fixture_id, args)
                if not skipped:
                    book.observe_statement(fixture_id, idempotency_key=key, **{'adjustment': 0, **args})
            elif op == 'apply_distribution':
                book.distribute(fixture_id, idempotency_key=key, order=args['order'])
            elif op == 'bind_refund':
                book.bind_refund(fixture_id, idempotency_key=key, **args)
            elif op == 'observe_mock_cancel_acceptance':
                book.observe_mock_cancel_acceptance(fixture_id, idempotency_key=key, **args)
            else:
                error = 'UNSUPPORTED_SCENARIO_OP'
        except SettlementError as exc:
            error = exc.code
        except Exception as exc:  # the pinned machines raise their own error types
            error = getattr(exc, 'code', type(exc).__name__)
        self.rows[fixture_id] = book.view(fixture_id)
        return {'ordinal': ordinal, 'op': op, 'error': error, 'expected_error': command['expected_error'],
                'matched': error == command['expected_error'], 'skipped': 'ALREADY_OBSERVED' if skipped else None,
                'label': self.label, 'scope': self.scope}

    def _already_observed(self, fixture_id, args):
        claim = self.rows[fixture_id]['claim']
        return (self.rows[fixture_id].get('commit_movement_id') is not None
                and claim['confirmed_cash'] == args['amount'] and claim['non_cash_accounted'] == args['fee']
                and claim['gross'] == args['gross'])
