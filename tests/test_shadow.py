"""Shadow arithmetic for refund bearer classes and resale unwind. Never applied."""
import ast
import hashlib
import http.client
import importlib.util
import json
import random
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from capital.producer import FixtureViews
from capital.scenarios import replay_scenarios
from capital.server import make_server
from capital.service import CapitalService
from capital.shadow import (
    COMPUTED, DEFERRED, DIVERGES, FALSE_FLAGS, INPUT_UNKNOWN, INCONSISTENT, MATCHES,
    NOT_BOUND, NOT_COMPARABLE, RULES_VERSION, SHADOW_LABEL, SHADOW_MODE, SHADOW_PROVENANCE,
    SHADOW_STATUSES, DecisionNoteShadow, ShadowInconsistent, ShadowPolicyPort,
    allocate_largest_remainder, capped_pro_rata, fill_sequential,
)

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_SETTLEMENT_POLICY.md'
SHADOW_PY = ROOT / 'capital' / 'shadow.py'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_SHADOW_AMOUNT = re.compile(r'\Ashadow_[a-z0-9_]*\Z')
FORBIDDEN_KEYS = frozenset(('distributed', 'outstanding', 'cancelled_unpaid',
                            'recovery_due', 'distributed_cash'))


def note_block():
    blocks = _FENCE.findall(NOTE.read_text(encoding='utf-8'))
    return json.loads(blocks[0])


def claim_vector(view):
    return {
        'gross': view['gross'],
        'policy': {'residual_payee': view['policy']['residual_payee'],
                   'fee_payee': view['policy']['fee_payee']},
        'obligations': [
            {'payee': row['payee'], 'face': row['face'], 'distributed': row['distributed'],
             'cancelled_unpaid': row['cancelled_unpaid'], 'outstanding': row['outstanding'],
             'recovery_due': row['recovery_due']}
            for row in view['obligations']],
    }


def refund_entry(refund_id, amount, reason_class, adjudicated=False):
    return {'refund_id': refund_id, 'amount': amount, 'reason_class': reason_class,
            'evidence_ref': 'SIMULATED', 'adjudicated_platform_fault': adjudicated}


def by_payee(lines):
    return {row['payee']: row for row in lines}


def walk_shadow_amounts(value, path='$'):
    """Every integer amount key in a shadow result starts with shadow_."""
    bad = []
    if type(value) is dict:
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                bad.append(f'{path}.{key}: forbidden FSM field name')
            if type(item) is int and not _SHADOW_AMOUNT.fullmatch(key):
                bad.append(f'{path}.{key}: integer amount without shadow_ prefix')
            bad.extend(walk_shadow_amounts(item, f'{path}.{key}'))
    elif type(value) is list:
        for index, item in enumerate(value):
            bad.extend(walk_shadow_amounts(item, f'{path}[{index}]'))
    return bad


def walk_statuses(value, path='$'):
    bad = []
    if type(value) is dict:
        status = value.get('status')
        if type(status) is str and status.startswith('SHADOW_') and status not in SHADOW_STATUSES:
            bad.append(f'{path}.status={status}')
        recon = value.get('reconciliation')
        if type(recon) is str and recon not in (MATCHES, DIVERGES, NOT_COMPARABLE):
            bad.append(f'{path}.reconciliation={recon}')
        for key, item in value.items():
            bad.extend(walk_statuses(item, f'{path}.{key}'))
    elif type(value) is list:
        for index, item in enumerate(value):
            bad.extend(walk_statuses(item, f'{path}[{index}]'))
    return bad


def walk_flags(value, path='$'):
    bad = []
    if type(value) is dict:
        if value.get('mode') == SHADOW_MODE:
            for flag in FALSE_FLAGS:
                if value.get(flag) is not False:
                    bad.append(f'{path}.{flag} is {value.get(flag)!r}')
        for key, item in value.items():
            bad.extend(walk_flags(item, f'{path}.{key}'))
    elif type(value) is list:
        for index, item in enumerate(value):
            bad.extend(walk_flags(item, f'{path}[{index}]'))
    return bad


