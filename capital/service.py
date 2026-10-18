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
from capital import coa, margin, overlay
from capital.agent_lane import AgentLane, AgentLaneError, ident as agent_ident
from capital.auth import (
    AGENT_PROPOSE, AGENT_PROPOSE_CHANGE, AGENT_QUERY, AGENT_QUERY_SUBJECT, AGENT_WITHDRAW,
    DEFAULT_ROLE, OP_PERMISSIONS, OVERLAY_COMMAND, PROVENANCE as ROLE_PROVENANCE,
    ROLES, UNLABELED, Principal, require, LocalRoleAuthorizer,
)
from capital.observability import Observability
from capital.decisions import DecisionIndex
from capital.export import VOLATILE_KEYS, UnsignedSigner, build_manifest, manifest_status
from capital.producer import CreditError, PinnedFsmProducer
from capital.projection import ProjectionError, SimulationProjection
from capital.protocol import VENDOR, MockSettlement
from capital.recon import build_reconciliation
from capital.policy import (
    POLICY_LABEL, POLICY_NOT_BOUND, SCENARIO_ID, DecisionNoteSettlementPolicy,
    apply_order, probe_order_freeze,
)
from capital.scenarios import ORDER, POLICY, STATEMENT, definitions, replay_scenarios
from capital.shadow import DecisionNoteShadow, SHADOW_LABEL, SHADOW_MODE, SHADOW_PROVENANCE
from capital.statement import build_statement
from capital.setoff import DecisionNoteSetoff
from capital.terms import TERMS_NOT_BOUND, DecisionNoteTermsPolicy
from capital.underwriting import DecisionNoteUnderwriting
from capital.readiness import GROUPS, UPSTREAM_BINDING_NOTE, resolve_note_blockers, source_integrity
from capital.resources import vendor_manifest
from capital.store import InMemoryStorage, WorkspaceError, overlay_section, verify_document

