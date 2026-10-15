"""Simulated AgentGrant fixture. Not the upstream mock and not an ActionPermit.

The lane covers the pinned draft's full tool allowlist: `query_grant`,
`query_subject`, `propose_action`, `withdraw_proposal`, and
`propose_grant_change`; `execute` is the always-refused name only. Grant rows
are process-local fixtures. Money limits come from the terms note
(`underwriting_depth` caps). The logical period and the draft input ceiling
are fixture labels, not a product term or a product count. Proposals stay in
this process and are not written to the workspace. EXECUTE cannot be turned
on. Identity, IdP, KYC, and ActionPermit stay NOT_BOUND.
"""
from __future__ import annotations

import json

LABEL = 'SIMULATED'
MODE = 'SIMULATED_AGENT_GRANT'
PROVENANCE = 'SIMULATED_AGENT_GRANT'
LIFECYCLE = 'IN_MEMORY_FIXTURE'
LIMITS_SOURCE = (
    'CAPITAL-TERMS-V1 underwriting_depth '
    'single_advance_cap_krw and beneficiary_aggregate_cap_krw'
)
COUNT_MEANING = 'DRAFT_INPUT_CEILING_NOT_A_PRODUCT_LIMIT'
PERIOD_MEANING = 'SIMULATED_LOGICAL_WINDOW'
ISSUER_KIND = 'SIMULATED_FIXTURE'

# Draft 0.1 integer ceiling for fixture fields. Not a Capital product limit.
MONEY_MAX = 10**12
INPUT_CEILING = MONEY_MAX

AGENT_ID = 'sim-agent'
ISSUER_ID = 'sim-organizer'
ACTIVE_GRANT_ID = 'sim-grant-agent'
REVOKED_GRANT_ID = 'sim-grant-agent-revoked'
ACTIVE_GENERATION = 2
REVOKED_GENERATION = 1
PERIOD_NOT_BEFORE = 1
PERIOD_NOT_AFTER = 1000

SURFACES = (
    'capital:approve',
    'capital:close',
    'capital:default',
    'capital:draw',
    'capital:offer',
    'capital:reconcile',
    'capital:repay',
)
SURFACE_OP = {surface: surface.split(':', 1)[1] for surface in SURFACES}

FALSE_FLAGS = (
    'execution_enabled',
    'issued',
    'paid',
    'signed',
    'transferred',
    'effects_executed',
    'funds_executed',
    'refund_executed',
    'chain_grant_confirmed',
    'revocation_cut_confirmed',
    'durable',
    'legal_authority',
)

_QUERY_KEYS = frozenset({'grant_id', 'generation', 'now'})
_SUBJECT_KEYS = frozenset({'grant_id', 'generation', 'now', 'surface'})
_PROPOSE_KEYS = frozenset({'grant_id', 'generation', 'now', 'proposal_id', 'surface', 'amount', 'kind'})
_WITHDRAW_KEYS = frozenset({'grant_id', 'generation', 'now', 'proposal_id'})
_CHANGE_KEYS = frozenset({'grant_id', 'generation', 'now', 'proposal_id', 'requested'})
_MEMO_KEYS = frozenset({'authority', 'scope', 'limits', 'period', 'note'})
_AUTHORITY_LEVELS = frozenset({'QUERY', 'PROPOSE'})


class AgentLaneError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def ident(value):
    return type(value) is str and 0 < len(value) <= 100 and value.strip() == value


def _positive_int(value):
    return type(value) is int and 0 < value <= MONEY_MAX


def _logical(value):
    return type(value) is int and 0 <= value <= MONEY_MAX


def _generation(value):
    return type(value) is int and 0 < value <= MONEY_MAX


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _flags():
    return {flag: False for flag in FALSE_FLAGS}


