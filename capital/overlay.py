"""Overlay ledger: the sim_day clock, ACT/365 simple-interest memo postings and repayment postings.

SIMULATED memo ledger. Nothing here is a payment, a receivable or a bank record.
This module never writes the F04 journal and never gates the FSM: the overlay is a
separate append-only journal inside the one workspace envelope, and its authority
is the deterministic fold of its entries (docs/decisions/CAPITAL_OVERLAY_STATE.md).
Digest, clock and golden policy follow docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md.
A `repayment` entry records an operator-asserted payment and its split over the posted
dues (docs/decisions/CAPITAL_REPAYMENT_POSTING.md); the service, not this module, issues
the matching F04 repay in the same save.

Pure functions only. The fold reads no note and no wall clock: rates, day counts and
bounds are stamped into each entry by the writer, and replay folds what was recorded.
Every integer here is 0, 1 or 2; limits and rates come from the decision notes.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.resources
import re
from fractions import Fraction
from pathlib import Path

from capital.store import canonical_bytes, section_checksum
from capital.terms import read_decision_block

SCHEMA = 1
DOMAIN = 'KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1'
LABEL = 'SIMULATED'
CLOCK_SOURCE = 'SIM_LOGICAL_CLOCK'
ACTOR = 'LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED'
COMMAND_OP = 'advance_day'
COMMAND_REPAY = 'post_repayment'
BASIS = 'SIM_REPAY_MEMO'
PAYMENT_BASIS = 'UNVERIFIED_ASSERTED'
STATE_NOTE = 'CAPITAL_OVERLAY_STATE.md'
EXPORT_NOTE = 'CAPITAL_OVERLAY_DIGEST_EXPORT.md'
REPAYMENT_NOTE = 'CAPITAL_REPAYMENT_POSTING.md'

KIND_TERMS = 'terms_binding'
KIND_CLOCK = 'clock'
KIND_INTEREST = 'interest_posting'
KIND_REPAYMENT = 'repayment'
KIND_MARGIN_CALL = 'margin_call'
KIND_MARGIN_CURE = 'margin_cure'
KIND_MARGIN_ACCELERATION = 'margin_acceleration'
KIND_DEFAULT_PROPOSAL = 'default_eligible_proposal'
MARGIN_KINDS = (KIND_MARGIN_CALL, KIND_MARGIN_CURE, KIND_MARGIN_ACCELERATION, KIND_DEFAULT_PROPOSAL)
# entry kind -> the section of the decided storage shape it belongs to
SECTION_OF = {KIND_CLOCK: 'clock', KIND_INTEREST: 'interest_ledger', KIND_REPAYMENT: 'interest_ledger', KIND_TERMS: 'decision_records',
              **{kind: 'decision_records' for kind in MARGIN_KINDS}}
SECTIONS = ('clock', 'interest_ledger', 'recovery_ledger', 'decision_records', 'agent_proposals')
ENTRY_KEYS = frozenset({'overlay_id', 'after_journal_index', 'sim_day', 'kind', 'payload'})
BOUND_NAMES = ('OVERLAY_MAX_ENTRIES', 'OVERLAY_ENTRY_MAX_BYTES', 'SIM_DAY_MAX',
               'AGENT_PROPOSALS_MAX', 'DECISION_RECORDS_MAX', 'ENVELOPE_MAX_BYTES')

_PAYLOAD_TYPES = {
    KIND_TERMS: {'terms_version': str, 'status': str},
    KIND_CLOCK: {'from_sim_day': int, 'to_sim_day': int, 'reason': str, 'actor': str, 'clock_source': str},
    KIND_INTEREST: {
        'advance_id': str, 'tier': str, 'principal': int, 'draw_day': int, 'maturity_day': int,
        'from_day': int, 'to_day': int, 'contractual_days': int, 'default_days': int,
        'contract_bps': int, 'default_bps': int, 'terms_version': str,
        'cumulative_contract_exact': str, 'cumulative_default_exact': str,
        'posted_contract_krw': int, 'posted_default_krw': int,
    },
    KIND_MARGIN_CALL: {
        'advance_id': str, 'tier': str, 'outstanding_krw': int, 'eligible_face_krw': int,
        'advance_rate_bps': int, 'base_krw': int, 'cure_window_days': int, 'cure_deadline': int,
        'cure_option': str, 'maturity_day': int, 'terms_version': str,
    },
    KIND_MARGIN_CURE: {
        'advance_id': str, 'outstanding_krw': int, 'eligible_face_krw': int, 'base_krw': int,
        'cure_deadline': int, 'cure_option': str, 'terms_version': str,
    },
    KIND_MARGIN_ACCELERATION: {
        'advance_id': str, 'outstanding_krw': int, 'eligible_face_krw': int, 'base_krw': int,
        'cure_deadline': int, 'maturity_before': int, 'maturity_after': int, 'grace_days': int,
        'default_eligible_day': int, 'terms_version': str,
    },
    KIND_DEFAULT_PROPOSAL: {
        'advance_id': str, 'proposal_kind': str, 'authority': str, 'default_eligible_day': int,
        'outstanding_krw': int, 'terms_version': str,
    },
}
_EXACT = re.compile(r'\A(0|[1-9][0-9]*)/([1-9][0-9]*)\Z')
_DECIMAL = re.compile(r'\A(0|[1-9][0-9]*)\Z')
EVIDENCE_REF = re.compile(r'\A[A-Za-z0-9._:-]{1,64}\Z')
_ALLOCATION_KEYS = ('default_interest_krw', 'interest_krw', 'principal_krw', 'unapplied_after_krw')
_WITNESS_INTS = ('denominator', 'paid_interest_krw', 'paid_default_krw', 'principal_before_krw')
_WITNESS_NUMERATORS = ('accrued_interest_num', 'accrued_default_num')
_REPAYMENT_REQUIRED = frozenset({
    'advance_ref', 'amount_krw', 'unapplied_before_krw', 'allocation', 'witness', 'terms_binding',
    'f04_operation_id', 'f04_receipt_ref', 'label', 'basis'})
_REPAYMENT_OPTIONAL = frozenset({'evidence_ref', 'proposal_id'})
_NO_PAYMENTS = {'paid_default_krw': 0, 'paid_interest_krw': 0, 'principal_krw': 0,
                'unapplied_cash_krw': 0, 'postings': 0}


class OverlayError(ValueError):
    """The overlay journal, its fold or its digest is not trustworthy. Fail closed."""


def _int(value):
    return type(value) is int and value >= 0


def exact_text(value):
    return f'{value.numerator}/{value.denominator}'


def parse_exact(text):
    match = _EXACT.fullmatch(text) if type(text) is str else None
    if match is None:
        raise OverlayError('exact fraction')
    value = Fraction(int(match.group(1)), int(match.group(2)))
    if exact_text(value) != text:
        raise OverlayError('exact fraction not reduced')
    return value


def floor(value):
    return value.numerator // value.denominator


# ---------------------------------------------------------------- bounds

def default_note_path(name):
    """Checkout path of a decision note, located through the package, never __file__."""
    return Path(str(importlib.resources.files('capital'))).parent / 'docs' / 'decisions' / name


def _adopted(block, name):
    entry = (block or {}).get('entries', {}).get(name) if type((block or {}).get('entries')) is dict else None
    if type(entry) is not dict or entry.get('status') != 'ADOPTED' or entry.get('provisional') is not True:
        return None
    return entry.get('value') if type(entry.get('value')) is dict else None


def load_bounds(state_note=None, export_note=None):
    """Bounds and the clock step, read from the ADOPTED entries. None means NOT_BOUND."""
    state = read_decision_block(default_note_path(STATE_NOTE) if state_note is None else state_note)
    export = read_decision_block(default_note_path(EXPORT_NOTE) if export_note is None else export_note)
    capacity = _adopted(state, 'overlay_capacity_bounds')
    clock = _adopted(export, 'clock_command_authority')
    if capacity is None or clock is None:
        return None
    bounds = {}
    for name in BOUND_NAMES:
        value = capacity.get(name)
        if type(value) is not int or value < 1:
            return None
        bounds[name] = value
    step = clock.get('max_step_days')
    if type(step) is not int or step < 1:
        return None
    bounds['max_step_days'] = step
    return bounds


REPAYMENT_BOUND_NAMES = ('amount_max_krw', 'entries_per_advance_max', 'entry_canonical_bytes_max',
                         'unapplied_max_krw_per_advance')


def load_repayment_bounds(note=None):
    """Repayment posting bounds, read from the ADOPTED entries of the note. None means NOT_BOUND."""
    block = read_decision_block(default_note_path(REPAYMENT_NOTE) if note is None else note)
    capacity = _adopted(block, 'capacity_and_envelope_effect')
    unapplied = _adopted(block, 'unapplied_cash_handling')
    if capacity is None or unapplied is None:
        return None
    bounds = {}
    for name in REPAYMENT_BOUND_NAMES:
        value = capacity.get(name)
        if type(value) is not int or value < 1:
            return None
        bounds[name] = value
    if unapplied.get('max_krw_per_advance') != bounds['unapplied_max_krw_per_advance']:
        return None
    return bounds


# ---------------------------------------------------------------- fold

def empty_state():
    return {
        'sim_day': 0,
        'clock_source': CLOCK_SOURCE,
        'terms_binding': None,
        'advances': {},
        'sections': {name: [] for name in SECTIONS},
        'entry_count': 0,
        'last_after_journal_index': 0,
    }


def validate_entry(entry):
    """Exact shape of one entry. Raises OverlayError."""
    if type(entry) is not dict or set(entry) != ENTRY_KEYS:
        raise OverlayError('entry keys')
    if type(entry['overlay_id']) is not str or not entry['overlay_id']:
        raise OverlayError('overlay_id')
    if not _int(entry['after_journal_index']) or not _int(entry['sim_day']):
        raise OverlayError('entry index')
    from capital import recovery
    if entry['kind'] in recovery.KINDS:
        recovery.validate_entry(entry)
        return
    if entry['kind'] == KIND_REPAYMENT:
        _validate_repayment(entry['payload'])
        return
    shape = _PAYLOAD_TYPES.get(entry['kind']) if type(entry['kind']) is str else None
    payload = entry['payload']
    if entry['kind'] == KIND_INTEREST and type(payload) is dict and 'recovery_witness' in payload:
        shape = {**shape, 'recovery_witness': dict}
    if entry['kind'] == KIND_CLOCK and type(payload) is dict and 'tick_directive' in payload:
        shape = {**shape, 'tick_directive': dict}
    if shape is None or type(payload) is not dict or set(payload) != set(shape):
        raise OverlayError('payload keys')
    for key, kind in shape.items():
        value = payload[key]
        if type(value) is not kind or (kind is int and value < 0) or (kind is str and not value):
            raise OverlayError(f'payload {key}')


def _decimal(text):
    match = _DECIMAL.fullmatch(text) if type(text) is str else None
    if match is None:
        raise OverlayError('decimal string')
    return int(text)


def _flat_ints(block, keys):
    if type(block) is not dict or set(block) != set(keys) or not all(_int(block[key]) for key in keys):
        raise OverlayError('repayment integers')


def _validate_repayment(payload):
    """Exact shape of a repayment payload: optional citations, nested blocks, nullable F04 refs."""
    if type(payload) is not dict or not _REPAYMENT_REQUIRED <= set(payload) <= _REPAYMENT_REQUIRED | _REPAYMENT_OPTIONAL:
        raise OverlayError('payload keys')
    if type(payload['advance_ref']) is not str or not payload['advance_ref']:
        raise OverlayError('payload advance_ref')
    if not _int(payload['amount_krw']) or not _int(payload['unapplied_before_krw']):
        raise OverlayError('payload amounts')
    _flat_ints(payload['allocation'], _ALLOCATION_KEYS)
    witness = payload['witness']
    if type(witness) is not dict or set(witness) != set(_WITNESS_INTS) | set(_WITNESS_NUMERATORS):
        raise OverlayError('witness keys')
    _flat_ints({key: witness[key] for key in _WITNESS_INTS}, _WITNESS_INTS)
    for key in _WITNESS_NUMERATORS:
        _decimal(witness[key])
    binding = payload['terms_binding']
    if type(binding) is not dict or set(binding) != {'terms_version'} or type(binding['terms_version']) is not str \
            or not binding['terms_version']:
        raise OverlayError('payload terms_binding')
    for key in ('f04_operation_id', 'f04_receipt_ref'):
        if payload[key] is not None and (type(payload[key]) is not str or not payload[key]):
            raise OverlayError(f'payload {key}')
    if 'evidence_ref' in payload and (type(payload['evidence_ref']) is not str
                                      or EVIDENCE_REF.fullmatch(payload['evidence_ref']) is None):
        raise OverlayError('payload evidence_ref')
    if 'proposal_id' in payload and (type(payload['proposal_id']) is not str or not payload['proposal_id']):
        raise OverlayError('payload proposal_id')
    if payload['label'] != LABEL or payload['basis'] != BASIS:
        raise OverlayError('repayment labels')


def _fold_terms(state, entry):
    payload = entry['payload']
    if state['terms_binding'] is not None:
        raise OverlayError('terms already bound')
    state['terms_binding'] = {'terms_version': payload['terms_version'], 'status': payload['status'],
                              'sim_day': entry['sim_day']}
    state['sections']['decision_records'].append({
        'overlay_id': entry['overlay_id'], 'record': 'TERMS_BINDING',
        'terms_version': payload['terms_version'], 'status': payload['status'],
        'sim_day': entry['sim_day']})


def _fold_clock(state, entry):
    payload = entry['payload']
    if payload['from_sim_day'] != state['sim_day'] or payload['to_sim_day'] <= payload['from_sim_day']:
        raise OverlayError('clock not advancing from the folded day')
    if entry['sim_day'] != payload['to_sim_day']:
        raise OverlayError('clock entry day')
    if payload['actor'] != ACTOR or payload['clock_source'] != CLOCK_SOURCE:
        raise OverlayError('clock labels')
    state['sim_day'] = payload['to_sim_day']
    state['sections']['clock'].append({
        'overlay_id': entry['overlay_id'], 'from_sim_day': payload['from_sim_day'],
        'to_sim_day': payload['to_sim_day'], 'after_journal_index': entry['after_journal_index']})


def _fold_interest(state, entry):
    payload = entry['payload']
    binding = state['terms_binding']
    if binding is None or payload['terms_version'] != binding['terms_version']:
        raise OverlayError('posting without matching terms binding')
    if entry['sim_day'] != state['sim_day'] or payload['to_day'] > entry['sim_day']:
        raise OverlayError('posting day')
    if payload['from_day'] >= payload['to_day'] or payload['from_day'] < payload['draw_day']:
        raise OverlayError('posting span')
    advance_id = payload['advance_id']
    prior = state['advances'].get(advance_id)
    cum_contract = parse_exact(payload['cumulative_contract_exact'])
    cum_default = parse_exact(payload['cumulative_default_exact'])
    if prior is None:
        before = {'cc': Fraction(0), 'cd': Fraction(0), 'pc': 0, 'pd': 0, 'last': payload['draw_day']}
    else:
        before = {'cc': parse_exact(prior['cumulative_contract_exact']),
                  'cd': parse_exact(prior['cumulative_default_exact']),
                  'pc': prior['posted_contract_krw'], 'pd': prior['posted_default_krw'],
                  'last': prior['last_accrued_day']}
        if (prior['tier'], prior['draw_day'], prior['contract_bps'], prior['default_bps']) != (
                payload['tier'], payload['draw_day'], payload['contract_bps'], payload['default_bps']):
            raise OverlayError('advance terms changed')
    if payload['from_day'] < before['last'] or cum_contract < before['cc'] or cum_default < before['cd']:
        raise OverlayError('accrual went backwards')
    if 'recovery_witness' in payload:
        witness = payload['recovery_witness']
        if (set(witness) != {'policy_version', 'denominator', 'stop_day'}
                or witness['policy_version'] != 'DEFAULT_RECOVERY_V1'
                or type(witness['denominator']) is not int or witness['denominator'] <= 0):
            raise OverlayError('recovery accrual witness')
        if witness['stop_day'] is not None and payload['to_day'] > witness['stop_day']:
            raise OverlayError('accrual after stop day')
        contractual = max(0, min(payload['to_day'], payload['maturity_day']) - min(payload['from_day'], payload['maturity_day']))
        default = payload['to_day'] - payload['from_day'] - contractual
        if (payload['contractual_days'], payload['default_days']) != (contractual, default):
            raise OverlayError('recovery accrual day split')
        if (cum_contract != before['cc'] + Fraction(payload['principal'] * contractual * payload['contract_bps'], witness['denominator'])
                or cum_default != before['cd'] + Fraction(payload['principal'] * default * payload['default_bps'], witness['denominator'])):
            raise OverlayError('recovery exact accrual')
    # The remainder carries: what has been posted is always exactly the floor of the cumulative exact.
    if before['pc'] + payload['posted_contract_krw'] != floor(cum_contract):
        raise OverlayError('contract posting is not the cumulative floor')
    if before['pd'] + payload['posted_default_krw'] != floor(cum_default):
        raise OverlayError('default posting is not the cumulative floor')
    state['advances'][advance_id] = {
        'tier': payload['tier'], 'draw_day': payload['draw_day'], 'maturity_day': payload['maturity_day'],
        'contract_bps': payload['contract_bps'], 'default_bps': payload['default_bps'],
        'principal': payload['principal'], 'last_accrued_day': payload['to_day'],
        'cumulative_contract_exact': payload['cumulative_contract_exact'],
        'cumulative_default_exact': payload['cumulative_default_exact'],
        'posted_contract_krw': floor(cum_contract), 'posted_default_krw': floor(cum_default),
    }
    state['sections']['interest_ledger'].append({
        'overlay_id': entry['overlay_id'], 'advance_id': advance_id,
        'from_day': payload['from_day'], 'to_day': payload['to_day'],
        'contractual_days': payload['contractual_days'], 'default_days': payload['default_days'],
        'posted_contract_krw': payload['posted_contract_krw'],
        'posted_default_krw': payload['posted_default_krw']})


def _numerator(value, denominator):
    scaled = value * denominator
    if scaled.denominator != 1:
        raise OverlayError('accrual is not an integer numerator over the denominator')
    return scaled.numerator


def _payments(state, advance_ref):
    return state.get('repayment', {}).get('advances', {}).get(advance_ref, _NO_PAYMENTS)


def repayment_position(state, advance_ref, denominator):
    """(witness without the F04 principal, default due, interest due, held cash) of one advance.

    The numerators are the cumulative exact accrual times the denominator; a due is the floor of
    its numerator over the denominator minus what is already paid, so a sub-won carry is derived
    and never lost. Pure: the writer stamps this, the fold recomputes it.
    """
    if not denominator:
        raise OverlayError('denominator')
    record = state['advances'].get(advance_ref)
    paid = _payments(state, advance_ref)
    numerators = {}
    for key, source in (('accrued_interest_num', 'cumulative_contract_exact'),
                        ('accrued_default_num', 'cumulative_default_exact')):
        numerators[key] = _numerator(parse_exact(record[source]) if record else Fraction(0), denominator)
    witness = {'denominator': denominator,
               'accrued_interest_num': str(numerators['accrued_interest_num']),
               'accrued_default_num': str(numerators['accrued_default_num']),
               'paid_interest_krw': paid['paid_interest_krw'], 'paid_default_krw': paid['paid_default_krw']}
    default_due = numerators['accrued_default_num'] // denominator - paid['paid_default_krw']
    interest_due = numerators['accrued_interest_num'] // denominator - paid['paid_interest_krw']
    return witness, default_due, interest_due, paid['unapplied_cash_krw']


def _fold_repayment(state, entry):
    payload = entry['payload']
    binding = state['terms_binding']
    if binding is None or payload['terms_binding']['terms_version'] != binding['terms_version']:
        raise OverlayError('repayment without matching terms binding')
    if entry['sim_day'] != state['sim_day']:
        raise OverlayError('repayment day')
    ref, split, stamped = payload['advance_ref'], payload['allocation'], payload['witness']
    if ref in state.get('default_anchors', {}):
        raise OverlayError('anchored default requires recovery ledger')
    witness, default_due, interest_due, held = repayment_position(state, ref, stamped['denominator'])
    if {key: stamped[key] for key in witness} != witness:
        raise OverlayError('repayment witness does not match the folded accrual and payments')
    if payload['unapplied_before_krw'] != held:
        raise OverlayError('repayment unapplied_before')
    if split['default_interest_krw'] > default_due or split['interest_krw'] > interest_due \
            or split['principal_krw'] > stamped['principal_before_krw']:
        raise OverlayError('repayment allocation exceeds a due')
    applied = split['default_interest_krw'] + split['interest_krw'] + split['principal_krw']
    if payload['amount_krw'] + held != applied + split['unapplied_after_krw']:
        raise OverlayError('repayment allocation invariant')
    if split['unapplied_after_krw'] and (split['default_interest_krw'] != default_due or split['interest_krw'] != interest_due
                                         or split['principal_krw'] != stamped['principal_before_krw']):
        raise OverlayError('cash held while a bucket is still due')
    refs = (payload['f04_operation_id'], payload['f04_receipt_ref'])
    if (split['principal_krw'] > 0) != (refs[0] is not None) or (refs[0] is None) != (refs[1] is None):
        raise OverlayError('repayment F04 reference')
    paid = _payments(state, ref)
    state.setdefault('repayment', {'advances': {}, 'close_gate': None})['advances'][ref] = {
        'paid_default_krw': paid['paid_default_krw'] + split['default_interest_krw'],
        'paid_interest_krw': paid['paid_interest_krw'] + split['interest_krw'],
        'principal_krw': paid['principal_krw'] + split['principal_krw'],
        'unapplied_cash_krw': split['unapplied_after_krw'],
        'postings': paid['postings'] + 1}
    state['sections']['interest_ledger'].append({
        'overlay_id': entry['overlay_id'], 'record': 'REPAYMENT', 'advance_id': ref,
        'sim_day': entry['sim_day'], 'amount_krw': payload['amount_krw'], **split})


def _gate(default_due, interest_due, held):
    status = 'INTEREST_DUE' if default_due + interest_due else ('UNAPPLIED_HELD' if held else 'CLEAR')
    return {'status': status, 'default_interest_due_krw': default_due, 'interest_due_krw': interest_due,
            'unapplied_cash_krw': held}


def advance_gate(state, advance_ref):
    """Advisory close_gate of one advance. Never rejects a close (close_gate_enforcement)."""
    record = state['advances'].get(advance_ref)
    paid = _payments(state, advance_ref)
    return _gate((record['posted_default_krw'] if record else 0) - paid['paid_default_krw'],
                 (record['posted_contract_krw'] if record else 0) - paid['paid_interest_krw'],
                 paid['unapplied_cash_krw'])


def close_gates(state):
    """Aggregate close_gate over every advance the overlay knows."""
    ids = set(state['advances']) | set(state.get('repayment', {}).get('advances', {}))
    gates = [advance_gate(state, advance_ref) for advance_ref in sorted(ids)]
    return _gate(sum(gate['default_interest_due_krw'] for gate in gates),
                 sum(gate['interest_due_krw'] for gate in gates),
                 sum(gate['unapplied_cash_krw'] for gate in gates))


def _margin_record(state, entry, *, expect):
    """The folded record of the entry's advance, after the checks every margin entry shares."""
    payload = entry['payload']
    binding = state['terms_binding']
    if binding is None or payload['terms_version'] != binding['terms_version']:
        raise OverlayError('margin entry without matching terms binding')
    if entry['sim_day'] != state['sim_day']:
        raise OverlayError('margin entry day')
    record = state.get('margin', {}).get('advances', {}).get(payload['advance_id'])
    status = None if record is None else record['status']
    if status not in expect:
        raise OverlayError('margin entry out of order')
    return record


