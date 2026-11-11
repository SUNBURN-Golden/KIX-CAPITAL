#!/usr/bin/env python3
"""SIMULATED disposable demo-book recorded provider-capture facts. No provider call or real cash."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import observation, overlay
from capital.observation_record import CHECK_ID, OP, project_fake
from capital.service import ApiError, CapitalService
from capital.verify import verify_manifest
from tests.test_overlay import draw_book, tick

GOLDEN = ROOT / 'tests/golden/overlay_observations.json'
CLAIM = 'sim-committed'

# Synthetic fixture fact, same family as tests/vectors/provider_facts.json base_fact.
BASE_FACT = {
    'provenance': 'SYNTHETIC_FIXTURE', 'provider': 'sim-provider', 'account': 'sim-mid',
    'environment': 'fixture', 'profile_version': 'sim-v1', 'item_key': 'sim-capture-1',
    'payment_key': 'sim-payment', 'order_id': 'sim-order', 'operation': 'sim-operation',
    'kind': 'capture', 'amount': 0, 'currency': 'KRW', 'method': 'sim-card',
    'status': 'DONE', 'occurred_at': '2026-10-01T12:00:00', 'offset': None,
    'api_version': 'sim-api-v1', 'product': 'sim-product',
    'transmission': {'id': 'sim-delivery-1', 'raw_evidence_ref': 'sim-raw-1',
                     'received_at': 'sim-receive-1'},
}
BINDING = {'provider': 'sim-provider', 'account': 'sim-mid', 'environment': 'fixture',
           'profile_version': 'sim-v1', 'operation': 'sim-operation',
           'payment_key': 'sim-payment', 'order_id': 'sim-order'}


def capture_fact(amount, item_key, delivery):
    fact = copy.deepcopy(BASE_FACT)
    fact['amount'] = amount
    fact['item_key'] = item_key
    fact['transmission'] = dict(fact['transmission'], id=delivery)
    return fact


def project(service, facts, sim_day):
    """Project the complete fake fold into record commands, or fail loudly."""
    output = observation.LocalFakeObservation().fold(facts, bindings=[BINDING])
    projected = project_fake(output, claim_id=CLAIM, sim_day=sim_day,
                             captured_sim_day=sim_day, instance_id=service.instance_id)
    if projected['diagnostics'] or not projected['commands']:
        raise AssertionError(f'unexpected projection: {projected}')
    return projected['commands']


def record(service, command):
    return service.overlay_command(command)


def check(service):
    return next(c for c in service.reconciliation()['checks'] if c['id'] == CHECK_ID)


def build(storage=None):
    service = CapitalService(storage)
    draw_book(service)
    tick(service, 'observe-tick', 0, 7)
    gross = service.fixtures.view(CLAIM)['claim']['gross']
    matched = project(service, [capture_fact(gross, 'sim-capture-1', 'sim-delivery-1')], 7)
    first = record(service, matched[0])
    before = check(service)
    assert before['status'] == 'MATCH' and not before['diagnostics'], before
    corrected = project(service, [capture_fact(gross - 10000, 'sim-capture-2', 'sim-delivery-2')], 7)
    corrected[0]['payload']['supersedes_fact_id'] = first['operation_id']
    second = record(service, corrected[0])
    after = check(service)
    assert after['status'] == 'ASSERTED_MISMATCH', after
    assert after['diagnostics'] == ['OBSERVED_FACT_MISMATCH'], after
    state = overlay.fold(service.overlay_entries)
    observations = state['observations']
    assert observations[first['operation_id']]['status'] == 'SUPERSEDED'
    assert observations[second['operation_id']]['status'] == 'ACTIVE'
    manifest = service.export_manifest()
    assert verify_manifest(manifest)['ok']
    result = {
        'label': 'SIMULATED_DISPOSABLE_BOOK', 'application': 'SHADOW_NOT_APPLIED',
        'provisional': True, 'claim_id': CLAIM, 'sim_day': state['sim_day'],
        'entry_count': len(service.overlay_entries),
        'fact_ids': [first['operation_id'], second['operation_id']],
        'observations': copy.deepcopy(observations),
        'match_check': before, 'mismatch_check': after,
        'overlay_digest': overlay.state_digest(state),
        'overlay_schema': overlay.SCHEMA,
        'f04_digest': service.machine.state_digest(),
        'manifest_verified': True,
        'overlay_fold_check': next(
            c['status'] for c in service.reconciliation()['checks']
            if c['id'] == 'overlay_fold_digest_equals_persisted'),
        'funds_executed': False, 'provider_call_made': False,
        'verification': 'UNVERIFIED_ASSERTED',
    }
    assert result['overlay_fold_check'] == 'MATCHED'
    return service, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    _, result = build()
    if args.write:
        GOLDEN.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    elif json.loads(GOLDEN.read_text()) != result:
        print('overlay observations golden mismatch', file=sys.stderr)
        return 1
    print('overlay observations ok SIMULATED entries=' + str(result['entry_count']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
