#!/usr/bin/env python3
"""Pinned fault-injection corpus for ``GateHttpProducer`` over the local fake gate.

Reads ``tests/vectors/gate_faults.json`` (format ``KIX_CAPITAL_GATE_FAULTS_V1``),
replays every case against ``scripts/fake_gate.py`` bound to ``127.0.0.1`` behind
a real ``make_server`` facade, and compares each normalized observation with the
pinned ``expect`` block. ``--check`` exits 0 only when every case matches; any
drift, malformed corpus, or setup failure exits 1. Nothing is rewritten.

The corpus is SIMULATED. The label is ``LOCAL_FAKE_GATE``, the binding stays
``NOT_BOUND``, ``semantic_conformance`` and ``funds_executed`` stay false, and a
lost or dropped response is ``UNKNOWN`` with ``retry_authorized=false`` — the
facade never resends a command. This is not SEMANTIC_CONFORMANCE. CAP-16 stays
NOT_BOUND.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.gate_producer import GateHttpProducer, load_fake_gate
from capital.producer import CreditError
from capital.server import make_server

FORMAT = 'KIX_CAPITAL_GATE_FAULTS_V1'
LABEL = 'LOCAL_FAKE_GATE'
DEFAULT_CORPUS = ROOT / 'tests' / 'vectors' / 'gate_faults.json'
OBSERVED_KEYS = (
    'http', 'outcome', 'error', 'retry_authorized', 'transport_duplicate',
    'post_count', 'lookup', 'upstream_receipt', 'phase')
POSTS = frozenset({'facade', 'gate'})
CASE_KEYS = frozenset({'id', 'journal_length', 'producer_timeout', 'fault_delay', 'steps'})
STEP_KEYS = frozenset({'post', 'operation_id', 'op', 'advance_id', 'args', 'fault', 'expect'})
_ID = re.compile(r'[A-Za-z0-9-]{1,80}\Z')


class CorpusError(Exception):
    """The corpus file is missing, malformed, or names an unknown hook."""


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def load_corpus(path=DEFAULT_CORPUS):
    """Read and shape-check the pinned corpus. Never writes it."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise CorpusError(f'corpus unreadable: {exc}')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_strict_object)
    except (ValueError, UnicodeError) as exc:
        raise CorpusError(f'corpus malformed: {exc}')
    if type(doc) is not dict or doc.get('format') != FORMAT:
        raise CorpusError('corpus format is not KIX_CAPITAL_GATE_FAULTS_V1')
    if doc.get('label') != LABEL or doc.get('mode') != 'SIMULATED':
        raise CorpusError('corpus labels changed')
    if doc.get('binding') != 'NOT_BOUND' or doc.get('semantic_conformance') is not False \
            or doc.get('funds_executed') is not False:
        raise CorpusError('corpus binding/funds flags changed')
    cases = doc.get('cases')
    if type(cases) is not list or not cases:
        raise CorpusError('corpus has no cases')
    fake_gate = load_fake_gate()
    seen = set()
    for index, case in enumerate(cases):
        where = f'cases[{index}]'
        if type(case) is not dict or not CASE_KEYS >= set(case) or not {'id', 'steps'} <= set(case):
            raise CorpusError(f'{where} has unknown or missing fields')
        if type(case['id']) is not str or case['id'] in seen:
            raise CorpusError(f'{where} id missing or duplicated')
        seen.add(case['id'])
        where = f'{case["id"]}'
        for number, key in enumerate(('producer_timeout', 'fault_delay')):
            if key in case and not (type(case[key]) in (int, float) and case[key] > 0):
                raise CorpusError(f'{where} {key} must be a positive number')
        if type(case.get('journal_length')) is not int:
            raise CorpusError(f'{where} journal_length must be an integer')
        steps = case['steps']
        if type(steps) is not list or not steps:
            raise CorpusError(f'{where} has no steps')
        for offset, step in enumerate(steps):
            here = f'{where}.steps[{offset}]'
            if type(step) is not dict or set(step) != STEP_KEYS:
                raise CorpusError(f'{here} fields must be exactly {sorted(STEP_KEYS)}')
            if step['post'] not in POSTS:
                raise CorpusError(f'{here} post must be facade or gate')
            if type(step['operation_id']) is not str or _ID.fullmatch(step['operation_id']) is None:
                raise CorpusError(f'{here} operation_id invalid')
            if type(step['op']) is not str or step['op'] not in fake_gate.COMMANDS:
                raise CorpusError(f'{here} op invalid')
            if type(step['advance_id']) is not str or not step['advance_id'].startswith('sim-'):
                raise CorpusError(f'{here} advance_id must be a synthetic sim- id')
            if type(step['args']) is not dict:
                raise CorpusError(f'{here} args must be an object')
            if step['fault'] is not None and step['fault'] not in fake_gate.FAULTS:
                raise CorpusError(f'{here} fault {step["fault"]!r} is not a fake-gate hook')
            expect = step['expect']
            if type(expect) is not dict or not expect or not set(expect) <= set(OBSERVED_KEYS):
                raise CorpusError(f'{here} expect must name only {sorted(OBSERVED_KEYS)}')
    return doc


