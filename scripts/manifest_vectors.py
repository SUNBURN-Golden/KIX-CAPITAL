#!/usr/bin/env python3
"""Regenerate and byte-pin the tamper corpus for the offline manifest verifier.

The corpus lives in tests/vectors/ and is SIMULATED. It is built from the
seed_demo story replayed into a file workspace, with one fixed instance id, so
every run emits the same bytes:

- manifest/unsigned.json: clean UNSIGNED manifest (signature NOT_BOUND)
- manifest/dev-hmac.json: the same book signed with DEV_HMAC_SHA256
- manifest/section-<id>.json: one byte flipped inside that section's body
- manifest/content-digest.json: one hex char of content_digest flipped
- manifest/signature.json: one hex char of the HMAC value flipped
- manifest/malformed.json: the signed manifest cut off mid-document
- export-dev.key: fixed synthetic DEV_ONLY key for dev-hmac.json. It is test
  vector material, not a credential, and not used anywhere else. It is stored
  mode 0644 by git; capital.verify only reads a key file at mode 0600, so
  copy it and chmod 0600 before passing it to --key-file.

A shared HMAC key is integrity only, not authentication. This is not stage7
authenticated export, and no new signature scheme is added here.

--check regenerates in memory and exits 1 when any file differs, is missing, or
is unexpected under manifest/. --write rewrites the files and removes any other
manifest/*.json, which this script owns. --dir points both at another
directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.export import DEV_KEY_NAME, PART_TAGS, SECTION_IDS, DevHmacSigner
from capital.service import CapitalService

DEFAULT_DIR = ROOT / 'tests' / 'vectors'
MANIFEST_DIR = 'manifest'
KEY_FILE = 'export-dev.key'
INSTANCE_ID = 'manifest-vectors'
# 'DEV_ONLY\n' plus 32 fixed ASCII bytes, the shape capital.export reads.
KEY_BYTES = b'DEV_ONLY\n' + b'manifest-vectors-DEV_ONLY-key-00'


class VectorError(Exception):
    pass


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(manifest) -> bytes:
    return (json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def export_seeded(directory):
    """Replay the seed_demo story into a file workspace; export it unsigned, then DEV_HMAC signed.

    The instance id is fixed before the first command so receipts, and the
    section hashes that cover them, do not change between runs.
    """
    seed = _load_seed()
    workspace = Path(directory) / 'workspace'
    port = seed.open_fresh(workspace)
    service = None
    try:
        service = CapitalService(port)
        service.instance_id = INSTANCE_ID
        service.storage.writer_instance = INSTANCE_ID
        seed.apply_steps(service)
        unsigned = service.export_manifest()
        key_path = workspace / DEV_KEY_NAME
        key_path.write_bytes(KEY_BYTES)
        os.chmod(key_path, 0o600)
        service.signer = DevHmacSigner(workspace)
        signed = service.export_manifest()
    finally:
        if service is not None:
            seed._release(service.producer)
        port.close()
    return unsigned, signed


def _flip(raw, index, first, second):
    """Swap the byte at `index` for `first`, or for `second` when it already is `first`."""
    current = raw[index:index + 1]
    replacement = first if current != first else second
    flipped = raw[:index] + replacement + raw[index + 1:]
    if len(flipped) != len(raw) or flipped == raw:
        raise VectorError('flip did not change exactly one byte')
    json.loads(flipped)
    return flipped


def _unique_index(raw, marker, start=0):
    if raw.count(marker) != 1:
        raise VectorError(f'marker is not unique: {marker!r}')
    return raw.index(marker, start)


def flip_section(raw, name):
    token = f'"part_tag":"{PART_TAGS[name]}"'.encode()
    # The last letter of the tag, just before the closing quote.
    return _flip(raw, _unique_index(raw, token) + len(token) - 2, b'u', b'v')


def flip_content_digest(raw):
    marker = b'"content_digest":"'
    return _flip(raw, _unique_index(raw, marker) + len(marker), b'0', b'1')


def flip_signature(raw):
    alg = _unique_index(raw, b'"alg":"DEV_HMAC_SHA256"')
    marker = b'"value":"'
    return _flip(raw, raw.index(marker, alg) + len(marker), b'a', b'b')


def truncate(raw):
    cut = raw[:len(raw) // 2]
    try:
        json.loads(cut)
    except ValueError:
        return cut
    raise VectorError('truncated manifest still parses')


def build_vectors() -> dict:
    """Relative path under the vectors directory -> bytes. Pure: nothing is written."""
    with tempfile.TemporaryDirectory() as tmp:
        unsigned, signed = export_seeded(tmp)
    raw = dump(signed)
    files = {'unsigned.json': dump(unsigned), 'dev-hmac.json': raw}
    for name in SECTION_IDS:
        files[f'section-{name}.json'] = flip_section(raw, name)
    files['content-digest.json'] = flip_content_digest(raw)
    files['signature.json'] = flip_signature(raw)
    files['malformed.json'] = truncate(raw)
    vectors = {f'{MANIFEST_DIR}/{name}': data for name, data in files.items()}
    vectors[KEY_FILE] = KEY_BYTES
    return vectors


def find_drift(root, vectors):
    problems = []
    for relative, data in sorted(vectors.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f'missing {relative}')
        elif path.read_bytes() != data:
            problems.append(f'differs {relative}')
    manifests = root / MANIFEST_DIR
    if manifests.is_dir():
        for path in sorted(manifests.iterdir()):
            if f'{MANIFEST_DIR}/{path.name}' not in vectors:
                problems.append(f'unexpected {MANIFEST_DIR}/{path.name}')
    return problems


def write_vectors(root, vectors):
    for relative, data in sorted(vectors.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifests = root / MANIFEST_DIR
    for path in sorted(manifests.glob('*.json')):
        if f'{MANIFEST_DIR}/{path.name}' not in vectors:
            path.unlink()
            print(f'removed stale {MANIFEST_DIR}/{path.name}')
    try:
        os.chmod(root / KEY_FILE, 0o600)
    except OSError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Byte-compare the corpus. Exit 1 on drift.')
    mode.add_argument('--write', action='store_true', help='Regenerate the corpus.')
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR, help='Vectors directory. Default tests/vectors')
    args = parser.parse_args(argv)
    try:
        vectors = build_vectors()
        if args.write:
            write_vectors(args.dir, vectors)
            print(f'manifest vectors written: {len(vectors)} files in {args.dir}')
            return 0
        problems = find_drift(args.dir, vectors)
    except (OSError, VectorError) as exc:
        print(f'manifest vectors failed: {exc}', file=sys.stderr)
        return 1
    if problems:
        print('manifest vectors drift: ' + ', '.join(problems), file=sys.stderr)
        print('run python3 scripts/manifest_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'manifest vectors ok: {len(vectors)} files match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
