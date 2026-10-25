#!/usr/bin/env python3
"""Seeded, deterministic SIMULATED journeys T03-sim through T06-sim over the loopback HTTP API.

All four journeys are scripts of fixed operation ids against a real ``capital.server`` on
127.0.0.1. They are Capital-local simulations. They are not the T03-T06 rungs of the
acceptance ladder, claim no qualification, move no funds, and call no provider.

T03-sim: the zero-exception full lifecycle of one advance in process (default pinned
FSM): offer, approve, bind_settlement, draw, advance_day accrual under the ACT/365
memo ledger, a full F04 repay of the outstanding principal, and close. Interest stays
a memo (interest_payments.status NONE_YET): these journeys deliberately use direct
F04 repay, so no overlay payment is posted and unpaid interest keeps close_ready false.

T04-sim: the auditor evidence chain on a ``python3 -m capital.server --workspace``
subprocess. The seeded demo book is replayed over HTTP and its state_digest is checked
against the seeded-demo pin, an auditor role is bound through POST /api/session, the
organizer advances the clock, and the auditor reads the overlay, the risk rollup, the
terms portfolio and the reconciliation (all MATCHED), then exports the manifest to a
file. ``python3 -m capital.verify FILE`` rechecks the manifest and
``python3 -m capital.verify --workspace DIR`` audits the live workspace read-only; both
run as subprocesses. The auditor token can neither advance the clock nor post a command.

T05-sim: partial allocation of the shared open face by two advances, ticks, a repay, a
partial refund on the settlement book mid-repay (the pinned refusal REFUND_OBLIGATION_OPEN
and DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED, shown beside the shadow refund split), a
margin call, a cure, an acceleration, late cash quoted and repaid by a human, a close, and a
DEFAULT_ELIGIBLE proposal that a human turns into a default. Capital has no HTTP route for
settlement events, so the refund is replayed on the disposable in-process book out of
band. That step is labelled SIMULATED_OUT_OF_BAND_SETTLEMENT_EVENT. Margin rules fire only
on such a disposable book, which is why T05-sim runs in process and not on a --workspace
subprocess.

T06-sim: a ``python3 -m capital.server --workspace`` subprocess is killed with SIGKILL and
restarted on the same directory. A lost response is fenced (UNKNOWN is never retried), the
stale instance gets SESSION_CHANGED, receipts are restored, and nothing is replayed. An
agent EXECUTE attempt is refused and a human executes the agent's proposal, citing
proposal_id on the receipt.

Each journey's step list is pinned by digest in tests/golden/journey_t03_sim.json,
journey_t04_sim.json, journey_t05_sim.json and journey_t06_sim.json. A mismatch or a
missing golden exits 1 unless --update-golden is passed. The golden carries no
instance id, token, port, path, or timestamp.

Output ends with ``SIM_JOURNEYS {json}`` and ``sim journeys ok SIMULATED ...``.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import margin
from capital.agent_lane import ACTIVE_GENERATION, ACTIVE_GRANT_ID
from capital.producer import PinnedFsmProducer
from capital.server import make_server

SEED = 'CAPITAL-SIM-JOURNEYS-V1'
LABEL = 'SIMULATED'
GOLDEN_DIR = ROOT / 'tests' / 'golden'
GOLDEN_FILES = {
    'T03-sim': 'journey_t03_sim.json', 'T04-sim': 'journey_t04_sim.json',
    'T05-sim': 'journey_t05_sim.json', 'T06-sim': 'journey_t06_sim.json',
}
JOURNEY_IDS = tuple(GOLDEN_FILES)
OUT_OF_BAND = 'SIMULATED_OUT_OF_BAND_SETTLEMENT_EVENT'
LISTEN_TIMEOUT = 20.0
REQUEST_TIMEOUT = 5
# Fixture units on the pinned open face, never a product limit, fee or allocation.
T03_AMOUNT = 30_000
T04_TICK_DAYS = 10
T05_A, T05_B = 48_000, 20_000
T05_B_REPAY = 5_000
T05_LATE_CASH = 5_000
VOLATILE_KEYS = frozenset({
    'instance_id', 'created_at', 'saved_at', 'timestamp', 'timestamps',
    'local_token', 'saved_by_instance', 'port', 'path', 'pid',
})


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_demo = _load('seed_demo')
diff_paths = seed_demo.diff_paths
render = seed_demo.render


class JourneyError(Exception):
    pass


class FenceError(JourneyError):
    """A write was attempted while an earlier write has no known outcome."""


class Fence:
    """Client-side UNKNOWN fence. No write leaves the process while an outcome is unresolved."""

    def __init__(self):
        self.unresolved = {}

    def hold(self, operation_id):
        self.unresolved[operation_id] = 'UNKNOWN'

    def resolve(self, operation_id):
        self.unresolved.pop(operation_id, None)

    def guard(self):
        if self.unresolved:
            raise FenceError('UNKNOWN outcome: ' + ','.join(sorted(self.unresolved)))


class Client:
    """Loopback http.client with no retry. The log holds every request that left the process."""

    def __init__(self, port):
        self.port = port
        self.fence = Fence()
        self.log = []

    def _connection(self):
        return http.client.HTTPConnection('127.0.0.1', self.port, timeout=REQUEST_TIMEOUT)

    @staticmethod
    def _operation_id(body):
        if type(body) is dict and type(body.get('operation_id')) is str:
            return body['operation_id']
        return None

    def request(self, method, path, body=None, token=None):
        headers = {}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        if token is not None:
            headers['X-Capital-Token'] = token
        if method == 'POST':
            self.fence.guard()
        self.log.append((method, path.split('?', 1)[0], self._operation_id(body)))
        connection = self._connection()
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            data = json.loads(response.read().decode())
            return response.status, data
        finally:
            connection.close()

    def send_lost(self, path, body, token):
        """POST and discard the response. The outcome is UNKNOWN until looked up."""
        operation_id = self._operation_id(body)
        self.fence.guard()
        self.fence.hold(operation_id)
        self.log.append(('POST', path, operation_id))
        connection = self._connection()
        try:
            connection.request('POST', path, body=json.dumps(body).encode(), headers={
                'Content-Type': 'application/json', 'X-Capital-Token': token})
        finally:
            connection.close()

    def posted_operation_ids(self):
        return [operation_id for method, _path, operation_id in self.log
                if method == 'POST' and operation_id is not None]


class Journey:
    """Ordered step records. A step whose actual value differs from its expectation raises."""

    def __init__(self, journey_id):
        self.id = journey_id
        self.steps = []

    def step(self, name, kind, actual, expect, **facts):
        if actual != expect:
            raise JourneyError(f'{self.id} step {len(self.steps) + 1} {name}: {actual!r} != {expect!r}')
        record = {'n': len(self.steps) + 1, 'name': name, 'kind': kind, 'status': actual, 'expect': expect}
        if facts:
            record['facts'] = facts
        self.steps.append(record)

    def result(self):
        body = {
            'journey': self.id,
            'label': LABEL,
            'seed': SEED,
            'funds_executed': False,
            'integrated': False,
            'qualification_claimed': False,
            'steps': self.steps,
            'step_count': len(self.steps),
        }
        body['digest'] = hashlib.sha256(
            json.dumps(self.steps, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        body = json.loads(json.dumps(body))
        _reject_volatile(body)
        return body


def _reject_volatile(value, path='$'):
    if type(value) is dict:
        for key, item in value.items():
            if key in VOLATILE_KEYS:
                raise JourneyError(f'volatile key {path}.{key}')
            _reject_volatile(item, path + '.' + key)
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_volatile(item, f'{path}[{index}]')


class Session:
    """One organizer-bound client against one server instance."""

    def __init__(self, port):
        self.client = Client(port)
        self.state = None
        self.instance_id = None
        self.token = None
        self.refresh()

    def refresh(self):
        status, state = self.client.request('GET', '/api/state')
        if status != 200:
            raise JourneyError(f'state {status}')
        self.state = state
        self.instance_id = state['instance_id']
        self.token = state['local_token']
        return state

    def get(self, path):
        return self.client.request('GET', path, token=self.token)

    def command(self, op, advance, key, instance=None, proposal_id=None, token=None, **args):
        body = {'instance_id': instance or self.instance_id, 'operation_id': key, 'op': op,
                'advance_id': advance, 'args': args}
        if proposal_id is not None:
            body['proposal_id'] = proposal_id
        return self.client.request('POST', '/api/commands', body, token or self.token)

    def tick(self, key, start, end):
        return self.client.request('POST', '/api/overlay/commands', {
            'instance_id': self.instance_id, 'operation_id': key, 'op': 'advance_day',
            'from_sim_day': start, 'to_sim_day': end, 'reason': 'SIM_JOURNEY'}, self.token)

    def operation(self, operation_id, instance=None):
        return self.get(f'/api/operations/{operation_id}?instance_id={instance or self.instance_id}')

    def overlay(self):
        status, body = self.get('/api/overlay')
        if status != 200:
            raise JourneyError(f'overlay {status}')
        return body

    def advance_row(self, advance_id):
        return next(row for row in self.overlay()['advances'] if row['advance_id'] == advance_id)


def _outcome(response):
    status, body = response
    return (status, body.get('outcome'), body.get('error'))


def _drive(journey, session, label, op, advance, key, **args):
    """A command that must be ACCEPTED."""
    response = session.command(op, advance, key, **args)
    journey.step(label, 'HTTP', _outcome(response), (200, 'ACCEPTED', None), op=op, advance_id=advance)
    return response[1]


def _tick(journey, session, key, start, end, label=None):
    status, body = session.tick(key, start, end)
    journey.step(label or f'advance_day {start}->{end}', 'HTTP', (status, body.get('outcome')), (200, 'APPLIED'),
                 sim_day=end)
    return body


# ----------------------------------------------------------------------- T03-sim

def run_t03():
    """Zero-exception lifecycle: offer -> approve -> bind -> draw -> accrue -> repay -> close."""
    journey = Journey('T03-sim')
    advance = 'sim-t03-a'
    with _InProcessServer(PinnedFsmProducer()) as port:
        session = Session(port)
        journey.step('organizer session on an in-process server', 'PROCESS',
                     (session.state['workspace']['kind'], session.state['funds_executed']),
                     ('MEMORY', False), label=LABEL)
        _drive(journey, session, f'offer {advance}', 'offer', advance, 't03-offer',
               fixture_id='sim-committed', amount=T03_AMOUNT)
        _drive(journey, session, f'approve {advance}', 'approve', advance, 't03-approve')
        _drive(journey, session, f'bind_settlement {advance}', 'bind_settlement', advance, 't03-bind')
        _drive(journey, session, f'draw {advance}', 'draw', advance, 't03-draw')
        row = session.advance_row(advance)
        journey.step('the advance is DRAWN from sim_day 0', 'HTTP',
                     (row['phase'], row['principal_outstanding_krw'], row['draw_day'],
                      row['accrued_through_sim_day'], row['interest_due_krw']),
                     ('DRAWN', T03_AMOUNT, 0, 0, 0),
                     tier=row['tier'], maturity_day=row['maturity_day'],
                     contract_bps=row['contract_bps'], margin_state=row['margin']['state'])
        status, receipt = session.operation('t03-draw')
        journey.step('the draw receipt is queryable by operation id', 'HTTP',
                     (status, receipt['outcome'], receipt['transport_duplicate']),
                     (200, 'ACCEPTED', False))

        _tick(journey, session, 't03-tick-1', 0, 15)
        row = session.advance_row(advance)
        journey.step('ACT/365 memo interest accrues through sim_day 15', 'HTTP',
                     (row['phase'], row['accrued_through_sim_day'], row['interest_due_krw'] > 0,
                      row['default_interest_due_krw'], row['close_ready']),
                     ('DRAWN', 15, True, 0, False),
                     interest_due_krw=row['interest_due_krw'],
                     cumulative_exact_contract=row['cumulative_exact_contract'],
                     carried_remainder_contract=row['carried_remainder_contract'])
        _tick(journey, session, 't03-tick-2', 15, 30)
        accrued_15 = row['interest_due_krw']
        row = session.advance_row(advance)
        journey.step('ACT/365 memo interest accrues through sim_day 30', 'HTTP',
                     (row['accrued_through_sim_day'], row['interest_due_krw'] > accrued_15,
                      row['default_interest_due_krw'], row['close_ready']),
                     (30, True, 0, False),
                     interest_due_krw=row['interest_due_krw'],
                     cumulative_exact_contract=row['cumulative_exact_contract'],
                     carried_remainder_contract=row['carried_remainder_contract'])

        status, recon = session.get('/api/reconciliation')
        journey.step('reconciliation is clean including the overlay fold check', 'HTTP',
                     (status, recon['status'], sorted({check['status'] for check in recon['checks']})),
                     (200, 'MATCHED', ['MATCHED']),
                     checks=[check['id'] for check in recon['checks']])
        status, risk = session.get('/api/risk')
        journey.step('the risk rollup is bound and reconciles to the projection', 'HTTP',
                     (status, risk['status'], risk['reconciliation']['matched'],
                      risk['totals']['outstanding_krw']),
                     (200, 'BOUND', True, T03_AMOUNT),
                     risk_digest=risk['risk_digest'], sim_day=risk['sim_day'])

        cash = row['principal_outstanding_krw'] + row['interest_due_krw'] + row['default_interest_due_krw']
        status, quote = session.get(
            f'/api/terms/{advance}/allocation?instance_id={session.instance_id}&as_of_day=30&cash={cash}')
        journey.step('the full-repayment allocation quote', 'HTTP',
                     (status, quote['allocation']['status'], quote['close_ready']),
                     (200, 'BOUND', True), cash=cash, tier=quote['tier'],
                     order=quote['allocation']['order'],
                     to_interest=quote['allocation']['to_interest'],
                     to_principal=quote['allocation']['to_principal'],
                     fsm_repay=quote['fsm_repay'])
        _drive(journey, session, 'repay the outstanding principal in full', 'repay', advance,
               't03-repay', amount=row['principal_outstanding_krw'], sequence=1)
        row = session.advance_row(advance)
        journey.step('principal is zero; the unpaid interest memo keeps it not close-ready', 'HTTP',
                     (row['phase'], row['principal_outstanding_krw'], row['close_ready'],
                      session.overlay()['interest_payments']['status']),
                     ('DRAWN', 0, False, 'NONE_YET'),
                     interest_due_krw=row['interest_due_krw'])
        _drive(journey, session, f'close {advance}', 'close', advance, 't03-close')
        state = session.refresh()
        journey.step('the advance is CLOSED', 'HTTP',
                     {c['advance_id']: c['phase'] for c in state['cases']}, {advance: 'CLOSED'})

        receipt = _tick(journey, session, 't03-tick-3', 30, 45, 'advance_day 30->45 after close')
        row = session.advance_row(advance)
        journey.step('no interest accrues after close', 'HTTP',
                     (receipt['postings'], row['accrued_through_sim_day'], row['phase']),
                     ([], 30, 'CLOSED'), interest_due_krw=row['interest_due_krw'])
        state = session.refresh()
        overlay = session.overlay()
        status, risk = session.get('/api/risk')
        journey.step('final phases and digests', 'HTTP',
                     {c['advance_id']: c['phase'] for c in state['cases']}, {advance: 'CLOSED'},
                     sim_day=overlay['sim_day'], overlay_state_digest=overlay['overlay_state_digest'],
                     interest_payments=overlay['interest_payments']['status'],
                     risk_digest=risk['risk_digest'], state_digest=state['state_digest'],
                     operation_count=state['operation_count'], funds_executed=state['funds_executed'])
        _audit_no_replay(journey, session.client.posted_operation_ids())
    return journey.result()


# ----------------------------------------------------------------------- T05-sim

class _InProcessServer:
    def __init__(self, producer):
        self.server = make_server(0, producer=producer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server.server_port

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


def _margin_facts(row):
    margin_row = row['margin']
    return {
        'advance_id': row['advance_id'],
        'principal_outstanding_krw': row['principal_outstanding_krw'],
        'margin_state': margin_row['state'],
        'base_krw': margin_row['base_krw'],
        'cure_deadline': margin_row['cure_deadline'],
        'default_eligible_day': margin_row['default_eligible_day'],
        'interest_rebased': margin_row['interest_rebased'],
    }


def _reserved_by_claim(statement):
    """reserved_open per claim. Advances on one claim share that figure, so it is never summed per advance."""
    for category in statement.get('categories', []):
        if category.get('id') == 'reserved':
            claims = {}
            for row in category['rows']:
                if claims.setdefault(row['claim_id'], row['reserved_open']) != row['reserved_open']:
                    raise JourneyError('reserved_open differs between advances of one claim')
            return claims
    raise JourneyError('statement has no reserved category')


def _audit_no_replay(journey, posted):
    journey.step('no operation id was posted twice', 'AUDIT', len(posted) == len(set(posted)), True,
                 posted=len(posted))


def run_t05():
    journey = Journey('T05-sim')
    source = margin.ScenarioReplaySource()
    with _InProcessServer(PinnedFsmProducer(fixtures=source)) as port:
        session = Session(port)
        a, b = 'sim-a', 'sim-b'

        # Partial allocation: two advances reserve part of the organizer line.
        for advance, amount, prefix in ((a, T05_A, 'a'), (b, T05_B, 'b')):
            _drive(journey, session, f'offer {advance}', 'offer', advance, f'{prefix}-offer',
                   fixture_id='sim-committed', amount=amount)
            _drive(journey, session, f'approve {advance}', 'approve', advance, f'{prefix}-approve')
            _drive(journey, session, f'bind_settlement {advance}', 'bind_settlement', advance, f'{prefix}-bind')
            _drive(journey, session, f'draw {advance}', 'draw', advance, f'{prefix}-draw')
        status, statement = session.get('/api/statement')
        reserved = _reserved_by_claim(statement)
        line = next(item for item in session.state['fixtures']['sim-committed']['claim']['obligations']
                    if item['payee'] == 'organizer')['face']
        journey.step('partial allocation reserved on the organizer line', 'HTTP',
                     (status, sorted(reserved), reserved['sim-committed'] < line),
                     (200, ['sim-committed'], True),
                     advances={a: T05_A, b: T05_B}, reserved_open_on_claim=reserved['sim-committed'],
                     organizer_line_face=line, unreserved_remainder=line - reserved['sim-committed'])
        _tick(journey, session, 't-1', 0, 2)
        journey.step('no margin call before the refund', 'HTTP',
                     [session.advance_row(x)['margin']['state'] for x in (a, b)], ['WITHIN_BASE', 'WITHIN_BASE'])

        # Repay mid-journey.
        _drive(journey, session, 'repay sim-b', 'repay', b, 'b-repay-1', amount=T05_B_REPAY, sequence=1)

        # Settlement event: partial refund on the disposable book, out of band.
        outcomes = source.replay('sim-committed', 'partial-before')
        journey.step(
            'partial refund before allocation replayed on the disposable settlement book', 'SETTLEMENT_EVENT',
            [(item['op'], item['error'], item['matched']) for item in outcomes],
            [('observe_settlement_statement', None, True), ('bind_refund', None, True),
             ('apply_distribution', 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED', True)],
            label=OUT_OF_BAND, scope='DISPOSABLE_BOOK_ONLY')

        # The pinned refusal beside the shadow split.
        refused = session.command('offer', 'sim-c', 'c-offer', fixture_id='sim-committed', amount=1_000)
        journey.step('pinned refusal while the refund obligation is open', 'HTTP', _outcome(refused),
                     (200, 'REJECTED', 'REFUND_OBLIGATION_OPEN'), advance_id='sim-c')
        status, shadow = session.get('/api/policy/shadow')
        item = next(row for row in shadow['items'] if row['item'] == 'refund_bearer')
        journey.step(
            'shadow refund split beside the pinned refusal', 'HTTP',
            (status, item['pinned']['status'], item['shadow']['status'], shadow['applied_to_fsm']),
            (200, 'UNSUPPORTED_BY_PINNED_FSM', 'SHADOW_COMPUTED', False),
            label=shadow['mode'], provenance=shadow['provenance'],
            vector='frozen partial-after input, not the live book', policy_adopted=shadow['policy_adopted'],
            per_class=[{'reason_class': entry['refunds'][0]['reason_class'],
                        'lines': entry['cumulative']['lines'],
                        'reconciliation': entry['cumulative']['reconciliation']}
                       for entry in item['shadow']['per_class']])
        journey.step('breach awaits a tick after the refund; sim-b stays within the base', 'HTTP',
                     [session.advance_row(x)['margin']['state'] for x in (a, b)],
                     ['BREACH_AWAITING_TICK', 'WITHIN_BASE'])

        # Margin call.
        _tick(journey, session, 't-2', 2, 3, 'advance_day 2->3 margin call')
        called = session.advance_row(a)
        journey.step('sim-a is called', 'HTTP', (called['margin']['state'], session.advance_row(b)['margin']['state']),
                     ('CALLED', 'WITHIN_BASE'), **_margin_facts(called))
        deadline = called['margin']['cure_deadline']

        # No cure. The deadline day is inclusive; one day later the advance accelerates.
        _tick(journey, session, 't-3', 3, deadline, f'advance_day 3->{deadline} deadline inclusive')
        journey.step('the deadline day is still inside the window', 'HTTP',
                     session.advance_row(a)['margin']['state'], 'CALLED')
        _tick(journey, session, 't-4', deadline, deadline + 1, 'advance_day deadline->deadline+1 acceleration')
        accelerated = session.advance_row(a)
        journey.step('sim-a accelerated; interest is re-based (CAPITAL_DEFAULT_RECOVERY.md §4.10)', 'HTTP', accelerated['margin']['state'],
                     'ACCELERATED', interest_basis='REBASED', **_margin_facts(accelerated))
        eligible_day = accelerated['margin']['default_eligible_day']

        # Late cash after acceleration. The allocation endpoint refuses once the refund has lowered the
        # base (tier NOT_APPLICABLE), so the split is the overlay's adopted order applied to memo dues.
        status, quote = session.get(
            f'/api/terms/{a}/allocation?instance_id={session.instance_id}&as_of_day={deadline + 1}'
            f'&cash={T05_LATE_CASH}')
        journey.step('the allocation quote is not applicable after the refund', 'HTTP',
                     (status, quote['tier'], quote['allocation']['status']), (200, 'NOT_APPLICABLE', 'NOT_APPLICABLE'),
                     cash=T05_LATE_CASH)
        dues = session.advance_row(a)
        interest = dues['interest_due_krw'] + dues['default_interest_due_krw']
        late_principal = T05_LATE_CASH - interest
        journey.step('late cash splits interest first; interest payments stay NONE_YET', 'HTTP',
                     (late_principal > 0, session.overlay()['interest_payments']['status']), (True, 'NONE_YET'),
                     cash=T05_LATE_CASH, order=dues['allocation']['order'],
                     interest_due_krw=dues['interest_due_krw'],
                     default_interest_due_krw=dues['default_interest_due_krw'], principal_share_krw=late_principal)
        _drive(journey, session, 'human repay of the late-cash principal share', 'repay', a, 'a-repay-late',
               amount=late_principal, sequence=1)
        later = session.advance_row(a)
        journey.step('acceleration is not reversed by late cash', 'HTTP', later['margin']['state'],
                     'ACCELERATED', principal_outstanding_krw=later['principal_outstanding_krw'])

        # Repay sim-b to zero and close it.
        remaining = session.advance_row(b)['principal_outstanding_krw']
        _drive(journey, session, 'repay sim-b to zero', 'repay', b, 'b-repay-final', amount=remaining, sequence=2)
        closing = session.advance_row(b)
        journey.step('interest payments are not recorded, so the overlay is not close-ready', 'HTTP',
                     (closing['close_ready'], session.overlay()['interest_payments']['status']),
                     (False, 'NONE_YET'))
        _drive(journey, session, 'human close sim-b', 'close', b, 'b-close')

        # Default-eligible proposal, then a human default.
        _tick(journey, session, 't-5', deadline + 1, eligible_day,
              f'advance_day to the default-eligible day {eligible_day}')
        block = session.overlay()['margin']
        journey.step('one DEFAULT_ELIGIBLE proposal; the FSM default is not called', 'HTTP',
                     (len(block['proposals']), block['proposals'][0]['proposal_kind'],
                      block['f04_default_called'], block['proposal_only']),
                     (1, 'DEFAULT_ELIGIBLE', False, True), default_eligible_day=eligible_day)
        journey.step('the advance is still DRAWN before a human acts', 'HTTP', session.advance_row(a)['phase'],
                     'DRAWN')
        _drive(journey, session, 'human default sim-a', 'default', a, 'a-default')
        state = session.refresh()
        journey.step('final phases', 'HTTP', {c['advance_id']: c['phase'] for c in state['cases']},
                     {a: 'DEFAULTED', b: 'CLOSED'}, state_digest=state['state_digest'],
                     operation_count=state['operation_count'], funds_executed=state['funds_executed'])
        _audit_no_replay(journey, session.client.posted_operation_ids())
    return journey.result()


# ----------------------------------------------------------------------- T06-sim

class ServerProcess:
    """``python3 -m capital.server --port 0 --workspace DIR`` on loopback. Killed with SIGKILL."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'capital.server', '--port', '0', '--workspace', os.fspath(self.workspace)],
            cwd=os.fspath(ROOT), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        deadline = time.monotonic() + LISTEN_TIMEOUT
        pattern = re.compile(r'^KIX Capital simulation: http://127\.0\.0\.1:(\d+)$')
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                break
            match = pattern.match(line.strip())
            if match:
                return int(match.group(1))
        self.kill()
        raise JourneyError('server did not report a listening port')

    def kill(self):
        process, self.process = self.process, None
        if process is None:
            return None
        if process.poll() is None:
            process.send_signal(signal.SIGKILL)
        code = process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()
        return code


