"""SIMULATED candidate postings, independent amounts, read fences and negative controls."""
import copy
import json
import threading
import unittest
from http.client import HTTPConnection

from capital import coa, margin, overlay, recon
from capital.auth import DEFAULT_ROLE, LocalRoleAuthorizer
from capital.producer import PinnedFsmProducer
from capital.projection import ProjectionError
from capital.server import make_server
from capital.service import CapitalService
from capital.store import canonical_bytes
from tests import facade_schema
from test_overlay import draw_book, formula, run, tick
from test_recovery import cmd, recover, seed
from test_repayment_posting import pay


def candidate(service):
    return service.projection('coa-candidate')


def selected(body, source, advance=None):
    return [entry for entry in body['entries'] if entry['source'] == source
            and (advance is None or entry['dimensions']['advance_id'] == advance)]


def amounts(entries):
    totals = {}
    for entry in entries:
        for line in entry['lines']:
            key = (line['account'], line['side'], line.get('interest_kind'))
            totals[key] = totals.get(key, 0) + line['amount']
    return totals


def combined(service=None, source=None):
    """One repaid advance and one default/recovery/write-off/late-recovery advance."""
    source = source or margin.ScenarioReplaySource()
    service = service or CapitalService(producer=PinnedFsmProducer(fixtures=source))
    draw_book(service, amount=45000)
    draw_book(service, advance='sim-b', amount=45000, prefix='b')
    tick(service, 'day10', 0, 10)
    run(service, 'default', 'sim-b', 'default-b')
    seed.distribute(source, 'sim-committed')
    tick(service, 'day20', 10, 20)
    service.overlay_command(recover(service, 100, ref='sim-b'))
    tick(service, 'stop', 20, 100)
    service.overlay_command(cmd(service, 'post_writeoff', 'writeoff-b', ref='sim-b',
                                setoff_declined_reason='SIMULATED_DECLINED'))
    service.overlay_command(recover(service, 100, key='late', ref='sim-b'))
    # Existing recovery quote replay requires recoveries before any repayment.
    # The two paths still coexist on the same book, without changing overlay.py.
    pay(service, 'payment-partial', 1000)
    tick(service, 'day110', 100, 110)
    maturity = min([60] + [e['payload']['maturity_after'] for e in service.overlay_entries
                           if e['kind'] == 'margin_acceleration' and e['payload']['advance_id'] == 'sim-a'])
    interest = formula(45000 * maturity, 700) + formula(45000 * (110 - maturity), 1000)
    pay(service, 'payment-full', 45000 + interest - 1000 + 50)
    return service


