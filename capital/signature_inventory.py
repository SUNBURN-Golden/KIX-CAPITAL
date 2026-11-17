"""Bounded offline inventory of local manifests under one DEV_ONLY snapshot.

Shared HMAC integrity is not authentication. No inputs are written or repaired.
"""
import argparse
import json
import os
import stat
import sys

from capital.export import ExportError
from capital.keyset import load_dev_keyset
from capital.strict_json import loads
from capital.verify import verify_manifest

MAX_INPUTS = 100
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 128
_KID_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._')


def _open_regular(path):
    """Walk components through pinned directory descriptors; never follow links."""
    if (not all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_NONBLOCK', 'O_DIRECTORY'))
            or os.open not in os.supports_dir_fd):
        raise ExportError('INVENTORY_SECURE_OPEN_UNSUPPORTED')
    # Do not normalize away components (notably symlink/..) before checking them.
    parts = path.split('/')
    directory = os.open('/' if path.startswith('/') else '.',
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[:-1]:
            if not component:
                continue
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                            | os.O_NONBLOCK, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ExportError('INVENTORY_INPUT_NOT_REGULAR')
        except BaseException:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(directory)


def _read_manifest(path, remaining):
    fd = None
    raw = bytearray()
    try:
        fd = _open_regular(path)
        size = os.fstat(fd).st_size
        if size > MAX_MANIFEST_BYTES:
            return None, 'INVENTORY_MANIFEST_BYTES_LIMIT', 0
        if size > remaining:
            return None, 'INVENTORY_TOTAL_BYTES_LIMIT', 0
        # One extra byte detects growth after fstat, even at an exact boundary.
        limit = min(MAX_MANIFEST_BYTES, remaining)
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                return bytes(raw), None, len(raw)
            raw.extend(part)
        error = ('INVENTORY_TOTAL_BYTES_LIMIT' if remaining <= MAX_MANIFEST_BYTES
                 else 'INVENTORY_MANIFEST_BYTES_LIMIT')
        return None, error, len(raw)
    except ExportError as exc:
        return None, exc.code, len(raw)
    except (OSError, ValueError):
        return None, 'INVENTORY_INPUT_UNREADABLE', len(raw)
    finally:
        if fd is not None:
            os.close(fd)


def _metadata(document):
    digest, kid = None, None
    if type(document) is dict:
        candidate = document.get('content_digest')
        if (type(candidate) is str and len(candidate) == 64
                and all(c in '0123456789abcdef' for c in candidate)):
            digest = candidate
        signature = document.get('signature')
        candidate = signature.get('kid') if type(signature) is dict else None
        if (type(candidate) is str and 1 <= len(candidate) <= 128
                and all(c in _KID_CHARS for c in candidate)):
            kid = candidate
    return digest, kid


def _check_depth(document):
    # Python JSON implementations differ in whether decoding limits nesting.
    # Bound verifier recursion using an iterator stack with bounded extra space.
    stack = [iter((document,))]
    while stack:
        try:
            value = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if type(value) in (dict, list):
            if len(stack) > MAX_JSON_DEPTH:
                raise ValueError('INVENTORY_DOCUMENT_INVALID')
            stack.append(iter(value.values() if type(value) is dict else value))


def inventory_manifests(paths, *, keyset_file):
    """Audit 1–100 explicit paths, in order, loading the keyset exactly once.

    Invalid argument counts raise ValueError. File/JSON failures become closed
    input_error codes; verification embeds the unmodified verifier report.
    verified counts completed verifier calls, including negative outcomes.
    failed counts all unsuccessful, non-skipped rows. complete means every row
    reached the verifier; all_valid additionally requires all outcomes to pass.
    """
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_INPUTS:
        raise ValueError('INVENTORY_INPUT_COUNT')
    paths = [os.fspath(path) for path in paths]
    if any(type(path) is not str for path in paths):
        raise ValueError('INVENTORY_PATH_TYPE')
    snapshot, keyset_error = None, None
    try:
        snapshot = load_dev_keyset(keyset_file, create=False)
    except ExportError as exc:
        keyset_error = exc.code
    files, total, exhausted = [], 0, False
    for index, path in enumerate(paths, 1):
        row = dict(index=index, path=path, content_digest=None, kid=None,
                   input_error=None, verification=None)
        files.append(row)
        if exhausted:
            row['input_error'] = 'INVENTORY_SKIPPED_TOTAL_BYTES_LIMIT'
            continue
        raw, error, consumed = _read_manifest(path, MAX_TOTAL_BYTES - total)
        total += consumed
        row['input_error'] = error
        if error:
            exhausted = error == 'INVENTORY_TOTAL_BYTES_LIMIT'
            continue
        try:
            document = loads(raw)
            _check_depth(document)
            row['content_digest'], row['kid'] = _metadata(document)
            row['verification'] = verify_manifest(document, keyset=snapshot,
                                                  keyset_error=keyset_error)
        except (ValueError, UnicodeError, RecursionError, OverflowError):
            row['input_error'] = 'INVENTORY_DOCUMENT_INVALID'
    verified = sum(row['verification'] is not None for row in files)
    skipped = sum(row['input_error'] == 'INVENTORY_SKIPPED_TOTAL_BYTES_LIMIT' for row in files)
    passed = sum(row['verification'] is not None and row['verification']['ok'] for row in files)
    all_valid = keyset_error is None and passed == len(paths)
    return {
        'format': 'KIX_CAPITAL_SIGNATURE_INVENTORY_V1', 'label': 'DEV_ONLY',
        'authentication': 'NOT_BOUND', 'stage7_authenticated_export': False,
        'funds_executed': False, 'keyset_error': keyset_error,
        'limits': {'max_inputs': MAX_INPUTS, 'max_manifest_bytes': MAX_MANIFEST_BYTES,
                   'max_total_bytes': MAX_TOTAL_BYTES, 'max_json_depth': MAX_JSON_DEPTH},
        'files': files,
        'summary': {'requested': len(paths), 'verified': verified,
                    'failed': len(paths) - passed - skipped, 'skipped': skipped,
                    'complete': verified == len(paths), 'all_valid': all_valid,
                    'all_dev_signatures_verified': all_valid and all(
                        row['verification']['signature'] == 'VERIFIED_DEV_ONLY_INTEGRITY'
                        for row in files)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Audit explicit saved manifests offline under one DEV_ONLY keyset snapshot. '
        'Local shared-HMAC integrity only; authentication remains NOT_BOUND.'))
    parser.add_argument('--keyset-file', required=True, help='Local snapshot, exact mode 0600')
    parser.add_argument('files', nargs='+', help='1–100 explicit manifest paths, in report order')
    args = parser.parse_args(argv)
    if len(args.files) > MAX_INPUTS:
        parser.error('INVENTORY_INPUT_COUNT: at most 100 manifests')
    report = inventory_manifests(args.files, keyset_file=args.keyset_file)
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
    return 0 if report['summary']['all_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