def _margin_event(state, entry, name, fields):
    payload = entry['payload']
    state['sections']['decision_records'].append({
        'overlay_id': entry['overlay_id'], 'record': name, 'advance_id': payload['advance_id'],
        'sim_day': entry['sim_day'], **{key: payload[key] for key in fields}})


def _margin_set(state, advance_id, record):
    state.setdefault('margin', {'advances': {}})['advances'][advance_id] = record


def _fold_margin_call(state, entry):
    payload = entry['payload']
    _margin_record(state, entry, expect=(None, 'CURED'))
    if payload['outstanding_krw'] <= payload['base_krw'] or payload['cure_window_days'] < 1:
        raise OverlayError('margin call without a breach')
    if payload['cure_deadline'] != entry['sim_day'] + payload['cure_window_days']:
        raise OverlayError('cure deadline')
    _margin_set(state, payload['advance_id'], {
        'status': 'CALLED', 'call_day': entry['sim_day'], 'cure_deadline': payload['cure_deadline'],
        'maturity_day': payload['maturity_day'], 'default_eligible_day': None, 'proposal_day': None,
        'calls': 1 + state.get('margin', {}).get('advances', {}).get(payload['advance_id'], {}).get('calls', 0)})
    _margin_event(state, entry, 'MARGIN_CALL', ('outstanding_krw', 'base_krw', 'cure_deadline'))


