#!/usr/bin/env python3
"""Generate the NOT_BOUND checklist from in-process readiness.

The block is the same data GET /api/readiness serves, without instance_id
and without a clock. --check exits 1 when docs/ACCEPTANCE_KO.md drifts.
--write replaces only the generated region.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.service import CapitalService

BEGIN = '<!-- generated:not-bound begin -->'
END = '<!-- generated:not-bound end -->'
DEFAULT_FILE = ROOT / 'docs' / 'ACCEPTANCE_KO.md'


def render(readiness=None) -> str:
    """Deterministic markdown. No instance id and no timestamp."""
    if readiness is None:
        readiness = CapitalService().readiness()
    lines = []
    for group in readiness['groups']:
        if group['status'] == 'AVAILABLE_LOCAL':
            continue
        caps = ', '.join(group['requirements'])
        for blocker in group['blockers']:
            lines.append(f"- [ ] {group['id']} ({group['status']}; {caps}): {blocker}")
    lines.append(f"upstream_binding: {readiness['upstream_binding']}")
    matched = bool(readiness['source_integrity']['all_matched'])
    lines.append(f"source_integrity.all_matched: {str(matched).lower()}")
    return '\n'.join(lines) + '\n'


def extract_generated(document: str) -> str:
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise ValueError('generated markers missing or repeated')
    _pre, rest = document.split(BEGIN, 1)
    inner, _post = rest.split(END, 1)
    if inner.startswith('\n'):
        inner = inner[1:]
    return inner


def replace_generated(document: str, block: str) -> str:
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise ValueError('generated markers missing or repeated')
    pre, rest = document.split(BEGIN, 1)
    _inner, post = rest.split(END, 1)
    if not block.endswith('\n'):
        block += '\n'
    return f'{pre}{BEGIN}\n{block}{END}{post}'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE)
    args = parser.parse_args(argv)
    try:
        document = args.file.read_text(encoding='utf-8')
        block = render()
        if args.write:
            args.file.write_text(replace_generated(document, block), encoding='utf-8')
            return 0
        if extract_generated(document) != block:
            print('not-bound checklist drift', file=sys.stderr)
            return 1
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
