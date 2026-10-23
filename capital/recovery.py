"""Provisional SIMULATED post-default ledger, never collections or F04 repayment.

Writers load all ten ADOPTED policies from CAPITAL_DEFAULT_RECOVERY.md. Entries
stamp their policy and arithmetic witnesses; the fold never reads current notes.
Reserve accounting and COA postings belong to later nodes.
"""
from __future__ import annotations

import copy
import hashlib
import re

from capital import overlay
from capital.store import canonical_bytes
from capital.terms import read_decision_block

NOTE = 'CAPITAL_DEFAULT_RECOVERY.md'
KINDS = ('default_anchor', 'RECOVERY', 'WRITEOFF', 'acceleration_event')
COMMANDS = ('post_recovery', 'post_writeoff', 'record_acceleration')
ITEMS = ('acceleration_interest_rebase', 'writeoff_trigger_and_day_basis', 'recovery_entry_schema',
         'waterfall_steps_in_scope', 'reserve_step_when_unbuilt', 'late_recovery_after_writeoff',
         'interest_stop_rule', 'recovery_authority', 'loss_attribution', 'digest_and_coa_effect')
LABEL = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z')


class RecoveryError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def approvals(value):
    if type(value) is not list or len(value) > 16:
        raise RecoveryError('INVALID_ARGUMENTS', 400)
    labels = []
    for item in value:
        if (type(item) is not dict or set(item) != {'approver_label'}
                or type(item['approver_label']) is not str or not LABEL.fullmatch(item['approver_label'])):
            raise RecoveryError('INVALID_ARGUMENTS', 400)
        labels.append(item['approver_label'])
    return [{'approver_label': label} for label in sorted(set(labels))]


def authorize(role, labels, amount, policy, proposal_id=None):
    if role == 'agent':
        raise RecoveryError('RECOVERY_AGENT_FORBIDDEN', 403)
    if role != 'organizer':
        raise RecoveryError('ROLE_FORBIDDEN', 403)
    labels = approvals(labels)
    if amount > policy['two_person_threshold_krw'] and len(labels) < 2:
        raise RecoveryError('TWO_PERSON_REQUIRED')
    authority = {'role': role, 'approvals': labels}
    if proposal_id is not None:
        if type(proposal_id) is not str or not LABEL.fullmatch(proposal_id):
            raise RecoveryError('INVALID_ARGUMENTS', 400)
        authority['proposal_id'] = proposal_id
    return authority


def load_policy(terms, note=None):
    block = read_decision_block(overlay.default_note_path(NOTE) if note is None else note)
    values = {name: overlay._adopted(block, name) for name in ITEMS}
    if any(value is None for value in values.values()):
        return None
    required = ('underwriting_depth', 'default_loss_treatment', 'term', 'additional_margin', 'interest_rate')
    items = getattr(terms, 'items', {})
    if any(items.get(name, {}).get('mark') != 'ADOPTED' for name in required):
        return None
    depth, loss, term = (items[name]['value'] for name in required[:3])
    threshold, delay = depth.get('two_person_threshold_krw'), loss.get('writeoff_days_after_default')
    if type(threshold) is not int or threshold < 1 or type(delay) is not int or delay < 1:
        return None
    # Keep the decision values in the witness, including NOT_BOUND/UNBUILT_V1.
    return {'decision_id': block['decision_id'], 'decision_date': block['date'],
            'policy_digest': sha(values), 'decision_entries': sha({k: sha(v) for k, v in values.items()}),
            'values': {
                'acceleration_interest_rebase': {'applies_to_events': values['acceleration_interest_rebase']['applies_to_events']},
                'waterfall_steps_in_scope': {'order': values['waterfall_steps_in_scope']['order']},
                'reserve_step_when_unbuilt': {k: values['reserve_step_when_unbuilt'][k] for k in ('trace_row', 'entry_marker')}},
            'terms_version': terms.version,
            'two_person_threshold_krw': threshold, 'writeoff_days_after_default': delay,
            'default_command_overdue_days': int(re.search(r'([0-9]+) sim_days', values['writeoff_trigger_and_day_basis']['no_default_command']).group(1)),
            'grace_days': term['grace_days_after_maturity'], 'loss_bearer': loss['loss_bearer_v1']}


def anchor(state, ref):
    return state.get('default_anchors', {}).get(ref)


def recovered(state, ref):
    return state.get('recovery', {}).get('advances', {}).get(ref, {
        'principal_recovered_krw': 0, 'paid_interest_krw': 0, 'paid_default_krw': 0,
        'written_off_krw': 0, 'residual_claim_krw': None, 'writeoff_sim_day': None})


