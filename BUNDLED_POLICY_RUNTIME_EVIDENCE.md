# Bundled policy runtime — local verification evidence

The original node record follows. The CI fix round 3 record at the end
contains the current build and verification results; earlier rounds remain historical.

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

## Conflict-fix round 1 — 2026-10-25

Resolved the supervisor-started merge of `origin/main` into
`agent/capital-bundled-policy-runtime` without aborting, committing, pushing,
rebasing or resetting. Both bundled policy runtime and main's repayment,
recovery, claim slices, shadow arithmetic, lifecycle/identity claims and
verification surfaces are retained. No messages were posted externally.
All runtime exercises use SIMULATED, provisional local data.

The combined service loads the clock/export bounds and repayment bounds through
Traversables without changing `capital/overlay.py`. Recovery and slice loaders
now use `capital.resources.note_path`, including the slice settlement-policy
input. Shadow retains main's added arguments, policy reads and calculations,
using the shared ledger parser for each bundled or explicitly selected note.
Explicit overrides remain exclusive; missing and malformed notes stay unbound.

The preservation tests retain main's historical and live byte guards plus the
reviewed node's exact-hash exception for the adopted bundling provenance
clarification. The shadow test still checks the original pre-bundling policy
result digest and now checks the two added provenance fields separately.
The release regression test exercises all newly combined loaders outside the
checkout, including missing/malformed recovery, slice and repayment inputs.

Resolved files (18):

- `README.md`
- `capital/service.py`
- `capital/shadow.py`
- `docs/INTEGRATION.md`
- `docs/OPERATOR_HANDBOOK_KO.md`
- `docs/VALIDATION.md`
- `tests/test_coa_candidate.py`
- `tests/test_decision_bindings.py`
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

Additional combination fixes: `capital/recovery.py`, `capital/slices.py`,
`tests/test_release.py`, `tests/test_shadow_slice_uc.py`, `docs/RELEASES.md`
and this evidence record. Finance and pack fixtures were regenerated from the
combined code through their existing writers, retaining all main sections.

The merged local artifact is `build/merge-bundled-a/capital-0.2.0.pyz`:
SHA256 `29dc4a74bba45cfac215f1e77b0f2ea7577bdb7e686b0f155c8751d57c020448`.
`build/merge-bundled-b/capital-0.2.0.pyz` has identical bytes. The authorized
additional set is exactly 18 paths (the 16 top-level decision Markdown files,
coverage and ledger parser). All archive members are accounted for by the
manifest, except the manifest itself, and each file's SHA256 matches.
Labels remain `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`.

Current logs use `/tmp/bundled-merge-*.log`. The initial targeted run used a
module invocation incompatible with main's `test_overlay` import and exposed
the expected provenance-only shadow digest change. Corrected discovery and
separate provenance assertions pass. An earlier full-suite run was interrupted
when test edits completed, then restarted against the final test sources.
The default browser command failed because host ports were occupied; the same
unchanged command/configuration passed in an isolated loopback namespace.

| Command / check | Conflict-fix round 1 result |
|---|---|
| `python3 -m unittest discover -s tests -p test_coa_candidate.py -v` | Exit 0; 36 tests, including historical/live guards and golden checks. |
| `python3 -m unittest discover -s tests -p test_release.py -v` | Exit 0; 13 tests, including the combined policy-loader regression. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; 7 pinned tests. |
| `python3 -m compileall -q capital` | Exit 0. |
| `node --check capital/static/app.js` | Exit 0. |
| `npm run test:browser` | Host environment port collision; no service was stopped or reused. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed, 1.9 min; unchanged suite and configuration. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 41 artifacts, 9 stages. |
| `python3 scripts/decision_ledger.py` | Exit 0; combined decision corpus validates. |
| `python3 scripts/decision_bindings.py --check` | Exit 0; bundling consumed and main consumers retained. |
| `python3 scripts/not_bound_checklist.py --check` | Exit 0. |
| `python3 scripts/auth_matrix.py --check` | Exit 0. |
| `python3 scripts/pack_vectors.py --write` / `--check` | Exit 0; all 9 regenerated pack fixtures match. |
| `python3 scripts/finance_vectors.py --write` / `--check` | Exit 0; regenerated 97,980-byte fixture matches. |
| `python3 scripts/build_release.py --out build/merge-bundled-a` / `build/merge-bundled-b` | Exit 0; identical SHA256 recorded above. |
| `cmp build/merge-bundled-a/capital-0.2.0.pyz build/merge-bundled-b/capital-0.2.0.pyz` | Exit 0; byte-identical. |
| `python3 scripts/smoke_release.py build/merge-bundled-a/capital-0.2.0.pyz` | Exit 0; all 11 checks, including actual terms accrual and persisted overlay/provenance after workspace restart outside checkout. |
| Inline stdlib archive audit | Every member matches its manifest hash; exactly the 18 authorized extra paths; tests/keysets/workspaces excluded except the pre-existing pinned vendor test. |
| Inline stdlib preservation audit | All five vendor SHA256 locks and file bytes, vendor manifest, `capital/export.py` and `capital/overlay.py` match incoming main exactly. `.aiops/` has no change against either parent. |
| `python3 -m unittest discover -s tests -v` | Exit 0; all 1,132 tests passed in 489.148 seconds on the final combined sources. |
| Merge hygiene | All 18 conflicts resolved; no unmerged index entries or conflict markers; `git diff --check origin/main` passes. The merge remains uncommitted for the supervisor. |

