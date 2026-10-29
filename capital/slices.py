"""Provisional SIMULATED claim slices in the overlay; never title or funds.

Pure replay uses stamped observations and policy. Current notes are read only by
load_policy; settlement observations are bounded witnesses, not an FSM journal.
"""
from __future__ import annotations

import copy
import re

from capital import overlay, recovery
from capital.resources import note_path
from capital.terms import read_decision_block
from capital.underwriting import BPS_SCALE

NOTE = 'CAPITAL_CLAIM_SLICE_REGISTRY.md'
KINDS = ('SLICE_PROPOSE', 'SLICE_OPEN', 'SLICE_IMPAIR', 'SLICE_RECOURSE', 'SLICE_RESOLVE', 'SLICE_VOID')
COMMANDS = dict(zip(('register_slice', 'open_slice', 'impair_slice', 'post_slice_recourse', 'resolve_slice', 'void_slice'), KINDS))
ITEMS = ('registry_storage_location', 'uniqueness_and_open_slice_rule', 'shared_cap_accounting',
         'borrowing_base_double_use_guard', 'holder_first_priority_shadow', 'impairment_and_recourse_shortfall',
         'slice_lifecycle_states', 'authority_and_proposal_only', 'capacity_bounds', 'export_and_digest_effect')
ACTIVE = ('OPEN', 'IMPAIRED')
TERMINAL = ('RESOLVED', 'VOID')
CAPS = ('single_advance_cap_krw', 'beneficiary_aggregate_cap_krw', 'portfolio_cap_krw')
IMPAIR_REASONS = ('REFUND_REDUCED_LINE', 'CLAIM_VOIDED_OR_REVERSED', 'COVERAGE_SHORTFALL_OTHER')
VOID_REASONS = ('OPERATOR_WITHDRAWN', 'SUPERSEDED_BY_NEW_PROPOSAL', 'OPERATOR_CORRECTION')
FIELDS = {
    'register_slice': {'claim_id', 'payee_label', 'slice_face_krw', 'holder_role', 'expected_days', 'quote_ref'},
    'open_slice': {'slice_id', 'expected_after_journal_index'},
    'impair_slice': {'slice_id', 'reason'},
    'post_slice_recourse': {'slice_id', 'amount_krw', 'source_ref', 'quote_ref'},
    'resolve_slice': {'slice_id', 'resolution'},
    'void_slice': {'slice_id', 'reason'},
}


class SliceError(ValueError):
    def __init__(self, code, status=409, detail=None):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(code)


def labels():
    from capital.shadow import _false_flags
    return {'label': 'SIMULATED', 'mode': 'SHADOW_NOT_APPLIED', 'application': 'SHADOW_NOT_APPLIED',
            'offering': 'SIMULATION_ONLY_NOT_OFFERED_V1', 'title_transferred': False,
            'legal_effect': 'NOT_ASSESSED', 'provisional': True, 'executionAuthorized': False, **_false_flags()}


def load_policy(terms, note=None):
    block = read_decision_block(note_path(NOTE) if note is None else note)
    values = {name: overlay._adopted(block, name) for name in ITEMS}
    if any(v is None for v in values.values()):
        return None
    items = getattr(terms, 'items', {})
    if any(items.get(k, {}).get('mark') != 'ADOPTED' for k in ('underwriting_depth', 'additional_margin', 'interest_rate')):
        return None
    purchase = overlay._adopted(read_decision_block(note_path('CAPITAL_SETTLEMENT_POLICY.md')), 'claim_purchase')
    if purchase is None:
        return None
    depth = items['underwriting_depth']['value']
    margin = items['additional_margin']['value']
    interest = items['interest_rate']['value']
    bounds = values['capacity_bounds']
    bound_names = ('max_registry_entries', 'max_slices_total', 'max_non_terminal_slices',
                   'max_non_terminal_per_beneficiary', 'max_recourse_entries_per_slice',
                   'max_string_bytes', 'demo_script_budget_operations')
    if any(type(bounds.get(k)) is not int or bounds[k] < 1 for k in bound_names):
        return None
    if any(type(depth.get(k)) is not int or depth[k] < 1 for k in (*CAPS, 'two_person_threshold_krw')):
        return None
    if (type(margin.get('beneficiary_payee_map')) is not dict
            or type(margin.get('advance_rate_bps_by_tier')) is not dict
            or type(interest.get('tiers')) is not list
            or type(purchase.get('volume')) is not dict
            or type(purchase['volume'].get('advance_rate_bps_by_tier')) is not dict):
        return None
    return {'policy_digest': recovery.sha(values), 'terms_version': terms.version,
            'caps': {k: depth[k] for k in CAPS}, 'threshold': depth['two_person_threshold_krw'],
            'bounds': {k: v for k, v in values['capacity_bounds'].items() if type(v) is int},
            'payees': margin['beneficiary_payee_map'], 'rates': margin['advance_rate_bps_by_tier'],
            'tier_gates': {t['condition']['settlement_gate']: t['id'] for t in interest['tiers']},
            'sizing_rates': purchase['volume']['advance_rate_bps_by_tier'],
            'price_rates': {t['id']: t['all_in_bps_annual'] for t in interest['tiers']}}