def position(state, ref):
    a = anchor(state, ref)
    if a is None:
        raise RecoveryError('DEFAULT_DAY_UNKNOWN')
    record = state['advances'].get(ref, {})
    paid = overlay._payments(state, ref)
    r = recovered(state, ref)
    principal = a['principal_krw'] - r['principal_recovered_krw'] - r['written_off_krw']
    interest = record.get('posted_contract_krw', 0) - paid['paid_interest_krw'] - r['paid_interest_krw']
    default = record.get('posted_default_krw', 0) - paid['paid_default_krw'] - r['paid_default_krw']
    return {'principal_krw': principal, 'interest_krw': interest, 'default_interest_krw': default,
            'claim_krw': r['residual_claim_krw'] if r['writeoff_sim_day'] is not None else principal + interest + default}


def source_quotes(state, subject, sources, setoff):
    """Use the setoff-proposal-quote classification and observed distribution arithmetic.

    Each line is shared across advances. A source cut is an observation digest, not
    an authenticated cursor. State-bound quotes become stale after any posting.
    """
    ref, case = subject['advance_id'], subject['case']
    if case['phase'] != 'DEFAULTED' or anchor(state, ref) is None:
        return []
    due = position(state, ref)['claim_krw']
    result = []
    for source_id, view in sorted(sources.items()):
        claim = view['claim']
        # _quote shares the existing classifier, beneficiary map and distribution formula.
        _facts, quote = setoff._quote({**case, 'settlement_id': source_id}, claim, subject['gate'])
        if quote.get('status') != 'BOUND':
            continue
        if setoff._execution()[2] is not None:
            continue
        lines = _facts.get('lines', [])
        for line in lines:
            if not line['counted']:
                continue
            key = source_key(source_id, line['payee'])
            consumed = state.get('recovery', {}).get('sources', {}).get(key, 0)
            available = max(0, line['eligible_krw'] - consumed)
            if available == 0:
                continue
            source = {'claim_id': source_id, 'payee_label': line['payee'], 'source_cut': sha(claim)}
            witness = {'source_ref': source, 'observed_eligible_krw': line['eligible_krw'],
                       'distributed_krw': line['distributed'], 'recovery_due_krw': line['recovery_due'],
                       'consumed_krw': consumed, 'state_digest': overlay.state_digest(state),
                       'advance_id': ref, 'claim_due_krw': due}
            result.append({'quote_ref': sha(witness), **witness, 'amount_krw': min(due, available),
                           'available_krw': available,
                           'waterfall_step': waterfall(state, ref)[0 if source_id == case['claim_id'] else 1],
                           'proposal_kind': 'RECOVERY_SETOFF', 'proposal_only': True,
                           'f04_default_called': False, 'executionAuthorized': False, 'label': 'SIMULATED'})
    return result


def source_key(claim, payee):
    return sha([claim, payee])


def waterfall(state, ref):
    return anchor(state, ref)['policy']['values']['waterfall_steps_in_scope']['order']


def _split(pos, amount):
    allocation = {}
    for key in ('default_interest_krw', 'interest_krw', 'principal_krw'):
        allocation[key] = min(pos[key], amount)
        amount -= allocation[key]
    return allocation


def interest_unpaid_by_recognition(state, ref):
    """Cash applies oldest days first within DEFAULT, then contractual interest.

    A spanning posting is split at the dated default anchor using exact rational
    daily accrual; floors are differences of cumulative floors, preserving carry.
    """
    a = anchor(state, ref)
    paid = overlay._payments(state, ref)
    r = recovered(state, ref)
    recognized = suspended = 0
    for bucket, paid_key, exact_key, bps_key in (
            ('default', 'paid_default_krw', 'cumulative_default_exact', 'default_bps'),
            ('contract', 'paid_interest_krw', 'cumulative_contract_exact', 'contract_bps')):
        # The default anchor freezes cumulative accrual exactly at the command day.
        total = state['advances'].get(ref, {}).get('posted_' + bucket + '_krw', 0)
        before = a['recognized_at_default'][bucket]
        payment = paid[paid_key] + r[paid_key]
        recognized += max(0, before - payment)
        suspended += max(0, total - before - max(0, payment - before))
    return recognized, suspended


