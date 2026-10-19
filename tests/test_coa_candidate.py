"""CAPITAL-COA-V1 candidate projection (SIMULATION_FIXED_V2): additive, SIMULATED, SYNTHETIC_UNADOPTED.

Expected interest is recomputed here from the CAPITAL-TERMS-V1 block through the test_overlay
helpers, never read back from the code under test. The chart is fenced against the
CAPITAL_ACCOUNTS_TAX_LEGAL note.
"""
import copy
import importlib.util
import json
import subprocess
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital import assets, coa, projection, recon
from capital.auth import ROLES
from capital.store import canonical_bytes as canonical_json
from capital.projection import ProjectionError
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.terms import read_decision_block
from test_overlay import draw_book, formula, run, tick, tier, row

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_ACCOUNTS_TAX_LEGAL.md'
_SPEC = importlib.util.spec_from_file_location('facade_schema', ROOT / 'tests' / 'facade_schema.py')
facade_schema = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(facade_schema)
USD = {'namespace': 'fiat', 'reference': 'USD', 'decimals': 2, 'max_atoms': 1_000_000_000_000}


def note_value():
    return read_decision_block(NOTE)['entries']['chart_of_accounts_mapping']['value']


def candidate(service):
    return service.projection('coa-candidate')


def by_code(body):
    return {row['code']: row for row in body['accounts']}


def lines(body, code):
    return [(entry, line) for entry in body['entries'] for line in entry['lines'] if line['account'] == code]


def total(body, code, side):
    return sum(line['amount'] for _, line in lines(body, code) if line['side'] == side)


class ChartFenceTests(unittest.TestCase):
    def test_chart_literal_equals_the_note_accounts_table(self):
        note = {row['code']: (row['name'], row['class'], row['normal']) for row in note_value()['accounts']}
        self.assertEqual(len(note), 23)
        self.assertEqual({code: spec for code, spec in coa.CHART.items() if code not in coa.CANDIDATE_ONLY}, note)
        self.assertEqual(set(coa.CHART) - set(note), {'9790'})
        self.assertEqual(coa.CHART['9790'][2], 'credit')
        self.assertEqual(coa.CHART['9700'][2], 'debit')

    def test_codes_are_four_digits_and_dimensions_are_not_in_the_code(self):
        self.assertTrue(all(len(code) == 4 and code.isdigit() for code in coa.CHART))
        self.assertEqual(note_value()['chart_version'], coa.COA_VERSION)
        self.assertEqual(coa.CHART_VERSION, 'SIMULATION_FIXED_V2')

    def test_every_v1_account_maps_to_exactly_one_coa_code(self):
        mapping = note_value()['v1_account_mapping']
        self.assertEqual(set(mapping), set(projection._CHART))
        self.assertEqual(set(coa.V1_TO_COA), set(projection._CHART))
        for prefix, code in coa.V1_TO_COA.items():
            with self.subTest(v1=prefix):
                self.assertIn(code, coa.CHART)
                self.assertEqual(mapping[prefix][:4], code)
                self.assertEqual(type(code), str)
        # the mapping is a function: one code per V1 account (dict keys are unique by construction)
        self.assertEqual(len(coa.V1_TO_COA), len(projection._CHART))

    def test_v1_sides_survive_the_mapping_on_a_real_book(self):
        service = CapitalService()
        draw_book(service)
        run(service, 'repay', 'sim-a', 'a-repay', amount=10000, sequence=1)
        v1 = service.projection(None)
        coa_body = candidate(service)
        v1_sides = [(line['account'].split(':', 1)[0], line['side'], line['amount'])
                    for entry in v1['entries'] for line in entry['lines']]
        mapped = [(coa.V1_TO_COA[prefix], side, amount) for prefix, side, amount in v1_sides]
        got = [(line['account'], line['side'], line['amount'])
               for entry in coa_body['entries'] if entry['source'] != 'OVERLAY_INTEREST' for line in entry['lines']]
        self.assertEqual(got, mapped)

    def test_chart_status_covers_the_whole_chart(self):
        body = candidate(CapitalService())
        status = {row['code']: row['status'] for row in body['chart_status']}
        self.assertEqual(set(status), set(coa.CHART))
        self.assertEqual(status['9150'], 'DERIVED_MEMO')
        self.assertEqual(status['9160'], 'DERIVED_MEMO')
        self.assertEqual(status['1190'], 'NOT_RECORDED')
        self.assertEqual(status['4200'], 'ZERO_FEE_PLACEHOLDER')
        self.assertEqual(status['1300'], 'NOT_MODELED_V1_FIELD_RESERVED')
        self.assertEqual(status['9200'], 'NOT_POSTED')


