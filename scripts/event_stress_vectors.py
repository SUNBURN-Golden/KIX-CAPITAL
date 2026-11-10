#!/usr/bin/env python3
"""Build/check deterministic SIMULATED detached event stress inputs and reports."""
import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capital.event_stress import evaluate_detached
from capital.portfolio_snapshot import FrozenInputs
from capital.service import CapitalService
from capital.store import canonical_bytes

DEFAULT_FILE = ROOT / 'tests/vectors/event_stress.json'


def build_artifact():
    service = CapitalService()
    try:
        # Fixed synthetic identifiers; there is no real event or cash execution.
        service.instance_id = 'event-stress-vectors'
        for advance, fixture, amount in (('sim-A1', 'sim-committed', 300),
                                         ('sim-A2', 'sim-committed', 200),
                                         ('sim-A3', 'demo-alpha-hall', 100)):
            for op, args in (
                ('offer', {'fixture_id': fixture, 'amount': amount}), ('approve', {}),
                ('bind_settlement', {}), ('draw', {})):
                receipt = service.execute({'instance_id': service.instance_id, 'operation_id': advance+'-'+op.replace('_', '-'),
                    'advance_id': advance, 'op': op, 'args': args})
                if receipt['outcome'] != 'ACCEPTED':
                    raise ValueError('synthetic vector setup rejected')
        with service.lock:
            frozen = FrozenInputs.capture(service.producer.snapshot_inputs(), service.receipts,
                service.case_fixtures, service.overlay_entries, service.terms, service.overlay_bounds)
        def ref(name):
            return {'claim_id': name, 'trade_id': 'sim-trade-'+name, 'currency': 'KRW'}
        request = {'format': 'CAPITAL_EVENT_STRESS_V1', 'events': [
            {'event_id': 'E1', 'claim_refs': [ref('sim-committed'), ref('sim-refund')]},
            {'event_id': 'E2', 'claim_refs': [ref('sim-committed'), ref('sim-pending')]}],
            'scenarios': [{'scenario_id': 'S1', 'event_id': 'E1', 'kind': 'ADDITIONAL_OPEN_REFUND_KRW',
                           'additional_open_refund_krw': 100},
                          {'scenario_id': 'S2', 'event_id': 'E2', 'kind': 'ADDITIONAL_OPEN_REFUND_KRW',
                           'additional_open_refund_krw': 0}]}
        cases = []
        for name, scenario_request in (('shared-overlap', request), ('above-mapped', copy.deepcopy(request)),
                                       ('unknown-unselected', copy.deepcopy(request))):
            if name == 'above-mapped':
                scenario_request['scenarios'][0]['additional_open_refund_krw'] = 90000
            if name == 'unknown-unselected':
                scenario_request['events'].append({'event_id': 'unused', 'claim_refs': [ref('missing')]})
            cases.append({'case_id': name, 'request': scenario_request,
                          'expected': evaluate_detached(frozen, canonical_bytes(scenario_request))})
        return canonical_bytes({'format': 'KIX_CAPITAL_EVENT_STRESS_VECTORS_V1', 'label': 'SIMULATED',
            'capture_audit': 'NOT_ASSERTED_DETACHED_INPUTS', 'funds_executed': False,
            'inputs': frozen.detached(), 'cases': cases}) + b'\n'
    finally:
        service.observability.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE)
    args = parser.parse_args(argv)
    raw = build_artifact()
    if args.write:
        args.file.write_bytes(raw)
        print(f'event stress vectors written: {len(raw)} bytes')
        return 0
    if not args.file.is_file() or args.file.read_bytes() != raw:
        print('event stress vectors drift', file=sys.stderr)
        return 1
    print('event stress vectors ok: 3 synthetic cases match')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
