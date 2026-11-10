"""SIMULATED, seeded finance properties over the existing in-process folds.

Specs contain synthetic inputs only. Materialization regenerates dependent schedules
and partial repayments with an independent Fraction oracle, so shrinking never keeps
stale principals or timestamps. No server, persistence, provider or product terms
are introduced. SYNTHETIC_PROBE policies are in-memory arithmetic probes only.
"""
from __future__ import annotations

import copy
import json
import random
from fractions import Fraction

from capital import forecast, overlay, risk
from capital.terms import BPS_SCALE, DecisionNoteTermsPolicy

FORMAT = 'KIX_CAPITAL_FINANCE_PROPERTIES_V1'
LABEL = 'SIMULATED'
SEED_BASE = 74820000
DEFAULT_CASES = 200
PROPERTIES = ('accrual_additivity', 'allocation_conservation', 'rollup_cap_check',
              'risk_bucket_sums', 'forecast_bucket_sums', 'stress_monotone')


def _value(terms, name):
    return terms.items[name]['value']


def _floor(value):
    return value.numerator // value.denominator


def generate(name, seed, terms):
    """Pinned stdlib PRNG, separate stream per property; no global random state."""
    rng = random.Random((PROPERTIES.index(name) << 32) | seed)
    bounds = overlay.load_bounds()
    if bounds is None:
        raise ValueError('overlay bounds not bound')
    minimum = _value(terms, 'interest_rate')['min_interest_days']
    subjects = [{'tier_idx': rng.randrange(len(_value(terms, 'interest_rate')['tiers'])),
                 'gate_match': rng.randrange(5) != 0, 'face': rng.randint(1, 1_000_000),
                 'draw_day': rng.randint(0, 12), 'role_idx': rng.randrange(3)}
                for _ in range(rng.randint(1, 6))]
    # Every cap probe has a matching positive-principal subject for the exact boundary.
    subjects[0]['gate_match'] = True
    segments = [{'len_days': rng.randint(14 + minimum, min(90, bounds['max_step_days'])),
                 'k': rng.randint(2, 8)} for _ in range(rng.randint(1, 3))]
    repayments = [{'segment_idx': i, 'subject_idx': rng.randrange(len(subjects)),
                   'cash_num': rng.randint(1, 3), 'cash_den': 4}
                  for i in range(len(segments)) if rng.randrange(2)]
    return {'subjects': subjects, 'segments': segments, 'repayments': repayments,
            'acceleration': ({'subject_idx': rng.randrange(len(subjects)),
                              'segment_idx': rng.randrange(len(segments)),
                              'window': rng.randint(0, 7)} if rng.randrange(2) else None),
            'settlement_day': rng.choice([None, 0, 7, 30, 60, 91, 200]),
            'cash': rng.randint(0, 2_000_000), 'probe': (seed - SEED_BASE) % 4}


def _oracle_increment(subject, start, end):
    t = subject['terms']
    elapsed = lambda day: 0 if day <= subject['draw_day'] else max(
        day - subject['draw_day'], t['min_interest_days'])
    before, after = elapsed(start), elapsed(end)
    contract = min(after, t['term_days']) - min(before, t['term_days'])
    default = after - before - contract
    return (Fraction(subject['principal'] * contract * t['contract_bps'], t['denominator']),
            Fraction(subject['principal'] * default * t['default_bps'], t['denominator']))


def _oracle_split(terms, principal, contract_due, default_due, cash):
    dues = {'DEFAULT_INTEREST': default_due, 'INTEREST': contract_due, 'PRINCIPAL': principal}
    paid = dict.fromkeys(dues, 0)
    for token in _value(terms, 'interest_rate')['repayment_allocation_order']:
        paid[token] = min(cash, dues[token])
        cash -= paid[token]
    return paid


