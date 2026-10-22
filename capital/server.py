"""Loopback-only same-origin local simulation API, without external integrations."""
from __future__ import annotations

import argparse
import json
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from capital import __version__
from capital.auth import (
    AGENT_PROPOSE, AGENT_PROPOSE_CHANGE, AGENT_QUERY, AGENT_QUERY_SUBJECT, AGENT_WITHDRAW,
    COMMAND_SUBMIT, DEFAULT_ROLE, OVERLAY_COMMAND, PROVENANCE, ROLES,
    SESSION_BIND, LocalRoleAuthorizer, path_matches, require, route_permission,
)
from capital.observability import EVENT_LOG_MAX_BYTES, Observability
from capital.resources import read_static
from capital.export import DevHmacSigner, ExportError, SignerConfigError
from capital.keyset import build_signer
from capital.service import ApiError, CapitalService
from capital.policy import DecisionNoteSettlementPolicy
from capital.terms import DecisionNoteTermsPolicy
from capital.store import FileWorkspace, UnavailableWorkspace, WorkspaceError

# Handler name is the third field. Permissions stay in auth.ROUTE_PERMISSIONS.
# The auth test fails if these two registries diverge. Unlisted paths are 404.
GET_DISPATCH = (
    ('/api/state', False, 'state'),
    ('/api/scenarios', True, 'scenarios'),
    ('/api/readiness', False, 'readiness'),
    ('/api/decisions', False, 'decisions'),
    ('/api/evidence', False, 'evidence'),
    ('/api/projection', False, 'projection'),
    ('/api/terms', True, 'terms'),
    ('/api/overlay', False, 'overlay'),
    ('/api/portfolio/snapshot', False, 'portfolio_snapshot'),
    ('/api/risk', False, 'risk'),
    ('/api/risk/covenants', False, 'covenants'),
    ('/api/policy', True, 'policy'),
    ('/api/preview/', True, 'preview'),
    ('/api/underwrite/', True, 'underwrite'),
    ('/api/operations/', True, 'operation'),
    ('/api/export', False, 'export'),
    ('/api/export/manifest', False, 'export_manifest'),
    ('/api/reconciliation', False, 'reconciliation'),
    ('/api/statement', False, 'statement'),
    ('/api/metrics', False, 'metrics'),
    ('/api/health', False, 'health'),
)
POST_DISPATCH = (
    ('/api/commands', COMMAND_SUBMIT),
    ('/api/session', SESSION_BIND),
    ('/api/overlay/commands', OVERLAY_COMMAND),
    ('/api/agent/query_grant', AGENT_QUERY),
    ('/api/agent/query_subject', AGENT_QUERY_SUBJECT),
    ('/api/agent/propose_action', AGENT_PROPOSE),
    ('/api/agent/withdraw_proposal', AGENT_WITHDRAW),
    ('/api/agent/propose_grant_change', AGENT_PROPOSE_CHANGE),
    ('/api/agent/execute', AGENT_PROPOSE),
)
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


def route_labels():
    """Closed HTTP label set. Unlisted paths collapse to `other` in route_label."""
    return tuple(prefix for prefix, _children, _name in GET_DISPATCH) + tuple(
        prefix for prefix, _permission in POST_DISPATCH)


def route_label(path):
    """Map a path to one dispatch label. Unknown paths are `other`, not the raw path."""
    for prefix, children, _name in GET_DISPATCH:
        if path_matches(prefix, children, path):
            return prefix
    for prefix, _permission in POST_DISPATCH:
        if path == prefix:
            return prefix
    return 'other'


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
            try:
                storage = getattr(self, 'storage', None)
                self.storage = None
                if storage is not None:
                    storage.close()
            finally:
                try:
                    producer = getattr(self, 'producer', None)
                    self.producer = None
                    close = getattr(producer, 'close', None)
                    if callable(close):
                        close()
                finally:
                    observability = getattr(self, 'observability', None)
                    self.observability = None
                    if observability is not None:
                        observability.close()


_DAY = re.compile(r'0|[1-9]\d{0,5}\Z')
_CASH = re.compile(r'0|[1-9]\d{0,12}\Z')
_AMOUNT = re.compile(r'[1-9]\d{0,12}\Z')


def query_day(query, name, required):
    values = parse_qs(query, keep_blank_values=True).get(name)
    if not values:
        if required:
            raise ApiError('INVALID_ARGUMENTS')
        return None
    if len(values) != 1 or _DAY.fullmatch(values[0]) is None:
        raise ApiError('INVALID_ARGUMENTS')
    return int(values[0])


