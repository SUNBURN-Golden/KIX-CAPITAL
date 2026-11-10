#!/usr/bin/env python3
"""SIMULATED CLAIM_CONFORMANCE; optional read-only Protocol citation verification."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from capital import contract_invariants as inv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--protocol-dir')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--table', type=Path, default=inv.TABLE)
    args = parser.parse_args(argv)
    if args.seed is not None and (args.check or args.write):
        parser.error('--seed cannot change the pinned corpus in --check/--write')
    if not (args.execute or args.check or args.write or args.protocol_dir or args.seed is not None):
        print('SKIPPED: no execution or protocol checkout requested; not a pass')
        return 0
    try:
        table = inv.load_table(args.table)
        code = 0
        if args.execute or args.check or args.write or args.seed is not None:
            corpus = inv.run_corpus(inv.SEEDS if args.seed is None else (args.seed,))
            result = inv.run_claims(table, corpus)
            print(f"CLAIM_CONFORMANCE SIMULATED passed={result['passed']} total={result['total']} loopback={result['loopback']}")
            if not result['ok']:
                print(json.dumps(result['rows'], sort_keys=True), file=sys.stderr)
                code = 1
            if args.write and result['ok']:
                table['pinned_seeds']['digests'] = inv.seed_digests(corpus)
                args.table.write_text(json.dumps(table, indent=2, sort_keys=True) + '\n', encoding='utf-8')
                print('SEEDS WRITTEN count=12')
            if args.check:
                if table['pinned_seeds']['digests'] != inv.seed_digests(corpus):
                    print('SEED_DRIFT', file=sys.stderr)
                    code = 1
                else:
                    print('SEEDS MATCH count=12')
        if args.protocol_dir:
            report = inv.check_protocol(args.protocol_dir, table)
            print(f"CLAIM_DRIFT verified={report['verified']} total={report['total']}")
            if report['status'] != 'verified':
                print(json.dumps(report['missing']), file=sys.stderr)
                code = 1
        elif args.execute or args.check:
            print('PROTOCOL_CITATION SKIPPED: no --protocol-dir; not a drift pass')
        return code
    except (inv.ClaimTableError, OSError, AssertionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
