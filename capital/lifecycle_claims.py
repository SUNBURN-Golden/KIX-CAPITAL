"""Local lifecycle analogues over disposable loopback HTTP, never full compliance.

The source pin is independent of the older FSM vendor pin. UNKNOWN fencing in
Client is a synthetic client adapter, not a server-wide prohibition or proof of
browser behavior. LC-TERM operational closure, LC-FACT custody and distributed
LC-CUT lease fencing remain outside this table.
"""
from __future__ import annotations

import copy
import http.client
import json
import socket
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from capital import upstream_claims
from capital.gate_producer import TransportLost
from capital.server import make_server
from capital.producer import PinnedFsmProducer
from capital.upstream_claims import ClaimTableError

PINNED_SHA = 'e2313ab473ea1b5a7b5b9246a564749188c1c2c8'
SOURCE_DOC = 'docs/contracts/STATE_LIFECYCLE.md'
FORMAT = 'KIX_CAPITAL_LIFECYCLE_CLAIMS_V1'
LABEL = 'CLAIM_CONFORMANCE'
LABELS = {'label': LABEL, 'simulation': 'SIMULATED', 'funds_executed': False}


def table_path(path=None):
    return Path(path) if path is not None else upstream_claims.table_path().with_name('lifecycle_claims.json')


def load_table(path=None):
    data = upstream_claims.load_table(table_path(path), format=FORMAT, pinned_sha=PINNED_SHA)
    return validate_table(data)


def validate_table(data):
    upstream_claims.validate_table(data, format=FORMAT, pinned_sha=PINNED_SHA)
    if data.get('simulation') != 'SIMULATED' or data.get('funds_executed') is not False:
        raise ClaimTableError('lifecycle table must be SIMULATED with funds_executed false')
    covered = set()
    for row in data['claims']:
        if row['source_doc'] != SOURCE_DOC:
            raise ClaimTableError('lifecycle source_doc must be ' + SOURCE_DOC)
        if row.get('clause') not in ('LC-TERM', 'LC-FACT', 'LC-CUT'):
            raise ClaimTableError('unknown lifecycle clause')
        if not row['section'].startswith('#') or not row['needle'].strip():
            raise ClaimTableError('lifecycle citation needs a heading and needle')
        if type(row.get('mapping')) is not str or not row['mapping'].strip():
            raise ClaimTableError('lifecycle row needs a limited local mapping')
        if row['check_id'] not in CHECKS:
            raise ClaimTableError('unknown lifecycle check_id: ' + row['check_id'])
        covered.add(row['check_id'])
    if covered != set(CHECKS):
        raise ClaimTableError('lifecycle table must cover every required behavior')
    if {r['clause'] for r in data['claims']} != {'LC-TERM', 'LC-FACT', 'LC-CUT'}:
        raise ClaimTableError('lifecycle table must cover all three clauses')
    return data


def run_claims(table):
    validate_table(table)
    report = upstream_claims.run_claims(table, checks=CHECKS, format=FORMAT, pinned_sha=PINNED_SHA)
    report.update(LABELS)
    for row in report['rows']:
        row.update(LABELS)
    return report


def check_protocol(protocol_dir, table=None):
    table = load_table() if table is None else validate_table(table)
    if protocol_dir is None or not str(protocol_dir).strip():
        return {**LABELS, 'status': 'SKIPPED', 'drift': 'not-run', 'verified': 0,
                'total': len(table['claims']), 'missing': []}
    report = upstream_claims.check_protocol(protocol_dir, table, format=FORMAT, pinned_sha=PINNED_SHA)
    report.update(LABELS)
    # Verify provenance as well as needles. A different HEAD is fine only if the
    # cited working file still equals the exact blob at the declared commit.
    try:
        blob = subprocess.run(
            ['git', '-C', str(protocol_dir), 'show', f'{PINNED_SHA}:{SOURCE_DOC}'],
            capture_output=True, check=True, timeout=10).stdout
        path = (Path(protocol_dir) / SOURCE_DOC).resolve()
        if not path.is_relative_to(Path(protocol_dir).resolve()):
            raise ValueError('source escapes checkout')
        if path.read_bytes() != blob:
            raise ValueError('working source differs from pinned commit')
    except (OSError, ValueError, subprocess.SubprocessError):
        report['missing'].append({'id': '*', 'problem': 'pinned source identity unavailable or changed'})
    # Require each needle inside its cited section, not elsewhere in the file.
    if not report['missing']:
        lines = blob.decode('utf-8').splitlines()
        for row in table['claims']:
            try:
                start = lines.index(row['section'])
                level = len(row['section']) - len(row['section'].lstrip('#'))
                end = next((i for i in range(start + 1, len(lines))
                            if lines[i].startswith('#') and
                            len(lines[i]) - len(lines[i].lstrip('#')) <= level), len(lines))
                if row['needle'] not in '\n'.join(lines[start:end]):
                    raise ValueError('needle outside section')
            except ValueError:
                report['missing'].append({'id': row['id'], 'problem': 'missing section-local needle'})
    report['status'] = 'failed' if report['missing'] else 'verified'
    report['verified'] = 0 if any(r['id'] == '*' for r in report['missing']) else (
        len(table['claims']) - len({r['id'] for r in report['missing']}))
    return report


