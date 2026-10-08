"""Positive and negative command vectors for any ProducerPort factory.

`run_producer_vectors(factory)` is the gate a future producer adapter must pass.
The factory is called with no arguments and must return a fresh port each time.
Passing these vectors is a local gateway check. It is not SEMANTIC_CONFORMANCE.
CAP-16 stays NOT_BOUND for the exact Protocol/Commerce producer tuple.
"""
import unittest
from pathlib import Path

from capital.producer import CreditError, PinnedFsmProducer
from capital.protocol import CreditMachine
from capital.service import CapitalService


def run_producer_vectors(factory):
    """Run every vector against a new port from `factory`. Raise AssertionError on drift."""
    if not callable(factory):
        raise AssertionError('ProducerPort factory must be callable')
    failures = []
    for name, steps in VECTORS:
        port = factory()
        try:
            _run_vector(port, name, steps)
        except AssertionError as exc:
            failures.append(str(exc))
        except CreditError as exc:
            failures.append(f'{name}: unexpected {exc.code}')
    if failures:
        raise AssertionError('\n'.join(failures))


def _run_vector(port, name, steps):
    bindings = {}
    for index, step in enumerate(steps, 1):
        label = f'{name}[{index}]'
        op = step['op']
        advance_id = step['advance_id']
        args = step.get('args', {})
        bound = step['bound'] if 'bound' in step else bindings.get(advance_id)
        key = step.get('key', f'{name}-{index}')
        try:
            result = port.apply(
                op, advance_id, idempotency_key=key, args=args, bound_settlement_id=bound)
        except CreditError as exc:
            if step.get('error') != exc.code:
                raise AssertionError(f'{label}: {exc.code} != {step.get("error")}')
            continue
        if step.get('error'):
            raise AssertionError(f'{label}: expected {step["error"]} but the command was accepted')
        if op == 'offer':
            bindings[advance_id] = args['fixture_id']
        credit = result['credit']
        if credit.get('funds_executed') is not False:
            raise AssertionError(f'{label}: funds_executed')
        if 'phase' in step and credit['phase'] != step['phase']:
            raise AssertionError(f'{label}: phase {credit["phase"]} != {step["phase"]}')
        if 'gate' in step and credit['settlement_gate'] != step['gate']:
            raise AssertionError(f'{label}: gate {credit["settlement_gate"]} != {step["gate"]}')
        if 'duplicate' in step and result['duplicate'] is not step['duplicate']:
            raise AssertionError(f'{label}: duplicate {result["duplicate"]}')
        if 'matched' in step and result.get('matched') is not step['matched']:
            raise AssertionError(f'{label}: matched')


def _offer(advance='sim-a', fixture='sim-committed', amount=60_000, **extra):
    return {'op': 'offer', 'advance_id': advance, 'args': {'fixture_id': fixture, 'amount': amount}, **extra}


def _step(op, advance='sim-a', args=None, **extra):
    body = {'op': op, 'advance_id': advance, 'args': {} if args is None else args}
    body.update(extra)
    return body


