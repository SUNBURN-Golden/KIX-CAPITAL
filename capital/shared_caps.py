"""SIMULATED shared-cap projection; slice face is a conservative policy measure.

Pure calculations on detached local inputs. Version-tagged hashes use canonical
JSON (sorted keys, ASCII, compact separators). Receipt/session metadata, paths,
tokens and timestamps are excluded. No headroom is authority to draw funds.
"""
from __future__ import annotations

import json
import re

from capital import overlay, slices
from capital.portfolio_snapshot import digest
from capital.producer import CreditError, FixtureViews, PinnedFsmProducer
from capital.protocol import CreditMachine
from capital.underwriting import DecisionNoteUnderwriting

FORMAT = 'KIX_CAPITAL_SHARED_CAPS_V1'
BASIS = 'CONSERVATIVE_SLICE_FACE_POLICY_MEASURE'


def diagnostic():
    return {**slices.labels(), 'format': FORMAT, 'status': 'NOT_BOUND',
            'read_only': True, 'workspace_mutated': False, 'write_authorized': False,
            'applied': False, 'enforced': False, 'authenticated_source_cut': 'NOT_BOUND',
            'exposure_basis': BASIS, 'reasons': [],
            'cut': dict.fromkeys(('state_digest', 'overlay_state_digest', 'fixtures_digest',
                                  'policy_inputs_digest', 'inputs_digest', 'sim_day')),
            'beneficiaries': None, 'portfolio': None}


def not_bound(body, reason):
    body.update(status='NOT_BOUND', beneficiaries=None, portfolio=None)
    body['reasons'].append(reason)
    return body


def captured_diagnostic(frozen, policy):
    data = frozen.detached()
    captured = data['producer']
    folded = overlay.fold(data['overlay_entries'])
    body = diagnostic()
    body['cut'].update(state_digest=captured['state_digest'],
                       overlay_state_digest=overlay.state_digest(folded), sim_day=folded['sim_day'],
                       fixtures_digest=digest(captured['fixtures']['rows']),
                       policy_inputs_digest=digest({'format': FORMAT, 'version': 1,
                                                    'underwriting': data['policy'], 'slice_policy': policy}))
    body['cut']['inputs_digest'] = digest({
        'format': FORMAT, 'version': 1, 'cut': {k: v for k, v in body['cut'].items() if k != 'inputs_digest'},
        'fixtures': captured['fixtures'], 'case_fixtures': data['case_fixtures'],
        'overlay_entries': data['overlay_entries']})
    return body


def _policy_valid(data, policy):
    """Fail closed even for an empty book; no filesystem policy reloads."""
    if (type(policy) is not dict or data['policy']['top'] != 'BOUND'
            or type(data['policy']['bounds']) is not dict):
        return False
    items = data['policy']['items']
    if type(items) is not dict:
        return False
    names = ('underwriting_depth', 'additional_margin', 'interest_rate')
    if any(type(items.get(k)) is not dict or items[k].get('mark') != 'ADOPTED'
           or type(items[k].get('value')) is not dict for k in names):
        return False
    depth, margin, interest = (items[k]['value'] for k in names)
    # Reuse U4's rule parser, with the positive-cap condition needed for ratios.
    rules = DecisionNoteUnderwriting(None)._rules(depth)
    if rules is None or any(type(depth[k]) is not int or depth[k] <= 0 for k in slices.CAPS):
        return False
    if rules['threshold'] <= 0:
        return False
    if not any(r['id'] == 'U4_CONCENTRATION' for r in rules['checks']):
        return False
    if (policy.get('caps') != rules['caps'] or policy.get('threshold') != rules['threshold']
            or policy.get('terms_version') != data['policy']['version']
            or policy.get('payees') != margin.get('beneficiary_payee_map')
            or policy.get('rates') != margin.get('advance_rate_bps_by_tier')):
        return False
    if type(policy.get('policy_digest')) is not str or not re.fullmatch('[0-9a-f]{64}', policy['policy_digest']):
        return False
    payees = policy.get('payees')
    if (type(payees) is not dict or not payees
            or any(type(k) is not str or not k or type(v) is not list or not v
                   or any(type(p) is not str or not p for p in v) or len(set(v)) != len(v)
                   for k, v in payees.items())):
        return False
    rates = policy.get('rates')
    if (type(rates) is not dict or not rates
            or any(type(k) is not str or type(v) is not int or not 0 <= v <= 10000 for k, v in rates.items())):
        return False
    for name in ('sizing_rates', 'price_rates', 'bounds'):
        values = policy.get(name)
        if (type(values) is not dict or not values
                or any(type(k) is not str or type(v) is not int or v < (1 if name == 'bounds' else 0)
                       for k, v in values.items())):
            return False
    if any(v > 10000 for v in policy['sizing_rates'].values()):
        return False
    if set(policy['caps']) != set(slices.CAPS) or any(type(v) is not int for v in policy['caps'].values()):
        return False
    tiers = interest.get('tiers')
    if type(tiers) is not list or not tiers:
        return False
    if (policy.get('tier_gates') != {t['condition']['settlement_gate']: t['id'] for t in tiers}
            or policy.get('price_rates') != {t['id']: t['all_in_bps_annual'] for t in tiers}):
        return False
    if not set(policy['tier_gates'].values()) <= (set(rates) & set(policy['sizing_rates'])):
        return False
    return True


