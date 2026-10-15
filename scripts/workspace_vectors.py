#!/usr/bin/env python3
"""Regenerate and byte-pin the tamper corpus for the offline workspace auditor.

The corpus lives in tests/vectors/workspace/ and is SIMULATED. It is built
from the seed_demo story replayed into a file workspace with one fixed
instance id, so every run emits the same bytes:

- workspace/clean.json: an untouched workspace.json
- workspace/truncated.json: the file cut off mid-document
- workspace/payload-byte.json: one digit flipped inside the payload; the
  JSON still parses, so the stored payload_sha256 disagrees
- workspace/digest.json: one hex char of payload_sha256 flipped
- workspace/duplicate-key.json: a second top-level "format" key spliced in
- workspace/stale-digest.json: payload.state_digest replaced and
  payload_sha256 recomputed, so the intact envelope replays to a digest
  that disagrees with the stored one

--check regenerates in memory and exits 1 when any file differs, is missing,
or is unexpected under workspace/. --write rewrites the files and removes any
other workspace/*.json, which this script owns. --dir points both at another
directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import store
from capital.service import CapitalService
from capital.store import FILE_NAME
from capital.verify import loads

DEFAULT_DIR = ROOT / 'tests' / 'vectors'
WORKSPACE_DIR = 'workspace'
INSTANCE_ID = 'workspace-vectors'
# The envelope clock stamp is the only volatile field; payload_sha256 does
# not cover it, so pinning it is cosmetic.
SAVED_AT = '2000-01-01T00:00:00.000000Z'


class VectorError(Exception):
    pass


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(document) -> bytes:
    return store.canonical_bytes(document) + b'\n'


def export_seeded(directory):
    """Replay the seed_demo story into a file workspace and read back the document.

    The instance id is fixed before the first command so receipts, and the
    payload digest that covers them, do not change between runs.
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
    finally:
        if service is not None:
            seed._release(service.producer)
        port.close()
    document = loads((workspace / FILE_NAME).read_bytes())
    document['saved_at'] = SAVED_AT
    return document


def _flip(raw, index, first, second):
    """Swap the byte at `index` for `first`, or for `second` when it already is `first`."""
    current = raw[index:index + 1]
    replacement = first if current != first else second
    flipped = raw[:index] + replacement + raw[index + 1:]
    if len(flipped) != len(raw) or flipped == raw:
        raise VectorError('flip did not change exactly one byte')
    json.loads(flipped)
    return flipped


def truncate(raw):
    cut = raw[:len(raw) // 2]
    try:
        json.loads(cut)
    except ValueError:
        return cut
    raise VectorError('truncated workspace still parses')


def flip_payload_byte(raw):
    """Flip one digit inside the payload; the JSON stays valid and reaches the checksum."""
    marker = b'"amount":'
    return _flip(raw, raw.index(marker) + len(marker), b'3', b'4')


def flip_checksum(raw):
    marker = b'"payload_sha256":"'
    return _flip(raw, raw.index(marker) + len(marker), b'0', b'1')


def duplicate_key(raw):
    pair = b'"format":"KIX_CAPITAL_LOCAL_WORKSPACE_V1"'
    if raw.count(pair) != 1:
        raise VectorError('format pair is not unique')
    doubled = raw.replace(pair, pair + b',' + pair, 1)
    json.loads(doubled)
    try:
        loads(doubled)
    except ValueError:
        return doubled
    raise VectorError('duplicate key still parses strictly')


def stale_digest(raw):
    document = loads(raw)
    document['payload']['state_digest'] = '0' * 64
    document['payload_sha256'] = store._checksum(document['payload'])
    return dump(document)


def build_vectors() -> dict:
    """Relative path under the vectors directory -> bytes. Pure: nothing is written."""
    with tempfile.TemporaryDirectory() as tmp:
        document = export_seeded(tmp)
    raw = dump(document)
    files = {
        'clean.json': raw,
        'truncated.json': truncate(raw),
        'payload-byte.json': flip_payload_byte(raw),
        'digest.json': flip_checksum(raw),
        'duplicate-key.json': duplicate_key(raw),
        'stale-digest.json': stale_digest(raw),
    }
    return {f'{WORKSPACE_DIR}/{name}': data for name, data in files.items()}


def find_drift(root, vectors):
    problems = []
    for relative, data in sorted(vectors.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f'missing {relative}')
        elif path.read_bytes() != data:
            problems.append(f'differs {relative}')
    workspace = root / WORKSPACE_DIR
    if workspace.is_dir():
        for path in sorted(workspace.iterdir()):
            if f'{WORKSPACE_DIR}/{path.name}' not in vectors:
                problems.append(f'unexpected {WORKSPACE_DIR}/{path.name}')
    return problems


def write_vectors(root, vectors):
    for relative, data in sorted(vectors.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    workspace = root / WORKSPACE_DIR
    if workspace.is_dir():
        for path in sorted(workspace.glob('*.json')):
            if f'{WORKSPACE_DIR}/{path.name}' not in vectors:
                path.unlink()
                print(f'removed stale {WORKSPACE_DIR}/{path.name}')


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
            print(f'workspace vectors written: {len(vectors)} files in {args.dir}')
            return 0
        problems = find_drift(args.dir, vectors)
    except (OSError, VectorError) as exc:
        print(f'workspace vectors failed: {exc}', file=sys.stderr)
        return 1
    if problems:
        print('workspace vectors drift: ' + ', '.join(problems), file=sys.stderr)
        print('run python3 scripts/workspace_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'workspace vectors ok: {len(vectors)} files match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
