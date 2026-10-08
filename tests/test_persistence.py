import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import (
    FileWorkspace, InMemoryStorage, WorkspaceError, canonical_bytes, verify_document,
)


def names(directory):
    return sorted(path.name for path in Path(directory).iterdir())


def command(service, op, case, operation_id, instance_override=None, **args):
    return service.execute({'instance_id': instance_override or service.instance_id, 'operation_id': operation_id,
                            'op': op, 'advance_id': case, 'args': args})


class MemoryPortTests(unittest.TestCase):
    def test_default_service_stays_in_memory(self):
        service = CapitalService()
        snap = service.snapshot()
        self.assertIs(snap['durable'], False)
        self.assertEqual(snap['workspace'], {'kind': 'MEMORY', 'status': 'ACTIVE', 'path': None})
        self.assertIn('not stage5', service.export()['note'])
        self.assertIs(service.export()['durable'], False)
        self.assertIs(service.evidence()['durable'], False)
        command(service, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=100)
        self.assertFalse(Path('workspace.json').exists())
        other = CapitalService()
        self.assertEqual(other.snapshot()['cases'], [])
        self.assertNotEqual(other.instance_id, service.instance_id)

    def test_shared_memory_port_restores_without_a_file(self):
        storage = InMemoryStorage()
        original = CapitalService(storage)
        receipt = command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
        restored = CapitalService(storage)
        self.assertNotEqual(restored.instance_id, original.instance_id)
        self.assertEqual(restored.machine.canonical_state(), original.machine.canonical_state())
        self.assertEqual(restored.machine.state_digest(), original.snapshot()['state_digest'])
        loaded = restored.operation('offer-a', restored.instance_id)
        self.assertEqual(loaded['outcome'], 'ACCEPTED')
        self.assertEqual(loaded['instance_id'], receipt['instance_id'])
        with self.assertRaisesRegex(ApiError, 'SESSION_CHANGED'):
            restored.operation('offer-a', original.instance_id)


class FileWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.open_ports = []

    def tearDown(self):
        for port in self.open_ports:
            port.close()
        self.tmp.cleanup()

    def occupy(self, port):
        self.open_ports.append(port)
        return port

    def service(self):
        return CapitalService(self.occupy(FileWorkspace.open(self.dir)))

    def test_round_trip_restores_canonical_state_and_original_receipts(self):
        original = self.service()
        accepted = command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=60000)
        command(original, 'approve', 'sim-a', 'approve-a')
        rejected = command(original, 'offer', 'sim-refund-case', 'refund-a', fixture_id='sim-refund', amount=100)
        self.assertEqual(rejected['error'], 'REFUND_OBLIGATION_OPEN')
        command(original, 'bind_settlement', 'sim-a', 'bind-a')
        drawn = command(original, 'draw', 'sim-a', 'draw-a')
        duplicate = command(original, 'draw', 'sim-a', 'draw-a')
        self.assertTrue(duplicate['transport_duplicate'])
        with self.assertRaisesRegex(ApiError, 'IDEMPOTENCY_CONFLICT'):
            command(original, 'close', 'sim-a', 'draw-a')
        command(original, 'reconcile', 'sim-a', 'reconcile-a')
        before_state = original.machine.canonical_state()
        before_digest = original.machine.state_digest()
        self.assertEqual(names(self.dir), ['workspace.json', 'workspace.json.lock'])
        document = json.loads((self.dir / 'workspace.json').read_text())
        self.assertEqual(verify_document(document)['format'], 'KIX_CAPITAL_LOCAL_WORKSPACE_V1')
        self.assertEqual(document['saved_by_instance'], original.instance_id)
        for port in self.open_ports:
            port.close()
        self.open_ports.clear()

        restored = self.service()
        self.assertNotEqual(restored.instance_id, original.instance_id)
        self.assertEqual(restored.machine.canonical_state(), before_state)
        self.assertEqual(restored.machine.state_digest(), before_digest)
        self.assertEqual(restored.snapshot()['state_digest'], before_digest)
        self.assertEqual(restored.snapshot()['durable'], 'LOCAL_FILE_WORKSPACE')
        self.assertEqual(restored.snapshot()['workspace']['status'], 'ACTIVE')
        self.assertTrue(restored.snapshot()['workspace']['path'].endswith('workspace.json'))
        self.assertIn('not stage5 durable transaction recovery', restored.export()['note'])
        self.assertTrue(restored.export()['replay_matched'])
        loaded = restored.operation('offer-a', restored.instance_id)
        self.assertEqual(loaded, accepted)
        self.assertEqual(loaded['instance_id'], original.instance_id)
        self.assertEqual(restored.operation('refund-a', restored.instance_id)['error'], 'REFUND_OBLIGATION_OPEN')
        replay = command(restored, 'draw', 'sim-a', 'draw-a')
        self.assertTrue(replay['transport_duplicate'])
        self.assertEqual(replay['result'], drawn['result'])
        with self.assertRaisesRegex(ApiError, 'IDEMPOTENCY_CONFLICT'):
            command(restored, 'close', 'sim-a', 'draw-a')
        again = command(restored, 'reconcile', 'sim-a', 'reconcile-a')
        self.assertTrue(again['transport_duplicate'])
        self.assertEqual(restored.machine.state_digest(), before_digest)
        with self.assertRaisesRegex(ApiError, 'SESSION_CHANGED'):
            command(restored, 'close', 'sim-a', 'close-old', instance_override=original.instance_id)
        self.assertEqual(loaded['role'], 'organizer')
        self.assertEqual(loaded['role_provenance'], 'SYNTHETIC_LOCAL_ROLE')
        self.assertEqual(replay['role'], 'organizer')

    def test_pre_label_file_loads_unlabeled_and_a_later_command_persists_it(self):
        original = self.service()
        accepted = command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
        digest_before = original.machine.state_digest()
        for port in self.open_ports:
            port.close()
        self.open_ports.clear()
        path = self.dir / 'workspace.json'
        document = json.loads(path.read_text())
        receipt = document['payload']['receipts']['offer-a']['receipt']
        self.assertEqual(receipt['role'], 'organizer')
        del receipt['role']
        del receipt['role_provenance']
        document['payload_sha256'] = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
        path.write_bytes(canonical_bytes(document))
        before = path.read_bytes()
        restored = self.service()
        self.assertEqual(path.read_bytes(), before)
        loaded = restored.operation('offer-a', restored.instance_id)
        self.assertEqual(loaded['role'], 'UNLABELED')
        self.assertEqual(loaded['role_provenance'], 'UNLABELED')
        self.assertEqual({key: loaded[key] for key in loaded if key not in {'role', 'role_provenance'}},
                         {key: accepted[key] for key in accepted if key not in {'role', 'role_provenance'}})
        replay = command(restored, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
        self.assertTrue(replay['transport_duplicate'])
        self.assertEqual(replay['role'], 'UNLABELED')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(restored.machine.state_digest(), digest_before)
        command(restored, 'approve', 'sim-a', 'approve-a')
        saved = json.loads(path.read_text())
        self.assertEqual(saved['payload']['receipts']['offer-a']['receipt']['role'], 'UNLABELED')
        self.assertEqual(saved['payload']['receipts']['approve-a']['receipt']['role'], 'organizer')
        self.assertEqual(saved['payload']['receipts']['approve-a']['receipt']['role_provenance'], 'SYNTHETIC_LOCAL_ROLE')

    def test_corrupt_files_are_unreadable_and_not_replaced(self):
        original = self.service()
        command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=100)
        digest = original.machine.state_digest()
        for port in self.open_ports:
            port.close()
        self.open_ports.clear()
        path = self.dir / 'workspace.json'
        intact = path.read_bytes()

        def reopen(raw=None, mutate=None):
            path.write_bytes(intact)
            if raw is not None:
                path.write_bytes(raw)
            if mutate is not None:
                document = json.loads(path.read_text())
                mutate(document)
                document['payload_sha256'] = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
                path.write_bytes(canonical_bytes(document))
            before = path.read_bytes()
            service = self.service()
            self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE')
            self.assertEqual(service.snapshot()['cases'], [])
            self.assertEqual(service.snapshot()['workspace']['kind'], 'LOCAL_FILE_WORKSPACE')
            with self.assertRaises(ApiError) as caught:
                command(service, 'offer', 'sim-b', 'offer-b', fixture_id='sim-committed', amount=100)
            self.assertEqual((caught.exception.code, caught.exception.status), ('WORKSPACE_UNREADABLE', 503))
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn('.tmp', ''.join(names(self.dir)))
            for port in self.open_ports:
                port.close()
            self.open_ports.clear()

        reopen(raw=intact[:12])
        flipped = bytearray(intact)
        flipped[flipped.find(b'sim-a')] ^= 0x01
        reopen(raw=bytes(flipped))
        reopen(mutate=lambda document: document['payload'].__setitem__('state_digest', '0' * 64))
        reopen(mutate=lambda document: document['payload']['journal'][0].__setitem__('op', 'not-an-op'))
        reopen(raw=b'{"format":"KIX_CAPITAL_LOCAL_WORKSPACE_V1","format":"OTHER"}')
        self.assertNotEqual(digest, '0' * 64)

    def test_failed_replace_keeps_the_previous_file_and_the_in_process_receipt(self):
        service = self.service()
        command(service, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=100)
        digest = service.machine.state_digest()
        previous = (self.dir / 'workspace.json').read_bytes()
        real = os.replace

        def fail(src, dst):
            raise OSError('simulated replace failure')

        os.replace = fail
        try:
            with self.assertRaises(ApiError) as caught:
                command(service, 'approve', 'sim-a', 'approve-a')
        finally:
            os.replace = real
        self.assertEqual((caught.exception.code, caught.exception.status), ('WORKSPACE_WRITE_FAILED', 503))
        self.assertEqual((self.dir / 'workspace.json').read_bytes(), previous)
        self.assertFalse(any(name.endswith('.tmp') for name in names(self.dir)))
        self.assertEqual(service.operation('approve-a', service.instance_id)['outcome'], 'ACCEPTED')
        with self.assertRaisesRegex(ApiError, 'WORKSPACE_WRITE_FAILED'):
            command(service, 'cancel', 'sim-a', 'cancel-a')
        self.assertIsNone(service.receipts.get('cancel-a'))
        for port in self.open_ports:
            port.close()
        self.open_ports.clear()
        restored = self.service()
        self.assertEqual(restored.machine.state_digest(), digest)
        self.assertEqual(restored.operation('approve-a', restored.instance_id)['outcome'], 'UNKNOWN')
        self.assertEqual(restored.operation('offer-a', restored.instance_id)['outcome'], 'ACCEPTED')

    def test_second_open_is_locked_until_release(self):
        first = self.occupy(FileWorkspace.open(self.dir))
        with self.assertRaises(WorkspaceError) as caught:
            FileWorkspace.open(self.dir)
        self.assertEqual(caught.exception.code, 'WORKSPACE_LOCKED')
        first.close()
        self.open_ports.remove(first)
        second = self.occupy(FileWorkspace.open(self.dir))
        self.assertIsNone(second.load())


class HttpWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.servers = []

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(5)
        self.tmp.cleanup()

    def start(self, workspace=None):
        server = make_server(0, workspace=self.dir if workspace is None else workspace)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server

    def request(self, server, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def state(self, server):
        status, raw = self.request(server, 'GET', '/api/state')
        self.assertEqual(status, 200)
        return json.loads(raw)

    def post(self, server, body):
        state = self.state(server)
        return self.request(server, 'POST', '/api/commands', json.dumps(body),
                            {'Content-Type': 'application/json', 'X-Capital-Token': state['local_token']})

    def test_restart_serves_the_original_receipt_to_the_new_instance(self):
        first = self.start()
        state = self.state(first)
        body = {'instance_id': state['instance_id'], 'operation_id': 'http-offer', 'op': 'offer',
                'advance_id': 'sim-http', 'args': {'fixture_id': 'sim-committed', 'amount': 100}}
        status, raw = self.post(first, body)
        self.assertEqual(status, 200)
        receipt = json.loads(raw)
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        digest = self.state(first)['state_digest']
        self.assertEqual(self.state(first)['durable'], 'LOCAL_FILE_WORKSPACE')
        first.shutdown(); first.server_close(); self.servers.pop()[1].join(5)

        second = self.start()
        restored = self.state(second)
        self.assertNotEqual(restored['instance_id'], state['instance_id'])
        self.assertEqual(restored['state_digest'], digest)
        self.assertEqual(restored['workspace']['status'], 'ACTIVE')
        self.assertEqual(restored['cases'][0]['advance_id'], 'sim-http')
        found = json.loads(self.request(second, 'GET', f"/api/operations/http-offer?instance_id={restored['instance_id']}")[1])
        self.assertEqual(found['outcome'], 'ACCEPTED')
        self.assertEqual(found['instance_id'], receipt['instance_id'])
        self.assertEqual(self.request(second, 'GET', f"/api/operations/http-offer?instance_id={state['instance_id']}")[0], 409)
        stale = dict(body, instance_id=state['instance_id'], operation_id='stale-after-restart')
        self.assertEqual(self.post(second, stale)[0], 409)
        self.assertEqual(self.state(second)['state_digest'], digest)

    def test_unreadable_workspace_serves_reads_and_disables_writes(self):
        first = self.start()
        state = self.state(first)
        body = {'instance_id': state['instance_id'], 'operation_id': 'kept', 'op': 'offer',
                'advance_id': 'sim-kept', 'args': {'fixture_id': 'sim-committed', 'amount': 50}}
        self.assertEqual(self.post(first, body)[0], 200)
        first.shutdown(); first.server_close(); self.servers.pop()[1].join(5)
        path = Path(self.dir) / 'workspace.json'
        path.write_bytes(path.read_bytes()[:8])
        damaged = path.read_bytes()
        server = self.start()
        state = self.state(server)
        self.assertEqual(state['workspace']['status'], 'WORKSPACE_UNREADABLE')
        self.assertEqual(state['cases'], [])
        self.assertEqual(state['durable'], 'LOCAL_FILE_WORKSPACE')
        status, raw = self.post(server, {'instance_id': state['instance_id'], 'operation_id': 'new', 'op': 'offer',
                                          'advance_id': 'sim-new', 'args': {'fixture_id': 'sim-committed', 'amount': 50}})
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(raw)['error'], 'WORKSPACE_UNREADABLE')
        self.assertEqual(path.read_bytes(), damaged)
        self.assertEqual(self.request(server, 'GET', '/api/evidence')[0], 200)

    def test_save_failure_keeps_the_receipt_queryable(self):
        server = self.start()
        state = self.state(server)
        body = {'instance_id': state['instance_id'], 'operation_id': 'persisted-then-failed', 'op': 'offer',
                'advance_id': 'sim-fail', 'args': {'fixture_id': 'sim-committed', 'amount': 75}}

        def fail(_document):
            raise WorkspaceError('WORKSPACE_WRITE_FAILED')

        server.service.storage.save = fail
        status, raw = self.post(server, body)
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(raw)['error'], 'WORKSPACE_WRITE_FAILED')
        found = json.loads(self.request(server, 'GET', f"/api/operations/persisted-then-failed?instance_id={state['instance_id']}")[1])
        self.assertEqual(found['outcome'], 'ACCEPTED')
        self.assertEqual(self.state(server)['workspace']['status'], 'WORKSPACE_WRITE_FAILED')
        again = dict(body, operation_id='blocked')
        self.assertEqual(self.post(server, again)[0], 503)
        self.assertEqual(json.loads(self.request(server, 'GET', f"/api/operations/blocked?instance_id={state['instance_id']}")[1])['outcome'], 'UNKNOWN')

    def test_locked_workspace_does_not_start_empty_writable(self):
        held = FileWorkspace.open(self.dir)
        try:
            server = self.start()
            state = self.state(server)
            self.assertEqual(state['workspace']['status'], 'WORKSPACE_LOCKED')
            self.assertEqual(state['cases'], [])
            status, raw = self.post(server, {'instance_id': state['instance_id'], 'operation_id': 'nope', 'op': 'offer',
                                              'advance_id': 'sim-nope', 'args': {'fixture_id': 'sim-committed', 'amount': 1}})
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(raw)['error'], 'WORKSPACE_LOCKED')
            self.assertFalse((Path(self.dir) / 'workspace.json').exists())
        finally:
            held.close()
