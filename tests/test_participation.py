"""Disposable multi-claim participation replay. Synthetic inputs only; never applied."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital.participation import (
    canonical, load_participation_policy, replay_participation,
)
from capital.shadow import (
    FALSE_FLAGS, SHADOW_STATUSES, DecisionNoteShadow, ShadowPolicyPort,
)

ROOT = Path(__file__).resolve().parents[1]
WINDOW = ROOT / 'docs' / 'decisions' / 'CAPITAL_PARTICIPATION_WINDOW.md'
SETTLEMENT = ROOT / 'docs' / 'decisions' / 'CAPITAL_SETTLEMENT_POLICY.md'
VECTORS = ROOT / 'tests' / 'vectors' / 'participation_window.json'
CHECKER = ROOT / 'scripts' / 'participation_vectors.py'
EXTRA_FALSE = ('fsm_expressible', 'vendor_fsm_reconciliation', 'persistent_commands',
               'automatic_payouts', 'upstream_adoption_claimed')


def component(source_id, cash_class, amount='omit'):
    row = {'source_id': source_id, 'cash_class': cash_class}
    if amount != 'omit':
        row['amount'] = amount
    return row


def claim(claim_id, anchor, holder_due=0, advance_due=0, advance_id=None,
          classes=('COUNTERPARTY_PROCEEDS',), beneficiary='capital'):
    return {
        'claim_id': claim_id,
        'source_amount_id': 'amount-' + claim_id,
        'beneficiary_id': beneficiary,
        'anchor_day': anchor,
        'components': [component(claim_id + '-' + str(i), klass)
                       for i, klass in enumerate(classes)],
        'source_scopes': ['scope-' + claim_id],
        'holder_due': holder_due,
        'advance_due': advance_due,
        'advance_id': advance_id,
    }


def original(claim_row, event_id, q, sequence=0, amounts=None):
    parts = [component(row['source_id'], row['cash_class'],
                      (amounts or {}).get(
                          row['source_id'],
                          q if row['cash_class'] == 'COUNTERPARTY_PROCEEDS' else 0))
             for row in claim_row['components']]
    return {
        'event_id': event_id,
        'kind': 'ORIGINAL',
        'claim_id': claim_row['claim_id'],
        'source_amount_id': claim_row['source_amount_id'],
        'beneficiary_id': claim_row['beneficiary_id'],
        'anchor_day': claim_row['anchor_day'],
        'sim_day': claim_row['anchor_day'],
        'sequence': sequence,
        'original_event_id': None,
        'components': parts,
    }


def adjustment(claim_row, event_id, day, sequence, amounts, original_event_id):
    parts = [component(row['source_id'], row['cash_class'],
                      amounts.get(row['source_id'], amounts.get(row['cash_class'], 0)))
             for row in claim_row['components']]
    return {
        'event_id': event_id,
        'kind': 'ADJUSTMENT',
        'claim_id': claim_row['claim_id'],
        'source_amount_id': claim_row['source_amount_id'],
        'beneficiary_id': claim_row['beneficiary_id'],
        'anchor_day': claim_row['anchor_day'],
        'sim_day': day,
        'sequence': sequence,
        'original_event_id': original_event_id,
        'components': parts,
    }


def book(claims, events, advances=(), funded=1000, start=0, end=120, as_of=150,
         complete=True, beneficiary='capital', terms='CAPITAL-REVSHARE-V1'):
    return {
        'schema': 'capital-participation-book-v1',
        'manifest': {
            'book_id': 'synthetic-book',
            'agreement_id': 'synthetic-agreement',
            'beneficiary_id': beneficiary,
            'funded_amount': funded,
            'terms_reference': terms,
            'start_day': start,
            'end_day': end,
            'as_of_day': as_of,
            'complete_history': complete,
            'claim_ids': [row['claim_id'] for row in claims],
        },
        'claims': list(claims),
        'advances': list(advances),
        'events': list(events),
    }


def binding(**overrides):
    return load_participation_policy(
        overrides.get('window'), overrides.get('settlement'))


def replay(value, **overrides):
    return replay_participation(value, binding=binding(**overrides))


def integer_shadow_keys(value, path='$'):
    found = []
    if type(value) is dict:
        for key, item in value.items():
            if type(item) is int and key.startswith('shadow_'):
                found.append(f'{path}.{key}')
            found.extend(integer_shadow_keys(item, f'{path}.{key}'))
    elif type(value) is list:
        for index, item in enumerate(value):
            found.extend(integer_shadow_keys(item, f'{path}[{index}]'))
    return found


def assert_envelope(case, result, status='SHADOW_COMPUTED'):
    case.assertIn(status, SHADOW_STATUSES)
    case.assertEqual(result['status'], status)
    case.assertEqual(result['mode'], 'SHADOW_NOT_APPLIED')
    case.assertEqual(result['production'], 'NOT_AUTHORIZED')
    for flag in (*FALSE_FLAGS, *EXTRA_FALSE):
        case.assertIs(result[flag], False, flag)
    for label in ('SIMULATED', 'SYNTHETIC_FIXTURE_PROFILE', 'SHADOW_NOT_APPLIED',
                  'SIMULATION_ONLY_NOT_OFFERED_V1', 'UNSUPPORTED_BY_PINNED_FSM'):
        case.assertIn(label, result['labels'])
    case.assertIs(result['provisional'], True)
    case.assertEqual(result['legal_tax'], 'WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW')


def simple_book(q=800, holder=200, advance=300, **manifest):
    """One claim, one statement: Q -> holder -> advance -> participation base."""
    row = claim('c1', 10, holder_due=holder, advance_due=advance,
                advance_id='a1' if advance else None)
    events = [original(row, 'o1', q)]
    advances = [{'advance_id': 'a1', 'balance': advance}] if advance else []
    return book([row], events, advances=advances, **manifest)


class BindingTests(unittest.TestCase):
    def test_bound_policy_reads_terms_from_notes(self):
        bound = binding()
        self.assertEqual(bound.status, 'SHADOW_BOUND')
        self.assertEqual((bound.ratio_bps, bound.cap_bps, bound.window_days), (2000, 15000, 90))
        self.assertEqual(bound.policy_version, 'CAPITAL-REVSHARE-V1')
        self.assertEqual(bound.bounds, (32, 16, 256, 1048576, 365, 10**12))
        provenance = json.loads(bound.provenance_json)
        for note in ('window', 'settlement'):
            self.assertEqual(provenance[note]['notes_source'], 'CHECKOUT')
            self.assertEqual(len(provenance[note]['note_sha256']), 64)
        self.assertIn('entries.revenue_participation.value', provenance['terms_entry_path'])
        self.assertEqual(provenance['decision_id'], 'participation-window-decision')
        self.assertEqual(provenance['terms_decision_id'], 'settlement-policy-decision')

    def test_missing_notes_report_not_bound_without_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'absent.md'
            for overrides in ({'window': missing}, {'settlement': missing},
                              {'window': missing, 'settlement': missing}):
                result = replay(simple_book(), **overrides)
                assert_envelope(self, result, 'SHADOW_NOT_BOUND')
                self.assertEqual(result['reasons'][0]['code'], 'DECISION_NOT_BOUND')
                self.assertEqual(integer_shadow_keys(result), [])
                self.assertNotIn('trace', result)

    def test_malformed_or_tampered_notes_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            garbage = Path(tmp) / 'garbage.md'
            garbage.write_text('# not a decision note\n', encoding='utf-8')
            self.assertEqual(replay(simple_book(), window=garbage)['status'], 'SHADOW_NOT_BOUND')
            blockless = Path(tmp) / 'noblock.md'
            blockless.write_text(SETTLEMENT.read_text(encoding='utf-8').split('```')[0],
                                 encoding='utf-8')
            self.assertEqual(replay(simple_book(), settlement=blockless)['status'],
                             'SHADOW_NOT_BOUND')

    def test_runtime_policy_mutations_unbind(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / 'window.md'
            text = WINDOW.read_text(encoding='utf-8')
            # Predicate disagreement with the day count unbinds, never re-derives.
            mutated.write_text(text.replace('"days_after_anchor": 90', '"days_after_anchor": 89', 1),
                               encoding='utf-8')
            self.assertEqual(replay(simple_book(), window=mutated)['status'], 'SHADOW_NOT_BOUND')
            mutated.write_text(text.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1),
                               encoding='utf-8')
            self.assertEqual(replay(simple_book(), window=mutated)['status'], 'SHADOW_NOT_BOUND')
            settlement = Path(tmp) / 'settlement.md'
            settlement.write_text(SETTLEMENT.read_text(encoding='utf-8').replace(
                '"ratio_bps_of_base": 2000', '"ratio_bps_of_base": "2000"', 1), encoding='utf-8')
            self.assertEqual(replay(simple_book(), settlement=settlement)['status'],
                             'SHADOW_NOT_BOUND')


class ReplayArithmeticTests(unittest.TestCase):
    def test_multi_claim_decomposition_and_exclusions(self):
        c1 = claim('c1', 10, holder_due=200, advance_due=300, advance_id='a1',
                   classes=('COUNTERPARTY_PROCEEDS', 'PROTECTED_LINES', 'PLATFORM_FEES',
                            'REFUND_RESERVES', 'CUSTOMER_DEPOSITS', 'HELD_TAX'))
        c2 = claim('c2', 10, holder_due=100, advance_due=100, advance_id='a1',
                   classes=('COUNTERPARTY_PROCEEDS', 'PROTECTED_LINES', 'PLATFORM_FEES',
                            'REFUND_RESERVES', 'CUSTOMER_DEPOSITS', 'HELD_TAX'))
        events = [
            original(c1, 'o1', 800, sequence=0, amounts={
                'c1-1': 100, 'c1-2': 50, 'c1-3': 50, 'c1-4': 20, 'c1-5': 30}),
            original(c2, 'o2', 500, sequence=1, amounts={
                'c2-1': 50, 'c2-2': 20, 'c2-3': 30, 'c2-4': 10, 'c2-5': 40}),
        ]
        result = replay(book([c1, c2], events,
                             advances=[{'advance_id': 'a1', 'balance': 400}]))
        assert_envelope(self, result)
        # Independent: Q = 1300, H = 300, A = 400, N = 600, U = 600 * 2000 // 10000.
        self.assertEqual((result['shadow_gross'], result['shadow_excluded']), (1700, 400))
        self.assertEqual((result['shadow_holder'], result['shadow_advance']), (300, 400))
        self.assertEqual(result['shadow_base'], 600)
        self.assertEqual((result['shadow_uncapped_entitlement'],
                          result['shadow_net_entitlement']), (120, 120))
        self.assertEqual(result['shadow_remaining_cap'], 1500 - 120)
        # gross = excluded + holder + advance + participation base (conservation).
        self.assertEqual(result['shadow_gross'],
                         result['shadow_excluded'] + result['shadow_holder'] +
                         result['shadow_advance'] + result['shadow_base'])

    def test_holder_shortage_stays_diagnostic(self):
        row = claim('short', 10, holder_due=200, advance_due=100, advance_id='a1')
        result = replay(book([row], [original(row, 'o', 150)],
                             advances=[{'advance_id': 'a1', 'balance': 100}]))
        assert_envelope(self, result)
        self.assertEqual((result['shadow_holder'], result['shadow_advance'],
                          result['shadow_base'], result['shadow_net_entitlement']),
                         (150, 0, 0, 0))
        arithmetic = result['trace'][0]['arithmetic']
        self.assertEqual((arithmetic['shadow_holder_unmet'], arithmetic['shadow_advance_unmet']),
                         (50, 100))

    def test_fractional_carry_within_and_across_statements(self):
        c1, c2 = claim('c1', 10), claim('c2', 10)
        result = replay(book([c1, c2], [original(c1, 'o1', 7), original(c2, 'o2', 7, sequence=1)]))
        assert_envelope(self, result)
        self.assertEqual((result['shadow_base'], result['shadow_net_entitlement']), (14, 2))
        self.assertEqual(result['statements'][0]['shadow_carry'], 8000)
        # Two separate statements never share the remainder.
        c3, c4 = claim('c3', 10), claim('c4', 11)
        separate = replay(book([c3, c4], [original(c3, 'o3', 4), original(c4, 'o4', 4)]))
        self.assertEqual([row['shadow_carry'] for row in separate['statements']], [8000, 8000])
        self.assertEqual(separate['shadow_net_entitlement'], 0)

    def test_cap_latch_clawback_and_no_backlog(self):
        row = claim('c1', 10)
        events = [
            original(row, 'o1', 60),
            adjustment(row, 'up', 11, 0, {'COUNTERPARTY_PROCEEDS': 100}, 'o1'),
            adjustment(row, 'down', 12, 0, {'COUNTERPARTY_PROCEEDS': 50}, 'o1'),
            adjustment(row, 'up-again', 13, 0, {'COUNTERPARTY_PROCEEDS': 100}, 'o1'),
            adjustment(row, 'down-again', 14, 0, {'COUNTERPARTY_PROCEEDS': 40}, 'o1'),
        ]
        result = replay(book([row], events, funded=10))  # cap = 10 * 15000 // 10000 = 15
        assert_envelope(self, result)
        payable = [step['shadow_payable'] for step in result['trace']]
        clawed = [step['shadow_clawback'] for step in result['trace']]
        self.assertEqual((payable, clawed), ([12, 3, 0, 0, 0], [0, 0, 10, 0, 5]))
        self.assertEqual((result['shadow_cumulative_positive_allocations'],
                          result['shadow_net_entitlement']), (15, 0))
        self.assertEqual(result['cap_status'], 'CAP_REACHED')
        self.assertEqual(result['shadow_remaining_cap'], 0)
        # The latched positive delta stays diagnostic, never a backlog.
        self.assertEqual(result['trace'][3]['shadow_unallocated_positive_delta'], 10)
        self.assertEqual((result['shadow_base'], result['shadow_uncapped_entitlement']), (40, 8))

    def test_downward_adjustment_limits_clawback_to_statement(self):
        c1, c2 = claim('c1', 10), claim('c2', 10)
        events = [
            original(c1, 'o1', 100, sequence=0),
            original(c2, 'o2', 100, sequence=1),
            adjustment(c1, 'zero', 20, 0, {'COUNTERPARTY_PROCEEDS': 0}, 'o1'),
        ]
        result = replay(book([c1, c2], events))
        assert_envelope(self, result)
        # U was 40; removing claim 1 gives U = 20 and claws back at most E1's share.
        self.assertEqual((result['shadow_uncapped_entitlement'],
                          result['shadow_net_entitlement'], result['shadow_clawback']), (20, 20, 20))
        self.assertEqual(result['shadow_cumulative_positive_allocations'], 40)

    def test_overcommitted_budget_and_overlapping_scope_reject(self):
        c1 = claim('c1', 10, advance_due=300, advance_id='a1')
        c2 = claim('c2', 10, advance_due=200, advance_id='a1')
        over = book([c1, c2], [original(c1, 'o1', 500), original(c2, 'o2', 500, sequence=1)],
                    advances=[{'advance_id': 'a1', 'balance': 400}])
        self.assertRejected(over, 'PRIORITY_INPUT_CONFLICT')
        c3 = claim('c3', 10)
        c4 = claim('c4', 10)
        c4['source_scopes'] = c3['source_scopes']
        overlap = book([c3, c4], [original(c3, 'o3', 500), original(c4, 'o4', 500, sequence=1)])
        self.assertRejected(overlap, 'PRIORITY_INPUT_CONFLICT')
        c5 = claim('c5', 10)
        c5['components'] = [{'source_id': 'shared', 'cash_class': 'COUNTERPARTY_PROCEEDS'}]
        c6 = claim('c6', 10)
        c6['components'] = [{'source_id': 'shared', 'cash_class': 'COUNTERPARTY_PROCEEDS'}]
        shared = book([c5, c6], [original(c5, 'o5', 500), original(c6, 'o6', 500, sequence=1)])
        self.assertRejected(shared, 'PRIORITY_INPUT_CONFLICT')

    def assertRejected(self, value, code):
        result = replay(value)
        assert_envelope(self, result, 'SHADOW_INCONSISTENT')
        self.assertEqual(result['reasons'][0]['code'], code)
        self.assertEqual(integer_shadow_keys(result), [])
        self.assertNotIn('trace', result)


class TemporalTests(unittest.TestCase):
    def boundary(self, day, as_of=None):
        row = claim('c1', 10)
        events = [original(row, 'o1', 800),
                  adjustment(row, 'refund', day, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')]
        return replay(book([row], events, as_of=101 if as_of is None else as_of))

    def test_adjustment_boundary_89_90_91(self):
        inside = self.boundary(99)
        edge = self.boundary(100)
        outside = self.boundary(101)
        for result in (inside, edge):
            assert_envelope(self, result)
            self.assertEqual(result['trace'][1]['window_status'], 'WITHIN_WINDOW')
            # N: 800 -> 700 gives delta -20 of uncapped entitlement.
            self.assertEqual((result['shadow_base'], result['shadow_net_entitlement']), (700, 140))
            self.assertEqual(result['shadow_clawback'], 20)
        assert_envelope(self, outside)
        late = outside['trace'][1]
        self.assertEqual(late['window_status'], 'OUTSIDE_WINDOW')
        self.assertEqual(late['shadow_unapplied_base_difference'], -100)
        self.assertEqual(late['before'], late['after'])
        # Settled entitlement is untouched but the fact stays in provenance.
        self.assertEqual((outside['shadow_base'], outside['shadow_net_entitlement']), (800, 160))
        self.assertEqual(outside['shadow_clawback'], 0)
        self.assertIn('refund', [row['event_id'] for row in outside['trace']])

    def test_original_must_occupy_the_anchor_day(self):
        row = claim('c1', 10)
        moved = original(row, 'o1', 800)
        moved['sim_day'] = 11
        result = replay(book([row], [moved]))
        self.assertEqual(result['status'], 'SHADOW_INCONSISTENT')
        self.assertEqual(result['reasons'][0]['code'], 'INVALID_ORIGINAL')

    def test_adjustment_must_follow_its_original(self):
        row = claim('c1', 10)
        earlier_day = adjustment(row, 'early', 9, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')
        result = replay(book([row], [original(row, 'o1', 800), earlier_day]))
        self.assertEqual(result['reasons'][0]['code'], 'INVALID_REFERENCE')
        same_slot = adjustment(row, 'same', 10, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')
        result = replay(book([row], [original(row, 'o1', 800), same_slot]))
        self.assertEqual(result['reasons'][0]['code'], 'INVALID_SEQUENCE')
        earlier_sequence = adjustment(row, 'same', 10, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')
        result = replay(book([row], [original(row, 'o1', 800, sequence=1), earlier_sequence]))
        self.assertEqual(result['reasons'][0]['code'], 'INVALID_REFERENCE')
        # Shuffled input arrays remain valid.
        good = adjustment(row, 'good', 11, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')
        shuffled = replay(book([row], [good, original(row, 'o1', 800)]))
        self.assertEqual(shuffled['status'], 'SHADOW_COMPUTED')
        self.assertEqual([step['event_id'] for step in shuffled['trace']], ['o1', 'good'])

    def test_future_events_and_future_observation_reject(self):
        row = claim('c1', 10)
        future = adjustment(row, 'future', 160, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')
        result = replay(book([row], [original(row, 'o1', 800), future], as_of=150))
        self.assertEqual(result['reasons'][0]['code'], 'FUTURE_EVENT')

    def test_observation_day_closes_statements_at_day_end(self):
        for as_of, expected in ((99, 'OPEN'), (100, 'FINAL_SIMULATED'), (101, 'FINAL_SIMULATED')):
            row = claim('c1', 10)
            result = replay(simple_book(as_of=as_of))
            self.assertEqual(result['window_status'], expected)
            self.assertEqual(result['statements'][0]['window_status'],
                             'OPEN' if expected == 'OPEN' else 'CLOSED')
        # Empty days advance closure: no events after day 10 still closes on day 100.
        row = claim('c1', 10)
        result = replay(book([row], [original(row, 'o1', 7)], as_of=100))
        self.assertEqual(result['window_status'], 'FINAL_SIMULATED')
        self.assertEqual(result['statements'][0]['shadow_carry'], 4000)

    def test_term_end_allows_only_in_window_negative_adjustments(self):
        row = claim('c1', 10)
        events = [
            original(row, 'o1', 100),
            adjustment(row, 'up', 11, 0, {'COUNTERPARTY_PROCEEDS': 150}, 'o1'),
            adjustment(row, 'down', 12, 0, {'COUNTERPARTY_PROCEEDS': 50}, 'o1'),
        ]
        result = replay(book([row], events, end=10))
        assert_envelope(self, result)
        self.assertEqual(result['term_status'], 'TERM_ENDED')
        self.assertEqual([step['shadow_payable'] for step in result['trace']], [20, 0, 0])
        self.assertEqual(result['trace'][1]['shadow_unallocated_positive_delta'], 10)
        self.assertEqual((result['shadow_net_entitlement'], result['shadow_clawback']), (0, 20))

    def test_day_t_still_allocates(self):
        row = claim('c1', 10)
        result = replay(simple_book(end=10, as_of=10))
        self.assertEqual(result['shadow_payable'], 60)
        self.assertEqual(result['term_status'], 'WITHIN_TERM')


class RejectionTests(unittest.TestCase):
    def reject(self, value, code):
        result = replay(value)
        assert_envelope(self, result, 'SHADOW_INCONSISTENT')
        self.assertEqual(result['reasons'][0]['code'], code)
        self.assertNotIn('trace', result)
        return result

    def test_membership_and_identity_fail_closed(self):
        row = claim('c1', 10)
        unknown = original(row, 'o1', 800)
        unknown['claim_id'] = 'ghost'
        self.reject(book([row], [unknown]), 'INVALID_MEMBERSHIP')
        wrong = book([row], [original(row, 'o1', 800)])
        wrong['claims'][0]['beneficiary_id'] = 'someone-else'
        self.reject(wrong, 'INVALID_MEMBERSHIP')
        dup_source = book([row], [original(row, 'o1', 800)])
        dup_source['claims'].append(claim('c2', 10))
        dup_source['claims'][1]['source_amount_id'] = 'amount-c1'
        dup_source['manifest']['claim_ids'].append('c2')
        event = original(dup_source['claims'][1], 'o2', 100, sequence=1)
        self.reject(dup_source | {'events': dup_source['events'] + [event]}, 'INVALID_MEMBERSHIP')
        retro = book([row], [original(row, 'o1', 800)], beneficiary='capital')
        retro['events'][0]['beneficiary_id'] = 'other'
        self.reject(retro, 'INVALID_MEMBERSHIP')

    def test_amounts_days_and_sequences_are_plain_integers(self):
        row = claim('c1', 10)
        for bad in (-1, True, 1.5, '800'):
            event = original(row, 'o1', 800)
            event['components'][0]['amount'] = bad
            self.reject(book([row], [event]), 'INVALID_AMOUNT')
        for bad in (True, 1.5, '10'):
            event = original(row, 'o1', 800)
            event['sim_day'] = bad
            self.reject(book([row], [event]), 'INVALID_DAY')
        for bad in (-1, True, 1.5):
            event = original(row, 'o1', 800)
            event['sequence'] = bad
            self.reject(book([row], [event]), 'INVALID_SEQUENCE')

    def test_duplicates_identical_conflicting_and_sequence_collisions(self):
        row = claim('c1', 10)
        first = original(row, 'o1', 800)
        identical = book([row], [first, dict(first)])
        result = replay(identical)
        assert_envelope(self, result)
        self.assertEqual(result['duplicate_diagnostics'],
                         [{'event_id': 'o1', 'ignored_copies': 1}])
        conflict = book([row], [first, dict(first, sequence=1)])
        self.reject(conflict, 'DUPLICATE_CONFLICT')
        second = original(row, 'o2', 900)
        second['claim_id'] = 'c1'
        collision = book([row], [first, second])
        # A second ORIGINAL for the same claim is rejected even before ordering.
        result = replay(collision)
        self.assertIn(result['reasons'][0]['code'], ('INVALID_SEQUENCE', 'INVALID_ORIGINAL'))
        # Conflicting payload after the dedupe point is still an atomic rejection.
        changed = dict(first, components=[dict(part, amount=1) for part in first['components']])
        self.reject(book([row], [first, changed]), 'DUPLICATE_CONFLICT')

    def test_classification_invariants_are_atomic(self):
        row = claim('c1', 10, classes=('COUNTERPARTY_PROCEEDS', 'PROTECTED_LINES'))
        base = original(row, 'o1', 800, amounts={'c1-1': 100})
        # Reclassification of a component source rejects the whole book.
        moved = adjustment(row, 'moved', 11, 0, {'COUNTERPARTY_PROCEEDS': 700, 'PROTECTED_LINES': 200}, 'o1')
        moved['components'] = [
            {'source_id': 'c1-0', 'cash_class': 'COUNTERPARTY_PROCEEDS', 'amount': 700},
            {'source_id': 'c1-1', 'cash_class': 'COUNTERPARTY_PROCEEDS', 'amount': 200},
        ]
        self.reject(book([row], [base, moved]), 'INVALID_CLASSIFICATION')
        # Source substitution rejects even inside the window.
        swapped = dict(moved, components=[
            {'source_id': 'new-source', 'cash_class': 'COUNTERPARTY_PROCEEDS', 'amount': 700},
            {'source_id': 'c1-1', 'cash_class': 'PROTECTED_LINES', 'amount': 200}])
        self.reject(book([row], [base, swapped]), 'INVALID_CLASSIFICATION')
        # And outside the window the same mutation is still atomic, not diagnostic.
        swapped['sim_day'] = 150
        self.reject(book([row], [base, swapped], as_of=150), 'INVALID_CLASSIFICATION')

    def test_capacity_bounds_reject_atomically(self):
        rows = [claim(f'c{i}', 10) for i in range(33)]
        events = [original(row, f'o{i}', 10, sequence=i) for i, row in enumerate(rows)]
        self.reject(book(rows, events), 'CAPACITY_EXCEEDED')
        rows = [claim(f'c{i}', i) for i in range(17)]
        events = [original(row, f'o{i}', 10) for i, row in enumerate(rows)]
        self.reject(book(rows, events), 'CAPACITY_EXCEEDED')
        row = claim('c1', 10)
        events = [original(row, 'o1', 10)] + [
            adjustment(row, f'a{i}', 11 + (i // 250), i, {'COUNTERPARTY_PROCEEDS': 10}, 'o1')
            for i in range(256)]
        self.reject(book([row], events, as_of=20), 'CAPACITY_EXCEEDED')
        big = claim('c1', 10)
        event = original(big, 'o1', 10**12 + 1)
        self.reject(book([big], [event]), 'INVALID_AMOUNT')
        far = claim('c1', 400)
        self.reject(book([far], [original(far, 'o1', 10)], end=500, as_of=500), 'INVALID_DAY')

    def test_incomplete_history_and_initial_state_reject(self):
        c1, c2 = claim('c1', 10), claim('c2', 10)
        self.reject(book([c1, c2], [original(c1, 'o1', 800)]), 'INCOMPLETE_HISTORY')
        self.reject(book([c1], [original(c1, 'o1', 800)], complete=False), 'INCOMPLETE_HISTORY')
        seeded = book([c1], [original(c1, 'o1', 800)])
        seeded['manifest']['initial_positive_allocations'] = 0
        self.reject(seeded, 'INVALID_SCHEMA')
        no_ref = adjustment(c1, 'a', 11, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'ghost')
        self.reject(book([c1], [original(c1, 'o1', 800), no_ref]), 'INVALID_REFERENCE')

    def test_unknown_fields_and_non_json_fail_closed(self):
        value = simple_book()
        value['extra'] = True
        self.reject(value, 'INVALID_SCHEMA')
        value = simple_book()
        value['manifest']['comment'] = 'x'
        self.reject(value, 'INVALID_SCHEMA')
        result = replay({'not': 'a book'})
        self.assertEqual(result['status'], 'SHADOW_INCONSISTENT')
        self.assertEqual(replay(None)['status'], 'SHADOW_INCONSISTENT')
        self.assertEqual(replay({'schema': {1}})['status'], 'SHADOW_INCONSISTENT')


class CompositionTests(unittest.TestCase):
    def test_shadow_composition_matches_direct_replay(self):
        value = simple_book()
        direct = replay(value)
        composed = DecisionNoteShadow().participation_replay(value)
        self.assertEqual(canonical(composed), canonical(direct))
        self.assertIsInstance(DecisionNoteShadow(), ShadowPolicyPort)

    def test_input_book_and_caller_state_are_untouched(self):
        value = simple_book()
        before = copy.deepcopy(value)
        replay(value)
        self.assertEqual(value, before)

    def test_determinism_and_reorder_invariance(self):
        c1, c2 = claim('c1', 10), claim('c2', 10)
        events = [original(c1, 'o1', 800), original(c2, 'o2', 500, sequence=1),
                  adjustment(c1, 'refund', 20, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')]
        first = replay(book([c1, c2], events))
        reordered = replay(book([c2, c1], [events[2], events[0], events[1]]))
        self.assertEqual(canonical(first), canonical(reordered))
        self.assertEqual(first['input_digest'], reordered['input_digest'])
        changed = dict(events[2], sequence=5)
        self.assertNotEqual(first['input_digest'],
                            replay(book([c1, c2], [events[0], events[1], changed]))['input_digest'])

    def test_overrides_are_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'missing.md'
            shadow = DecisionNoteShadow(participation_path=missing)
            result = shadow.participation_replay(simple_book())
            self.assertEqual(result['status'], 'SHADOW_NOT_BOUND')
            mutated = Path(tmp) / 'settlement.md'
            mutated.write_text(SETTLEMENT.read_text(encoding='utf-8').replace(
                '"cap_bps_of_funded_amount": 15000', '"cap_bps_of_funded_amount": 0', 1),
                encoding='utf-8')
            shadow = DecisionNoteShadow(mutated)
            self.assertEqual(shadow.participation_replay(simple_book())['status'],
                             'SHADOW_NOT_BOUND')

    def test_predecessor_outputs_unchanged(self):
        shadow = DecisionNoteShadow()
        single = shadow.participation({'class2_allocated': 95000, 'organizer_borne_refunds': 0,
                                       'F': 50000, 'paid_to_date': 0})
        self.assertEqual(single['status'], 'SHADOW_COMPUTED')
        self.assertEqual((single['shadow_base'], single['shadow_participation'],
                          single['shadow_payable']), (95000, 19000, 19000))
        deferred = shadow.deferred('revenue_participation', None)
        self.assertEqual(deferred['status'], 'SHADOW_DEFERRED')
        # The replay result carries no predecessor deferred shape.
        result = shadow.participation_replay(simple_book())
        self.assertNotIn('deferred', result)

    def test_lineage_digests_and_provenance(self):
        row = claim('c1', 10)
        value = book([row], [original(row, 'o1', 800),
                             adjustment(row, 'refund', 20, 0, {'COUNTERPARTY_PROCEEDS': 700}, 'o1')])
        result = replay(value)
        assert_envelope(self, result)
        self.assertEqual(len(result['input_digest']), 64)
        self.assertEqual(result['policy_version'], 'CAPITAL-REVSHARE-V1')
        statement = result['statements'][0]
        self.assertEqual(statement['identity'], ['synthetic-book', 'synthetic-agreement', 10])
        self.assertEqual(len(statement['revision_digest']), 64)
        self.assertEqual(len(statement['revisions']), 2)
        self.assertEqual([step['sort_key'] for step in result['trace']], [[10, 0], [20, 0]])
        self.assertEqual(result['trace'][1]['original_event_id'], 'o1')
        # Changing the observation day changes the input digest.
        self.assertNotEqual(result['input_digest'], replay(dict(value, manifest=dict(
            value['manifest'], as_of_day=99)))['input_digest'])


class CliTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, '-m', 'capital.participation', *args],
            capture_output=True, text=True, cwd=cwd or ROOT, check=False)

    def test_cli_computes_and_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'book.json'
            path.write_text(json.dumps(simple_book()), encoding='utf-8')
            proc = self.run_cli('--input', str(path))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result['status'], 'SHADOW_COMPUTED')
            path.write_text(json.dumps({'schema': 'wrong'}), encoding='utf-8')
            proc = self.run_cli('--input', str(path))
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stdout)['status'], 'SHADOW_INCONSISTENT')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['book.json'])

    def test_cli_hostile_input_and_argument_misuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'book.json'
            path.write_text('{"schema": 1, "schema": 2}', encoding='utf-8')
            self.assertEqual(self.run_cli('--input', str(path)).returncode, 1)
            path.write_text('{"schema": NaN}', encoding='utf-8')
            self.assertEqual(self.run_cli('--input', str(path)).returncode, 1)
            path.write_bytes(b'\x00' * (1048576 + 1))
            self.assertEqual(self.run_cli('--input', str(path)).returncode, 1)
            self.assertEqual(self.run_cli('--input', str(Path(tmp) / 'absent.json')).returncode, 1)
            self.assertEqual(self.run_cli().returncode, 2)
            self.assertEqual(self.run_cli(
                '--input', '-', '--window-note', str(Path(tmp) / 'absent.md')).returncode, 1)


class VectorTests(unittest.TestCase):
    def test_pinned_vectors_match_independent_expectations(self):
        vectors = json.loads(VECTORS.read_text(encoding='utf-8'))
        self.assertEqual(vectors['schema'], 'capital-participation-vectors-v1')
        spec = importlib.util.spec_from_file_location('participation_vectors', CHECKER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        shadow = DecisionNoteShadow()
        names = set()
        for row in vectors['scenarios']:
            names.add(row['name'])
            result = shadow.participation_replay(row['book'])
            self.assertEqual(module.differences(result, row['expected']), [], row['name'])
        self.assertEqual(len(names), len(vectors['scenarios']))


if __name__ == '__main__':
    unittest.main()