def _assert_no_funds(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'funds_executed' and item is not False:
                raise ClaimTableError('facade reported funds execution')
            _assert_no_funds(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_funds(item)


class Client:
    """SIMULATED client-owned UNKNOWN fence; no automatic command resubmission."""
    def __init__(self, server):
        self.server = server
        self.requests = []
        self.unresolved = set()
        self.elapsed = 0
        status, state = self.request('GET', '/api/state')
        if status != 200:
            raise ClaimTableError('loopback state bootstrap failed')
        self.token, self.instance = state['local_token'], state['instance_id']

    def request(self, method, path, body=None, token=None):
        self.requests.append((method, path))
        headers = {'Content-Type': 'application/json'}
        credential = token if token is not None else getattr(self, 'token', None)
        if credential is not None:
            headers['X-Capital-Token'] = credential
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            value = json.loads(response.read())
            _assert_no_funds(value)
            return response.status, value
        finally:
            connection.close()

    def body(self, key='sim-first', op='offer', args=None):
        return {'instance_id': self.instance, 'operation_id': key, 'op': op,
                'advance_id': 'sim-lifecycle',
                'args': {'fixture_id': 'sim-committed', 'amount': 100} if args is None else args}

    def submit(self, body):
        key = body['operation_id']
        if key in self.unresolved:
            return 'FENCED'
        self.unresolved.add(key)
        try:
            status, value = self.request('POST', '/api/commands', body)
        except (OSError, http.client.HTTPException):
            return 'UNKNOWN'
        if status == 200 and value['outcome'] in ('ACCEPTED', 'REJECTED'):
            self.unresolved.remove(key)
        return value['outcome'] if status == 200 else value['error']

    def lookup(self, key, instance=None):
        response = self.request('GET', f'/api/operations/{key}?instance_id={instance or self.instance}')
        status, value = response
        if status == 200 and value['outcome'] in ('ACCEPTED', 'REJECTED'):
            self.unresolved.discard(key)
        return response

    def guard(self):
        state = self.request('GET', '/api/state')[1]
        if state.get('funds_executed') is not False:
            raise ClaimTableError('state must assert funds_executed false')
        service = self.server.service
        with service.lock:
            return (state['state_digest'], state['operation_count'], state['cases'],
                    copy.deepcopy(service.machine.export_journal()),
                    copy.deepcopy(service.receipts), copy.deepcopy(service.overlay_entries))


@contextmanager
def _facade(workspace=None):
    server = make_server(0, workspace=workspace)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    try:
        client = Client(server)
        client.guard()
        yield client
        client.guard()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise ClaimTableError('loopback server failed to stop')


def _receipt(client, body):
    status, value = client.request('POST', '/api/commands', body)
    if status != 200 or value.get('funds_executed') is not False:
        raise ClaimTableError('expected a SIMULATED receipt')
    return value


def _first(rejected=False, conflict=False):
    with _facade() as client:
        body = client.body(op='approve', args={}) if rejected else client.body()
        first = _receipt(client, body)
        if rejected:
            created = _receipt(client, client.body('sim-create'))
            if created['outcome'] != 'ACCEPTED':
                raise ClaimTableError('business rejection precondition was not resolved')
        before = client.guard()
        again_body = copy.deepcopy(body)
        producer = client.server.service.producer
        with patch.object(producer, 'apply', wraps=producer.apply) as apply:
            if conflict:
                again_body['args']['amount'] += 1
                status, again = client.request('POST', '/api/commands', again_body)
                repeat = [status, again.get('error')]
            else:
                again = _receipt(client, again_body)
                duplicate = again.pop('transport_duplicate')
                repeat = duplicate and again == {k: v for k, v in first.items() if k != 'transport_duplicate'}
        return {'outcome': first['outcome'], 'repeat': repeat,
                'lookup_original': client.lookup(body['operation_id']) == (200, first),
                'repeat_applications': apply.call_count,
                'unchanged': before == client.guard()}


@contextmanager
def _lost(client):
    """Drop the actual HTTP reply after service application, with an event barrier."""
    completed = threading.Event()
    dropped = []
    handler = client.server.RequestHandlerClass
    original = handler.reply

    def reply(self, status, value, *args, **kwargs):
        if self.command == 'POST' and self.path == '/api/commands' and status == 200:
            dropped.append(copy.deepcopy(value))
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            completed.set()
            return
        return original(self, status, value, *args, **kwargs)

    with patch.object(handler, 'reply', reply):
        yield completed, dropped


def _loss(mode):
    with _facade() as client:
        body = client.body()
        with _lost(client) as (applied, dropped):
            initial = client.submit(body)
            if not applied.wait(timeout=5):
                raise ClaimTableError('lost response was not applied')
        before = client.guard()
        if mode == 'timeout':
            client.elapsed += 10**12  # synthetic client clock, not a provider TTL
            fenced = client.submit(body)
            return {'initial': initial, 'after_timeout': 'UNKNOWN' if client.unresolved else 'KNOWN',
                    'resubmit': fenced, 'unchanged': before == client.guard()}
        if mode == 'retry':
            fenced = client.submit(body)
            client.lookup(body['operation_id'])
            return {'resubmit': fenced, 'posts': sum(m == 'POST' for m, _ in client.requests),
                    'unchanged': before == client.guard(), 'unresolved': bool(client.unresolved)}
        state_read = client.guard()
        unresolved_before_lookup = body['operation_id'] in client.unresolved
        status, receipt = client.lookup(body['operation_id'])
        return {'initial': initial, 'state_read_unresolved': unresolved_before_lookup,
                'lookup': [status, receipt['outcome']], 'resolved': not client.unresolved,
                'original_receipt': dropped == [receipt],
                'unchanged': before == state_read == client.guard()}


def _absent():
    with _facade() as client:
        before = client.guard()
        values = [client.lookup('sim-never-sent')[1] for _ in range(3)]
        return {'outcomes': [v['outcome'] for v in values],
                'retry_authorized': [v['retry_authorized'] for v in values],
                'unchanged': before == client.guard(),
                'posts': sum(m == 'POST' for m, _ in client.requests)}


def _unknown():
    with _facade() as client:
        before = client.guard()
        with patch.object(client.server.service.producer, 'apply', side_effect=TransportLost('SIMULATED')) as apply:
            outcome = client.submit(client.body())
            client.elapsed += 10**12
            values = [client.lookup('sim-first')[1] for _ in range(3)]
            resubmit = client.submit(client.body())
        return {'outcome': outcome, 'lookups': [v['outcome'] for v in values],
                'retry_authorized': [v['retry_authorized'] for v in values],
                'resubmit': resubmit, 'applications': apply.call_count, 'unchanged': before == client.guard()}


def _session():
    with _facade() as client:
        before = client.guard()
        body = client.body()
        body['instance_id'] = 'sim-stale-instance'
        status, value = client.request('POST', '/api/commands', body)
        lookup_status, lookup = client.lookup('sim-first', 'sim-stale-instance')
        return {'command': [status, value['error']], 'lookup': [lookup_status, lookup['error']],
                'unchanged': before == client.guard()}


def _restart(fence=False):
    with tempfile.TemporaryDirectory(prefix='capital-lifecycle-') as workspace:
        with _facade(workspace) as first:
            body = first.body()
            receipt = _receipt(first, body)
            old_token, old_instance, before = first.token, first.instance, first.guard()
        with patch.object(PinnedFsmProducer, 'apply', autospec=True,
                          side_effect=PinnedFsmProducer.apply) as apply, _facade(workspace) as restored:
            if fence:
                status, value = restored.request('POST', '/api/commands', body, token=old_token)
                # A fresh local session/token still cannot authorize an old instance.
                new_status, new_value = restored.request('POST', '/api/commands', body)
                lookup_status, lookup = restored.lookup(body['operation_id'], old_instance)
                return {'old_token_status': status, 'old_token_error': value['error'],
                        'fresh_token': [new_status, new_value['error']],
                        'lookup': [lookup_status, lookup['error']], 'unchanged': before == restored.guard()}
            found = restored.lookup(body['operation_id'])[1]
            after = restored.guard()
            return {'new_instance': restored.instance != old_instance,
                    'original_writer': found['instance_id'] == old_instance,
                    'original_receipt': found == receipt, 'restored': before == after,
                    'command_posts': sum(m == 'POST' for m, _ in restored.requests),
                    'applications_on_restore': apply.call_count}


def _late():
    with _facade() as client:
        before = client.guard()
        status, value = client.request('GET', '/api/scenarios/late-cash')
        if status != 200 or value.get('funds_executed') is not False:
            raise ClaimTableError('late-cash read must assert no funds execution')
        scenario = value['scenario']
        final = scenario['final']
        return {'step_ops': [s['op'] for s in scenario['steps']],
                'confirmed_cash': final['confirmed_cash'], 'distributed_cash': final['distributed_cash'],
                'undistributed_cash': final['undistributed_cash'],
                'cancelled_unpaid': sum(o['cancelled_unpaid'] for o in final['obligations']),
                'outstanding': sum(o['outstanding'] for o in final['obligations']),
                'all_predicates_matched': scenario['all_predicates_matched'],
                'unchanged': before == client.guard()}


CHECKS = {
    'first.accepted': _first,
    'first.rejected': lambda: _first(rejected=True),
    'first.conflict': lambda: _first(conflict=True),
    'unknown.timeout': lambda: _loss('timeout'),
    'unknown.producer_loss': _unknown,
    'unknown.receipt_lookup': lambda: _loss('lookup'),
    'unknown.no_retry': lambda: _loss('retry'),
    'receipt.absent': _absent,
    'fence.session': _session,
    'fence.restart': lambda: _restart(fence=True),
    'restore.replay': _restart,
    'fact.late': _late,
}