def query_amount(query):
    values = parse_qs(query, keep_blank_values=True).get('amount')
    if not values:
        return None
    if len(values) != 1 or _AMOUNT.fullmatch(values[0]) is None:
        raise ApiError('INVALID_ARGUMENTS')
    return int(values[0])


def query_cash(query):
    values = parse_qs(query, keep_blank_values=True).get('cash')
    if not values or len(values) != 1 or _CASH.fullmatch(values[0]) is None:
        raise ApiError('INVALID_ARGUMENTS')
    return int(values[0])


def make_server(port=8765, authorizer=None, workspace=None, signer=None, terms=None, policy=None, underwriting=None, *, setoff=None, producer=None, event_log=None, decisions=None):
    authorizer = authorizer or LocalRoleAuthorizer()
    observability = Observability(event_log, routes=route_labels())
    storage = None
    if workspace is not None:
        try:
            storage = FileWorkspace.open(workspace)
        except WorkspaceError as exc:
            storage = UnavailableWorkspace(workspace, exc.code)
    try:
        service = CapitalService(
            storage, authorizer=authorizer, signer=signer, terms=terms, policy=policy,
            underwriting=underwriting, setoff=setoff, producer=producer, observability=observability, decisions=decisions)
    except Exception:
        observability.close()
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

        def _get_decisions(self, route, principal):
            return self.reply(200, service.decisions())

        def _get_scenarios(self, route, principal):
            path = route.path
            if path == '/api/scenarios':
                return self.reply(200, service.scenarios())
            return self.reply(200, service.scenarios(path.rsplit('/', 1)[-1]))

        def _get_policy(self, route, principal):
            if route.path == '/api/policy':
                return self.reply(200, service.policy_status())
            if route.path == '/api/policy/simulation':
                return self.reply(200, service.policy_simulation())
            if route.path == '/api/policy/shadow':
                return self.reply(200, service.policy_shadow())
            raise ApiError('NOT_FOUND', 404)

        def _get_terms(self, route, principal):
            if route.path == '/api/terms':
                return self.reply(200, service.terms_status())
            if route.path == '/api/terms/portfolio':
                instance = parse_qs(route.query).get('instance_id', [''])[0]
                draw_day = query_day(route.query, 'draw_day', False)
                as_of_day = query_day(route.query, 'as_of_day', True)
                expected = query_day(route.query, 'expected_settlement_cash_day', False)
                return self.reply(200, service.terms_portfolio(
                    instance, draw_day=draw_day, as_of_day=as_of_day,
                    expected_settlement_cash_day=expected))
            if route.path == '/api/terms/portfolio/forecast':
                # Only the documented parameters are accepted on this route.
                keys = set(parse_qs(route.query, keep_blank_values=True))
                if keys - {'instance_id', 'expected_settlement_cash_day'}:
                    raise ApiError('INVALID_ARGUMENTS')
                instance = parse_qs(route.query).get('instance_id', [''])[0]
                expected = query_day(route.query, 'expected_settlement_cash_day', False)
                return self.reply(200, service.forecast(
                    instance, expected_settlement_cash_day=expected))
            if route.path.endswith('/setoff'):
                advance_id = route.path[len('/api/terms/'):-len('/setoff')].rstrip('/')
                instance = parse_qs(route.query).get('instance_id', [''])[0]
                draw_day = query_day(route.query, 'draw_day', False)
                as_of_day = query_day(route.query, 'as_of_day', True)
                expected = query_day(route.query, 'expected_settlement_cash_day', False)
                return self.reply(200, service.case_setoff(
                    advance_id, instance, draw_day=draw_day or 0, as_of_day=as_of_day,
                    expected_settlement_cash_day=expected))
            if route.path.endswith('/allocation'):
                advance_id = route.path[len('/api/terms/'):-len('/allocation')].rstrip('/')
                instance = parse_qs(route.query).get('instance_id', [''])[0]
                draw_day = query_day(route.query, 'draw_day', False)
                as_of_day = query_day(route.query, 'as_of_day', True)
                cash = query_cash(route.query)
                expected = query_day(route.query, 'expected_settlement_cash_day', False)
                return self.reply(200, service.case_allocation(
                    advance_id, instance, draw_day=draw_day or 0, as_of_day=as_of_day,
                    cash=cash, expected_settlement_cash_day=expected))
            advance_id = route.path.rsplit('/', 1)[-1]
            instance = parse_qs(route.query).get('instance_id', [''])[0]
            draw_day = query_day(route.query, 'draw_day', True)
            as_of_day = query_day(route.query, 'as_of_day', True)
            expected = query_day(route.query, 'expected_settlement_cash_day', False)
            return self.reply(200, service.case_terms(
                advance_id, instance, draw_day, as_of_day, expected))

        def _get_overlay(self, route, principal):
            values = parse_qs(route.query, keep_blank_values=True).get('operation_id')
            lookup = values[0] if values and len(values) == 1 else None
            return self.reply(200, service.overlay_state(lookup))

        def _get_risk(self, route, principal):
            return self.reply(200, service.risk())

        def _get_portfolio_snapshot(self, route, principal):
            params = parse_qs(route.query, keep_blank_values=True)
            if set(params) - {'instance_id'} or len(params.get('instance_id', [])) > 1:
                raise ApiError('INVALID_ARGUMENTS')
            instance = params.get('instance_id', [''])[0]
            return self.reply(200, service.portfolio_snapshot(instance))

        def _get_covenants(self, route, principal):
            return self.reply(200, service.covenants())

        def _get_preview(self, route, principal):
            instance = parse_qs(route.query).get('instance_id', [''])[0]
            return self.reply(200, service.preview_draw(route.path.rsplit('/', 1)[-1], instance))

        def _get_underwrite(self, route, principal):
            instance = parse_qs(route.query).get('instance_id', [''])[0]
            sim_day = query_day(route.query, 'sim_day', False)
            amount = query_amount(route.query)
            return self.reply(200, service.underwrite(
                route.path.rsplit('/', 1)[-1], instance, principal.role,
                sim_day=sim_day or 0, amount=amount))

        def _get_export(self, route, principal):
            return self.reply(200, service.export())

        def _get_export_manifest(self, route, principal):
            return self.reply(200, service.export_manifest())

        def _get_reconciliation(self, route, principal):
            values = parse_qs(route.query, keep_blank_values=True).get('operation_id')
            probe = values[0] if values and len(values) == 1 else None
            return self.reply(200, service.reconciliation(probe, projection_mode(route.query)))

        def _get_statement(self, route, principal):
            return self.reply(200, service.statement())

        def _get_metrics(self, route, principal):
            return self.reply(200, service.metrics())

        def _get_health(self, route, principal):
            return self.reply(200, service.health())

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

        def _observe(self, started, path, status, code, operation_id):
            # After the reply, so a metrics read does not count itself.
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            try:
                service.observability.record_http(
                    route_label(path), status, code, operation_id, elapsed_ms)
            except Exception:
                return

        def do_GET(self):
            started = time.perf_counter()
            status = 500
            code = None
            operation_id = None
            path = ''
            try:
                path = urlsplit(self.path).path
                if path.startswith('/api/operations/'):
                    operation_id = path[len('/api/operations/'):]
                self.boundary()
                route = urlsplit(self.path)
                if route.path in ASSETS:
                    name, kind = ASSETS[route.path]
                    self.reply(200, read_static(name), kind)
                    status = 200
                    return
                principal = self.principal()
                permission = route_permission(route.path)
                if permission is None:
                    raise ApiError('NOT_FOUND', 404)
                require(authorizer, principal, permission)
                self.dispatch_get(route, principal)
                status = 200
            except ApiError as exc:
                status = exc.status
                code = exc.code
                self.fail(exc)
            finally:
                self._observe(started, path, status, code, operation_id)

        def do_POST(self):
            started = time.perf_counter()
            status = 500
            code = None
            operation_id = None
            path = ''
            try:
                path = urlsplit(self.path).path
                self.boundary(mutate=True)
                principal = self.principal()
                permission = None
                for prefix, required in POST_DISPATCH:
                    if path == prefix:
                        permission = required
                        break
                if permission is None:
                    raise ApiError('NOT_FOUND', 404)
                require(authorizer, principal, permission)
                body = self.read_json()
                if path == '/api/commands' and type(body) is dict and type(body.get('operation_id')) is str:
                    operation_id = body.get('operation_id')
                if path == '/api/session':
                    self.open_session(body)
                elif path == '/api/commands':
                    self.reply(200, service.execute(body, role=principal.role))
                elif path == '/api/overlay/commands':
                    if type(body) is dict and type(body.get('operation_id')) is str:
                        operation_id = body.get('operation_id')
                    self.reply(200, service.overlay_command(body, role=principal.role))
                elif path == '/api/agent/query_grant':
                    self.reply(200, service.agent_query(body, role=principal.role))
                elif path == '/api/agent/query_subject':
                    self.reply(200, service.agent_query_subject(body, role=principal.role))
                elif path == '/api/agent/propose_action':
                    self.reply(200, service.agent_propose(body, role=principal.role))
                elif path == '/api/agent/withdraw_proposal':
                    self.reply(200, service.agent_withdraw_proposal(body, role=principal.role))
                elif path == '/api/agent/propose_grant_change':
                    self.reply(200, service.agent_propose_grant_change(body, role=principal.role))
                elif path == '/api/agent/execute':
                    self.reply(200, service.agent_execute(body, role=principal.role))
                else:
                    raise ApiError('NOT_FOUND', 404)
                status = 200
            except ApiError as exc:
                status = exc.status
                code = exc.code
                self.fail(exc)
            finally:
                self._observe(started, path, status, code, operation_id)

    try:
        server = CapitalHTTPServer(('127.0.0.1', port), Handler)
    except Exception:
        observability.close()
        if storage is not None:
            storage.close()
        close = getattr(service.producer, 'close', None)
        if callable(close):
            close()
        raise
    server.service = service
    server.authorizer = authorizer
    server.storage = storage
    server.producer = service.producer
    server.observability = observability
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--workspace', default=None,
                        help='Opt-in local JSON workspace directory. Default is process memory. Not stage5 durable transactions.')
    parser.add_argument('--terms-note', default=None,
                        help='Decision note for the simulated terms overlay. A missing note reports terms not bound. Not bundled in the zipapp.')
    parser.add_argument('--policy-note', default=None,
                        help='Decision note for the simulated policy application. A missing note reports policy not bound. Not bundled in the zipapp.')
    signing = parser.add_mutually_exclusive_group()
    signing.add_argument('--dev-hmac', action='store_true',
                        help='Opt-in DEV_ONLY HMAC integrity key at WORKSPACE/export-dev.key (mode 0600). Integrity only, not authentication. Not an external key.')
    signing.add_argument('--dev-keyset', action='store_true',
                         help='Opt-in DEV_ONLY keyset at WORKSPACE/export-dev-keyset.json (0600). Integrity only; stage7 NOT_BOUND.')
    parser.add_argument('--producer', choices=('pinned', 'gate-fake'), default='pinned',
                        help='Opt-in producer. pinned is the in-process FSM (default). '
                             'gate-fake starts LOCAL_FAKE_GATE on 127.0.0.1. Not SEMANTIC_CONFORMANCE. CAP-16 stays NOT_BOUND.')
    parser.add_argument('--event-log', default=None,
                        help='Opt-in size-bounded JSONL event log. An unwritable path does not fail commands. '
                             'Not an exporter, a trace, or a network sink.')
    parser.add_argument('--version', action='version', version=f'kix-capital {__version__}')
    args = parser.parse_args()
    try:
        signer = build_signer(args.workspace, args.dev_hmac, args.dev_keyset)
    except (SignerConfigError, ExportError) as exc:
        parser.error(exc.code)
    terms = DecisionNoteTermsPolicy(args.terms_note) if args.terms_note is not None else None
    policy = DecisionNoteSettlementPolicy(args.policy_note) if args.policy_note is not None else None
    producer = None
    if args.producer == 'gate-fake':
        from capital.gate_producer import GateHttpProducer, GateUnavailable
        try:
            producer = GateHttpProducer()
        except GateUnavailable as exc:
            parser.error(exc.code)
    try:
        with make_server(args.port, workspace=args.workspace, signer=signer, terms=terms, policy=policy, producer=producer, event_log=args.event_log) as server:
            print(f'KIX Capital simulation: http://127.0.0.1:{server.server_port}', flush=True)
            if isinstance(signer, DevHmacSigner):
                print('export signature DEV_ONLY HMAC integrity only; not authentication', flush=True)
            if producer is not None:
                print(
                    f'producer LOCAL_FAKE_GATE {producer.base_url} NOT_BOUND semantic_conformance=false',
                    flush=True)
            if args.event_log:
                print(
                    f'event log {args.event_log} LOCAL_OBSERVABILITY max_bytes={EVENT_LOG_MAX_BYTES} not an exporter',
                    flush=True)
            view = server.service.workspace_view()
            if view['kind'] == 'LOCAL_FILE_WORKSPACE':
                print(f"workspace {view['status']} LOCAL_FILE_WORKSPACE {view['path']}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        if producer is not None:
            producer.close()


if __name__ == '__main__':
    main()