def _agent_body(**extra):
    body = {'grant_id': ACTIVE_GRANT_ID, 'generation': ACTIVE_GENERATION, 'now': 10}
    body.update(extra)
    return body


def _wait_known(session, operation_id):
    """Look an operation up by id. Polls reads only; a write is never re-sent."""
    deadline = time.monotonic() + REQUEST_TIMEOUT
    while True:
        status, body = session.operation(operation_id)
        if body.get('outcome') != 'UNKNOWN' or time.monotonic() > deadline:
            return status, body
        time.sleep(0.05)


def _lookup(session, operation_id):
    status, body = session.operation(operation_id)
    if status != 200 or body.get('outcome') not in ('ACCEPTED', 'REJECTED'):
        raise JourneyError(f'lookup {operation_id}: {status} {body.get("outcome")}')
    return body


def _command_total(counters):
    total = 0
    for value in counters.values() if type(counters) is dict else ():
        if type(value) is int:
            total += value
        elif type(value) is dict:
            total += _command_total(value)
    return total


def run_t06():
    journey = Journey('T06-sim')
    advance = 'sim-t06-a'
    with tempfile.TemporaryDirectory(prefix='capital-sim-t06-') as tmp:
        server = ServerProcess(Path(tmp))
        try:
            session = Session(server.start())
            client = session.client
            old_instance, old_token = session.instance_id, session.token
            journey.step('organizer session on a --workspace server', 'PROCESS',
                         (session.state['workspace']['kind'], session.state['funds_executed']),
                         ('LOCAL_FILE_WORKSPACE', False), label=LABEL)
            status, agent = client.request('POST', '/api/session', {'role': 'agent'}, session.token)
            journey.step('agent role bound', 'HTTP', (status, agent.get('role'), agent.get('agent_grant')),
                         (200, 'agent', 'NOT_BOUND'))
            agent_token = agent['local_token']

            for op, key, args in (('offer', 'o-offer', {'fixture_id': 'sim-committed', 'amount': 20_000}),
                                  ('approve', 'o-approve', {}), ('bind_settlement', 'o-bind', {}),
                                  ('draw', 'o-draw', {})):
                _drive(journey, session, f'{op} {advance}', op, advance, key, **args)
            _tick(journey, session, 'o-tick-1', 0, 5)

            # Agent: query, propose, and an EXECUTE attempt that is refused.
            status, grant = client.request('POST', '/api/agent/query_grant', _agent_body(), agent_token)
            journey.step('agent queries its grant', 'HTTP',
                         (status, grant['grant']['phase'], grant['workspace_mutated']), (200, 'ACTIVE', False),
                         authority=grant['grant']['authority'])
            proposal = _agent_body(proposal_id='sim-t06-proposal', surface='capital:repay', amount=10_000,
                                   kind='PROPOSE')
            status, proposed = client.request('POST', '/api/agent/propose_action', proposal, agent_token)
            journey.step('agent proposes a repay', 'HTTP',
                         (status, proposed['proposal']['phase'], proposed['proposal']['effects_executed']),
                         (200, 'HUMAN_PENDING', False))
            before = session.refresh()
            frozen = (before['state_digest'], before['operation_count'])
            status, refused = client.request('POST', '/api/agent/execute', _agent_body(kind='EXECUTE'), agent_token)
            journey.step('agent EXECUTE is refused', 'HTTP', (status, refused.get('error')),
                         (403, 'EXECUTE_AUTHORITY_DISABLED'))
            execute = _agent_body(proposal_id='sim-t06-exec', surface='capital:repay', amount=10_000, kind='EXECUTE')
            status, refused = client.request('POST', '/api/agent/propose_action', execute, agent_token)
            journey.step('agent propose_action with kind EXECUTE is refused', 'HTTP',
                         (status, refused.get('error')), (403, 'EXECUTE_AUTHORITY_DISABLED'))
            status, denied = session.command('repay', advance, 'x-agent-repay', token=agent_token,
                                             amount=10_000, sequence=1)
            journey.step('the agent token cannot submit a command', 'HTTP', (status, denied.get('error')),
                         (403, 'ROLE_FORBIDDEN'))
            after = session.refresh()
            journey.step('refused agent calls changed nothing', 'HTTP',
                         (after['state_digest'], after['operation_count']), frozen,
                         state_digest=after['state_digest'], operation_count=after['operation_count'])

            # A human executes the proposal and cites it.
            status, receipt = session.command('repay', advance, 'h-repay-proposal',
                                              proposal_id='sim-t06-proposal', amount=10_000, sequence=1)
            journey.step('a human executes the proposal with proposal_id on the receipt', 'HTTP',
                         (status, receipt.get('outcome'), receipt.get('proposal_id'), receipt.get('role'),
                          receipt.get('funds_executed')),
                         (200, 'ACCEPTED', 'sim-t06-proposal', 'organizer', False))
            status, memo = client.request('POST', '/api/agent/propose_action', proposal, agent_token)
            journey.step('the proposal is still a pending memo that executed no effect itself', 'HTTP',
                         (status, memo['duplicate'], memo['proposal']['phase'], memo['proposal']['effects_executed']),
                         (200, True, 'HUMAN_PENDING', False))

            # Lost response and UNKNOWN fencing.
            lost = {'instance_id': session.instance_id, 'operation_id': 'h-repay-lost', 'op': 'repay',
                    'advance_id': advance, 'args': {'amount': 4_000, 'sequence': 2}}
            client.send_lost('/api/commands', lost, session.token)
            fenced = 'SENT'
            try:
                session.command('repay', advance, 'h-repay-blocked', amount=1, sequence=3)
            except FenceError:
                fenced = 'FENCED_NO_NETWORK_CALL'
            journey.step('a write while an outcome is UNKNOWN never leaves the process', 'FENCE', fenced,
                         'FENCED_NO_NETWORK_CALL', held=sorted(client.fence.unresolved))
            status, known = _wait_known(session, 'h-repay-lost')
            client.fence.resolve('h-repay-lost')
            journey.step('lookup by operation id finds the lost response', 'HTTP',
                         (status, known.get('outcome'), known.get('transport_duplicate')),
                         (200, 'ACCEPTED', False))
            status, unknown = session.operation('h-never-sent')
            journey.step('a never-sent operation id is UNKNOWN and not authorized for retry', 'HTTP',
                         (status, unknown.get('outcome'), unknown.get('retry_authorized')), (200, 'UNKNOWN', False))

            # State to compare across the kill.
            pre = session.refresh()
            pre_overlay = session.overlay()
            pre_receipts = {key: _lookup(session, key) for key in
                            ('o-offer', 'o-draw', 'h-repay-proposal', 'h-repay-lost')}
            journey.step('state recorded before the kill', 'HTTP', pre['workspace']['status'], 'ACTIVE',
                         state_digest=pre['state_digest'], operation_count=pre['operation_count'],
                         overlay_state_digest=pre_overlay['overlay_state_digest'], sim_day=pre_overlay['sim_day'])
            posted = client.posted_operation_ids()

            # Kill and restart on the same workspace.
            journey.step('server killed with SIGKILL', 'PROCESS', server.kill(), -signal.SIGKILL)
            restarted = Session(server.start())
            journey.step('server restarted on the same workspace', 'PROCESS',
                         (restarted.state['workspace']['status'], restarted.instance_id != old_instance),
                         ('ACTIVE', True), workspace_kind=restarted.state['workspace']['kind'])
            status, body = restarted.client.request('POST', '/api/commands', {
                'instance_id': old_instance, 'operation_id': 'h-after-restart-old-token', 'op': 'repay',
                'advance_id': advance, 'args': {'amount': 1, 'sequence': 3}}, old_token)
            journey.step('the stale token is refused', 'HTTP', (status, body.get('error')),
                         (403, 'LOCAL_TOKEN_REQUIRED'))
            status, body = restarted.command('repay', advance, 'h-after-restart-stale-instance',
                                             instance=old_instance, amount=1, sequence=3)
            journey.step('the stale instance gets SESSION_CHANGED', 'HTTP', (status, body.get('error')),
                         (409, 'SESSION_CHANGED'))
            status, body = restarted.operation('h-repay-lost', instance=old_instance)
            journey.step('a lookup under the old instance gets SESSION_CHANGED', 'HTTP',
                         (status, body.get('error')), (409, 'SESSION_CHANGED'))

            # Receipts restored, nothing replayed.
            post = restarted.state
            post_overlay = restarted.overlay()
            journey.step('digests and counts survive the restart unchanged', 'HTTP',
                         (post['state_digest'], post['operation_count'], post_overlay['overlay_state_digest']),
                         (pre['state_digest'], pre['operation_count'], pre_overlay['overlay_state_digest']),
                         state_digest=post['state_digest'], operation_count=post['operation_count'])
            restored = {key: _lookup(restarted, key) for key in pre_receipts}
            journey.step('receipts are restored unchanged, with the original instance id', 'HTTP',
                         (restored == pre_receipts, all(r['instance_id'] == old_instance for r in restored.values())),
                         (True, True), operations=sorted(restored),
                         outcomes={key: restored[key]['outcome'] for key in sorted(restored)},
                         proposal_id=restored['h-repay-proposal'].get('proposal_id'))
            status, metrics = restarted.get('/api/metrics')
            journey.step('the new process executed no command at startup', 'HTTP',
                         (status, _command_total(metrics['counters']['commands'])), (200, 0))
            status, body = restarted.command('repay', advance, 'h-after-restart-cites-old-proposal',
                                             proposal_id='sim-t06-proposal', amount=10_000, sequence=3)
            journey.step('proposals are process memory: the old citation is unknown after restart', 'HTTP',
                         (status, body.get('error')), (404, 'UNKNOWN_PROPOSAL'))
            status, recon = restarted.get('/api/reconciliation')
            journey.step('reconciliation checks match after the restart', 'HTTP',
                         (status, sorted({check['status'] for check in recon['checks']})), (200, ['MATCHED']),
                         checks=len(recon['checks']))

            # Continue on the new instance.
            case = next(c for c in restarted.refresh()['cases'] if c['advance_id'] == advance)
            _drive(journey, restarted, 'repay the remainder on the new instance', 'repay', advance, 'h-repay-rest',
                   amount=case['outstanding_exposure'], sequence=3)
            _drive(journey, restarted, 'human close on the new instance', 'close', advance, 'h-close')
            final = restarted.refresh()
            journey.step('final phase', 'HTTP', {c['advance_id']: c['phase'] for c in final['cases']},
                         {advance: 'CLOSED'}, state_digest=final['state_digest'],
                         operation_count=final['operation_count'], funds_executed=final['funds_executed'])
            posted = posted + restarted.client.posted_operation_ids()
            _audit_no_replay(journey, posted)
        finally:
            server.kill()
    return journey.result()


