"""Executable CLAIM_CONFORMANCE checks for the simulated agent lane.

Each row in tests/agent_claims.json cites the pinned
AI_DELEGATION_AUTHORITY.md draft 0.1 (kix-protocol main
e2a029d8ac3af7575888dac22fc4bf173ebec232), names one check, and stores the
value that check must observe. Checks run over the in-process loopback
facade (CapitalService agent_query / agent_propose / agent_execute /
execute). The comparison is local and simulated. It does not vendor
reference/ai_delegation/ai_delegation_mock.py, it is not an ActionPermit,
and it does not move funds.

A protocol checkout is optional. The drift script reads that tree and does
not write it. With no checkout the drift status is SKIPPED.
"""
from __future__ import annotations

from pathlib import Path

from capital import upstream_claims
from capital.agent_lane import (
    ACTIVE_GENERATION,
    ACTIVE_GRANT_ID,
    FALSE_FLAGS,
    PERIOD_NOT_AFTER,
    PERIOD_NOT_BEFORE,
    REVOKED_GENERATION,
    REVOKED_GRANT_ID,
    AgentLane,
    AgentLaneError,
)
from capital.resources import ROOT, VENDOR
from capital.terms import DecisionNoteTermsPolicy
from capital.upstream_claims import ClaimTableError

PINNED_SHA = 'e2a029d8ac3af7575888dac22fc4bf173ebec232'
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_AGENT_CLAIMS_V1'
REQUIRED_FIELDS = upstream_claims.REQUIRED_FIELDS
SOURCE_DOC = 'docs/contracts/AI_DELEGATION_AUTHORITY.md'


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'agent_claims.json'


