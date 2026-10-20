#!/usr/bin/env python3
"""Run pinned FSM contract-claim checks, and optionally read a protocol checkout.

With no --protocol-dir, drift status is SKIPPED. SKIPPED is not a success.
--protocol-dir reads cited headings and needles and does not write the tree.
--execute first verifies every vendored byte against manifest.json, then runs
each claim's deterministic vector through the vendored CreditMachine and
SettlementMachine. Results are SIMULATED. This is CLAIM_CONFORMANCE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import upstream_claims
from capital.protocol import (
    CreditError,
    CreditMachine,
    SettlementError,
    SettlementMachine,
)
from capital.resources import VENDOR, vendor_manifest
from capital.upstream_claims import ClaimTableError

TABLE_PATH = ROOT / 'tests' / 'fsm_contract_claims.json'
FORMAT = 'KIX_CAPITAL_FSM_CONTRACT_CLAIMS_V1'
LABEL = upstream_claims.LABEL
PINNED_SHA = upstream_claims.PINNED_SHA
GROSS = 100_000
CASH = 97_000
DRAWN = 60_000


def table_path(path=None):
    return TABLE_PATH if path is None else Path(path)


def load_table(path=None):
    return upstream_claims.load_table(
        table_path(path), format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def validate_table(data):
    return upstream_claims.validate_table(
        data, format=FORMAT, label=LABEL, pinned_sha=PINNED_SHA)


def run_claims(table):
    """Run every check. An unmapped check fails that claim and no other."""
    validate_table(table)
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


def vendor_hashes(vendor_dir=None):
    """True when every vendored file matches the manifest hash."""
    return not _vendor_report(vendor_dir)


def _policy(fee_bps=500):
    return {
        'kind': 'PRIMARY_FEE_BPS',
        'fee_bps': fee_bps,
        'residual_payee': 'organizer',
        'fee_payee': 'platform',
    }


def _code(call):
    try:
        call()
    except (CreditError, SettlementError) as error:
        return error.code
    return None


def _committed_book():
    book = SettlementMachine()
    book.initiate(
        'set-1', idempotency_key='init', trade_id='trade-1', gross=GROSS,
        debtor_role='merchant', policy=_policy(),
    )
    book.authorize('set-1', idempotency_key='auth')
    book.capture('set-1', idempotency_key='cap')
    book.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=GROSS,
        amount=CASH, fee=GROSS - CASH, tax=0, held=0, adjustment=0,
    )
    return book


def _claim(book):
    return book.view('set-1')['claim']


def _drawn_machine():
    """adv-1 drawn 60000 on the standard committed face (open_face 100000)."""
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer-1', face=_claim(_committed_book()),
        amount=DRAWN, beneficiary_role='organizer',
    )
    machine.approve('adv-1', idempotency_key='approve-1')
    machine.draw('adv-1', idempotency_key='draw-1', draw_id='draw-1')
    return machine


def _refused_second():
    """adv-2 approved for 50000 on the same face, draw refused."""
    machine = _drawn_machine()
    face = _claim(_committed_book())
    machine.offer(
        'adv-2', idempotency_key='offer-2', face=face,
        amount=50_000, beneficiary_role='organizer',
    )
    machine.approve('adv-2', idempotency_key='approve-2')
    code = _code(lambda: machine.draw('adv-2', idempotency_key='draw-2', draw_id='draw-2'))
    return machine, code


def _refunded_book(amount):
    book = _committed_book()
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=amount,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return book


def _reclassified_book():
    """Committed, distributed 97000, then a one-shot full-gross refund."""
    book = _committed_book()
    book.distribute('set-1', idempotency_key='dist-1', order=['organizer', 'platform'])
    book.bind_refund(
        'set-1', idempotency_key='refund', refund_id='refund-1', amount=GROSS,
        beneficiary_role='buyer', reason='SYNTHETIC',
    )
    return book


def check_shared_face_exceeds():
    return _refused_second()[1]


def check_shared_face_phase():
    machine, _ = _refused_second()
    return machine.view('adv-2')['phase']


def check_shared_face_reserved():
    return _drawn_machine().view_claim('set-1')['reserved_open']


def check_shared_face_residual():
    return _drawn_machine().view_claim('set-1')['residual_unreserved']


def check_shared_face_repay_keeps():
    machine = _drawn_machine()
    machine.repay(
        'adv-1', idempotency_key='repay-1', repay_id='repay-1',
        sequence=1, amount=20_000,
    )
    return machine.view_claim('set-1')['reserved_open']


def check_shared_face_close_returns():
    machine = _drawn_machine()
    machine.repay(
        'adv-1', idempotency_key='repay-1', repay_id='repay-1',
        sequence=1, amount=DRAWN,
    )
    machine.close('adv-1', idempotency_key='close-1')
    return machine.view_claim('set-1')['reserved_open']


def check_shared_face_default_holds():
    machine = _drawn_machine()
    machine.default('adv-1', idempotency_key='default-1', reason='SYNTHETIC')
    return machine.view_claim('set-1')['reserved_open']


def check_face_snapshot_frozen():
    machine = _drawn_machine()
    mutated = dict(_claim(_committed_book()))
    mutated['confirmed_cash'] = CASH - 1
    machine.offer(
        'adv-2', idempotency_key='offer-2', face=mutated,
        amount=1000, beneficiary_role='organizer',
    )
    machine.approve('adv-2', idempotency_key='approve-2')
    return _code(lambda: machine.draw('adv-2', idempotency_key='draw-2', draw_id='draw-2'))


def check_binding_conflict():
    machine = _drawn_machine()
    return _code(lambda: machine.offer(
        'adv-1', idempotency_key='offer-again', face=_claim(_committed_book()),
        amount=DRAWN + 1, beneficiary_role='organizer',
    ))


def check_refund_open():
    face = _claim(_refunded_book(1000))
    return _code(lambda: CreditMachine().offer(
        'adv-1', idempotency_key='offer-1', face=face,
        amount=1000, beneficiary_role='organizer',
    ))


def check_refund_open_no_journal():
    face = _claim(_refunded_book(1000))
    machine = CreditMachine()
    _code(lambda: machine.offer(
        'adv-1', idempotency_key='offer-1', face=face,
        amount=1000, beneficiary_role='organizer',
    ))
    return len(machine.export_journal())


def check_distribution_blocked():
    book = _refunded_book(1000)
    return _code(lambda: book.distribute(
        'set-1', idempotency_key='dist-1', order=['organizer', 'platform'],
    ))


def check_partial_bearer():
    return _claim(_refunded_book(1000))['refund_bearer_policy']


def check_acceptance_required():
    book = _committed_book()
    return _code(lambda: book.observe_mock_cancel_acceptance(
        'set-1', idempotency_key='accept-1', source_id='accept-1', amount=1000,
    ))


def check_acceptance_exceeds():
    book = _refunded_book(1000)
    return _code(lambda: book.observe_mock_cancel_acceptance(
        'set-1', idempotency_key='accept-1', source_id='accept-1', amount=2000,
    ))


def check_full_bearer():
    return _claim(_reclassified_book())['refund_bearer_policy']


def check_recovery_due_sum():
    return _claim(_reclassified_book())['recovery_due']


def check_recovery_per_line():
    claim = _claim(_reclassified_book())
    return {line['payee']: line['recovery_due'] for line in claim['obligations']}


def check_recovery_face_not_capacity():
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer-1', face=_claim(_reclassified_book()),
        amount=1, beneficiary_role='organizer',
    )
    machine.approve('adv-1', idempotency_key='approve-1')
    return _code(lambda: machine.draw('adv-1', idempotency_key='draw-1', draw_id='draw-1'))


def check_recovery_due_copied():
    machine = CreditMachine()
    machine.offer(
        'adv-1', idempotency_key='offer-1', face=_claim(_reclassified_book()),
        amount=1, beneficiary_role='organizer',
    )
    return machine.view('adv-1')['recovery_due_on_face']


def check_f04_restore_digest():
    machine = _drawn_machine()
    restored = CreditMachine.restore(machine.export_journal())
    return restored.state_digest() == machine.state_digest()


def check_f04_restore_duplicate():
    machine = _drawn_machine()
    restored = CreditMachine.restore(machine.export_journal())
    again = restored.draw('adv-1', idempotency_key='draw-1', draw_id='draw-1')
    return again['duplicate']


def check_f04_reconcile():
    return _drawn_machine().reconcile('adv-1', idempotency_key='recon-1')['matched']


def check_f04_refusal_no_journal():
    machine = _drawn_machine()
    _code(lambda: machine.draw('adv-1', idempotency_key='draw-2', draw_id='draw-2'))
    return len(machine.export_journal())


def check_settlement_restore_digest():
    book = _reclassified_book()
    restored = SettlementMachine.restore(book.export_journal())
    return restored.state_digest() == book.state_digest()


def check_settlement_restore_duplicate():
    book = _committed_book()
    restored = SettlementMachine.restore(book.export_journal())
    again = restored.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=GROSS,
        amount=CASH, fee=GROSS - CASH, tax=0, held=0, adjustment=0,
    )
    return again['duplicate']


def check_settlement_idempotent_replay():
    book = _committed_book()
    again = book.commit(
        'set-1', idempotency_key='commit', movement_id='mov-1', gross=GROSS,
        amount=CASH, fee=GROSS - CASH, tax=0, held=0, adjustment=0,
    )
    return again['duplicate']


def check_settlement_reconcile():
    return _reclassified_book().reconcile('set-1', idempotency_key='recon-1')['matched']


def _vendor_sha(rel):
    return hashlib.sha256((VENDOR / rel).read_bytes()).hexdigest()


def check_vendor_commit():
    return vendor_manifest()['commit']


CHECKS = {
    'vendor.commit': check_vendor_commit,
    'vendor.hashes': vendor_hashes,
    'vendor.credit_fsm': lambda: _vendor_sha('credit_advance_f04/credit_fsm.py'),
    'vendor.mock_credit': lambda: _vendor_sha('credit_advance_f04/mock_credit.py'),
    'vendor.test_mock_credit': lambda: _vendor_sha('credit_advance_f04/test_mock_credit.py'),
    'vendor.mock_settlement': lambda: _vendor_sha('settlement_f01_f03/mock_settlement.py'),
    'vendor.settlement_fsm': lambda: _vendor_sha('settlement_f01_f03/settlement_fsm.py'),
    'f04.shared_face.exceeds': check_shared_face_exceeds,
    'f04.shared_face.phase': check_shared_face_phase,
    'f04.shared_face.reserved': check_shared_face_reserved,
    'f04.shared_face.residual': check_shared_face_residual,
    'f04.shared_face.repay_keeps': check_shared_face_repay_keeps,
    'f04.shared_face.close_returns': check_shared_face_close_returns,
    'f04.shared_face.default_holds': check_shared_face_default_holds,
    'f04.face_snapshot_frozen': check_face_snapshot_frozen,
    'f04.binding_conflict': check_binding_conflict,
    'f04.refund_open': check_refund_open,
    'f04.refund_open_no_journal': check_refund_open_no_journal,
    'f04.recovery_face_not_capacity': check_recovery_face_not_capacity,
    'f04.recovery_due_copied': check_recovery_due_copied,
    'f04.restore_digest': check_f04_restore_digest,
    'f04.restore_duplicate': check_f04_restore_duplicate,
    'f04.reconcile': check_f04_reconcile,
    'f04.refusal_no_journal': check_f04_refusal_no_journal,
    'settlement.distribution_blocked': check_distribution_blocked,
    'settlement.partial_bearer': check_partial_bearer,
    'settlement.acceptance_required': check_acceptance_required,
    'settlement.acceptance_exceeds': check_acceptance_exceeds,
    'settlement.full_bearer': check_full_bearer,
    'settlement.recovery_due_sum': check_recovery_due_sum,
    'settlement.recovery_per_line': check_recovery_per_line,
    'settlement.restore_digest': check_settlement_restore_digest,
    'settlement.restore_duplicate': check_settlement_restore_duplicate,
    'settlement.idempotent_replay': check_settlement_idempotent_replay,
    'settlement.reconcile': check_settlement_reconcile,
}


def _print_skipped():
    print('SKIPPED')
    print(json.dumps(
        {'drift': 'not-run', 'label': 'CLAIM_CONFORMANCE', 'status': 'SKIPPED'},
        sort_keys=True,
    ))


def _vendor_report(vendor_dir=None):
    root = VENDOR if vendor_dir is None else Path(vendor_dir)
    expected = vendor_manifest()['files']
    drifted = []
    for rel, sha in expected.items():
        path = root / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            drifted.append(rel)
    return drifted


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol-dir', default=None)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--table', type=Path, default=None)
    args = parser.parse_args(argv)
    protocol_dir = args.protocol_dir
    if protocol_dir is not None and not str(protocol_dir).strip():
        protocol_dir = None
    if not args.execute and protocol_dir is None:
        _print_skipped()
        return 0
    try:
        table = load_table(args.table)
    except ClaimTableError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    code = 0
    if args.execute:
        drifted = _vendor_report()
        if drifted:
            for rel in drifted:
                print(f'VENDOR_HASH_MISMATCH {rel}', file=sys.stderr)
            return 1
        result = run_claims(table)
        failed = result['failed']
        print(
            f"CLAIM_CONFORMANCE passed={result['passed']} total={result['total']} "
            f"failed={len(failed)}"
        )
        for row in failed:
            print(
                f"FAIL {row['id']} observed={row['observed']!r} expected={row['expected']!r}",
                file=sys.stderr,
            )
        if not result['ok']:
            code = 1
    if protocol_dir is not None:
        report = check_protocol(protocol_dir, table)
        print(f"CLAIM_DRIFT verified={report['verified']} total={report['total']}")
        if report['status'] != 'verified':
            for item in report['missing']:
                print(f"DRIFT {item.get('id')} {item.get('problem')}", file=sys.stderr)
            code = 1
    return code


if __name__ == '__main__':
    sys.exit(main())
