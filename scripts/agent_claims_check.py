#!/usr/bin/env python3
"""Run pinned agent-lane claim checks, and optionally read a protocol checkout.

With no --protocol-dir, drift status is SKIPPED. SKIPPED is not a success.
--protocol-dir reads cited headings and needles and does not write the tree.
--execute compares the agent claim table with the simulated agent lane over
the in-process loopback facade. Results are SIMULATED. This is
CLAIM_CONFORMANCE.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.agent_claims import ClaimTableError, check_protocol, load_table, run_claims


def _print_skipped():
    print('SKIPPED')
    print(json.dumps(
        {'drift': 'not-run', 'label': 'CLAIM_CONFORMANCE', 'status': 'SKIPPED'},
        sort_keys=True,
    ))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol-dir', default=None)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--table', type=Path, default=None)
    args = parser.parse_args(argv)
    protocol_dir = args.protocol_dir
    if protocol_dir is not None and not str(protocol_dir).strip():
        protocol_dir = None
    if not args.execute and protocol_dir is None:
        _print_skipped()
        return 0
    try:
        table = load_table(args.table)
    except ClaimTableError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    code = 0
    if args.execute:
        result = run_claims(table)
        failed = result['failed']
        print(
            f"CLAIM_CONFORMANCE passed={result['passed']} total={result['total']} "
            f"failed={len(failed)}"
        )
        for row in failed:
            print(
                f"FAIL {row['id']} observed={row['observed']!r} expected={row['expected']!r}",
                file=sys.stderr,
            )
        if not result['ok']:
            code = 1
    if protocol_dir is not None:
        report = check_protocol(protocol_dir, table)
        print(f"CLAIM_DRIFT verified={report['verified']} total={report['total']}")
        if report['status'] != 'verified':
            for item in report['missing']:
                print(f"DRIFT {item.get('id')} {item.get('problem')}", file=sys.stderr)
            code = 1
    return code


if __name__ == '__main__':
    sys.exit(main())
