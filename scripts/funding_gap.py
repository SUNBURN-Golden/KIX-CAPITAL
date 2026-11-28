#!/usr/bin/env python3
"""Emit one simulated funding-gap report from a local audited workspace."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capital.funding_gap import report_workspace
from capital.store import canonical_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path, help='directory containing workspace.json')
    parser.add_argument('--schedule', required=True, type=Path, help='strict JSON schedule file (at most 1 MiB)')
    args = parser.parse_args(argv)
    report = report_workspace(args.workspace, args.schedule)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return int(report['status'] != 'EVALUATED_HYPOTHETICAL')


if __name__ == '__main__':
    raise SystemExit(main())
