"""Executable CLAIM_CONFORMANCE checks binding the loopback facade and the
opt-in LOCAL_FILE_WORKSPACE file workspace to the pinned
docs/contracts/READINESS_RUNTIME.md boundary prose (kix-protocol
7481b0e16ce9b903abbffa62249bb91cd9e63cfe, the vendor pin — same SHA, a new
consumption scope named here per the repin policy's §3.1 consumer rule).

Each row in tests/readiness_claims.json cites a pinned section and needle,
names the Capital surface it observes, and stores the value that check must
observe on a live loopback server. READINESS_RUNTIME.md governs the
upstream `readiness/` journal wrapper (`journal.v1`, `KIXRDY01`, CRC32
records). Capital does not vendor or implement that journal format: its
single-file `LOCAL_FILE_WORKSPACE` and in-memory service are compared as an
analogue of the boundary rules only. Two pinned behaviors Capital does not
share — torn-tail prefix salvage and record-first receipt semantics — are
recorded as DOCUMENTED_DIVERGENCE rows whose rationale needles are
re-verified against the operator handbook, not as passes.

The comparisons are local and SIMULATED. Fault injection (`_FailingSave`,
`_LostTransport`) is labeled simulated in the row claim text. Nothing here
is a producer-profile adoption, stage5 durable transactions, or a money
movement. A protocol checkout is optional: the drift script reads that
tree and does not write it. With no checkout the drift status is SKIPPED,
which is not a pass.
"""
from __future__ import annotations

import http.client
import inspect
import json
import re
import tempfile
import threading
from pathlib import Path

from capital import upstream_claims
from capital.gate_producer import TransportLost
from capital.resources import ROOT
from capital.server import make_server
from capital.store import FileWorkspace, WorkspaceError
from capital.upstream_claims import ClaimTableError

PINNED_SHA = upstream_claims.PINNED_SHA
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_READINESS_CLAIMS_V1'
REQUIRED_FIELDS = upstream_claims.REQUIRED_FIELDS + ('surface',)
SOURCE_DOC = 'docs/contracts/READINESS_RUNTIME.md'
NOTE_DOC = 'docs/OPERATOR_HANDBOOK_KO.md'
NOTE_SECTION = '### readiness-runtime-claims'
DIVERGENCE_DISPOSITION = 'DOCUMENTED_DIVERGENCE'
DISPOSITIONS = ('CONFORMANCE', DIVERGENCE_DISPOSITION)
DIVERGENCE_CHECKS = ('readiness.torn_tail', 'readiness.failed_save_lookup')
DIVERGENCE_FIELDS = ('capital_note', 'note_section', 'rationale_needle',
                     'upstream_behavior', 'capital_behavior')
SURFACES = (
    'server bind', 'GET /api/state', 'POST /api/commands',
    'GET /api/operations/{id}', 'GET /api/health', 'GET /api/readiness',
    'FileWorkspace.open',
)
FIXTURE_ID = 'sim-committed'
OFFER_ARGS = {'fixture_id': FIXTURE_ID, 'amount': 500}


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'readiness_claims.json'


def load_table(path=None):
    data = upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    validate_table(data)
    return data


def validate_table(data):
    upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    for claim in data['claims']:
        if claim['source_doc'] != SOURCE_DOC:
            raise ClaimTableError(f'claim {claim["id"]} source_doc is not the readiness boundary doc')
        surface = claim.get('surface')
        if type(surface) is not str or surface not in SURFACES:
            raise ClaimTableError(f'claim {claim["id"]} surface is not a bound surface')
        disposition = claim.get('disposition', 'CONFORMANCE')
        if disposition not in DISPOSITIONS:
            raise ClaimTableError(f'claim {claim["id"]} has an unknown disposition')
        if claim['check_id'] in DIVERGENCE_CHECKS and disposition != DIVERGENCE_DISPOSITION:
            raise ClaimTableError(f'claim {claim["id"]} must record its documented divergence')
        divergence = claim.get('divergence')
        if disposition == DIVERGENCE_DISPOSITION:
            if claim['check_id'] not in DIVERGENCE_CHECKS:
                raise ClaimTableError(
                    f'claim {claim["id"]} records a divergence with a non-divergence check')
            if type(divergence) is not dict:
                raise ClaimTableError(f'claim {claim["id"]} is missing divergence')
            if divergence.get('capital_note') != NOTE_DOC:
                raise ClaimTableError(f'claim {claim["id"]} cites a wrong divergence note')
            if divergence.get('note_section') != NOTE_SECTION:
                raise ClaimTableError(f'claim {claim["id"]} cites a wrong divergence section')
            for field in DIVERGENCE_FIELDS:
                value = divergence.get(field)
                if type(value) is not str or not value.strip():
                    raise ClaimTableError(f'claim {claim["id"]} divergence is missing {field}')
        elif divergence is not None:
            raise ClaimTableError(f'claim {claim["id"]} carries divergence without the disposition')
    return data


