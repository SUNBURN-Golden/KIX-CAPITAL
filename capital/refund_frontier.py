"""SIMULATED integer refund boundaries; pure consumer of a detached local cut.

The supported decision value fingerprints are compatibility identifiers, not terms:
changed semantics fail closed. Rates/payees come only from resolved margin_terms.
Registry evidence is exhaustive over a successful full local overlay fold. PROPOSED
occupies zero; all other states use residual face (including terminal frozen service).
This conservative support guard does not change registry or margin accounting.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from capital import margin, resources, slices
from capital.store import canonical_bytes
from capital.terms import BPS_SCALE

_SUPPORTED = {
    'shock_basis_and_domain': '361ef46bec6a564095b30735bc10153a737f61b72f2b001fd5b21d43423a7d1f',
    'coverage_breach_predicate': '3a300ea68bfce555cf055bc025fc326781ea7b3c3d01291520691ddb1f46e74f',
    'eligible_case_scope': 'bd098ccff01081ce77bf43fa9ef74f3def513a7e8f3f91c195db6cc9774c7d84',
    'shared_claim_and_slice_treatment': 'fd5832d2feddf8db4e6c55056a30339abea33e171b55d2656e61446faa39f12f',
    'rounding_and_boundary_witness': 'c855f36e9a88e9b218b2e9fc8100cb71102b4228cfc90bd8d217be1ecc357831',
    'result_labels_and_consumers': 'a1f2a2d1c091caf2b4517aa9edb7b0f77455b342e64ac4a10626fcd3f4074762',
}
FIRST = 'BREACH_FRONTIER_KRW'
ALREADY = 'ALREADY_BREACHED_ZERO_SHOCK'
ZERO = 'FRONTIER_UNDEFINED_NO_OUTSTANDING'
TERMINAL = 'NOT_COMPUTED_TERMINAL'
MISSING = 'NOT_COMPUTED_MISSING_INPUTS'
UNSUPPORTED = 'NOT_COMPUTED_UNSUPPORTED_EVALUATION'
AMBIGUOUS = 'NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP'
SLICE = 'NOT_COMPUTED_SLICE_ENCUMBRANCE'
INCOMPLETE = 'NOT_COMPUTED_INCOMPLETE_SCOPE'
WORKSPACE = 'NOT_COMPUTED_WORKSPACE_SCOPE'
OUTCOMES = {FIRST: 'FIRST_BREACH', ALREADY: 'ALREADY_BREACHED', ZERO: 'NO_BREACH_IN_DOMAIN',
            TERMINAL: 'EXCLUDED', MISSING: 'UNAVAILABLE', UNSUPPORTED: 'UNSUPPORTED',
            AMBIGUOUS: 'UNSUPPORTED', SLICE: 'UNSUPPORTED', INCOMPLETE: 'UNAVAILABLE',
            WORKSPACE: 'EXCLUDED'}
FLAGS = {'label': 'SIMULATED', 'hypothetical': True, 'applied': False,
         'margin_call_recorded': False, 'default_eligibility_changed': False,
         'journal_written': False, 'funds_executed': False, 'policy_adopted': False}


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def utf8(value):
    return value.encode('utf-8')


def nonnegative(value):
    return type(value) is int and value >= 0


def load_policy(path=None):
    note = resources.read_note(resources.note_path('CAPITAL_REFUND_FRONTIER.md') if path is None else path,
                               override=path is not None)
    block = note['block'] or {}
    entries = block.get('entries', {})
    status, reason = 'BOUND', None
    if (block.get('decision_id') != 'refund-frontier-decision'
            or block.get('status') != 'PROVISIONAL_PRODUCT_DECISION'
            or any(entries.get(k, {}).get('status') != 'ADOPTED' for k in _SUPPORTED)):
        status, reason = 'NOT_BOUND', 'FRONTIER_POLICY_MISSING_OR_DEFERRED'
    elif any(digest(entries[k].get('value')) != expected for k, expected in _SUPPORTED.items()):
        status, reason = 'UNSUPPORTED', 'FRONTIER_POLICY_SEMANTICS_UNSUPPORTED'
    return {'status': status, 'reason': reason, **resources.provenance(note), 'block': block}


@dataclass(frozen=True)
class FrozenInputs:
    raw: bytes

    @classmethod
    def capture(cls, value):
        return cls(canonical_bytes(value))

    def detached(self):
        return json.loads(self.raw)


def registry_evidence(entries, folded, claim_ids):
    """Only a full successful fold plus explicit complete lookups proves absence."""
    return {'overlay_journal_digest': digest(entries), 'overlay_journal_count': len(entries),
            'fold_success': folded is not None, 'capture_complete': True,
            'section_present': folded is not None and 'claim_slices' in folded,
            'queried_claim_ids': sorted(claim_ids, key=utf8),
            'lookups': {key: [copy.deepcopy(row) for _, row in sorted(slices.registry(folded).items())
                              if row['claim_id'] == key] for key in sorted(claim_ids, key=utf8)}
            if folded is not None else {}}


def _status(row, status, reason=None, frontier=None):
    row.update(status=status, outcome=OUTCOMES[status], reason=reason, frontier_krw=frontier)
    return row


def _normalize(subject, data):
    case = subject.get('case') or {}
    row = {'advance_id': subject['advance_id'], 'claim_id': case.get('claim_id'),
           'beneficiary_role': case.get('beneficiary_role'), 'phase': case.get('phase'),
           'writeoff': subject.get('writeoff', False), 'outstanding_krw': subject.get('principal') if nonnegative(subject.get('principal')) else None,
           'gate': subject.get('gate'), 'draw_day': subject.get('draw_day'),
           'margin_terms': subject.get('margin'), 'input_binding': 'NOT_BOUND', 'lines': [],
           'domain_max_krw': None, 'witness': None}
    if row['phase'] in ('CLOSED', 'DEFAULTED') or row['writeoff']:
        return _status(row, TERMINAL)
    policy = data['policy']
    if policy['status'] != 'BOUND':
        return _status(row, MISSING if policy['status'] == 'NOT_BOUND' else UNSUPPORTED, policy['reason'])
    if data['workspace'] != margin.SOURCE_DISPOSABLE:
        return _status(row, WORKSPACE, 'IMMUTABLE_FIXTURE')
    if not nonnegative(row['outstanding_krw']):
        return _status(row, MISSING, 'EXPOSURE_MISSING')
    claim, terms = subject.get('claim'), subject.get('margin')
    if (not row['gate'] or not nonnegative(row['draw_day']) or not terms
            or not terms.get('payees') or type(claim) is not dict
            or row['claim_id'] != claim.get('claim_id') or subject.get('mapping_valid') is False):
        return _status(row, MISSING, 'CLAIM_MAPPING_OR_TERMS_MISSING')
    payees, rate = terms['payees'], terms.get('advance_rate_bps')
    eligible = margin.eligible_face(claim, payees)
    if eligible is None:
        return _status(row, MISSING, 'ELIGIBLE_FACE_UNAVAILABLE')
    mapped = [line for line in claim['obligations'] if type(line) is dict and line.get('payee') in payees]
    if not mapped:
        return _status(row, MISSING, 'MAPPED_LINES_EMPTY')
    if row['outstanding_krw'] == 0:
        # Structural absence is not collateral zero. Once the mapped claim and
        # its authoritative eligible face are known, strict breach is impossible
        # for zero debt, regardless of positive-exposure support restrictions.
        row['domain_max_krw'] = eligible
        return _status(row, ZERO)
    if not nonnegative(rate) or rate > BPS_SCALE:
        return _status(row, UNSUPPORTED, 'RATE_SHAPE_UNSUPPORTED')
    lines = {}
    for line in mapped:
        refund = 0 if claim['refund_face'] == 0 else line.get('refund_open_krw')
        attribution = 'ZERO_CLAIM_REFUND' if claim['refund_face'] == 0 else line.get('refund_attribution_source')
        if not nonnegative(refund) or not isinstance(attribution, str) or not attribution:
            return _status(row, MISSING, 'REFUND_LINE_ATTRIBUTION_MISSING')
        value = {'claim_id': row['claim_id'], 'payee_label': line['payee'],
                 'outstanding_krw': line['outstanding'], 'refund_open_krw': refund,
                 'attribution_source': attribution, 'eligible_krw': max(0, line['outstanding'] - refund)}
        key = (row['claim_id'], line['payee'])
        if key in lines and lines[key] != value:
            return _status(row, UNSUPPORTED, 'CONFLICTING_PHYSICAL_LINE')
        lines[key] = value
    row['lines'] = sorted(lines.values(), key=lambda v: (utf8(v['claim_id']), utf8(v['payee_label'])))
    row['domain_max_krw'] = sum(v['eligible_krw'] for v in row['lines'])
    if row['domain_max_krw'] != eligible:
        return _status(row, UNSUPPORTED, 'ELIGIBLE_FACE_RECONCILIATION_FAILED')
    evidence = data.get('registry', {})
    claim_id = row['claim_id']
    if (evidence.get('fold_success') is not True or evidence.get('capture_complete') is not True
            or claim_id not in evidence.get('queried_claim_ids', [])
            or claim_id not in evidence.get('lookups', {})
            or not isinstance(evidence.get('overlay_journal_digest'), str)
            or not nonnegative(evidence.get('overlay_journal_count'))):
        return _status(row, MISSING, 'REGISTRY_EVIDENCE_MISSING')
    try:
        for entry in evidence['lookups'][claim_id]:
            if entry['status'] == 'PROPOSED':
                continue
            if entry['status'] not in ('OPEN', 'IMPAIRED', 'RESOLVED', 'VOID'):
                return _status(row, UNSUPPORTED, 'REGISTRY_STATUS_UNSUPPORTED')
            obs = slices.observation(claim, [line['payee'] for line in claim['obligations']])
            residual = slices.derived(entry, obs)['outstanding_krw']
            if residual > 0:
                return _status(row, SLICE, 'POSITIVE_RESIDUAL_ENCUMBRANCE')
    except (KeyError, TypeError, ValueError):
        return _status(row, MISSING, 'REGISTRY_OBSERVATION_MISSING')
    row['input_binding'] = 'BOUND'
    baseline = _evaluate(subject, row, {})
    if baseline is None:
        return _status(row, UNSUPPORTED, 'MARGIN_PREDICATE_DISAGREEMENT')
    if baseline['breach']:
        return _status(row, ALREADY, frontier=0)
    # Inclusive endpoint checks; at E every supported positive debt breaches.
    endpoint = _evaluate(subject, row, {(v['claim_id'], v['payee_label']): v['eligible_krw'] for v in row['lines']})
    if endpoint is None or not endpoint['breach']:
        return _status(row, UNSUPPORTED, 'DOMAIN_ENDPOINT_DISAGREEMENT')
    lo, hi = 0, eligible
    while hi - lo > 1:
        mid = (lo + hi) // 2
        allocation = _allocation(row, mid)
        measured = _evaluate(subject, row, allocation)
        if measured is None:
            return _status(row, UNSUPPORTED, 'MARGIN_PREDICATE_DISAGREEMENT')
        if measured['breach']:
            hi = mid
        else:
            lo = mid
    inverse = eligible - (BPS_SCALE * row['outstanding_krw'] - 1) // rate
    if inverse != hi:
        return _status(row, UNSUPPORTED, 'INVERSE_DISAGREEMENT')
    return _status(row, FIRST, frontier=hi)


def _allocation(row, amount):
    result = {}
    for line in row['lines']:
        value = min(amount, line['eligible_krw'])
        result[(line['claim_id'], line['payee_label'])] = value
        amount -= value
    return result


def _evaluate(subject, row, allocation):
    shifted = copy.deepcopy(subject)
    delta = sum(allocation.get((line['claim_id'], line['payee_label']), 0) for line in row['lines'])
    shifted['claim']['refund_face'] += delta
    measured = margin.measure(shifted)
    if measured is None or measured['eligible_face_krw'] != row['domain_max_krw'] - delta:
        return None
    expected = (row['domain_max_krw'] - delta) * row['margin_terms']['advance_rate_bps'] // BPS_SCALE
    if measured['base_krw'] != expected or measured['breach'] != (row['outstanding_krw'] > expected):
        return None
    return measured


def _witness(selected, rows, subjects, complete):
    allocation = _allocation(selected, selected['frontier_krw'])
    previous = dict(allocation) if selected['frontier_krw'] else None
    if previous is not None:
        for key in reversed(previous):
            if previous[key]:
                previous[key] -= 1
                break
    def encoded(values):
        return None if values is None else [{'claim_id': k[0], 'payee_label': k[1], 'refund_krw': v}
                                            for k, v in values.items()]
    def evaluations(values):
        if values is None:
            return None
        out = []
        for row in rows:
            measured = None
            if row['status'] in (FIRST, ALREADY):
                measured = _evaluate(subjects[row['advance_id']], row, values)
            elif row['status'] == ZERO:
                shifted = copy.deepcopy(subjects[row['advance_id']])
                shifted['claim']['refund_face'] += sum(values.get((row['claim_id'], payee), 0)
                                                      for payee in set(shifted['margin']['payees']))
                measured = margin.measure(shifted)
            out.append({'advance_id': row['advance_id'], 'status': row['status'],
                        'reason': row['reason'], 'evaluation': measured})
        return out
    shocked = {key for key, value in allocation.items() if value}
    affected = [row['advance_id'] for row in rows if any(
        (row['claim_id'], payee) in shocked
        for payee in (subjects[row['advance_id']].get('margin') or {}).get('payees', []))]
    return {'frontier_krw': selected['frontier_krw'], 'selected_advance_id': selected['advance_id'],
            'affected_advance_ids': affected,
            'allocation': encoded(allocation), 'predecessor_allocation': encoded(previous),
            'advance_evaluations_at_frontier': evaluations(allocation),
            'advance_evaluations_at_predecessor': evaluations(previous), 'evaluation_complete': complete}


def build(frozen):
    data = frozen.detached()
    subjects = {s['advance_id']: s for s in data['subjects']}
    rows = [_normalize(subjects[k], data) for k in sorted(subjects, key=utf8)]
    physical, owners, conflicts = {}, {}, set()
    # Ownership is structural evidence even when exposure/refund inputs are missing.
    # Do not hide a known overlap just because one linked case cannot be measured.
    for row in rows:
        if row['status'] in (TERMINAL, WORKSPACE, ZERO):
            continue
        subject = subjects[row['advance_id']]
        claim, terms = subject.get('claim'), subject.get('margin')
        if type(claim) is not dict or type(terms) is not dict or type(claim.get('obligations')) is not list:
            continue
        for line in claim['obligations']:
            if type(line) is dict and line.get('payee') in terms.get('payees', []):
                key = (row['claim_id'], line['payee'])
                owners.setdefault(key, set()).add(row['beneficiary_role'])
    for row in rows:
        for line in row['lines']:
            key = (line['claim_id'], line['payee_label'])
            if key in physical and physical[key] != line:
                conflicts.add(key)
            physical[key] = line
            owners.setdefault(key, set()).add(row['beneficiary_role'])
    for row in rows:
        keys = {(line['claim_id'], line['payee_label']) for line in row['lines']}
        mapped = subjects[row['advance_id']].get('margin') or {}
        keys.update((row['claim_id'], payee) for payee in mapped.get('payees', []))
        if row['status'] not in (TERMINAL, WORKSPACE, ZERO, MISSING):
            if keys & conflicts:
                _status(row, UNSUPPORTED, 'CONFLICTING_PHYSICAL_LINE')
            elif any(len(owners.get(k, set())) > 1 for k in keys):
                _status(row, AMBIGUOUS, 'CROSS_BENEFICIARY_LINE_OVERLAP')
    assessed = (FIRST, ALREADY, ZERO)
    def complete(group):
        return all(r['status'] in (*assessed, TERMINAL) for r in group)
    def summary(group):
        numeric = [r for r in group if r['frontier_krw'] is not None]
        selected = min(numeric, key=lambda r: (r['frontier_krw'], utf8(r['advance_id']))) if numeric else None
        done = complete(group)
        if selected and (done or selected['frontier_krw'] == 0):
            status, value = selected['status'], selected['frontier_krw']
            witness = _witness(selected, group, subjects, done)
        else:
            status = INCOMPLETE if not done else (TERMINAL if group and all(r['status'] == TERMINAL for r in group) else ZERO)
            value, witness = None, None
        return {'status': status, 'outcome': OUTCOMES[status], 'frontier_krw': value,
                'evaluation_complete': done, 'witness': witness}
    beneficiaries = []
    for beneficiary in sorted({r['beneficiary_role'] for r in rows}, key=lambda v: utf8(v or '')):
        group = [r for r in rows if r['beneficiary_role'] == beneficiary]
        beneficiaries.append({'beneficiary_role': beneficiary, 'advance_ids': [r['advance_id'] for r in group], **summary(group)})
    for row in rows:
        if row['frontier_krw'] is not None:
            linked = [r for r in rows if r['beneficiary_role'] == row['beneficiary_role']]
            row['witness'] = _witness(row, linked, subjects, complete(linked))
    numeric = [r for r in rows if r['frontier_krw'] is not None]
    chosen = min(numeric, key=lambda r: (r['frontier_krw'], utf8(r['advance_id']))) if numeric else None
    witness = _witness(chosen, rows, subjects, complete(rows)) if chosen else None
    affected = witness['affected_advance_ids'] if witness else []
    body = {**FLAGS, 'status': 'PROVISIONAL_PRODUCT_DECISION', 'provisional': True,
            'cases': rows, 'beneficiaries': beneficiaries,
            'portfolio': {'scope': 'ASSESSED_CASES_ONLY', 'frontier_krw': chosen['frontier_krw'] if chosen else None,
                          'evaluation_complete': complete(rows), 'witness': witness},
            'coverage': {'assessed_ids': [r['advance_id'] for r in rows if r['status'] in assessed],
                         'excluded_ids': [r['advance_id'] for r in rows if r['outcome'] == 'EXCLUDED'],
                         'unavailable_ids': [r['advance_id'] for r in rows if r['outcome'] == 'UNAVAILABLE'],
                         'unsupported_ids': [r['advance_id'] for r in rows if r['outcome'] == 'UNSUPPORTED'],
                         'affected_ids': affected},
            'source': {'workspace': data['workspace'], 'scope': 'SERVICE_MANAGED_MUTATIONS_ONLY',
                       'financial_inputs_digest': digest(data['subjects']),
                       'capture_digest': digest(data['capture']),
                       'registry': {**data['registry'], 'lookups': {key: [
                           {'canonical_row_json': canonical_bytes(row).decode('ascii'), 'row_digest': digest(row)}
                           for row in values] for key, values in data['registry'].get('lookups', {}).items()}}, 'policy': {k: v for k, v in data['policy'].items() if k != 'block'}},
            'inputs_digest': digest(data)}
    body['result_digest'] = digest(body)
    return body
