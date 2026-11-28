"""Positive and negative command vectors for any ProducerPort factory.

`run_producer_vectors(factory)` is the gate a future producer adapter must pass.
`run_value_isolation_vectors(factory)` additionally probes caller ownership.
The factory is called with no arguments and must return a fresh port each time.
Passing these vectors is a local gateway check. It is not SEMANTIC_CONFORMANCE.
CAP-16 stays NOT_BOUND for the exact Protocol/Commerce producer tuple.
"""
import copy
import hashlib
import unittest
from contextlib import ExitStack
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


def _isolation_commands():
    # Existing SIMULATED fixture amounts; these are ownership probes, not terms.
    return [
        ('offer', {'fixture_id': 'sim-committed', 'amount': 60_000}),
        ('approve', {}),
        ('bind_settlement', {}),
        ('draw', {}),
        ('repay', {'amount': 20_000, 'sequence': 1}),
    ]


def _isolation_apply(port, op, args):
    return port.apply(op, 'sim-a', idempotency_key='isolation-' + op.replace('_', '-'),
                      args=copy.deepcopy(args), bound_settlement_id='sim-committed')


def _same(actual, expected, label):
    if actual != expected:
        raise AssertionError(f'{label}: value-isolation invariant changed')


def _book_snapshot(port):
    # Detach expectations before obtaining the object that will be mutated.
    return copy.deepcopy({
        'view': port.view('sim-a'), 'journal': port.export_journal(),
        'canonical_state': port.canonical_state(), 'state_digest': port.state_digest(),
    })


def _assert_book(port, expected, label):
    _same(port.view('sim-a'), expected['view'], label + ' view')
    _same(port.export_journal(), expected['journal'], label + ' journal')
    canonical = port.canonical_state()
    digest = port.state_digest()
    _same(canonical, expected['canonical_state'], label + ' canonical_state')
    _same(digest, expected['state_digest'], label + ' state_digest')
    _same(digest, hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
          label + ' SHA256(canonical_state)')


def _assert_original_results(port, accepted, label):
    for op, args, original in accepted:
        expected = copy.deepcopy(original)
        expected.update(duplicate=True, applied=None)
        _same(_isolation_apply(port, op, args), expected, label + f' original {op} result')


def _seed_isolation(port, count=5):
    return [(op, copy.deepcopy(args), copy.deepcopy(_isolation_apply(port, op, args)))
            for op, args in _isolation_commands()[:count]]


def _isolation_guard(port, own, accepted):
    expected = _book_snapshot(port)
    restored = own(port.restored(copy.deepcopy(expected['journal'])))
    restored_expected = _book_snapshot(restored)
    _same(restored_expected, expected, 'restore baseline')

    def check(path):
        for producer, baseline, side in ((port, expected, 'source'),
                                         (restored, restored_expected, 'restored')):
            label = f'{path} {side}'
            _assert_book(producer, baseline, label)
            _assert_original_results(producer, accepted, label)
            _assert_book(producer, baseline, label + ' after replay')

    return check


def _mutate_credit(credit, prefix, check):
    credit['amount'] = -1
    check(prefix + '.amount')
    repayments = credit['repayments']
    if repayments:
        repayments[0]['amount'] = -2
        check(prefix + '.repayments[0].amount')
        repayments[0].clear()
        check(prefix + '.repayments[0].clear')
    repayments.append({'SIMULATED': 'caller-owned'})
    check(prefix + '.repayments.append')
    repayments.pop(0)
    check(prefix + '.repayments.pop')
    credit.pop('phase')
    check(prefix + '.phase removal')


def _mutate_result(result, prefix, check):
    _mutate_credit(result['credit'], prefix + '.credit', check)
    if result['effect'] is not None:
        result['effect']['outstanding_exposure'] = -3
        check(prefix + '.effect.outstanding_exposure')
        result['effect'].clear()
        check(prefix + '.effect.clear')


