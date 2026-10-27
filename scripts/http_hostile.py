#!/usr/bin/env python3
"""Regenerate and byte-pin the hostile raw-HTTP corpus for the loopback server.

The corpus lives in tests/vectors/http/ and is SIMULATED. Each recipe is one
canonical JSON document carrying a single raw request as base64, plus the
pinned outcome the server must produce when tests/test_http_hostile.py replays
it against an in-process make_server(0):

- request_b64: the exact bytes sent on the socket. The ASCII sentinels
  __PORT__ and __TOKEN__ are placeholders the replay substitutes with the live
  server port and the organizer token, so no live value is pinned.
- expect.status: the status code on the HTTP status line, or null when the
  pinned outcome is "no status line" (connection closed or an HTTP/0.9-style
  body-only reply, which the stdlib produces for pre-version errors).
- expect.code: the JSON body's `error` field, or null for the stdlib's
  non-JSON error pages.
- expect.content_type_prefix and expect.body_marker pin the response kind
  and one literal substring where a bare status is not enough.
- post_state pins that every recipe leaves state_digest and operation_count
  unchanged and /api/health answering 200, and that no response carries a
  traceback, the local token, or a repository path.

--check regenerates in memory and exits 1 when any file differs, is missing,
or is unexpected under http/. --write rewrites the files and removes any
other http/*.json, which this script owns. --dir points both at another
directory.
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import store

DEFAULT_DIR = ROOT / 'tests' / 'vectors'
HTTP_DIR = 'http'
FORMAT = 'KIX_CAPITAL_HTTP_HOSTILE_V1'
PORT = b'__PORT__'
TOKEN = b'__TOKEN__'
HOST = b'127.0.0.1:' + PORT
GET_HEADERS = [(b'Host', HOST)]
POST_STATE = {
    'state_digest': 'UNCHANGED',
    'operation_count': 'UNCHANGED',
    'health_status': 200,
}


class VectorError(Exception):
    pass


def dump(document) -> bytes:
    return store.canonical_bytes(document) + b'\n'


def _join(method, target, pairs, body=b'', version=b'HTTP/1.0'):
    """Request line plus header pairs, CRLF-joined, with a raw body appended."""
    lines = [method + b' ' + target + b' ' + version]
    lines += [name + b': ' + value for name, value in pairs]
    return b'\r\n'.join(lines) + b'\r\n\r\n' + body


def _get(target, pairs=GET_HEADERS, version=b'HTTP/1.0'):
    return _join(b'GET', target, pairs, version=version)


def _post_headers(length, token=TOKEN, content_type=b'application/json'):
    return [
        (b'Host', HOST),
        (b'X-Capital-Token', token),
        (b'Content-Type', content_type),
        (b'Content-Length', length),
    ]


def _session(body, length=None, headers=None):
    """POST /api/session with a valid token; a stable non-mutating sink."""
    if length is None:
        length = str(len(body)).encode('ascii')
    if headers is None:
        headers = _post_headers(length)
    return _join(b'POST', b'/api/session', headers, body)


def _expect(status, code=None, content_type='application/json', body_marker=None):
    return {
        'status': status,
        'code': code,
        'content_type_prefix': content_type,
        'body_marker': body_marker,
    }


_HTML = 'text/html'
_HEALTH = '"status": "ok"'
_UNCHANGED = 'the read-only probe still answers'

_deep_body = b'{"a":' * 1300 + b'1' + b'}' * 1300
_pad_body = b'{"pad":"' + b'A' * (8192 - len(b'{"pad":""}')) + b'"}'
_flood = [(b'Host', HOST)] + [(f'X-Pad-{i}'.encode(), b'v') for i in range(110)]

# (name, note, request bytes, expect). Requests must stay byte-deterministic:
# live values may only appear through the __PORT__/__TOKEN__ sentinels.
CASES = (
    # Spoofed or malformed Host: only the literal loopback host:port is valid.
    ('host-absent', 'no Host header at all',
     _get(b'/api/health', [(b'Accept', b'application/json')]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-suffix-evil', 'loopback host with an evil DNS suffix',
     _get(b'/api/health', [(b'Host', b'127.0.0.1.evil:' + PORT)]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-trailing-dot', 'FQDN-style trailing dot on the loopback address',
     _get(b'/api/health', [(b'Host', b'127.0.0.1.:' + PORT)]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-ipv6', 'IPv6 loopback authority is not the literal IPv4 host',
     _get(b'/api/health', [(b'Host', b'[::1]:' + PORT)]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-wrong-port', 'loopback host but a different port',
     _get(b'/api/health', [(b'Host', b'127.0.0.1:1')]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-duplicated', 'two Host headers, one valid and one hostile',
     _get(b'/api/health', [(b'Host', HOST), (b'Host', b'evil.example')]),
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-folded', 'obsolete line folding mutates the Host value',
     b'GET /api/health HTTP/1.0\r\nHost: ' + HOST + b'\r\n\t.evil\r\n\r\n',
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    ('host-empty', 'an empty Host value',
     b'GET /api/health HTTP/1.0\r\nHost:\r\n\r\n',
     _expect(403, 'LOOPBACK_HOST_REQUIRED')),
    # Origin must equal the loopback origin exactly when present.
    ('origin-null', 'Origin: null sent by sandboxed cross-site contexts',
     _get(b'/api/health', [(b'Host', HOST), (b'Origin', b'null')]),
     _expect(403, 'ORIGIN_REJECTED')),
    ('origin-cross-site', 'a foreign Origin',
     _get(b'/api/health', [(b'Host', HOST), (b'Origin', b'http://evil.example')]),
     _expect(403, 'ORIGIN_REJECTED')),
    ('origin-trailing-slash', 'the right origin plus a trailing slash',
     _get(b'/api/health', [(b'Host', HOST), (b'Origin', b'http://' + HOST + b'/')]),
     _expect(403, 'ORIGIN_REJECTED')),
    ('origin-duplicated', 'two Origins, one valid and one null',
     _get(b'/api/health', [(b'Host', HOST), (b'Origin', b'http://' + HOST), (b'Origin', b'null')]),
     _expect(403, 'ORIGIN_REJECTED')),
    # Fetch metadata: only same-origin/none are allowed.
    ('sec-fetch-cross-site', 'Sec-Fetch-Site: cross-site',
     _get(b'/api/health', [(b'Host', HOST), (b'Sec-Fetch-Site', b'cross-site')]),
     _expect(403, 'CROSS_SITE_REJECTED')),
    ('sec-fetch-same-site', 'Sec-Fetch-Site: same-site is not same-origin',
     _get(b'/api/health', [(b'Host', HOST), (b'Sec-Fetch-Site', b'same-site')]),
     _expect(403, 'CROSS_SITE_REJECTED')),
    # Path tricks: traversal, encodings, authority forms, NUL bytes.
    ('path-dotdot', 'literal dot-dot traversal in the target',
     _get(b'/../x'), _expect(404, 'NOT_FOUND')),
    ('path-encoded-dots', 'percent-encoded dots inside /api/',
     _get(b'/api/%2e%2e/state'), _expect(404, 'NOT_FOUND')),
    ('path-encoded-traversal', 'encoded traversal to a well-known file',
     _get(b'/%2e%2e/etc/passwd'), _expect(404, 'NOT_FOUND')),
    ('path-backslash', 'backslash separators are not unescaped or normalized',
     _get(b'/api\\..\\state'), _expect(404, 'NOT_FOUND')),
    ('path-nul', 'a NUL byte inside the target',
     b'GET /api/health\x00x HTTP/1.0\r\nHost: ' + HOST + b'\r\n\r\n',
     _expect(404, 'NOT_FOUND')),
    ('path-invalid-utf8', 'a raw 0xff byte inside the target',
     b'GET /api/health\xff HTTP/1.0\r\nHost: ' + HOST + b'\r\n\r\n',
     _expect(404, 'NOT_FOUND')),
    ('path-double-slash', 'leading // is normalized by the stdlib (gh-87389) ' + _UNCHANGED,
     _get(b'//api/health'), _expect(200, None, body_marker=_HEALTH)),
    ('path-absolute-form', 'proxy-style absolute URI whose authority is ignored ' + _UNCHANGED,
     _get(b'http://' + HOST + b'/api/health'), _expect(200, None, body_marker=_HEALTH)),
    ('path-authority-evil', 'absolute URI with a foreign authority; the Host '
     'header still binds the request to loopback ' + _UNCHANGED,
     _get(b'http://evil.example/api/health'), _expect(200, None, body_marker=_HEALTH)),
    ('path-root-normalized', '// normalizes to / and serves the local index ' + _UNCHANGED,
     _get(b'//'), _expect(200, None, _HTML)),
    ('target-invalid-ipv6', 'malformed IPv6 authority used to crash urlsplit '
     'and drop the connection; the fix maps it to a clean rejection',
     _get(b'http://[bad/x'), _expect(400, 'INVALID_TARGET')),
    ('target-unclosed-ipv6', 'unclosed IPv6 bracket, same urlsplit crash family',
     _get(b'http://[::1/x'), _expect(400, 'INVALID_TARGET')),
    # Methods outside GET/POST: the stdlib answers 501 by design.
    ('method-trace', 'TRACE has no handler',
     _join(b'TRACE', b'/api/health', GET_HEADERS), _expect(501, None, _HTML, 'Unsupported method')),
    ('method-options', 'OPTIONS has no handler',
     _join(b'OPTIONS', b'/api/health', GET_HEADERS), _expect(501, None, _HTML, 'Unsupported method')),
    ('method-head', 'HEAD has no handler; the stdlib suppresses the error body',
     _join(b'HEAD', b'/api/health', GET_HEADERS), _expect(501, None, _HTML)),
    ('method-unknown', 'an invented method',
     _join(b'FOOBAR', b'/api/health', GET_HEADERS), _expect(501, None, _HTML, 'Unsupported method')),
    ('method-lowercase-get', 'methods are case-sensitive; get is not GET',
     _join(b'get', b'/api/health', GET_HEADERS), _expect(501, None, _HTML, 'Unsupported method')),
    ('method-connect', 'CONNECT has no handler',
     _join(b'CONNECT', b'127.0.0.1:' + PORT, GET_HEADERS), _expect(501, None, _HTML, 'Unsupported method')),
    # Request-line attacks, including the cases that answer without a status
    # line (the stdlib emits a bare body when no version was parsed).
    ('request-line-overflow', 'request line above the 65536 byte limit',
     b'GET /api/health?' + b'A' * 70000 + b' HTTP/1.0\r\n\r\n',
     _expect(414, None, _HTML)),
    ('request-line-bad-version', 'HTTP/9.9 draws a body-only 505 page, '
     'no status line',
     _get(b'/api/health', version=b'HTTP/9.9'),
     _expect(None, None, None, 'Invalid HTTP version')),
    ('request-line-weird-version', 'non-numeric minor version draws a '
     'body-only 400 page',
     _get(b'/api/health', version=b'HTTP/1.x'),
     _expect(None, None, None, 'Bad request version')),
    ('request-line-one-word', 'a bare method word, no target or version',
     b'GET\r\n\r\n',
     _expect(None, None, None, 'Bad request syntax')),
    ('request-line-four-words', 'four words in the request line; the version '
     'still parses so the 400 carries a status line',
     _get(b'/api/health extra', GET_HEADERS),
     _expect(400, None, _HTML, 'Bad request syntax')),
    ('request-line-no-version', 'HTTP/0.9 style GET is still served: headers '
     'are parsed, the boundary holds, and the reply is a bare JSON body '
     'with no status line',
     b'GET /api/health\r\nHost: ' + HOST + b'\r\n\r\n',
     _expect(None, None, None, _HEALTH)),
    ('blank-request', 'a blank request line closes the connection silently',
     b'\r\n\r\n',
     _expect(None)),
    ('pipelined-extra-ignored', 'HTTP/1.0 closes after the first request; '
     'the pipelined second request is never answered',
     _join(b'GET', b'/api/health', GET_HEADERS, version=b'HTTP/1.1')
     + _join(b'GET', b'/api/state', GET_HEADERS, version=b'HTTP/1.1'),
     _expect(200, None, body_marker=_HEALTH)),
    # Header attacks: floods, overlong lines, malformed lines.
    ('header-flood', 'more headers than the stdlib limit',
     _get(b'/api/health', _flood), _expect(431, None, _HTML, 'Too many headers')),
    ('header-line-overlong', 'one header line above the 65536 byte limit',
     _join(b'GET', b'/api/health', [(b'Host', HOST), (b'X-Pad', b'A' * 70000)]),
     _expect(431, None, _HTML, 'Line too long')),
    ('header-no-colon', 'a header line with no colon is tolerated; the valid '
     'Host still binds ' + _UNCHANGED,
     _join(b'GET', b'/api/health', [(b'Host', HOST), (b'NoColonHere', b'')], b'')
     .replace(b'NoColonHere: ', b'NoColonHere'),
     _expect(200, None, body_marker=_HEALTH)),
    ('header-bare-cr', 'a bare CR inside a header value is tolerated',
     b'GET /api/health HTTP/1.0\r\nHost: ' + HOST + b'\r\nX-Test: a\rb\r\n\r\n',
     _expect(200, None, body_marker=_HEALTH)),
    ('header-nul', 'a NUL inside a header value is tolerated',
     b'GET /api/health HTTP/1.0\r\nHost: ' + HOST + b'\r\nX-Test: a\x00b\r\n\r\n',
     _expect(200, None, body_marker=_HEALTH)),
    ('expect-100-continue', 'an HTTP/1.1 Expect: 100-continue POST gets no '
     'preamble from the HTTP/1.0 server and fails the token gate',
     _join(b'POST', b'/api/session',
           [(b'Host', HOST), (b'Content-Type', b'application/json'),
            (b'Content-Length', b'2'), (b'Expect', b'100-continue')],
           b'{}', version=b'HTTP/1.1'),
     _expect(403, 'LOCAL_TOKEN_REQUIRED')),
    # POST gates: token, Content-Type, then the body length rules.
    ('post-no-token', 'a POST without X-Capital-Token',
     _join(b'POST', b'/api/commands',
           [(b'Host', HOST), (b'Content-Type', b'application/json'),
            (b'Content-Length', b'2')], b'{}'),
     _expect(403, 'LOCAL_TOKEN_REQUIRED')),
    ('post-token-bogus', 'a token the authorizer does not know',
     _join(b'POST', b'/api/commands',
           _post_headers(b'2', token=b'not-a-real-token'), b'{}'),
     _expect(403, 'LOCAL_TOKEN_REQUIRED')),
    ('post-token-duplicate', 'two tokens, one valid and one bogus',
     _join(b'POST', b'/api/commands',
           [(b'Host', HOST), (b'X-Capital-Token', TOKEN), (b'X-Capital-Token', b'other-token'),
            (b'Content-Type', b'application/json'), (b'Content-Length', b'2')], b'{}'),
     _expect(403, 'LOCAL_TOKEN_REQUIRED')),
    ('post-unknown-path', 'a fully valid POST to an unregistered path',
     _join(b'POST', b'/api/no-such', _post_headers(b'2'), b'{}'),
     _expect(404, 'NOT_FOUND')),
    ('content-type-wrong', 'a POST whose Content-Type is not JSON',
     _session(b'{}', headers=_post_headers(b'2', content_type=b'text/plain')),
     _expect(415, 'JSON_REQUIRED')),
    ('content-type-charset-suffix', 'even a charset suffix is rejected: the '
     'media type must be literally application/json',
     _session(b'{}', headers=_post_headers(b'2', content_type=b'application/json; charset=utf-8')),
     _expect(415, 'JSON_REQUIRED')),
    ('length-missing', 'no Content-Length at all',
     _session(b'{}', headers=_post_headers(b'2')[:-1]),
     _expect(400, 'INVALID_LENGTH')),
    ('length-duplicate', 'two different Content-Length values',
     _session(b'{}', headers=_post_headers(b'2') + [(b'Content-Length', b'4')]),
     _expect(400, 'INVALID_LENGTH')),
    ('length-nonnumeric', 'a non-numeric Content-Length',
     _session(b'{}', headers=_post_headers(b'8192x')),
     _expect(400, 'INVALID_LENGTH')),
    ('length-signed', 'a signed Content-Length is not digits',
     _session(b'{}', headers=_post_headers(b'+10')),
     _expect(400, 'INVALID_LENGTH')),
    ('length-comma', 'a comma-joined Content-Length is not digits',
     _session(b'{}', headers=_post_headers(b'2, 4')),
     _expect(400, 'INVALID_LENGTH')),
    ('length-zero', 'zero is outside the designed 1..8192 window',
     _session(b'', length=b'0'),
     _expect(413, 'BODY_TOO_LARGE')),
    ('body-over-8192-declared', 'a declared body above the 8192 byte cap is '
     'refused before a byte of it is read',
     _session(b'', length=b'8193'),
     _expect(413, 'BODY_TOO_LARGE')),
    ('body-over-8192-sent', 'exactly 8192 declared bytes followed by extra '
     'bytes the server never reads; the declared body is a plain JSON object',
     _session(_pad_body + b'JUNK', length=b'8192'),
     _expect(400, 'INVALID_SESSION')),
    ('transfer-encoding-chunked', 'any Transfer-Encoding is refused outright',
     _session(b'2\r\n{}\r\n0\r\n\r\n',
              headers=_post_headers(b'13') + [(b'Transfer-Encoding', b'chunked')]),
     _expect(400, 'INVALID_LENGTH')),
    ('length-mismatch-short', 'the declared length exceeds the bytes sent '
     'before the peer closes; the short body fails to parse',
     _session(b'{"truncated":', length=b'120'),
     _expect(400, 'INVALID_JSON')),
    ('length-mismatch-long', 'the declared length is smaller than the bytes '
     'sent; only the declared prefix is read and the rest is dropped',
     _session(b'{}XXXXX', length=b'2'),
     _expect(400, 'INVALID_SESSION')),
    # Hostile JSON bodies: encodings, duplicates, constants, nesting.
    ('body-invalid-utf8', 'body bytes that are not valid UTF-8',
     _session(b'\xff\xfe{}'), _expect(400, 'INVALID_JSON')),
    ('body-bom', 'a UTF-8 BOM is tolerated by json.loads (utf-8-sig); the '
     'document still reaches the strict shape gate',
     _session(b'\xef\xbb\xbf{}'), _expect(400, 'INVALID_SESSION')),
    ('body-nul', 'a NUL byte inside a JSON string',
     _session(b'{"a":"\x00"}'), _expect(400, 'INVALID_JSON')),
    ('body-duplicate-keys', 'the same key twice is refused by the strict parser',
     _session(b'{"a":1,"a":2}'), _expect(400, 'INVALID_JSON')),
    ('body-nan', 'NaN is refused by the strict parser',
     _session(b'{"a":NaN}'), _expect(400, 'INVALID_JSON')),
    ('body-infinity', 'Infinity is refused by the strict parser',
     _session(b'{"a":Infinity}'), _expect(400, 'INVALID_JSON')),
    ('body-neg-infinity', '-Infinity is refused by the strict parser',
     _session(b'{"a":-Infinity}'), _expect(400, 'INVALID_JSON')),
    ('body-deep-nesting', 'the deepest nesting that fits the 8192 byte cap '
     'still parses under the recursion limit and reaches the shape gate',
     _session(_deep_body), _expect(400, 'INVALID_SESSION')),
    ('body-trailing-garbage', 'trailing bytes after a complete document',
     _session(b'{} extra'), _expect(400, 'INVALID_JSON')),
    ('body-json-array', 'a JSON array is not a session object',
     _session(b'[1]'), _expect(400, 'INVALID_SESSION')),
    ('body-json-scalar', 'a bare JSON scalar is not a session object',
     _session(b'1'), _expect(400, 'INVALID_SESSION')),
    # GET never reads a body: a declared length or chunked flag is inert.
    ('get-with-body-declared', 'a Content-Length on a GET is ignored; the '
     'body bytes are dropped when the connection closes ' + _UNCHANGED,
     _join(b'GET', b'/api/health', GET_HEADERS + [(b'Content-Length', b'99999')], b'{}'),
     _expect(200, None, body_marker=_HEALTH)),
    ('get-transfer-encoding', 'a Transfer-Encoding on a GET is ignored',
     _join(b'GET', b'/api/health', GET_HEADERS + [(b'Transfer-Encoding', b'chunked')]),
     _expect(200, None, body_marker=_HEALTH)),
)


def build_vectors() -> dict:
    """Relative path under the vectors directory -> bytes. Pure: nothing is written."""
    names = [name for name, _note, _request, _expect in CASES]
    if len(names) != len(set(names)):
        raise VectorError('duplicate case names')
    files = {}
    for name, note, request, expect in CASES:
        recipe = {
            'format': FORMAT,
            'label': 'SIMULATED',
            'name': name,
            'note': note,
            'request_b64': base64.b64encode(request).decode('ascii'),
            'expect': expect,
            'post_state': POST_STATE,
        }
        files[f'{HTTP_DIR}/{name}.json'] = dump(recipe)
    return files


def find_drift(root, vectors):
    problems = []
    for relative, data in sorted(vectors.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f'missing {relative}')
        elif path.read_bytes() != data:
            problems.append(f'differs {relative}')
    directory = root / HTTP_DIR
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if f'{HTTP_DIR}/{path.name}' not in vectors:
                problems.append(f'unexpected {HTTP_DIR}/{path.name}')
    return problems


def write_vectors(root, vectors):
    for relative, data in sorted(vectors.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    directory = root / HTTP_DIR
    if directory.is_dir():
        for path in sorted(directory.glob('*.json')):
            if f'{HTTP_DIR}/{path.name}' not in vectors:
                path.unlink()
                print(f'removed stale {HTTP_DIR}/{path.name}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Byte-compare the corpus. Exit 1 on drift.')
    mode.add_argument('--write', action='store_true', help='Regenerate the corpus.')
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR, help='Vectors directory. Default tests/vectors')
    args = parser.parse_args(argv)
    try:
        vectors = build_vectors()
        if args.write:
            write_vectors(args.dir, vectors)
            print(f'http hostile vectors written: {len(vectors)} files in {args.dir}')
            return 0
        problems = find_drift(args.dir, vectors)
    except (OSError, VectorError) as exc:
        print(f'http hostile vectors failed: {exc}', file=sys.stderr)
        return 1
    if problems:
        print('http hostile vectors drift: ' + ', '.join(problems), file=sys.stderr)
        print('run python3 scripts/http_hostile.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'http hostile vectors ok: {len(vectors)} files match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
