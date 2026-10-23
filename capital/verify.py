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
    FORMAT, FORMAT_V3, OVERLAY_SECTION, SECTION_IDS, ExportError, content_digest, load_dev_key,
    section_ids_for, sha256_hex,
)

_HEX = frozenset('0123456789abcdef')


from capital.strict_json import loads
from capital.keyset import DEV_KEYSET_ALG, load_dev_keyset, validate_dev_keyset, keyset_mac


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
        'format': FORMAT_V3 if OVERLAY_SECTION in sections else FORMAT,
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


def verify_manifest(document, key=None, key_error=None, *, keyset=None, keyset_error=None):
    """Check section hashes, then the content digest, then the signature.

    The first failing part supplies the reason. Later parts stay NOT_CHECKED
    so a body change is not reported as a digest or signature failure.
    """
    pending = {name: 'NOT_CHECKED' for name in SECTION_IDS}
    ids = section_ids_for(document.get('format')) if type(document) is dict else None
    if ids is None:
        return _fail('MANIFEST_SHAPE', pending)
    pending = {name: 'NOT_CHECKED' for name in ids}
    sections = document.get('sections')
    if type(sections) is not dict:
        return _fail('MANIFEST_SHAPE', pending)
    if set(sections) != set(ids):
        # V3 without overlay, or V2 with overlay: the format and section set disagree.
        reason = 'SECTION_SET' if set(sections) ^ set(ids) == {OVERLAY_SECTION} else 'MANIFEST_SHAPE'
        return _fail(reason, pending)
    for name in ids:
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
    return _check_signature(document, key, key_error, pending, keyset, keyset_error)


def _check_signature(document, key, key_error, sections, keyset, keyset_error):
    signature = document.get('signature')
    if type(signature) is not dict or signature.get('port') != 'SignaturePort':
        return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
    if signature.get('authentication') != 'NOT_BOUND' or 'key' in signature:
        return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
    algorithm = signature.get('alg')
    if algorithm == 'UNSIGNED':
        if signature.get('status') != 'NOT_BOUND' or signature.get('value') is not None:
            return _fail('SIGNATURE_SHAPE', sections, 'MATCHED', 'SIGNATURE_SHAPE')
        error = key_error or keyset_error
        if error is not None:
            return _fail(error, sections, 'MATCHED', error)
        return _report(
            ok=True, reason=None, sections=sections,
            digest_status='MATCHED', signature_status='NOT_BOUND',
        )
    if algorithm == DEV_KEYSET_ALG:
        def fail(reason):
            return _fail(reason, sections, 'MATCHED', reason)
        if set(signature) != {'port', 'alg', 'kid', 'status', 'label', 'purpose', 'authentication', 'value'} or type(signature.get('kid')) is not str:
            return fail('SIGNATURE_SHAPE')
        if signature['label'] != 'DEV_ONLY' or signature['status'] != 'DEV_ONLY' or signature['purpose'] != 'INTEGRITY_ONLY':
            return fail('SIGNATURE_LABEL')
        if keyset_error is not None:
            return fail(keyset_error)
        if keyset is None:
            return fail('SIGNATURE_KEYSET_REQUIRED')
        try:
            validate_dev_keyset(keyset)
        except ExportError as exc:
            return fail(exc.code)
        entry = next((entry for entry in keyset['keys'] if entry['kid'] == signature['kid']), None)
        if entry is None:
            return fail('UNKNOWN_KID')
        if entry['status'] == 'RETIRED':
            return fail('KEY_RETIRED')
        if not _hex_equal(signature['value'], keyset_mac(entry, document['content_digest'])):
            return fail('SIGNATURE_MISMATCH')
        return _report(ok=True, reason=None, sections=sections, digest_status='MATCHED',
                       signature_status='VERIFIED_DEV_ONLY_INTEGRITY')
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


def verify_path(path, key_file=None, *, keyset_file=None):
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
    keyset, keyset_error = None, None
    if keyset_file is not None:
        try:
            keyset = load_dev_keyset(keyset_file)
        except ExportError as exc:
            keyset_error = exc.code
    if key_file is not None and keyset_file is not None:
        keyset_error = key_error = 'SIGNATURE_KEYSET_CONFLICT'
    return verify_manifest(document, key, key_error, keyset=keyset, keyset_error=keyset_error)


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Recheck a Capital export manifest offline, or audit an opt-in '
        'LOCAL_FILE_WORKSPACE directory without a server. '
        'A DEV_ONLY HMAC key is integrity only, not authentication, and is not printed. '
        'This is not stage7 authenticated export.'
    ))
    parser.add_argument('file', nargs='?', help='Manifest JSON written by GET /api/export/manifest')
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument('--key-file', default=None, help='DEV_ONLY HMAC key. Required for a signed manifest. Not a credential.')
    keys.add_argument('--keyset-file', default=None, help='Pinned DEV_ONLY local keyset. Integrity only.')
    parser.add_argument('--workspace', default=None,
                        help='Audit DIR/workspace.json read-only. No lock, no write, no repair. Not stage5 durability evidence.')
    args = parser.parse_args(argv)
    if args.workspace is not None:
        if args.file is not None:
            parser.error('file and --workspace are mutually exclusive')
        if args.key_file is not None or args.keyset_file is not None:
            parser.error('--key-file/--keyset-file does not apply to --workspace')
        from capital.audit import audit_workspace
        report = audit_workspace(args.workspace)
    else:
        if args.file is None:
            parser.error('file or --workspace is required')
        report = verify_path(args.file, args.key_file, keyset_file=args.keyset_file)
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
