#!/usr/bin/env python3
"""Build a deterministic simulated portfolio and pin instance-independent digests.

The book is SIMULATED. Amounts are fixture units on the pinned open face so the
six cases can exist together. They are not a product limit, fee, or allocation.
No clock and no instance id is written into the golden file.

Cases, in story order, use fixed operation ids:

- sim-closed: repaid and CLOSED on the COMMITTED fixture
- sim-defaulted: DRAWN then DEFAULTED; the synthetic reservation stays
- sim-rejected: REJECTED from OFFERED
- sim-cancelled: CANCELLED from OFFERED
- sim-unbound: DRAWN with settlement_gate UNBOUND
- sim-pending-settlement: bound to the CAPTURED fixture; draw stays REJECTED

`tests/golden/demo.json` pins state_digest, projection totals, and the export
manifest content_digest. A mismatch fails. Rewriting the pin requires
`--update-golden`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.service import CapitalService
from capital.store import FILE_NAME, FileWorkspace

GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
VOLATILE_KEYS = frozenset({
    'instance_id', 'created_at', 'saved_at', 'timestamp', 'timestamps',
    'local_token', 'saved_by_instance',
})
# Fixture units only. Shared open face on the pinned views is 100000.
CLOSED_AMOUNT = 20_000
DEFAULTED_AMOUNT = 30_000
TERMINAL_OFFER_AMOUNT = 10_000
UNBOUND_AMOUNT = 15_000
PENDING_AMOUNT = 25_000

EXPECTED = (
    ('sim-closed', 'CLOSED', 'MOCK_COMMIT_OBSERVED'),
    ('sim-defaulted', 'DEFAULTED', 'MOCK_COMMIT_OBSERVED'),
    ('sim-rejected', 'REJECTED', 'UNBOUND'),
    ('sim-cancelled', 'CANCELLED', 'UNBOUND'),
    ('sim-unbound', 'DRAWN', 'UNBOUND'),
    ('sim-pending-settlement', 'APPROVED', 'BOUND'),
)

STEPS = (
    ('op-closed-offer', 'offer', 'sim-closed', {'fixture_id': 'sim-committed', 'amount': CLOSED_AMOUNT}, 'ACCEPTED', None),
    ('op-closed-approve', 'approve', 'sim-closed', {}, 'ACCEPTED', None),
    ('op-closed-bind', 'bind_settlement', 'sim-closed', {}, 'ACCEPTED', None),
    ('op-closed-draw', 'draw', 'sim-closed', {}, 'ACCEPTED', None),
    ('op-closed-repay', 'repay', 'sim-closed', {'amount': CLOSED_AMOUNT, 'sequence': 1}, 'ACCEPTED', None),
    ('op-closed-close', 'close', 'sim-closed', {}, 'ACCEPTED', None),
    ('op-defaulted-offer', 'offer', 'sim-defaulted', {'fixture_id': 'sim-committed', 'amount': DEFAULTED_AMOUNT}, 'ACCEPTED', None),
    ('op-defaulted-approve', 'approve', 'sim-defaulted', {}, 'ACCEPTED', None),
    ('op-defaulted-bind', 'bind_settlement', 'sim-defaulted', {}, 'ACCEPTED', None),
    ('op-defaulted-draw', 'draw', 'sim-defaulted', {}, 'ACCEPTED', None),
    ('op-defaulted-default', 'default', 'sim-defaulted', {}, 'ACCEPTED', None),
    ('op-rejected-offer', 'offer', 'sim-rejected', {'fixture_id': 'sim-committed', 'amount': TERMINAL_OFFER_AMOUNT}, 'ACCEPTED', None),
    ('op-rejected-reject', 'reject', 'sim-rejected', {}, 'ACCEPTED', None),
    ('op-cancelled-offer', 'offer', 'sim-cancelled', {'fixture_id': 'sim-committed', 'amount': TERMINAL_OFFER_AMOUNT}, 'ACCEPTED', None),
    ('op-cancelled-cancel', 'cancel', 'sim-cancelled', {}, 'ACCEPTED', None),
    ('op-unbound-offer', 'offer', 'sim-unbound', {'fixture_id': 'sim-pending', 'amount': UNBOUND_AMOUNT}, 'ACCEPTED', None),
    ('op-unbound-approve', 'approve', 'sim-unbound', {}, 'ACCEPTED', None),
    ('op-unbound-draw', 'draw', 'sim-unbound', {}, 'ACCEPTED', None),
    ('op-pending-offer', 'offer', 'sim-pending-settlement', {'fixture_id': 'sim-pending', 'amount': PENDING_AMOUNT}, 'ACCEPTED', None),
    ('op-pending-approve', 'approve', 'sim-pending-settlement', {}, 'ACCEPTED', None),
    ('op-pending-bind', 'bind_settlement', 'sim-pending-settlement', {}, 'ACCEPTED', None),
    ('op-pending-draw', 'draw', 'sim-pending-settlement', {}, 'REJECTED', 'SETTLEMENT_NOT_COMMITTED'),
)


class SeedError(Exception):
    pass


def _reject_volatile(value, path='$'):
    if type(value) is dict:
        for key, item in value.items():
            if key in VOLATILE_KEYS:
                raise SeedError(f'volatile key {path}.{key}')
            _reject_volatile(item, path + '.' + key)
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_volatile(item, f'{path}[{index}]')


def apply_steps(service):
    """Replay the fixed story. Rejected draw is part of the pending-settlement case."""
    for operation_id, op, advance_id, args, outcome, error in STEPS:
        receipt = service.execute({
            'instance_id': service.instance_id,
            'operation_id': operation_id,
            'op': op,
            'advance_id': advance_id,
            'args': args,
        })
        if receipt.get('outcome') != outcome or (error is not None and receipt.get('error') != error):
            raise SeedError(
                f'{operation_id} outcome {receipt.get("outcome")} error {receipt.get("error")}'
                f' expected {outcome} {error}')
        if receipt.get('funds_executed') is not False:
            raise SeedError(f'{operation_id} funds_executed')
    return service


def capture(service):
    """Instance-independent pin: digest, projection totals, manifest content digest."""
    snapshot = service.snapshot()
    if snapshot.get('funds_executed') is not False or snapshot.get('mode') != 'LOCAL_SIMULATION':
        raise SeedError('snapshot is not a local simulation')
    by_id = {case['advance_id']: case for case in snapshot['cases']}
    if set(by_id) != {row[0] for row in EXPECTED}:
        raise SeedError(f'case set {sorted(by_id)}')
    cases = []
    for advance_id, phase, gate in EXPECTED:
        case = by_id[advance_id]
        if case['phase'] != phase or case['settlement_gate'] != gate:
            raise SeedError(
                f'{advance_id} phase {case["phase"]} gate {case["settlement_gate"]}'
                f' expected {phase} {gate}')
        if case.get('funds_executed') is not False:
            raise SeedError(f'{advance_id} funds_executed')
        cases.append({
            'advance_id': advance_id,
            'phase': phase,
            'settlement_gate': gate,
            'label': 'SIMULATED',
        })
    unbound = by_id['sim-unbound']
    pending = by_id['sim-pending-settlement']
    if unbound['mock_settlement_commit_observed'] is not False or unbound['settlement_id'] is not None:
        raise SeedError('unbound case is not UNBOUND')
    if pending['settlement_id'] != 'sim-pending' or pending['mock_settlement_commit_observed'] is not False:
        raise SeedError('pending-settlement case is not bound to the captured fixture')
    if by_id['sim-closed']['outstanding_exposure'] != 0 or by_id['sim-defaulted']['outstanding_exposure'] != DEFAULTED_AMOUNT:
        raise SeedError('exposure does not match the simulated story')
    projection = service.projection()
    if projection.get('accounting_policy') != 'SYNTHETIC_UNADOPTED' or projection.get('funds_executed') is not False:
        raise SeedError('projection is not the unadopted simulation')
    if projection.get('cut') != snapshot['state_digest']:
        raise SeedError('projection cut drifted from state_digest')
    accounts = projection['accounts']
    advances = projection['read_model']['advances']
    debit = sum(row['debit_total'] for row in accounts)
    credit = sum(row['credit_total'] for row in accounts)
    if debit != credit:
        raise SeedError('projection totals do not balance')
    totals = {
        'label': 'SIMULATED',
        'accounting_policy': 'SYNTHETIC_UNADOPTED',
        'debit': debit,
        'credit': credit,
        'advance_drawn': sum(row['drawn'] for row in advances),
        'advance_repaid': sum(row['repaid'] for row in advances),
        'advance_outstanding': sum(row['outstanding'] for row in advances),
    }
    manifest = service.export_manifest()
    if manifest.get('label') != 'SIMULATED' or manifest.get('funds_executed') is not False:
        raise SeedError('manifest is not simulated')
    body = {
        'label': 'SIMULATED',
        'funds_executed': False,
        'note': 'SIMULATED pin of state_digest, projection totals, and manifest content_digest. Process identity and clock fields are excluded.',
        'cases': cases,
        'state_digest': snapshot['state_digest'],
        'projection_totals': totals,
        'content_digest': manifest['content_digest'],
    }
    _reject_volatile(body)
    return body


def build_service(storage=None):
    service = CapitalService(storage)
    apply_steps(service)
    return service


def render(body) -> str:
    return json.dumps(body, sort_keys=True, indent=2, ensure_ascii=True) + '\n'


def diff_paths(expected, actual, path='$'):
    if type(expected) is not type(actual):
        return [path]
    if type(expected) is dict:
        found = []
        for key in sorted(set(expected) | set(actual)):
            child = path + '.' + key
            if key not in expected or key not in actual:
                found.append(child)
            else:
                found.extend(diff_paths(expected[key], actual[key], child))
        return found
    if type(expected) is list:
        if len(expected) != len(actual):
            return [path]
        found = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            found.extend(diff_paths(left, right, f'{path}[{index}]'))
        return found
    if expected != actual:
        return [path]
    return []


def open_fresh(directory):
    path = Path(directory)
    try:
        path.mkdir(parents=True, exist_ok=True)
        target = path / FILE_NAME
        if target.exists():
            target.unlink()
        return FileWorkspace.open(path)
    except OSError as exc:
        raise SeedError(f'workspace: {exc}') from exc


def load_golden(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SeedError(f'golden unreadable: {path}') from exc


def check_or_update(body, golden, update):
    if update:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(render(body), encoding='utf-8')
        return []
    if not golden.is_file():
        raise SeedError(f'golden missing: {golden}. Pass --update-golden to write it.')
    expected = load_golden(golden)
    _reject_volatile(expected)
    return diff_paths(expected, body)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--golden', type=Path, default=GOLDEN, help='Pin file. Default tests/golden/demo.json')
    parser.add_argument('--update-golden', action='store_true', help='Rewrite the pin from this run')
    parser.add_argument('--workspace', type=Path, default=None, help='Optional local JSON workspace directory')
    args = parser.parse_args(argv)
    storage = None
    try:
        if args.workspace is not None:
            storage = open_fresh(args.workspace)
        service = build_service(storage)
        body = capture(service)
        drifted = check_or_update(body, args.golden, args.update_golden)
    except SeedError as exc:
        print(f'seed demo failed: {exc}', file=sys.stderr)
        return 1
    finally:
        if storage is not None:
            storage.close()
    totals = body['projection_totals']
    action = 'updated' if args.update_golden else 'ok'
    print(
        f'seed demo {action} SIMULATED state_digest={body["state_digest"]} '
        f'content_digest={body["content_digest"]} debit={totals["debit"]} credit={totals["credit"]}')
    if drifted:
        print('golden drift: ' + ', '.join(drifted), file=sys.stderr)
        print('pass --update-golden to rewrite the pin', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