def _row(principal, face, cap, cap_ref):
    combined = principal + face
    return {**slices.labels(), 'exposure_basis': BASIS, 'advance_principal_krw': principal,
            'counted_slice_face_krw': face, 'combined_policy_exposure_krw': combined,
            'cap_ref': cap_ref, 'cap_krw': cap, 'remaining_capacity_krw': cap - combined,
            'utilization_permille': combined * 1000 // cap,
            'cap_check': 'PASS' if combined <= cap else 'FAIL'}


def build(frozen, slice_policy):
    """Return deterministic sorted rows from one detached service capture."""
    body = captured_diagnostic(frozen, slice_policy)
    data = frozen.detached()
    try:
        valid = _policy_valid(data, slice_policy)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        valid = False
    if not valid:
        return not_bound(body, 'POLICY_INPUTS_NOT_BOUND')
    try:
        captured = data['producer']
        state = json.loads(captured['canonical_state'])
        cases = {c['advance_id']: c for c in state['cases']}
        fixtures = captured['fixtures']
        views = FixtureViews.__new__(FixtureViews)
        views.rows, views.profiles = fixtures['rows'], fixtures['profiles']
        views.beneficiaries, views.projection_ids = fixtures['beneficiaries'], frozenset(fixtures['projection_ids'])
        scratch = PinnedFsmProducer(views, CreditMachine.restore(state['journal'], views))
        if (scratch.canonical_state() != captured['canonical_state']
                or set(cases) != set(data['case_fixtures'])
                or digest(state) != captured['state_digest']):
            raise ValueError('capture state mismatch')
        folded = overlay.fold(data['overlay_entries'], len(state['journal']))
        observations = {}
        for claim_id, view in sorted(views.rows.items()):
            beneficiary = views.beneficiary(claim_id)
            if beneficiary not in slice_policy['payees']:
                raise ValueError('missing payee mapping')
            observations[claim_id] = slices.observation(view['claim'], slice_policy['payees'][beneficiary])
        principal = {}
        for key, case in sorted(cases.items()):
            claim = data['case_fixtures'][key]
            beneficiary = case['beneficiary_role']
            if claim != case['claim_id'] or views.beneficiary(claim) != beneficiary:
                raise ValueError('case mapping mismatch')
            amount = case['outstanding_exposure']
            if type(amount) is not int or amount < 0:
                raise ValueError('unusable principal')
            principal[beneficiary] = principal.get(beneficiary, 0) + amount
        for row in slices.registry(folded).values():
            if views.beneficiary(row['claim_id']) != row['beneficiary_role']:
                raise ValueError('slice mapping mismatch')
            principal.setdefault(row['beneficiary_role'], 0)
        rows = []
        for beneficiary in sorted(principal):
            face = slices.exposures(folded, observations, beneficiary)['slice_exposure_beneficiary_krw']
            rows.append({'beneficiary_role': beneficiary, **_row(
                principal[beneficiary], face, slice_policy['caps']['beneficiary_aggregate_cap_krw'],
                'beneficiary_aggregate_cap_krw')})
        total_face = slices.exposures(folded, observations, None)['slice_exposure_portfolio_krw']
        body.update(status='BOUND', beneficiaries=rows, portfolio=_row(
            sum(principal.values()), total_face, slice_policy['caps']['portfolio_cap_krw'], 'portfolio_cap_krw'))
        return body
    except (CreditError, KeyError, TypeError, ValueError, ArithmeticError):
        return not_bound(body, 'CAPTURE_RECONCILIATION_FAILED')
