#!/usr/bin/env python3
"""Pin SIMULATED seeded case dossiers; --check detects missing, extra or changed bytes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.service import CapitalService
from capital.store import canonical_bytes
from scripts.seed_demo import EXPECTED, apply_steps

DEFAULT_DIR = ROOT / 'tests' / 'vectors' / 'dossiers'


def build_vectors():
    service = CapitalService()
    service.instance_id = 'dossier-vectors'
    apply_steps(service)
    return {f'{advance_id}.json': canonical_bytes(service.dossier(advance_id, service.instance_id)) + b'\n'
            for advance_id, _phase, _gate in EXPECTED}


def find_drift(directory, vectors):
    directory = Path(directory)
    problems = []
    for name, raw in sorted(vectors.items()):
        path = directory / name
        if not path.is_file():
            problems.append(f'missing {name}')
        elif path.read_bytes() != raw:
            problems.append(f'differs {name}')
    if directory.is_dir():
        problems.extend(f'unexpected {path.name}' for path in sorted(directory.iterdir()) if path.name not in vectors)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR, help='Dossier directory')
    args = parser.parse_args(argv)
    vectors = build_vectors()
    if args.write:
        args.dir.mkdir(parents=True, exist_ok=True)
        for name, raw in sorted(vectors.items()):
            (args.dir / name).write_bytes(raw)
        for path in args.dir.glob('*.json'):
            if path.name not in vectors:
                path.unlink()
        print(f'dossier vectors written: {len(vectors)} SIMULATED files')
        return 0
    problems = find_drift(args.dir, vectors)
    if problems:
        print('dossier vectors drift: ' + ', '.join(problems), file=sys.stderr)
        return 1
    print(f'dossier vectors ok: {len(vectors)} SIMULATED files match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
