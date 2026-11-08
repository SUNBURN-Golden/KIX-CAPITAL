#!/usr/bin/env python3
"""Emit an existing statement and separate offline contribution map. SIMULATED."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.statement_trace import dump, trace_workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Read DIR/workspace.json once; no lock, write or repair.')
    args = parser.parse_args(argv)
    report = trace_workspace(args.workspace)
    sys.stdout.buffer.write(dump(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
