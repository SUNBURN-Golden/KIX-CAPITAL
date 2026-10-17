"""Overlay ledger: the sim_day clock and ACT/365 simple-interest memo postings.

SIMULATED memo ledger. Nothing here is a payment, a receivable or a bank record.
The F04 journal is never written and the FSM is never gated: the overlay is a
separate append-only journal inside the one workspace envelope, and its authority
is the deterministic fold of its entries (docs/decisions/CAPITAL_OVERLAY_STATE.md).
Digest, clock and golden policy follow docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md.

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
STATE_NOTE = 'CAPITAL_OVERLAY_STATE.md'
EXPORT_NOTE = 'CAPITAL_OVERLAY_DIGEST_EXPORT.md'

KIND_TERMS = 'terms_binding'
KIND_CLOCK = 'clock'
KIND_INTEREST = 'interest_posting'
KIND_MARGIN_CALL = 'margin_call'
KIND_MARGIN_CURE = 'margin_cure'
KIND_MARGIN_ACCELERATION = 'margin_acceleration'
KIND_DEFAULT_PROPOSAL = 'default_eligible_proposal'
MARGIN_KINDS = (KIND_MARGIN_CALL, KIND_MARGIN_CURE, KIND_MARGIN_ACCELERATION, KIND_DEFAULT_PROPOSAL)
# entry kind -> the section of the decided storage shape it belongs to
SECTION_OF = {KIND_CLOCK: 'clock', KIND_INTEREST: 'interest_ledger', KIND_TERMS: 'decision_records',
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
    shape = _PAYLOAD_TYPES.get(entry['kind']) if type(entry['kind']) is str else None
    payload = entry['payload']
    if shape is None or type(payload) is not dict or set(payload) != set(shape):
        raise OverlayError('payload keys')
    for key, kind in shape.items():
        value = payload[key]
        if type(value) is not kind or (kind is int and value < 0) or (kind is str and not value):
            raise OverlayError(f'payload {key}')


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


_FOLDERS = {KIND_TERMS: _fold_terms, KIND_CLOCK: _fold_clock, KIND_INTEREST: _fold_interest,
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
        _FOLDERS[entry['kind']](state, entry)
        state['entry_count'] += 1
        state['last_after_journal_index'] = entry['after_journal_index']
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
        end = min(to_day, terms['writeoff_day'])
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


def operation_receipt(entries, operation_id):
    """Rebuild a recorded command's receipt from its entries, or None when never applied."""
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
