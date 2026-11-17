#!/usr/bin/env python3
"""Regenerate and byte-pin the minimum-cure quote vectors in tests/vectors/cure_quote.json.

The artifact is SIMULATED / READ_ONLY_CAPTURED_INPUT_ADVISORY and deterministic:
no wall clock, no instance id, no path. It pins `capital.cure_quote.quote` over
the bounded SCENARIOS registry of built-in disposable books — the captured
inputs, outcome, quote amounts, admissibility and disposable-copy witnesses the
minimum-cure-quote node must keep producing. Instance ids and other volatile
keys are stripped with capital.export.strip_volatile so the bytes are
instance-free.

This is not SEMANTIC_CONFORMANCE, adopts no accounting policy and moves no
funds; the witnesses never mutate the scenario books. Passing --check says only
that the pinned local code still produces these bytes.

--check regenerates in memory and exits 1 when the file differs or is missing.
--write rewrites it. --file points both at another path.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import cure_quote
from capital.service import digest

DEFAULT_FILE = ROOT / 'tests' / 'vectors' / 'cure_quote.json'
FORMAT = 'KIX_CAPITAL_CURE_QUOTE_VECTORS_V1'


class VectorError(Exception):
    pass


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require(condition, message):
    if not condition:
        raise VectorError(message)


def dump(body) -> bytes:
    return (json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def build_body() -> dict:
    seed = _load_seed()
    scenarios = {}
    try:
        for name in sorted(cure_quote.SCENARIOS):
            scenarios[name] = cure_quote.evaluate_scenario(name)
    except (cure_quote.QuoteError, ValueError, KeyError, TypeError) as exc:
        raise VectorError(str(exc)) from exc
    for name, report in scenarios.items():
        _require(report['format'] == cure_quote.FORMAT, f'{name} format drifted')
        _require(report['outcome'] in cure_quote.OUTCOMES, f'{name} outcome outside the registry')
        _require(report['executionAuthorized'] is False and report['funds_executed'] is False, name)
        if report['amounts'] is not None:
            _require(type(report['amounts']['minimum_new_cash_krw']) is int, f'{name} minimum is not an integer')
    body = {
        'format': FORMAT, 'label': 'SIMULATED', 'data_label': 'SIMULATED_CURE_QUOTE',
        'funds_executed': False, 'executionAuthorized': False, 'semantic_conformance': False,
        'source': 'capital.cure_quote.quote over the bounded SCENARIOS builders (capital/cure_quote.py)',
        'scenarios': scenarios,
    }
    body['body_digest'] = digest(scenarios)
    try:
        seed._reject_volatile(body)
    except seed.SeedError as exc:
        raise VectorError(str(exc)) from exc
    return body


def build_artifact() -> bytes:
    """The full file bytes. Pure: nothing is written."""
    return dump(build_body())


def drift_paths(expected: bytes, actual: bytes, limit=8):
    seed = _load_seed()
    try:
        return seed.diff_paths(json.loads(expected), json.loads(actual))[:limit]
    except ValueError:
        return ['unparseable']


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Byte-compare the artifact. Exit 1 on drift.')
    mode.add_argument('--write', action='store_true', help='Regenerate the artifact.')
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE,
                        help='Artifact path. Default tests/vectors/cure_quote.json')
    args = parser.parse_args(argv)
    try:
        data = build_artifact()
        if args.write:
            args.file.parent.mkdir(parents=True, exist_ok=True)
            args.file.write_bytes(data)
            print(f'cure quote vectors written: {len(data)} bytes to {args.file}')
            return 0
        if not args.file.is_file():
            print(f'cure quote vectors missing: {args.file}', file=sys.stderr)
            print('run python3 scripts/cure_quote_vectors.py --write to regenerate', file=sys.stderr)
            return 1
        recorded = args.file.read_bytes()
    except (OSError, VectorError) as exc:
        print(f'cure quote vectors failed: {exc}', file=sys.stderr)
        return 1
    if recorded != data:
        print('cure quote vectors drift: ' + ', '.join(drift_paths(recorded, data)), file=sys.stderr)
        print('run python3 scripts/cure_quote_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'cure quote vectors ok: {len(data)} bytes match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
