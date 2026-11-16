"""SIMULATED offline draw permutations over one explicitly captured workspace.

Exploratory only: no recommended order, approval, live batch, clock advancement,
reserve booking, network, workspace lock or signing key. Current local policies
are comparison-time provisional inputs, not authenticated historical policy.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys

from capital import audit, overlay, slices
from capital.evidence import offline_service
from capital.portfolio_compare import _prepare, _compatible, _movement, _check
from capital.portfolio_snapshot import FrozenInputs, digest
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.service import ApiError, CapitalService, MAX_OPERATIONS
from capital.store import FILE_NAME, InMemoryStorage, canonical_bytes
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_DRAW_ORDER_REHEARSAL_V1'
INSTANCE = 'draw-order-rehearsal'


def _project(value):
    """Explicit volatile-field exclusion; retain economic and observed digests."""
    if type(value) is dict:
        return {k: _project(v) for k, v in value.items()
                if k not in ('instance_id', 'saved_at', 'saved_by_instance')}
    if type(value) is list:
        return [_project(v) for v in value]
    return value


def _frozen(service):
    return FrozenInputs.capture(service.producer.snapshot_inputs(), service.receipts,
                                service.case_fixtures, service.overlay_entries,
                                service.terms, service.overlay_bounds)


def _policy(service, day):
    return copy.deepcopy({
        'version': 1,
        'terms': {'ordered_items': [[k, v] for k, v in service.terms.items.items()],
                  # Reserve buckets also follow nested map order. Canonical
                  # JSON sorts maps, so retain that iteration order as text too.
                  'items_json': json.dumps(service.terms.items, separators=(',', ':'), ensure_ascii=True),
                  'version': service.terms.version, 'top': service.terms.top,
                  'reason': service.terms.reason, 'status': service.terms.status()},
        'overlay_bounds': service.overlay_bounds,
        'repayment_bounds': service.repayment_bounds,
        'slice_policy': service.slice_policy, 'recovery_policy': service.recovery_policy,
        'assumptions': {'sim_day': day, 'role': 'organizer', 'clock_advanced': False,
                        'draw_day': 'EXISTING_OVERLAY_JOURNAL_CUT_SEMANTICS'},
    })


def _prepare_service(service, side, checks):
    return _prepare(_frozen(service), {}, side, checks)


def _clone(document, fixtures, terms, policy):
    views = FixtureViews.__new__(FixtureViews)
    data = copy.deepcopy(fixtures)
    views.rows, views.profiles = data['rows'], data['profiles']
    views.beneficiaries = data['beneficiaries']
    views.projection_ids = frozenset(data['projection_ids'])
    service = CapitalService(InMemoryStorage.from_envelope(document),
                             producer=PinnedFsmProducer(views), terms=copy.deepcopy(terms),
                             overlay_bounds=copy.deepcopy(policy['overlay_bounds']),
                             repayment_bounds=copy.deepcopy(policy['repayment_bounds']))
    service.instance_id = INSTANCE
    service.storage.writer_instance = INSTANCE
    service.slice_policy = copy.deepcopy(policy['slice_policy'])
    service.recovery_policy = copy.deepcopy(policy['recovery_policy'])
    return service


def _measures(service):
    # F04 reserved_open is claim-wide. Never sum the repeated per-advance view.
    claims, exposures = {}, {}
    for advance, claim in sorted(service.case_fixtures.items()):
        case = service.machine.view(advance)
        claims[claim] = case['reserved_open']
        exposures[advance] = case['outstanding_exposure']
    state = overlay.fold(service.overlay_entries)
    registry = slices.registry(state)
    observations = service._slice_observations(state) if registry else {}
    slice_exposure = {key: slices.derived(row, observations[row['claim_id']])['exposure_krw']
                      for key, row in sorted(registry.items())}
    return {'claim_reservations_krw': claims, 'advance_exposure_krw': exposures,
            'slice_exposure_krw': slice_exposure}


def _final(service):
    checks = []
    _prepare_service(service, 'final', checks)
    if not all(c['status'] == 'MATCHED' for c in checks):
        raise ValueError('FINAL_INPUT_COVERAGE_INCOMPLETE')
    body = service.risk()
    if (body.get('status') != 'BOUND' or not body.get('reserve', {}).get('complete')
            or not body.get('reconciliation', {}).get('matched')):
        raise ValueError('FINAL_RISK_INCOMPLETE')
    return {'measures': _measures(service), 'risk': body,
            'state_digest': service.producer.state_digest(),
            'overlay_state_digest': overlay.state_digest(overlay.fold(service.overlay_entries))}


def _comparison(orderings, selection):
    outcomes = []
    for key in selection:
        variants = {}
        for index, ordering in enumerate(orderings):
            step = next((s for s in ordering['steps'] if s['advance_id'] == key), None)
            result = step['command'] if step else {'kind': 'NOT_ATTEMPTED'}
            signature = {k: result[k] for k in ('kind', 'outcome', 'code', 'error', 'status', 'detail') if k in result}
            token = canonical_bytes(signature)
            variants.setdefault(token, {'result': signature, 'ordering_indexes': []})['ordering_indexes'].append(index)
        outcomes.append({'advance_id': key, 'order_sensitive': len(variants) > 1,
                         'variants': list(variants.values())})
    # Compare financial values, never journal/risk digests or operation identities.
    measures = []
    for ordering in orderings:
        final = ordering['final']
        measures.append(None if final is None else {
            **final['measures'], **{k: final['risk'][k] for k in
                ('totals', 'by_tier', 'maturity_buckets', 'overdue_aging', 'concentration', 'reserve', 'stress')}})
    differing = []
    if measures and all(m is not None for m in measures):
        for key in measures[0]:
            if len({canonical_bytes(m[key]) for m in measures}) > 1:
                differing.append({'measure': key, 'by_ordering': [m[key] for m in measures]})
    return {'outcome_variants': outcomes, 'differing_financial_measures': differing,
            'complete_orderings': sum(o['status'] == 'COMPLETE' for o in orderings)}


def rehearse_workspace(directory, advance_ids):
    """Audit one read of workspace.json and rehearse 2, 6 or 24 memory books.

    Business refusals complete normally. Missing inputs and unexpected/UNKNOWN
    results fail closed, without retry. No exception detail includes local paths.
    """
    report = {'format': FORMAT, 'label': 'SIMULATED', 'status': 'INCOMPLETE',
              'reasons': [], 'audit': None, 'input_metadata': {}, 'inputs': {},
              'selection': [], 'baseline': None, 'orderings': [], 'comparison': None,
              'funds_executed': False, 'workspace_mutated': False, 'lock_taken': False,
              'historical_policy_provenance': 'NOT_BOUND', 'authentication': 'NOT_BOUND',
              'reserve_funding': 'NOT_BOUND',
              'limitations': ['Persisted evidence only: an earlier UNKNOWN without persisted evidence is unknowable.',
                              'Exploratory comparison; no recommended ordering or settlement allocation priority.']}
    def fail(reason):
        report['reasons'].append(reason)
        return _project_report(report)

    try:
        path = Path(directory) / FILE_NAME
        raw = path.read_bytes() if path.is_file() else None
    except (OSError, TypeError, ValueError):
        raw = None
    report['audit'] = audit.audit_workspace_bytes(raw, workspace='CAPTURED_WORKSPACE')
    report['inputs']['workspace_sha256'] = None if raw is None else hashlib.sha256(raw).hexdigest()
    if not report['audit']['ok']:
        return fail('WORKSPACE_AUDIT_FAILED')
    document = loads(raw)
    report['input_metadata'] = {k: document[k] for k in ('saved_at', 'saved_by_instance')}
    report['inputs']['payload_sha256'] = document['payload_sha256']
    if (type(advance_ids) not in (list, tuple) or not 2 <= len(advance_ids) <= 4
            or any(type(k) is not str for k in advance_ids)):
        return fail('SELECTION_REQUIRES_TWO_TO_FOUR_IDS')
    if len(set(advance_ids)) != len(advance_ids):
        return fail('DUPLICATE_ADVANCE')
    selection = report['selection'] = sorted(advance_ids)
    baseline = offline_service(document)
    clones = []
    try:
        journal = baseline.producer.export_journal()
        for key in selection:
            if key not in baseline.case_fixtures:
                return fail('UNKNOWN_ADVANCE:' + key)
            if (baseline.machine.view(key)['phase'] != 'APPROVED'
                    or any(r['op'] == 'draw' and r['advance_id'] == key for r in journal)):
                return fail('INELIGIBLE_ADVANCE:' + key)
        orders = list(itertools.permutations(selection))
        keys = {f'dor-p{p:02d}-s{s}' for p in range(len(orders)) for s in range(len(selection))}
        used = (set(baseline.receipts) | {r['idempotency_key'] for r in journal}
                | {r['overlay_id'] for r in baseline.overlay_entries})
        if keys & used:
            return fail('OPERATION_ID_COLLISION')
        if len(baseline.receipts) + len(selection) > MAX_OPERATIONS:
            return fail('SIMULATION_CAPACITY')
        checks = report['readiness_checks'] = []
        prepared = _prepare_service(baseline, 'baseline', checks)
        if not all(c['status'] == 'MATCHED' for c in checks):
            return fail('COMPARISON_INPUTS_UNAVAILABLE')
        day = overlay.fold(baseline.overlay_entries)['sim_day']
        bad_margins = []
        for key in selection:
            case = baseline.machine.view(key)
            claim = baseline.fixtures.view(baseline.case_fixtures[key])['claim']
            # Existing service preview resolves the prospective gate, without
            # mutating its book. A business refusal has no applicable tier.
            gate = baseline._case_gate(key, case)
            kwargs = {'gate': gate, 'draw_day': day}
            if (baseline.terms.ledger_terms(case, claim, **kwargs) is not None
                    and baseline.terms.margin_terms(case, claim, **kwargs) is None):
                bad_margins.append(key)
        _check(checks, 'selected_margin_terms', 'baseline', not bad_margins,
               'APPLICABLE_MARGIN_TERMS_UNUSABLE', bad_margins)
        if bad_margins:
            return fail('COMPARISON_INPUTS_UNAVAILABLE')
        policy = _policy(baseline, day)
        if any(policy[k] is None for k in ('slice_policy', 'recovery_policy', 'repayment_bounds')):
            return fail('REPLAY_POLICY_UNAVAILABLE')
        fixtures = baseline.producer.snapshot_inputs()['fixtures']
        report['inputs'].update(state_digest=baseline.producer.state_digest(),
            overlay_state_digest=overlay.state_digest(overlay.fold(baseline.overlay_entries)),
            fixtures_digest=digest(fixtures), policy_inputs_digest=digest(policy),
            policy_inputs=policy, sim_day=day)
        report['baseline'] = _final(baseline)
        # All restorations and compatibility checks precede every replay command.
        for _ in orders:
            clone = _clone(document, fixtures, baseline.terms, policy)
            clones.append(clone)
            clone_checks = []
            restored = _prepare_service(clone, 'clone', clone_checks)
            _compatible(prepared, restored, clone_checks)
            if (clone.workspace_status != 'ACTIVE' or _policy(clone, day) != policy
                    or clone.producer.snapshot_inputs()['fixtures'] != fixtures
                    or not all(c['status'] == 'MATCHED' for c in clone_checks)):
                report['clone_checks'] = clone_checks
                return fail('CLONE_INPUTS_MISMATCH')
        for p, (order, clone) in enumerate(zip(orders, clones)):
            ordering = {'order': list(order), 'status': 'COMPLETE', 'steps': [], 'final': None}
            report['orderings'].append(ordering)
            for s, key in enumerate(order):
                before = _measures(clone)
                step = {'advance_id': key, 'operation_id': f'dor-p{p:02d}-s{s}',
                        'observed_state_digest': clone.producer.state_digest(),
                        'underwriting': None, 'command': {'kind': 'NOT_ATTEMPTED'}}
                ordering['steps'].append(step)
                try:
                    step['underwriting'] = clone.underwrite(key, instance_id=INSTANCE, role='organizer', sim_day=day)
                    if step['underwriting'].get('status') != 'BOUND':
                        raise ValueError('UNDERWRITING_UNAVAILABLE')
                    try:
                        result = clone.execute({'instance_id': INSTANCE, 'operation_id': step['operation_id'],
                                                'op': 'draw', 'advance_id': key, 'args': {}}, role='organizer')
                        step['command'] = {'kind': 'RECEIPT', **result}
                        if result.get('outcome') not in ('ACCEPTED', 'REJECTED'):
                            raise ValueError('DRAW_OUTCOME_UNKNOWN')
                    except ApiError as exc:
                        step['command'] = {'kind': 'API_ERROR', 'code': exc.code,
                                           'status': exc.status, 'detail': exc.detail}
                        if exc.code != 'SLICE_DRAW_REFUSED':
                            raise
                except Exception as exc:
                    ordering['status'] = 'INCOMPLETE'
                    step['failure'] = exc.code if isinstance(exc, ApiError) else (
                        str(exc) if type(exc) is ValueError else 'UNEXPECTED_REPLAY_FAULT')
                    report['reasons'].append(f'ORDERING_{p}_INCOMPLETE')
                finally:
                    step['movements'] = _movement(before, _measures(clone))
                if ordering['status'] != 'COMPLETE':
                    break
            try:
                ordering['final'] = _final(clone)
            except Exception:
                ordering['status'] = 'INCOMPLETE'
                report['reasons'].append(f'ORDERING_{p}_FINAL_UNAVAILABLE')
        report['comparison'] = _comparison(report['orderings'], selection)
        report['status'] = 'INCOMPLETE' if report['reasons'] else 'COMPLETE'
        return _project_report(report)
    except Exception:
        return fail('REHEARSAL_INPUT_OR_CALCULATION_FAILED')
    finally:
        baseline.observability.close()
        for clone in clones:
            clone.observability.close()


def _project_report(report):
    metadata = report['input_metadata']
    result = _project(report)
    result['input_metadata'] = metadata
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, help='explicit directory containing workspace.json')
    parser.add_argument('--advance', action='append', required=True, help='approved advance ID; repeat 2–4 times')
    args = parser.parse_args(argv)
    report = rehearse_workspace(args.workspace, args.advance)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
