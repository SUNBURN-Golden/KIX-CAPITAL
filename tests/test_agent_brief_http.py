"""Loopback-only disclosure and atomic release tests."""
import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from capital.agent_brief import canonical
from capital.server import make_server
from tests.test_agent_brief import DENIED, SUBJECT, issue, seed, state


class BriefHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.server = make_server(0, workspace=root / 'workspace', event_log=root / 'events.jsonl')
        self.service = self.server.service
        seed(self.service)
        self.body = issue(self.service)
        self.tokens = {role: self.server.authorizer.bind_role(role) for role in ('agent', 'organizer', 'auditor', 'observer')}
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.thread.join(5); self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def send(self, raw=None, headers=None, path='/api/agent/query_case', role='agent'):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        sent = {'Content-Type': 'application/json'}
        if role is not None:
            sent['X-Capital-Token'] = self.tokens[role]
        sent.update(headers or {})
        try:
            client.request('POST', path, body=json.dumps(self.body) if raw is None else raw, headers=sent)
            response = client.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            client.close()

    def files(self):
        return {p.relative_to(self.directory.name).as_posix(): p.read_bytes()
                for p in Path(self.directory.name).rglob('*') if p.is_file()}

    def test_uniform_denial_bytes_headers_and_no_observation(self):
        variants = [dict(raw='{}'), dict(raw='[]'), dict(raw='null'), dict(raw='{'),
                    dict(raw='{"grant_id":"' + self.body['grant_id'] + '","grant_id":"' + self.body['grant_id'] + '","subject":' + json.dumps(SUBJECT) + '}'),
                    dict(raw=json.dumps({**self.body, 'subject': {**SUBJECT, 'case_id': 'absent'}})),
                    dict(headers={'Origin': 'http://evil.invalid'}), dict(headers={'Host': 'evil.invalid'}),
                    dict(headers={'X-Capital-Token': 'unknown'}),
                    dict(headers={'X-Capital-Role': 'organizer'}),
                    dict(headers={'Sec-Fetch-Site': 'cross-site'}),
                    dict(headers={'Content-Type': 'text/plain'}), dict(headers={'Content-Length': '0'}),
                    dict(headers={'Content-Length': '8193'}), dict(raw='x' * 8193),
                    dict(headers={'Transfer-Encoding': 'chunked'}),
                    dict(path='/api/agent/query_case?include_receipts=1'),
                    dict(path='/api/agent/query_case?'), dict(role=None),
                    dict(path='http://evil.invalid/api/agent/query_case'),
                    *[dict(role=role) for role in ('organizer', 'auditor', 'observer')]]
        before = self.files()
        with patch.object(self.service.observability, 'record_http', side_effect=AssertionError('observed')) as observe:
            replies = [self.send(**variant) for variant in variants]
            self.service.revoke_agent_case_grant(self.body['grant_id'])
            replies.append(self.send())
            self.body = issue(self.service, {**SUBJECT, 'case_id': 'sim-absent'}, advance='sim-absent')
            replies.append(self.send())
            self.body = issue(self.service)
            with patch('capital.agent_brief.build', side_effect=RuntimeError('private data')):
                replies.append(self.send())
            observe.assert_not_called()
        for status, headers, raw in replies:
            self.assertEqual((status, raw), (200, canonical(DENIED)))
            filtered = [(key, value) for key, value in headers if key.lower() != 'date']
            self.assertEqual(filtered, [(key, value) for key, value in replies[0][1] if key.lower() != 'date'])
        self.assertEqual(before, self.files())

    def test_success_non_mutation_including_workspace_events_grants_and_clock(self):
        before = state(self.service); before['grants'].pop('policy')
        files = self.files()
        with patch.object(self.service, 'dossier', side_effect=AssertionError('dossier')) as dossier, \
             patch.object(self.service, '_machine_frozen', side_effect=AssertionError('global guard')), \
             patch.object(self.service.producer, 'export_journal', side_effect=AssertionError('journal')), \
             patch.object(self.service.observability, 'record_http') as observe:
            first = self.send(); second = self.send()
            dossier.assert_not_called(); observe.assert_not_called()
        self.assertEqual(first[0], 200)
        self.assertIn('facts', json.loads(first[2]))
        self.assertEqual(first[2], second[2])
        after = state(self.service); after['grants'].pop('policy')
        self.assertEqual(before, after); self.assertEqual(files, self.files())

    def test_revocation_and_period_changes_serialize_with_response_release(self):
        for change in ('revoke', 'period'):
            with self.subTest(change=change):
                self.body = issue(self.service)
                entered = threading.Event(); release = threading.Event(); changed = threading.Event()
                handler = self.server.RequestHandlerClass
                original = handler.reply
                def blocked_reply(request, *args, **kwargs):
                    entered.set()
                    if not release.wait(5): raise AssertionError('release barrier timed out')
                    return original(request, *args, **kwargs)
                replies = []
                def change_authority():
                    if change == 'revoke': self.service.revoke_agent_case_grant(self.body['grant_id'])
                    else: self.service.set_agent_logical_period(1)
                    changed.set()
                with patch.object(handler, 'reply', blocked_reply):
                    query = threading.Thread(target=lambda: replies.append(self.send()))
                    query.start()
                    try:
                        self.assertTrue(entered.wait(5))
                        changer = threading.Thread(target=change_authority); changer.start()
                        self.assertFalse(changed.wait(.05))
                    finally:
                        release.set(); query.join(5)
                    changer.join(5)
                self.assertTrue(changed.is_set())
                self.assertIn('facts', json.loads(replies[0][2]))
                self.assertEqual(self.send()[2], canonical(DENIED))

    def test_revocation_before_query_denies_and_writing_failure_is_not_retried(self):
        self.service.revoke_agent_case_grant(self.body['grant_id'])
        self.assertEqual(self.send()[2], canonical(DENIED))
        # Handler-level test avoids logging an artificial socket failure in the server.
        handler = object.__new__(self.server.RequestHandlerClass)
        handler.path = '/api/agent/query_case'
        with patch.object(handler, 'boundary'), patch.object(handler, 'principal') as principal, \
             patch.object(handler, 'reply', side_effect=OSError('closed')) as reply:
            principal.return_value.role = 'organizer'
            with self.assertRaises(OSError): handler._post_agent_case()
            self.assertEqual(reply.call_count, 1)
