"""Capital-local simulation facade. The pinned Protocol FSM owns all arithmetic."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid

from capital import __version__
from capital.assets import declared as declared_assets, matches as asset_matches
from capital.agent_lane import AgentLane, AgentLaneError, ident as agent_ident
from capital.auth import (
    AGENT_PROPOSE, AGENT_PROPOSE_CHANGE, AGENT_QUERY, AGENT_QUERY_SUBJECT, AGENT_WITHDRAW,
    DEFAULT_ROLE, OP_PERMISSIONS, PROVENANCE as ROLE_PROVENANCE,
    ROLES, UNLABELED, Principal, require, LocalRoleAuthorizer,
)
from capital.observability import Observability
from capital.decisions import DecisionIndex
from capital.export import UnsignedSigner, build_manifest, manifest_status
from capital.producer import CreditError, PinnedFsmProducer
from capital.projection import ProjectionError, SimulationProjection
from capital.protocol import VENDOR
from capital.recon import build_reconciliation
from capital.policy import (
    POLICY_LABEL, POLICY_NOT_BOUND, SCENARIO_ID, DecisionNoteSettlementPolicy,
    apply_order, probe_order_freeze,
)
from capital.scenarios import ORDER, POLICY, STATEMENT, replay_scenarios
from capital.shadow import DecisionNoteShadow, SHADOW_LABEL, SHADOW_MODE, SHADOW_PROVENANCE
from capital.statement import build_statement
from capital.setoff import DecisionNoteSetoff
from capital.terms import TERMS_NOT_BOUND, DecisionNoteTermsPolicy
from capital.underwriting import DecisionNoteUnderwriting
from capital.readiness import GROUPS, UPSTREAM_BINDING_NOTE, resolve_note_blockers, source_integrity
from capital.resources import vendor_manifest
from capital.store import InMemoryStorage, WorkspaceError, verify_document

PROVENANCE = 'MOCK_CREDIT_F04_ONLY'
MAX_OPERATIONS = 500  # bounded local demo, not a financial limit
OPS = {
    'offer': {'fixture_id', 'amount'}, 'approve': set(),
    'reject': set(), 'cancel': set(), 'bind_settlement': set(),
    'draw': set(), 'repay': {'amount', 'sequence'}, 'close': set(),
    'default': set(), 'reconcile': set(),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _release_producer(producer):
    """Close an opt-in gate client. The pinned producer has no close method."""
    close = getattr(producer, 'close', None)
    if callable(close):
        close()


def _agent_api_error(code, role=None):
    """Map a lane code to HTTP. Literals stay visible to the facade error scan."""
    detail = {'role': role} if role is not None else None
    if code == 'EXECUTE_AUTHORITY_DISABLED':
        raise ApiError('EXECUTE_AUTHORITY_DISABLED', 403, detail)
    if code == 'TOOL_NOT_ALLOWED':
        raise ApiError('TOOL_NOT_ALLOWED', 403, detail)
    if code == 'GRANT_NOT_CURRENT':
        raise ApiError('GRANT_NOT_CURRENT', 403, detail)
    if code == 'GRANT_EXPIRED':
        raise ApiError('GRANT_EXPIRED', 403, detail)
    if code == 'GRANT_REVOKED':
        raise ApiError('GRANT_REVOKED', 403, detail)
    if code == 'UNKNOWN_GRANT':
        raise ApiError('UNKNOWN_GRANT', 404, detail)
    if code == 'UNKNOWN_PROPOSAL':
        raise ApiError('UNKNOWN_PROPOSAL', 404, detail)
    if code == 'PROPOSAL_BINDING_CONFLICT':
        raise ApiError('PROPOSAL_BINDING_CONFLICT', 409, detail)
    if code == 'PER_ACTION_EXCEEDED':
        raise ApiError('PER_ACTION_EXCEEDED', 400, detail)
    if code == 'CUMULATIVE_EXCEEDED':
        raise ApiError('CUMULATIVE_EXCEEDED', 400, detail)
    if code == 'COUNT_EXCEEDED':
        raise ApiError('COUNT_EXCEEDED', 400, detail)
    if code == 'SCOPE_VIOLATION':
        raise ApiError('SCOPE_VIOLATION', 400, detail)
    if code == 'INVALID_AMOUNT':
        raise ApiError('INVALID_AMOUNT', 400, detail)
    if code == 'INVALID_PERIOD':
        raise ApiError('INVALID_PERIOD', 400, detail)
    if code == 'INVALID_ARGUMENTS':
        raise ApiError('INVALID_ARGUMENTS', 400, detail)
    if code == 'NOT_BOUND':
        raise ApiError('NOT_BOUND', 400, detail)
    raise ApiError('NOT_BOUND', 500, detail)


class ApiError(Exception):
    def __init__(self, code, status=400, detail=None):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(code)


class CapitalService:
    def __init__(self, storage=None, authorizer=None, signer=None, *, projection=None, producer=None, terms=None, policy=None, underwriting=None, setoff=None, observability=None, decisions=None, shadow=None):
        self.lock = threading.RLock()
        self.authorizer = authorizer or LocalRoleAuthorizer()
        self.signer = signer if signer is not None else UnsignedSigner()
        self.storage = InMemoryStorage() if storage is None else storage
        self.instance_id = str(uuid.uuid4())
        self.storage.writer_instance = self.instance_id
        # Default producer is the pinned FSM adapter. Injection replaces that
        # object; the command path below does not call CreditMachine directly.
        self.producer = producer if producer is not None else PinnedFsmProducer()
        self.projection_port = projection if projection is not None else SimulationProjection()
        self.terms = terms if terms is not None else DecisionNoteTermsPolicy()
        self.policy = policy if policy is not None else DecisionNoteSettlementPolicy()
        self.underwriting = underwriting if underwriting is not None else DecisionNoteUnderwriting(self.terms)
        self.setoff = setoff if setoff is not None else DecisionNoteSetoff(self.terms, self.policy)
        self.shadow = shadow if shadow is not None else DecisionNoteShadow()
        self.decision_index = decisions if decisions is not None else DecisionIndex()
        self.agent_lane = AgentLane(self.terms)
        self.observability = observability or Observability()
        self.receipts = {}
        self.case_fixtures = {}
        self.workspace_status = 'ACTIVE'
        self.source = vendor_manifest()
        self.scenario_results = replay_scenarios()
        self._load_workspace()

    @property
    def machine(self):
        return self.producer.machine

    @property
    def fixtures(self):
        return self.producer.fixtures

    def workspace_view(self):
        kind = 'LOCAL_FILE_WORKSPACE' if self.storage.durable_label == 'LOCAL_FILE_WORKSPACE' else 'MEMORY'
        path = getattr(self.storage, 'path', None)
        return {'kind': kind, 'status': self.workspace_status, 'path': None if path is None else str(path)}

    def _load_workspace(self):
        try:
            document = self.storage.load()
        except WorkspaceError as exc:
            self.workspace_status = exc.code
            return
        if document is None:
            return
        try:
            installed = self._validated_restore(document)
        except WorkspaceError as exc:
            self.workspace_status = exc.code
            self.producer.reset()
            self.receipts = {}
            self.case_fixtures = {}
            return
        restored, self.receipts, self.case_fixtures = installed
        previous = self.producer
        self.producer = restored
        if previous is not restored:
            _release_producer(previous)

    def _validated_restore(self, document):
        verify_document(document)
        payload = document['payload']
        if type(payload) is not dict or set(payload) != {'receipts', 'journal', 'case_fixtures', 'state_digest'}:
            raise WorkspaceError('WORKSPACE_UNREADABLE')
        receipts, journal, mapping, state_digest = (
            payload['receipts'], payload['journal'], payload['case_fixtures'], payload['state_digest'])
        if type(receipts) is not dict or type(journal) is not list or type(mapping) is not dict or type(state_digest) is not str:
            raise WorkspaceError('WORKSPACE_UNREADABLE')
        self._require_receipts(receipts)
        restored = None
        try:
            try:
                restored = self.producer.restored(copy.deepcopy(journal))
            except CreditError as exc:
                raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
            if restored.state_digest() != state_digest:
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            expected = {}
            seen = []
            for entry in journal:
                advance_id = entry['advance_id']
                if advance_id not in seen:
                    seen.append(advance_id)
                    expected[advance_id] = restored.view(advance_id)['claim_id']
            if mapping != expected or any(fixture_id not in self.fixtures.rows for fixture_id in mapping.values()):
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            for entry in journal:
                stored = receipts.get(entry['idempotency_key'])
                if stored is None or stored['receipt'].get('outcome') != 'ACCEPTED':
                    raise WorkspaceError('WORKSPACE_UNREADABLE')
            labeled = self._label_restored_receipts(receipts)
            mapping_copy = copy.deepcopy(mapping)
        except Exception:
            if restored is not None and restored is not self.producer:
                _release_producer(restored)
            raise
        return restored, labeled, mapping_copy

    def _label_restored_receipts(self, receipts):
        """Keep a stored role. A pre-label workspace file loads as UNLABELED and is not rewritten here."""
        labeled = copy.deepcopy(receipts)
        for stored in labeled.values():
            receipt = stored['receipt']
            if 'role' not in receipt and 'role_provenance' not in receipt:
                receipt['role'] = UNLABELED
                receipt['role_provenance'] = UNLABELED
                continue
            role, provenance = receipt.get('role'), receipt.get('role_provenance')
            if role == UNLABELED and provenance == UNLABELED:
                continue
            if role not in ROLES or provenance != ROLE_PROVENANCE:
                raise WorkspaceError('WORKSPACE_UNREADABLE')
        return labeled

    def _require_receipts(self, receipts):
        for key, stored in receipts.items():
            if type(key) is not str or type(stored) is not dict or set(stored) != {'fingerprint', 'receipt'}:
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            fingerprint, receipt = stored['fingerprint'], stored['receipt']
            if type(fingerprint) is not str or len(fingerprint) != 64 or any(char not in '0123456789abcdef' for char in fingerprint):
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            if type(receipt) is not dict or receipt.get('operation_id') != key or receipt.get('outcome') not in {'ACCEPTED', 'REJECTED'}:
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            if type(receipt.get('instance_id')) is not str:
                raise WorkspaceError('WORKSPACE_UNREADABLE')

    def _persist(self):
        self.storage.save({
            'receipts': self.receipts, 'journal': self.machine.export_journal(),
            'case_fixtures': dict(self.case_fixtures), 'state_digest': self.machine.state_digest()})

    def snapshot(self, role=None):
        with self.lock:
            cases = [self.machine.view(key) for key in sorted(self.case_fixtures)]
            principal = Principal(role or DEFAULT_ROLE)
            return {'instance_id': self.instance_id, 'version': __version__, 'mode': 'LOCAL_SIMULATION',
                    'provenance': PROVENANCE, 'durable': self.storage.durable_label, 'funds_executed': False,
                    'source_commit': self.source['commit'], 'assets': declared_assets(), 'cases': cases,
                    'fixtures': copy.deepcopy(self.fixtures.rows),
                    'state_digest': self.machine.state_digest(),
                    'operation_count': len(self.receipts), 'operation_capacity': MAX_OPERATIONS,
                    'auth': self.authorizer.describe(principal),
                    'workspace': self.workspace_view(),
                    'terms': self._terms_snapshot(),
                    'decisions': [self._terms_decision_line(),
                                  self._policy_decision_line(),
                                  'Bank/PG, production DB and deployment: NOT_AUTHORIZED',
                                  'Finance projection/backend/export design: PENDING_NOT_ADOPTED']}

    def evidence(self):
        """Pass through immutable source values; never derive sales or real cash."""
        with self.lock:
            rows = []
            for key in sorted(self.fixtures.rows):
                view = self.fixtures.view(key)
                claim = view['claim']
                rows.append({'claim_id': key, 'trade_id': view['trade_id'],
                             'phase': view['phase'], 'currency': view['currency'],
                             'gross_face': claim['gross'],
                             'confirmed_cash': claim['confirmed_cash'],
                             'distributed_cash': claim['distributed_cash'],
                             'undistributed_cash': claim['undistributed_cash'],
                             'refund_face': claim['refund_face'],
                             'refund_outstanding': claim['refund_outstanding'],
                             'refund_bearer_policy': claim['refund_bearer_policy'],
                             'recovery_due': claim['recovery_due'],
                             'obligations': claim['obligations'],
                             'profile': self.fixtures.profile(key),
                             'source_view_digest': digest(view)})
            return {'mode': 'READ_ONLY_FIXTURE', 'provenance': 'MOCK_SETTLEMENT_ONLY',
                    'instance_id': self.instance_id, 'source_commit': self.source['commit'],
                    'source_scope': ('13 immutable synthetic settlement views; fixture-v1 plus the '
                                     'CAPITAL-DEMO-BOOK-V1 SYNTHETIC_FIXTURE_PROFILE claims'),
                    'source_cut': None, 'live_completeness': 'NOT_BOUND',
                    'unavailable': ['provider_authorized_amount', 'issued_rights_amount',
                                    'primary_sales', 'resale_sales', 'actual_paid',
                                    'unconfirmed_external_payout', 'tax_reporting'],
                    'rows': rows, 'funds_executed': False, 'durable': False}

    def scenarios(self, scenario_id=None):
        with self.lock:
            common = {'instance_id': self.instance_id, 'source_commit': self.source['commit'],
                      'mode': 'READ_ONLY_SCENARIOS', 'funds_executed': False,
                      'workspace_state_digest': self.machine.state_digest()}
            if scenario_id is not None:
                if scenario_id not in self.scenario_results:
                    raise ApiError('UNKNOWN_SCENARIO', 404)
                return {**common, 'scenario': copy.deepcopy(self.scenario_results[scenario_id])}
            return {**common, 'scenarios': [{'id': row['id'], 'title': row['title'],
                      'description': row['description'], 'steps': len(row['steps']),
                      'all_predicates_matched': row['all_predicates_matched']}
                     for row in self.scenario_results.values()]}

    def _terms_quote(self):
        policy = self.terms.status()
        if policy.get('status') == 'NOT_BOUND':
            return TERMS_NOT_BOUND
        version = policy.get('terms_version') or ''
        return f'PROVISIONAL per docs/decisions/CAPITAL_FINANCIAL_TERMS.md ({version})'

    def _terms_snapshot(self):
        policy = self.terms.status()
        return {
            'status': policy['status'],
            'reason': policy['reason'],
            'terms_version': policy['terms_version'],
        }

    def _terms_decision_line(self):
        return self._terms_quote()

    def _policy_quote(self):
        applied = self.policy.allocation(POLICY)
        version = applied.get('policy_version')
        if applied.get('outcome') == 'NOT_BOUND' or not version:
            return POLICY_NOT_BOUND
        return f'PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md ({version})'

    def _asset_quote(self):
        line = self.decision_index.note_line(UPSTREAM_BINDING_NOTE)
        return (f'KRW declared once as an AssetSpec (fiat/KRW, decimals 0, max_atoms 10^12 fixture bound), '
                f'{line}; any other asset on a command is rejected ASSET_MISMATCH before it is applied; '
                f'asset registry, u128 and FX stay NOT_BOUND')

    def _policy_decision_line(self):
        return self._policy_quote() + ' — ' + POLICY_LABEL

    def _terms_envelope(self, payload):
        return {
            **payload,
            'funds_executed': False,
            'workspace_mutated': False,
            'write_authorized': False,
            'instance_id': self.instance_id,
            'observed_state_digest': self.machine.state_digest(),
        }

    def _require_day(self, value):
        if type(value) is not int or value < 0 or len(str(value)) > 6:
            raise ApiError('INVALID_ARGUMENTS')

    def _require_cash(self, value):
        if type(value) is not int or value < 0 or len(str(value)) > 13:
            raise ApiError('INVALID_ARGUMENTS')

    def _case_gate(self, advance_id, case):
        """Caller holds the lock. Gate from the view; APPROVED peeks at preview_draw."""
        gate = case['settlement_gate']
        if case['phase'] == 'APPROVED':
            try:
                preview = self.producer.preview_draw(advance_id)
            except CreditError:
                preview = None
            if preview is not None:
                gate = preview['credit']['settlement_gate']
        return gate

    def terms_status(self):
        """Read-only policy status. Does not touch receipts or the FSM journal."""
        with self.lock:
            frozen = self._frozen()
            try:
                return self._terms_envelope(self.terms.status())
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def case_terms(self, advance_id, instance_id, draw_day, as_of_day, expected_settlement_cash_day=None):
        """Read-only simulated overlay for one case. Days are hypothetical query inputs."""
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if advance_id not in self.case_fixtures:
                raise ApiError('UNKNOWN_ADVANCE', 404)
            self._require_day(draw_day)
            self._require_day(as_of_day)
            if expected_settlement_cash_day is not None:
                self._require_day(expected_settlement_cash_day)
            frozen = self._frozen()
            try:
                case = self.machine.view(advance_id)
                claim = self.fixtures.view(self.case_fixtures[advance_id])['claim']
                gate = self._case_gate(advance_id, case)
                body = self.terms.overlay(
                    case, claim, draw_day=draw_day, as_of_day=as_of_day,
                    expected_settlement_cash_day=expected_settlement_cash_day, gate=gate)
                body = dict(body)
                body['advance_id'] = advance_id
                return self._terms_envelope(body)
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def case_allocation(self, advance_id, instance_id, *, draw_day, as_of_day, cash, expected_settlement_cash_day=None):
        """Read-only repayment allocation quote. Days and cash are hypothetical query inputs."""
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if advance_id not in self.case_fixtures:
                raise ApiError('UNKNOWN_ADVANCE', 404)
            self._require_day(draw_day)
            self._require_day(as_of_day)
            if expected_settlement_cash_day is not None:
                self._require_day(expected_settlement_cash_day)
            self._require_cash(cash)
            frozen = self._frozen()
            try:
                case = self.machine.view(advance_id)
                claim = self.fixtures.view(self.case_fixtures[advance_id])['claim']
                gate = self._case_gate(advance_id, case)
                body = self.terms.allocation(
                    case, claim, draw_day=draw_day, as_of_day=as_of_day,
                    expected_settlement_cash_day=expected_settlement_cash_day, gate=gate, cash=cash)
                body = dict(body)
                body['advance_id'] = advance_id
                return self._terms_envelope(body)
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def case_setoff(self, advance_id, instance_id, *, draw_day, as_of_day, expected_settlement_cash_day=None):
        """Read-only set-off proposal quote on the bound settlement view. A proposal only; nothing is posted."""
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if advance_id not in self.case_fixtures:
                raise ApiError('UNKNOWN_ADVANCE', 404)
            self._require_day(draw_day)
            self._require_day(as_of_day)
            if expected_settlement_cash_day is not None:
                self._require_day(expected_settlement_cash_day)
            frozen = self._frozen()
            try:
                case = self.machine.view(advance_id)
                claim = self.fixtures.view(self.case_fixtures[advance_id])['claim']
                gate = self._case_gate(advance_id, case)
                body = self.setoff.proposal(
                    case, claim, draw_day=draw_day, as_of_day=as_of_day,
                    expected_settlement_cash_day=expected_settlement_cash_day, gate=gate)
                body = dict(body)
                body['advance_id'] = advance_id
                return self._terms_envelope(body)
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def terms_portfolio(self, instance_id, *, draw_day=None, as_of_day, expected_settlement_cash_day=None):
        """Read-only simulated rollup across every case. Days are hypothetical query inputs."""
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if draw_day is None:
                draw_day, draw_day_source = 0, 'DEFAULT'
            else:
                self._require_day(draw_day)
                draw_day_source = 'QUERY_PARAMETER'
            self._require_day(as_of_day)
            if expected_settlement_cash_day is not None:
                self._require_day(expected_settlement_cash_day)
            frozen = self._frozen()
            try:
                subjects = []
                for advance_id in sorted(self.case_fixtures):
                    case = self.machine.view(advance_id)
                    claim = self.fixtures.view(self.case_fixtures[advance_id])['claim']
                    subjects.append({'advance_id': advance_id, 'case': case, 'claim': claim,
                                     'gate': self._case_gate(advance_id, case)})
                body = self.terms.portfolio(
                    subjects, draw_day=draw_day, draw_day_source=draw_day_source,
                    as_of_day=as_of_day, expected_settlement_cash_day=expected_settlement_cash_day)
                return self._terms_envelope(body)
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def _underwrite_subject(self, advance_id, fixture_id, case, fixture_view, amount, candidate):
        """Caller holds the lock. Collects the read inputs the rule record needs."""
        claim = fixture_view['claim']
        beneficiary = self.fixtures.beneficiary(fixture_id) if candidate else case['beneficiary_role']
        beneficiary_outstanding = 0
        portfolio_outstanding = 0
        sibling_reserved = 0
        for other_id, bound in self.case_fixtures.items():
            view = self.machine.view(other_id)
            portfolio_outstanding += view['outstanding_exposure']
            if view['beneficiary_role'] == beneficiary:
                beneficiary_outstanding += view['outstanding_exposure']
            if bound == fixture_id:
                sibling_reserved = view['reserved_open']
        if candidate:
            return {
                'advance_id': advance_id, 'candidate': True, 'phase': 'CANDIDATE',
                'amount': amount, 'beneficiary_role': beneficiary,
                'settlement_id': fixture_id, 'commit_observed': False,
                'settlement_phase': fixture_view['phase'], 'claim': claim,
                'open_face': sum(line['outstanding'] for line in claim['obligations']),
                'other_reserved': sibling_reserved,
                'beneficiary_outstanding': beneficiary_outstanding,
                'portfolio_outstanding': portfolio_outstanding,
                'incremental': amount,
            }
        own_note = case['amount'] if case['note_status'] == 'NOTED' else 0
        return {
            'advance_id': advance_id, 'candidate': False, 'phase': case['phase'],
            'amount': amount, 'beneficiary_role': beneficiary,
            'settlement_id': case['settlement_id'],
            'commit_observed': case['mock_settlement_commit_observed'],
            'settlement_phase': fixture_view['phase'], 'claim': claim,
            'open_face': case['open_face'],
            'other_reserved': case['reserved_open'] - own_note,
            'beneficiary_outstanding': beneficiary_outstanding,
            'portfolio_outstanding': portfolio_outstanding,
            'incremental': amount if case['drawn_exposure'] == 0 else 0,
        }

    def underwrite(self, advance_id, instance_id, role, *, sim_day=0, amount=None):
        """Read-only simulated decision record. No receipt and no journal write."""
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            self._require_day(sim_day)
            if amount is not None and (type(amount) is not int or amount < 1):
                raise ApiError('INVALID_ARGUMENTS')
            candidate = False
            case = None
            if advance_id in self.case_fixtures:
                case = self.machine.view(advance_id)
                fixture_id = self.case_fixtures[advance_id]
                if amount is not None and amount != case['amount']:
                    raise ApiError('INVALID_ARGUMENTS')
                amount = case['amount']
            elif advance_id in self.fixtures.rows:
                if amount is None:
                    raise ApiError('INVALID_ARGUMENTS')
                candidate = True
                fixture_id = advance_id
            else:
                raise ApiError('UNKNOWN_ADVANCE', 404)
            frozen = self._frozen()
            try:
                fixture_view = self.fixtures.view(fixture_id)
                subject = self._underwrite_subject(
                    advance_id, fixture_id, case, fixture_view, amount, candidate)
                body = self.underwriting.record(subject, decided_by_role=role, sim_day=sim_day)
                return self._terms_envelope(body)
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def _policy_envelope(self, payload):
        return {
            **payload,
            'funds_executed': False,
            'workspace_mutated': False,
            'write_authorized': False,
            'instance_id': self.instance_id,
            'observed_state_digest': self.machine.state_digest(),
        }

    def _comparison_row(self, row_id, kind, order):
        applied = apply_order(STATEMENT['gross'], POLICY, STATEMENT, order)
        return {
            'id': row_id,
            'kind': kind,
            'order': list(applied['order']),
            'per_payee': applied['per_payee'],
            'distributed_cash': applied['distributed_cash'],
            'undistributed_cash': applied['undistributed_cash'],
            'invariants': applied['invariants'],
            'label': POLICY_LABEL,
        }

    def _policy_body(self):
        """Caller holds the lock. Uses disposable books only."""
        applied = self.policy.allocation(POLICY)
        note = self.policy.status()
        outcome = applied['outcome']
        rows = []
        decided = None
        if outcome == 'DECIDED' and applied['order'] is not None:
            decided_order = list(applied['order'])
            rows.append(self._comparison_row(SCENARIO_ID, 'DECIDED', decided_order))
            decided = {
                'id': SCENARIO_ID,
                'order': decided_order,
                'policy_version': applied['alloc_version'],
                'policy_digest': applied['policy_digest'],
                'label': POLICY_LABEL,
            }
        rows.append(self._comparison_row('shortfall-platform', 'FIXTURE', list(ORDER)))
        rows.append(self._comparison_row('shortfall-organizer', 'FIXTURE', list(reversed(ORDER))))
        first = list(applied['order']) if outcome == 'DECIDED' and applied['order'] else list(ORDER)
        attempted = list(reversed(ORDER)) if first == list(ORDER) else list(ORDER)
        freeze = probe_order_freeze(STATEMENT['gross'], POLICY, STATEMENT, first, attempted)
        return {
            'label': POLICY_LABEL,
            'mode': 'SIMULATED_POLICY_APPLICATION',
            'provisional': True,
            'outcome': outcome,
            'policy_version': note['policy_version'],
            'policy_digest': applied['policy_digest'],
            'decided': decided,
            'comparison': rows,
            'order_freeze': {
                'attempted_order': freeze['attempted_order'],
                'refused': freeze['refused'],
                'code': freeze['code'],
                'label': POLICY_LABEL,
            },
            'unsupported': self.policy.unsupported(),
            'upstream_fsm_change_requests': {
                'ownership': 'upstream-owned',
                'items': self.policy.upstream_requests(),
                'label': POLICY_LABEL,
            },
        }

    def policy_status(self):
        """Read-only policy mark. Does not touch receipts or the workspace FSM."""
        with self.lock:
            frozen = self._frozen()
            try:
                applied = self.policy.allocation(POLICY)
                return self._policy_envelope({
                    'label': POLICY_LABEL,
                    'mode': 'SIMULATED_POLICY_APPLICATION',
                    'provisional': True,
                    'policy_version': applied['policy_version'],
                    'policy_digest': applied['policy_digest'],
                    'outcome': applied['outcome'],
                    'reason': applied['reason'],
                })
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def policy_simulation(self):
        """Apply the decided order on disposable books. Workspace digest stays put."""
        with self.lock:
            frozen = self._frozen()
            try:
                return self._policy_envelope(self._policy_body())
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def _shadow_claim_vector(self, claim):
        """Frozen input vector from a pinned view() snapshot. No amounts invented."""
        return {
            'gross': claim['gross'],
            'policy': {'residual_payee': claim['policy']['residual_payee'],
                       'fee_payee': claim['policy']['fee_payee']},
            'obligations': [
                {'payee': row['payee'], 'face': row['face'], 'distributed': row['distributed'],
                 'cancelled_unpaid': row['cancelled_unpaid'], 'outstanding': row['outstanding'],
                 'recovery_due': row['recovery_due']}
                for row in claim['obligations']],
        }

    def _shadow_refund_verdict(self):
        """Per-class shadow of the pinned partial-after view's open refund face."""
        if self.shadow.outcome != 'BOUND':
            return self.shadow.deferred('refund_bearer', None)
        claim = self.scenario_results['partial-after']['final']
        vector = self._shadow_claim_vector(claim)
        per_class = []
        for row in self.shadow.refund_classes():
            variants = [False, True] if row['working_assumption'] else [False]
            for adjudicated in variants:
                refund_id = 'shadow-sim-' + row['id'] + ('-adjudicated' if adjudicated else '')
                result = self.shadow.refund({**vector, 'refunds': [{
                    'refund_id': refund_id, 'amount': claim['refund_face'],
                    'reason_class': row['id'], 'evidence_ref': 'SIMULATED',
                    'adjudicated_platform_fault': adjudicated}]})
                per_class.append(result)
        verdict = {
            'status': 'SHADOW_COMPUTED' if all(
                item['status'] in ('SHADOW_COMPUTED', 'SHADOW_INPUT_UNKNOWN') for item in per_class)
            else 'SHADOW_INCONSISTENT',
            'detail': None,
            'mode': SHADOW_MODE, 'label': SHADOW_LABEL, 'provenance': SHADOW_PROVENANCE,
            'shadow_rules_version': self.shadow.status()['shadow_rules_version'],
            'note_digest': self.shadow.note_digest,
            'source': {'kind': 'PINNED_VIEW_SNAPSHOT', 'claim_id': claim['claim_id'],
                       'scenario': 'partial-after'},
            'per_class': per_class,
        }
        verdict.update({name: False for name in (
            'applied_to_fsm', 'funds_executed', 'policy_adopted', 'bank_debit_observed',
            'right_cancelled', 'external_return_closed', 'legal_debtor_bound',
            'admission_granted', 'workspace_mutated')})
        return verdict

    def _shadow_resale_verdict(self):
        """Shadow unwind of the note's synthetic worked resale example vectors."""
        if self.shadow.outcome != 'BOUND':
            return self.shadow.deferred('resale_prior_contract_cancel_burden', None)
        claim = self.fixtures.view('sim-committed')['claim']
        primary = self._shadow_claim_vector(claim)
        triggers = []
        for item in self.shadow.worked_resale_vectors():
            vector = {**item['vector'], 'primary': primary}
            result = self.shadow.resale(vector)
            result['vector_id'] = item['id']
            triggers.append(result)
        status = 'SHADOW_COMPUTED' if triggers and all(
            row['status'] == 'SHADOW_COMPUTED' for row in triggers) else 'SHADOW_INCONSISTENT'
        verdict = {
            'status': status, 'detail': None,
            'mode': SHADOW_MODE, 'label': SHADOW_LABEL, 'provenance': SHADOW_PROVENANCE,
            'shadow_rules_version': self.shadow.status()['shadow_rules_version'],
            'note_digest': self.shadow.note_digest,
            'source': {'kind': 'NOTE_SYNTHETIC_LITERALS',
                       'note': 'docs/decisions/CAPITAL_SETTLEMENT_POLICY.md',
                       'primary_claim_id': claim['claim_id']},
            'triggers': triggers,
        }
        verdict.update({name: False for name in (
            'applied_to_fsm', 'funds_executed', 'policy_adopted', 'bank_debit_observed',
            'right_cancelled', 'external_return_closed', 'legal_debtor_bound',
            'admission_granted', 'workspace_mutated')})
        return verdict

    _SHADOW_DEFERRED_DETAIL = (
        'out of scope for this node: the decision keeps the parts needing a logical clock, '
        'a slice registry or a multi-claim base deferred; this endpoint computes only the '
        'refund-bearer classes and the resale unwind')

    def _shadow_body(self):
        """Side-by-side pinned and shadow verdicts for the unsupported items."""
        items = []
        for row in self.policy.unsupported():
            name = row['item']
            if name == 'refund_bearer':
                verdict = self._shadow_refund_verdict()
            elif name == 'resale_prior_contract_cancel_burden':
                verdict = self._shadow_resale_verdict()
            else:
                verdict = self.shadow.deferred(name, self._SHADOW_DEFERRED_DETAIL)
            items.append({'item': name, 'pinned': row, 'shadow': verdict})
        bound = self.shadow.outcome == 'BOUND'
        body = {
            'label': SHADOW_LABEL,
            'mode': SHADOW_MODE,
            'provenance': SHADOW_PROVENANCE,
            'provisional': True,
            'shadow_rules_version': 'CAPITAL-SHADOW-V1',
            'policy_version': self.shadow.policy_version,
            'note_digest': self.shadow.note_digest,
            'outcome': 'SHADOW_COMPUTED' if bound else 'SHADOW_NOT_BOUND',
            'reason': None if bound else self.shadow.reason,
            'items': items,
            'applied_to_fsm': False,
            'policy_adopted': False,
            'bank_debit_observed': False,
            'right_cancelled': False,
            'external_return_closed': False,
            'legal_debtor_bound': False,
            'admission_granted': False,
        }
        return body

    def policy_shadow(self):
        """Shadow arithmetic on frozen input vectors. Nothing is applied."""
        with self.lock:
            frozen = self._frozen()
            try:
                return self._policy_envelope(self._shadow_body())
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def decisions(self):
        """Read-only index of the decision notes. Does not touch receipts or the workspace FSM."""
        with self.lock:
            frozen = self._frozen()
            try:
                return self._terms_envelope(self.decision_index.body())
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def readiness(self):
        with self.lock:
            terms_note = self._terms_quote()
            policy_note = self._policy_quote()
            groups = resolve_note_blockers(copy.deepcopy(GROUPS), self.decision_index.note_line)
            return {'instance_id': self.instance_id, 'mode': 'LOCAL_READINESS_ONLY',
                    'source_commit': self.source['commit'], 'upstream_binding': 'NOT_BOUND',
                    'source_integrity': source_integrity(VENDOR, self.source),
                    'groups': groups, 'production_authorized': False,
                    'upstream_nodes_completed': [], 'policy_adopted': False,
                    'requirement_notes': {
                        'CAP-01': terms_note,
                        'CAP-02': policy_note,
                        'CAP-03': policy_note,
                        'CAP-04': terms_note,
                        'CAP-05': policy_note,
                        'CAP-06': policy_note,
                        'CAP-09': 'local five-category statement only; primary_sales, resale_sales and actual_paid stay NOT_BOUND and are never summed',
                        'CAP-12': self._asset_quote(),
                        'CAP-13': 'local candidate projection; fin-ledger-contract still upstream',
                        'CAP-14': 'local reconciliation diagnostics only; no bank reconciliation or provider-authenticated completeness',
                        'CAP-15': 'local hashed manifest and SignaturePort only; not stage7 authenticated export; no external key, cross-service cursor, watermark, or retention duration; retention_policy names five empty owner slots',
                        'CAP-16': 'local facade contract capital-local-facade/1 at capital/contract/facade-v1.json; producer vectors are not SEMANTIC_CONFORMANCE; exact producer/SDK tuple stays NOT_BOUND'}}

    def projection(self, mode=None):
        """Fold copies of the accepted journal and fixture views. Nothing is cached or written."""
        with self.lock:
            if mode not in (None, 'simulation'):
                raise ApiError('NOT_BOUND', 400)
            before_canon = self.machine.canonical_state()
            before_receipts = copy.deepcopy(self.receipts)
            before_rows = copy.deepcopy(self.fixtures.rows)
            journal = self.machine.export_journal()
            evidence = [self.fixtures.view(key) for key in sorted(self.fixtures.projection_ids)]
            cut = self.machine.state_digest()
            try:
                projected = self.projection_port.project(journal, evidence)
            except ProjectionError as exc:
                raise ApiError(exc.code, 500) from exc
            if (self.machine.canonical_state() != before_canon or self.receipts != before_receipts
                    or self.fixtures.rows != before_rows or self.machine.state_digest() != cut
                    or len(self.receipts) != len(before_receipts)):
                raise ApiError('PROJECTION_INVARIANT', 500)
            return {'instance_id': self.instance_id, 'mode': 'LOCAL_PROJECTION_CANDIDATE',
                    'chart': SimulationProjection.CHART_VERSION,
                    'accounting_policy': 'SYNTHETIC_UNADOPTED', 'tax': 'NOT_BOUND', 'legal': 'NOT_BOUND',
                    'cut': cut, 'source_commit': self.source['commit'], 'funds_executed': False,
                    'policy_adopted': False, 'workspace_mutated': False, 'operating_ledger': 'NOT_BOUND',
                    'entries': projected['entries'], 'accounts': projected['accounts'],
                    'read_model': projected['read_model'], 'conservation': projected['conservation']}

    def preview_draw(self, advance_id, instance_id):
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if advance_id not in self.case_fixtures:
                raise ApiError('UNKNOWN_ADVANCE', 404)
            case = self.machine.view(advance_id)
            result = {'instance_id': self.instance_id, 'advance_id': advance_id,
                      'mode': 'READ_ONLY_PREVIEW', 'provenance': PROVENANCE,
                      'observed_state_digest': self.machine.state_digest(),
                      'funds_executed': False, 'workspace_mutated': False,
                      'write_authorized': False, 'settlement_gate': case['settlement_gate']}
            if case['phase'] != 'APPROVED':
                return {**result, 'outcome': 'NOT_APPLICABLE', 'reason': 'APPROVED_PHASE_REQUIRED'}
            # Replay only into a disposable process-local copy. No active receipt/key
            # or reservation is added; the actual command must re-evaluate its gates.
            try:
                preview = self.producer.preview_draw(advance_id)
                return {**result, 'outcome': 'WOULD_ACCEPT',
                        'predicted_exposure': preview['credit']['outstanding_exposure'],
                        'settlement_gate': preview['credit']['settlement_gate']}
            except CreditError as exc:
                return {**result, 'outcome': 'WOULD_REJECT', 'reason': exc.code}

    def agent_query(self, body, role=DEFAULT_ROLE):
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_QUERY)
            frozen = self._machine_frozen()
            try:
                return self._agent_call(lambda: self.agent_lane.query_grant(body))
            finally:
                self._machine_same(frozen)

    def agent_propose(self, body, role=DEFAULT_ROLE):
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_PROPOSE)
            frozen = self._machine_frozen()
            try:
                return self._agent_call(lambda: self.agent_lane.propose_action(body))
            finally:
                self._machine_same(frozen)

    def agent_query_subject(self, body, role=DEFAULT_ROLE):
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_QUERY_SUBJECT)
            frozen = self._machine_frozen()
            try:
                return self._agent_call(lambda: self.agent_lane.query_subject(body))
            finally:
                self._machine_same(frozen)

    def agent_withdraw_proposal(self, body, role=DEFAULT_ROLE):
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_WITHDRAW)
            frozen = self._machine_frozen()
            try:
                return self._agent_call(lambda: self.agent_lane.withdraw_proposal(body))
            finally:
                self._machine_same(frozen)

    def agent_propose_grant_change(self, body, role=DEFAULT_ROLE):
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_PROPOSE_CHANGE)
            frozen = self._machine_frozen()
            try:
                return self._agent_call(lambda: self.agent_lane.propose_grant_change(body))
            finally:
                self._machine_same(frozen)

    def agent_execute(self, body, role=DEFAULT_ROLE):
        """An EXECUTE attempt. The body is ignored and nothing is written."""
        del body
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, AGENT_PROPOSE)
            frozen = self._machine_frozen()
            proposals = len(self.agent_lane.proposals)
            try:
                self.agent_lane.refuse_execute()
            except AgentLaneError as exc:
                _agent_api_error(exc.code, principal.role)
            finally:
                self._machine_same(frozen)
                if len(self.agent_lane.proposals) != proposals:
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def _agent_call(self, call):
        try:
            return call()
        except AgentLaneError as exc:
            _agent_api_error(exc.code)

    def _machine_frozen(self):
        return (self.machine.state_digest(), self.machine.canonical_state(), len(self.receipts))

    def _machine_same(self, frozen):
        if self._machine_frozen() != frozen:
            raise ApiError('READ_ONLY_INVARIANT', 500)

    def execute(self, body, role=DEFAULT_ROLE):
        with self.lock:
            if type(body) is not dict:
                raise ApiError('INVALID_COMMAND')
            allowed = {'instance_id', 'operation_id', 'op', 'advance_id', 'args'}
            if set(body) - {'proposal_id', 'asset'} != allowed or not allowed <= set(body):
                raise ApiError('INVALID_COMMAND')
            # Before instance and idempotency lookups, so a denied role cannot read
            # another role's receipt by replaying its operation_id.
            principal = Principal(role if type(role) is str else '')
            op = body['op']
            if type(op) is str and op in OP_PERMISSIONS:
                require(self.authorizer, principal, OP_PERMISSIONS[op])
            else:
                require(self.authorizer, principal, 'command:submit')
            if self.workspace_status != 'ACTIVE':
                raise ApiError(self.workspace_status, 503)
            if body['instance_id'] != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            # The optional asset must equal the one declared spec. A mismatch is a boundary
            # error like INVALID_COMMAND: before the fingerprint and receipt lookup, so no
            # journal entry, receipt or idempotency record exists for it. After the
            # authorizer, so a denied role learns nothing from validation. asset is not in
            # the fingerprint: only one value is ever accepted, so it cannot conflict.
            if 'asset' in body and not asset_matches(body['asset']):
                raise ApiError('ASSET_MISMATCH')
            operation_id = body['operation_id']
            if type(operation_id) is not str or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', operation_id):
                raise ApiError('INVALID_OPERATION_ID')
            # Instance id authorizes the session. proposal_id is a citation, not identity.
            # A bad citation is rejected before the fingerprint, which stays
            # operation_id, op, advance_id, and args. Observability counters are not inputs.
            if 'proposal_id' in body and not agent_ident(body['proposal_id']):
                raise ApiError('INVALID_ARGUMENTS')
            fingerprint = digest({'operation_id': operation_id, 'op': body['op'],
                                  'advance_id': body['advance_id'], 'args': body['args']})
            prior = self.receipts.get(operation_id)
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise ApiError('IDEMPOTENCY_CONFLICT', 409)
                result = copy.deepcopy(prior['receipt'])
                result['transport_duplicate'] = True
                self._note_receipt(body['op'], result)
                return result
            if len(self.receipts) >= MAX_OPERATIONS:
                raise ApiError('SIMULATION_CAPACITY', 409)
            op, case, args = body['op'], body['advance_id'], body['args']
            if type(op) is not str or op not in OPS:
                self.observability.record_command(op if type(op) is str else None, 'REJECTED', None)
                raise ApiError('UNSUPPORTED_OPERATION')
            if type(case) is not str or not re.fullmatch(r'sim-[a-zA-Z0-9-]{1,60}', case):
                raise ApiError('SYNTHETIC_ID_REQUIRED')
            if type(args) is not dict or set(args) != OPS[op]:
                raise ApiError('INVALID_ARGUMENTS')
            cited = None
            if 'proposal_id' in body:
                try:
                    cited = self.agent_lane.reference(op, args, body['proposal_id'])
                except AgentLaneError as exc:
                    _agent_api_error(exc.code)
            receipt = {'operation_id': operation_id, 'instance_id': self.instance_id,
                       'provenance': PROVENANCE, 'funds_executed': False,
                       'economic_finality_claimed': False, 'transport_duplicate': False,
                       'role': principal.role, 'role_provenance': ROLE_PROVENANCE}
            if cited is not None:
                receipt['proposal_id'] = cited
            try:
                bound = None
                if op == 'bind_settlement':
                    if case not in self.case_fixtures:
                        raise CreditError('UNKNOWN_ADVANCE')
                    bound = self.case_fixtures[case]
                result = self.producer.apply(
                    op, case, idempotency_key=operation_id, args=args, bound_settlement_id=bound)
                if op == 'offer':
                    self.case_fixtures[case] = args['fixture_id']
                receipt.update(outcome='ACCEPTED', result=result)
            except CreditError as exc:
                receipt.update(outcome='REJECTED', error=exc.code)
            self.receipts[operation_id] = {'fingerprint': fingerprint, 'receipt': copy.deepcopy(receipt)}
            try:
                self._persist()
            except WorkspaceError as exc:
                self.workspace_status = exc.code
                raise ApiError(exc.code, 503)
            self._note_receipt(op, receipt)
            return receipt

    def _note_receipt(self, op, receipt):
        """Count one returned receipt. A persist failure never reaches this."""
        outcome = receipt.get('outcome') if type(receipt) is dict else None
        code = None
        if outcome == 'REJECTED' and type(receipt) is dict:
            error = receipt.get('error')
            if type(error) is str:
                code = error
        self.observability.record_command(op, outcome, code)

    def operation(self, operation_id, instance_id):
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            stored = self.receipts.get(operation_id)
            if stored is None:
                self.observability.record_lookup('UNKNOWN')
                return {'outcome': 'UNKNOWN', 'operation_id': operation_id,
                        'instance_id': self.instance_id, 'retry_authorized': False}
            self.observability.record_lookup('KNOWN')
            return copy.deepcopy(stored['receipt'])

    def metrics(self):
        """Process-local counters. The read does not write a receipt or the digest."""
        with self.lock:
            frozen = self._frozen()
            try:
                view = self.workspace_view()
                observed = self.observability.snapshot()
                return {
                    'mode': 'LOCAL_OBSERVABILITY',
                    'label': 'SIMULATED',
                    'instance_id': self.instance_id,
                    'version': __version__,
                    'uptime_seconds': observed['uptime_seconds'],
                    'workspace': {'kind': view['kind'], 'status': view['status']},
                    'counters': observed['counters'],
                    'latency_ms': observed['latency_ms'],
                    'external_exporters': 'NOT_BOUND',
                    'tracing': 'NOT_BOUND',
                    'alerting': 'NOT_BOUND',
                    'network_sinks': 'NOT_BOUND',
                    'funds_executed': False,
                }
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def health(self):
        """Minimal liveness. The read does not write a receipt or the digest."""
        with self.lock:
            frozen = self._frozen()
            try:
                return {
                    'status': 'ok' if self.workspace_status == 'ACTIVE' else 'degraded',
                    'uptime_seconds': self.observability.uptime_seconds(),
                    'workspace_status': self.workspace_status,
                    'mode': 'LOCAL_OBSERVABILITY',
                }
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def _replay_journal(self):
        """Caller holds the service lock. Restores a scratch machine and does not write."""
        journal = self.producer.export_journal()
        restored = self.producer.restored(journal)
        try:
            matched = restored.canonical_state() == self.producer.canonical_state()
        finally:
            if restored is not self.producer:
                _release_producer(restored)
        return journal, matched

    def _frozen(self):
        return (
            json.dumps(self.receipts, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode(),
            self.machine.state_digest(),
            len(self.receipts),
            self.machine.canonical_state(),
            digest(self.fixtures.rows),
        )

    def _same_frozen(self, frozen):
        return self._frozen() == frozen

    def _subject_payload(self):
        """Checksum-valid workspace payload when one exists; otherwise the live book."""
        try:
            document = self.storage.load()
        except WorkspaceError as exc:
            return None, exc.code
        if document is None:
            return {
                'receipts': copy.deepcopy(self.receipts),
                'journal': self.machine.export_journal(),
                'case_fixtures': copy.deepcopy(dict(self.case_fixtures)),
                'state_digest': self.machine.state_digest(),
            }, None
        return copy.deepcopy(document['payload']), None

    def reconciliation(self, probe_operation_id=None):
        """Read-only exception report. No receipt is written and nothing is retried."""
        with self.lock:
            frozen = self._frozen()
            try:
                payload, unreadable = self._subject_payload()
                rows = copy.deepcopy(self.fixtures.rows)
                return build_reconciliation(
                    payload=payload, unreadable=unreadable, fixture_rows=rows,
                    fixtures_digest=digest(rows), settlement_source=self.fixtures,
                    projection_port=self.projection_port, probe_operation_id=probe_operation_id,
                    instance_id=self.instance_id, operation_capacity=MAX_OPERATIONS,
                    workspace_status=self.workspace_status,
                )
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def statement(self):
        """Read-only five-category statement. Primary and resale sales are not summed."""
        with self.lock:
            frozen = self._frozen()
            try:
                cases = [self.machine.view(key) for key in sorted(self.case_fixtures)]
                fixtures = [self.fixtures.view(key) for key in sorted(self.fixtures.rows)]
                rows = copy.deepcopy(self.fixtures.rows)
                return build_statement(
                    cases=cases, fixture_views=fixtures, fixtures_digest=digest(rows),
                    state_digest=self.machine.state_digest(), instance_id=self.instance_id,
                    operation_capacity=MAX_OPERATIONS, workspace_status=self.workspace_status,
                )
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)

    def export(self):
        with self.lock:
            journal, matched = self._replay_journal()
            durable = self.storage.durable_label
            if durable == 'LOCAL_FILE_WORKSPACE':
                note = ('Accepted commands from an opt-in local file workspace. Rejected receipts are not in the Protocol journal. '
                        'durable=LOCAL_FILE_WORKSPACE is a development workspace file, not stage5 durable transaction recovery, inbox/outbox, or cross-host fencing.')
            else:
                note = ('Accepted in-memory commands only. Rejected receipts are not in the Protocol journal. No bank reconciliation or durable recovery. '
                        'An opt-in LOCAL_FILE_WORKSPACE file is not stage5 durable transaction recovery.')
            return {'format': 'KIX_CAPITAL_SIMULATION_V1', 'instance_id': self.instance_id,
                    'provenance': PROVENANCE, 'source': self.source,
                    'fixtures_digest': digest(self.fixtures.rows), 'journal': journal,
                    'state_digest': self.machine.state_digest(),
                    'replay_matched': matched,
                    'durable': durable, 'funds_executed': False, 'note': note}

    def export_manifest(self):
        """Read-only v2 manifest of hashed sections. No import, resume, or key material."""
        with self.lock:
            frozen = self._frozen()
            try:
                journal, _matched = self._replay_journal()
                projection = self.projection(None)
                reconciliation = self.reconciliation()
                statement = self.statement()
                rows = copy.deepcopy(self.fixtures.rows)
                sections = {
                    'journal': {'label': 'SIMULATED', 'entries': copy.deepcopy(journal)},
                    'receipts': {'label': 'SIMULATED', 'receipts': copy.deepcopy(self.receipts)},
                    'projection': copy.deepcopy(projection),
                    'reconciliation': copy.deepcopy(reconciliation),
                    'statement': copy.deepcopy(statement),
                    'fixtures': {
                        'label': 'READ_ONLY_FIXTURE',
                        'fixtures_digest': digest(rows),
                        'rows': rows,
                    },
                    'source_pin': {
                        'label': 'READ_ONLY_FIXTURE',
                        'commit': self.source['commit'],
                        'repository': self.source['repository'],
                        'files': copy.deepcopy(self.source['files']),
                        'integrity': source_integrity(VENDOR, self.source),
                        'assets': declared_assets(),
                    },
                }
                status, reasons = manifest_status(reconciliation['status'], self.workspace_status)
                return build_manifest(
                    sections=sections, instance_id=self.instance_id, signer=self.signer,
                    status=status, incomplete_reasons=reasons,
                )
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)
