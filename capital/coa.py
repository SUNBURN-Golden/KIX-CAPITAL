"""Additive CAPITAL-COA-V1 candidate projection (chart SIMULATION_FIXED_V2).

SIMULATED and SYNTHETIC_UNADOPTED. The chart is the CAPITAL-COA-V1 mapping of
docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md, a working assumption pending
professional review. Nothing here is a ledger of record, a revenue-recognition
adoption or a tax position, and no posting is a payment. SIMULATION_FIXED_V1
(capital/projection.py) stays the default and is not touched: the candidate runs
V1 first, which validates the journal and the evidence, then renames V1 accounts
to COA codes and adds interest, payment, recovery and write-off overlay postings.

The chart is a literal because the zipapp carries no docs/ to read it from (same
precedent as capital/assets.py). tests/test_coa_candidate.py fences it against the note.
"""
from __future__ import annotations

import copy
import re
from types import MappingProxyType

from capital import assets, overlay, risk
from capital.resources import note_path, read_note
from capital.projection import ProjectionError, ProjectionPort, SimulationProjection

CHART_VERSION = 'SIMULATION_FIXED_V2'
COA_VERSION = 'CAPITAL-COA-V1'
MODE = 'coa-candidate'
TERMS_NOT_BOUND = 'NOT_BOUND'
CANDIDATE_ONLY = ('9790', '9810', '9890')

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
    '9810': ('MEMO_UNAPPLIED_CASH_HELD', 'MEMO_OFF_BALANCE', 'debit'),
    '9890': ('MEMO_UNAPPLIED_CASH_CONTRA', 'MEMO_OFF_BALANCE', 'credit'),
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
_NOT_RECORDED = ('1190', '3100', '3200', '5100')
_RESERVED = ('1300', '2300')
_NOT_POSTED = ('9200', '9300', '9400', '9500')
_EVIDENCE_CODES = frozenset({'9100', '9110'})
_SIDES = ('debit', 'credit')


def _fail(code='PROJECTION_INVARIANT'):
    raise ProjectionError(code)


def asset_id(spec):
    return f"{spec['namespace']}:{spec['reference']}"


def chart_status(allowance_bound=False):
    """Every chart code with the status this candidate gives it. Nothing is silently dropped."""
    rows = []
    for code, (name, klass, normal) in CHART.items():
        if code in _DERIVED:
            status = 'DERIVED_MEMO'
        elif code in ('1190', '5100') and allowance_bound:
            status = STATUS_POSTED
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


NEW_SOURCES = ('OVERLAY_REPAYMENT', 'OVERLAY_RECOVERY', 'OVERLAY_WRITEOFF')
KNOWN_SOURCES = frozenset(('EVIDENCE', 'JOURNAL', 'OVERLAY_INTEREST') + NEW_SOURCES + ('ALLOWANCE',))
_ALLOWED = {
    'OVERLAY_REPAYMENT': frozenset(('1000', '1110', '4110', '9700', '9790', '9810', '9890')),
    'OVERLAY_RECOVERY': frozenset(('1000', '1100', '1110', '4110', '4300', '9700', '9790')),
    'OVERLAY_WRITEOFF': frozenset(('5200', '1100', '4100', '4110', '1110', '9700', '9790')),
}


