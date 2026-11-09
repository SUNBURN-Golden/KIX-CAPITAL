"""SIMULATED disposable recovery book. Test-only loopback server; no new routes."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from capital.margin import ScenarioReplaySource
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from seed_overlay_recovery import command, distribute, tick


def build_server(port, scenario):
    source = ScenarioReplaySource()
    server = make_server(port, producer=PinnedFsmProducer(fixtures=source))
    service = server.service
    high = scenario == 'high'
    fixture = 'demo-alpha-arena' if high else 'sim-committed'
    for op, args in [('offer', {'fixture_id': fixture, 'amount': 150000000 if high else 90000}),
                     ('approve', {}), ('bind_settlement', {}), ('draw', {})]:
        assert command(service, op, 'seed-' + op.replace('_', '-'), **args)['outcome'] == 'ACCEPTED'
    if scenario != 'unanchored':
        tick(service, 'seed-day10', 0, 10)
    result = service.execute({'instance_id': service.instance_id, 'operation_id': 'seed-default',
                              'op': 'default', 'advance_id': 'sim-recovery', 'args': {},
                              'approvals': [{'approver_label': 'sim-seed-a'}, {'approver_label': 'sim-seed-b'}]})
    assert result['outcome'] == 'ACCEPTED', result
    if scenario == 'unanchored':
        # Historical defaults predating overlay activation have no day anchor.
        tick(service, 'seed-day10', 0, 10)
    if scenario != 'no-sources':
        distribute(source, fixture)
        distribute(source, 'sim-pending')
    if scenario in ('high', 'eligible', 'unavailable', 'policy-race'):
        tick(service, 'seed-day100', 10, 100)
    if scenario == 'unavailable':
        service.recovery_policy = None
    if scenario == 'policy-race':
        original = service.overlay_command

        def policy_race(body, **kwargs):
            if body.get('op') in ('post_recovery', 'post_writeoff'):
                service.recovery_policy = None
            return original(body, **kwargs)

        service.overlay_command = policy_race
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--scenario', choices=['normal', 'eligible', 'high', 'unavailable', 'policy-race',
                                             'unanchored', 'no-sources'], default='normal')
    args = parser.parse_args()
    server = build_server(args.port, args.scenario)
    try:
        server.serve_forever()
    finally:
        server.server_close()
