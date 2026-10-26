"""Participation posting, claim-slice size/price and the UC1-UC4 partition. Never applied."""
import ast
import hashlib
import importlib.util
import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from capital.service import CapitalService
from capital.shadow import (
    COMPUTED, DEFERRED, FALSE_FLAGS, INCONSISTENT, INPUT_UNKNOWN, NOT_BOUND, NOT_COMPARABLE,
    SHADOW_MODE, DecisionNoteShadow, ShadowInconsistent, allocate_largest_remainder,
    participation_posting, slice_sizing, uc_partition,
)

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / 'docs' / 'decisions'
SETTLEMENT = DECISIONS / 'CAPITAL_SETTLEMENT_POLICY.md'
TERMS = DECISIONS / 'CAPITAL_FINANCIAL_TERMS.md'
SHADOW_NOTE = DECISIONS / 'CAPITAL_SHADOW_POLICY.md'
SHADOW_PY = ROOT / 'capital' / 'shadow.py'
ITEMS = ('revenue_participation', 'claim_purchase', 'residual_and_late_cash')
# sha256 of canonical policy_simulation() without the random instance_id, taken on main before this node.
SIMULATION_GOLDEN = '75a42992501bc376bf1975d49f14054d8732713dc33d5d668f2b6f1deb10270f'
RP = {'class2_allocated': 95000, 'organizer_borne_refunds': 0, 'F': 50000, 'paid_to_date': 0}
CP = {'outstanding': 95000, 'open_refund_face': 0, 'tier': 'T1_COMMIT_OBSERVED', 'expected_days': 60}


def note_block(path):
    text = path.read_text(encoding='utf-8')
    return json.loads(re.findall(r'```capital-decision-v1[ \t]*\n(.*?)```', text, re.DOTALL)[0])


def int_keys(result):
    return {key: value for key, value in result.items() if key.startswith('shadow_') and type(value) is int}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def canonical_digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


class PureFunctionTests(unittest.TestCase):
    def test_participation_vector(self):
        self.assertEqual(participation_posting(95000, 0, 50000, 0, 2000, 15000),
                         {'base': 95000, 'participation': 19000, 'cap': 75000, 'payable': 19000})

    def test_participation_cap_headroom_and_floor(self):
        self.assertEqual(participation_posting(95000, 0, 50000, 70000, 2000, 15000)['payable'], 5000)
        self.assertEqual(participation_posting(95000, 0, 50000, 75000, 2000, 15000)['payable'], 0)
        self.assertEqual(participation_posting(99, 0, 10, 0, 2000, 15000)['participation'], 19)
        self.assertEqual(participation_posting(95000, 5000, 50000, 0, 2000, 15000)['base'], 90000)

    def test_participation_rejects_bad_domain(self):
        for args in ((95000, 95001, 50000, 0, 2000, 15000), (1, 0, 1, 15001, 2000, 15000),
                     (-1, 0, 1, 0, 2000, 15000), (1.5, 0, 1, 0, 2000, 15000), (True, 0, 1, 0, 2000, 15000)):
            with self.assertRaises(ShadowInconsistent):
                participation_posting(*args)

    def test_slice_vector_and_t2_zero(self):
        self.assertEqual(slice_sizing(95000, 0, 8500, 700, 60),
                         {'slice_face_max': 80750, 'discount': 929, 'price': 79821})
        self.assertEqual(slice_sizing(95000, 0, 0, 1300, 60), {'slice_face_max': 0, 'discount': 0, 'price': 0})
        self.assertEqual(slice_sizing(95000, 5000, 8500, 700, 0)['price'], 76500)
        with self.assertRaises(ShadowInconsistent):
            slice_sizing(100, 101, 8500, 700, 1)

    def rows(self, *parts):
        return [{'face': f, 'distributed': d, 'cancelled_unpaid': c, 'outstanding': o} for f, d, c, o in parts]

    def test_partition_order_and_sum(self):
        rows = self.rows((95000, 43000, 0, 52000), (5000, 5000, 0, 0))
        self.assertEqual(uc_partition(97000, 49000, 0, False, rows), {'uc1': 49000, 'uc2': 0, 'uc3': 0, 'uc4': 0})
        rows = self.rows((100, 0, 0, 100))
        self.assertEqual(uc_partition(150, 150, 30, True, rows), {'uc1': 100, 'uc2': 30, 'uc3': 20, 'uc4': 0})
        self.assertEqual(uc_partition(150, 50, 0, False, self.rows((100, 100, 0, 0))),
                         {'uc1': 0, 'uc2': 0, 'uc3': 0, 'uc4': 50})

    def test_partition_inconsistent(self):
        done = self.rows((100, 100, 0, 0))
        for args in ((100, 50, 0, False, done),            # undistributed != confirmed - distributed
                     (100, 0, 0, 'no', done),
                     (100, 0, 0, False, []),
                     (100, 0, 0, False, self.rows((100, 50, 0, 10)))):
            with self.assertRaises(ShadowInconsistent):
                uc_partition(*args)
        # leftover that fits no state: not reclassified, no refund, cash not above the faces
        with self.assertRaises(ShadowInconsistent):
            uc_partition(80, 30, 0, False, self.rows((100, 50, 50, 0)))


