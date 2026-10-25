# Bundled policy runtime — local verification evidence

Date: 2026-10-25. Branch: `agent/capital-bundled-policy-runtime`.
Node baseline: `02bc3e5feef72d56f2f905d045746bedf455c927`.
Tools: Python 3.13.5, Node v20.19.2, npm 11.21.1, Playwright 1.58.2 / local Chromium.
All rehearsal results are **SIMULATED**, local and provisional; no real funds,
provider calls, credentials, publishing, signing or deployment. No git commit,
push, PR, issue or comment was created. Existing interrupted-attempt changes
were inspected and retained where correct.

The implementation uses the adopted 2026-10-23 supervisor ruling. Terms,
underwriting, state terms and the decision-body anchor hash the actual financial
terms note; policy hashes the settlement note; each decision row hashes its named
note. Missing inputs use NONE/null, readable invalid inputs retain source/hash,
missing expected rows stay PENDING, and invalid rows stay INVALID. Overrides are
exclusive even on failure. The ledger parser remains the single source of block
parsing and decision-index validation; financial policy values were not copied.

The 0.2.0 artifact is `build/bundled-a/capital-0.2.0.pyz`, SHA256
`f3b2f3db744c88fb85b435e03950b4a24450c68397cf5a87438ef25644ca1af2`.
`build/bundled-b/capital-0.2.0.pyz` is byte-identical. This is a same-interpreter
local build, `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`.
The artifacts contain the original runtime/static/pinned vendor set plus exactly
nonrecursive `docs/decisions/*.md`, `docs/CAP_COVERAGE.md` and
`scripts/decision_ledger.py`, with raw-byte per-file manifest hashes.

## Commands actually run and results

