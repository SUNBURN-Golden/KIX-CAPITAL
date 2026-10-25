#!/usr/bin/env python3
"""Loopback facade load harness. LOCAL_EXPLORATION, not production evidence.

Drives ``POST /api/commands`` on a fresh ``capital.server.make_server(0)``
per workload and storage mode, following the measurement semantics of the
upstream ``docs/contracts/PERFORMANCE_MEASUREMENT.md`` and
``docs/DEVELOPMENT_PLAN.md`` section 7 (kix-protocol, read-only reference):
the scheduled arrival instant and the service interval are separate fields,
and the outcome classes — new-success, replay, reject, conflict, capacity —
are counted and percentiled per class, never pooled. No SLO and no TPS is
claimed or reported.

Classes are mapped from the facade contract, never from process metrics
(the metrics duplicate-count is a different instrument by design):

- ``new_success``: HTTP 200, outcome ACCEPTED, transport_duplicate false
- ``replay``:      HTTP 200, transport_duplicate true (the stored receipt
                   again; no new receipt and no new journal entry)
- ``reject``:      HTTP 200, outcome REJECTED (stored receipt; counts
                   toward MAX_OPERATIONS, writes no journal entry)
- ``conflict``:    HTTP 409 IDEMPOTENCY_CONFLICT (nothing is written; the
                   pre-existing receipt under that operation_id stays)
- ``capacity``:    HTTP 409 SIMULATION_CAPACITY (no receipt, no journal)
- ``other``:       anything else. Counted and flagged, never folded into a
                   class. A nonzero ``other`` fails the run's assertions.

After every workload run the harness asserts: the journal length equals the
new-success count, every replay returned the stored receipt without a new
journal entry, conflicts and capacity rejections wrote nothing, and the
final state_digest equals a fresh journal replay.

Commands use demo-book claims (``demo-*``) and ``sim-*` ids only. Amounts
are synthetic fixture units, not financial values. The report is
``KIX_CAPITAL_LOAD_REPORT_V1`` labelled ``LOCAL_EXPLORATION``: input
fingerprint, Python/OS/CPU info, per-class counts and nearest-rank
percentiles. It is not production performance evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import platform
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.producer import PinnedFsmProducer
from capital.server import make_server
from capital.service import MAX_OPERATIONS, digest

REPORT_FORMAT = 'KIX_CAPITAL_LOAD_REPORT_V1'
REPORT_LABEL = 'LOCAL_EXPLORATION'
EVIDENCE_LABEL = 'NOT_PRODUCTION_PERFORMANCE_EVIDENCE'
WORKLOAD_IDS = (
    'low-load-uniform', 'uniform', 'hot-seat',
    'same-command-retry', 'history-growth', 'saturation',
)
CLASSES = ('new_success', 'replay', 'reject', 'conflict', 'capacity', 'other')
MODES = ('memory', 'workspace')
DEFAULT_SEED = 74810481
DEFAULT_WORKERS = 8
# Committed demo-book claims (drawable) and captured-only claims (draw rejects).
_T1 = ('demo-alpha-arena', 'demo-alpha-hall', 'demo-gamma-annex',
       'demo-delta-small', 'demo-epsilon-clean')
_T2 = ('demo-beta-festival', 'demo-beta-club', 'demo-gamma-tour', 'demo-delta-mid')
_SIZES = {
    'smoke': {
        'low_load_advances': 3, 'low_load_full': False,
        'uniform_extra': 0, 'retry_dups': 4,
        'history_advances': 4, 'history_conflicts': 8,
    },
    'full': {
        'low_load_advances': 10, 'low_load_full': True,
        'uniform_extra': 16, 'retry_dups': 10,
        'history_advances': 8, 'history_conflicts': 14,
    },
}


# --------------------------------------------------------------------- specs


def _spec(seq, op_id, op, advance, args, offset_ms, scheduled=True, **extra):
    spec = {
        'seq': seq, 'operation_id': op_id, 'op': op, 'advance_id': advance,
        'args': args, 'offset_ms': offset_ms, 'scheduled': scheduled,
    }
    spec.update(extra)
    return spec


def _chain(seq_start, prefix, steps, spacing_ms=1.5):
    """One sequential thread: spec j waits for spec j-1 inside its thread."""
    thread = []
    for index, (op, advance, args) in enumerate(steps):
        thread.append(_spec(
            seq_start + index, f'{prefix}-{index}-{op.replace("_", "-")}',
            op, advance, args, index * spacing_ms))
    return thread, seq_start + len(steps)


def _fingerprint_body(spec):
    """The same idempotency fingerprint the service computes for a command."""
    return digest({
        'operation_id': spec['operation_id'], 'op': spec['op'],
        'advance_id': spec['advance_id'], 'args': spec['args'],
    })


def _low_load(rng, sizes):
    threads, seq = [], 0
    for index in range(sizes['low_load_advances']):
        advance = f'sim-load-lu-{index}'
        fixture = rng.choice(_T1)
        amount = rng.choice((1000, 2000, 5000))
        steps = [
            ('offer', advance, {'fixture_id': fixture, 'amount': amount}),
            ('approve', advance, {}),
            ('bind_settlement', advance, {}),
            ('draw', advance, {}),
        ]
        if sizes['low_load_full']:
            steps += [
                ('repay', advance, {'amount': amount, 'sequence': 1}),
                ('close', advance, {}),
            ]
        thread, seq = _chain(seq, f'lu-{index}', steps)
        threads.append(thread)
    return {
        'phases': [{'name': 'lifecycle', 'threads': threads}],
        'expected': {'new_success'},
    }


def _uniform(rng, sizes):
    threads, seq = [], 0

    def add(prefix, steps):
        nonlocal seq
        thread, seq = _chain(seq, prefix, steps)
        threads.append(thread)

    drawn = 'sim-load-u-drawn'
    add('u-drawn', [
        ('offer', drawn, {'fixture_id': rng.choice(_T1), 'amount': 9000}),
        ('approve', drawn, {}),
        ('bind_settlement', drawn, {}),
        ('draw', drawn, {}),
        ('repay', drawn, {'amount': 5000, 'sequence': 2}),
        ('repay', drawn, {'amount': 9001, 'sequence': 1}),
        ('repay', drawn, {'amount': 5000, 'sequence': 1}),
        ('close', drawn, {}),
        ('repay', drawn, {'amount': 4000, 'sequence': 2}),
        ('close', drawn, {}),
    ])
    pending = 'sim-load-u-pending'
    add('u-pending', [
        ('offer', pending, {'fixture_id': rng.choice(_T2), 'amount': 4000}),
        ('approve', pending, {}),
        ('bind_settlement', pending, {}),
        ('draw', pending, {}),
        ('draw', pending, {}),
    ])
    add('u-refund', [
        ('offer', 'sim-load-u-refund', {'fixture_id': 'demo-epsilon-refund', 'amount': 1000}),
    ])
    add('u-missing', [
        ('offer', 'sim-load-u-missing', {'fixture_id': 'sim-not-a-claim', 'amount': 1000}),
    ])
    add('u-ghost', [('approve', 'sim-load-u-ghost', {})])
    unbound = 'sim-load-u-unbound'
    add('u-unbound', [
        ('offer', unbound, {'fixture_id': rng.choice(_T1), 'amount': 3000}),
        ('approve', unbound, {}),
        ('draw', unbound, {}),
        ('cancel', unbound, {}),
        ('default', unbound, {}),
    ])
    terminal = 'sim-load-u-terminal'
    add('u-terminal', [
        ('offer', terminal, {'fixture_id': rng.choice(_T1), 'amount': 2000}),
        ('approve', terminal, {}),
        ('reject', terminal, {}),
        ('approve', terminal, {}),
    ])
    for index in range(sizes['uniform_extra']):
        advance = f'sim-load-u-x{index}'
        fixture = rng.choice(_T1 if rng.random() < 0.8 else _T2)
        amount = rng.choice((1000, 2000, 5000, 10000))
        steps = [('offer', advance, {'fixture_id': fixture, 'amount': amount}),
                 ('approve', advance, {})]
        depth = rng.choice(('bound', 'bound', 'drawn', 'drawn', 'closed'))
        if depth != 'offer':
            steps.append(('bind_settlement', advance, {}))
        if depth in ('drawn', 'closed'):
            steps.append(('draw', advance, {}))
        if depth == 'closed':
            steps.append(('repay', advance, {'amount': amount, 'sequence': 1}))
            steps.append(('close', advance, {}))
        add(f'u-x{index}', steps)
    return {
        'phases': [{'name': 'commands', 'threads': threads}],
        'expected': {'new_success', 'reject'},
    }


def _hot_seat(rng, sizes):
    del rng
    share = 30_000_000  # two 30M offers contend on the 50M demo-delta-small face
    phases, seq = [], 0
    binds = []
    for name in ('a', 'b'):
        advance = f'sim-load-hs-{name}'
        thread, seq = _chain(seq, f'hs-{name}', [
            ('offer', advance, {'fixture_id': 'demo-delta-small', 'amount': share}),
            ('approve', advance, {}),
            ('bind_settlement', advance, {}),
        ])
        binds.append(thread)
    phases.append({'name': 'bind', 'threads': binds})
    draws = []
    for name in ('a', 'b'):
        draws.append([_spec(seq, f'hs-{name}-draw', 'draw', f'sim-load-hs-{name}', {}, 0)])
        seq += 1
    phases.append({'name': 'contend', 'threads': draws})
    after = []
    for name in ('a', 'b'):
        thread, seq = _chain(seq, f'hs-{name}-r', [
            ('repay', f'sim-load-hs-{name}', {'amount': 1000, 'sequence': 1}),
            ('repay', f'sim-load-hs-{name}', {'amount': 1000, 'sequence': 2}),
        ])
        after.append(thread)
    phases.append({'name': 'after', 'threads': after})
    return {'phases': phases, 'expected': {'new_success', 'reject'}}


def _same_command_retry(rng, sizes):
    phases, seq = [], 0
    fixture = rng.choice(_T1)
    first = [
        _spec(seq, 'rt-offer', 'offer', 'sim-load-rt',
              {'fixture_id': fixture, 'amount': 4000}, 0),
        _spec(seq + 1, 'rt-ghost', 'approve', 'sim-load-rt-ghost', {}, 0),
    ]
    seq += len(first)
    phases.append({'name': 'first', 'threads': [[first[0]], [first[1]]]})
    replays = []
    for index in range(sizes['retry_dups']):
        replays.append([_spec(
            seq, 'rt-offer', 'offer', 'sim-load-rt',
            {'fixture_id': fixture, 'amount': 4000}, 0, scheduled=False,
            keep_response=True)])
        seq += 1
    for index in range(2):
        replays.append([_spec(
            seq, 'rt-ghost', 'approve', 'sim-load-rt-ghost', {}, 0,
            scheduled=False, keep_response=True)])
        seq += 1
    phases.append({'name': 'replay', 'threads': replays})
    return {'phases': phases, 'expected': {'new_success', 'reject', 'replay'}}


def _history_growth(rng, sizes):
    grow, seq = [], 0
    for index in range(sizes['history_advances']):
        advance = f'sim-load-hg-{index}'
        steps = [
            ('offer', advance,
             {'fixture_id': rng.choice(_T1), 'amount': rng.choice((1000, 2000, 4000))}),
            ('approve', advance, {}),
        ]
        if rng.random() < 0.75:
            steps += [('bind_settlement', advance, {}), ('draw', advance, {})]
        thread, seq = _chain(seq, f'hg-{index}', steps)
        grow.append(thread)
    conflicts = []
    originals = [spec for thread in grow for spec in thread]
    offset = 0.0
    for original in originals[:sizes['history_conflicts']]:
        mutated = dict(original['args'])
        if 'amount' in mutated:
            mutated['amount'] += 1
        else:
            mutated['probe'] = 1
        conflicts.append([_spec(
            seq, original['operation_id'], original['op'], original['advance_id'],
            mutated, offset, prior_fingerprint=_fingerprint_body(original))])
        seq += 1
        offset += 1.5
    first = originals[0]
    conflicts.append([_spec(
        seq, first['operation_id'], 'close', first['advance_id'], {}, offset,
        prior_fingerprint=_fingerprint_body(first))])
    seq += 1
    return {
        'phases': [
            {'name': 'grow', 'threads': grow},
            {'name': 'conflict', 'threads': conflicts},
        ],
        'expected': {'new_success', 'conflict'},
    }


def _saturation(rng, sizes):
    del rng, sizes
    specs = [
        [_spec(i, f'sat-{i}', 'approve', f'sim-load-sat-{i}', {}, i * 0.4)]
        for i in range(MAX_OPERATIONS + 5)
    ]
    seq = len(specs)
    probe = [
        [_spec(seq, 'sat-0', 'approve', 'sim-load-sat-0', {}, 0,
               scheduled=False, keep_response=True)],
        [_spec(seq + 1, 'sat-0', 'approve', 'sim-load-sat-0', {'probe': 1}, 0,
               scheduled=False,
               prior_fingerprint=digest({'operation_id': 'sat-0', 'op': 'approve',
                                         'advance_id': 'sim-load-sat-0', 'args': {}}))],
        [_spec(seq + 2, 'sat-new', 'approve', 'sim-load-sat-new', {}, 0,
               scheduled=False)],
    ]
    return {
        'phases': [
            {'name': 'fill', 'threads': specs},
            {'name': 'probe', 'threads': probe},
        ],
        'expected': {'reject', 'capacity', 'replay', 'conflict'},
    }


_BUILDERS = {
    'low-load-uniform': _low_load,
    'uniform': _uniform,
    'hot-seat': _hot_seat,
    'same-command-retry': _same_command_retry,
    'history-growth': _history_growth,
    'saturation': _saturation,
}


def build_inputs(profile, seed, modes):
    """Seeded workload inputs. No instance_id, token, port, or clock here."""
    if profile not in _SIZES:
        raise ValueError(f'unknown profile {profile!r}')
    sizes = _SIZES[profile]
    workloads = []
    for workload_id in WORKLOAD_IDS:
        rng = random.Random(f'{seed}:{workload_id}')
        built = _BUILDERS[workload_id](rng, sizes)
        workloads.append({
            'id': workload_id,
            'seed': f'{seed}:{workload_id}',
            'phases': built['phases'],
            'expected': built['expected'],
        })
    return {'profile': profile, 'seed': seed, 'modes': list(modes),
            'workloads': workloads}


def input_fingerprint(inputs):
    """SHA256 over the canonical seeded inputs; volatile fields stay out."""
    canonical = {
        'profile': inputs['profile'], 'seed': inputs['seed'],
        'modes': inputs['modes'],
        'workloads': [{
            'id': workload['id'],
            'phases': [
                {'name': phase['name'],
                 'specs': [
                     {key: spec[key] for key in (
                         'seq', 'operation_id', 'op', 'advance_id', 'args',
                         'offset_ms', 'scheduled')}
                     for thread in phase['threads'] for spec in thread]
                 }
                for phase in workload['phases']
            ],
        } for workload in inputs['workloads']],
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------- driver


class HarnessError(Exception):
    pass


def _classify(status, payload):
    if status == 200 and type(payload) is dict:
        if payload.get('transport_duplicate') is True:
            return 'replay'
        outcome = payload.get('outcome')
        if outcome == 'ACCEPTED':
            return 'new_success'
        if outcome == 'REJECTED':
            return 'reject'
        return 'other'
    if status == 409 and type(payload) is dict:
        code = payload.get('error')
        if code == 'IDEMPOTENCY_CONFLICT':
            return 'conflict'
        if code == 'SIMULATION_CAPACITY':
            return 'capacity'
    return 'other'


class _Client:
    """One stdlib HTTPConnection per request. Loopback only, never retried."""

    def __init__(self, port, instance_id, token):
        self.port, self.instance_id, self.token = port, instance_id, token

    def _request(self, method, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            headers = {}
            if self.token:
                headers['X-Capital-Token'] = self.token
            if body is not None:
                headers['Content-Type'] = 'application/json'
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw)
        finally:
            connection.close()

    def post(self, spec):
        body = json.dumps({
            'instance_id': self.instance_id,
            'operation_id': spec['operation_id'],
            'op': spec['op'],
            'advance_id': spec['advance_id'],
            'args': spec['args'],
        }, sort_keys=True)
        return self._request('POST', '/api/commands', body)

    def get(self, path):
        return self._request('GET', path)


def _run_thread(client, origin, thread):
    """Issue one sequential thread of specs; returns per-request records."""
    records = []
    for spec in thread:
        scheduled_at = None
        if spec['scheduled']:
            scheduled_at = origin + spec['offset_ms'] / 1000.0
            wait = scheduled_at - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
        started = time.perf_counter()
        status, payload = client.post(spec)
        completed = time.perf_counter()
        records.append({
            'seq': spec['seq'],
            'operation_id': spec['operation_id'],
            'op': spec['op'],
            'class': _classify(status, payload),
            'http_status': status,
            'outcome': payload.get('outcome') if type(payload) is dict else None,
            'error': payload.get('error') if type(payload) is dict else None,
            'scheduled_at_ms': (
                None if scheduled_at is None else (scheduled_at - origin) * 1000.0),
            'started_at_ms': (started - origin) * 1000.0,
            'completed_at_ms': (completed - origin) * 1000.0,
            'service_ms': (completed - started) * 1000.0,
            'schedule_delay_ms': (
                None if scheduled_at is None else (started - scheduled_at) * 1000.0),
            'scheduled_latency_ms': (
                None if scheduled_at is None else (completed - scheduled_at) * 1000.0),
            'prior_fingerprint': spec.get('prior_fingerprint'),
            'response': payload if spec.get('keep_response') else None,
        })
    return records


def _nearest_rank(ordered, percentile):
    if not ordered:
        return None
    index = math.ceil(percentile / 100.0 * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _stats(samples):
    if not samples:
        return None
    ordered = sorted(samples)
    return {
        'count': len(ordered),
        'min': round(ordered[0], 3),
        'p50': round(_nearest_rank(ordered, 50), 3),
        'p90': round(_nearest_rank(ordered, 90), 3),
        'p99': round(_nearest_rank(ordered, 99), 3),
        'max': round(ordered[-1], 3),
    }


def _stored_receipt(service, operation_id):
    row = service.receipts.get(operation_id)
    return row['receipt'] if row is not None else None


def _verify(server, records, phase_checks, export, state, expected_classes):
    service = server.service
    counts = {name: 0 for name in CLASSES}
    for record in records:
        counts[record['class']] += 1
    journal_length = len(service.machine.export_journal())
    receipts_length = len(service.receipts)
    journal_ok = journal_length == counts['new_success']
    receipts_ok = receipts_length == counts['new_success'] + counts['reject']

    def phases_clean(with_class):
        return all(
            check['journal_delta'] == check['classes'].get('new_success', 0)
            and check['receipts_delta'] == (
                check['classes'].get('new_success', 0) + check['classes'].get('reject', 0))
            for check in phase_checks
            if check['classes'].get(with_class))

    for record in records:
        if record['class'] == 'replay':
            stored = _stored_receipt(service, record['operation_id'])
            record['receipt_match'] = (
                record['response'] is not None
                and stored is not None
                and record['response'] == {**stored, 'transport_duplicate': True})
    replays_stored = all(
        record['receipt_match']
        for record in records
        if record['class'] == 'replay')

    conflicts_kept = all(
        service.receipts.get(record['operation_id']) is not None
        and service.receipts[record['operation_id']]['fingerprint'] == record['prior_fingerprint']
        for record in records
        if record['class'] == 'conflict')

    journal = service.machine.export_journal()
    restored = PinnedFsmProducer().restored(journal)
    digest_now = service.machine.state_digest()
    replay_ok = (
        export.get('replay_matched') is True
        and export.get('state_digest') == digest_now
        and restored.state_digest() == digest_now
        and state.get('state_digest') == digest_now)

    return {
        'journal_equals_new_success': journal_ok,
        'receipts_equal_new_plus_reject': receipts_ok,
        'replays_no_new_journal': phases_clean('replay') and replays_stored,
        'conflicts_write_nothing': phases_clean('conflict') and conflicts_kept,
        'capacity_writes_nothing': (
            phases_clean('capacity') and receipts_length <= MAX_OPERATIONS),
        'state_digest_equals_replay': replay_ok,
        'no_other_outcomes': counts['other'] == 0,
        'classes_within_expected': all(
            counts[name] == 0 for name in CLASSES if name not in expected_classes),
        'operation_count_matches': (
            state.get('operation_count') == receipts_length),
    }


def _start_server(mode, workspace_root):
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode!r}')
    tempdir = None
    workspace = None
    if mode == 'workspace':
        tempdir = tempfile.TemporaryDirectory(prefix='kix-load-', dir=workspace_root)
        workspace = str(Path(tempdir.name) / 'workspace')
    server = make_server(0, workspace=workspace)
    thread = threading.Thread(
        target=server.serve_forever, name=f'load-{mode}', daemon=True)
    thread.start()
    return server, thread, tempdir


def _class_stats(records, name):
    bucket = [record for record in records if record['class'] == name]
    return {
        'count': len(bucket),
        'service_ms': _stats([r['service_ms'] for r in bucket]),
        'schedule_delay_ms': _stats(
            [r['schedule_delay_ms'] for r in bucket if r['schedule_delay_ms'] is not None]),
        'scheduled_latency_ms': _stats(
            [r['scheduled_latency_ms'] for r in bucket if r['scheduled_latency_ms'] is not None]),
    }


def _run_workload(workload, mode, workspace_root, workers):
    server, thread, tempdir = _start_server(mode, workspace_root)
    records = []
    phase_checks = []
    try:
        status, state = _Client(server.server_port, '', '').get('/api/state')
        if status != 200:
            raise HarnessError(f'/api/state status {status}')
        client = _Client(server.server_port, state['instance_id'], state['local_token'])
        started = time.perf_counter()
        for phase in workload['phases']:
            service = server.service
            journal_before = len(service.machine.export_journal())
            receipts_before = len(service.receipts)
            phase_start = len(records)
            origin = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_run_thread, client, origin, thread_specs)
                    for thread_specs in phase['threads']]
                for future in futures:
                    records.extend(future.result())
            added = records[phase_start:]
            classes = {}
            for record in added:
                classes[record['class']] = classes.get(record['class'], 0) + 1
            phase_checks.append({
                'name': phase['name'],
                'classes': classes,
                'journal_delta': len(service.machine.export_journal()) - journal_before,
                'receipts_delta': len(service.receipts) - receipts_before,
            })
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _status, metrics = client.get('/api/metrics')
        _status, export = client.get('/api/export')
        _status, state = client.get('/api/state')
        assertions = _verify(
            server, records, phase_checks, export, state, workload['expected'])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
        if tempdir is not None:
            tempdir.cleanup()

    capacity_seqs = sorted(r['seq'] for r in records if r['class'] == 'capacity')
    samples = [{
        'seq': r['seq'], 'operation_id': r['operation_id'], 'op': r['op'],
        'class': r['class'], 'http_status': r['http_status'],
        'outcome': r['outcome'], 'error': r['error'],
        'scheduled_at_ms': (
            None if r['scheduled_at_ms'] is None else round(r['scheduled_at_ms'], 3)),
        'started_at_ms': round(r['started_at_ms'], 3),
        'service_ms': round(r['service_ms'], 3),
        'schedule_delay_ms': (
            None if r['schedule_delay_ms'] is None else round(r['schedule_delay_ms'], 3)),
        'scheduled_latency_ms': (
            None if r['scheduled_latency_ms'] is None else round(r['scheduled_latency_ms'], 3)),
        'receipt_match': r.get('receipt_match'),
    } for r in sorted(records, key=lambda r: r['seq'])]
    return {
        'id': workload['id'],
        'mode': mode,
        'seed': workload['seed'],
        'requests': len(records),
        'workers': workers,
        'elapsed_ms': round(elapsed_ms, 3),
        'classes': {name: _class_stats(records, name)
                    for name in CLASSES
                    if any(r['class'] == name for r in records)},
        'first_capacity_index': capacity_seqs[0] if capacity_seqs else None,
        'samples_after_first_capacity': (
            sum(1 for r in records if r['seq'] > capacity_seqs[0])
            if capacity_seqs else 0),
        'operation_count': state.get('operation_count'),
        'journal_length': len(server.service.machine.export_journal()),
        'workspace_kind': server.service.workspace_view()['kind'],
        'state_digest': state.get('state_digest'),
        'assertions': assertions,
        'ok': all(assertions.values()),
        'phase_checks': phase_checks,
        'metrics': {
            'label': metrics.get('label'),
            'mode': metrics.get('mode'),
            'counters': metrics.get('counters'),
            'latency_ms': metrics.get('latency_ms'),
        },
        'samples': samples,
    }


def _environment():
    return {
        'python': platform.python_version(),
        'implementation': platform.python_implementation(),
        'os': platform.platform(),
        'machine': platform.machine(),
        'cpu_count': os.cpu_count(),
    }


def run(profile='smoke', mode='both', seed=DEFAULT_SEED, workspace_root=None,
        workers=DEFAULT_WORKERS, progress=None):
    """Run every workload in each requested mode. Returns the report dict."""
    modes = MODES if mode == 'both' else (mode,)
    for name in modes:
        if name not in MODES:
            raise ValueError(f'unknown mode {name!r}')
    inputs = build_inputs(profile, seed, modes)
    report = {
        'format': REPORT_FORMAT,
        'label': REPORT_LABEL,
        'evidence': EVIDENCE_LABEL,
        'funds_executed': False,
        'claims': {
            'slo': 'NOT_MEASURED',
            'tps': 'NOT_REPORTED',
            'throughput': 'NOT_REPORTED',
            'production': 'NOT_AUTHORIZED',
        },
        'profile': profile,
        'seed': seed,
        'modes': list(modes),
        'workers': workers,
        'input_fingerprint': input_fingerprint(inputs),
        'environment': _environment(),
        'workloads': [],
    }
    for mode_name in modes:
        for workload in inputs['workloads']:
            result = _run_workload(workload, mode_name, workspace_root, workers)
            report['workloads'].append(result)
            if callable(progress):
                progress(result)
    report['ok'] = all(workload['ok'] for workload in report['workloads'])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--profile', choices=sorted(_SIZES), default='smoke',
                        help='smoke is the deterministic unittest profile; full is manual.')
    parser.add_argument('--mode', choices=('memory', 'workspace', 'both'), default='both',
                        help='storage mode. memory is process state; workspace is an '
                             'opt-in LOCAL_FILE_WORKSPACE temp dir per workload.')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--out', type=Path, default=ROOT / 'build' / 'load-report.json',
                        help='report path. Default build/load-report.json (uncommitted).')
    parser.add_argument('--workspace-root', type=Path, default=None,
                        help='parent dir for per-workload LOCAL_FILE_WORKSPACE temp dirs.')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args(argv)

    def progress(result):
        classes = {name: stats['count'] for name, stats in result['classes'].items()}
        print(
            f"[load] {result['id']} ({result['mode']}) requests={result['requests']} "
            f"classes={classes} ok={str(result['ok']).lower()}", flush=True)

    report = run(profile=args.profile, mode=args.mode, seed=args.seed,
                 workspace_root=(None if args.workspace_root is None
                                 else str(args.workspace_root)),
                 workers=args.workers, progress=progress)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + '\n',
        encoding='utf-8')
    print(f'[load] report {args.out} format={REPORT_FORMAT} label={REPORT_LABEL} '
          f'fingerprint={report["input_fingerprint"]} ok={str(report["ok"]).lower()}',
          flush=True)
    if not report['ok']:
        print('[load] invariant assertions failed — see report assertions', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