def registry(state):
    return state.get('claim_slices', {}).get('slices', {})


def capacity(state, policy):
    rows = list(registry(state).values())
    return {'scope': 'claim_slice_registry', 'entries': len(state.get('claim_slices', {}).get('entries', [])),
            'slices': len(rows), 'non_terminal': sum(r['status'] not in TERMINAL for r in rows),
            'bounds': copy.deepcopy(policy['bounds'])}


def ceil_div(a, b):
    return (a + b - 1) // b if b else 0


def observation(claim, payees):
    """Small bound observation, retaining only pinned mapped lines."""
    return {'claim_view_sha': recovery.sha(claim), 'refund_face_krw': claim['refund_face'],
            'fixture_reclassified': claim['fixture_reclassified'],
            'lines': {r['payee']: {k: r[k] for k in ('face', 'outstanding', 'distributed', 'recovery_due')}
                      for r in claim['obligations'] if r['payee'] in payees}}


def eligible(obs, payee):
    line = obs['lines'].get(payee)
    if line is None:
        return 0
    total = sum(r['outstanding'] for r in obs['lines'].values())
    refund = ceil_div(obs['refund_face_krw'] * line['outstanding'], total)
    return max(0, line['outstanding'] - refund)


def derived(row, obs):
    line = obs['lines'].get(row['payee_label'], {'distributed': 0})
    served = min(row['slice_face_krw'], max(0, line['distributed'] - row.get('baseline_distributed_krw', line['distributed'])))
    if row['status'] in TERMINAL:
        served = row.get('served_krw', 0)
    # Late distributions can arrive after recourse. There is no negative exposure
    # or further collection; served is still the note's cumulative face formula.
    outstanding = max(0, row['slice_face_krw'] - served - row['recourse_received_krw'])
    el = eligible(obs, row['payee_label'])
    counted = row['status'] in ACTIVE
    shortfall = max(0, outstanding - el) if counted else 0
    return {'served_krw': served, 'outstanding_krw': outstanding,
            'eligible_line_krw': el, 'encumbered_face_krw': min(outstanding, el) if counted else 0,
            'exposure_krw': outstanding if counted else 0, 'shortfall_krw': shortfall,
            'SLICE_IMPAIRMENT_ELIGIBLE': row['status'] == 'OPEN' and shortfall > 0,
            'SLICE_RESOLVABLE': counted and outstanding == 0}


def held_on_line(state, claim, payee, distributed):
    held = 0
    for row in registry(state).values():
        if (row['claim_id'], row['payee_label']) != (claim, payee):
            continue
        if row['status'] in ACTIVE:
            held += min(row['slice_face_krw'], max(0, distributed - row['baseline_distributed_krw']))
        elif row['status'] == 'RESOLVED':
            held += row['served_krw']
    return held


def recourse_consumed(state, claim, payee):
    key = recovery.source_key(claim, payee)
    return state.get('claim_slices', {}).get('sources', {}).get(key, 0)


def source_terms(state, claim, payee, distributed):
    held = held_on_line(state, claim, payee, distributed)
    consumed = recourse_consumed(state, claim, payee)
    return {'slice_held_krw': held, 'slice_recourse_consumed_krw': consumed} if held or consumed else {}


def source_available(state, claim, payee, observed, distributed):
    consumed = state.get('recovery', {}).get('sources', {}).get(recovery.source_key(claim, payee), 0)
    return max(0, observed - consumed - sum(source_terms(state, claim, payee, distributed).values()))