PROVENANCE = 'MOCK_CREDIT_F04_ONLY'
OVERLAY_LABEL = 'SIMULATED memo ledger — not a payment, not a receivable, not an F04 journal entry'
CAPACITY_LABEL = 'DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY'
_REASON_MAX = 120  # a reason is a short note; the entry byte bound still applies
_OVERLAY_TERMS = ('interest_rate', 'term', 'default_loss_treatment')
_OVERLAY_ID = re.compile(r'[a-zA-Z0-9-]{1,80}\Z')
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
    def __init__(self, storage=None, authorizer=None, signer=None, *, projection=None, coa_projection=None, producer=None, terms=None, policy=None, underwriting=None, setoff=None, observability=None, decisions=None, shadow=None, overlay_bounds=None):
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
        self.coa_projection = coa_projection if coa_projection is not None else coa.CoaCandidateProjection()
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
        self.overlay_entries = []
        self.overlay_bounds = overlay_bounds if overlay_bounds is not None else overlay.load_bounds()
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
            self.overlay_entries = []
            return
        restored, self.receipts, self.case_fixtures, self.overlay_entries = installed
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
            entries = self._restore_overlay(document, len(journal))
        except Exception:
            if restored is not None and restored is not self.producer:
                _release_producer(restored)
            raise
        return restored, labeled, mapping_copy, entries

    def _restore_overlay(self, document, journal_length):
        """FOLD_THEN_VERIFY. A legacy v1 record is an empty overlay; a broken section is fatal, never repaired."""
        section = overlay_section(document)
        if section is None:
            return []
        try:
            return overlay.restore(section, journal_length)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc

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

    def _persist(self, entries=None):
        entries = self.overlay_entries if entries is None else entries
        payload = {
            'receipts': self.receipts, 'journal': self.machine.export_journal(),
            'case_fixtures': dict(self.case_fixtures), 'state_digest': self.machine.state_digest()}
        if entries:
            self.storage.save(payload, overlay=overlay.build_section(entries))
        else:
            self.storage.save(payload)

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

    def _shadow_item_verdict(self, item, vectors):
        """Computed vectors plus the note's deferred rows, each with its unblock seam."""
        reason = self.shadow.item_binding(item)
        if reason is not None:
            return self.shadow.not_bound(reason)
        results = [self._shadow_run(item, vector) for vector in vectors]
        verdict = self.shadow.not_bound(None)
        verdict.update({
            'status': 'SHADOW_COMPUTED' if results and all(
                row['status'] == 'SHADOW_COMPUTED' for row in results) else 'SHADOW_INCONSISTENT',
            'detail': None,
            'shadow_rules_version': self.shadow.status()['shadow_rules_version'],
            'vectors': results,
            'deferred': self.shadow.deferred_rows(item),
        })
        return verdict

    def _shadow_run(self, item, vector):
        method = {'revenue_participation': self.shadow.participation,
                  'claim_purchase': self.shadow.claim_purchase,
                  'residual_and_late_cash': self.shadow.residual_partition}[item]
        return method(vector)

    @staticmethod
    def _shadow_uc_vector(vector_id, source, view):
        return {
            'vector_id': vector_id, 'input_source': source,
            'confirmed_cash': view['confirmed_cash'],
            'undistributed_cash': view['undistributed_cash'],
            'refund_outstanding': view['refund_outstanding'],
            'reclassified': view['fixture_reclassified'],
            'pg_adjustment_outstanding': view['pg_adjustment_outstanding'],
            'obligations': [
                {'face': row['face'], 'distributed': row['distributed'],
                 'cancelled_unpaid': row['cancelled_unpaid'], 'outstanding': row['outstanding']}
                for row in view['obligations']],
        }

    def _shadow_late_cash_accepted_view(self):
        """late-cash replayed on a disposable book, then a full mock cancel acceptance."""
        late = next(row for row in definitions() if row[0] == 'late-cash')
        book = MockSettlement()
        claim_id = 'sim-lab-late-cash-accepted'
        book.recognize_claim(claim_id, trade_id='sim-lab-trade', gross=100_000,
                             debtor_role='fixture-merchant', policy=POLICY)
        for command in late[3]:
            getattr(book, command['op'])(claim_id, **copy.deepcopy(command['args']))
        book.observe_mock_cancel_acceptance(claim_id, source_id='sim-accept-late', amount=100_000)
        return book.view(claim_id)

    def _shadow_participation_verdict(self):
        vectors = [{**(row['inputs'] or {}), 'paid_to_date': 0, 'vector_id': row['id'],
                    'input_source': 'NOTE_VECTOR_FIRST_POSTING_NO_STORED_STATE'}
                   for row in self.shadow.note_vectors('revenue_participation')]
        return self._shadow_item_verdict('revenue_participation', vectors)

    def _shadow_claim_purchase_verdict(self):
        vectors = [{**(row['inputs'] or {}), 'vector_id': row['id'],
                    'input_source': 'NOTE_SYNTHETIC_VECTOR'}
                   for row in self.shadow.note_vectors('claim_purchase')]
        return self._shadow_item_verdict('claim_purchase', vectors)

    def _shadow_residual_verdict(self):
        if self.shadow.item_binding('residual_and_late_cash') is not None:
            return self._shadow_item_verdict('residual_and_late_cash', [])
        overpay_rows = [{'face': 95_000, 'distributed': 95_000, 'cancelled_unpaid': 0, 'outstanding': 0},
                        {'face': 5_000, 'distributed': 5_000, 'cancelled_unpaid': 0, 'outstanding': 0}]
        vectors = [
            self._shadow_uc_vector('V-UC-split-statement', 'PINNED_VIEW_SNAPSHOT:split-statement:step3',
                                   self.scenario_results['split-statement']['steps'][2]['view']),
            self._shadow_uc_vector('V-UC-late-cash-open-refund', 'PINNED_VIEW_SNAPSHOT:late-cash:final',
                                   self.scenario_results['late-cash']['final']),
            self._shadow_uc_vector('V-UC-late-cash-accepted',
                                   'DISPOSABLE_REPLAY:late-cash+full-mock-acceptance',
                                   self._shadow_late_cash_accepted_view()),
            {'vector_id': 'V-UC-overpay', 'input_source': 'SYNTHETIC_LITERAL',
             'confirmed_cash': 101_000, 'undistributed_cash': 1_000, 'refund_outstanding': 0,
             'reclassified': False, 'pg_adjustment_outstanding': 0, 'obligations': overpay_rows},
        ]
        return self._shadow_item_verdict('residual_and_late_cash', vectors)

    def _shadow_body(self):
        """Side-by-side pinned and shadow verdicts for the unsupported items."""
        items = []
        for row in self.policy.unsupported():
            name = row['item']
            if name == 'refund_bearer':
                verdict = self._shadow_refund_verdict()
            elif name == 'resale_prior_contract_cancel_burden':
                verdict = self._shadow_resale_verdict()
            elif name == 'revenue_participation':
                verdict = self._shadow_participation_verdict()
            elif name == 'claim_purchase':
                verdict = self._shadow_claim_purchase_verdict()
            elif name == 'residual_and_late_cash':
                verdict = self._shadow_residual_verdict()
            else:
                verdict = self.shadow.deferred(name, None)
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
            if mode == coa.MODE:
                return self._projection_coa()
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

    def _projection_coa(self):
        """Additive CAPITAL-COA-V1 candidate. Folds copies; V1 output and state are untouched."""
        with self.lock:
            frozen = self._frozen()
            try:
                journal = self.machine.export_journal()
                evidence = [self.fixtures.view(key) for key in sorted(self.fixtures.projection_ids)]
                cut = self.machine.state_digest()
                try:
                    projected = self.coa_projection.project(
                        journal, evidence, overlay_entries=copy.deepcopy(self.overlay_entries))
                except ProjectionError as exc:
                    raise ApiError(exc.code, 500) from exc
                return {'instance_id': self.instance_id, 'mode': 'LOCAL_PROJECTION_COA_CANDIDATE',
                        'chart': coa.CHART_VERSION, 'coa_version': coa.COA_VERSION,
                        'accounting_policy': 'SYNTHETIC_UNADOPTED', 'tax': 'NOT_BOUND', 'legal': 'NOT_BOUND',
                        'cut': cut, 'source_commit': self.source['commit'], 'funds_executed': False,
                        'policy_adopted': False, 'workspace_mutated': False, 'operating_ledger': 'NOT_BOUND',
                        **projected}
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('PROJECTION_INVARIANT', 500)

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

    # ------------------------------------------------------------ overlay ledger

    def _overlay_terms(self):
        """The terms status when the ledger can accrue from it, else None (NOT_BOUND)."""
        status = self.terms.status()
        items = status.get('items') or {}
        usable = (status.get('status') in ('BOUND', 'PARTIAL') and type(status.get('terms_version')) is str
                  and callable(getattr(self.terms, 'ledger_terms', None))
                  and all(items.get(name) == 'ADOPTED' for name in _OVERLAY_TERMS)
                  and self.overlay_bounds is not None)
        return status if usable else None

    def _overlay_not_bound(self, reason=TERMS_NOT_BOUND):
        return ApiError('NOT_BOUND', 400, {'reason': reason})

    def _overlay_subjects(self, entries):
        """One subject per drawn advance. Tier comes from the accepted draw receipt's gate."""
        draws = {}
        for index, row in enumerate(self.machine.export_journal()):
            if row['op'] == 'draw':
                draws[row['advance_id']] = (index, row['idempotency_key'])
        subjects = []
        for advance_id in sorted(draws):
            index, key = draws[advance_id]
            case = self.machine.view(advance_id)
            try:
                gate = self.receipts[key]['receipt']['result']['credit']['settlement_gate']
            except (KeyError, TypeError):
                raise self._overlay_not_bound('draw receipt gate not found')
            claim = self.fixtures.view(self.case_fixtures[advance_id])['claim']
            draw_day = overlay.draw_day_for(entries, index)
            subjects.append({'advance_id': advance_id, 'case': case, 'claim': claim, 'gate': gate,
                             'draw_day': draw_day, 'principal': case['outstanding_exposure']})
        return subjects

    def _margin_subjects(self, drawn):
        """Drawn advances that carry margin terms; the rest are NOT_BOUND for the margin rules."""
        provider = getattr(self.terms, 'margin_terms', None)
        if not callable(provider):
            return []
        out = []
        for subject in drawn:
            terms = provider(subject['case'], subject['claim'], gate=subject['gate'], draw_day=subject['draw_day'],
                             refund_after_draw=margin.views_mutable(self.fixtures))
            if terms is not None:
                out.append({**subject, 'margin': terms})
        return out

    def _overlay_volatile(self, value, top=True):
        """Volatile keys would be stripped from digests, leaving data uncovered. instance_id is the one
        top-level session key the command body must carry; it is never written into an entry."""
        if type(value) is dict:
            for key, item in value.items():
                if key in VOLATILE_KEYS and not (top and key == 'instance_id'):
                    raise ApiError('OVERLAY_VOLATILE_KEY')
                self._overlay_volatile(item, False)
        elif type(value) is list:
            for item in value:
                self._overlay_volatile(item, False)

    def _overlay_capacity(self, entries):
        bounds = self.overlay_bounds
        records = sum(1 for entry in entries if entry['kind'] == overlay.KIND_TERMS)
        return {
            'label': CAPACITY_LABEL,
            'entries': {'current': len(entries), 'max': bounds['OVERLAY_MAX_ENTRIES']},
            'entry_max_bytes': bounds['OVERLAY_ENTRY_MAX_BYTES'],
            'sim_day_max': bounds['SIM_DAY_MAX'],
            'max_step_days': bounds['max_step_days'],
            'decision_records': {'current': records, 'max': bounds['DECISION_RECORDS_MAX']},
            'agent_proposals': {'current': 0, 'max': bounds['AGENT_PROPOSALS_MAX']},
            'envelope_max_bytes': bounds['ENVELOPE_MAX_BYTES'],
        }

    def _overlay_check_capacity(self, entries, new, to_day, payload):
        bounds = self.overlay_bounds
        if to_day > bounds['SIM_DAY_MAX']:
            raise ApiError('SIMULATION_CAPACITY', 409, {'bound': 'SIM_DAY_MAX'})
        merged = entries + new
        if len(merged) > bounds['OVERLAY_MAX_ENTRIES']:
            raise ApiError('SIMULATION_CAPACITY', 409, {'bound': 'OVERLAY_MAX_ENTRIES'})
        if any(overlay.entry_size(entry) > bounds['OVERLAY_ENTRY_MAX_BYTES'] for entry in new):
            raise ApiError('SIMULATION_CAPACITY', 409, {'bound': 'OVERLAY_ENTRY_MAX_BYTES'})
        if sum(1 for entry in merged if entry['kind'] == overlay.KIND_TERMS) > bounds['DECISION_RECORDS_MAX']:
            raise ApiError('SIMULATION_CAPACITY', 409, {'bound': 'DECISION_RECORDS_MAX'})
        if overlay.section_size(payload, merged) > bounds['ENVELOPE_MAX_BYTES']:
            raise ApiError('SIMULATION_CAPACITY', 409, {'bound': 'ENVELOPE_MAX_BYTES'})

    def overlay_command(self, body, role=DEFAULT_ROLE):
        """advance_day: the only writer of sim_day. One atomic save; the F04 journal is never touched."""
        with self.lock:
            principal = Principal(role if type(role) is str else '')
            require(self.authorizer, principal, OVERLAY_COMMAND)
            if self.workspace_status != 'ACTIVE':
                raise ApiError(self.workspace_status, 503)
            if type(body) is not dict:
                raise ApiError('INVALID_COMMAND')
            self._overlay_volatile(body)
            if set(body) != {'instance_id', 'operation_id', 'op', 'from_sim_day', 'to_sim_day', 'reason'}:
                raise ApiError('INVALID_COMMAND')
            if body['instance_id'] != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            if body['op'] != overlay.COMMAND_OP:
                raise ApiError('UNSUPPORTED_OPERATION')
            operation_id = body['operation_id']
            if type(operation_id) is not str or _OVERLAY_ID.match(operation_id) is None:
                raise ApiError('INVALID_OPERATION_ID')
            from_day, to_day, reason = body['from_sim_day'], body['to_sim_day'], body['reason']
            self._require_day(from_day)
            self._require_day(to_day)
            if type(reason) is not str or not reason.strip() or len(reason) > _REASON_MAX:
                raise ApiError('INVALID_ARGUMENTS')
            prior = overlay.operation_receipt(self.overlay_entries, operation_id)
            if prior is not None:
                if (prior['from_sim_day'], prior['to_sim_day'], prior['reason']) != (from_day, to_day, reason):
                    raise ApiError('IDEMPOTENCY_CONFLICT', 409)
                prior.update(self._overlay_receipt_common(principal), transport_duplicate=True)
                return prior
            status = self._overlay_terms()
            if status is None:
                raise self._overlay_not_bound()
            state = overlay.fold(self.overlay_entries)
            binding = state['terms_binding']
            if binding is not None and binding['terms_version'] != status['terms_version']:
                raise self._overlay_not_bound('terms version mismatch')
            if from_day != state['sim_day']:
                raise ApiError('SIM_CLOCK_STALE', 409, {'sim_day': state['sim_day']})
            if to_day <= from_day:
                raise ApiError('SIM_CLOCK_NOT_ADVANCING')
            if to_day - from_day > self.overlay_bounds['max_step_days']:
                raise ApiError('SIM_CLOCK_STEP')
            journal = self.machine.export_journal()
            frozen = self._machine_frozen()
            subjects = []
            drawn = self._overlay_subjects(self.overlay_entries)
            for subject in drawn:
                terms = self.terms.ledger_terms(subject['case'], subject['claim'],
                                                gate=subject['gate'], draw_day=subject['draw_day'])
                if terms is not None:
                    subjects.append({**subject, 'terms': terms})
            binding = {'terms_version': status['terms_version'], 'status': status['status']}
            # Margin rules journal only against a source whose settlement views can change
            # (a disposable book). Immutable workspace fixtures are reported, never journaled.
            margin_subjects = self._margin_subjects(drawn) if margin.views_mutable(self.fixtures) else []
            cures = margin.plan_cures(state, margin_subjects, operation_id=operation_id,
                                      journal_length=len(journal), day=from_day)
            new = overlay.advance_entries(
                operation_id, state, len(journal), to_day=to_day, reason=reason,
                binding=binding, subjects=subjects, margin_before=cures)
            if margin_subjects:
                try:
                    stepped = overlay.fold(self.overlay_entries + new, len(journal))
                except ValueError:
                    raise ApiError('READ_ONLY_INVARIANT', 500)
                new += margin.plan_rules(stepped, margin_subjects, operation_id=operation_id,
                                         journal_length=len(journal), day=to_day)
            payload = {'receipts': self.receipts, 'journal': journal,
                       'case_fixtures': dict(self.case_fixtures), 'state_digest': self.machine.state_digest()}
            self._overlay_check_capacity(self.overlay_entries, new, to_day, payload)
            candidate = self.overlay_entries + new
            try:
                overlay.fold(candidate, len(journal))
            except ValueError:
                raise ApiError('READ_ONLY_INVARIANT', 500)
            try:
                self._persist(candidate)
            except WorkspaceError as exc:
                self.workspace_status = exc.code
                raise ApiError(exc.code, 503)
            self.overlay_entries = candidate
            self._machine_same(frozen)
            receipt = overlay.operation_receipt(candidate, operation_id)
            receipt.update(self._overlay_receipt_common(principal), transport_duplicate=False,
                           overlay_state_digest=overlay.state_digest(overlay.fold(candidate)))
            return receipt

    def _overlay_receipt_common(self, principal):
        return {'label': OVERLAY_LABEL, 'instance_id': self.instance_id, 'clock_source': overlay.CLOCK_SOURCE,
                'actor': overlay.ACTOR, 'role': principal.role, 'role_provenance': ROLE_PROVENANCE,
                'funds_executed': False, 'f04_journal_written': False, 'economic_finality_claimed': False}

    def _overlay_row(self, subject, state, status):
        case, advance_id = subject['case'], subject['advance_id']
        recorded = state['advances'].get(advance_id)
        terms = (self.terms.ledger_terms(case, subject['claim'], gate=subject['gate'], draw_day=subject['draw_day'])
                 if status is not None else None)
        interest = recorded['posted_contract_krw'] if recorded else 0
        default = recorded['posted_default_krw'] if recorded else 0
        outstanding = subject['principal']
        row = {'advance_id': advance_id, 'phase': case['phase'], 'draw_day': subject['draw_day'],
               'tier': 'NOT_APPLICABLE' if terms is None else terms['tier'],
               'principal_outstanding_krw': outstanding,
               'interest_due_krw': interest, 'default_interest_due_krw': default,
               'accrued_through_sim_day': recorded['last_accrued_day'] if recorded else subject['draw_day']}
        if recorded:
            for bucket, key in (('contract', 'cumulative_contract_exact'), ('default', 'cumulative_default_exact')):
                exact = overlay.parse_exact(recorded[key])
                row[f'carried_remainder_{bucket}'] = overlay.exact_text(exact - overlay.floor(exact))
            row['cumulative_exact_contract'] = recorded['cumulative_contract_exact']
            row['cumulative_exact_default'] = recorded['cumulative_default_exact']
        if terms is not None:
            row.update(maturity_day=terms['maturity_day'], writeoff_day=terms['writeoff_day'],
                       contract_bps=terms['contract_bps'], default_bps=terms['default_bps'])
        split = None
        if status is not None and callable(getattr(self.terms, 'allocate', None)):
            split = self.terms.allocate(outstanding, interest_due=interest, default_interest_due=default,
                                        cash=outstanding + interest + default)
        row['allocation'] = split
        fsm_repay = None
        sequence = case.get('next_repayment_sequence')
        if split and split.get('status') == 'BOUND' and case['phase'] == 'DRAWN' and split['to_principal'] > 0 \
                and type(sequence) is int:
            fsm_repay = {'amount': split['to_principal'], 'sequence': sequence, 'proposal_only': True}
        row['fsm_repay'] = fsm_repay
        row['close_ready'] = (case['phase'] == 'DRAWN' and outstanding == 0 and interest == 0 and default == 0)
        return row

    def overlay_state(self, operation_id=None):
        """Read-only overlay quote. Nothing is accrued or written here."""
        with self.lock:
            frozen = self._frozen()
            try:
                state = overlay.fold(self.overlay_entries)
                status = self._overlay_terms()
                body = {
                    'label': OVERLAY_LABEL, 'mode': 'SIMULATED_OVERLAY', 'provisional': True,
                    'clock_source': overlay.CLOCK_SOURCE, 'sim_day': state['sim_day'],
                    'terms_version': self.terms.status()['terms_version'],
                    'status': 'NOT_BOUND' if status is None else 'BOUND',
                    'reason': TERMS_NOT_BOUND if status is None else None,
                    'terms_binding': state['terms_binding'],
                    'overlay_state_digest': overlay.state_digest(state),
                    'entry_count': state['entry_count'],
                    'interest_payments': 'NOT_RECORDED', 'export': 'INCLUDED_IN_MANIFEST_V3' if self.overlay_entries else 'ABSENT_WHEN_EMPTY',
                    'f04_journal_written': False, 'workspace_status': self.workspace_status,
                    'capacity': 'NOT_BOUND' if self.overlay_bounds is None else self._overlay_capacity(self.overlay_entries),
                    'advances': [],
                }
                if status is not None:
                    body['terms_binding_matches'] = (
                        state['terms_binding'] is None
                        or state['terms_binding']['terms_version'] == status['terms_version'])
                    drawn = self._overlay_subjects(self.overlay_entries)
                    body['advances'] = [self._overlay_row(subject, state, status) for subject in drawn]
                    margin_subjects = self._margin_subjects(drawn)
                    mutable = margin.views_mutable(self.fixtures)
                    by_id = margin.row_blocks(state, margin_subjects, mutable=mutable)
                    body['margin'] = margin.status_block(
                        state, by_id, mutable=mutable, bound=True,
                        cure_terms=margin_subjects[0]['margin'] if margin_subjects else None)
                    for item in body['advances']:
                        item['margin'] = by_id.get(item['advance_id']) or margin.unbound_row(item['advance_id'])
                else:
                    body['margin'] = margin.status_block(
                        state, {}, mutable=margin.views_mutable(self.fixtures), bound=False)
                if operation_id is not None:
                    receipt = overlay.operation_receipt(self.overlay_entries, operation_id)
                    body['operation'] = receipt if receipt is not None else {
                        'outcome': 'UNKNOWN', 'operation_id': operation_id, 'retry_authorized': False}
                return self._terms_envelope(body)
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
            json.dumps(self.overlay_entries, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode(),
        )

    def _same_frozen(self, frozen):
        return self._frozen() == frozen

    def _subject_payload(self):
        """Checksum-valid workspace payload and overlay section when they exist; otherwise the live book."""
        try:
            document = self.storage.load()
        except WorkspaceError as exc:
            return None, exc.code, None
        if document is None:
            return {
                'receipts': copy.deepcopy(self.receipts),
                'journal': self.machine.export_journal(),
                'case_fixtures': copy.deepcopy(dict(self.case_fixtures)),
                'state_digest': self.machine.state_digest(),
            }, None, overlay.build_section(copy.deepcopy(self.overlay_entries))
        persisted = overlay_section(document)
        return copy.deepcopy(document['payload']), None, copy.deepcopy(persisted)

    def reconciliation(self, probe_operation_id=None, mode=None):
        """Read-only exception report. No receipt is written and nothing is retried.

        mode=coa-candidate appends the two COA candidate checks; the default report and the
        manifest are unchanged.
        """
        with self.lock:
            if mode not in (None, 'simulation', coa.MODE):
                raise ApiError('NOT_BOUND', 400)
            frozen = self._frozen()
            try:
                payload, unreadable, persisted = self._subject_payload()
                rows = copy.deepcopy(self.fixtures.rows)
                return build_reconciliation(
                    payload=payload, unreadable=unreadable, fixture_rows=rows,
                    fixtures_digest=digest(rows), settlement_source=self.fixtures,
                    projection_port=self.projection_port, probe_operation_id=probe_operation_id,
                    instance_id=self.instance_id, operation_capacity=MAX_OPERATIONS,
                    workspace_status=self.workspace_status,
                    coa_port=self.coa_projection if mode == coa.MODE else None,
                    overlay_entries=copy.deepcopy(self.overlay_entries) or None,
                    overlay_persisted=persisted,
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
        """Read-only v2 (empty overlay) or v3 (non-empty overlay) manifest of hashed sections. No import, resume, or key material."""
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
                if self.overlay_entries:
                    sections['overlay'] = overlay.export_section(self.overlay_entries, len(journal))
                status, reasons = manifest_status(reconciliation['status'], self.workspace_status)
                return build_manifest(
                    sections=sections, instance_id=self.instance_id, signer=self.signer,
                    status=status, incomplete_reasons=reasons,
                )
            finally:
                if not self._same_frozen(frozen):
                    raise ApiError('READ_ONLY_INVARIANT', 500)