def _mutate_journal(journal, prefix, check):
    journal[0]['body']['face']['obligations'][0]['face'] = -1
    check(prefix + '[0].body.face.obligations[0].face')
    journal[0]['body']['face']['obligations'].clear()
    check(prefix + '[0].body.face.obligations.clear')
    journal[0]['body']['face']['gross'] = -2
    check(prefix + '[0].body.face.gross')
    journal[0]['body']['amount'] = -3
    check(prefix + '[0].body.amount')
    journal[0].pop('op')
    check(prefix + '[0].op removal')
    journal.append({'SIMULATED': 'caller-owned'})
    check(prefix + '.append')
    journal.pop(0)
    check(prefix + '.pop')


def _isolate_command_results(port, own):
    accepted = []
    for op, args in _isolation_commands():
        result = _isolation_apply(port, op, args)
        accepted.append((op, copy.deepcopy(args), copy.deepcopy(result)))
        check = _isolation_guard(port, own, accepted)
        _mutate_result(result, f'first {op}', check)
        duplicate = _isolation_apply(port, op, args)
        _mutate_result(duplicate, f'duplicate {op}', check)
    # Earlier command-time payloads must survive later lifecycle transitions.
    _assert_original_results(port, accepted, 'after partial repayment')


def _isolate_views(port, own):
    accepted = _seed_isolation(port)
    check = _isolation_guard(port, own, accepted)
    _mutate_credit(port.view('sim-a'), 'view', check)


def _isolate_journals(port, own):
    accepted = _seed_isolation(port)
    check = _isolation_guard(port, own, accepted)
    _mutate_journal(port.export_journal(), 'export_journal', check)


def _isolate_preview(port, own):
    accepted = _seed_isolation(port, count=3)
    check_book = _isolation_guard(port, own, accepted)
    expected = copy.deepcopy(port.preview_draw('sim-a'))
    _same(expected['credit']['phase'], 'DRAWN', 'preview scratch phase')
    _same(port.view('sim-a')['phase'], 'APPROVED', 'preview live phase')

    def check(path):
        check_book(path)
        _same(port.preview_draw('sim-a'), expected, path + ' repeated preview')
        check_book(path + ' after repeated preview')

    _mutate_result(port.preview_draw('sim-a'), 'preview', check)


def _isolate_inputs_and_restore(port, own):
    accepted = []
    for op, pristine in _isolation_commands():
        args = copy.deepcopy(pristine)
        result = port.apply(op, 'sim-a', idempotency_key='isolation-' + op.replace('_', '-'),
                            args=args, bound_settlement_id='sim-committed')
        accepted.append((op, copy.deepcopy(pristine), copy.deepcopy(result)))
        check = _isolation_guard(port, own, accepted)
        for field in pristine:
            args[field] = 'SIMULATED caller replacement'
            check(f'{op} args.{field} replacement')
        args.clear()
        check(f'{op} args.clear')

    source_expected = _book_snapshot(port)
    journal = port.export_journal()
    restored = own(port.restored(journal))
    restored_expected = _book_snapshot(restored)
    _same(restored_expected, source_expected, 'restore from caller journal')

    def check(path):
        _assert_book(port, source_expected, path + ' source')
        _assert_book(restored, restored_expected, path + ' restored')
        _assert_original_results(port, accepted, path + ' source')
        _assert_original_results(restored, accepted, path + ' restored')
        _assert_book(port, source_expected, path + ' source after replay')
        _assert_book(restored, restored_expected, path + ' restored after replay')

    _mutate_journal(journal, 'restoration journal', check)
    _mutate_credit(restored.view('sim-a'), 'restored view', check)
    _mutate_journal(restored.export_journal(), 'restored export_journal', check)
    _mutate_result(_isolation_apply(restored, *_isolation_commands()[-1]),
                   'restored duplicate repay', check)
    result = restored.apply('repay', 'sim-a', idempotency_key='isolated-second-repay',
                            args={'amount': 40_000, 'sequence': 2},
                            bound_settlement_id='sim-committed')
    second_expected = copy.deepcopy(result)
    second_expected.update(duplicate=True, applied=None)
    restored_expected = _book_snapshot(restored)
    _same(restored_expected['view']['outstanding_exposure'], 0, 'independent repayment')

    def check_second(path):
        check(path)
        replay = restored.apply('repay', 'sim-a', idempotency_key='isolated-second-repay',
                                args={'amount': 40_000, 'sequence': 2},
                                bound_settlement_id='sim-committed')
        _same(replay, second_expected, path + ' original second repayment result')
        _assert_book(restored, restored_expected, path + ' after second repayment replay')

    _mutate_result(result, 'restored first second-repay', check_second)
    _assert_book(port, source_expected, 'after independent restored repayment')
    _assert_original_results(restored, accepted, 'restored earlier command-time results')