def run_claims(table):
    """Run every check against a live loopback server. An unmapped check fails that claim only."""
    validate_table(table)
    rows = []
    for claim in table['claims']:
        check_id = claim['check_id']
        expected = claim['expected']
        disposition = claim.get('disposition', 'CONFORMANCE')
        if check_id not in CHECKS:
            rows.append({
                'id': claim['id'],
                'check_id': check_id,
                'ok': False,
                'unmapped': True,
                'observed': None,
                'expected': expected,
                'disposition': disposition,
            })
            continue
        try:
            observed = CHECKS[check_id](claim)
        except Exception as exc:
            observed = {'error': type(exc).__name__, 'detail': str(exc)}
        rows.append({
            'id': claim['id'],
            'check_id': check_id,
            'ok': observed == expected,
            'unmapped': False,
            'observed': observed,
            'expected': expected,
            'disposition': disposition,
        })
    failed = [row for row in rows if not row['ok']]
    return {
        'label': LABEL,
        'passed': sum(row['ok'] and row['disposition'] != DIVERGENCE_DISPOSITION
                      for row in rows),
        'total': len(rows),
        'failed': failed,
        'rows': rows,
        'ok': not failed,
        'documented_divergences': [
            row['id'] for row in rows
            if row['disposition'] == DIVERGENCE_DISPOSITION and row['ok']
        ],
    }


def check_protocol(protocol_dir, table=None):
    """Read cited headings and needles. Never writes the checkout."""
    if table is None:
        table = load_table()
    else:
        validate_table(table)
    return upstream_claims.check_protocol(
        protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def _note_text():
    note_path = Path(str(ROOT)).resolve().parent / NOTE_DOC
    return note_path.read_text(encoding='utf-8')


def _note_section(text, heading):
    index = text.find(heading)
    if index < 0:
        return None
    rest = text[index + len(heading):]
    boundary = re.search(r'\n#{2,3} ', rest)
    return rest[:boundary.start()] if boundary else rest


def _note_cited(divergence):
    if divergence.get('capital_note') != NOTE_DOC:
        return False
    if divergence.get('note_section') != NOTE_SECTION:
        return False
    section = _note_section(_note_text(), NOTE_SECTION)
    return section is not None and divergence.get('rationale_needle', '') in section


class _LiveServer:
    """One loopback HTTP server on an ephemeral port. SIMULATED; not a deployment.

    `workspace` is a directory path for the opt-in LOCAL_FILE_WORKSPACE file,
    or None for the default in-memory storage.
    """

    def __init__(self, workspace=None, producer=None):
        self.server = make_server(0, workspace=workspace, producer=producer)
        # Keep real HTTP dispatch, but avoid the default half-second idle wait
        # at shutdown for every isolated claim and mutation probe.
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self._token = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self):
        try:
            self.server.shutdown()
        finally:
            self.server.server_close()
            self.thread.join(5)

    @property
    def service(self):
        return self.server.service

    @property
    def instance_id(self):
        return self.server.service.instance_id

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.request(method, path, body=body, headers=headers or {})
            response = client.getresponse()
            raw, status = response.read(), response.status
        finally:
            client.close()
        return status, raw

    def get(self, path):
        status, raw = self.request('GET', path)
        return status, json.loads(raw)

    def post(self, path, body):
        status, raw = self.request('POST', path, json.dumps(body), {
            'Content-Type': 'application/json', 'X-Capital-Token': self.token()})
        return status, json.loads(raw)

    def token(self):
        if self._token is None:
            status, state = self.get('/api/state')
            if status != 200:
                raise ClaimTableError('bootstrap state was not served')
            self._token = state['local_token']
        return self._token

    def command(self, operation_id, advance_id, op='offer', args=None):
        return {
            'instance_id': self.instance_id,
            'operation_id': operation_id,
            'op': op,
            'advance_id': advance_id,
            'args': OFFER_ARGS if args is None else args,
        }

    def offer(self, operation_id, advance_id):
        return self.post('/api/commands', self.command(operation_id, advance_id))

    def foreign_host_probe(self, host):
        """One GET with a non-loopback Host header. SIMULATED boundary probe."""
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.putrequest('GET', '/api/state', skip_host=True, skip_accept_encoding=True)
            client.putheader('Host', host)
            client.endheaders()
            response = client.getresponse()
            raw, status = response.read(), response.status
        finally:
            client.close()
        return status, json.loads(raw)


class _FailingSave:
    """SIMULATED storage-port fault, not an OS lock-loss detector."""

    def __init__(self, storage):
        self._storage = storage

    def arm(self, code='WORKSPACE_WRITE_FAILED'):
        def fail(*_args, **_kwargs):
            raise WorkspaceError(code)
        self._storage.save = fail


