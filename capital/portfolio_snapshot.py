"""SIMULATED local diagnostic cut; no authenticated or cross-process cut claim.

Only the in-process pinned producer, immutable FixtureViews and loaded decision
note policy are supported. Canonical input bytes detach every calculation from
live service state. No public service read or persistence path is called here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from capital import covenants, forecast, margin, overlay, risk
from capital.producer import CreditError, FixtureViews, PinnedFsmProducer
from capital.projection import SimulationProjection
from capital.protocol import CreditMachine
from capital.store import WorkspaceError, canonical_bytes, overlay_section, verify_document
from capital.terms import DecisionNoteTermsPolicy

FORMAT = 'KIX_CAPITAL_PORTFOLIO_SNAPSHOT_V1'
SECTIONS = ('terms_rollup', 'risk', 'covenants', 'forecast')
_REQUIRED_TERMS = ('interest_rate', 'fees', 'term', 'default_loss_treatment',
                   'reserve', 'additional_margin', 'underwriting_depth')
ASSUMPTIONS = {
    'terms_rollup': {'draw_day': 0, 'draw_day_source': 'DEFAULT', 'as_of_day': 'CAPTURED_SIM_DAY',
                     'expected_settlement_cash_day': None},
    'risk_covenants_forecast_draw_day': 'RECORDED_DRAW_DAY',
    'forecast_settlement_cash': forecast.NO_SETTLEMENT_DAY,
    'scope': 'SERVICE_MANAGED_MUTATIONS_ONLY',
}


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class FrozenInputs:
    """Immutable canonical bytes, including all mappings and receipt gate facts."""
    raw: bytes

    @classmethod
    def capture(cls, producer_inputs, receipts, mapping, entries, terms, bounds):
        return cls(canonical_bytes({
            'version': 1, 'producer': producer_inputs, 'receipts': receipts,
            'case_fixtures': mapping, 'overlay_entries': entries,
            # Existing risk reserve rows follow loaded policy map order. Preserve
            # that order as data while the outer frozen representation is canonical.
            'policy_items_json': json.dumps(terms.items, separators=(',', ':'), ensure_ascii=True),
            'policy': {'items': terms.items, 'version': terms.version,
                       'top': terms.top, 'reason': terms.reason, 'bounds': bounds,
                       'assumptions': ASSUMPTIONS},
        }))

    def detached(self):
        return json.loads(self.raw)


def diagnostic(instance_id):
    return {
        'format': FORMAT, 'label': 'SIMULATED', 'instance_id': instance_id,
        'status': 'INCOMPLETE', 'complete': False,
        'cut': {'kind': 'LOCAL_DIAGNOSTIC', **{key: None for key in (
            'state_digest', 'overlay_state_digest', 'sim_day', 'fixtures_digest',
            'policy_inputs_digest', 'inputs_digest')}},
        'assumptions': copy.deepcopy(ASSUMPTIONS),
        'completeness': {**dict.fromkeys(('producer', 'fixtures', 'storage', 'terms'), 'UNAVAILABLE'),
                         'sections': dict.fromkeys(SECTIONS, 'UNAVAILABLE'), 'reasons': []},
        **dict.fromkeys(SECTIONS), 'snapshot_digest': None,
        'authenticated_source_cut': 'NOT_BOUND', 'funds_executed': False,
        'workspace_mutated': False, 'write_authorized': False,
    }


def finish(body):
    reasons = body['completeness']['reasons']
    body['complete'] = not reasons
    body['status'] = 'COMPLETE' if body['complete'] else 'INCOMPLETE'
    # Session identity, paths, receipt telemetry and timestamps are never hashed.
    body['snapshot_digest'] = digest({
        'format': FORMAT, 'cut': body['cut'], 'assumptions': body['assumptions'],
        'completeness': body['completeness'], **{name: body[name] for name in SECTIONS}})
    return body


def storage_health(storage, workspace_status, data):
    """Read/validate without saving. An absent file is valid only for an empty book."""
    if workspace_status != 'ACTIVE':
        return workspace_status
    try:
        document = storage.load()
        producer = data['producer']
        journal = json.loads(producer['canonical_state'])['journal']
        if document is None:
            return None if not (journal or data['receipts'] or data['case_fixtures']
                                or data['overlay_entries']) else 'STORAGE_STATE_MISMATCH'
        verify_document(document)
        payload = document['payload']
        expected = {'journal': journal, 'state_digest': producer['state_digest'],
                    'case_fixtures': data['case_fixtures'], 'receipts': data['receipts']}
        # Legacy restored receipt labels are added in RAM without rewriting storage.
        persisted = copy.deepcopy(payload)
        for stored in persisted.get('receipts', {}).values():
            receipt = stored['receipt']
            if 'role' not in receipt and 'role_provenance' not in receipt:
                receipt.update(role='UNLABELED', role_provenance='UNLABELED')
        section = overlay_section(document)
        entries = [] if section is None else overlay.restore(section, len(journal))
        if persisted != expected or entries != data['overlay_entries']:
            return 'STORAGE_STATE_MISMATCH'
    except (WorkspaceError, OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return exc.code if isinstance(exc, WorkspaceError) else 'WORKSPACE_UNREADABLE'
    return None


def compose(frozen, body):
    data = frozen.detached()
    captured = data['producer']
    state = json.loads(captured['canonical_state'])
    journal = state['journal']
    cases = {row['advance_id']: row for row in state['cases']}
    fixtures = captured['fixtures']
    policy = data['policy']
    terms = DecisionNoteTermsPolicy.__new__(DecisionNoteTermsPolicy)
    terms.items, terms.version = json.loads(data['policy_items_json']), policy['version']
    terms.top, terms.reason = policy['top'], policy['reason']
    entries = data['overlay_entries']
    folded = overlay.fold(entries)
    sim_day = folded['sim_day']
    body['cut'].update(
        state_digest=captured['state_digest'], overlay_state_digest=overlay.state_digest(folded),
        sim_day=sim_day, fixtures_digest=digest(fixtures['rows']),
        policy_inputs_digest=digest({'version': 1, **policy}))
    # Only receipt gates affect calculations; session ids/fingerprints do not.
    gates = {}
    for row in journal:
        if row['op'] == 'draw':
            stored = data['receipts'].get(row['idempotency_key'], {}).get('receipt', {})
            if stored.get('outcome') != 'ACCEPTED':
                body['completeness']['reasons'].append('DRAW_RECEIPT_GATE_MISSING')
                return finish(body)
            try:
                gate = stored['result']['credit']['settlement_gate']
                if type(gate) is not str or not gate:
                    raise ValueError('missing draw gate')
                gates[row['advance_id']] = gate
            except (KeyError, TypeError, ValueError):
                body['completeness']['reasons'].append('DRAW_RECEIPT_GATE_MISSING')
                return finish(body)
    body['cut']['inputs_digest'] = digest({
        'version': 1, 'cut': {k: v for k, v in body['cut'].items() if k != 'inputs_digest'},
        'fixtures': fixtures, 'case_fixtures': data['case_fixtures'], 'draw_gates': gates,
        'overlay_entries': entries, 'policy_items_json': data['policy_items_json']})
    if (terms.top != 'BOUND' or not terms._ready(*_REQUIRED_TERMS) or policy['bounds'] is None
            or not risk.usable(terms) or not forecast.usable(terms)):
        body['completeness']['terms'] = 'NOT_BOUND'
        body['completeness']['reasons'].append('TERMS_NOT_BOUND')
        return finish(body)
    body['completeness']['terms'] = 'BOUND'
    # Scratch replay reconciles captured canonical cases and resolves APPROVED
    # preview gates without consulting or advancing the live machine.
    views = FixtureViews.__new__(FixtureViews)
    views.rows, views.profiles = fixtures['rows'], fixtures['profiles']
    views.beneficiaries = fixtures['beneficiaries']
    views.projection_ids = frozenset(fixtures['projection_ids'])
    scratch = PinnedFsmProducer(views, CreditMachine.restore(journal, views))
    if scratch.canonical_state() != captured['canonical_state'] or set(cases) != set(data['case_fixtures']):
        raise ValueError('CAPTURE_STATE_MISMATCH')
    subjects = []
    for key, case in sorted(cases.items()):
        fixture_id = data['case_fixtures'][key]
        if fixture_id != case['claim_id']:
            raise ValueError('CAPTURE_STATE_MISMATCH')
        gate = case['settlement_gate']
        if case['phase'] == 'APPROVED':
            try:
                gate = scratch.preview_draw(key)['credit']['settlement_gate']
            except CreditError:
                pass
        subjects.append({'advance_id': key, 'case': case, 'claim': views.view(fixture_id)['claim'], 'gate': gate})
    drawn = []
    by_id = {s['advance_id']: s for s in subjects}
    for index, row in enumerate(journal):
        if row['op'] == 'draw':
            key = row['advance_id']
            drawn.append({**by_id[key], 'gate': gates[key], 'draw_day': overlay.draw_day_for(entries, index),
                          'principal': cases[key]['outstanding_exposure']})
    drawn.sort(key=lambda subject: subject['advance_id'])
    margins = []
    for subject in drawn:
        value = terms.margin_terms(subject['case'], subject['claim'], gate=subject['gate'],
                                   draw_day=subject['draw_day'], refund_after_draw=False)
        if value is not None:
            margins.append({**subject, 'margin': value})
    projected = SimulationProjection().project(journal, [views.view(k) for k in sorted(views.projection_ids)])
    outstanding = sum(row['outstanding'] for row in projected['read_model']['advances'])
    body['terms_rollup'] = terms.portfolio(subjects, draw_day=0, draw_day_source='DEFAULT', as_of_day=sim_day,
                                           expected_settlement_cash_day=None)
    body['risk'] = risk.build(drawn, margins, terms=terms, sim_day=sim_day,
                              projection_outstanding_krw=outstanding)
    margin_rows = margin.row_blocks(folded, margins, mutable=False)
    block = margin.status_block(folded, margin_rows, mutable=False, bound=True,
                                cure_terms=margins[0]['margin'] if margins else None)
    body['covenants'] = covenants.build(drawn, margin_rows, block, body['risk'], terms=terms, sim_day=sim_day)
    posted = {key: row['posted_contract_krw'] + row['posted_default_krw'] for key, row in folded['advances'].items()}
    body['forecast'] = forecast.build(drawn, terms=terms, sim_day=sim_day, posted_interest=posted)
    for name in SECTIONS:
        section = body[name]
        available = section['status'] == 'BOUND'
        body['completeness']['sections'][name] = 'AVAILABLE' if available else 'PARTIAL'
        if not available:
            body['completeness']['reasons'].append(name.upper() + '_PARTIAL')
    checks = [body[name]['reconciliation']['matched'] for name in ('risk', 'covenants', 'forecast')]
    checks.extend((body['risk']['reserve']['complete'],
                   body['forecast']['reconciliation']['outstanding_principal_krw'] == outstanding))
    if not all(checks):
        body['completeness']['reasons'].append('RECONCILIATION_FAILED')
    return finish(body)
