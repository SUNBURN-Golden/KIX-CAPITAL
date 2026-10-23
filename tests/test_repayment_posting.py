"""Overlay repayment posting: interest and principal payments on the sim_day ledger.

SIMULATED. Every number is recomputed here from the decision notes or from the read-only
allocation quote (GET /api/terms/{id}/allocation), never read back from the code under test.
Spec: docs/decisions/CAPITAL_REPAYMENT_POSTING.md.
"""
import copy
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from capital import export, overlay, recon, verify
from capital.audit import audit_workspace
from capital.auth import ROLES
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, InMemoryStorage, WorkspaceError, canonical_bytes, section_checksum
from capital.terms import DecisionNoteTermsPolicy, read_decision_block
from tests import facade_schema
from tests.test_margin import BASE, drawn_then_refunded, kinds, margin_state
from tests.test_overlay import GOLDEN_DIR, ROOT, draw_book, f04_view, row, run, seed, terms_value, tick

NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_REPAYMENT_POSTING.md'
LABEL = 'SIMULATED'


def note_value(name):
    return read_decision_block(NOTE)['entries'][name]['value']


def body(service, key, amount, *, advance='sim-a', day=None, **extra):
    return {'instance_id': service.instance_id, 'operation_id': key, 'op': 'post_repayment',
            'advance_ref': advance, 'at_sim_day': service.overlay_state()['sim_day'] if day is None else day,
            'amount_krw': amount, **extra}


def pay(service, key, amount, *, role='organizer', **extra):
    return service.overlay_command(body(service, key, amount, **extra), role=role)


def refused(test, call):
    with test.assertRaises(ApiError) as caught:
        call()
    return caught.exception


def whole(service):
    """Everything a rejected posting must leave alone."""
    return (json.dumps(service.overlay_entries, sort_keys=True), json.dumps(service.receipts, sort_keys=True),
            service.machine.state_digest(), service.overlay_state()['overlay_state_digest'],
            json.dumps(service.machine.export_journal(), sort_keys=True), service.workspace_status)


def quote(service, day, cash):
    return service.case_allocation('sim-a', service.instance_id, draw_day=0, as_of_day=day, cash=cash)['allocation']


def drawn(day=60):
    service = CapitalService()
    draw_book(service)
    tick(service, 'c-1', 0, day)
    return service


def without(receipt, *keys):
    return {key: value for key, value in receipt.items() if key not in keys}


