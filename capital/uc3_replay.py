"""Disposable synthetic UC3 holds. No storage, clock, provider or execution port.

Policy is loaded exclusively through resources.read_note. The predecessor
partition and its narrower monetary domain are deliberately unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

from capital.resources import ARCHIVE_ROOT, as_resource, note_path, read_note
from capital.shadow import (
    COMPUTED, FALSE_FLAGS, INCONSISTENT, INPUT_UNKNOWN, NOT_BOUND,
    SHADOW_LABEL, SHADOW_MODE, ShadowInconsistent, canonical,
    uc_partition,
)

INPUT_BYTES = 1024 * 1024
VECTOR_PATH = ARCHIVE_ROOT / 'tests' / 'vectors' / 'uc3_replay.json'


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _value(entry):
    _require(type(entry) is dict and entry.get('status') == 'ADOPTED'
             and type(entry.get('value')) is dict, 'entry unavailable or not ADOPTED')
    return entry['value']


def _supports(value, fields):
    # Canonical comparison also distinguishes bool from integer.
    for key, expected in fields.items():
        _require(key in value and canonical(value[key]) == canonical(expected),
                 f'unsupported policy semantics: {key}')


def load_policy(*, hold_path=None, settlement_path=None, shadow_path=None):
    """Load all twelve dependencies, preserving raw and canonical provenance.

    Overrides are exclusive, including missing or malformed overrides. Limits
    and the duration are read from the adopted entries, never fallback terms.
    """
    refs = []
    result = {'status': NOT_BOUND, 'policy_references': refs}
    try:
        blocks = []
        for filename, override, decision_id in (
                ('CAPITAL_UC3_HOLD_CLOCK.md', hold_path, 'uc3-hold-clock-decision'),
                ('CAPITAL_SETTLEMENT_POLICY.md', settlement_path, 'settlement-policy-decision'),
                ('CAPITAL_SHADOW_POLICY.md', shadow_path, 'shadow-policy-decision')):
            note = read_note(note_path(filename) if override is None else as_resource(override),
                             override=override is not None)
            block = note['block']
            refs.append({'note': 'docs/decisions/' + filename,
                         'notes_source': note['notes_source'], 'note_sha256': note['note_sha256'],
                         'block_sha256': digest(block) if block is not None else None,
                         'decision_id': block.get('decision_id') if block else None,
                         'policy_version': block.get('policy_version') if block else None})
            _require(type(block) is dict and block.get('decision_id') == decision_id
                     and block.get('provisional') is True
                     and block.get('status') == 'PROVISIONAL_PRODUCT_DECISION'
                     and type(block.get('entries')) is dict, 'note unavailable or unusable: ' + filename)
            blocks.append(block)
        entries = blocks[0]['entries']
        anchor = _value(entries.get('hold_start_anchor'))
        identity = _value(entries.get('arrival_tranche_identity'))
        boundary = _value(entries.get('eligibility_day_boundary'))
        duplicates = _value(entries.get('duplicate_and_conflicting_inputs'))
        proposal = _value(entries.get('operator_disposition_proposal'))
        limits = _value(entries.get('replay_capacity_bounds'))
        entries = blocks[1]['entries']
        residual = _value(entries.get('residual_and_late_cash'))
        entries = blocks[2]['entries']
        stance = _value(entries.get('shadow_math_stance'))
        ownership = _value(entries.get('shadow_module_ownership'))
        labels = _value(entries.get('shadow_label_vocabulary'))
        rounding = _value(entries.get('rounding_and_tiebreak_rules'))
        deferral = _value(entries.get('revshare_claim_purchase_deferral'))
        _supports(anchor, {'anchor': 'EACH_TRANCHE_ARRIVAL_SIM_DAY',
                          'later_arrivals': 'INDEPENDENT_ANCHOR', 'reset_existing_anchor': False,
                          'duration_authority': 'docs/decisions/CAPITAL_SETTLEMENT_POLICY.md residual_and_late_cash.suspense_period_days (CAPITAL-RESIDUAL-V1)'})
        _supports(identity, {'scope': ['scenario_id', 'claim_id'], 'key': 'tranche_id',
                            'source_identity': 'source_fact_id', 'identity_relation': 'BIJECTION',
                            'currency': 'KRW', 'amount': 'POSITIVE_INTEGER',
                            'provider_identity_adopted': False})
        _supports(boundary, {'clock': 'EXPLICIT_INTEGER_SIM_DAY',
                            'eligible_when': 'as_of_sim_day >= arrival_sim_day + hold_days',
                            'before': 'HELD_INELIGIBLE', 'at_or_after': 'HELD_ELIGIBLE_FOR_PROPOSAL',
                            'automatic_release': False, 'advance_reopen': False})
        _supports(duplicates, {'exact_duplicate': 'COLLAPSE', 'conflict': 'REJECT_ENTIRE_SNAPSHOT',
                              'arrival_order': ['arrival_sim_day', 'tranche_id'],
                              'late_input': 'NEW_DISPOSABLE_SNAPSHOT', 'future_arrival': 'REJECT',
                              'wall_clock': False})
        _supports(proposal, {'trigger': 'EXPLICIT_OPERATOR_REQUEST',
                            'actions': ['CONTINUE_HOLD', 'REVIEW_ELIGIBLE_HELD_CASH'],
                            'scope': 'WHOLE_SELECTED_TRANCHES', 'binding': 'EXACT_SNAPSHOT_DIGEST',
                            'status': 'PROPOSED_ONLY', 'executionAuthorized': False,
                            'cash_effect': 'NONE', 'persist': False})
        _supports(limits, {'claims': 1, 'sim_day_min': 0,
                          'overflow': 'REJECT_ENTIRE_SNAPSHOT', 'eviction': False})
        for key in ('raw_arrival_records', 'unique_arrival_tranches', 'raw_proposal_requests',
                    'sim_day_max', 'max_integer_krw', 'identifier_max_ascii_bytes'):
            _require(type(limits.get(key)) is int and limits[key] > 0, 'invalid capacity: ' + key)
        _require(limits['identifier_max_ascii_bytes'] <= 64
                 and limits['max_integer_krw'] <= 9007199254740991,
                 'unsupported representation bounds')
        days = residual.get('suspense_period_days')
        _require(type(days) is int and 0 < days <= limits['sim_day_max']
                 and type(anchor.get('hold_days')) is int and anchor['hold_days'] == days,
                 'hold duration unavailable or contradictory')
        _supports(residual, {'policy_version': 'CAPITAL-RESIDUAL-V1',
                            'after_suspense': 'operator decision required; unclaimed-funds and deposit law is a review item; simulation retains indefinitely (RETAIN_ALL)',
                            'late_cash_after_capital_close': 'never reopens a CLOSED or DEFAULTED advance; overlay recovery ledger only (CAPITAL-TERMS-V1)'})
        states = residual.get('undistributed_cash_states_ordered')
        _require(type(states) is list and len(states) == 4, 'UC partition policy unavailable')
        _require([s.get('id') for s in states if type(s) is dict] == [
            'UC1_FROZEN_ORDER_CONTINUATION', 'UC2_REFUND_FUNDING_SUSPENSE',
            'UC3_LATE_CASH_AFTER_FULL_RECLASS', 'UC4_OVERPAYMENT'], 'unsupported UC partition')
        _supports(states[1], {'when': 'the claim has refund_outstanding or pg_adjustment_outstanding'})
        _supports(states[2], {'when': 'fixture_reclassified and no refund outstanding',
                             'rule': 'unapplied for the suspense period, then returned to the provider or applied to recovery_due of the same payee only by operator command'})
        _supports(stance, {'prevails': 'POLICY_SIMULATOR_REFUSAL_ON_FSM_PATH'})
        _supports(ownership, {'owner': 'KIX-CAPITAL; not kix-protocol, not kix-commerce-apps',
                              'effects': 'pure function; no workspace write; no FSM command; results placed beside pinned views under separate keys pinned and shadow',
                              'imports': 'stdlib plus the note loader only; never capital/vendor/*, never capital.protocol, never a SettlementMachine or MockSettlement instance'})
        _supports(labels, {'mode': 'SHADOW_NOT_APPLIED on every shadow result',
                           'label': SHADOW_LABEL, 'shadow_status_closed_set': [
                               'SHADOW_COMPUTED', 'SHADOW_DEFERRED', 'SHADOW_NOT_BOUND',
                               'SHADOW_INPUT_UNKNOWN', 'SHADOW_INCONSISTENT'],
                           'constant_false_flags': list(FALSE_FLAGS)})
        _supports(rounding, {'rules_version': 'CAPITAL-SHADOW-V1',
                             'domain': 'non-negative Python int only; no float, no Decimal; inputs <= 1000000000000 (pinned MONEY_MAX); negative or over-bound input -> SHADOW_INCONSISTENT'})
        deferred = deferral.get('residual_and_late_cash')
        _require(type(deferred) is dict, 'partition dependency unavailable')
        _supports(deferred, {
            'next_phase': 'ordered partition of undistributed_cash as a pure function of the pinned view: UC1 = min(undistributed, sum outstanding); UC2 = min(remaining, refund_outstanding); UC3 = remaining when reclassified; UC4 = remaining when confirmed_cash > sum of faces; plus the N-payee largest-remainder primitive',
            'deferred_SHADOW_DEFERRED': ['180-day suspense timer', 'D+1 business-day payout intent batch', 'provider return command']})
        result.update(status=COMPUTED, hold_days=days, limits=dict(limits))
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        result['reason'] = str(exc)
    return result


def _envelope(status, policy, reason=None):
    result = {'schema': 'capital-uc3-replay-v1', 'status': status, 'mode': SHADOW_MODE,
              'label': 'SIMULATED', 'provisional': True, 'shadow_label': SHADOW_LABEL,
              'provenance': 'SHADOW_ARITHMETIC_ONLY',
              'policy_references': policy.get('policy_references', []),
              **{key: False for key in FALSE_FLAGS}}
    if reason is not None:
        result['reason'] = reason
    return result


def _closed(value, fields, name):
    _require(type(value) is dict and set(value) == set(fields.split()), 'invalid fields: ' + name)


def _integer(value, low, high, name):
    _require(type(value) is int and low <= value <= high, 'invalid integer or capacity: ' + name)


def _identifier(value, limits, name):
    _require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) is not None
             and len(value) <= limits['identifier_max_ascii_bytes'], 'invalid identifier: ' + name)


def _normalize(snapshot, policy):
    _closed(snapshot, 'scenario_id claim_id as_of_sim_day classification arrivals proposal_requests', 'snapshot')
    limits = policy['limits']
    for key in ('scenario_id', 'claim_id'):
        _identifier(snapshot[key], limits, key)
    day = snapshot['as_of_sim_day']
    _integer(day, limits['sim_day_min'], limits['sim_day_max'], 'as_of_sim_day')
    c = snapshot['classification']
    _closed(c, 'confirmed_cash undistributed_cash refund_outstanding pg_adjustment_outstanding reclassified obligations', 'classification')
    for key in ('confirmed_cash', 'undistributed_cash', 'refund_outstanding', 'pg_adjustment_outstanding'):
        _integer(c[key], 0, limits['max_integer_krw'], key)
    _require(type(c['reclassified']) is bool, 'reclassified must be bool')
    rows = c['obligations']
    _require(type(rows) is list and bool(rows), 'obligations must be nonempty list')
    for row in rows:
        _closed(row, 'face distributed cancelled_unpaid outstanding', 'obligation')
        for key in ('face', 'distributed', 'cancelled_unpaid', 'outstanding'):
            _integer(row[key], 0, limits['max_integer_krw'], key)
        _require(row['face'] == row['distributed'] + row['cancelled_unpaid'] + row['outstanding'],
                 'obligation does not reconcile')
    partition = uc_partition(c['confirmed_cash'], c['undistributed_cash'],
                             c['refund_outstanding'], c['reclassified'], rows)
    _require(c['reclassified'] is True and c['refund_outstanding'] == 0
             and c['pg_adjustment_outstanding'] == 0 and all(r['outstanding'] == 0 for r in rows)
             and c['confirmed_cash'] <= sum(r['face'] for r in rows)
             and all(partition[k] == 0 for k in ('uc1', 'uc2', 'uc4')), 'outside UC3-only scope')
    arrivals = snapshot['arrivals']
    requests = snapshot['proposal_requests']
    _require(type(arrivals) is list and len(arrivals) <= limits['raw_arrival_records'], 'raw arrival capacity')
    _require(type(requests) is list and len(requests) <= limits['raw_proposal_requests'], 'raw proposal capacity')
    # Validate every record before comparing identity; never choose a winner.
    for a in arrivals:
        _closed(a, 'tranche_id source_fact_id arrival_sim_day amount_krw currency', 'arrival')
        for key in ('tranche_id', 'source_fact_id'):
            _identifier(a[key], limits, key)
        _integer(a['arrival_sim_day'], limits['sim_day_min'], day, 'arrival_sim_day')
        _integer(a['amount_krw'], 1, limits['max_integer_krw'], 'amount_krw')
        _require(a['currency'] == 'KRW', 'currency must be KRW')
        _integer(a['arrival_sim_day'] + policy['hold_days'], limits['sim_day_min'],
                 limits['sim_day_max'], 'eligible_sim_day')
    by_id, sources, conflicts = {}, {}, set()
    for a in arrivals:
        tid, sid = a['tranche_id'], a['source_fact_id']
        if tid in by_id and a != by_id[tid]:
            conflicts.add('tranche_id:' + tid)
        if sid in sources and sources[sid] != tid:
            conflicts.add('source_fact_id:' + sid)
        by_id[tid] = a
        sources[sid] = tid
    _require(not conflicts, 'conflicting identities: ' + ','.join(sorted(conflicts)))
    _require(len(by_id) <= limits['unique_arrival_tranches'], 'unique arrival capacity')
    total = sum(a['amount_krw'] for a in by_id.values())
    _integer(total, 0, limits['max_integer_krw'], 'aggregate held')
    _require(total == c['undistributed_cash'] == partition['uc3'], 'unique arrivals do not reconcile to UC3')
    proposals, conflicts = {}, set()
    for request in requests:
        _closed(request, 'proposal_id operator_label action tranche_ids', 'proposal request')
        for key in ('proposal_id', 'operator_label'):
            _identifier(request[key], limits, key)
        _require(request['action'] in ('CONTINUE_HOLD', 'REVIEW_ELIGIBLE_HELD_CASH'), 'invalid proposal action')
        selection = request['tranche_ids']
        _require(type(selection) is list and bool(selection), 'empty or invalid selection')
        for tid in selection:
            _identifier(tid, limits, 'selected tranche_id')
            _require(tid in by_id, 'unknown selected tranche: ' + tid)
        _require(len(selection) == len(set(selection)), 'duplicate selected tranche')
        if request['action'] == 'REVIEW_ELIGIBLE_HELD_CASH':
            _require(all(day >= by_id[tid]['arrival_sim_day'] + policy['hold_days'] for tid in selection),
                     'premature review request: ' + request['proposal_id'])
        normalized = {**request, 'tranche_ids': sorted(selection)}
        pid = request['proposal_id']
        if pid in proposals and proposals[pid] != normalized:
            conflicts.add(pid)
        proposals[pid] = normalized
    _require(not conflicts, 'conflicting proposal_ids: ' + ','.join(sorted(conflicts)))
    normalized_c = {**c, 'obligations': sorted((dict(r) for r in rows), key=lambda r: tuple(
        r[k] for k in ('face', 'distributed', 'cancelled_unpaid', 'outstanding')))}
    facts = {key: snapshot[key] for key in ('scenario_id', 'claim_id', 'as_of_sim_day')}
    facts.update(classification=normalized_c,
                 arrivals=sorted((dict(a) for a in by_id.values()), key=lambda a: (a['arrival_sim_day'], a['tranche_id'])))
    return facts, [proposals[k] for k in sorted(proposals)]


def evaluate_snapshot(snapshot, *, policy):
    """Validate atomically; successful results keep every synthetic KRW held."""
    if policy.get('status') != COMPUTED:
        return _envelope(NOT_BOUND, policy, policy.get('reason', 'policy unavailable'))
    try:
        facts, requests = _normalize(snapshot, policy)
    except (ValueError, ShadowInconsistent, RecursionError) as exc:
        return _envelope(INCONSISTENT, policy, str(exc))
    refs = policy['policy_references']
    snapshot_digest = digest({**facts, 'policy_references': refs})
    day = facts['as_of_sim_day']
    trace = []
    for a in facts['arrivals']:
        eligible_day = a['arrival_sim_day'] + policy['hold_days']
        eligible = day >= eligible_day
        trace.append({k: a[k] for k in ('tranche_id', 'source_fact_id', 'arrival_sim_day', 'currency')})
        trace[-1].update(shadow_amount_krw=a['amount_krw'], shadow_held_krw=a['amount_krw'],
                         eligible_sim_day=eligible_day,
                         temporal_state='HELD_ELIGIBLE_FOR_PROPOSAL' if eligible else 'HELD_INELIGIBLE',
                         reason='HOLD_ELAPSED_OPERATOR_REQUEST_REQUIRED' if eligible else 'HOLD_PERIOD_NOT_ELAPSED',
                         proposal_references=[r['proposal_id'] for r in requests if a['tranche_id'] in r['tranche_ids']])
    by_id = {t['tranche_id']: t for t in trace}
    proposals = []
    for request in requests:
        selected = [{key: by_id[tid][key] for key in (
            'tranche_id', 'source_fact_id', 'shadow_amount_krw', 'eligible_sim_day')}
                    for tid in request['tranche_ids']]
        proposals.append({**request, 'selected_tranches': selected, 'as_of_sim_day': day,
                          'snapshot_sha256': snapshot_digest, 'policy_references': refs,
                          'status': 'PROPOSED_ONLY', 'label': 'SIMULATED', 'executionAuthorized': False,
                          'shadow_proposed_disposition_krw': sum(t['shadow_amount_krw'] for t in selected)})
    total = sum(t['shadow_held_krw'] for t in trace)
    eligible = sum(t['shadow_held_krw'] for t in trace if t['temporal_state'] == 'HELD_ELIGIBLE_FOR_PROPOSAL')
    result = _envelope(COMPUTED, policy)
    result.update(scenario_id=facts['scenario_id'], claim_id=facts['claim_id'], as_of_sim_day=day,
                  snapshot_sha256=snapshot_digest, trace=trace, proposals=proposals,
                  conservation={'shadow_unique_input_krw': total, 'shadow_held_krw': total,
                                'shadow_eligible_held_krw': eligible, 'shadow_ineligible_held_krw': total - eligible,
                                'shadow_executed_disposition_krw': 0,
                                'input_equals_held_plus_executed': True,
                                'held_equals_eligible_plus_ineligible': True,
                                'proposals_are_independent_alternatives': True})
    return result


def replay(snapshots, *, policy):
    """Fold complete snapshots in memory; refuse and stop at the first bad step."""
    previous = None
    for snapshot in snapshots:
        result = evaluate_snapshot(snapshot, policy=policy)
        if result['status'] == COMPUTED and previous is not None:
            reason = None
            if any(snapshot[k] != previous[k] for k in ('scenario_id', 'claim_id')):
                reason = 'replay identity changed'
            elif snapshot['as_of_sim_day'] < previous['as_of_sim_day']:
                reason = 'backward replay day'
            else:
                current = {a['tranche_id']: a for a in snapshot['arrivals']}
                if any(current.get(a['tranche_id']) != a for a in previous['arrivals']):
                    reason = 'accepted arrival removed or corrected'
            if reason:
                result = _envelope(INCONSISTENT, policy, reason)
        # Capture before yielding: callers may mutate input while suspended.
        if result['status'] == COMPUTED:
            previous = json.loads(canonical(snapshot))
        yield result
        if result['status'] != COMPUTED:
            return


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError('nonstandard JSON constant: ' + value)


def parse_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_bad_constant)


def check_vectors(path=VECTOR_PATH):
    """Read-only golden check. A missing or edited expected artifact fails."""
    with as_resource(path).open('rb') as stream:
        pack = parse_json(_bounded_read(stream))
    _require(type(pack) is dict and pack.get('schema') == 'capital-uc3-vectors-v1'
             and pack.get('label') == 'SIMULATED' and type(pack.get('cases')) is list
             and bool(pack['cases']), 'invalid vector pack')
    policy = load_policy()
    _require(policy['status'] == COMPUTED, 'vector policy unbound')
    names = set()
    for case in pack['cases']:
        _require(type(case) is dict and set(case) == {'id', 'snapshots', 'expected'}
                 and type(case['id']) is str and case['id'] not in names
                 and type(case['snapshots']) is list and bool(case['snapshots']), 'invalid vector case')
        names.add(case['id'])
        _require(canonical(list(replay(case['snapshots'], policy=policy))) == canonical(case['expected']),
                 'vector drift: ' + case['id'])
    return len(names)


def _bounded_read(stream):
    raw = stream.read(INPUT_BYTES + 1)
    _require(len(raw) <= INPUT_BYTES, 'input exceeds 1 MiB')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--snapshot', metavar='PATH|-')
    mode.add_argument('--replay', metavar='PATH|-')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.check:
            count = check_vectors()
            checked = _envelope(COMPUTED, {})
            checked.update(vector_check='MATCH', cases=count)
            print(canonical(checked))
            return 0
        path = args.snapshot if args.snapshot is not None else args.replay
        if path == '-':
            raw = _bounded_read(sys.stdin.buffer)
        else:
            with open(path, 'rb') as stream:
                raw = _bounded_read(stream)
        text = raw.decode('utf-8')
        # Parse the entire bounded invocation first, so malformed trailing JSON
        # cannot produce a partial financial projection.
        snapshots = [parse_json(text)] if args.snapshot is not None else [parse_json(line) for line in text.splitlines()]
        _require(bool(snapshots), 'empty replay')
        code = 0
        for result in replay(snapshots, policy=load_policy()):
            print(canonical(result))
            if result['status'] != COMPUTED:
                code = 1
        return code
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(canonical(_envelope(INPUT_UNKNOWN, {}, str(exc))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
