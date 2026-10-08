"""Locate package data from a checkout or a zipapp.

Stdlib only. This module must not import other capital modules: protocol
imports it before the vendored FSM modules exist on sys.path.
"""
from __future__ import annotations

import importlib.resources
import json
import sys

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
