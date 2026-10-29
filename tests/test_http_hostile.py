"""Pinned hostile raw-HTTP corpus for the loopback server.

Every file in tests/vectors/http/ is a SIMULATED recipe: one raw request
(base64, with __PORT__/__TOKEN__ sentinels) plus the pinned outcome. These
tests replay each recipe on a raw socket against an in-process
make_server(0), assert the pinned status and error code, assert the response
leaks no traceback, token or repository path, and re-probe /api/state and
/api/health after every case. EXPECTED is written by hand: the generator must
not be its own oracle.
"""
import base64
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from capital.server import make_server

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests' / 'vectors'
HTTP = VECTORS / 'http'
SCRIPT = ROOT / 'scripts' / 'http_hostile.py'
_SENTINEL = re.compile(rb'__[A-Z]+__')
_NAME = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*\Z')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load('http_hostile', SCRIPT)
conformance = _load('storage_conformance', ROOT / 'tests' / 'storage_conformance.py')

# Written by hand on purpose: the generator must not be its own oracle.
# name -> (status, error code). status None pins "no HTTP status line".
EXPECTED = {
    'host-absent': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-suffix-evil': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-trailing-dot': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-ipv6': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-wrong-port': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-duplicated': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-folded': (403, 'LOOPBACK_HOST_REQUIRED'),
    'host-empty': (403, 'LOOPBACK_HOST_REQUIRED'),
    'origin-null': (403, 'ORIGIN_REJECTED'),
    'origin-cross-site': (403, 'ORIGIN_REJECTED'),
    'origin-trailing-slash': (403, 'ORIGIN_REJECTED'),
    'origin-duplicated': (403, 'ORIGIN_REJECTED'),
    'sec-fetch-cross-site': (403, 'CROSS_SITE_REJECTED'),
    'sec-fetch-same-site': (403, 'CROSS_SITE_REJECTED'),
    'path-dotdot': (404, 'NOT_FOUND'),
    'path-encoded-dots': (404, 'NOT_FOUND'),
    'path-encoded-traversal': (404, 'NOT_FOUND'),
    'path-backslash': (404, 'NOT_FOUND'),
    'path-nul': (404, 'NOT_FOUND'),
    'path-invalid-utf8': (404, 'NOT_FOUND'),
    'path-double-slash': (200, None),
    'path-absolute-form': (200, None),
    'path-authority-evil': (200, None),
    'path-root-normalized': (200, None),
    'target-invalid-ipv6': (400, 'INVALID_TARGET'),
    'target-unclosed-ipv6': (400, 'INVALID_TARGET'),
    'method-trace': (501, None),
    'method-options': (501, None),
    'method-head': (501, None),
    'method-unknown': (501, None),
    'method-lowercase-get': (501, None),
    'method-connect': (501, None),
    'request-line-overflow': (414, None),
    'request-line-bad-version': (None, None),
    'request-line-weird-version': (None, None),
    'request-line-one-word': (None, None),
    'request-line-four-words': (400, None),
    'request-line-no-version': (None, None),
    'blank-request': (None, None),
    'pipelined-extra-ignored': (200, None),
    'header-flood': (431, None),
    'header-line-overlong': (431, None),
    'header-no-colon': (200, None),
    'header-bare-cr': (200, None),
    'header-nul': (200, None),
    'expect-100-continue': (403, 'LOCAL_TOKEN_REQUIRED'),
    'post-no-token': (403, 'LOCAL_TOKEN_REQUIRED'),
    'post-token-bogus': (403, 'LOCAL_TOKEN_REQUIRED'),
    'post-token-duplicate': (403, 'LOCAL_TOKEN_REQUIRED'),
    'post-unknown-path': (404, 'NOT_FOUND'),
    'content-type-wrong': (415, 'JSON_REQUIRED'),
    'content-type-charset-suffix': (415, 'JSON_REQUIRED'),
    'length-missing': (400, 'INVALID_LENGTH'),
    'length-duplicate': (400, 'INVALID_LENGTH'),
    'length-nonnumeric': (400, 'INVALID_LENGTH'),
    'length-signed': (400, 'INVALID_LENGTH'),
    'length-comma': (400, 'INVALID_LENGTH'),
    'length-zero': (413, 'BODY_TOO_LARGE'),
    'body-over-8192-declared': (413, 'BODY_TOO_LARGE'),
    'body-over-8192-sent': (400, 'INVALID_SESSION'),
    'transfer-encoding-chunked': (400, 'INVALID_LENGTH'),
    'length-mismatch-short': (400, 'INVALID_JSON'),
    'length-mismatch-long': (400, 'INVALID_SESSION'),
    'body-invalid-utf8': (400, 'INVALID_JSON'),
    'body-bom': (400, 'INVALID_SESSION'),
    'body-nul': (400, 'INVALID_JSON'),
    'body-duplicate-keys': (400, 'INVALID_JSON'),
    'body-nan': (400, 'INVALID_JSON'),
    'body-infinity': (400, 'INVALID_JSON'),
    'body-neg-infinity': (400, 'INVALID_JSON'),
    'body-deep-nesting': (400, 'INVALID_SESSION'),
    'body-trailing-garbage': (400, 'INVALID_JSON'),
    'body-json-array': (400, 'INVALID_SESSION'),
    'body-json-scalar': (400, 'INVALID_SESSION'),
    'get-with-body-declared': (200, None),
    'get-transfer-encoding': (200, None),
}


