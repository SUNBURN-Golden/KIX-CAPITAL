"""SIMULATED, offline absolute refund sensitivity over one audited workspace cut.

Measurement projections are disposable, not valid settlement records. No commands,
postings, source mutations, allocation policy, or authenticated history are implied.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

from capital import assets, audit, limits, overlay, resources, risk, margin, strict_json
from capital.evidence import offline_service
from capital.portfolio_snapshot import FrozenInputs, digest
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.protocol import CreditMachine
from capital.projection import SimulationProjection
from capital.service import MAX_OPERATIONS
from capital.store import FILE_NAME, canonical_bytes
from capital.terms import BPS_SCALE, DecisionNoteTermsPolicy

FORMAT = 'KIX_CAPITAL_EVENT_STRESS_REPORT_V1'
REQUIRED_TERMS = ('interest_rate', 'term', 'default_loss_treatment', 'reserve',
                  'additional_margin', 'underwriting_depth')
POLICY_ENTRIES = ('synthetic_event_membership', 'claim_shock_identity', 'shared_claim_counting',
                  'shock_application_order', 'unsupported_position_handling', 'scenario_capacity_bounds')
CAPACITY_KEYS = ('max_request_bytes', 'max_events', 'max_claims_per_event', 'max_membership_edges',
                 'max_scenarios', 'max_snapshot_claims', 'max_snapshot_advances',
                 'max_advance_claim_edges', 'max_event_or_scenario_id_ascii_bytes')
METRICS = ('eligible_face_krw', 'borrowing_base_krw', 'exposure_krw', 'headroom_krw',
           'hypothetical_margin_breaches', 'open_refund_krw')


class StressError(ValueError):
    def __init__(self, code, detail=None, status='REJECTED'):
        self.code, self.detail, self.status = code, detail, status
        super().__init__(code)


def _require(ok, code, detail=None, status='REJECTED'):
    if not ok:
        raise StressError(code, detail, status)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_policy():
    """Only the six adopted entries authorize V1; numeric bounds are read, never copied."""
    note = resources.read_note(resources.note_path('CAPITAL_EVENT_STRESS.md'))
    block = note['block'] or {}
    entries = block.get('entries', {})
    _require(block.get('decision_id') == 'event-stress-scope-decision'
             and block.get('provisional') is True and type(entries) is dict,
             'EVENT_POLICY_NOT_BOUND', status='UNAVAILABLE')
    values = {}
    for name in POLICY_ENTRIES:
        entry = entries.get(name, {})
        _require(entry.get('status') == 'ADOPTED' and type(entry.get('value')) is dict,
                 'EVENT_POLICY_NOT_BOUND', name, 'UNAVAILABLE')
        values[name] = entry['value']
    # Validate categorical semantics as well as entry status. A future policy
    # revision must not silently change the meaning of this implementation.
    expected = {
        'synthetic_event_membership': {'format': 'CAPITAL_EVENT_STRESS_V1',
            'membership': 'EXPLICIT_REQUEST_LOCAL_FULL_CLAIM_IDENTITIES', 'events_per_scenario': 1,
            'empty_event': 'REJECT', 'duplicate_ids_or_members': 'REJECT_REQUEST',
            'unknown_or_ambiguous_claims': 'REJECT_REQUEST',
            'overlap_between_events': 'ALLOW_INDEPENDENT_SCENARIOS',
            'rights_authority_asserted': False, 'real_event_imports': False},
        'claim_shock_identity': {'kind': 'ADDITIONAL_OPEN_REFUND_KRW',
            'parameter': 'additional_open_refund_krw',
            'domain': 'NONNEGATIVE_INTEGER_WITHIN_EXISTING_MONETARY_CONSTRAINTS',
            'target': 'baseline_open_refund_krw + additional_open_refund_krw',
            'identity': ['baseline_identity', 'scenario_id', 'full_claim_identity'],
            'applications_per_member_claim': 1, 'zero_shock': 'FINANCIAL_IDENTITY',
            'arithmetic': 'EXISTING_SINGLE_CLAIM_REFUND_SCENARIO_EVALUATOR'},
        'shared_claim_counting': {'claim_view': 'ONE_SHARED_TRANSFORMED_VIEW',
            'collateral_counting': 'UNIQUE_FULL_CLAIM_IDENTITY',
            'exposure_counting': 'UNIQUE_ADVANCE_IDENTITY_WITH_EXISTING_INCLUSION_RULES',
            'duplicate_relationship_edges': 'REJECT_REQUEST', 'allocation': 'EXISTING_SUPPORTED_RULES_ONLY',
            'unsupported_allocation': 'NULL_DEPENDENT_METRICS', 'per_advance_claim_context': 'NON_ADDITIVE'},
        'shock_application_order': {'order': ['VALIDATE', 'CAPTURE_CONSISTENT_SNAPSHOT',
            'EVALUATE_BASELINE', 'TRANSFORM_UNIQUE_MEMBER_CLAIMS', 'RECOMPUTE_EXISTING_RISK',
            'AGGREGATE_AND_COMPARE'], 'scenario_baseline': 'SAME_IMMUTABLE_SNAPSHOT',
            'outside_claims': 'UNCHANGED_AND_RETAINED', 'terms': 'SAME_EXISTING_TERMS_SNAPSHOT',
            'ordering': 'CANONICAL_IDENTIFIERS', 'commands_emitted': False,
            'missing_snapshot_or_terms': 'UNAVAILABLE_DEPENDENT_METRICS'},
        'unsupported_position_handling': {'invalid_request': 'REJECT_ATOMICALLY',
            'known_unsupported_position': 'RETAIN_WITH_REASON_AND_NULL_AFFECTED_METRICS',
            'dependent_aggregates_and_deltas': 'NULL',
            'supported_subtotals': 'EXPLICIT_SCOPE_AND_EXCLUSIONS',
            'coverage': 'INCLUDE_UNSUPPORTED_IDENTITIES_REASONS_AND_COUNTS', 'partial_portfolio_pass': False},
        'scenario_capacity_bounds': {'existing_lower_limits': 'PREVAIL', 'overflow': 'REJECT_ATOMICALLY',
            'truncation': False, 'probability_models': False},
    }
    for name, fields in expected.items():
        for key, value in fields.items():
            _require(type(values[name].get(key)) is type(value) and values[name][key] == value,
                     'EVENT_POLICY_NOT_BOUND', name + '.' + key, 'UNAVAILABLE')
    bounds = values['scenario_capacity_bounds']
    _require(all(type(bounds.get(key)) is int and bounds[key] > 0 for key in CAPACITY_KEYS),
             'EVENT_POLICY_NOT_BOUND', 'capacity', 'UNAVAILABLE')
    binding = resources.read_note(resources.note_path('CAPITAL_EVENT_STRESS_BINDING.md'))
    adopted = (binding['block'] or {}).get('entries', {}).get('absolute_refund_measurement', {})
    _require(adopted.get('status') == 'ADOPTED' and adopted.get('value') == {
        'adapter_version': 'CAPITAL_EVENT_STRESS_MEASUREMENT_V1',
        'measurement': 'capital.margin.measure', 'allocation': 'NOT_BOUND'},
        'EVENT_MEASUREMENT_NOT_BOUND', status='UNAVAILABLE')
    return {'values': values, 'event_note_sha256': note['note_sha256'],
            'binding_note_sha256': binding['note_sha256']}


def _shape(value, keys):
    _require(type(value) is dict and set(value) == set(keys), 'INVALID_REQUEST_SHAPE')


def _ident(value):
    # Existing F04 identifier validation, retained for claim and trade identity.
    return type(value) is str and 0 < len(value) <= 100 and value.strip() == value


def _identity(ref):
    _shape(ref, ('claim_id', 'trade_id', 'currency'))
    _require(all(_ident(ref[k]) for k in ('claim_id', 'trade_id')) and ref['currency'] == 'KRW',
             'INVALID_CLAIM_IDENTITY')
    return tuple(ref[k] for k in ('claim_id', 'trade_id', 'currency'))


def claim_ref(claim):
    return {k: claim[k] for k in ('claim_id', 'trade_id', 'currency')}


def validate_request(raw, policy):
    bounds = policy['values']['scenario_capacity_bounds']
    _require(type(raw) is bytes, 'INVALID_REQUEST_ENCODING')
    _require(len(raw) <= min(bounds['max_request_bytes'], limits.MAX_REQUEST_BYTES),
             'SCENARIO_CAPACITY_EXCEEDED', 'request_bytes')
    try:
        request = strict_json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise StressError('INVALID_REQUEST_JSON') from None
    _shape(request, ('format', 'events', 'scenarios'))
    _require(request['format'] == policy['values']['synthetic_event_membership']['format'], 'INVALID_REQUEST_FORMAT')
    for field, bound in (('events', 'max_events'), ('scenarios', 'max_scenarios')):
        _require(type(request[field]) is list and request[field], 'INVALID_REQUEST_SHAPE')
        _require(len(request[field]) <= bounds[bound], 'SCENARIO_CAPACITY_EXCEEDED', field)
    def request_id(value):
        _require(type(value) is str and re.fullmatch(r'[A-Za-z0-9._-]+', value) is not None
                 and len(value) <= bounds['max_event_or_scenario_id_ascii_bytes'], 'INVALID_REQUEST_ID')
    seen, edges = set(), 0
    events = []
    for event in request['events']:
        _shape(event, ('event_id', 'claim_refs'))
        request_id(event['event_id'])
        _require(event['event_id'] not in seen, 'DUPLICATE_EVENT_ID')
        seen.add(event['event_id'])
        refs = event['claim_refs']
        _require(type(refs) is list and refs, 'INVALID_MEMBERSHIP')
        _require(len(refs) <= bounds['max_claims_per_event'], 'SCENARIO_CAPACITY_EXCEEDED', 'claims_per_event')
        ids = [_identity(ref) for ref in refs]
        _require(len(set(ids)) == len(ids), 'DUPLICATE_MEMBERSHIP')
        edges += len(ids)
        events.append({**event, 'claim_refs': sorted(refs, key=_identity)})
    _require(edges <= bounds['max_membership_edges'], 'SCENARIO_CAPACITY_EXCEEDED', 'membership_edges')
    scenarios, scenario_ids = [], set()
    for scenario in request['scenarios']:
        _shape(scenario, ('scenario_id', 'event_id', 'kind', 'additional_open_refund_krw'))
        request_id(scenario['scenario_id'])
        request_id(scenario['event_id'])
        _require(scenario['scenario_id'] not in scenario_ids, 'DUPLICATE_SCENARIO_ID')
        scenario_ids.add(scenario['scenario_id'])
        _require(scenario['event_id'] in seen, 'UNKNOWN_EVENT')
        _require(scenario['kind'] == policy['values']['claim_shock_identity']['kind'], 'UNSUPPORTED_SHOCK_KIND')
        amount = scenario['additional_open_refund_krw']
        _require(type(amount) is int and 0 <= amount <= assets.KRW['max_atoms'], 'INVALID_SHOCK_AMOUNT')
        scenarios.append(scenario)
    return {**request, 'events': sorted(events, key=lambda e: e['event_id']),
            'scenarios': sorted(scenarios, key=lambda s: s['scenario_id'])}


def _capacity(data, bounds):
    captured = data['producer']
    state = json.loads(captured['canonical_state'])
    checks = {'claims': (len(captured['fixtures']['rows']), bounds['max_snapshot_claims']),
              'advances': (len(state['cases']), min(bounds['max_snapshot_advances'], MAX_OPERATIONS)),
              'relationships': (len(data['case_fixtures']), bounds['max_advance_claim_edges']),
              'receipts': (len(data['receipts']), MAX_OPERATIONS)}
    ob = data['policy']['bounds']
    _require(type(ob) is dict and all(type(ob.get(k)) is int and ob[k] > 0 for k in overlay.BOUND_NAMES),
             'TERMS_NOT_BOUND', 'overlay_bounds', 'UNAVAILABLE')
    entries = data['overlay_entries']
    folded = overlay.fold(entries, len(state['journal']))
    payload = {'journal': state['journal'], 'state_digest': captured['state_digest'],
               'case_fixtures': data['case_fixtures'], 'receipts': data['receipts']}
    checks.update(overlay_entries=(len(entries), ob['OVERLAY_MAX_ENTRIES']),
                  overlay_entry_bytes=(max((overlay.entry_size(e) for e in entries), default=0), ob['OVERLAY_ENTRY_MAX_BYTES']),
                  decision_records=(sum(e['kind'] in (overlay.KIND_TERMS, *overlay.MARGIN_KINDS,
                       'default_anchor', 'acceleration_event') for e in entries), ob['DECISION_RECORDS_MAX']),
                  envelope_bytes=(overlay.section_size(payload, entries), ob['ENVELOPE_MAX_BYTES']),
                  sim_day=(folded['sim_day'], ob['SIM_DAY_MAX']))
    for name, (count, limit) in checks.items():
        _require(count <= limit, 'SCENARIO_CAPACITY_EXCEEDED', name)
    return state, folded


def prepare(frozen, policy):
    """Reconcile a detached capture and freeze every baseline financial binding."""
    data = frozen.detached()
    state, folded = _capacity(data, policy['values']['scenario_capacity_bounds'])
    captured, saved = data['producer'], data['policy']
    terms = DecisionNoteTermsPolicy.__new__(DecisionNoteTermsPolicy)
    terms.items, terms.version = json.loads(data['policy_items_json']), saved['version']
    terms.top, terms.reason = saved['top'], saved['reason']
    _require(terms.top in ('BOUND', 'PARTIAL') and terms._ready(*REQUIRED_TERMS) and risk.usable(terms),
             'TERMS_NOT_BOUND', status='UNAVAILABLE')
    binding = folded['terms_binding']
    _require(binding is None or (binding['terms_version'] == terms.version
             and binding['status'] in ('BOUND', 'PARTIAL')), 'TERMS_BINDING_INCOMPATIBLE', status='UNAVAILABLE')
    fixtures = captured['fixtures']
    views = FixtureViews.__new__(FixtureViews)
    views.rows, views.profiles = fixtures['rows'], fixtures['profiles']
    views.beneficiaries, views.projection_ids = fixtures['beneficiaries'], frozenset(fixtures['projection_ids'])
    scratch = PinnedFsmProducer(views, CreditMachine.restore(state['journal'], views))
    _require(scratch.canonical_state() == captured['canonical_state'], 'CAPTURE_STATE_MISMATCH', status='UNAVAILABLE')
    cases = {c['advance_id']: c for c in state['cases']}
    _require(len(cases) == len(state['cases']) and set(cases) == set(data['case_fixtures']),
             'INVALID_RELATIONSHIPS')
    claims, fixture_keys = {}, {}
    for key, row in sorted(fixtures['rows'].items()):
        claim = row['claim']
        identity = _identity(claim_ref(claim))
        _require(identity not in claims, 'AMBIGUOUS_CLAIM_IDENTITY', claim_ref(claim))
        claims[identity], fixture_keys[key] = claim, identity
    linked = {key: [] for key in claims}
    for key, case in sorted(cases.items()):
        fixture = data['case_fixtures'][key]
        _require(fixture in fixture_keys and case['claim_id'] == fixture
                 and _identity(claim_ref(case)) == fixture_keys[fixture], 'INVALID_RELATIONSHIPS')
        linked[fixture_keys[fixture]].append(key)
    drawn, gates = [], {}
    for index, row in enumerate(state['journal']):
        if row['op'] != 'draw':
            continue
        key = row['advance_id']
        _require(key not in gates, 'DUPLICATE_RELATIONSHIP_EDGE')
        receipt = data['receipts'].get(row['idempotency_key'], {}).get('receipt', {})
        result = receipt.get('result')
        credit = result.get('credit') if type(result) is dict else None
        gate = credit.get('settlement_gate') if type(credit) is dict else None
        _require(receipt.get('outcome') == 'ACCEPTED' and type(gate) is str and bool(gate),
                 'DRAW_RECEIPT_GATE_MISSING', key, 'UNAVAILABLE')
        gates[key] = gate
        case = cases[key]
        claim = claims[fixture_keys[data['case_fixtures'][key]]]
        args = {'gate': gate, 'draw_day': overlay.draw_day_for(data['overlay_entries'], index)}
        drawn.append({'advance_id': key, 'case': case, 'claim': claim, **args,
                      'principal': case['outstanding_exposure'],
                      'ledger': terms.ledger_terms(case, claim, **args),
                      'margin': terms.margin_terms(case, claim, **args, refund_after_draw=False)})
    drawn.sort(key=lambda s: s['advance_id'])
    # risk.build is evaluated ONLY on baseline claims. Its relative stress table
    # is excluded; unchanged exposure, reserve, tier and timing folds are retained.
    # Reconcile the complete F04 exposure journal independently of unsupported
    # settlement claims. Claim equations are checked per row below; a malformed
    # outside claim must not erase known exposure or improve collateral totals.
    projection = SimulationProjection().project(state['journal'], [])
    projected_outstanding = sum(r['outstanding'] for r in projection['read_model']['advances'])
    baseline_risk = risk.build(drawn, [s for s in drawn if s['margin'] is not None], terms=terms,
                              sim_day=folded['sim_day'], projection_outstanding_krw=projected_outstanding)
    _require(baseline_risk['reconciliation']['matched'], 'EXPOSURE_RECONCILIATION_FAILED', status='UNAVAILABLE')
    baseline_risk.pop('stress')
    baseline_risk.pop('risk_digest')
    encumbered = {e['payload'].get('claim_id') for e in data['overlay_entries']
                  if e['kind'] == 'SLICE_PROPOSE'}
    provenance = {'state_digest': captured['state_digest'], 'overlay_state_digest': overlay.state_digest(folded),
                  'sim_day': folded['sim_day'], 'fixtures_digest': digest(fixtures),
                  'policy_inputs_digest': digest(saved), 'terms_version': terms.version,
                  'terms_provenance': data.get('terms_provenance', {'notes_source': 'NOT_BOUND', 'note_sha256': None})}
    provenance['inputs_digest'] = digest({'producer': captured, 'case_fixtures': data['case_fixtures'],
        'draw_gates': gates, 'overlay_entries': data['overlay_entries'], 'policy': saved,
        'policy_items_json': data['policy_items_json'], 'terms_provenance': provenance['terms_provenance']})
    return {'claims': claims, 'linked': linked, 'drawn': drawn, 'cases': cases,
            'fixture_keys': {identity: key for key, identity in fixture_keys.items()},
            'fixtures': fixtures, 'terms': terms, 'encumbered': encumbered,
            'risk': baseline_risk, 'inputs': provenance}


def _claim_invariants(claim):
    """Validate original source equations, never repair or rewrite a settlement."""
    try:
        fields = ('gross', 'refund_face', 'refund_accepted', 'refund_outstanding', 'receivable_open',
                  'confirmed_cash', 'non_cash_accounted', 'distributed_cash', 'undistributed_cash',
                  'recovery_due', 'pg_adjustment_outstanding')
        if any(type(claim[k]) is not int or not 0 <= claim[k] <= assets.KRW['max_atoms'] for k in fields):
            return False
        lines = claim['obligations']
        if type(lines) is not list or not lines or len({l['payee'] for l in lines}) != len(lines):
            return False
        for line in lines:
            if not _ident(line['payee']) or any(type(line[k]) is not int or line[k] < 0 for k in
                ('face', 'distributed', 'cancelled_unpaid', 'recovery_due', 'outstanding')):
                return False
            if (line['face'] != line['distributed'] + line['cancelled_unpaid'] + line['outstanding']
                    or line['recovery_due'] > line['distributed']):
                return False
        return (sum(l['face'] for l in lines) == claim['gross']
            and claim['confirmed_cash'] + claim['non_cash_accounted'] + claim['receivable_open'] == claim['gross']
            and sum(l['distributed'] for l in lines) == claim['distributed_cash']
            and claim['confirmed_cash'] == claim['distributed_cash'] + claim['undistributed_cash']
            and claim['refund_accepted'] <= claim['refund_face'] <= claim['gross']
            and claim['refund_outstanding'] == claim['refund_face'] - claim['refund_accepted']
            and claim['pg_adjustment_outstanding'] == claim['refund_accepted']
            and claim['recovery_due'] == sum(l['recovery_due'] for l in lines)
            and type(claim['fixture_reclassified']) is bool
            and (all(l['outstanding'] == 0 and l['recovery_due'] == l['distributed'] for l in lines)
                 and claim['refund_face'] == claim['gross'] if claim['fixture_reclassified'] else
                 all(l['cancelled_unpaid'] == l['recovery_due'] == 0 for l in lines)
                 and claim['undistributed_cash'] <= sum(l['outstanding'] for l in lines)))
    except (KeyError, TypeError, ValueError):
        return False


def _sum(rows, name):
    values = [r[name] for r in rows]
    return None if any(v is None for v in values) else sum(values)


def _totals(claims, advances):
    return {'eligible_face_krw': _sum(claims, 'eligible_face_krw'),
            'borrowing_base_krw': _sum(advances, 'borrowing_base_krw'),
            'exposure_krw': _sum(advances, 'exposure_krw'), 'headroom_krw': _sum(advances, 'headroom_krw'),
            'hypothetical_margin_breaches': _sum(advances, 'hypothetical_margin_breaches'),
            'open_refund_krw': _sum(claims, 'open_refund_krw')}


def _delta(left, right):
    return {k: None if left[k] is None or right[k] is None else right[k] - left[k] for k in METRICS}


def measure_portfolio(prepared, members=(), increment=0):
    """Pure detached measurement; each full claim identity is projected exactly once."""
    members = set(members)
    claim_rows, projected = [], {}
    by_claim = {key: [] for key in prepared['claims']}
    for s in prepared['drawn']:
        by_claim[_identity(claim_ref(s['claim']))].append(s)
    payee_map = prepared['terms']._value('additional_margin')['beneficiary_payee_map']
    for identity, claim in sorted(prepared['claims'].items()):
        subjects = by_claim[identity]
        reasons = []
        valid = _claim_invariants(claim)
        original = claim.get('refund_face')
        bump = increment if identity in members else 0
        refund = original + bump if type(original) is int else None
        if refund is not None and valid:
            _require(refund <= claim['gross'] and refund <= assets.KRW['max_atoms'],
                     'REFUND_EXCEEDS_MONETARY_DOMAIN', claim_ref(claim))
        fixture = prepared['fixture_keys'][identity]
        mappings = [s['margin']['payees'] for s in subjects if s['margin'] is not None]
        # Unfinanced fixtures have an authoritative fixture beneficiary/payee
        # map, but no hypothetical rate or available borrowing permission.
        if not subjects:
            mappings = [payee_map.get(prepared['fixtures']['beneficiaries'][fixture])]
        payees = sorted(mappings[0]) if mappings and type(mappings[0]) is list else None
        if not mappings or any(p is None or sorted(p) != payees for p in mappings):
            payees = None
        if not valid:
            reasons.append('CLAIM_INVARIANTS_NOT_BOUND')
        if (not valid or claim.get('refund_accepted') != 0 or claim.get('fixture_reclassified') is not False
                or payees is None or not payees or len(set(payees)) != len(payees)
                or any(p not in {l['payee'] for l in claim.get('obligations', [])} for p in payees)):
            reasons.append('REFUND_MAPPING_NOT_BOUND')
        mapped = (sum(l['outstanding'] for l in claim['obligations'] if l['payee'] in payees)
                  if valid and payees is not None else None)
        if mapped is not None and refund is not None and refund > mapped:
            reasons.append('REFUND_MAPPING_NOT_BOUND')
        if any(s['margin'] is None or s['ledger'] is None for s in subjects):
            reasons.append('APPLICABLE_TERMS_NOT_BOUND')
        if (claim['claim_id'] in prepared['encumbered']
                or any(claim.get(k) for k in ('holder', 'holder_role', 'slices', 'claim_slices'))):
            reasons.append('REFUND_MAPPING_NOT_BOUND')
        projection = {'obligations': copy.deepcopy(claim.get('obligations')), 'refund_face': refund}
        projected[identity] = projection
        eligible = margin.eligible_face(projection, payees) if not reasons else None
        contexts = []
        for s in subjects:
            measured = margin.measure({**s, 'claim': projection}) if eligible is not None else None
            contexts.append({'advance_id': s['advance_id'], 'frozen_ledger_terms': s['ledger'],
                             'frozen_margin_terms': s['margin'], 'measurement': measured})
        claim_rows.append({'claim_ref': claim_ref(claim), 'member': identity in members,
            'linked_advance_ids': sorted(prepared['linked'][identity]), 'reasons': sorted(set(reasons)),
            'eligible_face_krw': eligible, 'open_refund_krw': refund if valid else None,
            'witness': {'source_claim_digest': digest(claim), 'source_invariants_valid': valid,
                'projection_kind': 'SIMULATED_MEASUREMENT_ONLY', 'baseline_open_refund_krw': original,
                'additional_open_refund_krw': bump, 'applications': 1 if identity in members else 0,
                'hypothetical_open_refund_krw': refund, 'payees': payees, 'mapped_outstanding_krw': mapped,
                'eligible_formula': 'mapped_outstanding - hypothetical_open_refund',
                'base_formula': 'floor(eligible_face * frozen_advance_rate_bps / BPS_SCALE)',
                'bps_scale': BPS_SCALE, 'contexts': contexts, 'context_additivity': 'NON_ADDITIVE'}})
    claims_by_id = {_identity(r['claim_ref']): r for r in claim_rows}
    advances = []
    for s in prepared['drawn']:
        identity = _identity(claim_ref(s['claim']))
        row = claims_by_id[identity]
        reasons = list(row['reasons'])
        # Count reservations as well as drawn exposure; a second reservation
        # cannot grant this advance a second full collateral base.
        reservations = [key for key in prepared['linked'][identity]
                        if prepared['cases'][key].get('note_status') == 'NOTED']
        if (len(by_claim[identity]) > 1 or len(reservations) > 1
                or s['claim']['claim_id'] in prepared['encumbered']):
            reasons.append('UNSUPPORTED_SHARED_ALLOCATION')
        measured = margin.measure({**s, 'claim': projected[identity]}) if not reasons else None
        advances.append({'advance_id': s['advance_id'], 'claim_refs': [row['claim_ref']],
            'claim_context': 'NON_ADDITIVE', 'reasons': sorted(set(reasons)),
            'exposure_krw': s['principal'],
            'borrowing_base_krw': None if measured is None else measured['base_krw'],
            'headroom_krw': None if measured is None else measured['headroom_krw'],
            'hypothetical_margin_breaches': None if measured is None else int(measured['breach']),
            'witness': {'exposure_inclusion': 'RECORDED_DRAW_ONCE',
                'frozen_ledger_terms': s['ledger'], 'frozen_margin_terms': s['margin'],
                'measurement': measured, 'breach_formula': 'exposure > 0 and exposure > base'}})
    inside_claims = [r for r in claim_rows if r['member']]
    inside_advances = [r for r in advances if any(_identity(ref) in members for ref in r['claim_refs'])]
    unsupported_claims = [r['claim_ref'] for r in claim_rows if r['reasons']]
    unsupported_advances = [r['advance_id'] for r in advances if r['reasons']]
    return {'claims': claim_rows, 'advances': advances,
        'portfolio': _totals(claim_rows, advances), 'event': _totals(inside_claims, inside_advances),
        'coverage': {'claims': len(claim_rows), 'advances': len(advances),
            'unsupported_claims': unsupported_claims, 'unsupported_advance_ids': unsupported_advances,
            'unsupported_claim_count': len(unsupported_claims), 'unsupported_advance_count': len(unsupported_advances),
            'complete': not (unsupported_claims or unsupported_advances), 'portfolio_safety_conclusion': 'NOT_ASSERTED'}}


def _envelope():
    return {'format': FORMAT, 'label': 'SIMULATED', 'provisional': True, 'applied': False,
            'funds_executed': False, 'workspace_mutated': False, 'production': 'NOT_AUTHORIZED',
            'historical_policy_authentication': 'NOT_BOUND', 'diagnostics': []}


def _failure(report, exc):
    # Financial results are only installed after EVERY scenario has validated.
    return {**report, 'status': exc.status,
            'diagnostics': [{'code': exc.code, 'detail': exc.detail}]}


def _evaluate(frozen, request, policy, report):
    prepared = prepare(frozen, policy)
    events = {e['event_id']: [_identity(ref) for ref in e['claim_refs']] for e in request['events']}
    for members in events.values():
        for identity in members:
            _require(identity in prepared['claims'], 'UNKNOWN_CLAIM_REFERENCE', dict(zip(
                ('claim_id', 'trade_id', 'currency'), identity)))
    baseline = measure_portfolio(prepared)
    scenarios = []
    for scenario in request['scenarios']:
        members = events[scenario['event_id']]
        before = measure_portfolio(prepared, members)
        stressed = measure_portfolio(prepared, members, scenario['additional_open_refund_krw'])
        body = {**scenario, 'baseline_event': before['event'], 'stressed': stressed,
                'delta': {scope: _delta(before[scope], stressed[scope]) for scope in ('portfolio', 'event')}}
        body['scenario_digest'] = digest({'inputs': prepared['inputs'], 'policy': policy,
            'normalized_request': request, 'calculation': body})
        scenarios.append(body)
    return {**report, 'status': 'COMPLETE' if baseline['coverage']['complete']
            and all(s['stressed']['coverage']['complete'] for s in scenarios) else 'PARTIAL',
        'inputs': {**report.get('inputs', {}), **prepared['inputs']}, 'events': request['events'],
        'aggregation_scope': {'eligible_face': 'UNIQUE_CAPTURED_FIXTURE_CLAIMS',
            'borrowing_base_headroom_breaches': 'RECORDED_DRAWN_ADVANCES_WITH_PROVEN_ALLOCATION',
            'exposure': 'UNIQUE_RECORDED_DRAWN_ADVANCES_CURRENT_OUTSTANDING',
            'unfinanced_claim_rate': 'NOT_BOUND', 'per_advance_claim_context': 'NON_ADDITIVE'},
        'baseline': baseline, 'unchanged_risk_folds': prepared['risk'], 'scenarios': scenarios}


def evaluate_detached(frozen, request_bytes):
    """Pure evaluator of FrozenInputs (no audit attestation); does not mutate it."""
    report = _envelope()
    report['capture_audit'] = 'NOT_ASSERTED_DETACHED_INPUTS'
    try:
        policy = load_policy()
        request = validate_request(request_bytes, policy)
        report.update(policy=policy, raw_request_digest=_sha(request_bytes), normalized_request_digest=digest(request))
        return _evaluate(frozen, request, policy, report)
    except StressError as exc:
        return _failure(report, exc)
    except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError):
        return _failure(report, StressError('CAPTURE_INPUTS_UNUSABLE', status='UNAVAILABLE'))


def report_workspace(directory, request_bytes):
    """Audit, hash and restore exactly one read; no FileWorkspace or filesystem lock."""
    report = _envelope()
    try:
        policy = load_policy()
        request = validate_request(request_bytes, policy)
        report.update(policy=policy, raw_request_digest=_sha(request_bytes), normalized_request_digest=digest(request))
        try:
            raw = (Path(directory) / FILE_NAME).read_bytes()
        except (OSError, ValueError, TypeError):
            raw = None
        audited = audit.audit_workspace_bytes(raw, workspace='CAPTURED_WORKSPACE')
        report['inputs'] = {'workspace_sha256': None if raw is None else _sha(raw),
                            'payload_sha256': audited['payload_sha256']}
        report['capture_audit'] = audited
        _require(audited['ok'], 'WORKSPACE_AUDIT_FAILED', audited['reason'], 'UNAVAILABLE')
        service = offline_service(strict_json.loads(raw))
        try:
            with service.lock:
                frozen = FrozenInputs.capture(service.producer.snapshot_inputs(), service.receipts,
                    service.case_fixtures, service.overlay_entries, service.terms, service.overlay_bounds)
                detached = frozen.detached()
                detached['terms_provenance'] = resources.provenance(service.terms.note)
                frozen = FrozenInputs(canonical_bytes(detached))
        finally:
            service.observability.close()
        return _evaluate(frozen, request, policy, report)
    except StressError as exc:
        return _failure(report, exc)
    except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError) as exc:
        code = str(exc) if str(exc) in ('COHERENT_SNAPSHOT_UNSUPPORTED', 'IMMUTABLE_FIXTURES_REQUIRED') else 'CAPTURE_INPUTS_UNUSABLE'
        return _failure(report, StressError(code, status='UNAVAILABLE'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--spec', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        # Read at most one byte beyond the effective cap, before JSON decoding.
        with args.spec.open('rb') as stream:
            request = stream.read(min(load_policy()['values']['scenario_capacity_bounds']['max_request_bytes'],
                                      limits.MAX_REQUEST_BYTES) + 1)
        report = report_workspace(args.workspace, request)
    except OSError:
        report = _failure(_envelope(), StressError('SPEC_UNREADABLE'))
    except StressError as exc:
        report = _failure(_envelope(), exc)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
