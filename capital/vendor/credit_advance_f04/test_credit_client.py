"""Live child parity and transport failures; source-informed, synthetic only."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from credit_client import CreditClient, CreditClientStateError, CreditTransportUncertainty
from credit_fixture import FixtureError, decode_json, load_fixture
from credit_fsm import CreditError
from mock_credit import PROVENANCE
from test_credit_fsm import assert_not_lending
from test_credit_session import FIXTURES, JOURNEYS, fixture_session, requests

HERE = Path(__file__).resolve().parent
OFFER = requests('lifecycle')[0]
VIEW = dict(operation='view', arguments=dict(advance_id='adv-1'))


def direct(session, row):
    """Call session methods directly; no CLI dispatch or shared reply validator."""
    operation = row['operation']
    try:
        result = getattr(session, operation)(**row['arguments'])
    except CreditError as error:
        return dict(operation=operation, provenance=PROVENANCE, error={'code': error.code})
    key = {'view': 'view', 'view_claim': 'claim'}.get(operation, 'receipt')
    return dict(operation=operation, provenance=PROVENANCE, **{key: result})


class CreditClientTests(unittest.TestCase):
    def launch(self, fixture='committed.json', *, cleanup_timeout=1):
        client = CreditClient.launch(FIXTURES / fixture, cleanup_timeout=cleanup_timeout)
        self.addCleanup(client.close)
        return client

    def exchange(self, client, row):
        # Test safeguard only; no product response timeout, sleeps or polling.
        done = threading.Event()
        result = []
        def call():
            try:
                result.append(client.request(row))
            except BaseException as error:
                result.append(error)
            finally:
                done.set()
        thread = threading.Thread(target=call)
        thread.start()
        completed = done.wait(10)
        if not completed:
            client._process.kill()
        thread.join(10)
        self.assertFalse(thread.is_alive(), 'test exchange did not stop')
        self.assertTrue(completed, 'reply must arrive while stdin is still open')
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    def test_live_lifecycle_matches_direct_session(self):
        environment = dict(os.environ)
        environment.pop('PYTHONUNBUFFERED', None)
        with patch.dict(os.environ, environment, clear=True), \
                patch('credit_client.subprocess.Popen', wraps=subprocess.Popen) as launch:
            client = self.launch()
            session = fixture_session('committed.json')
            credit = None
            for source in requests('lifecycle'):
                row = deepcopy(source)
                if credit is not None:
                    if 'advance_id' in row['arguments']:
                        row['arguments']['advance_id'] = credit['advance_id']
                    if row['operation'] == 'view_claim':
                        row['arguments']['claim_id'] = credit['claim_id']
                    if (row['operation'] == 'repay'
                            and row['arguments']['repay_id'] not in
                            {r['repay_id'] for r in credit['repayments']}):
                        row['arguments']['sequence'] = credit['next_repayment_sequence']
                reply = self.exchange(client, row)
                self.assertEqual(reply, direct(session, row))
                self.assertFalse(client._process.stdin.closed)
                if 'receipt' in reply:
                    credit = reply['receipt']['credit']
                    assert_not_lending(self, reply['receipt'])
            self.assertEqual(self.exchange(client, VIEW)['view']['phase'], 'CLOSED')
            self.assertEqual(client.close(), 0)
            self.assertEqual(client.close(), 0)
            launch.assert_called_once()
            command = launch.call_args.args[0]
            self.assertEqual(command[0], sys.executable)
            self.assertNotIn('-u', command)
            self.assertEqual(command[1], str(HERE / 'credit_cli.py'))
            self.assertTrue(Path(command[3]).is_absolute())
            self.assertEqual(command[-2:], ['--requests', '-'])
            self.assertFalse(launch.call_args.kwargs['shell'])
            self.assertNotIn('stderr', launch.call_args.kwargs)

    def test_existing_journeys_match_direct_session(self):
        for name, (fixture, _) in JOURNEYS.items():
            with self.subTest(journey=name):
                session = fixture_session(fixture)
                client = self.launch(fixture)
                rejected = False
                for row in requests(name):
                    reply = self.exchange(client, row)
                    self.assertEqual(reply, direct(session, row))
                    self.assertIsNone(client.uncertainty)
                    rejected |= 'error' in reply
                    if 'receipt' in reply:
                        assert_not_lending(self, reply['receipt'])
                self.assertEqual(client.close(), int(rejected))

    def test_exact_integer_roundtrip_without_coercion(self):
        row = deepcopy(OFFER)
        # An opaque face field exercises integers above IEEE-754's exact range.
        row['arguments']['face']['caller_integer'] = 2**100 + 1
        row['arguments']['amount'] = 79_999
        client = self.launch()
        session = fixture_session('committed.json')
        self.assertEqual(self.exchange(client, row), direct(session, row))
        self.assertIs(type(self.exchange(client, VIEW)['view']['amount']), int)
        bad_amount = deepcopy(row)
        bad_amount['arguments'].update(advance_id='other', idempotency_key='other', amount=True)
        self.assertEqual(self.exchange(client, bad_amount), direct(session, bad_amount))
        self.assertEqual(client.close(), 1)

    def test_local_validation_before_write_and_valid_continuation(self):
        with patch('credit_client.subprocess.Popen') as launch:
            for value in (True, False, None, '1', 0, -1, float('nan'), float('inf'), 10**1000):
                with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                    CreditClient.launch(FIXTURES / 'committed.json', cleanup_timeout=value)
            launch.assert_not_called()
        client = self.launch()
        cycle = []
        cycle.append(cycle)
        invalid = ([], OFFER | {'x': float('nan')}, OFFER | {'x': object()},
                   OFFER | {'x': {1: 'coerced key'}}, OFFER | {'x': (1, 2)},
                   OFFER | {'x': '\ud800'}, OFFER | {'x': cycle})
        with patch.object(client._process.stdin, 'write', wraps=client._process.stdin.write) as write:
            for row in invalid:
                with self.subTest(row_type=type(row)), self.assertRaises((TypeError, FixtureError)):
                    client.request(row)
            write.assert_not_called()
        self.assertIsNone(client.uncertainty)
        self.assertEqual(self.exchange(client, OFFER), direct(fixture_session('committed.json'), OFFER))

    def test_fatal_error_is_terminal_and_domain_error_allows_explicit_continuation(self):
        client = self.launch()
        session = fixture_session('committed.json')
        self.assertEqual(self.exchange(client, VIEW), direct(session, VIEW))
        self.assertEqual(self.exchange(client, OFFER), direct(session, OFFER))
        bad = OFFER | {'extra': 1}
        reply = self.exchange(client, bad)
        self.assertEqual(reply['error']['type'], 'FixtureError')
        with self.assertRaises(CreditClientStateError):
            client.request(OFFER)
        self.assertIsNone(client.uncertainty)
        self.assertEqual(client.close(), 2)

    def fault_worker(self, reply, *, exit_after=False, stubborn=False, linger=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        log = Path(temporary.name) / 'received'
        script = Path(temporary.name) / 'worker.py'
        script.write_text('import os, sys, signal\nfrom pathlib import Path\n'
            + ('signal.signal(signal.SIGTERM, signal.SIG_IGN)\n' if stubborn else '')
            + 'line = sys.stdin.buffer.readline()\n'
            + f'log = Path({str(log)!r})\nlog.write_bytes(line)\n'
            + ('os._exit(7)\n' if exit_after else
               f'sys.stdout.buffer.write({reply!r})\nsys.stdout.buffer.flush()\nos.close(1)\n')
            + ('while True: signal.pause()\n' if stubborn or linger else
               'log.write_bytes(line + sys.stdin.buffer.read())\n'))
        popen = subprocess.Popen
        def worker(command, **kwargs):
            return popen([sys.executable, str(script)], **kwargs)
        return log, worker

    def test_startup_errors_are_terminal_including_submission_race(self):
        for error in ({'type': 'FixtureError', 'message': 'bad fixture'},
                      {'code': 'INVALID_AMOUNT'}):
            expected = dict(operation=None, provenance=PROVENANCE, error=error)
            log, worker = self.fault_worker(json.dumps(expected).encode() + b'\n')
            with patch('credit_client.subprocess.Popen', side_effect=worker) as launch:
                client = self.launch()
                self.assertEqual(self.exchange(client, OFFER), expected)
                with self.assertRaises(CreditClientStateError):
                    client.request(OFFER)
                self.assertIsNone(client.uncertainty)
                self.assertEqual(client.close(), 0)
                self.assertEqual(decode_json(log.read_bytes()), OFFER)
                launch.assert_called_once()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / 'bad.json'
        fixture.write_text('{}')
        client = CreditClient.launch(fixture, cleanup_timeout=1)
        self.addCleanup(client.close)
        try:
            reply = self.exchange(client, OFFER)
        except CreditTransportUncertainty as error:
            self.assertIsInstance(error.__cause__, BrokenPipeError)
            self.assertEqual(error.reply_bytes, b'')
        else:
            self.assertIsNone(reply['operation'])
            self.assertEqual(reply['error']['type'], 'FixtureError')
        with self.assertRaises(CreditClientStateError):
            client.request(OFFER)
        self.assertEqual(client.close(), 2)

    def test_uncertain_replies_fence_without_resend(self):
        valid = dict(operation='offer', provenance=PROVENANCE, receipt={})
        encode = lambda value: json.dumps(value).encode() + b'\n'
        faults = [b'', b'{', json.dumps(valid).encode(), b'\xff\n', b'[]\n', b'NaN\n',
                  b'{"operation":"offer","operation":"offer"}\n',
                  encode(valid | {'provenance': 'REAL'}), encode(valid | {'operation': 'view'}),
                  encode(valid | {'receipt': []}), encode(valid | {'extra': 1}),
                  encode(valid | {'error': {'code': 'X'}}),
                  encode(dict(operation='offer', provenance=PROVENANCE, view={})),
                  encode(dict(operation='offer', provenance=PROVENANCE, error={'code': 2})),
                  encode(dict(operation='offer', provenance=PROVENANCE, error={'type': 'X'})),
                  encode(dict(operation='offer', provenance=PROVENANCE,
                              error={'type': 'X', 'message': False})),
                  b'{"operation":"offer","provenance":"MOCK_CREDIT_F04_ONLY",'
                  b'"receipt":{"x":1,"x":2}}\n',
                  b'{"operation":"offer","provenance":"MOCK_CREDIT_F04_ONLY",'
                  b'"receipt":{"x":1e999}}\n',
                  encode(valid | {'receipt': {'x': '\ud800'}})]
        for raw, exited in [(raw, False) for raw in faults] + [(b'', True)]:
            with self.subTest(reply=raw, exited=exited):
                log, worker = self.fault_worker(raw, exit_after=exited)
                with patch('credit_client.subprocess.Popen', side_effect=worker) as launch:
                    client = self.launch()
                    original = deepcopy(OFFER)
                    with self.assertRaises(CreditTransportUncertainty) as caught:
                        self.exchange(client, original)
                    uncertainty = caught.exception
                    self.assertEqual(uncertainty.reply_bytes, raw)
                    self.assertEqual(uncertainty.request, OFFER)
                    self.assertEqual(decode_json(uncertainty.request_bytes), OFFER)
                    original['arguments']['advance_id'] = 'mutated'
                    self.assertEqual(uncertainty.request, OFFER)
                    for row in (OFFER, VIEW, dict(operation='reconcile', arguments={})):
                        with self.assertRaises(CreditClientStateError):
                            client.request(row)
                    self.assertEqual(client.close(), 7 if exited else 0)
                    self.assertIs(client.uncertainty, uncertainty)
                    self.assertEqual(log.read_bytes(), uncertainty.request_bytes)
                    launch.assert_called_once()

    def test_payload_kind_validation_for_reads_and_unknown_operations(self):
        for operation, wrong in (('view', 'receipt'), ('view_claim', 'view'), ('new_command', 'receipt')):
            raw = json.dumps(dict(operation=operation, provenance=PROVENANCE, **{wrong: {}})).encode()+b'\n'
            _, worker = self.fault_worker(raw)
            with self.subTest(operation=operation), patch('credit_client.subprocess.Popen', side_effect=worker):
                client = self.launch()
                with self.assertRaises(CreditTransportUncertainty):
                    self.exchange(client, dict(operation=operation, arguments={}))
                client.close()

    def test_short_write_broken_pipe_and_interrupt_fence(self):
        for fault in ('short', 'broken', 'flush', 'write_interrupt', 'read_interrupt', 'read_error'):
            with self.subTest(fault=fault):
                client = self.launch()
                if fault.startswith('read_'):
                    error = KeyboardInterrupt() if fault == 'read_interrupt' else OSError('read failure')
                    context = patch.object(client._process.stdout, 'read', side_effect=[b'{', error])
                elif fault == 'flush':
                    context = patch.object(client._process.stdin, 'flush', side_effect=OSError('flush failure'))
                else:
                    options = ({'return_value': 1} if fault == 'short' else
                               {'side_effect': KeyboardInterrupt() if fault == 'write_interrupt' else BrokenPipeError()})
                    context = patch.object(client._process.stdin, 'write', **options)
                with context as transport:
                    with self.assertRaises(CreditTransportUncertainty) as caught:
                        client.request(OFFER)
                    with self.assertRaises(CreditClientStateError):
                        client.request(OFFER)
                    self.assertEqual(transport.call_count, 2 if fault.startswith('read_') else 1)
                self.assertEqual(caught.exception.reply_bytes, b'{' if fault.startswith('read_') else b'')
                client.close()
                self.assertIs(client.uncertainty, caught.exception)

    def test_busy_and_reentrant_calls_do_not_write(self):
        client = self.launch()
        entered, release = threading.Event(), threading.Event()
        original = client._process.stdout.read
        result = []
        def read(size):
            if not entered.is_set():
                entered.set()
                if not release.wait(10):
                    raise AssertionError('test release deadline')
            return original(size)
        def call():
            try:
                result.append(client.request(OFFER))
            except BaseException as error:
                result.append(error)
        with patch.object(client._process.stdout, 'read', side_effect=read), \
                patch.object(client._process.stdin, 'write', wraps=client._process.stdin.write) as write:
            thread = threading.Thread(target=call)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(CreditClientStateError):
                    client.request(VIEW)
                with self.assertRaises(CreditClientStateError):
                    client.close()
                self.assertEqual(write.call_count, 1)
            finally:
                release.set()
                thread.join(10)
                if thread.is_alive():
                    client._process.kill()
                    thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [direct(fixture_session('committed.json'), OFFER)])
        original_write = client._process.stdin.write
        def reentrant(wire):
            with self.assertRaises(CreditClientStateError):
                client.request(VIEW)
            with self.assertRaises(CreditClientStateError):
                client.close()
            return original_write(wire)
        with patch.object(client._process.stdin, 'write', side_effect=reentrant) as write:
            self.assertEqual(self.exchange(client, VIEW)['view']['phase'], 'OFFERED')
            write.assert_called_once()

    def test_close_reaps_owned_child_and_context_exception(self):
        client = self.launch()
        with self.assertRaisesRegex(RuntimeError, 'caller failure'):
            with client:
                self.exchange(client, OFFER)
                raise RuntimeError('caller failure')
        self.assertEqual(client.close(), 0)
        self.assertTrue(client._process.stdin.closed)
        self.assertTrue(client._process.stdout.closed)
        with self.assertRaises(CreditClientStateError):
            client.request(OFFER)
        with self.assertRaises(ChildProcessError):
            os.waitpid(client._process.pid, os.WNOHANG)
        # Cleanup without any request also reaps its fresh, owned session.
        self.assertEqual(self.launch().close(), 0)

    def test_cleanup_escalation(self):
        raw = json.dumps(dict(operation='offer', provenance=PROVENANCE, receipt={})).encode()+b'\n'
        for stubborn, code in ((False, -15), (True, -9)):
            with self.subTest(stubborn=stubborn):
                _, worker = self.fault_worker(raw, stubborn=stubborn, linger=True)
                with patch('credit_client.subprocess.Popen', side_effect=worker) as launch:
                    client = self.launch(cleanup_timeout=0.1)
                    self.exchange(client, OFFER)  # worker installs handler before responding
                    with patch.object(client._process, 'terminate', wraps=client._process.terminate) as terminate, \
                            patch.object(client._process, 'kill', wraps=client._process.kill) as kill:
                        self.assertEqual(client.close(), code)
                        self.assertEqual(client.close(), code)
                        terminate.assert_called_once()
                        self.assertEqual(kill.call_count, int(stubborn))
                    launch.assert_called_once()
                    with self.assertRaises(ChildProcessError):
                        os.waitpid(client._process.pid, os.WNOHANG)

    def test_concurrent_cleanup_rejected(self):
        client = self.launch()
        entered, release = threading.Event(), threading.Event()
        wait = client._process.wait
        result = []
        def blocked_wait(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError('cleanup test deadline')
            return wait(*args, **kwargs)
        with patch.object(client._process, 'wait', side_effect=blocked_wait):
            thread = threading.Thread(target=lambda: result.append(client.close()))
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(CreditClientStateError):
                    client.close()
                with self.assertRaises(CreditClientStateError):
                    client.request(OFFER)
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [0])

    def test_import_launches_nothing(self):
        code = ('from unittest.mock import patch\n'
                'with patch("subprocess.Popen", side_effect=AssertionError("unexpected launch")):\n'
                ' import credit_client\n import example_credit_client\n')
        result = subprocess.run([sys.executable, '-c', code], cwd=HERE, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))

    def test_example_matches_direct_session_and_stops_on_error(self):
        for journey, fixture in (('lifecycle', 'committed.json'), ('boundaries', 'unbound.json')):
            with self.subTest(journey=journey):
                session = fixture_session(fixture)
                expected = []
                for row in requests(journey):
                    reply = direct(session, row)
                    expected.append(reply)
                    if 'error' in reply:
                        break
                    if 'receipt' in reply:
                        credit = reply['receipt']['credit']
                        reads = [dict(operation='view', arguments={'advance_id': credit['advance_id']})]
                        if credit['snapshot_frozen']:
                            reads.append(dict(operation='view_claim', arguments={'claim_id': credit['claim_id']}))
                        expected.extend(direct(session, read) for read in reads)
                result = subprocess.run([sys.executable, str(HERE / 'example_credit_client.py'),
                    '--fixture', str(FIXTURES / fixture), '--requests', str(FIXTURES / (journey+'.jsonl')),
                    '--cleanup-timeout', '1'], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, int(any('error' in r for r in expected)), result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual([decode_json(line) for line in result.stdout.splitlines()], expected)


if __name__ == '__main__':
    unittest.main()
