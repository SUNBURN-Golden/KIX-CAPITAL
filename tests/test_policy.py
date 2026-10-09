"""Simulated policy application on disposable books. Not an executed distribution."""
import ast
import hashlib
import http.client
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from capital.policy import (
    POLICY_LABEL, SCENARIO_ID, DecisionNoteSettlementPolicy, SettlementPolicyPort,
    apply_order, default_note_path, probe_order_freeze,
)
from capital.protocol import SettlementError, SettlementMachine
from capital.scenarios import ORDER, POLICY, STATEMENT, definitions, public_invariants, replay_scenarios
from capital.server import make_server
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_SETTLEMENT_POLICY.md'
POLICY_PY = ROOT / 'capital' / 'policy.py'
QUOTE = 'PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md (CAPITAL-SETTLEMENT-POLICY-V1)'
REPLAY_DIGEST = '9fe00869ff007e628402859abc0c1070133d664ed98e3b230b025f478fd215d0'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_CASH = (0, 1, 3000, 5000, 5001, 50000, 97000, 100000)


def note_block():
    blocks = _FENCE.findall(NOTE.read_text(encoding='utf-8'))
    return json.loads(blocks[0])


def write_note(directory, mutate):
    text = NOTE.read_text(encoding='utf-8')
    match = _FENCE.search(text)
    block = json.loads(match.group(1))
    mutate(block)
    body = json.dumps(block, ensure_ascii=False, indent=2)
    path = Path(directory) / 'note.md'
    path.write_text(text[:match.start()] + '```capital-decision-v1\n' + body + '\n```' + text[match.end():], encoding='utf-8')
    return path


def labels_ok(value):
    if type(value) is dict:
        if 'label' in value and value['label'] != POLICY_LABEL:
            return False
        return all(labels_ok(item) for item in value.values())
    if type(value) is list:
        return all(labels_ok(item) for item in value)
    return True


def no_amounts(value):
    if type(value) is dict:
        for key, item in value.items():
            if any(ch.isdigit() for ch in key) or type(item) is int or type(item) is float:
                return False
            if not no_amounts(item):
                return False
        return True
    if type(value) is list:
        return all(no_amounts(item) for item in value)
    return True


