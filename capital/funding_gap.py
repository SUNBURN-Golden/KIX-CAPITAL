"""Read-only settlement-delay analysis for one audited local workspace cut."""
from __future__ import annotations

import hashlib
import os
import re
import stat
from collections import defaultdict
from pathlib import Path

from capital import audit, forecast, overlay, portfolio_snapshot, recovery, resources, shadow, slices, strict_json
from capital.evidence import offline_service
from capital.policy import DecisionNoteSettlementPolicy
from capital.store import FILE_NAME

SCHEDULE_MAX_BYTES = 1024 * 1024
FORMAT = 'KIX_CAPITAL_FUNDING_GAP_REPORT_V1'
MODEL_NOTE = 'CAPITAL_FUNDING_GAP.md'
SETTLEMENT_NOTE = 'CAPITAL_SETTLEMENT_POLICY.md'
REPAYMENT_NOTE = 'CAPITAL_REPAYMENT_POSTING.md'
GAP_ITEMS = (
    'cashflow_viewpoint', 'opening_cash_assumption', 'source_identity_and_budget',
    'due_day_ordering', 'shortfall_and_carry', 'unsupported_case_policy', 'horizon_and_input_bounds',
)
DUE_KINDS = (forecast.LEG_PRINCIPAL, forecast.LEG_INTEREST)
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', re.ASCII)
BOUND_FIELDS = (
    'advances_min', 'advances_max', 'sources_min', 'sources_max', 'raw_event_rows_max',
    'horizon_days_default', 'horizon_days_min', 'horizon_days_max',
    'individual_amount_min_krw', 'individual_amount_max_krw', 'sim_day_min', 'sim_day_max',
)


class InvalidInput(ValueError):
    pass


