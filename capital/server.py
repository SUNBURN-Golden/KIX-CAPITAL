"""Loopback-only same-origin local simulation API, without external integrations."""
from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from capital import __version__
from capital.auth import (
    COMMAND_SUBMIT, DEFAULT_ROLE, PROVENANCE, ROLES, SESSION_BIND, LocalRoleAuthorizer,
    path_matches, require, route_permission,
)
from capital.resources import read_static
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, UnavailableWorkspace, WorkspaceError

# Handler name is the third field. Permissions stay in auth.ROUTE_PERMISSIONS.
# The auth test fails if these two registries diverge. Unlisted paths are 404.
GET_DISPATCH = (
    ('/api/state', False, 'state'),
    ('/api/scenarios', True, 'scenarios'),
    ('/api/readiness', False, 'readiness'),
    ('/api/evidence', False, 'evidence'),
    ('/api/projection', False, 'projection'),
    ('/api/preview/', True, 'preview'),
    ('/api/operations/', True, 'operation'),
    ('/api/export', False, 'export'),
    ('/api/reconciliation', False, 'reconciliation'),
)
POST_DISPATCH = (
    ('/api/commands', COMMAND_SUBMIT),
    ('/api/session', SESSION_BIND),
)
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def projection_mode(query):
    values = parse_qs(query, keep_blank_values=True).get('mode')
    if values is None:
        return None
    if values == ['simulation']:
        return 'simulation'
    return values[0] if len(values) == 1 else 'REJECTED'


class CapitalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def server_close(self):
        try:
            super().server_close()
        finally:
            storage = getattr(self, 'storage', None)
            self.storage = None
            if storage is not None:
                storage.close()


