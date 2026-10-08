"""Read-only double-entry projection of an accepted journal and settlement evidence.

The chart is a fixed synthetic memo. It is not an adopted ledger, a revenue
policy, or a tax classification. Account kinds name mechanical roles only.
"""
from __future__ import annotations

import re
from types import MappingProxyType


class ProjectionPort:
    """Replacement seam. An adopted finance contract can supply another port."""

    def project(self, journal, evidence):
        raise NotImplementedError


class ProjectionError(Exception):
    def __init__(self, code='PROJECTION_INVARIANT'):
        self.code = code
        super().__init__(code)


def _fail():
    raise ProjectionError()


def _text(value, limit=200):
    if type(value) is not str or not 1 <= len(value) <= limit:
        _fail()
    if any(ord(char) < 32 or char.isspace() for char in value):
        _fail()
    return value


_IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}')


def _ident(value):
    value = _text(value, 81)
    if _IDENT.fullmatch(value) is None:
        _fail()
    return value


def _money(value, positive=False):
    if type(value) is not int or isinstance(value, bool):
        _fail()
    if value < (1 if positive else 0):
        _fail()
    return value


# prefix -> (kind, normal side, label). Kinds are synthetic roles, not GAAP classes.
_CHART = MappingProxyType({
    'SIM_CLAIM_FACE': ('SYNTHETIC_CLAIM_FACE', 'debit', '합성 청구 액면 (비채택)'),
    'SIM_PAYEE_OBLIGATION': ('SYNTHETIC_PAYEE_OBLIGATION', 'credit', '합성 수취인 의무 액면 (비채택)'),
    'SIM_ADVANCE_EXPOSURE': ('SYNTHETIC_ADVANCE_EXPOSURE', 'debit', '합성 모의 노출 (비채택)'),
    'SIM_ADVANCE_OBLIGATION': ('SYNTHETIC_ADVANCE_OBLIGATION', 'credit', '합성 노출 대응 (비채택)'),
    'SIM_REPAY_MEMO': ('SYNTHETIC_REPAY_MEMO', 'credit', '합성 상환 메모 (비채택)'),
})
_LIFECYCLE = frozenset({'offer', 'approve', 'reject', 'cancel', 'bind_settlement', 'close', 'default'})
_JOURNAL_KEYS = frozenset({'op', 'idempotency_key', 'advance_id', 'body'})
_REAL_FLAGS = (
    'funds_executed', 'bank_debit_observed', 'legal_debtor_bound', 'admission_granted',
    'right_cancelled', 'external_return_closed', 'economic_finality_claimed', 'durable',
)


def _spec(prefix):
    spec = _CHART.get(prefix)
    if spec is None:
        _fail()
    return spec


def _account(prefix, identity):
    _spec(prefix)
    return prefix + ':' + identity


def _line(prefix, identity, side, amount):
    return {'account': _account(prefix, identity), 'side': side, 'amount': amount}


class _Totals:
    __slots__ = ('debit', 'credit')

    def __init__(self):
        self.debit = 0
        self.credit = 0

    def add(self, side, amount):
        if side == 'debit':
            self.debit += amount
        elif side == 'credit':
            self.credit += amount
        else:
            _fail()