# ----------------------------------------------------------------------- T04-sim

def _verify_report(argv):
    """Run ``python3 -m capital.verify`` and parse its one-line JSON report."""
    proc = subprocess.run(
        [sys.executable, '-m', 'capital.verify', *argv], cwd=os.fspath(ROOT),
        capture_output=True, text=True, timeout=LISTEN_TIMEOUT)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise JourneyError(f'capital.verify {argv}: {exc}: {proc.stdout!r} {proc.stderr!r}') from exc


def _demo_pin():
    """The seeded-demo state_digest the T04 book is checked against."""
    try:
        pin = json.loads((GOLDEN_DIR / 'demo.json').read_text(encoding='utf-8')).get('state_digest')
    except (OSError, json.JSONDecodeError) as exc:
        raise JourneyError(f'seeded-demo pin unreadable: {exc}') from exc
    if type(pin) is not str:
        raise JourneyError('seeded-demo pin has no state_digest')
    return pin


def run_t04():
    """The auditor path: seeded book, manifest export + offline verify, workspace audit, recon."""
    journey = Journey('T04-sim')
    with tempfile.TemporaryDirectory(prefix='capital-sim-t04-') as tmp:
        workspace = Path(tmp) / 'workspace'
        workspace.mkdir()
        server = ServerProcess(workspace)
        try:
            session = Session(server.start())
            client = session.client
            journey.step('organizer session on a --workspace server', 'PROCESS',
                         (session.state['workspace']['kind'], session.state['funds_executed']),
                         ('LOCAL_FILE_WORKSPACE', False), label=LABEL)
            for operation_id, op, advance, args, outcome, error in seed_demo.STEPS:
                response = session.command(op, advance, operation_id, **args)
                journey.step(f'seed {op} {advance}', 'HTTP', _outcome(response),
                             (200, outcome, error), op=op, advance_id=advance)
            state = session.refresh()
            journey.step('the seeded book matches the seeded-demo state_digest pin', 'HTTP',
                         state['state_digest'], _demo_pin(),
                         cases=len(state['cases']), operation_count=state['operation_count'])

            status, auditor = client.request('POST', '/api/session', {'role': 'auditor'}, session.token)
            journey.step('auditor role bound through the organizer session', 'HTTP',
                         (status, auditor.get('role'), auditor.get('identity'),
                          auditor.get('authentication'), auditor.get('agent_grant')),
                         (200, 'auditor', 'NOT_BOUND', 'NOT_BOUND', 'NOT_BOUND'),
                         mode=auditor.get('mode'), role_provenance=auditor.get('role_provenance'))
            auditor_token = auditor['local_token']
            auditor_get = lambda path: client.request('GET', path, token=auditor_token)

            status, refused = client.request('POST', '/api/overlay/commands', {
                'instance_id': session.instance_id, 'operation_id': 't04-auditor-tick',
                'op': 'advance_day', 'from_sim_day': 0, 'to_sim_day': T04_TICK_DAYS,
                'reason': 'SIM_JOURNEY'}, auditor_token)
            journey.step('the auditor token cannot advance the clock', 'HTTP',
                         (status, refused.get('error')), (403, 'ROLE_FORBIDDEN'))
            _tick(journey, session, 't04-tick-1', 0, T04_TICK_DAYS)

            status, overlay = auditor_get('/api/overlay')
            journey.step('auditor reads the overlay after the organizer tick', 'HTTP',
                         (status, overlay['sim_day'], overlay['status'], overlay['export']),
                         (200, T04_TICK_DAYS, 'BOUND', 'INCLUDED_IN_MANIFEST_V3'),
                         overlay_state_digest=overlay['overlay_state_digest'],
                         advances=len(overlay['advances']),
                         interest_payments=overlay['interest_payments']['status'])
            status, risk = auditor_get('/api/risk')
            journey.step('auditor reads the risk rollup', 'HTTP',
                         (status, risk['status'], risk['reconciliation']['matched']),
                         (200, 'BOUND', True), risk_digest=risk['risk_digest'],
                         outstanding_krw=risk['totals']['outstanding_krw'],
                         advances_open=risk['totals']['advances_open'])
            status, portfolio = auditor_get(
                f'/api/terms/portfolio?instance_id={session.instance_id}&as_of_day={T04_TICK_DAYS}')
            journey.step('auditor reads the terms portfolio rollup', 'HTTP',
                         (status, portfolio['status']), (200, 'BOUND'),
                         rows=len(portfolio['rows']), evaluated=portfolio['totals']['evaluated'],
                         interest_krw=portfolio['totals']['interest_krw'])
            status, recon = auditor_get('/api/reconciliation')
            journey.step('auditor reconciliation: every check MATCHED', 'HTTP',
                         (status, recon['status'], sorted({check['status'] for check in recon['checks']})),
                         (200, 'MATCHED', ['MATCHED']),
                         checks=[check['id'] for check in recon['checks']])

            status, manifest = auditor_get('/api/export/manifest')
            journey.step('auditor exports the V3 manifest', 'HTTP',
                         (status, manifest['format'], manifest['status'],
                          manifest['signature']['alg'], manifest['signature']['status']),
                         (200, 'KIX_CAPITAL_EXPORT_MANIFEST_V3', 'COMPLETE', 'UNSIGNED', 'NOT_BOUND'),
                         sections=sorted(manifest['sections']),
                         content_digest=manifest['content_digest'],
                         stage7_authenticated_export=manifest['stage7_authenticated_export'])
            manifest_path = Path(tmp) / 'manifest.json'
            manifest_path.write_bytes(
                json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
            code, report = _verify_report([os.fspath(manifest_path)])
            journey.step('capital.verify rechecks the exported manifest offline', 'VERIFY',
                         (code, report['ok'], report['format'], report['content_digest'],
                          report['signature'], report['stage7_authenticated_export']),
                         (0, True, 'KIX_CAPITAL_EXPORT_MANIFEST_V3', 'MATCHED', 'NOT_BOUND', False),
                         sections=report['sections'])
            code, report = _verify_report(['--workspace', os.fspath(workspace)])
            journey.step('capital.verify --workspace audits the live file read-only', 'VERIFY',
                         (code, report['ok'], report['mode'], report['recon_status'],
                          report['writes'], report['funds_executed'], report['lock_taken']),
                         (0, True, 'OFFLINE_WORKSPACE_AUDIT', 'MATCHED', False, False, False),
                         checks=report['checks'], entry_count=report['entry_count'],
                         receipt_count=report['receipt_count'], state_digest=report['state_digest'],
                         durable=report['durable'],
                         stage5_durable_transactions=report['stage5_durable_transactions'])

            status, denied = session.command('repay', 'sim-unbound', 't04-auditor-repay',
                                             token=auditor_token, amount=1, sequence=1)
            journey.step('the auditor token cannot submit a command', 'HTTP',
                         (status, denied.get('error')), (403, 'ROLE_FORBIDDEN'))
            status, observer = client.request('POST', '/api/session', {'role': 'observer'}, session.token)
            status, denied = client.request('GET', '/api/export/manifest', token=observer['local_token'])
            journey.step('the observer token cannot export the manifest', 'HTTP',
                         (status, denied.get('error')), (403, 'ROLE_FORBIDDEN'))

            state = session.refresh()
            overlay = session.overlay()
            status, risk = session.get('/api/risk')
            journey.step('final phases and digests', 'HTTP',
                         {c['advance_id']: c['phase'] for c in state['cases']},
                         {row[0]: row[1] for row in seed_demo.EXPECTED},
                         sim_day=overlay['sim_day'],
                         overlay_state_digest=overlay['overlay_state_digest'],
                         risk_digest=risk['risk_digest'], state_digest=state['state_digest'],
                         operation_count=state['operation_count'],
                         funds_executed=state['funds_executed'])
            _audit_no_replay(journey, client.posted_operation_ids())
        finally:
            server.kill()
    return journey.result()


RUNNERS = {'T03-sim': run_t03, 'T04-sim': run_t04, 'T05-sim': run_t05, 'T06-sim': run_t06}


# ------------------------------------------------------------------------ golden

def golden_path(directory, journey_id):
    return Path(directory) / GOLDEN_FILES[journey_id]


def check_or_update(body, path, update):
    """Return the differing paths. A missing golden is a failure unless updating."""
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(body), encoding='utf-8')
        return []
    if not path.is_file():
        raise JourneyError(f'golden missing: {path}. Pass --update-golden to write it.')
    try:
        expected = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JourneyError(f'golden unreadable: {path}') from exc
    _reject_volatile(expected)
    return diff_paths(expected, body)