class _Open:
    """Unpaid recognized and suspended interest, in overlay order, per advance/kind."""

    def __init__(self):
        self.balances = {}

    def accrue(self, advance, payload, suspended):
        for kind, field in (('CONTRACT', 'posted_contract_krw'), ('DEFAULT', 'posted_default_krw')):
            self.balances.setdefault((advance, kind), [0, 0])[int(suspended)] += payload[field]

    def cash(self, advance, allocation):
        lines = []
        for kind, field in (('DEFAULT', 'default_interest_krw'), ('CONTRACT', 'interest_krw')):
            amount = allocation[field]
            balances = self.balances.setdefault((advance, kind), [0, 0])
            recognized = min(amount, balances[0])
            suspended = amount - recognized
            if suspended > balances[1]:
                _fail()
            balances[0] -= recognized
            balances[1] -= suspended
            if amount:
                lines.append(_line('1000', 'debit', amount, interest_kind=kind))
            if recognized:
                lines.append(_line('1110', 'credit', recognized, interest_kind=kind))
            if suspended:
                lines.extend((_line('4110', 'credit', suspended, interest_kind=kind),
                              _line('9790', 'debit', suspended, interest_kind=kind),
                              _line('9700', 'credit', suspended, interest_kind=kind)))
        return lines

    def writeoff(self, advance, payload):
        lines = []
        reversed_total = released_total = 0
        for kind, income in (('CONTRACT', '4100'), ('DEFAULT', '4110')):
            recognized, suspended = self.balances.setdefault((advance, kind), [0, 0])
            if recognized:
                lines.extend((_line(income, 'debit', recognized, interest_kind=kind),
                              _line('1110', 'credit', recognized, interest_kind=kind)))
            if suspended:
                lines.extend((_line('9790', 'debit', suspended, interest_kind=kind),
                              _line('9700', 'credit', suspended, interest_kind=kind)))
            reversed_total += recognized
            released_total += suspended
            self.balances[advance, kind] = [0, 0]
        if reversed_total != payload['accrued_interest_reversed_krw'] or \
                released_total != payload['suspended_interest_released_krw']:
            _fail()
        return lines


