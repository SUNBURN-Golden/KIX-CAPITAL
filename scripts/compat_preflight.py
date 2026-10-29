#!/usr/bin/env python3
"""Read-only offline SIMULATED byte checks. Exit 0 grants no semantic adoption."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from capital.compat_preflight import (
    CompatibilityError, PreflightReport, canonical_bytes, check_bundle,
    decode_input, read_bundle_file, sha256,
)

CORPUS = ROOT / 'tests/vectors/compat'
MANIFEST = 'sdk/compat/manifests/manifest.synthetic.json'


def check_corpus(root=CORPUS):
    """Check the committed inventory, canonical vectors and explicit tuple; no repair."""
    root = Path(root)
    report = check_bundle(root / 'bundle', MANIFEST, root / 'expected.json')
    errors = list(report.errors)
    try:
        corpus = decode_input(read_bundle_file(root, 'corpus.json'))
        if (corpus.get('format') != 'capital-compat-corpus/1'
                or corpus.get('label') != 'READ_ONLY_FIXTURE' or type(corpus.get('files')) is not dict):
            raise CompatibilityError('corpus-format', 'corpus')
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} - {'corpus.json'}
        if actual != set(corpus['files']):
            raise CompatibilityError('corpus-file-set', 'corpus.files')
        for path, digest in corpus['files'].items():
            if sha256(read_bundle_file(root, path)) != digest:
                errors.append({'code': 'corpus-drift', 'location': path})
        for case in decode_input(read_bundle_file(root, 'canonical.json'))['cases']:
            raw = case['utf8'].encode('utf-8')
            if canonical_bytes(decode_input(raw)) != raw or sha256(raw) != case['sha256']:
                errors.append({'code': 'canonical-vector', 'location': case['name']})
    except (CompatibilityError, OSError, KeyError, TypeError, ValueError) as exc:
        errors.append({'code': getattr(exc, 'code', 'invalid-corpus'), 'location': getattr(exc, 'location', 'corpus')})
    return PreflightReport(tuple(errors), report.profile_kind, report.manifest_sha256)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--manifest')
    parser.add_argument('--expected', type=Path)
    args = parser.parse_args(argv)
    if args.check:
        if any(x is not None for x in (args.bundle, args.manifest, args.expected)):
            parser.error('--check cannot be combined with explicit bundle inputs')
        report = check_corpus()
    else:
        if any(x is None for x in (args.bundle, args.manifest, args.expected)):
            parser.error('--bundle, --manifest and --expected are all required')
        report = check_bundle(args.bundle, args.manifest, args.expected)
    print(json.dumps(report.as_dict(), sort_keys=True, separators=(',', ':')))
    return 0 if report.matched else 1


if __name__ == '__main__':
    sys.exit(main())
