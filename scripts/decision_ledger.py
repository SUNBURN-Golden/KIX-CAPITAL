#!/usr/bin/env python3
"""Validate capital-decision-v1 blocks and print a decision index.

Expected note paths come from docs/decisions/*.md citations in the CAP
coverage owner cells. A missing file is PENDING and does not fail.
An existing note is invalid when it does not contain exactly one well-formed
block. ADOPTED requires value, provided_by and date. UNDETERMINED rejects
those three fields. DEFERRED and NOT_ADOPTED require a null value, provided_by,
date and target. This script does not import the Capital product and does not
invent decision values.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE = ROOT / 'docs' / 'CAP_COVERAGE.md'
DECISIONS = ROOT / 'docs' / 'decisions'

_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_NOTE_PATH = re.compile(r'docs/decisions/[A-Za-z0-9][A-Za-z0-9_.-]*\.md')
_CAP = re.compile(r'CAP-(?:0[1-9]|1[0-9]|20)\Z')
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_ENTRY_STATUS = frozenset(('ADOPTED', 'UNDETERMINED', 'DEFERRED', 'NOT_ADOPTED'))


class DecisionParseError(ValueError):
    pass


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise DecisionParseError(f'duplicate key {key}')
        obj[key] = value
    return obj


def _parse_object(raw):
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except DecisionParseError:
        raise
    except json.JSONDecodeError as exc:
        raise DecisionParseError(f'JSON {exc.msg}') from exc
    if type(parsed) is not dict:
        raise DecisionParseError('block must be a JSON object')
    return parsed


def extract_blocks(text):
    """Return the parsed JSON object of each capital-decision-v1 fence."""
    blocks = []
    for raw in _FENCE.findall(text):
        blocks.append(_parse_object(raw))
    return blocks


def expected_note_paths(coverage_text):
    """Unique docs/decisions/*.md paths in first-seen order."""
    found = []
    seen = set()
    for match in _NOTE_PATH.finditer(coverage_text):
        path = match.group(0)
        if path not in seen:
            seen.add(path)
            found.append(path)
    return found


def _iso_date(value):
    if type(value) is not str or _ISO_DATE.fullmatch(value) is None:
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _note_name(path):
    path = Path(path)
    return f'docs/decisions/{path.name}'


def _blank(note):
    return {'note': note, 'decision_id': None, 'status': 'INVALID', 'entries': {}}


def _rollup(entries):
    statuses = set(entries.values())
    if statuses == {'ADOPTED'}:
        return 'ADOPTED'
    if statuses == {'UNDETERMINED'}:
        return 'UNDETERMINED'
    if statuses:
        return 'MIXED'
    return 'INVALID'


def _validate_entry(name, entry, errors):
    if type(entry) is not dict:
        errors.append(f'{name}: entry must be an object')
        return 'INVALID'
    status = entry.get('status')
    if status not in _ENTRY_STATUS:
        errors.append(f'{name}: status must be ADOPTED or UNDETERMINED')
        recorded = status if type(status) is str else 'INVALID'
    else:
        recorded = status
    for key in ('cap_rows', 'rationale', 'provisional'):
        if key not in entry:
            errors.append(f'{name}: missing {key}')
    cap_rows = entry.get('cap_rows')
    if 'cap_rows' in entry and type(cap_rows) is not list:
        errors.append(f'{name}: cap_rows must be a list')
    elif type(cap_rows) is list:
        for cap in cap_rows:
            if type(cap) is not str or _CAP.fullmatch(cap) is None:
                errors.append(f'{name}: bad cap id {cap!r}')
    rationale = entry.get('rationale')
    if 'rationale' in entry and (type(rationale) is not str or not rationale.strip()):
        errors.append(f'{name}: rationale must be non-empty')
    if 'provisional' in entry and type(entry.get('provisional')) is not bool:
        errors.append(f'{name}: provisional must be a boolean')
    if status == 'ADOPTED':
        if 'value' not in entry or entry.get('value') is None:
            errors.append(f'{name}: ADOPTED requires value')
        provided_by = entry.get('provided_by')
        if type(provided_by) is not str or not provided_by.strip():
            errors.append(f'{name}: ADOPTED requires provided_by')
        if not _iso_date(entry.get('date')):
            errors.append(f'{name}: ADOPTED requires date')
    elif status == 'UNDETERMINED':
        for forbidden in ('value', 'provided_by', 'date'):
            if forbidden in entry:
                errors.append(f'{name}: UNDETERMINED must not include {forbidden}')
    elif status in ('DEFERRED', 'NOT_ADOPTED'):
        # Upstream binding notes record a direction in target and leave value null.
        # A non-null value belongs only on ADOPTED.
        if 'value' not in entry or entry.get('value') is not None:
            errors.append(f'{name}: {status} value must be null')
        provided_by = entry.get('provided_by')
        if type(provided_by) is not str or not provided_by.strip():
            errors.append(f'{name}: {status} requires provided_by')
        if not _iso_date(entry.get('date')):
            errors.append(f'{name}: {status} requires date')
        target = entry.get('target')
        if type(target) is not dict or not target:
            errors.append(f'{name}: {status} requires target')
    return recorded


def validate_note(path):
    """Return (errors, summary) for one decision note on disk."""
    path = Path(path)
    note = _note_name(path)
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as exc:
        return [f'{note}: {exc}'], _blank(note)
    try:
        blocks = extract_blocks(text)
    except DecisionParseError as exc:
        return [f'{note}: {exc}'], _blank(note)
    if len(blocks) != 1:
        return [f'{note}: expected exactly one capital-decision-v1 block, found {len(blocks)}'], _blank(note)
    block = blocks[0]
    errors = []
    if block.get('schema') != 'capital-decision-v1':
        errors.append(f'{note}: schema must be capital-decision-v1')
    decision_id = block.get('decision_id')
    if type(decision_id) is not str or not decision_id:
        errors.append(f'{note}: decision_id must be a string')
        decision_id = None
    entries = block.get('entries')
    recorded = {}
    if type(entries) is not dict:
        errors.append(f'{note}: entries must be an object')
    else:
        for name, entry in entries.items():
            recorded[name] = _validate_entry(name, entry, errors)
    if errors:
        status = 'INVALID'
    else:
        block_status = block.get('status')
        status = block_status if type(block_status) is str and block_status else _rollup(recorded)
    summary = {
        'note': note,
        'decision_id': decision_id,
        'status': status,
        'entries': recorded,
    }
    return errors, summary


def build_index(decisions_dir, expected):
    """Rows of {note, decision_id, status, entries} for expected paths, then extras."""
    decisions_dir = Path(decisions_dir)
    rows = []
    seen = set()
    for rel in expected:
        seen.add(Path(rel).name)
        path = decisions_dir / Path(rel).name
        if not path.is_file():
            rows.append({
                'note': f'docs/decisions/{Path(rel).name}',
                'decision_id': None,
                'status': 'PENDING',
                'entries': {},
            })
            continue
        _errors, summary = validate_note(path)
        rows.append(summary)
    if decisions_dir.is_dir():
        for path in sorted(decisions_dir.glob('*.md')):
            if path.name in seen:
                continue
            _errors, summary = validate_note(path)
            rows.append(summary)
    return rows


def collect_errors(decisions_dir, expected):
    """Errors for notes that exist. Missing expected notes are not errors."""
    decisions_dir = Path(decisions_dir)
    errors = []
    seen = set()
    names = [Path(rel).name for rel in expected]
    if decisions_dir.is_dir():
        names.extend(path.name for path in sorted(decisions_dir.glob('*.md')))
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = decisions_dir / name
        if not path.is_file():
            continue
        errors.extend(validate_note(path)[0])
    return errors


def format_index(rows):
    lines = ['note\tdecision_id\tstatus\tentries']
    for row in rows:
        entries = ', '.join(f'{name}={status}' for name, status in row['entries'].items()) or '-'
        decision_id = row['decision_id'] or '-'
        lines.append(f"{row['note']}\t{decision_id}\t{row['status']}\t{entries}")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage', type=Path, default=COVERAGE)
    parser.add_argument('--decisions', type=Path, default=DECISIONS)
    args = parser.parse_args(argv)
    try:
        coverage_text = args.coverage.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'cannot read coverage: {exc}', file=sys.stderr)
        return 2
    expected = expected_note_paths(coverage_text)
    rows = build_index(args.decisions, expected)
    sys.stdout.write(format_index(rows))
    errors = collect_errors(args.decisions, expected)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
