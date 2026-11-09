"""Bounded SIMULATED case evidence. Capital-local extension, no command authority.

Only the pinned local producer and immutable FixtureViews are supported. Case IDs
are advance IDs in this fixture; no general ownership relationship is inferred.
All callers hold CapitalService.lock, including through HTTP response release.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets

from capital.agent_lane import AGENT_ID, INPUT_CEILING
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.protocol import CreditMachine
from capital.resources import note_path, read_note

NOTE = 'CAPITAL_AGENT_CASE_DISCLOSURE.md'
# Supported semantics, checked against the note. Output values come from the note.
_USABLE = {
    'case_brief_field_allowlist': {
        'schema': 'CAPITAL_CASE_BRIEF_V1', 'additional_properties': False,
        'leaf_fields': ['schema', 'mode', 'subject.case_id', 'subject.beneficiary_id',
                        'subject.claim_id', 'subject.advance_id',
                        'facts.beneficiary_claim_outstanding_krw',
                        'facts.beneficiary_refund_exposure_krw',
                        'facts.advance_principal_outstanding_krw',
                        'provenance.policy_id', 'provenance.brief_sha256',
                        'authority.real_authentication', 'authority.execution_authority',
                        'authority.production'], 'unknown_amount': None},
    'explicit_subject_scope': {
        'permission': 'CAPITAL_LOCAL_QUERY_CASE_V1', 'subject_cardinality': 1,
        'subject_keys': ['case_id', 'beneficiary_id'], 'pin_keys': ['claim_id', 'advance_id'],
        'implicit_inheritance': False, 'persistent': False},
    'grant_currentness_checks': {
        'run': 'exact_current', 'agent': 'host_context_exact',
        'generation': 'exact_current_per_agent_subject_slot',
        'period': 'not_before <= current < expires',
        'issuance': 'not_before=current; expires=current+1', 'revoked': 'deny',
        'release': 'atomic_with_checks_and_projection', 'restart': 'invalidate_all'},
    'denial_disclosure_policy': {
        'failure_response': {'status': 'UNAVAILABLE', 'code': 'CASE_BRIEF_UNAVAILABLE'},
        'transport_status': 200, 'existence_oracle': False, 'query_subject': 'UNCHANGED'},
    'brief_provenance_scope': {
        'policy_id': 'CAPITAL_AGENT_CASE_DISCLOSURE_V1',
        'digest': 'SHA256 of canonical allowed response excluding provenance.brief_sha256',
        'workspace_provenance': False, 'authentication_proof': False},
    'local_tool_extension_boundary': {
        'tool': 'query_case', 'coverage': 'CAPITAL_LOCAL_EXTENSION',
        'pinned_five_tool_coverage': False, 'upstream_contract_change': False,
        'real_authentication': 'NOT_BOUND', 'execution_authority': 'NOT_BOUND',
        'production': 'NOT_AUTHORIZED', 'model_calls': False},
    'query_non_mutation': {
        'business_state': 'UNCHANGED', 'grant_state': 'UNCHANGED',
        'logical_period': 'UNCHANGED', 'persistence': False, 'proposal_creation': False,
        'proposal_execution': False, 'read_receipts': False},
}
_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_HANDLE = re.compile(r'[0-9a-f]{32}\Z')
_GRANT_KEYS = frozenset(('grant_id', 'run_id', 'agent_id', 'permission', 'subject',
                         'claim_id', 'advance_id', 'generation', 'not_before_period',
                         'expires_before_period', 'revoked'))


class Unavailable(Exception):
    """Internal only; never put a diagnostic on the wire."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def identifier(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def logical(value):
    return type(value) is int and 0 <= value <= INPUT_CEILING


def subject_valid(subject):
    return (type(subject) is dict and set(subject) == {'case_id', 'beneficiary_id'}
            and all(identifier(value) for value in subject.values()))


