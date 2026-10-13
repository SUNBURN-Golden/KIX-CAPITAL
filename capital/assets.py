"""The one declared asset. Stdlib only; imports nothing from capital.

PROVISIONAL per docs/decisions/CAPITAL_UPSTREAM_BINDING.md section 3.6
(entry asset-spec-declaration): KRW is declared once, as an AssetSpec shaped like
upstream reference/v0.3-rc1/assets.py (namespace, reference, decimals, max_atoms).
Amounts stay plain integers in that one asset. Capital has no asset registry
(DEFERRED), no FX and no cross-asset sums (NOT_ADOPTED); a second asset is not
accepted anywhere.

max_atoms is the pinned FSM MONEY_MAX fixture bound (10^12), not a registry limit.
The value is a literal because the zipapp carries no docs/ to read it from.
"""
from __future__ import annotations

import copy

KRW = {'namespace': 'fiat', 'reference': 'KRW', 'decimals': 0, 'max_atoms': 1_000_000_000_000}
ASSETS = (KRW,)


def declared():
    """Fresh copy of the declared assets, safe to embed in a response or a manifest."""
    return copy.deepcopy(list(ASSETS))


def matches(asset):
    """True only when asset is exactly the declared KRW spec.

    Strict: a bare 'KRW' string, a bool or float in place of an integer, or an extra
    or missing key all fail. Python compares True == 1 and 0.0 == 0, so the types are
    checked field by field.
    """
    if type(asset) is not dict or set(asset) != set(KRW):
        return False
    return all(type(asset[key]) is type(value) and asset[key] == value for key, value in KRW.items())
