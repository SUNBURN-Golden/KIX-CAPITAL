#!/usr/bin/env python3
"""Deterministic crash-boundary replay matrix for the LOCAL_FILE_WORKSPACE.

`SCRIPT` is a fixed command sequence: F04 journal-appends (offer, approve,
bind_settlement, draw, repay) and overlay-entry saves (advance_day). Every
workspace write boundary is crashed before and after the write:

- `save-boundary` cells arm a save-counted `CrashInjectingStorage` so the
  boundary raises `WORKSPACE_WRITE_FAILED` before or after the inner write.
- `rename` cells reuse the `tests/storage_conformance.py` os-level injector:
  `replace` fails inside `FileWorkspace._atomic_write` before the rename and
  `dir-fsync` fails after the rename committed the new complete file.
- `torn` cells write a truncated, payload-flipped or overlay-section-flipped
  workspace.json and must fail closed `WORKSPACE_UNREADABLE`: never a silent
  empty book, never a rewrite.
- `stale-temp` leaves a `.workspace.json.*.tmp` file that open must remove and
  never serve.
- `sigkill` drives the same script over the loopback HTTP API of a real
  `python3 -m capital.server --workspace` subprocess (the T06-sim harness from
  scripts/sim_journeys.py), drops one overlay write mid-flight, SIGKILLs, and
  restarts on the same directory. A mid-flight kill is legitimately bivalent,
  so the pin names the two complete digests it may restore, never a torn one.

After every injection the restart opens the directory fresh and compares the
restored `state_digest` and `overlay_state_digest` against the pinned cell, or
fails closed. Outcomes are pinned in `tests/vectors/workspace_crash.json`;
`--write` regenerates it and `--check` exits 1 on any drift. The table is
derived from digests only (no instance id, token, port or timestamp), so both
modes are byte-stable.

This is a local development-workspace gate. It is not SEMANTIC_CONFORMANCE,
not stage5 durable transaction recovery, not inbox/outbox, and makes no
cross-host fencing claim. CAP-11 stays NOT_BOUND; label SIMULATED; the amounts
and ids here are synthetic fixture units.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import signal
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import audit, overlay, store
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, StoragePort, WorkspaceError

FORMAT = 'KIX_CAPITAL_WORKSPACE_CRASH_V1'
LABEL = 'SIMULATED'
VECTOR = Path(__file__).resolve().parent / 'vectors' / 'workspace_crash.json'
ADVANCE = 'sim-cr-a'
STALE_TEMP = '.workspace.json.stale.tmp'

# The fixed replay. Every step is exactly one storage.save: F04 commands go
# through service.execute -> _persist, advance_day through overlay_command ->
# _persist (one atomic save, the F04 journal never written by the overlay).
# `boundary` names the workspace write boundary the save exercises.
SCRIPT = (
    {'step': 1, 'boundary': 'journal-append', 'op': 'offer', 'operation_id': 'cr-offer',
     'advance_id': ADVANCE, 'args': {'fixture_id': 'sim-committed', 'amount': 40000}},
    {'step': 2, 'boundary': 'journal-append', 'op': 'approve', 'operation_id': 'cr-approve',
     'advance_id': ADVANCE, 'args': {}},
    {'step': 3, 'boundary': 'journal-append', 'op': 'bind_settlement', 'operation_id': 'cr-bind',
     'advance_id': ADVANCE, 'args': {}},
    {'step': 4, 'boundary': 'journal-append', 'op': 'draw', 'operation_id': 'cr-draw',
     'advance_id': ADVANCE, 'args': {}},
    {'step': 5, 'boundary': 'overlay-entry', 'op': 'advance_day', 'operation_id': 'cr-tick-1',
     'from_sim_day': 0, 'to_sim_day': 3, 'reason': 'CRASH_MATRIX'},
    {'step': 6, 'boundary': 'journal-append', 'op': 'repay', 'operation_id': 'cr-repay',
     'advance_id': ADVANCE, 'args': {'amount': 10000, 'sequence': 1}},
    {'step': 7, 'boundary': 'overlay-entry', 'op': 'advance_day', 'operation_id': 'cr-tick-2',
     'from_sim_day': 3, 'to_sim_day': 4, 'reason': 'CRASH_MATRIX'},
)
SCRIPT_STEPS = {step['step']: step for step in SCRIPT}
SIGKILL_STEP = 5  # the fire-and-forget overlay write killed mid-flight

_TORN_FAILED_CHECK = {
    'truncate-half': 'strict_json',
    'payload-byte': 'payload_sha256',
    'overlay-digest-byte': 'service_restore',
}


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _conformance():
    """The os-level crash injector shared with the storage-conformance suite."""
    return _load_module('storage_conformance', Path(__file__).resolve().with_name('storage_conformance.py'))


def _sim_journeys():
    """The T06-sim subprocess restart harness."""
    return _load_module('sim_journeys', ROOT / 'scripts' / 'sim_journeys.py')


class CrashInjectingStorage(StoragePort):
    """Save-counted fault injection around one FileWorkspace.

    `arm(save_index)` returns 'before', 'after' or None for the save now
    running. 'before' raises before the inner write (the durable file keeps
    the previous complete envelope); 'after' lets the inner write commit then
    reports failure (the durable file already holds the new complete
    envelope). Both raise the same WorkspaceError the file adapter raises.
    """

    durable_label = 'LOCAL_FILE_WORKSPACE'

    def __init__(self, inner, arm):
        self.inner = inner
        self.arm = arm
        self.saves = 0

    @property
    def directory(self):
        return self.inner.directory

    @property
    def path(self):
        return self.inner.path

    @property
    def writer_instance(self):
        return self.inner.writer_instance

    @writer_instance.setter
    def writer_instance(self, value):
        self.inner.writer_instance = value

    def load(self):
        return self.inner.load()

    def save(self, document, overlay=None):
        self.saves += 1
        mode = self.arm(self.saves)
        if mode == 'before':
            raise WorkspaceError('WORKSPACE_WRITE_FAILED')
        self.inner.save(document, overlay)
        if mode == 'after':
            raise WorkspaceError('WORKSPACE_WRITE_FAILED')

    def close(self):
        self.inner.close()


# ------------------------------------------------------------------ runners

def _apply(service, step):
    """One scripted step. Journal ops go through execute, ticks through overlay_command."""
    if step['boundary'] == 'overlay-entry':
        return service.overlay_command({
            'instance_id': service.instance_id, 'operation_id': step['operation_id'],
            'op': 'advance_day', 'from_sim_day': step['from_sim_day'],
            'to_sim_day': step['to_sim_day'], 'reason': step['reason']})
    return service.execute({
        'instance_id': service.instance_id, 'operation_id': step['operation_id'],
        'op': step['op'], 'advance_id': step['advance_id'], 'args': dict(step['args'])})


def _capture(service):
    """The digest-only fingerprint the matrix pins. No instance id or timestamp."""
    return {
        'state_digest': service.machine.state_digest(),
        'overlay_state_digest': overlay.state_digest(overlay.fold(service.overlay_entries)),
        'receipts': len(service.receipts),
        'cases': len(service.snapshot()['cases']),
    }


def _temp_names(directory):
    return sorted(
        child.name for child in Path(directory).iterdir()
        if child.is_file() and child.name.startswith('.workspace.json.')
        and child.name.endswith('.tmp'))


def _restart_observed(directory, write_probe=False):
    """Close, reopen and read the restored state; then run the offline audit.

    The audit reads the file after the port closes. A write probe runs only
    for fail-closed cells so ACTIVE restarts keep the file untouched.
    """
    port = FileWorkspace.open(directory)
    try:
        service = CapitalService(port)
        observed = {
            'workspace_status': service.workspace_status,
            'state_digest': service.machine.state_digest(),
            'overlay_state_digest': overlay.state_digest(overlay.fold(service.overlay_entries)),
            'receipts_restored': len(service.receipts),
            'cases': len(service.snapshot()['cases']),
        }
        if write_probe:
            probe = {'instance_id': service.instance_id, 'operation_id': 'cr-probe',
                     'op': 'offer', 'advance_id': 'sim-cr-probe',
                     'args': {'fixture_id': 'sim-committed', 'amount': 1}}
            try:
                service.execute(probe)
            except ApiError as exc:
                assert exc.status == 503, exc.status
                observed['write_blocked'] = exc.code
            else:
                observed['write_blocked'] = None
    finally:
        port.close()
    report = audit.audit_workspace(directory)
    observed['audit_ok'] = report['ok']
    observed['audit_reason'] = report['reason']
    observed['audit_failed_check'] = report['failed_check']
    return observed


def _assert_blocked_after(service, index, cell):
    """Every command after the crashed boundary must be refused, never silently applied."""
    for step in SCRIPT:
        if step['step'] <= index:
            continue
        try:
            _apply(service, step)
        except ApiError as exc:
            assert (exc.code, exc.status) == ('WORKSPACE_WRITE_FAILED', 503), (cell['id'], exc.code)
        else:
            raise AssertionError(f"{cell['id']}: step {step['step']} was not blocked after the crash")


def _run_save_boundary(cell, directory):
    """One injection at the armed save index; every later command must stay blocked."""
    index = cell['save_index']
    port = FileWorkspace.open(directory)
    injecting = CrashInjectingStorage(port, lambda n: cell['position'] if n == index else None)
    service = CapitalService(injecting)
    failed_step, raised = None, None
    for step in SCRIPT:
        try:
            _apply(service, step)
        except ApiError as exc:
            assert exc.status == 503, (cell['id'], exc.code, exc.status)
            failed_step, raised = step['step'], exc.code
            break
    assert (failed_step, raised) == (index, 'WORKSPACE_WRITE_FAILED'), (cell['id'], failed_step, raised)
    _assert_blocked_after(service, index, cell)
    port.close()
    observed = _restart_observed(directory)
    observed['raised'] = raised
    assert not _temp_names(directory), (cell['id'], _temp_names(directory))
    return observed


def _run_rename(cell, directory):
    """os-level injection inside _atomic_write scoped to one scripted save."""
    index = cell['save_index']
    port = FileWorkspace.open(directory)
    service = CapitalService(port)
    failed_step, raised = None, None
    for step in SCRIPT:
        try:
            if step['step'] == index:
                with _conformance()._crash(cell['inject']):
                    _apply(service, step)
            else:
                _apply(service, step)
        except ApiError as exc:
            assert exc.status == 503, (cell['id'], exc.code, exc.status)
            failed_step, raised = step['step'], exc.code
            break
    assert (failed_step, raised) == (index, 'WORKSPACE_WRITE_FAILED'), (cell['id'], failed_step, raised)
    _assert_blocked_after(service, index, cell)
    port.close()
    observed = _restart_observed(directory)
    observed['raised'] = raised
    assert not _temp_names(directory), (cell['id'], _temp_names(directory))
    return observed


def _flip_byte(raw, marker, first, second):
    """Swap the byte after `marker` for `first` (or `second` when it already is)."""
    index = raw.index(marker) + len(marker)
    current = raw[index:index + 1]
    replacement = first if current != first else second
    flipped = raw[:index] + replacement + raw[index + 1:]
    assert len(flipped) == len(raw) and flipped != raw
    json.loads(flipped)  # the torn file still parses; the checksum must catch it
    return flipped


def _torn_bytes(raw, inject):
    if inject == 'truncate-half':
        cut = raw[:len(raw) // 2]
        try:
            json.loads(cut)
        except ValueError:
            return cut
        raise AssertionError('truncated workspace still parses')
    if inject == 'payload-byte':
        # One digit inside the payload journal: JSON stays valid, payload_sha256 disagrees.
        return _flip_byte(raw, b'"amount":', b'9', b'8')
    if inject == 'overlay-digest-byte':
        # One hex char inside the overlay section's cached digest: the payload
        # checksum stays intact, only the section checksum can catch this.
        return _flip_byte(raw, b'"overlay_state":{"digest":"', b'0', b'1')
    raise AssertionError(f'unknown torn inject {inject}')


def _run_torn(cell, directory):
    port = FileWorkspace.open(directory)
    service = CapitalService(port)
    for step in SCRIPT:
        _apply(service, step)
    port.close()
    path = Path(directory) / store.FILE_NAME
    raw = _torn_bytes(path.read_bytes(), cell['inject'])
    path.write_bytes(raw)
    observed = _restart_observed(directory, write_probe=True)
    observed['raised'] = None
    observed['file_unchanged'] = path.read_bytes() == raw
    assert not _temp_names(directory), (cell['id'], _temp_names(directory))
    return observed


def _run_stale_temp(cell, directory):
    port = FileWorkspace.open(directory)
    service = CapitalService(port)
    for step in SCRIPT:
        _apply(service, step)
    port.close()
    stale = Path(directory) / STALE_TEMP
    stale.write_bytes(b'partial-not-a-book')
    observed = _restart_observed(directory)
    observed['raised'] = None
    observed['temp_cleared'] = not stale.exists()
    return observed


def _run_sigkill(cell, directory):
    """Real SIGKILL on a --workspace subprocess mid-write; restart is one of two digests."""
    sim = _sim_journeys()
    server = sim.ServerProcess(directory)
    try:
        session = sim.Session(server.start())
        old_instance = session.instance_id
        confirmed = []
        for step in SCRIPT[:SIGKILL_STEP - 1]:
            status, receipt = session.command(
                step['op'], step['advance_id'], step['operation_id'], **step['args'])
            assert (status, receipt.get('outcome')) == (200, 'ACCEPTED'), (
                step['operation_id'], status, receipt)
            confirmed.append(step['operation_id'])
        lost = SCRIPT[SIGKILL_STEP - 1]
        session.client.send_lost('/api/overlay/commands', {
            'instance_id': session.instance_id, 'operation_id': lost['operation_id'],
            'op': 'advance_day', 'from_sim_day': lost['from_sim_day'],
            'to_sim_day': lost['to_sim_day'], 'reason': lost['reason']}, session.token)
        assert server.kill() == -signal.SIGKILL
        restarted = sim.Session(server.start())
        overlay_state = restarted.overlay()
        observed = {
            'workspace_status': restarted.state['workspace']['status'],
            'state_digest': restarted.state['state_digest'],
            'receipts_restored': restarted.state['operation_count'],
            'cases': len(restarted.state['cases']),
            'overlay_state_digest': overlay_state['overlay_state_digest'],
        }
        for operation_id in confirmed:
            status, receipt = restarted.operation(operation_id)
            assert (status, receipt.get('outcome')) == (200, 'ACCEPTED'), (operation_id, status, receipt)
            assert receipt['instance_id'] == old_instance, (operation_id, receipt['instance_id'])
        status, with_op = restarted.get(f'/api/overlay?operation_id={lost["operation_id"]}')
        assert status == 200, status
        # A completed tick is rebuilt from its overlay entries, an unapplied one
        # is UNKNOWN; a torn half-write must never appear.
        outcome = with_op['operation'].get('outcome')
        assert outcome in ('APPLIED', 'UNKNOWN'), with_op['operation']
        assert (overlay_state['sim_day'] == lost['to_sim_day']) == (outcome == 'APPLIED'), (
            overlay_state['sim_day'], outcome)
        assert not _temp_names(directory), _temp_names(directory)
        restarted.client.fence.resolve(lost['operation_id'])
    finally:
        server.kill()
    report = audit.audit_workspace(directory)
    observed['audit_ok'] = report['ok']
    observed['audit_reason'] = report['reason']
    observed['audit_failed_check'] = report['failed_check']
    observed['raised'] = None
    return observed


RUNNERS = {
    'save-boundary': _run_save_boundary,
    'rename': _run_rename,
    'torn': _run_torn,
    'stale-temp': _run_stale_temp,
    'sigkill': _run_sigkill,
}


def cell_outcome(cell):
    """Run one cell in a fresh directory and return the observed restart facts."""
    with tempfile.TemporaryDirectory(prefix='capital-crash-matrix-') as tmp:
        return RUNNERS[cell['runner']](cell, Path(tmp))


def outcome_problems(expect, observed):
    """Every pinned field that disagreed. `*_one_of` pins a set of valid values."""
    problems = []
    for key, wanted in expect.items():
        if key.endswith('_one_of'):
            actual = observed.get(key[:-len('_one_of')], '<missing>')
            if actual not in wanted:
                problems.append(f'{key}: {actual!r} not one of {wanted!r}')
        else:
            actual = observed.get(key, '<missing>')
            if actual != wanted:
                problems.append(f'{key}: {actual!r} != {wanted!r}')
    return problems


# ------------------------------------------------------------------- pinning

def cell_specs():
    """The fixed matrix: every save boundary crashed before and after the write."""
    cells = []
    for step in SCRIPT:
        for position in ('before', 'after'):
            cells.append({
                'id': f"{step['boundary']}-{position}-save{step['step']}",
                'runner': 'save-boundary', 'boundary': step['boundary'],
                'position': position, 'save_index': step['step'],
                'inject': 'WORKSPACE_WRITE_FAILED',
            })
    for save_index in (4, 7):
        for inject, position in (('replace', 'before'), ('dir-fsync', 'after')):
            cells.append({
                'id': f'temp-rename-{position}-save{save_index}',
                'runner': 'rename', 'boundary': 'temp-rename', 'position': position,
                'save_index': save_index, 'inject': inject,
                'rename_of': SCRIPT_STEPS[save_index]['boundary'],
            })
    for inject in ('truncate-half', 'payload-byte', 'overlay-digest-byte'):
        cells.append({
            'id': f'torn-{inject}', 'runner': 'torn', 'boundary': 'torn-payload',
            'position': 'trailing-partial', 'save_index': None, 'inject': inject,
        })
    cells.append({
        'id': 'stale-temp-never-loaded', 'runner': 'stale-temp', 'boundary': 'temp-rename',
        'position': 'trailing-partial', 'save_index': None, 'inject': 'stale-tmp',
    })
    cells.append({
        'id': 'sigkill-mid-overlay-write', 'runner': 'sigkill', 'boundary': 'sigkill',
        'position': 'mid-write', 'save_index': SIGKILL_STEP, 'inject': 'SIGKILL',
    })
    return cells


def compute_prefixes():
    """prefix[k] is the digest fingerprint after save k commits; prefix[0] is a fresh book."""
    with tempfile.TemporaryDirectory(prefix='capital-crash-matrix-base-') as tmp:
        port = FileWorkspace.open(tmp)
        try:
            service = CapitalService(port)
            prefixes = [_capture(service)]
            for step in SCRIPT:
                _apply(service, step)
                prefixes.append(_capture(service))
        finally:
            port.close()
    return prefixes


def _prefix_expect(prefix, raised, exists=True):
    # A restart on a never-saved directory is ACTIVE on an empty book; the
    # offline audit then finds no workspace.json, which is not a torn file.
    return {
        'workspace_status': 'ACTIVE',
        'raised': raised,
        'state_digest': prefix['state_digest'],
        'overlay_state_digest': prefix['overlay_state_digest'],
        'receipts_restored': prefix['receipts'],
        'cases': prefix['cases'],
        'audit_ok': exists,
        'audit_reason': None if exists else 'WORKSPACE_UNREADABLE',
        'audit_failed_check': None if exists else 'workspace_file',
    }


def cell_expect(cell, prefixes):
    """The pinned restart outcome of one cell, derived from the script and prefixes."""
    runner = cell['runner']
    if runner in ('save-boundary', 'rename'):
        index = cell['save_index']
        prefix_index = index - 1 if cell['position'] == 'before' else index
        return _prefix_expect(prefixes[prefix_index], 'WORKSPACE_WRITE_FAILED', exists=prefix_index > 0)
    if runner == 'torn':
        # Fails closed, never a silent empty book: the process reads the empty
        # state but reports UNREADABLE, blocks writes and leaves bytes intact.
        return {
            'workspace_status': 'WORKSPACE_UNREADABLE',
            'raised': None,
            'state_digest': prefixes[0]['state_digest'],
            'overlay_state_digest': prefixes[0]['overlay_state_digest'],
            'receipts_restored': 0,
            'cases': 0,
            'write_blocked': 'WORKSPACE_UNREADABLE',
            'file_unchanged': True,
            'audit_ok': False,
            'audit_reason': 'WORKSPACE_UNREADABLE',
            'audit_failed_check': _TORN_FAILED_CHECK[cell['inject']],
        }
    if runner == 'stale-temp':
        expect = _prefix_expect(prefixes[-1], None)
        expect['temp_cleared'] = True
        return expect
    if runner == 'sigkill':
        before, after = prefixes[SIGKILL_STEP - 1], prefixes[SIGKILL_STEP]
        return {
            'workspace_status': 'ACTIVE',
            'raised': None,
            'state_digest': before['state_digest'],
            'overlay_state_digest_one_of': [
                before['overlay_state_digest'], after['overlay_state_digest']],
            'receipts_restored': before['receipts'],
            'cases': before['cases'],
            'audit_ok': True,
        }
    raise AssertionError(f"unknown runner {runner}")


def build_table():
    """The pinned matrix table: script, prefix digests, and every cell's expectation."""
    prefixes = compute_prefixes()
    cells = [dict(cell, expect=cell_expect(cell, prefixes)) for cell in cell_specs()]
    return {
        'format': FORMAT,
        'label': LABEL,
        'durable': 'LOCAL_FILE_WORKSPACE',
        'stage5_durable_transactions': 'NOT_BOUND',
        'semantic_conformance': False,
        'cross_host_fencing': 'NOT_CLAIMED',
        'script': [dict(step) for step in SCRIPT],
        'prefix_digests': [
            dict({'after_step': index}, **prefix) for index, prefix in enumerate(prefixes)],
        'cells': cells,
        'cell_count': len(cells),
    }


