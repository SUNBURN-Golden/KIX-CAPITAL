#!/usr/bin/env python3
"""Run a scripted local journey against a Capital zipapp.

The journey uses synthetic sim- ids and the same amounts as the checkout
lifecycle test. Results are a local simulation, not a payment or a loan.
"""
from __future__ import annotations

import argparse
import ast
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
    for _ in range(25):
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
    status, raw = _request(port, method, path, body, token)
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssertionError(f'{method} {path} status {status} not json: {raw[:200]!r}') from exc
    if status != 200:
        raise AssertionError(f'{method} {path} status {status}: {parsed}')
    return parsed


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

            for operation_id, op, args in STEPS:
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