def exposures(state, observations, beneficiary, claim_id=None):
    own = portfolio = encumbered = 0
    for row in registry(state).values():
        d = derived(row, observations[row['claim_id']])
        portfolio += d['exposure_krw']
        if row['beneficiary_role'] == beneficiary:
            own += d['exposure_krw']
        if row['claim_id'] == claim_id:
            encumbered += d['encumbered_face_krw']
    return {'slice_exposure_beneficiary_krw': own, 'slice_exposure_portfolio_krw': portfolio,
            'slice_encumbered_krw': encumbered}


def authority_amount(state, key, day, kind, amount, slice_id=None):
    entries = state.get('claim_slices', {}).get('entries', [])
    for e in entries:
        p = e['payload']
        if (p['claim_id'], p['payee_label']) != key or e['sim_day'] != day:
            continue
        if kind in ('SLICE_PROPOSE', 'SLICE_OPEN') and e['kind'] == 'SLICE_PROPOSE' and p['slice_id'] != slice_id:
            amount += p['slice_face_krw']
        elif kind == 'SLICE_RECOURSE' and e['kind'] == kind:
            amount += p['amount_krw']
    return amount


def authorize(command, amount, policy):
    try:
        return recovery.authorize('organizer', command['approvals'], amount,
                                  {'two_person_threshold_krw': policy['threshold']}, command.get('proposal_id'))
    except recovery.RecoveryError as exc:
        raise SliceError(exc.code, exc.status) from exc


def guard(state, identity, witness, policy):
    claim, payee, beneficiary = (identity[k] for k in ('claim_id', 'payee_label', 'beneficiary_role'))
    obs = witness['observations'][claim]
    line = obs['lines'].get(payee)
    if line is None or payee not in policy['payees'].get(beneficiary, []):
        raise SliceError('SLICE_PAYEE_NOT_SLICEABLE')
    advances = witness['advances']
    reserved = max((v['reserved_open'] for v in advances.values() if v['claim_id'] == claim), default=0)
    el = eligible(obs, payee)
    total = sum(eligible(obs, p) for p in obs['lines'])
    pledged = ceil_div(reserved * el, total)
    exposure = exposures(state, witness['observations'], beneficiary)
    own = sum(v['outstanding_exposure'] for v in advances.values() if v['beneficiary_role'] == beneficiary)
    portfolio = sum(v['outstanding_exposure'] for v in advances.values())
    # G2 uses the beneficiary's bound claim bases, priced at the admitted tier.
    # Unpledged fixtures cannot supply additional collateral.
    bound_claims = {claim} | {a['claim_id'] for a in advances.values() if a['beneficiary_role'] == beneficiary}
    eligible_b = sum(eligible(o, p) for c, o in witness['observations'].items()
                     if c in bound_claims for p in o['lines'])
    enc = sum(derived(r, witness['observations'][r['claim_id']])['encumbered_face_krw']
              for r in registry(state).values() if r['beneficiary_role'] == beneficiary)
    rate = policy['rates'].get(identity['tier'], 0)
    reverse_max = max(0, eligible_b - enc - ceil_div(own * BPS_SCALE, rate)) if rate else 0
    caps = policy['caps']
    headroom = min(caps[CAPS[0]], caps[CAPS[1]] - own - exposure['slice_exposure_beneficiary_krw'],
                   caps[CAPS[2]] - portfolio - exposure['slice_exposure_portfolio_krw'])
    u1 = witness['gates'][claim] in policy['tier_gates']
    u2 = obs['refund_face_krw'] == 0 or obs['fixture_reclassified']
    return {'eligible_line_krw': el, 'advance_pledged_krw': pledged,
            'beneficiary_exposure_before_krw': own + exposure['slice_exposure_beneficiary_krw'],
            'portfolio_exposure_before_krw': portfolio + exposure['slice_exposure_portfolio_krw'],
            'u1': 'PASS' if u1 else 'FAIL', 'u2': 'PASS' if u2 else 'FAIL',
            'u3': 'PASS', 'u4': 'PASS'}, max(0, el - pledged), reverse_max, max(0, headroom)