class _LostTransport:
    """SIMULATED producer fault: the armed idempotency key loses its response."""

    def __init__(self, inner, armed_key):
        self._inner = inner
        self._armed = armed_key
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def apply(self, op, advance_id, *, idempotency_key, args, bound_settlement_id):
        self.calls += 1
        if idempotency_key == self._armed:
            raise TransportLost(idempotency_key)
        return self._inner.apply(
            op, advance_id, idempotency_key=idempotency_key, args=args,
            bound_settlement_id=bound_settlement_id)


def _journal_len(live):
    return len(live.service.machine.export_journal())


def _workspace_bytes(directory):
    path = Path(directory) / 'workspace.json'
    return path.read_bytes() if path.is_file() else None


def check_bind_loopback(claim):
    params = set(inspect.signature(make_server).parameters)
    with _LiveServer() as live:
        return {
            'bound_host': live.server.server_address[0],
            'host_parameter_present': 'host' in params,
        }


def check_host_rejected(claim):
    with _LiveServer() as live:
        probes = []
        for host in ('0.0.0.0', 'not-loopback.example'):
            status, body = live.foreign_host_probe(host)
            probes.append({'host': host, 'status': status, 'error': body.get('error')})
        return {'probe_results': probes}


def check_replay_first_result(claim):
    with _LiveServer() as live:
        command = live.command('op-replay', 'sim-replay')
        first_status, first = live.post('/api/commands', command)
        second_status, second = live.post('/api/commands', command)
        lookup_status, lookup = live.get(
            f'/api/operations/op-replay?instance_id={live.instance_id}')
        return {
            'first_status': first_status,
            'second_status': second_status,
            'duplicate_flag': second.get('transport_duplicate'),
            'result_equal': second.get('result') == first.get('result'),
            'lookup_status': lookup_status,
            'lookup_equal': lookup == first,
        }


def check_replay_journal_once(claim):
    with _LiveServer() as live:
        command = live.command('op-once', 'sim-once')
        live.post('/api/commands', command)
        live.post('/api/commands', command)
        _status, state = live.get('/api/state')
        return {
            'journal_entries': _journal_len(live),
            'operation_count': state['operation_count'],
        }


def check_reads_do_not_grow(claim):
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            live.offer('op-reads', 'sim-reads')
            digest = live.service.machine.state_digest()
            canonical = live.service.machine.canonical_state()
            bytes_before = _workspace_bytes(tmp)
            journal_before = _journal_len(live)
            reads = [
                '/api/state', f'/api/operations/op-reads?instance_id={live.instance_id}',
                '/api/health', '/api/readiness', '/api/reconciliation',
                '/api/export', '/api/metrics',
            ]
            statuses = [live.get(path)[0] for path in reads]
            _status, state = live.get('/api/state')
            return {
                'reads': len(reads),
                'all_200': all(status == 200 for status in statuses),
                'journal_entries': _journal_len(live) == journal_before and journal_before == 1,
                'operation_count': state['operation_count'],
                'canonical_state_equal': live.service.machine.canonical_state() == canonical,
                'state_digest_equal': live.service.machine.state_digest() == digest,
                'workspace_bytes_equal': _workspace_bytes(tmp) == bytes_before,
            }


def check_lock_contention(claim):
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            try:
                FileWorkspace.open(tmp).close()
                open_error = None
            except WorkspaceError as exc:
                open_error = exc.code
            with _LiveServer(workspace=tmp) as second:
                view = second.service.workspace_view()
                status, body = second.post(
                    '/api/commands', second.command('op-locked', 'sim-locked'))
            return {
                'open_error': open_error,
                'workspace_status': view['status'],
                'post_status': status,
                'post_error': body.get('error'),
            }


def check_lock_loss_fails_closed(claim):
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            bytes_before = _workspace_bytes(tmp)
            _FailingSave(live.service.storage).arm('WORKSPACE_LOCKED')
            first_status, first = live.offer('op-fail-closed', 'sim-fail-closed')
            second_status, second = live.offer('op-after-fail', 'sim-after-fail')
            _status, health = live.get('/api/health')
            return {
                'first_status': first_status,
                'first_error': first.get('error'),
                'second_status': second_status,
                'second_error': second.get('error'),
                'health_status': health.get('status'),
                'file_bytes_unchanged': _workspace_bytes(tmp) == bytes_before,
            }


def check_failed_save_lookup(claim):
    divergence = claim['divergence']
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            _FailingSave(live.service.storage).arm()
            post_status, post = live.offer('op-failed-save', 'sim-failed-save')
            lookup_status, lookup = live.get(
                f'/api/operations/op-failed-save?instance_id={live.instance_id}')
            return {
                'post_status': post_status,
                'post_error': post.get('error'),
                'lookup_status': lookup_status,
                'lookup_outcome': lookup.get('outcome'),
                'divergent': lookup.get('outcome') == 'ACCEPTED' and post_status == 503,
                'note_cited': _note_cited(divergence),
            }


