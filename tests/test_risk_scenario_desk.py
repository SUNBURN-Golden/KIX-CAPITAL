"""Read-only SIMULATED comparison contracts and scoped UI prohibitions."""
import copy
import json
import re
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.risk_whatif import CATALOG
from capital.server import make_server
from capital.store import FileWorkspace
from scripts.seed_demo import build_service
from tests.facade_schema import load_contract, validate
from tests.test_overlay import tick

ROOT = Path(__file__).resolve().parents[1]


class ComparisonHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with FileWorkspace.open(self.tmp.name) as storage:
            build_service(storage)
        self.server = make_server(0, workspace=self.tmp.name)
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.service = self.server.service
        self.token = self.call('/api/state')[1]['local_token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.tmp.cleanup()

    def call(self, path, token=None, role=None):
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {}
        chosen_token = token or getattr(self, 'token', None)
        if chosen_token:
            headers['X-Capital-Token'] = chosen_token
        if role:
            headers['Content-Type'] = 'application/json'
        client.request('POST' if role else 'GET', path,
                       json.dumps({'role': role}) if role else None, headers)
        response = client.getresponse()
        body = json.loads(response.read())
        client.close()
        return response.status, body

    def snapshot(self, token=None):
        return self.call('/api/portfolio/snapshot?instance_id=' + self.service.instance_id, token)

    def test_matching_pairs_have_server_results_and_leave_workspace_unchanged(self):
        frozen = copy.deepcopy((self.service._frozen(), self.service.case_fixtures,
                                self.service.producer.snapshot_inputs()))
        files = {p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir()}
        doc = load_contract()
        self.assertEqual(self.call('/api/risk/scenarios')[1]['scenarios'],
                         self.service.risk_scenarios()['scenarios'])
        for role in ('organizer', 'auditor'):
            token = self.call('/api/session', role=role)[1]['local_token']
            code, baseline = self.snapshot(token)
            self.assertEqual(code, 200)
            self.assertTrue(baseline['complete'])
            validate(baseline, {'$ref': '#/definitions/portfolio_snapshot'}, doc)
            for name in CATALOG:
                code, scenario = self.call('/api/risk/scenarios/' + name, token)
                self.assertEqual(code, 200)
                validate(scenario, {'$ref': '#/definitions/whatif_scenario'}, doc)
                for fold, digest in (('risk', 'risk_digest'), ('covenants', 'covenant_digest')):
                    self.assertEqual(scenario['reconciliation']['baseline_' + digest], baseline[fold][digest])
                    self.assertTrue(scenario[fold]['reconciliation']['matched'])
                self.assertTrue(scenario['evaluated'])
                self.assertTrue(scenario['reconciliation']['matched'])
                self.assertEqual(scenario['observed_state_digest'], baseline['cut']['state_digest'])
                for flag in ('funds_executed', 'workspace_mutated', 'write_authorized',
                             'policy_adopted', 'applied', 'enforced'):
                    self.assertIs(scenario[flag], False)
        self.assertEqual(frozen, (self.service._frozen(), self.service.case_fixtures,
                                  self.service.producer.snapshot_inputs()))
        self.assertEqual(files, {p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir()})

    def test_observer_and_agent_cannot_read_any_comparison_route(self):
        for role in ('observer', 'agent'):
            token = self.call('/api/session', role=role)[1]['local_token']
            for path in ('/api/risk/scenarios', *('/api/risk/scenarios/' + name for name in CATALOG),
                         '/api/portfolio/snapshot?instance_id=' + self.service.instance_id):
                code, body = self.call(path, token)
                self.assertEqual((code, body['error'], body['permission']),
                                 (403, 'ROLE_FORBIDDEN', 'projection:read'))

    def test_overlay_only_clock_change_invalidates_both_baseline_digests(self):
        _, baseline = self.snapshot()
        tick(self.service, 'comparison-clock', 0, 1)
        _, scenario = self.call('/api/risk/scenarios/all-watch-breach')
        self.assertEqual(scenario['observed_state_digest'], baseline['cut']['state_digest'])
        for fold, digest in (('risk', 'risk_digest'), ('covenants', 'covenant_digest')):
            self.assertNotEqual(scenario['reconciliation']['baseline_' + digest], baseline[fold][digest])
        _, refreshed = self.snapshot()
        self.assertEqual(refreshed['cut']['sim_day'], scenario['sim_day'])
        self.assertEqual(refreshed['risk']['risk_digest'], scenario['reconciliation']['baseline_risk_digest'])


class ComparisonStaticTests(unittest.TestCase):
    def test_comparison_code_is_display_only_and_role_gated(self):
        script = (ROOT / 'capital/static/app.js').read_text()
        block = script.split('// risk-scenario-desk:', 1)[1].split('// /risk-scenario-desk', 1)[0]
        for prohibited in ('innerHTML', 'insertAdjacentHTML', 'eval(', 'setInterval', 'setTimeout',
                           'BigInt', 'parseInt', 'parseFloat', 'Math.', '.reduce(', "method:",
                           "'/api/commands", "'/api/overlay", '.focus(', '||0', '|| 0', '??0', '?? 0'):
            self.assertNotIn(prohibited, block)
        # Epoch increments are request fencing. Arithmetic operators on amounts are forbidden.
        code = re.sub(r'//[^\n]*|"[^"\n]*"|\'[^\'\n]*\'|`[^`]*`', '', block)
        self.assertNotRegex(code, r'\s[+*/%]\s|\s-\s')
        paths = re.findall(r'request\(([^\n;]+)', block)
        self.assertEqual(len(paths), 3)
        self.assertIn("['organizer','auditor'].includes(currentRole())", block)
        self.assertIn("state?.auth?.role===currentRole()", block)
        self.assertIn("can('projection:read')", block)
        for digest in ('baseline_risk_digest', 'baseline_covenant_digest'):
            self.assertIn('comparisonDigest(scenario.reconciliation?.' + digest + ')', block)
        self.assertIn('invalidateComparison();', script.split('function refresh(){', 1)[1].split('}', 1)[0])

    def test_panel_has_accessible_explicit_capture_and_no_apply_controls(self):
        html = (ROOT / 'capital/static/index.html').read_text()
        panel = html.split('id="risk-comparison"', 1)[1].split('</section>', 1)[0]
        for needle in ('aria-labelledby', 'for="risk-comparison-select"', 'aria-live="polite"',
                       'aria-atomic="true"', 'Capture / refresh comparison', 'SYNTHETIC_UNADOPTED'):
            self.assertIn(needle, panel)
        self.assertNotIn('data-op', panel)
        self.assertEqual(panel.count('<button'), 1)
        css = (ROOT / 'capital/static/style.css').read_text()
        self.assertIn('#risk-comparison :focus-visible', css)
        self.assertIn('#risk-comparison .table-wrap', css)


if __name__ == '__main__':
    unittest.main()
