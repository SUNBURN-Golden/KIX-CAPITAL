#!/usr/bin/env python3
"""SIMULATED disposable demo-book claim slices. No server, title or real cash."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import margin, overlay, slices
from capital.producer import PinnedFsmProducer
from capital.service import ApiError, CapitalService
from capital.verify import verify_manifest

GOLDEN = ROOT / 'tests/golden/overlay_claim_slices.json'
APPROVALS = [{'approver_label': 'sim-human-a'}, {'approver_label': 'sim-human-b'}]


def book(storage=None):
    source = margin.ScenarioReplaySource()
    return source, CapitalService(storage, producer=PinnedFsmProducer(source))


def post(service, op, key, **kw):
    return service.overlay_command({'instance_id': service.instance_id, 'operation_id': key, 'op': op,
                                    'at_sim_day': overlay.fold(service.overlay_entries)['sim_day'],
                                    'approvals': APPROVALS, **kw})


def register(service, key, face, claim='demo-delta-small', payee='organizer', **kw):
    q = service.overlay_slices(claim, payee, 60)['quote']
    return post(service, 'register_slice', key, claim_id=claim, payee_label=payee, slice_face_krw=face,
                holder_role='KIX_CAPITAL_LENDER', expected_days=60, quote_ref=q['result_digest'], **kw)


def open_slice(service, sid, key=None, **kw):
    return post(service, 'open_slice', key or sid + '-open', slice_id=sid,
                expected_after_journal_index=len(service.machine.export_journal()), **kw)


def replay(source, claim, name, op, **args):
    result = source.replay(claim, name, steps=[{'op': op, 'args': args, 'expected_error': None}])
    assert all(r['matched'] for r in result), result
    return result


def distribute(source, claim):
    view = source.view(claim)
    if view['phase'] == 'CAPTURED':
        gross = view['claim']['gross']
        replay(source, claim, 'slice-source-commit', 'commit_settlement', movement_id='sim-source-movement',
               gross=gross, amount=gross, fee=0, tax=0, held=0, adjustment=0)
    replay(source, claim, 'slice-source-distribution', 'apply_distribution', order=['platform', 'organizer'])


def refund(source, claim, amount):
    return replay(source, claim, 'slice-refund', 'bind_refund', refund_id='sim-slice-refund',
                  amount=amount, beneficiary_role='demo-buyer', reason='SIMULATED_REFUND')


def build():
    source, service = book()
    claim = 'demo-delta-mid'
    gross = source.view(claim)['claim']['gross']
    # Synthetic held settlement observation, not a new product fee/term.
    cash = service.slice_policy['threshold'] // 5
    replay(source, claim, 'slice-low-cash', 'commit_settlement', movement_id='sim-held-statement',
           gross=gross, amount=cash, fee=0, tax=0, held=gross-cash, adjustment=0)
    face = cash * 2
    register(service, 'journey-slice', face, claim)
    open_slice(service, 'journey-slice')
    before = overlay.state_digest(overlay.fold(service.overlay_entries))
    try:
        register(service, 'journey-double', face, claim)
        raise AssertionError('double use accepted')
    except ApiError as exc:
        assert exc.code == 'SLICE_OPEN_EXISTS', exc.code
        refusal = exc.code
    assert before == overlay.state_digest(overlay.fold(service.overlay_entries))
    replay(source, claim, 'slice-holder-distribution', 'apply_distribution', order=['organizer', 'platform'])
    served = service.overlay_slices()['slices'][0]['served_krw']
    assert 0 < served < face
    line = next(l for l in source.view(claim)['claim']['obligations'] if l['payee'] == 'organizer')
    refund(source, claim, line['outstanding'])
    impair = post(service, 'impair_slice', 'journey-impair', slice_id='journey-slice', reason='REFUND_REDUCED_LINE')
    distribute(source, 'demo-delta-small')
    row = service.overlay_slices()['slices'][0]
    q = next(q for q in row['quotes'] if q['source_ref']['claim_id'] == 'demo-delta-small')
    post(service, 'post_slice_recourse', 'journey-recourse', slice_id='journey-slice',
         source_ref=q['source_ref'], quote_ref=q['quote_ref'], amount_krw=row['outstanding_krw'])
    post(service, 'resolve_slice', 'journey-resolve', slice_id='journey-slice', resolution='RECOURSE_SATISFIED')
    manifest = service.export_manifest()
    assert verify_manifest(manifest)['ok']
    result = {'label': 'SIMULATED_DISPOSABLE_BOOK', 'application': 'SHADOW_NOT_APPLIED', 'provisional': True,
              'double_use_refusal': refusal, 'holder_first': True, 'served_krw': served,
              'shortfall_krw': impair['entry']['shortfall_krw'],
              'slices': service.overlay_slices()['slices'], 'entry_count': len(service.overlay_entries),
              'overlay_digest': overlay.state_digest(overlay.fold(service.overlay_entries)),
              'f04_digest': service.machine.state_digest(), 'manifest_verified': True,
              'overlay_fold_check': next(c['status'] for c in service.reconciliation()['checks'] if c['id'] == 'overlay_fold_digest_equals_persisted'),
              **slices.labels()}
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
        print('claim slices golden mismatch', file=sys.stderr)
        return 1
    print('overlay claim slices ok SIMULATED entries=' + str(result['entry_count']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