class V1UnchangedTests(unittest.TestCase):
    def test_v1_response_bytes_do_not_move_across_candidate_calls_and_ticks(self):
        service = CapitalService()
        draw_book(service)
        first = canonical_json(service.projection(None))
        again = canonical_json(service.projection('simulation'))
        self.assertEqual(first, again)
        tick(service, 'c1', 0, 10)
        candidate(service)
        service.reconciliation(None, 'coa-candidate')
        self.assertEqual(canonical_json(service.projection(None)), first)

    def test_v1_and_golden_files_are_untouched(self):
        # Diff against main, not HEAD: files other nodes changed on main are not this node's edits.
        # overlay.py and overlay_demo.json belong to the overlay-repayment-posting node (repayment entry kind,
        # one regeneration cited in CAPITAL_REPAYMENT_POSTING.md 3.9); demo.json and overlay_empty.json stay locked.
        # Other goldens are compared key by key below; the T05-sim/T06-sim pins are new files owned by
        # scripts/sim_journeys.py (--update-golden) and compared to a live run by tests/test_sim_journeys.py.
        guarded = ['capital/projection.py', 'capital/ports.py', 'capital/export.py',
                   'tests/golden/demo.json', 'tests/golden/overlay_empty.json',
                   'capital/vendor', '.aiops', 'docs/decisions']
        probe = subprocess.run(['git', 'rev-parse', '--verify', '-q', 'origin/main'], cwd=ROOT,
                               capture_output=True, text=True)
        base = 'origin/main' if probe.returncode == 0 else 'HEAD'
        status = subprocess.run(['git', 'diff', '--name-only', base, '--', *guarded],
                                cwd=ROOT, capture_output=True, text=True)
        if status.returncode != 0:
            self.skipTest('git unavailable')
        changed = status.stdout.split()
        if base == 'origin/main' and changed:
            # A guarded file that main added after this branch's merge point, and that the working tree has
            # never had, is another node's addition, not an edit or a deletion made here. A file this branch
            # does hold, or did hold at its merge point, is still compared byte-for-byte against main.
            merge_base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/main'], cwd=ROOT,
                                        capture_output=True, text=True)
            if merge_base.returncode == 0:
                added_on_main = subprocess.run(
                    ['git', 'diff', '--name-only', '--diff-filter=A', merge_base.stdout.strip(), 'origin/main',
                     '--', *guarded],
                    cwd=ROOT, capture_output=True, text=True)
                if added_on_main.returncode == 0:
                    absent = set(added_on_main.stdout.split())
                    changed = [path for path in changed if path not in absent or (ROOT / path).exists()]
        self.assertEqual(changed, [])
        # Goldens: every value pinned on the base stays equal and no golden disappears. Another node may
        # add a key through its explicit regeneration path (seed_demo.py --update-golden adds `risk` to
        # demo.json), but no V1 pin -- state_digest, projection totals, content_digest, cases -- moves.
        listed = subprocess.run(['git', 'ls-tree', '--name-only', base, 'tests/golden/'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(listed.returncode, 0)
        names = listed.stdout.split()
        self.assertIn('tests/golden/demo.json', names)
        # overlay_demo.json is this node's one sanctioned regeneration (see the comment above); its pins are
        # the live reproductions in test_overlay.GoldenTests and test_repayment_posting, not the base values.
        names = [name for name in names if name != 'tests/golden/overlay_demo.json']
        if base == 'origin/main':
            # A golden that main added after this branch's merge point is another node's file; the merge
            # cannot contain it, so it is pinned when a worktree holds it, not here. A golden this branch
            # does hold, or did hold at its merge point, is still compared against main.
            merge_base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/main'], cwd=ROOT,
                                        capture_output=True, text=True)
            if merge_base.returncode == 0:
                added_on_main = subprocess.run(
                    ['git', 'diff', '--name-only', '--diff-filter=A', merge_base.stdout.strip(), 'origin/main',
                     '--', 'tests/golden/'],
                    cwd=ROOT, capture_output=True, text=True)
                if added_on_main.returncode == 0:
                    absent = set(added_on_main.stdout.split())
                    names = [name for name in names if name not in absent or (ROOT / name).exists()]
        for name in names:
            shown = subprocess.run(['git', 'show', f'{base}:{name}'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(shown.returncode, 0, name)
            pinned = json.loads(shown.stdout)
            current = json.loads((ROOT / name).read_text(encoding='utf-8'))
            self.assertIsInstance(current, dict, name)
            for key, value in pinned.items():
                self.assertIn(key, current, f'{name} ${key} dropped against {base}')
                self.assertEqual(current[key], value, f'{name} ${key} moved against {base}')

    def test_default_reconciliation_still_has_the_six_checks(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        for mode in (None, 'simulation'):
            checks = [check['id'] for check in service.reconciliation(None, mode)['checks']]
            # A non-empty overlay adds main's overlay fold check; the COA checks stay opt-in.
            self.assertEqual(tuple(checks), recon.CHECK_IDS + (recon.OVERLAY_CHECK_ID,))
        self.assertNotIn('coa_candidate', service.reconciliation())
        self.assertEqual(len(recon.CHECK_IDS), 6)

    def test_unknown_modes_stay_not_bound(self):
        service = CapitalService()
        for mode in ('operating-ledger', 'COA-CANDIDATE', 'coa-candidate ', '', ['coa-candidate']):
            for call in (service.projection, lambda m: service.reconciliation(None, m)):
                with self.assertRaises(ApiError) as caught:
                    call(mode)
                self.assertEqual(caught.exception.code, 'NOT_BOUND')


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        draw_book(self.service)
        self.journal = self.service.machine.export_journal()
        self.evidence = [self.service.fixtures.view(key) for key in sorted(self.service.fixtures.projection_ids)]

    def test_krw_is_the_declared_assetspec(self):
        body = candidate(self.service)
        self.assertEqual(body['assets'], [assets.KRW])
        self.assertEqual({entry['dimensions']['asset'] for entry in body['entries']}, {'fiat:KRW'})
        port = coa.CoaCandidateProjection()
        self.assertEqual(port.project(self.journal, self.evidence, asset=dict(assets.KRW))['assets'], [assets.KRW])

    def test_a_fake_non_krw_asset_is_rejected_asset_mismatch(self):
        port = coa.CoaCandidateProjection()
        for fake in (USD, 'KRW', {**assets.KRW, 'decimals': 2}, {**assets.KRW, 'reference': 'USD'}, {**assets.KRW, 'extra': 1}):
            with self.subTest(asset=fake):
                with self.assertRaises(ProjectionError) as caught:
                    port.project(self.journal, self.evidence, asset=fake)
                self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')

    def test_a_posting_in_a_non_declared_asset_is_rejected(self):
        body = candidate(self.service)
        bad = copy.deepcopy(body['entries'])
        for entry in bad:
            entry['dimensions']['asset'] = 'fiat:USD'
        with self.assertRaises(ProjectionError) as caught:
            coa.check_entries(bad)
        self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')

    def test_a_mixed_asset_entry_with_equal_sums_is_rejected(self):
        entry = {'dimensions': {'asset': 'fiat:KRW', 'sim_day': 0}, 'lines': [
            {'account': '1100', 'side': 'debit', 'amount': 100, 'asset': 'fiat:KRW'},
            {'account': '1000', 'side': 'credit', 'amount': 100, 'asset': 'fiat:USD'}]}
        with self.assertRaises(ProjectionError) as caught:
            coa.check_entries([entry])
        self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')
        entry['lines'][1]['asset'] = 'fiat:KRW'
        self.assertEqual(coa.check_entries([entry])[0]['matched'], True)

    def test_an_unbalanced_entry_is_a_projection_invariant(self):
        entry = {'dimensions': {'asset': 'fiat:KRW', 'sim_day': 0}, 'lines': [
            {'account': '1100', 'side': 'debit', 'amount': 100}, {'account': '1000', 'side': 'credit', 'amount': 99}]}
        with self.assertRaises(ProjectionError) as caught:
            coa.check_entries([entry])
        self.assertEqual(caught.exception.code, 'PROJECTION_INVARIANT')


class BalanceTests(unittest.TestCase):
    def test_debit_equals_credit_per_asset_per_sim_day_recomputed_from_entries(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        run(service, 'repay', 'sim-a', 'a-repay', amount=20000, sequence=1)
        tick(service, 'c2', 10, 25)
        body = candidate(service)
        groups = {}
        for entry in body['entries']:
            dims = entry['dimensions']
            for line in entry['lines']:
                cell = groups.setdefault((dims['asset'], dims['sim_day']), {'debit': 0, 'credit': 0})
                cell[line['side']] += line['amount']
        self.assertEqual({(g['asset'], g['sim_day']) for g in body['balance_groups']}, set(groups))
        self.assertIn(('fiat:KRW', 10), groups)
        self.assertIn(('fiat:KRW', 25), groups)
        for group in body['balance_groups']:
            expected = groups[(group['asset'], group['sim_day'])]
            self.assertEqual((group['debit'], group['credit']), (expected['debit'], expected['credit']))
            self.assertEqual(group['debit'], group['credit'])
            self.assertTrue(group['matched'])
        self.assertTrue(all(row['matched'] for row in body['conservation']))
        accounts = body['accounts']
        self.assertEqual(sum(a['debit_total'] for a in accounts), sum(a['credit_total'] for a in accounts))

    def test_labels_and_derived_memos(self):
        service = CapitalService()
        draw_book(service)
        run(service, 'repay', 'sim-a', 'a-repay', amount=20000, sequence=1)
        body = candidate(service)
        self.assertEqual(body['mode'], 'LOCAL_PROJECTION_COA_CANDIDATE')
        self.assertEqual((body['chart'], body['coa_version']), ('SIMULATION_FIXED_V2', 'CAPITAL-COA-V1'))
        self.assertEqual((body['accounting_policy'], body['tax'], body['legal'], body['operating_ledger']),
                         ('SYNTHETIC_UNADOPTED', 'NOT_BOUND', 'NOT_BOUND', 'NOT_BOUND'))
        self.assertIs(body['policy_adopted'], False)
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertEqual(body['cut'], service.machine.state_digest())
        self.assertEqual(body['memo_balances'], {'9150': 70000, '9160': 20000})
        self.assertEqual(by_code(body)['1100']['balance'], 70000)
        # 1000 is a contra memo: a draw credits it and a repayment debits it
        self.assertEqual((by_code(body)['1000']['debit_total'], by_code(body)['1000']['credit_total']), (20000, 90000))

    def test_dimensions_ride_on_entries_not_in_codes(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        body = candidate(service)
        for entry in body['entries']:
            self.assertEqual(set(entry['dimensions']),
                             {'asset', 'advance_id', 'claim_id', 'sim_day', 'chart_version', 'terms_version'})
            self.assertEqual(entry['dimensions']['chart_version'], 'SIMULATION_FIXED_V2')
            for line in entry['lines']:
                self.assertNotIn(':', line['account'])
                self.assertIn(line['account'], coa.CHART)
        interest = [entry for entry in body['entries'] if entry['source'] == 'OVERLAY_INTEREST']
        self.assertEqual(len(interest), 1)
        self.assertEqual(interest[0]['dimensions']['advance_id'], 'sim-a')
        self.assertEqual(interest[0]['dimensions']['sim_day'], 10)
        self.assertEqual(interest[0]['dimensions']['terms_version'], service.terms.status()['terms_version'])
        draws = [e for e in body['entries'] if e['source'] == 'JOURNAL' and e['lines'][0]['account'] == '1100']
        self.assertEqual(draws[0]['dimensions']['claim_id'], 'sim-committed')
        self.assertTrue(any(row['advance_id'] == 'sim-a' and row['code'] == '1100' for row in body['subledger']))

    def test_empty_overlay_and_unbound_terms_post_no_interest(self):
        service = CapitalService()
        draw_book(service)
        body = candidate(service)
        self.assertEqual({e['dimensions']['terms_version'] for e in body['entries'] if e['source'] == 'JOURNAL'}, {'NOT_BOUND'})
        self.assertFalse([e for e in body['entries'] if e['source'] == 'OVERLAY_INTEREST'])
        self.assertTrue({'1110', '4100', '4110', '9700', '9790'}.isdisjoint(by_code(body)))
        self.assertEqual(body['sim_day'], 0)

    def test_empty_book_is_a_valid_candidate(self):
        body = candidate(CapitalService())
        self.assertEqual(body['mode'], 'LOCAL_PROJECTION_COA_CANDIDATE')
        self.assertTrue(all(row['matched'] for row in body['conservation']))


class InterestTests(unittest.TestCase):
    def test_ten_days_post_1110_debit_and_4100_credit(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        body = candidate(service)
        expected = formula(90000 * 10, tier('T1')['all_in_bps_annual'])
        self.assertEqual(expected, 172)
        accounts = by_code(body)
        self.assertEqual((accounts['1110']['debit_total'], accounts['1110']['credit_total']), (expected, 0))
        self.assertEqual((accounts['4100']['credit_total'], accounts['4100']['debit_total']), (expected, 0))
        self.assertTrue({'4110', '9700', '9790'}.isdisjoint(accounts))
        self.assertEqual(total(body, '1110', 'debit'), row(service)['interest_due_krw'])
        for entry, line in lines(body, '1110'):
            self.assertEqual((entry['source'], line['interest_kind']), ('OVERLAY_INTEREST', 'CONTRACT'))

    def test_default_interest_after_maturity_while_performing_goes_to_4110(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        tick(service, 'c2', 10, 75)
        body = candidate(service)
        bps = tier('T1')['all_in_bps_annual']
        accounts = by_code(body)
        self.assertEqual(accounts['4100']['credit_total'], row(service)['interest_due_krw'])
        self.assertEqual(accounts['4110']['credit_total'], row(service)['default_interest_due_krw'])
        self.assertGreater(accounts['4110']['credit_total'], 0)
        self.assertEqual(accounts['1110']['debit_total'], accounts['4100']['credit_total'] + accounts['4110']['credit_total'])
        self.assertEqual(accounts['4100']['credit_total'], formula(90000 * 60, bps))
        self.assertTrue({'9700', '9790'}.isdisjoint(accounts))

    def test_accrual_after_default_goes_to_the_9700_memo_not_4100(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        self.assertEqual(run(service, 'default', 'sim-a', 'a-default')['outcome'], 'ACCEPTED')
        tick(service, 'c2', 10, 20)
        body = candidate(service)
        bps = tier('T1')['all_in_bps_annual']
        first = formula(90000 * 10, bps)
        second = row(service)['interest_due_krw'] - first
        self.assertGreater(second, 0)
        accounts = by_code(body)
        # before DEFAULTED: income. After: the memo only, and income does not grow.
        self.assertEqual(accounts['4100']['credit_total'], first)
        self.assertEqual(accounts['1110']['debit_total'], first)
        self.assertEqual(accounts['9700']['debit_total'], second)
        self.assertEqual(accounts['9790']['credit_total'], second)
        self.assertEqual(accounts['9700']['normal'], 'debit')
        for entry, line in lines(body, '9700'):
            self.assertEqual(entry['dimensions']['sim_day'], 20)
        self.assertEqual(coa.CHART['9700'][0], 'MEMO_SUSPENDED_INTEREST_AFTER_DEFAULT')

    def test_demo_book_defaulted_advance_is_memo_and_a_performing_one_is_income(self):
        service = CapitalService()
        for advance, fixture, prefix in (('sim-defaulted', 'sim-committed', 'd'), ('sim-unbound', 'sim-committed', 'u')):
            run(service, 'offer', advance, f'{prefix}-offer', fixture_id=fixture, amount=40000)
            run(service, 'approve', advance, f'{prefix}-approve')
            run(service, 'bind_settlement', advance, f'{prefix}-bind')
            run(service, 'draw', advance, f'{prefix}-draw')
        run(service, 'default', 'sim-defaulted', 'd-default')
        tick(service, 'c1', 0, 10)
        body = candidate(service)
        for entry, line in lines(body, '9700'):
            self.assertEqual(entry['dimensions']['advance_id'], 'sim-defaulted')
        for entry, line in lines(body, '4100'):
            self.assertEqual(entry['dimensions']['advance_id'], 'sim-unbound')
        self.assertGreater(total(body, '9700', 'debit'), 0)
        self.assertGreater(total(body, '4100', 'credit'), 0)
        self.assertEqual(service.reconciliation(None, 'coa-candidate')['status'], 'MATCHED')


class MemoOnlyTests(unittest.TestCase):
    def test_settlement_claim_face_appears_only_in_9100_and_9110(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        body = candidate(service)
        evidence = [entry for entry in body['entries'] if entry['source'] == 'EVIDENCE']
        self.assertTrue(evidence)
        for entry in evidence:
            self.assertEqual(entry['dimensions']['advance_id'], None)
            self.assertEqual({line['account'] for line in entry['lines']} - {'9100', '9110'}, set())
        others = [entry for entry in body['entries'] if entry['source'] != 'EVIDENCE']
        for entry in others:
            self.assertFalse({line['account'] for line in entry['lines']} & {'9100', '9110'})
        gross = sum(view['claim']['gross'] for view in
                    (service.fixtures.view(key) for key in sorted(service.fixtures.projection_ids)))
        self.assertEqual(total(body, '9100', 'debit'), gross)
        self.assertEqual(total(body, '9110', 'credit'), gross)
        asset_codes = {code for code, spec in coa.CHART.items() if spec[1] in ('ASSET', 'CONTRA_ASSET')}
        for entry in body['entries']:
            for line in entry['lines']:
                if line['account'] in asset_codes:
                    self.assertNotEqual(entry['source'], 'EVIDENCE')
        # the asset side sees principal and interest only, never the face
        asset_debits = sum(total(body, code, 'debit') for code in asset_codes)
        self.assertEqual(asset_debits, 90000 + total(body, '1110', 'debit'))
        self.assertNotEqual(asset_debits, gross)


class ReconciliationTests(unittest.TestCase):
    def clean_book(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c1', 0, 10)
        run(service, 'repay', 'sim-a', 'a-repay', amount=10000, sequence=1)
        tick(service, 'c2', 10, 30)
        return service

    def test_both_new_checks_are_matched_on_a_clean_book(self):
        report = self.clean_book().reconciliation(None, 'coa-candidate')
        status = {check['id']: check['status'] for check in report['checks']}
        self.assertEqual(tuple(status), recon.CHECK_IDS + (recon.OVERLAY_CHECK_ID,) + recon.COA_CHECK_IDS)
        self.assertEqual(status['coa_candidate_totals_vs_v1'], 'MATCHED')
        self.assertEqual(status['interest_ledger_vs_projection'], 'MATCHED')
        self.assertEqual(report['status'], 'MATCHED')
        self.assertEqual(report['coa_candidate'], {
            'chart': 'SIMULATION_FIXED_V2', 'coa_version': 'CAPITAL-COA-V1',
            'accounting_policy': 'SYNTHETIC_UNADOPTED', 'tax': 'NOT_BOUND', 'policy_adopted': False})
        self.assertEqual(report['source_cut'], 'NOT_BOUND')

    def test_empty_and_untouched_books_are_matched(self):
        self.assertEqual(CapitalService().reconciliation(None, 'coa-candidate')['status'], 'MATCHED')
        service = CapitalService()
        draw_book(service)
        self.assertEqual(service.reconciliation(None, 'coa-candidate')['status'], 'MATCHED')

    def test_tampered_totals_flip_the_matching_check(self):
        service = self.clean_book()
        journal = service.machine.export_journal()
        evidence = [service.fixtures.view(key) for key in sorted(service.fixtures.projection_ids)]
        v1 = projection.SimulationProjection().project(journal, evidence)
        good = coa.CoaCandidateProjection().project(journal, evidence, overlay_entries=service.overlay_entries)
        self.assertTrue(coa.totals_match_v1(good, v1))
        self.assertTrue(coa.interest_matches_ledger(good, service.overlay_entries))
        for code, field in (('1100', 'debit_total'), ('1100', 'credit_total'), ('1100', 'balance'),
                            ('9100', 'debit_total'), ('9110', 'credit_total')):
            bad = copy.deepcopy(good)
            next(a for a in bad['accounts'] if a['code'] == code)[field] += 1
            with self.subTest(code=code, field=field):
                self.assertFalse(coa.totals_match_v1(bad, v1))
        bad = copy.deepcopy(good)
        next(a for a in bad['accounts'] if a['code'] == '4100')['credit_total'] += 1
        self.assertFalse(coa.interest_matches_ledger(bad, service.overlay_entries))
        bad = copy.deepcopy(good)
        next(line for entry in bad['entries'] for line in entry['lines'] if line['account'] == '1110')['amount'] += 1
        self.assertFalse(coa.interest_matches_ledger(bad, service.overlay_entries))
        self.assertFalse(coa.totals_match_v1({}, v1))
        self.assertFalse(coa.interest_matches_ledger({}, service.overlay_entries))

    def test_a_dropped_overlay_posting_is_a_mismatch(self):
        service = self.clean_book()
        journal = service.machine.export_journal()
        evidence = [service.fixtures.view(key) for key in sorted(service.fixtures.projection_ids)]
        good = coa.CoaCandidateProjection().project(journal, evidence, overlay_entries=service.overlay_entries)
        # the ledger records more than the projection posted
        shorter = [entry for entry in service.overlay_entries if entry['overlay_id'] != 'c2:interest:sim-a']
        short_projection = coa.CoaCandidateProjection().project(journal, evidence, overlay_entries=shorter)
        self.assertFalse(coa.interest_matches_ledger(short_projection, service.overlay_entries))

    def test_recon_payload_shape_failure_marks_all_checks(self):
        report = recon.build_reconciliation(
            payload=None, unreadable=None, fixture_rows={}, fixtures_digest='x', settlement_source=None,
            projection_port=projection.SimulationProjection(), probe_operation_id=None, instance_id='i',
            operation_capacity=1, workspace_status='ACTIVE', coa_port=coa.CoaCandidateProjection(), overlay_entries=[])
        self.assertEqual([check['id'] for check in report['checks']], list(recon.CHECK_IDS + recon.COA_CHECK_IDS))
        self.assertTrue(all(check['status'] == 'RECON_MISMATCH' for check in report['checks']))

    def test_projection_and_recon_are_read_only(self):
        service = self.clean_book()
        before = service._frozen()
        candidate(service)
        service.reconciliation(None, 'coa-candidate')
        self.assertEqual(service._frozen(), before)

    def test_manifest_is_unchanged_by_the_candidate(self):
        service = self.clean_book()
        first = service.export_manifest()
        candidate(service)
        service.reconciliation(None, 'coa-candidate')
        second = service.export_manifest()
        self.assertEqual(first['content_digest'], second['content_digest'])
        self.assertEqual(first['sections']['projection'], second['sections']['projection'])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.service = cls.server.service
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.doc = facade_schema.load_contract()
        draw_book(cls.service)
        tick(cls.service, 'h1', 0, 10)
        cls.tokens = {'organizer': json.loads(cls.get('/api/state')[1])['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.post('/api/session', {'role': role})['local_token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def get(cls, path, token=None):
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request('GET', path, headers={'X-Capital-Token': token} if token else {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    @classmethod
    def post(cls, path, body):
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request('POST', path, body=json.dumps(body).encode(),
                       headers={'Content-Type': 'application/json', 'X-Capital-Token': cls.tokens['organizer']})
        response = client.getresponse()
        raw = response.read()
        client.close()
        return json.loads(raw)

    def route(self, path):
        return next(item for item in self.doc['routes'] if item['method'] == 'GET' and item['path'] == path)

    def test_candidate_route_balances_and_matches_the_facade_schema(self):
        status, raw = self.get('/api/projection?mode=coa-candidate')
        self.assertEqual(status, 200)
        body = json.loads(raw)
        facade_schema.validate(body, self.route('/api/projection')['response'], self.doc)
        self.assertEqual(body['chart'], 'SIMULATION_FIXED_V2')
        self.assertTrue(body['balance_groups'])
        self.assertTrue(all(g['debit'] == g['credit'] for g in body['balance_groups']))
        status, raw = self.get('/api/projection')
        v1 = json.loads(raw)
        self.assertEqual(v1['chart'], 'SIMULATION_FIXED_V1')
        facade_schema.validate(v1, self.route('/api/projection')['response'], self.doc)
        tainted = dict(body, not_in_facade=1)
        with self.assertRaises(facade_schema.SchemaError):
            facade_schema.validate(tainted, self.route('/api/projection')['response'], self.doc)

    def test_recon_candidate_route_matches_the_facade_schema(self):
        status, raw = self.get('/api/reconciliation?mode=coa-candidate')
        self.assertEqual(status, 200)
        body = json.loads(raw)
        facade_schema.validate(body, self.route('/api/reconciliation')['response'], self.doc)
        self.assertEqual(body['status'], 'MATCHED')
        plain = json.loads(self.get('/api/reconciliation')[1])
        self.assertEqual(len(plain['checks']), 6 + (recon.OVERLAY_CHECK_ID in [c['id'] for c in plain['checks']]))
        self.assertEqual(len(body['checks']), len(plain['checks']) + 2)
        self.assertNotIn('coa_candidate', plain)
        facade_schema.validate(plain, self.route('/api/reconciliation')['response'], self.doc)

    def test_roles_and_bad_modes(self):
        for role in ('organizer', 'auditor'):
            self.assertEqual(self.get('/api/projection?mode=coa-candidate', self.tokens[role])[0], 200, role)
        for role in ('observer', 'agent'):
            plain = self.get('/api/projection', self.tokens[role])[0]
            self.assertEqual(self.get('/api/projection?mode=coa-candidate', self.tokens[role])[0], plain, role)
        for path in ('/api/projection?mode=coa-candidate&mode=simulation', '/api/projection?mode=coa',
                     '/api/reconciliation?mode=coa-candidate&mode=simulation', '/api/reconciliation?mode=nope'):
            status, raw = self.get(path)
            self.assertEqual((status, json.loads(raw)['error']), (400, 'NOT_BOUND'), path)

    def test_the_contract_lists_the_new_query_and_error(self):
        self.assertIn('ASSET_MISMATCH', self.route('/api/projection')['errors'])
        self.assertEqual(self.route('/api/reconciliation')['query'], ['operation_id', 'mode'])


if __name__ == '__main__':
    unittest.main()