VECTORS = (
    ('accept-lifecycle', (
        _offer(),
        _step('approve', phase='APPROVED'),
        _step('bind_settlement', phase='APPROVED', gate='BOUND'),
        _step('draw', phase='DRAWN', gate='MOCK_COMMIT_OBSERVED'),
        _step('repay', args={'amount': 20_000, 'sequence': 1}, phase='DRAWN'),
        _step('repay', args={'amount': 40_000, 'sequence': 2}, phase='DRAWN'),
        _step('close', phase='CLOSED'),
        _step('reconcile', matched=True),
    )),
    ('duplicate-command-key', (
        _offer(key='same-offer', phase='OFFERED', duplicate=False),
        _offer(key='same-offer', phase='OFFERED', duplicate=True),
    )),
    ('unbound-draw-is-explicit', (
        _offer(fixture='sim-pending', amount=1_000),
        _step('approve'),
        _step('draw', phase='DRAWN', gate='UNBOUND'),
    )),
    ('reject-then-terminal', (
        _offer(amount=100),
        _step('reject', phase='REJECTED'),
        _step('approve', error='TERMINAL_IMMUTABLE'),
    )),
    ('default-keeps-exposure', (
        _offer(),
        _step('approve'),
        _step('bind_settlement'),
        _step('draw', phase='DRAWN'),
        _step('default', phase='DEFAULTED'),
        _step('repay', args={'amount': 1, 'sequence': 1}, error='TERMINAL_IMMUTABLE'),
    )),
    ('shared-face', (
        _offer('sim-a'),
        _offer('sim-b'),
        _step('approve', 'sim-a'),
        _step('approve', 'sim-b'),
        _step('bind_settlement', 'sim-a'),
        _step('bind_settlement', 'sim-b'),
        _step('draw', 'sim-a', phase='DRAWN'),
        _step('draw', 'sim-b', error='ADVANCE_EXCEEDS_OPEN_FACE'),
    )),
    ('unknown-fixture', (_offer(fixture='sim-missing', error='UNKNOWN_SETTLEMENT'),)),
    ('refund-obligation-open', (_offer(fixture='sim-refund', amount=100, error='REFUND_OBLIGATION_OPEN'),)),
    ('invalid-amount', (_offer(amount=0, error='INVALID_AMOUNT'),)),
    ('draw-before-approve', (
        _offer(),
        _step('draw', error='ILLEGAL_TRANSITION'),
    )),
    ('pending-settlement-blocks-draw', (
        _offer(fixture='sim-pending'),
        _step('approve'),
        _step('bind_settlement'),
        _step('draw', error='SETTLEMENT_NOT_COMMITTED'),
    )),
    ('bind-without-offer', (_step('bind_settlement', bound=None, error='UNKNOWN_ADVANCE'),)),
    ('close-while-outstanding', (
        _offer(),
        _step('approve'),
        _step('bind_settlement'),
        _step('draw'),
        _step('close', error='OUTSTANDING_REMAINS'),
    )),
    ('repayment-order', (
        _offer(),
        _step('approve'),
        _step('bind_settlement'),
        _step('draw'),
        _step('repay', args={'amount': 1, 'sequence': 2}, error='REPAYMENT_ORDER'),
    )),
    ('idempotency-conflict', (
        _offer(key='once'),
        _step('approve', key='once', error='IDEMPOTENCY_CONFLICT'),
    )),
)


class ProducerPortVectorTests(unittest.TestCase):
    def test_pinned_factory_passes_the_same_vectors_a_future_adapter_must_pass(self):
        calls = []

        def factory():
            calls.append('new')
            return PinnedFsmProducer()

        run_producer_vectors(factory)
        self.assertEqual(len(calls), len(VECTORS))

    def test_service_sends_commands_through_the_injected_port(self):
        seen = []

        class RecordingProducer(PinnedFsmProducer):
            def apply(self, op, advance_id, *, idempotency_key, args, bound_settlement_id):
                seen.append(op)
                return super().apply(
                    op, advance_id, idempotency_key=idempotency_key, args=args,
                    bound_settlement_id=bound_settlement_id)

        service = CapitalService(producer=RecordingProducer())
        control = CapitalService()
        body = {
            'instance_id': service.instance_id, 'operation_id': 'injected-offer', 'op': 'offer',
            'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
        }
        left = service.execute(body)
        right = control.execute({**body, 'instance_id': control.instance_id})
        self.assertEqual(seen, ['offer'])
        self.assertEqual(left['outcome'], 'ACCEPTED')
        self.assertEqual(left['result']['credit']['phase'], right['result']['credit']['phase'])
        self.assertEqual(left['result']['credit']['amount'], right['result']['credit']['amount'])
        self.assertIsInstance(service.machine, CreditMachine)
        self.assertIs(service.machine, service.producer.machine)

    def test_vectors_do_not_claim_semantic_conformance(self):
        text = Path(__file__).read_text(encoding='utf-8')
        self.assertIn('not SEMANTIC_CONFORMANCE', text)
        self.assertIn('NOT_BOUND', text)


if __name__ == '__main__':
    unittest.main()
