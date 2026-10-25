"""Read-only decision index using the single ledger parser in either runtime."""
from __future__ import annotations

from capital.resources import (
    ARCHIVE_ROOT, as_resource, load_ledger, provenance, read_note,
)

DECISIONS_LABEL = 'simulated decision index — local note summary, not an adoption'
DECISIONS_MODE = 'READ_ONLY_DECISION_INDEX'
DECISIONS_NOT_BOUND = 'decision notes not bound'
_ANCHOR = 'CAPITAL_FINANCIAL_TERMS.md'


def default_root():
    return ARCHIVE_ROOT


class DecisionIndex:
    def __init__(self, docs_dir=None, ledger_path=None):
        self.docs_dir = ARCHIVE_ROOT / 'docs' if docs_dir is None else as_resource(docs_dir)
        self.override = docs_dir is not None
        self.ledger_path = (ARCHIVE_ROOT / 'scripts' / 'decision_ledger.py'
                            if ledger_path is None else as_resource(ledger_path))
        self._ledger = None

    def _load_ledger(self):
        if self._ledger is None:
            self._ledger = load_ledger(self.ledger_path)
        return self._ledger

    def _read(self, path):
        return read_note(path, override=self.override, ledger=self._load_ledger())

    def rows(self):
        """Coverage-first rows, preserving PENDING and INVALID semantics."""
        ledger = self._load_ledger()
        notes = self.docs_dir / 'decisions'
        if ledger is None or not notes.is_dir():
            return None

        def validate(path):
            note = self._read(path)
            errors, row = ledger.validate_note_bytes(note['raw_bytes'], f'docs/decisions/{path.name}')
            row.update(provenance(note))
            return errors, row

        try:
            coverage = (self.docs_dir / 'CAP_COVERAGE.md').read_text(encoding='utf-8')
            rows = ledger.build_index(notes, ledger.expected_note_paths(coverage), validator=validate)
        except (OSError, ValueError, RecursionError):
            return None
        for row in rows:
            if row['status'] == 'PENDING':
                row.update(notes_source='NONE', note_sha256=None)
        return rows

    def body(self):
        anchor = self._read(self.docs_dir / 'decisions' / _ANCHOR)
        rows = self.rows()
        # The body hash names the actual financial-terms anchor, not a collection
        # digest. Missing/invalid anchors fail closed; rows retain their statuses.
        bound = rows is not None and anchor['block'] is not None
        if bound:
            bound = not self._load_ledger().validate_note_bytes(anchor['raw_bytes'], _ANCHOR)[0]
        return {'label': DECISIONS_LABEL, 'mode': DECISIONS_MODE,
                'status': 'BOUND' if bound else 'NOT_BOUND',
                'reason': None if bound else DECISIONS_NOT_BOUND,
                **provenance(anchor), 'rows': [] if rows is None else rows}

    def note_line(self, note):
        """Live status/version citation; no policy values copied into the index."""
        row = next((item for item in self.rows() or () if item['note'] == note), None)
        if row is None:
            return f'NOT_BOUND per {note}'
        line = f"{row['status']} per {note}"
        if row['version']:
            line += f" ({row['version']})"
        return line