def materialize(spec, terms):
    """Derive a valid book and event boundaries from a shrinkable plain JSON spec."""
    subjects = []
    tiers = _value(terms, 'interest_rate')['tiers']
    for i, item in enumerate(spec['subjects']):
        tier = tiers[item['tier_idx'] % len(tiers)]
        condition = tier['condition']
        gate = condition['settlement_gate'] if item['gate_match'] else 'SYNTHETIC_UNMATCHED'
        case = {'phase': 'DRAWN', 'amount': item['face'], 'outstanding_exposure': item['face'],
                'beneficiary_role': f"sim-role-{item['role_idx']}", 'next_repayment_sequence': 1}
        claim = {'refund_face': condition.get('refund_face', 0),
                 'obligations': [{'payee': 'organizer', 'outstanding': item['face'] * 4}]}
        ledger = terms.ledger_terms(case, claim, gate=gate, draw_day=item['draw_day'])
        if ledger is not None:
            ledger['writeoff_day'] = None
        subjects.append({'advance_id': f'sim-property-{i}', 'case': case, 'claim': claim,
                         'gate': gate, 'draw_day': item['draw_day'], 'principal': item['face'],
                         'terms': ledger})
    current = copy.deepcopy(subjects)
    exact = [[Fraction(0), Fraction(0)] for _ in subjects]
    paid = [[0, 0] for _ in subjects]
    segments, day = [], 0
    for index, item in enumerate(spec['segments']):
        end = day + item['len_days']
        k = min(item['k'], item['len_days'])
        ticks = [day + item['len_days'] * n // k for n in range(1, k + 1)]
        for i, subject in enumerate(current):
            if subject['terms'] is not None and end > subject['draw_day']:
                delta = _oracle_increment(subject, max(day, subject['draw_day']), end)
                exact[i] = [a + b for a, b in zip(exact[i], delta)]
        events = []
        for repayment in spec['repayments']:
            i = repayment['subject_idx']
            if repayment['segment_idx'] != index or i >= len(current):
                continue
            subject = current[i]
            if subject['terms'] is None or end <= subject['draw_day'] or subject['principal'] == 0:
                continue
            c, d = [_floor(value) - done for value, done in zip(exact[i], paid[i])]
            due = subject['principal'] + c + d
            cash = min(due, max(1, due * repayment['cash_num'] // repayment['cash_den']))
            split = _oracle_split(terms, subject['principal'], c, d, cash)
            paid[i][0] += split['INTEREST']
            paid[i][1] += split['DEFAULT_INTEREST']
            subject['principal'] -= split['PRINCIPAL']
            subject['case']['outstanding_exposure'] = subject['principal']
            events.append({'subject_idx': i, 'cash': cash})
        acceleration = None
        a = spec['acceleration']
        if a is not None and a['segment_idx'] == index and a['subject_idx'] < len(current):
            subject = current[a['subject_idx']]
            if subject['terms'] is not None:
                t = subject['terms']
                at = max(end, subject['draw_day'] + t['min_interest_days'])
                maturity = min(t['maturity_day'], at + a['window'])
                t.update(maturity_day=maturity, term_days=maturity - subject['draw_day'])
                acceleration = {'subject_idx': a['subject_idx'], 'maturity_day': maturity}
        segments.append({'start': day, 'end': end, 'ticks': ticks,
                         'repayments': events, 'acceleration': acceleration})
        day = end
    return {'label': LABEL, 'subjects': subjects, 'segments': segments, 'sim_day': day,
            'settlement_day': spec['settlement_day'], 'cash': spec['cash'], 'probe': spec['probe'],
            'final_subjects': current, 'oracle_exact': exact, 'oracle_paid': paid}


def valid(case):
    """Domain checks independent of the fold and its output (also used by shrinking)."""
    problems = []
    bounds = overlay.load_bounds()
    if not case['subjects'] or not case['segments'] or bounds is None:
        return ['empty book, segments or unbound bounds']
    for subject in case['subjects']:
        if subject['principal'] < 1 or subject['draw_day'] < 0:
            problems.append('principal or draw day')
    previous = 0
    for segment in case['segments']:
        if not 0 < segment['end'] - previous <= bounds['max_step_days']:
            problems.append('clock step')
        if segment['start'] != previous or segment['ticks'][-1] != segment['end']:
            problems.append('segment boundary')
        if any(a >= b for a, b in zip([previous] + segment['ticks'], segment['ticks'])):
            problems.append('subtick order')
        for event in segment['repayments']:
            if not 0 <= event['subject_idx'] < len(case['subjects']) or event['cash'] < 1:
                problems.append('repayment')
        a = segment['acceleration']
        if a is not None:
            subject = case['subjects'][a['subject_idx']]
            if a['maturity_day'] < subject['draw_day'] + subject['terms']['min_interest_days']:
                problems.append('acceleration before minimum')
        previous = segment['end']
    return problems


def _walk(case, terms, stepped):
    subjects = copy.deepcopy(case['subjects'])
    entries, state, serial = [], overlay.empty_state(), 0
    for segment in case['segments']:
        for day in segment['ticks'] if stepped else [segment['end']]:
            serial += 1
            entries.extend(overlay.advance_entries(
                f'sim-tick-{serial}', state, 0, to_day=day, reason=LABEL,
                binding={'terms_version': terms.version, 'status': terms.top},
                subjects=[s for s in subjects if s['terms'] is not None]))
            state = overlay.fold(entries)
        for j, event in enumerate(segment['repayments']):
            subject = subjects[event['subject_idx']]
            _, default, interest, held = overlay.repayment_position(
                state, subject['advance_id'], terms.ledger_denominator())
            split = terms.allocate(subject['principal'], interest_due=interest,
                                   default_interest_due=default, cash=event['cash'] + held)
            op = f'sim-repay-{serial}-{j}'
            entries.append(overlay.repayment_entry(
                op, state, journal_index=0, advance_ref=subject['advance_id'], amount=event['cash'],
                denominator=terms.ledger_denominator(), principal_before=subject['principal'],
                terms_version=terms.version, split=split,
                f04=(op, f'{op}:SIMULATED_REFERENCE') if split['to_principal'] else None))
            state = overlay.fold(entries)
            subject['principal'] -= split['to_principal']
        a = segment['acceleration']
        if a is not None:
            s = subjects[a['subject_idx']]
            s['terms'].update(maturity_day=a['maturity_day'],
                              term_days=a['maturity_day'] - s['draw_day'])
    return state


def _problem(code, detail):
    return {'code': code, 'detail': detail}


def check_accrual_additivity(case, terms):
    left, right = _walk(case, terms, True), _walk(case, terms, False)
    errors = []
    for i, subject in enumerate(case['subjects']):
        ref = subject['advance_id']
        for state in (left, right):
            record = state['advances'].get(ref, {})
            for n, suffix in enumerate(('contract', 'default')):
                exact = Fraction(record.get(f'cumulative_{suffix}_exact', '0/1'))
                posted = record.get(f'posted_{suffix}_krw', 0)
                expected = case['oracle_exact'][i][n]
                if (exact, posted, exact - posted) != (expected, _floor(expected), expected - _floor(expected)):
                    errors.append(_problem('ACCRUAL', f'{ref} {suffix}: exact={exact}, posted={posted}, expected={expected}'))
            position = overlay.repayment_position(state, ref, terms.ledger_denominator())
            expected_dues = [_floor(x) - p for x, p in zip(case['oracle_exact'][i], case['oracle_paid'][i])]
            if list(position[1:3]) != expected_dues[::-1] or position[3] != 0:
                errors.append(_problem('ACCRUAL', f'{ref} repayment dues differ from oracle'))
        if left['advances'].get(ref) != right['advances'].get(ref):
            errors.append(_problem('ACCRUAL', f'{ref} k-step and one-step differ'))
    if left['sim_day'] != right['sim_day'] or left['sim_day'] != case['sim_day']:
        errors.append(_problem('ACCRUAL', 'clock endpoints differ'))
    return errors


def _allocation_errors(split, principal, interest, default, cash, terms):
    dues = {'DEFAULT_INTEREST': default, 'INTEREST': interest, 'PRINCIPAL': principal}
    parts = {'DEFAULT_INTEREST': split['to_default_interest'], 'INTEREST': split['to_interest'],
             'PRINCIPAL': split['to_principal']}
    expected = _oracle_split(terms, principal, interest, default, cash)
    good = (sum(parts.values()) + split['unapplied_cash'] == cash
            and split['unapplied_cash'] >= 0 and parts == expected
            and all(0 <= parts[k] <= dues[k] for k in dues)
            and (split['unapplied_cash'] == 0 or parts == dues)
            and split['remaining'] == {'default_interest_due': default - parts['DEFAULT_INTEREST'],
                                       'interest_due': interest - parts['INTEREST'],
                                       'principal_outstanding': principal - parts['PRINCIPAL']})
    return [] if good else [_problem('ALLOCATION', f'cash={cash}, dues={dues}, split={split}')]


def check_allocation_conservation(case, terms):
    errors = []
    for subject in case['final_subjects']:
        if subject['terms'] is None:
            continue
        kwargs = dict(draw_day=subject['draw_day'], as_of_day=case['sim_day'],
                      expected_settlement_cash_day=case['settlement_day'], gate=subject['gate'])
        quote = terms.allocation(subject['case'], subject['claim'], cash=0, **kwargs)
        c, d = quote['interest']['interest_due_krw'], quote['interest']['default_interest_due_krw']
        p = subject['principal']
        due = p + c + d
        for cash in sorted({0, 1, max(0, due - 1), due, due + 1, due * 2, case['cash']}):
            errors += _allocation_errors(terms.allocate(p, interest_due=c, default_interest_due=d, cash=cash),
                                         p, c, d, cash, terms)
            split = terms.allocation(subject['case'], subject['claim'], cash=cash, **kwargs)['allocation']
            errors += _allocation_errors(split, p, c, d, cash, terms)
    return errors


def probe_terms(terms, cap_bps, one_time_fee_bps):
    probe = copy.copy(terms)
    probe.items = copy.deepcopy(terms.items)
    probe.version = f'{terms.version}:SYNTHETIC_PROBE'
    _value(probe, 'interest_rate')['all_in_cost_cap_bps_annual'] = cap_bps
    fees = _value(probe, 'fees')
    for key in ('origination_fee_bps', 'extension_fee_bps', 'prepayment_penalty_bps',
                'servicing_fee_bps_annual', 'commitment_fee_bps_annual_on_undrawn'):
        fees[key] = 0
    fees.update(origination_fee_bps=one_time_fee_bps, late_fee=0)
    return probe


def exact_cost(terms, subject, term_days):
    """Principal-scaled cost/cap KRW; explicit fee sets form an independent oracle."""
    interest, fees = _value(terms, 'interest_rate'), _value(terms, 'fees')
    tier = next(t for t in interest['tiers'] if t['condition']['settlement_gate'] == subject['gate'])
    annual = (tier['all_in_bps_annual'] + interest['default_interest_add_bps_annual']
              + fees['servicing_fee_bps_annual'] + fees['commitment_fee_bps_annual_on_undrawn'])
    once = sum(fees[k] for k in ('origination_fee_bps', 'extension_fee_bps', 'prepayment_penalty_bps'))
    once += fees['late_fee'] if type(fees['late_fee']) is int else 0
    days = int(interest['day_count'].split('_')[1])
    p = subject['principal']
    cost = Fraction(p * (annual * term_days + once * days), BPS_SCALE * days)
    cap = Fraction(p * interest['all_in_cost_cap_bps_annual'] * term_days, BPS_SCALE * days)
    return cost, cap, days


def check_rollup_cap_check(case, terms):
    policy = terms
    if case['probe'] >= 2:
        first = next((s for s in case['subjects'] if s['terms'] is not None), None)
        if first is None:
            return []
        tier = next(t for t in _value(terms, 'interest_rate')['tiers']
                    if t['condition']['settlement_gate'] == first['gate'])
        annual = tier['all_in_bps_annual'] + _value(terms, 'interest_rate')['default_interest_add_bps_annual']
        policy = probe_terms(terms, annual, 0 if case['probe'] == 2 else 1)
    errors, rows = [], []
    for subject in case['subjects']:
        body = policy.portfolio([subject], draw_day=subject['draw_day'], draw_day_source=LABEL,
                                as_of_day=case['sim_day'], expected_settlement_cash_day=case['settlement_day'])
        row = body['rows'][0]
        rows.append(row)
        if subject['terms'] is None:
            continue
        if row['status'] != 'BOUND':
            errors.append(_problem('CAP', 'matching subject is not BOUND'))
            continue
        cost, cap, days = exact_cost(policy, subject, row['term_days'])
        if row['cap_check'] != ('PASS' if cost <= cap else 'FAIL'):
            errors.append(_problem('CAP', f"cost_krw={cost}, cap_krw={cap}, actual={row['cap_check']}"))
        annualized = cost * BPS_SCALE * days / (subject['principal'] * row['term_days'])
        if Fraction(row['annualized_all_in_bps']) != annualized:
            errors.append(_problem('CAP_ANNUALIZED', f'expected={annualized}, actual={row["annualized_all_in_bps"]}'))
    # A common draw day is required by the portfolio API; also exercise the actual aggregate.
    body = policy.portfolio(case['subjects'], draw_day=0, draw_day_source=LABEL,
                            as_of_day=case['sim_day'], expected_settlement_cash_day=case['settlement_day'])
    expected = 'FAIL' if any(r.get('cap_check') == 'FAIL' for r in body['rows']) else 'PASS'
    if body['totals']['cap_check'] != expected:
        errors.append(_problem('CAP', 'portfolio total cap does not agree with rows'))
    return errors


def _risk(case, terms):
    subjects = case['final_subjects']
    margins = [{**s, 'margin': {'payees': ['organizer'], 'advance_rate_bps': BPS_SCALE}}
               for s in subjects]
    return risk.build(subjects, margins, terms=terms, sim_day=case['sim_day'],
                      projection_outstanding_krw=sum(s['principal'] for s in subjects))


def check_risk_bucket_sums(case, terms):
    body = _risk(case, terms)
    total = sum(s['principal'] for s in case['final_subjects'])
    groups = [body['by_tier'], body['maturity_buckets']['rows'], body['overdue_aging']['rows']]
    if (body['totals']['outstanding_krw'] != total or not body['reconciliation']['matched']
            or any(sum(r['outstanding_krw'] for r in group) != total for group in groups)):
        return [_problem('RISK_BUCKET', f'expected outstanding={total}, groups={groups}')]
    return []


def check_forecast_bucket_sums(case, terms):
    errors = []
    # Both branches on every seed, including an explicitly undated settlement leg.
    for day in (None, case['settlement_day'] if case['settlement_day'] is not None else case['sim_day']):
        body = forecast.build(case['final_subjects'], terms=terms, sim_day=case['sim_day'],
                              expected_settlement_cash_day=day)
        legs = [leg for row in body['advances'] if row['status'] == 'BOUND' for leg in row['legs']]
        scheduled = [leg for leg in legs if leg['bucket'] is not None]
        total = sum((Fraction(leg['exact']) for leg in scheduled), Fraction(0))
        bucket_total = Fraction(0)
        for bucket in body['buckets']['rows']:
            expected = sum((Fraction(leg['exact']) for leg in scheduled if leg['bucket'] == bucket['id']), Fraction(0))
            bucket_total += Fraction(bucket['expected_exact'])
            if Fraction(bucket['expected_exact']) != expected or bucket['expected_cash_krw'] != _floor(expected):
                errors.append(_problem('FORECAST_BUCKET', f'day={day}, bucket={bucket}, expected={expected}'))
        outstanding = sum(row['principal_krw'] for row in body['advances'] if row['status'] == 'BOUND')
        settlement = body['reconciliation']['settlement_exact']
        good = Fraction(settlement) == (0 if day is None else outstanding)
        if day is None:
            good = good and all(leg['bucket'] is None and leg['status'] == 'EXPECTED_DAY_NOT_PROVIDED'
                                for leg in legs if leg['kind'] == 'SETTLEMENT_CASH_IN')
        if total != bucket_total or not good or not body['reconciliation']['matched']:
            errors.append(_problem('FORECAST_BUCKET', f'day={day}, scheduled sum={total}, buckets={bucket_total}'))
    return errors


def check_stress_monotone(case, terms):
    stress = _risk(case, terms)['stress']
    # Four-times collateral guarantees a plateau at shocks 0 and 1 for a +1 won mutant.
    subjects = [{'eligible': s['claim']['obligations'][0]['outstanding'], 'rate': BPS_SCALE,
                 'outstanding': s['principal']} for s in case['final_subjects']]
    sweep = [risk._stress_row(shock, subjects) for shock in sorted({0, 1, BPS_SCALE, *risk.SHOCKS_BPS})]
    errors = []
    for rows in ([stress['baseline']] + stress['rows'], sweep):
        for a, b in zip(rows, rows[1:]):
            increasing = ('margin_call_count', 'called_outstanding_krw', 'shortfall_krw')
            if (any(a[k] > b[k] for k in increasing)
                    or a['shocked_eligible_face_krw'] < b['shocked_eligible_face_krw']):
                errors.append(_problem('STRESS', f'losses decrease: {a} -> {b}'))
    if not stress['monotone']:
        errors.append(_problem('STRESS', 'risk stress monotone flag is false'))
    return errors


def check(name, case, terms):
    try:
        return globals()[f'check_{name}'](case, terms)
    except ValueError as exc:
        return [_problem(f'FOLD_REJECTED:{type(exc).__name__}', str(exc))]


def _candidates(spec):
    for key in ('subjects', 'segments', 'repayments'):
        if len(spec[key]) > (0 if key == 'repayments' else 1):
            for index in range(len(spec[key]) - 1, -1, -1):
                candidate = copy.deepcopy(spec)
                candidate[key].pop(index)
                # Reindex surviving references; deleted targets are dropped.
                if key in ('subjects', 'segments'):
                    ref = 'subject_idx' if key == 'subjects' else 'segment_idx'
                    candidate['repayments'] = [r for r in candidate['repayments'] if r[ref] != index]
                    for r in candidate['repayments']:
                        r[ref] -= r[ref] > index
                    a = candidate['acceleration']
                    if a is not None:
                        if a[ref] == index:
                            candidate['acceleration'] = None
                        else:
                            a[ref] -= a[ref] > index
                yield candidate
    if spec['acceleration'] is not None:
        candidate = copy.deepcopy(spec)
        candidate['acceleration'] = None
        yield candidate
    for key, fields in (('segments', ('k', 'len_days')), ('subjects', ('face', 'draw_day'))):
        for i, item in enumerate(spec[key]):
            for field in fields:
                minimum = 0 if field == 'draw_day' else 1
                if item[field] > minimum:
                    candidate = copy.deepcopy(spec)
                    candidate[key][i][field] = max(minimum, item[field] // 2)
                    yield candidate


def shrink(spec, name, terms, codes, budget=200):
    current, attempts = copy.deepcopy(spec), 0
    while True:
        accepted = False
        for candidate in _candidates(current):
            if attempts >= budget:
                return {'spec': current, 'case': materialize(current, terms), 'attempts': attempts,
                        'exhausted': True, 'locally_minimal': False}
            attempts += 1
            try:
                case = materialize(candidate, terms)
            except (ValueError, IndexError, ZeroDivisionError):
                continue
            if not valid(case) and codes.intersection(v['code'] for v in check(name, case, terms)):
                current, accepted = candidate, True
                break
        if not accepted:
            return {'spec': current, 'case': materialize(current, terms), 'attempts': attempts,
                    'exhausted': False, 'locally_minimal': True}


def violation_message(name, violation):
    shrunk = violation['shrink']
    limit = '; not proven minimal' if shrunk['exhausted'] else ''
    return (f"{name} seed={violation['seed']} code={violation['code']}: {violation['detail']}; "
            f"minimal inputs={json.dumps(violation['inputs'], sort_keys=True, separators=(',', ':'))} "
            f"(attempts={shrunk['attempts']}, locally_minimal={shrunk['locally_minimal']}, "
            f"exhausted={shrunk['exhausted']}){limit}")


def run_property(name, cases=DEFAULT_CASES, terms=None):
    if name not in PROPERTIES or type(cases) is not int or cases < 1:
        raise ValueError('unknown property or invalid case count')
    terms = DecisionNoteTermsPolicy() if terms is None else terms
    if terms.top == 'NOT_BOUND' or not risk.usable(terms) or not forecast.usable(terms):
        raise ValueError('terms not bound')
    violations = []
    for seed in range(SEED_BASE, SEED_BASE + cases):
        spec = generate(name, seed, terms)
        case = materialize(spec, terms)
        problems = valid(case)
        found = [_problem('INVALID_GENERATOR', str(problems))] if problems else check(name, case, terms)
        if found:
            codes = {v['code'] for v in found}
            result = shrink(spec, name, terms, codes)
            minimal = check(name, result['case'], terms) if not problems else found
            for item in minimal:
                if item['code'] in codes:
                    violations.append({'seed': seed, **item, 'inputs': result['spec'],
                                       'shrink': {k: result[k] for k in ('attempts', 'exhausted', 'locally_minimal')}})
    return {'property': name, 'label': LABEL, 'cases_run': cases,
            'seeds': [SEED_BASE, SEED_BASE + cases - 1], 'violations': violations}


def run_all(cases=DEFAULT_CASES, terms=None):
    terms = DecisionNoteTermsPolicy() if terms is None else terms
    reports = [run_property(name, cases, terms) for name in PROPERTIES]
    return {'format': FORMAT, 'label': LABEL, 'cases_per_property': cases, 'properties': reports,
            'violations': sum(len(r['violations']) for r in reports)}
