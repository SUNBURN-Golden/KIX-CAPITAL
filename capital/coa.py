"""Additive CAPITAL-COA-V1 candidate projection (chart SIMULATION_FIXED_V2).

SIMULATED and SYNTHETIC_UNADOPTED. The chart is the CAPITAL-COA-V1 mapping of
docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md, a working assumption pending
professional review. Nothing here is a ledger of record, a revenue-recognition
adoption or a tax position, and no posting is a payment. SIMULATION_FIXED_V1
(capital/projection.py) stays the default and is not touched: the candidate runs
V1 first, which validates the journal and the evidence, then renames V1 accounts
to COA codes and adds the interest postings recorded in the overlay ledger.

The chart is a literal because the zipapp carries no docs/ to read it from (same
precedent as capital/assets.py). tests/test_coa_candidate.py fences it against the note.
"""
from __future__ import annotations

from types import MappingProxyType

from capital import assets, overlay
from capital.projection import ProjectionError, ProjectionPort, SimulationProjection

CHART_VERSION = 'SIMULATION_FIXED_V2'
COA_VERSION = 'CAPITAL-COA-V1'
MODE = 'coa-candidate'
TERMS_NOT_BOUND = 'NOT_BOUND'
CANDIDATE_ONLY = ('9790',)

# code -> (name, class, normal side). Names, classes and sides follow the note's accounts table.
# 9790 is not in the note: a candidate-only credit-normal counterpart so the 9700 memo posts
# balanced. It carries no money value of its own and is listed for the accountant to accept or drop.
CHART = MappingProxyType({
    '1000': ('CASH_AND_FUNDING_PLATFORM_TREASURY', 'ASSET', 'debit'),
    '1100': ('ADVANCES_RECEIVABLE_PRINCIPAL', 'ASSET', 'debit'),
    '1110': ('ACCRUED_INTEREST_RECEIVABLE', 'ASSET', 'debit'),
    '1190': ('ALLOWANCE_FOR_EXPECTED_CREDIT_LOSSES', 'CONTRA_ASSET', 'credit'),
    '1300': ('WITHHOLDING_TAX_RECEIVABLE_ON_INTEREST', 'ASSET', 'debit'),
    '2300': ('VAT_PAYABLE_ON_TAXABLE_FEES', 'LIABILITY', 'credit'),
    '3100': ('PROTOCOL_REVENUE_POOL_RETAINED', 'EQUITY', 'credit'),
    '3200': ('APPROPRIATED_RESERVE_FOR_CREDIT_LOSSES', 'EQUITY_APPROPRIATION', 'credit'),
    '4100': ('INTEREST_INCOME_ADVANCES', 'REVENUE', 'credit'),
    '4110': ('DEFAULT_INTEREST_INCOME', 'REVENUE', 'credit'),
    '4200': ('FEE_INCOME_CAPITAL', 'REVENUE', 'credit'),
    '4300': ('RECOVERIES_OF_WRITTEN_OFF_ADVANCES', 'REVENUE', 'credit'),
    '5100': ('CREDIT_LOSS_EXPENSE', 'EXPENSE', 'debit'),
    '5200': ('WRITE_OFF_LOSS_BEYOND_ALLOWANCE', 'EXPENSE', 'debit'),
    '9100': ('MEMO_SETTLEMENT_CLAIM_FACE_OBSERVED', 'MEMO_OFF_BALANCE', 'debit'),
    '9110': ('MEMO_PAYEE_OBLIGATION_FACE', 'MEMO_OFF_BALANCE', 'credit'),
    '9150': ('MEMO_BENEFICIARY_REPAYMENT_OBLIGATION', 'MEMO_OFF_BALANCE', 'credit'),
    '9160': ('MEMO_REPAYMENTS_RECEIVED_CUMULATIVE', 'MEMO_OFF_BALANCE', 'credit'),
    '9200': ('MEMO_OPEN_FACE_RESERVED', 'MEMO_OFF_BALANCE', 'credit'),
    '9300': ('MEMO_REFUND_OBLIGATION_EXPOSURE', 'MEMO_OFF_BALANCE', 'credit'),
    '9400': ('MEMO_RECOVERY_DUE_ON_FACE', 'MEMO_OFF_BALANCE', 'debit'),
    '9500': ('MEMO_SUPPLEMENTARY_TOKEN_COLLATERAL_ZERO_CREDIT_VALUE', 'MEMO_OFF_BALANCE', 'debit'),
    '9700': ('MEMO_SUSPENDED_INTEREST_AFTER_DEFAULT', 'MEMO_OFF_BALANCE', 'debit'),
    '9790': ('MEMO_SUSPENDED_INTEREST_CONTRA', 'MEMO_OFF_BALANCE', 'credit'),
})