def _fold_margin_cure(state, entry):
    payload = entry['payload']
    record = _margin_record(state, entry, expect=('CALLED',))
    if entry['sim_day'] > record['cure_deadline'] or payload['cure_deadline'] != record['cure_deadline']:
        raise OverlayError('cure after the deadline')
    if payload['outstanding_krw'] > payload['base_krw']:
        raise OverlayError('cure without being back within the base')
    _margin_set(state, payload['advance_id'], {**record, 'status': 'CURED'})
    _margin_event(state, entry, 'MARGIN_CURE', ('outstanding_krw', 'base_krw', 'cure_option'))


def _fold_margin_acceleration(state, entry):
    payload = entry['payload']
    record = _margin_record(state, entry, expect=('CALLED',))
    if entry['sim_day'] <= record['cure_deadline'] or payload['cure_deadline'] != record['cure_deadline']:
        raise OverlayError('acceleration before the cure deadline')
    if payload['outstanding_krw'] <= payload['base_krw']:
        raise OverlayError('acceleration without a breach')
    if (payload['maturity_before'] != record['maturity_day']
            or payload['maturity_after'] != min(record['maturity_day'], record['cure_deadline'])
            or payload['default_eligible_day'] != payload['maturity_after'] + payload['grace_days'] + 1):
        raise OverlayError('acceleration figures')
    _margin_set(state, payload['advance_id'], {
        **record, 'status': 'ACCELERATED', 'maturity_day': payload['maturity_after'],
        'default_eligible_day': payload['default_eligible_day']})
    _margin_event(state, entry, 'MARGIN_ACCELERATION',
                  ('outstanding_krw', 'maturity_before', 'maturity_after', 'default_eligible_day'))


