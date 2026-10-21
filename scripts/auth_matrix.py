#!/usr/bin/env python3
"""Generate the route-by-role authorization matrix and keep the docs in step with it.

The table is SIMULATED and built in-process from the dispatcher
(`capital.server.GET_DISPATCH`, `POST_DISPATCH`, `ASSETS`) and from
`capital.auth` (`ROUTE_PERMISSIONS`, `MATRIX`, `OP_PERMISSIONS`). It crosses
every registered route with organizer, auditor, observer, agent and a caller
with no token, and it pins the expected HTTP status, error code and permission
for each cell. `tests/test_auth_matrix.py` sends every cell to a real loopback
server, so the table is a claim about behavior and not a copy of the code.

Nothing here changes a route or a permission. The role matrix is a synthetic
placeholder (SYNTHETIC_LOCAL_ROLE), not an entitlement policy, and identity and
authentication stay NOT_BOUND.

--check exits 1 when tests/auth_matrix.json, the generated block in
docs/INTEGRATION.md, or the generated block in docs/OPERATOR_HANDBOOK_KO.md
differs from what the code produces now, or when the registries disagree with
each other. --write rewrites all three. Only the text between the generated
markers is replaced in the two documents.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.agent_lane import ACTIVE_GENERATION, ACTIVE_GRANT_ID
from capital.auth import (
    ALL_PERMISSIONS, COMMAND_SUBMIT, DEFAULT_ROLE, MATRIX, OP_ORDER, OP_PERMISSIONS,
    PROVENANCE, ROLES, ROUTE_PERMISSIONS,
)
from capital.server import ASSETS, GET_DISPATCH, POST_DISPATCH
from capital.service import OPS

FORMAT = 'KIX_CAPITAL_AUTH_MATRIX_V1'
NO_TOKEN = 'no-token'
CALLERS = (*ROLES, NO_TOKEN)
INSTANCE = '@instance'  # replaced by the live instance_id when the table is replayed
BOGUS_TOKEN = 'bogus-token'

BEGIN = '<!-- generated:auth-matrix begin -->'
END = '<!-- generated:auth-matrix end -->'
DEFAULT_TABLE = ROOT / 'tests' / 'auth_matrix.json'
DEFAULT_INTEGRATION = ROOT / 'docs' / 'INTEGRATION.md'
DEFAULT_HANDBOOK = ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md'

# Real request paths per GET prefix. Every probe must answer 200 for a caller that
# holds the permission, against the offer seeded as ADVANCE below.
ADVANCE = 'sim-mtx'
OFFER_OPERATION = 'sim-mtx-offer'
GET_PROBES = {
    '/api/state': ['/api/state'],
    '/api/scenarios': ['/api/scenarios', '/api/scenarios/full-after'],
    '/api/readiness': ['/api/readiness'],
    '/api/decisions': ['/api/decisions'],
    '/api/evidence': ['/api/evidence'],
    '/api/projection': ['/api/projection'],
    '/api/terms': [
        '/api/terms',
        f'/api/terms/portfolio?instance_id={INSTANCE}&as_of_day=1',
        f'/api/terms/portfolio/forecast?instance_id={INSTANCE}',
        f'/api/terms/{ADVANCE}?instance_id={INSTANCE}&draw_day=0&as_of_day=1',
        f'/api/terms/{ADVANCE}/allocation?instance_id={INSTANCE}&as_of_day=1&cash=1',
        f'/api/terms/{ADVANCE}/setoff?instance_id={INSTANCE}&as_of_day=1',
    ],
    '/api/overlay': ['/api/overlay'],
    '/api/risk': ['/api/risk'],
    '/api/risk/covenants': ['/api/risk/covenants'],
    '/api/risk/scenarios': ['/api/risk/scenarios', '/api/risk/scenarios/largest-advance-default'],
    '/api/policy': ['/api/policy', '/api/policy/simulation', '/api/policy/shadow'],
    '/api/preview/': [f'/api/preview/{ADVANCE}?instance_id={INSTANCE}'],
    '/api/underwrite/': [f'/api/underwrite/{ADVANCE}?instance_id={INSTANCE}'],
    '/api/operations/': [f'/api/operations/{OFFER_OPERATION}?instance_id={INSTANCE}'],
    '/api/export': ['/api/export'],
    '/api/export/manifest': ['/api/export/manifest'],
    '/api/reconciliation': ['/api/reconciliation'],
    '/api/statement': ['/api/statement'],
    '/api/metrics': ['/api/metrics'],
    '/api/health': ['/api/health'],
}
# `reconcile` on the seeded offer stores one receipt and leaves the machine digest alone.
POST_BODIES = {
    '/api/commands': {
        'instance_id': INSTANCE, 'operation_id': 'sim-mtx-reconcile', 'op': 'reconcile',
        'advance_id': ADVANCE, 'args': {},
    },
    '/api/session': {'role': 'auditor'},
    # Organizer-only. One advance of the simulated clock leaves the F04 digest alone.
    '/api/overlay/commands': {
        'instance_id': INSTANCE, 'operation_id': 'sim-mtx-advance', 'op': 'advance_day',
        'from_sim_day': 0, 'to_sim_day': 1, 'reason': 'auth matrix probe',
    },
    '/api/agent/query_grant': {
        'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 1,
    },
    '/api/agent/query_subject': {
        'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 1,
        'surface': 'capital:offer', 'subject': 'sim-matrix',
    },
    '/api/agent/propose_action': {
        'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 10,
        'proposal_id': 'sim-matrix', 'surface': 'capital:offer', 'amount': 100, 'kind': 'PROPOSE',
    },
    # sim-matrix is proposed by the propose_action cell earlier in table order.
    '/api/agent/withdraw_proposal': {
        'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 10,
        'proposal_id': 'sim-matrix',
    },
    '/api/agent/propose_grant_change': {
        'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 10,
        'proposal_id': 'sim-matrix-change', 'requested': {'note': 'sim-matrix-note'},
    },
    '/api/agent/execute': {'kind': 'EXECUTE'},
}
# What an allowed caller sees after the gate. The agent lane refuses EXECUTE by design.
POST_PASSED = {'/api/agent/execute': {'status': 403, 'error': 'EXECUTE_AUTHORITY_DISABLED'}}
POST_PASSED_NOTES = {
    '/api/agent/execute': 'The gate passes agent:propose_action and the lane then refuses. There is no execute switch.',
}
# Passes the auth gate and is rejected for its arguments before any receipt or journal write.
COMMAND_PROBE_ARGS = {'_probe': 0}
COMMAND_PROBE_ADVANCE = 'sim-mtx-probe'

ASSET_NOTE = 'Static assets are served after the loopback boundary and before authentication. Role and token headers are not read.'

CODE_MEANING = {
    'ROLE_FORBIDDEN': '토큰의 역할에 그 권한이 없다.',
    'LOCAL_TOKEN_REQUIRED': '토큰이 없거나 알 수 없다. 모든 POST는 먼저 토큰을 본다.',
    'ROLE_MISMATCH': '`X-Capital-Role`이 토큰의 역할과 다르다. 헤더로 역할을 바꿀 수 없다.',
    'SESSION_REQUIRED': '토큰 없이 organizer가 아닌 역할을 주장했다. 먼저 `POST /api/session`이 필요하다.',
    'ROLE_UNKNOWN': '`X-Capital-Role`이 알 수 없거나 중복된 역할이다.',
    'NOT_FOUND': '등록되지 않은 (메서드, 경로)다. 기본 거절이다.',
    'EXECUTE_AUTHORITY_DISABLED': 'agent 레인이 EXECUTE를 거절한다. 게이트는 통과했다.',
    'INVALID_ARGUMENTS': '게이트를 통과한 뒤 인자 검사에서 쓰기 전에 거절됐다.',
}


class MatrixError(Exception):
    """The registries disagree. The table is not written from a registry that contradicts itself."""


def _check_registries():
    dispatch = [(prefix, children) for prefix, children, _name in GET_DISPATCH]
    mapped = [(prefix, children) for prefix, _permission, children in ROUTE_PERMISSIONS]
    if dispatch != mapped:
        raise MatrixError('GET_DISPATCH and ROUTE_PERMISSIONS list different routes')
    for prefix, permission, _children in ROUTE_PERMISSIONS:
        if permission not in ALL_PERMISSIONS:
            raise MatrixError(f'{prefix} maps to a permission outside ALL_PERMISSIONS')
    for prefix, permission in POST_DISPATCH:
        if permission not in ALL_PERMISSIONS:
            raise MatrixError(f'{prefix} maps to a permission outside ALL_PERMISSIONS')
    if set(GET_PROBES) != {prefix for prefix, _children in dispatch}:
        raise MatrixError('GET_PROBES does not cover exactly the registered GET routes')
    if set(POST_BODIES) != {prefix for prefix, _permission in POST_DISPATCH}:
        raise MatrixError('POST_BODIES does not cover exactly the registered POST routes')
    if tuple(OP_ORDER) != tuple(OP_PERMISSIONS) or set(OP_ORDER) != set(OPS):
        raise MatrixError('OP_ORDER, OP_PERMISSIONS and CapitalService.OPS list different operations')
    if set(POST_PASSED) - set(POST_BODIES):
        raise MatrixError('POST_PASSED names an unregistered route')


def _principal(caller):
    return DEFAULT_ROLE if caller == NO_TOKEN else caller


def _holds(caller, permission):
    return permission in MATRIX[_principal(caller)]


def _forbidden(caller, permission):
    return {'status': 403, 'error': 'ROLE_FORBIDDEN', 'permission': permission, 'role': _principal(caller)}


def _routes():
    permissions = {(prefix, children): permission for prefix, permission, children in ROUTE_PERMISSIONS}
    routes = []
    for prefix, children, name in GET_DISPATCH:
        routes.append({
            'method': 'GET', 'route': prefix, 'children': children, 'handler': f'_get_{name}',
            'permission': permissions[(prefix, children)], 'probes': list(GET_PROBES[prefix]),
        })
    for prefix, permission in POST_DISPATCH:
        row = {'method': 'POST', 'route': prefix, 'permission': permission, 'body': POST_BODIES[prefix]}
        if prefix in POST_PASSED_NOTES:
            row['note'] = POST_PASSED_NOTES[prefix]
        routes.append(row)
    for path, (_file, kind) in ASSETS.items():
        routes.append({
            'method': 'GET', 'route': path, 'permission': None, 'kind': 'STATIC_ASSET',
            'content_type': kind, 'note': ASSET_NOTE,
        })
    return routes


def _cell(route, caller):
    method, permission = route['method'], route['permission']
    if permission is None:
        return 'PUBLIC', {'status': 200}
    if method == 'POST' and caller == NO_TOKEN:
        return 'DENY', {'status': 403, 'error': 'LOCAL_TOKEN_REQUIRED'}
    if not _holds(caller, permission):
        return 'DENY', _forbidden(caller, permission)
    if method == 'POST' and route['route'] in POST_PASSED:
        return 'ALLOW', dict(POST_PASSED[route['route']])
    return 'ALLOW', {'status': 200}


def _command_cell(op, caller):
    if caller == NO_TOKEN:
        return 'DENY', {'status': 403, 'error': 'LOCAL_TOKEN_REQUIRED'}
    if not _holds(caller, COMMAND_SUBMIT):
        return 'DENY', _forbidden(caller, COMMAND_SUBMIT)
    return 'ALLOW', {'status': 400, 'error': 'INVALID_ARGUMENTS'}


def _edges():
    edges = []

    def add(name, method, path, token, expect, headers=None, body=None):
        edge = {'name': name, 'method': method, 'path': path, 'token': token, 'expect': expect}
        if headers:
            edge['headers'] = headers
        if body is not None:
            edge['body'] = body
        edges.append(edge)

    tokens = (*ROLES, 'none')
    not_found = {'status': 404, 'error': 'NOT_FOUND'}
    no_token = {'status': 403, 'error': 'LOCAL_TOKEN_REQUIRED'}
    for token in tokens:
        add('unregistered GET path', 'GET', '/api/no-such-route', token, not_found)
    for token in tokens:
        add('unregistered POST path', 'POST', '/api/no-such-route', token,
            no_token if token == 'none' else not_found, body={})
    for path in ('/api/projection/extra', '/api/state/', '/api/preview'):
        add('near-miss GET path', 'GET', path, 'organizer', not_found)
    add('near-miss POST path', 'POST', '/api/session/', 'organizer', not_found, body={})
    for prefix, _permission in POST_DISPATCH:
        for token in tokens:
            add('GET on a POST-only route', 'GET', prefix, token, not_found)
    for token in tokens:
        add('POST on a GET-only route', 'POST', '/api/state', token,
            no_token if token == 'none' else not_found, body={})

    def mismatch(role, claimed):
        return {'status': 403, 'error': 'ROLE_MISMATCH', 'role': role, 'claimed': claimed}

    add('token role differs from the claimed role', 'GET', '/api/state', 'organizer', mismatch('organizer', 'auditor'),
        headers={'X-Capital-Role': 'auditor'})
    add('token role differs from the claimed role', 'GET', '/api/state', 'auditor', mismatch('auditor', 'organizer'),
        headers={'X-Capital-Role': 'organizer'})
    add('token role differs from the claimed role', 'GET', '/api/state', 'agent', mismatch('agent', 'organizer'),
        headers={'X-Capital-Role': 'organizer'})
    add('a mismatch is reported before a permission denial', 'GET', '/api/metrics', 'observer',
        mismatch('observer', 'organizer'), headers={'X-Capital-Role': 'organizer'})
    add('token role differs from the claimed role', 'POST', '/api/session', 'organizer',
        mismatch('organizer', 'auditor'), headers={'X-Capital-Role': 'auditor'}, body={'role': 'auditor'})
    add('token role differs from the claimed role', 'POST', '/api/agent/propose_action', 'agent',
        mismatch('agent', 'organizer'), headers={'X-Capital-Role': 'organizer'},
        body=POST_BODIES['/api/agent/propose_action'])

    for claimed in ('auditor', 'observer', 'agent'):
        add('non-organizer role claimed without a token', 'GET', '/api/state', 'none',
            {'status': 403, 'error': 'SESSION_REQUIRED', 'role': claimed}, headers={'X-Capital-Role': claimed})
    add('organizer claimed without a token is the default', 'GET', '/api/state', 'none',
        {'status': 200}, headers={'X-Capital-Role': 'organizer'})
    add('authentication runs before the unregistered-path 404', 'GET', '/api/no-such-route', 'none',
        {'status': 403, 'error': 'SESSION_REQUIRED', 'role': 'auditor'}, headers={'X-Capital-Role': 'auditor'})

    unknown = {'status': 403, 'error': 'ROLE_UNKNOWN'}
    add('unknown role header', 'GET', '/api/state', 'none', unknown, headers={'X-Capital-Role': 'clerk'})
    add('unknown role header', 'GET', '/api/state', 'organizer', unknown, headers={'X-Capital-Role': 'clerk'})
    add('unknown role header', 'GET', '/api/state', 'none', unknown, headers={'X-Capital-Role': 'UNLABELED'})
    add('unknown role header', 'POST', '/api/session', 'organizer', unknown,
        headers={'X-Capital-Role': 'clerk'}, body={'role': 'auditor'})

    add('unknown token', 'GET', '/api/state', 'bogus', no_token)
    add('unknown token', 'GET', '/api/no-such-route', 'bogus', no_token)
    add('unknown token', 'POST', '/api/session', 'bogus', no_token, body={'role': 'auditor'})
    add('unknown token', 'POST', '/api/commands', 'bogus', no_token, body=POST_BODIES['/api/commands'])

    for path in ASSETS:
        add('static asset ignores token and role headers', 'GET', path, 'bogus', {'status': 200})
        add('static asset ignores token and role headers', 'GET', path, 'none', {'status': 200},
            headers={'X-Capital-Role': 'clerk'})
    return edges


def build():
    """The whole table as plain data. Deterministic: no instance id, token or clock."""
    _check_registries()
    routes = _routes()
    cells = []
    for route in routes:
        for caller in CALLERS:
            outcome, expect = _cell(route, caller)
            cells.append({
                'method': route['method'], 'route': route['route'], 'caller': caller,
                'outcome': outcome, 'expect': expect,
            })
    command_cells = []
    for op in OP_ORDER:
        for caller in CALLERS:
            outcome, expect = _command_cell(op, caller)
            command_cells.append({'op': op, 'caller': caller, 'outcome': outcome, 'expect': expect})
    return {
        'format': FORMAT,
        'label': 'SIMULATED',
        'provenance': PROVENANCE,
        'identity': 'NOT_BOUND',
        'authentication': 'NOT_BOUND',
        'note': 'Synthetic placeholder roles, not an entitlement policy. Regenerate with python3 scripts/auth_matrix.py --write.',
        'callers': list(CALLERS),
        'no_token_principal': DEFAULT_ROLE,
        'role_permissions': {
            role: [permission for permission in ALL_PERMISSIONS if permission in MATRIX[role]]
            for role in ROLES
        },
        'routes': routes,
        'cells': cells,
        'command_permissions': {
            'submit_gate': COMMAND_SUBMIT,
            'unmapped_op_permission': COMMAND_SUBMIT,
            'ops': {
                op: {
                    'permission': OP_PERMISSIONS[op],
                    'roles': [role for role in ROLES if OP_PERMISSIONS[op] in MATRIX[role]],
                }
                for op in OP_ORDER
            },
            'probe': {'advance_id': COMMAND_PROBE_ADVANCE, 'args': COMMAND_PROBE_ARGS},
        },
        'command_cells': command_cells,
        'edges': _edges(),
    }


def dump(table) -> str:
    """Insertion order is deterministic, and it keeps roles and ops in registry order."""
    return json.dumps(table, indent=2, ensure_ascii=True) + '\n'


def label(expect) -> str:
    return f"{expect['status']} {expect['error']}" if 'error' in expect else str(expect['status'])


def _route_text(route):
    path = route['route']
    if route.get('children'):
        return path + '…' if path.endswith('/') else path + '[/…]'
    return path


def _headers_text(edge):
    headers = ', '.join(f"{name}: {value}" for name, value in sorted(edge.get('headers', {}).items()))
    return f' ({headers})' if headers else ''


def _edge_rows(edges):
    """Rows of (case, request, results). Requests that share case, headers and results share a row."""
    per_request = {}
    for edge in edges:
        key = (edge['name'], edge['method'], edge['path'], _headers_text(edge))
        per_request.setdefault(key, {}).setdefault(label(edge['expect']), []).append(edge['token'])
    rows = {}
    for (name, method, path, headers), results in per_request.items():
        text = '; '.join(f"{_tokens_text(tokens)}: {result}" for result, tokens in results.items())
        rows.setdefault((name, headers, text), []).append(f'`{method} {path}`')
    return [(name, ', '.join(paths) + headers, text) for (name, headers, text), paths in rows.items()]


def _tokens_text(tokens):
    names = {'none': NO_TOKEN, 'bogus': BOGUS_TOKEN}
    distinct = list(dict.fromkeys(names.get(token, token) for token in tokens))
    return 'every caller' if set(distinct) >= set(CALLERS) else ', '.join(distinct)


def render_integration(table=None) -> str:
    table = build() if table is None else table
    routes = {(route['method'], route['route']): route for route in table['routes']}
    cells = {(cell['method'], cell['route'], cell['caller']): cell for cell in table['cells']}
    callers = table['callers']
    lines = [
        f"Generated from `tests/auth_matrix.json` (`{table['format']}`, label `{table['label']}`, role provenance `{table['provenance']}`, identity and authentication `NOT_BOUND`). Do not edit this block by hand: `python3 scripts/auth_matrix.py --write` rewrites it, and `python3 -m unittest tests.test_auth_matrix` sends every cell below to a real loopback server and fails when the table, this block, the dispatcher or `ROUTE_PERMISSIONS` drift apart.",
        '',
        'Each cell is the HTTP result for that caller and route. A bare `200` means the gate passed. `no-token` sends no `X-Capital-Token`: a GET is the default organizer, and every POST is `403 LOCAL_TOKEN_REQUIRED` because the loopback boundary checks the token first. A static asset (`permission` `none`) is served before authentication. Denied cells carry the permission and role in the body.',
        '',
        '| Method | Route | Permission | ' + ' | '.join(callers) + ' |',
        '|---|---|---|' + '---|' * len(callers),
    ]
    for (method, path), route in routes.items():
        permission = route['permission']
        shown = f"`{permission}`" if permission else 'none'
        row = [label(cells[(method, path, caller)]['expect']) for caller in callers]
        lines.append(f"| {method} | `{_route_text(route)}` | {shown} | " + ' | '.join(row) + ' |')
    commands = table['command_permissions']
    lines += [
        '',
        f"`POST /api/commands` passes the route gate with `{commands['submit_gate']}`. The service then requires `command:{{op}}` for the named operation. An `op` outside this list needs only `{commands['unmapped_op_permission']}` and is then `UNSUPPORTED_OPERATION`.",
        '',
        '| op | Permission | Roles that hold it |',
        '|---|---|---|',
    ]
    for op, row in commands['ops'].items():
        lines.append(f"| `{op}` | `{row['permission']}` | {', '.join(row['roles'])} |")
    lines += [
        '',
        'Outside the route-by-role cells the table also pins these cases. Each lists what a real server returned.',
        '',
        '| Case | Request | Result |',
        '|---|---|---|',
    ]
    for name, request, results in _edge_rows(table['edges']):
        lines.append(f'| {name} | {request} | {results} |')
    return '\n'.join(lines) + '\n'


def render_handbook(table=None) -> str:
    table = build() if table is None else table
    holds = table['role_permissions']
    by_permission = {}
    for route in table['routes']:
        if route['permission'] is not None:
            by_permission.setdefault(route['permission'], []).append(f"`{route['method']} {_route_text(route)}`")
    for op, row in table['command_permissions']['ops'].items():
        by_permission.setdefault(row['permission'], []).append(f'`POST /api/commands` (op `{op}`)')
    post_permissions = {route['permission'] for route in table['routes'] if route['method'] == 'POST'}
    post_permissions |= {row['permission'] for row in table['command_permissions']['ops'].values()}
    roles = list(holds)
    lines = [
        f"이 블록은 `tests/auth_matrix.json`(`{table['format']}`)에서 `python3 scripts/auth_matrix.py --write`가 만든다. 손으로 고치지 않는다. 라벨은 `{table['label']}`이고 역할 출처는 `{table['provenance']}`다. 신원과 인증은 `NOT_BOUND`이며 이 표는 권한 정책이 아니라 합성 자리표시자다. `python3 -m unittest tests.test_auth_matrix`가 모든 칸을 루프백 서버에 실제로 보내 확인한다.",
        '',
        f"`허용`은 그 역할이 권한을 가진다는 뜻이고 `거절`은 `403 ROLE_FORBIDDEN`이다. `no-token`은 `X-Capital-Token`이 없는 호출자다. GET은 기본 `{table['no_token_principal']}`로 처리돼 그 열과 같고, POST는 어느 권한이든 `403 LOCAL_TOKEN_REQUIRED`(`토큰 필요`)다. 정적 파일(`/`, `/app.js`, `/style.css`)은 인증 전에 응답해 권한이 없다.",
        '',
        '| 권한 | ' + ' | '.join(roles) + f" | {NO_TOKEN} | 경로 |",
        '|---|' + '---|' * (len(roles) + 2),
    ]
    for permission in ALL_PERMISSIONS:
        row = ['허용' if permission in holds[role] else '거절' for role in roles]
        if permission in post_permissions:
            no_token = '토큰 필요'
        else:
            no_token = '허용' if permission in holds[table['no_token_principal']] else '거절'
        paths = ', '.join(by_permission.get(permission, []))
        lines.append(f"| `{permission}` | " + ' | '.join(row) + f" | {no_token} | {paths} |")
    lines += [
        '',
        '권한 표 밖에서 표가 고정한 오류 코드는 다음과 같다.',
        '',
        '| 코드 | 뜻 |',
        '|---|---|',
    ]
    seen = []
    for cell in (*table['cells'], *table['command_cells'], *table['edges']):
        code = cell['expect'].get('error')
        if code and code not in seen:
            seen.append(code)
    for code in seen:
        lines.append(f'| `{code}` | {CODE_MEANING[code]} |')
    return '\n'.join(lines) + '\n'


def extract_generated(document: str) -> str:
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise ValueError('generated markers missing or repeated')
    _pre, rest = document.split(BEGIN, 1)
    inner, _post = rest.split(END, 1)
    if inner.startswith('\n'):
        inner = inner[1:]
    return inner


def replace_generated(document: str, block: str) -> str:
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise ValueError('generated markers missing or repeated')
    pre, rest = document.split(BEGIN, 1)
    _inner, post = rest.split(END, 1)
    if not block.endswith('\n'):
        block += '\n'
    return f'{pre}{BEGIN}\n{block}{END}{post}'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--table', type=Path, default=DEFAULT_TABLE)
    parser.add_argument('--integration', type=Path, default=DEFAULT_INTEGRATION)
    parser.add_argument('--handbook', type=Path, default=DEFAULT_HANDBOOK)
    args = parser.parse_args(argv)
    try:
        table = build()
        text = dump(table)
        documents = (
            (args.integration, render_integration(table)),
            (args.handbook, render_handbook(table)),
        )
        if args.write:
            args.table.write_text(text, encoding='utf-8')
            for path, block in documents:
                path.write_text(replace_generated(path.read_text(encoding='utf-8'), block), encoding='utf-8')
            return 0
        drift = []
        if not args.table.is_file() or args.table.read_text(encoding='utf-8') != text:
            drift.append(str(args.table))
        for path, block in documents:
            if extract_generated(path.read_text(encoding='utf-8')) != block:
                drift.append(str(path))
        if drift:
            print('auth matrix drift: ' + ', '.join(drift), file=sys.stderr)
            print('run python3 scripts/auth_matrix.py --write', file=sys.stderr)
            return 1
    except (OSError, ValueError, MatrixError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