def _http(method, url, payload=None, token=None, timeout=5.0):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('ascii')
        headers['Content-Type'] = 'application/json'
    if token is not None:
        headers['X-Capital-Token'] = token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    try:
        return status, json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError):
        return status, None


def _facade_command(instance_id, step):
    return {'instance_id': instance_id, 'operation_id': step['operation_id'],
            'op': step['op'], 'advance_id': step['advance_id'], 'args': step['args']}


def _gate_envelope(step):
    operation_id = step['operation_id']
    return {'operationId': operation_id, 'actor': 'SIMULATED', 'action': step['op'],
            'body': {'operation_id': operation_id, 'advance_id': step['advance_id'],
                     'args': step['args'], 'bound_settlement_id': None}}


def _labeled(body, findings, where):
    """UNKNOWN envelopes and gate receipts keep the LOCAL_FAKE_GATE label."""
    if type(body) is not dict:
        return
    if body.get('outcome') == 'UNKNOWN' and body.get('label') != LABEL:
        findings.append(f'{where}: UNKNOWN response label is {body.get("label")!r}')
    if 'operationId' in body and body.get('label') != LABEL:
        findings.append(f'{where}: gate receipt label is {body.get("label")!r}')


def _observe_lookup(base, token, instance_id, operation_id):
    status, body = _http(
        'GET', f'{base}/api/operations/{operation_id}?instance_id={instance_id}', token=token)
    if status != 200 or type(body) is not dict:
        return f'HTTP_{status}'
    if body.get('outcome') == 'UNKNOWN' and body.get('label') != LABEL:
        return 'UNLABELED_UNKNOWN'
    return body.get('outcome')


def _observe_upstream(producer, operation_id):
    try:
        receipt = producer.lookup(operation_id)
    except Exception as exc:
        return 'ERROR:' + getattr(exc, 'code', type(exc).__name__)
    return None if receipt is None else receipt.get('outcome')


def _observe_phase(producer, advance_id):
    try:
        view = producer.view(advance_id)
    except CreditError as exc:
        return 'ERROR:' + exc.code
    except Exception as exc:
        return 'ERROR:' + getattr(exc, 'code', type(exc).__name__)
    return view.get('phase')


def _diff(expect, observed, where, findings):
    for key, wanted in expect.items():
        if observed[key] != wanted:
            findings.append(f'{where}.{key}: pinned {wanted!r}, observed {observed[key]!r}')


