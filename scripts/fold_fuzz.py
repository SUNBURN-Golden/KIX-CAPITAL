#!/usr/bin/env python3
"""SIMULATED seeded sequence verification; no durability or performance claim.

Envelope byte equality is conditional on fixed synthetic writer/clock inputs,
the same interpreter and tree. CAP-11 remains NOT_BOUND. --check writes only
temporary workspaces; --write explicitly authors the new corpus alone.
"""
from __future__ import annotations

import sys
# Disable caches before project imports, including on a clean checkout.
sys.dont_write_bytecode = True

import argparse
import copy
import datetime
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import overlay, store
from capital.service import ApiError, CapitalService, MAX_OPERATIONS
from capital.strict_json import loads

FORMAT = 'KIX_CAPITAL_FOLD_FUZZ_V1'
VECTOR = ROOT / 'tests/vectors/fold_fuzz.json'
SEEDS = tuple(range(74810048, 74810064))
MAX_COMMANDS = 64
MAX_ADVANCES = 6
WRITER = 'sim-fold-fuzz-writer'
GENERATOR = {'version': 'LCG32-LIFECYCLE-1', 'seeds': list(SEEDS),
             'max_commands': MAX_COMMANDS, 'max_advances': MAX_ADVANCES}


class FuzzError(Exception):
    pass


def require(condition, detail):
    if not condition:
        raise FuzzError(detail)


class Lcg32:
    def __init__(self, seed):
        require(type(seed) is int and 0 <= seed <= 0xffffffff, 'invalid seed')
        self.x = seed

    def next(self):
        self.x = (1664525 * self.x + 1013904223) & 0xffffffff
        return self.x

    def choose(self, candidates):
        return candidates[self.next() % len(candidates)]


def generate_commands(seed):
    """Randomly interleave ordered legal lifecycle heads, without retries.

    Six lanes guarantee coverage, using existing seed_demo fixture amounts.
    Four draws reserve at most 80,000 of the shared 100,000 synthetic face.
    Each drawn/repayment prefix is followed by a tick, including nonzero
    accrual. Four additional candidate ticks vary ordering. These workload
    budgets are verification choices, not financial policy or capacity limits.
    """
    rng = Lcg32(seed)
    paths = [
        ['offer', 'approve', 'bind_settlement', 'draw', 'repay', 'repay', 'close', 'reconcile'],
        ['offer', 'approve', 'draw', 'default', 'reconcile'],
        ['offer', 'reject', 'reconcile'],
        ['offer', 'cancel', 'reconcile'],
        ['offer', 'approve', 'draw', 'repay', 'repay', 'close', 'reconcile'],
        ['offer', 'approve', 'bind_settlement', 'draw', 'default', 'reconcile'],
    ]
    amounts = (20000, 30000, 10000, 10000, 20000, 10000)
    cursors, repayments = [0] * MAX_ADVANCES, [0] * MAX_ADVANCES
    commands, day, extra_ticks = [], 0, 0

    def tick():
        nonlocal day
        to_day = day + rng.choose((1, 3, 7))
        commands.append({'operation_id': f'ff-{seed}-{len(commands) + 1}',
                         'op': 'advance_day', 'from_sim_day': day,
                         'to_sim_day': to_day, 'reason': 'FOLD_FUZZ'})
        day = to_day

    tick()
    while any(cursors[i] < len(paths[i]) for i in range(MAX_ADVANCES)):
        candidates = [i for i in range(MAX_ADVANCES) if cursors[i] < len(paths[i])]
        if extra_ticks < 4:
            candidates.append('tick')
        lane = rng.choose(candidates)
        if lane == 'tick':
            tick()
            extra_ticks += 1
            continue
        op = paths[lane][cursors[lane]]
        args = {}
        if op == 'offer':
            args = {'fixture_id': 'sim-committed', 'amount': amounts[lane]}
        elif op == 'repay':
            repayments[lane] += 1
            args = {'amount': 10000, 'sequence': repayments[lane]}
        commands.append({'operation_id': f'ff-{seed}-{len(commands) + 1}',
                         'op': op, 'advance_id': f'sim-ff-{seed}-{lane}', 'args': args})
        cursors[lane] += 1
        if op in ('draw', 'repay'):
            tick()
    tick()
    require(len(commands) <= MAX_COMMANDS, f'seed {seed}: command budget')
    return commands


class FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2000, 1, 1, tzinfo=datetime.timezone.utc)


def sha(value):
    return hashlib.sha256(store.canonical_bytes(value)).hexdigest()