`git diff --cached --check` also reports three existing Markdown hard-break
spaces on lines 7–9 of the incoming `CAPITAL_UPSTREAM_REPINS.md` note. That
note is byte-identical to incoming main and was preserved; the diff against
`origin/main` has no whitespace errors.

Result: **STATUS: READY**. No consequential product decision was required.


## CI fix round 2 — 2026-10-26

Both reported CI failures were reproduced or traced to concrete causes. The
tracked `dist2/capital-0.1.0.pyz` made the unchanged package-job glob expand to
three arguments after building 0.2.0. The obsolete generated binary is removed
and `dist2/` is ignored; no workflow or acceptance timeout was changed.

The ledger loader previously compiled the same parser on every note read.
A ten-service snapshot profile measured 110 compilations and 0.481 seconds;
with exact-byte/filename compiled-code reuse it measured one compilation and
0.233 seconds. These are local diagnostic measurements, not a performance SLA.
The bounded cache stores code only: every load still reads the selected source
and executes it in a fresh module. The regression checks compilation reuse,
module-state isolation, equal-size/equal-timestamp source edits, malformed
source and missing source. There is no fallback or cached policy value.

Current artifacts: `dist/capital-0.2.0.pyz` and
`dist2/capital-0.2.0.pyz`, SHA256
`30454a639a424758f22796b6d2f5dd3cbdf9ab2c34ff1f7600548a84a7991b7d`.
Both were built with Python 3.13.5 and compare byte-identically using the exact
CI glob command. The stdlib archive audit found 77 members, exactly the 18
authorized extra inputs, and matching per-file manifest hashes. Five vendor
files match their locked SHA256 and HEAD bytes; the vendor manifest,
`capital/export.py` and `capital/overlay.py` also match HEAD bytes.
`.aiops/`, decision-note bytes, goldens and vector fixtures are unchanged.
Everything exercised is SIMULATED/provisional, unsigned and unpublished.
No commit, push or external post was made.

The host browser command encountered an existing service on a default test
port. The acceptance ladder therefore runs with its unchanged configuration
inside an isolated loopback namespace (`unshare -Urn`, then `ip link set lo up`).
Existing services were left untouched. Preliminary runs were interrupted when
the final cache fix and namespace setup were ready; the completed final run is
recorded below. Logs use `/tmp/capital-round2-*`.


The first completed acceptance run passed the unit stage (1,133 tests in
267.409 seconds, below the unchanged 300-second limit) and seven other stages.
Chromium passed 68/69; the unknown-check trace showed a gap from monotonic
8320.424 ms to 24972.6 ms while waiting for the first render, before the
reconciliation request began. The unchanged browser rerun passed that case but
timed out in failed-get (68/69 overall). Its trace is preserved at
`build/round2-browser-stall-trace.zip`; local API response times were milliseconds.
A concurrent preliminary Python 3.12 full-unit run also hit its external
300-second cap. These failed attempts are retained in the logs; no assertions,
timeouts or product logic were changed in response. A final complete acceptance
run uses Python 3.12.15 alone in an isolated loopback namespace.