class DivideTests(unittest.TestCase):
    def test_n_payee_largest_remainder(self):
        shadow = DecisionNoteShadow()
        self.assertEqual(shadow.divide(100, [('a', 1), ('b', 1), ('c', 1)]), [('a', 34), ('b', 33), ('c', 33)])
        self.assertEqual(shadow.divide(0, [('a', 1), ('b', 2), ('c', 3)]), [('a', 0), ('b', 0), ('c', 0)])
        with self.assertRaises(ShadowInconsistent):
            shadow.divide(1, [('a', 0), ('b', 0)])

    def test_seeded_properties(self):
        rng = random.Random(20261018)
        shadow = DecisionNoteShadow()
        for _ in range(300):
            count = rng.randint(3, 7)
            weights = [(f'p{i}', rng.randint(0, 50)) for i in range(count)]
            if sum(w for _l, w in weights) == 0:
                continue
            total = rng.randint(0, 10**6)
            out = shadow.divide(total, weights)
            weight_sum = sum(w for _l, w in weights)
            self.assertEqual(sum(q for _l, q in out), total)
            for (label, q), (_l, w) in zip(out, weights):
                self.assertIn(q - total * w // weight_sum, (0, 1))
            self.assertEqual(out, shadow.divide(total, weights))

    def test_ties_go_to_ascending_label(self):
        self.assertEqual(dict(allocate_largest_remainder(2, [('c', 1), ('a', 1), ('b', 1)])),
                         {'a': 1, 'b': 1, 'c': 0})


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shadow = DecisionNoteShadow()
        cls.service = CapitalService()
        cls.body = cls.service.policy_shadow()
        cls.items = {item['item']: item['shadow'] for item in cls.body['items']}

    def vectors(self, item):
        return {row['vector_id']: row for row in self.items[item]['vectors']}

    def test_note_expected_values_reproduce(self):
        block = note_block(SHADOW_NOTE)['entries']['revshare_claim_purchase_deferral']['value']
        rp = self.vectors('revenue_participation')['V-RP-single']
        self.assertEqual(int_keys(rp), block['revenue_participation']['vector']['expected'])
        self.assertEqual(int_keys(rp), {'shadow_base': 95000, 'shadow_participation': 19000,
                                        'shadow_cap': 75000, 'shadow_payable': 19000})
        cp = self.vectors('claim_purchase')['V-CP-size']
        self.assertEqual(int_keys(cp), block['claim_purchase']['vector']['expected'])
        self.assertEqual(int_keys(cp), {'shadow_slice_face_max': 80750, 'shadow_discount': 929,
                                        'shadow_price': 79821})
        uc = self.vectors('residual_and_late_cash')
        self.assertEqual(uc['V-UC-late-cash-open-refund']['shadow_uc2'], 100000)
        self.assertEqual(uc['V-UC-late-cash-accepted']['shadow_uc3'], 100000)
        self.assertEqual(uc['V-UC-overpay']['shadow_uc4'], 1000)
        self.assertEqual(uc['V-UC-split-statement']['shadow_uc1'], 49000)
        for vector_id, row in uc.items():
            self.assertEqual(sum(row[f'shadow_uc{n}'] for n in range(1, 5)),
                             {'V-UC-split-statement': 49000, 'V-UC-late-cash-open-refund': 100000,
                              'V-UC-late-cash-accepted': 100000, 'V-UC-overpay': 1000}[vector_id])
        self.assertEqual([row['vector_id'] for row in self.items['residual_and_late_cash']['vectors']],
                         [row['id'] for row in note_block(SHADOW_NOTE)['entries'][
                             'revshare_claim_purchase_deferral']['value']['residual_and_late_cash']['vectors']])

    def test_items_are_labelled_and_never_executed(self):
        for name in ITEMS:
            verdict = self.items[name]
            self.assertEqual((verdict['status'], verdict['mode']), (COMPUTED, SHADOW_MODE))
        for node in walk(self.body):
            if 'mode' in node:
                self.assertEqual(node['mode'], SHADOW_MODE)
            for flag in FALSE_FLAGS:
                if flag in node:
                    self.assertIs(node[flag], False)
        for name in ITEMS:
            for row in self.items[name]['vectors']:
                self.assertEqual(row['reconciliation'], NOT_COMPARABLE)
                for flag in FALSE_FLAGS:
                    self.assertIs(row[flag], False)
                self.assertTrue(row['input_source'])
                self.assertTrue(row['input_digest'] and row['result_digest'])

    def test_deferred_rows_match_note_and_name_the_seam(self):
        block = note_block(SHADOW_NOTE)['entries']['revshare_claim_purchase_deferral']['value']
        for name in ITEMS:
            rows = self.items[name]['deferred']
            self.assertEqual([row['deferred_item'] for row in rows], block[name]['deferred_SHADOW_DEFERRED'])
            for row in rows:
                self.assertEqual((row['status'], row['mode']), (DEFERRED, SHADOW_MODE))
                self.assertEqual(row['unblock'], block[name]['unblock'])
        wanted = ('multi-claim base', '90-day', 'slice registry', '180-day', 'D+1')
        text = json.dumps(self.body['items'])
        for needle in wanted:
            self.assertIn(needle, text)

    def test_pinned_row_still_unsupported(self):
        for item in self.body['items']:
            self.assertEqual(item['pinned']['status'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIs(item['pinned']['computed'], False)

    def test_state_receipts_and_simulation_unchanged(self):
        service = CapitalService()
        before = (service.machine.state_digest(), len(service.receipts), service.machine.canonical_state())
        scenarios = service.scenario_results
        simulation_before = service.policy_simulation()
        service.policy_shadow()
        service.policy_shadow()
        after = (service.machine.state_digest(), len(service.receipts), service.machine.canonical_state())
        self.assertEqual(before, after)
        simulation_after = service.policy_simulation()
        for body in (simulation_before, simulation_after):
            body = dict(body)
            body.pop('instance_id')
            self.assertEqual(canonical_digest(body), SIMULATION_GOLDEN)
        self.assertIs(service.scenario_results, scenarios)
        self.assertEqual((len(scenarios), sum(len(s['steps']) for s in scenarios.values())), (9, 35))

    def test_response_matches_the_facade_contract(self):
        spec = importlib.util.spec_from_file_location('facade_schema', ROOT / 'tests' / 'facade_schema.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate(self.body, {'$ref': '#/definitions/policy_shadow'}, module.load_contract())


class RuntimeReadTests(unittest.TestCase):
    """Policy values come from the notes, not from code."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy(self, source, edits=()):
        text = source.read_text(encoding='utf-8')
        for old, new in edits:
            self.assertIn(old, text)
            text = text.replace(old, new, 1)
        target = self.tmp / source.name
        target.write_text(text, encoding='utf-8')
        return target

    def shadow(self, settlement=SETTLEMENT, terms=TERMS, shadow=SHADOW_NOTE):
        return DecisionNoteShadow(settlement, terms_path=terms, shadow_path=shadow)

    def test_ratio_and_cap_are_read(self):
        path = self.copy(SETTLEMENT, [('"ratio_bps_of_base": 2000', '"ratio_bps_of_base": 1000'),
                                      ('"cap_bps_of_funded_amount": 15000', '"cap_bps_of_funded_amount": 10000')])
        result = self.shadow(path).participation(RP)
        self.assertEqual(int_keys(result), {'shadow_base': 95000, 'shadow_participation': 9500,
                                            'shadow_cap': 50000, 'shadow_payable': 9500})

    def test_advance_rate_is_read(self):
        path = self.copy(SETTLEMENT, [('"T1_COMMIT_OBSERVED": 8500', '"T1_COMMIT_OBSERVED": 5000')])
        self.assertEqual(self.shadow(path).claim_purchase(CP)['shadow_slice_face_max'], 47500)

    def test_tier_rate_is_read(self):
        path = self.copy(TERMS, [('"all_in_bps_annual": 700', '"all_in_bps_annual": 1400')])
        result = self.shadow(terms=path).claim_purchase(CP)
        self.assertEqual(result['shadow_discount'], 80750 * 1400 * 60 // 3_650_000)

    def test_t2_has_zero_advance(self):
        result = self.shadow().claim_purchase({**CP, 'tier': 'T2_UNBOUND'})
        self.assertEqual((result['status'], result['shadow_slice_face_max'], result['shadow_price']), (COMPUTED, 0, 0))

    def test_non_act365_day_count_is_not_bound(self):
        path = self.copy(TERMS, [('"day_count": "ACT_365_FIXED"', '"day_count": "ACT_360"')])
        self.assertEqual(self.shadow(terms=path).claim_purchase(CP)['status'], NOT_BOUND)

    def test_missing_notes_report_not_bound_without_numbers(self):
        gone = self.tmp / 'missing.md'
        cases = {
            'settlement': (self.shadow(settlement=gone), ITEMS),
            'terms': (self.shadow(terms=gone), ('claim_purchase',)),
            'shadow': (self.shadow(shadow=gone), ITEMS),
        }
        vectors = {'revenue_participation': RP, 'claim_purchase': CP, 'residual_and_late_cash': {}}
        methods = {'revenue_participation': 'participation', 'claim_purchase': 'claim_purchase',
                   'residual_and_late_cash': 'residual_partition'}
        for label, (shadow, items) in cases.items():
            for item in items:
                result = getattr(shadow, methods[item])(vectors[item])
                self.assertEqual(result['status'], NOT_BOUND, (label, item))
                self.assertEqual(int_keys(result), {}, (label, item))
                self.assertEqual(shadow.deferred_rows(item), [])
        self.assertIsNone(self.shadow(terms=gone).item_binding('revenue_participation'))

    def test_service_reports_not_bound_without_numbers(self):
        service = CapitalService(shadow=self.shadow(shadow=self.tmp / 'missing.md'))
        for item in service.policy_shadow()['items']:
            if item['item'] in ITEMS:
                verdict = item['shadow']
                self.assertEqual((verdict['status'], verdict['mode']), (NOT_BOUND, SHADOW_MODE))
                self.assertNotIn('vectors', verdict)
                self.assertFalse([k for k in verdict if k.startswith('shadow_') and type(verdict[k]) is int])

    def test_not_adopted_entry_is_not_bound(self):
        text = SETTLEMENT.read_text(encoding='utf-8')
        start = text.index('"revenue_participation": {')
        edited = text[:start] + text[start:].replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1)
        path = self.tmp / SETTLEMENT.name
        path.write_text(edited, encoding='utf-8')
        shadow = self.shadow(path)
        self.assertEqual(shadow.participation(RP)['status'], NOT_BOUND)
        self.assertEqual(shadow.claim_purchase(CP)['status'], COMPUTED)

    def test_no_copied_policy_constants(self):
        tree = ast.parse(SHADOW_PY.read_text(encoding='utf-8'))
        banned = {2000, 15000, 8500, 700, 1300, 5000, 929, 80750, 19000, 75000}
        found = {node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Constant) and type(node.value) is int and node.value in banned}
        self.assertEqual(found, set())
        self.assertNotIn('T1_COMMIT_OBSERVED', SHADOW_PY.read_text(encoding='utf-8'))


class InputTests(unittest.TestCase):
    def setUp(self):
        self.shadow = DecisionNoteShadow()
        self.uc = {'confirmed_cash': 1000, 'undistributed_cash': 0, 'refund_outstanding': 0,
                   'reclassified': False, 'pg_adjustment_outstanding': 0,
                   'obligations': [{'face': 1000, 'distributed': 1000, 'cancelled_unpaid': 0, 'outstanding': 0}]}

    def test_each_missing_key_is_input_unknown(self):
        cases = ((self.shadow.participation, RP), (self.shadow.claim_purchase, CP),
                 (self.shadow.residual_partition, self.uc))
        for method, vector in cases:
            self.assertEqual(method(vector)['status'], COMPUTED)
            for key in vector:
                partial = {k: v for k, v in vector.items() if k != key}
                result = method(partial)
                self.assertEqual(result['status'], INPUT_UNKNOWN, key)
                self.assertEqual(result['missing_inputs'], [key])
                self.assertEqual(int_keys(result), {})

    def test_unknown_tier_is_input_unknown(self):
        result = self.shadow.claim_purchase({**CP, 'tier': 'T9'})
        self.assertEqual((result['status'], result['missing_inputs']), (INPUT_UNKNOWN, ['tier']))

    def test_domain_violations_are_inconsistent(self):
        self.assertEqual(self.shadow.participation({**RP, 'paid_to_date': 75001})['status'], INCONSISTENT)
        self.assertEqual(self.shadow.claim_purchase({**CP, 'open_refund_face': 95001})['status'], INCONSISTENT)
        self.assertEqual(self.shadow.claim_purchase({**CP, 'expected_days': 1.5})['status'], INCONSISTENT)
        self.assertEqual(self.shadow.residual_partition({**self.uc, 'undistributed_cash': 5})['status'], INCONSISTENT)
        self.assertEqual(self.shadow.residual_partition({**self.uc, 'pg_adjustment_outstanding': -1})['status'], INCONSISTENT)

    def test_same_input_same_digest_and_inputs_not_echoed(self):
        first, second = self.shadow.participation(RP), self.shadow.participation(dict(RP))
        self.assertEqual(first, second)
        self.assertNotIn('organizer_borne_refunds', first)
        self.assertNotIn('outstanding', self.shadow.claim_purchase(CP))


if __name__ == '__main__':
    unittest.main()