class AgentLane:
    """In-memory QUERY/PROPOSE register over fixture grants.

    Callers that share a CapitalService hold that service lock. This object
    does not persist proposals and has no execution switch.
    """

    def __init__(self, terms):
        self.terms = terms
        self.proposals = {}

    def limits(self):
        """Money caps from the note. None when the note cannot be used."""
        depth = self._depth()
        if depth is None:
            return None
        per_action = depth.get('single_advance_cap_krw')
        cumulative = depth.get('beneficiary_aggregate_cap_krw')
        if not _positive_int(per_action) or not _positive_int(cumulative) or cumulative < per_action:
            return None
        return {
            'per_action_max': per_action,
            'cumulative_max': cumulative,
            'count_max': INPUT_CEILING,
            'currency': 'KRW',
            'count_max_meaning': COUNT_MEANING,
        }

    def query_grant(self, body):
        parsed = self._parse_call(body, _QUERY_KEYS)
        grant = self._current(parsed, 'QUERY')
        view = self._envelope(parsed['now'], False)
        view['grant'] = self._grant_view(grant)
        return view

    def query_subject(self, body):
        """Membership view only. `subjects` echoes the fixture registry: None is unrestricted."""
        parsed = self._parse_subject(body)
        grant = self._current(parsed, 'QUERY')
        if parsed['surface'] not in grant['scope']['surfaces']:
            raise AgentLaneError('SCOPE_VIOLATION')
        subjects = grant['scope']['subjects']
        if subjects is not None and parsed['subject'] is not None \
                and parsed['subject'] not in subjects:
            raise AgentLaneError('SCOPE_VIOLATION')
        view = self._envelope(parsed['now'], False)
        view['match'] = {
            'surface': parsed['surface'],
            'subject': parsed['subject'],
            'in_scope': True,
        }
        view['subjects'] = None if subjects is None else list(subjects)
        return view

    def propose_action(self, body):
        parsed = self._parse_propose(body)
        if parsed['kind'] == 'EXECUTE':
            raise AgentLaneError('EXECUTE_AUTHORITY_DISABLED')
        binding = _canonical({
            'proposal_id': parsed['proposal_id'],
            'grant_id': parsed['grant_id'],
            'surface': parsed['surface'],
            'subject': parsed['subject'],
            'amount': parsed['amount'],
            'kind': parsed['kind'],
        })
        existing = self.proposals.get(parsed['proposal_id'])
        if existing is not None:
            if existing['binding'] != binding:
                raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
            view = self._envelope(parsed['now'], True)
            view['proposal'] = self._proposal_view(existing)
            return view
        grant = self._current(parsed, 'PROPOSE')
        if parsed['surface'] not in grant['scope']['surfaces']:
            raise AgentLaneError('SCOPE_VIOLATION')
        self._require_room(grant, parsed['amount'])
        row = {
            'binding': binding,
            'proposal_id': parsed['proposal_id'],
            'grant_id': grant['grant_id'],
            'generation': grant['generation'],
            'surface': parsed['surface'],
            'subject': parsed['subject'],
            'amount': parsed['amount'],
            'kind': parsed['kind'],
            'phase': 'HUMAN_PENDING',
            'effects_executed': False,
        }
        self.proposals[parsed['proposal_id']] = row
        view = self._envelope(parsed['now'], False)
        view['proposal'] = self._proposal_view(row)
        return view

    def withdraw_proposal(self, body):
        """Move a pending proposal to WITHDRAWN. The period window is not enforced."""
        parsed = self._parse_proposal_ref(body, _WITHDRAW_KEYS)
        grant = self._current(parsed, 'PROPOSE', window=False)
        row = self.proposals.get(parsed['proposal_id'])
        if row is None:
            raise AgentLaneError('UNKNOWN_PROPOSAL')
        if row['grant_id'] != grant['grant_id']:
            raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
        if row['phase'] == 'WITHDRAWN':
            view = self._envelope(parsed['now'], True)
            view['proposal'] = self._memo_view(row, 'withdraw_proposal')
            return view
        if row['phase'] != 'HUMAN_PENDING':
            raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
        row['phase'] = 'WITHDRAWN'
        view = self._envelope(parsed['now'], False)
        view['proposal'] = self._memo_view(row, 'withdraw_proposal')
        return view

    def propose_grant_change(self, body):
        """Store a HUMAN_PENDING grant-change memo. The grant body never changes."""
        parsed = self._parse_proposal_ref(body, _CHANGE_KEYS)
        requested = self._parse_requested(body['requested'])
        binding = _canonical({
            'proposal_id': parsed['proposal_id'],
            'grant_id': parsed['grant_id'],
            'tool': 'propose_grant_change',
            'requested': requested,
        })
        existing = self.proposals.get(parsed['proposal_id'])
        if existing is not None:
            if existing['binding'] != binding:
                raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
            view = self._envelope(parsed['now'], True)
            view['proposal'] = self._memo_view(existing, 'propose_grant_change')
            return view
        grant = self._current(parsed, 'PROPOSE')
        self._require_room(grant, 0)
        row = {
            'binding': binding,
            'proposal_id': parsed['proposal_id'],
            'grant_id': grant['grant_id'],
            'generation': grant['generation'],
            'tool': 'propose_grant_change',
            'surface': None,
            'subject': None,
            'amount': None,
            'kind': 'GRANT_CHANGE',
            'memo': requested,
            'phase': 'HUMAN_PENDING',
            'effects_executed': False,
        }
        self.proposals[parsed['proposal_id']] = row
        view = self._envelope(parsed['now'], False)
        view['proposal'] = self._memo_view(row, 'propose_grant_change')
        return view

    def refuse_execute(self):
        """EXECUTE has no implementation. The call does not read or write state."""
        raise AgentLaneError('EXECUTE_AUTHORITY_DISABLED')

    def reference(self, op, args, proposal_id):
        """Cite a pending proposal from a human command. Do not execute it."""
        if not ident(proposal_id):
            raise AgentLaneError('INVALID_ARGUMENTS')
        row = self.proposals.get(proposal_id)
        if row is None:
            raise AgentLaneError('UNKNOWN_PROPOSAL')
        if row['phase'] != 'HUMAN_PENDING' or row['effects_executed'] is not False:
            raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
        if SURFACE_OP.get(row['surface']) != op:
            raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
        if type(args) is dict and 'amount' in args and args['amount'] != row['amount']:
            raise AgentLaneError('PROPOSAL_BINDING_CONFLICT')
        return proposal_id

    def _depth(self):
        items = getattr(self.terms, 'items', None)
        if type(items) is not dict:
            return None
        item = items.get('underwriting_depth')
        if type(item) is not dict or item.get('mark') != 'ADOPTED':
            return None
        value = item.get('value')
        if type(value) is not dict:
            return None
        return value

    def _grants(self):
        limits = self.limits()
        if limits is None:
            return None
        scope = {'surfaces': list(SURFACES), 'subjects': None}
        period = {
            'not_before': PERIOD_NOT_BEFORE,
            'not_after': PERIOD_NOT_AFTER,
            'period_meaning': PERIOD_MEANING,
        }
        depth = self._depth()
        ai_role = depth.get('ai_role') if depth is not None else None
        shared = {
            'issuer': ISSUER_ID,
            'issuer_kind': ISSUER_KIND,
            'agent_id': AGENT_ID,
            'authority': ['PROPOSE', 'QUERY'],
            'scope': scope,
            'limits': limits,
            'period': period,
            'ai_role': ai_role if type(ai_role) is str else None,
        }
        revoked = {
            **shared,
            'grant_id': REVOKED_GRANT_ID,
            'generation': REVOKED_GENERATION,
            'phase': 'REVOKED',
            'revoked_at_seq': 1,
            'reason': 'sim-fixture-revoked',
        }
        active = {
            **shared,
            'grant_id': ACTIVE_GRANT_ID,
            'generation': ACTIVE_GENERATION,
            'phase': 'ACTIVE',
            'revoked_at_seq': None,
            'reason': None,
        }
        return {REVOKED_GRANT_ID: revoked, ACTIVE_GRANT_ID: active}

    def _parse_call(self, body, keys):
        if type(body) is not dict or set(body) != keys:
            raise AgentLaneError('INVALID_ARGUMENTS')
        if not ident(body['grant_id']) or not _generation(body['generation']):
            raise AgentLaneError('INVALID_ARGUMENTS')
        if not _logical(body['now']):
            raise AgentLaneError('INVALID_PERIOD')
        return {'grant_id': body['grant_id'], 'generation': body['generation'], 'now': body['now']}

    def _parse_subject(self, body):
        if type(body) is not dict or set(body) not in {_SUBJECT_KEYS, _SUBJECT_KEYS | {'subject'}}:
            raise AgentLaneError('INVALID_ARGUMENTS')
        parsed = self._parse_call(
            {'grant_id': body['grant_id'], 'generation': body['generation'], 'now': body['now']},
            _QUERY_KEYS,
        )
        if not ident(body['surface']):
            raise AgentLaneError('INVALID_ARGUMENTS')
        subject = body['subject'] if 'subject' in body else None
        if subject is not None and not ident(subject):
            raise AgentLaneError('INVALID_ARGUMENTS')
        parsed.update(surface=body['surface'], subject=subject)
        return parsed

    def _parse_proposal_ref(self, body, keys):
        if type(body) is not dict or set(body) != keys:
            raise AgentLaneError('INVALID_ARGUMENTS')
        parsed = self._parse_call(
            {'grant_id': body['grant_id'], 'generation': body['generation'], 'now': body['now']},
            _QUERY_KEYS,
        )
        if not ident(body['proposal_id']):
            raise AgentLaneError('INVALID_ARGUMENTS')
        parsed['proposal_id'] = body['proposal_id']
        return parsed

    def _parse_requested(self, requested):
        """Grant-change memo: keys only from the draft's list; the rest is opaque."""
        if type(requested) is not dict or not requested or set(requested) - _MEMO_KEYS:
            raise AgentLaneError('INVALID_ARGUMENTS')
        if 'note' in requested and not ident(requested['note']):
            raise AgentLaneError('INVALID_ARGUMENTS')
        if 'authority' in requested:
            authority = requested['authority']
            if type(authority) is not list or not authority \
                    or any(type(item) is not str for item in authority):
                raise AgentLaneError('INVALID_ARGUMENTS')
            if 'EXECUTE' in authority:
                raise AgentLaneError('EXECUTE_AUTHORITY_DISABLED')
            if set(authority) - _AUTHORITY_LEVELS:
                raise AgentLaneError('INVALID_ARGUMENTS')
        try:
            _canonical(requested)
        except ValueError:
            raise AgentLaneError('INVALID_ARGUMENTS')
        return requested

    def _parse_propose(self, body):
        if type(body) is not dict or set(body) not in {_PROPOSE_KEYS, _PROPOSE_KEYS | {'subject'}}:
            raise AgentLaneError('INVALID_ARGUMENTS')
        parsed = self._parse_call(
            {'grant_id': body['grant_id'], 'generation': body['generation'], 'now': body['now']},
            _QUERY_KEYS,
        )
        subject = body['subject'] if 'subject' in body else None
        if not ident(body['proposal_id']) or not ident(body['surface']) or not ident(body['kind']):
            raise AgentLaneError('INVALID_ARGUMENTS')
        if subject is not None and not ident(subject):
            raise AgentLaneError('INVALID_ARGUMENTS')
        if not _positive_int(body['amount']):
            raise AgentLaneError('INVALID_AMOUNT')
        parsed.update(
            proposal_id=body['proposal_id'], surface=body['surface'], subject=subject,
            amount=body['amount'], kind=body['kind'],
        )
        return parsed

    def _current(self, parsed, level, window=True):
        grants = self._grants()
        if grants is None:
            raise AgentLaneError('NOT_BOUND')
        grant = grants.get(parsed['grant_id'])
        if grant is None:
            raise AgentLaneError('UNKNOWN_GRANT')
        if parsed['generation'] != grant['generation']:
            raise AgentLaneError('GRANT_NOT_CURRENT')
        if grant['phase'] == 'REVOKED':
            raise AgentLaneError('GRANT_REVOKED')
        if grant['phase'] != 'ACTIVE':
            raise AgentLaneError('GRANT_NOT_CURRENT')
        now = parsed['now']
        period = grant['period']
        if window:
            if now < period['not_before']:
                raise AgentLaneError('GRANT_NOT_CURRENT')
            if now > period['not_after']:
                raise AgentLaneError('GRANT_EXPIRED')
        if level not in grant['authority']:
            raise AgentLaneError('TOOL_NOT_ALLOWED')
        if grant['agent_id'] != AGENT_ID:
            raise AgentLaneError('UNKNOWN_GRANT')
        return grant

    def _charged(self, grant_id):
        amount = 0
        count = 0
        for row in self.proposals.values():
            if row['grant_id'] != grant_id or row['phase'] != 'HUMAN_PENDING':
                continue
            count += 1
            amount += row['amount'] if row['amount'] is not None else 0
        return amount, count

    def _require_room(self, grant, amount):
        limits = grant['limits']
        if amount > limits['per_action_max']:
            raise AgentLaneError('PER_ACTION_EXCEEDED')
        charged, count = self._charged(grant['grant_id'])
        if charged + amount > limits['cumulative_max']:
            raise AgentLaneError('CUMULATIVE_EXCEEDED')
        if count + 1 > limits['count_max']:
            raise AgentLaneError('COUNT_EXCEEDED')

    def _two_person(self, amount):
        depth = self._depth()
        if depth is None:
            return None
        threshold = depth.get('two_person_threshold_krw')
        if type(threshold) is not int or threshold < 0:
            return None
        return amount > threshold

    def _envelope(self, now, duplicate):
        body = {
            'label': LABEL,
            'mode': MODE,
            'provenance': PROVENANCE,
            'lifecycle_authority': LIFECYCLE,
            'identity': 'NOT_BOUND',
            'authentication': 'NOT_BOUND',
            'idp': 'NOT_BOUND',
            'kyc': 'NOT_BOUND',
            'action_permit': 'NOT_BOUND',
            'upstream_receipt': 'NONE',
            'workspace_mutated': False,
            'duplicate': duplicate,
            'now': now,
            'terms_version': getattr(self.terms, 'version', None),
            'limits_source': LIMITS_SOURCE,
        }
        body.update(_flags())
        return body

    def _grant_view(self, grant):
        return {
            'grant_id': grant['grant_id'],
            'generation': grant['generation'],
            'issuer': grant['issuer'],
            'issuer_kind': grant['issuer_kind'],
            'agent_id': grant['agent_id'],
            'authority': list(grant['authority']),
            'ai_role': grant['ai_role'],
            'scope': {'surfaces': list(grant['scope']['surfaces']), 'subjects': None},
            'limits': dict(grant['limits']),
            'period': dict(grant['period']),
            'phase': grant['phase'],
            'revoked_at_seq': grant['revoked_at_seq'],
            'reason': grant['reason'],
        }

    def _proposal_view(self, row):
        return {
            'proposal_id': row['proposal_id'],
            'grant_id': row['grant_id'],
            'generation': row['generation'],
            'tool': 'propose_action',
            'phase': row['phase'],
            'surface': row['surface'],
            'subject': row['subject'],
            'amount': row['amount'],
            'kind': row['kind'],
            'effects_executed': False,
            'decision': None,
            'two_person_required': self._two_person(row['amount']),
        }

    def _memo_view(self, row, tool):
        amount = row['amount']
        return {
            'proposal_id': row['proposal_id'],
            'grant_id': row['grant_id'],
            'generation': row['generation'],
            'tool': tool,
            'phase': row['phase'],
            'surface': row['surface'],
            'subject': row['subject'],
            'amount': amount,
            'kind': row['kind'],
            'memo': row.get('memo'),
            'effects_executed': False,
            'decision': None,
            'two_person_required': None if amount is None else self._two_person(amount),
        }
