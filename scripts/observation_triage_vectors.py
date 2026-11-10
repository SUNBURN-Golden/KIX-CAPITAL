#!/usr/bin/env python3
"""Read-only SIMULATED observation triage vector check; no regeneration mode."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from test_observation_triage import VECTORS, run_triage_vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', required=True, action='store_true')
    parser.add_argument('--file', type=Path, default=VECTORS / 'cases.json')
    args = parser.parse_args()
    try:
        run_triage_vectors(args.file)
    except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
        print(f'SIMULATED observation triage vectors FAIL: {exc}', file=sys.stderr)
        return 1
    print('SIMULATED observation triage vectors PASS; NOT_BOUND; applied=false; funds_executed=false')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
