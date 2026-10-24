"""Executable CLAIM_CONFORMANCE checks for the read-model query draft.

Each row in tests/read_model_claims.json cites the pinned
docs/contracts/READ_MODEL_QUERIES.md draft 0.1 (kix-protocol
7481b0e16ce9b903abbffa62249bb91cd9e63cfe), names the local read route it
maps to, and stores the value that read must observe. The mapping is a
local adapter, stated honestly: the draft's get_credit_advance reads
surface through GET /api/state case views (literal CreditMachine.view
dicts) and get_credit_claim through the in-process
CreditMachine.view_claim. No upstream query name is implemented and no
HTTP route is added; this table prepares the parked
read-model-credit-queries node only.

Every check runs the read under the section-8 non-mutation guard: the
machine canonical_state, the accepted journal length, the folded overlay
state digest, and the receipt count (operation_count) must be identical
before and after. A read that changes any of them fails its claim. The
comparison is local and SIMULATED; it is not a catalogue adoption and it
moves no funds.

A protocol checkout is optional. The drift script reads that tree and
does not write it. With no checkout the drift status is SKIPPED.
"""
from __future__ import annotations

from pathlib import Path

from capital import overlay, upstream_claims
from capital.protocol import CreditError
from capital.resources import ROOT
from capital.upstream_claims import ClaimTableError

PINNED_SHA = upstream_claims.PINNED_SHA
LABEL = upstream_claims.LABEL
FORMAT = 'KIX_CAPITAL_READ_MODEL_CLAIMS_V1'
REQUIRED_FIELDS = upstream_claims.REQUIRED_FIELDS + ('route',)
SOURCE_DOC = 'docs/contracts/READ_MODEL_QUERIES.md'
ROUTES = ('GET /api/state', 'CreditMachine.view', 'CreditMachine.view_claim')
SECTION_ADVANCE = '### 2.12 `get_credit_advance`'
SECTION_CLAIM = '### 2.13 `get_credit_claim`'
SECTION_NONMUTATION = '## 8. 비변경'
ADVANCE_ID = 'sim-read'
CLAIM_ID = 'sim-committed'
AMOUNT = 60_000
OPERATIONS = (
    ('offer', {'fixture_id': CLAIM_ID, 'amount': AMOUNT}),
    ('approve', {}),
    ('bind_settlement', {}),
    ('draw', {}),
)

_CACHE = {}


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'read_model_claims.json'


def load_table(path=None):
    return upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def validate_table(data):
    upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)
    for claim in data['claims']:
        route = claim.get('route')
        if type(route) is not str or route not in ROUTES:
            raise ClaimTableError(f'claim {claim["id"]} route is not a mapped read route')
    return data


def run_claims(table):
    """Run every check. An unmapped check fails that claim and no other."""
    validate_table(table)
    _CACHE.clear()
    return upstream_claims.run_claims(
        table, checks=CHECKS, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def check_protocol(protocol_dir, table=None):
    """Read cited headings and needles. Never writes the checkout."""
    if table is None:
        table = load_table()
    else:
        validate_table(table)
    return upstream_claims.check_protocol(
        protocol_dir, table, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


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


def _frozen(service):
    return (
        service.machine.canonical_state(),
        len(service.machine.export_journal()),
        overlay.state_digest(overlay.fold(service.overlay_entries)),
        len(service.receipts),
    )


def _read(call):
    """Run one read under the section-8 non-mutation guard."""
    service = _seeded()
    before = _frozen(service)
    value = call(service)
    if _frozen(service) != before:
        raise ClaimTableError('read mutated the facade guard')
    return value


def _nonmutation(call):
    """Section 8. 비변경: the read leaves every guard component unchanged."""
    service = _seeded()
    before = _frozen(service)
    try:
        call(service)
    except CreditError:
        pass
    after = _frozen(service)
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
        return _read(lambda service: _case(service)[name])
    return check


def _claim_field(name):
    def check():
        return _read(lambda service: service.machine.view_claim(CLAIM_ID)[name])
    return check


def _code(call):
    try:
        call()
    except CreditError as exc:
        return exc.code
    return None


def check_advance_unknown():
    return _read(lambda service: _code(lambda: service.machine.view('sim-missing')))


def check_claim_unknown():
    return _read(lambda service: _code(lambda: service.machine.view_claim('sim-missing')))


def check_claim_no_lifecycle_key():
    return _read(lambda service: 'lifecycle_authority' in service.machine.view_claim(CLAIM_ID))


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


CHECKS = {}
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