def plan_payload(state, entry):
    """Calculate the semantic payload from stamped command/policy witnesses.

    Used both by the writer and the replay validator. No policy note reads here.
    """
    p, ref = entry['payload'], entry['payload']['advance_id']
    day = entry['sim_day']
    policy = p['policy']
    command = p['command']
    kind = entry['kind']
    amount = p['principal_krw'] if kind in ('default_anchor', 'acceleration_event') else 0
    if kind == 'default_anchor':
        if anchor(state, ref) is not None:
            raise RecoveryError('DEFAULT_ALREADY_ANCHORED')
        record = state['advances'].get(ref, {})
        base = {k: p[k] for k in ('advance_id', 'claim_id', 'beneficiary_role', 'tier', 'policy', 'command', 'principal_krw', 'authority', 'f04_operation_id')}
        return {**base, 'default_sim_day': day,
                'writeoff_eligible_sim_day': day + policy['writeoff_days_after_default'],
                'recognized_at_default': {'contract': record.get('posted_contract_krw', 0),
                                          'default': record.get('posted_default_krw', 0)}}
    if kind == 'acceleration_event':
        previous = effective_maturity(state, ref, p['maturity_before'])
        if command['event'] not in policy['values']['acceleration_interest_rebase']['applies_to_events'][1:]:
            raise RecoveryError('INVALID_ARGUMENTS', 400)
        base = {k: p[k] for k in ('advance_id', 'claim_id', 'beneficiary_role', 'tier', 'policy', 'command', 'principal_krw', 'authority', 'maturity_before')}
        return {**base, 'maturity_after': min(previous, day),
                'default_eligible_day': min(previous, day) + policy['grace_days'] + 1}
    a = anchor(state, ref)
    if a is None:
        raise RecoveryError('DEFAULT_DAY_UNKNOWN')
    pos, r = position(state, ref), recovered(state, ref)
    base = {key: p[key] for key in ('advance_id', 'claim_id', 'beneficiary_role', 'tier', 'policy', 'command')}
    base.update(entry_id=entry['overlay_id'], entry_kind=kind, sim_day=day,
                after_journal_index=entry['after_journal_index'], label='SIMULATED')
    if kind == 'RECOVERY':
        amount = command['amount_krw']
        if type(amount) is not int or amount < 1:
            raise RecoveryError('INVALID_ARGUMENTS', 400)
        if amount > pos['claim_krw']:
            raise RecoveryError('RECOVERY_EXCEEDS_CLAIM')
        q = p['quote_witness']
        source = command['source_ref']
        consumed = state.get('recovery', {}).get('sources', {}).get(source_key(source['claim_id'], source['payee_label']), 0)
        from capital.setoff import observed_distribution
        eligible = observed_distribution({'distributed': q['distributed_krw'], 'recovery_due': q['recovery_due_krw']})
        expected_witness = {'source_ref': source, 'observed_eligible_krw': eligible,
                            'distributed_krw': q['distributed_krw'], 'recovery_due_krw': q['recovery_due_krw'],
                            'consumed_krw': consumed, 'state_digest': overlay.state_digest(state),
                            'advance_id': ref, 'claim_due_krw': pos['claim_krw']}
        if any(type(q[key]) is not int or q[key] < 0 for key in ('observed_eligible_krw', 'distributed_krw', 'recovery_due_krw', 'consumed_krw', 'claim_due_krw')):
            raise RecoveryError('RECOVERY_QUOTE_STALE')
        if q != expected_witness or sha(q) != command['quote_ref']:
            raise RecoveryError('RECOVERY_QUOTE_STALE')
        if amount > max(0, q['observed_eligible_krw'] - consumed):
            raise RecoveryError('RECOVERY_SOURCE_EXCEEDED')
        steps = waterfall(state, ref)
        step = steps[0 if source['claim_id'] == a['claim_id'] else 1]
        available = p['source_quotes']
        # Stamp the observed sources so replay also enforces the decided order.
        # Secondary set-off opens only after the bound-claim sources are exhausted.
        if step == steps[1] and any(q['waterfall_step'] == steps[0] and q['available_krw'] > 0
                                    for q in available):
            raise RecoveryError('RECOVERY_WATERFALL_ORDER')
        cumulative = amount + sum(e['amount_krw'] for e in state['sections']['recovery_ledger']
                                  if e['entry_kind'] == 'RECOVERY' and e['advance_id'] == ref and e['sim_day'] == day)
        base.update(amount_krw=amount, source_ref=source, quote_ref=command['quote_ref'], quote_witness=q,
                    source_quotes=available,
                    phase='POST_WRITEOFF' if r['writeoff_sim_day'] is not None else 'POST_DEFAULT',
                    waterfall_step=step)
        if r['writeoff_sim_day'] is not None:
            base['residual_claim_krw'] = pos['claim_krw'] - amount
        else:
            base['allocation'] = _split(pos, amount)
        amount = cumulative
    else:
        if r['writeoff_sim_day'] is not None or day < a['writeoff_eligible_sim_day'] or pos['principal_krw'] < 1:
            raise RecoveryError('WRITEOFF_NOT_ELIGIBLE')
        available = p['source_quotes']
        if any(q['available_krw'] > 0 for q in available) and not command.get('setoff_declined_reason'):
            raise RecoveryError('WRITEOFF_SETOFF_AVAILABLE')
        recognized, suspended = interest_unpaid_by_recognition(state, ref)
        steps = waterfall(state, ref)
        ledger = state['sections']['recovery_ledger']
        trace = [{'step': step, 'status': 'DECLINED' if any(q['waterfall_step'] == step and q['available_krw'] for q in available) else 'EXHAUSTED',
                  'absorbed_krw': sum(e['amount_krw'] for e in ledger if e['entry_kind'] == 'RECOVERY' and e['advance_id'] == ref and e['waterfall_step'] == step)} for step in steps[:2]]
        trace += [copy.deepcopy(policy['values']['reserve_step_when_unbuilt']['trace_row']),
                  {'step': steps[3], 'status': 'POSTED', 'absorbed_krw': pos['principal_krw']}]
        base.update(phase='POST_DEFAULT', default_sim_day=a['default_sim_day'],
                    writeoff_effective_sim_day=a['writeoff_eligible_sim_day'],
                    writeoff_principal_krw=pos['principal_krw'], accrued_interest_reversed_krw=recognized,
                    suspended_interest_released_krw=suspended, residual_claim_krw=pos['claim_krw'],
                    waterfall_trace=trace, source_quotes=available, loss_krw=pos['principal_krw'],
                    loss_bearer=policy['loss_bearer'], claim_status='RESIDUAL_CLAIM_RETAINED',
                    **policy['values']['reserve_step_when_unbuilt']['entry_marker'])
        amount = pos['principal_krw']
    base['authority'] = authorize('organizer', command.get('approvals', []), amount, policy, command.get('proposal_id'))
    return base