# Each V1 account maps to exactly one COA code and keeps its side (draw: Dr 1100 / Cr 1000,
# repay: Dr 1000 / Cr 1100, evidence: Dr 9100 / Cr 9110).
V1_TO_COA = MappingProxyType({
    'SIM_CLAIM_FACE': '9100',
    'SIM_PAYEE_OBLIGATION': '9110',
    'SIM_ADVANCE_EXPOSURE': '1100',
    'SIM_ADVANCE_OBLIGATION': '1000',
    'SIM_REPAY_MEMO': '1100',
})

STATUS_POSTED = 'POSTED'
_DERIVED = ('9150', '9160')
_NOT_RECORDED = ('1190', '3100', '3200', '4300', '5100', '5200')
_RESERVED = ('1300', '2300')
_NOT_POSTED = ('9200', '9300', '9400', '9500')
_EVIDENCE_CODES = frozenset({'9100', '9110'})
_SIDES = ('debit', 'credit')


def _fail(code='PROJECTION_INVARIANT'):
    raise ProjectionError(code)


def asset_id(spec):
    return f"{spec['namespace']}:{spec['reference']}"


def chart_status():
    """Every chart code with the status this candidate gives it. Nothing is silently dropped."""
    rows = []
    for code, (name, klass, normal) in CHART.items():
        if code in _DERIVED:
            status = 'DERIVED_MEMO'
        elif code in _NOT_RECORDED:
            status = 'NOT_RECORDED'
        elif code in _RESERVED:
            status = 'NOT_MODELED_V1_FIELD_RESERVED'
        elif code == '4200':
            status = 'ZERO_FEE_PLACEHOLDER'
        elif code in _NOT_POSTED:
            status = 'NOT_POSTED'
        else:
            status = STATUS_POSTED
        rows.append({'code': code, 'name': name, 'class': klass, 'normal': normal, 'status': status,
                     'adopted_in_note': code not in CANDIDATE_ONLY})
    return rows


def _line(account, side, amount, **extra):
    return {'account': account, 'side': side, 'amount': amount, **extra}


def check_entries(entries):
    """Validate entries and return the (asset, sim_day) balance groups.

    A declared-asset check, then a per-line asset check, then debit = credit per entry and per
    (asset, sim_day) group. Non-declared or mixed assets are ASSET_MISMATCH; imbalance is
    PROJECTION_INVARIANT.
    """
    declared = {asset_id(spec) for spec in assets.declared()}
    groups = {}
    for entry in entries:
        dims = entry['dimensions']
        asset = dims['asset']
        if asset not in declared:
            _fail('ASSET_MISMATCH')
        debit = credit = 0
        for line in entry['lines']:
            if line.get('asset', asset) != asset:
                _fail('ASSET_MISMATCH')
            if line['account'] not in CHART or line['side'] not in _SIDES or type(line['amount']) is not int \
                    or line['amount'] < 0:
                _fail()
            if line['side'] == 'debit':
                debit += line['amount']
            else:
                credit += line['amount']
        if debit != credit:
            _fail()
        group = groups.setdefault((asset, dims['sim_day']), [0, 0])
        group[0] += debit
        group[1] += credit
    return [{'asset': asset, 'sim_day': day, 'debit': debit, 'credit': credit, 'matched': debit == credit}
            for (asset, day), (debit, credit) in sorted(groups.items())]


def _dimensions(asset, advance_id, claim_id, sim_day, terms_version):
    return {'asset': asset, 'advance_id': advance_id, 'claim_id': claim_id, 'sim_day': sim_day,
            'chart_version': CHART_VERSION, 'terms_version': terms_version}


def _interest_lines(payload, suspended):
    lines = []
    for kind, amount, income in (('CONTRACT', payload['posted_contract_krw'], '4100'),
                                 ('DEFAULT', payload['posted_default_krw'], '4110')):
        if amount == 0:
            continue
        if suspended:
            lines.append(_line('9700', 'debit', amount, interest_kind=kind))
            lines.append(_line('9790', 'credit', amount, interest_kind=kind))
        else:
            lines.append(_line('1110', 'debit', amount, interest_kind=kind))
            lines.append(_line(income, 'credit', amount, interest_kind=kind))
    return lines