def registry_check(context, face_max):
    if context.get('policy') is None:
        return {'mode': 'SHADOW_NOT_APPLIED', 'read_only': True, 'status': 'NOT_BOUND', 'codes': ['NOT_BOUND']}
    state, ident, witness, policy = (context[k] for k in ('state', 'identity', 'witness', 'policy'))
    codes = []
    exists = any((r['claim_id'], r['payee_label']) == (ident['claim_id'], ident['payee_label'])
                 and r['status'] not in TERMINAL for r in registry(state).values())
    try:
        trace, free, reverse, cap = guard(state, ident, witness, policy)
        if trace['u1'] != 'PASS': codes.append('SLICE_U1_REFUSED')
        if trace['u2'] != 'PASS': codes.append('SLICE_U2_REFUSED')
        sliceable = True
    except SliceError as exc:
        codes.append(exc.code)
        sliceable, free, reverse, cap = False, 0, 0, 0
    if exists: codes.append('SLICE_OPEN_EXISTS')
    maximum = min(face_max, free, reverse, cap)
    return {'mode': 'SHADOW_NOT_APPLIED', 'read_only': True, 'status': 'REFUSED' if codes else 'ADMISSIBLE',
            'codes': codes, 'sliceable': sliceable, 'open_slice_exists': exists,
            'free_face_krw': free, 'admissible_face_max_krw': maximum if not codes else 0,
            'capacity': capacity(state, policy)}


def check_capacity(state, kind, ident, policy):
    c = capacity(state, policy)
    b = policy['bounds']
    rows = list(registry(state).values())
    fail = c['entries'] >= b['max_registry_entries']
    if kind == 'SLICE_PROPOSE':
        fail |= c['slices'] >= b['max_slices_total'] or c['non_terminal'] >= b['max_non_terminal_slices']
        fail |= sum(r['beneficiary_role'] == ident['beneficiary_role'] and r['status'] not in TERMINAL for r in rows) >= b['max_non_terminal_per_beneficiary']
    if kind == 'SLICE_RECOURSE':
        fail |= sum(e['kind'] == kind and e['payload']['slice_id'] == ident['slice_id']
                    for e in state['claim_slices']['entries']) >= b['max_recourse_entries_per_slice']
    if fail:
        raise SliceError('SIMULATION_CAPACITY', detail={'scope': 'claim_slice_registry'})


