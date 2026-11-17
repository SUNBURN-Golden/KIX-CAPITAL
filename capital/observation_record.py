"""SIMULATED organizer assertions, never provider confirmation or cash resources.

The decision's external_facts journal is exposed as state.observations for the
provider-capture-recon node. Pure replay does not load policy or persist arithmetic.
Contextual admission/restoration checks load the provisional adopted policy.
"""
from __future__ import annotations

import copy
import re
from collections import Counter

from capital import assets, observation, overlay, recovery
from capital.export import VOLATILE_KEYS
from capital.terms import read_decision_block

NOTE = 'CAPITAL_OBSERVATION_RECORD.md'
OP = 'record_external_fact'
KIND = 'EXTERNAL_FACT'
CLASS = 'PROVIDER_PAYMENT_CAPTURE'
CHECK_ID = 'recorded_captures_vs_claim_face'
PROVENANCE = 'DERIVED_FROM_UNVERIFIED_ASSERTED'
CONSTANTS = {'label': 'SIMULATED', 'verification': 'UNVERIFIED_ASSERTED',
             'recorded_by_role': 'organizer', 'funds_executed': False,
             'provider_call_made': False, 'legal_effect': 'NOT_ASSESSED'}
FIELDS = {'fact_class', 'claim_id', 'order_ref', 'amount_krw', 'claimed_provider_ref',
          'sim_day', 'effective_sim_day', 'captured_sim_day', 'authority'}
OPTIONAL = {'supersedes_fact_id'}
EVENT_ID = re.compile(r'\Asim-event-([0-9a-f]{64})\Z')
SYNTHETIC = re.compile(r'\A(?:sim|demo)-[A-Za-z0-9._:-]+\Z')
HASH = re.compile(r'\A[0-9a-f]{64}\Z')
PERSONAL_KEYS = frozenset({'name', 'full_name', 'person_name', 'customer_name', 'buyer_name',
    'email', 'phone', 'address', 'personal_data', 'pii', 'account', 'account_number',
    'bank_account', 'payment_key', 'transmission', 'occurred_at', 'received_at', 'timestamp',
    'offset', 'raw_evidence_ref', 'credentials', 'secret'})


class FactError(overlay.OverlayError):
    def __init__(self, code='INVALID_ARGUMENTS', status=400, detail=None):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(code)


def load_policy(note=None):
    block = read_decision_block(overlay.default_note_path(NOTE) if note is None else note)
    names = ('fact_class_set', 'verification_label_vocabulary', 'recording_authority',
             'fact_fold_location', 'recon_consumption_rule', 'derived_value_source_rule',
             'capacity_bounds', 'digest_export_effect')
    values = {name: overlay._adopted(block, name) for name in names}
    if any(value is None for value in values.values()):
        return None
    bounds = values['capacity_bounds']
    keys = ('max_fact_entries', 'max_facts_per_claim', 'max_supersede_chain_depth', 'string_field_bytes')
    if any(type(bounds.get(k)) is not int or bounds[k] < 1 for k in keys):
        return None
    constants = (block or {}).get('recorded_fact_constants')
    if (type(constants) is not dict or set(constants) != set(CONSTANTS)
            or any(type(constants[k]) is not type(v) or constants[k] != v for k, v in CONSTANTS.items())
            or values['verification_label_vocabulary'].get('recordable') != [constants['verification']]
            or CLASS not in values['fact_class_set'].get('classes', {})):
        return None
    return {'bounds': {k: bounds[k] for k in keys}, 'constants': copy.deepcopy(constants),
            'classes': list(values['fact_class_set']['classes'])}


def reject_volatile(value, *, transport=False):
    if type(value) is dict:
        for key, item in value.items():
            normalized = key.lower() if type(key) is str else key
            if (normalized in VOLATILE_KEYS or normalized in PERSONAL_KEYS) and not (transport and key == 'instance_id'):
                raise FactError('OVERLAY_VOLATILE_KEY')
            reject_volatile(item)
    elif type(value) is list:
        for item in value:
            reject_volatile(item)


def _token(value):
    return type(value) is str and recovery.LABEL.fullmatch(value) is not None