def check_lost_response_unknown(claim):
    with _LiveServer() as live:
        live.service.producer = _LostTransport(live.service.producer, 'op-lost')
        journal_before = _journal_len(live)
        post_status, post = live.offer('op-lost', 'sim-lost')
        _status, lookup = live.get(
            f'/api/operations/op-lost?instance_id={live.instance_id}')
        _status, absent = live.get(
            f'/api/operations/op-absent?instance_id={live.instance_id}')
        _status, state = live.get('/api/state')
        journal_entries = _journal_len(live)
    with _LiveServer() as fresh:
        _status, fresh_lookup = fresh.get(
            f'/api/operations/op-lost?instance_id={fresh.instance_id}')
    return {
        'post_status': post_status,
        'post_outcome': post.get('outcome'),
        'retry_authorized': post.get('retry_authorized'),
        'lookup_outcome': lookup.get('outcome'),
        'absent_lookup_outcome': absent.get('outcome'),
        'fresh_lookup_outcome': fresh_lookup.get('outcome'),
        'journal_entries': journal_entries == journal_before == 0,
        'operation_count': state['operation_count'],
        'producer_calls': live.service.producer.calls,
    }


def check_durable_false(claim):
    with _LiveServer() as memory:
        _status, memory_state = memory.get('/api/state')
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            live.offer('op-durable', 'sim-durable')
            _status, state = live.get('/api/state')
            case_durable = [case['durable'] for case in state['cases']]
            return {
                'memory_durable': memory_state['durable'],
                'workspace_durable': state['durable'],
                'case_durable': case_durable,
            }


def check_durable_not_claimed(claim):
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            live.offer('op-not-claimed', 'sim-not-claimed')
            _status, readiness = live.get('/api/readiness')
            _status, export = live.get('/api/export')
            _status, statement = live.get('/api/statement')
            _status, reconciliation = live.get('/api/reconciliation')
            groups = {group['id']: group['status'] for group in readiness['groups']}
            return {
                'durable_finance_group': groups.get('durable-finance'),
                'producer_binding_group': groups.get('producer-binding'),
                'export_durable': export['durable'],
                'statement_durable': statement['durable'],
                'reconciliation_durable': reconciliation['durable'],
            }


def check_torn_tail(claim):
    divergence = claim['divergence']
    with tempfile.TemporaryDirectory() as tmp:
        with _LiveServer(workspace=tmp) as live:
            live.offer('op-torn', 'sim-torn')
        path = Path(tmp) / 'workspace.json'
        original = path.read_bytes()
        path.write_bytes(original[:len(original) // 2])
        truncated = path.read_bytes()
        with _LiveServer(workspace=tmp) as reopened:
            _status, state = reopened.get('/api/state')
            post_status, post = reopened.offer('op-after-torn', 'sim-after-torn')
            return {
                'workspace_status': state['workspace']['status'],
                'case_count': len(state['cases']),
                'post_status': post_status,
                'post_error': post.get('error'),
                'bytes_unchanged': path.read_bytes() == truncated,
                'divergent': state['workspace']['status'] == 'WORKSPACE_UNREADABLE',
                'note_cited': _note_cited(divergence),
            }


def check_not_bound(claim):
    with _LiveServer() as live:
        _status, readiness = live.get('/api/readiness')
        groups = {group['id']: group['status'] for group in readiness['groups']}
        notes = readiness['requirement_notes']
        return {
            'production_authorized': readiness['production_authorized'],
            'upstream_binding': readiness['upstream_binding'],
            'cap16_note': 'CAP-16' in notes,
            'cap11_surface_not_local': groups.get('durable-finance') != 'AVAILABLE_LOCAL',
            'cap16_surface_not_local': groups.get('producer-binding') != 'AVAILABLE_LOCAL',
        }


CHECKS = {
    'readiness.bind_loopback': check_bind_loopback,
    'readiness.host_rejected': check_host_rejected,
    'readiness.replay_first_result': check_replay_first_result,
    'readiness.replay_journal_once': check_replay_journal_once,
    'readiness.reads_do_not_grow': check_reads_do_not_grow,
    'readiness.lock_contention': check_lock_contention,
    'readiness.lock_loss_fails_closed': check_lock_loss_fails_closed,
    'readiness.failed_save_lookup': check_failed_save_lookup,
    'readiness.lost_response_unknown': check_lost_response_unknown,
    'readiness.durable_false': check_durable_false,
    'readiness.durable_not_claimed': check_durable_not_claimed,
    'readiness.torn_tail': check_torn_tail,
    'readiness.not_bound': check_not_bound,
}