class CoaCandidateProjection(ProjectionPort):
    """Second ProjectionPort implementation. Selected only by mode=coa-candidate."""

    CHART_VERSION = CHART_VERSION
    COA_VERSION = COA_VERSION

    def project(self, journal, evidence, *, overlay_entries=(), asset=None):
        spec = assets.KRW if asset is None else asset
        if not assets.matches(spec):
            _fail('ASSET_MISMATCH')
        asset = asset_id(spec)
        v1 = SimulationProjection().project(journal, evidence)
        try:
            state = overlay.fold(list(overlay_entries), len(journal))
        except overlay.OverlayError as exc:
            raise ProjectionError() from exc
        binding_at = next((entry['after_journal_index'] for entry in overlay_entries
                           if entry['kind'] == overlay.KIND_TERMS), None)
        final_terms = (state['terms_binding'] or {}).get('terms_version', TERMS_NOT_BOUND)

        def terms_at(index):
            return final_terms if binding_at is not None and binding_at <= index else TERMS_NOT_BOUND

        entries = []
        claim_of = {}
        default_index = {}
        index = 0
        for source in v1['entries']:
            if source['source'] == 'EVIDENCE':
                lines = [_line(V1_TO_COA[line['account'].split(':', 1)[0]], line['side'], line['amount'])
                         for line in source['lines']]
                claim_id = source['lines'][0]['account'].split(':', 1)[1].split(':', 1)[0]
                dims = _dimensions(asset, None, claim_id, 0, final_terms)
            else:
                raw = journal[index]
                advance_id = raw['advance_id']
                if raw['op'] == 'offer':
                    face = raw['body'].get('face')
                    if type(face) is dict and type(face.get('claim_id')) is str:
                        claim_of[advance_id] = face['claim_id']
                elif raw['op'] == 'default':
                    default_index.setdefault(advance_id, index)
                lines = [_line(V1_TO_COA[line['account'].split(':', 1)[0]], line['side'], line['amount'])
                         for line in source['lines']]
                dims = _dimensions(asset, advance_id, claim_of.get(advance_id),
                                   overlay.draw_day_for(overlay_entries, index), terms_at(index))
                index += 1
            if lines:
                entries.append({'step': len(entries) + 1, 'source': source['source'], 'txn_id': source['txn_id'],
                                'dimensions': dims, 'lines': lines})
        # A tick records its accrual at after_journal_index = journal length, and the clock only moves
        # in a tick that accrues first, so a segment never straddles the accepted default.
        for record in overlay_entries:
            if record['kind'] != overlay.KIND_INTEREST:
                continue
            payload = record['payload']
            advance_id = payload['advance_id']
            suspended = advance_id in default_index and record['after_journal_index'] > default_index[advance_id]
            lines = _interest_lines(payload, suspended)
            if lines:
                entries.append({
                    'step': len(entries) + 1, 'source': 'OVERLAY_INTEREST', 'txn_id': record['overlay_id'],
                    'dimensions': _dimensions(asset, advance_id, claim_of.get(advance_id), record['sim_day'],
                                              payload['terms_version']),
                    'lines': lines})
        for entry in entries:
            codes = {line['account'] for line in entry['lines']}
            if (entry['source'] == 'EVIDENCE') != (codes <= _EVIDENCE_CODES) or \
                    (entry['source'] != 'EVIDENCE' and codes & _EVIDENCE_CODES):
                _fail()
        groups = check_entries(entries)
        accounts, subledger = _aggregate(entries)
        balances = {row['code']: row for row in accounts}
        principal = balances.get('1100', {'balance': 0, 'credit_total': 0})
        memo = {'9150': principal['balance'], '9160': principal['credit_total']}
        interest_by_kind = _interest_totals(accounts)
        conservation = [
            {'predicate': 'DEBITS_EQUAL_CREDITS_PER_ASSET_SIM_DAY', 'matched': all(row['matched'] for row in groups)},
            {'predicate': 'CLAIM_FACE_ONLY_IN_MEMO_9100_9110', 'matched': True},
            {'predicate': 'MEMO_9100_EQUALS_9110',
             'matched': balances.get('9100', {'debit_total': 0})['debit_total']
             == balances.get('9110', {'credit_total': 0})['credit_total']},
            {'predicate': 'PRINCIPAL_1100_EQUALS_V1_OUTSTANDING',
             'matched': principal['balance'] == sum(row['outstanding'] for row in v1['read_model']['advances'])},
            {'predicate': 'ACCRUED_1110_EQUALS_INCOME_4100_4110', 'matched': interest_by_kind},
            {'predicate': 'NO_REAL_EFFECT', 'matched': True},
        ]
        if not all(row['matched'] for row in conservation):
            _fail()
        return {
            'assets': assets.declared(), 'sim_day': state['sim_day'], 'overlay_state_digest': overlay.state_digest(state),
            'entries': entries, 'accounts': accounts, 'subledger': subledger, 'balance_groups': groups,
            'memo_balances': memo, 'chart_status': chart_status(), 'conservation': conservation,
        }


