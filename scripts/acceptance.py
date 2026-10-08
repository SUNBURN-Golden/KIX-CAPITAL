#!/usr/bin/env python3
"""One-command local acceptance ladder for the Capital simulation.

Stages: unit, pinned vendor, node --check, browser, packaged-artifact smoke,
and the seeded demo. Evidence is written to build/acceptance-evidence.json
(untracked). A failed or missing stage exits non-zero. This is a SIMULATED
ladder, not human product acceptance and not a payment, loan, or deployment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import __version__

FORMAT = 'KIX_CAPITAL_ACCEPTANCE_EVIDENCE_V1'
EVIDENCE = ROOT / 'build' / 'acceptance-evidence.json'
REQUIRED_STAGES = (
    'unit',
    'pinned-vendor',
    'node-check',
    'browser',
    'packaged-smoke',
    'seeded-demo',
)
_RAN = re.compile(r'^Ran (\d+) tests?(?: in .+)?$')
_PASSED = re.compile(r'^(\d+) passed(?: \(.+\))?$')
_FAILED_LINE = re.compile(r'^(\d+) failed$')
_UNIT_FAILED = re.compile(r'^FAILED \((.+)\)$')
_SMOKE = re.compile(r'^smoke ok: (.+)$')
_SEED = re.compile(r'^seed demo (ok|updated) ')
_COUNT_WORD = re.compile(r'(failures|errors|skipped)=(\d+)')


def build_plan(root=None):
    """The six required stages, in ladder order. Commands are relative to root."""
    py = sys.executable
    root = ROOT if root is None else Path(root)
    return [
        {
            'id': 'unit',
            'timeout': 300,
            'commands': [[py, '-m', 'unittest', 'discover', '-s', 'tests', '-v']],
        },
        {
            'id': 'pinned-vendor',
            'timeout': 60,
            'commands': [[
                py, '-m', 'unittest', 'discover',
                '-s', 'capital/vendor/credit_advance_f04',
                '-p', 'test_mock_credit.py', '-v',
            ]],
        },
        {
            'id': 'node-check',
            'timeout': 30,
            'commands': [['node', '--check', 'capital/static/app.js']],
        },
        {
            'id': 'browser',
            'timeout': 600,
            'commands': [['npm', 'run', 'test:browser']],
        },
        {
            'id': 'packaged-smoke',
            'kind': 'packaged-smoke',
            'timeout': 180,
            'commands': [[py, 'scripts/build_release.py', '--out', 'build/acceptance-dist']],
        },
        {
            'id': 'seeded-demo',
            'timeout': 60,
            'commands': [[py, 'scripts/seed_demo.py']],
        },
    ]


def inject_failure(plan, stage_id):
    """Replace one stage with a command that exits 1. Other stages stay."""
    found = False
    rewritten = []
    for stage in plan:
        stage = {
            'id': stage['id'],
            'timeout': stage.get('timeout', 60),
            'commands': [list(command) for command in stage.get('commands', [])],
            'kind': stage.get('kind'),
        }
        if stage['id'] == stage_id:
            found = True
            stage['kind'] = 'command'
            stage['commands'] = [[sys.executable, '-c', 'import sys; sys.exit(1)']]
            stage['injected'] = True
        rewritten.append(stage)
    if not found:
        raise KeyError(stage_id)
    return rewritten


def parse_test_count(text):
    """Pull ran/passed/failed from unittest, Playwright, or smoke output."""
    ran = passed = failed = None
    smoke_checks = None
    for raw in text.splitlines():
        line = raw.strip()
        match = _RAN.fullmatch(line)
        if match:
            # Unittest summary is authoritative. Earlier fixture lines must not remain.
            ran = int(match.group(1))
            passed = None
            failed = None
            continue
        match = _PASSED.fullmatch(line)
        if match:
            passed = int(match.group(1))
            continue
        match = _FAILED_LINE.fullmatch(line)
        if match:
            failed = int(match.group(1))
            continue
        match = _UNIT_FAILED.fullmatch(line)
        if match:
            counts = {name: int(value) for name, value in _COUNT_WORD.findall(match.group(1))}
            failed = counts.get('failures', 0) + counts.get('errors', 0)
            continue
        match = _SMOKE.fullmatch(line)
        if match:
            smoke_checks = [part.strip() for part in match.group(1).split(',') if part.strip()]
            continue
        if _SEED.match(line):
            ran = passed = 1
            failed = 0
    if smoke_checks is not None:
        return {'ran': len(smoke_checks), 'passed': len(smoke_checks), 'failed': 0}
    if ran is None and passed is None and failed is None:
        return None
    if ran is not None and passed is None:
        passed = ran - (failed or 0)
    if failed is None and (ran is not None or passed is not None):
        failed = 0
    if ran is None and passed is not None:
        ran = passed + (failed or 0)
    return {'ran': ran, 'passed': passed, 'failed': failed}


def _tail(text, limit=2000):
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_argv(argv, root, timeout):
    try:
        proc = subprocess.Popen(
            argv, cwd=os.fspath(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
    except FileNotFoundError as exc:
        return 127, '', f'command not found: {exc}'
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        _stop_group(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            _stop_group(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        return 124, out or '', (err or '') + '\nstage timed out'


def _stop_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def _command_record(argv, exit_code, out, err):
    combined = out + ('\n' if out and err else '') + err
    return {
        'argv': list(argv),
        'exit_code': exit_code,
        'test_count': parse_test_count(combined),
        'output_tail': _tail(combined),
    }


def _run_packaged(stage, root):
    timeout = stage.get('timeout', 180)
    build_argv = stage['commands'][0]
    code, out, err = run_argv(build_argv, root, timeout)
    records = [_command_record(build_argv, code, out, err)]
    if code != 0:
        return records, code
    printed = out.strip().splitlines()
    pyz = printed[-1].split()[0] if printed else ''
    if not pyz.endswith('.pyz'):
        records.append({
            'argv': [sys.executable, 'scripts/smoke_release.py'],
            'exit_code': 1,
            'test_count': None,
            'output_tail': 'build did not print a pyz path',
        })
        return records, 1
    smoke_argv = [sys.executable, 'scripts/smoke_release.py', pyz]
    scode, sout, serr = run_argv(smoke_argv, root, timeout)
    records.append(_command_record(smoke_argv, scode, sout, serr))
    return records, scode


def _run_stage(stage, root):
    if stage.get('kind') == 'packaged-smoke' and not stage.get('injected'):
        return _run_packaged(stage, root)
    records = []
    status = 0
    for argv in stage.get('commands', []):
        code, out, err = run_argv(argv, root, stage.get('timeout', 60))
        records.append(_command_record(argv, code, out, err))
        status = code
        if code != 0:
            break
    return records, status


def _merge_counts(records):
    ran = passed = failed = 0
    seen = False
    for record in records:
        count = record.get('test_count')
        if not count:
            continue
        seen = True
        ran += count.get('ran') or 0
        passed += count.get('passed') or 0
        failed += count.get('failed') or 0
    if not seen:
        return None
    return {'ran': ran, 'passed': passed, 'failed': failed}


def _tool_version(argv):
    code, out, err = run_argv(argv, ROOT, 20)
    if code == 0 and out.strip():
        return out.strip().splitlines()[-1].strip()
    return 'unrun'


def tool_versions(root):
    root = Path(root)
    playwright = 'unrun'
    installed = root / 'node_modules' / '@playwright' / 'test' / 'package.json'
    declared = root / 'package.json'
    if installed.is_file():
        try:
            playwright = json.loads(installed.read_text(encoding='utf-8'))['version']
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            playwright = 'unrun'
    elif declared.is_file():
        try:
            playwright = json.loads(declared.read_text(encoding='utf-8'))['devDependencies']['@playwright/test']
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            playwright = 'unrun'
    return {
        'python': sys.version.split()[0],
        'node': _tool_version(['node', '--version']),
        'npm': _tool_version(['npm', '--version']),
        'playwright': playwright,
        'capital': __version__,
    }


def head_sha(root):
    code, out, err = run_argv(['git', 'rev-parse', 'HEAD'], root, 20)
    if code == 0 and out.strip():
        return out.strip(), None
    detail = (err or out).strip() or f'git exit {code}'
    return None, detail


def vendor_hashes(root):
    root = Path(root)
    manifest_path = root / 'capital' / 'vendor' / 'manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {'commit': None, 'hashes': {}, 'verified': False, 'error': str(exc)}
    pinned = manifest.get('files')
    commit = manifest.get('commit')
    if type(pinned) is not dict or type(commit) is not str:
        return {'commit': None, 'hashes': {}, 'verified': False, 'error': 'manifest shape'}
    hashes = {}
    verified = True
    for rel, expected in pinned.items():
        path = root / 'capital' / 'vendor' / rel
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            actual = None
        hashes[rel] = actual
        if actual != expected:
            verified = False
    return {'commit': commit, 'hashes': hashes, 'verified': verified}


def golden_digests(root):
    path = Path(root) / 'tests' / 'golden' / 'demo.json'
    if not path.is_file():
        return {
            'status': 'unrun',
            'state_digest': None,
            'projection_totals': None,
            'content_digest': None,
        }
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            'status': 'unrun',
            'state_digest': None,
            'projection_totals': None,
            'content_digest': None,
        }
    return {
        'status': 'recorded',
        'state_digest': data.get('state_digest'),
        'projection_totals': data.get('projection_totals'),
        'content_digest': data.get('content_digest'),
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + '\n'
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def execute_plan(plan, *, root, evidence_path, required=REQUIRED_STAGES):
    """Run plan, write evidence, and return 0 only when every required stage passed."""
    root = Path(root)
    evidence_path = Path(evidence_path)
    sha, sha_error = head_sha(root)
    vendor = vendor_hashes(root)
    golden = golden_digests(root)
    stages = []
    by_id = {}
    for stage in plan:
        records, code = _run_stage(stage, root)
        status = 'passed' if code == 0 else 'failed'
        body = {
            'id': stage['id'],
            'status': status,
            'injected': bool(stage.get('injected')),
            'exit_code': code,
            'test_count': _merge_counts(records),
            'commands': records,
        }
        stages.append(body)
        by_id[stage['id']] = body
        count = body['test_count'] or {}
        print(
            f"[acceptance] {stage['id']} exit={code} status={status} "
            f"passed={count.get('passed')} failed={count.get('failed')}",
            flush=True,
        )
    for stage_id in required:
        if stage_id in by_id:
            continue
        missing = {
            'id': stage_id,
            'status': 'unrun',
            'injected': False,
            'exit_code': None,
            'test_count': None,
            'commands': [],
        }
        stages.append(missing)
        by_id[stage_id] = missing
        print(f'[acceptance] {stage_id} exit=None status=unrun passed=None failed=None', flush=True)
    required_ok = all(by_id[stage_id]['status'] == 'passed' for stage_id in required)
    extra_failed = any(stage['status'] == 'failed' for stage in stages)
    ok = bool(required_ok and not extra_failed and vendor.get('verified') and sha and golden.get('status') == 'recorded')
    evidence = {
        'format': FORMAT,
        'label': 'SIMULATED',
        'funds_executed': False,
        'note': (
            'Local simulation ladder. Not human product acceptance. '
            'Not a payment, loan, KYC decision, or deployment.'
        ),
        'head_sha': sha,
        'head_error': sha_error,
        'tool_versions': tool_versions(root),
        'vendor_hashes': vendor,
        'golden_digests': golden,
        'stages': stages,
        'ok': ok,
    }
    _write_json(evidence_path, evidence)
    print(f'[acceptance] evidence {evidence_path} ok={str(ok).lower()}', flush=True)
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--inject-fail', default=None, help='Replace one stage with a command that exits 1')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    plan = build_plan(args.root)
    if args.inject_fail:
        try:
            plan = inject_failure(plan, args.inject_fail)
        except KeyError:
            print(f'unknown stage {args.inject_fail}', file=sys.stderr)
            return 2
    try:
        return execute_plan(plan, root=args.root, evidence_path=args.evidence)
    except OSError as exc:
        print(f'acceptance failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