def _fold_default_proposal(state, entry):
    payload = entry['payload']
    record = _margin_record(state, entry, expect=('ACCELERATED',))
    if record['proposal_day'] is not None:
        raise OverlayError('proposal already recorded')
    if (entry['sim_day'] < record['default_eligible_day'] or payload['default_eligible_day'] != record['default_eligible_day']
            or payload['proposal_kind'] != 'DEFAULT_ELIGIBLE'):
        raise OverlayError('proposal before default eligibility')
    _margin_set(state, payload['advance_id'], {**record, 'proposal_day': entry['sim_day']})
    _margin_event(state, entry, 'DEFAULT_ELIGIBLE_PROPOSAL',
                  ('proposal_kind', 'authority', 'default_eligible_day', 'outstanding_krw'))


_FOLDERS = {KIND_TERMS: _fold_terms, KIND_CLOCK: _fold_clock, KIND_INTEREST: _fold_interest, KIND_REPAYMENT: _fold_repayment,
            KIND_MARGIN_CALL: _fold_margin_call, KIND_MARGIN_CURE: _fold_margin_cure,
            KIND_MARGIN_ACCELERATION: _fold_margin_acceleration, KIND_DEFAULT_PROPOSAL: _fold_default_proposal}


def fold(entries, journal_length=None):
    """Deterministic fold of the journal. Raises OverlayError on any violation; never repairs.

    A repeated overlay_id with an identical entry is ignored; a conflicting one fails closed.
    `journal_length`, when given, bounds every after_journal_index (a dangling reference fails).
    """
    if type(entries) is not list:
        raise OverlayError('journal')
    state = empty_state()
    seen = {}
    for entry in entries:
        validate_entry(entry)
        known = seen.get(entry['overlay_id'])
        if known is not None:
            if known != entry:
                raise OverlayError('conflicting overlay_id')
            continue
        seen[entry['overlay_id']] = entry
        if journal_length is not None and entry['after_journal_index'] > journal_length:
            raise OverlayError('dangling after_journal_index')
        if entry['after_journal_index'] < state['last_after_journal_index'] or entry['sim_day'] < state['sim_day']:
            raise OverlayError('entries not monotone')
        from capital import recovery
        if entry['kind'] in recovery.KINDS:
            recovery.fold_entry(state, entry)
        else:
            _FOLDERS[entry['kind']](state, entry)
        state['entry_count'] += 1
        state['last_after_journal_index'] = entry['after_journal_index']
    if 'repayment' in state:
        state['repayment']['close_gate'] = close_gates(state)
    return state