def plan_payload(state, e):
    p, kind = e['payload'], e['kind']
    command, policy, witness = p['command'], p['policy'], p['witness']
    sid = p['slice_id']
    if command['at_sim_day'] != state['sim_day'] or e['sim_day'] != state['sim_day']:
        raise SliceError('SIM_CLOCK_STALE')
    if kind == 'SLICE_PROPOSE':
        ident = {k: p[k] for k in ('slice_id', 'claim_id', 'payee_label', 'beneficiary_role', 'holder_role', 'tier', 'slice_face_krw')}
        if sid != e['overlay_id'] or any(command[k] != ident[k] for k in ('claim_id', 'payee_label', 'holder_role', 'slice_face_krw')):
            raise SliceError('INVALID_COMMAND', 400)
        if ident['holder_role'] != 'KIX_CAPITAL_LENDER':
            raise SliceError('SLICE_HOLDER_NOT_ADOPTED')
        if any((r['claim_id'], r['payee_label']) == (ident['claim_id'], ident['payee_label']) and r['status'] not in TERMINAL for r in registry(state).values()):
            raise SliceError('SLICE_OPEN_EXISTS')
        trace, _, _, _ = guard(state, ident, witness, policy)
        if trace['u1'] != 'PASS' or trace['u2'] != 'PASS':
            raise SliceError('SLICE_U1_REFUSED' if trace['u1'] != 'PASS' else 'SLICE_U2_REFUSED')
        from capital.shadow import slice_sizing
        obs = witness['observations'][ident['claim_id']]
        line = obs['lines'][ident['payee_label']]
        maxface = slice_sizing(line['outstanding'], line['outstanding'] - eligible(obs, ident['payee_label']),
                               policy['sizing_rates'][ident['tier']], policy['price_rates'][ident['tier']], command['expected_days'])['slice_face_max']
        if ident['slice_face_krw'] > maxface:
            raise SliceError('SLICE_QUOTE_MISMATCH')
    else:
        row = registry(state).get(sid)
        if row is None:
            raise SliceError('UNKNOWN_SLICE', 404)
        ident = {k: row[k] for k in ('slice_id', 'claim_id', 'payee_label', 'beneficiary_role', 'holder_role', 'tier', 'slice_face_krw')}
        if policy != row['policy']:
            raise SliceError('NOT_BOUND')
        if command['slice_id'] != sid:
            raise SliceError('INVALID_COMMAND', 400)
    check_capacity(state, kind, ident, policy)
    face = ident['slice_face_krw']
    base = {**ident, **labels(), 'command': copy.deepcopy(command), 'policy': copy.deepcopy(policy), 'witness': copy.deepcopy(witness)}
    amount = face
    if kind == 'SLICE_PROPOSE':
        base.update(quote_ref=command['quote_ref'], recourse='FULL_RECOURSE_TO_BENEFICIARY')
    else:
        obs = witness['observations'][ident['claim_id']]
        d = derived(row, obs)
        status = row['status']
        if kind == 'SLICE_OPEN':
            if status != 'PROPOSED': raise SliceError('SLICE_STATE_INVALID')
            if command['expected_after_journal_index'] != e['after_journal_index']:
                raise SliceError('REGISTRY_STALE_CAS')
            trace, free, reverse, _ = guard(state, ident, witness, policy)
            if face > free: raise SliceError('BASE_ALREADY_ENCUMBERED')
            if face > reverse: raise SliceError('SLICE_WOULD_BREACH_ADVANCE_BASE')
            for key, required in zip(CAPS, (face, trace['beneficiary_exposure_before_krw'] + face, trace['portfolio_exposure_before_krw'] + face)):
                if required > policy['caps'][key]: raise SliceError('SLICE_CAP_EXCEEDED', detail={'cap_ref': key})
            if trace['u1'] != 'PASS' or trace['u2'] != 'PASS':
                raise SliceError('SLICE_U1_REFUSED' if trace['u1'] != 'PASS' else 'SLICE_U2_REFUSED')
            base.update(baseline_distributed_krw=obs['lines'][ident['payee_label']]['distributed'], guard_trace=trace)
        elif kind == 'SLICE_IMPAIR':
            if status != 'OPEN': raise SliceError('SLICE_STATE_INVALID')
            if command['reason'] not in IMPAIR_REASONS: raise SliceError('INVALID_COMMAND', 400)
            if d['shortfall_krw'] == 0: raise SliceError('SLICE_NOT_IMPAIRABLE')
            base.update(reason=command['reason'], shortfall_krw=d['shortfall_krw'], served_at_impairment_krw=d['served_krw'],
                        outstanding_at_impairment_krw=d['outstanding_krw'], eligible_line_krw=d['eligible_line_krw'])
        elif kind == 'SLICE_RECOURSE':
            if status != 'IMPAIRED': raise SliceError('SLICE_STATE_INVALID')
            amount = command['amount_krw']
            q = p['quote_witness']
            src = command['source_ref']
            if src['claim_id'] == ident['claim_id'] or witness['beneficiaries'].get(src['claim_id']) != ident['beneficiary_role']:
                raise SliceError('SLICE_RECOURSE_SOURCE_INVALID')
            if src['payee_label'] not in policy['payees'].get(ident['beneficiary_role'], []):
                raise SliceError('SLICE_RECOURSE_SOURCE_INVALID')
            if q != recourse_witness(state, row, witness['observations'], src):
                raise SliceError('RECOVERY_QUOTE_STALE')
            if recovery.sha(q) != command['quote_ref']: raise SliceError('RECOVERY_QUOTE_STALE')
            if amount > q['available_krw']: raise SliceError('RECOVERY_SOURCE_EXCEEDED')
            if amount > d['outstanding_krw']: raise SliceError('RECOVERY_EXCEEDS_CLAIM')
            base.update(amount_krw=amount, source_ref=src, quote_ref=command['quote_ref'], quote_witness=q,
                        waterfall_step='SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY')
        elif kind == 'SLICE_RESOLVE':
            if status not in ACTIVE: raise SliceError('SLICE_STATE_INVALID')
            if d['outstanding_krw']: raise SliceError('SLICE_NOT_RESOLVABLE')
            resolution = command['resolution']
            if resolution not in ('SERVED_IN_FULL', 'RECOURSE_SATISFIED') or (resolution == 'RECOURSE_SATISFIED' and (status != 'IMPAIRED' or not row['recourse_received_krw'])) or (resolution == 'SERVED_IN_FULL' and d['served_krw'] != face):
                raise SliceError('SLICE_STATE_INVALID')
            base.update(resolution=resolution, served_krw=d['served_krw'], recourse_received_krw=row['recourse_received_krw'])
        elif kind == 'SLICE_VOID':
            if status not in ('PROPOSED', 'OPEN') or d['served_krw']:
                raise SliceError('SLICE_STATE_INVALID')
            if command['reason'] not in VOID_REASONS: raise SliceError('INVALID_COMMAND', 400)
            base['reason'] = command['reason']
    amount = authority_amount(state, (ident['claim_id'], ident['payee_label']), e['sim_day'], kind, amount, sid)
    base['authority'] = authorize(command, amount, policy)
    return base


