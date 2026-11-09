"""Bounded, in-memory SIMULATED explanations of the ObservationPort fold."""
import copy

from capital.observation import CONTENT, PROFILE, SCOPE, LocalFakeObservation, canonical, digest, normalize, safe
from capital.strict_json import loads

INPUT_FORMAT = 'KIX_CAPITAL_OBSERVATION_TRIAGE_INPUT_V1'
FORMAT = 'KIX_CAPITAL_OBSERVATION_TRIAGE_V1'
MAX_BYTES = 262144
MAX_FACTS = MAX_BINDINGS = 256
MAX_STRING = 4096
MAX_DEPTH = 8


class InputError(ValueError):
    code = 'INVALID_INPUT'


class ContractError(RuntimeError):
    code = 'ADAPTER_CONTRACT_ERROR'


def _tree(value, depth=1):
    if depth > MAX_DEPTH:
        raise InputError('nesting limit exceeded')
    if type(value) is str:
        if len(value) > MAX_STRING or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise InputError('invalid or oversized string')
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise InputError('object keys must be strings')
            _tree(key, depth)
            _tree(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _tree(item, depth + 1)
    elif value is not None and type(value) not in (int, bool):
        raise InputError('only JSON integers, strings, booleans and null are supported')


def validate(document):
    """Validate the exact envelope and return detached synthetic input lists."""
    try:
        _tree(document)
        if type(document) is not dict or set(document) != {'format', 'label', 'facts', 'bindings'}:
            raise InputError('exact input envelope required')
        if document['format'] != INPUT_FORMAT or document['label'] != 'SIMULATED':
            raise InputError('SIMULATED input format required')
        facts, bindings = document['facts'], document['bindings']
        if type(facts) is not list or len(facts) > MAX_FACTS:
            raise InputError('facts must be a list of at most 256 entries')
        if type(bindings) is not list or len(bindings) > MAX_BINDINGS:
            raise InputError('bindings must be a list of at most 256 entries')
        for fact in facts:
            normalize(fact)
        found = {}
        for binding in bindings:
            if type(binding) is not dict or set(binding) != set(SCOPE + ('operation', 'payment_key', 'order_id')):
                raise InputError('invalid binding fields')
            if not all(type(v) is str and v.strip() for v in binding.values()):
                raise InputError('binding values must be non-empty text')
            key = tuple(binding[n] for n in SCOPE + ('operation',))
            if key in found and found[key] != binding:
                raise InputError('inconsistent explicit bindings')
            found[key] = binding
        if len(canonical(document).encode('utf-8')) > MAX_BYTES:
            raise InputError('input byte limit exceeded')
        return copy.deepcopy((facts, bindings))
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError('invalid synthetic input') from exc


def parse_input(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise InputError('input byte limit exceeded')
    try:
        document = loads(raw)
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise InputError('invalid strict UTF-8 JSON') from exc
    facts, bindings = validate(document)
    return {'format': INPUT_FORMAT, 'label': 'SIMULATED', 'facts': facts, 'bindings': bindings}


def serialize(report):
    return (canonical(report) + '\n').encode('utf-8')


def _binding(content, bound):
    lookup = {name: content[name] for name in SCOPE + ('operation',)}
    supplied = bound.get(tuple(lookup.values()))
    differences = [] if supplied is None else [
        {'field': name, 'binding_value': supplied[name], 'observed_value': content[name]}
        for name in ('payment_key', 'order_id') if supplied[name] != content[name]]
    status = 'UNMATCHED' if supplied is None else ('BINDING_CONFLICT' if differences else 'MATCHED_FIXTURE')
    explanation = {
        'UNMATCHED': 'No explicit binding exists for this scoped operation.',
        'BINDING_CONFLICT': 'The explicit binding disagrees with the observed payment or order.',
        'MATCHED_FIXTURE': 'The synthetic payment and order match the explicit binding; no financial fact is recorded.',
    }[status]
    return dict(status=status, reason_code=status, explanation=explanation,
                lookup=lookup, supplied_binding=supplied, differences=differences)


REASONS = {
    'FIRST_OBSERVATION': 'First supplied content for comparison only; it is not an authoritative winner.',
    'IDENTICAL_REDELIVERY': 'Content and transmission metadata equal a previous delivery of this variant.',
    'TRANSMISSION_METADATA_CHANGED': 'Content equals a previous variant; transmission metadata differ.',
    'CONTENT_CONFLICT': 'Normalized content differs from the first supplied content; every variant is retained.',
}


def triage(facts, *, bindings, observation_port=None):
    """Call fold once on detached inputs; return diagnostics without recording effects.

    Adapter output is checked against the pinned local identity/fold contract,
    including safety labels, order, digests, persistent conflicts and bindings.
    """
    facts, bindings = validate(dict(format=INPUT_FORMAT, label='SIMULATED', facts=facts, bindings=bindings))
    bound = {tuple(b[n] for n in SCOPE + ('operation',)): b for b in bindings}
    port = LocalFakeObservation() if observation_port is None else observation_port
    try:
        folded = copy.deepcopy(port.fold(copy.deepcopy(facts), bindings=copy.deepcopy(bindings)))
    except Exception as exc:
        raise ContractError('observation adapter failed') from exc

    # Build the expected contract while assembling explanations. Equality checks
    # fail closed even for bool/int substitutions in adapter-provided indices.
    expected = safe(identity_profile=PROFILE, binding_status='NOT_BOUND', semantic_conformance=False,
                    event_items=[], deliveries=[], duplicates=[], conflicts=[], applied_effects=[])
    groups, deliveries, items = {}, [], {}
    for index, fact in enumerate(facts):
        key, content = normalize(fact)
        event_id = 'sim-event-' + digest({'profile': PROFILE, 'key': key})
        evidence = digest(content)
        binding = _binding(content, bound)
        expected['deliveries'].append(safe(event_item_id=event_id, transmission=fact['transmission']))
        if event_id not in groups:
            item = safe(event_item_id=event_id, scoped_key=key, normalized_fact=content,
                        evidence_digest=evidence, status=binding['status'], binding_status=binding['status'])
            items[event_id] = item
            expected['event_items'].append(item)
            groups[event_id] = dict(event_item_id=event_id, scoped_key=key, status=item['status'],
                                    binding_status=item['binding_status'], reference_delivery_index=index,
                                    reference_role='COMPARISON_ONLY', delivery_indices=[], variants=[],
                                    conflicts=[], reasons=[])
            classification, reason = 'FIRST', 'FIRST_OBSERVATION'
        else:
            item = items[event_id]
            if item['scoped_key'] != key:
                raise ContractError('synthetic identity collision')
            if item['normalized_fact'] == content:
                classification = 'DUPLICATE'
                expected['duplicates'].append(safe(event_item_id=event_id, delivery_index=index))
            else:
                classification = 'CONFLICT'
                item['status'] = 'CONFLICT'
                expected['conflicts'].append(safe(event_item_id=event_id, original=item['normalized_fact'],
                                                incoming=content, evidence_digest=evidence, delivery_index=index))
        group = groups[event_id]
        variant_index = next((i for i, v in enumerate(group['variants']) if v['normalized_fact'] == content), None)
        redelivery_reason = None
        if variant_index is not None:
            prior = group['variants'][variant_index]['delivery_indices']
            redelivery_reason = ('IDENTICAL_REDELIVERY'
                if any(facts[i]['transmission'] == fact['transmission'] for i in prior)
                else 'TRANSMISSION_METADATA_CHANGED')
        if classification != 'FIRST':
            if classification == 'CONFLICT':
                reason = 'CONTENT_CONFLICT'
            else:
                reason = redelivery_reason
        if variant_index is None:
            variant_index = len(group['variants'])
            group['variants'].append(dict(normalized_fact=content, evidence_digest=evidence,
                                          delivery_indices=[], binding=binding))
        group['variants'][variant_index]['delivery_indices'].append(index)
        group['delivery_indices'].append(index)
        group['status'] = item['status']
        for code in (reason, redelivery_reason):
            if code is not None and code not in [r['code'] for r in group['reasons']]:
                group['reasons'].append(dict(code=code, explanation=REASONS[code]))
        if classification == 'CONFLICT':
            group['conflicts'].append(dict(delivery_index=index, reference_delivery_index=group['reference_delivery_index'],
                differences=[dict(field=n, reference_value=item['normalized_fact'][n], incoming_value=content[n])
                             for n in SCOPE + CONTENT if item['normalized_fact'][n] != content[n]]))
        deliveries.append(dict(delivery_index=index, event_item_id=event_id, transmission=fact['transmission'],
                               variant_index=variant_index, fold_classification=classification,
                               reason_code=reason, explanation=REASONS[reason],
                               redelivery_reason_code=redelivery_reason,
                               redelivery_explanation=REASONS.get(redelivery_reason)))
    try:
        if canonical(folded) != canonical(expected):
            raise ContractError('observation adapter output violates the local fold contract')
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise ContractError('invalid observation adapter output') from exc
    return copy.deepcopy(safe(format=FORMAT, identity_profile=folded['identity_profile'],
        binding_status=folded['binding_status'], semantic_conformance=False, applied_effects=[],
        groups=list(groups.values()), deliveries=deliveries))