class DisclosurePolicy:
    def __init__(self, resource=None):
        block = read_note(note_path(NOTE) if resource is None else resource)['block']
        self.values = {}
        if (type(block) is not dict or block.get('decision_id') != 'agent-case-disclosure-decision'
                or block.get('status') != 'PROVISIONAL_PRODUCT_DECISION'
                or block.get('provisional') is not True):
            return
        entries = block.get('entries')
        if type(entries) is not dict:
            return
        for name, supported in _USABLE.items():
            entry = entries.get(name)
            if (type(entry) is not dict or entry.get('status') != 'ADOPTED'
                    or canonical(entry.get('value')) != canonical(supported)):
                return
        self.values = {name: copy.deepcopy(entries[name]['value']) for name in _USABLE}

    @property
    def ready(self):
        return len(self.values) == len(_USABLE)

    def denial(self):
        # Fail closed even when the policy itself cannot be loaded.
        return copy.deepcopy(self.values['denial_disclosure_policy']['failure_response']
                             if self.ready else _USABLE['denial_disclosure_policy']['failure_response'])


class GrantRegistry:
    """Host-only ephemeral fixture setup; queries do not change this registry."""
    def __init__(self, run_id, policy):
        self.run_id, self.policy = run_id, policy
        self.grants = {}
        self.generations = {}
        self.generation_high_water = {}
        self.logical_period = 0
        self.period_high_water = 0

    def _period(self):
        p = self.logical_period
        if not logical(p) or not logical(self.period_high_water) or p != self.period_high_water:
            raise Unavailable()
        return p

    def set_period(self, period):
        current = self._period()
        if not logical(period) or period < current:
            raise Unavailable()
        self.logical_period = self.period_high_water = period

    def _advance(self, slot):
        generation = self.generations.get(slot, 0)
        high_water = self.generation_high_water.get(slot, 0)
        if (not logical(generation) or not logical(high_water) or generation != high_water
                or (slot in self.generations) != (slot in self.generation_high_water)
                or generation >= INPUT_CEILING):
            self.generations[slot] = None  # permanently exhausted/corrupt slot
            raise Unavailable()
        generation += 1
        self.generations[slot] = self.generation_high_water[slot] = generation
        return generation

    def issue(self, subject, claim_id, advance_id):
        if (not self.policy.ready or not subject_valid(subject)
                or not identifier(claim_id) or not identifier(advance_id)):
            raise Unavailable()
        p = self._period()
        if p >= INPUT_CEILING:
            raise Unavailable()
        handle = None
        for _ in range(8):
            candidate = secrets.token_hex(16)
            if type(candidate) is str and _HANDLE.fullmatch(candidate) and candidate not in self.grants:
                handle = candidate
                break
        if handle is None:
            raise Unavailable()
        slot = (AGENT_ID, subject['case_id'], subject['beneficiary_id'])
        generation = self._advance(slot)
        row = dict(grant_id=handle, run_id=self.run_id, agent_id=AGENT_ID,
                   permission=self.policy.values['explicit_subject_scope']['permission'],
                   subject=copy.deepcopy(subject), claim_id=claim_id, advance_id=advance_id,
                   generation=generation, not_before_period=p, expires_before_period=p + 1,
                   revoked=False)
        self.grants[handle] = row
        return copy.deepcopy(row)

    def revoke(self, handle):
        row = self.grants.get(handle)
        if type(row) is not dict or not subject_valid(row.get('subject')):
            raise Unavailable()
        slot = (AGENT_ID, row['subject']['case_id'], row['subject']['beneficiary_id'])
        row['revoked'] = True
        self._advance(slot)

    def authorize(self, body, run_id, lane):
        if not self.policy.ready or type(body) is not dict or set(body) != {'grant_id', 'subject'}:
            raise Unavailable()
        handle, subject = body['grant_id'], body['subject']
        if type(handle) is not str or not _HANDLE.fullmatch(handle) or not subject_valid(subject):
            raise Unavailable()
        row = self.grants.get(handle)
        if type(row) is not dict or set(row) != _GRANT_KEYS:
            raise Unavailable()
        if (not lane.case_query_eligible() or row['run_id'] != run_id or self.run_id != run_id
                or row['agent_id'] != AGENT_ID or row['grant_id'] != handle
                or row['permission'] != self.policy.values['explicit_subject_scope']['permission']
                or not subject_valid(row['subject']) or row['subject'] != subject
                or row['revoked'] is not False
                or not identifier(row['claim_id']) or not identifier(row['advance_id'])):
            raise Unavailable()
        slot = (AGENT_ID, subject['case_id'], subject['beneficiary_id'])
        generation = row['generation']
        if (type(generation) is not int or not 1 <= generation <= INPUT_CEILING
                or type(self.generations.get(slot)) is not int
                or self.generations[slot] != generation
                or type(self.generation_high_water.get(slot)) is not int
                or self.generation_high_water[slot] != generation):
            raise Unavailable()
        p = self._period()
        start, end = row['not_before_period'], row['expires_before_period']
        if not logical(start) or not logical(end) or end != start + 1 or not start <= p < end:
            raise Unavailable()
        return row


