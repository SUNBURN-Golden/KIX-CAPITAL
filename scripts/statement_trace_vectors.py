#!/usr/bin/env python3
"""Pin SIMULATED statement trace inputs/results; --check never writes."""
import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import store
from capital.service import CapitalService
from capital.statement_trace import dump, trace_workspace_bytes

DEFAULT_DIR = ROOT / 'tests' / 'vectors' / 'statement_trace'


def command(service, op, case, key, **args):
    receipt = service.execute({'instance_id': service.instance_id, 'op': op,
                               'advance_id': case, 'operation_id': key, 'args': args})
    if receipt['outcome'] != 'ACCEPTED':
        raise AssertionError(receipt)


def ready(service, case, amount, fixture='sim-committed'):
    command(service, 'offer', case, case + '-offer', fixture_id=fixture, amount=amount)
    for op in ('approve', 'bind_settlement', 'draw'):
        command(service, op, case, case + '-' + op.replace('_', '-'))


def scene(name):
    service = CapitalService()
    service.instance_id = service.storage.writer_instance = 'statement-trace-vectors'
    if name != 'empty':
        ready(service, 'sim-a', 60_000)
        command(service, 'repay', 'sim-a', 'a-partial', amount=20_000, sequence=1)
        ready(service, 'sim-b', 30_000)
    if name in ('lifecycle', 'optional-detail', 'tampered-input'):
        command(service, 'repay', 'sim-a', 'a-final', amount=40_000, sequence=2)
        command(service, 'close', 'sim-a', 'a-close')
        command(service, 'default', 'sim-b', 'b-default')
        ready(service, 'sim-demo', 100_000, 'demo-alpha-arena')
        # Unlinked accepted reconcile and rejected offer receipts contribute nothing.
        command(service, 'reconcile', 'sim-demo', 'demo-reconcile')
        rejected = service.execute({'instance_id': service.instance_id, 'op': 'offer',
                                    'advance_id': 'sim-bad', 'operation_id': 'bad-offer',
                                    'args': {'fixture_id': 'sim-refund', 'amount': 100}})
        assert rejected['outcome'] == 'REJECTED'
    payload = {'receipts': copy.deepcopy(service.receipts), 'journal': service.machine.export_journal(),
               'case_fixtures': dict(service.case_fixtures), 'state_digest': service.machine.state_digest()}
    if name == 'optional-detail':
        payload['receipts']['sim-a-draw']['receipt']['result'].pop('credit')
        payload['receipts']['sim-a-draw']['receipt']['result']['extension'] = {'amount': 999}
    if name == 'tampered-input':
        payload['receipts']['sim-a-draw']['receipt']['result']['credit']['drawn_exposure'] += 1
    document = store.envelope('statement-trace-vectors', payload)
    document['saved_at'] = '2000-01-01T00:00:00.000000Z'
    return document


def build_vectors():
    result = {}
    for name in ('empty', 'shared-claim', 'lifecycle', 'optional-detail', 'tampered-input'):
        raw = dump(scene(name))
        result[name + '-workspace.json'] = raw
        result[name + '-expected.json'] = dump(trace_workspace_bytes(raw))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    files = build_vectors()
    if args.write:
        args.dir.mkdir(parents=True, exist_ok=True)
        for name, raw in files.items():
            (args.dir / name).write_bytes(raw)
        # Never delete unrelated files implicitly.
    else:
        actual = {path.name for path in args.dir.iterdir() if path.is_file()} if args.dir.is_dir() else set()
        drift = sorted(actual ^ set(files))
        drift += [name for name, raw in files.items()
                  if name in actual and (args.dir / name).read_bytes() != raw]
        if drift:
            print('statement trace vector drift: ' + ', '.join(drift), file=sys.stderr)
            return 1
    print(f'statement trace vectors {"written" if args.write else "matched"}: {len(files)} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
