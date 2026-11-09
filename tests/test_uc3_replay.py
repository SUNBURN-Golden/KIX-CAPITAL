"""Synthetic disposable hold-clock acceptance, refusal and preservation evidence."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital.resources import note_path, read_note
from capital.shadow import (COMPUTED, FALSE_FLAGS, INCONSISTENT, INPUT_UNKNOWN,
                            MONEY_MAX, NOT_BOUND, SHADOW_STATUSES,
                            ShadowInconsistent, canonical, fill_sequential, uc_partition)
from capital.uc3_replay import (INPUT_BYTES, VECTOR_PATH, check_vectors, digest,
                               evaluate_snapshot, load_policy, parse_json, replay)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/uc3_replay.py'
POLICY_KEYS = {
    'hold_path': ('CAPITAL_UC3_HOLD_CLOCK.md', (
        'hold_start_anchor', 'arrival_tranche_identity', 'eligibility_day_boundary',
        'duplicate_and_conflicting_inputs', 'operator_disposition_proposal', 'replay_capacity_bounds')),
    'settlement_path': ('CAPITAL_SETTLEMENT_POLICY.md', ('residual_and_late_cash',)),
    'shadow_path': ('CAPITAL_SHADOW_POLICY.md', (
        'shadow_math_stance', 'shadow_module_ownership', 'shadow_label_vocabulary',
        'rounding_and_tiebreak_rules', 'revshare_claim_purchase_deferral')),
}


def arrival(tid='A', day=10, amount=100, source=None):
    return {'tranche_id': tid, 'source_fact_id': source or 'fact_' + tid,
            'arrival_sim_day': day, 'amount_krw': amount, 'currency': 'KRW'}


def snapshot(day=190, arrivals=None, requests=None):
    arrivals = [arrival(), arrival('B', 189, 40)] if arrivals is None else arrivals
    total = sum({a['tranche_id']: a['amount_krw'] for a in arrivals}.values())
    return {'scenario_id': 'synthetic_uc3', 'claim_id': 'claim_1', 'as_of_sim_day': day,
            'classification': {'confirmed_cash': total, 'undistributed_cash': total,
                               'refund_outstanding': 0, 'pg_adjustment_outstanding': 0,
                               'reclassified': True, 'obligations': [
                                   {'face': total, 'distributed': 0,
                                    'cancelled_unpaid': total, 'outstanding': 0}]},
            'arrivals': arrivals, 'proposal_requests': requests or []}


def request(pid='P', tids=None, action='REVIEW_ELIGIBLE_HELD_CASH'):
    return {'proposal_id': pid, 'operator_label': 'synthetic_operator', 'action': action,
            'tranche_ids': ['A'] if tids is None else tids}


def walk(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from walk(child)
    elif type(value) is list:
        for child in value:
            yield from walk(child)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()
        assert cls.policy['status'] == COMPUTED, cls.policy

    def evaluate(self, s):
        return evaluate_snapshot(s, policy=self.policy)

    def assert_refused(self, s, reason=None):
        r = self.evaluate(s)
        self.assertEqual(r['status'], INCONSISTENT, r)
        self.assert_no_amounts(r)
        if reason:
            self.assertIn(reason, r['reason'])
        return r

    def assert_no_amounts(self, result):
        self.assertNotIn('trace', result)
        self.assertNotIn('proposals', result)
        self.assertNotIn('conservation', result)
        for row in walk(result):
            self.assertFalse(any(k.startswith('shadow_') and type(v) is int for k, v in row.items()))

    def test_boundary_days_and_independent_arrival(self):
        for day, eligible in ((189, 0), (190, 100), (191, 100), (368, 100), (369, 140), (370, 140)):
            with self.subTest(day=day):
                r = self.evaluate(snapshot(day))
                self.assertEqual(r['status'], COMPUTED)
                self.assertEqual([t['eligible_sim_day'] for t in r['trace']], [190, 369])
                self.assertEqual(r['conservation']['shadow_eligible_held_krw'], eligible)
                self.assertEqual(r['conservation']['shadow_held_krw'], 140)
        for day in (190, 369, 370):
            r = self.evaluate(snapshot(day, [arrival(), arrival('B', 189, 40), arrival('C', 190, 7)]))
            self.assertEqual(r['trace'][2]['eligible_sim_day'], 370)
            self.assertEqual(r['trace'][2]['temporal_state'],
                             'HELD_ELIGIBLE_FOR_PROPOSAL' if day == 370 else 'HELD_INELIGIBLE')
        # Late delivery uses the arrival day, not evaluation day.
        self.assertEqual(self.evaluate(snapshot(191))['trace'][0]['eligible_sim_day'], 190)

    def test_proposals_are_independent_snapshot_bound_alternatives(self):
        s = snapshot(requests=[request('P2'), request('P1'), request('hold', ['B'], 'CONTINUE_HOLD')])
        r = self.evaluate(s)
        self.assertEqual(r['status'], COMPUTED)
        self.assertEqual([p['proposal_id'] for p in r['proposals']], ['P1', 'P2', 'hold'])
        self.assertEqual(r['trace'][0]['proposal_references'], ['P1', 'P2'])
        self.assertEqual(r['trace'][1]['eligible_sim_day'], 369)
        self.assertEqual(r['conservation']['shadow_held_krw'], 140)
        self.assertEqual(r['conservation']['shadow_executed_disposition_krw'], 0)
        self.assertEqual(r['snapshot_sha256'], self.evaluate(snapshot())['snapshot_sha256'])
        for p in r['proposals']:
            self.assertEqual(p['status'], 'PROPOSED_ONLY')
            self.assertIs(p['executionAuthorized'], False)
            self.assertEqual(p['snapshot_sha256'], r['snapshot_sha256'])
            self.assertEqual(p['shadow_proposed_disposition_krw'], sum(t['shadow_amount_krw'] for t in p['selected_tranches']))
        later = self.evaluate(snapshot(191, requests=[request()]))
        self.assertNotEqual(r['snapshot_sha256'], later['snapshot_sha256'])
        self.assertEqual(self.evaluate(snapshot())['proposals'], [])

    def test_duplicates_permutations_and_obligation_canonicalization(self):
        s = snapshot(370, requests=[request('P', ['B', 'A'])])
        s['classification']['obligations'] = [
            {'face': 40, 'distributed': 0, 'cancelled_unpaid': 40, 'outstanding': 0},
            {'face': 100, 'distributed': 0, 'cancelled_unpaid': 100, 'outstanding': 0}]
        other = deepcopy(s)
        other['arrivals'].reverse()
        other['arrivals'] += [arrival()]
        other['classification']['obligations'].reverse()
        other['proposal_requests'] += [request('P', ['A', 'B'])]
        self.assertEqual(self.evaluate(s), self.evaluate(other))
        for day in (189, 190, 191):
            s = snapshot(day)
            base = self.evaluate(s)
            s['arrivals'] += [arrival()]
            self.assertEqual(base, self.evaluate(s))

    def test_identity_conflicts_are_atomic_and_lexical(self):
        for field, value in (('amount_krw', 101), ('arrival_sim_day', 11), ('source_fact_id', 'new_source')):
            s = snapshot()
            other = {**arrival(), field: value}
            s['arrivals'] += [other]
            self.assert_refused(s, 'tranche_id:A')
        s = snapshot()
        s['arrivals'] += [arrival('C', source='fact_A'), {**arrival('B', 189, 40), 'amount_krw': 41}]
        result = self.assert_refused(s)
        s['arrivals'].reverse()
        self.assertEqual(result, self.evaluate(s))
        self.assertIn('source_fact_id:fact_A,tranche_id:B', result['reason'])

    def test_proposal_refusals(self):
        for req in (request(tids=[]), request(tids=['A', 'A']), request(tids=['unknown']),
                    request(action='RELEASE'), {**request(), 'approved': True},
                    {**request(), 'operator_label': 'not authenticated'}):
            self.assert_refused(snapshot(requests=[req]))
        self.assert_refused(snapshot(189, requests=[request()]), 'premature')
        for day in (190, 191):
            self.assertEqual(self.evaluate(snapshot(day, requests=[request()]))['status'], COMPUTED)
        self.assert_refused(snapshot(requests=[request(), request(action='CONTINUE_HOLD')]), 'conflicting proposal_ids')

    def test_closed_shapes_and_types(self):
        s = snapshot()
        mutations = [
            lambda x: x.update(extra=1),
            lambda x: x.update(claim_id=['claim_1', 'claim_2']),
            lambda x: x.update(scenario_id=' bad'),
            lambda x: x.update(claim_id='é'),
            lambda x: x.update(as_of_sim_day=True),
            lambda x: x.update(arrivals={}),
            lambda x: x.update(proposal_requests={}),
            lambda x: x['classification'].update(reclassified=1),
            lambda x: x['classification'].update(confirmed_cash=True),
            lambda x: x['classification'].update(obligations=[]),
            lambda x: x['classification']['obligations'][0].update(extra=1),
            lambda x: x['classification']['obligations'][0].update(outstanding=1),
            lambda x: x['arrivals'][0].update(extra=1),
            lambda x: x['arrivals'][0].update(currency='USD'),
            lambda x: x['arrivals'][0].update(arrival_sim_day=191),
        ]
        for mutate in mutations:
            other = deepcopy(s)
            mutate(other)
            self.assert_refused(other)
        for bad in (0, -1, 1.1, True, '100', None):
            other = deepcopy(s)
            other['arrivals'][0]['amount_krw'] = bad
            self.assert_refused(other)
        for malformed in (None, [], True, 'snapshot'):
            self.assert_refused(malformed)

    def test_uc3_gate_and_partition_reconciliation(self):
        for field, value in (('reclassified', False), ('refund_outstanding', 1),
                             ('pg_adjustment_outstanding', 1), ('undistributed_cash', 139)):
            s = snapshot()
            s['classification'][field] = value
            self.assert_refused(s)
        s = snapshot()
        s['classification']['obligations'][0].update(outstanding=1, cancelled_unpaid=139)
        self.assert_refused(s, 'UC3-only')
        s = snapshot()
        s['classification']['obligations'][0].update(face=139, cancelled_unpaid=139)
        self.assert_refused(s, 'UC3-only')
        s = snapshot()
        s['classification']['confirmed_cash'] += 10
        s['classification']['obligations'][0].update(face=150, distributed=10)
        self.assertEqual(self.evaluate(s)['status'], COMPUTED)
        s['arrivals'].pop()
        self.assert_refused(s, 'reconcile')

    def test_capacity_bounds_and_unchanged_partition_domain(self):
        limits = self.policy['limits']
        s = snapshot(arrivals=[arrival()] * limits['raw_arrival_records'])
        self.assertEqual(self.evaluate(s)['status'], COMPUTED)
        s['arrivals'].append(arrival())
        self.assert_refused(s, 'raw arrival capacity')
        arrivals = [arrival('T' + str(i), 0, 1) for i in range(limits['unique_arrival_tranches'])]
        self.assertEqual(self.evaluate(snapshot(arrivals=arrivals))['status'], COMPUTED)
        self.assert_refused(snapshot(arrivals=arrivals + [arrival('extra', 0, 1)]), 'unique arrival capacity')
        s = snapshot(requests=[request()] * limits['raw_proposal_requests'])
        self.assertEqual(self.evaluate(s)['status'], COMPUTED)
        s['proposal_requests'].append(request())
        self.assert_refused(s, 'raw proposal capacity')
        self.assertEqual(self.evaluate(snapshot(arrivals=[arrival('A' * 64, source='source')]))['status'], COMPUTED)
        self.assert_refused(snapshot(arrivals=[arrival('A' * 65, source='source')]), 'identifier')
        max_day = limits['sim_day_max']
        hold = self.policy['hold_days']
        self.assertEqual(self.evaluate(snapshot(max_day, [arrival(day=max_day - hold)]))['status'], COMPUTED)
        self.assert_refused(snapshot(max_day, [arrival(day=max_day - hold + 1)]), 'eligible_sim_day')
        self.assert_refused(snapshot(max_day + 1), 'as_of_sim_day')
        self.assert_refused(snapshot(-1), 'as_of_sim_day')
        self.assertEqual(self.evaluate(snapshot(0, [arrival(day=0)]))['status'], COMPUTED)
        self.assertEqual(self.evaluate(snapshot(arrivals=[arrival(amount=MONEY_MAX)]))['status'], COMPUTED)
        for amount in (MONEY_MAX + 1, limits['max_integer_krw'], limits['max_integer_krw'] + 1):
            self.assert_refused(snapshot(arrivals=[arrival(amount=amount)]))
        # Replay's representation bound never expands any legacy primitive.
        with self.assertRaises(ShadowInconsistent):
            fill_sequential(MONEY_MAX + 1, [('A', 1)])
        with self.assertRaises(ShadowInconsistent):
            uc_partition(MONEY_MAX + 1, MONEY_MAX + 1, 0, True, [
                {'face': MONEY_MAX + 1, 'distributed': 0, 'cancelled_unpaid': MONEY_MAX + 1, 'outstanding': 0}])
        # Isolate representation aggregate check from classification arithmetic.
        s = snapshot(arrivals=[arrival('A', amount=limits['max_integer_krw']), arrival('B', amount=1)])
        s['classification'] = snapshot()['classification']
        self.assert_refused(s, 'aggregate held')

    def test_replay_monotonicity_immutability_and_direct_equivalence(self):
        days = [189, 190, 191, 368, 369, 370]
        results = list(replay([snapshot(d) for d in days], policy=self.policy))
        self.assertEqual(results[-1], self.evaluate(snapshot(370)))
        self.assertEqual(len(results), len(days))
        self.assertEqual(len(list(replay([snapshot(190), snapshot(190)], policy=self.policy))), 2)
        results = list(replay([snapshot(190), snapshot(189), snapshot(370)], policy=self.policy))
        self.assertEqual(len(results), 2)
        self.assertIn('backward', results[-1]['reason'])
        self.assert_no_amounts(results[-1])
        self.assertEqual(self.evaluate(snapshot(189))['status'], COMPUTED)
        for changed in (snapshot(191, [arrival('B', 189, 40)]),
                        snapshot(191, [arrival(day=11), arrival('B', 189, 40)]),
                        {**snapshot(191), 'claim_id': 'other'},
                        {**snapshot(191), 'scenario_id': 'other'}):
            results = list(replay([snapshot(), changed, snapshot(370)], policy=self.policy))
            self.assertEqual(len(results), 2)
            self.assertEqual(results[-1]['status'], INCONSISTENT)
            self.assert_no_amounts(results[-1])
        initial = snapshot()
        it = replay(iter([initial, snapshot(191)]), policy=self.policy)
        next(it)
        initial['arrivals'][0]['amount_krw'] = 99
        self.assertEqual(next(it)['status'], COMPUTED)
        new = snapshot(190, [arrival(), arrival('B', 189, 40), arrival('C', 190, 7)])
        self.assertEqual(list(replay([snapshot(189), new], policy=self.policy))[-1]['status'], COMPUTED)

    def test_labels_flags_conservation_and_amount_vocabulary(self):
        for r in (self.evaluate(snapshot()), self.evaluate(snapshot(370, requests=[request()])),
                  self.evaluate(snapshot(-1)), evaluate_snapshot(snapshot(), policy={'status': NOT_BOUND})):
            self.assertIn(r['status'], SHADOW_STATUSES)
            self.assertEqual(r['mode'], 'SHADOW_NOT_APPLIED')
            self.assertEqual(r['label'], 'SIMULATED')
            self.assertIs(r['provisional'], True)
            for key in FALSE_FLAGS:
                self.assertIs(r[key], False)
            for row in walk(r):
                self.assertFalse({'distributed', 'outstanding', 'cancelled_unpaid', 'recovery_due', 'distributed_cash'} & row.keys())
            if r['status'] == COMPUTED:
                c = r['conservation']
                self.assertEqual(c['shadow_unique_input_krw'], c['shadow_held_krw'] + c['shadow_executed_disposition_krw'])
                self.assertEqual(c['shadow_held_krw'], c['shadow_eligible_held_krw'] + c['shadow_ineligible_held_krw'])
                self.assertEqual(c['shadow_held_krw'], sum(t['shadow_held_krw'] for t in r['trace']))

    def test_snapshot_digest_exact_inputs_and_policy(self):
        s = snapshot()
        facts = deepcopy(s)
        facts.pop('proposal_requests')
        self.assertEqual(self.evaluate(s)['snapshot_sha256'], digest({**facts, 'policy_references': self.policy['policy_references']}))
        other_policy = deepcopy(self.policy)
        other_policy['policy_references'][0]['note_sha256'] = 'f' * 64
        self.assertNotEqual(self.evaluate(s)['snapshot_sha256'], evaluate_snapshot(s, policy=other_policy)['snapshot_sha256'])

    def test_no_mutation_storage_provider_clock_or_source_writes(self):
        from capital.service import CapitalService
        service = CapitalService()
        def workspace():
            return (service.machine.canonical_state(), canonical(service.receipts),
                    canonical(service.overlay_entries), canonical(service.scenario_results),
                    canonical(service.storage.load()), canonical(service.workspace_view()))
        before = workspace()
        paths = [ROOT / 'capital/shadow.py', ROOT / 'capital/export.py', ROOT / 'capital/vendor/manifest.json']
        paths += [note_path(v[0]) for v in POLICY_KEYS.values()]
        manifest = json.loads((ROOT / 'capital/vendor/manifest.json').read_bytes())
        paths += [ROOT / 'capital/vendor' / p for p in manifest['files']]
        source_bytes = {p: p.read_bytes() for p in paths}
        s, p = snapshot(), deepcopy(self.policy)
        untouched = deepcopy((s, p))
        with patch('builtins.open', side_effect=AssertionError('no file IO in evaluator')), \
             patch('socket.socket', side_effect=AssertionError('no provider')), \
             patch('time.time', side_effect=AssertionError('no wall clock')), \
             patch('time.monotonic', side_effect=AssertionError('no timer')), \
             patch('time.sleep', side_effect=AssertionError('no wait')):
            self.assertEqual(len(list(replay([s, snapshot(370)], policy=p))), 2)
        self.assertEqual((s, p), untouched)
        self.assertEqual(before, workspace())
        self.assertEqual(source_bytes, {path: path.read_bytes() for path in paths})
        for filename, sha in manifest['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'capital/vendor' / filename).read_bytes()).hexdigest(), sha)
        tree = ast.parse((ROOT / 'capital/uc3_replay.py').read_bytes())
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertFalse(any(n and ('vendor' in n or n in ('capital.service', 'capital.protocol', 'capital.overlay')) for n in imports))


class PolicyTests(unittest.TestCase):
    assert_no_amounts = ReplayTests.assert_no_amounts
    def test_every_dependency_missing_or_unusable_is_unbound(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'note.md'
            for arg, (filename, keys) in POLICY_KEYS.items():
                original = read_note(note_path(filename))['block']
                for key in keys:
                    for status in (None, 'DEFERRED', 'UNDETERMINED', 'ADOPTED_BAD_VALUE'):
                        with self.subTest(key=key, status=status):
                            block = deepcopy(original)
                            if status is None:
                                block['entries'].pop(key)
                            elif status == 'ADOPTED_BAD_VALUE':
                                block['entries'][key]['value'] = None
                            else:
                                block['entries'][key]['status'] = status
                            target.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
                            policy = load_policy(**{arg: target})
                            self.assertEqual(policy['status'], NOT_BOUND, policy)
                            self.assert_no_amounts(evaluate_snapshot(snapshot(), policy=policy))
                            ref = next(r for r in policy['policy_references'] if r['note'].endswith(filename))
                            self.assertEqual(ref['notes_source'], 'OVERRIDE_FILE')

    def test_exclusive_overrides_provenance_and_malformed_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'note.md'
            for arg, (filename, _) in POLICY_KEYS.items():
                for raw in (b'', b'bad', b'\xff', b'```capital-decision-v1\n{"schema":1,"schema":2}\n```'):
                    target.write_bytes(raw)
                    policy = load_policy(**{arg: str(target)})
                    self.assertEqual(policy['status'], NOT_BOUND)
                    ref = next(r for r in policy['policy_references'] if r['note'].endswith(filename))
                    self.assertEqual(ref['note_sha256'], hashlib.sha256(raw).hexdigest())
                target.unlink()
                policy = load_policy(**{arg: target})
                self.assertEqual(policy['status'], NOT_BOUND)
                ref = policy['policy_references'][-1]
                self.assertEqual(ref['notes_source'], 'NONE')
                self.assertIsNone(ref['note_sha256'])
                target.write_bytes(note_path(filename).read_bytes())
                policy = load_policy(**{arg: target})
                self.assertEqual(policy['status'], COMPUTED)
                ref = next(r for r in policy['policy_references'] if r['note'].endswith(filename))
                self.assertEqual(ref['notes_source'], 'OVERRIDE_FILE')
                self.assertEqual(ref['block_sha256'], digest(read_note(note_path(filename))['block']))

    def test_duration_limits_are_loaded_and_contradictions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            def load_changed(arg, mutate):
                block = deepcopy(read_note(note_path(POLICY_KEYS[arg][0]))['block'])
                mutate(block['entries'])
                target = Path(temp) / (arg + '.md')
                target.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
                return load_policy(**{arg: target})
            for arg, mutate in (
                ('hold_path', lambda e: e['hold_start_anchor']['value'].update(hold_days=181)),
                ('hold_path', lambda e: e['hold_start_anchor']['value'].update(reset_existing_anchor=True)),
                ('hold_path', lambda e: e['eligibility_day_boundary']['value'].update(automatic_release=True)),
                ('hold_path', lambda e: e['replay_capacity_bounds']['value'].update(raw_arrival_records=True)),
                ('shadow_path', lambda e: e['shadow_label_vocabulary']['value'].update(constant_false_flags=[])),
                ('shadow_path', lambda e: e['rounding_and_tiebreak_rules']['value'].update(domain='expanded')),
                ('settlement_path', lambda e: e['residual_and_late_cash']['value'].update(suspense_period_days=True)),
            ):
                self.assertEqual(load_changed(arg, mutate)['status'], NOT_BOUND)
            p = load_changed('hold_path', lambda e: e['replay_capacity_bounds']['value'].update(raw_arrival_records=1))
            self.assertEqual(p['limits']['raw_arrival_records'], 1)
            self.assertEqual(evaluate_snapshot(snapshot(), policy=p)['status'], INCONSISTENT)
            # Matching changed note values prove duration is consumed, not a runtime 180 constant.
            hold = deepcopy(read_note(note_path('CAPITAL_UC3_HOLD_CLOCK.md'))['block'])
            settlement = deepcopy(read_note(note_path('CAPITAL_SETTLEMENT_POLICY.md'))['block'])
            hold['entries']['hold_start_anchor']['value']['hold_days'] = 181
            settlement['entries']['residual_and_late_cash']['value']['suspense_period_days'] = 181
            paths = []
            for index, block in enumerate((hold, settlement)):
                path = Path(temp) / str(index)
                path.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
                paths.append(path)
            p = load_policy(hold_path=paths[0], settlement_path=paths[1])
            self.assertEqual(p['status'], COMPUTED)
            self.assertEqual(evaluate_snapshot(snapshot(), policy=p)['trace'][0]['eligible_sim_day'], 191)


class CLITests(unittest.TestCase):
    def cli(self, args, data=b'', cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=data,
                              capture_output=True, cwd=cwd or ROOT, check=False)

    def test_cli_canonical_determinism_any_cwd_and_stdin(self):
        raw = canonical(snapshot()).encode()
        with tempfile.TemporaryDirectory() as temp:
            first = self.cli(['--snapshot', '-'], raw, temp)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, self.cli(['--snapshot', '-'], raw).stdout)
            self.assertEqual(first.stdout.decode(), canonical(json.loads(first.stdout)) + '\n')
            path = Path(temp) / 'input.json'
            path.write_bytes(raw)
            self.assertEqual(first.stdout, self.cli(['--snapshot', str(path)]).stdout)
            self.assertEqual(path.read_bytes(), raw)
        raw = '\n'.join(canonical(snapshot(d)) for d in (189, 190, 370)).encode()
        result = self.cli(['--replay', '-'], raw)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 3)
        raw = '\n'.join(canonical(snapshot(d)) for d in (190, 189, 370)).encode()
        result = self.cli(['--replay', '-'], raw)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_input_bound_json_strictness_and_argument_misuse(self):
        raw = canonical(snapshot()).encode()
        exact = raw + b' ' * (INPUT_BYTES - len(raw))
        self.assertEqual(self.cli(['--snapshot', '-'], exact).returncode, 0)
        for bad in (exact + b' ', b'{"x":1,"x":2}', b'{"a":NaN}', b'{"a":Infinity}',
                    b'{"a":-Infinity}', b'[]', b'\xff', b'{', b'[' * 2000):
            result = self.cli(['--snapshot', '-'], bad)
            self.assertEqual(result.returncode, 1, result.stderr)
            body = json.loads(result.stdout)
            self.assertIn(body['status'], (INPUT_UNKNOWN, INCONSISTENT))
            self.assertNotIn('trace', body)
        for args in ([], ['--snapshot', '-', '--replay', '-'], ['--check', '--snapshot', '-']):
            self.assertEqual(self.cli(args).returncode, 2)
        for raw in (b'', canonical(snapshot()).encode() + b'\n{bad'):
            result = self.cli(['--replay', '-'], raw)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            self.assertNotIn('trace', json.loads(result.stdout))
        self.assertEqual(self.cli(['--snapshot', '/no-such-uc3-input']).returncode, 1)

    def test_pinned_vector_check_and_missing_or_tampered_artifacts(self):
        self.assertGreaterEqual(check_vectors(), 10)
        result = self.cli(['--check'])
        self.assertEqual(result.returncode, 0, result.stdout)
        body = json.loads(result.stdout)
        self.assertEqual(body['status'], COMPUTED)
        self.assertEqual(body['vector_check'], 'MATCH')
        for key in FALSE_FLAGS:
            self.assertIs(body[key], False)
        raw = VECTOR_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'vector.json'
            with self.assertRaises(OSError):
                check_vectors(path)
            pack = json.loads(raw)
            pack['cases'][0]['expected'][0]['conservation']['shadow_held_krw'] += 1
            path.write_text(json.dumps(pack))
            with self.assertRaisesRegex(ValueError, 'drift'):
                check_vectors(path)
            path.write_text('{}')
            with self.assertRaises(ValueError):
                check_vectors(path)
        self.assertEqual(VECTOR_PATH.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