class CoaCandidateProjection(ProjectionPort):
    """Second ProjectionPort implementation. Selected only by mode=coa-candidate."""

    CHART_VERSION = CHART_VERSION
    COA_VERSION = COA_VERSION

    def project(self, journal, evidence, *, overlay_entries=(), asset=None, allowance_context=None):
        spec = assets.KRW if asset is None else asset
        if not assets.matches(spec):
            _fail('ASSET_MISMATCH')
        asset = asset_id(spec)
        v1 = SimulationProjection().project(journal, evidence)
        try:
            state = overlay.fold(list(overlay_entries), len(journal))
        except overlay.OverlayError as exc:
            raise ProjectionError() from exc
        # The overlay fold deliberately ignores identical transport duplicates. Posting does too.
        overlay_entries = list({e['overlay_id']: e for e in overlay_entries}.values())
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
        open_interest = _Open()
        for record in overlay_entries:
            kind, payload = record['kind'], record['payload']
            if kind not in (overlay.KIND_INTEREST, overlay.KIND_REPAYMENT, 'RECOVERY', 'WRITEOFF'):
                continue
            advance_id = payload['advance_ref'] if kind == overlay.KIND_REPAYMENT else payload['advance_id']
            if kind == overlay.KIND_INTEREST:
                suspended = advance_id in default_index and record['after_journal_index'] > default_index[advance_id]
                open_interest.accrue(advance_id, payload, suspended)
                lines = _interest_lines(payload, suspended)
                source, terms = 'OVERLAY_INTEREST', payload['terms_version']
            elif kind == overlay.KIND_REPAYMENT:
                lines = open_interest.cash(advance_id, payload['allocation'])
                delta = payload['allocation']['unapplied_after_krw'] - payload['unapplied_before_krw']
                if delta:
                    lines.extend((_line('9810', 'debit' if delta > 0 else 'credit', abs(delta)),
                                  _line('9890', 'credit' if delta > 0 else 'debit', abs(delta))))
                source, terms = 'OVERLAY_REPAYMENT', payload['terms_binding']['terms_version']
            elif kind == 'RECOVERY':
                source, terms = 'OVERLAY_RECOVERY', payload['policy']['terms_version']
                if payload['phase'] == 'POST_WRITEOFF':
                    lines = [_line('1000', 'debit', payload['amount_krw']),
                             _line('4300', 'credit', payload['amount_krw'])]
                else:
                    allocation = payload['allocation']
                    if sum(allocation.values()) != payload['amount_krw']:
                        _fail()
                    lines = open_interest.cash(advance_id, allocation)
                    if allocation['principal_krw']:
                        lines.extend((_line('1000', 'debit', allocation['principal_krw']),
                                      _line('1100', 'credit', allocation['principal_krw'])))
            else:
                source, terms = 'OVERLAY_WRITEOFF', payload['policy']['terms_version']
                lines = [_line('5200', 'debit', payload['writeoff_principal_krw']),
                         _line('1100', 'credit', payload['writeoff_principal_krw'])]
                lines.extend(open_interest.writeoff(advance_id, payload))
            if lines:
                entries.append({
                    'step': len(entries) + 1, 'source': source, 'txn_id': record['overlay_id'],
                    'dimensions': _dimensions(asset, advance_id, claim_of.get(advance_id), record['sim_day'], terms),
                    'lines': lines})
        allowance, reserve_pool, entries = allowance_fold(
            journal, overlay_entries, entries, allowance_context, spec)
        for step, entry in enumerate(entries, 1):
            entry['step'] = step
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
        interest_by_kind = _interest_totals(accounts, entries)
        reductions = sum(r['principal_recovered_krw'] + r['written_off_krw']
                         for r in state.get('recovery', {}).get('advances', {}).values())
        conservation = [
            {'predicate': 'DEBITS_EQUAL_CREDITS_PER_ASSET_SIM_DAY', 'matched': all(row['matched'] for row in groups)},
            {'predicate': 'CLAIM_FACE_ONLY_IN_MEMO_9100_9110', 'matched': True},
            {'predicate': 'MEMO_9100_EQUALS_9110',
             'matched': balances.get('9100', {'debit_total': 0})['debit_total']
             == balances.get('9110', {'credit_total': 0})['credit_total']},
            {'predicate': 'PRINCIPAL_1100_EQUALS_V1_OUTSTANDING',
             'matched': principal['balance'] == sum(row['outstanding'] for row in v1['read_model']['advances']) - reductions},
            {'predicate': 'ACCRUED_1110_EQUALS_INCOME_4100_4110', 'matched': interest_by_kind},
            {'predicate': 'MEMO_9810_EQUALS_9890',
             'matched': balances.get('9810', {'balance': 0})['balance']
             == balances.get('9890', {'balance': 0})['balance']},
            {'predicate': 'WRITTEN_OFF_ADVANCE_HAS_NO_OPEN_1110_9700',
             'matched': all(not any(open_interest.balances.get((advance, kind), (0, 0)))
                            for advance, r in state.get('recovery', {}).get('advances', {}).items()
                            if r['writeoff_sim_day'] is not None for kind in ('CONTRACT', 'DEFAULT'))},
            {'predicate': 'NO_REAL_EFFECT', 'matched': True},
        ]
        if allowance['status'] == 'BOUND':
            conservation.extend([
                {'predicate': 'ALLOWANCE_WITHIN_EFFECTIVE_PRINCIPAL',
                 'matched': all(0 <= row['allowance_krw'] <= row['effective_principal_krw']
                                for row in allowance['rows'])},
                {'predicate': 'ALLOWANCE_1190_EQUALS_NET_5100',
                 'matched': balances.get('1190', {'balance': 0})['balance']
                 == balances.get('5100', {'balance': 0})['balance'] == allowance['allowance_component_krw']},
            ])
        if not all(row['matched'] for row in conservation):
            _fail()
        return {
            'assets': assets.declared(), 'sim_day': state['sim_day'], 'overlay_state_digest': overlay.state_digest(state),
            'entries': entries, 'accounts': accounts, 'subledger': subledger, 'balance_groups': groups,
            'memo_balances': memo, 'chart_status': chart_status(allowance['status'] == 'BOUND'),
            'conservation': conservation, 'allowance': allowance, 'reserve_pool': reserve_pool,
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


def _interest_totals(accounts, entries=()):
    by = {row['code']: row for row in accounts}

    def get(code, field):
        return by.get(code, {field: 0})[field]

    cash_income = sum(line['amount'] for entry in entries
                      if entry['source'] in ('OVERLAY_REPAYMENT', 'OVERLAY_RECOVERY')
                      for line in entry['lines'] if line['account'] == '4110' and line['side'] == 'credit')
    return get('1110', 'debit_total') == get('4100', 'credit_total') + get('4110', 'credit_total') - cash_income \
        and get('9700', 'debit_total') == get('9790', 'credit_total') \
        and get('9700', 'credit_total') == get('9790', 'debit_total')


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


def totals_match_v1(coa, v1, overlay_entries=()):
    """coa_candidate_totals_vs_v1: the renamed accounts carry the same totals as V1."""
    by = _code_totals(coa)
    v1_accounts = v1.get('accounts') if type(v1) is dict else None
    if by is None or type(v1_accounts) is not list:
        return False

    def field(code, name):
        return by.get(code, {}).get(name, 0)

    state = _fold(overlay_entries)
    if state is None:
        return False
    reduction = sum(r['principal_recovered_krw'] + r['written_off_krw']
                    for r in state.get('recovery', {}).get('advances', {}).values())
    posted_reduction = sum(line['amount'] for entry in coa.get('entries', ())
                           if entry.get('source') in ('OVERLAY_RECOVERY', 'OVERLAY_WRITEOFF')
                           for line in entry.get('lines', ())
                           if line.get('account') == '1100' and line.get('side') == 'credit')
    return (
        posted_reduction == reduction
        and field('1100', 'balance') + reduction == _sum(v1_accounts, 'SIM_ADVANCE_OBLIGATION', 'balance')
        and field('1100', 'debit_total') == _sum(v1_accounts, 'SIM_ADVANCE_EXPOSURE', 'debit_total')
        and field('1100', 'credit_total') - reduction == _sum(v1_accounts, 'SIM_REPAY_MEMO', 'credit_total')
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
    return _interest_totals(list(by.values()), entries)


def _fold(entries):
    try:
        return overlay.fold(list(entries))
    except overlay.OverlayError:
        return None


def _overlay_postings(coa):
    """Collect new-source lines; unknown sources and cross-source accounts fail closed."""
    postings = {}
    try:
        for entry in coa['entries']:
            source = entry['source']
            if source not in KNOWN_SOURCES:
                return None
            if source == 'ALLOWANCE':
                if any(line['account'] not in ('1190', '5100') for line in entry['lines']):
                    return None
                continue
            if source not in NEW_SOURCES:
                continue
            advance = entry['dimensions']['advance_id']
            if not isinstance(advance, str) or not advance:
                return None
            target = postings.setdefault((source, advance), {})
            for line in entry['lines']:
                if line['account'] not in _ALLOWED[source] or line['side'] not in _SIDES \
                        or type(line['amount']) is not int or line['amount'] < 0:
                    return None
                key = (line['account'], line['side'], line.get('interest_kind'))
                target[key] = target.get(key, 0) + line['amount']
    except (KeyError, TypeError):
        return None
    return postings


def _account_guard(coa):
    by = _code_totals(coa)
    if by is None:
        return False
    for code in ('4300', '5200', '9810', '9890'):
        totals = {'debit': 0, 'credit': 0}
        for entry in coa['entries']:
            for line in entry['lines']:
                if line['account'] != code:
                    continue
                if entry['source'] not in NEW_SOURCES or line['side'] not in _SIDES:
                    return False
                totals[line['side']] += line['amount']
        if any(by.get(code, {}).get(side + '_total', 0) != amount for side, amount in totals.items()):
            return False
    return True


def _expected(state, source):
    """Independent expected metrics from folded totals and recovery ledger records."""
    expected = {}
    if source == 'OVERLAY_REPAYMENT':
        for advance, row in state.get('repayment', {}).get('advances', {}).items():
            expected[advance] = (row['paid_default_krw'], row['paid_interest_krw'],
                                 row['paid_default_krw'] + row['paid_interest_krw'], row['unapplied_cash_krw'])
    elif source == 'OVERLAY_RECOVERY':
        for advance, row in state.get('recovery', {}).get('advances', {}).items():
            records = [r for r in state['sections']['recovery_ledger']
                       if r['advance_id'] == advance and r['entry_kind'] == 'RECOVERY']
            expected[advance] = (row['principal_recovered_krw'], row['paid_default_krw'], row['paid_interest_krw'],
                                 sum(r['amount_krw'] for r in records if r['phase'] == 'POST_WRITEOFF'),
                                 sum(r['amount_krw'] for r in records))
    else:
        for row in state['sections']['recovery_ledger']:
            if row['entry_kind'] == 'WRITEOFF':
                expected[row['advance_id']] = (row['writeoff_principal_krw'], row['accrued_interest_reversed_krw'],
                                                row['suspended_interest_released_krw'])
    return expected


def _matches_overlay(coa, overlay_entries, source):
    state, postings = _fold(overlay_entries), _overlay_postings(coa)
    if state is None or postings is None or not _account_guard(coa):
        return False
    actual = {}
    for (entry_source, advance), amounts in postings.items():
        if entry_source != source:
            continue

        def total(accounts, side, kind=None):
            return sum(amount for (account, line_side, line_kind), amount in amounts.items()
                       if account in accounts and line_side == side and (kind is None or line_kind == kind))

        if source == 'OVERLAY_REPAYMENT':
            metrics = (total(('1110', '4110'), 'credit', 'DEFAULT'),
                       total(('1110', '4110'), 'credit', 'CONTRACT'), total(('1000',), 'debit'),
                       total(('9810',), 'debit') - total(('9810',), 'credit'))
        elif source == 'OVERLAY_RECOVERY':
            metrics = (total(('1100',), 'credit'), total(('1110', '4110'), 'credit', 'DEFAULT'),
                       total(('1110', '4110'), 'credit', 'CONTRACT'), total(('4300',), 'credit'),
                       total(('1000',), 'debit'))
        else:
            metrics = (total(('5200',), 'debit'), total(('4100', '4110'), 'debit'), total(('9700',), 'credit'))
        actual[advance] = metrics
    # Equality over the union rejects both missing and unexpected advance IDs.
    return {key: value for key, value in _expected(state, source).items() if any(value)} == \
        {key: value for key, value in actual.items() if any(value)}


def payments_match_ledger(coa, overlay_entries):
    """payment_ledger_vs_projection: interest cash and held memo equal the payment fold."""
    return _matches_overlay(coa, overlay_entries, 'OVERLAY_REPAYMENT')


def recoveries_match_ledger(coa, overlay_entries):
    """recovery_ledger_vs_projection: principal, interest, late recovery and cash tie per advance."""
    return _matches_overlay(coa, overlay_entries, 'OVERLAY_RECOVERY')


def writeoffs_match_ledger(coa, overlay_entries):
    """writeoff_ledger_vs_projection: principal loss, interest reversal and memo release tie."""
    return _matches_overlay(coa, overlay_entries, 'OVERLAY_WRITEOFF')


# The separate V2 allowance candidate reads the adopted decision at runtime. Rates
# are exclusively TERMS inputs; the note's descriptive_bps is never a fallback.
_ALLOWANCE_ITEMS = (
    'allowance_measurement_basis', 'allowance_posting_timing', 'allowance_true_up_and_reversal',
    'allowance_after_acceleration_and_default', 'reserve_pool_3100_3200_appropriation_link',
    'recon_check_allowance_vs_risk_reserve', 'cut_scope_and_export_section',
)
_ALLOWANCE_LABELS = {'label': 'SIMULATED', 'accounting_policy': 'SYNTHETIC_UNADOPTED',
                     'policy_adopted': False, 'export': 'NOT_IN_EXPORT_V1'}
_ZERO_BUCKET = 'UNFUNDED_OR_WRITTEN_OFF_OR_CLOSED'


def allowance_policy():
    note = read_note(note_path('CAPITAL_LOSS_ALLOWANCE.md'))
    block = note['block']
    if type(block) is not dict or block.get('policy_adopted') is not False:
        return None
    entries = block.get('entries', {})
    if any(type(entries.get(name)) is not dict or entries[name].get('status') != 'ADOPTED'
           or type(entries[name].get('value')) is not dict for name in _ALLOWANCE_ITEMS):
        return None
    # Fail closed for unsupported semantics, including a changed posting profile.
    if (block.get('allowance_policy_version') != 'CAPITAL-LOSS-ALLOWANCE-V2'
            or block.get('posting_profile') != 'ALLOWANCE_CANDIDATE_V2'
            or block.get('bases', {}).get('chart_version') != COA_VERSION
            or entries['allowance_measurement_basis']['value'].get('bucket_order') != [
                _ZERO_BUCKET, 'DEFAULTED', 'PAST_DUE_OR_ACCELERATED', 'T2_PERFORMING', 'T1_PERFORMING']
            or entries['allowance_measurement_basis']['value'].get('formula') !=
                'floor(effective_principal * bucket_bps / 10000); sum rounded levels'
            or entries['allowance_posting_timing']['value'].get('measurement') !=
                'Every recorded sim_day tick and economic event; replay crossed stage transitions'
            or entries['allowance_true_up_and_reversal']['value'].get('full_reversal_and_repost') is not False
            or entries['allowance_after_acceleration_and_default']['value'].get('posting_profile') != block['posting_profile']
            or entries['reserve_pool_3100_3200_appropriation_link']['value'].get('mode') != 'RESERVE_POOL_MEMO_V1'
            or entries['cut_scope_and_export_section']['value'].get('cut') !=
                ['f04_state_digest', 'overlay_digest', 'overlay_sim_day']
            or entries['reserve_pool_3100_3200_appropriation_link']['value'].get('post_3100_to_3200') is not False
            or entries['recon_check_allowance_vs_risk_reserve']['value'].get('tolerance_krw') != 0):
        return None
    return {'terms_version': block['bases']['terms_version'], 'chart_version': block['bases']['chart_version'],
            'allowance_policy_version': block['allowance_policy_version'],
            'posting_profile': block['posting_profile'], 'decision_note_digest': note['note_sha256']}


def allowance_not_bound(reason):
    common = {**_ALLOWANCE_LABELS, 'status': 'NOT_BOUND', 'reason': reason}
    return ({**common, 'rows': [], 'allowance_component_krw': None, 'effective_principal_krw': None,
             'source_cut': None, 'population': None, 'policy_context': None},
            {**common, 'source_cut': None, 'population': None, 'policy_context': None,
             'memo_version': 'RESERVE_POOL_MEMO_V1',
             'loss_reserve': {'status': 'NOT_BOUND', 'absorbed_krw': 0},
             'allowance_component_krw': None, 'portfolio_floor_krw': None,
             'pool_target_krw': None, 'binding_component': None, 'funded_krw': None,
             'shortfall_krw': None, 'floor_bps': None, 'floor_formula': None})


def allowance_fold(journal, overlay_entries, entries, context, spec):
    """Replay anchored economic events and crossed opening-day stages, without writes.

    Principal is reconstructed from draw/repay, then only unreflected recovery and
    write-off principal is deducted. Interest cash and post-writeoff recovery never
    change it. A complete event is measured once; write-off releases precede gross loss.
    """
    policy = allowance_policy()
    if context is None or policy is None:
        a, memo = allowance_not_bound('allowance context or adopted policy absent')
        return a, memo, entries
    state = overlay.fold(list(overlay_entries), len(journal))
    population = {'asset': copy.deepcopy(spec), 'advance_ids': sorted({e['advance_id'] for e in journal})}
    cut = context.get('source_cut')
    if (context.get('population') != population or context.get('policy_context') != policy
            or type(cut) is not dict or cut.get('overlay_digest') != overlay.state_digest(state)
            or cut.get('overlay_sim_day') != state['sim_day']
            or context.get('journal_digest') != risk._digest(journal)):
        a, memo = allowance_not_bound('context does not describe replay cut/population/policy')
        return a, memo, entries
    weights = (context.get('reserve_terms') or {}).get('provision_bps_of_outstanding')
    facts = {r['advance_id']: r for r in context.get('advances', [])}
    if (set(facts) != set(population['advance_ids']) or type(weights) is not dict
            or context.get('terms_version') != policy['terms_version']
            or any(type(bps) is not int or not 0 <= bps <= 10000 for bps in weights.values())):
        a, memo = allowance_not_bound('terms or population evidence absent')
        return a, memo, entries
    for event in journal:
        if event['op'] == 'draw':
            ledger = facts[event['advance_id']].get('ledger_terms')
            if (not ledger or ledger.get('terms_version') != policy['terms_version']
                    or type(ledger.get('maturity_day')) is not int or ledger['maturity_day'] < 0
                    or risk.reserve_bucket(weights, ledger.get('tier')) is None
                    or risk.reserve_bucket(weights, ledger.get('tier'), past_due=True) is None
                    or risk.reserve_bucket(weights, ledger.get('tier'), defaulted=True) is None):
                a, memo = allowance_not_bound('draw tier or maturity evidence absent')
                return a, memo, entries
    rows = {ref: {'advance_id': ref, 'tier': 'NOT_APPLICABLE', 'effective_principal_krw': 0,
                  'allowance_krw': 0, 'bucket': _ZERO_BUCKET, 'bps': 0}
            for ref in population['advance_ids']}
    runtime = {ref: {'drawn': False, 'defaulted': False, 'accelerated': False, 'closed': False,
                     'written_off': False, 'fsm_principal': 0, 'deductions': 0}
               for ref in rows}
    originals = {(entry['source'], entry['txn_id']): entry for entry in entries if entry['source'] != 'EVIDENCE'}
    ordered = [entry for entry in entries if entry['source'] == 'EVIDENCE']
    day = 0

    def measure(ref, at, operation, anchor, *, effective_day=None, source_reserve_step=None):
        row, live = rows[ref], runtime[ref]
        principal = live['fsm_principal'] - live['deductions']
        if principal < 0 or ((live['closed'] or live['written_off']) and principal != 0):
            _fail()
        bucket = _ZERO_BUCKET
        if live['drawn'] and not (live['closed'] or live['written_off']) and principal:
            ledger = facts[ref]['ledger_terms']
            bucket = risk.reserve_bucket(weights, row['tier'], defaulted=live['defaulted'],
                                         past_due=live['accelerated'] or at > ledger['maturity_day'])
        if bucket is None:
            _fail()
        bps = 0 if bucket == _ZERO_BUCKET else weights[bucket]
        target = risk.provision_level(principal, bps)
        delta = target - row['allowance_krw']
        if delta:
            legs = [('5100', 'debit'), ('1190', 'credit')] if delta > 0 else [('1190', 'debit'), ('5100', 'credit')]
            identity = f"{policy['allowance_policy_version']}:{ref}:{operation}"
            evidence = {'operation_id': operation, 'bucket_from': row['bucket'], 'bucket_to': bucket,
                        'policy_context': copy.deepcopy(policy), 'source_cut': copy.deepcopy(cut),
                        'replay_anchor': anchor, 'effective_sim_day': effective_day,
                        'source_reserve_step_version': source_reserve_step}
            dims = _dimensions(asset_id(spec), ref, facts[ref]['case']['claim_id'], at, policy['terms_version'])
            dims['tier'] = row['tier']
            ordered.append({'source': 'ALLOWANCE', 'txn_id': identity, 'dimensions': dims,
                            'evidence': evidence, 'lines': [
                                _line(code, side, abs(delta), leg=f'{identity}:{code}:{side}') for code, side in legs]})
        row.update(effective_principal_krw=principal, allowance_krw=target, bucket=bucket, bps=bps)
        if not 0 <= target <= principal:
            _fail()

    def move(to_day, anchor):
        nonlocal day
        if to_day < day:
            _fail()
        transitions = sorted((facts[ref]['ledger_terms']['maturity_day'] + 1, ref)
                             for ref, live in runtime.items() if live['drawn']
                             and day < facts[ref]['ledger_terms']['maturity_day'] + 1 <= to_day)
        for at, ref in transitions:
            measure(ref, at, f'STAGE_TRANSITION:{ref}:{at}', anchor)
        day = to_day

    overlays = {}
    for sequence, record in enumerate(overlay_entries):
        overlays.setdefault(record['after_journal_index'], []).append((sequence, record))
    for index in range(len(journal) + 1):
        for sequence, record in overlays.get(index, []):
            anchor = {'journal_index': index, 'overlay_sequence': sequence, 'overlay_id': record['overlay_id']}
            move(record['sim_day'], anchor)
            kind, payload = record['kind'], record['payload']
            ref = payload.get('advance_id', payload.get('advance_ref'))
            if ref is not None and ref not in rows:
                _fail()
            original_source = {overlay.KIND_INTEREST: 'OVERLAY_INTEREST', overlay.KIND_REPAYMENT: 'OVERLAY_REPAYMENT',
                               'RECOVERY': 'OVERLAY_RECOVERY', 'WRITEOFF': 'OVERLAY_WRITEOFF'}.get(kind)
            original = originals.pop((original_source, record['overlay_id']), None)
            if original and kind != 'WRITEOFF':
                ordered.append(original)
            if kind in (overlay.KIND_MARGIN_ACCELERATION, 'acceleration_event'):
                runtime[ref]['accelerated'] = True
            elif kind == 'RECOVERY' and payload['phase'] != 'POST_WRITEOFF':
                runtime[ref]['deductions'] += payload['allocation']['principal_krw']
            elif kind == 'WRITEOFF':
                live = runtime[ref]
                if live['written_off'] or payload['writeoff_principal_krw'] != live['fsm_principal'] - live['deductions']:
                    _fail()
                live['deductions'] += payload['writeoff_principal_krw']
                live['written_off'] = True
            if kind in (overlay.KIND_MARGIN_ACCELERATION, 'acceleration_event', 'RECOVERY', 'WRITEOFF'):
                measure(ref, day, record['overlay_id'], anchor,
                        effective_day=payload.get('writeoff_effective_sim_day', payload.get('effective_sim_day')),
                        source_reserve_step=payload.get('reserve_step_version'))
            if original and kind == 'WRITEOFF':
                ordered.append(original)
        if index == len(journal):
            break
        event = journal[index]
        ref, op = event['advance_id'], event['op']
        live, row = runtime[ref], rows[ref]
        anchor = {'journal_index': index, 'overlay_sequence': None, 'overlay_id': None}
        move(overlay.draw_day_for(overlay_entries, index), anchor)
        original = originals.pop(('JOURNAL', event['idempotency_key']), None)
        if original:
            ordered.append(original)
        if op == 'draw':
            if live['drawn']:
                _fail()
            live['drawn'] = True
            live['fsm_principal'] = facts[ref]['case']['amount']
            row['tier'] = facts[ref]['ledger_terms']['tier']
        elif op == 'repay':
            live['fsm_principal'] -= event['body']['amount']
        elif op == 'default':
            live['defaulted'] = True
        elif op == 'close':
            live['closed'] = True
        measure(ref, day, event['idempotency_key'], anchor)
    if originals:
        _fail()
    for ref, live in runtime.items():
        if (live['fsm_principal'] != facts[ref]['case']['outstanding_exposure']
                or (facts[ref]['case']['phase'] == 'CLOSED' and live['fsm_principal'] != 0)):
            _fail()
    amount = sum(r['allowance_krw'] for r in rows.values())
    principal = sum(r['effective_principal_krw'] for r in rows.values())
    net_expense = sum((1 if line['side'] == 'debit' else -1) * line['amount']
                      for e in ordered if e['source'] == 'ALLOWANCE' for line in e['lines'] if line['account'] == '5100')
    if net_expense != amount:
        _fail()
    common = {**_ALLOWANCE_LABELS, 'source_cut': copy.deepcopy(cut), 'population': population,
              'policy_context': policy}
    block = {**common, 'status': 'BOUND', 'reason': None, 'rows': list(rows.values()),
             'allowance_component_krw': amount, 'effective_principal_krw': principal}
    formula = context['reserve_terms'].get('pool_target')
    match = re.fullmatch(r'max\(sum of provisions, (\d+) bps of portfolio outstanding\)', formula or '')
    floor_bps = int(match[1]) if match and int(match[1]) <= 10000 else None
    floor = None if floor_bps is None else risk.provision_level(principal, floor_bps)
    target = None if floor is None else max(amount, floor)
    memo = {**common, 'status': 'NOT_BOUND' if floor is None else 'MEMO_NOT_POSTED',
            'reason': 'unverified TERMS pool_target' if floor is None else None,
            'memo_version': 'RESERVE_POOL_MEMO_V1', 'allowance_component_krw': amount,
            'portfolio_floor_krw': floor, 'pool_target_krw': target, 'floor_bps': floor_bps,
            'floor_formula': formula, 'binding_component': None if floor is None else (
                'ALLOWANCE' if amount >= floor else 'PORTFOLIO_FLOOR'),
            'funded_krw': 0, 'shortfall_krw': target,
            'loss_reserve': {'status': 'NOT_BOUND', 'absorbed_krw': 0}}
    return block, memo, ordered
