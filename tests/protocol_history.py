"""Test projection of the frozen pre-8ba7f6c T05 evidence."""
import copy
import hashlib
import json

from capital.margin import ScenarioReplaySource


def replay_t05_prefix(history):
    source = ScenarioReplaySource()
    for event in history['source_replay']:
        assert event['scenario_id'] == 'partial-before'
        outcomes = source.replay_refund_before_distribution(event['fixture_id'])
        assert len(outcomes) == 2 and all(row['matched'] for row in outcomes)
    return source


def legacy_settlement_views(source):
    rows = copy.deepcopy(source.rows)
    for row in rows.values():
        claim = row['claim']
        if claim and claim['refund_bearer_policy'] == 'REQUESTER':
            assert claim['distribution_blocked'] is False
            claim.update(refund_bearer_policy='UNDEFINED', distribution_blocked=True)
    return rows


def legacy_f04_digest(machine):
    state = json.loads(machine.canonical_state())
    for case in state['cases']:
        del case['open_terms']
    raw = json.dumps(state, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()