class PostingTests(unittest.TestCase):
    def assert_book(self, service):
        before = service._frozen()
        plain = (canonical_bytes(service.projection()), canonical_bytes(service.reconciliation()),
                 canonical_bytes(service.export_manifest()))
        body = candidate(service)
        report = service.reconciliation(None, 'coa-candidate')
        self.assertEqual(service._frozen(), before)
        self.assertEqual(plain, (canonical_bytes(service.projection()), canonical_bytes(service.reconciliation()),
                                 canonical_bytes(service.export_manifest())))
        self.assertTrue(body['balance_groups'])
        self.assertTrue(all(r['debit'] == r['credit'] for r in body['balance_groups']))
        self.assertTrue(all(r['matched'] for r in body['conservation']))
        self.assertEqual({r['id']: r['status'] for r in report['checks'] if r['id'] in recon.COA_CHECK_IDS},
                         dict.fromkeys(recon.COA_CHECK_IDS, 'MATCHED'))
        self.assertEqual(body['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        for label in ('tax', 'legal', 'operating_ledger'):
            self.assertEqual(body[label], 'NOT_BOUND')
        self.assertFalse(body['policy_adopted'])
        self.assertFalse(body['funds_executed'])
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertTrue(all(not row['adopted_in_note'] for row in body['chart_status']
                            if row['code'] in coa.CANDIDATE_ONLY))
        contract = facade_schema.load_contract()
        for path, value in (('/api/projection', body), ('/api/reconciliation', report)):
            route = next(r for r in contract['routes'] if r['path'] == path and r['method'] == 'GET')
            facade_schema.validate(value, route['response'], contract)
        return body

    def test_payment_partial_then_payoff_and_unapplied_cash(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'day10', 0, 10)
        pay(service, 'partial', 70)
        self.assertEqual(amounts(selected(self.assert_book(service), 'OVERLAY_REPAYMENT')),
                         {('1000', 'debit', 'CONTRACT'): 70, ('1110', 'credit', 'CONTRACT'): 70})
        tick(service, 'day20', 10, 20)
        interest = formula(90000 * 20, 700)
        pay(service, 'payoff', 90000 + interest - 70)
        pay(service, 'overpay', 50)
        body = self.assert_book(service)
        self.assertEqual(amounts(selected(body, 'OVERLAY_REPAYMENT')),
                         {('1000', 'debit', 'CONTRACT'): interest, ('1110', 'credit', 'CONTRACT'): interest,
                          ('9810', 'debit', None): 50, ('9890', 'credit', None): 50})
        by = {r['code']: r for r in body['accounts']}
        self.assertEqual(by['1100']['credit_total'], 90000)  # Principal is posted only by F04.
        self.assertEqual(by['1110']['balance'], 0)
        self.assertEqual(by['9810']['balance'], 50)
        pay(service, 'held-no-change', 0)
        self.assertEqual(amounts(selected(self.assert_book(service), 'OVERLAY_REPAYMENT')),
                         amounts(selected(body, 'OVERLAY_REPAYMENT')))
        self.assertTrue(coa.totals_match_v1(body, service.projection()))

    def test_combined_book_has_all_checks_matched_and_exact_writeoff_legs(self):
        service = combined()
        body = self.assert_book(service)
        self.assertEqual(service.reconciliation(None, 'coa-candidate')['status'], 'MATCHED')
        self.assertEqual(service.machine.view('sim-a')['outstanding_exposure'], 0)
        recognized = formula(45000 * 10, 700)
        suspended = formula(45000 * 90, 1000)
        self.assertEqual(amounts(selected(body, 'OVERLAY_RECOVERY', 'sim-b')),
                         {('1000', 'debit', 'DEFAULT'): 100, ('4110', 'credit', 'DEFAULT'): 100,
                          ('9790', 'debit', 'DEFAULT'): 100, ('9700', 'credit', 'DEFAULT'): 100,
                          ('1000', 'debit', None): 100, ('4300', 'credit', None): 100})
        self.assertEqual(amounts(selected(body, 'OVERLAY_WRITEOFF', 'sim-b')),
                         {('5200', 'debit', None): 45000, ('1100', 'credit', None): 45000,
                          ('4100', 'debit', 'CONTRACT'): recognized, ('1110', 'credit', 'CONTRACT'): recognized,
                          ('9790', 'debit', 'DEFAULT'): suspended - 100,
                          ('9700', 'credit', 'DEFAULT'): suspended - 100})
        for code in ('1110', '9700'):
            rows = [r for r in body['subledger'] if r['code'] == code and r['advance_id'] == 'sim-b']
            self.assertTrue(all(r['debit_total'] == r['credit_total'] for r in rows))
        self.assertTrue(coa.totals_match_v1(body, service.projection(), service.overlay_entries))
        self.assertFalse(coa.totals_match_v1(body, service.projection()))
        status = {r['code']: r['status'] for r in body['chart_status']}
        self.assertEqual((status['4300'], status['5200']), ('POSTED', 'POSTED'))
        self.assertTrue(all(status[c] == 'NOT_RECORDED' for c in ('1190', '3100', '3200', '5100')))

    def test_seeded_disposable_recovery_book_and_principal_conservation(self):
        service, _ = seed.build()
        body = self.assert_book(service)
        # Seed: 48,000 drawn, 5,000 recovered, 1,000 recovered after write-off.
        contract = formula(48000 * 8, 700)
        default = formula(48000 * 11, 1000)
        principal_paid = 5000 - contract - default
        self.assertEqual(amounts(selected(body, 'OVERLAY_RECOVERY'))[('1100', 'credit', None)], principal_paid)
        self.assertEqual(amounts(selected(body, 'OVERLAY_WRITEOFF'))[('5200', 'debit', None)], 48000 - principal_paid)
        self.assertEqual(amounts(selected(body, 'OVERLAY_RECOVERY'))[('4300', 'credit', None)], 1000)
        self.assertEqual({r['code']: r['balance'] for r in body['accounts']}['1110'], 0)
        # The disposable source changed since offer; the pre-existing fixture check is outside this node.
        self.assertEqual(next(r['status'] for r in service.reconciliation()['checks']
                              if r['id'] == 'fixtures_digest'), 'RECON_MISMATCH')

    def test_oldest_recognized_default_interest_is_paid_before_suspended_default(self):
        source = margin.ScenarioReplaySource()
        service = CapitalService(producer=PinnedFsmProducer(fixtures=source))
        draw_book(service)
        tick(service, 'day70', 0, 70)
        run(service, 'default', 'sim-a', 'default')
        tick(service, 'day80', 70, 80)
        seed.distribute(source, 'sim-committed')
        service.overlay_command(recover(service, 300))
        recognized = formula(90000 * 10, 1000)
        got = amounts(selected(self.assert_book(service), 'OVERLAY_RECOVERY'))
        self.assertEqual(got, {('1000', 'debit', 'DEFAULT'): 300,
                              ('1110', 'credit', 'DEFAULT'): recognized,
                              ('4110', 'credit', 'DEFAULT'): 300 - recognized,
                              ('9790', 'debit', 'DEFAULT'): 300 - recognized,
                              ('9700', 'credit', 'DEFAULT'): 300 - recognized})

    def test_payment_after_maturity_has_both_interest_kinds(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'day70', 0, 70)
        interest, default = formula(90000 * 60, 700), formula(90000 * 10, 1000)
        pay(service, 'all-interest', interest + default)
        self.assertEqual(amounts(selected(self.assert_book(service), 'OVERLAY_REPAYMENT')),
                         {('1000', 'debit', 'CONTRACT'): interest, ('1110', 'credit', 'CONTRACT'): interest,
                          ('1000', 'debit', 'DEFAULT'): default, ('1110', 'credit', 'DEFAULT'): default})

    def test_writeoff_reverses_recognized_default_as_well_as_contract(self):
        source = margin.ScenarioReplaySource()
        service = CapitalService(producer=PinnedFsmProducer(fixtures=source))
        draw_book(service)
        tick(service, 'day70', 0, 70)
        run(service, 'default', 'sim-a', 'default')
        tick(service, 'stop', 70, 160)
        service.overlay_command(cmd(service, 'post_writeoff', 'wo'))
        body = self.assert_book(service)
        got = amounts(selected(body, 'OVERLAY_WRITEOFF'))
        self.assertEqual(got[('4110', 'debit', 'DEFAULT')], formula(90000 * 10, 1000))
        self.assertEqual(got[('4100', 'debit', 'CONTRACT')], formula(90000 * 60, 700))
        self.assertTrue(all(r['balance'] == 0 for r in body['accounts'] if r['code'] in ('1110', '9700')))

    def test_http_candidate_gets_on_a_combined_book(self):
        source = margin.ScenarioReplaySource()
        auth = LocalRoleAuthorizer()
        server = make_server(0, authorizer=auth, producer=PinnedFsmProducer(fixtures=source))
        worker = threading.Thread(target=server.serve_forever)
        try:
            combined(server.service, source)
            before = server.service._frozen()
            worker.start()
            for path in ('/api/projection?mode=coa-candidate', '/api/reconciliation?mode=coa-candidate'):
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    client.request('GET', path, headers={'X-Capital-Token': auth.token_for(DEFAULT_ROLE)})
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    result = json.loads(response.read())
                    if path.startswith('/api/projection'):
                        self.assertEqual(set(e['source'] for e in result['entries']) & set(coa.NEW_SOURCES),
                                         set(coa.NEW_SOURCES))
                    else:
                        self.assertEqual(result['status'], 'MATCHED')
                finally:
                    client.close()
            self.assertEqual(server.service._frozen(), before)
        finally:
            if worker.is_alive():
                server.shutdown()
                worker.join()
            server.server_close()


class ReconciliationNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = combined()
        cls.good = candidate(cls.service)

    def test_empty_book_checks_match(self):
        empty = candidate(CapitalService())
        for check in (coa.payments_match_ledger, coa.recoveries_match_ledger, coa.writeoffs_match_ledger):
            self.assertTrue(check(empty, []))
            self.assertFalse(check({}, []))
            self.assertFalse(check(empty, [{'invalid': True}]))

    def test_each_check_rejects_changed_amount_and_missing_entry(self):
        for source, account, check in (('OVERLAY_REPAYMENT', '1110', coa.payments_match_ledger),
                                        ('OVERLAY_RECOVERY', '4300', coa.recoveries_match_ledger),
                                        ('OVERLAY_WRITEOFF', '5200', coa.writeoffs_match_ledger)):
            with self.subTest(source=source):
                bad = copy.deepcopy(self.good)
                next(line for e in selected(bad, source) for line in e['lines'] if line['account'] == account)['amount'] += 1
                self.assertFalse(check(bad, self.service.overlay_entries))
                bad = copy.deepcopy(self.good)
                bad['entries'] = [e for e in bad['entries'] if e['source'] != source]
                bad['accounts'], bad['subledger'] = coa._aggregate(bad['entries'])
                self.assertFalse(check(bad, self.service.overlay_entries))

    def test_changed_interest_kind_rejected_for_payments_and_recoveries(self):
        for source, check in (('OVERLAY_REPAYMENT', coa.payments_match_ledger),
                              ('OVERLAY_RECOVERY', coa.recoveries_match_ledger)):
            bad = copy.deepcopy(self.good)
            line = next(line for e in selected(bad, source) for line in e['lines']
                        if line['account'] in ('1110', '4110') and line['side'] == 'credit')
            line['interest_kind'] = 'DEFAULT' if line['interest_kind'] == 'CONTRACT' else 'CONTRACT'
            self.assertFalse(check(bad, self.service.overlay_entries))

    def ghost(self, body, advance='sim-ghost', source='OVERLAY_RECOVERY'):
        bad = copy.deepcopy(body)
        bad['entries'].append({'step': len(bad['entries']) + 1, 'source': source, 'txn_id': 'sim-ghost',
                               'dimensions': coa._dimensions('fiat:KRW', advance, None, 0, 'NOT_BOUND'),
                               'lines': [coa._line('1000', 'debit', 100), coa._line('4300', 'credit', 100)]})
        bad['accounts'], bad['subledger'] = coa._aggregate(bad['entries'])
        return bad

    def test_extra_late_recovery_against_empty_overlay_is_rejected_only_by_recovery_check(self):
        service = CapitalService()
        bad = self.ghost(candidate(service))
        self.assertFalse(coa.recoveries_match_ledger(bad, []))
        self.assertTrue(coa.totals_match_v1(bad, service.projection()))

    def test_ghost_advance_and_wrong_source_and_unknown_source_on_real_fold(self):
        for advance, source in (('sim-ghost', 'OVERLAY_RECOVERY'), ('sim-b', 'OVERLAY_REPAYMENT'),
                                ('sim-b', 'UNKNOWN'), ('sim-b', 'OVERLAY_INTEREST')):
            with self.subTest(advance=advance, source=source):
                bad = self.ghost(self.good, advance, source)
                self.assertFalse(coa.recoveries_match_ledger(bad, self.service.overlay_entries))

    def test_unexpected_payment_and_writeoff_advances_are_rejected(self):
        for source, check in (('OVERLAY_REPAYMENT', coa.payments_match_ledger),
                              ('OVERLAY_WRITEOFF', coa.writeoffs_match_ledger)):
            bad = copy.deepcopy(self.good)
            for entry in selected(bad, source):
                entry['dimensions']['advance_id'] = 'sim-ghost'
            self.assertFalse(check(bad, self.service.overlay_entries))

    def test_special_account_rows_are_guarded(self):
        for code in ('4300', '5200', '9810', '9890'):
            bad = copy.deepcopy(self.good)
            next(r for r in bad['accounts'] if r['code'] == code)['credit_total'] += 1
            self.assertFalse(coa.recoveries_match_ledger(bad, self.service.overlay_entries))

    def test_unmapped_account_or_missing_advance_fails_closed(self):
        for mutation in ('missing_advance', 'unmapped_account'):
            bad = copy.deepcopy(self.good)
            entry = selected(bad, 'OVERLAY_RECOVERY')[0]
            if mutation == 'missing_advance':
                entry['dimensions']['advance_id'] = None
            else:
                entry['lines'].append(coa._line('4200', 'credit', 1))
            for check in (coa.payments_match_ledger, coa.recoveries_match_ledger, coa.writeoffs_match_ledger):
                self.assertFalse(check(bad, self.service.overlay_entries))

    def test_v1_adjustment_requires_actual_recovery_and_writeoff_credits(self):
        bad = copy.deepcopy(self.good)
        # Forged account rows alone cannot justify the reduction adjustment.
        bad['entries'] = [e for e in bad['entries'] if e['source'] != 'OVERLAY_WRITEOFF']
        self.assertFalse(coa.totals_match_v1(bad, self.service.projection(), self.service.overlay_entries))
        self.assertFalse(coa.totals_match_v1(self.good, self.service.projection(), [{'invalid': True}]))

    def test_projection_rejects_invalid_cash_and_writeoff_amounts(self):
        # Fold validation is independent of the candidate's posting pass.
        for source_kind, field in (('RECOVERY', 'amount_krw'), ('WRITEOFF', 'accrued_interest_reversed_krw'),
                                   ('WRITEOFF', 'suspended_interest_released_krw')):
            entries = copy.deepcopy(self.service.overlay_entries)
            next(e for e in entries if e['kind'] == source_kind)['payload'][field] += 1
            with self.assertRaises(ProjectionError):
                coa.CoaCandidateProjection().project(self.service.machine.export_journal(), [], overlay_entries=entries)

    def test_open_interest_never_overdraws_and_writeoff_totals_are_verified(self):
        for operation in ('cash', 'reversed', 'released'):
            opened = coa._Open()
            opened.accrue('sim-a', {'posted_contract_krw': 10, 'posted_default_krw': 0}, False)
            with self.assertRaises(ProjectionError):
                if operation == 'cash':
                    opened.cash('sim-a', {'interest_krw': 11, 'default_interest_krw': 0})
                else:
                    opened.writeoff('sim-a', {'accrued_interest_reversed_krw': 11 if operation == 'reversed' else 10,
                                              'suspended_interest_released_krw': 1 if operation == 'released' else 0})