def recourse_witness(state, row, observations, source):
    obs = observations[source['claim_id']]
    line = obs['lines'][source['payee_label']]
    if source['source_cut'] != obs['claim_view_sha']:
        raise SliceError('RECOVERY_QUOTE_STALE')
    observed = max(0, line['distributed'] - line['recovery_due'])
    return {'source_ref': source, 'slice_id': row['slice_id'], 'state_digest': overlay.state_digest(state),
            'observed_eligible_krw': observed, 'available_krw': source_available(state, source['claim_id'], source['payee_label'], observed, line['distributed'])}


def recourse_quotes(state, row, fixtures, setoff):
    if row['status'] != 'IMPAIRED': return []
    results = []
    obs = {c: observation(v['claim'], row['policy']['payees'].get(fixtures.beneficiary(c), [])) for c, v in fixtures.rows.items()}
    outstanding = derived(row, obs[row['claim_id']])['outstanding_krw']
    for c, v in sorted(fixtures.rows.items()):
        if c == row['claim_id'] or fixtures.beneficiary(c) != row['beneficiary_role']: continue
        case = {'settlement_id': c, 'beneficiary_role': row['beneficiary_role'], 'outstanding_exposure': outstanding, 'phase': 'DEFAULTED'}
        facts, quote = setoff._quote(case, v['claim'], 'MOCK_COMMIT_OBSERVED')
        if quote.get('status') != 'BOUND' or setoff._execution()[2] is not None: continue
        for line in facts['lines']:
            if not line['counted']: continue
            src = {'claim_id': c, 'payee_label': line['payee'], 'source_cut': obs[c]['claim_view_sha']}
            q = recourse_witness(state, row, obs, src)
            results.append({**q, 'quote_ref': recovery.sha(q), 'amount_krw': min(outstanding, q['available_krw']),
                            'waterfall_step': 'SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY', **labels()})
    return results


def entry(operation_id, kind, state, index, payload):
    e = {'overlay_id': operation_id, 'kind': kind, 'after_journal_index': index, 'sim_day': state['sim_day'], 'payload': payload}
    e['payload'] = plan_payload(state, e)
    validate_entry(e)
    return e


def receipt(e):
    return {'operation_id': e['overlay_id'], 'op': e['payload']['command']['op'], 'outcome': 'APPLIED',
            'sim_day': e['sim_day'], 'entry': copy.deepcopy(e['payload']), **labels()}


def validate_command(command):
    op = command.get('op') if type(command) is dict else None
    if type(op) is not str or op not in COMMANDS or set(command) - {'proposal_id'} != {'op', 'at_sim_day', 'approvals'} | FIELDS[op]:
        raise SliceError('INVALID_COMMAND', 400)
    if type(command['at_sim_day']) is not int or command['at_sim_day'] < 0:
        raise SliceError('INVALID_COMMAND', 400)
    if recovery.approvals(command['approvals']) != command['approvals']:
        raise SliceError('INVALID_COMMAND', 400)
    for k, v in command.items():
        if k in ('slice_face_krw', 'amount_krw', 'expected_days', 'expected_after_journal_index'):
            if type(v) is not int or v < (1 if k in ('slice_face_krw', 'amount_krw') else 0): raise SliceError('INVALID_COMMAND', 400)
        elif k == 'source_ref':
            if type(v) is not dict or set(v) != {'claim_id', 'payee_label', 'source_cut'} or any(type(x) is not str or not recovery.LABEL.fullmatch(x) for x in v.values()):
                raise SliceError('INVALID_COMMAND', 400)
        elif k != 'approvals' and k != 'at_sim_day':
            if type(v) is not str or not recovery.LABEL.fullmatch(v): raise SliceError('INVALID_COMMAND', 400)


