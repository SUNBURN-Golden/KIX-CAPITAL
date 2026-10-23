"""Executable CLAIM_CONFORMANCE checks binding Capital canonical JSON and
digest framing to the pinned CANONICAL_ENCODING_V1 (CE1) byte rules.

Each row in tests/ce1_claims.json cites the pinned
docs/CANONICAL_ENCODING_V1.md (kix-protocol
7481b0e16ce9b903abbffa62249bb91cd9e63cfe, the vendor pin), names one check,
carries the row input, and stores the value that check must observe.

The gate is the binding's input validation, not a Capital encoder change:
`decode_input` applies the CE1 input rules a row cites (bounded UTF-8 bytes,
strict JSON without duplicate keys, nonstandard constants, non-integer
numbers, -0 or out-of-range integers, and the visible-ASCII key grammar)
before any canonical_bytes or digest call runs. A rejected input never
reaches hashing. The pinned Unicode-15.0 assigned-scalar repertoire is not
enforced: that range table is not a vendored input, so the gate checks NFC
and scalar validity only and no row claims repertoire enforcement.

`ce1_bytes` in divergence rows is a local reference rendering
(json.dumps with ensure_ascii=False over gate-clean input) used only to
record what CE1 emits for the same value. The known divergence — Capital
canonical bytes use ensure_ascii escaping — is pinned in
DOCUMENTED_DIVERGENCE rows that also re-verify the stage-7 alignment
rationale in docs/decisions/CAPITAL_UPSTREAM_BINDING.md. Rows never claim
CE1 byte-exact hash framing: Capital carries the domain tag as a canonical
object field, and the `KIX-CE1\\0<domain>\\0` wire form is stage-7 adapter
scope.

The comparison is local and SIMULATED. It is not a SEMANTIC_CONFORMANCE
profile, not a producer tuple, and it moves no funds. A protocol checkout
is optional: the drift script reads that tree and does not write it. With
no checkout the drift status is SKIPPED, which is not a pass.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from capital import upstream_claims
from capital.resources import ROOT
from capital.store import canonical_bytes
from capital.upstream_claims import ClaimTableError

PINNED_SHA = upstream_claims.PINNED_SHA
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_CE1_CLAIMS_V1'
REQUIRED_FIELDS = upstream_claims.REQUIRED_FIELDS
SOURCE_DOC = 'docs/CANONICAL_ENCODING_V1.md'
BINDING_NOTE = 'docs/decisions/CAPITAL_UPSTREAM_BINDING.md'
BINDING_SECTION = '### 3.4 stage7_authenticated_export'
DIVERGENCE_DISPOSITION = 'DOCUMENTED_DIVERGENCE'
DISPOSITIONS = ('CONFORMANCE', DIVERGENCE_DISPOSITION)
DIVERGENCE_CHECKS = ('ce1.divergence', 'ce1.divergent_digest')

MAX_SAFE_INTEGER = 2 ** 53 - 1
MAX_INPUT_BYTES = 262_144
MAX_DEPTH = 64
MAX_KEY_CHARS = 128
INPUT_FORMS = ('value', 'payload', 'payload_repeat', 'payload_nest')
_MACHINE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9:_./-]*\Z')


class InputRejected(ValueError):
    """The binding gate refused an input under the CE1 byte rules.

    `.code` names the rejected class (e.g. DUPLICATE_KEY). The check rows
    observe `REJECTED:<code>`; a rejected input is never hashed.
    """

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'ce1_claims.json'


def load_table(path=None):
    data = upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    validate_table(data)
    return data


def validate_table(data):
    upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    for claim in data['claims']:
        if claim['source_doc'] != SOURCE_DOC:
            raise ClaimTableError(f'claim {claim["id"]} source_doc is not the CE1 spec')
        spec = claim.get('input')
        if type(spec) is not dict or len(spec) != 1 or next(iter(spec)) not in INPUT_FORMS:
            raise ClaimTableError(f'claim {claim["id"]} input is not a known input form')
        disposition = claim.get('disposition', 'CONFORMANCE')
        if disposition not in DISPOSITIONS:
            raise ClaimTableError(f'claim {claim["id"]} has an unknown disposition')
        divergence = claim.get('divergence')
        if disposition == DIVERGENCE_DISPOSITION:
            if claim['check_id'] not in DIVERGENCE_CHECKS:
                raise ClaimTableError(
                    f'claim {claim["id"]} records a divergence with a non-divergence check')
            if type(divergence) is not dict:
                raise ClaimTableError(f'claim {claim["id"]} is missing divergence')
            if divergence.get('binding_note') != BINDING_NOTE:
                raise ClaimTableError(f'claim {claim["id"]} cites a wrong binding note')
            for field in ('binding_section', 'rationale_needle'):
                value = divergence.get(field)
                if type(value) is not str or not value.strip():
                    raise ClaimTableError(f'claim {claim["id"]} divergence is missing {field}')
        elif divergence is not None:
            raise ClaimTableError(f'claim {claim["id"]} carries divergence without the disposition')
    return data


def run_claims(table):
    """Run every check. An unmapped check fails that claim and no other."""
    validate_table(table)
    rows = []
    for claim in table['claims']:
        check_id = claim['check_id']
        expected = claim['expected']
        disposition = claim.get('disposition', 'CONFORMANCE')
        if check_id not in CHECKS:
            rows.append({
                'id': claim['id'],
                'check_id': check_id,
                'ok': False,
                'unmapped': True,
                'observed': None,
                'expected': expected,
                'disposition': disposition,
            })
            continue
        try:
            observed = CHECKS[check_id](claim)
        except InputRejected as exc:
            observed = {'error': 'InputRejected', 'code': exc.code}
        except Exception as exc:
            observed = {'error': type(exc).__name__, 'detail': str(exc)}
        rows.append({
            'id': claim['id'],
            'check_id': check_id,
            'ok': observed == expected,
            'unmapped': False,
            'observed': observed,
            'expected': expected,
            'disposition': disposition,
        })
    failed = [row for row in rows if not row['ok']]
    return {
        'label': LABEL,
        'passed': len(rows) - len(failed),
        'total': len(rows),
        'failed': failed,
        'rows': rows,
        'ok': not failed,
        'documented_divergences': [
            row['id'] for row in rows
            if row['disposition'] == DIVERGENCE_DISPOSITION and row['ok']
        ],
    }


def check_protocol(protocol_dir, table=None):
    """Read cited headings and needles. Never writes the checkout."""
    if table is None:
        table = load_table()
    else:
        validate_table(table)
    return upstream_claims.check_protocol(
        protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputRejected('DUPLICATE_KEY')
        result[key] = value
    return result


def _integer_token(token):
    if token == '-0':
        raise InputRejected('NEGATIVE_ZERO')
    if len(token.lstrip('-')) > 16:
        raise InputRejected('UNSAFE_INTEGER')
    value = int(token)
    if abs(value) > MAX_SAFE_INTEGER:
        raise InputRejected('UNSAFE_INTEGER')
    return value


def _reject_float(_token):
    raise InputRejected('NON_INTEGER_NUMBER')


def _reject_constant(_token):
    raise InputRejected('NONSTANDARD_CONSTANT')


def _check_key(key):
    if (type(key) is not str or not 1 <= len(key) <= MAX_KEY_CHARS
            or not all(0x21 <= ord(char) <= 0x7E for char in key)):
        raise InputRejected('INVALID_KEY')


def _check_string(value):
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise InputRejected('INVALID_SCALAR')
    if not unicodedata.is_normalized('NFC', value):
        raise InputRejected('NON_NFC_STRING')


def _check_value(value, depth):
    if depth > MAX_DEPTH:
        raise InputRejected('MAX_DEPTH')
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise InputRejected('UNSAFE_INTEGER')
        return
    if type(value) is str:
        _check_string(value)
        return
    if type(value) is list:
        for item in value:
            _check_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            _check_key(key)
            _check_value(item, depth + 1)
        return
    raise InputRejected('NON_INTEGER_NUMBER' if type(value) is float else 'UNSUPPORTED_VALUE')


def _decode_payload(raw):
    if type(raw) is not bytes:
        raise InputRejected('INPUT_MUST_BE_BYTES')
    if len(raw) > MAX_INPUT_BYTES:
        raise InputRejected('INPUT_TOO_LARGE')
    if raw.startswith(b'\xef\xbb\xbf') or b'\x00' in raw:
        raise InputRejected('REJECTED_ENCODING')
    try:
        value = json.loads(
            raw.decode('utf-8'), object_pairs_hook=_unique_object,
            parse_int=_integer_token, parse_float=_reject_float,
            parse_constant=_reject_constant)
    except InputRejected:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise InputRejected('INVALID_JSON') from exc
    _check_value(value, 0)
    return value


def _repeat_payload(spec):
    if type(spec) is not dict or set(spec) != {'char', 'count'}:
        raise InputRejected('INPUT_SHAPE')
    char, count = spec['char'], spec['count']
    if type(char) is not str or len(char) != 1 or type(count) is not int or count < 0:
        raise InputRejected('INPUT_SHAPE')
    return ('"' + char * count + '"').encode('utf-8')


def _nest_payload(depth):
    if type(depth) is not int or depth < 0:
        raise InputRejected('INPUT_SHAPE')
    return ('[' * depth + ']' * depth).encode('utf-8')


def decode_input(spec):
    """Resolve a row's `input` to a gate-checked value, before any hashing."""
    if type(spec) is not dict or len(spec) != 1:
        raise InputRejected('INPUT_SHAPE')
    if 'value' in spec:
        value = spec['value']
        _check_value(value, 0)
        return value
    if 'payload' in spec:
        payload = spec['payload']
        if type(payload) is not str:
            raise InputRejected('INPUT_SHAPE')
        try:
            raw = payload.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise InputRejected('INVALID_JSON') from exc
        return _decode_payload(raw)
    if 'payload_repeat' in spec:
        return _decode_payload(_repeat_payload(spec['payload_repeat']))
    return _decode_payload(_nest_payload(spec['payload_nest']))