def _aggregate(entries):
    totals = {}
    sub = {}
    for entry in entries:
        dims = entry['dimensions']
        for line in entry['lines']:
            code, side, amount = line['account'], line['side'], line['amount']
            totals.setdefault(code, [0, 0])[0 if side == 'debit' else 1] += amount
            key = (code, dims['asset'], dims['advance_id'] or '', dims['claim_id'] or '')
            sub.setdefault(key, [0, 0])[0 if side == 'debit' else 1] += amount
    accounts = []
    for code in sorted(totals):
        name, klass, normal = CHART[code]
        debit, credit = totals[code]
        balance = debit - credit if normal == 'debit' else credit - debit
        # 1000 is a contra memo in simulation: a draw credits it, so its debit-normal balance is <= 0.
        if balance < 0 and code != '1000':
            _fail()
        accounts.append({'code': code, 'name': name, 'class': klass, 'normal': normal,
                         'adopted_in_note': code not in CANDIDATE_ONLY,
                         'debit_total': debit, 'credit_total': credit, 'balance': balance})
    subledger = [{'code': code, 'asset': asset, 'advance_id': advance or None, 'claim_id': claim or None,
                  'debit_total': debit, 'credit_total': credit}
                 for (code, asset, advance, claim), (debit, credit) in sorted(sub.items())]
    return accounts, subledger


def _interest_totals(accounts):
    by = {row['code']: row for row in accounts}

    def get(code, field):
        return by.get(code, {field: 0})[field]

    return get('1110', 'debit_total') == get('4100', 'credit_total') + get('4110', 'credit_total') \
        and get('9700', 'debit_total') == get('9790', 'credit_total')


# ---------------------------------------------------------------- reconciliation checks

def _code_totals(coa):
    accounts = coa.get('accounts') if type(coa) is dict else None
    if type(accounts) is not list:
        return None
    out = {}
    for row in accounts:
        if type(row) is not dict or type(row.get('code')) is not str:
            return None
        out[row['code']] = row
    return out


def _sum(rows, prefix, field):
    return sum(row.get(field, 0) for row in rows if str(row.get('code', '')).startswith(prefix + ':'))


def totals_match_v1(coa, v1):
    """coa_candidate_totals_vs_v1: the renamed accounts carry the same totals as V1."""
    by = _code_totals(coa)
    v1_accounts = v1.get('accounts') if type(v1) is dict else None
    if by is None or type(v1_accounts) is not list:
        return False

    def field(code, name):
        return by.get(code, {}).get(name, 0)

    return (
        field('1100', 'balance') == _sum(v1_accounts, 'SIM_ADVANCE_OBLIGATION', 'balance')
        and field('1100', 'debit_total') == _sum(v1_accounts, 'SIM_ADVANCE_EXPOSURE', 'debit_total')
        and field('1100', 'credit_total') == _sum(v1_accounts, 'SIM_REPAY_MEMO', 'credit_total')
        and field('9100', 'debit_total') == _sum(v1_accounts, 'SIM_CLAIM_FACE', 'debit_total')
        and field('9110', 'credit_total') == _sum(v1_accounts, 'SIM_PAYEE_OBLIGATION', 'credit_total')
    )


def interest_matches_ledger(coa, overlay_entries):
    """interest_ledger_vs_projection: the folded overlay totals equal 1110 + 9700, per advance."""
    by = _code_totals(coa)
    entries = coa.get('entries') if type(coa) is dict else None
    if by is None or type(entries) is not list:
        return False
    try:
        state = overlay.fold(list(overlay_entries))
    except overlay.OverlayError:
        return False
    posted = {}
    for entry in entries:
        for line in entry.get('lines', ()):
            if line.get('account') in ('1110', '9700') and line.get('side') == 'debit':
                advance = entry.get('dimensions', {}).get('advance_id')
                posted[advance] = posted.get(advance, 0) + line['amount']
    folded = {advance: row['posted_contract_krw'] + row['posted_default_krw']
              for advance, row in state['advances'].items()
              if row['posted_contract_krw'] + row['posted_default_krw']}
    if posted != folded:
        return False
    return _interest_totals(list(by.values()))
