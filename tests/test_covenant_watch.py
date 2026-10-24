"""Read-only SIMULATED covenant watch and desk reason feed."""
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital import covenants, margin, risk
from capital.auth import ROLES
from capital.server import make_server
from capital.service import CapitalService
from capital.store import FileWorkspace
from capital.terms import DecisionNoteTermsPolicy
from tests.test_overlay import draw_book, terms_value, tick
from tests.test_risk import fake_subject

ROOT = Path(__file__).resolve().parents[1]
CAPS = terms_value('underwriting_depth')


def built(subjects, sim_day=0, margin_rows=None, proposals=None):
    terms = DecisionNoteTermsPolicy()
    total = sum(row['principal'] for row in subjects)
    risk_body = risk.build(subjects, [], terms=terms, sim_day=sim_day,
                           projection_outstanding_krw=total)
    return covenants.build(subjects, margin_rows or {}, {'proposals': proposals or []}, risk_body,
                           terms=terms, sim_day=sim_day)


class VectorTests(unittest.TestCase):
    def test_pinned_clear_watch_breach_vector(self):
        table = [
            (0, 'CLEAR', []),
            (30, 'WATCH', ['MATURITY_WINDOW']),
            (61, 'BREACH', ['PAST_MATURITY', 'RESERVE_CLASS_ESCALATED']),
        ]
        for day, status, codes in table:
            body = built([fake_subject('sim-pin', 1000)], sim_day=day)
            row = body['advances'][0]
            self.assertEqual((row['status'], [item['code'] for item in row['reasons']]),
                             (status, codes), day)

    def test_closed_advances_carry_no_cap_reason(self):
        # A repaid advance keeps its original amount in the journal but holds no open exposure,
        # so no U4 cap — single-advance, shared beneficiary or shared portfolio — may flag it.
        agg, total = CAPS['beneficiary_aggregate_cap_krw'], CAPS['portfolio_cap_krw']
        subjects = [
            fake_subject('sim-big', agg + 1, role='organizer-b', amount=agg + 1),
            fake_subject('sim-top', total - agg, role='organizer-c', amount=total - agg),
            fake_subject('sim-repaid', 0, role='organizer-b', amount=total),
        ]
        body = built(subjects)
        rows = {row['advance_id']: row for row in body['advances']}
        for key in ('sim-big', 'sim-top'):
            self.assertIn('U4_CAP_BREACHED', [item['code'] for item in rows[key]['reasons']], key)
        repaid = rows['sim-repaid']
        self.assertEqual((repaid['status'], repaid['reasons']), ('CLEAR', []))
        self.assertNotIn(repaid, body['watch_list'])

    def test_margin_states_are_server_reasons(self):
        subject = fake_subject('sim-margin', 1000)
        called = {'sim-margin': {'state': margin.CALLED, 'cure_deadline': 5,
                                 'effective_maturity_day': 60, 'default_eligible_day': None}}
        row = built([subject], sim_day=2, margin_rows=called)['advances'][0]
        self.assertIn('MARGIN_CALL_ACTIVE', [item['code'] for item in row['reasons']])
        row = built([subject], sim_day=6, margin_rows=called)['advances'][0]
        self.assertIn('CURE_DEADLINE_PASSED', [item['code'] for item in row['reasons']])

    def test_totals_reconcile_to_risk(self):
        service = CapitalService()
        draw_book(service, amount=90_000)
        covenant = service.covenants()
        risk_body = service.risk()
        self.assertEqual(covenant['totals']['outstanding_krw'], risk_body['totals']['outstanding_krw'])
        self.assertTrue(covenant['reconciliation']['matched'])
        self.assertFalse(covenant['enforced'])
        self.assertEqual(covenant['reserve']['coverage'], 'NOT_BOUND')


class ReadOnlyTests(unittest.TestCase):
    def test_read_changes_no_state_or_workspace_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileWorkspace.open(tmp)
            try:
                service = CapitalService(storage)
                draw_book(service, amount=50_000)
                path = next(Path(tmp).iterdir())
                before = (path.read_bytes(), service.machine.state_digest(), len(service.receipts),
                          json.dumps(service.overlay_entries, sort_keys=True))
                service.covenants()
                after = (path.read_bytes(), service.machine.state_digest(), len(service.receipts),
                         json.dumps(service.overlay_entries, sort_keys=True))
                self.assertEqual(before, after)
            finally:
                storage.close()

    def test_missing_note_is_not_bound_without_numeric_sections(self):
        terms = DecisionNoteTermsPolicy(ROOT / 'docs' / 'decisions' / 'NO_SUCH_NOTE.md')
        body = CapitalService(terms=terms).covenants()
        self.assertEqual(body['status'], 'NOT_BOUND')
        self.assertIsNone(body['covenant_digest'])
        for key in ('advances', 'watch_list', 'totals', 'caps', 'reserve', 'reconciliation',
                    'watch_window_days'):
            self.assertNotIn(key, body)


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        _, state = cls.call('/api/state')
        cls.tokens = {'organizer': state['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.session(role, cls.tokens['organizer'])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, path, token=None):
        headers = {} if token is None else {'X-Capital-Token': token}
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request('GET', path, headers=headers)
        response = client.getresponse()
        body = json.loads(response.read())
        client.close()
        return response.status, body

    @classmethod
    def session(cls, role, token):
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        body = json.dumps({'role': role}).encode()
        client.request('POST', '/api/session', body=body,
                       headers={'Content-Type': 'application/json', 'X-Capital-Token': token})
        response = client.getresponse()
        result = json.loads(response.read())
        client.close()
        return result['local_token']

    def test_route_role_gate(self):
        for role in ('organizer', 'auditor'):
            status, body = self.call('/api/risk/covenants', self.tokens[role])
            self.assertEqual(status, 200, role)
            self.assertEqual(body['mode'], covenants.MODE)
        for role in ('observer', 'agent'):
            status, body = self.call('/api/risk/covenants', self.tokens[role])
            self.assertEqual((status, body['error']), (403, 'ROLE_FORBIDDEN'), role)


if __name__ == '__main__':
    unittest.main()
