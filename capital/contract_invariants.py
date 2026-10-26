"""Finite-trace Capital analogues of INV-1..INV-5: CLAIM_CONFORMANCE, SIMULATED.

The Rust kernel is a contract citation only. No kernel code is copied or run.
Predicates consume observed facade traces, not a second transition model.
Sensitivity tests corrupt copies of those observations, never the pinned FSMs.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import random
import signal
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from capital import overlay, upstream_claims
from capital.resources import ROOT as CAPITAL_ROOT
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, canonical_bytes

PINNED_SHA = upstream_claims.PINNED_SHA
LABEL = 'CLAIM_CONFORMANCE'
FORMAT = 'KIX_CAPITAL_CONTRACT_INVARIANTS_V1'
SOURCE_DOC = 'docs/contracts/CONTRACT_INVARIANTS.md'
ROOT = Path(str(CAPITAL_ROOT)).resolve().parent
TABLE = ROOT / 'tests/contract_invariants.json'
BASE_SEED = 74810500
SEEDS = tuple(range(BASE_SEED, BASE_SEED + 12))
RECEIPT_BOUND = 12
OVERLAY_BOUND = 3
_CACHE = {}
ClaimTableError = upstream_claims.ClaimTableError


def projection(receipt):
    """Command bytes retain original instance; overlay replay rebuilds its envelope."""
    omitted = {'transport_duplicate'}
    if receipt.get('outcome') == 'APPLIED':
        omitted |= {'instance_id', 'overlay_state_digest'}
    return canonical_bytes({k: v for k, v in receipt.items() if k not in omitted})


def _result(violations):
    return {'ok': not violations, 'violations': violations}


def inv1_shared_face(trace):
    bad = []
    for snap in trace['snapshots']:
        groups = {}
        for row in snap['cases']:
            groups.setdefault(row['claim_id'], []).append(row)
        for claim, rows in groups.items():
            reserved = sum(r['amount'] for r in rows if r['note_status'] == 'NOTED')
            if any(not 0 <= r['reserved_open'] <= r['open_face'] or
                   r['reserved_open'] != reserved for r in rows):
                bad.append((snap['n'], claim, 'shared face reservation'))
    return _result(bad)


def inv2_capacity(trace):
    bad = []
    prior = None
    for snap in trace['snapshots']:
        if len(snap['receipt_ids']) > snap['receipt_bound'] or len(snap['overlay_ids']) > snap['overlay_bound']:
            bad.append((snap['n'], 'capacity exceeded'))
        if prior:
            if not prior['receipt_ids'] <= snap['receipt_ids'] or not prior['overlay_ids'] <= snap['overlay_ids']:
                bad.append((snap['n'], 'eviction'))
        prior = snap
    for cell in trace['steps']:
        if cell.get('capacity_probe') and any(
                (r['status'], r.get('error')) != (409, 'SIMULATION_CAPACITY') for r in cell['results']):
            bad.append((cell['n'], 'new id admitted after saturation'))
        if cell.get('capacity_probe'):
            before, after = trace['snapshots'][cell['n']], trace['snapshots'][cell['n'] + 1]
            if (before['receipt_ids'], before['overlay_ids']) != (after['receipt_ids'], after['overlay_ids']):
                bad.append((cell['n'], 'capacity refusal changed stores'))
    return _result(bad)


def inv3_first_result(trace):
    bad = []
    first_steps = {}
    for cell in trace['steps']:
        for row in cell['results']:
            if row['status'] == 200:
                first_steps.setdefault(row['id'], cell['n'])
    observed_reads = {(r['n'], r['id']) for r in trace['reads']}
    for key, first_step in first_steps.items():
        if key not in trace['first']:
            bad.append((first_step, key, 'first result missing'))
        for snap in trace['snapshots']:
            if snap['n'] > first_step and (snap['n'], key) not in observed_reads:
                bad.append((snap['n'], key, 'later receipt probe missing'))
    for read in trace['reads']:
        if read['bytes'] != trace['first'].get(read['id']):
            bad.append((read['n'], read['id'], 'first result changed'))
    for cell in trace['steps']:
        for row in cell['results']:
            if row.get('replay') and not row.get('transport_duplicate'):
                bad.append((cell['n'], row['id'], 'replay unmarked'))
    for first in trace['overlay_digests']:
        if first['receipt'] != first['folded']:
            bad.append((first['n'], 'initial overlay digest'))
    for probe in trace['session_probes']:
        if probe != 'SESSION_CHANGED':
            bad.append(('old session accepted', probe))
    return _result(bad)


def inv4_single_effect(trace):
    bad, previous, raises, draws = [], {}, {}, {}
    for snap in trace['snapshots']:
        for row in snap['cases']:
            key = row['advance_id']
            now = row['outstanding_exposure']
            if previous.get(key, 0) == 0 and now > 0:
                raises[key] = raises.get(key, 0) + 1
            if (raises.get(key, 0) > 1 or not 0 <= now <= row['drawn_exposure'] <= row['amount']
                    or (row['draw_id'] and row['drawn_exposure'] != row['amount'])):
                bad.append((snap['n'], key, 'multiple economic effects'))
            if row['draw_id']:
                if key in draws and draws[key] != row['draw_id']:
                    bad.append((snap['n'], key, 'draw binding changed'))
                draws[key] = row['draw_id']
            previous[key] = now
    for cell in trace['steps']:
        if cell.get('duplicate_draw_probe') and any(
                r.get('outcome') != 'REJECTED' or r.get('error') not in
                ('DUPLICATE_DRAW', 'TERMINAL_IMMUTABLE') for r in cell['results']):
            bad.append((cell['n'], 'new draw id accepted'))
    return _result(bad)


def inv5_retained_facts(trace):
    bad, journal, overlays, facts = [], set(), set(), {}
    length = 0
    def retained(row, snap):
        return tuple(row[field] for field in (
            'claim_id', 'trade_id', 'currency', 'amount', 'drawn_exposure', 'draw_id'
        )) + (snap['draw_indices'].get(row['advance_id']),)

    for snap in trace['snapshots']:
        current = set(snap['journal'])
        if not journal <= current or len(snap['journal']) < length or not overlays <= snap['overlay_ids']:
            bad.append((snap['n'], 'retained entry vanished'))
        rows = {r['advance_id']: r for r in snap['cases']}
        for key, fact in facts.items():
            row = rows.get(key)
            if (row is None or row['note_status'] not in ('NOTED', 'RELEASED') or
                    retained(row, snap) != fact):
                bad.append((snap['n'], key, 'retained draw changed'))
        for key, row in rows.items():
            if row['draw_id']:
                facts.setdefault(key, retained(row, snap))
        journal, overlays, length = current, snap['overlay_ids'], len(snap['journal'])
    return _result(bad)


CHECKS = {f'inv{i}': fn for i, fn in enumerate((
    inv1_shared_face, inv2_capacity, inv3_first_result, inv4_single_effect, inv5_retained_facts), 1)}


def command(op, key, advance='sim-inv-a', **args):
    return {'op': op, 'operation_id': key, 'advance_id': advance, 'args': args}


def tick(key, start, end):
    return {'op': 'advance_day', 'operation_id': key, 'from_sim_day': start,
            'to_sim_day': end, 'reason': 'SIMULATED_CONTRACT_INVARIANTS'}


def generate_sequence(seed):
    """Seeded stimuli plus a non-vacuous lifecycle; no expected FSM replies model."""
    rng = random.Random(seed)
    amount = rng.choice((1000, 2000, 5000))  # synthetic fixture units only
    draw = command('draw', 'draw')
    cells = [dict(commands=[c]) for c in (
        command('offer', 'offer', fixture_id='sim-committed', amount=amount),
        command('approve', 'approve'), command('bind_settlement', 'bind'))]
    cells += [{'commands': [draw, copy.deepcopy(draw)], 'kind': 'concurrent'},
              {'commands': [tick('tick', 0, 1)]}, {'kind': 'restart', 'commands': []},
              {'commands': [draw], 'replay': True},
              {'commands': [command('draw', 'draw-new')], 'duplicate_draw_probe': True},
              {'commands': [command('repay', 'repay', amount=amount, sequence=1)]},
              {'commands': [command('cancel', 'cancel', reason='SIMULATED')]}]
    for index in range(6):
        chance = rng.random()
        if chance < .23:
            cells.append({'commands': [draw] * (2 if chance < .08 else 1),
                          'kind': 'concurrent' if chance < .08 else 'replay', 'replay': True})
        elif chance < .33:
            cells.append({'commands': [tick('tick', 0, 1)], 'replay': True})
        else:
            op = rng.choice(('approve', 'draw', 'cancel', 'repay', 'offer', 'bind_settlement'))
            args = ({'reason': 'SIMULATED'} if op == 'cancel' else
                    {'amount': amount, 'sequence': 2} if op == 'repay' else
                    {'fixture_id': 'sim-committed', 'amount': amount} if op == 'offer' else {})
            cells.append({'commands': [command(op, f'random-{index}', **args)]})
    return cells


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def loopback_available():
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
        return True
    except PermissionError:
        return False


class Observer:
    """All writes use the real facade. Snapshots contain only observed facts."""
    def __init__(self, directory, *, http=False, receipt_bound=500, overlay_bound=None):
        self.directory, self.http = directory, http
        self.receipt_bound = receipt_bound
        self.bounds = {**overlay.load_bounds()}
        if overlay_bound is not None:
            self.bounds['OVERLAY_MAX_ENTRIES'] = overlay_bound
        self.trace = {'steps': [], 'snapshots': [], 'first': {}, 'reads': [],
                      'overlay_digests': [], 'session_probes': [], 'instances': []}
        self.bodies = {}
        self.open()
        self.observe()

    def open(self):
        if self.http:
            self.server = make_server(0, workspace=self.directory)
            self.service = self.server.service
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.start()
            sim = _module('inv_sim', ROOT / 'scripts/sim_journeys.py')
            self.session = sim.Session(self.server.server_port)
        else:
            self.port = FileWorkspace.open(self.directory)
            self.service = CapitalService(self.port, overlay_bounds=self.bounds)
        self.trace['instances'].append(self.service.instance_id)

    def close(self):
        if self.http:
            self.server.shutdown()
            self.thread.join(timeout=5)
            self.server.server_close()
        else:
            self.port.close()

    def invoke(self, body):
        full = {**body, 'instance_id': self.service.instance_id}
        if self.http:
            path = '/api/overlay/commands' if body['op'] == 'advance_day' else '/api/commands'
            return self.session.client.request('POST', path, full, self.session.token)
        try:
            fn = self.service.overlay_command if body['op'] == 'advance_day' else self.service.execute
            return 200, fn(full)
        except ApiError as exc:
            return exc.status, {'error': exc.code}

    def observe(self):
        service, trace = self.service, self.trace
        n = len(trace['steps'])
        journal = service.machine.export_journal()
        entries = service.overlay_entries
        trace['snapshots'].append({
            'n': n, 'cases': service.snapshot()['cases'],
            'journal': [canonical_bytes(e) for e in journal],
            'draw_indices': {e['advance_id']: i for i, e in enumerate(journal) if e['op'] == 'draw'},
            'receipt_ids': set(service.receipts),
            'overlay_ids': {e['overlay_id'] for e in entries},
            'receipt_bound': self.receipt_bound, 'overlay_bound': self.bounds['OVERLAY_MAX_ENTRIES']})
        frozen = copy.deepcopy((journal, entries, service.receipts))
        for key, body in self.bodies.items():
            if body['op'] == 'advance_day':
                status, receipt = self.invoke(body)
                assert status == 200 and receipt['transport_duplicate'], receipt
            elif self.http:
                status, receipt = self.session.operation(key)
                assert status == 200, receipt
            else:
                receipt = service.operation(key, service.instance_id)
            trace['reads'].append({'n': n, 'id': key, 'bytes': projection(receipt)})

        assert frozen == (service.machine.export_journal(), service.overlay_entries, service.receipts), 'receipt probes mutated stores'

    def step(self, cell):
        n = len(self.trace['steps'])
        if cell.get('kind') == 'restart':
            old = self.service.instance_id
            self.close()
            self.open()
            try:
                self.service.operation('draw', old)
            except ApiError as exc:
                self.trace['session_probes'].append(exc.code)
            else:
                self.trace['session_probes'].append('ACCEPTED_OLD_SESSION')
            results = []
        else:
            bodies = cell['commands']
            if cell.get('kind') == 'concurrent':
                barrier = threading.Barrier(len(bodies))
                def submit(body):
                    barrier.wait(timeout=10)
                    return self.invoke(body)
                with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
                    responses = list(pool.map(submit, bodies))
            else:
                responses = [self.invoke(b) for b in bodies]
            results = []
            # A duplicate may finish first. Its projection still is the first terminal result.
            for body, (status, receipt) in zip(bodies, responses):
                key = body['operation_id']
                results.append({'id': key, 'status': status, 'outcome': receipt.get('outcome'),
                                'error': receipt.get('error'), 'transport_duplicate': receipt.get('transport_duplicate', False),
                                'replay': cell.get('replay', False)})
                if status == 200:
                    self.trace['first'].setdefault(key, projection(receipt))
                    self.bodies.setdefault(key, body)
                    self.trace['reads'].append({'n': n, 'id': key, 'bytes': projection(receipt)})
                    if 'overlay_state_digest' in receipt:
                        self.trace['overlay_digests'].append({'n': n, 'receipt': receipt['overlay_state_digest'],
                            'folded': overlay.state_digest(overlay.fold(self.service.overlay_entries))})
        self.trace['steps'].append({**cell, 'n': n, 'results': results})
        self.observe()


def _run(cells, **kwargs):
    with tempfile.TemporaryDirectory(prefix='capital-invariants-') as directory:
        observer = Observer(directory, **kwargs)
        try:
            for cell in cells:
                observer.step(cell)
            return observer.trace
        finally:
            observer.close()


def _shared_face(fixture):
    # Derive amounts from the existing synthetic fixture; do not choose product limits.
    service = CapitalService()
    gross = service.fixtures.view(fixture)['claim']['gross']
    amount = gross * 3 // 4
    cells = []
    for suffix in ('a', 'b'):
        advance = 'sim-shared-' + suffix
        for op, args in (('offer', {'fixture_id': fixture, 'amount': amount}), ('approve', {})):
            cells.append({'commands': [command(op, op + suffix, advance, **args)]})
    cells.append({'kind': 'concurrent', 'commands': [command('draw', 'draw' + s, 'sim-shared-' + s) for s in ('a', 'b')]})
    cells.append({'kind': 'restart', 'commands': []})
    return _run(cells)


def _capacity():
    cells = [{'commands': [command('offer', f'capacity-{i}', fixture_id='sim-committed', amount=1000)]}
             for i in range(RECEIPT_BOUND)]
    cells += [{'commands': [command('approve', f'overflow-{i}')], 'capacity_probe': True} for i in range(2)]
    cells += [{'commands': [command('offer', 'capacity-0', fixture_id='sim-committed', amount=1000)], 'replay': True},
              {'kind': 'restart', 'commands': []},
              {'commands': [command('approve', 'overflow-restart')], 'capacity_probe': True},
              {'commands': [command('offer', 'capacity-0', fixture_id='sim-committed', amount=1000)], 'replay': True}]
    # No drawn subject: first tick stores binding + clock, second fills the third entry.
    cells += [{'commands': [tick('cap-tick-1', 0, 1)]}, {'commands': [tick('cap-tick-2', 1, 2)]}]
    cells += [{'commands': [tick(f'cap-overflow-{i}', 2, 3)], 'capacity_probe': True} for i in range(2)]
    cells += [{'commands': [tick('cap-tick-1', 0, 1)], 'replay': True}]
    cells += [{'kind': 'restart', 'commands': []},
              {'commands': [tick('cap-overflow-restart', 2, 3)], 'capacity_probe': True},
              {'commands': [tick('cap-tick-1', 0, 1)], 'replay': True}]
    with patch('capital.service.MAX_OPERATIONS', RECEIPT_BOUND):
        return _run(cells, receipt_bound=RECEIPT_BOUND, overlay_bound=OVERLAY_BOUND)


def _sigkill():
    """Crash-matrix SIGKILL cell, with first-result and retained-fact observations."""
    sim = _module('inv_sigkill_sim', ROOT / 'scripts/sim_journeys.py')
    matrix = _module('inv_crash_matrix', ROOT / 'tests/crash_matrix.py')
    with tempfile.TemporaryDirectory(prefix='capital-inv-sigkill-') as directory:
        observer = Observer(directory)
        server = sim.ServerProcess(directory)
        try:
            for step in matrix.SCRIPT[:matrix.SIGKILL_STEP - 1]:
                body = {k: v for k, v in step.items() if k not in ('step', 'boundary')}
                observer.step({'commands': [body]})
            observer.close()
            session = sim.Session(server.start())
            lost = matrix.SCRIPT[matrix.SIGKILL_STEP - 1]
            session.client.send_lost('/api/overlay/commands', {
                k: v for k, v in {**lost, 'instance_id': session.instance_id}.items()
                if k not in ('step', 'boundary')}, session.token)
            assert server.kill() == -signal.SIGKILL
            restarted = sim.Session(server.start())
            recovered_overlay = restarted.overlay()
            assert recovered_overlay['sim_day'] in (0, lost['to_sim_day'])
            status, recovered = restarted.get('/api/overlay?operation_id=' + lost['operation_id'])
            assert status == 200 and recovered['operation']['outcome'] in ('UNKNOWN', 'APPLIED')
            assert (recovered['operation']['outcome'] == 'APPLIED') == (recovered_overlay['sim_day'] == lost['to_sim_day'])
            restarted.client.fence.resolve(lost['operation_id'])
            assert restarted.state['workspace']['status'] == 'ACTIVE'
            for key, first in observer.trace['first'].items():
                status, receipt = restarted.operation(key)
                assert status == 200
                observer.trace['reads'].append({'n': 5, 'id': key, 'bytes': projection(receipt)})
            status, receipt = restarted.command('draw', matrix.ADVANCE, 'cr-draw')
            assert status == 200 and receipt['transport_duplicate']
            observer.trace['reads'].append({'n': 5, 'id': 'cr-draw', 'bytes': projection(receipt)})
            server.kill()
            observer.open()
            observer.trace['steps'].append({'n': 4, 'kind': 'sigkill', 'commands': [], 'results': []})
            observer.observe()
            observer.step({'commands': [command('draw', 'cr-draw', matrix.ADVANCE)], 'replay': True})
            # The lost write is UNKNOWN or APPLIED. Resolve it through the facade,
            # then retain its first observed receipt through the remaining matrix.
            lost_body = {k: v for k, v in lost.items() if k not in ('step', 'boundary')}
            observer.step({'commands': [lost_body]})
            for step in matrix.SCRIPT[matrix.SIGKILL_STEP:]:
                body = {k: v for k, v in step.items() if k not in ('step', 'boundary')}
                observer.step({'commands': [body]})
            return observer.trace
        finally:
            server.kill()
            # The file port may already have been closed before a failed server start.
            observer.close()


def run_corpus(seeds=SEEDS, *, fresh=False):
    seeds = tuple(seeds)
    if not fresh and seeds in _CACHE:
        return copy.deepcopy(_CACHE[seeds])
    available = loopback_available()
    traces = {str(seed): _run(generate_sequence(seed)) for seed in seeds}
    traces.update({fixture: _shared_face(fixture) for fixture in
                   ('sim-committed', 'demo-beta-festival', 'demo-gamma-tour')})
    traces['capacity'] = _capacity()
    if available:
        traces['loopback'] = _run(generate_sequence(seeds[0]), http=True)
        traces['sigkill'] = _sigkill()
    result = {'traces': traces, 'loopback': 'EXECUTED' if available else 'SKIPPED_LOOPBACK'}
    _CACHE[seeds] = copy.deepcopy(result)
    return result


def trace_digest(trace):
    """Pin sequential replies and concurrent multisets, excluding volatile context."""
    summary = []
    for cell in trace['steps']:
        outcomes = [(r['status'], r.get('outcome') or '', r.get('error') or '',
                     r['transport_duplicate']) for r in cell['results']]
        if cell.get('kind') == 'concurrent':
            outcomes.sort()
        summary.append((cell['n'], [(b['op'], b['args']) if 'args' in b else
                                  (b['op'], b['from_sim_day'], b['to_sim_day']) for b in cell['commands']], outcomes))
    return hashlib.sha256(canonical_bytes(summary)).hexdigest()


def load_table(path=None):
    table = upstream_claims.load_table(path or TABLE, format=FORMAT)
    validate_table(table)
    return table


def validate_table(table):
    upstream_claims.validate_table(table, format=FORMAT)
    if {r['check_id'] for r in table['claims']} != set(CHECKS):
        raise ClaimTableError('table must bind all five predicates')
    for row in table['claims']:
        if row['source_doc'] != SOURCE_DOC or row['section'] != '## 3. Five predicates and their observation boundary':
            raise ClaimTableError('wrong contract source or section')
        if row['expected'] is not True:
            raise ClaimTableError('invariant predicates must be expected true')
    if table.get('semantic_conformance') is not False or table.get('upstream_kernel_executed') is not False or table.get('vendored') is not False:
        raise ClaimTableError('scope flags must remain false')
    divergence = next((r for r in table['claims'] if r['id'] == 'inv.3.overlay_projection'), {})
    if (divergence.get('check_id') != 'inv3' or
            divergence.get('disposition') != 'DOCUMENTED_DIVERGENCE' or
            not isinstance(divergence.get('divergence'), str) or
            not all(field in divergence['divergence'] for field in ('instance_id', 'overlay_state_digest', 'transport_duplicate'))):
        raise ClaimTableError('overlay projection must be a documented divergence')
    pin = table.get('pin_consumer', {})
    for field in ('repository', 'full_sha', 'target_path', 'consumption_scope', 'consumer', 'verification', 'pin_class', 'note_registration'):
        if not pin.get(field):
            raise ClaimTableError('pin_consumer missing ' + field)
    if pin['full_sha'] != PINNED_SHA or pin['target_path'] != SOURCE_DOC or pin['pin_class'] != 'EXECUTABLE_CITATION' or pin['note_registration'] != 'PENDING_NOTE_REGISTRATION':
        raise ClaimTableError('invalid pin consumer declaration')
    pinned = table.get('pinned_seeds', {})
    if (pinned.get('base_seed'), pinned.get('count'), pinned.get('seeds')) != (BASE_SEED, len(SEEDS), list(SEEDS)):
        raise ClaimTableError('pinned seed list drift')
    return table


def check_protocol(protocol_dir, table=None):
    table = load_table() if table is None else validate_table(table)
    report = upstream_claims.check_protocol(protocol_dir, table, format=FORMAT)
    # Needles must occur in the cited section, rather than anywhere in the document.
    path = Path(protocol_dir) / SOURCE_DOC
    if path.is_file() and path.resolve().is_relative_to(Path(protocol_dir).resolve()):
        text = path.read_text(encoding='utf-8')
        heading = '## 3. Five predicates and their observation boundary'
        section = text.split(heading, 1)[-1].split('\n## ', 1)[0] if heading in text else ''
        for row in table['claims']:
            if row['needle'] not in section and not any(m['id'] == row['id'] for m in report['missing']):
                report['missing'].append({'id': row['id'], 'problem': 'needle outside section'})
        report['verified'] = report['total'] - len({m['id'] for m in report['missing']})
        report['status'] = 'failed' if report['missing'] else 'verified'
    return report


def run_claims(table, corpus=None):
    validate_table(table)
    corpus = run_corpus() if corpus is None else corpus
    rows = []
    for row in table['claims']:
        violations = {name: result['violations'] for name, trace in corpus['traces'].items()
                      if not (result := CHECKS[row['check_id']](trace))['ok']}
        rows.append({'id': row['id'], 'ok': (not violations) == row['expected'], 'violations': violations})
    return {'label': LABEL, 'simulation': 'SIMULATED', 'passed': sum(r['ok'] for r in rows),
            'total': len(rows), 'ok': all(r['ok'] for r in rows), 'rows': rows, 'loopback': corpus['loopback']}


def seed_digests(corpus):
    return {str(seed): trace_digest(corpus['traces'][str(seed)]) for seed in SEEDS}