class PrimitiveTests(unittest.TestCase):
    def test_fill_sequential_order_and_cap(self):
        alloc, leftover = fill_sequential(100, [('a', 40), ('b', 80)])
        self.assertEqual(alloc, [('a', 40), ('b', 60)])
        self.assertEqual(leftover, 0)
        alloc, leftover = fill_sequential(200, [('a', 40), ('b', 80)])
        self.assertEqual(alloc, [('a', 40), ('b', 80)])
        self.assertEqual(leftover, 80)
        alloc, leftover = fill_sequential(0, [('a', 40)])
        self.assertEqual(alloc, [('a', 0)])
        self.assertEqual(leftover, 0)

    def test_largest_remainder_ties_ascending_label(self):
        # 1 over two equal weights: remainders tie, 'a' wins by code-point order.
        self.assertEqual(allocate_largest_remainder(1, [('b', 1), ('a', 1)]), [('b', 0), ('a', 1)])
        self.assertEqual(allocate_largest_remainder(1, [('z', 1), ('m', 1), ('a', 1)]),
                         [('z', 0), ('m', 0), ('a', 1)])
        # Exact split leaves no remainder.
        self.assertEqual(allocate_largest_remainder(100, [('a', 1), ('b', 3)]), [('a', 25), ('b', 75)])
        # 7 over weights 1/1/1 -> quota 2 each, remainder 1 to smallest label.
        self.assertEqual(allocate_largest_remainder(7, [('c', 1), ('a', 1), ('b', 1)]),
                         [('c', 2), ('a', 3), ('b', 2)])
        self.assertEqual(allocate_largest_remainder(0, [('a', 5)]), [('a', 0)])
        with self.assertRaises(ShadowInconsistent):
            allocate_largest_remainder(10, [('a', 0), ('b', 0)])
        with self.assertRaises(ShadowInconsistent):
            allocate_largest_remainder(5, [('a', 1), ('a', 2)])
        with self.assertRaises(ShadowInconsistent):
            allocate_largest_remainder(-1, [('a', 1)])

    def test_capped_pro_rata_fixes_caps_and_redistributes(self):
        alloc, leftover = capped_pro_rata(100, [('a', 1, 10), ('b', 1, 1000)])
        self.assertEqual(dict(alloc), {'a': 10, 'b': 90})
        self.assertEqual(leftover, 0)
        alloc, leftover = capped_pro_rata(100, [('a', 1, 10), ('b', 1, 20)])
        self.assertEqual(dict(alloc), {'a': 10, 'b': 20})
        self.assertEqual(leftover, 70)

    def test_seeded_primitive_properties(self):
        rng = random.Random(20261015)
        for _ in range(500):
            total = rng.randrange(0, 100001)
            count = rng.randrange(1, 6)
            labels = [f'p{i}' for i in range(count)]
            weights = [rng.randrange(0, 100) for _ in range(count)]
            if sum(weights) == 0:
                continue
            alloc = dict(allocate_largest_remainder(total, list(zip(labels, weights))))
            self.assertEqual(sum(alloc.values()), total)
            self.assertTrue(all(value >= 0 for value in alloc.values()))
            caps = [rng.randrange(0, 100001) for _ in range(count)]
            fill, leftover = fill_sequential(total, list(zip(labels, caps)))
            self.assertEqual(sum(amount for _l, amount in fill) + leftover, total)
            self.assertTrue(all(amount >= 0 for _l, amount in fill))
            alloc2, leftover2 = capped_pro_rata(total, list(zip(labels, weights, caps)))
            self.assertEqual(sum(a for _l, a in alloc2) + leftover2, total)
            self.assertTrue(all(0 <= a <= c for (_l, a), (_l, _w, c) in zip(alloc2, zip(labels, weights, caps))))


