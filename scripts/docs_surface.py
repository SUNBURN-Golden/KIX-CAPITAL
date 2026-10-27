#!/usr/bin/env python3
"""Cross-check that the docs keep enumerating the surfaces they claim to enumerate.

This fences the audit-fix drift class: a registered route dropped from
docs/INTEGRATION.md, a pinned vector artifact (or its --check script) dropped
from README.md, or the acceptance stage ids disagreeing between
scripts/acceptance.py and docs/OPERATOR_HANDBOOK_KO.md / docs/ACCEPTANCE_KO.md.
It changes nothing: --check is the only mode and nothing is written.

Routes are derived live from capital.server.GET_DISPATCH and POST_DISPATCH,
checked against capital.auth.ROUTE_PERMISSIONS — the same source the auth
matrix uses. Each route must keep its hand-maintained needle (ROUTE_NEEDLES)
in the prose of docs/INTEGRATION.md. Generated blocks are stripped first:
the auth-matrix table names every route, but it is already fenced by
scripts/auth_matrix.py --check and is not the hand enumeration this guard
watches. Every file under tests/vectors/ must be covered by a VECTOR_NEEDLES
entry whose needles stay in README.md, and the stage ids listed after the
'stage id' anchor in docs/OPERATOR_HANDBOOK_KO.md and docs/ACCEPTANCE_KO.md
must equal REQUIRED_STAGES in scripts/acceptance.py.

--check exits 0 when the current tree has zero findings and 1 otherwise,
naming the missing needle, uncovered artifact, or disagreeing stage list.
The needle registries are maintained by hand like tests/test_handbook.py;
tests/test_docs_surface.py mutates temporary doc copies and expects a
failure for each mutation.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.auth import ROUTE_PERMISSIONS
from capital.server import GET_DISPATCH, POST_DISPATCH

DEFAULT_INTEGRATION = ROOT / 'docs' / 'INTEGRATION.md'
DEFAULT_README = ROOT / 'README.md'
DEFAULT_VECTORS = ROOT / 'tests' / 'vectors'
ACCEPTANCE_SCRIPT = ROOT / 'scripts' / 'acceptance.py'
# label -> default path; each doc must list the stage ids after a 'stage id' anchor
STAGE_DOCS = {
    'docs/OPERATOR_HANDBOOK_KO.md': ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md',
    'docs/ACCEPTANCE_KO.md': ROOT / 'docs' / 'ACCEPTANCE_KO.md',
}

_GENERATED = re.compile(
    r'<!-- generated:[a-z0-9-]+ begin -->.*?<!-- generated:[a-z0-9-]+ end -->', re.DOTALL)
_MARKER_KIND = re.compile(r'<!-- generated:[a-z0-9-]+ (begin|end) -->')
_BACKTICKED = re.compile(r'`([^`]+)`')
_STAGE_ANCHOR = 'stage id'

# The hand enumerations each registered route must keep in docs/INTEGRATION.md
# prose. Terminal routes are pinned by their exact bullet lead
# ('- `GET /api/state`:'), which prose mentions like
# '`GET /api/state` returns the loopback token' do not match. Routes with
# children are pinned by the phrase that enumerates the children
# ('`GET /api/terms/{advance_id}/allocation'), and the six agent POSTs by the
# one prose sentence that names them — the generated matrix repeats those
# names and is stripped before the search.
ROUTE_NEEDLES = {
    ('GET', '/api/state'): ('- `GET /api/state`:',),
    ('GET', '/api/scenarios'): ('`GET /api/scenarios` and `/api/scenarios/{id}`',),
    ('GET', '/api/readiness'): ('- `GET /api/readiness`:',),
    ('GET', '/api/decisions'): ('- `GET /api/decisions`:',),
    ('GET', '/api/evidence'): ('- `GET /api/evidence`:',),
    ('GET', '/api/projection'): ('- `GET /api/projection`:',),
    ('GET', '/api/terms'): (
        '`GET /api/terms` and `GET /api/terms/{advance_id}',
        '`GET /api/terms/{advance_id}/allocation',
        '`GET /api/terms/{advance_id}/setoff',
        '`GET /api/terms/portfolio',
        '`GET /api/terms/portfolio/forecast',
    ),
    ('GET', '/api/overlay'): ('- `GET /api/overlay`:',),
    ('GET', '/api/overlay/slices'): ('- `GET /api/overlay/slices`:',),
    ('GET', '/api/portfolio/snapshot'): ('- `GET /api/portfolio/snapshot`:',),
    ('GET', '/api/risk'): ('- `GET /api/risk`:',),
    ('GET', '/api/risk/covenants'): ('- `GET /api/risk/covenants`:',),
    ('GET', '/api/risk/scenarios'): ('`GET /api/risk/scenarios/{id}`',),
    ('GET', '/api/policy'): (
        '`GET /api/policy` and `GET /api/policy/simulation`',
        '`GET /api/policy/shadow`',),
    ('GET', '/api/preview/'): ('`GET /api/preview/{advance_id}',),
    ('GET', '/api/underwrite/'): ('`GET /api/underwrite/{advance_id}',),
    ('GET', '/api/operations/'): ('`GET /api/operations/{operation_id}',),
    ('GET', '/api/export'): ('- `GET /api/export`:',),
    ('GET', '/api/export/manifest'): ('- `GET /api/export/manifest`:',),
    ('GET', '/api/reconciliation'): ('- `GET /api/reconciliation`:',),
    ('GET', '/api/statement'): ('- `GET /api/statement`:',),
    ('GET', '/api/metrics'): ('- `GET /api/metrics`:',),
    ('GET', '/api/health'): ('- `GET /api/health`:',),
    ('POST', '/api/commands'): ('- `POST /api/commands`:',),
    ('POST', '/api/session'): ('- `POST /api/session`:',),
    ('POST', '/api/overlay/commands'): ('- `POST /api/overlay/commands`:',),
    ('POST', '/api/agent/query_grant'): ('`POST /api/agent/query_grant`',),
    ('POST', '/api/agent/query_subject'): ('`POST /api/agent/query_subject`',),
    ('POST', '/api/agent/propose_action'): ('`POST /api/agent/propose_action`',),
    ('POST', '/api/agent/withdraw_proposal'): ('`POST /api/agent/withdraw_proposal`',),
    ('POST', '/api/agent/propose_grant_change'): ('`POST /api/agent/propose_grant_change`',),
    ('POST', '/api/agent/execute'): ('`POST /api/agent/execute`',),
}

# Every file under tests/vectors/ must sit under exactly one key here (an
# exact relative path or a directory prefix ending in '/'), and each key's
# needles must stay in README.md — the artifact path itself plus the --check
# command that pins its bytes.
VECTOR_NEEDLES = {
    'provider_facts.json': ('tests/vectors/provider_facts.json', 'scripts/observation_vectors.py --check'),
    'manifest/': ('tests/vectors/manifest/', 'scripts/manifest_vectors.py --check'),
    'workspace/': ('tests/vectors/workspace/', 'scripts/workspace_vectors.py --check'),
    'http/': ('tests/vectors/http/', 'scripts/http_hostile.py --check'),
    'pack/': ('tests/vectors/pack/', 'scripts/pack_vectors.py --check'),
    'finance_vectors.json': (
        'tests/vectors/finance_vectors.json', 'scripts/finance_vectors.py --check'),
    'closeout_digest.json': (
        'tests/vectors/closeout_digest.json', 'scripts/closeout_digest.py --check'),
    'gate_faults.json': (
        'tests/vectors/gate_faults.json', 'scripts/gate_faults.py --check'),
    'forecast_vectors.json': (
        'tests/vectors/forecast_vectors.json', 'scripts/forecast_vectors.py --check'),
    'risk_scenarios.json': (
        'tests/vectors/risk_scenarios.json', 'scripts/risk_scenario_vectors.py --check'),
    'workspace_crash.json': (
        'tests/vectors/workspace_crash.json', 'tests/crash_matrix.py --check'),
    'fold_fuzz.json': (
        'tests/vectors/fold_fuzz.json', 'scripts/fold_fuzz.py --check'),
    'export-dev.key': ('tests/vectors/export-dev.key',),
    'dev-keyset-active.json': ('tests/vectors/dev-keyset-active.json', 'scripts/manifest_vectors.py --check'),
    'dev-keyset-retired.json': ('tests/vectors/dev-keyset-retired.json', 'scripts/manifest_vectors.py --check'),
}


# Claim artifacts live outside tests/vectors/.
CLAIM_NEEDLES = {
    'tests/lifecycle_claims.json': (
        'tests/lifecycle_claims.json', 'scripts/lifecycle_claims_check.py --execute',
        'e2313ab473ea1b5a7b5b9246a564749188c1c2c8',
        'citation SKIPPED',
    ),
}


class SurfaceError(Exception):
    """A needle registry contradicts the live routes or the vectors tree."""


def strip_generated(text, label='document'):
    """Remove generated blocks: machine-owned claims fenced by their own --check scripts."""
    kinds = _MARKER_KIND.findall(text)
    if len(kinds) % 2 or kinds != ['begin', 'end'] * (len(kinds) // 2):
        raise SurfaceError(f'{label} has unbalanced generated markers')
    return _GENERATED.sub('', text)


def live_routes():
    """Registered (method, prefix) pairs in dispatch order; fails closed on drift."""
    dispatch = [(prefix, children) for prefix, children, _name in GET_DISPATCH]
    mapped = [(prefix, children) for prefix, _permission, children in ROUTE_PERMISSIONS]
    if dispatch != mapped:
        raise SurfaceError('GET_DISPATCH and ROUTE_PERMISSIONS list different routes')
    routes = [('GET', prefix) for prefix, _children in dispatch]
    routes += [('POST', prefix) for prefix, _permission in POST_DISPATCH]
    if set(ROUTE_NEEDLES) != set(routes):
        raise SurfaceError('ROUTE_NEEDLES does not cover exactly the registered routes')
    return routes


def acceptance_stages():
    """REQUIRED_STAGES loaded from scripts/acceptance.py (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location('docs_surface_acceptance', ACCEPTANCE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.REQUIRED_STAGES)


def stage_ids(text):
    """Backticked tokens that follow the 'stage id' anchor, in document order."""
    ids = []
    for line in text.splitlines():
        anchor = line.find(_STAGE_ANCHOR)
        if anchor >= 0:
            ids.extend(_BACKTICKED.findall(line[anchor + len(_STAGE_ANCHOR):]))
    return ids


def _covering_key(relative):
    """The one VECTOR_NEEDLES key that owns a vectors-relative path, or None."""
    keys = [
        key for key in VECTOR_NEEDLES
        if relative == key or (key.endswith('/') and relative.startswith(key))]
    if len(keys) > 1:
        raise SurfaceError(f'tests/vectors/{relative} matches two needle entries')
    return keys[0] if keys else None


def _read_stripped(path, label, findings):
    try:
        return strip_generated(path.read_text(encoding='utf-8'), label)
    except OSError as exc:
        findings.append(f'{label} unreadable: {exc}')
    except SurfaceError as exc:
        findings.append(str(exc))
    return ''


def find_drift(integration=DEFAULT_INTEGRATION, readme=DEFAULT_README,
               handbook=None, acceptance=None, vectors_dir=DEFAULT_VECTORS):
    """Every drift finding, plus counts for the ok line. Registry errors raise."""
    handbook = STAGE_DOCS['docs/OPERATOR_HANDBOOK_KO.md'] if handbook is None else handbook
    acceptance = STAGE_DOCS['docs/ACCEPTANCE_KO.md'] if acceptance is None else acceptance
    routes = live_routes()
    findings = []
    docs = {
        'docs/INTEGRATION.md': _read_stripped(integration, 'docs/INTEGRATION.md', findings),
        'README.md': _read_stripped(readme, 'README.md', findings),
        'docs/OPERATOR_HANDBOOK_KO.md': _read_stripped(
            handbook, 'docs/OPERATOR_HANDBOOK_KO.md', findings),
        'docs/ACCEPTANCE_KO.md': _read_stripped(
            acceptance, 'docs/ACCEPTANCE_KO.md', findings),
    }

    for method, prefix in routes:
        for needle in ROUTE_NEEDLES[(method, prefix)]:
            if needle not in docs['docs/INTEGRATION.md']:
                findings.append(
                    f'docs/INTEGRATION.md drops {method} {prefix}: needle {needle!r} is absent')

    vectors_dir = Path(vectors_dir)
    if not vectors_dir.is_dir():
        findings.append(f'tests/vectors directory is missing: {vectors_dir}')
        files = []
    else:
        files = sorted(
            path.relative_to(vectors_dir).as_posix()
            for path in vectors_dir.rglob('*') if path.is_file())
    owned = set()
    for relative in files:
        key = _covering_key(relative)
        if key is None:
            findings.append(f'tests/vectors/{relative} has no VECTOR_NEEDLES entry')
        else:
            owned.add(key)
    for key in VECTOR_NEEDLES:
        if files and key not in owned:
            findings.append(f'VECTOR_NEEDLES entry {key!r} names no pinned artifact')
        for needle in VECTOR_NEEDLES[key]:
            if needle not in docs['README.md']:
                findings.append(f'README.md drops tests/vectors/{key}: needle {needle!r} is absent')

    for artifact, needles in CLAIM_NEEDLES.items():
        if not (ROOT / artifact).is_file():
            findings.append(f'claim artifact missing: {artifact}')
        for needle in needles:
            if needle not in docs['README.md']:
                findings.append(f'README.md drops {artifact}: needle {needle!r} is absent')

    required = acceptance_stages()
    for label in STAGE_DOCS:
        found = stage_ids(docs[label])
        if not found:
            findings.append(f'{label} has no {_STAGE_ANCHOR!r} stage enumeration')
        elif found != list(required):
            findings.append(
                f'{label} stage ids {found} disagree with scripts/acceptance.py {list(required)}')

    stats = {'routes': len(routes), 'artifacts': len(files), 'stages': len(required)}
    return findings, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--check', action='store_true', required=True,
        help='Compare the registries with the docs. Exit 1 on drift. The only mode.')
    parser.add_argument('--integration', type=Path, default=DEFAULT_INTEGRATION)
    parser.add_argument('--readme', type=Path, default=DEFAULT_README)
    parser.add_argument('--handbook', type=Path, default=STAGE_DOCS['docs/OPERATOR_HANDBOOK_KO.md'])
    parser.add_argument('--acceptance', type=Path, default=STAGE_DOCS['docs/ACCEPTANCE_KO.md'])
    parser.add_argument('--vectors', type=Path, default=DEFAULT_VECTORS)
    args = parser.parse_args(argv)
    try:
        findings, stats = find_drift(
            integration=args.integration, readme=args.readme, handbook=args.handbook,
            acceptance=args.acceptance, vectors_dir=args.vectors)
    except (OSError, SurfaceError) as exc:
        print(f'docs surface failed: {exc}', file=sys.stderr)
        return 1
    if findings:
        print('docs surface drift: ' + '; '.join(findings), file=sys.stderr)
        print('restore the enumeration or update the needle registry', file=sys.stderr)
        return 1
    print(
        f"docs surface ok: {stats['routes']} routes, "
        f"{stats['artifacts']} artifacts, {stats['stages']} stages")
    return 0


if __name__ == '__main__':
    sys.exit(main())