class SimulationProjection(ProjectionPort):
    CHART_VERSION = 'SIMULATION_FIXED_V1'

    def project(self, journal, evidence):
        if type(journal) is not list or type(evidence) is not list:
            _fail()
        claims = [_claim(view) for view in evidence]
        if len({row['claim_id'] for row in claims}) != len(claims):
            _fail()
        claims.sort(key=lambda row: row['claim_id'])
        entries = []
        accounts = {}
        running = _Totals()
        seen_txn = set()
        for claim in claims:
            lines = [_line('SIM_CLAIM_FACE', claim['claim_id'], 'debit', claim['gross'])]
            for obligation in claim['obligations']:
                lines.append(_line(
                    'SIM_PAYEE_OBLIGATION', claim['claim_id'] + ':' + obligation['payee'],
                    'credit', obligation['face']))
            _append(entries, accounts, running, seen_txn, 'EVIDENCE', 'evidence:' + claim['claim_id'], lines, None)
        advances = {}
        for raw in journal:
            advance_id, lines, record = _journal_lines(raw, advances)
            _append(entries, accounts, running, seen_txn, 'JOURNAL', _text(raw['idempotency_key']), lines, advance_id)
            if record is not None:
                record['drawn_ok'] = record['drawn'] == record['outstanding'] + record['repaid']
                if not record['drawn_ok']:
                    _fail()
        if running.debit != running.credit:
            _fail()
        _check_claims(claims, accounts)
        _check_advances(advances, accounts)
        rendered = _render_accounts(accounts)
        if sum(row['debit_total'] for row in rendered) != sum(row['credit_total'] for row in rendered):
            _fail()
        return {
            'entries': entries,
            'accounts': rendered,
            'read_model': {
                'claims': [_public_claim(row) for row in claims],
                'advances': [_public_advance(row) for row in sorted(advances.values(), key=lambda row: row['advance_id'])],
            },
            'conservation': [
                {'predicate': 'DEBITS_EQUAL_CREDITS_EVERY_STEP', 'matched': True},
                {'predicate': 'CLAIM_FACE_EQUALS_PAYEE_FACES', 'matched': True},
                {'predicate': 'ADVANCE_EXPOSURE_CONSERVATION', 'matched': True},
                {'predicate': 'REFUND_ACCEPTANCE_CONSERVATION', 'matched': True},
                {'predicate': 'NO_REAL_EFFECT', 'matched': True},
            ],
        }


def _append(entries, accounts, running, seen_txn, source, txn_id, lines, advance_id):
    step_debit = sum(line['amount'] for line in lines if line['side'] == 'debit')
    step_credit = sum(line['amount'] for line in lines if line['side'] == 'credit')
    if step_debit != step_credit or any(line['side'] not in ('debit', 'credit') for line in lines):
        _fail()
    if txn_id in seen_txn:
        _fail()
    seen_txn.add(txn_id)
    running.add('debit', step_debit)
    running.add('credit', step_credit)
    if running.debit != running.credit:
        _fail()
    for line in lines:
        accounts.setdefault(line['account'], _Totals()).add(line['side'], line['amount'])
    body = {'step': len(entries) + 1, 'source': source, 'txn_id': txn_id, 'lines': lines}
    if advance_id is not None:
        body['advance_id'] = advance_id
    entries.append(body)


def _claim(view):
    if type(view) is not dict or type(view.get('claim')) is not dict:
        _fail()
    claim = view['claim']
    claim_id = _ident(claim.get('claim_id'))
    if claim_id != view.get('settlement_id') or type(view.get('phase')) is not str or not view['phase']:
        _fail()
    gross = _money(claim.get('gross'), positive=True)
    if _money(view.get('gross'), positive=True) != gross:
        _fail()
    obligations = []
    seen = set()
    raw_rows = claim.get('obligations')
    if type(raw_rows) is not list or not raw_rows:
        _fail()
    for raw in raw_rows:
        if type(raw) is not dict:
            _fail()
        payee = _ident(raw.get('payee'))
        if payee in seen:
            _fail()
        seen.add(payee)
        obligations.append({
            'payee': payee,
            'face': _money(raw.get('face'), positive=True),
            'distributed': _money(raw.get('distributed')),
            'outstanding': _money(raw.get('outstanding')),
            'recovery_due': _money(raw.get('recovery_due')),
        })
    obligations.sort(key=lambda row: row['payee'])
    if sum(row['face'] for row in obligations) != gross:
        _fail()
    refund_face = _money(claim.get('refund_face'))
    refund_accepted = _money(claim.get('refund_accepted'))
    refund_outstanding = _money(claim.get('refund_outstanding'))
    if refund_face != refund_accepted + refund_outstanding or refund_face > gross:
        _fail()
    _no_real_effect(view)
    _no_real_effect(claim)
    return {
        'claim_id': claim_id,
        'phase': view['phase'],
        'gross': gross,
        'confirmed_cash': _money(claim.get('confirmed_cash')),
        'refund_face': refund_face,
        'refund_outstanding': refund_outstanding,
        'obligations': obligations,
    }


def _no_real_effect(body):
    if body.get('funds_executed') is not False:
        _fail()
    for name in _REAL_FLAGS:
        if name in body and body[name] is not False:
            _fail()


