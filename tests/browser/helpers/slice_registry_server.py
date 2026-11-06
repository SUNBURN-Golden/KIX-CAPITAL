#!/usr/bin/env python3
"""Loopback SIMULATED disposable registry; no persisted book or external calls."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from capital.margin import ScenarioReplaySource
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from capital.shadow import DecisionNoteShadow
from scripts.seed_overlay_slices import distribute, open_slice, post, refund, register, replay


def seed(source, service):
    # Existing helper commands/notes alone determine admission and prices.
    face = service.slice_policy['threshold'] // 5
    for op, args in [('offer', {'fixture_id': 'demo-alpha-arena', 'amount': 100}),
                     ('approve', {}), ('bind_settlement', {}), ('draw', {})]:
        result = service.execute({'instance_id': service.instance_id, 'operation_id': 'desk-' + op.replace('_', '-'),
                                  'op': op, 'advance_id': 'sim-desk-linked-advance', 'args': args})
        assert result['outcome'] == 'ACCEPTED', result
    def partial_impair(claim, sid):
        gross = source.view(claim)['claim']['gross']
        replay(source, claim, sid + '-held', 'commit_settlement', movement_id=sid + '-movement',
               gross=gross, amount=face, fee=0, tax=0, held=gross-face, adjustment=0)
        register(service, sid, face * 2, claim)
        open_slice(service, sid)
        replay(source, claim, sid + '-distribution', 'apply_distribution', order=['organizer', 'platform'])
        line = next(row for row in source.view(claim)['claim']['obligations'] if row['payee'] == 'organizer')
        refund(source, claim, line['outstanding'])
        post(service, 'impair_slice', sid + '-impair', slice_id=sid, reason='REFUND_REDUCED_LINE')

    # Resolve before adding the other states: keep sealed recourse witnesses within
    # the existing entry-size bound, without changing the policy or capacity.
    partial_impair('demo-delta-mid', 'desk-resolved')
    distribute(source, 'demo-delta-small')
    row = next(row for row in service.overlay_slices()['slices'] if row['slice_id'] == 'desk-resolved')
    quote = next(q for q in row['quotes'] if q['source_ref']['claim_id'] == 'demo-delta-small')
    post(service, 'post_slice_recourse', 'desk-recourse', slice_id=row['slice_id'], source_ref=quote['source_ref'],
         quote_ref=quote['quote_ref'], amount_krw=row['outstanding_krw'])
    post(service, 'resolve_slice', 'desk-resolve', slice_id=row['slice_id'], resolution='RECOURSE_SATISFIED')
    # A different same-beneficiary source supplies inspectable recourse evidence.
    distribute(source, 'demo-beta-festival')
    partial_impair('demo-beta-club', 'desk-impaired')
    register(service, 'desk-open', face, 'demo-alpha-arena')
    open_slice(service, 'desk-open')
    register(service, 'desk-proposed', face, 'demo-gamma-annex')
    register(service, 'desk-void', face, 'demo-epsilon-clean')
    post(service, 'void_slice', 'desk-void-end', slice_id='desk-void', reason='OPERATOR_WITHDRAWN')

    assert {row['status'] for row in service.overlay_slices()['slices']} == {'PROPOSED', 'OPEN', 'IMPAIRED', 'RESOLVED', 'VOID'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8951)
    parser.add_argument('--empty', action='store_true')
    parser.add_argument('--shadow-not-bound', action='store_true')
    args = parser.parse_args()
    source = ScenarioReplaySource()
    with make_server(args.port, producer=PinnedFsmProducer(source)) as server:
        if not args.empty:
            seed(source, server.service)
        if args.shadow_not_bound:
            # Fault setup uses the real missing-note evaluator, not invented fields.
            server.service.shadow = DecisionNoteShadow(ROOT / 'tests' / '__SIMULATED_missing_shadow_note__.md')
        print('SIMULATED_DISPOSABLE_BOOK loopback ready', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
