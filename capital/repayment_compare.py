"""SIMULATED counterfactual repayment schedules over one audited capture.

Only advance_day and post_repayment run, on disposable memory ports. This is
neither an optimizer nor a funding forecast. No external cash is inferred.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import re
import sys

from capital import audit, overlay, recovery, residuals, store
from capital.producer import PinnedFsmProducer
from capital.resources import note_path, resource_source
from capital.service import ApiError, CapitalService
from capital.terms import DecisionNoteTermsPolicy
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_REPAYMENT_COMPARISON_V1'
SPEC_FORMAT = 'KIX_CAPITAL_REPAYMENT_SCHEDULES_V1'
SCHEDULE_ID = re.compile(r'[A-Za-z0-9-]{1,32}\Z')
ADVANCE_ID = re.compile(r'sim-[A-Za-z0-9-]{1,60}\Z')
OP_ID = re.compile(r'[A-Za-z0-9-]{1,80}\Z')
REQUIRED_TERMS = ('interest_rate', 'term', 'default_loss_treatment')
METRICS = ('principal_outstanding_krw', 'interest_paid_krw', 'default_interest_paid_krw',
           'interest_due_krw', 'default_interest_due_krw', 'unapplied_cash_krw')
EXACT_FIELDS = ('cumulative_exact_contract', 'cumulative_exact_default',
                'carried_remainder_contract', 'carried_remainder_default')
# Explicit allowlist: no instance identities, saved envelopes, telemetry or stamps.
OUTCOME_FIELDS = ('outcome', 'transport_duplicate', 'sim_day', 'from_sim_day', 'to_sim_day',
                  'at_sim_day', 'advance_ref', 'amount_krw', 'allocation', 'f04',
                  'unapplied_before_krw', 'unapplied_after_krw', 'close_gate',
                  'terms_bound_by_this_command', 'postings', 'f04_journal_written')


def _digest(value):
    return hashlib.sha256(store.canonical_bytes(value)).hexdigest()


class ComparisonError(ValueError):
    def __init__(self, code, entries=()):
        self.code, self.entries = code, list(entries)
        super().__init__(code)


class CapturedMemoryStorage(store.StoragePort):
    """Writable, detached StoragePort; saves replace an envelope only in RAM.

    The audited source is copied at construction. load verifies and copies;
    save uses the normal envelope constructor. No file/lock/signing port exists.
    Volatile envelope timestamps are never included in comparison reports.
    """
    def __init__(self, document):
        self.document = copy.deepcopy(store.verify_document(document))

    def load(self):
        return store.verify_document(copy.deepcopy(self.document))

    def save(self, payload, overlay=None):
        self.document = store.envelope(self.writer_instance, payload, overlay)

    def close(self):
        pass


class _CapturedNote:
    """Feed policy loaders exactly the bytes used for provenance."""
    def __init__(self, path):
        self.path = path
        try:
            self.raw = path.read_bytes()
        except (OSError, ValueError):
            self.raw = None

    def read_bytes(self):
        if self.raw is None:
            raise OSError('note unavailable')
        return self.raw

    def provenance(self):
        return {'notes_source': 'NONE' if self.raw is None else resource_source(self.path),
                'note_sha256': None if self.raw is None else hashlib.sha256(self.raw).hexdigest()}


def _load_policy():
    names = ('CAPITAL_FINANCIAL_TERMS.md', overlay.STATE_NOTE, overlay.EXPORT_NOTE, overlay.REPAYMENT_NOTE)
    notes = {name: _CapturedNote(note_path(name)) for name in names}
    terms = DecisionNoteTermsPolicy(notes[names[0]])
    terms.note.update(notes[names[0]].provenance())
    bounds = overlay.load_bounds(notes[overlay.STATE_NOTE], notes[overlay.EXPORT_NOTE])
    repayments = overlay.load_repayment_bounds(notes[overlay.REPAYMENT_NOTE])
    info = {'provenance': {name: notes[name].provenance() for name in names},
            'status': terms.status(), 'validated_items': copy.deepcopy(terms.items),
            'overlay_bounds': bounds, 'repayment_bounds': repayments}
    info['policy_sha256'] = _digest(info)
    return terms, bounds, repayments, info


def _keys(value, keys, reason):
    if type(value) is not dict or set(value) != set(keys):
        raise ComparisonError(reason)


def _integer(value, low, high, reason):
    if type(value) is not int or not low <= value <= high:
        raise ComparisonError(reason)


def _validate_spec(spec, day, bounds, repayments):
    _keys(spec, ('format', 'advance_id', 'horizon_sim_day', 'schedules'), 'INVALID_SPECIFICATION_FIELDS')
    if spec['format'] != SPEC_FORMAT:
        raise ComparisonError('INVALID_SPECIFICATION_FORMAT')
    if type(spec['advance_id']) is not str or not ADVANCE_ID.fullmatch(spec['advance_id']):
        raise ComparisonError('INVALID_ADVANCE_ID')
    _integer(spec['horizon_sim_day'], day, bounds['SIM_DAY_MAX'], 'INVALID_HORIZON_SIM_DAY')
    if type(spec['schedules']) is not list or len(spec['schedules']) != 2:
        raise ComparisonError('EXACTLY_TWO_SCHEDULES_REQUIRED')
    seen = set()
    for schedule in spec['schedules']:
        _keys(schedule, ('id', 'payments'), 'INVALID_SCHEDULE_FIELDS')
        ident = schedule['id']
        if type(ident) is not str or not SCHEDULE_ID.fullmatch(ident) or ident in seen:
            raise ComparisonError('INVALID_OR_DUPLICATE_SCHEDULE_ID')
        seen.add(ident)
        payments = schedule['payments']
        if type(payments) is not list or len(payments) > 32:
            raise ComparisonError('SCHEDULE_PAYMENT_LIMIT')
        previous = day
        for payment in payments:
            _keys(payment, ('at_sim_day', 'amount_krw'), 'INVALID_PAYMENT_FIELDS')
            _integer(payment['at_sim_day'], previous, spec['horizon_sim_day'], 'INVALID_PAYMENT_SIM_DAY')
            _integer(payment['amount_krw'], 0, repayments['amount_max_krw'], 'INVALID_PAYMENT_AMOUNT')
            previous = payment['at_sim_day']


def _check(report, ident, side, ok, reason=None, entries=()):
    report['comparability']['checks'].append({
        'id': ident, 'side': side,
        'status': 'NOT_CHECKED' if ok is None else 'MATCHED' if ok else 'MISMATCH',
        'reason': reason if ok is not True else None, 'entries': list(entries)})


def _service(document, terms, bounds, repayments, branch, producer=None):
    service = CapitalService(CapturedMemoryStorage(document), terms=copy.deepcopy(terms),
                             overlay_bounds=copy.deepcopy(bounds), repayment_bounds=copy.deepcopy(repayments),
                             producer=producer)
    service.instance_id = 'repayment-compare-' + branch
    service.storage.writer_instance = service.instance_id
    return service


def _close(service):
    service.observability.close()
    close = getattr(service.producer, 'close', None)
    if callable(close):
        close()
    service.storage.close()


def _preflight(service, spec, state):
    if service.workspace_status != 'ACTIVE':
        raise ComparisonError('RESTORE_NOT_ACTIVE')
    ref = spec['advance_id']
    if ref not in service.case_fixtures:
        raise ComparisonError('UNKNOWN_ADVANCE', [ref])
    case = service.machine.view(ref)
    if case['phase'] != 'DRAWN' or recovery.anchor(state, ref) is not None:
        raise ComparisonError('UNSUPPORTED_ADVANCE_STATE', [ref, case['phase']])
    bad = []
    for row in service.machine.export_journal():
        if row['op'] != 'draw':
            continue
        receipt = service.receipts.get(row['idempotency_key'], {}).get('receipt', {})
        result = receipt.get('result')
        credit = result.get('credit') if type(result) is dict else None
        gate = credit.get('settlement_gate') if type(credit) is dict else None
        if receipt.get('outcome') != 'ACCEPTED' or type(gate) is not str or not gate:
            bad.append(row['advance_id'])
    if bad:
        raise ComparisonError('DRAW_RECEIPT_GATE_MISSING', sorted(set(bad)))
    binding = state['terms_binding']
    if binding is not None and (binding['terms_version'] != service.terms.version
                               or binding['status'] not in ('BOUND', 'PARTIAL')):
        raise ComparisonError('TERMS_BINDING_INCOMPATIBLE')
    if binding is None and any(s['payments'] and s['payments'][0]['at_sim_day'] == state['sim_day']
                               for s in spec['schedules']):
        raise ComparisonError('REPAYMENT_TERMS_NOT_BOUND')
    subject = next((s for s in service._overlay_subjects(service.overlay_entries) if s['advance_id'] == ref), None)
    ledger = None if subject is None else service._ledger_terms(subject)
    if ledger is None:
        raise ComparisonError('TARGET_LEDGER_TERMS_NOT_BOUND', [ref])
    return {**copy.deepcopy(ledger), 'advance_id': ref, 'draw_gate': subject['gate'],
            'draw_day': subject['draw_day'], 'original_maturity_day': ledger['maturity_day'],
            'effective_maturity_day': recovery.effective_maturity(state, ref, ledger['maturity_day']),
            'captured_binding': copy.deepcopy(binding),
            'allocation_order': copy.deepcopy(service.terms._value('interest_rate')['repayment_allocation_order'])}


def _plan(spec, schedule, day, step, branch):
    operations = []
    def append(body):
        op = f'rc-b{branch}-c{len(operations):04d}'
        if not OP_ID.fullmatch(op):
            raise ComparisonError('GENERATED_ID_INVALID')
        operations.append({'operation_id': op, **body})
    def advance(target):
        nonlocal day
        while day < target:
            end = min(day + step, target)
            append({'op': 'advance_day', 'from_sim_day': day, 'to_sim_day': end,
                    'reason': 'SIMULATED_REPAYMENT_COMPARISON'})
            day = end
    for payment in schedule['payments']:
        advance(payment['at_sim_day'])
        append({'op': 'post_repayment', 'advance_ref': spec['advance_id'], **payment})
    advance(spec['horizon_sim_day'])
    return operations


def _reserve_ids(plans, service):
    journal = service.machine.export_journal()
    drawn = sorted({r['advance_id'] for r in journal if r['op'] == 'draw'})
    occupied = ({e['overlay_id'] for e in service.overlay_entries} | set(service.receipts)
                | {r['idempotency_key'] for r in journal})
    generated, collisions = set(), set()
    for plan in plans:
        for command in plan:
            op = command['operation_id']
            # Reserve even conditional outputs, so no simulated command can
            # alias a restored identity or any other planned derived identity.
            ids = [op, op + ':terms', *(op + ':interest:' + ref for ref in drawn),
                   'rp-' + hashlib.sha256(('KIX_CAPITAL_REPAY_F04_V1|' + op).encode()).hexdigest()[:32]]
            for ident in ids:
                if ident in occupied or ident in generated:
                    collisions.add(ident)
                generated.add(ident)
    if collisions:
        raise ComparisonError('GENERATED_ID_COLLISION', sorted(collisions))


def _final(service, ref):
    """Read existing servicing values; absent monetary evidence stays unknown."""
    view = service.overlay_state()
    row = next(r for r in view['advances'] if r['advance_id'] == ref)
    state = overlay.fold(service.overlay_entries)
    recorded = state['advances'].get(ref)
    paid = state.get('repayment', {}).get('advances', {}).get(ref)
    interest_bound = state['terms_binding'] is not None and recorded is not None
    cash_bound = state['terms_binding'] is not None and (recorded is not None or paid is not None)
    bound = interest_bound and cash_bound
    values = {k: row[k] if (k == 'principal_outstanding_krw' or
                           (cash_bound if k == 'unapplied_cash_krw' else interest_bound)) else None
              for k in METRICS}
    values.update({k: row.get(k) for k in EXACT_FIELDS})
    journal = copy.deepcopy(service.machine.export_journal())
    sections = residuals.compose_sections(service, state, journal, copy.deepcopy(service.overlay_entries),
                                          advance_ids={ref})
    complete = all(not s['coverage']['not_bound'] and s['reconciliation']['matched'] is True
                   for s in sections.values())
    advisory = ({'status': 'NOT_APPLICABLE', 'reason': 'EMPTY_OVERLAY', 'close_gate': None,
                 'close_ready': None} if 'close_gate' not in row else
                {'status': 'BOUND' if bound else 'NOT_BOUND', 'reason': None if bound else 'MONETARY_EVIDENCE_NOT_BOUND',
                 'close_gate': row['close_gate'] if bound else None,
                 'close_ready': row['close_ready'] if bound else None})
    return {'reached_sim_day': state['sim_day'], 'phase': row['phase'],
            'state_digest': service.machine.state_digest(), 'f04_journal_sha256': _digest(journal),
            'overlay_state_digest': view['overlay_state_digest'],
            'overlay_journal_sha256': _digest(service.overlay_entries),
            'evidence_status': 'BOUND' if bound else 'NOT_BOUND', 'values': values,
            'close_advisory': advisory, 'residuals': {
                'scope': {'advance_ids': [ref], 'claim_slices': 'OUTSIDE_SCOPE'},
                'status': 'COMPLETE' if complete else 'INCOMPLETE', 'sections': sections}}


def _execute(service, plan, schedule, spec, report):
    side = schedule['id']
    branch = {'id': side, 'steps': [], 'final': None}
    stopped = False
    for command in plan:
        step = {'command': copy.deepcopy(command), 'status': 'NOT_ATTEMPTED', 'result': None}
        branch['steps'].append(step)
        if stopped:
            continue
        try:
            receipt = service.overlay_command({'instance_id': service.instance_id, **command}, role='organizer')
            step['result'] = {k: copy.deepcopy(receipt[k]) for k in OUTCOME_FIELDS if k in receipt}
            ok = receipt.get('outcome') == 'APPLIED' and receipt.get('transport_duplicate') is False
            step['status'] = 'APPLIED' if ok else 'REJECTED'
            stopped = not ok
        except ApiError as exc:
            step.update(status='REJECTED', result={'code': exc.code, 'http_status': exc.status,
                                                 'detail': copy.deepcopy(exc.detail)})
            stopped = True
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            step.update(status='REJECTED', result={'code': 'COMMAND_FAILED', 'exception': type(exc).__name__})
            stopped = True
    _check(report, 'commands', side, not stopped, 'SCHEDULE_STEP_REJECTED')
    try:
        branch['final'] = _final(service, spec['advance_id'])
        final = branch['final']
        _check(report, 'horizon', side, final['reached_sim_day'] == spec['horizon_sim_day'], 'HORIZON_NOT_REACHED')
        _check(report, 'final_evidence', side, final['evidence_status'] == 'BOUND', 'MONETARY_EVIDENCE_NOT_BOUND')
        _check(report, 'residuals', side, final['residuals']['status'] == 'COMPLETE', 'RESIDUALS_INCOMPLETE')
    except (ApiError, ValueError, KeyError, TypeError, ArithmeticError, StopIteration) as exc:
        _check(report, 'final_reader', side, False, 'FINAL_READER_FAILED', [type(exc).__name__])
    return branch


def _new_report():
    return {'format': FORMAT, 'label': 'SIMULATED', 'mode': 'SIMULATED_REPAYMENT_COMPARISON',
              'status': 'NON_COMPARABLE', 'applied': False, 'workspace_mutated': False,
              'funds_executed': False, 'source': {}, 'policy': None, 'target': None,
              'specification': None, 'specification_sha256': None, 'branches': [],
              'comparability': {'checks': []}, 'comparison': None,
              'authentication': 'NOT_BOUND', 'actual_payments': 'NOT_BOUND',
              'historical_policy_provenance': 'NOT_BOUND',
              'interpretation': 'Counterfactual schedules only; no optimization, funding forecast, external cash assumptions or lifecycle decisions.'}


def compare_workspace(directory, specification):
    """Audit a single capture and simulate two explicitly dated schedules.

    Determinism includes captured bytes, specification, directory spelling, and
    local policy/fixture/audit inputs. No authenticated historical policy claim.
    Validation failures are reports; the caller's specification is never edited.
    """
    report = _new_report()
    service = None
    try:
        try:
            raw = (Path(directory) / store.FILE_NAME).read_bytes()
        except (OSError, TypeError, ValueError):
            raw = None
        audited = audit.audit_workspace_bytes(raw, workspace=str(directory))
        report['source'] = {'workspace_sha256': None if raw is None else hashlib.sha256(raw).hexdigest(),
                            'payload_sha256': audited['payload_sha256'], 'audit': audited}
        _check(report, 'audit', 'source', audited['ok'], 'WORKSPACE_AUDIT_FAILED')
        if not audited['ok']:
            return report
        document = loads(raw)
        terms, bounds, repayments, report['policy'] = _load_policy()
        if (terms.top not in ('BOUND', 'PARTIAL') or not terms._ready(*REQUIRED_TERMS)
                or bounds is None or repayments is None):
            raise ComparisonError('POLICY_INPUTS_UNUSABLE', [n for n in REQUIRED_TERMS if not terms._ready(n)])
        _check(report, 'policy', 'source', True)
        # Detach first; reject Python booleans/floats as well as JSON ones.
        spec = copy.deepcopy(specification)
        section = store.overlay_section(document)
        entries = [] if section is None else section['journal']
        state = overlay.fold(entries, len(document['payload']['journal']))
        _validate_spec(spec, state['sim_day'], bounds, repayments)
        report.update(specification=spec, specification_sha256=_digest(spec))
        _check(report, 'specification', 'pair', True)
        service = _service(document, terms, bounds, repayments, 'preflight')
        report['source'].update(state_digest=service.machine.state_digest(), sim_day=state['sim_day'],
                                overlay_state_digest=overlay.state_digest(state),
                                f04_journal_sha256=_digest(service.machine.export_journal()),
                                overlay_journal_sha256=_digest(entries), vendor_pin=service.source,
                                fixtures_sha256=_digest(service.producer.snapshot_inputs()['fixtures']))
        report['target'] = _preflight(service, spec, state)
        _check(report, 'preflight', 'source', True)
        plans = [_plan(spec, s, state['sim_day'], bounds['max_step_days'], i) for i, s in enumerate(spec['schedules'])]
        _reserve_ids(plans, service)
        _check(report, 'generated_ids', 'pair', True)
        # Both branches restore exactly the captured envelope and frozen fixture
        # values. Neither branch observes another branch's machine or storage.
        fixtures = copy.deepcopy(service.fixtures)
        for i, (schedule, plan) in enumerate(zip(spec['schedules'], plans)):
            branch = _service(document, terms, bounds, repayments, f'b{i}',
                              producer=PinnedFsmProducer(copy.deepcopy(fixtures)))
            try:
                report['branches'].append(_execute(branch, plan, schedule, spec, report))
            finally:
                _close(branch)
        if all(c['status'] == 'MATCHED' for c in report['comparability']['checks']):
            a, b = [s['final']['values'] for s in report['branches']]
            report['comparison'] = {'direction': 'B_MINUS_A', 'delta': {
                k: None if a[k] is None or b[k] is None else b[k] - a[k] for k in METRICS}}
            report['status'] = 'COMPARABLE'
    except ComparisonError as exc:
        _check(report, 'validation', 'source', False, exc.code, exc.entries)
    except (ApiError, store.WorkspaceError, OSError, ValueError, KeyError, TypeError, ArithmeticError, RecursionError) as exc:
        _check(report, 'composition', 'source', False, 'COMPARISON_FAILED', [type(exc).__name__])
    finally:
        if service is not None:
            _close(service)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--schedule', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        spec = loads(args.schedule.read_bytes())
    except (OSError, ValueError, UnicodeError, RecursionError):
        report = _new_report()
        report['reason'] = 'INVALID_SCHEDULE_JSON'
        _check(report, 'specification', 'pair', False, 'INVALID_SCHEDULE_JSON')
    else:
        report = compare_workspace(args.workspace, spec)
    sys.stdout.buffer.write(store.canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPARABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