class NotBound(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_regular(path, limit=None):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError('regular file required')
        if limit is None:
            return stream.read()
        if info.st_size > limit:
            raise InvalidInput('SCHEDULE_TOO_LARGE')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise InvalidInput('SCHEDULE_TOO_LARGE')
        return raw


def _entry_marks(note, names, version_key):
    block = note['block'] or {}
    entries = block.get('entries', {})
    marks = {}
    for name in names:
        entry = entries.get(name) if isinstance(entries, dict) else None
        value = entry.get('value') if isinstance(entry, dict) else None
        marks[name] = {'status': entry.get('status') if isinstance(entry, dict) else None,
                       'version': value.get('policy_version') if isinstance(value, dict) else None}
    return {**resources.provenance(note), 'decision_id': block.get('decision_id'),
            'schema': block.get('schema'), 'version': block.get(version_key), 'status': block.get('status'),
            'entries': marks}


def _policies(marks):
    model = resources.read_note(resources.note_path(MODEL_NOTE))
    settlement = DecisionNoteSettlementPolicy()
    repayment = resources.read_note(resources.note_path(REPAYMENT_NOTE))
    gap_block = model['block'] or {}
    binding = gap_block.get('dependency_field_binding', {})
    settlement_names = ('allocation_order', 'refund_bearer', 'residual_and_late_cash')
    repayment_names = ('f04_repay_coupling', 'interest_payment_entry_schema', 'unapplied_cash_handling',
                       'close_gate_enforcement', 'margin_cure_interaction')
    marks.update({
        MODEL_NOTE: _entry_marks(model, GAP_ITEMS, 'model_version'),
        SETTLEMENT_NOTE: _entry_marks(settlement.note, settlement_names, 'policy_version'),
        REPAYMENT_NOTE: _entry_marks(repayment, repayment_names, 'policy_version'),
    })
    gap = {name: overlay._adopted(gap_block, name) for name in GAP_ITEMS}
    # These literals are policy field names and supported interpretation tags.
    alloc = overlay._adopted(settlement.note['block'], 'allocation_order')
    refund = overlay._adopted(settlement.note['block'], 'refund_bearer')
    residual = overlay._adopted(settlement.note['block'], 'residual_and_late_cash')
    coupling = overlay._adopted(repayment['block'], 'f04_repay_coupling')
    interest = overlay._adopted(repayment['block'], 'interest_payment_entry_schema')
    held = overlay._adopted(repayment['block'], 'unapplied_cash_handling')
    close = overlay._adopted(repayment['block'], 'close_gate_enforcement')
    margin = overlay._adopted(repayment['block'], 'margin_cure_interaction')
    if (not gap_block.get('model_version') or type(binding) is not dict
            or binding.get('status') != 'SPECIFIED'
            or binding.get('policy_sources') != [f'docs/decisions/{name}' for name in
                                                (SETTLEMENT_NOTE, REPAYMENT_NOTE)]
            or binding.get('settlement_entries') != list(settlement_names)
            or binding.get('repayment_entries') != list(repayment_names)
            or any(value is None for value in (*gap.values(), alloc, refund, residual,
                                                coupling, interest, held, close, margin))
            or settlement.outcome != 'DECIDED'):
        raise NotBound('REQUIRED_POLICY_NOT_ADOPTED')
    if (coupling.get('principal_source') != 'F04_OUTSTANDING_READ_NEVER_DUPLICATED'
            or interest.get('due_rounding') != 'FLOOR_WHOLE_KRW_SUBWON_CARRY_DERIVED_NEVER_ROUNDED_OR_LOST'
            or not refund.get('application_to_lines') or not refund.get('reason_classes_ordered')
            or held.get('auto_apply_on_clock_advance') is not False
            or close.get('mode') != 'ADVISORY_NEVER_REJECTS_F04_CLOSE'
            or margin.get('evaluation') != 'PURE_FOLD_OF_JOURNAL_OWNED_BY_margin-cure-default'
            or gap['due_day_ordering'].get('same_day_order') != ['SOURCE_RELEASES', 'AGGREGATE_DUE_OBLIGATIONS']
            or type(gap['due_day_ordering'].get('delay_days_min')) is not int
            or not gap['due_day_ordering'].get('snapshot_cut')
            or gap['shortfall_and_carry'].get('retain_negative_net') is not True
            or type(gap['opening_cash_assumption'].get('default_krw')) is not int
            or gap['opening_cash_assumption']['default_krw'] != 0
            or not all(gap['cashflow_viewpoint'].get(key) for key in ('scope', 'source_basis', 'beneficiary_id'))
            or gap['source_identity_and_budget'].get('currency') != 'KRW'
            or gap['source_identity_and_budget'].get('source_key') != [
                'workspace_id', 'beneficiary_id', 'claim_id', 'settlement_entitlement_id', 'currency']
            or gap['unsupported_case_policy'].get('supported_status') != 'EVALUATED_HYPOTHETICAL'
            or any(type(gap['horizon_and_input_bounds'].get(key)) is not int for key in BOUND_FIELDS)):
        raise NotBound('UNSUPPORTED_POLICY_BINDING')
    return gap, settlement, residual


def _shape(item, required, optional=()):
    if type(item) is not dict or not set(required) <= item.keys() <= set(required) | set(optional):
        raise InvalidInput('UNEXPECTED_OR_MISSING_FIELDS')


def _integer(value, low, high, reason='INTEGER_OUT_OF_BOUNDS'):
    if type(value) is not int or not low <= value <= high:
        raise InvalidInput(reason)
    return value


def _amount(value, bounds):
    return _integer(value, bounds['individual_amount_min_krw'], bounds['individual_amount_max_krw'],
                    'AMOUNT_OUT_OF_BOUNDS')


def _day(value, bounds):
    return _integer(value, bounds['sim_day_min'], bounds['sim_day_max'], 'SIM_DAY_OUT_OF_BOUNDS')


def _label(value):
    if type(value) is not str or not LABEL.fullmatch(value):
        raise InvalidInput('INVALID_IDENTIFIER')
    return value


def _reference(ref):
    _shape(ref, ('kind', 'id'))
    if ref['kind'] not in ('FIXTURE', 'CLAIM', 'ADVANCE'):
        raise InvalidInput('INVALID_REFERENCE_KIND')
    _label(ref['id'])


def _validate_opening(opening, bounds):
    _shape(opening, ('origin', 'as_of_sim_day', 'total_krw', 'lots'))
    if opening['origin'] != 'EXPLICIT_SYNTHETIC_ASSUMPTION' or type(opening['lots']) is not list:
        raise InvalidInput('INVALID_OPENING_CASH')
    _day(opening['as_of_sim_day'], bounds)
    total = _amount(opening['total_krw'], bounds)
    observed = 0
    for lot in opening['lots']:
        if type(lot) is dict and lot.get('kind') == 'SETTLEMENT_RECEIPT':
            _shape(lot, ('lot_id', 'kind', 'amount_krw', 'reference', 'received_offset_krw'))
            _reference(lot['reference'])
            _amount(lot['received_offset_krw'], bounds)
        else:
            _shape(lot, ('lot_id', 'kind', 'amount_krw'))
            if lot['kind'] != 'INDEPENDENT_SYNTHETIC_ENDOWMENT':
                raise InvalidInput('INVALID_OPENING_LOT_KIND')
        _label(lot['lot_id'])
        observed += _amount(lot['amount_krw'], bounds)
    if observed != total:
        raise InvalidInput('OPENING_CASH_TOTAL_MISMATCH')


def _validate_schedule(schedule, gap):
    bounds = gap['horizon_and_input_bounds']
    _shape(schedule, ('scenario_id', 'workspace_id', 'snapshot_digest', 'beneficiary_id',
                      'advance_ids', 'sources'), ('opening_cash', 'horizon_days'))
    _label(schedule['scenario_id'])
    _label(schedule['beneficiary_id'])
    for name, prefix in (('workspace_id', 'sha256:'), ('snapshot_digest', '')):
        if type(schedule[name]) is not str or not re.fullmatch(prefix + r'[0-9a-f]{64}', schedule[name]):
            raise InvalidInput('INVALID_CAPTURE_PIN')
    advances, sources = schedule['advance_ids'], schedule['sources']
    if type(advances) is not list or type(sources) is not list:
        raise InvalidInput('INVALID_SCHEDULE_LIST')
    raw_rows = len(DUE_KINDS) * len(advances)
    for source in sources:
        _shape(source, ('reference', 'basis', 'budget_krw', 'delay_days', 'releases'))
        if type(source['releases']) is not list:
            raise InvalidInput('INVALID_RELEASE_LIST')
        raw_rows += len(source['releases'])
    if raw_rows > bounds['raw_event_rows_max']:
        raise InvalidInput('RAW_EVENT_ROW_LIMIT')
    selected = sorted({_label(ref) for ref in advances})
    _integer(len(selected), bounds['advances_min'], bounds['advances_max'], 'UNIQUE_ADVANCE_LIMIT')
    if schedule['beneficiary_id'] != gap['cashflow_viewpoint']['beneficiary_id']:
        raise NotBound('BENEFICIARY_OUTSIDE_MODEL')
    horizon = _integer(schedule.get('horizon_days', bounds['horizon_days_default']),
                       bounds['horizon_days_min'], bounds['horizon_days_max'], 'HORIZON_OUT_OF_BOUNDS')
    for source in sources:
        _reference(source['reference'])
        _label(source['basis'])
        _amount(source['budget_krw'], bounds)
        delay = _integer(source['delay_days'], gap['due_day_ordering']['delay_days_min'],
                         bounds['sim_day_max'], 'DELAY_OUT_OF_BOUNDS')
        for row in source['releases']:
            _shape(row, ('release_id', 'base_available_sim_day', 'amount_krw'), ('release_offset_krw',))
            _label(row['release_id'])
            _amount(row['amount_krw'], bounds)
            if 'release_offset_krw' in row:
                _amount(row['release_offset_krw'], bounds)
            _day(_day(row['base_available_sim_day'], bounds) + delay, bounds)
    if 'opening_cash' in schedule:
        _validate_opening(schedule['opening_cash'], bounds)
    return selected, horizon, raw_rows


class Capture:
    """Indexed detached facts for exactly one workspace envelope and snapshot."""

    def __init__(self, service, workspace_id):
        with service.lock:
            frozen = portfolio_snapshot.FrozenInputs.capture(
                service.producer.snapshot_inputs(), service.receipts, service.case_fixtures,
                service.overlay_entries, service.terms, service.overlay_bounds)
            self.snapshot = service.portfolio_snapshot(service.instance_id)
            # The restored service has no writer. Its loaded terms port is local
            # to this invocation, with the same inputs as the frozen capture.
            self.terms = service.terms
        self.workspace_id = workspace_id
        data = frozen.detached()
        state = strict_json.loads(data['producer']['canonical_state'].encode())
        self.journal = state['journal']
        self.cases = {row['advance_id']: row for row in state['cases']}
        self.mapping = data['case_fixtures']
        self.fixtures = data['producer']['fixtures']
        self.receipts = data['receipts']
        self.entries = data['overlay_entries']
        self.state = overlay.fold(self.entries, len(self.journal))
        self.used_sources = {key for ledger in ('claim_slices', 'recovery')
                             for key, amount in self.state.get(ledger, {}).get('sources', {}).items() if amount}
        self.cut = self.state['sim_day']
        self.draws = {row['advance_id']: (index, row['idempotency_key'])
                      for index, row in enumerate(self.journal) if row['op'] == 'draw'}
        self.repayments = defaultdict(list)
        for index, row in enumerate(self.journal):
            if row['op'] == 'repay':
                day = overlay.draw_day_for(self.entries, index)
                self.repayments[row['advance_id']].append((day, row['body']['amount']))
        self.accruals = defaultdict(list)
        for entry in {row['overlay_id']: row for row in self.entries}.values():
            if entry['kind'] == overlay.KIND_INTEREST:
                payload = entry['payload']
                self.accruals[payload['advance_id']].append(payload)
        self.forecasts = {row['advance_id']: row for row in
                          (self.snapshot['forecast'] or {}).get('advances', [])}
        self.advances_by_claim = defaultdict(list)
        for ref, case in self.cases.items():
            self.advances_by_claim[case['claim_id']].append(ref)
        self.fixture_ids_by_claim = defaultdict(list)
        for fixture_id, view in self.fixtures['rows'].items():
            if view.get('claim'):
                self.fixture_ids_by_claim[view['claim']['claim_id']].append(fixture_id)

    def fixture(self, fixture_id, beneficiary):
        view = self.fixtures['rows'].get(fixture_id, {})
        claim = view.get('claim')
        if (not claim or self.fixtures['beneficiaries'].get(fixture_id) != beneficiary
                or view.get('settlement_id') != fixture_id
                or view.get('currency') != 'KRW' or claim.get('currency') != 'KRW'):
            raise NotBound('FIXTURE_BENEFICIARY_CLAIM_OR_CURRENCY_UNVERIFIED')
        return view, claim

    def advance_fixture(self, ref, beneficiary):
        case = self.cases.get(ref)
        fixture_id = self.mapping.get(ref)
        if not case or case.get('beneficiary_role') != beneficiary or not fixture_id:
            raise NotBound('ADVANCE_BENEFICIARY_OR_FIXTURE_UNVERIFIED')
        view, claim = self.fixture(fixture_id, beneficiary)
        if (case.get('claim_id') != claim['claim_id'] or case.get('currency') != claim['currency']
                or (ref in self.draws and case.get('settlement_id') != view['settlement_id'])):
            raise NotBound('ADVANCE_CLAIM_OR_CURRENCY_MISMATCH')
        return view, claim

    def entitlement(self, ref, beneficiary, settlement):
        kind, name = ref['kind'], ref['id']
        if kind == 'ADVANCE':
            view, claim = self.advance_fixture(name, beneficiary)
        elif kind == 'CLAIM':
            aliases = self.fixture_ids_by_claim.get(name, [])
            if len(aliases) != 1:
                raise NotBound('CLAIM_ALIAS_UNRESOLVED')
            view, claim = self.fixture(aliases[0], beneficiary)
        else:
            view, claim = self.fixture(name, beneficiary)
        if self.fixture_ids_by_claim.get(claim['claim_id']) != [view['settlement_id']]:
            raise NotBound('CLAIM_ALIAS_UNRESOLVED')
        classes = settlement.payee_classes(claim.get('policy'))
        mapping = self.terms._value('additional_margin')['beneficiary_payee_map']
        payees = mapping.get(beneficiary, [])
        if (len(payees) != 1 or classes['outcome'] != 'DECIDED'
                or classes['classes'].get(payees[0], {}).get('id') != 'COUNTERPARTY_PROCEEDS'):
            raise NotBound('BENEFICIARY_PAYEE_CLASS_UNRESOLVED')
        key = (self.workspace_id, beneficiary, claim['claim_id'], payees[0], claim['currency'])
        return key, view, claim, classes['classes']

    def restriction(self, ref, end):
        state = self.state
        if (self.cases[ref]['phase'] == 'DEFAULTED' or recovery.anchor(state, ref) is not None
                or ref in state.get('recovery', {}).get('advances', {})):
            return 'DEFAULT_RECOVERY_OR_WRITEOFF'
        margin_row = state.get('margin', {}).get('advances', {}).get(ref, {})
        if ref in state.get('accelerations', {}) or margin_row.get('status') == 'ACCELERATED':
            return 'ACCELERATED_OBLIGATION'
        if (margin_row.get('status') == 'CALLED' and margin_row['cure_deadline'] < end
                and self.cases[ref]['outstanding_exposure'] > 0):
            return 'ACCELERATION_WITHIN_HORIZON'
        return None

    def claim_restriction(self, claim_id):
        if any(row['claim_id'] == claim_id and row['status'] not in ('PROPOSED', 'VOID')
               for row in slices.registry(self.state).values()):
            return 'SLICE_ENCUMBRANCE_OR_PRIOR_USE'
        if any(recovery.source_key(claim_id, label) in self.used_sources
               for label in self._claim_payees(claim_id)):
            return 'PRIOR_SETTLEMENT_SOURCE_USE'
        return None

    def _claim_payees(self, claim_id):
        return [line['payee'] for fixture_id in self.fixture_ids_by_claim[claim_id]
                for line in self.fixtures['rows'][fixture_id]['claim']['obligations']]


def _clean_claim(view, claim):
    """Reject residual states whose refund, hold or recovery burden is unresolved."""
    if (claim.get('refund_bearer_policy') != 'NONE'
            or any(claim.get(key) != 0 for key in
                   ('refund_face', 'refund_accepted', 'refund_outstanding',
                    'pg_adjustment_outstanding', 'recovery_due'))
            or any(claim.get(key) is not False for key in
                   ('distribution_blocked', 'fixture_reclassified', 'right_cancelled', 'external_return_closed'))
            or view.get('cancel_reason') is not None
            or any(row.get('dispute') or row.get('disputed') for row in (view, claim))):
        raise NotBound('REFUND_DISPUTE_OR_RESTRICTED_RESIDUAL')


def _repayment_position(state, ref, denominator):
    try:
        return overlay.repayment_position(state, ref, denominator)
    except (overlay.OverlayError, ArithmeticError) as exc:
        raise NotBound('ACCRUAL_OR_REPAYMENT_POSITION_UNVERIFIED') from exc


def _settlement_evidence(capture, entitlement, selected, end, residual, settlement, bounds):
    key, view, claim, classes = entitlement
    claim_id, payee = key[2:4]
    _clean_claim(view, claim)
    if view.get('phase') != 'COMMITTED' or claim.get('receivable_open') != 0:
        raise NotBound('SETTLEMENT_CASH_UNCONFIRMED')
    # Only the adopted clean continuation case is supported. This also fences
    # any future nonzero holdback policy until it can be applied explicitly.
    if (residual.get('holdback_reserve', {}).get('v1_bps') != 0
            or not any(row.get('id') == 'UC1_FROZEN_ORDER_CONTINUATION'
                       for row in residual.get('undistributed_cash_states_ordered', []))):
        raise NotBound('RESIDUAL_POLICY_UNSUPPORTED')
    reason = capture.claim_restriction(claim_id)
    if reason:
        raise NotBound(reason)
    for ref in capture.advances_by_claim[claim_id]:
        capture.advance_fixture(ref, key[1])
        case = capture.cases[ref]
        if capture.restriction(ref, end):
            raise NotBound('CLAIM_COMMITTED_TO_RESTRICTED_ADVANCE')
        if ref not in selected:
            _, unpaid_default, unpaid_interest, held = _repayment_position(
                capture.state, ref, capture.terms.ledger_denominator())
            if (case['note_status'] == 'NOTED' or
                    any((case['outstanding_exposure'], unpaid_default, unpaid_interest, held))):
                raise NotBound('UNSELECTED_ADVANCE_COMMITMENT')

    try:
        cash = {name: _amount(claim[name], bounds) for name in
                ('gross', 'confirmed_cash', 'non_cash_accounted', 'distributed_cash', 'undistributed_cash')}
        lines = {line['payee']: {name: _amount(line[name], bounds) for name in
                                ('face', 'outstanding', 'distributed', 'cancelled_unpaid', 'recovery_due')}
                 for line in claim['obligations']}
    except (InvalidInput, KeyError, TypeError) as exc:
        raise NotBound('SETTLEMENT_AMOUNTS_UNVERIFIED') from exc
    if (len(lines) != len(claim['obligations']) or lines.keys() != classes.keys()
            or any(line['face'] != line['outstanding'] + line['distributed'] + line['cancelled_unpaid']
                   or line['cancelled_unpaid'] or line['recovery_due'] for line in lines.values())
            or cash['gross'] != sum(line['face'] for line in lines.values())
            or cash['gross'] != cash['confirmed_cash'] + cash['non_cash_accounted']
            or cash['confirmed_cash'] != cash['distributed_cash'] + cash['undistributed_cash']
            or cash['distributed_cash'] != sum(line['distributed'] for line in lines.values())):
        raise NotBound('SETTLEMENT_CONSERVATION_UNVERIFIED')
    order = settlement.allocation(claim['policy'])['order']
    frozen_order = claim.get('distribution_order')
    if ((frozen_order is not None and frozen_order != order)
            or (cash['distributed_cash'] and frozen_order is None)):
        raise NotBound('RECORDED_ALLOCATION_ORDER_UNVERIFIED')
    allocated, residual_cash = shadow.fill_sequential(
        cash['undistributed_cash'], [(label, lines[label]['outstanding']) for label in order])
    if residual_cash:
        raise NotBound('UNALLOCATED_SETTLEMENT_CASH')
    allocation = dict(allocated)
    return {
        'fixture_id': view['settlement_id'], 'claim_cash_krw': cash,
        'payee_lines_krw': lines, 'payee_classes': classes, 'allocation_order': order,
        'prospective_allocation_krw': allocation, 'remaining_entitlement_krw': allocation[payee],
        'recorded_distribution_krw': lines[payee]['distributed'],
        'application': 'SHADOW_NOT_APPLIED',
    }


def _not_bound(report, row, reason):
    row.update(status='NOT_BOUND', reason=reason)
    report['issues'].append({key: row[key] for key in (
        'reference', 'source_key', 'advance_id', 'obligation_id', 'lot_id', 'reason') if key in row})


def _verify_release_portions(rows, budget):
    portions = []
    for row in rows:
        start = row.get('release_offset_krw')
        if start is None:
            continue
        stop = start + row['amount_krw']
        if stop > budget:
            raise InvalidInput('RELEASE_PORTION_EXCEEDS_SOURCE_BUDGET')
        if stop > start:
            portions.append((start, stop))
    portions.sort()
    if any(left[1] > right[0] for left, right in zip(portions, portions[1:])):
        raise NotBound('OVERLAPPING_RELEASE_PORTIONS')
    positive_releases = sum(row['amount_krw'] > 0 for row in rows)
    if positive_releases > 1 and len(portions) != positive_releases:
        raise NotBound('RELEASE_PORTION_UNVERIFIED')


class SettlementSources:
    def __init__(self, capture, schedule, selected, end, settlement, residual, bounds, source_policy):
        self.capture = capture
        self.beneficiary = schedule['beneficiary_id']
        self.selected = set(selected)
        self.end = end
        self.settlement = settlement
        self.residual = residual
        self.bounds = bounds
        self.key_fields = source_policy['source_key']
        self.evidence = {}

    def resolve(self, reference):
        return self.capture.entitlement(reference, self.beneficiary, self.settlement)

    def describe_key(self, key):
        return dict(zip(self.key_fields, key))

    def verified(self, entitlement):
        key = entitlement[0]
        if key not in self.evidence:
            self.evidence[key] = _settlement_evidence(
                self.capture, entitlement, self.selected, self.end, self.residual, self.settlement, self.bounds)
        return self.evidence[key]

    def collect(self, schedule, report):
        groups = {}
        for spec in schedule['sources']:
            reference = spec['reference']
            try:
                entitlement = self.resolve(reference)
            except NotBound as exc:
                row = {'reference': reference, 'basis': spec['basis']}
                _not_bound(report, row, str(exc))
                report['sources'].append(row)
                continue
            key = entitlement[0]
            identity = {field: spec[field] for field in ('basis', 'budget_krw', 'delay_days')}
            group = groups.setdefault(key, (identity, set(), {}, entitlement))
            terms, refs, releases, _ = group
            if terms != identity:
                raise InvalidInput('CONFLICTING_SOURCE_BUDGET_DELAY_OR_BASIS')
            refs.add((reference['kind'], reference['id']))
            for release in spec['releases']:
                release_id = release['release_id']
                row = {**release, 'available_sim_day': release['base_available_sim_day'] + terms['delay_days']}
                if releases.setdefault(release_id, row) != row:
                    raise InvalidInput('CONFLICTING_RELEASE')
        _integer(len(groups), self.bounds['sources_min'], self.bounds['sources_max'], 'UNIQUE_SOURCE_LIMIT')
        for key, (terms, refs, releases, entitlement) in sorted(groups.items()):
            rows = sorted(releases.values(), key=lambda row: (row['available_sim_day'], row['release_id']))
            scheduled = sum(row['amount_krw'] for row in rows)
            budget = terms['budget_krw']
            if scheduled > budget:
                raise InvalidInput('RELEASES_EXCEED_SOURCE_BUDGET')
            row = {'source_key': self.describe_key(key), **terms,
                   'references': [{'kind': kind, 'id': ref} for kind, ref in sorted(refs)],
                   'releases': rows, 'status': 'BOUND'}
            try:
                _verify_release_portions(rows, budget)
                if terms['basis'] != 'PROSPECTIVE_PRE_SETOFF_ALLOCATION':
                    raise NotBound('PRE_SETOFF_ALLOCATION_UNVERIFIED')
                evidence = self.verified(entitlement)
            except NotBound as exc:
                _not_bound(report, row, str(exc))
            else:
                if budget > evidence['remaining_entitlement_krw']:
                    raise InvalidInput('SOURCE_BUDGET_EXCEEDS_ENTITLEMENT')
                row.update(evidence=evidence, unscheduled_budget_krw=budget - scheduled)
            report['sources'].append(row)

    def opening_cash(self, spec, default, report):
        if spec is None:
            return {'origin': 'DEFAULT_ZERO', 'as_of_sim_day': self.capture.cut, 'total_krw': default, 'lots': []}
        if spec['as_of_sim_day'] != self.capture.cut:
            raise InvalidInput('OPENING_CASH_CUT_MISMATCH')
        lots, ids, intervals = [], set(), defaultdict(list)
        independent = False
        for value in sorted(spec['lots'], key=lambda lot: lot['lot_id']):
            lot = {**value, 'status': 'BOUND'}
            lots.append(lot)
            if lot['lot_id'] in ids:
                raise InvalidInput('DUPLICATE_OPENING_LOT_ID')
            ids.add(lot['lot_id'])
            if lot['kind'] == 'INDEPENDENT_SYNTHETIC_ENDOWMENT':
                if independent:
                    _not_bound(report, lot, 'INDEPENDENT_ENDOWMENT_OVERLAP_UNVERIFIED')
                independent = True
                continue
            try:
                entitlement = self.resolve(lot['reference'])
                key = entitlement[0]
                lot['source_key'] = self.describe_key(key)
                evidence = self.verified(entitlement)
                offset = lot['received_offset_krw']
                stop = offset + lot['amount_krw']
                if stop > evidence['recorded_distribution_krw']:
                    raise NotBound('OPENING_RECEIPT_PORTION_UNVERIFIED')
                if stop > offset:
                    intervals[key].append((offset, stop, lot['lot_id'], lot))
                lot['recorded_distribution_krw'] = evidence['recorded_distribution_krw']
            except NotBound as exc:
                _not_bound(report, lot, str(exc))
        for portions in intervals.values():
            previous_end = 0
            for start, stop, _, lot in sorted(portions):
                if start < previous_end:
                    _not_bound(report, lot, 'OVERLAPPING_OPENING_RECEIPT_PORTIONS')
                previous_end = max(previous_end, stop)
        return {**spec, 'lots': lots}


def _verify_recorded_accrual(capture, ref, terms, draw_day):
    accrued_through = draw_day
    principal = capture.cases[ref]['drawn_exposure']
    repayments = iter(capture.repayments[ref])
    repayment = next(repayments, None)
    verified = {'advances': {}}
    posted_contract = posted_default = 0
    # An ordinary clock posting has no recovery write-off stop.
    subject = {'advance_id': ref, 'draw_day': draw_day, 'terms': {**terms, 'writeoff_day': None}}
    for posting in capture.accruals[ref]:
        if any(posting[k] != terms[k] for k in ('maturity_day', 'tier', 'contract_bps', 'default_bps')):
            raise NotBound('RECORDED_INTEREST_TERMS_OR_MATURITY_MISMATCH')
        if posting['draw_day'] != draw_day or posting['from_day'] != accrued_through:
            raise NotBound('RECORDED_ACCRUAL_INCOMPLETE')
        # A repayment at the start changes this span's principal. A repayment
        # at its end changes the next span, after this day's clock posting.
        while repayment is not None and repayment[0] <= accrued_through:
            principal -= repayment[1]
            repayment = next(repayments, None)
        end = posting['to_day']
        if repayment is not None and repayment[0] < end:
            raise NotBound('RECORDED_ACCRUAL_SPANS_PRINCIPAL_CHANGE')
        expected = overlay.accrual_postings(verified, end, [{**subject, 'principal': principal}])
        if not expected or posting != expected[0]:
            raise NotBound('RECORDED_ACCRUAL_CALCULATION_MISMATCH')
        posted_contract += posting['posted_contract_krw']
        posted_default += posting['posted_default_krw']
        verified['advances'][ref] = {
            'last_accrued_day': end,
            'cumulative_contract_exact': posting['cumulative_contract_exact'],
            'cumulative_default_exact': posting['cumulative_default_exact'],
            'posted_contract_krw': posted_contract,
            'posted_default_krw': posted_default,
        }
        accrued_through = end
    return accrued_through


def _obligation_amounts(capture, ref, beneficiary, end):
    case = capture.cases.get(ref, {})
    if ref not in capture.draws or not case:
        raise NotBound('DRAW_NOT_RECORDED')
    reason = capture.restriction(ref, end)
    if reason:
        raise NotBound(reason)
    if case['phase'] not in ('DRAWN', 'CLOSED'):
        raise NotBound('UNSUPPORTED_ADVANCE_STATE')
    view, claim = capture.advance_fixture(ref, beneficiary)
    _clean_claim(view, claim)
    reason = capture.claim_restriction(claim['claim_id'])
    if reason:
        raise NotBound(reason)
    binding = capture.state['terms_binding']
    if (binding is None or binding['status'] not in ('BOUND', 'PARTIAL')
            or binding['terms_version'] != capture.terms.version):
        raise NotBound('RECORDED_TERMS_BINDING_MISSING_OR_INCOMPATIBLE')
    index, receipt_id = capture.draws[ref]
    receipt = capture.receipts.get(receipt_id, {}).get('receipt', {})
    credit = (receipt.get('result') or {}).get('credit', {})
    if (receipt.get('outcome') != 'ACCEPTED' or credit.get('advance_id') != ref
            or any(credit.get(key) != case[key] for key in (
                'beneficiary_role', 'claim_id', 'currency', 'settlement_id', 'draw_id', 'settlement_gate'))
            or not credit.get('settlement_gate')):
        raise NotBound('ACCEPTED_DRAW_RECEIPT_GATE_UNVERIFIED')
    draw_day = overlay.draw_day_for(capture.entries, index)
    terms = capture.terms.ledger_terms(case, claim, gate=credit['settlement_gate'], draw_day=draw_day,
                                      expected_settlement_cash_day=None)
    if terms is None:
        raise NotBound('CONTRACTUAL_TERMS_NOT_BOUND')
    maturity = terms['maturity_day']
    principal = case['outstanding_exposure']
    if principal:
        row = capture.forecasts.get(ref, {})
        if (row.get('status') != 'BOUND' or row['principal_krw'] != principal
                or row['maturity_day'] != maturity or row['draw_day'] != draw_day
                or row['tier'] != terms['tier']):
            raise NotBound('FORECAST_PRINCIPAL_OR_MATURITY_UNVERIFIED')
        principal, maturity = row['principal_krw'], row['maturity_day']
    state = capture.state
    accrued_through = _verify_recorded_accrual(capture, ref, terms, draw_day)
    through = capture.cut
    if not principal:
        repayments = capture.repayments[ref]
        if not repayments:
            raise NotBound('PRINCIPAL_RETIREMENT_UNVERIFIED')
        through = repayments[-1][0]
    if accrued_through < through:
        raise NotBound('RECORDED_ACCRUAL_INCOMPLETE')
    _, default_due, interest_due, held = _repayment_position(state, ref, terms['denominator'])
    if held:
        raise NotBound('UNAPPLIED_REPAYMENT_CASH_HELD')
    if default_due or interest_due < 0:
        raise NotBound('DEFAULT_INTEREST_OR_REPAYMENT_EVIDENCE_UNSUPPORTED')
    if principal:
        rows = overlay.accrual_postings(state, maturity, [
            {'advance_id': ref, 'principal': principal, 'draw_day': draw_day, 'terms': terms}])
        if rows:
            # Read the contractual floor increment from the pure accrual preview.
            # The folded position already subtracts recorded paid interest.
            interest_due += rows[0]['posted_contract_krw']
    elif interest_due and not capture.accruals[ref]:
        raise NotBound('RESIDUAL_INTEREST_MATURITY_UNVERIFIED')
    return maturity, principal, interest_due


def _obligations(capture, selected, beneficiary, end, bounds, report):
    for ref in selected:
        rows = [{'advance_id': ref, 'obligation_id': kind, 'status': 'BOUND'} for kind in DUE_KINDS]
        report['obligations'].extend(rows)
        try:
            maturity, *amounts = _obligation_amounts(capture, ref, beneficiary, end)
        except NotBound as exc:
            for row in rows:
                _not_bound(report, row, str(exc))
            continue
        _day(maturity, bounds)
        for row, amount in zip(rows, amounts):
            row.update(due_sim_day=maturity, amount_krw=_amount(amount, bounds))
            if amount and maturity <= capture.cut:
                _not_bound(report, row, 'UNPAID_OBLIGATION_ON_OR_BEFORE_CUT')


def _outside(rows, end):
    late = [(day, amount) for day, amount in rows if day > end]
    return {'count': len(late), 'amount_krw': sum(amount for _, amount in late),
            'first_sim_day': min((day for day, _ in late), default=None)}


def _chronology(cut, end, opening, sources, dues):
    releases = [(row['available_sim_day'], row['amount_krw']) for source in sources for row in source['releases']]
    obligations = [(row['due_sim_day'], row['amount_krw']) for row in dues if row['amount_krw']]
    inflow_by_day, due_by_day = defaultdict(int), defaultdict(int)
    for day, amount in releases:
        inflow_by_day[day] += amount
    for day, amount in obligations:
        due_by_day[day] += amount
    daily, net = [], opening
    for day in range(cut + 1, end + 1):
        carry, backlog = max(net, 0), max(-net, 0)
        inflows, new_dues = inflow_by_day[day], due_by_day[day]
        resources_krw = carry + inflows
        covered = min(resources_krw, backlog + new_dues)
        net += inflows - new_dues
        daily.append({
            'sim_day': day, 'opening_carry_krw': carry, 'opening_shortage_krw': backlog,
            'source_inflows_krw': inflows, 'resources_krw': resources_krw, 'new_dues_krw': new_dues,
            'covered_krw': covered, 'net_krw': net, 'closing_carry_krw': max(net, 0),
            'shortage_krw': max(-net, 0),
        })
    first = next((row for row in daily if row['shortage_krw']), None)
    metrics = {
        'first_shortage_sim_day': first['sim_day'] if first else None,
        'first_shortage_krw': first['shortage_krw'] if first else 0,
        'peak_shortage_krw': max(row['shortage_krw'] for row in daily),
        'terminal_shortage_krw': daily[-1]['shortage_krw'],
    }
    outside = {'releases': _outside(releases, end), 'obligations': _outside(obligations, end)}
    return daily, metrics, outside


def _report():
    return {
        'format': FORMAT, 'status': 'UNEVALUATED', 'label': 'SIMULATED',
        'source_label': 'READ_ONLY_FIXTURE', 'mode': 'HYPOTHETICAL_FUNDING_GAP',
        'provisional': True, 'non_posting': True, 'funds_executed': False,
        'production': 'NOT_AUTHORIZED', 'scenario_id': None, 'beneficiary_id': None,
        'workspace_id': None, 'snapshot_digest': None, 'cut': None, 'schedule_sha256': None,
        'audit': None, 'policies': {}, 'policy_digest': None, 'issues': [],
        'assumptions': None, 'opening_cash_origin': None, 'opening_cash': None, 'sources': [], 'obligations': [],
        'daily': None, 'metrics': None, 'outside_horizon': None,
    }


def report_workspace(directory, schedule_path):
    """Produce a JSON-compatible report without opening a writable workspace."""
    report = _report()
    try:
        schedule_raw = _read_regular(schedule_path, SCHEDULE_MAX_BYTES)
        report['schedule_sha256'] = _sha(schedule_raw)
        schedule = strict_json.loads(schedule_raw)
    except (OSError, ValueError, RecursionError) as exc:
        report['status'] = 'INVALID_INPUT'
        report['issues'].append({'reason': str(exc) if isinstance(exc, InvalidInput) else 'SCHEDULE_UNREADABLE'})
        return report
    try:
        raw = _read_regular(Path(directory) / FILE_NAME)
        report['workspace_id'] = 'sha256:' + _sha(raw)
    except OSError:
        raw = None
    result = audit.audit_workspace_bytes(raw, workspace='CAPTURE')
    report['audit'] = {key: result[key] for key in ('ok', 'reason', 'failed_check', 'checks')}
    if not result['ok']:
        report['issues'].append({'reason': result['reason'], 'status': 'NOT_BOUND'})
        return report
    capture = Capture(offline_service(strict_json.loads(raw)), report['workspace_id'])
    snapshot = capture.snapshot
    report.update(snapshot_digest=snapshot['snapshot_digest'], cut=snapshot['cut'])
    marks = report['policies']
    marks['CAPITAL_FINANCIAL_TERMS.md'] = capture.terms.status()
    try:
        gap, settlement, residual = _policies(marks)
        selected, horizon, raw_rows = _validate_schedule(schedule, gap)
        report.update(scenario_id=schedule['scenario_id'], beneficiary_id=schedule['beneficiary_id'])
        if not snapshot['complete']:
            report['issues'].extend({'reason': reason, 'status': 'NOT_BOUND'}
                                    for reason in snapshot['completeness']['reasons'])
            return report
        pins = [key for key in ('workspace_id', 'snapshot_digest') if schedule[key] != report[key]]
        if pins:
            report['issues'].extend({'reason': 'CAPTURE_PIN_MISMATCH', 'pin': pin} for pin in pins)
            raise InvalidInput()
        bounds = gap['horizon_and_input_bounds']
        end = _day(_day(capture.cut, bounds) + horizon, bounds)
        if any(row['base_available_sim_day'] + source['delay_days'] <= capture.cut
               for source in schedule['sources'] for row in source['releases']):
            raise InvalidInput('RELEASE_ON_OR_BEFORE_CUT')
        report['assumptions'] = {
            'as_of_sim_day': capture.cut, 'start_sim_day': capture.cut + 1,
            'end_sim_day': end, 'horizon_days': horizon, 'raw_event_rows': raw_rows,
            'selected_advance_ids': selected, 'currency': gap['source_identity_and_budget']['currency'],
            'same_day_order': gap['due_day_ordering']['same_day_order'],
            'snapshot_cut': gap['due_day_ordering']['snapshot_cut'],
            'scope': gap['cashflow_viewpoint']['scope'],
            'source_basis': gap['cashflow_viewpoint']['source_basis'],
            'forecast_digest': snapshot['forecast']['forecast_digest'],
        }
        sources = SettlementSources(capture, schedule, selected, end, settlement, residual, bounds,
                                    gap['source_identity_and_budget'])
        sources.collect(schedule, report)
        opening = sources.opening_cash(schedule.get('opening_cash'), gap['opening_cash_assumption']['default_krw'], report)
        report.update(opening_cash=opening, opening_cash_origin=opening['origin'])
        _obligations(capture, selected, schedule['beneficiary_id'], end, bounds, report)
        if not report['issues']:
            daily, metrics, outside = _chronology(
                capture.cut, end, opening['total_krw'], report['sources'], report['obligations'])
            report.update(status=gap['unsupported_case_policy']['supported_status'],
                          daily=daily, metrics=metrics, outside_horizon=outside)
    except InvalidInput as exc:
        report['status'] = 'INVALID_INPUT'
        if str(exc):
            report['issues'].append({'reason': str(exc)})
    except NotBound as exc:
        report['issues'].append({'reason': str(exc), 'status': 'NOT_BOUND'})
    finally:
        report['policy_digest'] = portfolio_snapshot.digest(marks)
    return report
