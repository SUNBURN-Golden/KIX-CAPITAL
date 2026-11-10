#!/usr/bin/env python3
"""SIMULATED bounded synthetic refund-frontier vectors; --check never writes."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from capital import margin, refund_frontier as frontier

FILE = ROOT / 'tests/vectors/refund_frontier.json'


def subject(advance_id='a', claim_id='c', beneficiary='B', amounts=(6, 4), exposure=4, rate=5000):
    """Explicit synthetic terms, never real product terms or a provider input."""
    payees = [f'payee-{i}' for i in range(len(amounts))]
    return {'advance_id': advance_id, 'case': {'claim_id': claim_id, 'beneficiary_role': beneficiary,
            'phase': 'DRAWN'}, 'claim': {'claim_id': claim_id, 'refund_face': 0,
            'fixture_reclassified': False, 'obligations': [
                {'payee': p, 'outstanding': value, 'face': value, 'distributed': 0, 'recovery_due': 0}
                for p, value in zip(payees, amounts)]}, 'principal': exposure, 'gate': 'SYNTHETIC_GATE',
            'draw_day': 0, 'margin': {'payees': payees, 'advance_rate_bps': rate},
            'writeoff': False, 'mapping_valid': True}


def inputs(subjects):
    ids = {s['case']['claim_id'] for s in subjects}
    return {'workspace': margin.SOURCE_DISPOSABLE, 'subjects': subjects,
            'registry': frontier.registry_evidence([], {}, ids),
            'policy': frontier.load_policy(), 'capture': {'label': 'SIMULATED_SYNTHETIC_BOOK'}}


def build_body():
    books = {'plateau': [subject()],
             'shared': [subject('a', amounts=(10,), exposure=5), subject('b', amounts=(10,), exposure=1)],
             'unequal_rates': [subject('a', 'c', amounts=(20,), exposure=15, rate=8500),
                               subject('b', 'd', amounts=(10,), exposure=3)],
             'already': [subject(exposure=6)], 'zero': [subject(exposure=0)],
             'endpoint': [subject(amounts=(10,), exposure=1, rate=10000)]}
    return {'format': 'KIX_CAPITAL_REFUND_FRONTIER_V1', 'label': 'SIMULATED',
            'cases': {name: frontier.build(frontier.FrozenInputs.capture(inputs(rows)))
                      for name, rows in books.items()}}


def build_artifact():
    return (json.dumps(build_body(), sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--file', type=Path, default=FILE)
    args = parser.parse_args(argv)
    raw = build_artifact()
    if args.write:
        args.file.write_bytes(raw)
        print(f'refund frontier vectors written: {len(raw)} bytes')
        return 0
    if not args.file.exists() or args.file.read_bytes() != raw:
        print('refund frontier vectors drift; run python3 scripts/refund_frontier_vectors.py --write', file=sys.stderr)
        return 1
    print(f'refund frontier vectors ok: {len(raw)} bytes match')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
