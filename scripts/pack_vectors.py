#!/usr/bin/env python3
"""Regenerate and byte-pin the tamper corpus for the evidence pack verifier.

The corpus lives in tests/vectors/pack/ and is SIMULATED. It is built from the
seed_demo story replayed into a file workspace, with one fixed instance id, a
pinned saved_at stamp, and a fixed workspace label, so every run emits the
same bytes:

- pack/clean.json: a COMPLETE pack over the seeded workspace
- pack/section-<id>.json: one byte flipped inside that section's body
- pack/volatile.json: one byte flipped inside the volatile block
- pack/content-digest.json: one hex char of the pack content_digest flipped
- pack/truncated.json: the pack cut off mid-document

--check regenerates in memory and exits 1 when any file differs, is missing,
or is unexpected under pack/. --write rewrites the files and removes any other
pack/*.json, which this script owns. --dir points both at another directory.

The pack is a local diagnostic. Remote attestation, stage7 authenticated
export, and retention enforcement stay out of scope, and no DEV_ONLY key or
token is read or copied.
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

from capital.evidence import PACK_PART_TAGS, PACK_SECTION_IDS, dump, pack_document
from capital.service import CapitalService
from capital.store import FILE_NAME
from capital.verify import loads

DEFAULT_DIR = ROOT / 'tests' / 'vectors'
PACK_DIR = 'pack'
INSTANCE_ID = 'pack-vectors'
# The workspace path and envelope clock stamp are the only per-run fields; the
# pack records them in the volatile block, so both are pinned here.
WORKSPACE_LABEL = 'pack-vectors-workspace'
SAVED_AT = '2000-01-01T00:00:00.000000Z'


class VectorError(Exception):
    pass


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_seeded(directory):
    """Replay the seed_demo story into a file workspace and pin saved_at.

    The instance id is fixed before the first command so receipts, and the
    payload digest that covers them, do not change between runs. saved_at sits
    outside payload_sha256; pinning it keeps the volatile block stable.
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
    path = workspace / FILE_NAME
    document = loads(path.read_bytes())
    document['saved_at'] = SAVED_AT
    path.write_bytes(dump(document))
    return workspace


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
    token = f'"part_tag":"{PACK_PART_TAGS[name]}"'.encode()
    # The last letter of the tag, just before the closing quote.
    return _flip(raw, _unique_index(raw, token) + len(token) - 2, b'l', b'm')


def flip_volatile(raw):
    marker = b'"event_log":"EXCLUDED_NOT_PACKAGED"'
    return _flip(raw, _unique_index(raw, marker) + len(marker) - 2, b'E', b'F')


def flip_content_digest(raw):
    marker = b'"content_digest":"'
    # Canonical key order puts the pack-level digest before the embedded
    # manifest's own content_digest inside sections.
    return _flip(raw, raw.index(marker) + len(marker), b'0', b'1')


def truncate(raw):
    cut = raw[:len(raw) // 2]
    try:
        json.loads(cut)
    except ValueError:
        return cut
    raise VectorError('truncated pack still parses')


def build_vectors() -> dict:
    """Relative path under the vectors directory -> bytes. Pure: nothing is written."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = export_seeded(tmp)
        pack = pack_document(workspace, workspace_label=WORKSPACE_LABEL)
    if pack['status'] != 'COMPLETE':
        raise VectorError(f"seeded pack is not COMPLETE: {pack['incomplete_reasons']}")
    raw = dump(pack)
    files = {'clean.json': raw}
    for name in PACK_SECTION_IDS:
        files[f'section-{name}.json'] = flip_section(raw, name)
    files['volatile.json'] = flip_volatile(raw)
    files['content-digest.json'] = flip_content_digest(raw)
    files['truncated.json'] = truncate(raw)
    return {f'{PACK_DIR}/{name}': data for name, data in files.items()}


def find_drift(root, vectors):
    problems = []
    for relative, data in sorted(vectors.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f'missing {relative}')
        elif path.read_bytes() != data:
            problems.append(f'differs {relative}')
    packs = root / PACK_DIR
    if packs.is_dir():
        for path in sorted(packs.iterdir()):
            if f'{PACK_DIR}/{path.name}' not in vectors:
                problems.append(f'unexpected {PACK_DIR}/{path.name}')
    return problems


def write_vectors(root, vectors):
    for relative, data in sorted(vectors.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    packs = root / PACK_DIR
    if packs.is_dir():
        for path in sorted(packs.glob('*.json')):
            if f'{PACK_DIR}/{path.name}' not in vectors:
                path.unlink()
                print(f'removed stale {PACK_DIR}/{path.name}')


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
            print(f'pack vectors written: {len(vectors)} files in {args.dir}')
            return 0
        problems = find_drift(args.dir, vectors)
    except (OSError, VectorError) as exc:
        print(f'pack vectors failed: {exc}', file=sys.stderr)
        return 1
    if problems:
        print('pack vectors drift: ' + ', '.join(problems), file=sys.stderr)
        print('run python3 scripts/pack_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'pack vectors ok: {len(vectors)} files match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
