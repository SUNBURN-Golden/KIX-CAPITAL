Refund frontier analytics builder evidence — 2026-11-07

All financial data and calculations below are SIMULATED / provisional. No real
funds, providers, credentials, production deployment or upstream adoption were
used. Worktree: `agent/capital-refund-frontier-analytics`. No commits, pushes,
GitHub operations, or changes to Protocol/Commerce/.aiops were performed.

Implemented the planned opt-in projection read, detached lock-held capture,
bounded integer search cross-checked against the adopted inverse, physical-line
witnesses, completeness-aware beneficiary minima, assessed-only portfolio minima,
source/result digests, closed schemas, synthetic vectors and behavioral tests.
Rates/payees resolve through existing margin terms; existing risk goldens remain
unchanged. Positive existing refunds without sourced line attribution remain
unavailable, rather than being proportionally allocated.

Verification commands actually run (final results unless an attempt is named):

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_refund_frontier -v` (first attempt) | 25 tests, one test-expectation failure: disjoint line was already breached. Corrected the synthetic exposure; retained strict predicate. |
| `python3 -m unittest tests.test_refund_frontier tests.test_facade_contract -v` | Final narrow run: 33 tests passed. Intermediate extension had one invalid synthetic void reason; changed to the existing enum's `OPERATOR_WITHDRAWN`. |
| `python3 -m unittest discover -s tests -v` (first attempt) | 1,396 tests, one vector mismatch: this process had loaded the earlier witness code while the artifact was regenerated. Later runs use frozen code/artifacts. |
| `python3 -m unittest discover -s tests -v` (second run) | 1,400 passed in 450.154 seconds; before final zero-exposure precedence fix. |
| `python3 -m unittest discover -s tests -v` (final rerun after zero-exposure precedence regression) | 1,401 passed in 469.369 seconds. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital` | Passed. |
| `node --check capital/static/app.js` | Passed. |
| `python3 scripts/refund_frontier_vectors.py --write` | Generated 28,265-byte synthetic frontier artifact including affected-case witnesses and zero-exposure precedence. |
| `python3 scripts/refund_frontier_vectors.py --check` | Passed; 28,265 bytes match. |
| `python3 scripts/risk_scenario_vectors.py --check` | Passed; existing 37,747 bytes match, unchanged. |
| `python3 scripts/decision_ledger.py` | Passed; all six frontier entries ADOPTED in the provisional decision. |
| `python3 scripts/decision_bindings.py --check` | Passed; frontier module, route and behavioral tests registered. |
| `python3 scripts/pack_vectors.py --write` | Regenerated through its generator; all nine files byte-identical to baseline. |
| `python3 scripts/pack_vectors.py --check` | Passed; nine files match. |
| `python3 scripts/finance_vectors.py --write` | Regenerated 101,325-byte artifact for the changed facade contract. |
| `python3 scripts/finance_vectors.py --check` | Passed; 101,325 bytes match. |
| `python3 scripts/auth_matrix.py --check` | Passed. |
| `python3 scripts/docs_surface.py --check` | Passed; 36 routes, 274 artifacts, nine stages. |
| `python3 scripts/seed_demo.py` | Passed; existing state/content digests and debit=credit=385000 preserved. |
| `npm ci` | Three packages installed; audit reported zero vulnerabilities. No lockfile changes. |
| `npm run test:browser` | Startup failed: ports 8765–8767 belong to unrelated pre-existing services. Those services were left untouched. |
| `npm run test:browser -- --config=build/refund-frontier.playwright.cjs` | 76 passed in 2.3 minutes; same tests/settings, only server ports changed to 18765–18768. All suite-owned servers stopped. |
| `python3 scripts/build_release.py --out dist` | Passed; final artifact SHA256 `afaf66779698c6810275c2d8c3e887df92734f5448ec3d5c2414907fb5bae13e`. |
| `python3 scripts/build_release.py --out dist2` | Passed; same SHA256. |
| `cmp dist/capital-*.pyz dist2/capital-*.pyz` | Passed; byte-identical builds. |
| `python3 scripts/smoke_release.py dist/capital-*.pyz` | Passed all 11 packaged smoke checks. |
| `python3 build/check_refund_frontier_release.py` | New packaged opt-in route passed: SIMULATED, bundled policy BOUND, assessed-only portfolio scope. Task-owned server stopped in finally. |
| `python3 scripts/upstream_claims_check.py --execute` | Local claim conformance: 87/87 passed. No adoption claim. |
| `python3 scripts/agent_claims_check.py --execute` | 94/94 passed. |
| `python3 scripts/read_model_claims_check.py --execute` | 39/39 passed. |
| `python3 scripts/ce1_claims_check.py --execute` | 49/49 passed. |
| `python3 scripts/lifecycle_claims_check.py --execute` | 12/12 passed; optional external drift verification skipped by existing script defaults. |
| `python3 scripts/adapter_identity_claims_check.py --execute` | 30/30 passed. |
| `python3 scripts/readiness_claims_check.py --execute` | 11 passed, zero failed, two pre-existing documented divergences; optional drift verification skipped. |
| `python3 scripts/compat_preflight.py --execute` | Invalid CLI option, exit 2; corrected below. No files changed. |
| `python3 scripts/compat_preflight.py --check` | Passed; byte agreement MATCHED; adoption remains NOT_BOUND and semantic consumption HOLD. |
| `python3 scripts/sim_journeys.py --check` | Six SIMULATED journeys passed: T03=22, T04=38, T05=35, T06=33, N1=16, N2=18 steps. |
| `git diff --check` | Passed. |
| Inline Python SHA256/baseline guard | Five vendor files match manifest locks; manifest, export and historical root decision match HEAD bytes; .aiops untouched. |

