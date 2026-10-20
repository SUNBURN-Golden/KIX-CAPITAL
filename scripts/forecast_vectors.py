#!/usr/bin/env python3
"""Regenerate and byte-pin the cash-ladder vector in tests/vectors/forecast_vectors.json.

The artifact is SIMULATED and deterministic: no clock, no random instance id, no
path. It pins the read-only `GET /api/terms/portfolio/forecast` body for the
seeded demo book of scripts/seed_demo.py (sim_day 0, three drawn advances) at a
fixed hypothetical `expected_settlement_cash_day` — the forecast the
cashflow-forecast node must keep producing. Instance ids and state digests are
stripped with capital.export.strip_volatile so the bytes are instance-free.

This is not SEMANTIC_CONFORMANCE, adopts no accounting policy and moves no
funds. Passing --check says only that the pinned local code still produces
these bytes.

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

from capital.export import strip_volatile
from capital.service import digest

DEFAULT_FILE = ROOT / 'tests' / 'vectors' / 'forecast_vectors.json'
FORMAT = 'KIX_CAPITAL_FORECAST_VECTORS_V1'
# Fixed hypothetical settlement day for the pin. A query parameter, not a note value.
EXPECTED_DAY = 45


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
    service = seed.build_service()
    try:
        body = {
            'format': FORMAT, 'label': 'SIMULATED', 'data_label': 'SIMULATED',
            'funds_executed': False, 'semantic_conformance': False,
            'source': 'CapitalService.forecast on the fixed-instance-free seed book (capital/forecast.py)',
            'expected_settlement_cash_day': EXPECTED_DAY,
            'forecasts': {
                'with_settlement_day': strip_volatile(
                    service.forecast(service.instance_id, expected_settlement_cash_day=EXPECTED_DAY)),
                'without_settlement_day': strip_volatile(
                    service.forecast(service.instance_id)),
            },
        }
        for name, forecast in body['forecasts'].items():
            _require(forecast['status'] == 'BOUND', f'{name} not BOUND')
            _require(forecast['reconciliation']['matched'] is True, f'{name} does not reconcile')
        body['body_digest'] = digest(body['forecasts'])
    finally:
        seed._release(service.producer)
    try:
        seed._reject_volatile(body)
    except seed.SeedError as exc:
        raise VectorError(str(exc)) from exc
    return body


def build_artifact() -> bytes:
    """The full file bytes. Pure: nothing is written."""
    return dump(build_body())


def drift_paths(expected: bytes, actual: bytes, limit=8):
    """JSON paths where the two byte strings differ, or a reason when either does not parse."""
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
                        help='Artifact path. Default tests/vectors/forecast_vectors.json')
    args = parser.parse_args(argv)
    try:
        data = build_artifact()
        if args.write:
            args.file.parent.mkdir(parents=True, exist_ok=True)
            args.file.write_bytes(data)
            print(f'forecast vectors written: {len(data)} bytes to {args.file}')
            return 0
        if not args.file.is_file():
            print(f'forecast vectors missing: {args.file}', file=sys.stderr)
            print('run python3 scripts/forecast_vectors.py --write to regenerate', file=sys.stderr)
            return 1
        recorded = args.file.read_bytes()
    except (OSError, VectorError) as exc:
        print(f'forecast vectors failed: {exc}', file=sys.stderr)
        return 1
    if recorded != data:
        print('forecast vectors drift: ' + ', '.join(drift_paths(recorded, data)), file=sys.stderr)
        print('run python3 scripts/forecast_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'forecast vectors ok: {len(data)} bytes match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