Final acceptance result: **PASS**, exit 0, `ok:true` in
`build/acceptance-evidence.json`. Python 3.12.15 unit discovery completed all
1,133 tests in 257.375 seconds under the unchanged 300-second limit.
The same final ladder passed all 69 Chromium tests and every required stage.

| Command / check | CI fix round 2 result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3.12 scripts/acceptance.py'` | Exit 0; all nine stages passed; evidence `ok:true`. |
| Unit discovery through final acceptance | 1,133 passed; 257.375 seconds; legacy golden checks and export byte guards pass. |
| Storage conformance / crash replay | 19 passed. |
| Pinned vendor tests | 7 passed; all five SHA256 locks and manifest bytes unchanged. |
| Upstream claim checks | 311 passed; local claims only, no adoption. |
| Chromium through final acceptance | All 69 passed, unchanged suite/configuration in isolated loopback namespace. |
| Packaged smoke through final acceptance | All 11 checks passed; actual terms accrual, sim_day advance, workspace restart and matching overlay/provenance. |
| Seeded demo / integrated journeys | 1 / 4 passed, SIMULATED; integrated=false, funds_executed=false. |
| Release tests with Python 3.13.5 / 3.12.15 | 14 passed on each interpreter, including the new parser-cache regression. |
| Two builds and exact CI `cmp dist/capital-*.pyz dist2/capital-*.pyz` | Exit 0; byte-identical; SHA256 recorded above. Python 3.12 rebuild pair and smoke also pass. |
| `python3 -m compileall -q capital` / `node --check capital/static/app.js` | Exit 0. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 41 artifacts, 9 stages. |
| `python3 scripts/decision_bindings.py --check` / decision ledger | Exit 0. |
| Finance / pack vector checks | Exit 0; 97,980 bytes / all 9 fixtures match; no regeneration or fixture edits. |
| Archive and preservation audit | Exact authorized additions; all 77 members accounted for; vendor, legacy export, overlay, decision notes, goldens and `.aiops/` preserved. |
| `git diff --check` | Exit 0. |

Result: **STATUS: READY**. No consequential product decision was needed.
No commit, push or external post was made.

## CI fix round 3 — 2026-10-26

The reported failure was the unit stage exceeding its unchanged 300-second
limit. Profiling found that each decision-index read parsed every note twice,
including unchanged notes during repeated readiness requests. The index now
reads and hashes every selected note on every request, validates it once with
the existing ledger parser, and reuses only the summary for exactly matching
bytes. Its cache retains the most recently indexed corpus, and returned rows are deep
copies. No financial values, parser rules, CI limits or test assertions changed.
This removes redundant work; it does not establish the sole cause of the
historical CI timeout or promise a runtime under arbitrary host contention.

A local 100-read diagnostic changed from 1.019 seconds to 0.137 seconds.
The new regression verifies equal-size/equal-timestamp revisions, invalid UTF-8,
removal, restoration, current provenance, and isolation from caller mutations.
All 19 decision-surface tests pass on Python 3.13.5 and Python 3.12.15; all
14 release tests pass, including damaged archives and exclusive overrides.

Preserved unsuccessful diagnostics:

- The initial Python 3.13 discovery ran 1,133 tests in 234.894 seconds with
  one no-write snapshot failure because `capital/decisions.py` was edited while
  the fold-fuzz check was running. This was a verification-order mistake; no
  test was changed to bypass it. Subsequent full runs keep sources untouched.
- The first Python 3.12 acceptance run timed out in the 200-sequence storage
  test after earlier unit checks had completed, and Chromium passed 68/69.
  The browser trace shows an unfinished `app.js` request and no API requests
  during the stalled navigation. Host load was approximately 26 when inspected.
  Failed evidence and the trace remain in ignored `build/` as
  `fix-round3-acceptance-failed.json` and `fix-round3-browser-failed-trace.zip`.
  The unchanged ladder was rerun when observed load fell to approximately 5.