def effective_maturity(state, ref, standard):
    marker = state.get('margin', {}).get('advances', {}).get(ref, {})
    external = state.get('accelerations', {}).get(ref, {})
    return min(standard, marker.get('maturity_day', standard) if marker.get('status') == 'ACCELERATED' else standard,
               external.get('maturity_after', standard))


def fold_entry(state, entry):
    p = entry['payload']
    ref, kind = p['advance_id'], entry['kind']
    if state['terms_binding'] is None or p['policy']['terms_version'] != state['terms_binding']['terms_version']:
        raise overlay.OverlayError('recovery terms binding')
    if entry['sim_day'] != state['sim_day']:
        raise overlay.OverlayError('recovery entry day')
    try:
        expected = plan_payload(state, entry)
        if expected != p:
            raise ValueError('recovery calculation witness differs')
        if kind in ('default_anchor', 'acceleration_event'):
            expected_authority = authorize('organizer', p['command'].get('approvals', []), p['principal_krw'], p['policy'], p['command'].get('proposal_id'))
            if p['authority'] != expected_authority:
                raise ValueError('authority')
            key = 'default_anchors' if kind == 'default_anchor' else 'accelerations'
            state.setdefault(key, {})[ref] = copy.deepcopy(p)
            state['sections']['decision_records'].append({'overlay_id': entry['overlay_id'], 'record': kind.upper(), **copy.deepcopy(p)})
            return
        a = anchor(state, ref)
        if any(p[key] != a[key] for key in ('claim_id', 'beneficiary_role', 'tier', 'policy')):
            raise ValueError('recovery anchor identity')
        ledger = state.setdefault('recovery', {'advances': {}, 'sources': {}})
        r = ledger['advances'].setdefault(ref, copy.deepcopy(recovered(state, ref)))
        if kind == 'WRITEOFF':
            r.update(written_off_krw=p['writeoff_principal_krw'], residual_claim_krw=p['residual_claim_krw'], writeoff_sim_day=entry['sim_day'])
        else:
            if p['phase'] == 'POST_DEFAULT':
                for target, source in (('principal_recovered_krw', 'principal_krw'), ('paid_interest_krw', 'interest_krw'), ('paid_default_krw', 'default_interest_krw')):
                    r[target] += p['allocation'][source]
            else:
                r['residual_claim_krw'] = p['residual_claim_krw']
            source = p['source_ref']
            key = source_key(source['claim_id'], source['payee_label'])
            ledger['sources'][key] = ledger['sources'].get(key, 0) + p['amount_krw']
        state['sections']['recovery_ledger'].append(copy.deepcopy(p))
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise overlay.OverlayError('recovery semantic fold') from exc


