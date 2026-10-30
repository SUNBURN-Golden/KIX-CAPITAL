"""Locate package data from a checkout or a zipapp.

Stdlib only. This module must not import other capital modules: protocol
imports it before the vendored FSM modules exist on sys.path.
"""
from __future__ import annotations

import hashlib
import importlib.resources
import json
import sys
import types
from functools import lru_cache
from pathlib import Path

ROOT = importlib.resources.files('capital')
STATIC = ROOT / 'static'
VENDOR = ROOT / 'vendor'
# Same insertion order as the previous vendor-directory loop: each insert(0)
# leaves the last package at sys.path[0].
VENDOR_PACKAGES = ('credit_advance_f04', 'settlement_f01_f03')


def read_static(name: str) -> bytes:
    if not name or '/' in name or '\\' in name or name in {'.', '..'}:
        raise ValueError('invalid static asset name')
    return (STATIC / name).read_bytes()


def vendor_manifest() -> dict:
    return json.loads((VENDOR / 'manifest.json').read_bytes().decode('utf-8'))


def vendor_sys_path() -> list[str]:
    # zipfile.Path string form can end with a slash; zipimport rejects that.
    return [str(VENDOR / name).rstrip('/\\') for name in VENDOR_PACKAGES]


def install_vendor_path() -> None:
    """Put vendored reference packages on sys.path. Idempotent."""
    for entry in vendor_sys_path():
        if entry not in sys.path:
            sys.path.insert(0, entry)


ARCHIVE_ROOT = ROOT.parent


def note_path(name):
    """Keep the archive-root Traversable intact in both runtime forms."""
    return ARCHIVE_ROOT / 'docs' / 'decisions' / name


def as_resource(value):
    return Path(value) if isinstance(value, str) else value


def resource_source(resource, *, override=False):
    if override:
        return 'OVERRIDE_FILE'
    return 'CHECKOUT' if isinstance(resource, Path) else 'BUNDLED_IN_ARTIFACT'


@lru_cache(maxsize=8)
def _ledger_code(raw, filename):
    """Reuse compilation by exact source bytes, never by path or timestamp alone."""
    return compile(raw, filename, 'exec')


def load_ledger(path=None):
    """Execute only the selected parser source; Markdown is always data."""
    source = ARCHIVE_ROOT / 'scripts' / 'decision_ledger.py' if path is None else as_resource(path)
    try:
        raw = source.read_bytes()
        module = types.ModuleType('capital_decision_ledger')
        module.__file__ = str(source)
        exec(_ledger_code(raw, str(source)), module.__dict__)
        return module
    except (OSError, ValueError, ImportError, SyntaxError):
        return None


_DEFAULT_LEDGER = object()


def read_note(resource, *, override=False, ledger=_DEFAULT_LEDGER):
    """Read once: raw-byte provenance survives decoding and parse failures.

    Explicit overrides are exclusive; this function never selects a fallback.
    Consumer-specific usability checks remain with each policy port.
    """
    resource = as_resource(resource)
    result = {'raw_bytes': None, 'notes_source': 'NONE', 'note_sha256': None, 'block': None}
    try:
        raw = resource.read_bytes()
    except (OSError, ValueError):
        return result
    result.update(raw_bytes=raw, notes_source=resource_source(resource, override=override),
                  note_sha256=hashlib.sha256(raw).hexdigest())
    parser = load_ledger() if ledger is _DEFAULT_LEDGER else ledger
    if parser is None:
        return result
    try:
        blocks = parser.extract_blocks(raw.decode('utf-8'))
        if len(blocks) == 1 and blocks[0].get('schema') == 'capital-decision-v1':
            result['block'] = blocks[0]
    except (UnicodeError, ValueError, RecursionError):
        pass
    return result


def provenance(note):
    return {key: note[key] for key in ('notes_source', 'note_sha256')}
