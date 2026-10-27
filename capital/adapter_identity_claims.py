"""CLAIM_CONFORMANCE for the pinned identity draft and local fixture profile.

Fake folds supply event-item diagnostics. CapitalService actions supply explicitly
labelled command/read analogues, never kernel or authenticated provider evidence.
All results are SIMULATED; no event identity source or durable alias is adopted.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from capital import observation, overlay, upstream_claims
from capital.ports import ObservationPort
from capital.read_model_claims import ADVANCE_ID, OPERATIONS
from capital.resources import ROOT
from capital.service import ApiError, CapitalService
from capital.upstream_claims import ClaimTableError

PINNED_SHA = observation.CONTRACT_REVISION
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_ADAPTER_IDENTITY_CLAIMS_V1'
SOURCE_DOC = 'docs/contracts/ADAPTER_EVENT_IDENTITY.md'
SECTIONS = {'identity.': '## 2. 정체성 용어', 'cardinality.': '## 3. 관계와 기수',
            'case.': '## 5. 경우 행렬', 'boundary.': '## 5. 경우 행렬'}
FACADE_EVIDENCE = ('COMMAND_BOUNDARY_ANALOGUE', 'FACADE_READ_ANALOGUE',
                   'SCENARIO_FIXTURE_ANALOGUE', 'ISOLATION_ONLY')
BOUNDARY_NOTE = 'COMMAND_RECEIPT_IDEMPOTENCY_IS_NOT_EVENT_IDENTITY'
CASE_MAP = {
    'redelivery': ('같은 전송이 다시 도착', ('case.redelivery',)),
    'new-transmission-same-fact': ('새 전송, 같은 사실', ('case.new-transmission',)),
    'lost-ack': ('수신 뒤 응답만 유실', ('case.lost-ack',)),
    'snapshot-repeat': ('같은 사실의 snapshot 반복', ('case.snapshot-repeat',)),
    'same-id-different-content': ('같은 `event_id`, 다른 내용', ('case.same-id-different-content',)),
    'state-change-new-item': ('이후 상태 변화 (예: DONE→CANCELED)', ('case.state-change',)),
    'partial-cancel-separate': ('반환 종류의 **별도** 항목', ('case.partial-cancel',)),
    'out-of-order': ('새 snapshot 뒤에 옛 snapshot', ('case.out-of-order',)),
    'late-capture': ('만료 뒤 늦은 capture', ('case.late-capture',)),
    'unmatched': ('계약 용어 **UNMATCHED**', ('case.unmatched',)),
    'other-scope': ('다른 MID, 환경, 또는 수단', tuple('case.other-scope.' + x for x in
                    ('provider', 'account', 'environment', 'profile-version', 'method'))),
}
KERNEL_TERMS = ('observe_capture', 'DuplicateEffect', 'Review', 'ClockRegression',
                'ReturnRequired', 'UnknownOperation', 'Capacity', 'OperationAlreadyBound')
# Independent projection: an adapter dropping any normalized field must fail.
FACT_FIELDS = ('provider', 'account', 'environment', 'profile_version', 'payment_key',
               'order_id', 'operation', 'kind', 'amount', 'currency', 'method', 'status',
               'occurred_at', 'offset', 'api_version', 'product')


def table_path(path=None):
    return Path(path) if path is not None else Path(str(ROOT)).resolve().parent / 'tests/adapter_identity_claims.json'


def load_table(path=None):
    return validate_table(upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA))


def validate_table(data):
    upstream_claims.validate_table(data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    if data.get('results') != 'SIMULATED' or data.get('semantic_conformance') is not False:
        raise ClaimTableError('results must be SIMULATED with semantic_conformance false')
    seen = set()
    required = {check for _, checks in CASE_MAP.values() for check in checks}
    for row in data['claims']:
        check = row['check_id']
        prefix = next((p for p in SECTIONS if check.startswith(p)), None)
        if row['source_doc'] != SOURCE_DOC or prefix is None or row['section'] != SECTIONS[prefix]:
            raise ClaimTableError('unmapped source or section')
        if check in seen:
            raise ClaimTableError('duplicate check_id ' + check)
        seen.add(check)
        if 'SEMANTIC_CONFORMANCE' in row['claim'] or any(term in row['claim'] for term in KERNEL_TERMS):
            raise ClaimTableError('claim asserts an excluded semantic or kernel boundary')
        if 'case' in row:
            case = row['case']
            if not isinstance(case, str) or case not in CASE_MAP:
                raise ClaimTableError('unknown case')
            needle, checks = CASE_MAP[case]
            expected = row['expected']
            if row['needle'] != needle or check not in checks or type(expected) is not dict or expected.get('case') != case:
                raise ClaimTableError('case/check/needle mismatch')
            facade = expected.get('facade')
            if (type(facade) is not dict or facade.get('evidence') not in FACADE_EVIDENCE
                    or type(facade.get('action')) is not str or not facade['action'].strip()):
                raise ClaimTableError('missing facade evidence/action')
            if facade['evidence'] == 'COMMAND_BOUNDARY_ANALOGUE' and facade.get('boundary_note') != BOUNDARY_NOTE:
                raise ClaimTableError('command analogue requires boundary_note')
            if expected.get('label') != 'SIMULATED':
                raise ClaimTableError('case result must be SIMULATED')
        elif check.startswith('case.'):
            raise ClaimTableError('case check lacks case')
    if not required <= seen:
        raise ClaimTableError('missing case checks: ' + ', '.join(sorted(required - seen)))
    return data


def run_claims(table, *, checks=None):
    validate_table(table)
    return upstream_claims.run_claims(table, checks=CHECKS if checks is None else checks,
                                     format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def check_protocol(protocol_dir, table=None):
    table = load_table() if table is None else validate_table(table)
    return upstream_claims.check_protocol(protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def _corpus():
    return json.loads((table_path().parent / 'vectors/provider_facts.json').read_text(encoding='utf-8'))


def _fresh():
    service = CapitalService()
    bodies = []
    for op, args in OPERATIONS:
        body = _body(service, 'sim-identity-' + op.replace('_', '-'), op, copy.deepcopy(args))
        if service.execute(body)['outcome'] != 'ACCEPTED':
            raise ClaimTableError('seed rejected ' + op)
        bodies.append(body)
    return service, bodies


def _body(service, operation_id, op, args, **extra):
    return dict(instance_id=service.instance_id, operation_id=operation_id,
                op=op, advance_id=ADVANCE_ID, args=args, **extra)


def _frozen(service):
    return copy.deepcopy((service.machine.canonical_state(), len(service.machine.export_journal()),
                          overlay.state_digest(overlay.fold(service.overlay_entries)), service.receipts))


def _fold(facts, bindings):
    fake = observation.LocalFakeObservation()
    if not isinstance(fake, ObservationPort):
        raise ClaimTableError('fake does not satisfy ObservationPort')
    return fake.fold(copy.deepcopy(facts), bindings=copy.deepcopy(bindings))


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def _fake_summary(result, facts):
    first = {}
    for fact in facts:
        key = tuple(fact[name] for name in ('provider', 'account', 'environment', 'profile_version', 'item_key'))
        first.setdefault(key, {name: fact[name] for name in FACT_FIELDS})
    originals = list(first.values())
    items = result['event_items']
    return {
        'items': len(items), 'statuses': [item['status'] for item in items],
        'binding_statuses': [item['binding_status'] for item in items],
        'duplicates': [x['delivery_index'] for x in result['duplicates']],
        'conflicts': [x['delivery_index'] for x in result['conflicts']],
        'originals_preserved': [x['normalized_fact'] for x in items] == originals,
        'evidence_preserved': [x['evidence_digest'] for x in items] == [_hash(x) for x in originals],
        'transmissions_preserved': [x['transmission'] for x in result['deliveries']] == [x['transmission'] for x in facts],
        'conflicting_evidence_preserved': all(
            x['incoming'] == {name: facts[x['delivery_index']][name] for name in FACT_FIELDS}
            and x['evidence_digest'] == _hash(x['incoming'])
            and x['original'] in originals for x in result['conflicts']),
        'no_effects': result['applied_effects'] == [],
        'safe': all(x.get('label') == 'SIMULATED' and x.get('applied') is False
                    and x.get('funds_executed') is False for x in
                    [result] + sum((result[k] for k in ('event_items', 'deliveries', 'duplicates', 'conflicts')), [])),
    }


def _error(call):
    try:
        call()
    except ApiError as exc:
        return {'code': exc.code, 'status': exc.status}
    return None


def _facade(service, bodies, action, kind='COMMAND_BOUNDARY_ANALOGUE'):
    evidence = {'evidence': kind, 'action': action}
    if kind == 'COMMAND_BOUNDARY_ANALOGUE':
        evidence['boundary_note'] = BOUNDARY_NOTE
    before = copy.deepcopy(service.receipts)
    count = len(before)
    if action in ('replay-draw', 'reordered-draw', 'replay-earliest-offer'):
        body = bodies[0 if action == 'replay-earliest-offer' else -1]
        if action == 'reordered-draw':
            body = dict(reversed(list(body.items())))
        frozen = _frozen(service)
        result = service.execute(body)
        expected = copy.deepcopy(before[body['operation_id']]['receipt'])
        expected['transport_duplicate'] = True
        evidence.update(transport_duplicate=result['transport_duplicate'], receipt_equal=result == expected,
                        state_preserved=_frozen(service) == frozen)
    elif action in ('discard-reply-lookup', 'new-reconcile', 'new-approve'):
        op = 'approve' if action == 'new-approve' else 'reconcile'
        body = _body(service, 'sim-identity-new', op, {})
        service.execute(body)  # deliberately discard the reply; consult only stored receipt
        receipt = service.operation(body['operation_id'], service.instance_id)
        evidence.update(outcome=receipt['outcome'], receipts_added=len(service.receipts) - count,
                        seed_receipts_preserved=all(service.operation(k, service.instance_id) == v['receipt'] for k, v in before.items()))
        if action == 'discard-reply-lookup':
            unknown = service.operation('sim-never-sent', service.instance_id)
            evidence.update(stored_receipt_equal=receipt == service.receipts[body['operation_id']]['receipt'],
                            unknown=unknown['outcome'], retry_authorized=unknown['retry_authorized'])
    elif action in ('conflicting-draw', 'foreign-instance', 'foreign-asset'):
        body = copy.deepcopy(bodies[-1])
        if action == 'conflicting-draw':
            body['args'] = {'unexpected': 'SIMULATED'}
        elif action == 'foreign-instance':
            body['instance_id'] = 'sim-foreign-instance'
        else:
            body['asset'] = {'currency': 'SIMULATED_OTHER_ASSET'}
        frozen = _frozen(service)
        evidence.update(error=_error(lambda: service.execute(body)), state_preserved=_frozen(service) == frozen)
        if action == 'conflicting-draw':
            step = service.scenarios('duplicate-statement')['scenario']['steps'][2]
            evidence.update(scenario_error=step['error'], rejection_preserves_state=any(
                x == {'predicate': 'REJECTION_PRESERVES_STATE', 'matched': True} for x in step['checks']))
    elif action == 'reject-unmatched':
        frozen = (service.machine.canonical_state(), copy.deepcopy(service.case_fixtures))
        receipt = service.execute(dict(_body(service, 'sim-identity-unmatched', 'bind_settlement', {}), advance_id='sim-unmatched-1'))
        evidence.update(outcome=receipt['outcome'], error=receipt['error'],
                        state_preserved=frozen == (service.machine.canonical_state(), service.case_fixtures))
    elif action == 'repeat-snapshot-and-statement':
        scenario = service.scenarios('duplicate-statement')['scenario']
        a, b = scenario['steps'][:2]
        evidence.update(duplicate=b['duplicate'], same_view=a['view'] == b['view'],
                        snapshot_equal=service.snapshot() == service.snapshot())
    elif action == 'separate-cancel-acceptances':
        steps = service.scenarios('full-after')['scenario']['steps'][3:6]
        evidence.update(outcomes=[s['outcome'] for s in steps], duplicates=[s['duplicate'] for s in steps],
                        source_ids=[s['args']['source_id'] for s in steps])
    elif action == 'late-cash-preserves-refund':
        scenario = service.scenarios('late-cash')['scenario']
        a, b = scenario['steps'][:2]
        evidence.update(outcome=b['outcome'], refund_preserved=a['view']['refund_face'] == b['view']['refund_face'],
                        all_predicates_matched=scenario['all_predicates_matched'], funds_executed=scenario['funds_executed'])
    elif action == 'read-isolation-only':
        frozen = _frozen(service)
        service.snapshot()
        evidence.update(state_preserved=_frozen(service) == frozen)
    else:
        raise ClaimTableError('unknown facade action')
    return evidence


def _case(case, patches, action, kind='COMMAND_BOUNDARY_ANALOGUE', *, unmatched=False, reverse=False, divergence=None):
    corpus = _corpus()
    facts = [dict(copy.deepcopy(corpus['base_fact']), **copy.deepcopy(patch)) for patch in patches]
    bindings = [] if unmatched else corpus['bindings']
    service, bodies = _fresh()
    before = _frozen(service)
    result = _fold(facts, bindings)
    summary = _fake_summary(result, facts)
    if reverse:
        reversed_result = _fold(list(reversed(facts)), bindings)
        def by_id(output):
            return {x['event_item_id']: x['evidence_digest'] for x in output['event_items']}
        summary['order_independent'] = by_id(result) == by_id(reversed_result)
    if case == 'late-capture':
        summary['times_separate'] = all(
            'received_at' not in x['normalized_fact'] and x['normalized_fact']['occurred_at'] == f['occurred_at']
            and x['normalized_fact']['offset'] == f['offset'] for x, f in zip(result['event_items'], facts))
    if divergence:
        summary['fixture_divergence'] = divergence
        summary['incoming_method'] = result['conflicts'][0]['incoming']['method']
    isolated = _frozen(service) == before
    return {'case': case, 'fake': summary, 'facade': _facade(service, bodies, action, kind),
            'isolation': isolated, 'label': 'SIMULATED'}


def check_redelivery():
    return _case('redelivery', [{}, {}], 'replay-draw')


def check_new_transmission():
    return _case('new-transmission-same-fact', [{}, {'transmission': {
        'id': 'sim-delivery-2', 'raw_evidence_ref': 'sim-raw-2', 'received_at': 'sim-receive-2'}}], 'reordered-draw')


def check_lost_ack():
    return _case('lost-ack', [{}, {}], 'discard-reply-lookup')


def check_snapshot_repeat():
    return _case('snapshot-repeat', [{}, {}, {}], 'repeat-snapshot-and-statement', 'SCENARIO_FIXTURE_ANALOGUE')


def check_conflict():
    return _case('same-id-different-content', [{}, {'amount': 999}, {}], 'conflicting-draw')


def check_state_change():
    return _case('state-change-new-item', [{}, {'item_key': 'sim-canceled-1', 'status': 'CANCELED'}], 'new-reconcile')


def check_partial_cancel():
    return _case('partial-cancel-separate', [{}, {'item_key': 'sim-cancel-1', 'kind': 'return', 'amount': 200},
                  {'item_key': 'sim-cancel-2', 'kind': 'return', 'amount': 200}],
                 'separate-cancel-acceptances', 'SCENARIO_FIXTURE_ANALOGUE')


def check_out_of_order():
    return _case('out-of-order', [{}, {'item_key': 'sim-canceled-1', 'status': 'CANCELED'}],
                 'replay-earliest-offer', reverse=True)


def check_late_capture():
    return _case('late-capture', [{'item_key': 'sim-canceled-1', 'status': 'CANCELED'},
                 {'offset': '+09:00', 'occurred_at': '2026-10-01T11:00:00', 'transmission': {
                     'id': 'sim-late-delivery', 'raw_evidence_ref': 'sim-late-raw', 'received_at': 'sim-receive-2'}}],
                 'late-cash-preserves-refund', 'SCENARIO_FIXTURE_ANALOGUE')


def check_unmatched():
    return _case('unmatched', [{}, {'amount': 999}, {}], 'reject-unmatched', unmatched=True)


def _scope(field):
    return _case('other-scope', [{}, {field: 'sim-other-' + field}],
                 'foreign-instance' if field == 'environment' else 'read-isolation-only',
                 'COMMAND_BOUNDARY_ANALOGUE' if field == 'environment' else 'ISOLATION_ONLY')


def check_method():
    return _case('other-scope', [{}, {'method': 'sim-other-method'}], 'foreign-asset',
                 divergence='METHOD_IS_CONTENT_NOT_SCOPE_IN_LOCAL_PROFILE')


def check_command_vs_event():
    value = _case('command-vs-event', [{}, {'transmission': {
        'id': 'sim-delivery-2', 'raw_evidence_ref': 'sim-raw-2', 'received_at': 'sim-receive-2'}}], 'new-approve')
    return value


def _identity(name):
    corpus = _corpus()
    result = _fold([corpus['base_fact']], corpus['bindings'])
    item = result['event_items'][0]
    if name == 'transmission':
        return 'transmission' not in item['normalized_fact'] and result['deliveries'][0]['transmission'] == corpus['base_fact']['transmission']
    if name == 'raw-evidence':
        return 'raw_evidence_ref' not in item['normalized_fact'] and result['deliveries'][0]['transmission']['raw_evidence_ref'] == 'sim-raw-1'
    if name == 'payment':
        return [item['normalized_fact'][k] for k in ('provider', 'account', 'environment', 'payment_key', 'order_id')]
    if name == 'fact-key':
        return item['scoped_key']['item_key']
    if name == 'event-item':
        return item['event_item_id'].startswith('sim-event-') and item['event_item_id'] != item['scoped_key']['item_key']
    return item['normalized_fact']['operation']


def _cardinality(name):
    corpus = _corpus()
    fact = corpus['base_fact']
    if name == 'transmission-items':
        result = _fold([fact, fact], corpus['bindings'])
        return [len(result['deliveries']), len(result['event_items'])]
    if name == 'payment-items':
        result = _fold([fact, dict(fact, item_key='sim-canceled-1', status='CANCELED')], corpus['bindings'])
        return [len({x['normalized_fact']['payment_key'] for x in result['event_items']}), len(result['event_items'])]
    field = 'payment_key' if name == 'operation-payment' else 'order_id'
    result = _fold([dict(fact, **{field: 'sim-other'})], corpus['bindings'])
    return {'status': result['event_items'][0]['status'], 'no_effects': result['applied_effects'] == []}


def _boundary(name):
    corpus = _corpus()
    result = _fold([corpus['base_fact']], corpus['bindings'])
    if name == 'safe-items':
        return _fake_summary(result, [corpus['base_fact']])['safe']
    return result[name]


CHECKS = {
    'case.redelivery': check_redelivery, 'case.new-transmission': check_new_transmission,
    'case.lost-ack': check_lost_ack, 'case.snapshot-repeat': check_snapshot_repeat,
    'case.same-id-different-content': check_conflict, 'case.state-change': check_state_change,
    'case.partial-cancel': check_partial_cancel, 'case.out-of-order': check_out_of_order,
    'case.late-capture': check_late_capture, 'case.unmatched': check_unmatched,
    'case.other-scope.method': check_method, 'boundary.command-vs-event': check_command_vs_event,
}
for _field in ('provider', 'account', 'environment', 'profile-version'):
    CHECKS['case.other-scope.' + _field] = lambda field=_field: _scope(field.replace('-', '_'))
for _name in ('transmission', 'raw-evidence', 'payment', 'fact-key', 'event-item', 'operation'):
    CHECKS['identity.' + _name] = lambda name=_name: _identity(name)
for _name in ('transmission-items', 'payment-items', 'operation-payment', 'operation-order'):
    CHECKS['cardinality.' + _name] = lambda name=_name: _cardinality(name)
for _name in ('semantic_conformance', 'binding_status', 'applied_effects', 'safe-items'):
    CHECKS['boundary.' + _name] = lambda name=_name: _boundary(name)