Verification commands are listed below; repeated inspections (`git status`,
`git diff`, `rg`, file reads) are not represented as test runs. Logs were captured
under `/tmp/bundled-*.log`; build outputs and the temporary browser configuration
are under ignored `build/`.

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_release.py' -v` | Initial: 7 tests, 1 failure (clock receipt expects APPLIED, not ACCEPTED). Corrected: 7 passed. Expanded coverage: 12 passed. |
| `python3 -m unittest discover -s tests -p 'test_terms*.py' -v` | 15 passed. |
| `python3 -m unittest tests.test_decisions tests.test_decisions_surface tests.test_policy tests.test_shadow tests.test_underwriting tests.test_facade -v` | Initial: 82 attempted, 1 failure (bundled shadow malformed input is SHADOW_INCONSISTENT) and 1 import error (module name is test_facade_contract). Both corrected. |
| `python3 -m unittest tests.test_decisions tests.test_decisions_surface tests.test_policy tests.test_shadow tests.test_underwriting tests.test_facade_contract -v` | 86 passed. |
| `python3 -m unittest tests.test_handbook -v` | 12 passed. |
| `python3 scripts/finance_vectors.py --write` | Regenerated existing 91,570-byte fixture. |
| `python3 scripts/pack_vectors.py --write` | Regenerated all 9 existing pack fixtures, including tamper/truncation variants. |
| `python3 scripts/finance_vectors.py --check` | Passed; 91,570 bytes match. Repeated after review. |
| `python3 scripts/pack_vectors.py --check` | Passed; all 9 files match. Repeated after review. |
| `python3 scripts/decision_ledger.py` | Exit 0; coverage-first index validated. |
| `python3 scripts/decision_bindings.py --check` | Passed; bundling entries now CONSUMED, unrelated pending consumers retained. |
| `python3 scripts/docs_surface.py --check` | Passed; 29 routes, 38 artifacts, 9 stages. |
| `python3 scripts/not_bound_checklist.py --check` | Exit 0. |
| `python3 scripts/auth_matrix.py --check` | Exit 0. |
| `python3 -m unittest tests.test_evidence_pack tests.test_finance_vectors -v` | 71 passed before adding the explicit pack note-provenance assertion. |
| `python3 -m unittest tests.test_evidence_pack.CorpusTests.test_pack_decision_provenance_hashes_the_actual_notes -v` | Invocation error: class is PackVectorTests. No implementation failure. |
| `python3 -m unittest tests.test_evidence_pack.PackVectorTests.test_pack_decision_provenance_hashes_the_actual_notes -v` | 1 passed. |
| `python3 -m unittest tests.test_decision_bindings tests.test_evidence_pack.PackVectorTests -v` | 27 passed. |
| `python3 -m unittest discover -s tests -p 'test_coa_candidate.py' -v` | First: 35 tests, 1 failure due to later origin/main journey regeneration. After the baseline correction described below: all 35 passed. |
| `python3 -m unittest discover -s tests -v` | Initial: 826 tests, 2 failures (stale bundling PENDING assertion; preservation guard confuses later main changes with node edits). Final: 827 passed in 174.547 seconds (exit 0). |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | All 7 pinned vendor tests passed. |
| `python3 -m compileall -q capital` | Exit 0. |
| `node --check capital/static/app.js` | Exit 0. |
| `npm ci` | Exit 0; 3 dev packages installed, 0 vulnerabilities. No dependency versions changed. |
| `npm run test:browser` | Environment failure: unrelated existing services occupy 8765/8766. Those services were left untouched. |
| `npm run test:browser -- --config build/bundled.playwright.config.cjs` | All 69 tests passed (2.4 minutes), unchanged suite/configuration except loopback port relocation and resolved paths. |
| `python3 scripts/seed_demo.py` | Passed; SIMULATED, debit=credit=385000; state_digest a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45; content_digest 2f71dab1a6b7ec3640f2c7c133b0b3acbe95036f8094f9f070bea3b37b651dca. |
| `python3 scripts/sim_journeys.py` | Passed; SIMULATED T03/T04/T05/T06, respectively 22/38/35/33 steps; integrated=false, funds_executed=false. |
| `python3 scripts/upstream_claims_check.py --execute` | Local CLAIM_CONFORMANCE 87/87; no upstream adoption claimed. |
| `python3 scripts/agent_claims_check.py --execute` | Local CLAIM_CONFORMANCE 94/94. |
| `python3 scripts/read_model_claims_check.py --execute` | Local CLAIM_CONFORMANCE 39/39. |
| `python3 scripts/ce1_claims_check.py --execute` | Local CLAIM_CONFORMANCE 49/49. |
| `python3 -m unittest discover -s tests -p 'test_storage_conformance.py' -v` | 7 passed, including 500 malformed loopback requests. |
| `python3 -m unittest tests.test_crash_replay -v` | 12 passed. |
| `python3 scripts/build_release.py --out build/bundled-a` | Exit 0; digest shown above. |
| `python3 scripts/build_release.py --out build/bundled-b` | Exit 0; same digest. |
| `cmp build/bundled-a/capital-0.2.0.pyz build/bundled-b/capital-0.2.0.pyz` | Exit 0, byte-identical. |
| `python3 scripts/smoke_release.py build/bundled-a/capital-0.2.0.pyz` | All 11 checks passed, including bound surfaces, actual-note provenance, nonzero accrual, rational remainder, persisted overlay and receipt equality after restart. |
| `git diff --check` | Exit 0. |

Inline stdlib review commands additionally verified:

- `capital/export.py` is byte-identical to both HEAD and origin/main.
- Vendor manifest bytes are unchanged; all five vendor files match both their
  locked SHA256 and node-baseline bytes.
- `capital/overlay.py`, `capital/projection.py`, `capital/ports.py`, goldens and
  `.aiops/` are untouched relative to the node baseline.
- Every artifact member matches its manifest hash and the current source bytes;
  the manifest has exactly the archive member set excluding itself.
- The bundling note's machine block differs only in the adopted raw-note hash
  contract and packaged smoke comparison; no financial policy values changed.

## Vector review

Finance changes are confined to `groups.facade_read_model` contract, definitions,
response-definition and closure digests. No journal/arithmetic/export groups
changed. The clean evidence pack gains decision-body/row provenance only, plus
the resulting decision section hash and pack digest; all other section bodies
and hashes are identical to the baseline. Existing tests continue to assert that
the embedded legacy export digest equals the unchanged golden.