def load_table(path=None):
    return upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def validate_table(data):
    return upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def run_claims(table):
    """Run every check. An unmapped check fails that claim and no other."""
    return upstream_claims.run_claims(
        table, checks=CHECKS, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def check_protocol(protocol_dir, table=None):
    """Read cited headings and needles. Never writes the checkout."""
    if table is None:
        table = load_table()
    return upstream_claims.check_protocol(
        protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def _service():
    from capital.service import CapitalService
    return CapitalService()


def _api_error(call):
    from capital.service import ApiError
    try:
        call()
    except ApiError as exc:
        return {'code': exc.code, 'status': exc.status}
    return None


def _lane_error(call):
    try:
        call()
    except AgentLaneError as exc:
        return exc.code
    return None


def _call(grant_id=ACTIVE_GRANT_ID, generation=ACTIVE_GENERATION, now=10, **extra):
    body = {'grant_id': grant_id, 'generation': generation, 'now': now}
    body.update(extra)
    return body


def _propose(proposal_id='sim-claim-proposal', surface='capital:draw',
             amount=100, kind='PROPOSE', **extra):
    body = _call(proposal_id=proposal_id, surface=surface, amount=amount, kind=kind)
    body.update(extra)
    return body


def _query(service=None, **extra):
    service = _service() if service is None else service
    return service.agent_query(_call(**extra), role='agent')


def _propose_view(service=None, **extra):
    service = _service() if service is None else service
    return service.agent_propose(_propose(**extra), role='agent')


def _agent_flag(name):
    def check():
        return _query()[name]
    return check


def check_agent_query_grant_id():
    return _query()['grant']['grant_id']


def check_agent_query_generation():
    return _query()['grant']['generation']


def check_agent_query_phase():
    return _query()['grant']['phase']


def check_agent_query_authority():
    return _query()['grant']['authority']


def check_agent_query_agent_id():
    return _query()['grant']['agent_id']


def check_agent_query_issuer():
    return _query()['grant']['issuer']


def check_agent_query_issuer_kind():
    return _query()['grant']['issuer_kind']


def check_agent_query_scope():
    return _query()['grant']['scope']


def check_agent_query_ai_role():
    return _query()['grant']['ai_role']


def check_agent_query_limits():
    return _query()['grant']['limits']


def check_agent_query_currency():
    return _query()['grant']['limits']['currency']


def check_agent_query_count_meaning():
    return _query()['grant']['limits']['count_max_meaning']


def check_agent_query_period():
    return _query()['grant']['period']


def check_agent_query_provenance():
    return _query()['provenance']


def check_agent_query_lifecycle():
    return _query()['lifecycle_authority']


def check_agent_query_identity():
    return _query()['identity']


def check_agent_query_action_permit():
    return _query()['action_permit']


def check_agent_query_idp():
    return _query()['idp']


def check_agent_query_kyc():
    return _query()['kyc']


def check_agent_query_upstream_receipt():
    return _query()['upstream_receipt']


def check_agent_query_workspace_mutated():
    return _query()['workspace_mutated']


def check_agent_query_duplicate():
    return _query()['duplicate']


def check_agent_query_no_receipt():
    service = _service()
    service.agent_query(_call(), role='agent')
    return len(service.receipts)


def check_agent_query_not_bound():
    lane = AgentLane(DecisionNoteTermsPolicy(Path(str(ROOT)).resolve().parent / 'docs' / 'missing-terms-note.md'))
    return _lane_error(lambda: lane.query_grant(_call()))


def check_agent_propose_phase():
    return _propose_view()['proposal']['phase']


def check_agent_propose_effects_executed():
    return _propose_view()['proposal']['effects_executed']


def check_agent_propose_decision():
    return _propose_view()['proposal']['decision']


def check_agent_propose_stored():
    service = _service()
    service.agent_propose(_propose(proposal_id='sim-claim-stored'), role='agent')
    row = service.agent_lane.proposals['sim-claim-stored']
    return {'phase': row['phase'], 'effects_executed': row['effects_executed']}


def check_agent_propose_duplicate():
    service = _service()
    service.agent_propose(_propose(proposal_id='sim-claim-dup'), role='agent')
    again = service.agent_propose(_propose(proposal_id='sim-claim-dup'), role='agent')
    return again['duplicate']


def check_agent_propose_binding_conflict():
    service = _service()
    service.agent_propose(_propose(proposal_id='sim-claim-conflict', amount=100), role='agent')
    return _api_error(lambda: service.agent_propose(
        _propose(proposal_id='sim-claim-conflict', amount=101), role='agent'))


def check_agent_propose_two_person():
    service = _service()
    limit = service.agent_lane.limits()['per_action_max']
    view = service.agent_propose(_propose(amount=limit), role='agent')
    return view['proposal']['two_person_required']


def check_agent_propose_scope_violation():
    return _api_error(lambda: _propose_view(surface='capital:not-a-surface'))


def check_agent_propose_invalid_amount():
    return _api_error(lambda: _propose_view(amount=0))


def check_agent_propose_per_action():
    service = _service()
    limit = service.agent_lane.limits()['per_action_max']
    return _api_error(lambda: service.agent_propose(
        _propose(amount=limit + 1), role='agent'))


def check_agent_propose_cumulative():
    service = _service()
    limits = service.agent_lane.limits()
    per_action = limits['per_action_max']
    cumulative = limits['cumulative_max']
    charged = 0
    index = 0
    while charged + per_action <= cumulative:
        service.agent_propose(
            _propose(proposal_id=f'sim-claim-cum-{index}', amount=per_action),
            role='agent')
        charged += per_action
        index += 1
    over = cumulative - charged + 1
    return _api_error(lambda: service.agent_propose(
        _propose(proposal_id='sim-claim-cum-over', amount=over), role='agent'))


def check_agent_propose_execute_kind():
    return _api_error(lambda: _propose_view(kind='EXECUTE'))


def check_agent_propose_tool_not_allowed():
    service = _service()
    lane = service.agent_lane
    real = lane._grants

    def narrowed():
        grants = real()
        grants[ACTIVE_GRANT_ID]['authority'] = ['QUERY']
        return grants

    lane._grants = narrowed
    try:
        return _api_error(lambda: service.agent_propose(_propose(), role='agent'))
    finally:
        lane._grants = real


def check_agent_execute_refused():
    service = _service()
    return _api_error(lambda: service.agent_execute({'kind': 'EXECUTE'}, role='agent'))


def check_agent_execute_no_write():
    service = _service()
    _api_error(lambda: service.agent_execute({'kind': 'EXECUTE'}, role='agent'))
    return len(service.agent_lane.proposals)


def check_agent_period_not_before():
    return _query(now=PERIOD_NOT_BEFORE)['grant']['phase']


def check_agent_period_not_after():
    return _query(now=PERIOD_NOT_AFTER)['grant']['phase']


def check_agent_period_before():
    return _api_error(lambda: _query(now=PERIOD_NOT_BEFORE - 1))


def check_agent_period_after():
    return _api_error(lambda: _query(now=PERIOD_NOT_AFTER + 1))


def check_agent_period_stale():
    return _api_error(lambda: _query(generation=ACTIVE_GENERATION - 1))


def check_agent_period_revoked():
    return _api_error(lambda: _query(
        grant_id=REVOKED_GRANT_ID, generation=REVOKED_GENERATION))


def check_agent_period_unknown():
    return _api_error(lambda: _query(grant_id='sim-grant-missing'))


def check_agent_period_invalid():
    return _api_error(lambda: _query(now=-1))


def _cite_setup():
    """A pending agent memo, then an organizer command that cites it."""
    service = _service()
    service.agent_propose(
        _propose(proposal_id='sim-claim-cite', surface='capital:offer', amount=100),
        role='agent')
    body = {
        'instance_id': service.instance_id,
        'operation_id': 'sim-claim-cite-op',
        'op': 'offer',
        'advance_id': 'sim-claim-cite',
        'args': {'fixture_id': 'sim-committed', 'amount': 100},
        'proposal_id': 'sim-claim-cite',
    }
    return service, service.execute(body)


def check_agent_cite_stamped():
    _service_obj, receipt = _cite_setup()
    return receipt['proposal_id']


def check_agent_cite_outcome():
    _service_obj, receipt = _cite_setup()
    return receipt['outcome']


def check_agent_cite_role():
    _service_obj, receipt = _cite_setup()
    return receipt['role']


def check_agent_cite_pending():
    service, _receipt = _cite_setup()
    row = service.agent_lane.proposals['sim-claim-cite']
    return {'phase': row['phase'], 'effects_executed': row['effects_executed']}


def check_agent_cite_unknown():
    service = _service()
    body = {
        'instance_id': service.instance_id,
        'operation_id': 'sim-claim-cite-unknown',
        'op': 'offer',
        'advance_id': 'sim-claim-cite-missing',
        'args': {'fixture_id': 'sim-committed', 'amount': 100},
        'proposal_id': 'sim-claim-not-stored',
    }
    return _api_error(lambda: service.execute(body))


def check_agent_cite_mismatch():
    service = _service()
    service.agent_propose(
        _propose(proposal_id='sim-claim-mismatch', surface='capital:offer', amount=100),
        role='agent')
    body = {
        'instance_id': service.instance_id,
        'operation_id': 'sim-claim-cite-mismatch',
        'op': 'offer',
        'advance_id': 'sim-claim-cite-mismatch',
        'args': {'fixture_id': 'sim-committed', 'amount': 99},
        'proposal_id': 'sim-claim-mismatch',
    }
    return _api_error(lambda: service.execute(body))


def check_agent_mock_not_vendored():
    names = {path.name for path in Path(str(VENDOR)).rglob('*') if path.is_file()}
    return 'ai_delegation_mock.py' in names


CHECKS = {}
for _name in FALSE_FLAGS:
    CHECKS['agent.flag.' + _name] = _agent_flag(_name)

CHECKS.update({
    'agent.query.grant_id': check_agent_query_grant_id,
    'agent.query.generation': check_agent_query_generation,
    'agent.query.phase': check_agent_query_phase,
    'agent.query.authority': check_agent_query_authority,
    'agent.query.agent_id': check_agent_query_agent_id,
    'agent.query.issuer': check_agent_query_issuer,
    'agent.query.issuer_kind': check_agent_query_issuer_kind,
    'agent.query.scope': check_agent_query_scope,
    'agent.query.ai_role': check_agent_query_ai_role,
    'agent.query.limits': check_agent_query_limits,
    'agent.query.currency': check_agent_query_currency,
    'agent.query.count_meaning': check_agent_query_count_meaning,
    'agent.query.period': check_agent_query_period,
    'agent.query.provenance': check_agent_query_provenance,
    'agent.query.lifecycle': check_agent_query_lifecycle,
    'agent.query.identity': check_agent_query_identity,
    'agent.query.action_permit': check_agent_query_action_permit,
    'agent.query.idp': check_agent_query_idp,
    'agent.query.kyc': check_agent_query_kyc,
    'agent.query.upstream_receipt': check_agent_query_upstream_receipt,
    'agent.query.workspace_mutated': check_agent_query_workspace_mutated,
    'agent.query.duplicate': check_agent_query_duplicate,
    'agent.query.no_receipt': check_agent_query_no_receipt,
    'agent.query.not_bound': check_agent_query_not_bound,
    'agent.propose.phase': check_agent_propose_phase,
    'agent.propose.effects_executed': check_agent_propose_effects_executed,
    'agent.propose.decision': check_agent_propose_decision,
    'agent.propose.stored': check_agent_propose_stored,
    'agent.propose.duplicate': check_agent_propose_duplicate,
    'agent.propose.binding_conflict': check_agent_propose_binding_conflict,
    'agent.propose.two_person': check_agent_propose_two_person,
    'agent.propose.scope_violation': check_agent_propose_scope_violation,
    'agent.propose.invalid_amount': check_agent_propose_invalid_amount,
    'agent.propose.per_action': check_agent_propose_per_action,
    'agent.propose.cumulative': check_agent_propose_cumulative,
    'agent.propose.execute_kind': check_agent_propose_execute_kind,
    'agent.propose.tool_not_allowed': check_agent_propose_tool_not_allowed,
    'agent.execute.refused': check_agent_execute_refused,
    'agent.execute.no_write': check_agent_execute_no_write,
    'agent.period.not_before': check_agent_period_not_before,
    'agent.period.not_after': check_agent_period_not_after,
    'agent.period.before': check_agent_period_before,
    'agent.period.after': check_agent_period_after,
    'agent.period.stale': check_agent_period_stale,
    'agent.period.revoked': check_agent_period_revoked,
    'agent.period.unknown': check_agent_period_unknown,
    'agent.period.invalid': check_agent_period_invalid,
    'agent.cite.stamped': check_agent_cite_stamped,
    'agent.cite.outcome': check_agent_cite_outcome,
    'agent.cite.role': check_agent_cite_role,
    'agent.cite.pending': check_agent_cite_pending,
    'agent.cite.unknown': check_agent_cite_unknown,
    'agent.cite.mismatch': check_agent_cite_mismatch,
    'agent.vendor.not_vendored': check_agent_mock_not_vendored,
})