def state_digest(state):
    return hashlib.sha256(canonical_bytes({'domain': DOMAIN, 'overlay_schema': SCHEMA, 'state': state})).hexdigest()


def build_section(entries, state=None):
    state = fold(entries) if state is None else state
    section = {'overlay_schema': SCHEMA, 'journal': [dict(entry) for entry in entries],
               'overlay_state': {'digest': state_digest(state), 'state': state}}
    section['section_sha256'] = section_checksum(section)
    return section


def export_section(entries, journal_length=None):
    """Body of the V3 manifest `overlay` section (CAPITAL_OVERLAY_DIGEST_EXPORT.md 3.2).

    A pure function of the overlay journal; the other seven sections never see it.
    """
    state = fold(entries, journal_length)
    return {
        'label': LABEL, 'overlay_schema': SCHEMA, 'sim_day': state['sim_day'],
        'clock_source': CLOCK_SOURCE, 'terms_binding': copy.deepcopy(state['terms_binding']),
        'entry_count': state['entry_count'], 'journal': copy.deepcopy(entries),
        'state': copy.deepcopy(state), 'overlay_state_digest': state_digest(state),
    }


def empty_section():
    return build_section([], empty_state())


def restore(section, journal_length):
    """Entries of a checksum-verified section after folding and comparing the digest."""
    entries = section['journal']
    state = fold(entries, journal_length)
    cached = section['overlay_state']
    if set(cached) != {'digest', 'state'} or cached['state'] != state or cached['digest'] != state_digest(state):
        raise OverlayError('fold does not match the persisted overlay_state')
    return [dict(entry) for entry in entries]


