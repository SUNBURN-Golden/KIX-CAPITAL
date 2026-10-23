"""Read-only set-off proposal quote on an advance's bound settlement view.

Applies the ADOPTED ``collateral_execution.primary`` step of the financial-terms
note (set-off against the beneficiary's settlement distribution) to the cash
the pinned settlement view already shows as distributed on the beneficiary's
counterparty-proceeds lines (CAPITAL-ALLOC-V1 class table of the settlement
note). The proposal is ``min(outstanding_exposure, that cash)`` split in the
note's ``repayment_allocation_order`` through the same arithmetic path as the
repayment allocation quote. It is a proposal only: execution authority is
echoed from the note and stays with human operators, the pinned FSM is never
invoked, no receipt or journal entry is written, cash under ``recovery_due``
is not counted, and the overlay recovery ledger after DEFAULTED is out of
scope. A missing or unusable note entry, or an undecided settlement class
table, is NOT_BOUND and carries no numbers.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from capital.policy import POLICY_NOT_BOUND
from capital.terms import OVERLAY_LABEL, TERMS_NOT_BOUND

SETOFF_MODE = 'SIMULATED_OVERLAY'
POST_DEFAULT = 'OVERLAY_RECOVERY_LEDGER_NOT_IN_SCOPE'
SETTLEMENT_NOT_BOUND = 'settlement not bound'
SETTLEMENT_VIEW_UNREADABLE = 'settlement view unreadable'
BENEFICIARY_NOT_MAPPED = 'beneficiary not mapped'
PRIMARY_STEP_NOT_SETOFF = 'primary step is not set-off'
EXECUTION_AUTHORITY_NOT_HUMAN = 'execution authority not human'
COUNTERPARTY_CLASS_NOT_FOUND = 'counterparty class not found'

ALLOCATION_OBSERVED = 'ALLOCATION_OBSERVED'
ALLOCATION_NOT_OBSERVED = 'ALLOCATION_NOT_OBSERVED'
ALLOCATED_CASH_UNDER_RECOVERY = 'ALLOCATED_CASH_UNDER_RECOVERY'
CAPPED_BY_EXPOSURE = 'EXPOSURE'
CAPPED_BY_ALLOCATED_CASH = 'ALLOCATED_CASH'
ROUTE_FSM_REPAY = 'FSM_REPAY'
ROUTE_OVERLAY_LEDGER = 'OVERLAY_RECOVERY_LEDGER'
ROUTE_NOT_APPLICABLE = 'NOT_APPLICABLE'

_PRIMARY_STEP = 'SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION'
_HUMAN_AUTHORITY_PREFIX = 'HUMAN_OPERATOR'
_COUNTERPARTY_ROW = 'COUNTERPARTY_PROCEEDS'
_LINE_KEYS = ('face', 'distributed', 'cancelled_unpaid', 'recovery_due', 'outstanding')
_VIEW_CASH_KEYS = (
    'gross', 'confirmed_cash', 'distributed_cash', 'undistributed_cash',
    'recovery_due', 'refund_face', 'refund_outstanding',
)


def _nonneg_int(value):
    return type(value) is int and value >= 0


def _nonempty_str(value):
    return type(value) is str and bool(value.strip())


def _unbound_section(reason=TERMS_NOT_BOUND):
    return {'status': 'NOT_BOUND', 'reason': reason}


def _na_section(reason):
    return {'status': 'NOT_APPLICABLE', 'reason': reason}


def observed_distribution(line):
    """Unencumbered observed cash on one payee line, shared by recovery quotes."""
    return max(0, line['distributed'] - line['recovery_due'])


@runtime_checkable
class SetoffQuotePort(Protocol):
    """Quote the decided primary recovery step on one bound settlement view. Not an execution."""

    def proposal(self, case, claim, *, draw_day, as_of_day, expected_settlement_cash_day, gate) -> dict:
        """Read-only set-off proposal. Nothing is posted; the pinned FSM is not called."""


class DecisionNoteSetoff:
    """Set-off quote read from the two parsed decision notes. No copied literals."""

    def __init__(self, terms, policy):
        self.terms = terms
        self.policy = policy

    def _value(self, name):
        items = getattr(self.terms, 'items', None)
        item = items.get(name) if type(items) is dict else None
        if type(item) is not dict or item.get('mark') != 'ADOPTED':
            return None
        return item['value']

    def _top(self):
        top = getattr(self.terms, 'top', 'NOT_BOUND')
        reason = getattr(self.terms, 'reason', TERMS_NOT_BOUND)
        return top, reason

    def _unbound(self, advance_id):
        return {
            'label': OVERLAY_LABEL,
            'mode': SETOFF_MODE,
            'terms_version': getattr(self.terms, 'version', None),
            'provisional': True,
            'status': 'NOT_BOUND',
            'reason': TERMS_NOT_BOUND,
            'advance_id': advance_id,
            'proposal_only': True,
            'applied': False,
            'execution_authority': None,
            'collateral_execution': _unbound_section(),
            'recovery_waterfall': _unbound_section(),
            'settlement_view': _unbound_section(),
            'setoff': _unbound_section(),
            'interest': _unbound_section(),
            'allocation': _unbound_section(),
            'fsm_repay': None,
            'close_ready': False,
            'post_default': POST_DEFAULT,
        }

    def _execution(self):
        """(echo section, authority, reason). The quote refuses a non-human or non-set-off step."""
        execution = self._value('collateral_execution')
        if execution is None:
            return _unbound_section(), None, TERMS_NOT_BOUND
        echo = {
            'applied': False,
            'primary': execution['primary'],
            'secondary': execution['secondary'],
            'tertiary': execution['tertiary'],
            'never': list(execution['never']),
            'execution_authority': execution['execution_authority'],
        }
        if execution['primary'] != _PRIMARY_STEP:
            return echo, execution['execution_authority'], PRIMARY_STEP_NOT_SETOFF
        if not execution['execution_authority'].startswith(_HUMAN_AUTHORITY_PREFIX):
            return echo, execution['execution_authority'], EXECUTION_AUTHORITY_NOT_HUMAN
        return echo, execution['execution_authority'], None

    def _waterfall(self):
        loss = self._value('default_loss_treatment')
        if loss is None:
            return _unbound_section()
        return {
            'status': 'BOUND',
            'applied': False,
            'steps': list(loss['recovery_waterfall']),
            'loss_bearer_v1': loss['loss_bearer_v1'],
        }

    def _class_map(self, claim):
        """(payee_classes result, reason). The settlement note decides the class of each payee."""
        accessor = getattr(self.policy, 'payee_classes', None)
        if not callable(accessor):
            return None, POLICY_NOT_BOUND
        result = accessor(claim.get('policy'))
        if type(result) is not dict or result.get('outcome') != 'DECIDED' or type(result.get('classes')) is not dict:
            reason = result.get('reason') if type(result) is dict else None
            return None, reason if _nonempty_str(reason) else POLICY_NOT_BOUND
        return result, None

    def _counterparty(self, classes):
        """Class number of the counterparty-proceeds row, or None when no payee sits in it."""
        for row in classes.values():
            if row.get('id') == _COUNTERPARTY_ROW:
                return row['class']
        return None

    def _lines(self, claim, payees, classes, counterparty_class):
        """Classified copies of the view's obligation lines. None when a value is not a usable integer."""
        obligations = claim.get('obligations')
        if type(obligations) is not list:
            return None
        rows = []
        for line in obligations:
            if type(line) is not dict or not _nonempty_str(line.get('payee')):
                return None
            values = {}
            for key in _LINE_KEYS:
                if not _nonneg_int(line.get(key)):
                    return None
                values[key] = line[key]
            payee = line['payee']
            row = classes.get(payee)
            cls = row['class'] if type(row) is dict else None
            mapped = payee in payees
            counted = mapped and cls is not None and cls == counterparty_class
            eligible = observed_distribution(values)
            rows.append({
                'payee': payee,
                'class': cls,
                'class_id': row.get('id') if type(row) is dict else None,
                'beneficiary_mapped': mapped,
                'counted': counted,
                **values,
                'eligible_krw': eligible if counted else 0,
            })
        return rows

    def _view_facts(self, claim):
        facts = {}
        for key in _VIEW_CASH_KEYS:
            if not _nonneg_int(claim.get(key)):
                return None
            facts[key] = claim[key]
        if type(claim.get('fixture_reclassified')) is not bool:
            return None
        order = claim.get('distribution_order')
        if order is not None and (type(order) is not list or any(not _nonempty_str(item) for item in order)):
            return None
        facts['fixture_reclassified'] = claim['fixture_reclassified']
        facts['distribution_order'] = None if order is None else list(order)
        return facts

    def _bound(self, case, claim):
        settlement_id = case.get('settlement_id')
        return _nonempty_str(settlement_id) and settlement_id == claim.get('claim_id')

    def _quote(self, case, claim, gate):
        """(settlement_view section, setoff section). Either may be NOT_BOUND or NOT_APPLICABLE."""
        margin = self._value('additional_margin')
        if margin is None:
            return _unbound_section(), _unbound_section()
        if not self._bound(case, claim):
            return _na_section(SETTLEMENT_NOT_BOUND), _na_section(SETTLEMENT_NOT_BOUND)
        role = case.get('beneficiary_role')
        payees = margin['beneficiary_payee_map'].get(role)
        if payees is None:
            return _unbound_section(BENEFICIARY_NOT_MAPPED), _unbound_section(BENEFICIARY_NOT_MAPPED)
        policy, reason = self._class_map(claim)
        if policy is None:
            return _unbound_section(reason), _unbound_section(reason)
        counterparty_class = self._counterparty(policy['classes'])
        if counterparty_class is None:
            return _unbound_section(COUNTERPARTY_CLASS_NOT_FOUND), _unbound_section(COUNTERPARTY_CLASS_NOT_FOUND)
        facts = self._view_facts(claim)
        lines = self._lines(claim, payees, policy['classes'], counterparty_class)
        outstanding = case.get('outstanding_exposure')
        if facts is None or lines is None or not _nonneg_int(outstanding):
            return _unbound_section(SETTLEMENT_VIEW_UNREADABLE), _unbound_section(SETTLEMENT_VIEW_UNREADABLE)
        allocated = sum(row['distributed'] for row in lines if row['counted'])
        recovery = sum(row['recovery_due'] for row in lines if row['counted'])
        base = sum(row['eligible_krw'] for row in lines if row['counted'])
        if base > 0:
            base_reason = ALLOCATION_OBSERVED
        elif allocated > 0:
            base_reason = ALLOCATED_CASH_UNDER_RECOVERY
        else:
            base_reason = ALLOCATION_NOT_OBSERVED
        amount = base if base < outstanding else outstanding
        phase = case.get('phase')
        if phase == 'DRAWN':
            route = ROUTE_FSM_REPAY
        elif phase == 'DEFAULTED':
            route = ROUTE_OVERLAY_LEDGER
        else:
            route = ROUTE_NOT_APPLICABLE
        view = {
            'status': 'BOUND',
            'claim_id': claim['claim_id'],
            'gate': gate,
            'policy_version': policy['alloc_version'],
            'policy_digest': policy['policy_digest'],
            'beneficiary_role': role,
            'beneficiary_payees': list(payees),
            'counterparty_class': counterparty_class,
            'counterparty_class_id': _COUNTERPARTY_ROW,
            **facts,
            'lines': lines,
            'recovery_due_excluded': True,
        }
        setoff = {
            'status': 'BOUND',
            'outstanding_exposure': outstanding,
            'allocated_krw': allocated,
            'recovery_due_krw': recovery,
            'base_krw': base,
            'base_reason': base_reason,
            'setoff_amount': amount,
            'capped_by': CAPPED_BY_ALLOCATED_CASH if base < outstanding else CAPPED_BY_EXPOSURE,
            'route': route,
        }
        return view, setoff

    def proposal(self, case, claim, *, draw_day, as_of_day, expected_settlement_cash_day, gate) -> dict:
        advance_id = case.get('advance_id') if type(case) is dict else None
        top, reason = self._top()
        if top == 'NOT_BOUND' or type(case) is not dict or type(claim) is not dict:
            return self._unbound(advance_id)
        echo, authority, execution_reason = self._execution()
        if execution_reason is None:
            view, setoff = self._quote(case, claim, gate)
        else:
            view, setoff = _unbound_section(execution_reason), _unbound_section(execution_reason)
        cash = setoff['setoff_amount'] if setoff['status'] == 'BOUND' else 0
        quote = self.terms.allocation(
            case, claim, draw_day=draw_day, as_of_day=as_of_day,
            expected_settlement_cash_day=expected_settlement_cash_day, gate=gate, cash=cash)
        if setoff['status'] == 'BOUND':
            split = quote['allocation']
            fsm_repay = quote['fsm_repay']
            close_ready = quote['close_ready']
        else:
            split = dict(setoff)
            fsm_repay = None
            close_ready = False
        return {
            'label': OVERLAY_LABEL,
            'mode': SETOFF_MODE,
            'terms_version': getattr(self.terms, 'version', None),
            'provisional': True,
            'status': top,
            'reason': reason,
            'advance_id': advance_id,
            'proposal_only': True,
            'applied': False,
            'execution_authority': authority,
            'tier': quote.get('tier', 'NOT_APPLICABLE'),
            'principal': quote.get('principal'),
            'collateral_execution': echo,
            'recovery_waterfall': self._waterfall(),
            'settlement_view': view,
            'setoff': setoff,
            'interest': quote['interest'],
            'allocation': split,
            'fsm_repay': fsm_repay,
            'close_ready': close_ready,
            'post_default': POST_DEFAULT,
        }