class ShadowLoaderTests(unittest.TestCase):
    def test_bound_and_port(self):
        shadow = DecisionNoteShadow()
        self.assertIsInstance(shadow, ShadowPolicyPort)
        self.assertEqual(shadow.outcome, 'BOUND')
        status = shadow.status()
        self.assertEqual(status['shadow_rules_version'], RULES_VERSION)
        self.assertEqual(status['mode'], SHADOW_MODE)
        self.assertEqual(status['provenance'], SHADOW_PROVENANCE)
        self.assertEqual(status['policy_version'], 'CAPITAL-SETTLEMENT-POLICY-V1')
        self.assertEqual(len(status['note_digest']), 64)

    def test_missing_or_malformed_note_is_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = DecisionNoteShadow(Path(tmp) / 'absent.md')
            self.assertEqual(missing.outcome, 'NOT_BOUND')
            result = missing.refund({'gross': 1})
            self.assertEqual(result['status'], NOT_BOUND)
            self.assertEqual(missing.deferred('x', 'detail')['status'], NOT_BOUND)
            bad = Path(tmp) / 'bad.md'
            bad.write_text('no block here', encoding='utf-8')
            self.assertEqual(DecisionNoteShadow(bad).outcome, 'NOT_BOUND')

    def test_no_fsm_or_vendor_imports(self):
        text = SHADOW_PY.read_text(encoding='utf-8')
        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for name in imported:
            self.assertFalse(name.startswith('capital.protocol') or name.startswith('capital.vendor'), name)


class RefundVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shadow = DecisionNoteShadow()
        cls.scenarios = replay_scenarios()
        # Post-distribution, pre-refund pinned view (organizer 95000/92000/3000,
        # platform 5000/5000/0) shared by the RC vectors.
        cls.base = claim_vector(cls.scenarios['partial-after']['final'])

    def refund(self, *refunds, base=None):
        return self.shadow.refund({**(base or self.base), 'refunds': list(refunds)})

    def test_rc1_40k_vector(self):
        result = self.refund(refund_entry('v1', 40000, 'RC1_BUYER_WITHIN_POLICY'))
        entry = result['refunds'][0]
        self.assertEqual(entry['status'], COMPUTED)
        got = by_payee(entry['lines'])
        self.assertEqual((got['organizer']['shadow_reversal'], got['organizer']['shadow_cancelled_unpaid'],
                          got['organizer']['shadow_recovery_due']), (38000, 3000, 35000))
        self.assertEqual((got['platform']['shadow_reversal'], got['platform']['shadow_recovery_due']), (2000, 2000))
        self.assertEqual(entry['shadow_platform_pool_obligation'], 0)
        self.assertEqual(entry['reconciliation'], DIVERGES)

    def test_rc2_full_gross_matches_pinned_reclassification(self):
        result = self.refund(refund_entry('v2', 100000, 'RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT'))
        entry = result['refunds'][0]
        self.assertEqual(entry['status'], COMPUTED)
        self.assertEqual(entry['reconciliation'], MATCHES)
        self.assertEqual(result['cumulative']['reconciliation'], MATCHES)
        got = by_payee(entry['lines'])
        self.assertEqual((got['organizer']['shadow_reversal'], got['organizer']['shadow_cancelled_unpaid'],
                          got['organizer']['shadow_recovery_due']), (95000, 3000, 92000))
        self.assertEqual((got['platform']['shadow_reversal'], got['platform']['shadow_recovery_due']), (5000, 5000))
        # Compare with the pinned FIXTURE_FULL_GROSS_RECLASS outcome, line by line.
        fixture = by_payee(self.scenarios['full-after']['final']['obligations'])
        for payee, row in got.items():
            self.assertEqual(row['shadow_cancelled_unpaid'], fixture[payee]['cancelled_unpaid'])
            self.assertEqual(row['shadow_recovery_due'], fixture[payee]['recovery_due'])

    def test_rc2_partial_40k_vector(self):
        entry = self.refund(refund_entry('v3', 40000, 'RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT'))['refunds'][0]
        got = by_payee(entry['lines'])
        self.assertEqual((got['organizer']['shadow_reversal'], got['organizer']['shadow_cancelled_unpaid'],
                          got['organizer']['shadow_recovery_due']), (40000, 3000, 37000))
        self.assertEqual(got['platform']['shadow_reversal'], 0)
        self.assertEqual(entry['reconciliation'], DIVERGES)

    def test_rc3_20k_vector(self):
        entry = self.refund(refund_entry('v4', 20000, 'RC3_PLATFORM_FAULT'))['refunds'][0]
        got = by_payee(entry['lines'])
        self.assertEqual((got['platform']['shadow_reversal'], got['platform']['shadow_recovery_due']), (5000, 5000))
        self.assertEqual(got['organizer']['shadow_reversal'], 0)
        self.assertEqual(entry['shadow_platform_pool_obligation'], 15000)
        self.assertEqual(entry['reconciliation'], DIVERGES)

    def test_rc4_adjudicated_vector(self):
        entry = self.refund(refund_entry(
            'v5', 40000, 'RC4_PROVIDER_CHARGEBACK_OR_DISPUTE', adjudicated=True))['refunds'][0]
        got = by_payee(entry['lines'])
        self.assertEqual((got['platform']['shadow_reversal'], got['platform']['shadow_recovery_due']), (5000, 5000))
        self.assertEqual(entry['shadow_platform_pool_obligation'], 35000)
        self.assertIs(entry['working_assumption'], True)
        self.assertEqual(entry['reconciliation'], DIVERGES)
        plain = self.refund(refund_entry('v5b', 40000, 'RC4_PROVIDER_CHARGEBACK_OR_DISPUTE'))['refunds'][0]
        self.assertIs(plain['working_assumption'], True)
        self.assertEqual(by_payee(plain['lines'])['organizer']['shadow_reversal'], 40000)

    def test_rc1_split_refunds_vector(self):
        result = self.refund(
            refund_entry('v6a', 40000, 'RC1_BUYER_WITHIN_POLICY'),
            refund_entry('v6b', 60000, 'RC1_BUYER_WITHIN_POLICY'))
        second = by_payee(result['refunds'][1]['lines'])
        self.assertEqual(second['organizer']['shadow_reversal'], 57000)
        self.assertEqual(second['platform']['shadow_reversal'], 3000)
        cumulative = by_payee(result['cumulative']['lines'])
        self.assertEqual((cumulative['organizer']['shadow_cancelled_unpaid'],
                          cumulative['organizer']['shadow_recovery_due']), (3000, 92000))
        self.assertEqual(cumulative['platform']['shadow_recovery_due'], 5000)
        self.assertIs(result['cumulative']['auto_reclassified'], False)
        # Split refunds never reproduce the pinned full-gross reclassification.
        self.assertEqual(result['cumulative']['reconciliation'], DIVERGES)

    def test_rc5_routes_to_resale(self):
        entry = self.refund(refund_entry('v7', 10000, 'RC5_RESALE_UNWIND'))['refunds'][0]
        self.assertEqual(entry['status'], INPUT_UNKNOWN)
        self.assertEqual(entry['routed_to'], 'resale_prior_contract_cancel_burden')
        self.assertEqual(entry['reconciliation'], NOT_COMPARABLE)

    def test_refund_invariants(self):
        # Cumulative refund above gross is inconsistent.
        result = self.refund(refund_entry('x1', 60000, 'RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT'),
                             refund_entry('x2', 60000, 'RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT'))
        self.assertEqual(result['status'], INCONSISTENT)
        self.assertIsNone(result['refunds'])
        # Unknown class and bad domain values.
        bad = self.refund(refund_entry('x3', -1, 'RC1_BUYER_WITHIN_POLICY'))
        self.assertEqual(bad['status'], INCONSISTENT)
        unknown = self.refund(refund_entry('x4', 100, 'RC9_UNKNOWN'))
        self.assertEqual(unknown['refunds'][0]['status'], INCONSISTENT)

    def test_seeded_refund_property(self):
        rng = random.Random(7481)
        classes = ['RC1_BUYER_WITHIN_POLICY', 'RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT',
                   'RC3_PLATFORM_FAULT', 'RC4_PROVIDER_CHARGEBACK_OR_DISPUTE']
        for _ in range(200):
            gross = rng.randrange(1, 200001)
            fee = rng.randrange(0, gross + 1)
            base = {'gross': gross,
                    'policy': {'residual_payee': 'seller', 'fee_payee': 'feep'},
                    'obligations': [
                        {'payee': 'seller', 'face': gross - fee, 'distributed': rng.randrange(0, gross - fee + 1),
                         'cancelled_unpaid': 0, 'outstanding': 0, 'recovery_due': 0},
                        {'payee': 'feep', 'face': fee, 'distributed': rng.randrange(0, fee + 1),
                         'cancelled_unpaid': 0, 'outstanding': 0, 'recovery_due': 0}]}
            for row in base['obligations']:
                row['outstanding'] = row['face'] - row['distributed']
            refunds = []
            spent = 0
            for index in range(rng.randrange(1, 4)):
                amount = rng.randrange(0, max(1, gross - spent + 1))
                spent += amount
                if spent > gross:
                    break
                refunds.append(refund_entry(f'r{index}', amount, rng.choice(classes),
                                            adjudicated=rng.random() < 0.3))
            result = self.shadow.refund({**base, 'refunds': refunds})
            for entry in result['refunds'] or []:
                if entry['status'] != COMPUTED:
                    continue
                lines = entry['lines'] or []
                self.assertTrue(all(row['shadow_reversal'] >= 0 for row in lines))
                total = sum(row['shadow_reversal'] for row in lines)
                self.assertEqual(total + (entry['shadow_platform_pool_obligation'] or 0),
                                 entry['shadow_refund_amount'])
                for row in lines:
                    self.assertEqual(row['shadow_reversal'],
                                     row['shadow_cancelled_unpaid'] + row['shadow_recovery_due'])
            cumulative = result['cumulative']
            self.assertLessEqual(cumulative['shadow_cumulative_refund'], gross)


class ResaleVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shadow = DecisionNoteShadow()
        comm = FixtureViews().view('sim-committed')['claim']
        cls.primary = claim_vector(comm)
        cls.ru1, cls.ru2, cls.ru3 = cls.shadow.resale_triggers()

    def resale(self, trigger, **kw):
        vector = {'P_p': 100000, 'trigger': trigger, 'primary': self.primary}
        vector.update(kw)
        return self.shadow.resale(vector)

    def by_line(self, rows):
        return {row['line']: row for row in rows}

    def test_ru1_premium_worked_example(self):
        result = self.resale(self.ru1, P_r=130000, seller_due=117000,
                             organizer_due=6500, platform_due=6500)
        self.assertEqual(result['status'], COMPUTED)
        self.assertEqual(result['shadow_holder_entitlement'], 113000)
        self.assertEqual(result['shadow_seller_kept'], 117000)
        self.assertEqual(result['shadow_seller_receives'], 0)
        self.assertEqual(result['shadow_holder_market_risk'], 17000)
        primary = by_payee(result['shadow_primary_refund_by_line'])
        self.assertEqual(primary['organizer']['shadow_reversal'], 95000)
        self.assertEqual(primary['platform']['shadow_reversal'], 5000)
        reversal = self.by_line(result['shadow_resale_line_reversal'])
        self.assertEqual((reversal['seller_due']['shadow_reversal'],
                          reversal['organizer_due']['shadow_reversal'],
                          reversal['platform_due']['shadow_reversal']), (0, 6500, 6500))
        self.assertEqual(result['shadow_recovery_due'], [])
        self.assertEqual(result['reconciliation'], NOT_COMPARABLE)
        self.assertEqual(result['primary_refund_reconciliation'], MATCHES)

    def test_ru1_discount_worked_example(self):
        result = self.resale(self.ru1, P_r=80000)
        self.assertEqual(result['status'], COMPUTED)
        self.assertEqual(result['shadow_holder_entitlement'], 80000)
        self.assertEqual(result['shadow_seller_receives'], 20000)
        self.assertIsNone(result['shadow_seller_kept'])
        self.assertEqual(result['shadow_holder_market_risk'], 0)
        self.assertTrue(all(row['shadow_reversal'] == 0 for row in result['shadow_resale_line_reversal']))
        self.assertEqual(result['primary_refund_reconciliation'], MATCHES)

    def test_ru2_full_reversal(self):
        result = self.resale(self.ru2, P_r=130000, seller_due=117000,
                             organizer_due=6500, platform_due=6500)
        self.assertEqual(result['status'], COMPUTED)
        self.assertEqual(result['shadow_holder_entitlement'], 130000)
        reversal = self.by_line(result['shadow_resale_line_reversal'])
        self.assertEqual((reversal['seller_due']['shadow_reversal'],
                          reversal['organizer_due']['shadow_reversal'],
                          reversal['platform_due']['shadow_reversal']), (117000, 6500, 6500))

    def test_ru3_full_and_partial(self):
        full = self.resale(self.ru3, P_r=130000, seller_due=117000,
                           organizer_due=6500, platform_due=6500, chargeback_amount=130000)
        self.assertEqual(full['status'], COMPUTED)
        self.assertEqual(full['shadow_holder_entitlement'], 0)
        recovery = self.by_line(full['shadow_recovery_due'])
        self.assertEqual(recovery['seller_due']['shadow_recovery_due'], 117000)
        reversal = self.by_line(full['shadow_resale_line_reversal'])
        self.assertEqual((reversal['organizer_due']['shadow_reversal'],
                          reversal['platform_due']['shadow_reversal']), (6500, 6500))
        partial = self.resale(self.ru3, P_r=130000, seller_due=117000,
                              organizer_due=6500, platform_due=6500, chargeback_amount=50000)
        self.assertEqual(self.by_line(partial['shadow_recovery_due'])['seller_due']['shadow_recovery_due'], 50000)
        self.assertTrue(all(row['shadow_reversal'] == 0 for row in partial['shadow_resale_line_reversal']))
        self.assertEqual(partial['shadow_seller_kept'], 67000)

    def test_resale_input_unknown_and_inconsistent(self):
        missing = self.resale(self.ru1, P_r=130000)  # premium without resale lines
        self.assertEqual(missing['status'], INPUT_UNKNOWN)
        self.assertIn('seller_due', missing['missing_inputs'])
        no_trigger = self.shadow.resale({'P_p': 1, 'P_r': 1})
        self.assertEqual(no_trigger['status'], INPUT_UNKNOWN)
        over = self.resale(self.ru3, P_r=130000, seller_due=117000,
                           organizer_due=6500, platform_due=6500, chargeback_amount=130001)
        self.assertEqual(over['status'], INCONSISTENT)

    def test_determinism_and_digests(self):
        first = self.resale(self.ru1, P_r=130000, seller_due=117000,
                            organizer_due=6500, platform_due=6500)
        second = self.resale(self.ru1, P_r=130000, seller_due=117000,
                             organizer_due=6500, platform_due=6500)
        self.assertEqual(first['result_digest'], second['result_digest'])
        self.assertEqual(first['input_digest'], second['input_digest'])
        canon = json.dumps(first, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        canon2 = json.dumps(second, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        self.assertEqual(canon, canon2)


class LabelTests(unittest.TestCase):
    def test_labels_prefixes_flags_on_every_result(self):
        service = CapitalService()
        body = service.policy_shadow()
        self.assertEqual(body['mode'], SHADOW_MODE)
        self.assertEqual(body['label'], SHADOW_LABEL)
        self.assertEqual(body['provenance'], SHADOW_PROVENANCE)
        bad = []
        for item in body['items']:
            bad.extend(walk_shadow_amounts(item['shadow']))
            bad.extend(walk_statuses(item['shadow']))
            bad.extend(walk_flags(item['shadow']))
        bad.extend(walk_flags(body))
        self.assertEqual(bad, [])


class ServiceShadowTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def test_side_by_side_pinned_and_shadow_verdicts(self):
        body = self.service.policy_shadow()
        self.assertEqual(body['outcome'], COMPUTED)
        self.assertEqual([item['item'] for item in body['items']], [
            'refund_bearer', 'resale_prior_contract_cancel_burden',
            'revenue_participation', 'claim_purchase', 'residual_and_late_cash'])
        for item in body['items']:
            self.assertEqual(item['pinned']['status'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIs(item['pinned']['computed'], False)
            self.assertIn(item['shadow']['status'], SHADOW_STATUSES)
        by_item = {item['item']: item for item in body['items']}
        self.assertEqual(by_item['refund_bearer']['shadow']['status'], COMPUTED)
        classes = [r['refunds'][0]['reason_class'] for r in
                   by_item['refund_bearer']['shadow']['per_class']]
        self.assertEqual(len(classes), 6)  # RC1-RC4, RC4 adjudicated, RC5 routed
        resale = by_item['resale_prior_contract_cancel_burden']['shadow']
        self.assertEqual(resale['status'], COMPUTED)
        premium = next(t for t in resale['triggers'] if t['vector_id'] == 'worked-ru1-premium')
        self.assertEqual(premium['shadow_holder_entitlement'], 113000)
        for name in ('revenue_participation', 'claim_purchase', 'residual_and_late_cash'):
            self.assertEqual(by_item[name]['shadow']['status'], COMPUTED)
            self.assertTrue(by_item[name]['shadow']['deferred'])
            self.assertTrue(all(row['status'] == DEFERRED for row in by_item[name]['shadow']['deferred']))

    def test_read_only_flags_and_digest_unchanged(self):
        before = (self.service.machine.state_digest(), self.service.machine.canonical_state(),
                  len(self.service.receipts))
        body = self.service.policy_shadow()
        self.assertEqual(body['observed_state_digest'], before[0])
        for flag in (*FALSE_FLAGS, 'write_authorized'):
            self.assertIs(body[flag], False)
        self.assertEqual(before, (self.service.machine.state_digest(),
                                  self.service.machine.canonical_state(), len(self.service.receipts)))
        # The pinned FSM still blocks distribution on the open-refund fixture.
        final = self.service.scenario_results['partial-after']['final']
        self.assertEqual(final['refund_bearer_policy'], 'UNDEFINED')
        self.assertTrue(final['distribution_blocked'])
        errors = [step['error'] for step in self.service.scenario_results['partial-after']['steps']]
        self.assertIn('DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED', errors)

    def test_unbound_shadow_reports_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CapitalService(shadow=DecisionNoteShadow(Path(tmp) / 'absent.md'))
            body = service.policy_shadow()
            self.assertEqual(body['outcome'], NOT_BOUND)
            for item in body['items']:
                self.assertEqual(item['shadow']['status'], NOT_BOUND)


class ShadowHttpTests(unittest.TestCase):
    def test_route_permission_and_readonly(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        service = server.service
        before = (service.machine.state_digest(), len(service.receipts))
        try:
            def get(path, token=None):
                headers = {'X-Capital-Token': token} if token else {}
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path, headers=headers)
                response = client.getresponse()
                payload = json.loads(response.read().decode('utf-8'))
                status = response.status
                client.close()
                return status, payload

            code, body = get('/api/policy/shadow')
            self.assertEqual(code, 200)
            self.assertEqual(body['mode'], SHADOW_MODE)
            self.assertIs(body['applied_to_fsm'], False)
            self.assertIs(body['funds_executed'], False)
            self.assertIs(body['policy_adopted'], False)
            denied_code, denied = get('/api/policy/shadow', server.authorizer.bind_role('observer'))
            self.assertEqual(denied_code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['permission'], 'projection:read')
            code, _ = get('/api/policy/unknown')
            self.assertEqual(code, 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        self.assertEqual(before, (service.machine.state_digest(), len(service.receipts)))

    def test_response_matches_the_facade_contract(self):
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            'facade_schema', ROOT / 'tests' / 'facade_schema.py')
        module = _ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        doc = module.load_contract()
        body = CapitalService().policy_shadow()
        module.validate(body, {'$ref': '#/definitions/policy_shadow'}, doc)


class ShadowZipappTests(unittest.TestCase):
    def test_zipapp_reports_not_bound(self):
        spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts' / 'build_release.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            pyz = module.build(tmp, ROOT)
            code = (
                'import sys\n'
                'sys.path.insert(0, sys.argv[1])\n'
                'from capital.shadow import DecisionNoteShadow\n'
                's = DecisionNoteShadow()\n'
                'print(s.outcome)\n'
                'print(s.refund({"gross": 1})["status"])\n'
            )
            proc = subprocess.run([sys.executable, '-c', code, str(pyz)],
                                  capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.splitlines(), ['NOT_BOUND', 'SHADOW_NOT_BOUND'])


if __name__ == '__main__':
    unittest.main()
