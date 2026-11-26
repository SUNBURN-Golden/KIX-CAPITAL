#!/usr/bin/env python3
"""Build, verify and exercise the read-only KIX Protocol delivery bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capital.compat_preflight import canonical_bytes, check_bundle
from capital.protocol_delivery import COMMIT, EXPECTED, MANIFEST, TUPLE

REPOSITORY = 'SUNBURN-Golden/kix-protocol'
PREFIX = 'reference/'
DIRECTORIES = ('credit_advance_f04', 'settlement_f01_f03')
VENDOR = ROOT / 'capital/vendor'
SUPPORT = (
    'reference/booking_resale_admission', 'reference/economics', 'reference/payment_effects',
    'reference/v0.3-rc1', 'integration_gate', 'docs/contracts/CREDIT_ADVANCE_F04.md',
    'docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md', 'readiness',
    'durable/__init__.py', 'durable/model.py', 'durable/budgets.py',
    'durable/errors.py', 'durable/normalize.py', 'durable/test_pure.py',
)


def git(protocol, *args):
    return subprocess.check_output(('git', '-C', str(protocol), *args))


def blobs(protocol, paths):
    entries = git(protocol, 'ls-tree', '-rz', COMMIT, '--', *paths).split(b'\0')
    for entry in filter(None, entries):
        metadata, path = entry.decode().split('\t', 1)
        mode, kind, oid = metadata.split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError(f'Expected a regular tracked file: {path}')
        yield path, git(protocol, 'cat-file', 'blob', oid)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def render(body):
    return (json.dumps(body, indent=2) + '\n').encode('utf-8')


def bundle(protocol):
    head = git(protocol, 'rev-parse', 'HEAD').decode().strip()
    if head != COMMIT:
        raise ValueError(f'Expected Protocol {COMMIT}, found {head}')
    refs = dict(blobs(protocol, [PREFIX + name for name in DIRECTORIES]))
    files = {name.removeprefix(PREFIX): sha(raw) for name, raw in refs.items()}
    manifest = dict(repository=REPOSITORY, commit=COMMIT, source_prefix=PREFIX, files=files)
    result = {VENDOR / name.removeprefix(PREFIX): raw for name, raw in refs.items()}
    result[VENDOR / 'manifest.json'] = render(manifest)

    sdk = git(protocol, 'show', f'{COMMIT}:{MANIFEST}')
    m = json.loads(sdk)
    source = m['source_references']
    paths = (
        MANIFEST, MANIFEST + '.sha256', 'toolchains.json',
        f"sdk/compat/profiles/{m['profile_revision']}.profile.json",
        source['fixture_profile'], source['extension_profile']['path'],
        m['generator']['path'], m['sdk_output']['path'],
        *(item['path'] for item in (*m['contract'].values(), *m['vectors'])),
    )
    copied = dict(blobs(protocol, paths))
    if set(copied) != set(paths):
        raise ValueError(f'Missing SDK input: {sorted(set(paths) - copied.keys())}')
    result.update({ROOT / path: raw for path, raw in copied.items()})
    result[ROOT / EXPECTED] = canonical_bytes({
        'format': 'capital-compat-expected/1', 'manifest_sha256': sha(sdk), 'tuple': m,
    })
    result[ROOT / TUPLE] = render({
        'format': 'capital-protocol-delivery/1',
        'repository': REPOSITORY,
        'commit': COMMIT,
        'tree': git(protocol, 'rev-parse', f'{COMMIT}^{{tree}}').decode().strip(),
        'sdk_manifest_sha256': sha(sdk),
        'vendor_manifest_sha256': sha(result[VENDOR / 'manifest.json']),
    })
    return result


def stage_tests(protocol):
    with tempfile.TemporaryDirectory(prefix='capital-protocol-tests-') as tmp:
        root = Path(tmp)
        for name, raw in blobs(protocol, SUPPORT):
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        for name in DIRECTORIES:
            for path in (VENDOR / name).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    dest = root / PREFIX / path.relative_to(VENDOR)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
        for path in (ROOT / 'docs/contracts/openapi').glob('*.json'):
            dest = root / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
        for name in DIRECTORIES:
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', PREFIX + name, '-v'],
                           check=True, cwd=root)
        subprocess.run([sys.executable, '-m', 'unittest', 'durable.test_pure', '-v'],
                       check=True, cwd=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ('write', 'check', 'test-vendor'):
        mode.add_argument('--' + name, action='store_true')
    parser.add_argument('--protocol-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        expected = bundle(args.protocol_dir)
        if args.write:
            for path, raw in expected.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        extras = [
            str(path.relative_to(ROOT)) for path in VENDOR.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts
            and path.suffix != '.pyc' and path not in expected
        ]
        mismatched = [
            str(path.relative_to(ROOT)) for path, raw in expected.items()
            if not path.is_file() or path.is_symlink() or path.read_bytes() != raw
        ]
        if extras or mismatched:
            raise ValueError(f'Bundle mismatch: unexpected={extras}, missing or changed={mismatched}')
        preflight = check_bundle(ROOT, MANIFEST, ROOT / EXPECTED)
        if not preflight.matched:
            raise ValueError(f'SDK preflight: {preflight.as_dict()}')
        print(f'READ_ONLY_FIXTURE {COMMIT} verified {len(json.loads(expected[VENDOR / "manifest.json"])["files"])} vendor files',
              flush=True)
        if args.test_vendor:
            stage_tests(args.protocol_dir)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