# ---------------------------------------------------------------- clock and accrual

def draw_day_for(entries, draw_index):
    """sim_day in force when the draw at F04 journal index `draw_index` was accepted."""
    day = 0
    for entry in entries:
        if entry['kind'] == KIND_CLOCK and entry['after_journal_index'] <= draw_index:
            day = entry['sim_day']
    return day


def _split(elapsed, term_days):
    if elapsed <= term_days:
        return elapsed, 0
    return term_days, elapsed - term_days


def _elapsed(day, draw_day, minimum):
    if day <= draw_day:
        return 0
    return max(day - draw_day, minimum)


def accrual_postings(state, to_day, subjects):
    """Interest posting payloads for the segment ending at `to_day`.

    Each subject: advance_id, principal (F04 outstanding_exposure, constant over the
    segment because every command since the last tick happened at the folded sim_day),
    draw_day and terms (terms.ledger_terms plus min_interest_days). Cumulative exact
    values are simple ACT/365 sums of principal * days * bps / (10000 * 365); each
    posting is floor(cumulative) minus what is already posted, so the remainder carries.
    """
    out = []
    for subject in sorted(subjects, key=lambda item: item['advance_id']):
        terms, principal, draw_day = subject['terms'], subject['principal'], subject['draw_day']
        if principal < 1:
            continue
        prior = state['advances'].get(subject['advance_id'])
        start = draw_day if prior is None else prior['last_accrued_day']
        end = min(to_day, terms['writeoff_day']) if terms['writeoff_day'] is not None else to_day
        if end <= start:
            continue
        before = _split(_elapsed(start, draw_day, terms['min_interest_days']), terms['term_days'])
        after = _split(_elapsed(end, draw_day, terms['min_interest_days']), terms['term_days'])
        contractual, default = after[0] - before[0], after[1] - before[1]
        cum_contract = Fraction(0) if prior is None else parse_exact(prior['cumulative_contract_exact'])
        cum_default = Fraction(0) if prior is None else parse_exact(prior['cumulative_default_exact'])
        cum_contract += Fraction(principal * contractual * terms['contract_bps'], terms['denominator'])
        cum_default += Fraction(principal * default * terms['default_bps'], terms['denominator'])
        out.append({
            **({'recovery_witness': dict(terms['recovery_witness'])} if 'recovery_witness' in terms else {}),
            'advance_id': subject['advance_id'], 'tier': terms['tier'], 'principal': principal,
            'draw_day': draw_day, 'maturity_day': terms['maturity_day'],
            'from_day': start, 'to_day': end, 'contractual_days': contractual, 'default_days': default,
            'contract_bps': terms['contract_bps'], 'default_bps': terms['default_bps'],
            'terms_version': terms['terms_version'],
            'cumulative_contract_exact': exact_text(cum_contract),
            'cumulative_default_exact': exact_text(cum_default),
            'posted_contract_krw': floor(cum_contract) - (0 if prior is None else prior['posted_contract_krw']),
            'posted_default_krw': floor(cum_default) - (0 if prior is None else prior['posted_default_krw']),
        })
    return out


