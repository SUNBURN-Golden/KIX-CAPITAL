"""In-process SIMULATED observation diagnostics; no IO or retained fold state.

This local JSON/SHA256 fixture profile exercises the separately pinned adapter
identity draft. It does not implement authenticated provider facts, KIX-BCS,
16-byte kernel aliases, durable custody, or kernel conflict quarantine.
"""
import copy
import hashlib
import json


PROFILE = 'LOCAL_SYNTHETIC_JSON_SHA256_V1'
CONTRACT_REVISION = 'e2a029d8ac3af7575888dac22fc4bf173ebec232'
CONTRACT_SHA256 = 'e640151bbdff15b67584337e6cdb6e95b2cc9c060f48dcc9de45df84f8de5345'
SCOPE = ('provider', 'account', 'environment', 'profile_version')
CONTENT = ('payment_key', 'order_id', 'operation', 'kind', 'amount', 'currency',
           'method', 'status', 'occurred_at', 'offset', 'api_version', 'product')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def safe(**fields):
    return dict(fields, label='SIMULATED', applied=False, funds_executed=False)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def normalize(fact):
    if not isinstance(fact, dict) or fact.get('provenance') != 'SYNTHETIC_FIXTURE':
        raise ValueError('synthetic fixture provenance required')
    required = set(SCOPE + CONTENT + ('item_key', 'provenance', 'transmission'))
    if set(fact) != required:
        raise ValueError('unexpected or missing fact fields')
    for name in SCOPE + CONTENT + ('item_key',):
        if name not in ('amount', 'offset') and not _text(fact[name]):
            raise ValueError(f'{name} must be non-empty text')
    if type(fact['amount']) is not int or fact['amount'] < 0 or fact['currency'] != 'KRW':
        raise ValueError('amount must be nonnegative integer KRW')
    if fact['offset'] is not None and not _text(fact['offset']):
        raise ValueError('offset must be supplied text or null; no timezone is inferred')
    transmission = fact['transmission']
    if not isinstance(transmission, dict) or set(transmission) != {'id', 'raw_evidence_ref', 'received_at'}:
        raise ValueError('transmission metadata required')
    if not all(_text(value) for value in transmission.values()):
        raise ValueError('transmission metadata must be text')
    key = {name: fact[name] for name in SCOPE + ('item_key',)}
    content = {name: fact[name] for name in SCOPE + CONTENT}
    return key, content


def _bindings(bindings):
    if not isinstance(bindings, list):
        raise ValueError('bindings must be a synthetic list')
    found = {}
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != set(SCOPE + ('operation', 'payment_key', 'order_id')):
            raise ValueError('invalid binding fields')
        if not all(_text(value) for value in binding.values()):
            raise ValueError('invalid binding value')
        key = tuple(binding[name] for name in SCOPE + ('operation',))
        if key in found and found[key] != binding:
            raise ValueError('inconsistent explicit bindings')
        found[key] = binding
    return found


class LocalFakeObservation:
    """Structural ObservationPort stand-in. Each call folds only supplied facts."""

    def fold(self, facts, *, bindings):
        if not isinstance(facts, list):
            raise ValueError('facts must be a list')
        bound = _bindings(bindings)
        items, deliveries, duplicates, conflicts = {}, [], [], []
        for fact in facts:
            key, content = normalize(fact)
            event_id = 'sim-event-' + digest({'profile': PROFILE, 'key': key})
            evidence = digest(content)
            delivery = safe(event_item_id=event_id, transmission=copy.deepcopy(fact['transmission']))
            deliveries.append(delivery)
            if event_id in items:
                original = items[event_id]
                if original['scoped_key'] != key:
                    raise ValueError('synthetic alias collision')
                if original['normalized_fact'] == content:
                    duplicates.append(safe(event_item_id=event_id, delivery_index=len(deliveries) - 1))
                else:
                    original['status'] = 'CONFLICT'
                    conflicts.append(safe(event_item_id=event_id, original=copy.deepcopy(original['normalized_fact']),
                                          incoming=content, evidence_digest=evidence,
                                          delivery_index=len(deliveries) - 1))
                continue
            binding = bound.get(tuple(fact[name] for name in SCOPE + ('operation',)))
            status = 'UNMATCHED' if binding is None else 'MATCHED_FIXTURE'
            if binding and any(binding[name] != fact[name] for name in ('payment_key', 'order_id')):
                status = 'BINDING_CONFLICT'
            items[event_id] = safe(event_item_id=event_id, scoped_key=key, normalized_fact=content,
                                   evidence_digest=evidence, status=status, binding_status=status)
        return safe(identity_profile=PROFILE, binding_status='NOT_BOUND', semantic_conformance=False,
                    event_items=list(items.values()), deliveries=deliveries,
                    duplicates=duplicates, conflicts=conflicts, applied_effects=[])
