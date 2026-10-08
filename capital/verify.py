"""Offline checker for a Capital export manifest.

Recomputes every section hash, the content digest, and the signature.
A shared HMAC key is integrity only, not authentication. This is not stage7
authenticated export. The key file is never printed.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path

from capital.export import (
    FORMAT, SECTION_IDS, ExportError, content_digest, load_dev_key, sha256_hex,
)

_HEX = frozenset('0123456789abcdef')


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def loads(raw):
    if raw.startswith(b'\xef\xbb\xbf') or b'\x00' in raw:
        raise ValueError('rejected encoding')
    text = raw.decode('utf-8')
    return json.loads(
        text, object_pairs_hook=_strict_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
    )


def _hex_equal(expected, actual):
    if type(expected) is not str or type(actual) is not str:
        return False
    if len(expected) != len(actual) or len(expected) != 64:
        return False
    if any(char not in _HEX for char in expected) or any(char not in _HEX for char in actual):
        return False
    return hmac.compare_digest(expected, actual)


def _report(*, ok, reason, sections, digest_status, signature_status):
    return {
        'ok': ok,
        'reason': reason,
        'format': FORMAT,
        'sections': sections,
        'content_digest': digest_status,
        'signature': signature_status,
        'authentication': 'NOT_BOUND',
        'stage7_authenticated_export': False,
    }


def _fail(reason, sections, digest_status='NOT_CHECKED', signature_status='NOT_CHECKED'):
    return _report(
        ok=False, reason=reason, sections=sections,
        digest_status=digest_status, signature_status=signature_status,
    )


def verify_manifest(document, key=None, key_error=None):
    """Check section hashes, then the content digest, then the signature.

    The first failing part supplies the reason. Later parts stay NOT_CHECKED
    so a body change is not reported as a digest or signature failure.
    """
    pending = {name: 'NOT_CHECKED' for name in SECTION_IDS}
    if type(document) is not dict or document.get('format') != FORMAT:
        return _fail('MANIFEST_SHAPE', pending)
    sections = document.get('sections')
    if type(sections) is not dict or set(sections) != set(SECTION_IDS):
        return _fail('MANIFEST_SHAPE', pending)
    for name in SECTION_IDS:
        section = sections.get(name)
        if type(section) is not dict or set(section) != {'sha256', 'body'}:
            pending[name] = 'SECTION_SHAPE'
            return _fail(f'SECTION_HASH_MISMATCH:{name}', pending)
        actual = sha256_hex(section['body'])
        if not _hex_equal(section.get('sha256'), actual):
            pending[name] = 'SECTION_HASH_MISMATCH'
            return _fail(f'SECTION_HASH_MISMATCH:{name}', pending)
        pending[name] = 'MATCHED'
    try:
        expected = content_digest(document)
    except ExportError:
        return _fail('CONTENT_DIGEST_MISMATCH', pending, 'CONTENT_DIGEST_MISMATCH')
    if not _hex_equal(document.get('content_digest'), expected):
        return _fail('CONTENT_DIGEST_MISMATCH', pending, 'CONTENT_DIGEST_MISMATCH')
    return _check_signature(document, key, key_error, pending)


def _check_signature(document, key, key_error, sections):
    signature = document.get('signature')
    if type(signature) is not dict or signature.get('port') != 'SignaturePort':
        return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
    if signature.get('authentication') != 'NOT_BOUND' or 'key' in signature:
        return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
    algorithm = signature.get('alg')
    if algorithm == 'UNSIGNED':
        if signature.get('status') != 'NOT_BOUND' or signature.get('value') is not None:
            return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
        if key_error is not None:
            return _fail(key_error, sections, 'MATCHED', key_error)
        return _report(
            ok=True, reason=None, sections=sections,
            digest_status='MATCHED', signature_status='NOT_BOUND',
        )
    if algorithm != 'DEV_HMAC_SHA256':
        return _fail('SIGNATURE_ALG', sections, 'MATCHED', 'SIGNATURE_ALG')
    if signature.get('label') != 'DEV_ONLY' or signature.get('purpose') != 'INTEGRITY_ONLY':
        return _fail('SIGNATURE_LABEL', sections, 'MATCHED', 'SIGNATURE_LABEL')
    if signature.get('status') != 'DEV_ONLY':
        return _fail('SIGNATURE_LABEL', sections, 'MATCHED', 'SIGNATURE_LABEL')
    if key_error is not None:
        return _fail(key_error, sections, 'MATCHED', key_error)
    if key is None:
        return _fail('SIGNATURE_KEY_REQUIRED', sections, 'MATCHED', 'SIGNATURE_KEY_REQUIRED')
    digest = document.get('content_digest')
    try:
        mac = hmac.new(key, digest.encode('ascii'), hashlib.sha256).hexdigest()
    except (AttributeError, UnicodeEncodeError):
        return _fail('SIGNATURE_MISMATCH', sections, 'MATCHED', 'SIGNATURE_MISMATCH')
    if not _hex_equal(signature.get('value'), mac):
        return _fail('SIGNATURE_MISMATCH', sections, 'MATCHED', 'SIGNATURE_MISMATCH')
    return _report(
        ok=True, reason=None, sections=sections,
        digest_status='MATCHED', signature_status='VERIFIED_DEV_ONLY_INTEGRITY',
    )


def verify_path(path, key_file=None):
    try:
        raw = Path(path).read_bytes()
        document = loads(raw)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        pending = {name: 'NOT_CHECKED' for name in SECTION_IDS}
        return _fail('MANIFEST_UNREADABLE', pending)
    key = None
    key_error = None
    if key_file is not None:
        try:
            key = load_dev_key(key_file, create=False)
        except ExportError as exc:
            key_error = exc.code
    return verify_manifest(document, key, key_error)


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Recheck a Capital export manifest offline. '
        'A DEV_ONLY HMAC key is integrity only, not authentication, and is not printed. '
        'This is not stage7 authenticated export.'
    ))
    parser.add_argument('file', help='Manifest JSON written by GET /api/export/manifest')
    parser.add_argument('--key-file', default=None, help='DEV_ONLY HMAC key. Required for a signed manifest. Not a credential.')
    args = parser.parse_args(argv)
    report = verify_path(args.file, args.key_file)
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