def _ce1_encode(value):
    """Reference CE1 rendering for divergence records only.

    Compact sorted-keys JSON written as UTF-8 (ensure_ascii=False) over
    gate-clean input. The pinned Unicode-15.0 repertoire is not checked;
    no row uses it to claim repertoire enforcement.
    """
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _note_text():
    note_path = Path(str(ROOT)).resolve().parent / BINDING_NOTE
    return note_path.read_text(encoding='utf-8')


def _note_section(text, heading):
    index = text.find(heading)
    if index < 0:
        return None
    rest = text[index + len(heading):]
    boundary = re.search(r'\n#{2,3} ', rest)
    return rest[:boundary.start()] if boundary else rest


def _note_cited(divergence):
    if divergence.get('binding_note') != BINDING_NOTE:
        return False
    section = _note_section(_note_text(), divergence.get('binding_section', ''))
    return section is not None and divergence.get('rationale_needle', '') in section


def check_encode(claim):
    return canonical_bytes(decode_input(claim['input'])).decode('utf-8')


def check_reject(claim):
    try:
        decode_input(claim['input'])
    except InputRejected as exc:
        return 'REJECTED:' + exc.code
    raise ClaimTableError(f'claim {claim["id"]} input was not rejected')


def check_plain_digest(claim):
    return hashlib.sha256(canonical_bytes(decode_input(claim['input']))).hexdigest()