def capture(service, raw):
    """Independently refold copied journals and bound every persisted prefix."""
    journal = copy.deepcopy(service.producer.export_journal())
    restored = service.producer.restored(journal)
    require(restored.canonical_state() == service.producer.canonical_state(), 'F04 fold state')
    require(restored.state_digest() == service.machine.state_digest(), 'F04 fold digest')
    entries = copy.deepcopy(service.overlay_entries)
    state = overlay.fold(entries, len(journal))
    document = loads(raw)
    store.verify_document(document)
    require(store.canonical_bytes(state) == store.canonical_bytes(document['overlay']['overlay_state']['state']),
            'overlay fold state')
    require(overlay.state_digest(state) == document['overlay']['overlay_state']['digest'],
            'persisted overlay_state_digest')
    require(document['payload']['receipts'] == service.receipts, 'persisted receipts')
    require(document['payload']['journal'] == journal, 'persisted F04 journal')
    require(document['overlay']['journal'] == entries, 'persisted overlay journal')
    require(document['payload']['state_digest'] == restored.state_digest(), 'persisted state_digest')
    bounds = overlay.load_bounds()
    require(bounds is not None and bounds == service.overlay_bounds, 'capacity NOT_BOUND')
    require(len(service.receipts) <= MAX_OPERATIONS, 'receipt capacity')
    require(len(service.case_fixtures) <= MAX_ADVANCES, 'advance budget')
    require(len(entries) <= bounds['OVERLAY_MAX_ENTRIES'], 'entry capacity')
    require(all(overlay.entry_size(e) <= bounds['OVERLAY_ENTRY_MAX_BYTES'] for e in entries), 'entry size')
    require(state['sim_day'] <= bounds['SIM_DAY_MAX'], 'day capacity')
    capacity = service._overlay_capacity(entries)
    require(capacity['decision_records']['current'] <= bounds['DECISION_RECORDS_MAX'], 'decision capacity')
    require(capacity['agent_proposals']['current'] <= bounds['AGENT_PROPOSALS_MAX'], 'proposal capacity')
    require(overlay.section_size(document['payload'], entries) <= bounds['ENVELOPE_MAX_BYTES'],
            'service envelope capacity')
    require(len(raw) <= bounds['ENVELOPE_MAX_BYTES'], 'actual envelope capacity')
    cores = {e['overlay_id']: overlay.operation_receipt(entries, e['overlay_id'])
             for e in entries if e['kind'] == overlay.KIND_CLOCK}
    return {'state_digest': restored.state_digest(), 'overlay_state_digest': overlay.state_digest(state),
            'envelope_sha256': hashlib.sha256(raw).hexdigest(), 'receipts_sha256': sha(service.receipts),
            'overlay_receipts_sha256': sha(cores)}


def replay(commands, directory):
    """Real file writes, prefix folds, then fresh-session reload; no normalization."""
    directory = Path(directory)
    require(not (directory / store.FILE_NAME).exists(), 'replay needs a fresh workspace')
    port = store.FileWorkspace.open(directory)
    checkpoints, envelopes = [], []
    try:
        service = CapitalService(port)
        require(service.workspace_status == 'ACTIVE', 'fresh workspace not ACTIVE')
        service.instance_id = port.writer_instance = WRITER
        require(service.overlay_bounds is not None, 'capacity NOT_BOUND')
        for step, command in enumerate(commands, 1):
            try:
                before = len(service.machine.export_journal())
                body = dict(copy.deepcopy(command), instance_id=service.instance_id)
                # Replace only capital.store's datetime reference, never the global module.
                with patch.object(store, 'datetime') as clock:
                    clock.datetime = FixedDateTime
                    clock.timezone = datetime.timezone
                    if command['op'] == 'advance_day':
                        require(0 < command['to_sim_day'] - command['from_sim_day']
                                <= service.overlay_bounds['max_step_days'], 'tick step bound')
                        receipt = service.overlay_command(body)
                        require(receipt['outcome'] == 'APPLIED', 'tick outcome')
                    else:
                        if command['op'] == 'draw':
                            view = service.producer.view(command['advance_id'])
                            require(view['amount'] <= view['residual_unreserved'], 'shared face')
                        receipt = service.execute(body)
                        require(receipt['outcome'] == 'ACCEPTED', f'unexpected rejection {receipt}')
                        require(receipt['funds_executed'] is False, 'funds executed')
                delta = 0 if command['op'] in ('advance_day', 'reconcile') else 1
                require(len(service.machine.export_journal()) == before + delta, 'journal append count')
                raw = port.path.read_bytes()
                checkpoint = dict(step=step, **capture(service, raw))
                checkpoints.append(checkpoint)
                envelopes.append(raw)
            except (FuzzError, ApiError, ValueError, KeyError) as exc:
                raise FuzzError(f'step {step} {command["op"]}: {exc}') from exc
        receipts = copy.deepcopy(service.receipts)
        entries = copy.deepcopy(service.overlay_entries)
        journal = copy.deepcopy(service.machine.export_journal())
        mapping = copy.deepcopy(service.case_fixtures)
    finally:
        port.close()
    port = store.FileWorkspace.open(directory)
    try:
        reloaded = CapitalService(port)
        require(reloaded.workspace_status == 'ACTIVE', 'reload not ACTIVE')
        require(reloaded.instance_id != WRITER, 'reload session did not change')
        require(reloaded.receipts == receipts, 'reload receipt/fingerprint mappings')
        require(reloaded.overlay_entries == entries, 'reload overlay journal')
        require(reloaded.machine.export_journal() == journal, 'reload F04 journal')
        require(reloaded.case_fixtures == mapping, 'reload fixture mapping')
        for operation_id, stored in receipts.items():
            require(reloaded.operation(operation_id, reloaded.instance_id) == stored['receipt'],
                    f'reload receipt lookup {operation_id}')
        for command in commands:
            if command['op'] == 'advance_day':
                operation_id = command['operation_id']
                core = overlay.operation_receipt(entries, operation_id)
                require(overlay.operation_receipt(reloaded.overlay_entries, operation_id) == core,
                        f'reload overlay receipt {operation_id}')
                require(reloaded.overlay_state(operation_id)['operation'] == core,
                        f'reload overlay lookup {operation_id}')
        require(capture(reloaded, port.path.read_bytes()) == {k: v for k, v in checkpoints[-1].items()
                                                           if k != 'step'}, 'reload digests')
        require(port.path.read_bytes() == envelopes[-1], 'reload rewrote envelope')
    finally:
        port.close()
    return checkpoints, envelopes


