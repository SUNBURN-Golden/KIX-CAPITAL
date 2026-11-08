"""Deterministic, read-only statement provenance over one audited byte capture.

Hashes establish local consistency, not authenticity. Fixtures are generated
locally; no settlement receipt, sales observation or actual payment is bound.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from capital import audit, evidence, store
from capital.producer import DEMO_BOOK_PROFILE
from capital.protocol import CreditMachine
from capital.service import MAX_OPERATIONS, digest
from capital.statement import APPROVED_PHASES
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_STATEMENT_TRACE_V1'
PROVENANCE_FORMAT = 'KIX_CAPITAL_STATEMENT_PROVENANCE_V1'
WORKSPACE_LABEL = 'statement-trace-captured-workspace'


class TraceError(ValueError):
    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def _escape(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def _path(*parts):
    return ''.join('/' + _escape(part) for part in parts)


def _ref(root, *parts):
    return {'root': root, 'pointer': _path(*parts)}


def _resolve(roots, ref):
    value = roots[ref['root']]
    for token in ref['pointer'].split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if type(value) is list else value[token]
    return value


def _numeric(value, pointer=''):
    if type(value) in (int, float):
        yield pointer, value
    elif type(value) is dict:
        for key, item in value.items():
            yield from _numeric(item, pointer + '/' + _escape(key))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from _numeric(item, pointer + '/' + str(index))


def _labels(fixtures, fixture_id):
    profile = fixtures.profile(fixture_id)
    return {
        'source_classification': 'READ_ONLY_FIXTURE',
        'label': 'SYNTHETIC_FIXTURE_PROFILE' if profile == DEMO_BOOK_PROFILE else 'SIMULATED',
        'profile_version': profile, 'policy_adopted': False, 'funds_executed': False,
        'units': 'SYNTHETIC_KRW_INTEGER', 'roles': 'SYNTHETIC_ROLES',
    }


def _receipt_checks(payload, fixtures):
    """Compare present pinned fields with their immediate historical result.

    Missing details are optional evidence, never supplied from replay. Unknown
    extension fields are retained verbatim but cannot support a witness.
    """
    machine = CreditMachine(fixtures)
    checks, results = [], []
    linked = set()
    for index, entry in enumerate(payload['journal']):
        key = entry['idempotency_key']
        linked.add(key)
        expected = copy.deepcopy(getattr(machine, entry['op'])(
            entry['advance_id'], idempotency_key=key, **copy.deepcopy(entry['body'])))
        results.append(expected)
        receipt = payload['receipts'][key]['receipt']
        base = _path(key, 'receipt')
        check = {
            'operation_id': key, 'journal_index': index, 'prefix_length': index + 1,
            'status': 'MATCHED', 'linkage': 'MATCHED',
            'checked': [], 'unavailable': [], 'unvalidated': [],
        }

        def mismatch(pointer):
            raise TraceError('RECEIPT_RESULT_MISMATCH', {
                'operation_id': key, 'journal_index': index, 'pointer': pointer})

        def compare(actual, replayed, pointer, expected_pointer):
            if type(actual) is not type(replayed):
                mismatch(pointer)
            if type(replayed) is dict:
                for name, value in replayed.items():
                    child = pointer + '/' + _escape(name)
                    replay_child = expected_pointer + '/' + _escape(name)
                    if name in actual:
                        compare(actual[name], value, child, replay_child)
                    else:
                        check['unavailable'].append({'root': 'receipts', 'pointer': child,
                                                     'status': 'NOT_BOUND', 'reason': 'OPTIONAL_DETAIL_ABSENT'})
                for name in sorted(set(actual) - set(replayed)):
                    check['unvalidated'].append({'root': 'receipts',
                                                'pointer': pointer + '/' + _escape(name)})
            elif type(replayed) is list:
                if len(actual) != len(replayed):
                    mismatch(pointer)
                for n, (left, right) in enumerate(zip(actual, replayed)):
                    compare(left, right, pointer + '/' + str(n), expected_pointer + '/' + str(n))
            else:
                if actual != replayed:
                    mismatch(pointer)
                check['checked'].append({
                    'receipt': {'root': 'receipts', 'pointer': pointer},
                    'expected': {'root': 'historical_replay', 'pointer': expected_pointer}})

        if receipt.get('operation_id') != key or receipt.get('outcome') != 'ACCEPTED':
            mismatch(base)
        if 'result' in receipt:
            compare(receipt['result'], expected, base + '/result', _path(index))
        else:
            check['unavailable'].append({'root': 'receipts', 'pointer': base + '/result',
                                         'status': 'NOT_BOUND', 'reason': 'OPTIONAL_DETAIL_ABSENT'})
        for name in sorted(set(receipt) - {'result', 'operation_id', 'outcome'}):
            check['unvalidated'].append({'root': 'receipts', 'pointer': base + '/' + _escape(name)})
        checks.append(check)
    if (machine.export_journal() != payload['journal']
            or machine.state_digest() != payload['state_digest']):
        raise TraceError('HISTORICAL_REPLAY_MISMATCH')
    for key in sorted(set(payload['receipts']) - linked):
        checks.append({'operation_id': key, 'journal_index': None, 'prefix_length': None,
                       'status': 'NOT_BOUND', 'reason': 'NO_JOURNAL_ENTRY',
                       'case_association': 'NOT_BOUND', 'contributes_amounts': False,
                       'checked': [], 'unavailable': [],
                       'unvalidated': [_ref('receipts', key, 'receipt')]})
    return checks, results


def _provenance(raw, document, service, statement):
    payload = document['payload']
    fixtures = service.fixtures
    checks, historical = _receipt_checks(payload, fixtures)
    cases = {key: {'view': copy.deepcopy(service.machine.view(key)),
                   'fixture_id': fixture, 'classification': 'F04_CASE_EVIDENCE',
                   **_labels(fixtures, fixture)}
             for key, fixture in sorted(payload['case_fixtures'].items())}
    fixture_rows = {key: {'view': fixtures.view(key), 'beneficiary_role': fixtures.beneficiary(key),
                          **_labels(fixtures, key)} for key in sorted(fixtures.rows)}
    roots = {
        'cases': cases, 'fixtures': fixture_rows,
        'case_fixtures': copy.deepcopy(payload['case_fixtures']),
        'journal': copy.deepcopy(payload['journal']),
        'receipts': copy.deepcopy(payload['receipts']), 'historical_replay': historical,
        'configuration': {'MAX_OPERATIONS': MAX_OPERATIONS,
                          'source': 'capital.service.MAX_OPERATIONS',
                          'meaning': 'local operation capacity; not a financial limit'},
    }
    journal = roots['journal']
    by_case = {key: [i for i, row in enumerate(journal) if row['advance_id'] == key] for key in cases}
    offers = {row['advance_id']: i for i, row in enumerate(journal) if row['op'] == 'offer'}
    fields, witnesses = {}, {}
    checked_refs = {row['journal_index']: [item['receipt'] for item in row['checked']]
                    for row in checks if row['journal_index'] is not None}

    def term(ref, sign=1, *, case=None, fixture=None, journal_index=None):
        fixture = fixture if fixture is not None else payload['case_fixtures'].get(case)
        result = {'source': ref, 'sign': sign}
        if fixture is not None:
            result.update(_labels(fixtures, fixture))
        if case is not None:
            result['advance_id'] = case
        if journal_index is not None:
            result['journal_index'] = journal_index
        return result

    def offer_term(case, sign=1, index=None):
        return term(_ref('journal', offers[case], 'body', 'amount'), sign,
                    case=case, journal_index=index if index is not None else offers[case])

    def operations(case, kind):
        selected = [i for i in by_case[case] if journal[i]['op'] == kind]
        if kind in ('draw', 'close'):
            return [offer_term(case, -1 if kind == 'close' else 1, i) for i in selected]
        return [term(_ref('journal', i, 'body', 'amount'), case=case, journal_index=i) for i in selected]

    def bind(pointer, terms, sources=(), indexes=(), rule='SUM_SIGNED_TERMS'):
        statement_ref = {'root': 'statement', 'pointer': pointer}
        target = _resolve({'statement': statement}, statement_ref)
        computed = 0
        for item in terms:
            value = _resolve(roots, item['source'])
            if type(value) is not int or item['sign'] not in (-1, 1):
                raise TraceError('INVALID_WITNESS', {'pointer': pointer})
            computed += item['sign'] * value
        if type(target) is not int or computed != target:
            raise TraceError('CONTRIBUTION_MISMATCH', {'pointer': pointer})
        witness_id = 'w' + str(len(witnesses))
        witnesses[witness_id] = {'target': statement_ref, 'rule': rule, 'terms': terms,
                                 'computed': computed, 'statement_value': target, 'status': 'MATCHED'}
        indexes = sorted(set(indexes) | {item['journal_index'] for item in terms if 'journal_index' in item})
        receipt_names = {'amount' if pointer.endswith('/total') else pointer.rsplit('/', 1)[-1],
                         'applied', 'phase', 'advance_id', 'claim_id'}
        receipt_names.update({'drawn': 'drawn_exposure', 'repaid': 'repaid_exposure',
                              'outstanding': 'outstanding_exposure'}.get(name, name)
                             for name in tuple(receipt_names))
        fields[pointer] = {
            'sources': list(sources), 'witnesses': [witness_id],
            'journal': [_ref('journal', i) for i in indexes],
            'receipts': [_ref('receipts', journal[i]['idempotency_key'], 'receipt') for i in indexes],
            'validated_receipt_fields': [ref for i in indexes for ref in checked_refs[i]
                                         if ref['pointer'].rsplit('/', 1)[-1] in receipt_names],
            'receipt_evidence': 'HISTORICAL_PRESENT_FIELDS_ONLY' if indexes else 'NOT_BOUND',
        }
        return terms

    for pointer in ('/operation_capacity', '/scope/operation_capacity', '/scope/capacity_bound'):
        ref = _ref('configuration', 'MAX_OPERATIONS')
        bind(pointer, [term(ref)], [ref], rule='CONFIGURATION')

    for category_index, category in enumerate(statement['categories']):
        category_id = category['id']
        prefix = _path('categories', category_index)
        totals, total_sources, total_indexes = {}, {}, {}
        seen_claims = {}
        for row_index, row in enumerate(category['rows']):
            path = prefix + _path('rows', row_index)
            case = row.get('advance_id')
            fixture = row.get('claim_id') if case is None else payload['case_fixtures'][case]
            indexes = by_case[case] if case else []
            if category_id == 'reserved':
                siblings = [key for key in cases if payload['case_fixtures'][key] == fixture]
                values = {cases[key]['view']['reserved_open'] for key in siblings}
                if len(values) != 1:
                    raise TraceError('INCONSISTENT_CLAIM_RESERVATION', {'claim_id': fixture})
                indexes = [i for key in siblings for i in by_case[key]]
            for name, value in row.items():
                if type(value) is not int:
                    continue
                source_name = {'drawn': 'drawn_exposure', 'repaid': 'repaid_exposure',
                               'outstanding': 'outstanding_exposure'}.get(name, name)
                source = _ref('cases', case, 'view', source_name) if case else _ref('fixtures', fixture, 'view', 'claim', name)
                if category_id == 'approved':
                    terms = [{**offer_term(case), 'eligibility': _ref('cases', case, 'view', 'phase'),
                              'allowed_phases': sorted(APPROVED_PHASES)}]
                elif category_id == 'exposure' and name != 'confirmed_cash_on_face':
                    drawn, repaid = operations(case, 'draw'), operations(case, 'repay')
                    terms = drawn if name == 'drawn' else repaid if name == 'repaid' else drawn + [{**item, 'sign': -1} for item in repaid]
                elif category_id == 'reserved':
                    terms = []
                    for i in sorted(indexes):
                        entry = journal[i]
                        if entry['op'] in ('draw', 'close'):
                            terms.append(offer_term(entry['advance_id'], -1 if entry['op'] == 'close' else 1, i))
                elif case:
                    terms = [term(_ref('fixtures', fixture, 'view', 'claim', 'confirmed_cash'), case=case)]
                else:
                    terms = [term(source, fixture=fixture)]
                bind(path + '/' + name, terms, [source], indexes)
                total_name = {'amount': 'total', 'reserved_open': 'total', 'confirmed_cash': 'confirmed',
                              'distributed_cash': 'distributed'}.get(name, name)
                if category_id == 'exposure' and name == 'confirmed_cash_on_face':
                    continue
                if category_id == 'reserved':
                    if fixture in seen_claims:
                        continue
                    seen_claims[fixture] = True
                totals.setdefault(total_name, []).extend(terms)
                total_sources.setdefault(total_name, []).append(source)
                total_indexes.setdefault(total_name, []).extend(indexes)
        for name, value in category.items():
            if type(value) is int:
                bind(prefix + '/' + name, totals.get(name, []), total_sources.get(name, []),
                     total_indexes.get(name, []),
                     rule='SUM_UNIQUE_CLAIMS' if category_id == 'reserved' else 'SUM_ROWS')
    numeric = dict(_numeric(statement))
    if set(fields) != set(numeric):
        raise TraceError('NUMERIC_FIELD_COVERAGE')
    fixture_inputs = {'rows': copy.deepcopy(fixtures.rows), 'profiles': copy.deepcopy(fixtures.profiles),
                      'beneficiaries': copy.deepcopy(fixtures.beneficiaries),
                      'projection_ids': sorted(fixtures.projection_ids)}
    return {
        'format': PROVENANCE_FORMAT, 'label': 'SIMULATED',
        'hashes': {'workspace_sha256': hashlib.sha256(raw).hexdigest(),
                   'payload_sha256': document['payload_sha256'], 'state_digest': payload['state_digest'],
                   'fixture_inputs_sha256': digest(fixture_inputs), 'statement_sha256': digest(statement)},
        'fixture_inputs': fixture_inputs, 'roots': roots, 'fields': fields, 'witnesses': witnesses,
        'receipt_checks': checks,
        'not_bound': copy.deepcopy(statement['not_bound']) + [
            {'id': name, 'status': 'NOT_BOUND'} for name in (
                'authenticated_historical_fixtures', 'workspace_authenticity', 'external_receipts',
                'bank_pg_provider_observations', 'source_cut', 'completeness', 'capital_revenue')],
        'funds_executed': False, 'workspace_mutated': False,
    }


def trace_workspace_bytes(raw: bytes | None) -> dict:
    """Audit, restore and trace only these bytes; never read a workspace path."""
    audited = audit.audit_workspace_bytes(raw, workspace=WORKSPACE_LABEL)
    report = {'format': FORMAT, 'label': 'SIMULATED', 'ok': False, 'reason': audited['reason'],
              'failed_check': audited['failed_check'], 'audit': audited,
              'statement': None, 'provenance': None, 'funds_executed': False, 'workspace_mutated': False}
    if not audited['ok']:
        return report
    service = None
    try:
        document = loads(raw)
        service = evidence.offline_service(document)
        if service.workspace_status != 'ACTIVE':
            raise TraceError('RESTORE_NOT_ACTIVE')
        with service.lock:
            statement = copy.deepcopy(service.statement())
            provenance = _provenance(raw, document, service, statement)
        report.update(ok=True, reason=None, failed_check=None, statement=statement, provenance=provenance)
    except TraceError as exc:
        report.update(reason=exc.reason, failed_check='statement_trace', detail=exc.detail)
    except (ValueError, KeyError, TypeError, ArithmeticError, RecursionError):
        report.update(reason='TRACE_INPUT_INCONSISTENT', failed_check='statement_trace')
    finally:
        if service is not None:
            close = getattr(service.producer, 'close', None)
            if callable(close):
                close()
            service.storage.close()
    return report


def trace_workspace(directory) -> dict:
    """Capture workspace.json exactly once. No locks, writes or keyset reads."""
    try:
        raw = (Path(directory) / store.FILE_NAME).read_bytes()
    except (OSError, TypeError, ValueError):
        raw = None
    return trace_workspace_bytes(raw)


def dump(report: dict) -> bytes:
    return store.canonical_bytes(report) + b'\n'
