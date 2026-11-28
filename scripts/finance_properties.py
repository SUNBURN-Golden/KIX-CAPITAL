#!/usr/bin/env python3
"""Read-only SIMULATED finance property suite; stdlib only, no server or writes."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.finance_properties import DEFAULT_CASES, run_all, violation_message


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--seeds', type=int, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    if args.seeds < 1:
        parser.error('--seeds must be at least 1')
    try:
        report = run_all(args.seeds)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for prop in report['properties']:
        for violation in prop['violations']:
            print(violation_message(prop['property'], violation), file=sys.stderr)
    if report['violations']:
        return 1
    print(f'finance properties ok SIMULATED: 6 properties, {args.seeds} cases each, 0 violations')
    return 0


if __name__ == '__main__':
    sys.exit(main())