def serialize(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def compare(expected, actual, context):
    require(type(expected) is type(actual), f'{context}: type drift')
    if type(actual) is dict:
        require(set(expected) == set(actual), f'{context}: keys drift')
        for key in actual:
            compare(expected[key], actual[key], f'{context}.{key}')
    elif type(actual) is list:
        require(len(expected) == len(actual), f'{context}: length drift')
        for index, (left, right) in enumerate(zip(expected, actual), 1):
            compare(left, right, f'{context} step {index}')
    else:
        require(expected == actual, f'{context}: drift')


def build_corpus(expected=None):
    result = {'format': FORMAT, 'label': 'SIMULATED', 'generator': copy.deepcopy(GENERATOR), 'cases': []}
    if expected is not None:
        compare({k: v for k, v in expected.items() if k != 'cases'},
                {k: v for k, v in result.items() if k != 'cases'}, 'corpus')
        require(type(expected.get('cases')) is list and len(expected['cases']) == len(SEEDS), 'cases drift')
    with tempfile.TemporaryDirectory(prefix='capital-fold-fuzz-') as tmp:
        for index, seed in enumerate(SEEDS):
            commands = generate_commands(seed)
            case = {'seed': seed, 'commands': commands}
            context = f'seed {seed}'
            if expected is not None:
                pinned = expected['cases'][index]
                require(type(pinned) is dict and set(pinned) == {'seed', 'commands', 'checkpoints'},
                        f'{context}: case shape')
                compare(pinned['seed'], seed, context)
                compare(pinned['commands'], commands, context + ' commands')
            try:
                first, first_bytes = replay(commands, Path(tmp) / f'{seed}-a')
                second, second_bytes = replay(commands, Path(tmp) / f'{seed}-b')
                compare(first, second, context + ' independent checkpoints')
                compare(first_bytes, second_bytes, context + ' envelope bytes')
                case['checkpoints'] = first
                if expected is not None:
                    compare(pinned['checkpoints'], first, context + ' checkpoints')
            except FuzzError as exc:
                raise FuzzError(f'{context}: {exc}') from exc
            result['cases'].append(case)
    return result


def check_corpus(path=VECTOR):
    raw = Path(path).read_bytes()
    expected = loads(raw)
    require(type(expected) is dict, 'corpus shape')
    require(raw == serialize(expected), 'corpus byte formatting drift')
    generated = build_corpus(expected)
    require(raw == serialize(generated), 'corpus byte drift')
    return generated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--file', type=Path, default=VECTOR)
    args = parser.parse_args(argv)
    try:
        if args.write:
            corpus = build_corpus()
            args.file.write_bytes(serialize(corpus))
        else:
            corpus = check_corpus(args.file)
    except (FuzzError, OSError, ValueError, KeyError, TypeError, RecursionError,
            ApiError, store.WorkspaceError) as exc:
        print(f'fold fuzz failed: {exc}', file=sys.stderr)
        return 1
    print(f'fold fuzz {"written" if args.write else "ok"} SIMULATED: '
          f'{len(corpus["cases"])} seeds, '
          f'{sum(len(c["commands"]) for c in corpus["cases"])} commands')
    return 0


if __name__ == '__main__':
    sys.exit(main())
