"""Capital-local simulation facade. The pinned Protocol FSM owns all arithmetic."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import threading
import uuid
from pathlib import Path

VENDOR = Path(__file__).parent / 'vendor'
for name in ('credit_advance_f04', 'settlement_f01_f03'):
    sys.path.insert(0, str(VENDOR / name))
from credit_fsm import CreditError, CreditMachine
from settlement_fsm import SettlementMachine

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
    def __init__(self, code, status=400):
        self.code, self.status = code, status
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
            row = book.view(fixture_id)
            # Explicit adverse fixture; NOT a settlement command or new refund policy.
            if refund:
                row['claim']['refund_face'] = 10_000
                row['claim']['refund_outstanding'] = 10_000
                row['claim']['refund_bearer_policy'] = 'UNDEFINED'
            self.rows[fixture_id] = row

    def view(self, key):
        if key not in self.rows:
            raise CreditError('UNKNOWN_SETTLEMENT')
        return copy.deepcopy(self.rows[key])


class CapitalService:
    def __init__(self):
        self.lock = threading.RLock()
        self.instance_id = str(uuid.uuid4())
        self.fixtures = FixtureViews()
        self.machine = CreditMachine(self.fixtures)
        self.receipts = {}
        self.case_fixtures = {}
        self.source = json.loads((VENDOR / 'manifest.json').read_text())

    def snapshot(self):
        with self.lock:
            cases = [self.machine.view(key) for key in sorted(self.case_fixtures)]
            return {'instance_id': self.instance_id, 'mode': 'LOCAL_SIMULATION',
                    'provenance': PROVENANCE, 'durable': False, 'funds_executed': False,
                    'source_commit': self.source['commit'], 'cases': cases,
                    'fixtures': copy.deepcopy(self.fixtures.rows),
                    'state_digest': self.machine.state_digest(),
                    'operation_count': len(self.receipts), 'operation_capacity': MAX_OPERATIONS,
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

    def execute(self, body):
        with self.lock:
            if type(body) is not dict or set(body) != {'instance_id', 'operation_id', 'op', 'advance_id', 'args'}:
                raise ApiError('INVALID_COMMAND')
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
                       'economic_finality_claimed': False, 'transport_duplicate': False}
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

    def export(self):
        with self.lock:
            journal = self.machine.export_journal()
            restored = CreditMachine.restore(journal, self.fixtures)
            return {'format': 'KIX_CAPITAL_SIMULATION_V1', 'instance_id': self.instance_id,
                    'provenance': PROVENANCE, 'source': self.source,
                    'fixtures_digest': digest(self.fixtures.rows), 'journal': journal,
                    'state_digest': self.machine.state_digest(),
                    'replay_matched': restored.canonical_state() == self.machine.canonical_state(),
                    'durable': False, 'funds_executed': False,
                    'note': 'Accepted in-memory commands only. Rejected receipts are not in the Protocol journal. No bank reconciliation or durable recovery.'}