def _journal_lines(raw, advances):
    if type(raw) is not dict or set(raw) != _JOURNAL_KEYS or type(raw.get('body')) is not dict:
        _fail()
    op = raw['op']
    if type(op) is not str:
        _fail()
    advance_id = _ident(raw.get('advance_id'))
    body = raw['body']
    if op == 'offer':
        if advance_id in advances:
            _fail()
        advances[advance_id] = {
            'advance_id': advance_id,
            'beneficiary_role': _ident(body.get('beneficiary_role')),
            'amount': _money(body.get('amount'), positive=True),
            'drawn': 0, 'repaid': 0, 'outstanding': 0,
        }
        return advance_id, [], None
    record = advances.get(advance_id)
    if record is None or op not in _LIFECYCLE and op not in {'draw', 'repay'}:
        _fail()
    if op in _LIFECYCLE:
        return advance_id, [], None
    if op == 'draw':
        if record['drawn'] != 0:
            _fail()
        amount = record['amount']
        record['drawn'] = amount
        record['outstanding'] = amount
        return advance_id, [
            _line('SIM_ADVANCE_EXPOSURE', advance_id, 'debit', amount),
            _line('SIM_ADVANCE_OBLIGATION', advance_id, 'credit', amount),
        ], record
    amount = _money(body.get('amount'), positive=True)
    if record['drawn'] == 0 or amount > record['outstanding']:
        _fail()
    record['repaid'] += amount
    record['outstanding'] -= amount
    return advance_id, [
        _line('SIM_ADVANCE_OBLIGATION', advance_id, 'debit', amount),
        _line('SIM_REPAY_MEMO', advance_id, 'credit', amount),
    ], record


def _check_claims(claims, accounts):
    for claim in claims:
        face = accounts.get(_account('SIM_CLAIM_FACE', claim['claim_id']))
        if face is None or face.debit != claim['gross'] or face.credit != 0:
            _fail()
        posted = 0
        for obligation in claim['obligations']:
            row = accounts.get(_account('SIM_PAYEE_OBLIGATION', claim['claim_id'] + ':' + obligation['payee']))
            if row is None or row.credit != obligation['face'] or row.debit != 0:
                _fail()
            posted += row.credit
        if posted != claim['gross']:
            _fail()


def _check_advances(advances, accounts):
    for record in advances.values():
        if record['drawn'] != record['outstanding'] + record['repaid']:
            _fail()
        exposure = accounts.get(_account('SIM_ADVANCE_EXPOSURE', record['advance_id']))
        obligation = accounts.get(_account('SIM_ADVANCE_OBLIGATION', record['advance_id']))
        memo = accounts.get(_account('SIM_REPAY_MEMO', record['advance_id']))
        if record['drawn'] == 0:
            if exposure is not None or obligation is not None or memo is not None:
                _fail()
            continue
        if exposure is None or obligation is None:
            _fail()
        if exposure.debit != record['drawn'] or exposure.credit != 0:
            _fail()
        if obligation.credit != record['drawn'] or obligation.debit != record['repaid']:
            _fail()
        if obligation.credit - obligation.debit != record['outstanding']:
            _fail()
        if record['repaid'] == 0:
            if memo is not None:
                _fail()
        elif memo is None or memo.credit != record['repaid'] or memo.debit != 0:
            _fail()


def _render_accounts(accounts):
    rendered = []
    for code in sorted(accounts):
        prefix = code.split(':', 1)[0]
        kind, normal, label = _spec(prefix)
        totals = accounts[code]
        balance = totals.debit - totals.credit if normal == 'debit' else totals.credit - totals.debit
        if balance < 0:
            _fail()
        rendered.append({
            'code': code,
            'label': label + ' · ' + code.split(':', 1)[1],
            'kind': kind,
            'debit_total': totals.debit,
            'credit_total': totals.credit,
            'balance': balance,
        })
    return rendered


def _public_claim(row):
    return {
        'claim_id': row['claim_id'],
        'phase': row['phase'],
        'gross': row['gross'],
        'confirmed_cash': row['confirmed_cash'],
        'refund_face': row['refund_face'],
        'refund_outstanding': row['refund_outstanding'],
        'obligations': [dict(item) for item in row['obligations']],
    }


def _public_advance(row):
    return {
        'advance_id': row['advance_id'],
        'beneficiary_role': row['beneficiary_role'],
        'amount': row['amount'],
        'drawn': row['drawn'],
        'repaid': row['repaid'],
        'outstanding': row['outstanding'],
    }