def validate_payload(payload, *, stored=False):
    reject_volatile(payload)
    if type(payload) is not dict:
        raise FactError()
    if payload.get('verification') in ('PROVIDER_CONFIRMED', 'BANK_MATCHED', 'CHAIN_CONFIRMED'):
        raise FactError('FACT_VERIFICATION_NOT_BOUND', 409)
    if payload.get('fact_class') != CLASS:
        if payload.get('fact_class') in ('SETTLEMENT_CASH_ARRIVAL', 'REFUND_EVENT_OBSERVED'):
            raise FactError('NOT_BOUND', 409)
        raise FactError('FACT_CLASS_NOT_ADOPTED')
    constants = CONSTANTS if stored else {k: v for k, v in CONSTANTS.items() if k != 'recorded_by_role'}
    required = FIELDS | set(constants)
    if not required <= set(payload) <= required | OPTIONAL:
        raise FactError()
    if any(type(payload[k]) is not type(v) or payload[k] != v for k, v in constants.items()):
        raise FactError()
    for key in ('claim_id', 'order_ref', 'claimed_provider_ref', *OPTIONAL & payload.keys()):
        if not _token(payload[key]):
            raise FactError()
    if SYNTHETIC.fullmatch(payload['order_ref']) is None:
        raise FactError()
    ref = payload['claimed_provider_ref']
    if not (HASH.fullmatch(ref) or SYNTHETIC.fullmatch(ref)):
        raise FactError()
    if type(payload['amount_krw']) is not int or not 1 <= payload['amount_krw'] <= assets.KRW['max_atoms']:
        raise FactError()
    for key in ('sim_day', 'effective_sim_day', 'captured_sim_day'):
        if type(payload[key]) is not int or payload[key] < 0:
            raise FactError()
    if payload['effective_sim_day'] > payload['sim_day'] or payload['captured_sim_day'] > payload['sim_day']:
        raise FactError('FACT_FUTURE_DAY', 409)
    if payload['captured_sim_day'] != payload['effective_sim_day']:
        raise FactError()
    authority = payload['authority']
    if (type(authority) is not dict or not {'role', 'approvals'} <= set(authority) <= {'role', 'approvals', 'proposal_id'}
            or authority['role'] != 'organizer'):
        raise FactError()
    try:
        if recovery.approvals(authority['approvals']) != authority['approvals']:
            raise FactError()
    except recovery.RecoveryError as exc:
        raise FactError() from exc
    if 'proposal_id' in authority and not _token(authority['proposal_id']):
        raise FactError()


def validate_entry(entry):
    validate_payload(entry['payload'], stored=True)
    if not _token(entry['overlay_id']) or entry['sim_day'] != entry['payload']['sim_day']:
        raise FactError()


def fold_entry(state, entry):
    if entry['sim_day'] != state['sim_day']:
        raise FactError()
    facts = state.setdefault('observations', {})
    payload = entry['payload']
    target = payload.get('supersedes_fact_id')
    if target is not None:
        prior = facts.get(target)
        if (prior is None or prior['status'] != 'ACTIVE'
                or (prior['claim_id'], prior['fact_class']) != (payload['claim_id'], payload['fact_class'])):
            raise FactError('FACT_SUPERSEDE_INVALID', 409)
        prior['status'] = 'SUPERSEDED'
    facts[entry['overlay_id']] = {**copy.deepcopy(payload), 'status': 'ACTIVE'}


def _strings(value):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for item in value.values():
            yield from _strings(item)
    elif type(value) is list:
        for item in value:
            yield from _strings(item)


def validate_links(entries, journal, fixtures, policy=None):
    """Replay references and loaded limits, independently of checksums and cached fold."""
    facts = [e for e in entries if e['kind'] == KIND]
    if not facts:
        return
    policy = load_policy() if policy is None else policy
    if policy is None:
        raise FactError('NOT_BOUND', 409)
    bounds = policy['bounds']
    rows = fixtures.rows if hasattr(fixtures, 'rows') else fixtures
    unique, depths, counts = {}, {}, Counter()
    for e in facts:
        validate_entry(e)
        key, p = e['overlay_id'], e['payload']
        if key in unique:
            if e != unique[key]:
                raise FactError('FACT_IDEMPOTENCY_CONFLICT', 409)
            continue
        if p['claim_id'] not in rows:
            raise FactError('FACT_CLAIM_UNKNOWN', 409)
        if type(e['after_journal_index']) is not int or not 0 <= e['after_journal_index'] <= len(journal):
            raise FactError()
        if any(len(s.encode('utf-8')) > bounds['string_field_bytes'] for s in _strings(e)):
            raise FactError('SIMULATION_CAPACITY', 409, {'scope': 'external_facts'})
        target = p.get('supersedes_fact_id')
        if target is not None and (target not in unique or target == key):
            raise FactError('FACT_SUPERSEDE_INVALID', 409)
        depth = 0 if target is None else depths[target] + 1
        if depth > bounds['max_supersede_chain_depth']:
            raise FactError('FACT_SUPERSEDE_DEPTH', 409)
        depths[key], unique[key] = depth, e
        counts[p['claim_id']] += 1
        if len(unique) > bounds['max_fact_entries'] or counts[p['claim_id']] > bounds['max_facts_per_claim']:
            raise FactError('SIMULATION_CAPACITY', 409, {'scope': 'external_facts'})
    overlay.fold(entries, len(journal))
    global_bounds = overlay.load_bounds()
    if global_bounds is None:
        raise FactError('NOT_BOUND', 409)
    if (len(entries) > global_bounds['OVERLAY_MAX_ENTRIES']
            or any(overlay.entry_size(e) > global_bounds['OVERLAY_ENTRY_MAX_BYTES']
                   or e['sim_day'] > global_bounds['SIM_DAY_MAX'] for e in facts)):
        raise FactError('SIMULATION_CAPACITY', 409, {'scope': 'external_facts'})


def receipt(entry):
    return {'operation_id': entry['overlay_id'], 'op': OP, 'outcome': 'APPLIED',
            'at_sim_day': entry['sim_day'], 'sim_day': entry['sim_day'],
            'entry': copy.deepcopy(entry['payload'])}


