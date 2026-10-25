#!/usr/bin/env python3
"""Execute SIMULATED lifecycle claims; citation drift is SKIPPED without a checkout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.lifecycle_claims import ClaimTableError, check_protocol, load_table, run_claims


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--protocol-dir')
    parser.add_argument('--table', type=Path)
    args = parser.parse_args(argv)
    try:
        table = load_table(args.table)
    except ClaimTableError as exc:
        print(json.dumps({'label': 'CLAIM_CONFORMANCE', 'simulation': 'SIMULATED',
                          'funds_executed': False, 'status': 'INVALID', 'error': str(exc)}), file=sys.stderr)
        return 2
    code = 0
    if args.execute:
        result = run_claims(table)
        print(f"CLAIM_CONFORMANCE passed={result['passed']} total={result['total']} failed={len(result['failed'])}")
        print(json.dumps(result, sort_keys=True))
        if not result['ok']:
            code = 1
    report = check_protocol(args.protocol_dir, table)
    if report['status'] == 'SKIPPED':
        print('SKIPPED')
    else:
        print(f"CLAIM_DRIFT verified={report['verified']} total={report['total']}")
    print(json.dumps(report, sort_keys=True))
    return 1 if report['status'] == 'failed' else code


if __name__ == '__main__':
    sys.exit(main())
