"""Capital-local simulation facade. The pinned Protocol FSM owns all arithmetic."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid

from capital import __version__
from capital.auth import (
    DEFAULT_ROLE, OP_PERMISSIONS, PROVENANCE as ROLE_PROVENANCE, ROLES, UNLABELED,
    Principal, require, LocalRoleAuthorizer,
)
from capital.protocol import VENDOR, CreditError, CreditMachine, SettlementMachine
from capital.projection import ProjectionError, SimulationProjection
from capital.recon import build_reconciliation
from capital.scenarios import replay_scenarios
from capital.statement import build_statement
from capital.readiness import GROUPS, source_integrity
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


class ApiError(Exception):
    def __init__(self, code, status=400, detail=None):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(code)


class FixtureViews:
    """No commands exposed to the credit adapter; snapshots cannot be advanced."""
    def __init__(self):
        self.rows = {}
        for fixture_id, phase, refund in (
            ('sim-committed', 'COMMITTED', False),
            ('sim-pending', 'CAPTURED', False),
            ('sim-refund', 'COMMITTED', True),
        ):
            book = SettlementMachine()
            book.initiate(fixture_id, idempotency_key='init', trade_id='sim-trade-' + fixture_id,
                          gross=100_000, debtor_role='fixture-merchant',
                          policy={'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
                                  'residual_payee': 'organizer', 'fee_payee': 'platform'})
            book.authorize(fixture_id, idempotency_key='authorize')
            book.capture(fixture_id, idempotency_key='capture')
            if phase == 'COMMITTED':
                book.commit(fixture_id, idempotency_key='commit', movement_id='sim-movement',
                            gross=100_000, amount=97_000, fee=3_000, tax=0, held=0, adjustment=0)
            # Adverse fixture: one synthetic partial refund through the pinned FSM, so
            # bearer UNDEFINED and the distribution block are derived, never hand-set.
            if refund:
                book.bind_refund(fixture_id, idempotency_key='refund', refund_id='sim-fixture-refund',
                                 amount=10_000, beneficiary_role='fixture-buyer', reason='SYNTHETIC_FIXTURE')
            self.rows[fixture_id] = book.view(fixture_id)

    def view(self, key):
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return copy.deepcopy(self.rows[key])


class CapitalService:
    def __init__(self, storage=None, authorizer=None):
        self.lock = threading.RLock()
        self.authorizer = authorizer or LocalRoleAuthorizer()
        self.storage = InMemoryStorage() if storage is None else storage
        self.instance_id = str(uuid.uuid4())
        self.storage.writer_instance = self.instance_id
        self.fixtures = FixtureViews()
        self.machine = CreditMachine(self.fixtures)
        self.projection_port = SimulationProjection()
        self.receipts = {}
        self.case_fixtures = {}
        self.workspace_status = 'ACTIVE'
        self.source = vendor_manifest()
        self.scenario_results = replay_scenarios()
        self._load_workspace()

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
            self.machine = CreditMachine(self.fixtures)
            self.receipts = {}
            self.case_fixtures = {}
            return
        self.machine, self.receipts, self.case_fixtures = installed

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
        try:
            restored = CreditMachine.restore(copy.deepcopy(journal), self.fixtures)
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
        return restored, self._label_restored_receipts(receipts), copy.deepcopy(mapping)

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
                    'source_commit': self.source['commit'], 'cases': cases,
                    'fixtures': copy.deepcopy(self.fixtures.rows),
                    'state_digest': self.machine.state_digest(),
                    'operation_count': len(self.receipts), 'operation_capacity': MAX_OPERATIONS,
                    'auth': self.authorizer.describe(principal),
                    'workspace': self.workspace_view(),
                    'decisions': ['Interest, fees, term, underwriting and KYC: UNDETERMINED',
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
                             'source_view_digest': digest(view)})
            return {'mode': 'READ_ONLY_FIXTURE', 'provenance': 'MOCK_SETTLEMENT_ONLY',
                    'instance_id': self.instance_id, 'source_commit': self.source['commit'],
                    'source_scope': 'Three immutable synthetic settlement views; fixture-v1',
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

    def readiness(self):
        with self.lock:
            return {'instance_id': self.instance_id, 'mode': 'LOCAL_READINESS_ONLY',
                    'source_commit': self.source['commit'], 'upstream_binding': 'NOT_BOUND',
                    'source_integrity': source_integrity(VENDOR, self.source),
                    'groups': copy.deepcopy(GROUPS), 'production_authorized': False,
                    'upstream_nodes_completed': [], 'policy_adopted': False,
                    'requirement_notes': {
                        'CAP-09': 'local five-category statement only; primary_sales, resale_sales and actual_paid stay NOT_BOUND and are never summed',
                        'CAP-13': 'local candidate projection; fin-ledger-contract still upstream',
                        'CAP-14': 'local reconciliation diagnostics only; no bank reconciliation or provider-authenticated completeness'}}

    def projection(self, mode=None):
        """Fold copies of the accepted journal and fixture views. Nothing is cached or written."""
        with self.lock:
            if mode not in (None, 'simulation'):
                raise ApiError('NOT_BOUND', 400)
            before_canon = self.machine.canonical_state()
            before_receipts = copy.deepcopy(self.receipts)
            before_rows = copy.deepcopy(self.fixtures.rows)
            journal = self.machine.export_journal()
            evidence = [self.fixtures.view(key) for key in sorted(self.fixtures.rows)]
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
            scratch = CreditMachine.restore(self.machine.export_journal(), self.fixtures)
            try:
                preview = scratch.draw(advance_id, idempotency_key='diagnostic:draw', draw_id='diagnostic:draw')
                return {**result, 'outcome': 'WOULD_ACCEPT',
                        'predicted_exposure': preview['credit']['outstanding_exposure'],
                        'settlement_gate': preview['credit']['settlement_gate']}
            except CreditError as exc:
                return {**result, 'outcome': 'WOULD_REJECT', 'reason': exc.code}

    def execute(self, body, role=DEFAULT_ROLE):
        with self.lock:
            if type(body) is not dict or set(body) != {'instance_id', 'operation_id', 'op', 'advance_id', 'args'}:
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
            operation_id = body['operation_id']
            if type(operation_id) is not str or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', operation_id):
                raise ApiError('INVALID_OPERATION_ID')
            # Instance id authorizes the session. It is not part of the stored command identity,
            # so a restarted process can return the original receipt instead of applying it again.
            fingerprint = digest({'operation_id': operation_id, 'op': body['op'],
                                  'advance_id': body['advance_id'], 'args': body['args']})
            prior = self.receipts.get(operation_id)
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise ApiError('IDEMPOTENCY_CONFLICT', 409)
                result = copy.deepcopy(prior['receipt'])
                result['transport_duplicate'] = True
                return result
            if len(self.receipts) >= MAX_OPERATIONS:
                raise ApiError('SIMULATION_CAPACITY', 409)
            op, case, args = body['op'], body['advance_id'], body['args']
            if type(op) is not str or op not in OPS:
                raise ApiError('UNSUPPORTED_OPERATION')
            if type(case) is not str or not re.fullmatch(r'sim-[a-zA-Z0-9-]{1,60}', case):
                raise ApiError('SYNTHETIC_ID_REQUIRED')
            if type(args) is not dict or set(args) != OPS[op]:
                raise ApiError('INVALID_ARGUMENTS')
            receipt = {'operation_id': operation_id, 'instance_id': self.instance_id,
                       'provenance': PROVENANCE, 'funds_executed': False,
                       'economic_finality_claimed': False, 'transport_duplicate': False,
                       'role': principal.role, 'role_provenance': ROLE_PROVENANCE}
            try:
                method = getattr(self.machine, op)
                kwargs = {'idempotency_key': operation_id}
                if op == 'offer':
                    if type(args['fixture_id']) is not str or args['fixture_id'] not in self.fixtures.rows:
                        raise CreditError('UNKNOWN_SETTLEMENT')
                    kwargs.update(face=self.fixtures.view(args['fixture_id'])['claim'],
                                  amount=args['amount'], beneficiary_role='fixture-organizer')
                elif op == 'bind_settlement':
                    if case not in self.case_fixtures:
                        raise CreditError('UNKNOWN_ADVANCE')
                    kwargs['settlement_id'] = self.case_fixtures[case]
                elif op == 'draw':
                    kwargs['draw_id'] = 'draw-' + operation_id
                elif op == 'repay':
                    kwargs.update(amount=args['amount'], sequence=args['sequence'], repay_id='repay-' + operation_id)
                elif op in {'reject', 'cancel', 'default'}:
                    kwargs['reason'] = 'synthetic-operator-scenario'
                result = method(case, **kwargs)
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
            return receipt

    def operation(self, operation_id, instance_id):
        with self.lock:
            if instance_id != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            stored = self.receipts.get(operation_id)
            if stored is None:
                return {'outcome': 'UNKNOWN', 'operation_id': operation_id,
                        'instance_id': self.instance_id, 'retry_authorized': False}
            return copy.deepcopy(stored['receipt'])

    def _replay_journal(self):
        """Caller holds the service lock. Restores a scratch machine and does not write."""
        journal = self.machine.export_journal()
        restored = CreditMachine.restore(journal, self.fixtures)
        return journal, restored.canonical_state() == self.machine.canonical_state()

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