Current Python 3.13.5 artifacts: `dist/capital-0.2.0.pyz` and
`dist2/capital-0.2.0.pyz`, byte-identical with SHA256
`86b763eece31758c04fcea10f8fcb26ff02f69921a24fcc4fd879da5783c3119`.
An independent archive audit verified all 77 members and per-file manifest
hashes, including exactly the 18 authorized additional inputs. No tests,
keysets or workspace files were added; the previously pinned vendor test stays.
All five vendor files match their locked SHA256 and HEAD bytes. Their manifest,
`capital/export.py`, `capital/overlay.py`, decision notes, goldens, existing
vectors and `.aiops/` are unchanged. No Protocol or Commerce reference was edited.
All rehearsals remain SIMULATED/provisional, `LOCAL_SIMULATION_ARTIFACT`,
`signed:false`, `published:false`, with no real funds or provider calls.

Completed local checks and final acceptance results are recorded below.

Final Python 3.12 acceptance: exit 0, `ok:true` in
`build/acceptance-evidence.json` (also preserved as
`build/fix-round3-acceptance-passed.json`). All 1,134 unit tests passed in
258.880 seconds, under the unchanged 300-second timeout; all 69 Chromium tests
passed in 1.9 minutes. The command uses an isolated loopback namespace because
the host's default browser ports are shared; it changes no tests or limits.
Evidence describes the local uncommitted working tree based on HEAD
`6a7aa0f8279f1207b43873ee13d6fd2f4b9fca52`; it is not a new exact-head CI result.

