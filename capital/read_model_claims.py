"""Executable CLAIM_CONFORMANCE checks for the read-model credit and settlement queries.

Each row in tests/read_model_claims.json cites the pinned
READ_MODEL_QUERIES.md draft 0.1 (kix-protocol main
244595db1524cbb1a01148baa07d6d28cd1b8dc6), names one check, and stores the
value that check must observe. Checks run over the in-process loopback
facade (CapitalService.read_query). The comparison is local and simulated.
It is a consumer rehearsal of the draft, not a read model, not a
ReadObservationV1, and it does not move funds.

A protocol checkout is optional. The drift check reads the working tree of
that checkout, not the pinned commit, and does not write it. Besides the
shared heading and needle test, it scopes each needle to its own section and
re-derives the key lists of sections 2.11 to 2.13, so a key added to or
dropped from the draft fails the row that pins it. With no checkout the
CLI reports SKIPPED without running rows (except explicit --execute).
The original mapped read-surface checks remain under their per-read overlay
non-mutation guard beside the point-query checks.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from capital import overlay, upstream_claims
from capital.protocol import CreditError
from capital.resources import ROOT
from capital.upstream_claims import ClaimTableError

PINNED_SHA = '244595db1524cbb1a01148baa07d6d28cd1b8dc6'
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_READ_MODEL_CLAIMS_V1'
REQUIRED_FIELDS = upstream_claims.REQUIRED_FIELDS + ('route',)
ROUTES = ('GET /api/state', 'CreditMachine.view', 'CreditMachine.view_claim',
          'GET /api/read/credit_advance/{id}', 'GET /api/read/credit_claim/{id}',
          'GET /api/read/settlement/{id}', 'CapitalService.read_query')
SECTION_ADVANCE = '### 2.12 `get_credit_advance`'
SECTION_CLAIM = '### 2.13 `get_credit_claim`'
SECTION_NONMUTATION = '## 8. 비변경'
ADVANCE_ID = 'sim-read'
CLAIM_ID = 'sim-committed'
AMOUNT = 60_000
OPERATIONS = (('offer', {'fixture_id': CLAIM_ID, 'amount': AMOUNT}),
              ('approve', {}), ('bind_settlement', {}), ('draw', {}))
SOURCE_DOC = 'docs/contracts/READ_MODEL_QUERIES.md'
KEYSET_SECTIONS = {
    'settlement': '### 2.11 `get_settlement`',
    'credit_advance': '### 2.12 `get_credit_advance`',
    'credit_claim': '### 2.13 `get_credit_claim`',
}
ENVELOPE_SECTION = '## 3. 공통 봉투 (제안)'
RESERVED = (
    'source_cut', 'projection_watermark', 'snapshot_digest', 'observed_receipt_refs',
    'producer_manifest_digest', 'subject_scope', 'profile_revision',
)
ERROR_CODES = ['INVALID_ID', 'UNKNOWN_ADVANCE', 'UNKNOWN_CLAIM', 'UNKNOWN_SETTLEMENT']
QUERY = {
    'credit_advance': 'get_credit_advance',
    'credit_claim': 'get_credit_claim',
    'settlement': 'get_settlement',
}
DRAWN_ADVANCE = 'sim-rm-drawn'
OFFERED_ADVANCE = 'sim-rm-offered'
FIXTURE = 'sim-committed'
_CACHE = upstream_claims._CACHE


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'read_model_claims.json'


def load_table(path=None):
    return validate_table(upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA))


def validate_table(data):
    upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    for claim in data['claims']:
        if type(claim.get('route')) is not str or claim['route'] not in ROUTES:
            raise ClaimTableError(f'claim {claim["id"]} route is not a mapped read route')
    return data


def run_claims(table):
    """Run every check. An unmapped check fails that claim and no other."""
    validate_table(table)
    return upstream_claims.run_claims(
        table, checks=CHECKS, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


# --- drift -----------------------------------------------------------------

_KEY = re.compile(r'`([a-z][a-z0-9_]*)`')


def section_text(text, heading):
    """The lines under `heading`, up to the next heading of the same or a higher level."""
    level = len(heading) - len(heading.lstrip('#'))
    lines = text.splitlines()
    found = [index for index, line in enumerate(lines) if line.strip() == heading]
    if len(found) != 1:
        return None
    body = []
    for line in lines[found[0] + 1:]:
        hashes = len(line) - len(line.lstrip('#'))
        if line.startswith('#') and 0 < hashes <= level and line[hashes:hashes + 1] == ' ':
            break
        body.append(line)
    return '\n'.join(body)


def _exposed(section):
    """(lead line, key line) of the 노출 상태 bullet. None when the draft changed shape."""
    lead = key = None
    for line in section.splitlines():
        if line.startswith('- **노출 상태.**'):
            lead = line
        elif lead is not None and key is None and line.strip().startswith('키:'):
            key = line.strip()
        elif key is not None and line.startswith('- **'):
            break
    if lead is None or key is None:
        return None
    return lead, key


def draft_flags(text):
    """The always-false `_flags` listed in section 2.12, after the `mock_credit._flags` mention."""
    section = section_text(text, KEYSET_SECTIONS['credit_advance'])
    parts = _exposed(section) if section is not None else None
    if parts is None or 'mock_credit._flags' not in parts[1]:
        return None
    return _KEY.findall(parts[1].split('mock_credit._flags', 1)[1])


def draft_keys(text, kind):
    """Sorted key list the draft gives for one query, or None when it cannot be read."""
    section = section_text(text, KEYSET_SECTIONS[kind])
    parts = _exposed(section) if section is not None else None
    if parts is None:
        return None
    lead, key = parts
    if kind == 'credit_claim':
        flags = draft_flags(text)
        if flags is None:
            return None
        return sorted(set(_KEY.findall(key)) | set(flags))
    return sorted(set(_KEY.findall(lead)) | set(_KEY.findall(key)))


def check_protocol(protocol_dir, table=None):
    """Read cited headings and needles inside their own section. Never writes the checkout."""
    if table is None:
        table = load_table()
    validate_table(table)
    report = upstream_claims.check_protocol(
        protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    if report['status'] != 'verified':
        return report
    root = Path(protocol_dir)
    texts = {}
    missing = []
    for claim in table['claims']:
        rel = claim['source_doc']
        if rel not in texts:
            texts[rel] = upstream_claims._read_only((root / rel).resolve())
        text = texts[rel]
        section = section_text(text, claim['section'])
        if section is None:
            missing.append({'id': claim['id'], 'problem': 'missing section', 'section': claim['section']})
        elif claim['needle'] not in section:
            missing.append({'id': claim['id'], 'problem': 'missing needle', 'needle': claim['needle']})
        elif claim['check_id'].startswith('keyset.'):
            kind = claim['check_id'][len('keyset.'):]
            if kind not in KEYSET_SECTIONS or claim['section'] != KEYSET_SECTIONS[kind]:
                missing.append({'id': claim['id'], 'problem': 'keyset row cites the wrong section'})
            elif draft_keys(text, kind) != claim['expected']:
                missing.append({'id': claim['id'], 'problem': 'key list differs from the draft'})
    total = len(table['claims'])
    return {
        'status': 'verified' if not missing else 'failed',
        'label': LABEL,
        'verified': total - len({item['id'] for item in missing}),
        'total': total,
        'missing': missing,
    }


# --- checks ----------------------------------------------------------------

def _op(service, op, advance, args=None):
    # The operation id only allows letters, digits and hyphens.
    body = {
        'instance_id': service.instance_id,
        'operation_id': f'op-{advance}-{op.replace("_", "")}',
        'op': op, 'advance_id': advance, 'args': {} if args is None else args,
    }
    return service.execute(body)


def _service():
    from capital.service import CapitalService
    return CapitalService()


def _book():
    """One drawn advance, one offered advance, on the committed settlement fixture."""
    if 'rm_book' not in _CACHE:
        service = _service()
        _op(service, 'offer', DRAWN_ADVANCE, {'fixture_id': FIXTURE, 'amount': 1000})
        _op(service, 'approve', DRAWN_ADVANCE)
        _op(service, 'bind_settlement', DRAWN_ADVANCE)
        _op(service, 'draw', DRAWN_ADVANCE)
        _op(service, 'offer', OFFERED_ADVANCE, {'fixture_id': FIXTURE, 'amount': 2000})
        _CACHE['rm_book'] = service
    return _CACHE['rm_book']


def _target(kind, pending=False):
    if kind == 'credit_advance':
        return DRAWN_ADVANCE
    if kind == 'settlement':
        return 'sim-pending' if pending else FIXTURE
    return FIXTURE  # the claim id the draw noted


def _read(kind, ident=None, pending=False):
    return _book().read_query(kind, _target(kind, pending) if ident is None else ident)


def _error(kind, ident, service=None):
    from capital.service import ApiError
    service = _book() if service is None else service
    try:
        service.read_query(kind, ident)
    except ApiError as exc:
        return {'code': exc.code, 'status': exc.status}
    return None


def _field(kind, name):
    def check():
        return _read(kind)['body'][name]
    return check


def _keyset(kind):
    def check():
        return sorted(_read(kind)['body'])
    return check


def _unknown(kind):
    def check():
        return _error(kind, 'sim-rm-missing')
    return check


def _invalid(kind):
    def check():
        return _error(kind, ' padded')
    return check


def check_error_codes():
    seen = set()
    for kind in QUERY:
        for ident in ('sim-rm-missing', '', ' padded', 'x' * 101):
            result = _error(kind, ident)
            seen.add(result['code'] if result else None)
    return sorted(seen, key=str)


def _envelope(name):
    def check():
        return _read('credit_advance')[name]
    return check


def check_digest():
    expected = hashlib.sha256(json.dumps(
        {'id': DRAWN_ADVANCE, 'query': 'get_credit_advance'},
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return _read('credit_advance')['query_digest'] == expected


def check_accepted_through_credit():
    service = _book()
    return [_read('credit_advance')['accepted_through'], len(service.machine.export_journal())]


def check_accepted_through_claim():
    service = _book()
    return [_read('credit_claim')['accepted_through'], len(service.machine.export_journal())]


def check_accepted_through_settlement():
    result = _read('settlement')
    return [result['accepted_through'], result['body']['accepted_entries']]


def check_no_clock():
    results = [_read(kind) for kind in QUERY]
    return any('logical_time_ms' in result or 'logical_time_ms' in result['body']
               for result in results)


def check_reserved_absent():
    found = set()
    for kind in QUERY:
        result = _read(kind)
        found.update(name for name in RESERVED if name in result or name in result['body'])
    return sorted(found)


def check_visibility():
    result = _read('credit_advance')
    return [result['visibility_enforced'], result['visibility_matrix']]


def check_body_unmodified():
    service = _book()
    return [
        _read('credit_advance')['body'] == service.machine.view(DRAWN_ADVANCE),
        _read('credit_claim')['body'] == service.machine.view_claim(FIXTURE),
        _read('settlement')['body'] == service.fixtures.view(FIXTURE),
    ]


def check_claim_no_lifecycle_authority():
    return 'lifecycle_authority' in _read('credit_claim')['body']


def check_snapshot_before_draw():
    # A fresh book: the mock ledger notes a claim at the first draw on a fixture and
    # every later advance on that fixture then sees it.
    service = _service()
    _op(service, 'offer', OFFERED_ADVANCE, {'fixture_id': FIXTURE, 'amount': 2000})
    return service.read_query('credit_advance', OFFERED_ADVANCE)['body']['snapshot_frozen']


def check_snapshot_after_draw():
    return _read('credit_claim')['body']['snapshot_frozen']


def check_claim_unknown_before_draw():
    return _error('credit_claim', FIXTURE, service=_service())


def check_settlement_claim_when_captured():
    body = _read('settlement', pending=True)['body']
    return [body['phase'], body['claim']['provenance']]


def check_settlement_claim_provenance():
    return _read('settlement')['body']['claim']['provenance']


def _frozen(service):
    return (service.machine.state_digest(), service.machine.canonical_state(),
            service.machine.export_journal(), len(service.receipts),
            json.dumps(service.receipts, sort_keys=True))


def check_non_mutation():
    service = _service()
    _op(service, 'offer', DRAWN_ADVANCE, {'fixture_id': FIXTURE, 'amount': 1000})
    _op(service, 'approve', DRAWN_ADVANCE)
    _op(service, 'bind_settlement', DRAWN_ADVANCE)
    _op(service, 'draw', DRAWN_ADVANCE)
    before = _frozen(service)
    for fixture_id in sorted(service.fixtures.rows):
        service.read_query('settlement', fixture_id)
        _error('credit_claim', fixture_id, service=service)
    service.read_query('credit_advance', DRAWN_ADVANCE)
    service.read_query('credit_claim', FIXTURE)
    for kind in QUERY:
        for ident in ('sim-rm-missing', '', ' padded'):
            _error(kind, ident, service=service)
    return before == _frozen(service)


CHECKS = {}
for _kind in QUERY:
    CHECKS['keyset.' + _kind] = _keyset(_kind)
    CHECKS['error.unknown.' + _kind] = _unknown(_kind)
    CHECKS['error.invalid.' + _kind] = _invalid(_kind)
for _name in (
    'funds_executed', 'license_granted', 'regulated_product', 'collateral_perfected',
    'priority_bound', 'disposal_controlled', 'revenue_assigned', 'admission_granted',
    'legal_debtor_bound', 'bank_debit_observed', 'external_pledge_complete', 'durable',
    'repayment_observed', 'interest_defined',
):
    CHECKS['field.credit_advance.' + _name] = _field('credit_advance', _name)
    CHECKS['field.credit_claim.' + _name] = _field('credit_claim', _name)
for _name in (
    'provenance', 'lifecycle_authority', 'exposure_ledger', 'kyc_executed',
    'underwriting_executed', 'economic_finality_claimed', 'ownership_mutated',
    'ticket_ownership_authoritative',
):
    CHECKS['field.credit_advance.' + _name] = _field('credit_advance', _name)
for _name in (
    'provenance', 'lifecycle_authority', 'provider_authorization_executed',
    'legal_debtor_bound', 'admission_granted', 'right_cancelled', 'bank_debit_observed',
    'external_return_closed', 'funds_executed', 'durable',
):
    CHECKS['field.settlement.' + _name] = _field('settlement', _name)
CHECKS['field.credit_claim.provenance'] = _field('credit_claim', 'provenance')
for _name in ('read_schema_version', 'fixture_mode'):
    CHECKS['envelope.' + _name] = _envelope(_name)
CHECKS.update({
    'error.codes': check_error_codes,
    'envelope.query_digest': check_digest,
    'envelope.accepted_through.credit_advance': check_accepted_through_credit,
    'envelope.accepted_through.credit_claim': check_accepted_through_claim,
    'envelope.accepted_through.settlement': check_accepted_through_settlement,
    'envelope.no_clock': check_no_clock,
    'envelope.reserved_absent': check_reserved_absent,
    'envelope.visibility': check_visibility,
    'body.unmodified': check_body_unmodified,
    'claim.no_lifecycle_authority': check_claim_no_lifecycle_authority,
    'advance.snapshot_before_draw': check_snapshot_before_draw,
    'claim.snapshot_after_draw': check_snapshot_after_draw,
    'claim.unknown_before_draw': check_claim_unknown_before_draw,
    'settlement.claim_when_captured': check_settlement_claim_when_captured,
    'settlement.claim_provenance': check_settlement_claim_provenance,
    'nonmutation.service': check_non_mutation,
})


# Original mapped read surfaces remain covered beside the point queries.
def _seeded():
    """One committed-and-drawn case on the loopback facade."""
    if 'service' not in _CACHE:
        from capital.service import CapitalService
        service = CapitalService()
        for op, args in OPERATIONS:
            receipt = service.execute({
                'instance_id': service.instance_id,
                'operation_id': f'sim-read-{op.replace("_", "-")}',
                'op': op,
                'advance_id': ADVANCE_ID,
                'args': args,
            })
            if receipt['outcome'] != 'ACCEPTED':
                raise ClaimTableError(f'seed {op} was rejected: {receipt}')
        _CACHE['service'] = service
    return _CACHE['service']


def _surface_frozen(service):
    return (
        service.machine.canonical_state(),
        len(service.machine.export_journal()),
        overlay.state_digest(overlay.fold(service.overlay_entries)),
        len(service.receipts),
    )


def _surface_read(call):
    """Run one read under the section-8 non-mutation guard."""
    service = _seeded()
    before = _surface_frozen(service)
    value = call(service)
    if _surface_frozen(service) != before:
        raise ClaimTableError('read mutated the facade guard')
    return value


def _nonmutation(call):
    """Section 8. 비변경: the read leaves every guard component unchanged."""
    service = _seeded()
    before = _surface_frozen(service)
    try:
        call(service)
    except CreditError:
        pass
    after = _surface_frozen(service)
    return {
        'canonical_state': after[0] == before[0],
        'journal': after[1] == before[1],
        'overlay_state_digest': after[2] == before[2],
        'operation_count': after[3] == before[3],
    }


def _case(service):
    for case in service.snapshot()['cases']:
        if case['advance_id'] == ADVANCE_ID:
            return case
    raise ClaimTableError('seeded case is not in GET /api/state')


def _advance_field(name):
    def check():
        return _surface_read(lambda service: _case(service)[name])
    return check


def _claim_field(name):
    def check():
        return _surface_read(lambda service: service.machine.view_claim(CLAIM_ID)[name])
    return check


def _code(call):
    try:
        call()
    except CreditError as exc:
        return exc.code
    return None


def check_advance_unknown():
    return _surface_read(lambda service: _code(lambda: service.machine.view('sim-missing')))


def check_claim_unknown():
    return _surface_read(lambda service: _code(lambda: service.machine.view_claim('sim-missing')))


def check_claim_no_lifecycle_key():
    return _surface_read(lambda service: 'lifecycle_authority' in service.machine.view_claim(CLAIM_ID))


def check_readonly_state():
    return _nonmutation(lambda service: service.snapshot())


def check_readonly_advance():
    return _nonmutation(lambda service: service.machine.view(ADVANCE_ID))


def check_readonly_claim():
    return _nonmutation(lambda service: service.machine.view_claim(CLAIM_ID))


def check_readonly_unknown():
    def reads(service):
        _code(lambda: service.machine.view('sim-missing'))
        _code(lambda: service.machine.view_claim('sim-missing'))
    return _nonmutation(reads)


for _name in (
    'phase', 'provenance', 'lifecycle_authority', 'claim_id', 'trade_id',
    'currency', 'amount', 'beneficiary_role', 'open_face', 'reserved_open',
    'residual_unreserved', 'confirmed_cash_on_face', 'recovery_due_on_face',
    'snapshot_frozen', 'outstanding_exposure', 'draw_id', 'settlement_gate',
    'note_status', 'funds_executed', 'repayment_observed', 'kyc_executed',
    'underwriting_executed', 'interest_defined',
):
    CHECKS['read.advance.' + _name] = _advance_field(_name)
for _name in (
    'provenance', 'claim_id', 'open_face', 'reserved_open',
    'residual_unreserved', 'confirmed_cash_on_face', 'recovery_due_on_face',
    'snapshot_frozen', 'funds_executed',
):
    CHECKS['read.claim.' + _name] = _claim_field(_name)
CHECKS.update({
    'read.advance.unknown': check_advance_unknown,
    'read.claim.unknown': check_claim_unknown,
    'read.claim.no_lifecycle_key': check_claim_no_lifecycle_key,
    'read.readonly.state': check_readonly_state,
    'read.readonly.advance': check_readonly_advance,
    'read.readonly.claim': check_readonly_claim,
    'read.readonly.unknown': check_readonly_unknown,
})