def check_framed_digest(claim):
    from capital import overlay
    return overlay.state_digest(decode_input(claim['input']))


def check_part_tag_digest(claim):
    from capital import evidence
    spec = claim['input'].get('value')
    if type(spec) is not dict or set(spec) != {'part', 'document'}:
        raise ClaimTableError(f'claim {claim["id"]} part-tag input needs part and document')
    part = spec['part']
    if type(part) is not str or part not in evidence.PACK_PART_TAGS:
        raise ClaimTableError(f'claim {claim["id"]} names no evidence part')
    _check_value(spec['document'], 0)
    return evidence._seal(part, spec['document'])['sha256']


def check_domain_tag(claim):
    from capital import overlay
    value = decode_input(claim['input'])
    domain = overlay.DOMAIN
    return (value == domain and type(domain) is str
            and _MACHINE_ID.fullmatch(domain) is not None)


def check_digest_family(claim):
    from capital.export import sha256_hex
    from capital.service import digest
    value = decode_input(claim['input'])
    return digest(value) == sha256_hex(value) == hashlib.sha256(canonical_bytes(value)).hexdigest()


def check_divergence(claim):
    value = decode_input(claim['input'])
    capital = canonical_bytes(value).decode('ascii')
    ce1 = _ce1_encode(value)
    return {
        'capital_bytes': capital,
        'ce1_bytes': ce1,
        'divergent': capital != ce1,
        'note_cited': _note_cited(claim['divergence']),
    }


def check_divergent_digest(claim):
    value = decode_input(claim['input'])
    capital = hashlib.sha256(canonical_bytes(value)).hexdigest()
    ce1 = hashlib.sha256(_ce1_encode(value).encode('utf-8')).hexdigest()
    return {
        'capital_sha256': capital,
        'ce1_bytes_sha256': ce1,
        'divergent': capital != ce1,
        'note_cited': _note_cited(claim['divergence']),
    }


CHECKS = {
    'ce1.encode': check_encode,
    'ce1.reject': check_reject,
    'ce1.plain_digest': check_plain_digest,
    'ce1.framed_digest': check_framed_digest,
    'ce1.part_tag_digest': check_part_tag_digest,
    'ce1.domain_tag': check_domain_tag,
    'ce1.digest_family': check_digest_family,
    'ce1.divergence': check_divergence,
    'ce1.divergent_digest': check_divergent_digest,
}
