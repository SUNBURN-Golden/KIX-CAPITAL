"""Minimum-cure quote for a recorded simulated margin call.

SIMULATED read-only advisory (cure-quote-scope-decision,
docs/decisions/CAPITAL_MINIMUM_CURE_QUOTE.md). For one identified drawn
advance under a recorded CALLED margin state the quote computes:

- `required_principal_reduction_krw` (R): the smallest integer principal
  reduction in [0, outstanding] that makes the existing `margin.measure`
  predicate true, preserving the borrowing base, thresholds, rounding and
  equality treatment of that predicate.
- `posted_interest_due_krw` (I): unpaid posted contractual and
  default-interest dues the existing pre-default waterfall consumes before
  principal, with the accrual witness numerator/denominator retained so the
  sub-won carry stays visible.
- `gross_repayment_resources_krw` (G), `held_cash_applied_krw` (A) and
  `minimum_new_cash_krw` (N): G = I + R when R > 0, A = min(H, G),
  N = G - A, where H is the recorded unconsumed held cash of the same
  advance (`overlay.repayment_position`). When R = 0, G = A = N = 0 and the
  outstanding interest stays disclosed.

Independence: the quote is a pure read of captured inputs. Sufficiency and
minimality are verified by applying the existing `post_repayment` command on
disposable service copies (`PinnedFsmProducer.restored` shares only the
settlement fixtures); the source journal, receipts, sim_day clock and
workspace bytes are never changed. `recorded_cure` reports the folded margin
status and is never synthesized from the quote; a recorded CURE requires the
existing tick ordering. Three conclusions are separate:
`arithmetic_sufficient`, `command_admissibility` and `recorded_cure`.

All policy constants come from the adopted decision notes at quote time;
this module copies no financial literals. The six entries of the cure quote
note are required ADOPTED, else the outcome is NOT_BOUND with the missing
names. Settlement imports, new HTTP routes, automatic postings, alternate
repayment schedules, refund-frontier search, waivers, backdating and real
money are all out of scope.

CLI: `python3 -m capital.cure_quote [--scenario ID | --list]` over the
bounded SCENARIOS registry of built-in disposable books. Canonical JSON on
stdout; exit 0 when evaluated, 1 on internal failure, 2 on misuse.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import sys

from capital import __version__, margin, overlay, recovery
from capital.export import strip_volatile
from capital.producer import PinnedFsmProducer
from capital.resources import as_resource, note_path, read_note
from capital.service import ApiError, CapitalService
from capital.store import canonical_bytes
from capital.terms import BPS_SCALE, DecisionNoteTermsPolicy

FORMAT = 'KIX_CAPITAL_CURE_QUOTE_V1'
NOTE_NAME = 'CAPITAL_MINIMUM_CURE_QUOTE.md'
DECISION_ID = 'cure-quote-scope-decision'
ENTRIES = ('cure_target_predicate', 'new_cash_and_held_cash', 'posted_interest_basis',
           'deadline_and_acceleration_boundary', 'quote_snapshot_binding',
           'unsupported_case_handling')
OUTCOMES = ('QUOTED', 'AT_DEADLINE', 'NO_REDUCTION_REQUIRED', 'WINDOW_EXPIRED',
            'ALREADY_ACCELERATED', 'TERMINAL_CASE', 'NO_ACTIVE_MARGIN_CALL',
            'NO_FEASIBLE_CURE', 'NOT_BOUND', 'INVALID_INPUT',
            'UNSUPPORTED_PRODUCER', 'UNSUPPORTED_CALCULATION', 'STALE_QUOTE')
AMOUNT_KEYS = ('required_principal_reduction_krw', 'posted_interest_due_krw',
               'interest_due_krw', 'default_interest_due_krw',
               'gross_repayment_resources_krw', 'eligible_held_cash_krw',
               'held_cash_applied_krw', 'minimum_new_cash_krw',
               'outstanding_principal_krw', 'base_krw', 'eligible_face_krw')
_LABEL = 'SIMULATED'
_MODE = 'READ_ONLY_CAPTURED_INPUT_ADVISORY'
_MONOTONIC = 'PRINCIPAL_REDUCTION_LINEAR_IN_CASH_ABOVE_POSTED_DUES'
_WITNESS_CURE = 'cq-witness-cure'
_WITNESS_MINUS = 'cq-witness-minus-one'
_CURE_PROBE = 'cq-cure-plan-probe'


class QuoteError(Exception):
    """An internal scenario or capture failure, not a product outcome."""


def _sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def note_binding(path=None):
    """The six adopted entries of the cure quote note, or the missing names."""
    resource = note_path(NOTE_NAME) if path is None else as_resource(path)
    note = read_note(resource)
    block = note['block']
    entries = (block or {}).get('entries') if type(block) is dict else None
    if type(entries) is not dict:
        entries = {}

    def adopted(value):
        return (type(value) is dict and value.get('status') == 'ADOPTED'
                and value.get('provisional') is True and type(value.get('value')) is dict)

    checks = {
        'cure_target_predicate': adopted(entries.get('cure_target_predicate')),
        'new_cash_and_held_cash': adopted(entries.get('new_cash_and_held_cash')),
        'posted_interest_basis': adopted(entries.get('posted_interest_basis')),
        'deadline_and_acceleration_boundary': adopted(entries.get('deadline_and_acceleration_boundary')),
        'quote_snapshot_binding': adopted(entries.get('quote_snapshot_binding')),
        'unsupported_case_handling': adopted(entries.get('unsupported_case_handling')),
    }
    missing = [name for name in ENTRIES if not checks[name]]
    return {'note': NOTE_NAME, 'notes_source': note['notes_source'],
            'note_sha256': note['note_sha256'], 'bound': not missing,
            'missing_entries': missing,
            'decision_id': (block or {}).get('decision_id') if type(block) is dict else None}


def _producer_of(service):
    producer = getattr(service, 'producer', None)
    source = getattr(service, 'source', None) or {}
    return {'type': type(producer).__name__,
            'supported': type(producer) is PinnedFsmProducer and callable(getattr(producer, 'restored', None)),
            'source_repository': source.get('repository'), 'source_commit': source.get('commit')}


def _margin_subject(service, advance_id):
    """The one margin subject of a drawn advance, or None."""
    try:
        subjects = service._overlay_subjects(service.overlay_entries)
    except ApiError:
        return None, 'SUBJECTS_NOT_BOUND'
    subject = next((item for item in subjects if item['advance_id'] == advance_id), None)
    if subject is None:
        return None, 'ADVANCE_NOT_DRAWN'
    margin_subjects = service._margin_subjects([subject])
    if not margin_subjects:
        return None, 'MARGIN_TERMS_NOT_BOUND'
    return margin_subjects[0], None


def capture(service, advance_id, *, note=None):
    """A consistent snapshot of every input the quote reads. Pure, no mutation."""
    binding = note_binding(note)
    cap = {'advance_id': advance_id, 'binding': binding, 'missing': [], 'invalid': [],
           'phase': None, 'terminal': False, 'record': None, 'measured': None,
           'tier': None, 'dues': None, 'sim_day': None, 'terms_version': None,
           'producer': _producer_of(service), 'notes': {}, 'input_digest': None}
    cap['missing'].extend('decision_entry:' + name for name in binding['missing_entries'])
    if not isinstance(service, CapitalService) or type(advance_id) is not str or not advance_id:
        cap['invalid'].append('SERVICE_OR_ADVANCE_INPUT')
        return cap
    live = {'service': service, 'state': None, 'subject': None, 'ledger_terms': None, 'journal': None}
    cap['_live'] = live
    with service.lock:
        terms_note = getattr(service.terms, 'note', None) or {}
        cap['notes'] = {
            'cure_quote': binding['note_sha256'],
            'financial_terms': terms_note.get('note_sha256'),
            'repayment_posting': read_note(note_path(overlay.REPAYMENT_NOTE)).get('note_sha256'),
        }
        try:
            state = overlay.fold(service.overlay_entries)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            cap['invalid'].append('OVERLAY_FOLD_UNREADABLE')
            return cap
        live['state'] = state
        journal = service.machine.export_journal()
        live['journal'] = journal
        cap['sim_day'] = state['sim_day']
        cap['terms_version'] = (
            state['terms_binding']['terms_version'] if state['terms_binding'] is not None
            else getattr(service.terms, 'version', None))
        subject, reason = _margin_subject(service, advance_id)
        try:
            plain = next((item for item in service._overlay_subjects(service.overlay_entries)
                          if item['advance_id'] == advance_id), None)
        except ApiError:
            cap['invalid'].append('SUBJECTS_NOT_BOUND')
            return cap
        if plain is None:
            cap['invalid'].append('ADVANCE_NOT_DRAWN')
            return cap
        cap['phase'] = plain['case'].get('phase')
        cap['terminal'] = (plain['case'].get('phase') != margin.DRAWN
                           or recovery.anchor(state, advance_id) is not None)
        record = state.get('margin', {}).get('advances', {}).get(advance_id)
        cap['record'] = copy.deepcopy(record)
        if subject is None:
            cap['missing'].append('margin_terms')
        else:
            live['subject'] = subject
            cap['tier'] = subject['margin'].get('tier')
            cap['measured'] = margin.measure(subject)
            if cap['measured'] is None:
                cap['invalid'].append('MARGIN_MEASURE_UNUSABLE')
        ledger_terms = service._ledger_terms(plain)
        denominator = None if ledger_terms is None else ledger_terms['denominator']
        if denominator is None:
            denominator = getattr(service.terms, 'ledger_denominator', lambda: None)()
        if type(denominator) is not int or denominator <= 0:
            cap['missing'].append('ledger_denominator')
        else:
            live['ledger_terms'] = ledger_terms
            witness, default_due, interest_due, held = overlay.repayment_position(
                state, advance_id, denominator)
            cap['dues'] = {'default_interest_due_krw': default_due,
                           'interest_due_krw': interest_due,
                           'unapplied_cash_krw': held,
                           'witness': dict(witness)}
        if service.repayment_bounds is None:
            cap['missing'].append('repayment_bounds')
        if service.overlay_bounds is None:
            cap['missing'].append('overlay_bounds')
        if not callable(getattr(service.terms, 'allocate', None)):
            cap['missing'].append('allocator')
        material = {'format': FORMAT, 'advance_id': advance_id,
                    'sim_day': state['sim_day'], 'margin_record': cap['record'],
                    'measured': cap['measured'], 'dues': cap['dues'],
                    'phase': cap['phase'], 'terminal': cap['terminal'],
                    'tier': cap['tier'], 'terms_version': cap['terms_version'],
                    'terms_binding': copy.deepcopy(state['terms_binding']),
                    'journal': {'length': len(journal), 'state_digest': service.machine.state_digest()},
                    'overlay': {'entry_count': state['entry_count'],
                                'digest': overlay.state_digest(state)},
                    'producer': cap['producer'], 'notes': cap['notes'],
                    'repayment_bounds': service.repayment_bounds,
                    'version': __version__}
        cap['input'] = material
        cap['input_digest'] = _sha({'format': FORMAT, 'kind': 'quote-inputs', 'material': material})
    return cap


def classify(cap):
    """The §3.4/§3.6 outcome token of a captured state. Pure."""
    if cap.get('invalid'):
        return 'INVALID_INPUT'
    if cap.get('terminal'):
        return 'TERMINAL_CASE'
    record = cap.get('record')
    if type(record) is dict and record.get('status') == margin.ACCELERATED:
        return 'ALREADY_ACCELERATED'
    if cap.get('missing'):
        return 'NOT_BOUND'
    if record is None or record.get('status') != margin.CALLED:
        return 'NO_ACTIVE_MARGIN_CALL'
    sim_day, deadline = cap.get('sim_day'), record.get('cure_deadline')
    if type(sim_day) is not int or type(deadline) is not int:
        return 'INVALID_INPUT'
    if sim_day > deadline:
        return 'WINDOW_EXPIRED'
    measured = cap.get('measured')
    if measured is None or type(measured.get('outstanding_krw')) is not int \
            or type(measured.get('base_krw')) is not int:
        return 'INVALID_INPUT'
    if not measured['breach']:
        return 'NO_REDUCTION_REQUIRED'
    return 'AT_DEADLINE' if sim_day == deadline else 'QUOTED'


def evaluate(cap, allocator=None):
    """The §3.2 amounts of a captured state. Pure; None when inputs are missing."""
    measured, dues = cap.get('measured'), cap.get('dues')
    if measured is None or dues is None:
        return None
    principal, base = measured['outstanding_krw'], measured['base_krw']
    interest_due, default_due = dues['interest_due_krw'], dues['default_interest_due_krw']
    held = dues['unapplied_cash_krw']
    interest = interest_due + default_due
    reduction = max(0, principal - base) if measured['breach'] else 0
    if reduction > 0:
        gross = interest + reduction
        applied = min(held, gross)
        new_cash = gross - applied
    else:
        gross = applied = new_cash = 0
    amounts = {'required_principal_reduction_krw': reduction,
               'posted_interest_due_krw': interest,
               'interest_due_krw': interest_due,
               'default_interest_due_krw': default_due,
               'gross_repayment_resources_krw': gross,
               'eligible_held_cash_krw': held,
               'held_cash_applied_krw': applied,
               'minimum_new_cash_krw': new_cash,
               'outstanding_principal_krw': principal,
               'base_krw': base,
               'eligible_face_krw': measured['eligible_face_krw']}
    result = {'amounts': amounts, 'allocation_projection': None, 'allocation_supported': None}
    if reduction > 0 and allocator is not None:
        split = allocator(principal, interest_due=interest_due,
                          default_interest_due=default_due, cash=new_cash + held)
        projection = None
        if type(split) is dict and split.get('status') == 'BOUND':
            projection = {'split': {key: split[key] for key in
                                    ('to_default_interest', 'to_interest', 'to_principal', 'unapplied_cash')},
                          'cash_projected_krw': new_cash + held}
        result['allocation_projection'] = projection
        result['allocation_supported'] = (projection is not None
                                          and split['to_default_interest'] == default_due
                                          and split['to_interest'] == interest_due
                                          and split['to_principal'] >= reduction)
    return result


def disposable_copy(service):
    """A restored-service copy: same fixtures, fresh machine, deep-copied state."""
    producer = service.producer.restored(service.machine.export_journal())
    twin = CapitalService(producer=producer, authorizer=service.authorizer, signer=service.signer,
                          terms=service.terms, policy=service.policy, underwriting=service.underwriting,
                          setoff=service.setoff, decisions=service.decision_index,
                          overlay_bounds=service.overlay_bounds, repayment_bounds=service.repayment_bounds)
    twin.overlay_entries = copy.deepcopy(service.overlay_entries)
    twin.receipts = copy.deepcopy(service.receipts)
    twin.case_fixtures = copy.deepcopy(service.case_fixtures)
    twin.workspace_status = service.workspace_status
    return twin


def _post_on_copy(service, advance_id, sim_day, amount, operation_id):
    twin = disposable_copy(service)
    try:
        receipt = twin.overlay_command({
            'instance_id': twin.instance_id, 'operation_id': operation_id,
            'op': overlay.COMMAND_REPAY, 'advance_ref': advance_id,
            'at_sim_day': sim_day, 'amount_krw': amount}, role='organizer')
    except ApiError as exc:
        return {'twin': twin, 'error': {'code': exc.code, 'detail': exc.detail}}
    return {'twin': twin, 'receipt': receipt}


def _measure_on(service, advance_id):
    subject, _reason = _margin_subject(service, advance_id)
    return None if subject is None else margin.measure(subject)


def _cure_plan(service, advance_id):
    """Pure plan_cures on the current state: would the next tick record a cure?"""
    subject, _reason = _margin_subject(service, advance_id)
    if subject is None:
        return None
    state = overlay.fold(service.overlay_entries)
    return bool(margin.plan_cures(state, [subject], operation_id=_CURE_PROBE,
                                  journal_length=len(service.machine.export_journal()),
                                  day=state['sim_day']))


def _witnesses(service, cap, amounts):
    """Apply the quote on disposable copies; never on the source service."""
    sim_day, advance_id = cap['sim_day'], cap['advance_id']
    new_cash = amounts['minimum_new_cash_krw']
    report = {'scope': margin.SOURCE_DISPOSABLE,
              'cure_would_record': {'at_snapshot': _cure_plan(service, advance_id), 'after_quote': None},
              'sufficiency': None, 'minimality': {'attempted': False, 'result': 'NOT_EXPRESSIBLE_ZERO_MINIMUM',
                                                'minimum_confirmed': None}}
    posted = _post_on_copy(service, advance_id, sim_day, new_cash, _WITNESS_CURE)
    if 'error' in posted:
        report['sufficiency'] = {'attempted': True, 'operation_id': _WITNESS_CURE,
                                 'result': 'COMMAND_REFUSED', 'error': posted['error']}
        admissibility = {'status': 'REFUSED', 'reason': posted['error']['code'], 'detail': posted['error']['detail']}
        return report, admissibility, None
    after = _measure_on(posted['twin'], advance_id)
    base_unchanged = (after is not None and cap['measured'] is not None
                      and after['eligible_face_krw'] == cap['measured']['eligible_face_krw'])
    coverage = after is not None and not after['breach']
    report['sufficiency'] = {'attempted': True, 'operation_id': _WITNESS_CURE,
                             'receipt': strip_volatile(posted['receipt']), 'predicate': after,
                             'result': 'COVERAGE_SATISFIED' if coverage and base_unchanged else 'COVERAGE_NOT_SATISFIED'}
    report['cure_would_record']['after_quote'] = _cure_plan(posted['twin'], advance_id)
    if not base_unchanged:
        return report, None, 'UNSUPPORTED_CALCULATION'
    admissibility = {'status': 'ADMISSIBLE_AT_SNAPSHOT', 'reason': None}
    if new_cash > 0:
        probe = _post_on_copy(service, advance_id, sim_day, new_cash - 1, _WITNESS_MINUS)
        if 'error' in probe:
            report['minimality'] = {'attempted': True, 'operation_id': _WITNESS_MINUS,
                                    'result': 'COMMAND_REFUSED', 'error': probe['error'],
                                    'minimum_confirmed': True}
        else:
            probe_measure = _measure_on(probe['twin'], advance_id)
            still = probe_measure is not None and probe_measure['breach']
            report['minimality'] = {'attempted': True, 'operation_id': _WITNESS_MINUS,
                                    'receipt': strip_volatile(probe['receipt']), 'predicate': probe_measure,
                                    'result': 'STILL_BREACHED' if still else 'ALSO_SATISFIED',
                                    'minimum_confirmed': still}
    return report, admissibility, None


def _report(cap, outcome):
    record = cap.get('record')
    return {'format': FORMAT, 'label': _LABEL, 'mode': _MODE, 'provisional': True,
            'advisory': True, 'executionAuthorized': False, 'funds_executed': False,
            'decision_id': DECISION_ID, 'advance_id': cap['advance_id'], 'outcome': outcome,
            'reasons': list(cap.get('missing', ())) + list(cap.get('invalid', ())),
            'sim_day': cap.get('sim_day'),
            'cure_deadline': None if record is None else record.get('cure_deadline'),
            'tier': cap.get('tier'), 'terms_version': cap.get('terms_version'),
            'margin_record': record,
            'recorded_cure': None if record is None else record.get('status'),
            'amounts': None, 'arithmetic_sufficient': None,
            'allocation_projection': None,
            'command_admissibility': {'status': 'UNKNOWN', 'reason': 'NOT_EVALUATED'},
            'monotonicity': None, 'witnesses': None,
            'notes': cap.get('notes'), 'producer': cap.get('producer'),
            'input_digest': cap.get('input_digest'),
            'stale_check': 'RECAPTURE_COMPARE_AND_RUN_EXISTING_GUARDS',
            'version': __version__}


def quote(service, advance_id, *, note=None):
    """The full minimum-cure quote. Never mutates the source service."""
    cap = capture(service, advance_id, note=note)
    outcome = classify(cap)
    report = _report(cap, outcome)
    if outcome in ('QUOTED', 'AT_DEADLINE', 'NO_REDUCTION_REQUIRED'):
        ev = evaluate(cap, getattr(service.terms, 'allocate', None))
        if ev is None:
            report['outcome'] = 'INVALID_INPUT'
        elif outcome != 'NO_REDUCTION_REQUIRED' and not cap['producer']['supported']:
            report['outcome'] = 'UNSUPPORTED_PRODUCER'
        else:
            report['amounts'] = ev['amounts']
            report['allocation_projection'] = ev['allocation_projection']
            report['monotonicity'] = _MONOTONIC
            if ev['allocation_supported'] is False:
                report['outcome'] = 'UNSUPPORTED_CALCULATION'
                report['amounts'] = None
            elif outcome == 'NO_REDUCTION_REQUIRED':
                report['arithmetic_sufficient'] = True
                report['command_admissibility'] = {'status': 'UNKNOWN',
                                                   'reason': 'NO_COMMAND_FOR_ZERO_QUOTE'}
                report['witnesses'] = {
                    'scope': margin.SOURCE_DISPOSABLE,
                    'cure_would_record': {'at_snapshot': _cure_plan(service, advance_id),
                                          'after_quote': None},
                    'sufficiency': {'attempted': False, 'result': 'PREDICATE_ALREADY_SATISFIED'},
                    'minimality': {'attempted': False, 'result': 'NOT_EXPRESSIBLE_ZERO_MINIMUM',
                                   'minimum_confirmed': None}}
            else:
                witnesses, admissibility, unsupported = _witnesses(service, cap, ev['amounts'])
                report['witnesses'] = witnesses
                if unsupported is not None:
                    report['outcome'] = unsupported
                    report['amounts'] = None
                    report['arithmetic_sufficient'] = None
                    report['command_admissibility'] = {'status': 'UNKNOWN', 'reason': 'UNSUPPORTED_CALCULATION'}
                else:
                    report['arithmetic_sufficient'] = (
                        witnesses['sufficiency']['result'] == 'COVERAGE_SATISFIED'
                        or ev['allocation_supported'] is True)
                    report['command_admissibility'] = admissibility
    report['quote_digest'] = _sha({'format': FORMAT, 'kind': 'quote',
                                   'body': {key: value for key, value in report.items()
                                            if key != 'quote_digest'}})
    return report


def is_stale(service, quoted, *, note=None):
    """True when the captured inputs changed since `quoted` was produced."""
    if type(quoted) is not dict or quoted.get('format') != FORMAT \
            or type(quoted.get('advance_id')) is not str:
        return True
    return capture(service, quoted['advance_id'], note=note)['input_digest'] != quoted.get('input_digest')


# ---------------------------------------------------------------- bounded scenarios

def _run(service, op, advance, key, **args):
    receipt = service.execute({'instance_id': service.instance_id, 'operation_id': key,
                               'op': op, 'advance_id': advance, 'args': args})
    if receipt.get('outcome') != 'ACCEPTED':
        raise QuoteError(f'{op} rejected in scenario: {receipt.get("error")}')
    return receipt


def _draw(service, fixture, amount, *, bind=True, advance='sim-a', prefix='cq'):
    _run(service, 'offer', advance, f'{prefix}-offer', fixture_id=fixture, amount=amount)
    _run(service, 'approve', advance, f'{prefix}-approve')
    if bind:
        _run(service, 'bind_settlement', advance, f'{prefix}-bind')
    _run(service, 'draw', advance, f'{prefix}-draw')


def _tick(service, key, start, end):
    receipt = service.overlay_command({'instance_id': service.instance_id, 'operation_id': key,
                                       'op': overlay.COMMAND_OP, 'from_sim_day': start,
                                       'to_sim_day': end, 'reason': 'cure quote scenario'},
                                      role='organizer')
    if receipt.get('outcome') not in ('APPLIED', 'ACCEPTED'):
        raise QuoteError(f'tick rejected in scenario: {receipt}')
    return receipt


def _pay(service, key, amount, advance='sim-a', day=None):
    day = overlay.fold(service.overlay_entries)['sim_day'] if day is None else day
    receipt = service.overlay_command({'instance_id': service.instance_id, 'operation_id': key,
                                       'op': overlay.COMMAND_REPAY, 'advance_ref': advance,
                                       'at_sim_day': day, 'amount_krw': amount}, role='organizer')
    if receipt.get('outcome') != 'APPLIED':
        raise QuoteError(f'post_repayment rejected in scenario: {receipt}')
    return receipt


def _disposable(**kwargs):
    source = margin.ScenarioReplaySource()
    return source, CapitalService(producer=PinnedFsmProducer(fixtures=source), **kwargs)


def _refund_steps(refund_id, amount):
    return [{'op': 'bind_refund',
             'args': {'refund_id': refund_id, 'amount': amount,
                      'beneficiary_role': 'fixture-buyer', 'reason': 'SYNTHETIC_SCENARIO'},
             'expected_error': None}]


def _breach_draw(service, fixture_id, gate, refund_amount, advance='sim-a'):
    """Draw one KRW above the base that a later refund replay leaves.

    The FSM refuses an offer on a claim with an open refund, so the refund is
    bound on the disposable book only after the draw; the amount is projected
    from the post-refund eligible face through the same margin terms.
    """
    claim = service.fixtures.view(fixture_id)['claim']
    case = {'phase': margin.DRAWN, 'beneficiary_role': service.fixtures.beneficiary(fixture_id)}
    terms = service.terms.margin_terms(case, claim, gate=gate, draw_day=0,
                                       refund_after_draw=margin.views_mutable(service.fixtures))
    if terms is None:
        raise QuoteError('margin terms not bound for scenario')
    eligible = margin.eligible_face({**claim, 'refund_face': refund_amount}, terms['payees'])
    if eligible is None:
        raise QuoteError('eligible face not bound for scenario')
    base = eligible * terms['advance_rate_bps'] // BPS_SCALE
    _draw(service, fixture_id, base + 1, bind=gate == 'MOCK_COMMIT_OBSERVED', advance=advance)


def _scenario_breach_tier1():
    source, service = _disposable()
    _breach_draw(service, 'sim-committed', 'MOCK_COMMIT_OBSERVED', 40_000)
    source.replay('sim-committed', 'partial-before')
    _tick(service, 'cq-tick-1', 0, 3)
    return service, 'sim-a'


def _scenario_breach_tier2_unbound():
    source, service = _disposable()
    _breach_draw(service, 'sim-pending', 'UNBOUND', 60_000)
    source.replay('sim-pending', 'cure-quote-refund', steps=_refund_steps('sim-cure-refund', 60_000))
    _tick(service, 'cq-tick-1', 0, 3)
    return service, 'sim-a'


def _scenario_at_deadline():
    service, advance = _scenario_breach_tier1()
    _tick(service, 'cq-tick-2', 3, 8)
    return service, advance


def _scenario_fractional_carry():
    source, service = _disposable()
    _breach_draw(service, 'sim-committed', 'MOCK_COMMIT_OBSERVED', 40_000)
    source.replay('sim-committed', 'partial-before')
    _tick(service, 'cq-tick-1', 0, 1)
    _tick(service, 'cq-tick-2', 1, 3)
    return service, 'sim-a'


def _scenario_zero_required_cash():
    service, advance = _scenario_breach_tier1()
    state = overlay.fold(service.overlay_entries)
    subject, _reason = _margin_subject(service, advance)
    measured = margin.measure(subject)
    terms = service._ledger_terms(subject)
    _w, default_due, interest_due, _held = overlay.repayment_position(state, advance, terms['denominator'])
    _pay(service, 'cq-pay-1', default_due + interest_due + measured['outstanding_krw'] - measured['base_krw'])
    return service, advance


def _scenario_missing_terms():
    source, service = _disposable(terms=DecisionNoteTermsPolicy(note_path('CAPITAL_TERMS_ABSENT.md')))
    _draw(service, 'sim-committed', 90_000)
    return service, 'sim-a'


def _scenario_capacity_refusal():
    bounds = dict(overlay.load_repayment_bounds(), amount_max_krw=1)
    source, service = _disposable(repayment_bounds=bounds)
    _breach_draw(service, 'sim-committed', 'MOCK_COMMIT_OBSERVED', 40_000)
    source.replay('sim-committed', 'partial-before')
    _tick(service, 'cq-tick-1', 0, 3)
    return service, 'sim-a'


def _scenario_already_accelerated():
    service, advance = _scenario_breach_tier1()
    _tick(service, 'cq-tick-2', 3, 9)
    return service, advance


def _scenario_no_call():
    source, service = _disposable()
    _draw(service, 'sim-committed', 80_000)
    _tick(service, 'cq-tick-1', 0, 3)
    return service, 'sim-a'


SCENARIOS = {
    'breach-tier1': _scenario_breach_tier1,
    'breach-tier2-unbound': _scenario_breach_tier2_unbound,
    'at-deadline': _scenario_at_deadline,
    'fractional-carry': _scenario_fractional_carry,
    'zero-required-cash': _scenario_zero_required_cash,
    'missing-terms': _scenario_missing_terms,
    'capacity-refusal': _scenario_capacity_refusal,
    'already-accelerated': _scenario_already_accelerated,
    'no-call': _scenario_no_call,
}


def _release(producer):
    close = getattr(producer, 'close', None)
    if callable(close):
        close()


def evaluate_scenario(scenario_id):
    """Build one bounded scenario and quote it. Returns the stripped report."""
    builder = SCENARIOS.get(scenario_id)
    if builder is None:
        raise QuoteError(f'unknown scenario {scenario_id}')
    service, advance_id = builder()
    try:
        return strip_volatile(quote(service, advance_id))
    finally:
        _release(service.producer)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--scenario', choices=sorted(SCENARIOS),
                       help='One bounded scenario id from --list')
    group.add_argument('--list', action='store_true', help='List the bounded scenario ids')
    args = parser.parse_args(argv)
    try:
        if args.list:
            out = {'format': FORMAT, 'label': _LABEL, 'mode': _MODE,
                   'scenarios': sorted(SCENARIOS)}
        elif args.scenario is not None:
            out = evaluate_scenario(args.scenario)
        else:
            out = {'format': FORMAT, 'label': _LABEL, 'mode': _MODE,
                   'scenarios': {name: evaluate_scenario(name) for name in sorted(SCENARIOS)}}
    except (ApiError, QuoteError, ValueError, KeyError, TypeError) as exc:
        print(f'cure quote failed: {exc}', file=sys.stderr)
        return 1
    sys.stdout.buffer.write(canonical_bytes(out) + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