def validate_entry(e):
    try:
        p = e['payload']
        validate_command(p['command'])
        if COMMANDS[p['command']['op']] != e['kind']: raise ValueError('kind')
        def walk(v, key=''):
            if type(v) is dict:
                if set(v) & {'instance_id', 'created_at', 'saved_at', 'timestamp', 'timestamps', 'token', 'holder_ref', 'transfer_to'}: raise ValueError('forbidden')
                for k, x in v.items(): walk(x, k)
            elif type(v) is list:
                for x in v: walk(x, key)
            elif type(v) is str:
                if len(v.encode()) > p['policy']['bounds']['max_string_bytes']: raise ValueError('string bound')
            elif type(v) not in (int, bool, type(None)) or (type(v) is int and v < 0): raise ValueError('value')
        walk(p)
        for obs in p['witness']['observations'].values():
            if type(obs['fixture_reclassified']) is not bool or not re.fullmatch(r'[0-9a-f]{64}', obs['claim_view_sha']):
                raise ValueError('observation')
            for line in obs['lines'].values():
                if any(type(line[k]) is not int or line[k] < 0 for k in ('face', 'outstanding', 'distributed', 'recovery_due')):
                    raise ValueError('line amount')
                if line['outstanding'] + line['distributed'] > line['face'] or line['recovery_due'] > line['distributed']:
                    raise ValueError('line bound')
        for k, v in labels().items():
            if type(p[k]) is not type(v) or p[k] != v: raise ValueError('labels')
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise overlay.OverlayError('claim slice shape') from exc


def fold_entry(state, e):
    try:
        p, kind = e['payload'], e['kind']
        if state['terms_binding'] is None or p['policy']['terms_version'] != state['terms_binding']['terms_version']:
            raise ValueError('terms')
        if plan_payload(state, e) != p: raise ValueError('calculation witness')
        reg = state.setdefault('claim_slices', {'slices': {}, 'entries': [], 'sources': {}})
        if kind == 'SLICE_PROPOSE':
            reg['slices'][p['slice_id']] = {k: copy.deepcopy(p[k]) for k in ('slice_id', 'claim_id', 'payee_label', 'beneficiary_role', 'holder_role', 'tier', 'slice_face_krw', 'policy', 'quote_ref')}
            reg['slices'][p['slice_id']].update(status='PROPOSED', recourse_received_krw=0)
        row = reg['slices'][p['slice_id']]
        if kind == 'SLICE_OPEN': row.update(status='OPEN', baseline_distributed_krw=p['baseline_distributed_krw'])
        elif kind == 'SLICE_IMPAIR': row['status'] = 'IMPAIRED'
        elif kind == 'SLICE_RECOURSE':
            row['recourse_received_krw'] += p['amount_krw']
            src = p['source_ref']
            key = recovery.source_key(src['claim_id'], src['payee_label'])
            reg['sources'][key] = reg['sources'].get(key, 0) + p['amount_krw']
        elif kind == 'SLICE_RESOLVE': row.update(status='RESOLVED', served_krw=p['served_krw'], resolution=p['resolution'])
        elif kind == 'SLICE_VOID': row['status'] = 'VOID'
        reg['entries'].append(copy.deepcopy(e))
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise overlay.OverlayError('claim slice semantic fold') from exc


def advance_witness(producer, journal):
    return {a: {k: producer.view(a)[k] for k in ('beneficiary_role', 'claim_id', 'outstanding_exposure', 'reserved_open')}
            for a in sorted({e['advance_id'] for e in journal})}