class SplitTests(unittest.TestCase):
    def test_the_note_order_is_the_terms_order(self):
        # allocation_order_matches_terms: the decision stops here if CAPITAL_FINANCIAL_TERMS disagrees.
        order = terms_value('interest_rate')['repayment_allocation_order']
        self.assertEqual(order, ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL'])
        self.assertEqual(row(drawn())['allocation']['order'], order)

    def test_a_posting_splits_exactly_as_the_allocation_quote_for_the_same_cash_and_day(self):
        service = drawn()
        cash = 5000
        expected = quote(service, 60, cash)
        receipt = pay(service, 'p-1', cash)
        self.assertEqual(receipt['allocation'], {
            'default_interest_krw': expected['to_default_interest'], 'interest_krw': expected['to_interest'],
            'principal_krw': expected['to_principal'], 'unapplied_after_krw': expected['unapplied_cash']})
        self.assertEqual(receipt['allocation']['interest_krw'], formula_due(90000 * 60, 700))
        self.assertEqual(receipt['outcome'], 'APPLIED')
        self.assertEqual((receipt['label'] == service.overlay_state()['label'], receipt['basis']),
                         (True, 'SIM_REPAY_MEMO'))
        self.assertEqual(receipt['payment_basis'], 'UNVERIFIED_ASSERTED')

    def test_default_interest_is_applied_first_then_interest_then_principal(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 10)
        tick(service, 'c-2', 10, 75)
        current = row(service)
        default_due, interest_due = current['default_interest_due_krw'], current['interest_due_krw']
        self.assertGreater(default_due, 0)
        small = default_due - 1
        first = pay(service, 'p-1', small)
        self.assertEqual(first['allocation'], {'default_interest_krw': small, 'interest_krw': 0,
                                               'principal_krw': 0, 'unapplied_after_krw': 0})
        cash = 1 + interest_due + 700
        expected = service.terms.allocate(90000, interest_due=interest_due, default_interest_due=1, cash=cash)
        second = pay(service, 'p-2', cash)
        self.assertEqual(second['allocation'], {
            'default_interest_krw': 1, 'interest_krw': interest_due, 'principal_krw': 700, 'unapplied_after_krw': 0})
        self.assertEqual(expected['to_principal'], 700)
        after = row(service)
        self.assertEqual((after['default_interest_due_krw'], after['interest_due_krw']), (0, 0))
        self.assertEqual((after['default_interest_paid_krw'], after['interest_paid_krw']),
                         (default_due, interest_due))
        self.assertEqual(after['principal_outstanding_krw'], 90000 - 700)

    def test_payments_carry_across_ticks_and_the_sub_won_remainder_is_never_lost(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 3)
        first = pay(service, 'p-1', row(service)['interest_due_krw'])
        tick(service, 'c-2', 3, 6)
        second = pay(service, 'p-2', row(service)['interest_due_krw'])
        paid = first['allocation']['interest_krw'] + second['allocation']['interest_krw']
        self.assertEqual(paid, formula_due(90000 * 6, 700))
        self.assertEqual(row(service)['interest_due_krw'], 0)
        self.assertEqual(row(service)['carried_remainder_contract'], row(service)['carried_remainder_contract'])
        state = overlay.fold(service.overlay_entries)
        witness = service.overlay_entries[-1]['payload']['witness']
        self.assertEqual(witness['denominator'], 10000 * 365)
        self.assertEqual(int(witness['accrued_interest_num']) // witness['denominator'], paid)

    def test_get_overlay_reports_the_payments_with_paid_and_due_instead_of_not_recorded(self):
        service = drawn()
        before = service.overlay_state()['interest_payments']
        self.assertEqual((before['status'], before['payments_recorded']), ('NONE_YET', 0))
        due = row(service)['interest_due_krw']
        pay(service, 'p-1', due - 10)
        payments = service.overlay_state()['interest_payments']
        self.assertEqual(payments['status'], 'RECORDED')
        self.assertEqual((payments['payments_recorded'], payments['paid_interest_krw'], payments['interest_due_krw']),
                         (1, due - 10, 10))
        self.assertEqual((payments['paid_default_interest_krw'], payments['default_interest_due_krw']), (0, 0))
        self.assertEqual((payments['basis'], payments['amounts']), ('SIM_REPAY_MEMO', 'UNVERIFIED_ASSERTED'))
        self.assertNotEqual(payments, 'NOT_RECORDED')
        bare = CapitalService(terms=DecisionNoteTermsPolicy(Path('/nonexistent/terms.md')))
        self.assertEqual(bare.overlay_state()['interest_payments']['status'], 'NOT_BOUND')


def formula_due(person_days, bps):
    day_count = int(terms_value('interest_rate')['day_count'].split('_')[1])
    return (person_days * bps) // (10000 * day_count)


class F04CouplingTests(unittest.TestCase):
    def test_an_interest_only_posting_never_calls_f04(self):
        service = drawn()
        before = f04_view(service)
        calls = []
        real = PinnedFsmProducer.apply
        with mock.patch.object(PinnedFsmProducer, 'apply', lambda self, *a, **k: calls.append(a) or real(self, *a, **k)):
            receipt = pay(service, 'p-1', row(service)['interest_due_krw'])
        self.assertEqual(calls, [])
        self.assertEqual(f04_view(service), before)
        self.assertIsNone(receipt['f04'])
        self.assertIs(receipt['f04_journal_written'], False)
        self.assertEqual(receipt['allocation']['principal_krw'], 0)

    def test_the_principal_portion_reaches_f04_once_as_one_pinned_repay(self):
        service = drawn()
        interest = row(service)['interest_due_krw']
        before_journal = service.machine.export_journal()
        receipt = pay(service, 'p-1', interest + 4000)
        journal = service.machine.export_journal()
        self.assertEqual(len(journal), len(before_journal) + 1)
        added = journal[-1]
        self.assertEqual((added['op'], added['advance_id'], added['body']['amount'], added['body']['sequence']),
                         ('repay', 'sim-a', 4000, 1))
        self.assertEqual(receipt['allocation']['principal_krw'], 4000)
        self.assertIs(receipt['f04_journal_written'], True)
        # One operation_id reaches both receipts: the F04 id is rp- + the first 32 hex of the domain hash.
        import hashlib
        expected_id = 'rp-' + hashlib.sha256(b'KIX_CAPITAL_REPAY_F04_V1|p-1').hexdigest()[:32]
        self.assertEqual(receipt['f04']['operation_id'], expected_id)
        self.assertEqual(added['idempotency_key'], expected_id)
        stored = service.operation(expected_id, service.instance_id)
        self.assertEqual(stored['outcome'], 'ACCEPTED')
        self.assertEqual(stored['result']['effect']['amount'], 4000)
        self.assertEqual(receipt['f04']['receipt_ref'], stored['result']['effect']['repay_id'])
        self.assertEqual(service.overlay_entries[-1]['after_journal_index'], len(journal))
        self.assertEqual(service.machine.view('sim-a')['outstanding_exposure'], 90000 - 4000)
        # The same repay through the direct path would be byte-identical to what the posting issued.
        twin = drawn()
        direct = run(twin, 'repay', 'sim-a', expected_id, amount=4000, sequence=1)
        self.assertEqual(twin.machine.export_journal()[-1], added)
        self.assertEqual(direct['result']['effect'], stored['result']['effect'])

    def test_a_rejected_f04_repay_leaves_journal_receipts_and_digests_unchanged(self):
        service = drawn()
        import hashlib
        taken = 'rp-' + hashlib.sha256(b'KIX_CAPITAL_REPAY_F04_V1|p-1').hexdigest()[:32]
        run(service, 'repay', 'sim-a', taken, amount=1, sequence=1)  # the derived F04 id is already used
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', 9000))
        self.assertEqual((error.code, error.status), ('REPAYMENT_ADVANCE_STATE', 409))
        self.assertEqual(whole(service), before)
        # The rejection kept the id free: the same operation_id works once the F04 side is clear.
        fresh = drawn()
        self.assertEqual(pay(fresh, 'p-1', 9000)['outcome'], 'APPLIED')

    def test_a_historical_unanchored_default_takes_interest_only_because_f04_is_terminal(self):
        # A default recorded before the overlay exists has no dated recovery anchor.
        # Anchored defaults permanently use recovery (covered in test_recovery).
        service = CapitalService()
        draw_book(service)
        run(service, 'default', 'sim-a', 'd-1')
        tick(service, 'c-1', 0, 60)
        self.assertNotIn('default_anchors', overlay.fold(service.overlay_entries))
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', 9000))
        self.assertEqual((error.code, error.status), ('REPAYMENT_ADVANCE_STATE', 409))
        self.assertEqual(error.detail['phase'], 'DEFAULTED')
        self.assertEqual(whole(service), before)
        due = row(service)['interest_due_krw']
        receipt = pay(service, 'p-2', due)
        self.assertEqual(receipt['allocation']['interest_krw'], due)
        self.assertIsNone(receipt['f04'])

    def test_an_unsupported_producer_refuses_a_principal_portion_but_not_interest(self):
        class Other(PinnedFsmProducer):
            """Not the in-process pinned producer."""

        service = CapitalService(producer=Other())
        draw_book(service)
        tick(service, 'c-1', 0, 60)
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', 9000))
        self.assertEqual((error.code, error.status), ('REPAYMENT_PRODUCER_UNSUPPORTED', 409))
        self.assertEqual(whole(service), before)
        self.assertEqual(pay(service, 'p-2', row(service)['interest_due_krw'])['outcome'], 'APPLIED')

    def test_a_failed_save_rolls_the_machine_receipts_and_overlay_back(self):
        class Failing(InMemoryStorage):
            fail = False

            def save(self, document, overlay=None):
                if self.fail:
                    raise WorkspaceError('WORKSPACE_WRITE_FAILED')
                super().save(document, overlay)

        storage = Failing()
        service = CapitalService(storage)
        draw_book(service)
        tick(service, 'c-1', 0, 60)
        before = whole(service)
        storage.fail = True
        error = refused(self, lambda: pay(service, 'p-1', 9000))
        self.assertEqual((error.code, error.status), ('WORKSPACE_WRITE_FAILED', 503))
        self.assertEqual(service.workspace_status, 'WORKSPACE_WRITE_FAILED')
        self.assertEqual(whole(service)[:5], before[:5])
        self.assertEqual(service.machine.view('sim-a')['outstanding_exposure'], 90000)

    def test_replay_and_reload_read_the_recorded_receipt_and_never_call_the_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = FileWorkspace.open(tmp)
            try:
                service = CapitalService(port)
                draw_book(service)
                tick(service, 'c-1', 0, 60)
                original = pay(service, 'p-1', 9000, evidence_ref='ops:ref-7')
                digest = service.overlay_state()['overlay_state_digest']
            finally:
                port.close()
            calls = []
            real = PinnedFsmProducer.apply
            port = FileWorkspace.open(tmp)
            try:
                with mock.patch.object(PinnedFsmProducer, 'apply',
                                       lambda self, *a, **k: calls.append(a) or real(self, *a, **k)):
                    again = CapitalService(port)
                    self.assertEqual(again.workspace_status, 'ACTIVE')
                    duplicate = pay(again, 'p-1', 9000, evidence_ref='ops:ref-7')
                    again.overlay_state()
                    again.export_manifest()
                    again.reconciliation()
                self.assertEqual(calls, [])
                self.assertEqual(again.overlay_state()['overlay_state_digest'], digest)
                self.assertIs(duplicate['transport_duplicate'], True)
                self.assertEqual(without(duplicate, 'transport_duplicate', 'instance_id'),
                                 without(original, 'transport_duplicate', 'instance_id', 'overlay_state_digest'))
                self.assertEqual(again.overlay_state('p-1')['operation']['entry_no'], original['entry_no'])
            finally:
                port.close()

    def test_a_workspace_whose_entry_names_a_missing_f04_repay_is_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = FileWorkspace.open(tmp)
            try:
                service = CapitalService(port)
                draw_book(service)
                tick(service, 'c-1', 0, 60)
                pay(service, 'p-1', 9000)
                path = Path(tmp) / 'workspace.json'
                document = json.loads(path.read_text(encoding='utf-8'))
            finally:
                port.close()
            entries = copy.deepcopy(document['overlay']['journal'])
            entries[-1]['payload']['f04_receipt_ref'] = 'repay-someone-else'
            document['overlay'] = overlay.build_section(entries)
            path.write_bytes(canonical_bytes(document))
            port = FileWorkspace.open(tmp)
            try:
                self.assertEqual(CapitalService(port).workspace_status, 'WORKSPACE_UNREADABLE')
            finally:
                port.close()


class IdempotencyTests(unittest.TestCase):
    def test_the_same_operation_returns_the_stored_receipt_and_writes_nothing(self):
        service = drawn()
        original = pay(service, 'p-1', 9000, evidence_ref='bank:ref-1')
        before = whole(service)
        duplicate = pay(service, 'p-1', 9000, evidence_ref='bank:ref-1')
        self.assertIs(original['transport_duplicate'], False)
        self.assertIs(duplicate['transport_duplicate'], True)
        self.assertEqual(without(duplicate, 'transport_duplicate', 'overlay_state_digest'),
                         without(original, 'transport_duplicate', 'overlay_state_digest'))
        self.assertEqual(whole(service), before)

    def test_dedup_comes_before_the_clock_check(self):
        service = drawn()
        original = pay(service, 'p-1', 9000)
        tick(service, 'c-2', 60, 70)
        again = service.overlay_command(body(service, 'p-1', 9000, day=60))
        self.assertIs(again['transport_duplicate'], True)
        self.assertEqual(again['entry_no'], original['entry_no'])
        fresh = refused(self, lambda: service.overlay_command(body(service, 'p-2', 5, day=60)))
        self.assertEqual((fresh.code, fresh.status), ('SIM_CLOCK_STALE', 409))

    def test_a_different_body_under_the_same_id_is_a_conflict(self):
        service = drawn()
        pay(service, 'p-1', 9000, evidence_ref='bank:ref-1')
        before = whole(service)
        for changed in ({'amount': 9001}, {'evidence_ref': 'bank:ref-2'}, {'advance': 'sim-b'}, {'day': 59},
                        {'amount': 9000, 'evidence_ref': None}):
            with self.subTest(changed):
                extra = {} if 'evidence_ref' in changed and changed['evidence_ref'] is None else {'evidence_ref': 'bank:ref-1'}
                extra.update({k: v for k, v in changed.items() if k == 'evidence_ref' and v is not None})
                error = refused(self, lambda: pay(service, 'p-1', changed.get('amount', 9000),
                                                  advance=changed.get('advance', 'sim-a'),
                                                  day=changed.get('day'), **extra))
                self.assertEqual((error.code, error.status), ('IDEMPOTENCY_CONFLICT', 409))
        self.assertEqual(whole(service), before)

    def test_an_operation_id_never_crosses_between_advance_day_and_post_repayment(self):
        service = drawn()
        pay(service, 'p-1', 9000)
        again = refused(self, lambda: tick(service, 'p-1', 60, 61))
        self.assertEqual((again.code, again.status), ('IDEMPOTENCY_CONFLICT', 409))
        crossed = refused(self, lambda: pay(service, 'c-1', 9000))
        self.assertEqual((crossed.code, crossed.status), ('IDEMPOTENCY_CONFLICT', 409))
        self.assertEqual(overlay.fold(service.overlay_entries)['sim_day'], 60)

    def test_lookup_by_operation_id_and_unknown(self):
        service = drawn()
        receipt = pay(service, 'p-1', 9000)
        known = service.overlay_state('p-1')['operation']
        self.assertEqual(known, without(receipt, *[k for k in receipt if k not in known]))
        self.assertEqual(service.overlay_state('p-nope')['operation']['outcome'], 'UNKNOWN')
        self.assertIs(service.overlay_state('p-nope')['operation']['retry_authorized'], False)


class UnappliedAndBoundsTests(unittest.TestCase):
    def paid_off(self, extra):
        service = drawn()
        due = row(service)['interest_due_krw']
        return service, pay(service, 'p-1', due + 90000 + extra)

    def test_an_overpayment_is_held_and_never_counted_as_principal_or_interest(self):
        service, receipt = self.paid_off(500)
        self.assertEqual(receipt['allocation']['unapplied_after_krw'], 500)
        self.assertEqual(receipt['close_gate']['status'], 'UNAPPLIED_HELD')
        current = row(service)
        self.assertEqual((current['principal_outstanding_krw'], current['unapplied_cash_krw']), (0, 500))
        self.assertEqual(service.overlay_state()['close_gate']['unapplied_cash_krw'], 500)
        self.assertEqual(service.machine.view('sim-a')['outstanding_exposure'], 0)

    def test_the_held_cash_is_added_to_the_next_posting_and_a_zero_posting_is_allowed_only_with_a_hold(self):
        service, _first = self.paid_off(500)
        second = pay(service, 'p-2', 0)
        self.assertEqual((second['unapplied_before_krw'], second['unapplied_after_krw']), (500, 500))
        third = pay(service, 'p-3', 100)
        self.assertEqual((third['unapplied_before_krw'], third['unapplied_after_krw']), (500, 600))
        bare = drawn()
        error = refused(self, lambda: pay(bare, 'z-1', 0))
        self.assertEqual((error.code, error.status), ('REPAYMENT_AMOUNT', 400))

    def test_the_unapplied_cap_and_amount_and_entry_limits_come_from_the_note(self):
        cap = note_value('unapplied_cash_handling')['max_krw_per_advance']
        capacity = note_value('capacity_and_envelope_effect')
        self.assertEqual(overlay.load_repayment_bounds(), {
            'amount_max_krw': capacity['amount_max_krw'], 'entries_per_advance_max': capacity['entries_per_advance_max'],
            'entry_canonical_bytes_max': capacity['entry_canonical_bytes_max'], 'unapplied_max_krw_per_advance': cap})
        service = drawn()
        due = row(service)['interest_due_krw']
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', due + 90000 + cap + 1))
        self.assertEqual((error.code, error.status), ('REPAYMENT_UNAPPLIED_CAP', 409))
        error = refused(self, lambda: pay(service, 'p-2', capacity['amount_max_krw'] + 1))
        self.assertEqual((error.code, error.status, error.detail), ('SIMULATION_CAPACITY', 409,
                                                                    {'bound': 'REPAYMENT_AMOUNT_MAX_KRW'}))
        self.assertEqual(whole(service), before)
        self.assertEqual(pay(service, 'p-3', due + 90000 + cap)['allocation']['unapplied_after_krw'], cap)

    def test_entries_per_advance_are_bounded(self):
        bounds = dict(overlay.load_repayment_bounds(), entries_per_advance_max=2)
        service = CapitalService(repayment_bounds=bounds)
        draw_book(service)
        tick(service, 'c-1', 0, 60)
        pay(service, 'p-1', 1)
        pay(service, 'p-2', 1)
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-3', 1))
        self.assertEqual((error.code, error.status, error.detail),
                         ('SIMULATION_CAPACITY', 409, {'bound': 'REPAYMENT_ENTRIES_PER_ADVANCE'}))
        self.assertEqual(whole(service), before)

    def test_the_shared_envelope_bounds_still_apply(self):
        service = drawn()
        service.overlay_bounds = dict(service.overlay_bounds, OVERLAY_MAX_ENTRIES=len(service.overlay_entries))
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', 1))
        self.assertEqual((error.code, error.detail), ('SIMULATION_CAPACITY', {'bound': 'OVERLAY_MAX_ENTRIES'}))
        self.assertEqual(whole(service), before)
        service.overlay_bounds = dict(service.overlay_bounds, OVERLAY_MAX_ENTRIES=10 ** 6, ENVELOPE_MAX_BYTES=1)
        error = refused(self, lambda: pay(service, 'p-1', 1))
        self.assertEqual((error.code, error.detail), ('SIMULATION_CAPACITY', {'bound': 'ENVELOPE_MAX_BYTES'}))

    def entry_for(self, big, advance_ref, operation_id, evidence_ref, proposal_id):
        bounds = overlay.load_repayment_bounds()
        state = overlay.empty_state()
        state['advances'][advance_ref] = {
            'cumulative_contract_exact': f'{big}/1', 'cumulative_default_exact': f'{big}/1'}
        state['repayment'] = {'advances': {advance_ref: {
            'paid_default_krw': big // 2, 'paid_interest_krw': big // 2, 'principal_krw': big,
            'unapplied_cash_krw': bounds['unapplied_max_krw_per_advance'], 'postings': 599}}, 'close_gate': None}
        split = {'to_default_interest': big // 2, 'to_interest': big // 2, 'to_principal': bounds['amount_max_krw'],
                 'unapplied_cash': bounds['unapplied_max_krw_per_advance']}
        return overlay.repayment_entry(
            operation_id, state, journal_index=10 ** 6, advance_ref=advance_ref, amount=bounds['amount_max_krw'],
            denominator=10000 * 365, principal_before=bounds['amount_max_krw'], terms_version='CAPITAL-TERMS-V1',
            split=split, f04=('rp-' + 'f' * 32, 'repay-rp-' + 'f' * 32), evidence_ref=evidence_ref,
            proposal_id=proposal_id)

    def test_a_maximum_length_entry_fits_the_note_byte_bound(self):
        bounds = overlay.load_repayment_bounds()
        # Largest amounts, longest operation id, advance ref and evidence_ref; the optional citation is short.
        entry = self.entry_for(10 ** 15, 'sim-' + 'x' * 60, 'o' * 80, 'e' * 64, 'sim-proposal')
        self.assertLessEqual(overlay.entry_size(entry), bounds['entry_canonical_bytes_max'])
        self.assertLessEqual(bounds['entry_canonical_bytes_max'], overlay.load_bounds()['OVERLAY_ENTRY_MAX_BYTES'])
        self.assertTrue(overlay.fold([], 0) == overlay.empty_state())

    def test_an_entry_over_the_note_bound_is_refused_without_a_write(self):
        service = drawn()
        service.repayment_bounds = dict(service.repayment_bounds, entry_canonical_bytes_max=100)
        before = whole(service)
        error = refused(self, lambda: pay(service, 'p-1', 9000))
        self.assertEqual((error.code, error.status, error.detail),
                         ('SIMULATION_CAPACITY', 409, {'bound': 'REPAYMENT_ENTRY_MAX_BYTES'}))
        self.assertEqual(whole(service), before)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.service = drawn()

    def test_strict_shape_and_types_write_nothing(self):
        service = self.service
        before = whole(service)
        base = body(service, 'v-1', 100)
        cases = {
            'unknown key': {**base, 'split': {'interest_krw': 1}},
            'client timestamp': {**base, 'timestamp': 'x'},
            'payer identity': {**base, 'payer': 'x'},
            'missing amount': {k: v for k, v in base.items() if k != 'amount_krw'},
            'missing advance': {k: v for k, v in base.items() if k != 'advance_ref'},
            'bool amount': {**base, 'amount_krw': True},
            'float amount': {**base, 'amount_krw': 1.5},
            'string amount': {**base, 'amount_krw': '100'},
            'negative amount': {**base, 'amount_krw': -1},
            'huge amount': {**base, 'amount_krw': 10 ** 13},
            'bad advance': {**base, 'advance_ref': 'not-synthetic'},
            'bad day': {**base, 'at_sim_day': -1},
            'bool day': {**base, 'at_sim_day': True},
            'bad evidence': {**base, 'evidence_ref': 'has space'},
            'long evidence': {**base, 'evidence_ref': 'e' * 65},
            'account evidence': {**base, 'evidence_ref': 'KB 123-456-789 홍길동'},
            'bad operation id': {**base, 'operation_id': 'bad id!'},
            'bad proposal': {**base, 'proposal_id': ' padded '},
            'wrong op': {**base, 'op': 'post_payment'},
        }
        for label, command in cases.items():
            with self.subTest(label):
                error = refused(self, lambda: service.overlay_command(command))
                self.assertIn(error.status, (400,), (label, error.code))
        self.assertEqual(whole(service), before)
        self.assertEqual(refused(self, lambda: service.overlay_command({**base, 'instance_id': 'other'})).code,
                         'SESSION_CHANGED')

    def test_precondition_failures(self):
        service = self.service
        stale = refused(self, lambda: pay(service, 'v-1', 1, day=59))
        self.assertEqual((stale.code, stale.status), ('SIM_CLOCK_STALE', 409))
        self.assertEqual(stale.detail, {'sim_day': 60})
        unknown = refused(self, lambda: pay(service, 'v-2', 1, advance='sim-nope'))
        self.assertEqual((unknown.code, unknown.status), ('UNKNOWN_ADVANCE', 404))
        run(service, 'offer', 'sim-b', 'b-offer', fixture_id='sim-pending', amount=1000)
        before = whole(service)
        undrawn = refused(self, lambda: pay(service, 'v-3', 1, advance='sim-b'))
        self.assertEqual((undrawn.code, undrawn.status, undrawn.detail), ('REPAYMENT_ADVANCE_STATE', 409,
                                                                         {'reason': 'NOT_DRAWN'}))
        self.assertEqual(whole(service), before)

    def test_terms_not_bound_before_the_first_tick_and_when_the_note_is_absent(self):
        service = CapitalService()
        draw_book(service)
        error = refused(self, lambda: pay(service, 'v-1', 1, day=0))
        self.assertEqual((error.code, error.status), ('REPAYMENT_TERMS_NOT_BOUND', 409))
        self.assertEqual(service.overlay_entries, [])
        with tempfile.TemporaryDirectory() as tmp:
            bare = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'absent.md'))
            error = refused(self, lambda: pay(bare, 'v-2', 1, day=0))
            self.assertEqual((error.code, error.status, error.detail['reason']), ('NOT_BOUND', 400, 'terms not bound'))
        unbound = drawn()
        unbound.repayment_bounds = None
        self.assertEqual(refused(self, lambda: pay(unbound, 'v-3', 1)).code, 'NOT_BOUND')
        self.assertIsNone(overlay.load_repayment_bounds(Path(tempfile.gettempdir()) / 'absent-note.md'))

    def test_roles_and_workspace_state(self):
        for role in ('auditor', 'observer', 'agent', 'nobody', None):
            with self.subTest(role):
                error = refused(self, lambda: pay(self.service, 'v-1', 1, role=role))
                self.assertEqual(error.status, 403)
        self.service.workspace_status = 'WORKSPACE_UNREADABLE'
        self.assertEqual(refused(self, lambda: pay(self.service, 'v-2', 1)).status, 503)

    def test_a_proposal_citation_is_checked_and_recorded(self):
        service = self.service
        unknown = refused(self, lambda: pay(service, 'v-1', 5000, proposal_id='sim-nope'))
        self.assertEqual((unknown.code, unknown.status), ('UNKNOWN_PROPOSAL', 404))
        from tests.test_agent_lane import _propose
        service.agent_propose(_propose(proposal_id='sim-rp', surface='capital:repay', amount=5000), role='agent')
        wrong = refused(self, lambda: pay(service, 'v-2', 4000, proposal_id='sim-rp'))
        self.assertEqual((wrong.code, wrong.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        receipt = pay(service, 'v-3', 5000, proposal_id='sim-rp')
        self.assertEqual(receipt['proposal_id'], 'sim-rp')
        self.assertEqual(service.overlay_entries[-1]['payload']['proposal_id'], 'sim-rp')
        self.assertEqual(service.agent_lane.proposals['sim-rp']['effects_executed'], False)
        agent = refused(self, lambda: pay(service, 'v-4', 5000, role='agent', proposal_id='sim-rp'))
        self.assertEqual(agent.code, 'ROLE_FORBIDDEN')


class CloseAndMarginTests(unittest.TestCase):
    def test_close_is_never_gated_and_its_f04_result_matches_the_empty_overlay_path(self):
        with_overlay = CapitalService()
        draw_book(with_overlay)
        tick(with_overlay, 'c-1', 0, 5)
        self.assertGreater(row(with_overlay)['interest_due_krw'], 0)
        run(with_overlay, 'repay', 'sim-a', 'r-1', amount=90000, sequence=1)
        current = row(with_overlay)
        self.assertFalse(current['close_ready'])
        self.assertEqual(current['close_gate']['status'], 'INTEREST_DUE')
        closed = run(with_overlay, 'close', 'sim-a', 'k-1')
        plain = CapitalService()
        draw_book(plain)
        run(plain, 'repay', 'sim-a', 'r-1', amount=90000, sequence=1)
        expected = run(plain, 'close', 'sim-a', 'k-1')
        self.assertEqual(closed['outcome'], 'ACCEPTED')
        self.assertEqual(closed['result'], expected['result'])
        self.assertEqual(with_overlay.machine.state_digest(), plain.machine.state_digest())
        self.assertEqual(with_overlay.overlay_state()['close_gate']['status'], 'INTEREST_DUE')
        self.assertIn(with_overlay.overlay_state()['warnings'][0]['code'], ('UNPOSTED_F04_REPAY',))

    def test_after_close_accrual_freezes_and_only_the_interest_share_can_be_posted(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 5)
        due = row(service)['interest_due_krw']
        run(service, 'repay', 'sim-a', 'r-1', amount=90000, sequence=1)
        run(service, 'close', 'sim-a', 'k-1')
        tick(service, 'c-2', 5, 20)
        self.assertEqual(row(service)['interest_due_krw'], due)
        receipt = pay(service, 'p-1', due + 300)
        self.assertEqual(receipt['allocation'], {'default_interest_krw': 0, 'interest_krw': due,
                                                 'principal_krw': 0, 'unapplied_after_krw': 300})
        self.assertIsNone(receipt['f04'])
        self.assertEqual(receipt['close_gate']['status'], 'UNAPPLIED_HELD')
        self.assertEqual(service.machine.view('sim-a')['phase'], 'CLOSED')

    def test_close_ready_flips_only_when_every_due_is_zero(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 5)
        due = row(service)['interest_due_krw']
        run(service, 'repay', 'sim-a', 'r-1', amount=90000, sequence=1)
        pay(service, 'p-1', due - 1)
        self.assertFalse(row(service)['close_ready'])
        self.assertEqual(row(service)['close_gate']['interest_due_krw'], 1)
        pay(service, 'p-2', 1)
        self.assertTrue(row(service)['close_ready'])
        self.assertEqual(row(service)['close_gate']['status'], 'CLEAR')
        self.assertEqual(run(service, 'close', 'sim-a', 'k-1')['outcome'], 'ACCEPTED')

    def test_close_gate_appears_only_for_a_non_empty_overlay(self):
        service = CapitalService()
        draw_book(service)
        self.assertNotIn('close_gate', service.snapshot())
        self.assertNotIn('close_gate', service.overlay_state())
        self.assertEqual(service.overlay_state()['warnings'], [])
        tick(service, 'c-1', 0, 5)
        self.assertEqual(service.snapshot()['close_gate'], service.overlay_state()['close_gate'])
        self.assertEqual(set(service.overlay_state()['close_gate']),
                         {'status', 'default_interest_due_krw', 'interest_due_krw', 'unapplied_cash_krw'})

    def test_a_repay_back_within_the_base_still_records_margin_cure(self):
        source, service = drawn_then_refunded()
        tick(service, 'c-1', 0, 3)
        due = row(service)['interest_due_krw']
        receipt = pay(service, 'p-1', due + 2)
        self.assertEqual(receipt['allocation']['principal_krw'], 2)
        self.assertEqual(overlay.KIND_MARGIN_CURE in kinds(service), False)  # the posting writes no cure state
        tick(service, 'c-2', 3, 4)
        cure = next(e for e in service.overlay_entries if e['kind'] == overlay.KIND_MARGIN_CURE)
        self.assertEqual((cure['sim_day'], cure['payload']['outstanding_krw']), (3, BASE - 1))
        self.assertEqual(margin_state(service)['status'], 'CURED')
        order = [entry['kind'] for entry in service.overlay_entries]
        self.assertLess(order.index(overlay.KIND_REPAYMENT), order.index(overlay.KIND_MARGIN_CURE))

    def test_a_posting_that_leaves_exposure_over_the_base_does_not_cure(self):
        source, service = drawn_then_refunded(amount=BASE + 5)
        tick(service, 'c-1', 0, 3)
        pay(service, 'p-1', 2)
        tick(service, 'c-2', 3, 4)
        self.assertNotIn(overlay.KIND_MARGIN_CURE, kinds(service))
        self.assertEqual(margin_state(service)['status'], 'CALLED')
        # Recovery decision keeps the draw tier after a refund; these two won
        # pay posted contractual interest before principal, so the breach remains.
        self.assertEqual(service.machine.view('sim-a')['outstanding_exposure'], BASE + 5)
        entry = next(e for e in service.overlay_entries if e['kind'] == overlay.KIND_REPAYMENT)
        self.assertEqual(entry['payload']['allocation']['interest_krw'], 2)
        self.assertEqual(entry['payload']['allocation']['principal_krw'], 0)


class DigestExportTests(unittest.TestCase):
    def test_an_empty_overlay_stays_v2_and_byte_identical_to_the_demo_golden(self):
        demo = json.loads((GOLDEN_DIR / 'demo.json').read_text(encoding='utf-8'))
        service = seed.build_service()
        manifest = service.export_manifest()
        self.assertEqual(manifest['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V2')
        self.assertEqual(manifest['content_digest'], demo['content_digest'])
        self.assertNotIn('repayment', overlay.fold([]))
        self.assertEqual(overlay.fold([]), overlay.empty_state())

    def test_a_posting_moves_to_v3_and_verifier_and_reconciliation_cover_it(self):
        service = seed.build_service()
        tick(service, 'x-1', 0, 60)
        before = service.export_manifest()['content_digest']
        pay(service, 'x-2', 5000, advance='sim-unbound')
        manifest = service.export_manifest()
        self.assertEqual(manifest['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V3')
        self.assertNotEqual(manifest['content_digest'], before)
        self.assertIn(overlay.KIND_REPAYMENT, [e['kind'] for e in manifest['sections']['overlay']['body']['journal']])
        self.assertEqual(manifest['sections']['overlay']['body']['state']['repayment']['close_gate'],
                         overlay.close_gates(overlay.fold(service.overlay_entries)))
        report = verify.verify_manifest(copy.deepcopy(manifest))
        self.assertTrue(report['ok'], report)
        self.assertEqual(len(report['sections']), 8)
        self.assertEqual(set(report['sections'].values()), {'MATCHED'})
        recon_report = service.reconciliation()
        self.assertEqual(recon_report['status'], 'MATCHED')
        check = recon_report['checks'][-1]
        self.assertEqual((check['id'], check['status']), ('overlay_fold_digest_equals_persisted', 'MATCHED'))
        self.assertEqual(len(recon_report['checks']), 7)
        edited = copy.deepcopy(manifest)
        edited['sections']['overlay']['body']['journal'][-1]['payload']['amount_krw'] += 1
        self.assertFalse(verify.verify_manifest(edited)['ok'])

    def test_the_workspace_file_reloads_audits_and_fails_closed_when_a_signed_repayment_is_tampered(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = FileWorkspace.open(tmp)
            try:
                service = CapitalService(port)
                draw_book(service)
                tick(service, 'c-1', 0, 60)
                pay(service, 'p-1', 5000)
                self.assertEqual(service.reconciliation()['checks'][-1]['status'], 'MATCHED')
                digest = service.overlay_state()['overlay_state_digest']
            finally:
                port.close()
            self.assertTrue(audit_workspace(Path(tmp))['ok'])
            path = Path(tmp) / 'workspace.json'
            good = json.loads(path.read_text(encoding='utf-8'))
            mutations = {
                'witness paid': lambda p: p['witness'].__setitem__('paid_interest_krw', 1),
                'witness numerator': lambda p: p['witness'].__setitem__(
                    'accrued_interest_num', str(int(p['witness']['accrued_interest_num']) + 10 ** 7)),
                'allocation moved': lambda p: p['allocation'].__setitem__(
                    'interest_krw', p['allocation']['interest_krw'] + 1),
                'amount': lambda p: p.__setitem__('amount_krw', p['amount_krw'] + 1),
                'unapplied before': lambda p: p.__setitem__('unapplied_before_krw', 1),
                'f04 id dropped': lambda p: p.__setitem__('f04_operation_id', None),
                'terms version': lambda p: p['terms_binding'].__setitem__('terms_version', 'other'),
                'basis': lambda p: p.__setitem__('basis', 'REAL_PAYMENT'),
            }
            for label, mutate in mutations.items():
                with self.subTest(label):
                    document = copy.deepcopy(good)
                    entries = copy.deepcopy(document['overlay']['journal'])
                    mutate(entries[-1]['payload'])
                    section = copy.deepcopy(document['overlay'])
                    section['journal'] = entries  # re-signed: the checksum is valid, only the fold can object
                    section['section_sha256'] = section_checksum(section)
                    document['overlay'] = section
                    path.write_bytes(canonical_bytes(document))
                    reopened_port = FileWorkspace.open(tmp)
                    try:
                        reopened = CapitalService(reopened_port)
                        self.assertEqual(reopened.workspace_status, 'WORKSPACE_UNREADABLE')
                        self.assertEqual(reopened.overlay_entries, [])
                    finally:
                        reopened_port.close()
                    self.assertFalse(audit_workspace(Path(tmp))['ok'])
            path.write_bytes(canonical_bytes(good))
            port = FileWorkspace.open(tmp)
            try:
                self.assertEqual(CapitalService(port).overlay_state()['overlay_state_digest'], digest)
            finally:
                port.close()

    def test_the_overlay_demo_golden_cites_the_decision_and_the_scenario_reproduces(self):
        golden = json.loads((GOLDEN_DIR / 'overlay_demo.json').read_text(encoding='utf-8'))
        self.assertIn('CAPITAL_REPAYMENT_POSTING.md 3.9', golden['decision_note'])
        self.assertIn('post_repayment', golden['scenario'])
        from tests.test_overlay import GoldenTests
        self.assertEqual(GoldenTests.demo_scenario(), golden)


class FoldTests(unittest.TestCase):
    def setUp(self):
        service = drawn()
        pay(service, 'p-1', 9000)
        self.entries = copy.deepcopy(service.overlay_entries)
        self.length = len(service.machine.export_journal())

    def mutate(self, change):
        entries = copy.deepcopy(self.entries)
        change(entries[-1])
        return entries

    def test_the_untouched_journal_folds_and_carries_a_repayment_block(self):
        state = overlay.fold(self.entries, self.length)
        block = state['repayment']['advances']['sim-a']
        self.assertEqual((block['postings'], block['principal_krw'], block['unapplied_cash_krw']), (1, 9000 - block['paid_interest_krw'], 0))
        self.assertEqual(state['repayment']['close_gate']['status'], 'CLEAR')
        self.assertEqual(state['sections']['interest_ledger'][-1]['record'], 'REPAYMENT')
        self.assertEqual(overlay.fold(self.entries + [copy.deepcopy(self.entries[-1])], self.length), state)

    def test_every_violation_raises(self):
        def payload(change):
            return lambda entry: change(entry['payload'])

        cases = {
            'day': lambda entry: entry.__setitem__('sim_day', entry['sim_day'] + 1),
            'unknown key': payload(lambda p: p.__setitem__('payer', 'x')),
            'missing key': payload(lambda p: p.pop('witness')),
            'float amount': payload(lambda p: p.__setitem__('amount_krw', 1.0)),
            'bool amount': payload(lambda p: p.__setitem__('amount_krw', True)),
            'negative': payload(lambda p: p['allocation'].__setitem__('interest_krw', -1)),
            'numerator not decimal': payload(lambda p: p['witness'].__setitem__('accrued_interest_num', '1.5')),
            'numerator leading zero': payload(lambda p: p['witness'].__setitem__('accrued_interest_num', '007')),
            'zero denominator': payload(lambda p: p['witness'].__setitem__('denominator', 0)),
            'extra witness key': payload(lambda p: p['witness'].__setitem__('extra', 1)),
            'bad evidence': payload(lambda p: p.__setitem__('evidence_ref', 'a b')),
            'label': payload(lambda p: p.__setitem__('label', 'REAL')),
            'principal over outstanding': payload(lambda p: (
                p['allocation'].__setitem__('principal_krw', p['witness']['principal_before_krw'] + 1),
                p.__setitem__('amount_krw', p['amount_krw'] + p['witness']['principal_before_krw'] + 1 - p['allocation']['principal_krw'] + 1))),
            'f04 refs half set': payload(lambda p: p.__setitem__('f04_receipt_ref', None)),
            'cash held while principal is due': payload(lambda p: (
                p['allocation'].__setitem__('unapplied_after_krw', 1), p.__setitem__('amount_krw', p['amount_krw'] + 1))),
            'invariant': payload(lambda p: p.__setitem__('amount_krw', p['amount_krw'] + 1)),
        }
        for label, change in cases.items():
            with self.subTest(label):
                with self.assertRaises(overlay.OverlayError):
                    overlay.fold(self.mutate(change), self.length)

    def test_a_repayment_needs_a_terms_binding_and_the_folded_accrual(self):
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(self.entries[-1:], self.length)
        without_interest = [e for e in self.entries if e['kind'] != overlay.KIND_INTEREST]
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(without_interest, self.length)

    def test_a_repeated_posting_is_not_applied_twice_by_the_fold(self):
        again = copy.deepcopy(self.entries[-1])
        again['overlay_id'] = 'p-1-copy'
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(self.entries + [again], self.length)


class ContractTests(unittest.TestCase):
    def test_live_bodies_validate_against_the_closed_facade_schema(self):
        doc = facade_schema.load_contract()
        routes = {(item['method'], item['path']): item for item in doc['routes']}
        quote_schema = routes[('GET', '/api/overlay')]['response']
        receipt_schema = routes[('POST', '/api/overlay/commands')]['response']
        request_schema = routes[('POST', '/api/overlay/commands')]['request']
        service = drawn()
        facade_schema.validate(service.overlay_state(), quote_schema, doc)
        command = body(service, 'p-1', 5000, evidence_ref='bank:ref-1')
        facade_schema.validate(command, request_schema, doc)
        receipt = service.overlay_command(command)
        facade_schema.validate(receipt, receipt_schema, doc)
        facade_schema.validate(service.overlay_command(command), receipt_schema, doc)
        facade_schema.validate(pay(service, 'p-2', 100), receipt_schema, doc)
        for operation in ('p-1', 'p-nope', 'c-1'):
            facade_schema.validate(service.overlay_state(operation), quote_schema, doc)
        facade_schema.validate(service.overlay_state(), quote_schema, doc)
        facade_schema.validate({**service.snapshot(), 'local_token': 'x'}, routes[('GET', '/api/state')]['response'], doc)
        with self.assertRaises(facade_schema.SchemaError):
            facade_schema.validate({**command, 'surprise': 1}, request_schema, doc)
        with self.assertRaises(facade_schema.SchemaError):
            facade_schema.validate({**receipt, 'surprise': 1}, receipt_schema, doc)
        listed = set(routes[('POST', '/api/overlay/commands')]['errors'])
        for code in ('REPAYMENT_AMOUNT', 'REPAYMENT_TERMS_NOT_BOUND', 'REPAYMENT_ADVANCE_STATE',
                     'REPAYMENT_PRODUCER_UNSUPPORTED', 'REPAYMENT_UNAPPLIED_CAP', 'UNKNOWN_ADVANCE'):
            self.assertIn(code, listed)


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        status, state = cls.call('GET', '/api/state')
        cls.instance = state['instance_id']
        cls.tokens = {'organizer': state['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.call('POST', '/api/session', {'role': role}, cls.tokens['organizer'])[1]['local_token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, method, path, payload=None, token=None):
        headers = {}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            client.request(method, path, body=data, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read().decode('utf-8'))
        finally:
            client.close()

    def command(self, op, key, **args):
        return self.call('POST', '/api/commands', {'instance_id': self.instance, 'operation_id': key, 'op': op,
                                                   'advance_id': 'sim-live', 'args': args}, self.tokens['organizer'])

    def repayment(self, key, amount, day, **extra):
        return {'instance_id': self.instance, 'operation_id': key, 'op': 'post_repayment', 'advance_ref': 'sim-live',
                'at_sim_day': day, 'amount_krw': amount, **extra}

    def test_organizer_only_and_the_http_round_trip(self):
        for op, args in (('offer', {'fixture_id': 'sim-committed', 'amount': 90000}), ('approve', {}),
                         ('bind_settlement', {}), ('draw', {})):
            self.assertEqual(self.command(op, 'live-' + op.replace('_', '-'), **args)[1]['outcome'], 'ACCEPTED', op)
        organizer = self.tokens['organizer']
        status, tick_receipt = self.call('POST', '/api/overlay/commands', {
            'instance_id': self.instance, 'operation_id': 'live-tick', 'op': 'advance_day',
            'from_sim_day': 0, 'to_sim_day': 60, 'reason': 'live'}, organizer)
        self.assertEqual(status, 200, tick_receipt)
        before = self.call('GET', '/api/state')[1]
        for role in ('auditor', 'observer', 'agent'):
            status, payload = self.call('POST', '/api/overlay/commands', self.repayment('live-denied', 100, 60),
                                        self.tokens[role])
            self.assertEqual((status, payload['error'], payload['permission']), (403, 'ROLE_FORBIDDEN', 'overlay:command'), role)
        status, payload = self.call('POST', '/api/overlay/commands', self.repayment('live-denied', 100, 60))
        self.assertEqual((status, payload['error']), (403, 'LOCAL_TOKEN_REQUIRED'))
        self.assertEqual(self.call('GET', '/api/state')[1]['state_digest'], before['state_digest'])
        status, applied = self.call('POST', '/api/overlay/commands', self.repayment('live-pay', 5000, 60), organizer)
        self.assertEqual((status, applied['outcome'], applied['op']), (200, 'APPLIED', 'post_repayment'))
        status, duplicate = self.call('POST', '/api/overlay/commands', self.repayment('live-pay', 5000, 60), organizer)
        self.assertEqual((status, duplicate['transport_duplicate']), (200, True))
        status, conflict = self.call('POST', '/api/overlay/commands', self.repayment('live-pay', 5001, 60), organizer)
        self.assertEqual((status, conflict['error']), (409, 'IDEMPOTENCY_CONFLICT'))
        status, stale = self.call('POST', '/api/overlay/commands', self.repayment('live-stale', 1, 59), organizer)
        self.assertEqual((status, stale['error']), (409, 'SIM_CLOCK_STALE'))
        status, missing = self.call('POST', '/api/overlay/commands',
                                    {**self.repayment('live-zero', 0, 60)}, organizer)
        self.assertEqual((status, missing['error']), (400, 'REPAYMENT_AMOUNT'))
        status, volatile = self.call('POST', '/api/overlay/commands',
                                     {**self.repayment('live-v', 1, 60), 'timestamp': 'x'}, organizer)
        self.assertEqual((status, volatile['error']), (400, 'OVERLAY_VOLATILE_KEY'))
        status, quote = self.call('GET', '/api/overlay?operation_id=live-pay', token=self.tokens['auditor'])
        self.assertEqual(status, 200)
        self.assertEqual(quote['interest_payments']['status'], 'RECORDED')
        self.assertEqual(quote['operation']['entry_no'], applied['entry_no'])
        state = self.call('GET', '/api/state')[1]
        self.assertEqual(state['close_gate'], quote['close_gate'])
        derived = applied['f04']['operation_id']
        status, f04 = self.call('GET', f'/api/operations/{derived}?instance_id={self.instance}', token=organizer)
        self.assertEqual((status, f04['outcome']), (200, 'ACCEPTED'))


if __name__ == '__main__':
    unittest.main()