| Command / check | CI fix round 3 result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3.12 scripts/acceptance.py'` | Exit 0; all nine stages passed; `ok:true`. |
| Unit stage, Python 3.12.15 | 1,134 passed in 258.880s; includes new cache regression, legacy golden checks and export byte guards. |
| `python3 -m unittest discover -s tests -v`, Python 3.13.5, final unchanged sources | Exit 0; 1,134 passed in 257.152s. |
| Storage conformance / crash replay | 19 passed. |
| Pinned vendor tests | 7 passed; five SHA256 locks and manifest preserved. |
| Upstream claim checks | 311 passed; local conformance only, no upstream adoption. |
| `npm run test:browser`, through acceptance | 69 passed in 1.9 min with unchanged suite/configuration. |
| Packaged smoke | All 11 checks passed, including bound terms/policy/index/underwriting provenance, advance draw, sim-day accrual and identical overlay/provenance after temporary workspace restart. |
| Seeded demo / integrated journeys | 1 / 4 passed, SIMULATED; `integrated:false`, `funds_executed:false`. |
| Decision-surface tests, Python 3.13.5 and 3.12.15 | 19 passed on each interpreter. |
| Release tests, Python 3.13.5 | 14 passed. |
| `python3 -m unittest discover -s tests -p test_coa_candidate.py -v` | 36 passed. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital` / `node --check capital/static/app.js` | Exit 0. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 41 artifacts, 9 stages. |
| `python3 scripts/decision_bindings.py --check` / decision ledger | Exit 0. |
| Finance / pack vector checks | Exit 0; 97,980 bytes / all 9 fixtures match, without regeneration. |
| Two builds and `cmp dist/capital-*.pyz dist2/capital-*.pyz` | Exit 0; byte-identical SHA256 recorded above. |
| Archive / preservation audit | Exact scope, all member hashes verified; protected files and `.aiops/` preserved. |

Final logs: `build/fix-round3-unit-final.log`,
`build/fix-round3-acceptance-final.log`, `build/fix-round3-decisions.log`,
`build/fix-round3-decisions-py312.log`, `build/fix-round3-release.log` and
`build/fix-round3-legacy.log`. `git diff --check` passes.

Result: **STATUS: READY**. No consequential product decision was required.
No commit, push or external post was made.


## Acceptance timeout follow-up — 2026-10-26

The supplied CI tail omitted the failing stage. Read-only retrieval of run
40244287984 and its acceptance evidence confirms unit discovery was killed by
the existing 300-second limit (exit 124), during the 200-sequence storage test.
All eight other stages passed, including 69 browser tests and 11 packaged
smoke checks. The run identifies PR head `d6f922b1b4b3a2173c48ef36ee8af14cd6ad8ee8`;
its acceptance evidence records GitHub's merge checkout
`789f31396de2b7ff0a93989d63a0e71d50f234af`. No assertion failure was reported in
the captured timeout tail. The available independent review has no findings.

Profiling repeated service creation and readiness requests identified
Markdown-fence regex scanning as avoidable work in the existing ledger parser.
The parser now searches for the unchanged opening-fence pattern, then uses
`str.find` for its first closing triple backtick. It retains non-overlapping
matches, the same JSON validator and error behavior. There is no new parser,
policy-value copy, parsed-policy cache or source fallback. Runtime inputs,
CI timeouts, test workload, financial terms and export construction are unchanged.

A local Python 3.12.15 diagnostic of 500 passes over the actual note corpus
measured 1.863–1.896 seconds with the previous regex and 0.896–0.921 seconds
with the changed parser (three samples each). This demonstrates the targeted
improvement, not a CI timing guarantee or a claim that parsing was the sole
cause of the historical timeout. Two regressions check corpus equivalence and
fence/JSON edge cases, including a malformed first block followed by a valid
block. All 44 targeted ledger, decision-surface and release tests passed.

The untouched starting tree passed 1,134 tests in 261.325 seconds on Python
3.13.5. Its browser command initially hit unrelated host services on ports
8765/8766. The unchanged suite then passed all 69 tests in an isolated loopback
namespace; those existing services were left untouched. Final acceptance uses
that same isolation and Python 3.12.15, retaining the 300-second unit timeout.

The changed tree produces byte-identical `dist/capital-0.2.0.pyz` and
`dist2/capital-0.2.0.pyz`, SHA256
`11a78ed934c9bbb6e6c59d6440cc5c135654cee7e2a6142cdb2fab78353bfca2`.
An independent archive audit verified 77 members, exactly 18 authorized
additional inputs, and all per-file manifest hashes. All 11 stdlib smoke checks
pass, including bundled provenance, note-derived accrual and temporary workspace
restart equality. Five vendor hashes, vendor manifest bytes and legacy export
bytes match the starting HEAD. Decision notes, goldens, existing vectors,
`.aiops/`, Protocol and Commerce references are untouched. Artifacts remain
SIMULATED/provisional, LOCAL_SIMULATION_ARTIFACT, unsigned and unpublished.
No commit, push, external post or consequential product decision was made.


Final acceptance passed with exit 0 and `ok:true` in
`build/bundled-fix-validation.json`. Unit discovery completed 1,136 tests in
249.142 seconds, below the unchanged 300-second cap. Chromium passed all 69
checks in 1.9 minutes. This is local working-tree evidence, not a new remote
exact-head CI result. Python was 3.12.15, Node 20.19.2 and Playwright 1.58.2;
CI's Node version is 24. No test configuration was changed.

| Verification | Result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3.12 scripts/acceptance.py --evidence build/bundled-fix-validation.json'` | All nine stages pass; exit 0; `ok:true`. |
| Full unit discovery, final Python 3.12.15 tree | 1,136 passed in 249.142s, including legacy golden and export byte guards. |
| Storage conformance / crash replay | 19 passed. |
| Vendored credit tests | 7 passed; also rerun with the requested standalone command. |
| Local upstream claim checks | 311 passed; no upstream adoption claimed. |
| `npm run test:browser`, through acceptance | 69 passed; unchanged configuration in isolated loopback namespace. |
| Packaged smoke | 11 passed; advance draw, sim-day accrual, restart overlay equality and policy provenance. |
| Seeded demo / integrated journeys | 1 / 4 passed; SIMULATED, integrated=false, funds_executed=false. |
| Targeted ledger / decision-surface / release suites | 44 passed, including two new parser regressions. |
| `python3 -m compileall -q capital` / `node --check capital/static/app.js` | Pass. |
| `python3 scripts/docs_surface.py --check` | Pass; 31 routes, 41 artifacts, 9 stages. |
| `python3 scripts/decision_bindings.py --check` | Pass. |
| Two builds / exact CI glob `cmp` / archive audit | Byte-identical; 77 members, 18 authorized additions; all hashes match. |
| Vendor / legacy / forbidden-path audit | Five pins, manifest and export unchanged; no policy, `.aiops/` or upstream reference edits. |
| `git diff --check` | Pass. |

Logs are retained locally as `build/bundled-fix-acceptance.log`,
`build/bundled-fix-targeted.log`, and `build/bundled-baseline-unit.log`.
Only the parser, its regressions and release/evidence notes changed.

STATUS: READY

## Conflict-fix round 2 — 2026-10-27

Resolved all three merge conflicts while retaining both parents' work:

- `docs/OPERATOR_HANDBOOK_KO.md`: preserves the artifact bundling and hostile-HTTP sections verbatim, each with its own closing section marker.
- `docs/VALIDATION.md`: preserves both appended validation histories verbatim and adds this round's evidence pointer.
- `tests/vectors/finance_vectors.json`: regenerated with `python3 scripts/finance_vectors.py --write` from the combined facade contract. Only the facade read-model group differs; all seven other groups and top-level metadata match both merge parents.

Main's hostile-HTTP generator, replay tests, 76 fixture files, docs registry and
acceptance script match `MERGE_HEAD` byte-for-byte. The reviewed bundling resource
loader, decision index, ledger parser, builder, packaged smoke and release tests
match `HEAD` byte-for-byte. The incoming acceptance timeout is retained as part
of main; this resolution changes no CI configuration, timeout, runtime code or
test. The five vendor references, their manifest, `capital/export.py` and
`tests/golden/demo.json` match both merge parents byte-for-byte. All five vendor
SHA256 locks match. No policy values were changed.

All measurements below are local working-tree evidence under Python 3.13.5 and
Node 20.19.2, not remote CI results. Chromium runs use the unchanged configuration
inside an isolated loopback network namespace. All journeys are SIMULATED and
provisional; no real funds, provider calls, signing, publication or deployment.

| Verification | Actual result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1,145 tests passed in 255.289 seconds, including legacy goldens, export byte guards, bundled-resource tests, hostile HTTP and fold-fuzz coverage. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; 7 passed. |
| `python3 -m compileall -q capital` | Exit 0. |
| `node --check capital/static/app.js` | Exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed in 1.9 minutes. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 117 artifacts, 9 stages. |
| `python3 scripts/decision_bindings.py --check`; `python3 scripts/decision_ledger.py` | Both exit 0. |
| `python3 scripts/finance_vectors.py --check` | Exit 0; 97,980 bytes match the combined contract. |
| `python3 scripts/http_hostile.py --check` | Exit 0; all 76 fixtures match. |
| `python3 scripts/fold_fuzz.py --check` | Exit 0; 16 seeds and 736 commands match, SIMULATED. |
| Two `scripts/build_release.py --out` builds and `cmp` | Exit 0; byte-identical artifacts in `build/bundled-round2/dist/` and `build/bundled-round2/dist2/`. |
| `python3 scripts/smoke_release.py build/bundled-round2/dist/capital-0.2.0.pyz` | Exit 0; all 11 checks pass, including bundled provenance, actual note-derived accrual, identical overlay state/provenance after temporary workspace restart, repayment and closure outside checkout. |
| Independent archive audit | Exact 77-member archive, including exactly 18 authorized additional inputs; all manifest file hashes and raw note bytes match. Unsigned/unpublished labels retained. |
| Preservation and merge hygiene | Five vendor pins, manifest, export and golden unchanged; both doc histories retained; no unmerged entries or conflict markers; whitespace checks pass against both parents. |

Merged build SHA256:
`51bc10dbf4d121e37ee7f67267617974cf0c1be3daf59d2256eb4f89c5367289`.
The artifact remains `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`.
Unit and browser logs are retained locally in `build/bundled-round2/unit.log`
and `build/bundled-round2/browser.log`; artifacts and logs are ignored.

The merge remains uncommitted for the supervisor. No abort, commit, push, rebase,
reset, external post, `.aiops/` edit or Protocol/Commerce modification was made.
No consequential product decision was needed.

STATUS: READY


## Conflict-fix round 3 — 2026-10-28

Resolved the supervisor-started merge of incoming main
`e445f38282e14bc271c94b48d3f4dcfbe195cba0` into feature parent
`00e0cc45529790d98037e538b47b53b5f0a0d291`. Both the bundled policy runtime
and main's permission catalog, facts cursor export, tests and documentation survive.
No combination-specific runtime, test, CI or policy change was required.

Files resolved (13):

