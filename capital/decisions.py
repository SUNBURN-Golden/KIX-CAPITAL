"""Read-only index of the capital-decision-v1 decision notes.

Rows come from scripts/decision_ledger.py, loaded by file path so the parser and
validator stay in one place. This module does not adopt a decision and does not
copy a note value. It reports each note's status, provisional flag, version and
per-entry statuses. The zipapp bundles neither docs/ nor scripts/, so that run
stays NOT_BOUND.
"""
from __future__ import annotations

import importlib.resources
import importlib.util
from pathlib import Path

DECISIONS_LABEL = 'simulated decision index — local note summary, not an adoption'
DECISIONS_MODE = 'READ_ONLY_DECISION_INDEX'
DECISIONS_NOT_BOUND = 'decision notes not bound'


def default_root():
    """Checkout root. Inside the zipapp this is the archive, which has no docs/."""
    return Path(str(importlib.resources.files('capital'))).parent


class DecisionIndex:
    def __init__(self, docs_dir=None, ledger_path=None):
        root = default_root()
        self.docs_dir = Path(docs_dir) if docs_dir is not None else root / 'docs'
        self.ledger_path = Path(ledger_path) if ledger_path is not None else root / 'scripts' / 'decision_ledger.py'
        self._ledger = None

    def _load_ledger(self):
        if self._ledger is None:
            if not self.ledger_path.is_file():
                return None
            spec = importlib.util.spec_from_file_location('capital_decision_ledger', self.ledger_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except (OSError, ImportError, SyntaxError):
                return None
            self._ledger = module
        return self._ledger

    def rows(self):
        """One ledger row per decision note, or None when the notes cannot be bound."""
        ledger = self._load_ledger()
        notes = self.docs_dir / 'decisions'
        if ledger is None or not notes.is_dir():
            return None
        try:
            coverage = (self.docs_dir / 'CAP_COVERAGE.md').read_text(encoding='utf-8')
            index = ledger.build_index(notes, ledger.expected_note_paths(coverage))
        except (OSError, ValueError):
            return None
        return [{
            'note': row['note'],
            'decision_id': row['decision_id'],
            'status': row['status'],
            'provisional': row['provisional'],
            'version': row['version'],
            'entries': dict(row['entries']),
        } for row in index]

    def body(self):
        rows = self.rows()
        if rows is None:
            return {'label': DECISIONS_LABEL, 'mode': DECISIONS_MODE, 'status': 'NOT_BOUND',
                    'reason': DECISIONS_NOT_BOUND, 'rows': []}
        return {'label': DECISIONS_LABEL, 'mode': DECISIONS_MODE, 'status': 'BOUND',
                'reason': None, 'rows': rows}

    def note_line(self, note):
        """`<status> per <note> (<version>)` from the live row, `NOT_BOUND per <note>` without one."""
        row = next((item for item in self.rows() or () if item['note'] == note), None)
        if row is None:
            return f'NOT_BOUND per {note}'
        line = f"{row['status']} per {note}"
        if row['version']:
            line += f" ({row['version']})"
        return line
