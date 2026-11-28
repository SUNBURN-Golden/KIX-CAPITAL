"""Disposable, bounded participation replay. Synthetic inputs; no execution or storage.

Policy terms and capacity limits come exclusively from the selected decision notes.
Statement arithmetic is integer-only; adjustments are classified replacement amounts.
The shadow port composes this module without changing its predecessor responses.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

from capital.resources import note_path, read_note, provenance

BOOK_SCHEMA = 'capital-participation-book-v1'
CLASSES = frozenset(('COUNTERPARTY_PROCEEDS', 'PROTECTED_LINES', 'PLATFORM_FEES',
                     'REFUND_RESERVES', 'CUSTOMER_DEPOSITS', 'HELD_TAX'))

# Supported semantic vocabulary, not financial terms. Numeric terms are loaded.
_SEMANTICS = {'event_claim_membership': {'agreements': 1,
                            'beneficiaries': 1,
                            'membership': 'FIXED_MANIFEST',
                            'claim_originals': 'ONE_PER_CLAIM_PER_BOOK',
                            'source_amount_identity': 'UNIQUE_PER_BOOK',
                            'events': ['ORIGINAL', 'ADJUSTMENT'],
                            'adjustment': 'SAME_CLASSIFICATION_REPLACEMENT_AMOUNT',
                            'inputs': 'SYNTHETIC_ALREADY_CLASSIFIED_ONLY',
                            'fsm_expressible': False,
                            'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'statement_anchor_and_day_order': {'identity': ['book_id', 'agreement_id', 'anchor_day'],
                                    'anchor': 'EXPLICIT_IMMUTABLE_SIM_DAY',
                                    'original_day': 'ANCHOR_DAY',
                                    'order': ['sim_day', 'sequence'],
                                    'sequence': 'UNIQUE_WITHIN_DAY',
                                    'close': 'AFTER_ALL_EVENTS_OF_DAY',
                                    'wall_clock': False,
                                    'fsm_expressible': False,
                                    'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'advance_slice_priority_inputs': {'excluded': ['PROTECTED_LINES',
                                                'PLATFORM_FEES',
                                                'REFUND_RESERVES'],
                                   'order': ['SLICE_HOLDER_FIRST',
                                             'ADVANCE_SETOFF_ON_REMAINDER',
                                             'PARTICIPATION',
                                             'BENEFICIARY_RESIDUAL'],
                                   'obligations': 'PINNED_DISJOINT_CLAIM_BUDGETS',
                                   'conflict': 'REJECT_BOOK',
                                   'conservation': 'GROSS_EQUALS_EXCLUDED_PLUS_HOLDER_PLUS_ADVANCE_PLUS_PARTICIPATION_PLUS_RESIDUAL',
                                   'fsm_expressible': False,
                                   'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'adjustment_window_boundary': {'boundary_inclusive': True,
                                'outside_window': 'DIAGNOSTIC_ONLY_NO_RESTATEMENT',
                                'reanchor': False,
                                'fsm_expressible': False,
                                'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'cap_clawback_and_term_end': {'terms': 'PRESERVE_EXISTING_RATIO_CAP_AND_TERM',
                               'missing_terms': 'BLOCK_CALCULATION',
                               'cap_basis': 'CUMULATIVE_ACCEPTED_POSITIVE_ALLOCATIONS',
                               'clawback_reopens_cap': False,
                               'cap_reached': 'IRREVERSIBLE_LATCH',
                               'negative_delta': 'LIMIT_TO_CURRENT_STATEMENT_NET_ALLOCATION',
                               'unallocated_positive_delta': 'NO_BACKLOG',
                               'term_end': 'INCLUSIVE_THEN_NEGATIVE_ADJUSTMENTS_ONLY_WITHIN_ORIGINAL_WINDOW',
                               'fsm_expressible': False,
                               'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'rounding_carry_and_duplicates': {'arithmetic': 'INTEGER_BPS',
                                   'uncapped_amount': 'floor(sum_current_claim_bases * ratio_bps / '
                                                      '10000)',
                                   'carry': 'REMAINDER_WITHIN_STATEMENT_ONLY',
                                   'final_fraction': 'DISCLOSE_WITHOUT_ROUNDUP',
                                   'duplicate_identical': 'NO_OP',
                                   'duplicate_conflicting': 'REJECT_BOOK',
                                   'adjustments': 'RECOMPUTE_FROM_REPLACEMENT_AMOUNTS',
                                   'fsm_expressible': False,
                                   'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'disposable_replay_bounds': {'complete_history_required': True,
                              'persistent_commands': False,
                              'automatic_payouts': False,
                              'failure': 'ATOMIC_REJECTION',
                              'fsm_expressible': False,
                              'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM'},
 'provenance_and_output_labels': {'labels': ['SIMULATED',
                                             'SYNTHETIC_FIXTURE_PROFILE',
                                             'SHADOW_NOT_APPLIED',
                                             'SIMULATION_ONLY_NOT_OFFERED_V1',
                                             'UNSUPPORTED_BY_PINNED_FSM'],
                                  'production': 'NOT_AUTHORIZED',
                                  'funds_executed': False,
                                  'upstream_adoption_claimed': False,
                                  'consumer': 'participation-window-replay',
                                  'consumer_status': 'PENDING_CONSUMER',
                                  'registration_applied': True,
                                  'required_provenance': ['DECISION',
                                                          'TERMS_SOURCE',
                                                          'INPUT_DIGEST',
                                                          'STATEMENT_IDENTITY',
                                                          'REVISION_DIGEST',
                                                          'EVENT_LINEAGE'],
                                  'fsm_expressible': False,
                                  'fsm_support': 'UNSUPPORTED_BY_PINNED_FSM',
                                  'implementation_status': 'PENDING_IMPLEMENTATION',
                                  'vendor_fsm_reconciliation': False,
                                  'persistent_commands': False,
                                  'automatic_payouts': False}}
_BOUND_KEYS = ('max_claims', 'max_statements', 'max_input_events', 'max_input_bytes',
               'max_day_span', 'max_book_amount')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ParticipationBinding:
    """Immutable loaded policy; provenance is canonical JSON, never caller state."""
    status: str
    reason: str
    provenance_json: str
    policy_version: str | None = None
    ratio_bps: int = 0
    cap_bps: int = 0
    window_days: int = 0
    bounds: tuple = ()


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def load_participation_policy(window_note=None, settlement_note=None):
    """Exclusive overrides, raw-byte provenance, and fail-closed semantic binding."""
    window = read_note(note_path('CAPITAL_PARTICIPATION_WINDOW.md') if window_note is None
                       else window_note, override=window_note is not None)
    settlement = read_note(note_path('CAPITAL_SETTLEMENT_POLICY.md') if settlement_note is None
                           else settlement_note, override=settlement_note is not None)
    source = {'window': provenance(window), 'settlement': provenance(settlement),
              'entry_paths': ['entries.' + key for key in _SEMANTICS],
              'terms_entry_path': 'entries.revenue_participation.value'}
    def unbound(reason):
        return ParticipationBinding('SHADOW_NOT_BOUND', reason, canonical(source))
    try:
        for note, identity in ((window, 'participation-window-decision'),
                               (settlement, 'settlement-policy-decision')):
            block = note['block']
            if (not block or block['decision_id'] != identity or
                    block['status'] != 'PROVISIONAL_PRODUCT_DECISION' or block['provisional'] is not True):
                return unbound('missing or unusable decision')
        entries = window['block']['entries']
        values = {}
        for key, supported in _SEMANTICS.items():
            entry = entries[key]
            if entry['status'] != 'ADOPTED' or entry['provisional'] is not True:
                return unbound('required window entry is not adopted: ' + key)
            value = entry['value'].copy()
            values[key] = value.copy()
            if key == 'adjustment_window_boundary':
                days = value.pop('days_after_anchor')
                if not _int(days, 0, 365) or value.pop('predicate') != (
                        f'anchor_day <= adjustment_day <= anchor_day + {days}'):
                    return unbound('unsupported window predicate')
            if key == 'disposable_replay_bounds':
                bounds = tuple(value.pop(name) for name in _BOUND_KEYS)
                if any(type(n) is not int or n <= 0 for n in bounds):
                    return unbound('unusable capacity bounds')
            if canonical(value) != canonical(supported):
                return unbound('unsupported window semantics: ' + key)
        # Settlement terms are read here, never inferred from worked examples.
        terms = settlement['block']['entries']['revenue_participation']
        value = terms['value']
        if terms['status'] != 'ADOPTED' or terms['provisional'] is not True:
            return unbound('participation terms are not adopted')
        ratio, cap = value['ratio_bps_of_base'], value['cap_bps_of_funded_amount']
        version = value['policy_version']
        if not _int(ratio, 0, 10000) or not _int(cap, 1, 10**12) or not _label(version):
            return unbound('unusable participation terms')
        source.update(decision_id=window['block']['decision_id'],
                      terms_decision_id=settlement['block']['decision_id'], policy_version=version, ratio_bps=ratio, cap_bps=cap,
                      window_days=values['adjustment_window_boundary']['days_after_anchor'],
                      capacity_bounds=dict(zip(_BOUND_KEYS, bounds)))
        return ParticipationBinding('SHADOW_BOUND', '', canonical(source), version, ratio, cap,
                                    values['adjustment_window_boundary']['days_after_anchor'], bounds)
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError):
        return unbound('missing or malformed required entries')


class Rejected(ValueError):
    def __init__(self, code, path, detail):
        self.reason = {'code': code, 'path': path, 'detail': detail}
        super().__init__(detail)


def _require(condition, code, path, detail):
    if not condition:
        raise Rejected(code, path, detail)


def _shape(value, keys, path):
    _require(type(value) is dict and set(value) == set(keys.split()), 'INVALID_SCHEMA', path,
             'object must contain exactly: ' + keys)


def _label(value):
    return type(value) is str and bool(value.strip()) and value.isascii()


def _labels(row, names, path):
    for key in names.split():
        _require(_label(row[key]), 'INVALID_IDENTITY', path + '.' + key, 'nonempty ASCII identity required')


def _amount(value, maximum, path):
    _require(_int(value, 0, maximum), 'INVALID_AMOUNT', path, 'bounded nonnegative integer required')
    return value


def _list(value, path, maximum=None):
    _require(type(value) is list, 'INVALID_SCHEMA', path, 'array required')
    if maximum is not None:
        _require(len(value) <= maximum, 'CAPACITY_EXCEEDED', path, 'too many entries before deduplication')


def _components(items, path, maximum=None):
    _list(items, path)
    _require(bool(items), 'INVALID_CLASSIFICATION', path, 'nonempty classified components required')
    result = {}
    for item in items:
        _shape(item, 'source_id cash_class' + (' amount' if maximum is not None else ''), path)
        _labels(item, 'source_id cash_class', path)
        _require(item['cash_class'] in CLASSES and item['source_id'] not in result,
                 'INVALID_CLASSIFICATION', path, 'unknown class or duplicate component source')
        if maximum is not None:
            _amount(item['amount'], maximum, path + '.amount')
        result[item['source_id']] = item['cash_class']
    return result


def _validate(book, binding):
    limits = dict(zip(_BOUND_KEYS, binding.bounds))
    maximum = limits['max_book_amount']
    _require(len(canonical(book).encode('utf-8')) <= limits['max_input_bytes'],
             'CAPACITY_EXCEEDED', '$', 'canonical input exceeds byte limit')
    _shape(book, 'schema manifest claims advances events', '$')
    _require(book['schema'] == BOOK_SCHEMA, 'INVALID_SCHEMA', 'schema', 'unsupported book version')
    m = book['manifest']
    _shape(m, 'book_id agreement_id beneficiary_id funded_amount terms_reference start_day end_day as_of_day complete_history claim_ids', 'manifest')
    _labels(m, 'book_id agreement_id beneficiary_id terms_reference', 'manifest')
    _require(m['terms_reference'] == binding.policy_version, 'TERMS_MISMATCH', 'manifest.terms_reference',
             'terms reference must match bound participation policy version')
    _amount(m['funded_amount'], maximum, 'manifest.funded_amount')
    _require(m['complete_history'] is True, 'INCOMPLETE_HISTORY', 'manifest', 'complete history from agreement start required')
    for key in ('start_day', 'end_day', 'as_of_day'):
        _require(type(m[key]) is int and m[key] >= 0, 'INVALID_DAY', 'manifest.' + key, 'nonnegative integer day required')
    start, end, observation = (m[k] for k in ('start_day', 'end_day', 'as_of_day'))
    def day(n, path):
        _require(_int(n, start, start + limits['max_day_span']), 'INVALID_DAY', path, 'day outside bounded horizon')
    day(end, 'manifest.end_day')
    day(observation, 'manifest.as_of_day')
    _list(m['claim_ids'], 'manifest.claim_ids', limits['max_claims'])
    _require(all(_label(x) for x in m['claim_ids']) and len(set(m['claim_ids'])) == len(m['claim_ids']),
             'INVALID_MEMBERSHIP', 'manifest.claim_ids', 'unique claim IDs required')
    _list(book['claims'], 'claims', limits['max_claims'])
    _list(book['advances'], 'advances')
    _list(book['events'], 'events', limits['max_input_events'])
    claims, sources, components, scopes, anchors = {}, set(), set(), set(), set()
    budgets, advances = {}, {}
    for a in book['advances']:
        _shape(a, 'advance_id balance', 'advances')
        _labels(a, 'advance_id', 'advances')
        _require(a['advance_id'] not in advances, 'PRIORITY_INPUT_CONFLICT', 'advances', 'duplicate advance')
        advances[a['advance_id']] = _amount(a['balance'], maximum, 'advances.balance')
    _amount(sum(advances.values()), maximum, 'advances.total')
    for c in book['claims']:
        _shape(c, 'claim_id source_amount_id beneficiary_id anchor_day components source_scopes holder_due advance_due advance_id', 'claims')
        _labels(c, 'claim_id source_amount_id beneficiary_id', 'claims')
        _require(c['claim_id'] not in claims and c['source_amount_id'] not in sources and
                 c['beneficiary_id'] == m['beneficiary_id'], 'INVALID_MEMBERSHIP', 'claims',
                 'duplicate claim/source amount or wrong beneficiary')
        day(c['anchor_day'], 'claims.anchor_day')
        _require(c['anchor_day'] <= min(end, observation), 'INVALID_DAY', 'claims.anchor_day', 'anchor after term or observation')
        day(c['anchor_day'] + binding.window_days, 'claims.closing_day')
        anchors.add(c['anchor_day'])
        mapping = _components(c['components'], 'claims.components')
        _require(not components.intersection(mapping), 'PRIORITY_INPUT_CONFLICT', 'claims.components', 'shared source components')
        components.update(mapping)
        _list(c['source_scopes'], 'claims.source_scopes')
        scope = c['source_scopes']
        _require(scope and all(_label(x) for x in scope) and len(set(scope)) == len(scope) and
                 not scopes.intersection(scope), 'PRIORITY_INPUT_CONFLICT', 'claims.source_scopes',
                 'nonempty disjoint atomic source scopes required')
        scopes.update(scope)
        for key in ('holder_due', 'advance_due'):
            _amount(c[key], maximum, 'claims.' + key)
        aid = c['advance_id']
        _require((aid is None and c['advance_due'] == 0) or (_label(aid) and aid in advances),
                 'PRIORITY_INPUT_CONFLICT', 'claims.advance_id', 'advance budget must reference its balance')
        if aid is not None:
            budgets[aid] = budgets.get(aid, 0) + c['advance_due']
            _require(budgets[aid] <= advances[aid], 'PRIORITY_INPUT_CONFLICT', 'claims.advance_due', 'overcommitted advance budget')
        claims[c['claim_id']] = c
        sources.add(c['source_amount_id'])
    _amount(sum(c['holder_due'] for c in claims.values()), maximum, 'claims.total_holder_due')
    _require(bool(claims) and set(claims) == set(m['claim_ids']), 'INVALID_MEMBERSHIP', 'claims', 'fixed manifest membership required')
    _require(len(anchors) <= limits['max_statements'], 'CAPACITY_EXCEEDED', 'claims', 'too many statements')
    events, duplicates, positions, originals = {}, {}, set(), {}
    for e in book['events']:
        _shape(e, 'event_id kind claim_id source_amount_id beneficiary_id anchor_day sim_day sequence original_event_id components', 'events')
        _labels(e, 'event_id kind claim_id source_amount_id beneficiary_id', 'events')
        _require(e['kind'] in ('ORIGINAL', 'ADJUSTMENT') and e['claim_id'] in claims,
                 'INVALID_MEMBERSHIP', 'events', 'unknown event kind or claim')
        c = claims[e['claim_id']]
        for key in ('source_amount_id', 'beneficiary_id', 'anchor_day'):
            _require(type(e[key]) is type(c[key]) and e[key] == c[key], 'INVALID_MEMBERSHIP', 'events.' + key, 'claim identity must be preserved')
        mapping = _components(e['components'], 'events.components', maximum)
        _require(mapping == _components(c['components'], 'claims.components'), 'INVALID_CLASSIFICATION', 'events.components', 'source-to-classification mapping must be preserved')
        _amount(sum(x['amount'] for x in e['components']), maximum, 'events.gross')
        day(e['sim_day'], 'events.sim_day')
        _require(e['sim_day'] <= observation, 'FUTURE_EVENT', 'events.sim_day', 'event after end-of-day observation')
        _require(type(e['sequence']) is int and e['sequence'] >= 0, 'INVALID_SEQUENCE', 'events.sequence', 'nonnegative integer sequence required')
        _require((e['kind'] == 'ORIGINAL' and e['original_event_id'] is None) or
                 (e['kind'] == 'ADJUSTMENT' and _label(e['original_event_id'])), 'INVALID_REFERENCE', 'events.original_event_id', 'explicit original reference required for adjustments only')
        # Component and collection order is not semantic. Payload identity uses this normalization.
        e = dict(e, components=sorted(e['components'], key=lambda x: x['source_id']))
        eid = e['event_id']
        if eid in events:
            _require(e == events[eid], 'DUPLICATE_CONFLICT', 'events.' + eid, 'same event ID has conflicting payload')
            duplicates[eid] = duplicates.get(eid, 0) + 1
            continue
        pos = (e['sim_day'], e['sequence'])
        _require(pos not in positions, 'INVALID_SEQUENCE', 'events', 'sequence must be unique within day')
        positions.add(pos)
        events[eid] = e
        if e['kind'] == 'ORIGINAL':
            _require(e['claim_id'] not in originals and e['sim_day'] == c['anchor_day'],
                     'INVALID_ORIGINAL', 'events', 'one original per claim, exactly at anchor')
            originals[e['claim_id']] = e
    _require(set(originals) == set(claims), 'INCOMPLETE_HISTORY', 'events', 'one original per manifest claim required')
    ordered = sorted(events.values(), key=lambda e: (e['sim_day'], e['sequence']))
    for e in ordered:
        if e['kind'] == 'ADJUSTMENT':
            o = originals[e['claim_id']]
            _require(e['original_event_id'] == o['event_id'] and
                     (e['sim_day'], e['sequence']) > (o['sim_day'], o['sequence']),
                     'INVALID_REFERENCE', 'events.' + e['event_id'], 'adjustment must follow its own original in day/sequence order')
    # Normalize all unordered collections; duplicates remain part of input provenance.
    normalized_manifest = dict(m, claim_ids=sorted(m['claim_ids']))
    normalized_claims = {c['claim_id']: dict(c, components=sorted(
        c['components'], key=lambda x: x['source_id']),
        source_scopes=sorted(c['source_scopes'])) for c in claims.values()}
    normalized = dict(book, manifest=normalized_manifest,
                      claims=sorted(normalized_claims.values(), key=lambda c: c['claim_id']),
                      advances=sorted(book['advances'], key=lambda a: a['advance_id']),
                      events=ordered, duplicate_counts=dict(sorted(duplicates.items())))
    return normalized_manifest, normalized_claims, ordered, duplicates, maximum, digest(normalized)


def _envelope(binding, status, reasons=()):
    from capital.shadow import FALSE_FLAGS
    result = dict.fromkeys(FALSE_FLAGS + ('fsm_expressible', 'vendor_fsm_reconciliation',
                           'persistent_commands', 'automatic_payouts', 'upstream_adoption_claimed'), False)
    result.update(status=status, mode='SHADOW_NOT_APPLIED', production='NOT_AUTHORIZED',
                  labels=['SIMULATED', 'SYNTHETIC_FIXTURE_PROFILE', 'SHADOW_NOT_APPLIED',
                          'SIMULATION_ONLY_NOT_OFFERED_V1', 'UNSUPPORTED_BY_PINNED_FSM'],
                  provisional=True, legal_tax='WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW',
                  provenance=json.loads(binding.provenance_json), reasons=list(reasons))
    return result


def _decompose(e, c):
    gross = sum(x['amount'] for x in e['components'])
    q = sum(x['amount'] for x in e['components'] if x['cash_class'] == 'COUNTERPARTY_PROCEEDS')
    holder = min(q, c['holder_due'])
    advance = min(q - holder, c['advance_due'])
    return {'shadow_gross': gross, 'shadow_excluded': gross - q, 'shadow_eligible_cash': q,
            'shadow_holder': holder, 'shadow_advance': advance, 'shadow_base': q - holder - advance,
            'shadow_holder_unmet': c['holder_due'] - holder,
            'shadow_advance_unmet': c['advance_due'] - advance}


def _fold(m, claims, events, binding, maximum):
    cap = _amount(m['funded_amount'] * binding.cap_bps // 10000, maximum, 'shadow_cap')
    statements = {}
    for c in claims.values():
        anchor = c['anchor_day']
        statements.setdefault(anchor, {'identity': [m['book_id'], m['agreement_id'], anchor],
            'anchor_day': anchor, 'closing_day': anchor + binding.window_days,
            'shadow_base': 0, 'shadow_uncapped_entitlement': 0, 'shadow_carry': 0,
            'shadow_net_entitlement': 0, 'revisions': []})
    current, observed, trace = {}, {}, []
    positive, clawbacks = 0, 0
    for e in events:
        c = claims[e['claim_id']]
        s = statements[c['anchor_day']]
        arithmetic = _decompose(e, c)
        observed[c['claim_id']] = arithmetic
        _amount(sum(x['shadow_gross'] for x in observed.values()), maximum, 'observed_book_gross')
        before = {k: s[k] for k in ('shadow_base', 'shadow_uncapped_entitlement',
                                    'shadow_carry', 'shadow_net_entitlement')}
        candidate_base = s['shadow_base'] - current.get(c['claim_id'], {}).get('shadow_base', 0) + arithmetic['shadow_base']
        candidate_u, candidate_carry = divmod(candidate_base * binding.ratio_bps, 10000)
        delta = candidate_u - s['shadow_uncapped_entitlement']
        inside = e['sim_day'] <= s['closing_day']
        payable = clawback = 0
        if inside:
            if delta > 0 and e['sim_day'] <= m['end_day']:
                payable = min(delta, cap - positive)
            elif delta < 0:
                clawback = min(s['shadow_net_entitlement'], -delta)
            positive += payable
            clawbacks += clawback
            current[c['claim_id']] = arithmetic
            s.update(shadow_base=candidate_base, shadow_uncapped_entitlement=candidate_u,
                     shadow_carry=candidate_carry,
                     shadow_net_entitlement=s['shadow_net_entitlement'] + payable - clawback)
            _amount(sum(x['shadow_gross'] for x in current.values()), maximum, 'settled_book_gross')
            _amount(sum(x['shadow_uncapped_entitlement'] for x in statements.values()), maximum, 'book_uncapped_entitlement')
        row = {'event_id': e['event_id'], 'claim_id': e['claim_id'],
               'original_event_id': e['original_event_id'], 'sort_key': [e['sim_day'], e['sequence']],
               'statement_identity': s['identity'], 'input': e, 'arithmetic': arithmetic,
               'window_status': 'WITHIN_WINDOW' if inside else 'OUTSIDE_WINDOW',
               'before': before, 'after': {k: s[k] for k in before},
               'shadow_candidate_base': candidate_base, 'shadow_candidate_uncapped_entitlement': candidate_u,
               'shadow_candidate_carry': candidate_carry, 'shadow_delta': delta,
               'shadow_unapplied_base_difference': 0 if inside else candidate_base - s['shadow_base'],
               'shadow_unallocated_positive_delta': max(0, delta - payable),
               'shadow_payable': payable, 'shadow_clawback': clawback,
               'shadow_cumulative_positive_allocations': positive, 'shadow_remaining_cap': cap - positive,
               'cap_status': 'CAP_REACHED' if positive == cap else 'CAP_AVAILABLE',
               'term_status': 'WITHIN_TERM' if e['sim_day'] <= m['end_day'] else 'TERM_ENDED'}
        row['revision_digest'] = digest({'statement': s['identity'], 'previous': s['revisions'][-1] if s['revisions'] else None,
                                         'event': e, 'after': row['after']})
        s['revisions'].append(row['revision_digest'])
        trace.append(row)
    for s in statements.values():
        s['window_status'] = 'CLOSED' if m['as_of_day'] >= s['closing_day'] else 'OPEN'
        s['revision_digest'] = s['revisions'][-1]
        s['shadow_beneficiary_residual'] = s['shadow_base'] - s['shadow_net_entitlement']
    settled = list(current.values())
    return {'shadow_base': sum(s['shadow_base'] for s in statements.values()),
            'shadow_uncapped_entitlement': sum(s['shadow_uncapped_entitlement'] for s in statements.values()),
            'shadow_net_entitlement': positive - clawbacks, 'shadow_payable': positive,
            'shadow_clawback': clawbacks, 'shadow_cap': cap, 'shadow_remaining_cap': cap - positive,
            'shadow_cumulative_positive_allocations': positive,
            'cap_status': 'CAP_REACHED' if positive == cap else 'CAP_AVAILABLE',
            'window_status': 'FINAL_SIMULATED' if all(s['window_status'] == 'CLOSED' for s in statements.values()) else 'OPEN',
            'term_status': 'TERM_ENDED' if m['as_of_day'] > m['end_day'] else 'WITHIN_TERM',
            'as_of_day': m['as_of_day'], 'statements': [statements[k] for k in sorted(statements)],
            'input_manifest': m,
            'settled_claims': [{'claim_id': k, 'input': claims[k], **current[k]} for k in sorted(current)],
            'shadow_gross': sum(x['shadow_gross'] for x in settled),
            'shadow_excluded': sum(x['shadow_excluded'] for x in settled),
            'shadow_holder': sum(x['shadow_holder'] for x in settled),
            'shadow_advance': sum(x['shadow_advance'] for x in settled),
            'trace': trace}


def replay_participation(book, *, binding):
    """Pure replay from complete original inputs. Never accepts an initial cap state."""
    if binding.status != 'SHADOW_BOUND':
        return _envelope(binding, 'SHADOW_NOT_BOUND', [{'code': 'DECISION_NOT_BOUND', 'path': 'binding', 'detail': binding.reason}])
    try:
        # JSON copy both enforces the JSON domain and protects caller-owned state.
        book = json.loads(canonical(book))
        m, claims, events, duplicates, maximum, input_digest = _validate(book, binding)
        calculated = _fold(m, claims, events, binding, maximum)
        return dict(_envelope(binding, 'SHADOW_COMPUTED'), **calculated,
                    input_digest=input_digest, policy_version=binding.policy_version,
                    input_advances=sorted(book['advances'], key=lambda a: a['advance_id']),
                    duplicate_diagnostics=[{'event_id': k, 'ignored_copies': duplicates[k]} for k in sorted(duplicates)])
    except Rejected as exc:
        return _envelope(binding, 'SHADOW_INCONSISTENT', [exc.reason])
    except (TypeError, ValueError, RecursionError, OverflowError):
        return _envelope(binding, 'SHADOW_INCONSISTENT', [{'code': 'INVALID_JSON', 'path': '$', 'detail': 'bounded finite JSON book required'}])


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--window-note', type=Path)
    parser.add_argument('--settlement-note', type=Path)
    args = parser.parse_args(argv)
    binding = load_participation_policy(args.window_note, args.settlement_note)
    if binding.status != 'SHADOW_BOUND':
        result = replay_participation(None, binding=binding)
    else:
        try:
            maximum_bytes = dict(zip(_BOUND_KEYS, binding.bounds))['max_input_bytes']
            with args.input.open('rb') as stream:
                raw = stream.read(maximum_bytes + 1)
            _require(len(raw) <= maximum_bytes, 'CAPACITY_EXCEEDED', '$', 'raw UTF-8 input exceeds byte limit')
            def nonfinite(value):
                raise ValueError('nonfinite JSON value')
            book = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=nonfinite)
            result = replay_participation(book, binding=binding)
        except Rejected as exc:
            result = _envelope(binding, 'SHADOW_INCONSISTENT', [exc.reason])
        except (OSError, UnicodeError, ValueError, RecursionError):
            result = _envelope(binding, 'SHADOW_INCONSISTENT', [{'code': 'INVALID_JSON', 'path': '$', 'detail': 'cannot read finite, unique-key UTF-8 JSON input'}])
    print(canonical(result))
    return 0 if result['status'] == 'SHADOW_COMPUTED' else 1


if __name__ == '__main__':
    sys.exit(main())