def summary(results):
    return {
        'label': LABEL,
        'seed': SEED,
        'funds_executed': False,
        'integrated': False,
        'journeys': [{'id': r['journey'], 'label': r['label'], 'steps': r['step_count'],
                      'digest': r['digest'], 'funds_executed': r['funds_executed'],
                      'integrated': r['integrated']} for r in results],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journey', choices=JOURNEY_IDS, default=None, help='Run one journey. Default both.')
    parser.add_argument('--golden-dir', type=Path, default=GOLDEN_DIR, help='Default tests/golden')
    parser.add_argument('--update-golden', action='store_true', help='Rewrite the pins from this run')
    args = parser.parse_args(argv)
    results = []
    drifted = []
    for journey_id in ([args.journey] if args.journey else JOURNEY_IDS):
        try:
            body = RUNNERS[journey_id]()
            paths = check_or_update(body, golden_path(args.golden_dir, journey_id), args.update_golden)
        except JourneyError as exc:
            print(f'sim journeys failed: {exc}', file=sys.stderr)
            return 1
        except (OSError, http.client.HTTPException, KeyError, TypeError, ValueError, StopIteration) as exc:
            print(f'sim journeys failed: {journey_id}: {type(exc).__name__}: {exc}', file=sys.stderr)
            return 1
        results.append(body)
        drifted.extend(f'{journey_id}{path[1:]}' for path in paths)
    if drifted:
        print('golden drift: ' + ', '.join(drifted), file=sys.stderr)
        print('pass --update-golden to rewrite the pins', file=sys.stderr)
        return 1
    action = 'updated' if args.update_golden else 'ok'
    print('SIM_JOURNEYS ' + json.dumps(summary(results), sort_keys=True))
    print(f'sim journeys {action} SIMULATED ' + ' '.join(
        f'{r["journey"]} steps={r["step_count"]}' for r in results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