def validate_links(entries, journal, fixtures=None):
    """Bind admission to the exact F04 prefix and bounded settlement observations.

    A changed settlement cut cannot be replayed from F04. Face and monotonic
    distribution are checked even then; an equal observation hash is exact.
    """
    if not any(e.get('kind') in KINDS for e in entries):
        return
    from capital.producer import CreditError, PinnedFsmProducer, FixtureViews
    source = fixtures or FixtureViews()
    if type(source) is dict:
        rows = source
        source = FixtureViews()
        source.rows = copy.deepcopy(rows)
    previous = {}
    seen = set()
    for position, e in enumerate(entries):
        if e['kind'] not in KINDS or e['overlay_id'] in seen: continue
        seen.add(e['overlay_id'])
        try:
            p, w = e['payload'], e['payload']['witness']
            if plan_payload(overlay.fold(entries[:position]), e) != p:
                raise ValueError('claim slice witness')
            prefix = journal[:e['after_journal_index']]
            producer = PinnedFsmProducer(source).restored(prefix)
            if w['advances'] != advance_witness(producer, prefix): raise ValueError('FSM prefix')
            for c, obs in w['observations'].items():
                view = source.view(c)
                b = source.beneficiary(c)
                if w['beneficiaries'][c] != b: raise ValueError('beneficiary')
                expected = observation(view['claim'], p['policy']['payees'].get(b, []))
                if set(obs['lines']) != set(expected['lines']): raise ValueError('mapped lines')
                for payee, line in obs['lines'].items():
                    if line['face'] != expected['lines'][payee]['face']: raise ValueError('line face')
                    if line['distributed'] < previous.get((c, payee), 0): raise ValueError('distribution decreased')
                    previous[c, payee] = line['distributed']
                if obs['claim_view_sha'] == expected['claim_view_sha'] and obs != expected: raise ValueError('settlement observation')
            if e['kind'] in ('SLICE_PROPOSE', 'SLICE_OPEN'):
                c = p['claim_id']
                if c not in w['observations']: raise ValueError('missing claim')
                # Gate at the observed cut; a current identical cut must agree.
                if w['observations'][c]['claim_view_sha'] == recovery.sha(source.view(c)['claim']):
                    gate = 'MOCK_COMMIT_OBSERVED' if source.view(c)['phase'] == 'COMMITTED' else 'BOUND'
                    if w['gates'][c] != gate: raise ValueError('gate')
                if p['tier'] != p['policy']['tier_gates'].get(w['gates'][c]): raise ValueError('tier')
        except (ValueError, KeyError, TypeError, ArithmeticError, CreditError) as exc:
            raise overlay.OverlayError('claim_slice_link') from exc
    _validate_draw_links(entries, journal, source)


def _validate_draw_links(entries, journal, source):
    """A resealed cross-journal splice must not bypass the advance-side G4."""
    from capital.producer import CreditError, PinnedFsmProducer
    try:
        for index, command in enumerate(journal):
            if command['op'] != 'draw':
                continue
            prior = [e for e in entries if e['after_journal_index'] <= index]
            state = overlay.fold(prior, index)
            rows = list(registry(state).values())
            if not rows:
                continue
            observations = {}
            for e in prior:
                if e['kind'] in KINDS:
                    observations.update(e['payload']['witness']['observations'])
            # No historical settlement journal accompanies an F04 draw. Only
            # an unchanged observed cut supports this additional splice check.
            if any(o['claim_view_sha'] != recovery.sha(source.view(c)['claim']) for c, o in observations.items()):
                continue
            if not any(derived(r, observations[r['claim_id']])['exposure_krw'] for r in rows):
                continue
            producer = PinnedFsmProducer(source).restored(journal[:index])
            case = producer.view(command['advance_id'])
            policy = rows[0]['policy']
            claim = case['claim_id']
            beneficiary = case['beneficiary_role']
            if claim not in observations:
                # F04's offer face is bound even when the external settlement
                # observation subsequently changes; no new historical cut is claimed.
                face = next(e['body']['face'] for e in journal[:index] if e['op'] == 'offer' and e['advance_id'] == command['advance_id'])
                observations[claim] = observation(face, policy['payees'].get(beneficiary, []))
            exp = exposures(state, observations, beneficiary, claim)
            el = sum(eligible(observations[claim], p) for p in observations[claim]['lines'])
            if exp['slice_encumbered_krw'] and case['reserved_open'] + case['amount'] + exp['slice_encumbered_krw'] > el:
                raise ValueError('G4 shared face')
            after = PinnedFsmProducer(source).restored(journal[:index+1]).view(command['advance_id'])
            gate = 'MOCK_COMMIT_OBSERVED' if after['mock_settlement_commit_observed'] else 'UNBOUND'
            tier = policy['tier_gates'][gate]
            if case['amount'] > (el-exp['slice_encumbered_krw'])*policy['rates'][tier]//BPS_SCALE:
                raise ValueError('G4 borrowing base')
            advances = advance_witness(producer, journal[:index])
            own = sum(a['outstanding_exposure'] for a in advances.values() if a['beneficiary_role'] == beneficiary)
            portfolio = sum(a['outstanding_exposure'] for a in advances.values())
            requirements = (case['amount'], own+case['amount']+exp['slice_exposure_beneficiary_krw'],
                            portfolio+case['amount']+exp['slice_exposure_portfolio_krw'])
            if any(n > policy['caps'][cap] for n, cap in zip(requirements, CAPS)):
                raise ValueError('G4 shared caps')
    except (ValueError, KeyError, TypeError, ArithmeticError, CreditError) as exc:
        raise overlay.OverlayError('claim_slice_link') from exc