def validate_entry(entry):
    p = entry['payload']
    required = {'advance_id', 'claim_id', 'beneficiary_role', 'tier', 'policy', 'command'}
    if type(p) is not dict or not required <= set(p):
        raise overlay.OverlayError('recovery payload')
    def walk(value):
        if type(value) is dict:
            if set(value) & {'instance_id', 'created_at', 'saved_at', 'timestamp', 'timestamps'}:
                raise overlay.OverlayError('recovery volatile key')
            for item in value.values(): walk(item)
        elif type(value) is list:
            for item in value: walk(item)
        elif type(value) not in (str, int, bool, type(None)) or (type(value) is int and value < 0):
            raise overlay.OverlayError('recovery value')
    walk(p)
    command = p['command']
    if type(command) is not dict:
        raise overlay.OverlayError('recovery command witness')
    kind = entry['kind']
    common = {'op', 'approvals'}
    optional = {'proposal_id'}
    if kind != 'default_anchor':
        common |= {'advance_ref', 'at_sim_day'}
    if kind == 'RECOVERY':
        common |= {'amount_krw', 'source_ref', 'quote_ref'}
    if kind == 'WRITEOFF':
        optional |= {'setoff_declined_reason'}
    if kind == 'acceleration_event':
        common |= {'event'}
    op = {'RECOVERY': 'post_recovery', 'WRITEOFF': 'post_writeoff',
          'default_anchor': 'default', 'acceleration_event': 'record_acceleration'}[kind]
    if (not common <= set(command) <= common | optional or command['op'] != op
            or (kind != 'default_anchor' and (command['advance_ref'] != p['advance_id'] or command['at_sim_day'] != entry['sim_day']))):
        raise overlay.OverlayError('recovery command witness')
    try:
        if approvals(command['approvals']) != command['approvals']:
            raise ValueError('noncanonical approvals')
    except (ValueError, TypeError) as exc:
        raise overlay.OverlayError('recovery approvals') from exc
    if entry['kind'] in ('default_anchor', 'acceleration_event') and (type(p.get('principal_krw')) is not int or p['principal_krw'] < 0):
        raise overlay.OverlayError('recovery principal')
    if type(p.get('policy')) is not dict or any(type(p['policy'].get(k)) is not int or p['policy'][k] < 1 for k in ('two_person_threshold_krw', 'writeoff_days_after_default')):
        raise overlay.OverlayError('recovery policy witness')
    if any(type(p[k]) is not str or not LABEL.fullmatch(p[k]) for k in ('advance_id', 'claim_id', 'beneficiary_role', 'tier')):
        raise overlay.OverlayError('recovery identity')


def entry(operation_id, kind, state, index, payload):
    result = {'overlay_id': operation_id, 'kind': kind, 'sim_day': state['sim_day'],
              'after_journal_index': index, 'payload': payload}
    result['payload'] = plan_payload(state, result)
    return result


def receipt(entry):
    return {'operation_id': entry['overlay_id'], 'op': entry['payload']['command']['op'],
            'outcome': 'APPLIED', 'sim_day': entry['sim_day'], 'recorded_posting': True,
            'f04_journal_written': False, 'label': 'SIMULATED', 'entry': copy.deepcopy(entry['payload'])}


def validate_links(entries, journal):
    """Dated defaults must identify the accepted F04 default and its outstanding principal."""
    for entry in entries:
        if entry['kind'] != 'default_anchor':
            continue
        p, n = entry['payload'], entry['after_journal_index']
        if n < 1 or n > len(journal):
            raise overlay.OverlayError('default link')
        if overlay.draw_day_for(entries, n - 1) != entry['sim_day']:
            raise overlay.OverlayError('default logical day link')
        row = journal[n - 1]
        if row['op'] != 'default' or row['advance_id'] != p['advance_id'] or row['idempotency_key'] != p['f04_operation_id']:
            raise overlay.OverlayError('default link')
        principal = 0
        for event in journal[:n]:
            if event['advance_id'] != p['advance_id']:
                continue
            if event['op'] == 'draw': principal = event['body']['amount'] if 'amount' in event['body'] else principal
            if event['op'] == 'offer': principal = event['body']['amount']
            if event['op'] == 'repay': principal -= event['body']['amount']
        if p['principal_krw'] != principal:
            raise overlay.OverlayError('default principal link')
