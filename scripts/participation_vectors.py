#!/usr/bin/env python3
"""Check independent participation expectations, reporting JSON paths. Never writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from capital.shadow import DecisionNoteShadow


def differences(actual, expected):
    findings = []
    for path, wanted in expected.items():
        value = actual
        try:
            for key in path.split('.'):
                value = value[int(key)] if type(value) is list else value[key]
        except (KeyError, IndexError, ValueError, TypeError):
            findings.append(f'{path}: missing (expected {wanted!r})')
            continue
        if type(value) is not type(wanted) or value != wanted:
            findings.append(f'{path}: expected {wanted!r}, got {value!r}')
    return findings


def check(path):
    vectors = json.loads(path.read_text(encoding='utf-8'))
    if vectors['schema'] != 'capital-participation-vectors-v1' or not vectors['scenarios']:
        return ['invalid or empty participation vectors']
    shadow = DecisionNoteShadow()
    return [f'{row["name"]}.{finding}' for row in vectors['scenarios']
            for finding in differences(shadow.participation_replay(row['book']), row['expected'])]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', required=True, action='store_true')
    parser.add_argument('--vectors', type=Path, default=ROOT / 'tests/vectors/participation_window.json')
    args = parser.parse_args(argv)
    try:
        findings = check(args.vectors)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        findings = [str(exc)]
    for finding in findings:
        print(finding, file=sys.stderr)
    if not findings:
        print('participation vectors match independent expectations (SIMULATED only)')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