def project_fake(output, *, claim_id, sim_day, captured_sim_day, instance_id):
    """Project complete fake output; explicit linkage supplies days, never timestamps.

    A 64-character event hash survives in full. Redelivery folds to one command;
    retained conflict content is never recordable, regardless of delivery order.
    """
    if (type(output) is not dict or output.get('identity_profile') != observation.PROFILE
            or output.get('label') != 'SIMULATED' or output.get('applied') is not False
            or output.get('funds_executed') is not False or type(output.get('event_items')) is not list):
        raise FactError()
    policy = load_policy()
    if policy is None:
        raise FactError('NOT_BOUND', 409)
    commands, diagnostics = [], []
    for item in output['event_items']:
        event_id = item.get('event_item_id')
        match = EVENT_ID.fullmatch(event_id) if type(event_id) is str else None
        if match is None:
            raise FactError()
        reason = None
        if item.get('status') != 'MATCHED_FIXTURE' or item.get('binding_status') != 'MATCHED_FIXTURE':
            reason = item.get('status') if item.get('status') != 'MATCHED_FIXTURE' else item.get('binding_status')
        fact = item.get('normalized_fact', {})
        if reason is None and (fact.get('kind') != 'capture' or fact.get('status') != 'DONE'):
            reason = 'NON_CAPTURE_OR_NOT_DONE'
        if reason is not None:
            diagnostics.append({'event_item_id': event_id, 'recordable': False, 'reason': reason,
                                'label': 'SIMULATED'})
            continue
        payload = {**{k: v for k, v in policy['constants'].items() if k != 'recorded_by_role'},
                   'fact_class': CLASS, 'claim_id': claim_id, 'order_ref': fact.get('order_id'),
                   'claimed_provider_ref': match[1], 'amount_krw': fact.get('amount'),
                   'sim_day': sim_day, 'effective_sim_day': captured_sim_day, 'captured_sim_day': captured_sim_day,
                   'authority': {'role': 'organizer', 'approvals': []}}
        validate_payload(payload)
        if fact.get('currency') != 'KRW':
            raise FactError()
        commands.append({'instance_id': instance_id, 'operation_id': match[1], 'op': OP,
                         'at_sim_day': sim_day, 'payload': payload})
    return {'commands': commands, 'diagnostics': diagnostics, 'label': 'SIMULATED'}


def capture_check(entries, journal, fixtures):
    """Diagnostic comparison only. Draws/settlement are independently labelled inputs."""
    validate_links(entries, journal, fixtures)
    facts = overlay.fold(entries, len(journal)).get('observations', {})
    if not facts:
        return None
    rows = fixtures.rows if hasattr(fixtures, 'rows') else fixtures
    offers = {e['advance_id']: e['body'] for e in journal if e['op'] == 'offer'}
    population = []
    for claim_id in sorted(rows):
        claim = fixtures.view(claim_id)['claim'] if hasattr(fixtures, 'view') else rows[claim_id]['claim']
        active = [{'fact_id': key, **copy.deepcopy(p)} for key, p in sorted(facts.items())
                  if p['claim_id'] == claim_id and p['status'] == 'ACTIVE']
        total = sum(p['amount_krw'] for p in active)
        draws = [{'operation_id': e['idempotency_key'], 'advance_id': e['advance_id'],
                  'amount_krw': offers[e['advance_id']]['amount'], 'label': 'SIMULATED_F04_ACCEPTED_DRAW'} for e in journal
                 if e['op'] == 'draw' and offers.get(e['advance_id'], {}).get('face', {}).get('claim_id') == claim_id]
        status = 'NO_FACTS' if not active else ('MATCH' if total == claim['gross'] else 'ASSERTED_MISMATCH')
        population.append({'claim_id': claim_id, 'status': status, 'source_fact_ids': [p['fact_id'] for p in active],
                           'active_facts': active, 'capture_sum_krw': total, 'expected_claim_gross_krw': claim['gross'],
                           'draw_diagnostics': draws, 'settlement_diagnostics': {
                               'label': 'READ_ONLY_FIXTURE', 'confirmed_cash_krw': claim['confirmed_cash'],
                               'distributed_krw': sum(line['distributed'] for line in claim['obligations'])}})
    status = ('ASSERTED_MISMATCH' if any(r['status'] == 'ASSERTED_MISMATCH' for r in population)
              else 'MATCH' if any(r['status'] == 'MATCH' for r in population) else 'NO_FACTS')
    return {'id': CHECK_ID, 'status': status, 'derived': True, 'derivation': CHECK_ID,
            'provenance': PROVENANCE, 'label': 'SIMULATED', 'verification': 'UNVERIFIED_ASSERTED',
            'source_fact_ids': sorted(k for k, p in facts.items() if p['status'] == 'ACTIVE'),
            'diagnostics': ['OBSERVED_FACT_MISMATCH'] if status == 'ASSERTED_MISMATCH' else [],
            'coverage': {'observed_claims': sum(bool(r['source_fact_ids']) for r in population),
                         'total_claims': len(population), 'completeness': 'NOT_BOUND'}, 'claims': population}
