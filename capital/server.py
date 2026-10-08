"""Loopback-only same-origin local simulation API, without external integrations."""
from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from capital.service import ApiError, CapitalService

STATIC = Path(__file__).parent / 'static'
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


def make_server(port=8765):
    service = CapitalService()
    token = secrets.token_urlsafe(32)

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
                if self.headers.get_all('X-Capital-Token') != [token]:
                    raise ApiError('LOCAL_TOKEN_REQUIRED', 403)
                if self.headers.get('Content-Type') != 'application/json':
                    raise ApiError('JSON_REQUIRED', 415)

        def do_GET(self):
            try:
                self.boundary()
                route = urlsplit(self.path)
                if route.path in ASSETS:
                    name, kind = ASSETS[route.path]
                    return self.reply(200, (STATIC / name).read_bytes(), kind)
                if route.path == '/api/state':
                    return self.reply(200, {**service.snapshot(), 'local_token': token})
                if route.path == '/api/evidence':
                    return self.reply(200, service.evidence())
                if route.path == '/api/projection':
                    return self.reply(200, service.projection(projection_mode(route.query)))
                if route.path == '/api/readiness':
                    return self.reply(200, service.readiness())
                if route.path == '/api/scenarios':
                    return self.reply(200, service.scenarios())
                if route.path.startswith('/api/scenarios/'):
                    return self.reply(200, service.scenarios(route.path.rsplit('/', 1)[-1]))
                if route.path.startswith('/api/preview/'):
                    instance = parse_qs(route.query).get('instance_id', [''])[0]
                    return self.reply(200, service.preview_draw(route.path.rsplit('/', 1)[-1], instance))
                if route.path == '/api/export':
                    return self.reply(200, service.export())
                if route.path.startswith('/api/operations/'):
                    instance = parse_qs(route.query).get('instance_id', [''])[0]
                    return self.reply(200, service.operation(route.path.rsplit('/', 1)[-1], instance))
                raise ApiError('NOT_FOUND', 404)
            except ApiError as exc:
                self.reply(exc.status, {'error': exc.code})

        def do_POST(self):
            try:
                self.boundary(mutate=True)
                if self.path != '/api/commands':
                    raise ApiError('NOT_FOUND', 404)
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):
                    raise ApiError('INVALID_LENGTH')
                length = int(lengths[0])
                if not 0 < length <= 8192:
                    raise ApiError('BODY_TOO_LARGE', 413)
                self.connection.settimeout(3)
                try:
                    raw = self.rfile.read(length)
                    body = json.loads(raw, object_pairs_hook=strict_object,
                                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (ValueError, UnicodeDecodeError, TimeoutError, RecursionError):
                    raise ApiError('INVALID_JSON')
                self.reply(200, service.execute(body))
            except ApiError as exc:
                self.reply(exc.status, {'error': exc.code})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.service = service
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with make_server(args.port) as server:
        print(f'KIX Capital simulation: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