def advance_entries(operation_id, state, journal_length, *, to_day, reason, binding, subjects,
                    margin_before=(), margin_after=()):
    """The entries one advance_day command appends, in order. Pure; nothing is stored here.

    `binding` is {'terms_version', 'status'} and is recorded only when no binding exists yet.
    `margin_before` (cures dated at the folded day) precede the clock entry; `margin_after`
    (calls, accelerations, proposals dated at the target day) come last.
    """
    from_day = state['sim_day']
    entries = []
    if state['terms_binding'] is None:
        entries.append({'overlay_id': f'{operation_id}:terms', 'after_journal_index': journal_length,
                        'sim_day': from_day, 'kind': KIND_TERMS, 'payload': dict(binding)})
    entries.extend(margin_before)
    entries.append({'overlay_id': operation_id, 'after_journal_index': journal_length,
                    'sim_day': to_day, 'kind': KIND_CLOCK,
                    'payload': {'from_sim_day': from_day, 'to_sim_day': to_day, 'reason': reason,
                                'actor': ACTOR, 'clock_source': CLOCK_SOURCE}})
    for posting in accrual_postings(state, to_day, subjects):
        entries.append({'overlay_id': f"{operation_id}:interest:{posting['advance_id']}",
                        'after_journal_index': journal_length, 'sim_day': to_day,
                        'kind': KIND_INTEREST, 'payload': posting})
    entries.extend(margin_after)
    return entries


