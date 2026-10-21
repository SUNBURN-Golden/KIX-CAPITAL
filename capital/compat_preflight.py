"""Offline, SIMULATED compatibility byte rehearsal; semantic HOLD, NOT_BOUND.

Encoding and manifest shape follow Protocol research 9b462fd (see
docs/COMPAT_PREFLIGHT.md). This module neither executes bundle code nor
qualifies a producer. Expectations must come from a separate caller input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

SCHEMA = 'kix-compat-manifest/1'
EXPECTED_FORMAT = 'capital-compat-expected/1'
SAFE_MAX = 9007199254740991
MANIFEST_FIELDS = {
    'manifest_schema_version', 'producer', 'profile_kind', 'profile_revision',
    'profile_sha256', 'contract', 'generator', 'sdk_output', 'vectors', 'source_references',
}
PROFILE_FIELDS = {
    'manifest_schema_version', 'profile_kind', 'profile_revision', 'catalogue',
    'vectors', 'grants', 'non_claims',
}
MANIFEST_FORBIDDEN = {'manifest_digest', 'manifest_sha256', 'final_commit', 'delivery_head', 'consumer_head'}
PROFILE_FORBIDDEN = MANIFEST_FORBIDDEN | {'profile_sha256', 'commit', 'source_commit', 'source_tree'}


class CompatibilityError(ValueError):
    def __init__(self, code, location='json'):
        self.code, self.location = code, location
        super().__init__(f'{code}: {location}')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CompatibilityError('duplicate-key')
        result[key] = value
    return result


def canonical_bytes(value):
    """kix-canonical-json/1, separate from Capital's legacy ASCII encoder."""
    def string(text):
        # JSON.stringify preserves non-ASCII, but escapes lone UTF-16 surrogates.
        encoded = json.dumps(text, ensure_ascii=False, separators=(',', ':'))
        return ''.join(f'\\u{ord(c):04x}' if 0xd800 <= ord(c) <= 0xdfff else c for c in encoded)

    def encode(item, depth):
        if item is None:
            return 'null'
        if type(item) is bool:
            return 'true' if item else 'false'
        if type(item) is str:
            return string(item)
        if type(item) is int:
            if abs(item) > SAFE_MAX:
                raise CompatibilityError('integer-range')
            return str(item)
        if type(item) not in (dict, list):
            raise CompatibilityError('non-integer' if type(item) is float else 'unsupported-value')
        if depth >= 32:
            raise CompatibilityError('depth')
        if type(item) is list:
            return '[' + ','.join(encode(v, depth + 1) for v in item) + ']'
        if any(type(k) is not str for k in item):
            raise CompatibilityError('unsupported-key')
        return '{' + ','.join(string(k) + ':' + encode(item[k], depth + 1) for k in sorted(item)) + '}'
    return encode(value, 0).encode('utf-8')


def decode_input(raw, *, canonical=True):
    """Reject duplicates even in pretty contract files; canonical inputs are exact."""
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise CompatibilityError('invalid-utf8') from exc

    def integer(token):
        if token == '-0':
            raise CompatibilityError('non-integer')
        value = int(token)
        if abs(value) > SAFE_MAX:
            raise CompatibilityError('integer-range')
        return value

    def refuse(_token):
        raise CompatibilityError('non-integer')

    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_int=integer if canonical else int,
                           parse_float=refuse if canonical else float, parse_constant=refuse)
        if canonical and canonical_bytes(value) != raw:
            raise CompatibilityError('non-canonical')
        return value
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, CompatibilityError):
            raise
        raise CompatibilityError('invalid-json') from exc


def read_bundle_file(root, relative):
    """All declared and derived paths must name regular files inside root."""
    if type(relative) is not str or not relative or '\\' in relative or '\0' in relative:
        raise CompatibilityError('unsafe-path', str(relative))
    path = PurePosixPath(relative)
    if path.is_absolute() or any(p in ('', '.', '..') for p in relative.split('/')):
        raise CompatibilityError('unsafe-path', relative)
    try:
        root = Path(root).resolve(strict=True)
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root):
            raise CompatibilityError('unsafe-path', relative)
        if not stat.S_ISREG(target.stat().st_mode):
            raise CompatibilityError('nonregular-file', relative)
        return target.read_bytes()
    except (OSError, RuntimeError) as exc:
        raise CompatibilityError('unreadable-file', relative) from exc


def _require(condition, code, location):
    if not condition:
        raise CompatibilityError(code, location)


def _keys(value, keys, location, forbidden=()):
    _require(type(value) is dict, 'object-required', location)
    for key in sorted(set(value) & set(forbidden)):
        raise CompatibilityError('forbidden-field', location + '.' + key)
    _require(set(value) == set(keys), 'field-set', location)


