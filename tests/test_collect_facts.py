"""Real stdlib loopback collection and hostile peers; all books are SIMULATED."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from capital import facts
from capital.server import make_server
from capital.service import CapitalService
from capital.store import FileWorkspace, canonical_bytes
from scripts import collect_facts as collector
from scripts.facts_vectors import seed, with_overlay
from scripts.seed_demo import apply_steps

TOKEN = 'SYNTHETIC_SENTINEL_TOKEN_DO_NOT_PERSIST_0192837465'
BOOTSTRAP = canonical_bytes({'instance_id': 'sim-session', 'local_token': TOKEN})
ROOT = Path(__file__).resolve().parents[1]


def wire(body, status=200, headers=None):
    if headers is None:
        headers = [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))]
    return (f'HTTP/1.0 {status} SIMULATED\r\n'.encode()
            + b''.join(f'{k}: {v}\r\n'.encode() for k, v in headers) + b'\r\n' + body)


def book_pages(service=None, limit=4):
    service = service or CapitalService()
    pages, after = [], None
    while True:
        page = service.export_facts('instance_id=' + service.instance_id + '&limit=' + str(limit)
                                    + ('&after=' + after if after else ''))
        pages.append(canonical_bytes(page))
        after = page['next_cursor']
        if after is None:
            return pages


@contextlib.contextmanager
def peer(responses):
    """One script entry per request; record every method/header without retries."""
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = False

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(1)
            request = self.rfile.readline()
            headers = []
            while True:
                line = self.rfile.readline()
                if line in (b'\r\n', b'\n', b''):
                    break
                headers.append(line)
            with server.record_lock:
                index = len(server.requests)
                server.requests.append((request, b''.join(headers)))
            if index < len(responses):
                response = responses[index]
                try:
                    if callable(response):
                        response(self.connection)
                    else:
                        self.connection.sendall(response)
                except (OSError, TimeoutError):
                    pass

    server = Server(('127.0.0.1', 0), Handler)
    server.requests, server.record_lock = [], threading.Lock()
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextlib.contextmanager
def capital_server(**kwargs):
    server = make_server(0, **kwargs)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.counter = 0

    def invoke(self, server, *extra, out=None, subprocess_cli=False):
        if out is None:
            self.counter += 1
            out = self.base / f'artifact-{self.counter}'
        argv = ['--endpoint', f'http://127.0.0.1:{server.server_address[1]}', '--out', str(out), *extra]
        if subprocess_cli:
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/collect_facts.py'), *argv],
                                  cwd=self.base, text=True, capture_output=True, timeout=15)
            return proc.returncode, out, proc.stdout + proc.stderr
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = collector.main(argv)
        return code, out, stdout.getvalue() + stderr.getvalue()

    def assert_failed(self, result, diagnostic=None):
        code, out, output = result
        self.assertEqual(code, 1, output)
        self.assertFalse((out / 'COMPLETE.json').exists())
        if diagnostic:
            self.assertIn(diagnostic, output)
        self.assert_secret_absent(out, output)

    def assert_secret_absent(self, out, output):
        self.assertNotIn(TOKEN, output)
        if out.is_dir():
            for path in out.iterdir():
                self.assertNotIn(TOKEN.encode(), path.read_bytes(), path.name)

    def assert_complete(self, result, raws):
        code, out, output = result
        self.assertEqual(code, 0, output)
        names = [f'page-{index:08d}.json' for index in range(len(raws))]
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['COMPLETE.json', *names])
        for name, raw in zip(names, raws):
            self.assertEqual((out / name).read_bytes(), raw)
            self.assertEqual((out / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        marker = json.loads((out / 'COMPLETE.json').read_bytes())
        self.assertEqual((out / 'COMPLETE.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(marker['status'], 'VERIFIED_COMPLETE')
        self.assertEqual(marker['format'], 'KIX_CAPITAL_FACTS_COLLECTION_V1')
        self.assertEqual(marker['label'], 'SIMULATED')
        self.assertEqual(marker['source_cut'], 'NOT_BOUND')
        self.assertEqual(marker['authentication'], 'NOT_BOUND')
        self.assertIs(marker['stage7_authenticated_export'], False)
        self.assertIs(marker['funds_executed'], False)
        self.assertEqual(marker['pages'], [{'name': name, 'bytes': len(raw),
                                           'sha256': hashlib.sha256(raw).hexdigest()}
                                          for name, raw in zip(names, raws)])
        self.assertEqual(marker['page_bytes_total'], sum(map(len, raws)))
        self.assertEqual(marker['verification'], facts.verify_dir(out))
        self.assertIs(marker['verification']['ok'], True)
        self.assert_secret_absent(out, output)
        return out

    def test_empty_f04_and_overlay_books_against_real_server_and_cli(self):
        for kind in ('empty', 'f04', 'overlay'):
            with self.subTest(kind=kind), capital_server() as server:
                service = server.service
                if kind != 'empty':
                    apply_steps(service)
                if kind == 'overlay':
                    with_overlay(service)
                frozen = service._frozen()
                before_export = service.export()
                raws = book_pages(service)
                out = self.assert_complete(self.invoke(server, '--limit', '4', subprocess_cli=True), raws)
                rows = [r for p in sorted(out.glob('page-*.json')) for r in json.loads(p.read_bytes())['rows']]
                self.assertEqual([r['entry'] for r in rows if r['source'] == 'JOURNAL'],
                                 service.machine.export_journal())
                self.assertEqual(canonical_bytes([r['entry'] for r in rows if r['source'] == 'JOURNAL']),
                                 canonical_bytes(before_export['journal']))
                manifest = service.export_manifest()
                if kind == 'overlay':
                    self.assertEqual(canonical_bytes([r['entry'] for r in rows if r['source'] == 'OVERLAY']),
                                     canonical_bytes(manifest['sections']['overlay']['body']['journal']))
                self.assertEqual([r['entry'] for r in rows if r['source'] == 'OVERLAY'], service.overlay_entries)
                self.assertEqual(service.export(), before_export)
                self.assertEqual(service._frozen(), frozen)

    def test_private_file_workspace_bytes_and_receipts_unchanged(self):
        source = self.base / 'source'
        storage = FileWorkspace.open(source)
        service = CapitalService(storage)
        apply_steps(service)
        storage.close()
        self.assertEqual((source / 'workspace.json').stat().st_mode & 0o777, 0o600)
        before = {p.name: p.read_bytes() for p in source.iterdir()}
        with capital_server(workspace=source) as server:
            raws = book_pages(server.service)
            self.assert_complete(self.invoke(server, '--limit', '4'), raws)
            self.assertEqual({p.name: p.read_bytes() for p in source.iterdir()}, before)

    def test_proxy_environment_ignored_and_exact_get_headers(self):
        raws = book_pages(limit=100)
        with peer([wire(BOOTSTRAP), *map(wire, raws)]) as server, patch.dict(os.environ, {
                'http_proxy': 'http://192.0.2.1:9', 'HTTP_PROXY': 'http://192.0.2.1:9',
                'ALL_PROXY': 'http://192.0.2.1:9', 'NO_PROXY': ''}):
            self.assert_complete(self.invoke(server, subprocess_cli=True), raws)
            self.assertEqual(len(server.requests), 2)
            for request, headers in server.requests:
                self.assertTrue(request.startswith(b'GET /api/'))
                self.assertIn(f'Host: 127.0.0.1:{server.server_address[1]}\r\n'.encode(), headers)
            self.assertIn(b'X-Capital-Token: ' + TOKEN.encode(), server.requests[1][1])

    def test_fixed_session_cursor_and_limit(self):
        raws = book_pages(with_overlay(seed()), 4)
        with peer([wire(BOOTSTRAP), *map(wire, raws)]) as server:
            self.assert_complete(self.invoke(server, '--limit', '4'), raws)
            for index, (request, _) in enumerate(server.requests[1:]):
                params = parse_qs(urlsplit(request.decode().split()[1]).query)
                self.assertEqual(params['instance_id'], ['sim-session'])
                self.assertEqual(params['limit'], ['4'])
                expected = {} if index == 0 else {'after': [json.loads(raws[index - 1])['next_cursor']]}
                self.assertEqual({k: v for k, v in params.items() if k == 'after'}, expected)

    def test_terminal_http_errors_do_not_restart_or_submit(self):
        first = book_pages(seed())[0]
        for status, reason in ((409, 'CUT_MOVED'), (409, 'SESSION_CHANGED'),
                               (503, 'STORAGE_STATE_MISMATCH'), (403, 'ROLE_FORBIDDEN')):
            with self.subTest(reason=reason), peer([wire(BOOTSTRAP), wire(first),
                    wire(canonical_bytes({'error': reason, 'token': TOKEN}), status)]) as server:
                self.assert_failed(self.invoke(server, '--limit', '4'), f'HTTP_{status}')
                self.assertEqual(len(server.requests), 3)
                self.assertTrue(all(request.startswith(b'GET ') for request, _ in server.requests))

    def test_real_cut_session_and_storage_refusals_are_terminal(self):
        with capital_server() as server:
            apply_steps(server.service)
            original = server.service.export_facts
            for mode in ('cut', 'session', 'storage'):
                calls = []
                def changing(query):
                    calls.append(query)
                    if len(calls) == 2:
                        if mode == 'cut':
                            server.service.execute({'instance_id': server.service.instance_id,
                                'operation_id': 'collector-fault', 'op': 'offer', 'advance_id': 'collector-fault',
                                'args': {'fixture_id': 'sim-committed', 'amount': 1}})
                        elif mode == 'session':
                            server.service.instance_id = 'replacement-session'
                        else:
                            from capital.service import ApiError
                            raise ApiError('STORAGE_STATE_MISMATCH', 503)
                    return original(query)
                with self.subTest(mode=mode), patch.object(server.service, 'export_facts', side_effect=changing):
                    self.assert_failed(self.invoke(server, '--limit', '1'), 'HTTP_')
                    self.assertEqual(len(calls), 2)

    def test_redirects_refused_without_target_requests(self):
        for status in (301, 302, 303, 307, 308):
            with peer([]) as target:
                for location in (f'http://127.0.0.1:{target.server_address[1]}/stolen',
                                 'http://192.0.2.1/stolen', '/api/state'):
                    with self.subTest(status=status, location=location), peer([
                            wire(b'', status, [('Content-Length', '0'), ('Location', location)])]) as server:
                        self.assert_failed(self.invoke(server), 'REDIRECT_REFUSED')
                        self.assertEqual(len(server.requests), 1)
                self.assertEqual(target.requests, [])

    def test_page_response_and_total_byte_bounds_exact_and_over(self):
        raws = book_pages(seed(), 4)
        responses = [wire(BOOTSTRAP), *map(wire, raws)]
        total = len(BOOTSTRAP) + sum(map(len, raws))
        maximum = max(len(BOOTSTRAP), *map(len, raws))
        with peer(responses) as server:
            self.assert_complete(self.invoke(server, '--limit', '4', '--max-pages', str(len(raws)),
                '--max-response-bytes', str(maximum), '--max-total-bytes', str(total)), raws)
        for options, reason, requests in (
                (('--max-pages', str(len(raws) - 1)), 'PAGE_COUNT_BOUND', len(raws)),
                (('--max-response-bytes', str(maximum - 1)), 'RESPONSE_BYTE_BOUND', None),
                (('--max-total-bytes', str(total - 1)), 'TOTAL_BYTE_BOUND', len(responses)),
                (('--max-response-bytes', str(len(BOOTSTRAP) - 1)), 'RESPONSE_BYTE_BOUND', 1),
                (('--max-total-bytes', str(len(BOOTSTRAP) - 1)), 'TOTAL_BYTE_BOUND', 1)):
            with self.subTest(options=options), peer(responses) as server:
                self.assert_failed(self.invoke(server, '--limit', '4', *options), reason)
                if requests:
                    self.assertEqual(len(server.requests), requests)

    def test_framing_truncation_oversize_encoding_and_disconnect(self):
        raw = book_pages(limit=100)[0]
        base = [('Content-Type', 'application/json')]
        cases = [
            (wire(raw, headers=base), 'FRAMING'),
            (wire(raw, headers=base + [('Content-Length', str(len(raw)))] * 2), 'FRAMING'),
            (wire(raw, headers=base + [('Content-Length', '2, 2')]), 'FRAMING'),
            (wire(raw, headers=base + [('Content-Length', '+2')]), 'FRAMING'),
            (wire(raw, headers=base + [('Content-Length', '2'), ('Transfer-Encoding', 'chunked')]), 'FRAMING'),
            (wire(raw, headers=base + [('Content-Length', str(len(raw))), ('Content-Encoding', 'gzip')]), 'FRAMING'),
            (wire(raw[:-1], headers=base + [('Content-Length', str(len(raw)))]), 'TRUNCATED'),
            (wire(raw + b'x', headers=base + [('Content-Length', str(len(raw)))]), 'TRUNCATED'),
            (wire(raw, headers=base + [('Content-Length', '999999999')]), 'BYTE_BOUND'),
            (wire(raw, headers=[('Content-Type', 'text/html'), ('Content-Length', str(len(raw)))]), 'CONTENT_TYPE'),
            (b'', 'TRANSPORT_FAILED'),
        ]
        for response, reason in cases:
            with self.subTest(reason=reason, response=response[:80]), peer([wire(BOOTSTRAP), response]) as server:
                self.assert_failed(self.invoke(server), reason)
                self.assertEqual(len(server.requests), 2)

    def test_socket_timeout_and_monotonic_slow_header_and_body_deadlines(self):
        raw = book_pages(limit=100)[0]
        def drip(data):
            def send(sock):
                for byte in data:
                    sock.sendall(bytes([byte]))
                    time.sleep(0.015)
            return send
        def stall(sock):
            time.sleep(0.2)
        # Header and body drips continually deliver bytes faster than the socket timeout.
        def body_drip(sock):
            head = wire(raw).split(b'\r\n\r\n', 1)[0] + b'\r\n\r\n'
            sock.sendall(head)
            drip(raw)(sock)
        for response in (stall, drip(wire(raw)), body_drip):
            with self.subTest(response=response), peer([wire(BOOTSTRAP), response]) as server:
                start = time.monotonic()
                self.assert_failed(self.invoke(server, '--timeout', '0.08'), 'TIMEOUT')
                self.assertLess(time.monotonic() - start, 0.6)
                self.assertEqual(len(server.requests), 2)

    def test_malformed_bootstrap_and_pages_do_not_continue(self):
        bad = (b'{', b'[]', b'{}', b'{"instance_id":"x","instance_id":"y","local_token":"z"}',
               canonical_bytes({'instance_id': 'x', 'local_token': 'bad\nheader'}),
               canonical_bytes({'instance_id': 1, 'local_token': TOKEN}))
        for raw in bad:
            with self.subTest(bootstrap=raw), peer([wire(raw)]) as server:
                self.assert_failed(self.invoke(server), 'BOOTSTRAP_INVALID')
                self.assertEqual(len(server.requests), 1)
        valid = book_pages(seed())[0]
        for raw in (b'{', b'[]', b'{"x":NaN}', b'{"x":1,"x":2}', b'\xef\xbb\xbf' + valid,
                    valid + b' ', valid[:-1], b'[' * 1100 + b']' * 1100):
            with self.subTest(page=raw[:40]), peer([wire(BOOTSTRAP), wire(raw)]) as server:
                result = self.invoke(server, '--limit', '4')
                self.assert_failed(result, 'PAGE_INVALID')
                self.assertEqual(list(result[1].glob('page-*.json')), [])
                self.assertEqual(len(server.requests), 2)

    def test_page_validation_before_persistence_and_next_cursor(self):
        raw = book_pages(seed())[0]
        def reseal(page):
            page['page_digest'] = facts.page_digest(page)
            return canonical_bytes(page)
        changes = [lambda p: p.update(next_cursor=p['after']),
                   lambda p: p.update(next_cursor='kfc1.00000000.' + p['cut']['cut_id']),
                   lambda p: p.update(start_seq=True), lambda p: p.update(limit=3),
                   lambda p: p.update(after='bad'), lambda p: p.update(label='REAL'),
                   lambda p: p.update(chain_before='0' * 64),
                   lambda p: p['rows'][0].update(row_sha256='0' * 64),
                   lambda p: p.update(rows=[]), lambda p: p.update(row_count_total=False),
                   lambda p: p['cut'].update(cut_id='0' * 64),
                   lambda p: p['schema'].update(source_cut='BOUND')]
        for change in changes:
            page = json.loads(raw)
            change(page)
            with self.subTest(change=change), peer([wire(BOOTSTRAP), wire(reseal(page))]) as server:
                result = self.invoke(server, '--limit', '4')
                self.assert_failed(result, 'PAGE_INVALID')
                self.assertEqual(list(result[1].glob('page-*.json')), [])
                self.assertEqual(len(server.requests), 2)
        # A valid first page may never be repeated or followed by another cut.
        pages = book_pages(seed())
        changed = json.loads(pages[1])
        changed['cut']['state_digest'] = '0' * 64
        changed['cut']['cut_id'] = facts.cut_digest(changed['cut'])
        for second in (pages[0], reseal(changed)):
            with peer([wire(BOOTSTRAP), wire(pages[0]), wire(second)]) as server:
                result = self.invoke(server, '--limit', '4')
                self.assert_failed(result, 'PAGE_INVALID')
                self.assertEqual(len(list(result[1].glob('page-*.json'))), 1)
                self.assertEqual(len(server.requests), 3)

    def test_all_existing_tamper_vectors_fail_without_marker(self):
        vectors = ROOT / 'tests/vectors/facts'
        index = json.loads((vectors / 'index.json').read_bytes())['cases']
        for case, reason in index.items():
            if reason is None:
                continue
            raws = [p.read_bytes() for p in sorted((vectors / case).glob('page-*.json'))]
            with self.subTest(case=case), peer([wire(BOOTSTRAP), *map(wire, raws)]) as server:
                self.assert_failed(self.invoke(server, '--limit', '4'))
                self.assertLessEqual(len(server.requests), len(raws) + 2)

    def test_token_echo_is_refused_even_with_json_escaping(self):
        page = json.loads(book_pages(seed())[0])
        for escaped in (False, True):
            page['rows'][0]['entry']['sentinel'] = TOKEN
            page['page_digest'] = facts.page_digest(page)
            raw = canonical_bytes(page)
            if escaped:
                raw = raw.replace(TOKEN.encode(), b'\\u0053' + TOKEN[1:].encode())
            with peer([wire(BOOTSTRAP), wire(raw)]) as server:
                result = self.invoke(server, '--limit', '4', subprocess_cli=True)
                self.assert_failed(result, 'TOKEN_IN_PAGE')
                self.assertEqual(list(result[1].iterdir()), [])

    def test_existing_outputs_symlinks_checkouts_and_workspace_ancestry(self):
        existing = self.base / 'existing'
        existing.mkdir()
        (existing / 'keep').write_bytes(b'untouched')
        empty = self.base / 'empty'
        empty.mkdir()
        file = self.base / 'file'
        file.write_bytes(b'untouched')
        symlink = self.base / 'symlink'
        symlink.symlink_to(existing, target_is_directory=True)
        dangling = self.base / 'dangling'
        dangling.symlink_to(self.base / 'absent')
        workspace = self.base / 'workspace'
        workspace.mkdir()
        (workspace / 'workspace.json').write_bytes(b'READ_ONLY_FIXTURE')
        (workspace / 'nested').mkdir()
        cases = [existing, empty, file, symlink, dangling, ROOT / 'collector-must-not-exist',
                 workspace / 'new', workspace / 'nested/new', self.base / 'missing-parent/new']
        with peer([]) as server:
            for out in cases:
                with self.subTest(out=out):
                    result = self.invoke(server, out=out)
                    self.assertEqual(result[0], 1, result[2])
                    self.assertFalse((out / 'COMPLETE.json').exists())
            self.assertEqual(server.requests, [])
        self.assertEqual((existing / 'keep').read_bytes(), b'untouched')
        self.assertEqual(file.read_bytes(), b'untouched')
        self.assertEqual((workspace / 'workspace.json').read_bytes(), b'READ_ONLY_FIXTURE')

    def test_directory_creation_race_does_not_overwrite(self):
        out = self.base / 'race'
        original = Path.mkdir
        def race(path, *args, **kwargs):
            if path == out:
                original(path)
                (path / 'keep').write_bytes(b'other invocation')
            return original(path, *args, **kwargs)
        with peer([]) as server, patch.object(Path, 'mkdir', race):
            self.assert_failed(self.invoke(server, out=out))
            self.assertEqual((out / 'keep').read_bytes(), b'other invocation')
            self.assertEqual(server.requests, [])

    def test_write_verify_and_completion_failures_never_publish(self):
        raws = book_pages(limit=100)
        original = collector.write_private
        def fail_name(name):
            def write(fd, current, raw):
                if current == name:
                    raise OSError('fault with ' + TOKEN)
                return original(fd, current, raw)
            return write
        injections = [patch.object(collector, 'write_private', side_effect=fail_name('page-00000000.json')),
                      patch.object(collector.os, 'fsync', side_effect=OSError(TOKEN)),
                      patch.object(collector.facts, 'verify_dir', return_value={'ok': False, 'reason': TOKEN}),
                      patch.object(collector, 'write_private', side_effect=fail_name('.COMPLETE.tmp')),
                      patch.object(collector.os, 'link', side_effect=OSError(TOKEN))]
        for injection in injections:
            with self.subTest(injection=injection), peer([wire(BOOTSTRAP), *map(wire, raws)]) as server, injection:
                self.assert_failed(self.invoke(server))
                self.assertEqual(len(server.requests), 2)
        with peer([wire(BOOTSTRAP), *map(wire, raws)]) as server, patch.object(collector.os, 'unlink', side_effect=OSError):
            result = self.invoke(server)
            self.assertEqual(result[0], 0, result[2])
            self.assertTrue((result[1] / 'COMPLETE.json').exists())

    def test_later_corruption_requires_reverification_even_with_marker(self):
        raws = book_pages(limit=100)
        with peer([wire(BOOTSTRAP), *map(wire, raws)]) as server:
            out = self.assert_complete(self.invoke(server), raws)
        (out / 'page-00000000.json').write_bytes(raws[0] + b' ')
        self.assertTrue((out / 'COMPLETE.json').exists())
        self.assertFalse(facts.verify_dir(out)['ok'])

    def test_argument_validation_before_any_connection(self):
        invalid_endpoints = ['https://127.0.0.1:80', 'http://localhost:80', 'http://127.1:80',
            'http://2130706433:80', 'http://127.0.0.2:80', 'http://[::1]:80', 'http://0.0.0.0:80',
            'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:65536', 'http://127.0.0.1:080',
            'http://127.0.0.1:80/path', 'http://127.0.0.1:80?x', 'http://127.0.0.1:80#x',
            'http://user@127.0.0.1:80', 'http://127.0.0.1.evil:80', 'http://127.0.0.1.:80',
            'http://127.0.0.1:80\n', 'http://127.0.0.1:80\\evil']
        invalid_args = [['--endpoint', endpoint] for endpoint in invalid_endpoints]
        invalid_args += [[flag, value] for flag, value in (
            ('--limit', '0'), ('--limit', '501'), ('--max-pages', '-1'), ('--max-response-bytes', '0'),
            ('--max-total-bytes', '0'), ('--timeout', 'nan'), ('--timeout', 'inf'), ('--timeout', '0'))]
        with peer([]) as server:
            for options in invalid_args:
                with self.subTest(options=options), self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                    self.invoke(server, *options)
                self.assertEqual(cm.exception.code, 2)
            self.assertEqual(server.requests, [])
        self.assertEqual(collector.endpoint_port('http://127.0.0.1:8765/'), 8765)


if __name__ == '__main__':
    unittest.main()