The browser config is a local ignored build artifact, generated without changing
the repository's Playwright config or weakening tests:

```javascript
const config = require('../playwright.config.cjs');
const root = require('path').resolve(__dirname, '..');
config.testDir = root + '/tests/browser';
const remap = value => value.replace(/876([5-8])/g, '1876$1');
config.use.baseURL = remap(config.use.baseURL);
for (const project of config.projects) {
  if (project.use?.baseURL) project.use.baseURL = remap(project.use.baseURL);
}
for (const server of config.webServer) {
  server.command = remap(server.command);
  if (server.url.includes(':8765')) server.command += ' --port 18765';
  server.url = remap(server.url);
  server.cwd = root;
}
module.exports = config;
```

Plan deviations and support limits:

- Browser verification used alternate loopback ports because defaults were occupied.
- Decision value fingerprints conservatively identify supported semantics. The note
  is read through resources.read_note; deferred/missing entries remain unavailable,
  changed value semantics are unsupported. No tier-rate literals were copied.
- Complete registry lookup rows are exposed as canonical JSON strings with row
  digests, keeping nested response schemas closed without opening the registry's
  embedded policy shape. Numerical evaluation uses the captured full lookup rows.
- A failed overlay fold leaves the legacy NOT_BOUND sim_day null; its contract now
  permits that truthful absence rather than substituting zero.
- Final review corrected zero-exposure precedence over slice/attribution restrictions that apply only to positive exposure. Missing structural mappings and malformed eligible-face inputs still remain unavailable.
- No consequential product decision or scope expansion was needed. Pack generation
  produced no tracked changes; only the finance artifact needed a contract update.

Protected-byte verification command (run from the worktree):

```sh
python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
manifest = json.loads(Path('capital/vendor/manifest.json').read_bytes())
for name, expected in manifest['files'].items():
    assert hashlib.sha256((Path('capital/vendor') / name).read_bytes()).hexdigest() == expected
for name in ('capital/vendor/manifest.json', 'capital/export.py', 'DECISION_REQUIRED.md'):
    assert Path(name).read_bytes() == subprocess.check_output(['git', 'show', 'HEAD:' + name])
assert not subprocess.check_output(['git', 'diff', '--name-only', '--', '.aiops/',
                                    'capital/vendor/', 'capital/export.py', 'DECISION_REQUIRED.md'])
print('protected bytes OK')
PY
```
