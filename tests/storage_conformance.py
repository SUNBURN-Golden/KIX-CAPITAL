"""StoragePort conformance vectors, crash injection, and seeded chaos.

`run_storage_vectors(factory)` is the gate a future storage adapter must pass.
The factory is called once and must return a fresh port. Passing these vectors
is a local gate. It is not SEMANTIC_CONFORMANCE. CAP-11 stays NOT_BOUND.
`LOCAL_FILE_WORKSPACE` is a development-file label, not stage5 durable
transaction recovery, inbox/outbox, or cross-host fencing.

File-only checks run when `durable_label == 'LOCAL_FILE_WORKSPACE'`. Crash
injection and the HTTP fuzzer are separate runners. The fuzzer sends only
GET and POST. The stdlib handler returns 501 for other methods by design, so
those methods are not part of this boundary.

A failing seeded run prints `seed=<n>; reproduce: CAPITAL_CHAOS_SEED=<n>`.
Set that variable to rerun one sequence or the one fuzz stream. An invalid
value raises ValueError. Amounts and ids here are synthetic fixture units.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import random
import re
import socket
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import (
    FORMAT, FileWorkspace, WorkspaceError, canonical_bytes, verify_document,
)
from capital.verify import verify_path

BASE_SEED = 74810048
SEQUENCE_COUNT = 200
FUZZ_COUNT = 500
SEED_ENV = 'CAPITAL_CHAOS_SEED'
CRASH_STEPS = (
    'temp-open',
    'write-zero',
    'write-partial',
    'file-fsync',
    'replace',
    'dir-fsync',
)
_SEED_RE = re.compile(r'-?\d{1,18}\Z')
_ADVANCES = ('sim-ch-a', 'sim-ch-b', 'sim-ch-c')
_FIXTURES = (
    'sim-committed', 'sim-committed', 'sim-committed', 'sim-committed',
    'sim-pending', 'sim-refund', 'sim-missing',
)
_AMOUNTS = (1000, 2000, 5000, 10000, 20000)
_OPS = (
    'offer', 'approve', 'reject', 'cancel', 'bind_settlement',
    'draw', 'repay', 'close', 'default', 'reconcile',
)
FUZZ_CATEGORIES = (
    'host-absent',
    'host-wrong',
    'host-duplicated',
    'origin-mismatch',
    'sec-fetch-cross-site',
    'token-missing',
    'token-bogus',
    'token-duplicated',
    'content-type-wrong',
    'length-missing',
    'length-zero',
    'length-non-numeric',
    'length-duplicated',
    'length-over-8192',
    'transfer-encoding',
    'duplicate-json-keys',
    'bom',
    'nan',
    'deep-nesting',
    'nul-bytes',
    'body-over-declared',
    'truncated-body',
    'query-oversize',
    'query-duplicated',
    'unknown-path',
)


def seed_note(seed):
    return f'seed={seed}; reproduce: {SEED_ENV}={seed}'


def fail_seed(seed, detail):
    message = f'{detail} {seed_note(seed)}'
    print(message, file=sys.stderr, flush=True)
    raise AssertionError(message)


def env_seed():
    """The reproduction seed, or None when the variable is unset.

    An empty or non-integer value fails loudly. There is no silent default.
    """
    if SEED_ENV not in os.environ:
        return None
    raw = os.environ[SEED_ENV]
    if _SEED_RE.fullmatch(raw) is None:
        raise ValueError(
            f'{SEED_ENV} must be an integer seed of at most 18 digits, got {raw!r}')
    return int(raw)


def sequence_seeds():
    chosen = env_seed()
    if chosen is None:
        return [BASE_SEED + i for i in range(SEQUENCE_COUNT)]
    return [chosen]


def fuzz_stream_seed():
    chosen = env_seed()
    if chosen is None:
        return BASE_SEED
    return chosen


def run_storage_vectors(factory):
    """Run the adapter-agnostic vectors, plus file checks when the label matches."""
    if not callable(factory):
        raise AssertionError('StoragePort factory must be callable')
    port = factory()
    try:
        port.writer_instance = 'conformance-writer'
        _assert_fresh_empty(port)
        _assert_round_trip(port)
        _assert_replace(port)
        _assert_snapshot(port)
        _assert_rejects_non_dict(port)
        if getattr(port, 'durable_label', None) == 'LOCAL_FILE_WORKSPACE':
            _assert_second_open_locks(port)
            _assert_tamper_does_not_rewrite(port)
            _assert_stale_tmp_removed_on_open(port)
    finally:
        close = getattr(port, 'close', None)
        if callable(close):
            close()


def run_crash_vectors(directory_factory):
    """Inject one failure at each FileWorkspace write step. Return the step names."""
    if not callable(directory_factory):
        raise AssertionError('directory_factory must be callable')
    done = []
    for step in CRASH_STEPS:
        _run_crash_step(directory_factory, step)
        done.append(step)
    return tuple(done)


def run_command_sequences(storage_factories, seeds=None):
    """Replay seeded command sequences on each factory. Return the seeds used."""
    if not storage_factories:
        raise AssertionError('storage_factories is empty')
    if seeds is None:
        seeds = sequence_seeds()
    for seed in seeds:
        for factory in storage_factories:
            if not callable(factory):
                fail_seed(seed, 'storage factory is not callable')
            storage = factory()
            try:
                service = CapitalService(storage)
                _exercise(service, seed, _storage_label(storage))
            except AssertionError as exc:
                if 'reproduce:' not in str(exc):
                    fail_seed(seed, str(exc))
                raise
            except Exception as exc:
                fail_seed(seed, f'{_storage_label(storage)} {type(exc).__name__}: {exc}')
            finally:
                close = getattr(storage, 'close', None)
                if callable(close):
                    close()
    return tuple(seeds)


def run_http_fuzz(seed=None):
    """Send FUZZ_COUNT malformed loopback requests. Return (seed, count)."""
    if seed is None:
        seed = fuzz_stream_seed()
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, name='chaos-http', daemon=True)
    thread.start()
    try:
        port = server.server_port
        try:
            before = _read_state(port)
        except Exception as exc:
            fail_seed(seed, f'state probe before fuzz failed: {type(exc).__name__}: {exc}')
        token = before['local_token']
        digest = before['state_digest']
        count = before['operation_count']
        rng = random.Random(seed)
        for index in range(FUZZ_COUNT):
            category = rng.choice(FUZZ_CATEGORIES)
            try:
                payload = _build_fuzz_request(rng, port, token, category)
                response = _exchange(port, payload)
            except AssertionError as exc:
                if 'reproduce:' not in str(exc):
                    fail_seed(seed, f'fuzz[{index}] {category} {exc}')
                raise
            except Exception as exc:
                fail_seed(seed, f'fuzz[{index}] {category} {type(exc).__name__}: {exc}')
            status, _body = _split_response(response)
            if status is None:
                fail_seed(seed, f'fuzz[{index}] {category} no HTTP status')
            if status >= 500 and status != 503:
                fail_seed(seed, f'fuzz[{index}] {category} status {status}')
        if not thread.is_alive():
            fail_seed(seed, 'server thread exited')
        try:
            after = _read_state(port)
        except Exception as exc:
            fail_seed(seed, f'state probe after fuzz failed: {type(exc).__name__}: {exc}')
        if after['operation_count'] != count or after['state_digest'] != digest:
            fail_seed(seed, 'fuzz changed operation_count or state_digest')
        if after.get('funds_executed') is not False:
            fail_seed(seed, 'fuzz reported funds_executed')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    return seed, FUZZ_COUNT


def _storage_label(storage):
    if getattr(storage, 'durable_label', None) == 'LOCAL_FILE_WORKSPACE':
        return 'LOCAL_FILE_WORKSPACE'
    return 'MEMORY'


def _assert_fresh_empty(port):
    if port.load() is not None:
        raise AssertionError('fresh port load() must be None')


def _assert_envelope(port, loaded, payload):
    if type(loaded) is not dict:
        raise AssertionError('load did not return an envelope')
    if loaded.get('format') != FORMAT:
        raise AssertionError(f'format {loaded.get("format")!r}')
    if loaded.get('payload') != payload:
        raise AssertionError('payload mismatch')
    if loaded.get('saved_by_instance') != port.writer_instance:
        raise AssertionError('saved_by_instance')
    digest = hashlib.sha256(canonical_bytes(loaded['payload'])).hexdigest()
    if loaded.get('payload_sha256') != digest:
        raise AssertionError('payload_sha256')
    verify_document(loaded)


def _assert_round_trip(port):
    payload = {'label': 'SIMULATED', 'n': 1, 'nested': {'ok': True}}
    port.save(payload)
    _assert_envelope(port, port.load(), payload)


def _assert_replace(port):
    first = {'label': 'SIMULATED', 'n': 1}
    second = {'label': 'SIMULATED', 'n': 2}
    port.save(first)
    loaded_first = port.load()
    port.save(second)
    loaded_second = port.load()
    _assert_envelope(port, loaded_second, second)
    if loaded_second['payload_sha256'] == loaded_first['payload_sha256']:
        raise AssertionError('checksum did not change on replace')
    if loaded_first['payload'] != first:
        raise AssertionError('first envelope was aliased to the replacement')


def _assert_snapshot(port):
    payload = {'label': 'SIMULATED', 'nested': {'a': 1}}
    port.save(payload)
    payload['nested']['a'] = 9
    payload['extra'] = True
    loaded = port.load()
    if loaded['payload'] != {'label': 'SIMULATED', 'nested': {'a': 1}}:
        raise AssertionError('caller mutation leaked into the saved payload')


def _assert_rejects_non_dict(port):
    kept = {'label': 'SIMULATED', 'keep': 1}
    port.save(kept)
    before = port.load()
    for bad in (None, [], 'x', 1):
        try:
            port.save(bad)
        except WorkspaceError:
            pass
        else:
            raise AssertionError(f'non-dict payload {bad!r} was accepted')
        loaded = port.load()
        if loaded['payload'] != before['payload'] or loaded['payload_sha256'] != before['payload_sha256']:
            raise AssertionError('rejected payload replaced the last complete envelope')


def _assert_second_open_locks(port):
    try:
        second = FileWorkspace.open(port.directory)
    except WorkspaceError as exc:
        if exc.code != 'WORKSPACE_LOCKED':
            raise AssertionError(f'second open raised {exc.code}')
    else:
        second.close()
        raise AssertionError('second open did not lock')
    if port.load() is None:
        raise AssertionError('lock attempt cleared the open workspace')


def _assert_tamper_does_not_rewrite(port):
    path = Path(port.path)
    intact = path.read_bytes()
    loaded = port.load()
    truncated = intact[:12]
    path.write_bytes(truncated)
    try:
        _expect_unreadable(port, path, truncated, 'truncated')
    finally:
        path.write_bytes(intact)
    flipped = bytearray(intact)
    flipped[-1] ^= 0x01
    path.write_bytes(bytes(flipped))
    try:
        _expect_unreadable(port, path, bytes(flipped), 'tampered')
    finally:
        path.write_bytes(intact)
    restored = port.load()
    if restored['payload'] != loaded['payload'] or restored['payload_sha256'] != loaded['payload_sha256']:
        raise AssertionError('load after restoring bytes did not return the last complete file')


def _expect_unreadable(port, path, raw, label):
    try:
        port.load()
    except WorkspaceError as exc:
        if exc.code != 'WORKSPACE_UNREADABLE':
            raise AssertionError(f'{label} raised {exc.code}')
    else:
        raise AssertionError(f'{label} workspace was readable')
    if path.read_bytes() != raw:
        raise AssertionError(f'{label} workspace was rewritten')


def _assert_stale_tmp_removed_on_open(port):
    loaded = port.load()
    directory = Path(port.directory)
    intact = Path(port.path).read_bytes()
    port.close()
    stale = directory / '.workspace.json.chaos.tmp'
    stale.write_bytes(b'partial-not-a-book')
    keep = directory / 'keep.txt'
    keep.write_bytes(b'leave-me')
    reopened = FileWorkspace.open(directory)
    try:
        if stale.exists():
            raise AssertionError('stale temp survived open')
        if keep.read_bytes() != b'leave-me':
            raise AssertionError('open removed an unrelated file')
        again = reopened.load()
        if again['payload'] != loaded['payload'] or again['payload_sha256'] != loaded['payload_sha256']:
            raise AssertionError('stale cleanup changed the loaded envelope')
        if Path(reopened.path).read_bytes() != intact:
            raise AssertionError('stale cleanup rewrote workspace bytes')
    finally:
        reopened.close()


def _run_crash_step(directory_factory, step):
    directory = Path(directory_factory())
    port = FileWorkspace.open(directory)
    reopened = None
    try:
        port.writer_instance = 'crash-writer'
        baseline = {'label': 'SIMULATED', 'step': 'baseline', 'n': 1}
        attempted = {'label': 'SIMULATED', 'step': 'attempted', 'n': 2}
        port.save(baseline)
        before = Path(port.path).read_bytes()
        before_doc = port.load()
        _assert_envelope(port, before_doc, baseline)
        raised = None
        with _crash(step):
            try:
                port.save(attempted)
            except WorkspaceError as exc:
                raised = exc
        if raised is None or raised.code != 'WORKSPACE_WRITE_FAILED':
            raise AssertionError(f'{step}: save did not raise WORKSPACE_WRITE_FAILED')
        if not isinstance(raised.__cause__, OSError) or 'injected' not in str(raised.__cause__):
            raise AssertionError(f'{step}: injection did not cause the failure')
        temps = _temp_names(directory)
        if temps:
            raise AssertionError(f'{step}: temp left behind {temps}')
        raw = Path(port.path).read_bytes()
        if not raw:
            raise AssertionError(f'{step}: empty book')
        if step == 'dir-fsync':
            if raw == before:
                raise AssertionError('dir-fsync left the previous file instead of the new complete file')
            loaded = port.load()
            _assert_envelope(port, loaded, attempted)
            verify_document(json.loads(raw.decode('ascii')))
        else:
            if raw != before:
                raise AssertionError(f'{step}: workspace.json changed')
            loaded = port.load()
            _assert_envelope(port, loaded, baseline)
            if loaded['payload_sha256'] != before_doc['payload_sha256']:
                raise AssertionError(f'{step}: checksum drifted')
        port.close()
        reopened = FileWorkspace.open(directory)
        again = reopened.load()
        if again['payload'] != loaded['payload'] or again['payload_sha256'] != loaded['payload_sha256']:
            raise AssertionError(f'{step}: reopened load is not the last complete file')
        if not again['payload']:
            raise AssertionError(f'{step}: reopened book is empty')
    finally:
        port.close()
        if reopened is not None:
            reopened.close()


def _temp_names(directory):
    names = []
    for child in Path(directory).iterdir():
        if child.is_file() and child.name.startswith('.workspace.json.') and child.name.endswith('.tmp'):
            names.append(child.name)
    return names


@contextlib.contextmanager
def _crash(step):
    real_open = os.open
    real_write = os.write
    real_fsync = os.fsync
    real_replace = os.replace
    if step == 'temp-open':
        def fake_open(path, flags, mode=0o777, *, dir_fd=None):
            if flags & os.O_CREAT and flags & os.O_EXCL:
                raise OSError('injected temp open')
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(os, 'open', fake_open):
            yield
        return
    if step == 'write-zero':
        def fake_write(_fd, _data):
            raise OSError('injected write')

        with mock.patch.object(os, 'write', fake_write):
            yield
        return
    if step == 'write-partial':
        state = {'armed': True}

        def fake_write(fd, data):
            if state['armed']:
                state['armed'] = False
                if len(data) < 2:
                    raise OSError('injected short buffer')
                return real_write(fd, data[:1])
            raise OSError('injected write after partial')

        with mock.patch.object(os, 'write', fake_write):
            yield
        return
    if step == 'file-fsync':
        seen = {'n': 0}

        def fake_fsync(fd):
            seen['n'] += 1
            if seen['n'] == 1:
                raise OSError('injected file fsync')
            return real_fsync(fd)

        with mock.patch.object(os, 'fsync', fake_fsync):
            yield
        return
    if step == 'replace':
        def fake_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
            raise OSError('injected replace')

        with mock.patch.object(os, 'replace', fake_replace):
            yield
        return
    if step == 'dir-fsync':
        seen = {'n': 0}

        def fake_fsync(fd):
            seen['n'] += 1
            if seen['n'] == 2:
                raise OSError('injected directory fsync')
            return real_fsync(fd)

        with mock.patch.object(os, 'fsync', fake_fsync):
            yield
        return
    raise AssertionError(f'unknown crash step {step}')


def _blank_advance():
    return {'phase': 'NEW', 'bound': False, 'amount': 0, 'outstanding': 0, 'next_seq': 1}


def _likely_op(rng, state):
    phase = state['phase']
    if phase == 'NEW':
        return 'offer'
    if phase == 'OFFERED':
        return rng.choice(('approve', 'approve', 'approve', 'bind_settlement', 'reject', 'cancel', 'reconcile'))
    if phase == 'APPROVED':
        if not state['bound']:
            return rng.choice(('bind_settlement', 'bind_settlement', 'draw', 'cancel', 'reconcile'))
        return rng.choice(('draw', 'draw', 'draw', 'cancel', 'reconcile'))
    if phase == 'DRAWN':
        if state['outstanding'] > 0:
            return rng.choice(('repay', 'repay', 'repay', 'default', 'reconcile', 'close'))
        return rng.choice(('close', 'close', 'reconcile'))
    return 'reconcile'


def _args_for(rng, op, state):
    if op == 'offer':
        return {'fixture_id': rng.choice(_FIXTURES), 'amount': rng.choice(_AMOUNTS)}
    if op == 'repay':
        outstanding = state['outstanding']
        amount = outstanding if outstanding > 0 else 1
        if amount > 1 and rng.randrange(2) == 0:
            amount = max(1, amount // 2)
        if rng.randrange(12) == 0:
            amount = amount + 1
        sequence = state['next_seq']
        if rng.randrange(12) == 0:
            sequence = state['next_seq'] + 1
        return {'amount': amount, 'sequence': sequence}
    return {}


def _note_accepted(state, op, args):
    if op == 'offer':
        state['phase'] = 'OFFERED'
        state['amount'] = args['amount']
        state['bound'] = False
        state['outstanding'] = 0
        state['next_seq'] = 1
        return
    if op == 'approve':
        state['phase'] = 'APPROVED'
        return
    if op in {'reject', 'cancel', 'close', 'default'}:
        state['phase'] = 'TERMINAL'
        state['outstanding'] = 0
        return
    if op == 'bind_settlement':
        state['bound'] = True
        return
    if op == 'draw':
        state['phase'] = 'DRAWN'
        state['outstanding'] = state['amount']
        return
    if op == 'repay':
        state['outstanding'] = max(0, state['outstanding'] - args['amount'])
        state['next_seq'] += 1


def _next_command(rng, states, serial):
    advance_id = rng.choice(_ADVANCES)
    state = states[advance_id]
    if rng.randrange(100) < 78:
        op = _likely_op(rng, state)
    else:
        op = rng.choice(_OPS)
    return {
        'operation_id': f'ch-{serial}',
        'op': op,
        'advance_id': advance_id,
        'args': _args_for(rng, op, state),
    }


def _exercise(service, seed, label):
    rng = random.Random(seed)
    states = {advance_id: _blank_advance() for advance_id in _ADVANCES}
    issued = []
    serial = 0
    for _step in range(rng.randint(8, 16)):
        roll = rng.randrange(100)
        if issued and roll < 15:
            body = copy.deepcopy(rng.choice(issued))
        elif issued and roll < 27:
            prior = rng.choice(issued)
            serial += 1
            body = _next_command(rng, states, serial)
            body['operation_id'] = prior['operation_id']
            same = (
                body['op'] == prior['op']
                and body['advance_id'] == prior['advance_id']
                and body['args'] == prior['args']
            )
            if same:
                body['op'] = 'reconcile' if prior['op'] != 'reconcile' else 'approve'
                body['args'] = {}
        else:
            serial += 1
            body = _next_command(rng, states, serial)
            issued.append(copy.deepcopy(body))
        body['instance_id'] = service.instance_id
        try:
            result = service.execute(body)
        except ApiError:
            continue
        if result.get('transport_duplicate') or result.get('outcome') != 'ACCEPTED':
            continue
        _note_accepted(states[body['advance_id']], body['op'], body['args'])
    _assert_sequence(service, seed, label)


def _assert_sequence(service, seed, label):
    journal = service.machine.export_journal()
    replayed = service.producer.restored(journal)
    try:
        replay_digest = replayed.state_digest()
    finally:
        close = getattr(replayed, 'close', None)
        if callable(close) and replayed is not service.producer:
            close()
    live = service.machine.state_digest()
    if replay_digest != live:
        fail_seed(seed, f'{label} replay digest != state_digest')
    report = service.reconciliation()
    checks = report.get('checks')
    if report.get('status') != 'MATCHED' or type(checks) is not list or not checks:
        fail_seed(seed, f'{label} reconciliation {report.get("status")}')
    for row in checks:
        if row.get('status') != 'MATCHED':
            fail_seed(seed, f'{label} check {row.get("id")} {row.get("status")} {row.get("detail")}')
    manifest = service.export_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'manifest.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        verified = verify_path(path)
    if verified.get('ok') is not True:
        fail_seed(seed, f'{label} verifier {verified.get("reason")}')


def _host(port):
    return f'127.0.0.1:{port}'


def _join_request(method, path, header_pairs, body):
    lines = [f'{method} {path} HTTP/1.0'.encode('ascii')]
    for name, value in header_pairs:
        lines.append(f'{name}: {value}'.encode('ascii'))
    return b'\r\n'.join(lines) + b'\r\n\r\n' + body


def _post_headers(host, token, length, content_type='application/json'):
    return [
        ('Host', host),
        ('X-Capital-Token', token),
        ('Content-Type', content_type),
        ('Content-Length', str(length)),
    ]


def _build_fuzz_request(rng, port, token, category):
    host = _host(port)
    if category == 'host-absent':
        return _join_request('GET', '/api/state', [('Accept', 'application/json')], b'')
    if category == 'host-wrong':
        return _join_request('GET', '/api/state', [('Host', 'evil.example')], b'')
    if category == 'host-duplicated':
        return _join_request('GET', '/api/state', [('Host', host), ('Host', 'evil.example')], b'')
    if category == 'origin-mismatch':
        return _join_request(
            'GET', '/api/state', [('Host', host), ('Origin', 'http://evil.example')], b'')
    if category == 'sec-fetch-cross-site':
        return _join_request(
            'GET', '/api/state', [('Host', host), ('Sec-Fetch-Site', 'cross-site')], b'')
    if category == 'token-missing':
        body = b'{}'
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
        ], body)
    if category == 'token-bogus':
        body = b'{}'
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', 'not-a-real-token'),
            ('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
        ], body)
    if category == 'token-duplicated':
        body = b'{}'
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', token), ('X-Capital-Token', 'other-token'),
            ('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
        ], body)
    if category == 'content-type-wrong':
        body = b'{"a":1}'
        kind = rng.choice(('text/plain', 'application/json; charset=utf-8'))
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body), kind), body)
    if category == 'length-missing':
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', token), ('Content-Type', 'application/json'),
        ], b'{}')
    if category == 'length-zero':
        return _join_request('POST', '/api/commands', _post_headers(host, token, 0), b'')
    if category == 'length-non-numeric':
        bad = rng.choice(('nope', '-1', '1.5', '8192x'))
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', token),
            ('Content-Type', 'application/json'), ('Content-Length', bad),
        ], b'{}')
    if category == 'length-duplicated':
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', token), ('Content-Type', 'application/json'),
            ('Content-Length', '2'), ('Content-Length', '4'),
        ], b'{}')
    if category == 'length-over-8192':
        declared = rng.choice((8193, 9000, 20000))
        return _join_request('POST', '/api/commands', _post_headers(host, token, declared), b'')
    if category == 'transfer-encoding':
        body = b'notjs'
        return _join_request('POST', '/api/commands', [
            ('Host', host), ('X-Capital-Token', token), ('Content-Type', 'application/json'),
            ('Content-Length', str(len(body))), ('Transfer-Encoding', 'chunked'),
        ], body)
    if category == 'duplicate-json-keys':
        body = b'{"a":1,"a":2}'
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body)), body)
    if category == 'bom':
        body = b'\xef\xbb\xbf{"a":1}'
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body)), body)
    if category == 'nan':
        body = rng.choice((b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'))
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body)), body)
    if category == 'deep-nesting':
        depth = 900
        body = ('{"a":' * depth + '1' + '}' * depth).encode('ascii')
        if len(body) > 8192:
            raise AssertionError('deep nesting body exceeds the designed limit')
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body)), body)
    if category == 'nul-bytes':
        body = b'{"a":"\x00"}'
        return _join_request('POST', '/api/commands', _post_headers(host, token, len(body)), body)
    if category == 'body-over-declared':
        declared = b'{"x"'
        extra = b'Y' * rng.randint(8, 64)
        return _join_request(
            'POST', '/api/commands', _post_headers(host, token, len(declared)), declared + extra)
    if category == 'truncated-body':
        body = b'{"truncated":'
        return _join_request('POST', '/api/commands', _post_headers(host, token, 120), body)
    if category == 'query-oversize':
        width = rng.randint(2000, 6000)
        return _join_request('GET', '/api/state?pad=' + ('A' * width), [('Host', host)], b'')
    if category == 'query-duplicated':
        return _join_request(
            'GET', '/api/projection?mode=simulation&mode=operating', [('Host', host)], b'')
    if category == 'unknown-path':
        suffix = ''.join(rng.choice('abcde012345') for _ in range(8))
        return _join_request('GET', f'/api/not-bound-{suffix}', [('Host', host)], b'')
    raise AssertionError(f'unknown fuzz category {category}')


def _exchange(port, payload, timeout=5):
    sock = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    try:
        sock.sendall(payload)
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        sock.settimeout(timeout)
        chunks = []
        while True:
            try:
                block = sock.recv(8192)
            except TimeoutError:
                break
            if not block:
                break
            chunks.append(block)
        return b''.join(chunks)
    finally:
        sock.close()


def _split_response(raw):
    if not raw:
        return None, b''
    head, sep, body = raw.partition(b'\r\n\r\n')
    status_line = head.split(b'\r\n', 1)[0]
    parts = status_line.split()
    if len(parts) < 2 or not parts[0].startswith(b'HTTP/'):
        return None, body if sep else b''
    try:
        status = int(parts[1])
    except ValueError:
        return None, body if sep else b''
    return status, body if sep else b''


def _read_state(port):
    raw = _exchange(port, _join_request(
        'GET', '/api/state', [('Host', _host(port)), ('Accept', 'application/json')], b''))
    status, body = _split_response(raw)
    if status != 200:
        raise AssertionError(f'state probe status {status}')
    return json.loads(body.decode('utf-8'))
