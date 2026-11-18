"""Offline, advisory inventory of undrawn nonterminal F04 cases.

Run ``python3 -m capital.origination --workspace DIR``. Exit 0 means complete
inventory coverage, 1 means incomplete evidence or a failed audit/restoration,
and 2 means argument misuse. No workspace lock, write, repair or command.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import sys

from capital import audit, evidence, overlay, slices, store
from capital.service import ApiError, digest
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_ORIGINATION_READINESS_V1'
_REQUIRED_POLICY = ('underwriting_depth', 'additional_margin', 'interest_rate')
LIMITATIONS = (
    'Individually acceptable previews do not establish simultaneous fundability. '
    'Underwriting remains advisory.',
    'F04 previews do not evaluate every live command guard, including the separate slice draw guard.',
    'The auditor role is a synthetic evaluation context, not authenticated authority.',
    'COMPLETE describes inventory coverage, not approval or admission authority.',
)


def _cut(service):
    """Include reservations (canonical state), receipts, mappings and overlays."""
    return store.canonical_bytes({
        'state': service.machine.canonical_state(),
        'journal': service.machine.export_journal(),
        'receipts': service.receipts,
        'case_fixtures': service.case_fixtures,
        'overlay': service.overlay_entries,
        'fixtures': service.fixtures.rows,
        'profiles': service.fixtures.profiles,
        'beneficiaries': service.fixtures.beneficiaries,
        'terms': service.terms.items,
        'slice_policy': service.slice_policy,
    })


def _require_cut(service, original, observed=None):
    if (_cut(service) != original or
            (observed is not None and observed != service.machine.state_digest())):
        raise ApiError('READ_ONLY_INVARIANT', 500)


def _references(service, document):
    """Zero-based source indexes; aggregate inputs reference the entire cut."""
    journal = document['payload']['journal']
    f04 = [{'index': i, 'pointer': f'/payload/journal/{i}',
            'advance_id': entry['advance_id'], 'operation_id': entry['idempotency_key'],
            'op': entry['op'], 'sha256': digest(entry)}
           for i, entry in enumerate(journal)]
    overlays = [{'index': i, 'pointer': f'/overlay/journal/{i}',
                 'overlay_id': entry['overlay_id'], 'kind': entry['kind'],
                 'sha256': digest(entry)}
                for i, entry in enumerate(service.overlay_entries)]
    fixtures = [{'fixture_id': fid, 'claim_id': service.fixtures.rows[fid]['claim']['claim_id'],
                 'profile': service.fixtures.profile(fid),
                 'beneficiary_role': service.fixtures.beneficiary(fid),
                 'view_sha256': digest(service.fixtures.rows[fid]),
                 'claim_sha256': digest(service.fixtures.rows[fid]['claim'])}
                for fid in sorted(service.fixtures.rows)]
    portfolio = [{'advance_id': aid, 'fixture_id': service.case_fixtures[aid],
                  'view_sha256': digest(service.machine.view(aid)),
                  'f04_indexes': [r['index'] for r in f04 if r['advance_id'] == aid]}
                 for aid in sorted(service.case_fixtures)]
    return {'f04': f04, 'overlay': overlays, 'fixtures': fixtures, 'portfolio': portfolio}


def _inventory(service, document, source):
    original = _cut(service)
    state_digest = service.machine.state_digest()
    journal = service.machine.export_journal()
    state = overlay.fold(service.overlay_entries, len(journal))
    policy = service.terms.status()
    source.update({
        'recorded_sim_day': state['sim_day'],
        'overlay_state_digest': overlay.state_digest(state),
        'fixtures_digest': digest(service.fixtures.rows),
        'vendor_pin': copy.deepcopy(service.source),
        'loaded_policy': {'terms': policy, 'slice_policy': copy.deepcopy(service.slice_policy),
                          'inputs_digest': digest({'terms': service.terms.items,
                                                   'slice_policy': service.slice_policy})},
        'references': _references(service, document),
    })
    refs = source['references']
    rows = []
    reasons = []
    if (any(policy['items'].get(name) != 'ADOPTED' for name in _REQUIRED_POLICY)
            or (slices.registry(state) and service.slice_policy is None)):
        reasons.append('POLICY_EVIDENCE_NOT_BOUND')
    # Enumeration order is deliberately immaterial. Only the final rows are sorted.
    for advance_id, fixture_id in service.case_fixtures.items():
        _require_cut(service, original)
        case = service.machine.view(advance_id)
        if case['drawn_exposure'] != 0 or case['terminal'] is not False:
            continue
        preview = service.preview_draw(advance_id, service.instance_id)
        _require_cut(service, original, preview['observed_state_digest'])
        try:
            record = service.underwrite(advance_id, service.instance_id, 'auditor', sim_day=state['sim_day'])
        except ApiError as exc:
            if exc.code != 'NOT_BOUND':
                raise
            # A restored slice registry can encounter missing slice-policy
            # evidence before underwrite reaches its record producer. Preserve
            # the existing number-free NOT_BOUND record, never bypass the guard
            # or evaluate a subject with its slice constraints removed.
            record = service._terms_envelope(service.underwriting._unbound(
                {'advance_id': advance_id, 'candidate': False}, 'auditor'))
        _require_cut(service, original, record['observed_state_digest'])
        if record['status'] == 'NOT_BOUND' and 'POLICY_EVIDENCE_NOT_BOUND' not in reasons:
            reasons.append('POLICY_EVIDENCE_NOT_BOUND')
        rows.append({
            'advance_id': advance_id, 'fixture_id': fixture_id, 'claim_id': case['claim_id'],
            'phase': case['phase'], 'amount': case['amount'],
            'fsm_preview': preview, 'underwriting': record,
            'source_references': {
                'f04_indexes': [r['index'] for r in refs['f04'] if r['advance_id'] == advance_id],
                'fixture_index': next(i for i, r in enumerate(refs['fixtures']) if r['fixture_id'] == fixture_id),
                # All portfolio cases and overlay entries can contribute to aggregate
                # caps, shared reservations or slice holds, including excluded cases.
                'portfolio_indexes': list(range(len(refs['portfolio']))),
                'overlay_indexes': list(range(len(refs['overlay']))),
                'policy_note_sha256': record.get('note_sha256'),
            },
        })
    _require_cut(service, original, state_digest)
    return sorted(rows, key=lambda row: row['advance_id']), reasons


def report_workspace(directory) -> dict:
    """Capture workspace.json once, audit those bytes, then restore read-only.

    Deterministic for identical bytes, supplied path and loaded local inputs.
    On failed audit/restoration/invariants, cases is null: no partial conclusions.
    """
    try:
        raw = (Path(directory) / store.FILE_NAME).read_bytes()
    except (OSError, TypeError, ValueError):
        raw = None
    audited = audit.audit_workspace_bytes(raw, workspace=str(directory))
    report = {
        'format': FORMAT, 'label': 'SIMULATED', 'mode': 'READ_ONLY_ORIGINATION_REVIEW',
        'status': 'AUDIT_FAILED', 'reasons': [], 'cases': None,
        'source': {
            'workspace': str(directory), 'file': store.FILE_NAME,
            'captured_sha256': None if raw is None else hashlib.sha256(raw).hexdigest(),
            'payload_sha256': audited['payload_sha256'], 'state_digest': audited['state_digest'],
            'audit': audited,
        },
        'limitations': list(LIMITATIONS),
        'authentication': 'NOT_BOUND', 'historical_policy_provenance': 'NOT_BOUND',
        'funds_executed': False, 'workspace_mutated': False, 'write_authorized': False,
    }
    if not audited['ok']:
        report['reasons'] = [audited['reason']]
        return report
    service = None
    failure = 'WORKSPACE_RESTORE_FAILED'
    try:
        document = loads(raw)
        service = evidence.offline_service(document)
        if service.workspace_status != 'ACTIVE':
            raise ValueError('inactive restore')
        failure = 'INVENTORY_FAILED'
        cases, reasons = _inventory(service, document, report['source'])
        report.update(cases=cases, reasons=reasons, status='INCOMPLETE' if reasons else 'COMPLETE')
    except Exception as exc:
        reason = 'READ_ONLY_INVARIANT' if isinstance(exc, ApiError) and exc.code == 'READ_ONLY_INVARIANT' else failure
        report.update(status='INCOMPLETE', reasons=[reason], cases=None)
    finally:
        if service is not None:
            service.observability.close()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, help='captured local workspace directory')
    args = parser.parse_args(argv)
    report = report_workspace(args.workspace)
    sys.stdout.buffer.write(store.canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