def _text(value, location):
    _require(type(value) is str and bool(value), 'string-required', location)


def _hex(value, size, location):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None,
             'invalid-digest', location)


def _compare(actual, expected, location, errors):
    if type(actual) is not type(expected):
        errors.append({'code': 'tuple-mismatch', 'location': location})
    elif type(actual) is dict:
        for key in sorted(set(actual) | set(expected)):
            if key not in actual or key not in expected:
                errors.append({'code': 'tuple-mismatch', 'location': location + '.' + key})
            else:
                _compare(actual[key], expected[key], location + '.' + key, errors)
    elif type(actual) is list:
        if len(actual) != len(expected):
            errors.append({'code': 'tuple-mismatch', 'location': location})
        for index, (left, right) in enumerate(zip(actual, expected)):
            _compare(left, right, f'{location}[{index}]', errors)
    elif actual != expected:
        errors.append({'code': 'tuple-mismatch', 'location': location})


@dataclass(frozen=True)
class PreflightReport:
    errors: tuple
    profile_kind: str | None = None
    manifest_sha256: str | None = None

    @property
    def matched(self):
        return not self.errors

    def as_dict(self):
        return {
            'byte_agreement': 'MATCHED' if self.matched else 'MISMATCH',
            'semantic_consumption': 'HOLD', 'adoption': 'NOT_BOUND',
            'semantic_conformance': False, 'label': 'SIMULATED',
            'profile_kind': self.profile_kind, 'manifest_sha256': self.manifest_sha256,
            'errors': list(self.errors),
        }


def _validate_bundle(root, manifest_path, manifest, raw):
    m = manifest
    _keys(m, MANIFEST_FIELDS, 'manifest', MANIFEST_FORBIDDEN)
    _require(m['manifest_schema_version'] == SCHEMA, 'schema-version', 'manifest.manifest_schema_version')
    _require(m['profile_kind'] in ('BOOTSTRAP', 'SEMANTIC_CONFORMANCE'), 'profile-kind', 'manifest.profile_kind')
    revision = m['profile_revision']
    _require(type(revision) is str and re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}', revision) is not None,
             'profile-revision', 'manifest.profile_revision')
    _keys(m['producer'], {'repository', 'source_commit', 'source_tree', 'protocol_domain', 'contract_schema_version'}, 'manifest.producer')
    for key, value in m['producer'].items():
        _text(value, 'manifest.producer.' + key)
    for key in ('source_commit', 'source_tree'):
        _hex(m['producer'][key], 40, 'manifest.producer.' + key)

    def hashed(relative, digest, location):
        _hex(digest, 64, location + '.sha256')
        data = read_bundle_file(root, relative)
        _require(sha256(data) == digest, 'sha256-mismatch', location)
        return data

    def reference(ref, location, extra=()):
        _keys(ref, {'path', 'sha256'} | set(extra), location)
        data = hashed(ref['path'], ref['sha256'], location)
        if 'gitBlob' in extra:
            _hex(ref['gitBlob'], 40, location + '.gitBlob')
            _require(git_blob(data) == ref['gitBlob'], 'git-blob-mismatch', location)
        return data

    _keys(m['contract'], {'contract_only', 'integration_gate'}, 'manifest.contract')
    loaded = {key: reference(ref, 'manifest.contract.' + key, {'gitBlob'})
              for key, ref in m['contract'].items()}
    reference(m['generator'], 'manifest.generator', {'toolchain'})
    toolchains = decode_input(read_bundle_file(root, 'toolchains.json'), canonical=False)
    _require(type(toolchains) is dict and type(toolchains.get('nodeMajor')) is int
             and toolchains['nodeMajor'] == 24 and m['generator']['toolchain'] == 'node-24',
             'toolchain-mismatch', 'manifest.generator.toolchain')
    reference(m['sdk_output'], 'manifest.sdk_output')
    _keys(m['source_references'], {'fixture_profile', 'extension_profile'}, 'manifest.source_references')
    read_bundle_file(root, m['source_references']['fixture_profile'])
    extension = m['source_references']['extension_profile']
    if extension is not False:
        reference(extension, 'manifest.source_references.extension_profile', {'gitBlob'})
    _require(type(m['vectors']) is list and bool(m['vectors']), 'vectors-required', 'manifest.vectors')
    names, paths = set(), set()
    for index, vector in enumerate(m['vectors']):
        location = f'manifest.vectors[{index}]'
        _keys(vector, {'name', 'path', 'sha256'}, location)
        _text(vector['name'], location + '.name')
        _text(vector['path'], location + '.path')
        _require(vector['name'] not in names and vector['path'] not in paths, 'duplicate-vector', location)
        names.add(vector['name'])
        paths.add(vector['path'])
        data = reference(vector, location, {'name'})
        decode_input(data)
    profile_raw = hashed(f'sdk/compat/profiles/{revision}.profile.json', m['profile_sha256'], 'profile')
    p = decode_input(profile_raw)
    _keys(p, PROFILE_FIELDS, 'profile', PROFILE_FORBIDDEN)
    for field in ('manifest_schema_version', 'profile_kind', 'profile_revision', 'vectors'):
        _require(canonical_bytes(p[field]) == canonical_bytes(m[field]), 'profile-binding', 'profile.' + field)
    if p['profile_kind'] == 'BOOTSTRAP':
        _require(p['grants'] == 'catalogue-schema-binding only', 'bootstrap-grants', 'profile.grants')
    _require(type(p['non_claims']) is list and bool(p['non_claims'])
             and all(type(v) is str for v in p['non_claims']), 'non-claims', 'profile.non_claims')
    catalogue = p['catalogue']
    _keys(catalogue, {'command_set_sha256', 'openapi_path', 'openapi_sha256', 'schema_digests'}, 'profile.catalogue')
    ref = m['contract']['contract_only']
    _require(catalogue['openapi_path'] == ref['path'] and catalogue['openapi_sha256'] == ref['sha256'],
             'catalogue-binding', 'profile.catalogue')
    # Resolve the profile's path too, independently of the manifest binding.
    read_bundle_file(root, catalogue['openapi_path'])
    api = decode_input(loaded['contract_only'], canonical=False)
    _require(type(api) is dict and api.get('x-kix-live-http-server') is False
             and api.get('x-kix-production-endpoint') is False and 'servers' not in api,
             'contract-live-flag', 'contract_only')
    _require(type(api.get('x-kix-source')) is dict and api['x-kix-source'].get('domain') == m['producer']['protocol_domain'],
             'contract-identity', 'contract_only.domain')
    _require(type(api.get('info')) is dict and api['info'].get('version') == m['producer']['contract_schema_version'],
             'contract-identity', 'contract_only.version')
    _require(type(api.get('components')) is dict and type(api['components'].get('schemas')) is dict,
             'contract-schemas', 'contract_only')
    schemas = api['components']['schemas']
    names = sorted(set(schemas) - {'LocalCallEnvelope'})
    _require(catalogue['command_set_sha256'] == sha256(canonical_bytes(names)), 'command-set-digest', 'profile.catalogue')
    _require(type(catalogue['schema_digests']) is dict and set(catalogue['schema_digests']) == set(names),
             'schema-digest-map', 'profile.catalogue')
    for name in names:
        _require(catalogue['schema_digests'][name] == sha256(canonical_bytes(schemas[name])),
                 'schema-digest', 'profile.catalogue.schema_digests.' + name)
    sidecar = read_bundle_file(root, manifest_path + '.sha256')
    _require(sidecar == (sha256(raw) + '\n').encode('ascii'), 'sidecar-mismatch', 'manifest.sidecar')
    _require(sha256(raw).encode('ascii') not in raw, 'self-digest', 'manifest')