class PolicyLoaderTests(unittest.TestCase):
    def test_real_note_derives_the_order_without_copied_literals(self):
        block = note_block()
        expected = block['entries']['allocation_order']['value']['derived_order_for_pinned_two_payee_policy']
        policy = DecisionNoteSettlementPolicy()
        self.assertIsInstance(policy, SettlementPolicyPort)
        status = policy.status()
        self.assertEqual(status['outcome'], 'DECIDED')
        self.assertEqual(status['policy_version'], block['policy_version'])
        self.assertEqual(status['label'], POLICY_LABEL)
        applied = policy.allocation(POLICY)
        self.assertEqual(applied['outcome'], 'DECIDED')
        self.assertEqual(applied['order'], expected)
        self.assertEqual(applied['order'][0], POLICY['residual_payee'])
        self.assertEqual(applied['alloc_version'], block['entries']['allocation_order']['value']['policy_version'])
        text = POLICY_PY.read_text(encoding='utf-8')
        self.assertNotIn('organizer', text)
        self.assertNotIn('platform', text)
        self.assertNotIn('500', text)
        self.assertIsNone(re.search(r'\[\s*[\'"][^\'"]+[\'"]\s*,', text))
        for word in ('refund_bearer', 'revenue_participation', 'claim_purchase', 'resale_prior', 'residual_and_late'):
            self.assertNotIn(word, text)
        tree = ast.parse(text)
        self.assertIsNone(re.search(r'Path\s*\(\s*__file__\s*\)', text))
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == 'default_note_path' for node in tree.body))

    def test_missing_malformed_undecided_and_unexpressible_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = DecisionNoteSettlementPolicy(Path(tmp) / 'absent.md')
            self.assertEqual(missing.status()['outcome'], 'NOT_BOUND')
            self.assertEqual(missing.status()['reason'], 'policy not bound')
            self.assertEqual(missing.unsupported(), [])

            def undecided(block):
                block['entries']['allocation_order']['status'] = 'UNDETERMINED'
                block['entries']['allocation_order']['value'] = None

            path = write_note(tmp, undecided)
            policy = DecisionNoteSettlementPolicy(path)
            self.assertEqual(policy.status()['outcome'], 'POLICY_UNDECIDED')
            self.assertIsNone(policy.allocation(POLICY)['order'])
            self.assertEqual(len(policy.unsupported()), 5)

            def deferred(block):
                block['entries']['allocation_order']['status'] = 'DEFERRED'

            self.assertEqual(DecisionNoteSettlementPolicy(write_note(tmp, deferred)).status()['outcome'], 'POLICY_UNDECIDED')

            def not_adopted(block):
                block['entries']['allocation_order']['status'] = 'NOT_ADOPTED'

            self.assertEqual(DecisionNoteSettlementPolicy(write_note(tmp, not_adopted)).status()['outcome'], 'POLICY_UNDECIDED')

            def unexpressible(block):
                block['entries']['allocation_order']['fsm_expressible'] = False

            flipped = DecisionNoteSettlementPolicy(write_note(tmp, unexpressible))
            self.assertEqual(flipped.allocation(POLICY)['outcome'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIsNone(flipped.allocation(POLICY)['order'])

            def inconsistent(block):
                block['entries']['allocation_order']['value']['derived_order_for_pinned_two_payee_policy'] = list(reversed(
                    block['entries']['allocation_order']['value']['derived_order_for_pinned_two_payee_policy']))

            broken = DecisionNoteSettlementPolicy(write_note(tmp, inconsistent))
            self.assertEqual(broken.allocation(POLICY)['outcome'], 'NOT_BOUND')
            self.assertEqual(broken.allocation(POLICY)['reason'], 'POLICY_INCONSISTENT')

            def same_class(block):
                table = block['entries']['allocation_order']['value']['class_table_ordered']
                fee_kind = None
                for row in table:
                    kept = []
                    for kind in row['payee_kinds']:
                        if kind.startswith('primary fee_payee'):
                            fee_kind = kind
                        else:
                            kept.append(kind)
                    row['payee_kinds'] = kept
                for row in table:
                    if any(kind.startswith('primary residual_payee') for kind in row['payee_kinds']):
                        row['payee_kinds'].append(fee_kind)

            collided = DecisionNoteSettlementPolicy(write_note(tmp, same_class))
            self.assertEqual(collided.allocation(POLICY)['outcome'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIn('within-class', collided.allocation(POLICY)['reason'])

            two = Path(tmp) / 'two.md'
            two.write_text(NOTE.read_text(encoding='utf-8') + '\n```capital-decision-v1\n{"schema":"capital-decision-v1"}\n```\n', encoding='utf-8')
            self.assertEqual(DecisionNoteSettlementPolicy(two).status()['outcome'], 'NOT_BOUND')


class PolicyApplicationTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def test_simulation_is_read_only_and_labels_every_output(self):
        before = (
            self.service.machine.state_digest(),
            self.service.machine.canonical_state(),
            len(self.service.receipts),
        )
        status = self.service.policy_status()
        body = self.service.policy_simulation()
        self.assertEqual(before, (
            self.service.machine.state_digest(),
            self.service.machine.canonical_state(),
            len(self.service.receipts),
        ))
        self.assertEqual(status['observed_state_digest'], before[0])
        self.assertEqual(body['observed_state_digest'], before[0])
        self.assertFalse(body['workspace_mutated'])
        self.assertFalse(body['funds_executed'])
        self.assertFalse(body['write_authorized'])
        self.assertEqual(body['outcome'], 'DECIDED')
        self.assertEqual(body['mode'], 'SIMULATED_POLICY_APPLICATION')
        self.assertTrue(body['provisional'])
        self.assertEqual([row['kind'] for row in body['comparison']], ['DECIDED', 'FIXTURE', 'FIXTURE'])
        self.assertEqual(body['comparison'][0]['id'], SCENARIO_ID)
        self.assertEqual([row['id'] for row in body['comparison'][1:]], ['shortfall-platform', 'shortfall-organizer'])
        self.assertTrue(labels_ok(status))
        self.assertTrue(labels_ok(body))
        self.assertEqual(status['label'], POLICY_LABEL)
        for row in body['comparison']:
            self.assertEqual(row['label'], POLICY_LABEL)
            self.assertTrue(all(check['matched'] for check in row['invariants']))
        decided = {line['payee']: line for line in body['comparison'][0]['per_payee']}
        fixture = {line['payee']: line for line in body['comparison'][2]['per_payee']}
        self.assertEqual(decided, fixture)
        self.assertEqual(body['comparison'][0]['kind'], 'DECIDED')
        self.assertEqual(body['comparison'][2]['kind'], 'FIXTURE')
        self.assertNotEqual(body['comparison'][0]['id'], body['comparison'][2]['id'])
        first = body['decided']['order'][0]
        self.assertEqual(decided[first]['distributed'], decided[first]['face'])
        self.assertLess(decided[body['decided']['order'][1]]['distributed'], decided[body['decided']['order'][1]]['face'])

    def test_undecided_keeps_fixture_rows_and_drops_the_decided_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            def undecided(block):
                block['entries']['allocation_order']['status'] = 'UNDETERMINED'

            service = CapitalService(policy=DecisionNoteSettlementPolicy(write_note(tmp, undecided)))
            body = service.policy_simulation()
            self.assertEqual(body['outcome'], 'POLICY_UNDECIDED')
            self.assertIsNone(body['decided'])
            self.assertEqual([row['kind'] for row in body['comparison']], ['FIXTURE', 'FIXTURE'])
            self.assertEqual(service.policy_status()['outcome'], 'POLICY_UNDECIDED')

    def test_unsupported_items_are_never_computed(self):
        body = self.service.policy_simulation()
        items = body['unsupported']
        self.assertEqual(
            [row['item'] for row in items],
            ['refund_bearer', 'resale_prior_contract_cancel_burden', 'revenue_participation', 'claim_purchase', 'residual_and_late_cash'],
        )
        for row in items:
            self.assertEqual(row['status'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIs(row['computed'], False)
            self.assertEqual(row['requires'], 'upstream FSM change')
        self.assertTrue(no_amounts(items))
        self.assertEqual(body['upstream_fsm_change_requests']['ownership'], 'upstream-owned')
        self.assertEqual(
            body['upstream_fsm_change_requests']['items'],
            note_block()['upstream_fsm_change_requests_decision_required_astra'],
        )
        with tempfile.TemporaryDirectory() as tmp:
            def unexpressible(block):
                block['entries']['allocation_order']['fsm_expressible'] = False

            service = CapitalService(policy=DecisionNoteSettlementPolicy(write_note(tmp, unexpressible)))
            flipped = service.policy_simulation()
            self.assertEqual(flipped['outcome'], 'UNSUPPORTED_BY_PINNED_FSM')
            self.assertIsNone(flipped['decided'])
            self.assertTrue(all(row['kind'] == 'FIXTURE' for row in flipped['comparison']))
            self.assertTrue(no_amounts(flipped['unsupported']))

    def test_conservation_under_the_decided_order(self):
        order = DecisionNoteSettlementPolicy().allocation(POLICY)['order']
        gross = STATEMENT['gross']
        for cash in _CASH:
            statement = dict(STATEMENT)
            statement['amount'] = cash
            statement['fee'] = gross - cash
            statement['tax'] = 0
            statement['held'] = 0
            statement['adjustment'] = 0
            result = apply_order(gross, POLICY, statement, order)
            self.assertTrue(all(row['matched'] for row in result['invariants']))
            self.assertLessEqual(sum(line['distributed'] for line in result['per_payee']), cash)
            by_payee = {line['payee']: line for line in result['per_payee']}
            first, second = order
            if cash <= by_payee[first]['face']:
                self.assertEqual(by_payee[first]['distributed'], cash)
                self.assertEqual(by_payee[second]['distributed'], 0)
            else:
                self.assertEqual(by_payee[first]['distributed'], by_payee[first]['face'])
                rest = cash - by_payee[first]['face']
                self.assertEqual(by_payee[second]['distributed'], min(by_payee[second]['face'], rest))

    def test_pinned_fsm_refuses_an_order_change_after_the_first_distribution(self):
        order = DecisionNoteSettlementPolicy().allocation(POLICY)['order']
        other = list(ORDER) if list(order) != list(ORDER) else list(reversed(ORDER))
        machine = SettlementMachine()
        machine.initiate(
            'sim-freeze', idempotency_key='init', trade_id='sim-policy-trade', gross=STATEMENT['gross'],
            debtor_role='fixture-merchant', policy=POLICY,
        )
        machine.authorize('sim-freeze', idempotency_key='auth')
        machine.capture('sim-freeze', idempotency_key='cap')
        machine.commit(
            'sim-freeze', idempotency_key='commit', movement_id=STATEMENT['movement_id'],
            gross=STATEMENT['gross'], amount=STATEMENT['amount'], fee=STATEMENT['fee'],
            tax=STATEMENT['tax'], held=STATEMENT['held'], adjustment=STATEMENT['adjustment'],
        )
        machine.distribute('sim-freeze', idempotency_key='dist', order=list(order))
        before = machine.view('sim-freeze')['claim']
        machine.distribute('sim-freeze', idempotency_key='dist-same', order=list(order))
        self.assertEqual(machine.view('sim-freeze')['claim']['distributed_cash'], before['distributed_cash'])
        with self.assertRaises(SettlementError) as caught:
            machine.distribute('sim-freeze', idempotency_key='dist-other', order=other)
        self.assertEqual(caught.exception.code, 'DISTRIBUTION_ORDER_FROZEN')
        self.assertEqual(machine.view('sim-freeze')['claim'], before)
        self.assertTrue(all(row['matched'] for row in public_invariants(before)))
        probe = probe_order_freeze(STATEMENT['gross'], POLICY, STATEMENT, order, other)
        self.assertTrue(probe['refused'])
        self.assertEqual(probe['code'], 'DISTRIBUTION_ORDER_FROZEN')
        self.assertTrue(probe['unchanged'])
        self.assertEqual(probe['same_order_added'], 0)
        body = self.service.policy_simulation()
        self.assertEqual(body['order_freeze']['code'], 'DISTRIBUTION_ORDER_FROZEN')
        self.assertTrue(body['order_freeze']['refused'])
        self.assertEqual(body['order_freeze']['attempted_order'], list(ORDER))

    def test_fixtures_stay_byte_identical_comparison_rows(self):
        raw = json.dumps(replay_scenarios(), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), REPLAY_DIGEST)
        self.assertEqual(len(definitions()), 9)
        self.assertEqual(sum(len(steps) for _i, _t, _d, steps in definitions()), 35)
        self.assertEqual(POLICY, {
            'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
            'residual_payee': 'organizer', 'fee_payee': 'platform',
        })
        self.assertEqual(ORDER, ['platform', 'organizer'])
        self.assertEqual(STATEMENT, {
            'movement_id': 'sim-move-1', 'gross': 100000, 'amount': 97000,
            'fee': 3000, 'tax': 0, 'held': 0, 'adjustment': 0,
        })
        self.assertFalse(self.service.readiness()['policy_adopted'])
        self.assertIn('어느 순서도 제품 기본 정책으로 채택하지 않습니다', (ROOT / 'capital' / 'scenarios.py').read_text(encoding='utf-8'))

    def test_readiness_quotes_the_note_and_keeps_upstream_blockers(self):
        ready = self.service.readiness()
        for cap in ('CAP-02', 'CAP-03', 'CAP-05', 'CAP-06'):
            self.assertEqual(ready['requirement_notes'][cap], QUOTE)
        group = next(row for row in ready['groups'] if row['id'] == 'financial-contracts')
        self.assertEqual(group['status'], 'DECISION_REQUIRED')
        self.assertIn('수익·원가 정의와 배분 순서/상한', group['blockers'])
        self.assertIn('채권 양도량·보유자·대가·우선순위', group['blockers'])
        self.assertTrue(any('UNSUPPORTED_BY_PINNED_FSM' in item and 'upstream FSM change' in item for item in group['blockers']))
        local = next(row for row in ready['groups'] if row['id'] == 'local-simulation')
        self.assertTrue(any('simulated policy application' in item for item in local['available']))
        self.assertIn(QUOTE, self.service.snapshot()['decisions'][1])
        with tempfile.TemporaryDirectory() as tmp:
            missing = CapitalService(policy=DecisionNoteSettlementPolicy(Path(tmp) / 'absent.md'))
            self.assertEqual(missing.readiness()['requirement_notes']['CAP-02'], 'policy not bound')


class PolicyHttpTests(unittest.TestCase):
    def test_get_does_not_mutate_and_post_is_not_found(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        service = server.service
        before = (service.machine.state_digest(), service.machine.canonical_state(), len(service.receipts))
        try:
            def get(path, token=None):
                headers = {}
                if token:
                    headers['X-Capital-Token'] = token
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path, headers=headers)
                response = client.getresponse()
                payload = json.loads(response.read().decode('utf-8'))
                status = response.status
                client.close()
                return status, payload

            code, status = get('/api/policy')
            self.assertEqual(code, 200)
            code, body = get('/api/policy/simulation')
            self.assertEqual(code, 200)
            self.assertEqual(body['outcome'], 'DECIDED')
            self.assertEqual(len(body['comparison']), 3)
            self.assertTrue(labels_ok(body))
            state_code, state = get('/api/state')
            self.assertEqual(state_code, 200)
            token = state['local_token']
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            client.request('POST', '/api/policy', headers={
                'Content-Type': 'application/json', 'X-Capital-Token': token,
            })
            response = client.getresponse()
            posted = json.loads(response.read().decode('utf-8'))
            self.assertEqual(response.status, 404)
            self.assertEqual(posted['error'], 'NOT_FOUND')
            client.close()
            observer = server.authorizer.bind_role('observer')
            denied_code, denied = get('/api/policy/simulation', observer)
            self.assertEqual(denied_code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['permission'], 'projection:read')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        self.assertEqual(before, (
            service.machine.state_digest(), service.machine.canonical_state(), len(service.receipts),
        ))


class PolicyZipappTests(unittest.TestCase):
    def test_zipapp_reports_not_bound(self):
        spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts' / 'build_release.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            pyz = module.build(tmp, ROOT)
            code = (
                'import sys\n'
                'sys.path.insert(0, sys.argv[1])\n'
                'from capital.policy import DecisionNoteSettlementPolicy, default_note_path\n'
                'print(default_note_path().is_file())\n'
                'status = DecisionNoteSettlementPolicy().status()\n'
                'print(status["outcome"])\n'
                'print(status["reason"])\n'
            )
            proc = subprocess.run([sys.executable, '-c', code, str(pyz)], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.splitlines(), ['False', 'NOT_BOUND', 'policy not bound'])
            self.assertTrue(default_note_path().is_file())


if __name__ == '__main__':
    unittest.main()
