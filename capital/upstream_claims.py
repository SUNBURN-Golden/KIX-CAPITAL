"""Executable CLAIM_CONFORMANCE checks for the pinned FSM and local facade.

Each row in tests/upstream_claims.json cites a kix-protocol heading and a
needle, names one check, and stores the value that check must observe.
The comparison is local and simulated. It is not a producer-profile
adoption, and it does not move funds.

A protocol checkout is optional. The drift script reads that tree and does
not write it. With no checkout the drift status is SKIPPED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from capital.protocol import (
    CreditError,
    CreditMachine,
    MockSettlement,
    SettlementError,
    SettlementMachine,
)
from capital.resources import ROOT, VENDOR, vendor_manifest

PINNED_SHA = '7481b0e16ce9b903abbffa62249bb91cd9e63cfe'
LABEL = 'CLAIM_CONFORMANCE'
FORMAT = 'KIX_CAPITAL_UPSTREAM_CLAIMS_V1'
REQUIRED_FIELDS = ('id', 'source_doc', 'section', 'pinned_sha', 'claim', 'check_id')
OFFER_AMOUNT = 1000
GROSS = 100_000
STATEMENT_CASH = 97_000
STATEMENT_FEE = 3_000

_CACHE = {}


class ClaimTableError(ValueError):
    """The claim table is missing a required field or has the wrong shape."""


def table_path(path=None):
    if path is not None:
        return Path(path)
    # Package data lives under capital/. The claim table stays in the checkout tests/.
    return Path(str(ROOT)).resolve().parent / 'tests' / 'upstream_claims.json'


def load_table(path=None, *, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA):
    raw_path = table_path(path)
    try:
        data = json.loads(raw_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClaimTableError(f'claim table is not readable JSON: {exc}') from exc
    validate_table(data, format=format, label=label, pinned_sha=pinned_sha)
    return data


def validate_table(data, *, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA):
    if type(data) is not dict:
        raise ClaimTableError('claim table must be an object')
    if data.get('format') != format:
        raise ClaimTableError('claim table format is not ' + format)
    if data.get('label') != label:
        raise ClaimTableError('claim table label is not ' + label)
    if data.get('pinned_sha') != pinned_sha:
        raise ClaimTableError('claim table pinned_sha is not the vendor pin')
    claims = data.get('claims')
    if type(claims) is not list or not claims:
        raise ClaimTableError('claims must be a non-empty list')
    seen = set()
    for index, claim in enumerate(claims):
        if type(claim) is not dict:
            raise ClaimTableError(f'claim {index} is not an object')
        for field in REQUIRED_FIELDS:
            value = claim.get(field)
            if type(value) is not str or not value.strip():
                raise ClaimTableError(f'claim {index} is missing {field}')
        if 'expected' not in claim:
            raise ClaimTableError(f'claim {claim["id"]} is missing expected')
        needle = claim.get('needle')
        if type(needle) is not str or not needle:
            raise ClaimTableError(f'claim {claim["id"]} is missing needle')
        if claim['pinned_sha'] != pinned_sha:
            raise ClaimTableError(f'claim {claim["id"]} pinned_sha is not the vendor pin')
        if claim['id'] in seen:
            raise ClaimTableError(f'duplicate claim id {claim["id"]}')
        seen.add(claim['id'])
        _relative_source(claim['source_doc'], claim['id'])
    return data


def _relative_source(source_doc, claim_id):
    rel = Path(source_doc)
    if rel.is_absolute() or any(part == '..' for part in rel.parts):
        raise ClaimTableError(f'claim {claim_id} source_doc escapes the checkout')
    return rel


def run_claims(table, *, checks=None, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA):
    """Run every check. An unmapped check fails that claim and no other."""
    validate_table(table, format=format, label=label, pinned_sha=pinned_sha)
    checks = CHECKS if checks is None else checks
    _CACHE.clear()
    rows = []
    for claim in table['claims']:
        check_id = claim['check_id']
        expected = claim['expected']
        if check_id not in checks:
            rows.append({
                'id': claim['id'],
                'check_id': check_id,
                'ok': False,
                'unmapped': True,
                'observed': None,
                'expected': expected,
            })
            continue
        try:
            observed = checks[check_id]()
        except Exception as exc:
            observed = {'error': type(exc).__name__, 'detail': str(exc)}
        rows.append({
            'id': claim['id'],
            'check_id': check_id,
            'ok': observed == expected,
            'unmapped': False,
            'observed': observed,
            'expected': expected,
        })
    failed = [row for row in rows if not row['ok']]
    return {
        'label': label,
        'passed': len(rows) - len(failed),
        'total': len(rows),
        'failed': failed,
        'rows': rows,
        'ok': not failed,
    }


def check_protocol(protocol_dir, table=None, *, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA):
    """Read cited headings and needles. Never writes the checkout.

    A missing directory argument is the caller's SKIPPED path. This function
    requires a directory and returns verified or failed.
    """
    if table is None:
        table = load_table(format=format, label=label, pinned_sha=pinned_sha)
    else:
        validate_table(table, format=format, label=label, pinned_sha=pinned_sha)
    root = Path(protocol_dir)
    if not root.is_dir():
        return {
            'status': 'failed',
            'label': label,
            'verified': 0,
            'total': len(table['claims']),
            'missing': [{'id': '*', 'problem': 'protocol dir is not a directory'}],
        }
    root_resolved = root.resolve()
    missing = []
    texts = {}
    for claim in table['claims']:
        rel = _relative_source(claim['source_doc'], claim['id'])
        path = (root / rel).resolve()
        if not path.is_relative_to(root_resolved) or not path.is_file():
            missing.append({'id': claim['id'], 'problem': 'missing file', 'source_doc': claim['source_doc']})
            continue
        key = str(path)
        if key not in texts:
            try:
                texts[key] = _read_only(path)
            except (OSError, UnicodeError) as exc:
                texts[key] = None
                missing.append({'id': claim['id'], 'problem': f'unreadable: {exc}', 'source_doc': claim['source_doc']})
                continue
        text = texts[key]
        if text is None:
            missing.append({'id': claim['id'], 'problem': 'unreadable', 'source_doc': claim['source_doc']})
            continue
        if claim['section'] not in text:
            missing.append({'id': claim['id'], 'problem': 'missing section', 'section': claim['section']})
        elif claim['needle'] not in text:
            missing.append({'id': claim['id'], 'problem': 'missing needle', 'needle': claim['needle']})
    total = len(table['claims'])
    verified = total - len({item['id'] for item in missing})
    return {
        'status': 'verified' if not missing else 'failed',
        'label': label,
        'verified': verified,
        'total': total,
        'missing': missing,
    }


def _read_only(path):
    """Read a checkout file without opening it for write."""
    fd = os.open(os.fspath(path), os.O_RDONLY)
    try:
        chunks = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(fd)
    return b''.join(chunks).decode('utf-8')


def _code(fn):
    try:
        fn()
    except (CreditError, SettlementError) as error:
        return error.code
    return None


def _policy(fee_bps):
    return {
        'kind': 'PRIMARY_FEE_BPS',
        'fee_bps': fee_bps,
        'residual_payee': 'organizer',
        'fee_payee': 'platform',
    }


def _captured(gross=GROSS, fee_bps=500):
    book = SettlementMachine()
    book.initiate(
        'set-1', idempotency_key='init', trade_id='trade-1', gross=gross,
        debtor_role='merchant', policy=_policy(fee_bps),
    )
    book.authorize('set-1', idempotency_key='auth')
    book.capture('set-1', idempotency_key='cap')
    return book


def _committed():
    book = _captured()
    book.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=GROSS,
        amount=STATEMENT_CASH, fee=STATEMENT_FEE, tax=0, held=0, adjustment=0,
    )
    return book


def _claim_view(book):
    return book.view('set-1')['claim']


def _payee_face(book, payee):
    for line in _claim_view(book)['obligations']:
        if line['payee'] == payee:
            return line['face']
    return None


def _credit(face, amount=OFFER_AMOUNT):
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=face, amount=amount,
        beneficiary_role='organizer',
    )
    machine.approve('adv-1', idempotency_key='approve')
    return machine


def _drawn_view():
    if 'drawn_view' not in _CACHE:
        machine = _credit(_claim_view(_committed()))
        _CACHE['draw_envelope'] = copy.deepcopy(
            machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1'))
        _CACHE['drawn_view'] = copy.deepcopy(machine.view('adv-1'))
    return _CACHE['drawn_view']


def _draw_envelope():
    _drawn_view()
    return _CACHE['draw_envelope']


def _facade():
    if 'facade' not in _CACHE:
        _CACHE['facade'] = json.loads((ROOT / 'contract' / 'facade-v1.json').read_text(encoding='utf-8'))
    return _CACHE['facade']


def _service():
    if 'service' not in _CACHE:
        from capital.service import CapitalService
        _CACHE['service'] = CapitalService()
    return _CACHE['service']


def _f04_flag(name):
    def check():
        return _drawn_view()[name]
    return check


def _settlement_flag(name):
    def check():
        return _committed().view('set-1')[name]
    return check


def check_f04_provenance():
    return _drawn_view()['provenance']


def check_f04_currency():
    face = copy.deepcopy(_claim_view(_committed()))
    face['currency'] = 'USD'

    def offer():
        CreditMachine().offer(
            'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
            beneficiary_role='organizer',
        )

    return _code(offer)


def check_f04_bool_amount():
    face = _claim_view(_committed())

    def offer():
        CreditMachine().offer(
            'adv-1', idempotency_key='offer', face=face, amount=True,
            beneficiary_role='organizer',
        )

    return _code(offer)


def check_f04_product():
    face = _claim_view(_committed())

    def offer():
        CreditMachine().offer(
            'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
            beneficiary_role='organizer', product={},
        )

    return _code(offer)


def check_f04_refund_open():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    face = _claim_view(book)

    def offer():
        CreditMachine().offer(
            'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
            beneficiary_role='organizer',
        )

    return _code(offer)


def check_f04_real_funds():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    return _code(lambda: machine.attempt_execution('adv-1', kind='DISBURSE'))


def check_f04_phase_after_execution_attempt():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    _code(lambda: machine.attempt_execution('adv-1', kind='DISBURSE'))
    return machine.view('adv-1')['phase']


def check_f04_unknown_advance():
    return _code(lambda: CreditMachine().view('missing-advance'))


def check_f04_unknown_journal_empty():
    machine = CreditMachine()
    _code(lambda: machine.view('missing-advance'))
    return len(machine.export_journal())


def check_f04_duplicate_draw():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    return _code(lambda: machine.draw('adv-1', idempotency_key='draw-2', draw_id='draw-2'))


def check_f04_outstanding():
    return _drawn_view()['outstanding_exposure']


def check_f04_journal_after_second_draw():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    _code(lambda: machine.draw('adv-1', idempotency_key='draw-2', draw_id='draw-2'))
    return len(machine.export_journal())


def check_f04_economic_finality():
    return _draw_envelope()['economic_finality_claimed']


def check_f04_repayment_observed_after_repay():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    machine.repay(
        'adv-1', idempotency_key='repay', repay_id='repay-1', sequence=1, amount=OFFER_AMOUNT,
    )
    return machine.view('adv-1')['repayment_observed']


def check_f04_close_is_not_repayment():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    machine.repay(
        'adv-1', idempotency_key='repay', repay_id='repay-1', sequence=1, amount=OFFER_AMOUNT,
    )
    machine.close('adv-1', idempotency_key='close')
    return machine.view('adv-1')['repayment_observed']


def check_f04_open_face():
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=_claim_view(_committed()), amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    return machine.view('adv-1')['open_face']


def check_f04_confirmed_cash_copied():
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=_claim_view(_committed()), amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    return machine.view('adv-1')['confirmed_cash_on_face']


def check_f04_terminal():
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=_claim_view(_committed()), amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    machine.reject('adv-1', idempotency_key='reject', reason='synthetic')
    return _code(lambda: machine.approve('adv-1', idempotency_key='approve'))


def check_f04_duplicate_replay():
    face = _claim_view(_committed())
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    again = machine.offer(
        'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    return again['duplicate']


def check_f04_idempotency_conflict():
    face = _claim_view(_committed())
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT,
        beneficiary_role='organizer',
    )
    return _code(lambda: machine.offer(
        'adv-1', idempotency_key='offer', face=face, amount=OFFER_AMOUNT + 1,
        beneficiary_role='organizer',
    ))


def check_f04_lifecycle():
    return _drawn_view()['lifecycle_authority']


def check_f04_kyc():
    return _drawn_view()['kyc_executed']


def check_f04_underwriting():
    return _drawn_view()['underwriting_executed']


def check_vendor_credit_fsm_sha():
    blob = (VENDOR / 'credit_advance_f04' / 'credit_fsm.py').read_bytes()
    return hashlib.sha256(blob).hexdigest()


def check_manifest_commit():
    return vendor_manifest()['commit']


def check_fee_face():
    return _payee_face(_captured(), 'platform')


def check_face_sum():
    lines = _claim_view(_captured())['obligations']
    return sum(line['face'] for line in lines)


def check_floor_fee():
    return _payee_face(_captured(gross=19999, fee_bps=1), 'platform')


def check_float_gross():
    def initiate():
        SettlementMachine().initiate(
            'set-1', idempotency_key='init', trade_id='trade-1', gross=100000.0,
            debtor_role='merchant', policy=_policy(500),
        )

    return _code(initiate)


def check_order_frozen():
    book = _committed()
    book.distribute('set-1', idempotency_key='dist-1', order=['organizer', 'platform'])
    return _code(lambda: book.distribute(
        'set-1', idempotency_key='dist-2', order=['platform', 'organizer'],
    ))


def check_frozen_order():
    book = _committed()
    book.distribute('set-1', idempotency_key='dist-1', order=['organizer', 'platform'])
    return _claim_view(book)['distribution_order']


def check_rejected_order_not_frozen():
    book = _committed()
    _code(lambda: book.distribute('set-1', idempotency_key='dist-1', order=['nobody', 'platform']))
    return _claim_view(book)['distribution_order']


def check_zero_cash_freezes_order():
    book = _captured()
    book.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=1000,
        amount=0, fee=1000, tax=0, held=0, adjustment=0,
    )
    book.distribute('set-1', idempotency_key='dist-1', order=['organizer', 'platform'])
    return _claim_view(book)['distribution_order']


def check_refund_ceiling():
    book = _committed()
    return _code(lambda: book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=GROSS + 1,
        beneficiary_role='buyer', reason='SYNTHETIC',
    ))


def check_partial_bearer():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return _claim_view(book)['refund_bearer_policy']


def check_distribution_blocked():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return _code(lambda: book.distribute(
        'set-1', idempotency_key='dist-1', order=['organizer', 'platform'],
    ))


def check_full_reclass():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=GROSS,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return _claim_view(book)['refund_bearer_policy']


def check_remainder_stays_undefined():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund-1', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    book.bind_refund(
        'set-1', idempotency_key='refund-2', refund_id='refund-2', amount=GROSS - 1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return _claim_view(book)['refund_bearer_policy']


def check_distributed_sum():
    book = _committed()
    book.distribute('set-1', idempotency_key='dist-1', order=['organizer', 'platform'])
    return _claim_view(book)['distributed_cash']


def check_component_mismatch():
    book = _captured()
    return _code(lambda: book.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=GROSS,
        amount=1, fee=1, tax=0, held=0, adjustment=0,
    ))


def check_external_return_after_acceptance():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    book.observe_mock_cancel_acceptance(
        'set-1', idempotency_key='accept', source_id='accept-1', amount=1000,
    )
    return book.view('set-1')['external_return_closed']


def check_confirmed_cash_after_refund():
    book = _committed()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=1000,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return _claim_view(book)['confirmed_cash']


def check_unknown_claim():
    return _code(lambda: MockSettlement().view('missing-claim'))


def check_unknown_settlement():
    return _code(lambda: SettlementMachine().view('missing-settlement'))


def check_settlement_provenance():
    return _committed().view('set-1')['provenance']


def check_provider_authorization():
    book = SettlementMachine()
    book.initiate(
        'set-1', idempotency_key='init', trade_id='trade-1', gross=GROSS,
        debtor_role='merchant', policy=_policy(500),
    )
    book.authorize('set-1', idempotency_key='auth')
    return book.view('set-1')['provider_authorization_executed']


def check_mock_authorized():
    book = SettlementMachine()
    book.initiate(
        'set-1', idempotency_key='init', trade_id='trade-1', gross=GROSS,
        debtor_role='merchant', policy=_policy(500),
    )
    book.authorize('set-1', idempotency_key='auth')
    return book.view('set-1')['mock_authorized']


def check_external_payment():
    return _code(lambda: SettlementMachine().reject_external('BANK_DEBIT'))


def check_settlement_replay_journal():
    book = SettlementMachine()
    kwargs = dict(
        idempotency_key='init', trade_id='trade-1', gross=GROSS,
        debtor_role='merchant', policy=_policy(500),
    )
    book.initiate('set-1', **kwargs)
    book.initiate('set-1', **kwargs)
    return len(book.export_journal())


def check_digest_length():
    return len(_committed().state_digest())


def check_restore_digest():
    book = _committed()
    restored = SettlementMachine.restore(book.export_journal())
    return restored.state_digest() == book.state_digest()


def check_money_max():
    def initiate():
        SettlementMachine().initiate(
            'set-1', idempotency_key='init', trade_id='trade-1', gross=10**12 + 1,
            debtor_role='merchant', policy=_policy(500),
        )

    return _code(initiate)


def check_replay_draw_funds():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    again = machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    return again['funds_executed']


def check_service_unknown_outcome():
    service = _service()
    body = service.operation('missing-op', service.instance_id)
    return body['outcome']


def check_service_unknown_retry():
    service = _service()
    body = service.operation('missing-op', service.instance_id)
    return body['retry_authorized']


def check_gate_unknown_retry():
    from capital.gate_producer import ProducerUnknown
    return ProducerUnknown('missing-op').retry_authorized


def check_recon_unknown_retry():
    return _service().reconciliation()['unknown_policy']['retry_authorized']


def check_facade_unknown_retry_const():
    schema = _facade()
    return schema['definitions']['unknown_policy']['properties']['retry_authorized']['const']


def check_facade_profile_flag():
    return _facade()['semantic_conformance']


def check_draw_bank_debit():
    return _drawn_view()['bank_debit_observed']


def check_replay_finality():
    machine = _credit(_claim_view(_committed()))
    machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    again = machine.draw('adv-1', idempotency_key='draw', draw_id='draw-1')
    return again['economic_finality_claimed']


F04_FALSE_FLAGS = (
    'funds_executed',
    'license_granted',
    'regulated_product',
    'collateral_perfected',
    'priority_bound',
    'disposal_controlled',
    'revenue_assigned',
    'admission_granted',
    'legal_debtor_bound',
    'bank_debit_observed',
    'external_pledge_complete',
    'durable',
    'repayment_observed',
    'interest_defined',
)

SETTLEMENT_FALSE_FLAGS = (
    'funds_executed',
    'admission_granted',
    'legal_debtor_bound',
    'bank_debit_observed',
    'external_return_closed',
    'right_cancelled',
    'durable',
)

CHECKS = {}
for _name in F04_FALSE_FLAGS:
    CHECKS['f04.flag.' + _name] = _f04_flag(_name)
for _name in SETTLEMENT_FALSE_FLAGS:
    CHECKS['settlement.flag.' + _name] = _settlement_flag(_name)

CHECKS.update({
    'f04.provenance': check_f04_provenance,
    'f04.currency': check_f04_currency,
    'f04.bool_amount': check_f04_bool_amount,
    'f04.product': check_f04_product,
    'f04.refund_open': check_f04_refund_open,
    'f04.real_funds': check_f04_real_funds,
    'f04.phase_after_execution': check_f04_phase_after_execution_attempt,
    'f04.unknown_advance': check_f04_unknown_advance,
    'f04.unknown_journal': check_f04_unknown_journal_empty,
    'f04.duplicate_draw': check_f04_duplicate_draw,
    'f04.outstanding': check_f04_outstanding,
    'f04.journal_after_second_draw': check_f04_journal_after_second_draw,
    'f04.economic_finality': check_f04_economic_finality,
    'f04.repayment_after_repay': check_f04_repayment_observed_after_repay,
    'f04.close_not_repayment': check_f04_close_is_not_repayment,
    'f04.open_face': check_f04_open_face,
    'f04.confirmed_cash_copied': check_f04_confirmed_cash_copied,
    'f04.terminal': check_f04_terminal,
    'f04.duplicate_replay': check_f04_duplicate_replay,
    'f04.idempotency_conflict': check_f04_idempotency_conflict,
    'f04.lifecycle': check_f04_lifecycle,
    'f04.kyc': check_f04_kyc,
    'f04.underwriting': check_f04_underwriting,
    'vendor.credit_fsm_sha': check_vendor_credit_fsm_sha,
    'vendor.manifest_commit': check_manifest_commit,
    'settlement.fee_face': check_fee_face,
    'settlement.face_sum': check_face_sum,
    'settlement.floor_fee': check_floor_fee,
    'settlement.float_gross': check_float_gross,
    'settlement.order_frozen': check_order_frozen,
    'settlement.frozen_order': check_frozen_order,
    'settlement.rejected_order': check_rejected_order_not_frozen,
    'settlement.zero_cash_order': check_zero_cash_freezes_order,
    'settlement.refund_ceiling': check_refund_ceiling,
    'settlement.partial_bearer': check_partial_bearer,
    'settlement.distribution_blocked': check_distribution_blocked,
    'settlement.full_reclass': check_full_reclass,
    'settlement.remainder_undefined': check_remainder_stays_undefined,
    'settlement.distributed_sum': check_distributed_sum,
    'settlement.component_mismatch': check_component_mismatch,
    'settlement.external_return_after_acceptance': check_external_return_after_acceptance,
    'settlement.confirmed_cash_after_refund': check_confirmed_cash_after_refund,
    'settlement.unknown_claim': check_unknown_claim,
    'settlement.unknown_settlement': check_unknown_settlement,
    'settlement.provenance': check_settlement_provenance,
    'settlement.provider_authorization': check_provider_authorization,
    'settlement.mock_authorized': check_mock_authorized,
    'settlement.external_payment': check_external_payment,
    'settlement.replay_journal': check_settlement_replay_journal,
    'settlement.digest_length': check_digest_length,
    'settlement.restore_digest': check_restore_digest,
    'commerce.float_gross': check_float_gross,
    'commerce.money_max': check_money_max,
    'commerce.confirmed_cash_after_refund': check_confirmed_cash_after_refund,
    'commerce.external_payment': check_external_payment,
    'commerce.component_mismatch': check_component_mismatch,
    'authority.replay_funds': check_replay_draw_funds,
    'authority.unknown_outcome': check_service_unknown_outcome,
    'authority.unknown_retry': check_service_unknown_retry,
    'authority.gate_retry': check_gate_unknown_retry,
    'authority.recon_retry': check_recon_unknown_retry,
    'authority.facade_retry_const': check_facade_unknown_retry_const,
    'authority.profile_flag': check_facade_profile_flag,
    'authority.bank_debit': check_draw_bank_debit,
    'authority.replay_finality': check_replay_finality,
    'authority.provider_not_payment': check_provider_authorization,
})