def run_script(*argv):
    """Call script.main with its status lines swallowed; return (exit code, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main(list(argv))
    return code, err.getvalue()


def load_recipes():
    return {path.name[:-5]: json.loads(path.read_text(encoding='utf-8'))
            for path in sorted(HTTP.iterdir())}


def render_request(request, port, token):
    # Validate the template, not substituted data: token_urlsafe may emit __.
    # Keep rejecting unknown/malformed sentinels, and substitute only once so
    # even a token containing a sentinel's exact spelling remains opaque.
    replacements = {b'__PORT__': str(port).encode(), b'__TOKEN__': token.encode()}
    template = request
    for sentinel in replacements:
        template = template.replace(sentinel, b'')
    if b'__' in template:
        raise ValueError('unresolved request sentinel')
    return _SENTINEL.sub(lambda match: replacements[match.group()], request)


class RenderingTests(unittest.TestCase):
    def test_token_bytes_are_not_template_sentinels(self):
        for token in ('SIMULATED__token', 'SIMULATED__TOKEN____PORT__'):
            with self.subTest(token=token):
                self.assertEqual(
                    render_request(b'Host: __PORT__\r\nToken: __TOKEN__', 1234, token),
                    b'Host: 1234\r\nToken: ' + token.encode())

    def test_unknown_and_malformed_sentinels_are_rejected(self):
        for sentinel in (b'__UNKNOWN__', b'__TOKEN_', b'__token__', b'__'):
            with self.subTest(sentinel=sentinel), self.assertRaises(ValueError):
                render_request(b'__PORT__ __TOKEN__ ' + sentinel, 1234, 'SIMULATED')


def _split(raw):
    """(status, Content-Type value, body); skips a 100-continue preamble."""
    while True:
        head, sep, body = raw.partition(b'\r\n\r\n')
        status_line = head.split(b'\r\n', 1)[0]
        parts = status_line.split()
        status = None
        if len(parts) >= 2 and parts[0].startswith(b'HTTP/'):
            try:
                status = int(parts[1])
            except ValueError:
                status = None
        if status == 100 and sep:
            raw = body
            continue
        content_type = None
        if status is not None and sep:
            for line in head.split(b'\r\n')[1:]:
                name, colon, value = line.partition(b':')
                if colon and name.strip().lower() == b'content-type':
                    content_type = value.strip()
        return status, content_type, (body if sep else raw)


class ShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = load_recipes()

    def test_corpus_holds_exactly_the_pinned_files(self):
        self.assertEqual(sorted(self.recipes), sorted(EXPECTED))
        self.assertGreaterEqual(len(self.recipes), 30)

    def test_every_recipe_has_the_pinned_shape(self):
        for name, recipe in self.recipes.items():
            with self.subTest(vector=name):
                self.assertEqual(recipe['format'], 'KIX_CAPITAL_HTTP_HOSTILE_V1')
                self.assertEqual(recipe['label'], 'SIMULATED')
                self.assertEqual(recipe['name'], name)
                self.assertIsNotNone(_NAME.fullmatch(name))
                self.assertTrue(recipe['note'])
                request = base64.b64decode(recipe['request_b64'], validate=True)
                sentinels = set(_SENTINEL.findall(request))
                self.assertLessEqual(sentinels, {b'__PORT__', b'__TOKEN__'}, name)
                expect = recipe['expect']
                self.assertEqual(sorted(expect), [
                    'body_marker', 'code', 'content_type_prefix', 'status'])
                self.assertEqual(recipe['post_state'], {
                    'state_digest': 'UNCHANGED',
                    'operation_count': 'UNCHANGED',
                    'health_status': 200,
                })

    def test_recipe_pins_match_the_handwritten_oracle(self):
        for name, (status, code) in EXPECTED.items():
            with self.subTest(vector=name):
                expect = self.recipes[name]['expect']
                self.assertEqual((expect['status'], expect['code']), (status, code))


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.baseline = conformance._read_state(cls.port)
        cls.token = cls.baseline['local_token']
        cls.recipes = load_recipes()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def _probe_health(self):
        raw = conformance._exchange(self.port, conformance._join_request(
            'GET', '/api/health', [('Host', conformance._host(self.port))], b''))
        status, _body = conformance._split_response(raw)
        self.assertEqual(status, 200)

    def _assert_clean(self, raw):
        self.assertNotIn(b'Traceback', raw)
        self.assertNotIn(b'File "', raw)
        self.assertNotIn(self.token.encode(), raw)
        self.assertNotIn(os.fspath(ROOT).encode(), raw)

    def _assert_post_state(self):
        after = conformance._read_state(self.port)
        self.assertEqual(after['state_digest'], self.baseline['state_digest'])
        self.assertEqual(after['operation_count'], self.baseline['operation_count'])
        self._probe_health()

    def test_every_recipe_replays_its_pin(self):
        for name in sorted(self.recipes):
            recipe = self.recipes[name]
            with self.subTest(vector=name):
                expect = recipe['expect']
                self.assertEqual(
                    (expect['status'], expect['code']), EXPECTED[name])
                request = base64.b64decode(recipe['request_b64'])
                request = render_request(request, self.port, self.token)
                raw = conformance._exchange(self.port, request)
                self._assert_clean(raw)
                status, content_type, body = _split(raw)
                self.assertEqual(status, expect['status'], name)
                status_lines = sum(
                    1 for line in raw.split(b'\r\n') if line.startswith(b'HTTP/'))
                if expect['status'] is None:
                    self.assertEqual(status_lines, 0, name)
                    if expect['body_marker'] is None:
                        self.assertEqual(raw, b'', name)
                    else:
                        self.assertIn(expect['body_marker'].encode(), raw, name)
                else:
                    self.assertEqual(status_lines, 1, name)
                    prefix = expect['content_type_prefix']
                    self.assertIsNotNone(prefix, name)
                    self.assertIsNotNone(content_type, name)
                    self.assertTrue(
                        content_type.startswith(prefix.encode()), (name, content_type))
                    if expect['code'] is not None:
                        self.assertEqual(prefix, 'application/json')
                        self.assertEqual(json.loads(body)['error'], expect['code'], name)
                    if expect['body_marker'] is not None:
                        self.assertIn(expect['body_marker'].encode(), raw, name)
                self._assert_post_state()

    def test_state_is_still_the_baseline_after_the_whole_corpus(self):
        after = conformance._read_state(self.port)
        self.assertEqual(after['state_digest'], self.baseline['state_digest'])
        self.assertEqual(after['operation_count'], self.baseline['operation_count'])
        self._probe_health()
        self.assertTrue(self.thread.is_alive())


class ReplayUnderscoreTokenTests(ReplayTests):
    @classmethod
    def setUpClass(cls):
        # Reproduce the CI token collision on every run, with all corpus pins
        # and leak/state/health assertions inherited unchanged.
        with mock.patch('capital.auth.secrets.token_urlsafe', return_value='SIMULATED__TOKEN____PORT__'):
            super().setUpClass()


class RegenerationTests(unittest.TestCase):
    def committed(self):
        """Every file this script owns: everything under http/."""
        found = {}
        if HTTP.is_dir():
            for path in sorted(HTTP.iterdir()):
                if path.is_file():
                    found[f'{HTTP.name}/{path.name}'] = path.read_bytes()
        return found

    def test_regeneration_reproduces_the_committed_bytes(self):
        first = script.build_vectors()
        self.assertEqual(first, script.build_vectors())
        self.assertEqual(first, self.committed())

    def test_check_passes_on_the_committed_corpus(self):
        proc = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), '--check'],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_write_then_drift_missing_unexpected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'vectors'
            self.assertEqual(run_script('--write', '--dir', os.fspath(target))[0], 0)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)
            written = {
                path.relative_to(target).as_posix(): path.read_bytes()
                for path in sorted(target.rglob('*')) if path.is_file()
            }
            self.assertEqual(written, self.committed())

            victim = target / 'http' / 'host-absent.json'
            original = victim.read_bytes()
            victim.write_bytes(original.replace(b'"SIMULATED"', b'"REAL"', 1))
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            victim.write_bytes(original)
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            extra = target / 'http' / 'extra.json'
            extra.write_bytes(b'{}\n')
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)
            self.assertEqual(run_script('--write', '--dir', os.fspath(target))[0], 0)
            self.assertFalse(extra.exists())
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 0)

            victim.unlink()
            self.assertEqual(run_script('--check', '--dir', os.fspath(target))[0], 1)

    def test_check_writes_nothing(self):
        before = self.committed()
        self.assertEqual(run_script('--check'), (0, ''))
        self.assertEqual(self.committed(), before)


if __name__ == '__main__':
    unittest.main()
