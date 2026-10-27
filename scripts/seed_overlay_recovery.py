#!/usr/bin/env python3
"""Deterministic SIMULATED_DISPOSABLE_BOOK recovery journey; no server or real cash."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import margin, overlay
from capital.producer import PinnedFsmProducer
from capital.service import CapitalService
from capital.verify import verify_manifest

GOLDEN = ROOT / 'tests/golden/overlay_recovery.json'


def command(service, op, key, **args):
    return service.execute({'instance_id': service.instance_id, 'operation_id': key, 'op': op,
                            'advance_id': 'sim-recovery', 'args': args})


def tick(service, key, start, end, **extra):
    return service.overlay_command({'instance_id': service.instance_id, 'operation_id': key, 'op': 'advance_day',
                                    'from_sim_day': start, 'to_sim_day': end, 'reason': 'SIMULATED recovery journey', **extra})


def distribute(source, fixture):
    claim = source.view(fixture)['claim']
    steps = []
    if claim['confirmed_cash'] == 0:
        steps.append({'op': 'commit_settlement' if source.view(fixture)['phase'] == 'CAPTURED' else 'observe_settlement_statement', 'args': {
            'movement_id': 'sim-recovery-statement', 'amount': claim['gross'], 'gross': claim['gross'], 'fee': 0, 'tax': 0, 'held': 0, 'adjustment': 0}, 'expected_error': None})
    steps.append({'op': 'apply_distribution', 'args': {'order': ['platform', 'organizer']}, 'expected_error': None})
    outcomes = source.replay(fixture, 'recovery-distribution', steps=steps)
    assert all(x['matched'] for x in outcomes), outcomes
    return outcomes


def post(service, key, amount, *, advance='sim-recovery', source_claim='sim-pending'):
    state = service.overlay_state()
    row = next(x for x in state['recovery']['advances'] if x['advance_id'] == advance)
    quote = next(q for q in row['quotes'] if q['source_ref']['claim_id'] == source_claim)
    return service.overlay_command({'instance_id': service.instance_id, 'operation_id': key, 'op': 'post_recovery',
                                    'advance_ref': advance, 'at_sim_day': state['sim_day'], 'amount_krw': amount,
                                    'source_ref': quote['source_ref'], 'quote_ref': quote['quote_ref']})


def build():
    source = margin.ScenarioReplaySource()
    service = CapitalService(producer=PinnedFsmProducer(fixtures=source))
    for op, args in [('offer', {'fixture_id': 'sim-committed', 'amount': 48000}), ('approve', {}), ('bind_settlement', {}), ('draw', {})]:
        assert command(service, op, 'recovery-' + op.replace('_', '-'), **args)['outcome'] == 'ACCEPTED'
    assert all(x['matched'] for x in source.replay('sim-committed', 'partial-before'))
    tick(service, 'call', 0, 3)
    deadline = service.overlay_state()['advances'][0]['margin']['cure_deadline']
    tick(service, 'accelerate', 3, deadline + 1)
    eligible = service.overlay_state()['advances'][0]['interest_rebase']['default_eligible_sim_day']
    tick(service, 'eligible', deadline + 1, eligible)
    proposal = service.overlay_state()['margin']
    assert proposal['proposal_only'] and not proposal['f04_default_called']
    assert command(service, 'default', 'recovery-default')['outcome'] == 'ACCEPTED'
    f04 = service.machine.state_digest()
    distribute(source, 'sim-pending')
    first = post(service, 'recovery-first', 5000)
    stop = service.overlay_state()['recovery']['advances'][0]['writeoff_sim_day']
    tick(service, 'stop-interest', eligible, stop)
    assert not service.overlay_state()['recovery']['entries'][-1]['entry_kind'] == 'WRITEOFF'
    # A bare tick did not write off; the explicit directive below is atomic with the next tick.
    tick(service, 'writeoff-tick', stop, stop + 1, writeoff={
        'operation_id': 'recovery-writeoff', 'advance_ref': 'sim-recovery', 'at_sim_day': stop + 1,
        'setoff_declined_reason': 'SIMULATED_OPERATOR_DECLINES_REMAINING_SETOFF'})
    late = post(service, 'recovery-late', 1000)
    tick(service, 'no-more-interest', stop + 1, stop + 5)
    assert service.machine.state_digest() == f04
    assert command(service, 'repay', 'terminal-repay', amount=1, sequence=1)['error'] == 'TERMINAL_IMMUTABLE'
    result = service.overlay_state()
    manifest = service.export_manifest()
    assert verify_manifest(manifest)['ok']
    assert next(c for c in service.reconciliation()['checks'] if c['id'] == 'overlay_fold_digest_equals_persisted')['status'] == 'MATCHED'
    state = overlay.fold(service.overlay_entries)
    return service, {'label': 'SIMULATED_DISPOSABLE_BOOK', 'policy_version': 'DEFAULT_RECOVERY_V1',
                     'first_allocation': first['entry']['allocation'],
                     'late_residual_claim_krw': late['entry']['residual_claim_krw'],
                     'recovery': result['recovery'], 'f04_digest': service.machine.state_digest(),
                     'overlay_digest': overlay.state_digest(state), 'entry_count': len(service.overlay_entries),
                     'reconciliation': service.reconciliation()['status'],
                     'reconciliation_limit': 'DISPOSABLE_SETTLEMENT_CHANGED_SINCE_OFFER',
                     'overlay_fold_check': 'MATCHED', 'manifest_verified': True,
                     'fsm_phase': service.machine.view('sim-recovery')['phase'], 'funds_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-golden', action='store_true')
    args = parser.parse_args()
    _, result = build()
    if args.update_golden:
        GOLDEN.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    elif json.loads(GOLDEN.read_text()) != result:
        print('recovery golden mismatch', file=sys.stderr)
        return 1
    print('overlay recovery ok SIMULATED_DISPOSABLE_BOOK entries=' + str(result['entry_count']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