def amount(value):
    # This ceiling is a technical fixture input bound, not a financial term.
    return value if type(value) is int and 0 <= value <= INPUT_CEILING else None


def project(policy, grant, advance, settlement, beneficiary, mapping):
    """Copy individual attributable facts. No summation or financial arithmetic."""
    subject = grant['subject']
    claim = settlement.get('claim')
    if (grant['advance_id'] != subject['case_id']
            or advance.get('advance_id') != grant['advance_id']
            or advance.get('claim_id') != grant['claim_id']
            or advance.get('beneficiary_role') != subject['beneficiary_id']
            or beneficiary != subject['beneficiary_id']
            or advance.get('settlement_id') not in (None, grant['claim_id'])
            or settlement.get('settlement_id') != grant['claim_id']
            or type(claim) is not dict or claim.get('claim_id') != grant['claim_id']):
        raise Unavailable()
    payees = mapping.get(beneficiary) if type(mapping) is dict else None
    outstanding = None
    if type(payees) is list and payees and all(type(p) is str for p in payees):
        lines = claim.get('obligations')
        if type(lines) is list and all(type(line) is dict for line in lines):
            attributable = [line for line in lines if line.get('payee') in payees]
            if len(attributable) == 1:
                outstanding = amount(attributable[0].get('outstanding'))
    refund = amount(claim.get('refund_outstanding'))
    # refund_beneficiary is the recipient, never evidence of bearer attribution.
    if refund != 0 and claim.get('refund_bearer') != beneficiary:
        refund = None
    boundary = policy.values['local_tool_extension_boundary']
    body = {
        'schema': policy.values['case_brief_field_allowlist']['schema'], 'mode': 'SIMULATED',
        'subject': {**subject, 'claim_id': grant['claim_id'], 'advance_id': grant['advance_id']},
        'facts': {'beneficiary_claim_outstanding_krw': outstanding,
                  'beneficiary_refund_exposure_krw': refund,
                  'advance_principal_outstanding_krw': amount(advance.get('outstanding_exposure'))},
        'provenance': {'policy_id': policy.values['brief_provenance_scope']['policy_id']},
        'authority': {key: boundary[key] for key in
                      ('real_authentication', 'execution_authority', 'production')},
    }
    body['provenance']['brief_sha256'] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def build(service, grant):
    producer = service.producer
    # Check adapters before accessing properties or invoking any reader.
    if (type(producer) is not PinnedFsmProducer or type(producer.fixtures) is not FixtureViews
            or type(producer.machine) is not CreditMachine
            or getattr(producer.fixtures, 'settlement_views_mutable', False)):
        raise Unavailable()
    if (grant['subject']['case_id'] != grant['advance_id']
            or service.case_fixtures.get(grant['advance_id']) != grant['claim_id']):
        raise Unavailable()
    advance = producer.view(grant['advance_id'])
    settlement = producer.fixtures.view(grant['claim_id'])
    beneficiary = producer.fixtures.beneficiary(grant['claim_id'])
    item = service.terms.items.get('additional_margin', {})
    mapping = item.get('value', {}).get('beneficiary_payee_map') if item.get('mark') == 'ADOPTED' else None
    return project(service.agent_brief_policy, grant, advance, settlement, beneficiary, mapping)