VALUE_ISOLATION_SCENARIOS = (
    ('command-results', _isolate_command_results),
    ('views', _isolate_views),
    ('journal-exports', _isolate_journals),
    ('preview', _isolate_preview),
    ('inputs-and-restore', _isolate_inputs_and_restore),
)


def run_value_isolation_vectors(factory):
    """Local ownership checks for a fresh ProducerPort factory; stdlib only.

    Each scenario uses public methods and reports its mutated path and invariant.
    Every returned port's optional close() is registered immediately, including
    restored ports, so a failed assertion also releases owned loopback servers.
    This is not SEMANTIC_CONFORMANCE; CAP-16 remains NOT_BOUND.
    """
    if not callable(factory):
        raise AssertionError('ProducerPort factory must be callable')
    for name, scenario in VALUE_ISOLATION_SCENARIOS:
        with ExitStack() as cleanup:
            def own(port):
                close = getattr(port, 'close', None)
                if callable(close):
                    cleanup.callback(close)
                return port

            try:
                scenario(own(factory()), own)
            except AssertionError as exc:
                raise AssertionError(f'value-isolation {name}: {exc}') from exc


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
    def test_pinned_factory_passes_value_isolation_vectors(self):
        run_value_isolation_vectors(PinnedFsmProducer)

    def test_value_isolation_vectors_detect_aliases_and_close_on_failure(self):
        for mode, failure in (
            ('result', r'command-results: first offer.credit.amount source original offer result'),
            ('view', r'views: view.amount source view'),
            ('journal', r'journal-exports: export_journal\[0\].body.face.obligations\[0\].face source journal'),
            ('preview', r'preview: preview.credit.amount repeated preview'),
        ):
            with self.subTest(mode=mode):
                opened = []

                class AliasingProducer:
                    """Deliberately faulty output cache; never used by production."""

                    def __init__(self, delegate=None):
                        self.delegate = delegate or PinnedFsmProducer()
                        self.cache = {}
                        self.closed = False
                        opened.append(self)

                    def canonical_state(self):
                        return self.delegate.canonical_state()

                    def state_digest(self):
                        return self.delegate.state_digest()

                    def reset(self):
                        self.delegate.reset()
                        self.cache.clear()

                    def apply(self, op, advance_id, **kwargs):
                        result = self.delegate.apply(op, advance_id, **kwargs)
                        if not result['duplicate']:
                            # Keep caches current across transitions; only caller aliasing
                            # is faulty, so detection must name a mutation, not stale state.
                            self.cache.pop('view', None)
                            self.cache.pop('journal', None)
                        if mode != 'result':
                            return result
                        key = kwargs['idempotency_key']
                        if key not in self.cache:
                            self.cache[key] = result
                            return result
                        # Only the envelope is new; nested values alias the first response.
                        return {**self.cache[key], 'duplicate': True, 'applied': None}

                    def view(self, advance_id):
                        if mode == 'view':
                            if 'view' not in self.cache:
                                self.cache['view'] = self.delegate.view(advance_id)
                            return self.cache['view']
                        return self.delegate.view(advance_id)

                    def export_journal(self):
                        if mode == 'journal':
                            if 'journal' not in self.cache:
                                self.cache['journal'] = self.delegate.export_journal()
                            return self.cache['journal']
                        return self.delegate.export_journal()

                    def preview_draw(self, advance_id):
                        if mode == 'preview':
                            if 'preview' not in self.cache:
                                self.cache['preview'] = self.delegate.preview_draw(advance_id)
                            return self.cache['preview']
                        return self.delegate.preview_draw(advance_id)

                    def restored(self, journal):
                        return AliasingProducer(self.delegate.restored(journal))

                    def close(self):
                        self.closed = True

                with self.assertRaisesRegex(AssertionError, failure):
                    run_value_isolation_vectors(AliasingProducer)
                self.assertGreaterEqual(len(opened), 2)
                self.assertTrue(all(port.closed for port in opened))

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