def make_server(port=8765, authorizer=None, workspace=None):
    authorizer = authorizer or LocalRoleAuthorizer()
    storage = None
    if workspace is not None:
        try:
            storage = FileWorkspace.open(workspace)
        except WorkspaceError as exc:
            storage = UnavailableWorkspace(workspace, exc.code)
    try:
        service = CapitalService(storage, authorizer=authorizer)
    except Exception:
        if storage is not None:
            storage.close()
        raise
    if hasattr(authorizer, 'token_for') and authorizer.token_for(DEFAULT_ROLE):
        bootstrap_token = authorizer.token_for(DEFAULT_ROLE)
    else:
        bootstrap_token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass  # no payloads, financial labels or tokens logged

        def reply(self, status, value, content_type='application/json; charset=utf-8'):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # receipt remains queryable; never retry a command

        def fail(self, exc):
            self.reply(exc.status, {'error': exc.code, **(exc.detail or {})})

        def boundary(self, mutate=False):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get_all('Host') != [host]:
                raise ApiError('LOOPBACK_HOST_REQUIRED', 403)
            origins = self.headers.get_all('Origin', [])
            if origins and origins != [f'http://{host}']:
                raise ApiError('ORIGIN_REJECTED', 403)
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                raise ApiError('CROSS_SITE_REJECTED', 403)
            if mutate:
                tokens = self.headers.get_all('X-Capital-Token')
                if not tokens or len(tokens) != 1 or not self.token_known(tokens[0]):
                    raise ApiError('LOCAL_TOKEN_REQUIRED', 403)
                if self.headers.get('Content-Type') != 'application/json':
                    raise ApiError('JSON_REQUIRED', 415)

        def token_known(self, value):
            if hasattr(authorizer, 'role_for_token'):
                return authorizer.role_for_token(value) is not None
            return value == bootstrap_token

        def local_token(self, principal):
            if hasattr(authorizer, 'token_for'):
                issued = authorizer.token_for(principal.role)
                if issued:
                    return issued
            return bootstrap_token

        def principal(self):
            return authorizer.authenticate(self.headers)

        def dispatch_get(self, route, principal):
            path = route.path
            for prefix, children, name in GET_DISPATCH:
                if path_matches(prefix, children, path):
                    return getattr(self, f'_get_{name}')(route, principal)
            raise ApiError('NOT_FOUND', 404)

        def _get_state(self, route, principal):
            return self.reply(200, {**service.snapshot(role=principal.role), 'local_token': self.local_token(principal)})

        def _get_evidence(self, route, principal):
            return self.reply(200, service.evidence())

        def _get_projection(self, route, principal):
            return self.reply(200, service.projection(projection_mode(route.query)))

        def _get_readiness(self, route, principal):
            return self.reply(200, service.readiness())

        def _get_scenarios(self, route, principal):
            path = route.path
            if path == '/api/scenarios':
                return self.reply(200, service.scenarios())
            return self.reply(200, service.scenarios(path.rsplit('/', 1)[-1]))

        def _get_preview(self, route, principal):
            instance = parse_qs(route.query).get('instance_id', [''])[0]
            return self.reply(200, service.preview_draw(route.path.rsplit('/', 1)[-1], instance))

        def _get_export(self, route, principal):
            return self.reply(200, service.export())

        def _get_reconciliation(self, route, principal):
            return self.reply(200, service.reconciliation())

        def _get_operation(self, route, principal):
            instance = parse_qs(route.query).get('instance_id', [''])[0]
            return self.reply(200, service.operation(route.path.rsplit('/', 1)[-1], instance))

        def read_json(self):
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):
                raise ApiError('INVALID_LENGTH')
            length = int(lengths[0])
            if not 0 < length <= 8192:
                raise ApiError('BODY_TOO_LARGE', 413)
            self.connection.settimeout(3)
            try:
                raw = self.rfile.read(length)
                return json.loads(raw, object_pairs_hook=strict_object,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeDecodeError, TimeoutError, RecursionError):
                raise ApiError('INVALID_JSON')

        def open_session(self, body):
            if type(body) is not dict or set(body) != {'role'} or type(body['role']) is not str:
                raise ApiError('INVALID_SESSION')
            role = body['role']
            if role not in ROLES:
                raise ApiError('ROLE_UNKNOWN', 403)
            if not hasattr(authorizer, 'bind_role'):
                raise ApiError('NOT_BOUND', 400)
            issued = authorizer.bind_role(role)
            self.reply(200, {
                'role': role,
                'local_token': issued,
                'role_provenance': PROVENANCE,
                'mode': 'LOCAL_SYNTHETIC_ROLES',
                'identity': 'NOT_BOUND',
                'authentication': 'NOT_BOUND',
                'idp': 'NOT_BOUND',
                'kyc': 'NOT_BOUND',
                'agent_grant': 'NOT_BOUND',
                'action_permit': 'NOT_BOUND',
            })

        def do_GET(self):
            try:
                self.boundary()
                route = urlsplit(self.path)
                if route.path in ASSETS:
                    name, kind = ASSETS[route.path]
                    return self.reply(200, read_static(name), kind)
                principal = self.principal()
                permission = route_permission(route.path)
                if permission is None:
                    raise ApiError('NOT_FOUND', 404)
                require(authorizer, principal, permission)
                self.dispatch_get(route, principal)
            except ApiError as exc:
                self.fail(exc)

        def do_POST(self):
            try:
                self.boundary(mutate=True)
                principal = self.principal()
                path = urlsplit(self.path).path
                permission = None
                for prefix, required in POST_DISPATCH:
                    if path == prefix:
                        permission = required
                        break
                if permission is None:
                    raise ApiError('NOT_FOUND', 404)
                require(authorizer, principal, permission)
                body = self.read_json()
                if path == '/api/session':
                    self.open_session(body)
                elif path == '/api/commands':
                    self.reply(200, service.execute(body, role=principal.role))
                else:
                    raise ApiError('NOT_FOUND', 404)
            except ApiError as exc:
                self.fail(exc)

    try:
        server = CapitalHTTPServer(('127.0.0.1', port), Handler)
    except Exception:
        if storage is not None:
            storage.close()
        raise
    server.service = service
    server.authorizer = authorizer
    server.storage = storage
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--workspace', default=None,
                        help='Opt-in local JSON workspace directory. Default is process memory. Not stage5 durable transactions.')
    parser.add_argument('--version', action='version', version=f'kix-capital {__version__}')
    args = parser.parse_args()
    with make_server(args.port, workspace=args.workspace) as server:
        print(f'KIX Capital simulation: http://127.0.0.1:{server.server_port}', flush=True)
        view = server.service.workspace_view()
        if view['kind'] == 'LOCAL_FILE_WORKSPACE':
            print(f"workspace {view['status']} LOCAL_FILE_WORKSPACE {view['path']}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