def run_case(case, fake_gate, findings):
    """One independent case: fresh gate, fresh facade, all loopback."""
    gate = fake_gate.start(
        '127.0.0.1', 0, fault_delay=float(case.get('fault_delay', 1.5)))
    producer = GateHttpProducer(gate=gate, timeout=float(case.get('producer_timeout', 5.0)))
    server = make_server(0, producer=producer)
    thread = threading.Thread(target=server.serve_forever, name='gate-faults-facade', daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    steps = []
    try:
        status, state = _http('GET', base + '/api/state')
        if status != 200 or type(state) is not dict:
            findings.append(f'{case["id"]}: /api/state answered {status}')
            return {'steps': steps, 'journal_length': None}
        token, instance_id = state['local_token'], state['instance_id']
        for offset, step in enumerate(case['steps']):
            where = f'{case["id"]}.steps[{offset}]'
            operation_id = step['operation_id']
            if step['fault'] is not None:
                gate.arm(operation_id, step['fault'])
            if step['post'] == 'gate':
                status, body = _http('POST', gate.url + '/v1/commands', _gate_envelope(step))
            else:
                status, body = _http(
                    'POST', base + '/api/commands', _facade_command(instance_id, step), token=token)
            _labeled(body, findings, where)
            try:
                post_count = producer.post_count(operation_id)
            except Exception as exc:
                post_count = 'ERROR:' + getattr(exc, 'code', type(exc).__name__)
            observed = {
                'http': status,
                'outcome': body.get('outcome') if type(body) is dict else None,
                'error': body.get('error') if type(body) is dict else None,
                'retry_authorized': body.get('retry_authorized') if type(body) is dict else None,
                'transport_duplicate': body.get('transport_duplicate') if type(body) is dict else None,
                'post_count': post_count,
                'lookup': _observe_lookup(base, token, instance_id, operation_id),
                'upstream_receipt': _observe_upstream(producer, operation_id),
                'phase': _observe_phase(producer, step['advance_id']),
            }
            _diff(step['expect'], observed, where, findings)
            steps.append(observed)
        journal_length = len(producer.export_journal())
        if journal_length != case['journal_length']:
            findings.append(
                f'{case["id"]}.journal_length: pinned {case["journal_length"]}, observed {journal_length}')
        return {'steps': steps, 'journal_length': journal_length}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        producer.close()
        gate.close()


def run_corpus(path=DEFAULT_CORPUS):
    """Replay every case. Returns a normalized report; never rewrites the file."""
    findings = []
    doc = load_corpus(path)
    fake_gate = load_fake_gate()
    report = {'format': FORMAT, 'label': LABEL, 'mode': 'SIMULATED',
              'binding': 'NOT_BOUND', 'cases': {}, 'findings': findings}
    for case in doc['cases']:
        try:
            report['cases'][case['id']] = run_case(case, fake_gate, findings)
        except Exception as exc:
            findings.append(f'{case["id"]}: run failed with {type(exc).__name__}: {exc}')
            report['cases'][case['id']] = {'steps': [], 'journal_length': None}
    report['ok'] = not findings
    return report


def check(path=DEFAULT_CORPUS, out=None):
    """``--check`` body. Returns 0 on a match, 1 on any drift or corpus error."""
    out = sys.stdout if out is None else out
    try:
        report = run_corpus(path)
    except CorpusError as exc:
        print(f'gate_faults: {exc}', file=out)
        return 1
    for finding in report['findings']:
        print(f'gate_faults: DRIFT {finding}', file=out)
    if report['ok']:
        print(f'gate_faults: {len(report["cases"])} cases match the pinned corpus '
              f'({LABEL} SIMULATED NOT_BOUND)', file=out)
        return 0
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Re-run the pinned corpus on 127.0.0.1; nonzero on drift. Rewrites nothing.')
    parser.add_argument('--corpus', default=DEFAULT_CORPUS,
                        help='Corpus path. Default tests/vectors/gate_faults.json.')
    args = parser.parse_args(argv)
    if not args.check:
        parser.error('only --check is supported; this script never rewrites the corpus')
    return check(args.corpus)


if __name__ == '__main__':
    sys.exit(main())
