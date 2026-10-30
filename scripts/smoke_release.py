#!/usr/bin/env python3
"""Run a scripted local journey against a Capital zipapp.

The journey uses synthetic sim- ids and the same amounts as the checkout
lifecycle test. Results are a local simulation, not a payment or a loan.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import http.client
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from fractions import Fraction

# Two repayments match tests/test_capital.py so the following close is ACCEPTED.
ADVANCE = 'sim-journey'
STEPS = (
    ('sim-offer', 'offer', {'fixture_id': 'sim-committed', 'amount': 60000}),
    ('sim-approve', 'approve', {}),
    ('sim-bind', 'bind_settlement', {}),
    ('sim-draw', 'draw', {}),
    ('sim-repay-1', 'repay', {'amount': 20000, 'sequence': 1}),
    ('sim-repay-2', 'repay', {'amount': 40000, 'sequence': 2}),
    ('sim-close', 'close', {}),
)
_PORT = re.compile(r'^KIX Capital simulation: http://127\.0\.0\.1:(\d+)\s*$')


def checkout_version() -> str:
    path = Path(__file__).resolve().parent.parent / 'capital' / '__init__.py'
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if '__version__' in names and isinstance(node.value, ast.Constant):
            value = node.value.value
            if isinstance(value, str):
                return value
    raise AssertionError(f'no __version__ in {path}')


class _Server:
    def __init__(self, proc, port, lines, stderr_parts, threads):
        self.proc = proc
        self.port = port
        self.lines = lines
        self.stderr_parts = stderr_parts
        self.threads = threads
        self._stopped = False

    def stderr(self) -> str:
        return ''.join(self.stderr_parts)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        proc = self.proc
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        for thread in self.threads:
            thread.join(timeout=5)


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    return env


def _drain(stream, sink) -> None:
    try:
        for line in stream:
            sink.append(line)
    finally:
        stream.close()


def _start(pyz: Path, workdir: Path, cwd: Path, env: dict[str, str]) -> _Server:
    proc = subprocess.Popen(
        [sys.executable, '-B', os.fspath(pyz), '--port', '0', '--workspace', os.fspath(workdir)],
        cwd=os.fspath(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    stderr_parts: list[str] = []
    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, lines), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, stderr_parts), daemon=True),
    ]
    for thread in threads:
        thread.start()
    server = _Server(proc, 0, lines, stderr_parts, threads)
    deadline = time.monotonic() + 20
    while not lines and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    if not lines:
        detail = ''.join(stderr_parts).strip()
        server.stop()
        raise AssertionError(f'server did not listen (exit={proc.poll()}): {detail}')
    match = _PORT.match(lines[0])
    if match is None:
        server.stop()
        raise AssertionError(f'unexpected listen line: {lines[0]!r}')
    server.port = int(match.group(1))
    return server


def _request(port: int, method: str, path: str, body=None, token=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {}
    if data is not None:
        headers['Content-Type'] = 'application/json'
        if token is not None:
            headers['X-Capital-Token'] = token
    last = None
    for _ in range(1 if method == 'POST' else 25):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, raw
        except (http.client.HTTPException, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
        finally:
            conn.close()
    raise AssertionError(f'{method} {path} failed: {last}')


def _json(port: int, method: str, path: str, body=None, token=None) -> dict:
    try:
        status, raw = _request(port, method, path, body, token)
    except AssertionError:
        if method != 'POST' or not body or 'operation_id' not in body:
            raise
        # A mutation is sent once. Resolve an ambiguous transport via its receipt.
        if path == '/api/overlay/commands':
            return _json(port, 'GET', f"/api/overlay?operation_id={body['operation_id']}")['operation']
        return _json(port, 'GET', f"/api/operations/{body['operation_id']}?instance_id={body['instance_id']}")
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssertionError(f'{method} {path} status {status} not json: {raw[:200]!r}') from exc
    if status != 200:
        raise AssertionError(f'{method} {path} status {status}: {parsed}')
    return parsed



def _bundled_surfaces(pyz, port, instance, state=None):
    with zipfile.ZipFile(pyz) as archive:
        manifest = json.loads(archive.read('RELEASE-MANIFEST.json'))
        for name, digest in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise AssertionError(f'release manifest hash mismatch: {name}')
    terms_note = 'docs/decisions/CAPITAL_FINANCIAL_TERMS.md'
    policy_note = 'docs/decisions/CAPITAL_SETTLEMENT_POLICY.md'

    def check(body, note):
        if (body.get('notes_source') != 'BUNDLED_IN_ARTIFACT'
                or body.get('note_sha256') != manifest['files'][note]):
            raise AssertionError(f'bundled provenance {note}: {body}')
        return body

    terms = check(_json(port, 'GET', '/api/terms'), terms_note)
    if terms['status'] not in ('BOUND', 'PARTIAL'):
        raise AssertionError(f'terms unbound: {terms}')
    policy = check(_json(port, 'GET', '/api/policy'), policy_note)
    if policy['outcome'] != 'DECIDED':
        raise AssertionError(f'policy undecided: {policy}')
    check(_json(port, 'GET', '/api/policy/simulation'), policy_note)
    decisions = check(_json(port, 'GET', '/api/decisions'), terms_note)
    if decisions['status'] != 'BOUND' or not decisions['rows']:
        raise AssertionError(f'decisions unbound: {decisions}')
    for row in decisions['rows']:
        check(row, row['note'])
    check((state or _json(port, 'GET', '/api/state'))['terms'], terms_note)
    underwriting = check(_json(port, 'GET',
        f'/api/underwrite/sim-committed?instance_id={instance}&amount=60000'), terms_note)
    if underwriting['status'] != 'BOUND' or not underwriting['checks']:
        raise AssertionError(f'underwriting unbound: {underwriting}')
    return terms


def _accrual_restart(pyz, server, servers, workdir, cwd, env, instance, token, checks):
    with zipfile.ZipFile(pyz) as archive:
        namespace = {'__name__': 'smoke_ledger', '__file__': 'scripts/decision_ledger.py'}
        exec(compile(archive.read('scripts/decision_ledger.py'), namespace['__file__'], 'exec'), namespace)
        block, = namespace['extract_blocks'](archive.read(
            'docs/decisions/CAPITAL_FINANCIAL_TERMS.md').decode('utf-8'))
    rate = block['entries']['interest_rate']['value']
    state = _json(server.port, 'GET', '/api/state')
    case = next(c for c in state['cases'] if c['advance_id'] == ADVANCE)
    tier = next(t for t in rate['tiers'] if t['condition']['settlement_gate'] == case['settlement_gate']
                and t['condition'].get('refund_face', 0) == 0)
    day_count = int(re.fullmatch(r'ACT_(\d+)_FIXED', rate['day_count']).group(1))
    day = 3  # synthetic rehearsal interval, not a financial term
    receipt = _json(server.port, 'POST', '/api/overlay/commands', {
        'instance_id': instance, 'operation_id': 'sim-clock', 'op': 'advance_day',
        'from_sim_day': 0, 'to_sim_day': day, 'reason': 'SIMULATED packaged rehearsal'}, token)
    if receipt['outcome'] != 'APPLIED':
        raise AssertionError(f'advance_day failed: {receipt}')
    before = _json(server.port, 'GET', '/api/overlay?operation_id=sim-clock')
    row, = before['advances']
    exact = Fraction(60000 * day * tier['all_in_bps_annual'], 10000 * day_count)
    posted = exact.numerator // exact.denominator
    remainder = exact - posted
    if (posted <= 0 or row['interest_due_krw'] != posted
            or row['carried_remainder_contract'] != f'{remainder.numerator}/{remainder.denominator}'
            or before['sim_day'] != day or before['status'] != 'BOUND'):
        raise AssertionError(f'accrual does not match bundled note: {before}')
    query = f'?instance_id={instance}&draw_day=0&as_of_day={day}'
    detail = _json(server.port, 'GET', f'/api/terms/{ADVANCE}' + query)
    allocation = _json(server.port, 'GET', f'/api/terms/{ADVANCE}/allocation' + query + '&cash=60000')
    terms = _json(server.port, 'GET', '/api/terms')
    for body in (detail, allocation):
        if (body['notes_source'], body['note_sha256']) != (terms['notes_source'], terms['note_sha256']):
            raise AssertionError(f'case provenance differs: {body}')
    checks.append('bundled-accrual')
    server.stop()
    restarted = _start(pyz, workdir, cwd, env)
    servers.append(restarted)
    state = _json(restarted.port, 'GET', '/api/state')
    after = _json(restarted.port, 'GET', '/api/overlay')
    for key in ('sim_day', 'terms_binding', 'terms_binding_matches', 'overlay_state_digest',
                'entry_count', 'advances', 'status', 'capacity'):
        if before[key] != after[key]:
            raise AssertionError(f'overlay changed after restart: {key}')
    if state['instance_id'] == instance:
        raise AssertionError('accrual restart reused instance_id')
    restored = _json(restarted.port, 'GET', '/api/overlay?operation_id=sim-clock')['operation']
    if restored != before['operation']:
        raise AssertionError(f'clock receipt changed: {restored}')
    restored_terms = _bundled_surfaces(pyz, restarted.port, state['instance_id'], state)
    for key in ('status', 'terms_version', 'notes_source', 'note_sha256'):
        if restored_terms[key] != terms[key]:
            raise AssertionError(f'policy provenance changed: {key}')
    checks.append('restart-overlay-provenance')
    return restarted, state['instance_id'], state['local_token']

def smoke(pyz, workdir) -> list[str]:
    pyz = Path(pyz).resolve()
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    version = checkout_version()
    checks: list[str] = []
    env = _child_env()
    servers: list[_Server] = []
    with tempfile.TemporaryDirectory(prefix='kix-smoke-cwd-') as cwd_name:
        cwd = Path(cwd_name)
        try:
            version_proc = subprocess.run(
                [sys.executable, '-B', os.fspath(pyz), '--version'],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            expected = f'kix-capital {version}'
            if version_proc.returncode != 0 or version_proc.stdout.strip() != expected:
                raise AssertionError(
                    f'--version {version_proc.returncode} stdout={version_proc.stdout!r} '
                    f'stderr={version_proc.stderr!r} expected {expected!r}')
            checks.append('version-flag')

            server = _start(pyz, workdir, cwd, env)
            servers.append(server)
            state = _json(server.port, 'GET', '/api/state')
            if state.get('version') != version:
                raise AssertionError(f"/api/state version {state.get('version')!r} != {version!r}")
            checks.append('state-version')
            instance = state['instance_id']
            token = state['local_token']

            status, index = _request(server.port, 'GET', '/')
            with zipfile.ZipFile(pyz) as archive:
                packaged = archive.read('capital/static/index.html')
            if status != 200 or index != packaged:
                raise AssertionError(f'static index mismatch status={status} bytes={len(index)}')
            checks.append('static-index')
            _bundled_surfaces(pyz, server.port, instance, state)
            checks.append('bundled-policy-provenance')

            for step_index, (operation_id, op, args) in enumerate(STEPS):
                if step_index == 4:
                    server, instance, token = _accrual_restart(
                        pyz, server, servers, workdir, cwd, env, instance, token, checks)

                receipt = _json(server.port, 'POST', '/api/commands', {
                    'instance_id': instance,
                    'operation_id': operation_id,
                    'op': op,
                    'advance_id': ADVANCE,
                    'args': args,
                }, token)
                if receipt.get('outcome') != 'ACCEPTED':
                    raise AssertionError(f'{op} receipt {receipt}')
            checks.append('journey-accepted')

            ready = _json(server.port, 'GET', '/api/readiness')
            if ready.get('source_integrity', {}).get('all_matched') is not True:
                raise AssertionError(f"source_integrity {ready.get('source_integrity')}")
            checks.append('source-integrity')

            server.stop()
            restarted = _start(pyz, workdir, cwd, env)
            servers.append(restarted)
            restored = _json(restarted.port, 'GET', '/api/state')
            if restored.get('instance_id') == instance:
                raise AssertionError('restart reused instance_id')
            if restored.get('version') != version:
                raise AssertionError(f"restored version {restored.get('version')!r}")
            checks.append('restart-instance')
            new_instance = restored['instance_id']
            for operation_id, _, _ in STEPS:
                found = _json(
                    restarted.port, 'GET',
                    f'/api/operations/{operation_id}?instance_id={new_instance}')
                if found.get('outcome') != 'ACCEPTED' or found.get('operation_id') != operation_id:
                    raise AssertionError(f'restored receipt {operation_id}: {found}')
            checks.append('restart-receipts')
            closed = [case for case in restored.get('cases', []) if case.get('advance_id') == ADVANCE]
            if len(closed) != 1 or closed[0].get('phase') != 'CLOSED':
                raise AssertionError(f'closed case missing: {restored.get("cases")}')
            checks.append('restart-closed')
        finally:
            for running in servers:
                running.stop()
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pyz', help='Path to capital-<version>.pyz')
    args = parser.parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix='kix-capital-smoke-') as work:
            checks = smoke(args.pyz, work)
    except AssertionError as exc:
        print(f'smoke failed: {exc}', file=sys.stderr)
        return 1
    print('smoke ok: ' + ', '.join(checks))
    return 0


if __name__ == '__main__':
    sys.exit(main())