Clean pack bytes: 164710 -> 166422. Truncated fixture bytes: 82355 -> 83211,
remaining an exact prefix of the new clean pack. The tampered variants still
differ by exactly one byte and retain their expected rejection reasons.
Decision section SHA256:
`45ab628d3776aa03deb2ee4d67e8434ba9543e785254d118080394c1a5c51135`.
Clean pack digest:
`c4151d23e38d168e13f9edee2af98180485ba189cdb31abccfb694969e7ff4ab`.
No new vector filenames were added, so no docs-surface registry additions were
needed; existing README needles and registry checks pass.

## Deviations and environment adjustments

1. The design's provenance STOP was superseded by the adopted supervisor ruling;
   implementation follows that ruling and adds its clarification to the note.
   No DECISION_REQUIRED file was needed.
2. Four stale bundling binding records were advanced to CONSUMED and their test
   now checks all six exact bundling bindings; the separate seed budget remains
   pending. This makes the implementation inventory match the shipped node.
3. The preservation guard had assumed main would only add guarded files, but
   origin/main also revised overlay/ports/upstream-binding and journey pins after
   this node's baseline. It now recognizes a later upstream revision only when
   the local file still matches the common ancestor byte-for-byte. The direct
   origin/main byte guard on export.py remains. The single authorized bundling
   note clarification is pinned by its complete SHA256; no broad note exemption
   was introduced. No goldens, vendor files, arithmetic or exports were changed.
4. Existing unrelated loopback services occupy the default browser ports. The
   temporary ignored configuration below remaps only the four managed ports to
   18765–18768; no tests, timeouts, assertions or permissions were changed.
   All started Capital servers were stopped by their test/smoke harnesses.
5. CI stages were run individually with the commands above, including storage,
   upstream claims, browser, packaging, seed and integrated-journey equivalents.
   The aggregate `scripts/acceptance.py` CLI was inspected with `--help`; it was
   not claimed as a separate successful real ladder run. Some unit tests print
   intentionally synthetic acceptance results; those are test fixtures, not
   evidence of an additional real ladder execution.

Temporary browser configuration actually used:

```javascript
const path = require('path');
const config = require('../playwright.config.cjs');
const root = path.resolve(__dirname, '..');
const remap = value => value.replace(/876[5-8]/g, port => String(Number(port) + 10000));
config.testDir = path.join(root, 'tests/browser');
config.use.baseURL = remap(config.use.baseURL);
for (const project of config.projects) {
  if (project.use && project.use.baseURL) project.use.baseURL = remap(project.use.baseURL);
}
for (const server of config.webServer) {
  server.url = remap(server.url);
  server.command = remap(server.command);
  if (server.command === 'python3 -m capital.server') server.command += ' --port 18765';
  server.cwd = root;
}
module.exports = config;
```

## Files changed

- `README.md`
- `capital/__init__.py`
- `capital/contract/facade-v1.json`
- `capital/decisions.py`
- `capital/policy.py`
- `capital/resources.py`
- `capital/server.py`
- `capital/service.py`
- `capital/shadow.py`
- `capital/terms.py`
- `capital/underwriting.py`
- `docs/ACCEPTANCE_KO.md`
- `docs/INTEGRATION.md`
- `docs/OPERATOR_HANDBOOK_KO.md`
- `docs/RELEASES.md`
- `docs/VALIDATION.md`
- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`
- `package-lock.json`
- `package.json`
- `scripts/build_release.py`
- `scripts/decision_ledger.py`
- `scripts/smoke_release.py`
- `tests/decision_bindings.json`
- `tests/test_coa_candidate.py`
- `tests/test_decision_bindings.py`
- `tests/test_decisions_surface.py`
- `tests/test_evidence_pack.py`
- `tests/test_handbook.py`
- `tests/test_policy.py`
- `tests/test_release.py`
- `tests/test_shadow.py`
- `tests/vectors/finance_vectors.json`
- `tests/vectors/pack/clean.json`
- `tests/vectors/pack/content-digest.json`
- `tests/vectors/pack/section-auth_matrix.json`
- `tests/vectors/pack/section-decisions.json`
- `tests/vectors/pack/section-export_manifest.json`
- `tests/vectors/pack/section-reconciliation.json`
- `tests/vectors/pack/section-workspace_audit.json`
- `tests/vectors/pack/truncated.json`
- `tests/vectors/pack/volatile.json`
- `BUNDLED_POLICY_RUNTIME_EVIDENCE.md`