def repayment_entry(operation_id, state, *, journal_index, advance_ref, amount, denominator, principal_before,
                    terms_version, split, f04=None, evidence_ref=None, proposal_id=None):
    """The one entry a post_repayment command appends. Pure; nothing is stored here.

    `split` is the shared allocation (terms.allocate); `f04` is (operation id, receipt ref) of the
    principal repay the service issues in the same save, None when no principal is applied.
    `journal_index` is the F04 journal length after that repay.
    """
    witness, _default_due, _interest_due, held = repayment_position(state, advance_ref, denominator)
    payload = {
        'advance_ref': advance_ref, 'amount_krw': amount, 'unapplied_before_krw': held,
        'allocation': {'default_interest_krw': split['to_default_interest'], 'interest_krw': split['to_interest'],
                       'principal_krw': split['to_principal'], 'unapplied_after_krw': split['unapplied_cash']},
        'witness': {**witness, 'principal_before_krw': principal_before},
        'terms_binding': {'terms_version': terms_version},
        'f04_operation_id': None if f04 is None else f04[0],
        'f04_receipt_ref': None if f04 is None else f04[1],
        'label': LABEL, 'basis': BASIS}
    if evidence_ref is not None:
        payload['evidence_ref'] = evidence_ref
    if proposal_id is not None:
        payload['proposal_id'] = proposal_id
    return {'overlay_id': operation_id, 'after_journal_index': journal_index, 'sim_day': state['sim_day'],
            'kind': KIND_REPAYMENT, 'payload': payload}


def _repayment_receipt(position, entry):
    """Receipt of a recorded repayment, a pure function of its entry (a duplicate matches after a reload)."""
    payload = entry['payload']
    split, witness = payload['allocation'], payload['witness']
    denominator = witness['denominator']
    gate = _gate(_decimal(witness['accrued_default_num']) // denominator - witness['paid_default_krw']
                 - split['default_interest_krw'],
                 _decimal(witness['accrued_interest_num']) // denominator - witness['paid_interest_krw']
                 - split['interest_krw'],
                 split['unapplied_after_krw'])
    receipt = {
        'operation_id': entry['overlay_id'], 'op': COMMAND_REPAY, 'outcome': 'APPLIED',
        'advance_ref': payload['advance_ref'], 'at_sim_day': entry['sim_day'], 'sim_day': entry['sim_day'],
        'amount_krw': payload['amount_krw'], 'unapplied_before_krw': payload['unapplied_before_krw'],
        'entry_no': position + 1, 'allocation': dict(split),
        'f04': None if payload['f04_operation_id'] is None else {
            'operation_id': payload['f04_operation_id'], 'receipt_ref': payload['f04_receipt_ref']},
        'unapplied_after_krw': split['unapplied_after_krw'], 'close_gate': gate,
        'payment_basis': PAYMENT_BASIS, 'basis': BASIS}
    for key in ('evidence_ref', 'proposal_id'):
        if key in payload:
            receipt[key] = payload[key]
    return receipt


def operation_receipt(entries, operation_id):
    """Rebuild a recorded command's receipt from its entries, or None when never applied."""
    from capital import recovery
    for entry in entries:
        if entry['overlay_id'] == operation_id and entry['kind'] in recovery.KINDS:
            return recovery.receipt(entry)
    for position, entry in enumerate(entries):
        if entry['overlay_id'] == operation_id and entry['kind'] == KIND_REPAYMENT:
            return _repayment_receipt(position, entry)
    clock = next((entry for entry in entries if entry['kind'] == KIND_CLOCK and entry['overlay_id'] == operation_id), None)
    if clock is None:
        return None
    prefix = f'{operation_id}:interest:'
    payload = clock['payload']
    return {
        'operation_id': operation_id, 'op': COMMAND_OP, 'outcome': 'APPLIED',
        'from_sim_day': payload['from_sim_day'], 'to_sim_day': payload['to_sim_day'],
        'reason': payload['reason'], 'sim_day': clock['sim_day'],
        'terms_bound_by_this_command': any(entry['overlay_id'] == f'{operation_id}:terms' for entry in entries),
        'postings': [{'advance_id': entry['payload']['advance_id'],
                      'posted_contract_krw': entry['payload']['posted_contract_krw'],
                      'posted_default_krw': entry['payload']['posted_default_krw']}
                     for entry in entries if entry['overlay_id'].startswith(prefix)],
    }


def section_size(payload, entries):
    """Canonical byte size of the persisted payload plus overlay journal, for the envelope bound."""
    return len(canonical_bytes(payload)) + len(canonical_bytes(entries))


def entry_size(entry):
    return len(canonical_bytes(entry))
