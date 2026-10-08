"""Capital-local simulation facade. The pinned Protocol FSM owns all arithmetic."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid

from capital.auth import (
    DEFAULT_ROLE, OP_PERMISSIONS, PROVENANCE as ROLE_PROVENANCE, Principal,
    require, LocalRoleAuthorizer,
)
from capital.protocol import VENDOR, CreditError, CreditMachine, SettlementMachine
from capital.scenarios import replay_scenarios
from capital.readiness import GROUPS, source_integrity

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
    def __init__(self, authorizer=None):
        self.lock = threading.RLock()
        self.authorizer = authorizer or LocalRoleAuthorizer()
        self.instance_id = str(uuid.uuid4())
        self.fixtures = FixtureViews()
        self.machine = CreditMachine(self.fixtures)
        self.receipts = {}
        self.case_fixtures = {}
        self.source = json.loads((VENDOR / 'manifest.json').read_text())
        self.scenario_results = replay_scenarios()

    def snapshot(self, role=None):
        with self.lock:
            cases = [self.machine.view(key) for key in sorted(self.case_fixtures)]
            principal = Principal(role or DEFAULT_ROLE)
            return {'instance_id': self.instance_id, 'mode': 'LOCAL_SIMULATION',
                    'provenance': PROVENANCE, 'durable': False, 'funds_executed': False,
                    'source_commit': self.source['commit'], 'cases': cases,
                    'fixtures': copy.deepcopy(self.fixtures.rows),
                    'state_digest': self.machine.state_digest(),
                    'operation_count': len(self.receipts), 'operation_capacity': MAX_OPERATIONS,
                    'auth': self.authorizer.describe(principal),
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
                    'upstream_nodes_completed': [], 'policy_adopted': False}

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
            if body['instance_id'] != self.instance_id:
                raise ApiError('SESSION_CHANGED', 409)
            operation_id = body['operation_id']
            if type(operation_id) is not str or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', operation_id):
                raise ApiError('INVALID_OPERATION_ID')
            fingerprint = digest(body)
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

    def reconciliation(self):
        """Read-only replay. No receipt, so operation_count stays unchanged."""
        with self.lock:
            journal, matched = self._replay_journal()
            return {'mode': 'READ_ONLY_RECONCILIATION', 'instance_id': self.instance_id,
                    'replay_matched': matched, 'entry_count': len(journal),
                    'state_digest': self.machine.state_digest(),
                    'bank_reconciliation': 'NOT_BOUND', 'funds_executed': False, 'durable': False}

    def export(self):
        with self.lock:
            journal, matched = self._replay_journal()
            return {'format': 'KIX_CAPITAL_SIMULATION_V1', 'instance_id': self.instance_id,
                    'provenance': PROVENANCE, 'source': self.source,
                    'fixtures_digest': digest(self.fixtures.rows), 'journal': journal,
                    'state_digest': self.machine.state_digest(),
                    'replay_matched': matched,
                    'durable': False, 'funds_executed': False,
                    'note': 'Accepted in-memory commands only. Rejected receipts are not in the Protocol journal. No bank reconciliation or durable recovery.'}