- `docs/INTEGRATION.md`: retains the permissions route and state terms provenance.
- `docs/OPERATOR_HANDBOOK_KO.md`: retains both the artifact bundling and facts export sections verbatim; the merged authorization table includes main's routes.
- `docs/VALIDATION.md`: retains both parent histories verbatim and in order.
- `tests/vectors/finance_vectors.json`: regenerated from the combined contract. Relative to HEAD, only `facade_read_model` and main's recorded `closeout_digest` group change; relative to incoming main, only `facade_read_model` changes. All other groups and top-level metadata are preserved.
- `tests/vectors/pack/clean.json`, `content-digest.json`, `section-auth_matrix.json`, `section-decisions.json`, `section-export_manifest.json`, `section-reconciliation.json`, `section-workspace_audit.json`, `truncated.json`, `volatile.json`: regenerated with the unchanged generator. The clean pack combines main's authorization matrix and this node's decision provenance; all other sections match both parents. Intentional corruption variants retain their generator-defined mutations.

The reviewed resource loader, decision index, terms/policy loaders, builder,
packaged smoke and release tests remain byte-identical to HEAD. Main's facts
implementation, authorization implementation, verifier, associated generators,
docs registry, facts tests and closeout fixture remain byte-identical to incoming
main. The five vendor SHA256 locks, manifest, legacy `capital/export.py` and
`tests/golden/demo.json` match both parents. `.aiops/` and CI are unchanged.

All results are local working-tree evidence under Python 3.13.5 and Node 20.19.2.
Rehearsals are SIMULATED/provisional and loopback-only. No real funds, provider
calls, credentials, signing, publication, deployment or upstream adoption.

| Verification | Actual result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1,165 passed in 268.000 s, including bundled-resource behavior, explicit overrides, missing/malformed note handling, legacy golden/export byte guards and incoming facts/catalog coverage. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed in 2.0 min using the installed headless shell and unchanged configuration. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 34 routes, 250 artifacts, nine stages. |
| `scripts/{auth_matrix,decision_bindings,finance_vectors,pack_vectors,closeout_digest,facts_vectors,http_hostile,fold_fuzz}.py --check`; `python3 scripts/decision_ledger.py` | All exit 0; finance 99,070 bytes, nine pack files, 133 facts files, 76 hostile requests, 16 fuzz seeds / 736 commands match. |
| Two `scripts/build_release.py --out` builds plus `cmp` | Exit 0; byte-identical artifacts in `build/bundled-round3/dist/` and `dist2/`. |
| `python3 scripts/smoke_release.py build/bundled-round3/dist/capital-0.2.0.pyz` | Exit 0; all 11 checks pass, including actual note-derived accrual and identical overlay state/provenance after temporary workspace restart outside checkout. |
| Independent archive audit | Exactly 78 members, including exactly 18 authorized additional inputs. All manifest hashes and bundled raw input bytes match; unsigned/unpublished labels retained. |
| Preservation and merge hygiene | Vendor/export/golden bytes preserved; no conflict markers or unmerged entries. Whitespace check against incoming main passes; against HEAD it passes excluding main's unchanged intentional whitespace-corruption fixture. |

Merged artifact SHA256:
`e743c548468cb436aba8bb0c177d243e2766c6f404a6f69dd9da1232b5738100`.
It remains `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`.
Logs and artifacts are retained locally in ignored `build/bundled-round3/`
(`unit.log`, `browser.log`, `checks.log`, `smoke.log`, `decision-ledger.log`).

All resolutions are staged. The merge remains uncommitted for the supervisor.
No abort, commit, push, rebase, reset, external post, `.aiops/` edit or
Protocol/Commerce modification was made. No consequential product decision was needed.

STATUS: READY


## Supervisor conflict-fix round 1 — incoming main 97fb680 (2026-10-29)

Resolved the supervisor-started merge of incoming main
`97fb68039d0108a7413770ff1534c612788ac07f` into feature parent
`436eb4c5ac3d974ef53cceb8c99d49b5a7b57ecb`. The bundled policy runtime and
main's contract invariant claims, compatibility preflight, risk what-if,
case dossiers and extended simulation journeys all survive. No additional
runtime implementation, test assertion, CI or policy change was required.

Files resolved (13):

- `README.md`: retains main's contract-invariant documentation and the current bundled decision-index behavior.
- `docs/OPERATOR_HANDBOOK_KO.md`: retains the complete artifact-docs-bundling, advance-case-dossier and contract-invariants-claims sections. Main's authorization additions also survive.
- `docs/VALIDATION.md`: retains both parent histories verbatim and in order.
- `tests/vectors/finance_vectors.json`: regenerated with the unchanged generator; only `facade_read_model` differs from either parent. All other groups and top-level metadata are preserved.
- `tests/vectors/pack/clean.json`
- `tests/vectors/pack/content-digest.json`
- `tests/vectors/pack/section-auth_matrix.json`
- `tests/vectors/pack/section-decisions.json`
- `tests/vectors/pack/section-export_manifest.json`
- `tests/vectors/pack/section-reconciliation.json`
- `tests/vectors/pack/section-workspace_audit.json`
- `tests/vectors/pack/truncated.json`
- `tests/vectors/pack/volatile.json`