def check_bundle(root, manifest_path, expected_path):
    """Check local bytes against an explicit complete external expectation.

    No Git ancestry, provenance, semantic qualification or adoption is inferred.
    The expected file is caller-controlled and may be outside the bundle root.
    """
    errors = []
    kind = digest = None
    try:
        expected = decode_input(Path(expected_path).read_bytes())
        _keys(expected, {'format', 'manifest_sha256', 'tuple'}, 'expected')
        _require(expected['format'] == EXPECTED_FORMAT, 'expected-format', 'expected.format')
        _hex(expected['manifest_sha256'], 64, 'expected.manifest_sha256')
        _keys(expected['tuple'], MANIFEST_FIELDS, 'expected.tuple', MANIFEST_FORBIDDEN)
        raw = read_bundle_file(root, manifest_path)
        manifest = decode_input(raw)
        digest = sha256(raw)
        if type(manifest) is dict and type(manifest.get('profile_kind')) is str:
            kind = manifest['profile_kind']
        _compare(manifest, expected['tuple'], 'tuple', errors)
        if digest != expected['manifest_sha256']:
            errors.append({'code': 'manifest-digest-mismatch', 'location': 'expected.manifest_sha256'})
        _validate_bundle(root, manifest_path, manifest, raw)
    except CompatibilityError as exc:
        errors.append({'code': exc.code, 'location': exc.location})
    except (OSError, ValueError, TypeError) as exc:
        errors.append({'code': 'unreadable-input' if isinstance(exc, OSError) else 'invalid-input', 'location': 'expected-or-bundle'})
    return PreflightReport(tuple(errors), kind, digest)