def serialize(table):
    return (json.dumps(table, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('utf-8')


def _drift_detail(committed, generated):
    if committed.get('format') != generated.get('format'):
        return 'format mismatch'
    for key in generated:
        if key == 'cells':
            continue
        if committed.get(key) != generated[key]:
            return f'{key} drifted'
    committed_cells = {cell['id']: cell for cell in committed.get('cells', [])}
    generated_ids = {cell['id'] for cell in generated['cells']}
    drifted = [cell['id'] for cell in generated['cells'] if committed_cells.get(cell['id']) != cell]
    extra = sorted(set(committed_cells) - generated_ids)
    detail = []
    if drifted:
        detail.append('differing cells: ' + ', '.join(drifted))
    if extra:
        detail.append('unexpected cells: ' + ', '.join(extra))
    return '; '.join(detail) or 'byte drift'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true',
                      help='Regenerate the table and exit 1 on any drift from the pin.')
    mode.add_argument('--write', action='store_true', help='Rewrite the pinned table.')
    args = parser.parse_args(argv)
    generated = build_table()
    if args.write:
        VECTOR.parent.mkdir(parents=True, exist_ok=True)
        VECTOR.write_bytes(serialize(generated))
        print(f'crash matrix vectors written: {generated["cell_count"]} cells -> {VECTOR}')
        return 0
    if not VECTOR.is_file():
        print(f'crash matrix vectors missing: {VECTOR}; run tests/crash_matrix.py --write',
              file=sys.stderr)
        return 1
    raw = VECTOR.read_bytes()
    if raw != serialize(generated):
        try:
            committed = json.loads(raw.decode('utf-8'))
        except (UnicodeError, json.JSONDecodeError):
            print('crash matrix vectors unreadable; run tests/crash_matrix.py --write',
                  file=sys.stderr)
            return 1
        print('crash matrix vectors drift: ' + _drift_detail(committed, generated),
              file=sys.stderr)
        print('run python3 tests/crash_matrix.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'crash matrix vectors ok: {generated["cell_count"]} cells match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