The nine pack fixtures were regenerated with the unchanged generator. Relative
to the feature parent, only the clean pack's auth_matrix section changes;
relative to incoming main, only its decisions section changes. The intentional
tamper variants retain their generator-defined mutations.

Combination fix: regenerated all six `tests/vectors/dossiers/sim-*.json`
fixtures. Their only semantic additions are the underwriting `notes_source`
and `note_sha256` fields; each enclosing `dossier_digest` changes accordingly.
The initial dossier check detected this drift; the regenerated fixtures pass.
Risk scenario vectors remain byte-identical to incoming main.

Removed incoming main's obsolete root `DECISION_REQUIRED.md`: it requested
integration with moved main, which this supervisor-authorized merge completes.
The existing guarded baseline test now passes without edits to the guard.
No consequential product decision remains for this node.

The reviewed builder, resources, decision index, terms/policy loaders,
packaged smoke and release tests match the feature parent byte-for-byte.
Main's new runtime modules, their tests, fixture generators and docs registry
match incoming main byte-for-byte. The five vendor reference files and
manifest, legacy `capital/export.py` and `tests/golden/demo.json` match both
parents. All five vendor SHA256 locks match. `.aiops/`, CI and upstream
Protocol/Commerce references were not edited.

All measurements below are local working-tree evidence under Python 3.13.5
and Node 20.19.2. Journeys are SIMULATED/provisional, with loopback-only
servers and temporary workspaces. No real money, provider calls, credentials,
signing, publication, deployment or upstream adoption is claimed.

| Verification | Actual result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1,259 tests passed in 277.775 s, including legacy goldens/export guards, main's added features and bundled missing/malformed/override regressions. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven tests passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 76 Chromium tests passed in 1.8 min with the unchanged configuration in an isolated loopback network namespace. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 36 routes, 273 artifacts, nine stages. |
| `scripts/{auth_matrix,decision_bindings,finance_vectors,pack_vectors,closeout_digest,facts_vectors,http_hostile,fold_fuzz,dossier_vectors,risk_scenario_vectors,compat_preflight,contract_invariants_check}.py --check`; `python3 scripts/decision_ledger.py` | All final checks exit 0. Finance: 101,048 bytes; pack: nine files; dossiers: six files; facts: 133 files; hostile HTTP: 76 files; fuzz: 16 seeds / 736 commands. Invariant claims: 6/6, twelve seed digests match, loopback executed. Optional Protocol citation verification is explicitly SKIPPED without a supplied checkout; this is not an upstream citation pass. |
| Two `scripts/build_release.py --out` builds plus `cmp` | Exit 0; byte-identical artifacts in `build/bundled-merge-20261029/dist/` and `dist2/`. |
| `python3 scripts/smoke_release.py build/bundled-merge-20261029/dist/capital-0.2.0.pyz` | Exit 0; all eleven checks pass, including actual note-derived accrual and identical overlay state/provenance after temporary workspace restart outside checkout. |
| Independent archive audit | Exactly 82 members, including exactly 18 authorized additional inputs; all manifest hashes and raw input bytes match. Unsigned/unpublished labels preserved. |
| Preservation and merge hygiene | Both features preserved; vendor/export/golden bytes unchanged; no conflict markers or unmerged entries; whitespace checks against both parents pass. |

Merged artifact SHA256:
`e5c6b8e1c6dfd1c02310078b0732f5a84f4b87ab3514be604119ddef98f807e5`.
The artifact remains `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`.
Logs and artifacts are local ignored files under `build/bundled-merge-20261029/`
(`unit.log`, `browser.log`, `checks.log`, `final-static.log`, `smoke.log`,
`archive-audit.log`, `preservation.log`).

All resolutions and combination fixes are staged. The merge remains
uncommitted for the supervisor. No merge abort, commit, push, rebase, reset
or external post was performed.

STATUS: READY
