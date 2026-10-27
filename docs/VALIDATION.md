# Validation scope

## Provider observation adapter

`tests/test_observation_port.py` exposes `run_observation_vectors(factory)` for a
fresh no-argument `ObservationPort` factory. The 27-case synthetic corpus pins
scoped item identity, separate delivery metadata, normalized-fact dedup, original
content retention after conflicts and original replays, explicit binding conflicts,
UNMATCHED retention, capture/cancellation coexistence, reverse delivery order,
null/supplied offsets, and every normalized content field. Complete output SHA256
expectations supplement explicit identity, evidence, status and diagnostic-index
assertions. The corpus itself is byte-pinned; the checker has no regeneration path.
Negative controls cover malformed/missing/drifted corpus files, a drifting factory,
invalid inputs and synthetic alias collisions. Every output and diagnostic is
SIMULATED with applied=false/funds_executed=false and no applied effects.

A populated disposable service with a nonempty overlay journal is snapshotted after
every fold (canonical state, state_digest, journal, receipts/count, overlay and its
overlay_state_digest). No recording path, provider call or HTTP surface was added.
CAP-14/CAP-16 remain NOT_BOUND. Fixture replay does not authenticate evidence or
establish production identity, kernel quarantine, or SEMANTIC_CONFORMANCE.

Plan deviations: the draft is pinned to the existing upstream-binding decision's
`e2a029d8ac3af7575888dac22fc4bf173ebec232` citation, separately from the FSM-only
`7481b0e` pin. Read-only `git show` verified document SHA256
`e640151bbdff15b67584337e6cdb6e95b2cc9c060f48dcc9de45df84f8de5345`.
The corpus uses base facts and explicit patches with complete output digests instead
of repeated full output JSON. Item `binding_status` preserves UNMATCHED even when
its diagnostic `status` becomes CONFLICT. The supervisor-authorized append-only
structural check replaces only the ports.py whole-file byte guard; every original
AST node, Protocol signature/body and import remains intact. Negative controls
reject edits/removal/reordering of original definitions or unrelated added classes.
All other current-main byte guards remain unchanged.

### Builder verification (2026-10-23)

The resumed worktree started at `4cf1de3` with interrupted implementation edits.
Initial observation (6 tests), seam (6 tests), vector and documentation checks passed.
The initial COA run (36 tests) failed solely because the worktree lagged five merges
behind locally available `origin/main`: the preexisting overlay guard compared old
source to main's repayment implementation. Tracked edits were backed up under
`/tmp/provider-observation-resume-vk6mkzqe`; `git merge --ff-only origin/main` advanced
to `8c5ad10` without creating a commit. `git apply --3way` reapplied the work, with
one conflict in the guard list resolved to preserve current main's guards and the
authorized ObservationPort exception. `git restore --staged .` left all changes
unstaged. COA re-run: 36 passed. No upstream repository was modified.

### Merge conflict verification, round 1 (2026-10-23)

Combined `c0f85f3` with main `68c8896` in `tests/test_coa_candidate.py`.
Main's historical COA guard and live byte guards remain, with the reviewed
append-only ObservationPort structural check for `capital/ports.py`. The merged
closeout binding note is byte-guarded against main's reviewed version. Both the
observation corpus and main's closeout/finance artifacts and documentation survive.
All results below use local SIMULATED fixtures; CAP-14/CAP-16 remain NOT_BOUND.

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | 956 passed, including observation isolation and drift controls |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed |
| `python3 -m compileall -q capital` | Exit 0 |
| `node --check capital/static/app.js` | Exit 0 |
| `python3 scripts/docs_surface.py --check` | 30 routes, 40 artifacts, 9 stages; zero findings |
| `python3 scripts/observation_vectors.py --check` | PASS; applied=false; funds_executed=false |
| `python3 scripts/closeout_digest.py --check` | 4401 bytes match, embedded in finance vectors |
| `python3 scripts/finance_vectors.py --check` | 97125 bytes match |
| `npm run test:browser -- --config /tmp/provider-observation-browser-2ch96cd0/playwright.config.cjs` | 69 Chromium tests passed |
| Vendor SHA256 and merge-parent byte comparison | All five pinned reference files and manifest unchanged |

The first default browser invocation could not start because existing listeners
occupied ports 8765/8766. Dependencies were installed from the local npm cache with
`npm ci --offline --no-audit --no-fund`. A temporary configuration moved only the
four suite servers/base URLs to loopback ports 18865–18868; all tests and the tracked
Playwright configuration stayed unchanged. No commit or push was performed.

## DEV_ONLY keyset coverage

`tests/test_dev_keyset.py` covers secure creation/restart, strict schema and encoding,
0600/no-follow/nonregular rejection, two-key rotation, retirement, identity-bound MACs,
V2/V3, CLI refusal, and response/log non-disclosure. The deterministic manifest corpus
adds two clean keyset manifests, unknown-kid and retired-key cases with independently
written expected reasons. Fixture keysets are synthetic DEV_ONLY, never external keys.
Stage7 remains NOT_BOUND.

Actual local node verification (2026-10-20; SIMULATED fixtures only):

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_dev_keyset.py' -v` | 7 passed (initial run before HTTP coverage: 6 passed) |
| `python3 -m unittest discover -s tests -p 'test_manifest_vectors.py' -v` | 11 passed, including rerun after module relocation |
| `python3 -m unittest discover -s tests -p 'test_coa_candidate.py' -v` | 35 passed |
| `python3 -m unittest discover -s tests -v` | Final 711 passed; first run had 2 failures (export byte guard, missing fixture registry); second had 1 error (upstream-only absent goldens); both corrected and rerun |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed |
| `python3 scripts/manifest_vectors.py --check` | Initial expected failure: six new files missing; final 19 files match |
| `python3 scripts/manifest_vectors.py --write` | 19 files written; no stale files removed; legacy bytes unchanged |
| `python3 scripts/seed_demo.py` | SIMULATED golden digests matched |
| `python3 scripts/docs_surface.py --check` | 29 routes, 26 artifacts, 9 stages; zero findings |
| `python3 -m compileall -q capital` | Exit 0 |
| `node --check capital/static/app.js` | Exit 0 |
| `npm ci` | Installed locked dependencies; audit reported zero vulnerabilities |
| `npm run test:browser` | 62 Chromium tests passed |
| `python3 scripts/acceptance.py` | All 9 stages passed; local build/acceptance-evidence.json reports ok=true |
| `python3 scripts/build_release.py --out dist` | Built capital-0.1.0.pyz |
| `python3 scripts/build_release.py --out dist2` | Same package SHA256 as dist build |
| `cmp dist/capital-*.pyz dist2/capital-*.pyz` | Exit 0, byte-identical |
| `python3 scripts/smoke_release.py dist/capital-*.pyz` | 8 checks passed |
| `git diff --check` | Exit 0 |
| `git diff --exit-code -- capital/vendor .aiops capital/export.py tests/golden` | Exit 0; locked/reference and legacy files untouched |

Plan deviations: signer/loader/factory live in `capital/keyset.py` to preserve the existing
export byte guard, with strict JSON parsing shared in `capital/strict_json.py`. Added docs
surface registry entries. Corrected the existing COA baseline test to ignore only goldens
added exclusively on main after the merge point and absent from HEAD; deletion of any
branch-owned golden still fails. No golden or vendor content was regenerated to hide drift.

Initial Capital base: `e9bea122102b87a1f11ac673d50e01c31cba6922` (README only; no pre-existing test or workflow gates).
Protocol reference: `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`.

Existing coverage was inspected first: Protocol `test_mock_credit.py` covers face arithmetic, snapshots, product/real-funds refusal, reservation release; retained byte-for-byte and rerun. Existing `test_credit_fsm.py` documents lifecycle, terminal, shared face, settlement and replay behavior. Capital does not claim those historic runs as its own evidence.

New coverage addresses the absent application layer: `tests/test_capital.py` tests full facade lifecycle, immutable views, duplicate/conflicting first receipts, two-thread shared face contention, lost-response lookup, absent outcome UNKNOWN, old session, strict input, malformed/duplicate JSON, Unicode regression, host/Origin/CSRF, capacity, exact vendor hashes and replay. `tests/browser/journey.spec.cjs` tests actual UI normal/negative journeys, response loss before/after apply, reload fencing, GET-only recovery, keyboard order, mobile overflow and desktop/mobile screenshots.

Commands and initial actual results: Python facade/API 19 passed; pinned MockCredit 7 passed; JS syntax passed. Initial Chromium browser suite: 6 passed; desktop/mobile screenshots inspected. Exact-head CI is reported in PR evidence after their actual runs. A sandbox initially blocked loopback bind; the same test suite passed when local bind permission was available. This is not a product test failure masked by a skip.

No production DB/Supabase/Docker is needed or accessed. No external provider call, money movement, personal financial data, token issuance or deployment. No durability, cross-host fencing, bank exactly-once, credit validity, legal compliance, authenticated export, large-scale throughput or full blueprint completion is inferred. Required independent architecture/financial decisions and human product acceptance remain pending.

## Independent-review repair

A non-author reviewer inspected implementation `6c7a064cb378f9bebea8e5cc7da5c2d1c467f8cc` and ran 19 facade/API plus 7 pinned regressions. The reviewer reproduced a P1: a delayed receipt lookup in one tab could erase a later UNKNOWN request from another tab. The repair takes the same Web Lock for command, recovery and old-session acknowledgment and compares instance + operation identity before deleting pending state. Browser regression delays the first recovery, blocks the second tab, then verifies the next UNKNOWN remains shared by both tabs. Accepted receipt validation now requires the actual F04 result/case and reconcile match, rather than only a successful envelope. Four additional browser tests cover malformed accepted response, two-tab recovery, old-process acknowledgment and unavailable storage. Local Chromium suite: **11 passed**. Deeply nested JSON now produces INVALID_JSON rather than disconnecting.

Final independent exact-HEAD review and CI are recorded in the PR after the repair commit. The earlier green CI/review does not apply to the repaired commit automatically. The reviewer is a separate Codex agent with source context, not a clean-room implementation or external Fable/A3 provider. No new external audit provider received private source.

## CI timing regression

On `0add7e1`, PR CI succeeded but push run `37581556883` failed in the repayment browser test. Its trace shows 40000 was already present as **unreserved face**, so a broad text wait passed before the first repayment refresh. The test then edited an input still being refreshed; the next request was rejected as exceeding outstanding exposure. The domain safely retained 40000 exposure and 20000 repaid. The correction waits on the specific **outstanding exposure** field, and the UI disables amount/scenario inputs as well as buttons while a request is in progress or UNKNOWN. No retry/skip/timeout increase was used to hide the failure.

## Read-only product extension

Added nine disposable F01–F03 scenarios (35 steps), behavior-level readiness for all 20 requirements, and a current-case draw preview on a restored scratch machine. New tests check fixed-order differences, partial versus full refund semantics, late cash, duplicate/conflicting observations, refund acceptance without bank closure, active journal/receipt preservation, shared-face preview contention, old sessions, readiness coverage, and modified source-byte detection. Browser coverage exercises timeline comparison, prerequisite filtering, zero-POST diagnostics and stale scenario callbacks.

The first extension run passed 31 Python tests and 14/15 browser tests. The preview test caught a setup wait matching `BOUND` inside `UNBOUND`; the test took its “before” snapshot while the preceding bind command was still running. The helper now waits for the exact settlement-gate value and enabled next action. The API scratch-preview preservation tests had already passed. This correction preserves the assertion that preview sends zero POSTs and leaves operation count/state digest unchanged; no skip or retry is added.

After the precise setup wait: local Chromium **15 passed**; Python facade/API/read-only **31 passed**; unchanged pinned MockCredit **7 passed**. Exact-HEAD independent review and CI follow the extension commit.

## Command admission and refresh fence regression

The independent run at `097c228` passed 11/12 selected browser tests but timed out in `ready()` waiting for APPROVED. Its trace contains one offer POST and no approve POST. The test accepted an existing case's OFFERED label before the new offer request had even started; the approve click overlapped that offer's transition. This is retained as a failed run, despite both CI runs passing.

Two deterministic browser regressions failed against the old implementation: existing actions were still enabled synchronously after offer submission (before the asynchronous Web Lock callback), and a storage event unlocked inputs during a delayed post-receipt evidence refresh. The UI now claims its local busy fence before requesting the Web Lock and releases it only after the lock callback, including refresh, completes. Recovery uses the same lifetime. No command is queued or retried; pending UNKNOWN and cross-tab exclusion remain in force. The journey helper additionally verifies the exact advance ID from the accepted offer receipt before checking OFFERED, so an older case cannot satisfy setup.

After repair, all 17 Chromium tests passed, including the two regressions and all existing read-only scenario, preview, recovery and layout tests. The regressions preserve their failing-before traces outside the repo at `/tmp/capital-fence-before`; exact committed HEAD API, CI and independent review evidence is reported separately. No retry, skip or timeout increase was introduced.

## Independent manual-refresh findings

The separate Astra review of `dbc2eea` independently passed API 31, pinned 7 and browser 17, then reproduced two additional P2 defects: a delayed manual state response overwrote a completed APPROVED display with OFFERED; and a delayed manual evidence response replaced an entered 20000 repayment draft with 60000, which the synthetic server accepted. These failures are preserved in `/tmp/capital-review-dbc2eea/refresh-experiments.log` and its traces.

Initial load and manual refresh now use the local busy fence, including refresh and case-selection controls. A refreshed state is published only after its matching evidence is validated. Repayment drafts survive unchanged case/phase/sequence/exposure renders, and reset when that identity changes. New regressions exercise delayed state/evidence, exact submitted repayment amount, and initial-load controls. The first 20-test run passed 19 but caught test fixture leakage: the new partial-repayment regression left a reservation, so the following lifecycle correctly rejected a 60000 draw with ADVANCE_EXCEEDS_OPEN_FACE. The regression now completes repayment and close through the UI, releasing its reservation without weakening the shared-face rule.

## Refund fixture provenance repair

An audit found that `FixtureViews` built `sim-refund` from the committed view and then hand-set `refund_face`, `refund_outstanding` and `refund_bearer_policy`. That left `distribution_blocked` false, `refund_beneficiary` null and no accepted refund command, so the view was not one the pinned F01–F03 machine can produce. The repair applies one synthetic partial refund (10000, beneficiary `fixture-buyer`, reason `SYNTHETIC_FIXTURE`) through the unchanged pinned `SettlementMachine.bind_refund` and stores the resulting view. Bearer `UNDEFINED`, the distribution block and every other derived field come from upstream calculation; no field is adjusted by hand. The production repair is confined to `capital/service.py`; the new regression is in `tests/test_readonly_tools.py`, and this section is the only change to `docs/VALIDATION.md`. Exactly these three files differ from baseline. Vendor files, manifest hashes and Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` are unchanged. No refund bearer policy is adopted, and nothing has a real-world or external effect.

Failing-before evidence (actual supervisor run, before the fix): `python3 -m unittest discover -s tests -p test_readonly_tools.py -v` ran 12 tests: 11 passed and exactly one failed, `test_refund_fixture_is_pinned_partial_bind_refund_and_offer_refused`, at line 87 `self.assertIs(claim['distribution_blocked'],True)` with `False is not True`. The supervisor keeps the full log outside the repository. Because the test stopped at line 87, its later assertions (beneficiary, replay equality, offer refusal) had not run before the fix.

After-fix results (actual supervisor run; the author did not run any tests or commands for this repair):

- `python3 -m unittest discover -s tests -v`: all **32 passed** in 0.644s. The new regression passed every later assertion, including full claim equality with an independent pinned replay and refusal of the original offer with `REFUND_OBLIGATION_OPEN`.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` (pinned): all **7 passed**.
- `node --check capital/static/app.js`: exit 0.
- All five vendor SHA256 hashes and Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` verified unchanged. Exactly three files differ from baseline: `capital/service.py`, `tests/test_readonly_tools.py`, `docs/VALIDATION.md`.

The Chromium browser suite has **not run** for this patch because dependency setup was denied. The earlier 20-test browser and CI results do not apply to the changed tree. This section claims no independent review or external certification. It also claims no new commit, CI run, push, merge or deploy.

## Local authorization boundary

Author-local verification of the synthetic role seam on the auth-boundary tree, before it was combined with the projection and file-workspace work already on main. These runs are not CI, not an independent review, and not a product acceptance. No IdP, KYC, credential, bank, or vendor change was made. `git diff --stat -- capital/vendor .aiops .github` printed no files.

Commands actually run, in order:

- `python3 -m unittest discover -s tests -v`: **46 passed** in 1.752s. This was before an `app.js` brace typo was fixed; Python sources did not change after it.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: **failed**, `SyntaxError: Unexpected token '}'` at `capital/static/app.js:32`. The extra brace was removed. A later check exited 0.
- `npm ci`: added 3 packages (`@playwright/test` was not installed). Chromium builds were already present in the Playwright cache (`chromium-1208`, `chromium-1243`) and `/usr/bin/google-chrome` exists. No browser download was required for the runs below.
- `npm run test:browser`: **26 passed, 1 failed**. `auditor-role.spec.cjs` died in `page.evaluate` with `ReferenceError: state is not defined`, because `app.js` is a module and `state` is not a window global. The spec was changed to pass `local_token` and `instance_id` from the auditor `GET /api/state` into the page. No assertion, timeout, or existing test was weakened.
- `npx playwright test tests/browser/auditor-role.spec.cjs`: **1 passed** (3.0s).
- `npm run test:browser`: **27 passed** (20.2s), including the auditor session, the existing fence, journey, and portfolio specs.
- Final repeat on the same tree: `python3 -m unittest discover -s tests -v` **46 passed** in 1.736s; pinned mock credit **7 passed** in 0.002s; `python3 -m compileall -q capital` exit 0; `node --check capital/static/app.js` exit 0; vendor/`.aiops`/`.github` diff still empty.

The passing export click received a download whose JSON had `replay_matched: true`. The CSP header was not changed. No server was left listening. No commit, push, pull request, or issue was created from this run.

## Local candidate projection

CAP-13/14 local candidate only. `GET /api/projection` folds the accepted F04 journal and the three immutable settlement views into `SIMULATION_FIXED_V1`. Labels stay `SYNTHETIC_UNADOPTED` / `NOT_BOUND`. `fin-ledger-contract` is not adopted. No revenue, tax, fee, or account policy was chosen. Vendor bytes were not edited.

Commands actually run on the projection tree, before it was combined with the file-workspace work already on main:

- `python3 -m unittest discover -s tests -v`: **41 passed** in 1.271s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- Vendor SHA256 check against `capital/vendor/manifest.json`: all **5 files OK**. Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` unchanged.
- `npm ci` (no `node_modules` yet): added 3 packages. `npx playwright install chromium` then `npm run test:browser`: **28 passed** (27.7s), including the projection panel after draw and repay on an isolated loopback port and the existing 375px layout test. Playwright stopped both loopback servers when the run finished.

No skip was added. This section claims no independent review, CI run, commit, push, or deploy.

## Opt-in local file workspace

`StoragePort` keeps the default process in memory. `python3 -m capital.server --workspace DIR` adds one stdlib JSON file with a payload checksum, temp-file rename, and an exclusive `fcntl` lock. Restart replays the pinned journal, checks `state_digest`, and serves the original receipts under a new `instance_id`. `durable=LOCAL_FILE_WORKSPACE` on state and export is a development-file label. It is not `k-stage5-durable-tx`. CAP-11 stays NOT_BOUND. Vendor bytes and the Protocol pin were not edited. Existing test modules were not edited or weakened.

The first persistence run failed in `test_round_trip_restores_canonical_state_and_original_receipts`: repeating the stored draw on the new instance raised `IDEMPOTENCY_CONFLICT` because the fingerprint included `instance_id`. The fingerprint is now the command fields only. Session checks still require the current `instance_id`, and the stored receipt keeps the writer instance. The assertion was not removed.

Final local commands on the persistence tree, before it was combined with the projection candidate:

- `python3 -m unittest discover -s tests -v`: **42 passed** in 4.702s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `npm ci`: added 3 packages.
- `npm run test:browser`: **27 passed** in 19.3s, including the kill-and-restart stale-tab acknowledgment. Chromium was available. The spawned workspace server was stopped in the test `finally`.
- `git diff --name-only -- capital/vendor .aiops`: no output. `test_vendor_pin_byte_integrity` passed.

No database, provider, credential, money movement, or deployment was used. This section does not claim a GitHub CI run, an independent review, or stage5 recovery. A later process does not see a command whose file replace failed; that receipt stays queryable only in the process that applied it, and further writes return 503.

## Projection and file workspace combined

Conflict resolution kept both the local projection candidate and the opt-in file workspace. `GET /api/projection` still folds the accepted journal into `SIMULATION_FIXED_V1` with `SYNTHETIC_UNADOPTED` / `NOT_BOUND`. `make_server` still opens `FileWorkspace` when `--workspace` is set and closes it on shutdown. The UI refresh validates workspace kind and status, then loads the projection panel. The two sections above record the separate pre-merge trees. Counts below are the combined tree.

Commands actually run after the conflict resolution:

- `python3 -m unittest discover -s tests -v`: **51 passed** in 5.230s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- Vendor SHA256 check against `capital/vendor/manifest.json`: all **5 files OK**. Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` unchanged. `git diff --name-only -- capital/vendor .aiops` produced no output.
- `npm run test:browser`: **29 passed** in 27.9s. That includes the projection panel after draw and repay, the projection read-failure fence, and the restarted file-workspace stale-tab acknowledgment. Chromium was already available. Playwright stopped its loopback servers when the run finished.

A separate in-process check projected an offered case on a file workspace, confirmed debits equaled credits and the journal digest was unchanged, restored that file into a new service, projected again, and received `NOT_BOUND` for `operating-ledger`. No skip was added. This section claims no independent review, CI run, commit, push, or deploy.

## Authorization boundary with projection and file workspace

Conflict resolution kept the synthetic role seam together with the local projection candidate and the opt-in file workspace. `GET /api/projection` is registered as `projection:read` and stays default-deny for any unmapped path. Export `durable` follows memory / `LOCAL_FILE_WORKSPACE`. Receipt `role` is outside the idempotency fingerprint, survives workspace restore, and a pre-label file loads as `UNLABELED` without being rewritten until a later command. Identity, IdP, KYC, and AgentGrant/ActionPermit stay NOT_BOUND. Vendor bytes were not edited. No assertion, timeout, or existing test was weakened. The fingerprint assertion now checks the command identity without `instance_id` or `role`, which is the persistence contract plus the role label.

Commands actually run on this combined tree:

- `python3 -m unittest discover -s tests -v`: **66 passed** in 5.996s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- Vendor SHA256 check against `capital/vendor/manifest.json`: all **5 files OK**. Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` unchanged. `git diff --name-only -- capital/vendor .aiops .github` produced no output.
- `npm run test:browser`: **30 passed** in 31.2s. That includes the auditor session, the projection panel, the restarted file-workspace acknowledgment, and the keyboard / 375px layout test. Chromium was already available. Playwright stopped its loopback servers when the run finished.

No skip was added. This section claims no independent review, CI run, commit, push, or deploy. The merge itself is left uncommitted for the supervisor.

## Local facade contract and port seams

`capital/ports.py` holds the five `typing.Protocol` seams. `PinnedFsmProducer` is the default `ProducerPort` and is what `CapitalService` calls for commands, preview, and journal restore. Default callers still see the same `machine` and `fixtures` objects. `docs/SEAMS.md` is the registry; no row is `ADOPTED`. `capital/contract/facade-v1.json` is namespace `capital-local-facade/1`. The schema checker walks a real loopback journey and rejects an unknown field. Producer vectors are not SEMANTIC_CONFORMANCE. CAP-16 exact tuple stays NOT_BOUND. The readiness row quotes `capital-local-facade/1` and `capital/contract/facade-v1.json`.

Commands actually run on this tree, after the schema and tests were in place:

- `python3 -m unittest discover -s tests -v`: **112 passed** in 10.158s (exit 0). An earlier run on the same product code, before a test-helper rename, was **112 passed** in 10.129s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.003s (exit 0).
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- Vendor SHA256 against `capital/vendor/manifest.json`: all **5 files OK**. Protocol pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` unchanged.
- `npm ci`: added 3 packages, 0 vulnerabilities.
- `npm run test:browser`: **32 passed** in 41.5s. Playwright started and stopped the loopback servers. A later port check showed no listener on 8765–8767.

No existing test was weakened or skipped. This section claims no independent review, CI run, commit, push, or deploy.

## Acceptance ladder

`scripts/acceptance.py` runs six stages on one command: unit, pinned vendor, `node --check`, browser, packaged-artifact smoke, and the seeded demo. It writes untracked `build/acceptance-evidence.json` and exits non-zero when a stage fails or is missing. Human product acceptance is not part of this ladder. `scripts/seed_demo.py` builds a SIMULATED book with fixed operation ids: closed, defaulted, rejected, cancelled, UNBOUND draw, and a pending-settlement case whose draw stays `SETTLEMENT_NOT_COMMITTED`. Amounts are fixture units on the pinned open face, not a product limit. `tests/golden/demo.json` pins `state_digest`, projection totals, and manifest `content_digest`. It has no instance id and no clock field. Drift fails unless `--update-golden` is passed.

`content_digest` follows the rule in `docs/INTEGRATION.md` and `content_material()`: (a) remove `content_digest` and `signature`, (b) strip `instance_id`, `created_at`, `saved_at`, `timestamp`, and `timestamps` at every depth, then (c) recompute each section's `sha256` over the stripped body. Stored section hashes still cover the saved body, so they move with instance id and still match `sha256` of that body. Two fresh processes, and a file-workspace restore, share one content digest. The verifier still checks the stored section hash before the digest.

Browser coverage saves desktop and 375px PNGs of the portfolio, case, projection, statement, reconciliation, readiness, and organizer, auditor, and observer views under `test-results/acceptance/`. Blank captures and console errors fail the test. Those files are not committed. `python3 -m compileall -q capital` is a local check beside the ladder. It is not one of the six stages.

An earlier ladder invocation on this tree exited 0 but reported unit `passed=1` because seed-demo log lines inside unittest overwrote the `Ran N tests` summary. That count was wrong and is not the record below. The parser now treats the unittest summary as authoritative. No stage in the recorded run was skipped or left unrun. `node --check` has no test count because it is a syntax check.

Recorded run, after that parser fix, at HEAD `6e161eb6b4e0def7eb996b634121210de80f2b6a` (dirty worktree; the evidence file stores that SHA). Tools: Python 3.13.5, Node v20.19.2, npm 9.2.0, Playwright 1.58.2. Vendor commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, all 5 file hashes matched. Golden `state_digest` `a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45`, `content_digest` `c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`, projection debit and credit both 385000. `git diff --name-only -- capital/vendor .aiops` produced no output.

```text
[acceptance] unit exit=0 status=passed passed=123 failed=0
[acceptance] pinned-vendor exit=0 status=passed passed=7 failed=0
[acceptance] node-check exit=0 status=passed passed=None failed=None
[acceptance] browser exit=0 status=passed passed=33 failed=0
[acceptance] packaged-smoke exit=0 status=passed passed=8 failed=0
[acceptance] seeded-demo exit=0 status=passed passed=1 failed=0
[acceptance] evidence build/acceptance-evidence.json ok=true
```

Exit code 0. Evidence `ok` is true. The same tree, before this ladder, also ran `python3 -m compileall -q capital` (exit 0), `node --check capital/static/app.js` (exit 0), pinned MockCredit **7 passed** in 0.002s, and `npm run test:browser` **33 passed** in 54.1s. `npm ci` had added 3 packages. A port check after the ladder showed no listener on 8765–8768. Playwright stopped its loopback servers. No skip was added. This section claims no independent review, GitHub CI run, commit, push, or deploy.

## Operator handbook

Documentation and checks only. No file under `capital/`, `capital/vendor/`, `.aiops/`, or `.github/` was edited. No test was weakened or skipped. `python3 scripts/not_bound_checklist.py --write` was run once to fill the generated region in `docs/ACCEPTANCE_KO.md`. The commands below are the verification of that tree. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

- `python3 -m unittest tests.test_coverage tests.test_decisions tests.test_handbook -v`: **16 passed** in 1.083s (exit 0). This was before stderr from an intentional invalid-note case was redirected inside the test.
- `python3 -m unittest discover -s tests -v`: **139 passed** in 12.934s (exit 0). That includes `test_vendor_pin_byte_integrity`.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s (exit 0).
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0. The index listed `financial-terms-decision` as `PROVISIONAL_PRODUCT_DECISION` with nine `ADOPTED` entries, and `docs/decisions/revenue-participation.md` and `docs/decisions/claim-purchase.md` as `PENDING`.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `git diff --name-only -- capital .aiops .github`: no output (exit 0).
- `npm ci`: added 3 packages, 0 vulnerabilities. `node_modules` was absent. Chromium was already available at `/usr/bin/google-chrome` and in the Playwright cache. No browser download was required.
- `npm run test:browser`: **33 passed** in 53.0s (exit 0). A following `ss` check showed no listener. Playwright stopped its loopback servers.

After this section was appended, the unit discover was repeated: **139 passed** in 12.870s (exit 0). `python3 scripts/decision_ledger.py` and `python3 scripts/not_bound_checklist.py --check` both exited 0 again. `git diff --name-only -- capital .aiops .github` still printed nothing.

## Merge with origin/main

Conflict resolution kept both auditor assertions: the handbook bind receipt (`applied=bind_settlement` and the enabled draw control) and main's settlement-gate `BOUND` check. The three decision notes already on main stay. CAP-02 and CAP-03 in `docs/CAP_COVERAGE.md` name `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md` and stay `DECISION_REQUIRED`. The ledger accepts `DEFERRED` and `NOT_ADOPTED` only when `value` is null and `provided_by`, an ISO date, and `target` are present. `ADOPTED` and `UNDETERMINED` rules are unchanged. No file under `capital/`, `capital/vendor/`, `.aiops/`, or `.github/` was edited. No test was weakened or skipped. This paragraph claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

- `python3 -m unittest discover -s tests -v`: **140 passed** in 12.554s (exit 0).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s (exit 0).
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0. The index lists `settlement-policy-decision`, `accounts-tax-legal-decision`, `upstream-binding-decision` (`DEFERRED` / `NOT_ADOPTED` / one `ADOPTED`), and `financial-terms-decision`.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `git diff --name-only -- capital .aiops .github`: no output (exit 0).
- `npm run test:browser`: the first run failed to launch because Playwright 1.58.2's headless shell build 1208 was absent. After `npx playwright install chromium`, **33 passed** in 49.6s (exit 0), including the combined auditor spec.

## terms-overlay

Read-only simulated overlay of ADOPTED entries in `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`. Outputs use the label `simulated overlay — not vendor FSM arithmetic, not an offer`. This is not an offer, not vendor FSM arithmetic, and not real funds. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. `scripts/build_release.py` was not edited. No test was weakened or skipped. `python3 scripts/not_bound_checklist.py --write` was run once so the generated region in `docs/ACCEPTANCE_KO.md` matches the provisional financial-contracts blocker. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

Earlier discovers on incomplete trees failed and were fixed before the results below: an approved case used the settlement envelope instead of its inner claim; the facade `requirement_notes` schema omitted CAP-01 and CAP-04; the checklist block was stale; `capital/terms.py` used `Path(__file__)`, which `tests/test_release.py` rejects.

- `python3 -m unittest discover -s tests -v`: **149 passed** in 13.563s (exit 0). Seed lines that completed printed `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45` and `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.002s (exit 0).
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0. `financial-terms-decision` is `PROVISIONAL_PRODUCT_DECISION` with nine `ADOPTED` entries.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- `npm ci`: added 3 packages, 0 vulnerabilities. `node_modules` was absent.
- `npx playwright install chromium && npm run test:browser`: exit 0. **35 passed** in 54.5s, including `terms-overlay.spec.cjs` bound and unbound cases. The install step printed no download log; Chromium builds were already in the Playwright cache.
- `python3 scripts/acceptance.py`: exit 0. Evidence `ok` is true. Unit 149 passed, pinned vendor 7 passed, node-check passed, browser 35 passed, packaged-smoke 8 passed, seeded-demo 1 passed.
- A temporary zipapp `capital-0.1.0.pyz` (sha256 `f377c896cf93a1496b4380276ceeb09c40c24ffd6a37179cbc55c0e0f916717e`, then deleted) reported `default_note_path().is_file()` false and terms status `NOT_BOUND` / `terms not bound`.
- After the browser run and the acceptance ladder, `ss` showed no listener on 8765–8768 or 8891–8892.

## policy-simulator

Read-only simulated application of the `allocation_order` entry in `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md` through disposable `SettlementMachine` books. Outputs use the label `simulated policy application — not executed distribution, not bank movement`. `policy_adopted` stays false. Production stays `NOT_AUTHORIZED`. Items with `fsm_expressible: false` stay `UNSUPPORTED_BY_PINNED_FSM` with `computed: false`. The note's §7 shadow math (`SHADOW_NOT_APPLIED`) is not implemented; the node spec forbids that arithmetic in Capital. `derived-order-v1` is a comparison row. `/api/scenarios` stays at nine scenarios and 35 steps. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. `capital/scenarios.py`, `scripts/build_release.py`, and `tests/golden/demo.json` were not edited. No test was weakened or skipped. `python3 scripts/not_bound_checklist.py --write` was run once so the generated region in `docs/ACCEPTANCE_KO.md` matches the appended `UNSUPPORTED_BY_PINNED_FSM` financial-contracts blocker. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy. The node header says `user_merge: False`; the work encodes allocation priority, so merge stays with JunTae.

An earlier coupled discover failed twice and was fixed before the results below: the source scan matched `row['payee']`, and the checklist block was stale after the new readiness blocker.

- `python3 -m unittest discover -s tests -v`: **160 passed** in 13.922s (exit 0). Seed lines that completed printed `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45` and `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: **7 passed** in 0.003s (exit 0).
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0. `settlement-policy-decision` is `PROVISIONAL_PRODUCT_DECISION` with six `ADOPTED` entries (`allocation_order`, `refund_bearer`, `resale_prior_contract_cancel_burden`, `revenue_participation`, `claim_purchase`, `residual_and_late_cash`).
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- `npm ci && npm run test:browser`: exit 0. `npm ci` added 3 packages and reported 0 vulnerabilities (`node_modules` was absent). **37 passed** in 1.0m, including `policy-simulator.spec.cjs` adopted and undecided cases. Chromium was already in the Playwright cache; `npx playwright install chromium` was not run.
- `python3 scripts/acceptance.py`: exit 0. Evidence `ok` is true. Unit 160 passed, pinned vendor 7 passed, node-check passed, browser 37 passed, packaged-smoke 8 passed, seeded-demo 1 passed. Packaged artifact `build/acceptance-dist/capital-0.1.0.pyz` sha256 `a88c0a73dc6bc243bc33627cf1ebb09b04ee24462c8861ac3e57a4ce32994c32`. Seeded demo printed the same `state_digest` and `content_digest` as the unit run, with `debit=385000` and `credit=385000`.
- `test_zipapp_reports_not_bound` (inside the 160) asserts zipapp stdout `False`, `NOT_BOUND`, `policy not bound`.
- After the browser run and the acceptance ladder, `ss -ltnp` filtered for 8765–8768 and 8891–8894 showed no listeners.

## chaos-storage-conformance

Local `StoragePort` conformance vectors, crash-point injection, seeded command sequences, and a loopback HTTP boundary fuzzer. `tests/storage_conformance.py` exports `run_storage_vectors(factory)`. `InMemoryStorage` and `FileWorkspace` pass it. A future adapter must pass the same vectors. That pass is a local gate. It is not SEMANTIC_CONFORMANCE. CAP-11 stays `NOT_BOUND`. `LOCAL_FILE_WORKSPACE` stays a development-file label. This section claims no durability, no stage5 transaction recovery, no human acceptance, no independent review, no GitHub CI run, no commit, no push, and no deploy. Amounts and ids in the suite are synthetic fixture units. The label on the acceptance evidence is `SIMULATED`. `funds_executed` is false.

No file under `capital/`, `capital/vendor/`, `.aiops/`, or `.github/` was edited. `capital/store.py` is unchanged. No storage or HTTP defect was found, so no product fix was applied. No test was weakened or skipped. Sequence count stays 200 and fuzz count stays 500. `BASE_SEED` is `74810048`. Crash steps are temp open, write of zero bytes, partial write, file fsync, `os.replace`, and directory fsync. Each injected failure raises `WORKSPACE_WRITE_FAILED`. The next `load()` returns the last complete envelope. `CAPITAL_CHAOS_SEED` was unset for the full runs. An invalid value raises `ValueError`. A failing assertion prints `seed=<n>; reproduce: CAPITAL_CHAOS_SEED=<n>`. The env-seed unit test prints `digest drift seed=424242; reproduce: CAPITAL_CHAOS_SEED=424242` on purpose and still passes.

The first narrow run failed one honesty assertion because the helper docstring wrapped the words `GET and POST` across two lines. The docstring was reflowed onto one line. The fuzzer sends only GET and POST. The stdlib handler returns 501 for other methods by design. After that fix, every run below exited 0. The 500 malformed requests returned no 5xx other than the designed 503, and the server stayed up. `GET /api/state` after the fuzz still returned 200 with the same `operation_count` and `state_digest`. The acceptance parser leaves the browser `test_count` as null when Playwright prints an ANSI summary. The captured tail still contains `37 passed (56.8s)`. The parser was left unchanged. `node-check` has no count by design. HEAD at the ladder was `54cab8944fae74d3dc946b6e10814d48a37dc6b4`. Tools: Python 3.13.5, Node v20.19.2, npm 9.2.0, Playwright 1.58.2, capital 0.1.0.

- `python3 -m unittest tests.test_storage_conformance.StorageVectorTests tests.test_storage_conformance.CrashVectorTests tests.test_storage_conformance.ChaosSequenceTests.test_env_seed_reproduces_a_single_sequence -v`: exit 1 before the docstring fix. 5 tests in 0.069s, 1 failure (`GET and POST` split across lines). Crash vectors, both factories, and the env-seed test were otherwise ok.
- `python3 -m unittest tests.test_storage_conformance.ChaosSequenceTests.test_200_seeded_sequences_replay_reconcile_and_verify tests.test_storage_conformance.HttpFuzzTests -v`: exit 0. **2 passed** in 14.107s.
- `python3 -m unittest discover -s tests -p test_storage_conformance.py -v`: exit 0. **7 passed** in 14.794s, including the expected stderr seed line.
- `python3 -m unittest tests.test_acceptance tests.test_handbook -v`: exit 0. **11 passed** in 2.028s.
- `python3 -m unittest discover -s tests -v`: exit 0. **208 passed** in 38.504s. Completed seed lines printed `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45` and `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502` with `debit=385000` and `credit=385000`.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github`: no output (exit 0).
- `git diff --name-only -- capital/store.py`: no output (exit 0).
- `npm ci`: exit 0. Added 3 packages, audited 4 packages in 373ms, 0 vulnerabilities. `node_modules` was absent. npm warned that `NO_COLOR` is ignored because `FORCE_COLOR` is set.
- `npm run test:browser`: exit 0. **37 passed** (1.1m). Chromium is `/usr/bin/google-chrome`.
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` has `ok` true and label `SIMULATED`. Unit 208 passed in 40.080s, storage-conformance 7 passed in 13.575s, pinned vendor 7 passed, node-check passed (`test_count` null), browser passed (`test_count` null; tail shows `37 passed (56.8s)`), packaged-smoke 8 passed, seeded-demo 1 passed. Packaged artifact `build/acceptance-dist/capital-0.1.0.pyz` sha256 `3c67763e3121f42702d02c96cab282b4ba2c8fb84bda662a5fed70b930075b00`. Seeded demo printed the same digests, with `debit=385000` and `credit=385000`.
- `ss -ltnp`: header only. No leftover listener.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.

## upstream-claims-conformance

Executable CLAIM_CONFORMANCE table for the pinned FSM wrappers and the local facade. `tests/upstream_claims.json` has 87 claims. Each row has `source_doc`, `section`, `pinned_sha` `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, claim text, `check_id`, a citation needle, and the observed `expected` value. Checks run through `capital.protocol` and `capital/contract/facade-v1.json`. Amounts are synthetic fixture units. The label is SIMULATED. `funds_executed` stays false. This section claims no human acceptance, no GitHub CI run, no commit, no push, and no deploy. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. Upstream docs were not copied into the repo. The kix-protocol checkout was read only.

The first full `unittest discover` failed one package rule: `capital/upstream_claims.py` located the table with `Path(__file__)`. The locator now uses the parent of `capital.resources.ROOT`. After that change, every run below exited 0.

- `python3 -m unittest tests.test_upstream_claims tests.test_acceptance tests.test_handbook -v`: exit 0. **21 passed** in 4.589s. This was before the locator fix. Those three modules do not cover the package-path rule.
- `python3 -m unittest discover -s tests -v`: exit 1. **218 tests**, 1 failure, `test_package_modules_do_not_use_path_dunder_file` on `upstream_claims.py`.
- `python3 -m unittest tests.test_release.ResourceTests.test_package_modules_do_not_use_path_dunder_file tests.test_upstream_claims tests.test_release.SmokeTests -v`: exit 0 after the locator fix. **12 passed** in 2.863s.
- `python3 -m unittest discover -s tests -v`: exit 0. **218 passed** in 41.454s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/upstream_claims_check.py --protocol-dir /workspace/capital-run/kixproto-ro`: exit 0. `CLAIM_DRIFT verified=87 total=87`. The checkout was not modified.
- `python3 scripts/upstream_claims_check.py`: exit 0. First line `SKIPPED`. JSON status `SKIPPED`, label `CLAIM_CONFORMANCE`. The output has no success count.
- `python3 scripts/upstream_claims_check.py --execute`: exit 0. `CLAIM_CONFORMANCE passed=87 total=87 failed=0`.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `npm ci`: exit 0. Added 3 packages, audited 4 packages in 303ms, 0 vulnerabilities. `node_modules` was absent. npm warned that `NO_COLOR` is ignored because `FORCE_COLOR` is set.
- `npm run test:browser`: exit 0. **37 passed** (1.0m). Chromium is `/usr/bin/google-chrome`. `npx playwright install chromium` was not run.
- `ss -ltnp` after the browser run: header only. No leftover listener.
- `python3 scripts/acceptance.py`: exit 0 in 907s. Evidence `build/acceptance-evidence.json` has `ok` true, label `SIMULATED`, and `funds_executed` false. HEAD `863152c592aed04243bc578b5ef1137062ad9805`. Tools: Python 3.13.5, Node v20.19.2, npm 9.2.0, Playwright 1.58.2, capital 0.1.0. Unit 218 passed in 42.977s, storage-conformance 7 passed, pinned vendor 7 passed, upstream-claims passed with label `CLAIM_CONFORMANCE`, `passed=87`, `total=87`, and output `CLAIM_CONFORMANCE passed=87 total=87 failed=0`. node-check passed (`test_count` null). Browser passed (`test_count` null; tail shows `37 passed (1.8m)`). Packaged-smoke 8 passed. Artifact `build/acceptance-dist/capital-0.1.0.pyz` sha256 `11d98fcf527714c4f5961857f04941eaac557e9afae2a2be55c932af5da04c18`. Seeded demo 1 passed, `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45`, `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`, `debit=385000`, `credit=385000`. A search of that evidence file found no `SEMANTIC_CONFORMANCE` string.
- `ss -ltnp` after the ladder: header only. No leftover listener.

## observability-metrics

Local in-process counters, fixed millisecond latency buckets, uptime, workspace status, and an opt-in size-bounded JSONL event log. `GET /api/metrics` requires `metrics:read` (organizer and auditor). `GET /api/health` requires `health:read` (organizer, auditor, and observer). The agent role has neither permission. Counters stay out of the idempotency fingerprint, `state_digest`, `operation_count`, the workspace payload, and the export sections. The metrics body is labeled `LOCAL_OBSERVABILITY` and `SIMULATED`. External exporters, tracing, network sinks, and alerting stay `NOT_BOUND`. `funds_executed` is false. This section claims no human acceptance, no GitHub CI run, no commit, no push, and no deploy. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. No `ObservabilityPort` was added. `capital/static/app.js` was not edited. Amounts in the suite are synthetic fixture units. The label on the acceptance evidence is `SIMULATED`.

Commands actually run, in order:

- `python3 -m unittest tests.test_observability tests.test_auth tests.test_facade_contract tests.test_agent_lane -v`: exit 0. **46 passed** in 7.378s.
- `python3 -m unittest discover -s tests -v`: exit 0. **231 passed** in 62.182s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.004s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `npm ci`: exit 0. Added 3 packages, audited 4 packages in 360ms, 0 vulnerabilities. `node_modules` was absent. npm warned that `NO_COLOR` is ignored because `FORCE_COLOR` is set. The Playwright cache already had `chromium-1208` and `chromium-1243`. `npx playwright install` was not run. Chromium is `/usr/bin/google-chrome`.
- `npm run test:browser`: exit 0. **37 passed** (1.6m).
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` has `ok` true, label `SIMULATED`, and `funds_executed` false. HEAD `9e5e691c6390297fbf228a0d1650d5b595af80bb`. Tools: Python 3.13.5, Node v20.19.2, npm 9.2.0, Playwright 1.58.2, capital 0.1.0. Unit 231 passed in 47.107s, storage-conformance 7 passed in 13.435s, pinned vendor 7 passed in 0.002s, upstream-claims passed with label `CLAIM_CONFORMANCE`, `passed=87`, `total=87`, and output `CLAIM_CONFORMANCE passed=87 total=87 failed=0`. node-check passed (`test_count` null). Browser passed (`test_count` null; tail shows `37 passed (56.2s)`). Packaged-smoke 8 passed. Artifact `build/acceptance-dist/capital-0.1.0.pyz` sha256 `19fff12dc0fe9c6d945218400b32c6534839202f142859ad51a6d2dfe7775e41`. Seeded demo 1 passed, `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45`, `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`, `debit=385000`, `credit=385000`. A search of that evidence file found no `SEMANTIC_CONFORMANCE` string. Vendor hashes in the evidence file are `verified` true.
- After the browser run and after the ladder, nothing was listening on 127.0.0.1 ports 8765–8768. No `capital.server` process was left running.

The plan's manual `python3 -m capital.server --event-log` smoke was not started. `tests/test_observability.py` covers the JSONL writer, the unwritable path, the byte cap, and `--help`. No test was weakened or skipped. No product decision was left open.

## repay-allocation-preview

Read-only repayment allocation quote on the terms overlay: `GET /api/terms/{advance_id}/allocation?instance_id=&as_of_day=&cash=&draw_day=&expected_settlement_cash_day=`. Contract and default interest buckets are exact rationales floored to 1 KRW each; the hypothetical cash splits in the note's `repayment_allocation_order` (DEFAULT_INTEREST, INTEREST, PRINCIPAL); `fsm_repay` carries only the principal portion and is `null` when it is 0; `close_ready` requires phase `DRAWN` and all post-application dues at 0. Missing or unknown allocation orders fail closed to `NOT_BOUND`. Labels stay `SIMULATED_OVERLAY`. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. `scripts/build_release.py` was not edited. No test was weakened or skipped. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

Commands actually run, in order:

- `python3 -m unittest tests.test_repay_allocation -v`: exit 0. **10 passed** in 0.668s. An intermediate run failed once (`test_partial_note_and_bad_order_fail_closed`) because dropping the order line left an illegal trailing comma in the note JSON; the test was fixed to remove the preceding comma and to assert per-section status.
- `python3 -m unittest tests.test_terms tests.test_facade_contract tests.test_auth tests.test_seams -v`: exit 0. **34 passed** in 2.841s.
- `python3 -m unittest discover -s tests -v`: exit 0. **241 passed** in 50.484s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `npm ci`: exit 0. Added 3 packages, audited 4 packages, 0 vulnerabilities. `node_modules` was absent.
- `npm run test:browser`: exit 0. **37 passed** (1.1m). Chromium is `/usr/bin/google-chrome`; no browser download was required.
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` has `ok` true. Unit 241 passed, storage-conformance 7 passed, pinned-vendor 7 passed, upstream-claims `passed=87`, node-check passed, browser 37 passed, packaged-smoke 8 passed, seeded-demo 1 passed.
- After the browser run and after the ladder, `ss` showed no listener on 127.0.0.1 ports 8765–8768 and no `capital.server` process remained.

## terms-policy-ui

Read-only panels over existing GET responses in `capital/static`: the per-advance terms overlay card (interest, maturity, cap readout), the policy comparison table (DECIDED derived order beside the FIXTURE orders, with the `UNSUPPORTED_BY_PINNED_FSM` rows), and the U1–U6 underwriting record from `GET /api/underwrite/{id}`. The terms and policy panels were already present; this node adds the underwriting record in two places: `#case-underwrite` in the case detail (existing advance) and a full-width `#underwrite` section (fixture candidate with an assumed amount; GET-only inputs for scenario, amount and day). Values are shown verbatim from the response; the page does no arithmetic and shows full values without truncation. Responses are validated fail-closed (label, mode, `provisional`, `funds_executed`, `workspace_mutated`, `write_authorized`, `kyc_executed`, `underwriting_executed`, instance and state digest, `failed_check` equals the first FAIL, `proposal` matches). Invalid amount or day input is refused in the page and sends no request. Observer sees the authorizer's forbidden reason and no request is sent; auditor sees the same panels with no button, form or `data-op` control. `proposal` is labelled a rule-check record, not an approval. No endpoint, command, role, permission or CSP change. `capital/server.py` was not edited. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. No test was weakened or skipped. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy. All amounts are SIMULATED fixture units.

Commands actually run, in order:

- `npx playwright test tests/browser/underwrite-record.spec.cjs --project=workspace`: first run **5 passed, 1 failed**. The failing check was the test's own reference GET: the record echoes the caller's role (`decided_by_role`), and the Node-side reference carried no session token, so it compared `organizer` against the page's `auditor`. The page was correct. The reference GET now sends the auditor's `X-Capital-Token` and asserts `decided_by_role == auditor`. Rerun: **6 passed**.
- A visual check of the 375px screenshot showed `PASS`/`FAIL` splitting across lines in the narrow outcome column. Fixed with `white-space:nowrap` on that column.
- `npm run test:browser` (first full run): exit 1, **42 passed, 1 failed**. `tests/browser/acceptance-views.spec.cjs` uses the selector `#workspace .table-wrap`, and the new per-case table wrapper inside `#workspace` also carried `.table-wrap`, so Playwright's strict mode saw two elements. The existing assertion was not changed. The new wrappers use their own class `uw-scroll` instead.
- `npm run test:browser` (rerun): exit 0. **43 passed** (1.5m): the 37 existing specs plus 6 in `tests/browser/underwrite-record.spec.cjs`. Chromium is `/usr/bin/google-chrome`; the Playwright cache already had chromium. `node_modules` was absent and `npm ci` added 3 packages, 0 vulnerabilities.
- `python3 -m unittest discover -s tests -v`: exit 0. **241 passed** in 46.279s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output (exit 0).
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` has `ok` true, label `SIMULATED`, `funds_executed` false. Unit 241 passed, storage-conformance 7 passed, pinned-vendor 7 passed, upstream-claims `passed=87` `failed=0`, node-check passed, browser 43 passed, packaged-smoke 8 passed, seeded-demo 1 passed.
- Screenshots were written under `test-results/terms-policy-ui/` (15 files: desktop and 375px for the terms card, policy table, case record APPROVE and DECLINE, candidate APPROVE, U1 decline and U2 decline, plus auditor and observer views) and under `test-results/acceptance/{desktop,mobile}/` (`case-underwrite.png`, `candidate-underwrite.png` added to the seeded-demo views). `test-results/` is git-ignored.
- After the browser runs and the ladder, nothing was listening on 127.0.0.1 ports 8765–8768 or 8895–8899, and no `capital.server` process remained.

## manifest-verifier-vectors

Pinned tamper corpus for the offline manifest verifier (`python3 -m capital.verify`). `tests/vectors/manifest/` holds 12 manifests (SIMULATED book; `malformed.json` is a truncated copy): `unsigned.json` (clean, signature `NOT_BOUND`), `dev-hmac.json` (clean, `DEV_HMAC_SHA256`, `VERIFIED_DEV_ONLY_INTEGRITY` with its key), seven `section-<id>.json` (one byte of that section's `part_tag` flipped, `SECTION_HASH_MISMATCH:<id>`), `content-digest.json` (`CONTENT_DIGEST_MISMATCH`), `signature.json` (`SIGNATURE_MISMATCH`) and `malformed.json` (cut off mid-document, `MANIFEST_UNREADABLE`). `tests/vectors/export-dev.key` is a fixed synthetic `DEV_ONLY` key, test vector material and not a credential. Git stores it at mode 0644 and the verifier only reads mode 0600, so the tests copy it and chmod the copy. `scripts/manifest_vectors.py --write` regenerates the corpus from the `seed_demo` story replayed into a file workspace with a fixed instance id; `--check` byte-compares every file and fails on drift, a missing file, or an unexpected `manifest/*.json`. `tests/test_manifest_vectors.py` runs the CLI over every file and pins the reason, the per-section statuses, the digest status and the signature status. Its expectation table is written by hand, not read from the generator. `dev-hmac.json` and `unsigned.json` share `content_digest` `c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502` with `tests/golden/demo.json`. A shared HMAC key is integrity only, not authentication; this is not stage7 authenticated export. No new signature scheme, no export schema change, no external key. `capital/export.py`, `capital/verify.py`, `capital/contract/facade-v1.json`, `capital/vendor/`, `.aiops/`, `.github/` and `tests/golden/demo.json` were not edited. No test was weakened or skipped. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

Commands actually run, in order:

- `python3 scripts/manifest_vectors.py --write --dir <tmp1>` and `--dir <tmp2>`, then `diff -r`: identical. Both were separate processes. No UUID-shaped string in any file.
- `python3 -m capital.verify <file> --key-file <key at 0600>` over each of the 12 generated files: every file gave its intended reason. `dev-hmac.json` without a key gave `SIGNATURE_KEY_REQUIRED`.
- `python3 scripts/manifest_vectors.py --write` then `--check`: exit 0, 13 files match.
- `python3 -m unittest tests.test_manifest_vectors -v` (first run): **11 tests, 2 failed**, both bugs in the new test and not in the corpus. The stand-in wrong key was 31 bytes, so the verifier reported `SIGNATURE_KEY_UNREADABLE` instead of `SIGNATURE_MISMATCH`. The drift check edited `section-journal.json` for `journalpart`, but that file's tag is the tampered one, so the replace changed nothing. The test now uses a 32-byte key and edits `dev-hmac.json`, and asserts the edit changed the bytes.
- `python3 -m unittest tests.test_manifest_vectors -v` (rerun): exit 0. **11 passed** in 1.916s.
- Mutation checks, each restored with `--write`: one signature char changed in `signature.json` failed four regeneration tests; `signature.json` overwritten with the clean signed manifest failed `test_every_vector_reports_its_pinned_reason` for `signature.json` (`0 != 1`) and the one-byte test, plus the regeneration tests. After `--write` all 11 passed again.
- `python3 -m unittest discover -s tests -v` (first full run): exit 0. **272 passed**, tests ran 76.882s, wall time 10m04s with 42s user CPU. The gap was not investigated.
- `python3 -m unittest discover -s tests -v` (second full run, per-line timestamps): exit 0. **272 passed** in 51.076s, 52s wall. No step over 20s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0. `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`. The golden was not rewritten.
- `git diff --name-only -- capital/vendor capital/export.py capital/verify.py capital/contract/facade-v1.json .aiops .github docs/decisions tests/golden`: no output (exit 0).
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `npm ci`: exit 0. Added 3 packages, audited 4 packages, 0 vulnerabilities. `node_modules` was absent.
- `npm run test:browser`: exit 0. **43 passed** (1.2m). Chromium is `/usr/bin/google-chrome`. The only listeners on 127.0.0.1:87xx/88xx afterwards belonged to the sandbox egress tunnel, not to this repo, and no `capital.server` process remained.
- `python3 scripts/acceptance.py`: exit 0. Wall time 16m17s with 1m31s user CPU. Evidence `build/acceptance-evidence.json` has `ok` true, label `SIMULATED`, `funds_executed` false. Unit 272 passed, storage-conformance 7 passed, pinned-vendor 7 passed, upstream-claims `passed=87` `failed=0`, node-check passed, browser 43 passed, packaged-smoke 8 passed, seeded-demo 1 passed.
- `grep` of `tests/vectors/` for `/workspace`, `/tmp/`, `/home/`, a temp-directory name and `workspace.json`: no match. The key staying out of every manifest is asserted by `test_key_file_is_dev_only_and_stays_out_of_every_manifest`.

## auth-matrix-freeze

A pinned route-by-role authorization table, `tests/auth_matrix.json` (`KIX_CAPITAL_AUTH_MATRIX_V1`, SIMULATED, `SYNTHETIC_LOCAL_ROLE`, identity and authentication `NOT_BOUND`). It crosses all 25 registered routes (17 GET and 5 POST in the dispatcher, plus the 3 static assets) with organizer, auditor, observer, agent and a caller with no token: 125 cells, each with an expected outcome, status, error code, and for a denial the permission and role. It also pins 50 command cells (the 10 `/api/commands` operations by the 5 callers), the per-operation permission map, the role-to-permission snapshot, and 69 boundary cases (unregistered paths, near-miss paths, method mismatches, `ROLE_MISMATCH`, `SESSION_REQUIRED`, `ROLE_UNKNOWN`, unknown tokens, assets served before authentication). `tests/test_auth_matrix.py` sends every one of them to a real loopback `make_server(0)`. `scripts/auth_matrix.py --write` regenerates the table and the generated blocks in `docs/INTEGRATION.md` and `docs/OPERATOR_HANDBOOK_KO.md`; `--check` exits 1 on drift. The table pins the behavior observed today. It is a synthetic placeholder, not an entitlement policy.

No file under `capital/`, `capital/vendor/`, `.aiops/`, `.github/`, `docs/decisions/`, or `tests/golden/` was edited, so no route, permission, role, or error code changed. No test was weakened or skipped. The handbook's existing `## 역할` table was left as written (the handbook convention is to add a node section, not to rewrite one); the new generated section is the complete table and says it governs if they differ. `docs/ACCEPTANCE_KO.md` gained one auditor step that names `LiveMatrixTests.test_every_cell`. `README.md` gained one bullet. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy.

Facts the live run established, which the table now pins: an agent token is denied every GET including `/api/state`; `POST /api/agent/execute` passes the `agent:propose_action` gate and then returns `403 EXECUTE_AUTHORITY_DISABLED`; every POST checks the token before the route, so an unregistered POST path is `403 LOCAL_TOKEN_REQUIRED` with no token and `404 NOT_FOUND` with one; authentication runs before the unregistered-GET 404, so `X-Capital-Role: auditor` without a token on an unknown path is `403 SESSION_REQUIRED`; a role mismatch is reported before a permission denial; static assets are served before authentication and ignore a bogus token or role header. Through HTTP only `command:submit` is checked at the route gate, and the service then names `command:{op}`. Because organizer holds every `command:*`, the per-operation denial is shown over HTTP with a test-only authorizer subclass (`SubmitOnlyAuthorizer`, defined in the test module, never used by the server).

Commands actually run, in order:

- A scratch loopback server probe (not kept) confirmed all 24 GET probes answer 200 for organizer after one seeded `offer`, and that the `reconcile` probe stores one receipt and leaves the machine `state_digest` unchanged.
- `python3 -m unittest tests.test_auth_matrix` (first run): **36 tests, 6 failed**, all bugs in the new work and not in the server. Roles and ops were reordered alphabetically because the table was dumped with `sort_keys=True`, so a render from the loaded table differed from one from `build()`; `dump()` now keeps insertion order. One edge assertion required an exact caller set and was relaxed to a superset.
- `python3 -m unittest tests.test_auth_matrix` (second run): **2 failed**. The probe operation id `sim-mtx-probe-bind_settlement` contains an underscore, which the operation-id pattern rejects, so the command probes stopped at `INVALID_OPERATION_ID` before the check they were meant to reach. Ids now replace `_` with `-`.
- `python3 -m unittest tests.test_auth_matrix` three times in a row: exit 0 each time, **36 passed** in about 1.4s. No flake.
- Mutation checks, patched in memory only through a scratch script, no file under `capital/` edited: observer given `projection:read` failed 15 tests; `/api/metrics` remapped to `state:read` in `ROUTE_PERMISSIONS` failed 8 (including the live observer and agent cells for `/api/metrics`); `/api/metrics` removed from `GET_DISPATCH` failed 9 and errored 3; agent given `session:bind` failed 7 (including the live `POST /api/session` agent cell); auditor given `command:submit` failed 18 (live command cells). Every mutation failed the suite.
- `python3 scripts/auth_matrix.py --write` then `--check`: exit 0.
- `python3 -m unittest discover -s tests -v`: exit 0. **308 passed** in 53.6s (272 before this node plus 36).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital scripts tests`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/not_bound_checklist.py --check`: exit 0.
- `python3 scripts/decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0. `content_digest=c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502`, the same as before this node. The golden was not rewritten.
- `git diff --name-only -- capital capital/vendor .aiops .github docs/decisions tests/golden`: no output.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `npm ci`: exit 0. Added 3 packages, 0 vulnerabilities. `node_modules` was absent.
- `npm run test:browser`: exit 0. **43 passed** (reported 1.8m by Playwright). Chromium is `/usr/bin/google-chrome`. The shell wall time for the command was 51m58s against 1m9s of user CPU; the gap was not investigated and no step of this node's work is in it.
- `python3 scripts/build_release.py --out` twice into temporary directories, then `cmp`: identical. `python3 scripts/smoke_release.py` on that archive: exit 0, eight checks ok. The archive contains no `scripts/`, `tests/`, or `auth_matrix` entry, so the zipapp surface is unchanged. The temporary directories were removed.
- `python3 scripts/acceptance.py` was not run in full. Its stages are the commands above, run one by one, except `upstream-claims`, which `tests/test_upstream_claims.py` covers inside the unit suite.
- After the browser run, the only listener on 127.0.0.1:87xx/88xx was `sand-egress-tun` on 8791, which belongs to the sandbox and not to this repo. No `capital.server` process remained.

## retention-slots-sync

The manifest `retention_policy` `NOT_BOUND` constant became five named empty slots — `legal_dispute_hold`, `business_reconciliation`, `retry_support`, `memory_residency`, `tax_accounting_records` — each exactly `{owner, status}`, status `UNDETERMINED` or `DECISION_REQUIRED`. Names, owners and statuses come from the merged `capital-decision-v1` blocks in `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` (`deployment_tls_retention`, upstream R1 / PR #139 `6e54e723`) and `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` (`data_retention_privacy`, `CAPITAL-RETENTION-PRIVACY-V1`; `NOT_SET_OWNER_SUPPLIED` reads as `UNDETERMINED`, `NOT_SET_DECISION_REQUIRED` as `DECISION_REQUIRED`). The `memory_residency` `{count, bytes, age}` bounds stay prose in the notes and flatten to one `DECISION_REQUIRED`; `MAX_OPERATIONS 500` is a demo capacity bound, not a retention value. No duration, bound, timer, or deletion code was added anywhere. The `not_bound` `retention_policy` row keeps `status` `NOT_BOUND` and `value` null because the durations are what stay unbound.

`capital/verify.py` semantics are unchanged: it still checks only sections, `content_digest`, and signature. Because `retention_policy` is inside `content_material()`, the pin moved exactly one field: `tests/golden/demo.json` `content_digest` `c06f05d3…7502` → `c0701501…0376`, regenerated only via `python3 scripts/seed_demo.py --update-golden`; `state_digest` `a8609033…ef45` and `debit=385000`/`credit=385000` are unchanged. The 12 files under `tests/vectors/manifest/` were regenerated only via `python3 scripts/manifest_vectors.py --write`. `capital/static/app.js` `manifestValid` now fail-closed checks the five keys, each `{owner: non-empty string, status}` with the per-slot status. `capital/contract/facade-v1.json` gains `retention_slot_undetermined`/`retention_slot_decision_required`/`retention_policy` definitions with `additionalProperties: false` and a per-slot `const` status. The readiness `release` blocker `인증/TLS/보존·복구·개인정보·배포 명시 승인` now cites `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` per that note's consumer row; the generated block in `docs/ACCEPTANCE_KO.md` was rewritten only by `python3 scripts/not_bound_checklist.py --write`. No file under `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited. No test was weakened or skipped. This section claims no human acceptance, independent review, GitHub CI run, commit, push, or deploy. Labels stay SIMULATED / provisional.

Commands actually run, in order:

- `python3 -m unittest tests.test_export_manifest -v`: exit 0. **16 passed** in 1.611s, including the new `test_retention_policy_mirrors_the_merged_decision_notes`, which derives expected owners and statuses from the two decision-note blocks instead of copied literals.
- `python3 scripts/not_bound_checklist.py --write` then `--check`: exit 0 both. The regenerated block differs only in the release blocker line.
- `python3 -m unittest tests.test_export_manifest tests.test_manifest_vectors tests.test_facade_contract tests.test_seed_demo tests.test_handbook`: exit 0. **43 passed** in 7.180s.
- `python3 scripts/manifest_vectors.py --check`: exit 0, `manifest vectors ok: 13 files match`.
- `python3 -m capital.verify tests/vectors/manifest/unsigned.json`: exit 0, `ok:true`, all seven sections `MATCHED`, `content_digest` `MATCHED`, signature `NOT_BOUND`.
- `git diff tests/golden/demo.json`: only the `content_digest` line changed.
- `python3 -m unittest discover -s tests`: exit 0. **309 passed** in 57.599s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0. **7 passed** in 0.002s.
- `python3 -m compileall -q capital`: exit 0.
- `node --check capital/static/app.js`: exit 0.
- `python3 scripts/auth_matrix.py --check`: exit 0 (no route or permission change).
- `python3 scripts/decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, golden matches (`state_digest=a8609033…ef45`, `content_digest=c0701501…0376`, `debit=385000`, `credit=385000`). The golden was not rewritten a second time.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output.
- `npm ci`: exit 0. Added 3 packages, 0 vulnerabilities. `node_modules` was absent. Chromium builds were already in the Playwright cache; `/usr/bin/google-chrome` exists.
- `npm run test:browser`: exit 0. **43 passed** (1.4m), including the updated `export-manifest.spec.cjs` slot assertions. Playwright started and stopped the loopback servers; a later `pgrep`/`ss` check found no `capital.server` process and no listener on 8765–8768.
- `python3 scripts/acceptance.py` was not run in full. Its stages are the commands above, run one by one, except `upstream-claims`, which `tests/test_upstream_claims.py` covers inside the unit suite.

No `DECISION_REQUIRED.md` was written: slot names, owners, statuses, and the no-durations rule are all decided by the merged notes, so no product decision was left open.

## asset-spec-krw

KRW is declared once as an AssetSpec in `capital/assets.py` (`{namespace: fiat, reference: KRW, decimals: 0, max_atoms: 1000000000000}`, PROVISIONAL per `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` section 3.6, entry `asset_registry_fx`, sync item `asset-spec-declaration`). `max_atoms` is the pinned FSM `MONEY_MAX` fixture bound, not a registry limit; a test pins it to `mock_credit.MONEY_MAX` and `mock_settlement.MONEY_MAX`. `GET /api/state` gains `assets` and the manifest `source_pin` body gains the same one-entry `assets` array. `POST /api/commands` accepts an optional envelope field `asset`: it must match the declared spec field by field and type (so `0.0`, `false` or `1e12` in place of an integer, a bare `"KRW"` and an extra key all fail), otherwise `400 ASSET_MISMATCH`. The check runs after the role check and the `SESSION_CHANGED` check and before the idempotency lookup, so a mismatch leaves the journal, the receipts, the storage `save` count, the command counters and `state_digest` untouched and the operation id stays `UNKNOWN` and reusable. `asset` is not in the idempotency fingerprint and is not echoed into receipts. Registry stays DEFERRED, FX NOT_ADOPTED, there is no second asset and amounts stay integers. The projection account keys that the note's sync item also names are not changed (out of scope for this node).

Pinned artifacts moved because the `source_pin` body changed: all 12 `tests/vectors/manifest/*.json` manifests (regenerated by `python3 scripts/manifest_vectors.py --write`, `export-dev.key` untouched) and `tests/golden/demo.json` `content_digest` `c0701501…0376` → `7a7da500…17da` (regenerated by `python3 scripts/seed_demo.py --update-golden`); `state_digest` `a8609033…ef45` and `debit=385000 credit=385000` are unchanged. `capital/vendor/` and `.aiops/` have no diff.

Commands actually run, in order:

- `python3 -m unittest tests.test_facade_contract tests.test_capital tests.test_export_manifest tests.test_manifest_vectors tests.test_seed_demo` before regenerating: 57 ran, 7 failed, all pinned-artifact drift (4 in `test_manifest_vectors`, 3 in `test_seed_demo`).
- `python3 scripts/manifest_vectors.py --write` then `--check`: exit 0, `manifest vectors ok: 13 files match`. `python3 scripts/seed_demo.py --update-golden` then `python3 scripts/seed_demo.py`: both `seed demo ok SIMULATED`.
- `python3 scripts/not_bound_checklist.py --write` then `--check`: exit 0; `docs/ACCEPTANCE_KO.md` unchanged (readiness blockers were not edited). `python3 scripts/auth_matrix.py --check`: exit 0 (no route or permission added).
- `python3 -m unittest discover -s tests -p test_asset_spec.py`: **32 passed**. Two mutants were run against it and both failed it: `asset_matches` always true (6 failures) and naive `==` (3 failures, which is why the matcher compares types).
- `python3 -m unittest discover -s tests -v`: exit 0, **341 tests OK** in 158s (a rerun on the finished tree: 341 OK in 56s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: 7 passed. `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `python3 scripts/build_release.py --out /tmp/asset-dist` then `python3 scripts/smoke_release.py` on the zipapp: exit 0, `capital/assets.py` is inside the archive and `snapshot()['assets']` is the same one entry there (decision notes are not bundled, so the CAP-12 note reads `NOT_BOUND per docs/decisions/CAPITAL_UPSTREAM_BINDING.md` in that run, as the other note quotes do).
- `npm ci --offline --ignore-scripts` (cache only, no network), then `npm run test:browser`: the first run reported 32 passed, 11 failed (9.0 min; failures in `acceptedClick` waits across `auditor-role`, `journey`, `persistence`, `policy-simulator` and `portfolio` specs). `npx playwright test --project=workspace tests/browser/journey.spec.cjs` then passed 15/15 and a second full `npm run test:browser` passed **43/43** in 1.5 min. The first run's cause was not isolated; it was not reproduced. No `capital.server` process or listener on 8765-8769 remained.

## finance-vector-pack

Deterministic, SIMULATED input vectors for FINANCE_PENDING_NODES candidates, in `tests/vectors/finance_vectors.json` (format `KIX_CAPITAL_FINANCE_VECTORS_V1`, canonical ASCII JSON, no clock, no instance id, no path). This is the vector-supplier role of `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` (entry `stage6_finance_candidates`). Every group carries the label `INPUT_VECTOR_CANDIDATE` and names one candidate id (eight groups, one per candidate):

- `scenario_obligations` → `fin-multi-payee-refund-proof`: all 9 F01-F03 scenarios of `capital/scenarios.py` and their 35 steps. Each step records op, args, outcome, error, duplicate flag, the per-payee obligation rows (`face`, `distributed`, `cancelled_unpaid`, `recovery_due`, `outstanding`), the cash and refund totals, the predicate results and a digest of the whole settlement view. No settlement policy is chosen; the fixture orders and the undefined refund bearer are replayed as they are.
- `f04_command_outcomes` → `fin-ledger-contract`: the 22 `seed_demo` commands run through `CapitalService.execute` (21 `ACCEPTED`, one `REJECTED` `SETTLEMENT_NOT_COMMITTED` that leaves the journal at 21 entries), each with phase, exposure and `state_digest` after, plus the 21 journal entries (scalar body fields and a body digest). The final `state_digest` is the `tests/golden/demo.json` value.
- `journal_projection_digests` → `fin-double-entry-projection`: for each of the 22 journal prefixes (0 through 21 entries) the restored `state_digest` and the `SIMULATION_FIXED_V1` entries, accounts and read-model digests with debit and credit totals, then the final 16 account totals and the five conservation predicates. The last prefix ends at debit = credit = 385000, the golden projection totals.

- `seed_reconciliation` → `fin-observation-reconciliation`: the `capital/recon.py` six-check report on the fixed-instance seed book (`finance-vectors`), all six `MATCHED` in order, with `state_digest` equal to the golden value, the three `NOT_BOUND` gaps, and one probed operation id (`op-never-issued`) that stays `UNKNOWN_UNRESOLVED` with `retry_authorized` false. Instance id keys are stripped (`capital.export.strip_volatile`), so the report is what any instance produces.
- `statement_and_previews` → `fin-credit-exposure-reconciliation`: the `capital/statement.py` five-category statement (approved 90000, exposure drawn 65000 / repaid 20000 / outstanding 45000, reserved 45000, settlement confirmed 194000 / distributed 0, refund face 10000 / accepted 0), `sales_combined` false, and the six read-only draw previews of `/api/preview/{advance_id}` (only `sim-pending-settlement` is `WOULD_REJECT` / `SETTLEMENT_NOT_COMMITTED`). Instance id keys are stripped.
- `manifest_section_digests` → `fin-consistent-accounting-export`: for the v2 manifest of the same seed book, the seven section ids, each stored section `sha256` (it covers a body that carries the seed's instance id), each instance-free section hash that `content_digest` covers, and `content_digest` itself, which equals `tests/golden/demo.json`. The manifest body is not copied; `status` is `COMPLETE`, the signature is `UNSIGNED` / `NOT_BOUND`.
- `facade_read_model` → `fin-catalogue-read-model`: for each of the 21 GET api routes of `capital/contract/facade-v1.json`, the permission, the response definitions with their sha256 digests, and the transitive `$ref` closure with its digest, plus a digest of the whole contract. It is the local `capital-local-facade/1` read shape, not a catalogue, and `semantic_conformance` stays false.

- `closeout_digest` → `fin-finance-closeout`: the committed digest `tests/vectors/closeout_digest.json` (format `KIX_CAPITAL_CLOSEOUT_DIGEST_V1`), embedded as it is. It is derived from `build/acceptance-evidence.json` by `scripts/closeout_digest.py` and is the only way it is written; see the `closeout-evidence-vector` section. Regenerate it before `finance_vectors.py --write`.

All eight candidates now have vectors. The `candidates` index shows `vectors` non-null and `reason` null for each of the eight ids, `fin-finance-closeout` now pointing at `closeout_digest`. The eight ids are the ones the binding note copies from `docs/aiops/FINANCE_PENDING_NODES.json` in kix-protocol, which stays the source of truth; the test reads them from the note.

This is not SEMANTIC_CONFORMANCE, and it completes no upstream node. `semantic_conformance` is `false` and `upstream_nodes_completed` is `[]` inside the artifact. `--check` says only that the pinned local code still produces these bytes. No candidate becomes DONE, the denominator does not shrink, no accounting policy or settlement policy is adopted, and an upstream node can use these vectors only with its own completion proof.

`python3 scripts/finance_vectors.py --write` regenerates the file and `--check` byte-compares it, exits 1 on any difference or a missing file, and names the first differing JSON paths. `--file` points both at another path. `tests/test_finance_vectors.py` writes its expectations by hand (the 35-step obligation table, the 22-command table, the per-prefix debit totals, the statement and preview tables, the 21 facade read routes) and does not read them from the generator. It also cross-checks the artifact against the live `CapitalService.scenarios`, `seed_demo.build_service()` (a random instance id) with `reconciliation()`, `statement()`, `preview_draw()`, `export_manifest()` and `projection()`, against the contract file, and against `tests/golden/demo.json`.

No file under `capital/`, `capital/vendor/`, `.aiops/`, `.github/`, `docs/decisions/`, `tests/golden/` or `tests/vectors/manifest/` was edited. No test was weakened or skipped.

Commands actually run, in order:

- Cross-check of the eight candidate ids against `docs/aiops/FINANCE_PENDING_NODES.json` in the read-only protocol checkout (`/workspace/capital-run/kixproto-ro`, HEAD `ab42cfe`): all eight ids present and equal to the binding note's `candidate_ids`. Nothing in that checkout was modified. (The test itself reads only the note, so it needs no checkout.)
- `python3 scripts/finance_vectors.py --write` twice, then `cmp`: identical, 63372 bytes, sha256 `ea69c992…1375`. `--check`: exit 0.
- `python3 -m unittest tests.test_finance_vectors -v` (first run, docs section not yet written): **28 ran, 1 failed**, `test_docs_state_the_non_claim` for the missing section. Everything else passed.
- Mutation checks on the committed artifact, each restored by `--write` and `cmp` against the saved original: one `outstanding` value changed (9 failures across the hand-written table, the conservation test and the regeneration tests) and one group `label` changed to `ADOPTED` (8 failures, including `test_every_group_names_one_candidate_and_carries_the_label`).
- `--check --file <temp copy>` with one `outstanding` value edited: exit 1, `finance vectors drift: $.groups.scenario_obligations.scenarios[0].steps[1].obligations[0].outstanding`. After `--write --file`: exit 0 and byte-identical to the committed file. `--check --file <absent>`: exit 1, `finance vectors missing`.
- `python3 -m unittest tests.test_finance_vectors -v` (after the docs section): exit 0, **28 passed**.
- `python3 -m unittest discover -s tests -v` (first full run): **369 ran, 2 failed**, both in `tests/test_manifest_vectors.py`. Its `RegenerationTests.committed()` collected every file under `tests/vectors/`, so the new sibling `finance_vectors.json` made `test_regeneration_reproduces_the_committed_bytes` and `test_write_into_another_directory_matches_and_check_catches_drift` fail. This was caused by this node adding a file to a directory the older test treated as its own. The helper now collects only what `scripts/manifest_vectors.py` owns: `export-dev.key` and every file under `manifest/`. A stray `tests/vectors/manifest/extra.json` still fails five of its tests (checked, then removed), so the test is no looser for the files it owns. No assertion was removed or skipped.
- `python3 -m unittest tests.test_manifest_vectors tests.test_finance_vectors`: exit 0, **39 passed**.
- `python3 -m unittest discover -s tests -v` (rerun on the finished tree): exit 0, **369 passed** in 62.8s (341 before this node plus 28 new).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`: exit 0. `python3 -m py_compile scripts/finance_vectors.py tests/test_finance_vectors.py`: exit 0. `node --check capital/static/app.js`: exit 0.
- `python3 scripts/finance_vectors.py --check`, `python3 scripts/manifest_vectors.py --check` (13 files match), `python3 scripts/not_bound_checklist.py --check`, `python3 scripts/auth_matrix.py --check`, `python3 scripts/decision_ledger.py`: all exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=7a7da500…17da`, `debit=385000 credit=385000`. The golden was not rewritten and `git diff tests/golden` is empty.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`.
- `git diff --name-only -- capital .aiops .github docs/decisions tests/golden tests/vectors/manifest`: no output.
- `npm ci --offline --ignore-scripts` (cache only, no network): exit 0, 3 packages. `npm run test:browser`: exit 0, **43 passed** (1.9m). Chromium headless shell from the Playwright cache. Afterwards no `capital.server` or Playwright process from this worktree remained and nothing listened on 127.0.0.1:8765-8769 or 88xx. Other processes on the host (a different project's Playwright run and the host's own Chrome sessions) were not started by this node and were left alone.
- `python3 scripts/acceptance.py` was not run in full. Its stages are the commands above, run one by one, except `upstream-claims`, which `tests/test_upstream_claims.py` covers inside the unit suite.

No `DECISION_REQUIRED.md` was written: every amount already sits inside the pinned mocks, and no rate, fee, limit, allocation priority, refund burden, provider, credential or upstream change was needed.

## delegation-claims-conformance

A second pinned claim table `tests/agent_claims.json` (format `KIX_CAPITAL_AGENT_CLAIMS_V1`, 66 rows) mirrors the upstream-claims pattern for the SIMULATED agent lane. Every row cites `docs/contracts/AI_DELEGATION_AUTHORITY.md` (draft 0.1) with a `section` heading fragment and a verbatim `needle`, pinned to `e2a029d8ac3af7575888dac22fc4bf173ebec232` — the kix-protocol main named in `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` section 3.9 (`ai_agent_grant_action_permit`, ADOPTED for the grant/proposal lane). The doc is byte-identical at that SHA and at the read-only checkout's HEAD `ab42cfe` (sha256 `aedcd484e47b72f1f520495648394cb4c51250e9eceb1951aa4cf0b1d5eaf861` both ways). Rows cover the fixture grant view (grant_id `sim-grant-agent`, generation 2, `['PROPOSE','QUERY']` authority, the four limit fields plus KRW and the `DRAFT_INPUT_CEILING_NOT_A_PRODUCT_LIMIT` and `SIMULATED_LOGICAL_WINDOW` labels), all twelve always-false flags, proposal storage (`HUMAN_PENDING`, `effects_executed` false, `decision` null, duplicate/binding-conflict, two-person marker, scope/amount/per-action/cumulative refusals, `EXECUTE` kind), the 403 `EXECUTE_AUTHORITY_DISABLED` facade refusal with no write, period/generation/revocation/unknown/invalid boundaries, organizer `proposal_id` citation stamped on the receipt while the memo stays pending, and the not-vendored mock check. The table `note` records the honest adapter mapping: Capital `HUMAN_PENDING` mirrors the draft's `PROPOSED` memo, and `EXECUTE_AUTHORITY_DISABLED` mirrors the draft's always-failing `attempt_execution` (`DELEGATED_EXECUTION_DISABLED`).

`capital/agent_claims.py` holds the `agent.*` check registry and thin wrappers that delegate to the shared table/drift helpers in `capital/upstream_claims.py`, which gained keyword-only `format`/`label`/`pinned_sha`/`checks` parameters with unchanged defaults; `tests/test_upstream_claims.py` is unedited and still green. `scripts/agent_claims_check.py` mirrors the upstream CLI: bare invocation prints `SKIPPED` (never a pass), `--execute` prints the `CLAIM_CONFORMANCE passed=N total=N failed=0` count line, `--protocol-dir` verifies the doc title and cited strings read-only (`os.O_RDONLY`, no writes). `scripts/acceptance.py` runs it as a second command inside the unchanged `upstream-claims` stage, so both tables merge under the `CLAIM_CONFORMANCE` label (`_merge_counts` sums the two count lines; stage total is now 87+66=153). `tests/test_agent_claims.py` adds 12 tests: field/pin/source validation, all-rows-pass, acceptance-coverage presence, unmapped-check and flipped-expected mutations, SKIPPED semantics, read-only synthetic-tree drift verification (byte snapshot before/after), non-directory failure, the count line, the merged acceptance stage, wrong format/label/pin rejection, and script separation. Nothing was vendored; no auth, EXECUTE, ActionPermit or facade change was made. This is not SEMANTIC_CONFORMANCE, not a producer-profile adoption, and no funds move.

Commands actually run, in order:

- `git show e2a029d…:docs/contracts/AI_DELEGATION_AUTHORITY.md | sha256sum` and `sha256sum` of the working file in `/workspace/capital-run/kixproto-ro`: identical, `aedcd484…f861`; `git log e2a029d..HEAD` for that path and `reference/ai_delegation/` shows no commits. The checkout was read only.
- `python3 scripts/agent_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=66 total=66 failed=0`.
- `python3 scripts/agent_claims_check.py --protocol-dir /workspace/capital-run/kixproto-ro`: exit 0, `CLAIM_DRIFT verified=66 total=66`; `--execute --protocol-dir` together also exit 0.
- `python3 scripts/agent_claims_check.py`: exit 0, first line `SKIPPED`, JSON status `SKIPPED` label `CLAIM_CONFORMANCE`, no success count.
- `python3 -m unittest discover -s tests -p test_agent_claims.py -v`: exit 0, **12 passed** in 5.2s (merged stage evidence shows `passed=153`).
- `python3 -m unittest tests.test_upstream_claims tests.test_acceptance tests.test_agent_lane -v`: exit 0, **28 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **381 passed** in 97.9s (369 before this node plus 12 new).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `npm ci`: exit 0, added 3 packages. `npm run test:browser`: exit 0, **43 passed** (1.4m). Playwright started and stopped its loopback servers; afterwards no `capital.server` process and nothing on 127.0.0.1:8765-8768 remained.
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` `ok` true. Stages: unit 381, storage-conformance 7, pinned-vendor 7, upstream-claims `passed=153` `failed=0` label `CLAIM_CONFORMANCE`, node-check, browser 43, packaged-smoke 8, seeded-demo 1. Vendor hashes `verified` true; no `SEMANTIC_CONFORMANCE` string in the evidence.
- `git diff --name-only -- capital/vendor .aiops .github`: no output; `source_integrity` reports all five vendor files matched, commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`.

No `DECISION_REQUIRED.md` was written: the pin SHA is the binding note's decided `kix_protocol_main`, and the lane's limits and two-person value come from the ADOPTED `underwriting_depth` entry — nothing needed a new product decision.

## audit30-fix2

Audit@30 found that `tests/vectors/finance_vectors.json` supplied vectors for 3 of the 8 `FINANCE_PENDING_NODES` candidates although the node title and `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` §3.3 (`artifact_map`) name a Capital input for each. `scripts/finance_vectors.py` now has four more deterministic groups, all labelled `INPUT_VECTOR_CANDIDATE` and `SIMULATED`: `seed_reconciliation` (`fin-observation-reconciliation`), `statement_and_previews` (`fin-credit-exposure-reconciliation`), `manifest_section_digests` (`fin-consistent-accounting-export`) and `facade_read_model` (`fin-catalogue-read-model`). The `candidates` index now shows `vectors` non-null for 7 of 8 ids; `fin-finance-closeout` stays `null` and gains a `reason` field (its input `build/acceptance-evidence.json` is an untracked per-run file recording `head_sha` and tool versions, so no stable bytes exist to pin). Every row of the index now has `reason`, `null` for the seven supplied candidates. The artifact is still not SEMANTIC_CONFORMANCE and it completes no upstream node; `semantic_conformance` is `false`, `upstream_nodes_completed` is `[]`, and no clock, no instance id and no path is in the bytes. The group descriptions and the stale "other five candidates" paragraph in `## finance-vector-pack` were updated in place. No projection, policy, chart or amount changed, and nothing under `capital/`, `capital/vendor/`, `.aiops/`, `.github/`, `docs/decisions/`, `tests/golden/` or `tests/vectors/manifest/` was edited.

Two things in the new groups are worth knowing. The manifest group records two hashes per section: `section_sha256` is the stored hash, which covers a body that carries the seed's instance id (`finance-vectors`) for the `receipts`, `projection`, `reconciliation` and `statement` sections, and `section_content_sha256` is the hash `content_digest` covers after instance and timestamp keys are removed. The second set and `content_digest` are what any instance reproduces; `tests/test_finance_vectors.py` asserts `content_digest` equals `tests/golden/demo.json` and recomputes both against `seed_demo.build_service()` on a random instance id. The facade group stores, per GET route, the digest of each response definition and of the transitive `$ref` closure, so an edit to a nested definition such as `gap` moves the route's `closure_digest` while its own `definition_digest` stays; the 8 POST and static routes are left out.

Commands actually run, in order:

- `python3 scripts/finance_vectors.py --check` before regenerating: exit 1, drift at `$.candidates[*].reason` and the vectors of three ids (the new `reason` field and the new groups).
- `python3 scripts/finance_vectors.py --write` twice, then `cmp`: identical, 85079 bytes (63372 before), sha256 `5e0ab57a…bc10`. `--check`: exit 0, `finance vectors ok: 85079 bytes match`.
- A scan of the artifact bytes for `instance_id`, `timestamp`, `/workspace`, `/tmp`, `/home/`, `finance-vectors` and `workspace.json`: none present.
- `python3 -m unittest tests.test_finance_vectors` (first run with the new tests): 54 ran, 3 failed. Two were my own section-order assertion (JSON object keys come back sorted, so the test now compares sorted keys) and one was `test_docs_state_the_non_claim`, which failed until the docs text above was written. After both fixes: exit 0, **54 passed** (28 before this node, 26 new).
- Mutation checks on the committed artifact, each restored and compared with `cmp` against the saved original: `drawn` 65000→65001, the manifest `content_digest` last-bit edit, one recon check `MATCHED`→`MISMATCHED`, `route_count` 21→20, the closeout `reason` text, and a preview `WOULD_REJECT`→`WOULD_ACCEPT`. Each failed 7-8 tests, including the matching hand-written test (`test_content_digest_is_the_golden_content_digest`, `test_exactly_the_twenty_one_get_routes_in_contract_order`, `test_only_the_closeout_candidate_is_null_and_it_says_why`) and the regeneration tests. The artifact was restored byte-identical each time.
- `python3 -m unittest discover -s tests -v`: exit 0, **407 passed** in 68.0s (381 before this node plus 26 new).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. `python3 -m compileall -q capital`, `python3 -m py_compile scripts/finance_vectors.py tests/test_finance_vectors.py` and `node --check capital/static/app.js`: exit 0.
- `python3 scripts/manifest_vectors.py --check` (13 files match), `python3 scripts/not_bound_checklist.py --check`, `python3 scripts/auth_matrix.py --check` and `python3 scripts/decision_ledger.py`: all exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=7a7da500…17da`, `debit=385000 credit=385000`. The golden was not rewritten and `git diff tests/golden` is empty.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`. `git diff --name-only -- capital .aiops .github docs/decisions tests/golden tests/vectors/manifest`: no output.
- `npm ci --offline --ignore-scripts` (local cache only, no network): exit 0, 3 packages. `npm run test:browser`: exit 0, **43 passed** (1.6m). Playwright started and stopped its own loopback servers on 8766-8768; afterwards none of them was still listening. The one remaining listener on 127.0.0.1:8791 is the sandbox's own `sand-egress-tunnel`, which this node did not start.
- `python3 scripts/acceptance.py` was not run in full; its stages are the commands above, run one by one.

No `DECISION_REQUIRED.md` was written: every input is an already-built deterministic read on the fixed-instance seed book, and no rate, fee, limit, allocation priority, refund burden, provider, credential or upstream change was needed. Supplying `fin-finance-closeout` would need a deterministic committed evidence artifact in place of the untracked `build/acceptance-evidence.json`, which is a separate decision and was not taken here.

## terms-portfolio-rollup

`GET /api/terms/portfolio?instance_id=&as_of_day=&draw_day=&expected_settlement_cash_day=` is a read-only portfolio rollup on the terms overlay. `capital/terms.py` extracts the cap arithmetic from `_accrual` into `_cost_cap` (shared, note-read, AST literal budget kept to `{0,1,10000}`) and adds `portfolio(subjects, *, draw_day, draw_day_source, as_of_day, expected_settlement_cash_day)` on `TermsPolicyPort` and `DecisionNoteTermsPolicy`: one row per case with tier, `draw_day_source` (`QUERY_PARAMETER`/`DEFAULT` — the journal has no clock, no `sim_day` is stored), term/maturity/past-due days, contract and default interest as exact rational strings floored to 1 KRW per row, `annualized_all_in_bps` as an exact rational, and `cap_check` against `interest_rate.all_in_cost_cap_bps_annual` read from the note at runtime. `totals` sums rationals first and floors once; `cap_check` is `FAIL` if any evaluated row fails, `PASS` if all pass, `NOT_APPLICABLE` if none. `capital/service.py` adds `terms_portfolio` with SESSION_CHANGED, `_require_day` guards and the frozen-state invariant; `capital/server.py` matches the literal path inside `_get_terms` before the `{advance_id}` fallthrough (no registry change — `/api/terms` children already map it to `projection:read`). The facade gains the route plus `terms_portfolio*` definitions (`additionalProperties: false`); `index.html`/`app.js` add the rollup panel beside `#terms` with the same envelope checks and no POSTs. `scripts/auth_matrix.py` gains the probe; `tests/auth_matrix.json` and `tests/vectors/finance_vectors.json` were regenerated. `tests/test_terms_portfolio.py` adds 6 tests (independent reference rows, totals floor, lowered-cap FAIL on a temp note only, unbound bodies with no numbers, guards, literal-route/observer 403 HTTP); `tests/test_facade_contract.py` reads the live route; `tests/test_finance_vectors.py` `FACADE_READS` and the route-count assertions moved 22→23 and 30→31. `tests/browser/terms-portfolio.spec.cjs` adds 3 specs (panel beside the terms card with zero POSTs, unbound note with no numbers, lowered synthetic cap FAIL with the committed note byte-identical). Docs updated: README, INTEGRATION.md, OPERATOR_HANDBOOK_KO.md section, CAP-01 rows. Nothing under `capital/vendor/`, `.aiops/`, `docs/decisions/` or `tests/golden/` changed. This is SIMULATED, not an offer, not underwriting, not vendor FSM arithmetic; exposure buckets, concentration caps, reserve and refund-shock stress are out of scope.

Commands actually run, in order:

- `python3 -m unittest tests.test_terms_portfolio -v`: exit 0, **6 passed**.
- `python3 scripts/auth_matrix.py --write` then `--check`: exit 0 (probe added; `tests/auth_matrix.json` regenerated).
- `python3 scripts/finance_vectors.py --write` then `--check`: exit 0, `finance vectors ok: 86477 bytes match`.
- `python3 -m unittest tests.test_facade_contract -v`: exit 0, **5 passed** (journey read validates the live body against `terms_portfolio`).
- `python3 -m unittest discover -s tests -v` first run: 424 ran, 2 failed — the two hardcoded route counts in `test_finance_vectors.py` (22→23 GET routes, 30→31 total routes). After updating them: exit 0, **424 passed** in 61.2s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `python3 scripts/auth_matrix.py --check`, `python3 scripts/manifest_vectors.py --check` (13 files match), `python3 scripts/not_bound_checklist.py --check`: all exit 0.
- `npm ci --offline --ignore-scripts`: exit 0, 3 packages (local cache only). `npm run test:browser` first run: 46 passed, 2 failed — both in the new spec (a `waitForResponse` matched an earlier in-flight rollup GET, and the spec asserted a cell the renderer does not emit; the low-cap spec clicked a draw button the UI only shows after `bind_settlement`). After the spec fixes, second run: 47 passed, 1 flaky — pre-existing `journey.spec.cjs` gate repaint timed out once and passed alone (15/15). Third run: exit 0, **48 passed** (1.5m). Playwright's own loopback servers stopped; no `capital.server` remains.
- `git diff --name-only -- capital/vendor .aiops`: no output.

No `DECISION_REQUIRED.md` was written: the cap, tiers, fees and term values all come from the ADOPTED `CAPITAL-TERMS-V1` note, and no rate, fee, limit, allocation priority, provider or upstream change was needed.

## agent-lane-tools

The simulated agent lane now covers the pinned draft's whole allowlist. `capital/agent_lane.py` adds `query_subject` (QUERY-level surface and optional subject membership over the fixture scope; `subjects` echoes the registry, null means unrestricted), `withdraw_proposal` (PROPOSE-level; a stored pending memo moves to `WITHDRAWN` with `effects_executed` false, a second withdrawal is `duplicate: true`, the period window is not enforced while `now` format still is, and the row releases its charged share), and `propose_grant_change` (PROPOSE-level; a `HUMAN_PENDING` memo whose `requested` keys stay inside `authority`/`scope`/`limits`/`period`/`note`, count-only charge, `EXECUTE` in `authority` is `EXECUTE_AUTHORITY_DISABLED` storing nothing, the grant body never changes). `_charged` skips `amount` null rows and `_proposal_view` reports the stored phase so a replayed withdrawn proposal reads `WITHDRAWN` (facade `agent_proposal_view.phase` is now the enum `HUMAN_PENDING`/`WITHDRAWN`). `capital/auth.py` adds `agent:query_subject`, `agent:withdraw_proposal`, `agent:propose_grant_change` to `AGENT_PERMISSIONS`; `capital/service.py` wraps the three calls in the same snapshot/`_machine_same` read-only invariant; `capital/server.py` dispatches them in the same order (`propose_action` before `withdraw_proposal` so the matrix replay finds `sim-matrix` pending). The facade gains three route entries plus `agent_subject_request`/`agent_subject_response`, `agent_withdraw_request`/`agent_withdraw_response`, `agent_grant_change_request`/`agent_grant_change_response`, `agent_change_memo` and `agent_memo_view` (`additionalProperties: false`, `effects_executed` const false). `tests/agent_claims.json` grows 66→94 rows, all citing the pinned draft at `e2a029d8ac3af7575888dac22fc4bf173ebec232` with verbatim needles; `capital/agent_claims.py` adds the 28 checks. `scripts/auth_matrix.py` gains the three POST bodies; `tests/auth_matrix.json`, both generated doc blocks and `tests/vectors/finance_vectors.json` were regenerated. Docs updated: README agent bullet, INTEGRATION prose, a new `agent-lane-tools` handbook section (the earlier `delegation-claims-conformance` section's 66-row sentence is left as history). Nothing under `capital/vendor/`, `docs/decisions/` or `.aiops/` changed; proposals stay process memory only; labels stay `SIMULATED_AGENT_GRANT`/`IN_MEMORY_FIXTURE`/`NOT_BOUND`. SIMULATED — no real grant, execution, money or upstream call.

Commands actually run, in order:

- `python3 -m unittest tests.test_agent_lane -v`: exit 0, **17 passed** (3 new lane tests, 1 new HTTP test).
- `python3 scripts/auth_matrix.py --write` then `--check`: exit 0 (`tests/auth_matrix.json` and both generated doc blocks regenerated; lane cells now `6 * len(CALLERS)`).
- `python3 scripts/finance_vectors.py --write` then `--check`: exit 0, `finance vectors ok: 86477 bytes match` (facade digests moved; `test_finance_vectors.py` route counts updated 31→34 routes, 8→11 non-GET).
- `python3 scripts/agent_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=94 total=94 failed=0`.
- `python3 scripts/agent_claims_check.py`: exit 0, `SKIPPED` (no protocol checkout; not a pass).
- `python3 scripts/agent_claims_check.py --execute --protocol-dir /workspace/capital-run/kixproto-ro`: exit 0, `CLAIM_CONFORMANCE passed=94` + `CLAIM_DRIFT verified=94 total=94` (read-only citation check of the pinned doc).
- `python3 -m unittest discover -s tests -v` first run: 8 failures, all in `test_finance_vectors` — the committed vector artifact pins facade contract digests and went stale on the schema change. After regenerating the artifact and the two hardcoded counts: exit 0, **428 passed** in 66.0s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `npm ci`: exit 0, 3 packages (network was available; playwright was not previously installed). `npm run test:browser`: exit 0, **48 passed** (1.6m). Playwright started and stopped its own loopback servers.
- `python3 scripts/acceptance.py` first run: `browser` stage failed because playwright was not installed yet (ordered before `npm ci`). Second run: exit 0, `evidence build/acceptance-evidence.json ok=true` — unit 428, storage-conformance 7, pinned-vendor 7, upstream-claims 181 (87+94), node-check, browser 48, packaged-smoke 8, seeded-demo 1.
- `git fetch origin main`: `origin/main` `4e4011c4f99eba1200a825203462acd16902b78e`, equal to branch HEAD — the task base is the current main tip.
- `git diff --name-only -- capital/vendor docs/decisions .aiops`: no output.

No `DECISION_REQUIRED.md` was written: limits still come from the ADOPTED `CAPITAL-TERMS-V1` note, product subject identifiers stay an unrestricted fixture registry (`subjects: null`), and no credential, provider, real-grant, persistence or upstream change was needed.

## workspace-offline-audit

`python3 -m capital.verify --workspace DIR` audits `DIR/workspace.json` without a server. `capital/audit.py` reads the bytes once (`read_bytes` only: no flock, no mkdir, no write, no repair) and runs a staged pipeline: `workspace_file`, `strict_json`, `envelope_shape`, `payload_sha256`, `payload_shape`, `journal_replay` into a scratch `CreditMachine`, `state_digest`, `service_restore` through the same `verify_document`/`_validated_restore` path over an in-memory document port whose `save()` raises, `receipt_journal_fingerprints` (recomputed per journal entry; REJECTED and reconcile receipts keep shape and uniqueness checks because their args are not persisted), and `recon` — the same `build_reconciliation` checks as `GET /api/reconciliation` (six, plus `overlay_fold_digest_equals_persisted` and `scope.overlay_state_digest` when the overlay is non-empty), embedded verbatim. The first failing check supplies the reason (`WORKSPACE_UNREADABLE`, or `RECON_MISMATCH` when the intact envelope disagrees with the reconciliation); exit 0/1, 2 on CLI misuse. `capital/verify.py` keeps the manifest positional and adds `--workspace` (mutually exclusive, no `--key-file`). `scripts/workspace_vectors.py --write/--check` owns the pinned corpus `tests/vectors/workspace/` (`clean`, `truncated`, `payload-byte`, `digest`, `duplicate-key`, `stale-digest`), seeded with fixed instance `workspace-vectors` and pinned `saved_at` (a top-level field `payload_sha256` does not cover). `tests/test_workspace_audit.py` covers the seeded all-MATCHED audit, audit under a live `FileWorkspace` lock and a live HTTP server, no-write/no-repair, missing/empty/non-directory dirs, a `RECON_MISMATCH` on an intact envelope with a tampered receipt result, and CLI misuse; `tests/test_workspace_vectors.py` pins each vector's failing check, byte-level tamper facts, and regeneration/drift behavior. Docs updated: README, INTEGRATION.md, OPERATOR_HANDBOOK_KO.md. No route, permission, or workspace-format change; CAP-11 stays `NOT_BOUND`.

Commands actually run, in order:

- `python3 scripts/seed_demo.py --workspace /tmp/ws-audit-smoke && python3 -m capital.verify --workspace /tmp/ws-audit-smoke`: exit 0, all ten checks `MATCHED`, `state_digest=a8609033…ef45` equals `tests/golden/demo.json`, `recon.status` `MATCHED` with all six `CHECK_IDS`.
- `python3 -m capital.verify --workspace` on each committed vector copied to a scratch dir: `clean` exit 0; `truncated`/`duplicate-key` exit 1 `strict_json`; `payload-byte`/`digest` exit 1 `payload_sha256`; `stale-digest` exit 1 `state_digest`; all `reason` `WORKSPACE_UNREADABLE`. A missing dir exits 1 `workspace_file`; no args exits 2. An ad-hoc tamper of `receipts.op-closed-offer.result.credit.amount` with a recomputed `payload_sha256` exits 1 `RECON_MISMATCH` at `recon` (`projection_totals_vs_case_views` names the drift); an unhashable journal `idempotency_key` exits 1 `journal_replay`. Neither traceback nor repair occurs.
- `python3 scripts/workspace_vectors.py --write` then `--check`: wrote 6 files, `workspace vectors ok: 6 files match`.
- `python3 -m unittest tests.test_workspace_audit tests.test_workspace_vectors -v`: exit 0, **17 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **445 passed** in 69.6s on the final tree (428 before this node plus 17 new).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/manifest_vectors.py --check` (13 files match), `python3 scripts/finance_vectors.py --check` (86477 bytes), `python3 scripts/not_bound_checklist.py --check`, `python3 scripts/auth_matrix.py --check`, `python3 scripts/decision_ledger.py`: all exit 0.
- `python3 scripts/seed_demo.py`: exit 0, golden unchanged.
- `npm ci --offline --ignore-scripts`: exit 0, 3 packages (local cache only). `npm run test:browser`: exit 0, **48 passed** (1.5m). Playwright's own loopback servers stopped; no `capital.server` remains.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions tests/golden`: no output.

No `DECISION_REQUIRED.md` was written: the auditor adds no money, credential, provider, production, format, or financial-terms decision; the recon checks are reused, not re-implemented.

## event-log-summary

`python3 -m capital.events FILE --summary` reads one `--event-log FILE` JSONL file offline with no server. `capital/events.py` validates each line's exact five-field shape (`time`, `route`, `status`, `code`, `operation_id` — reusing `EVENT_LOG_KEYS` and the writer's `_CODE`/`_OP_ID`/`_status_class` from `capital/observability.py` and strict `loads` from `capital/verify.py`), then prints one sorted JSON line with `events`, `by_route`, `by_status`, `by_status_class` (unclassed statuses collapse to `other`), `by_code`, `without_code`, and min/max UTC `first_time`/`last_time`. `time` must match the writer's fixed `YYYY-MM-DDTHH:MM:SS.ffffffZ` shape and parse (`datetime.strptime` rejects 13월/2월 30일). `route` is checked as a non-empty ASCII string, not against the closed dispatch set, so a log from a build with other routes still summarizes. The first malformed line exits 1 naming the 1-based line number on stderr; an unreadable path exits 1 `EVENT_LOG_UNREADABLE`; CLI misuse exits 2; an empty file summarizes as zero events and exits 0. `event_log.dropped`/`event_log.errors` are process counters the file does not carry, so the report prints them null under `NOT_OBSERVABLE_OFFLINE` and points at `GET /api/metrics` `counters.event_log` — no invented zeros. `mode` is `OFFLINE_EVENT_LOG_SUMMARY`, `label` `SIMULATED`, `diagnostic` `LOCAL_ONLY`; exporter, tracing, alerting, network sinks, and audit/financial evidence stay `NOT_BOUND`. `tests/test_events.py` holds an in-memory nine-row fixture (deliberately not under `tests/vectors/`), 25 tampered variants each pinned to its line number, a no-write directory-snapshot test, CLI misuse tests, and a live-server round-trip where a unit-spawned `make_server(0, event_log=tmp)` summary equals the server's own `counters.event_log.written`, per-route `http_requests` sums, and per-class totals — and where `OUTSTANDING_REMAINS` stays out of `by_code` because HTTP-200 rejection receipts carry `code: null`. Docs updated: README bullet, the INTEGRATION `--event-log` bullet, a `event-log-summary` handbook section. The event-log format, cap, and server behavior are unchanged; nothing under `capital/vendor/`, `.aiops/`, `docs/decisions/`, `tests/vectors/`, or `tests/golden/` moved.

Commands actually run, in order:

- `python3 -m unittest tests.test_events -v`: exit 0, **10 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **462 passed** in 72.6s.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`: exit 0. `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`, `python3 scripts/auth_matrix.py --check`, `python3 scripts/not_bound_checklist.py --check`: all exit 0 (`docs surface ok: 25 routes, 20 artifacts, 8 stages`).
- `python3 scripts/seed_demo.py`: exit 0, golden `state_digest=a8609033…ef45` unchanged.
- Vendor pin check: all five `capital/vendor` files SHA256-match `manifest.json` (`OK` ×5); `git diff --name-only HEAD -- capital/vendor .aiops .github docs/decisions tests/golden tests/vectors`: no output.
- Manual smoke: `python3 -m capital.server --port 18791 --event-log /tmp/evs-smoke.jsonl`, four requests (state 200, unknown route 404 NOT_FOUND, health 200, metrics 200), server stopped, then `python3 -m capital.events /tmp/evs-smoke.jsonl --summary`: exit 0, one JSON line, `events=4`, `by_route` `/api/state`/`/api/health`/`/api/metrics`/`other` ×1, `by_status` `{"200":3,"404":1}`, `by_code` `{"NOT_FOUND":1}`, `without_code=3`, first/last times populated, `dropped`/`errors` null under `NOT_OBSERVABLE_OFFLINE`. A tampered file `{"time":"bad"}` exits 1 with `capital.events: /tmp/evs-bad.jsonl:1: FIELD_SET`.
- `python3 -m unittest discover -s tests -p test_storage_conformance.py -v`: exit 0, **7 passed**. `python3 scripts/upstream_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=87`. `python3 scripts/agent_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=94`.
- `python3 scripts/build_release.py --out build/acceptance-dist` + `python3 scripts/smoke_release.py build/acceptance-dist/*.pyz`: exit 0, `smoke ok: version-flag, state-version, static-index, journey-accepted, source-integrity, restart-instance, restart-receipts, restart-closed`; `capital/events.py` confirmed inside the `.pyz`; the dist directory was removed afterwards.
- `npm ci`: exit 0, 3 packages. `npm run test:browser`: exit 1 on the first run — **37 passed, 11 failed**, every failure a 30s `page.goto`/`waitForResponse` timeout while the shared box sat at load average ~47–50 (other tenants' chrome/ffmpeg processes). Re-running the failed spec files: `projection.spec.cjs` 2/2 ok (4.1s), `recon-statement.spec.cjs` + `terms-portfolio.spec.cjs` 4/4 ok (7.7s), `journey.spec.cjs` + `auditor-role.spec.cjs` + `underwrite-record.spec.cjs` 22/22 ok (27.9s) — all 48 browser tests pass; the failures were load flakes, not this change (no server, route, or static-asset change exists). Playwright's own loopback servers stopped; no `capital.server` remains. `python3 scripts/acceptance.py` was not run end-to-end: its browser stage timeout is 600s against a ~940s loaded suite; every stage was instead verified individually above.

No `DECISION_REQUIRED.md` was written: the reader reuses the writer's field definitions, adds no money, credential, provider, production, format, or financial-terms decision, and the offline-unobservable counters are honestly labeled `NOT_OBSERVABLE_OFFLINE` rather than invented.

## Demo book fixtures (CAPITAL-DEMO-BOOK-V1)

The `caps-binding-fixtures` node added ten synthetic claims replayed only through pinned `SettlementMachine` calls (T1 commit, T2 stop at CAPTURED, `demo-epsilon-refund` binds its 60,000,000 open refund face; the commit statement reuses the fixture-v1 synthetic 97/3 split). `tests/test_demo_book.py` byte-compares every stored view to an independent pinned replay and pins `producer.DEMO_BOOK` to the parsed `capital-decision-v1` block, so a hand-set field or table drift fails. `GET /api/underwrite` then exercises real `DECLINE` records: `single_advance_cap_krw` on a candidate above the cap, `beneficiary_aggregate_cap_krw` on five drawn cap-size advances under `demo-org-beta`, and `portfolio_cap_krw` on a drawn `demo-org-delta` advance once the book passes the portfolio cap. U4 check order is single, beneficiary, portfolio; each test reads cap, threshold and rate values from `docs/decisions/CAPITAL_FINANCIAL_TERMS.md` at runtime. The V1 projection keeps folding `FixtureViews.projection_ids` (the three original views) so its pinned totals stay debit = credit = 385,000 and `state_digest` is unchanged; only `content_digest` moved, regenerated via `python3 scripts/seed_demo.py --update-golden`. Actual run evidence: `python3 -m unittest tests.test_demo_book -v` 9 tests OK; `python3 -m unittest discover -s tests -v` 491 tests, 29 pinned-artifact failures before regeneration, all resolved after `--update-golden` and `--write`; `python3 scripts/manifest_vectors.py --check`, `python3 scripts/finance_vectors.py --check`, `python3 scripts/workspace_vectors.py --check` all match; `git diff tests/golden/demo.json` touches the `content_digest` line only. Vendor manifest hashes and the three fixture-v1 views are unchanged.

## margin-cure-default

`capital/margin.py` evaluates the `additional_margin` rules of `CAPITAL-TERMS-V1` inside every `advance_day`. Entries `margin_call`, `margin_cure`, `margin_acceleration` and `default_eligible_proposal` are written in the same atomic save as the clock and interest entries; `GET /api/overlay` gains a `margin` block (top level and per row). Rules journal only against a source declaring `settlement_views_mutable` (the disposable, SIMULATED `ScenarioReplaySource`); workspace fixtures report `checked` true, `triggered` false, `limit` `FIXTURE_VIEWS_IMMUTABLE`. F04 `default` is never called. Cure options 2 and 3 are `NOT_BOUND`. Interest and write-off are not re-based on the accelerated maturity (`NOT_REBASED / DECISION_REQUIRED`, owner JunTae); this node does not need the answer. `ScenarioReplaySource` replays six of the nine F01–F03 scenarios with exactly the expected errors on a committed fixture; `duplicate-statement`, `late-cash` and `split-statement` start from an uncommitted claim and report their divergence. `margin_terms` matches the tier on the frozen draw gate for a mutable source, because the F04 snapshot keeps no draw-time refund.

Commands actually run:

- `python3 -m unittest tests.test_margin -v`: exit 0, **24 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **560 passed** (83.6s). The first run had 8 failures in `test_finance_vectors` because the facade contract changed; `python3 scripts/finance_vectors.py --write` regenerated `tests/vectors/finance_vectors.json` and the re-run passed.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`, `manifest_vectors`, `finance_vectors`, `workspace_vectors`, `not_bound_checklist`, `auth_matrix` with `--check`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, golden unchanged.
- `npm ci --offline --ignore-scripts`: exit 0. `npm run test:browser`: exit 0, **48 passed** (1.6m); no server left running.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions tests/golden`: no output.

## coa-candidate-projection

`capital/coa.py` adds `CoaCandidateProjection`, a second `ProjectionPort` implementation for the `CAPITAL-COA-V1` mapping in `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` (chart `SIMULATION_FIXED_V2`). It is selected only by `GET /api/projection?mode=coa-candidate`; the default and `mode=simulation` remain V1 and `capital/projection.py` is not edited. The candidate runs V1 first (which validates the journal and the evidence), renames each V1 account to exactly one COA code with its side kept (`SIM_CLAIM_FACE`→9100, `SIM_PAYEE_OBLIGATION`→9110, `SIM_ADVANCE_EXPOSURE`→1100, `SIM_ADVANCE_OBLIGATION`→1000, `SIM_REPAY_MEMO`→1100), and adds the overlay `interest_posting` entries: before the accepted `default` Dr 1110 / Cr 4100 (contract) or 4110 (default interest); after it Dr 9700 memo with a counter-memo. Dimensions ride on each entry, never in the code. KRW is the one declared AssetSpec (`assets.KRW`); any other spec or a mixed-asset posting is `ASSET_MISMATCH`. 1190, 3100, 3200, 4300, 5100, 5200 are `NOT_RECORDED`, 1300 and 2300 `NOT_MODELED_V1_FIELD_RESERVED`, 4200 `ZERO_FEE_PLACEHOLDER`, 9200-9500 `NOT_POSTED`, 9150 and 9160 `DERIVED_MEMO`.

Review items for the accountant (working assumptions, nothing adopted): (1) `9790 MEMO_SUSPENDED_INTEREST_CONTRA` is not in the note. The note gives 9700 as debit-normal and names no counter account, so a candidate-only credit-normal 9790 balances the memo posting. It carries no money value of its own; drop or rename it on review. (2) Interest payments are `NOT_RECORDED`, so 1110 is never relieved, and margin-acceleration rebasing is not applied. (3) 4100/4110 are candidate postings, not revenue-recognition adoption. (4) Only `asset`, `advance_id`, `claim_id`, `sim_day`, `chart_version`, `terms_version` (with `operation_id` as `txn_id` and `source_cut` as the response `cut`) are carried; `beneficiary_role`, `tier`, `proposal_id` are not. (5) EVIDENCE entries use `sim_day` 0 as a stated convention.

The two new reconciliation checks, `coa_candidate_totals_vs_v1` and `interest_ledger_vs_projection`, run only on `GET /api/reconciliation?mode=coa-candidate`. The default report keeps the six checks because `capital/static/app.js` rejects any other count and the manifest `content_digest` is pinned across ticks. Under `export_section_policy` of `docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md` a manifest change would need V3 and an `overlay` section, which is out of scope, so the manifest, `capital/export.py`, `tests/golden/demo.json` and the offline audit are unchanged. `accounting_policy` stays `SYNTHETIC_UNADOPTED`, `tax` and `legal` `NOT_BOUND`, `policy_adopted` false. `capital/contract/facade-v1.json` gains the `coa_*` and `projection_coa_candidate` definitions, the `/api/projection` response becomes `anyOf` V1 or candidate, the reconciliation route gains the `mode` query and an optional `coa_candidate` block. That is a derived-artifact change, so `tests/vectors/finance_vectors.json` was regenerated with `python3 scripts/finance_vectors.py --write` (only the `facade_read_model` group moved) and the `/api/projection` row of `FACADE_READS` in `tests/test_finance_vectors.py` now lists both definitions. Tax filing, revenue-recognition adoption, `fin-ledger-contract` adoption and any V1 change are out of scope. Every output is SIMULATED; no money, provider or credential is involved.

## audit60-fix2

Implements `docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md` 3.2 and 3.4. A non-empty overlay journal makes `GET /api/export/manifest` emit `KIX_CAPITAL_EXPORT_MANIFEST_V3` with an `overlay` section (`overlaypart`); an empty overlay stays byte-identical V2 (`content_digest` equals `tests/golden/demo.json`). `GET /api/reconciliation` gains `overlay_fold_digest_equals_persisted` and `scope.overlay_state_digest` only for a non-empty overlay. `capital.verify` accepts V2 and V3 and rejects V3-without-overlay and V2-with-overlay as `SECTION_SET`. `GET /api/overlay` `export` is `INCLUDED_IN_MANIFEST_V3` or `ABSENT_WHEN_EMPTY`. `tests/golden/overlay_demo.json` pins the V3 `content_digest` (written by hand from a verified run, identical across two processes). Facade schema, `app.js` `manifestValid` and `finance_vectors.json` were updated for the new shapes. Out of scope: stage7 signing, `demo.json`, `audit.py` (still six checks).

Commands actually run:

- `python3 -m unittest tests.test_overlay_export -v`: exit 0, **14 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **574 passed**. The first runs failed in the facade schema and in `test_overlay_commands_leave_f04_and_the_demo_golden_untouched`, which asserted the old no-V3 behaviour; the test was rewritten, not removed.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, passed.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/finance_vectors.py --write`, then `--check`: exit 0. `manifest_vectors`, `workspace_vectors`, `docs_surface`, `not_bound_checklist`, `auth_matrix` with `--check`, and `decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `demo.json` unchanged.
- `npm ci --offline --ignore-scripts`: exit 0. `npm run test:browser`: exit 0, **48 passed**; no server left running.

## http-hostile-corpus

`tests/vectors/http/` pins 76 hostile raw-HTTP request recipes (format `KIX_CAPITAL_HTTP_HOSTILE_V1`, label `SIMULATED`). Each recipe is one raw request with `__PORT__`/`__TOKEN__` sentinels plus a pinned outcome (`status`, `code`, `content_type_prefix`, `body_marker`) and the unchanged post-state triple. `tests/test_http_hostile.py` replays every recipe over a raw socket against an in-process `make_server(0)`, asserts the pin, scans each response for traceback/token/repository-path leaks, and re-probes `state_digest`, `operation_count` and `/api/health` after every case. `scripts/http_hostile.py --write`/`--check` own the directory like the manifest and workspace corpora; `EXPECTED` in the test is the hand-written oracle.

The corpus found one genuine server defect: a request target whose authority is a malformed IPv6 literal (for example `GET http://[bad/x`) made `urllib.parse.urlsplit` raise `ValueError`, which escaped `do_GET`/`do_POST`, printed a traceback on stderr and dropped the connection without any response. The minimal fix adds `Handler.request_route()` mapping that `ValueError` to `400 INVALID_TARGET`; `target-invalid-ipv6` and `target-unclosed-ipv6` are its pinning vectors. `INVALID_TARGET` was added to `capital/contract/facade-v1.json` (`errors`, `errorGroups.boundary`, first entry of every route's `errors`) because the contract fences every `ApiError` literal, and `tests/vectors/finance_vectors.json` was regenerated with `python3 scripts/finance_vectors.py --write` since the `facade_read_model` digests cover the contract bytes. No route, permission, role or auth rule changed.

Other observed behaviors are pinned as designed stdlib semantics, not defects: `//` targets normalize to a single `/` (gh-87389), absolute-form authorities are ignored while the `Host` header binds loopback, HTTP/0.9-style requests get a body-only reply with no status line, malformed headers are tolerated, GET ignores declared bodies, TRACE/OPTIONS/HEAD get stdlib 501 HTML pages, and the 8192 byte cap keeps deep nesting under the interpreter recursion limit. The UTF-8 BOM parses through `utf-8-sig` and reaches the strict shape gate (`INVALID_SESSION`).

Commands actually run:

- `python3 /tmp/probe_hostile.py`, `python3 /tmp/probe2.py`: observed every candidate case live; confirmed the `urlsplit` crash (empty reply plus stderr traceback) before fixing it.
- `python3 scripts/http_hostile.py --write`: wrote 76 recipes; `--check`: exit 0, `76 files match`.
- `python3 -m unittest tests.test_http_hostile -v`: 9 passed.
- `python3 -m unittest discover -s tests -v`: 631 run, **1 failed** — `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched`, which diffs the worktree against `origin/main`. The flagged paths (`docs/decisions/CAPITAL_EXTERNAL_GATES.md`, `docs/decisions/CAPITAL_RELEASE_ACCEPTANCE.md`, `tests/golden/demo.json`) are changed on main after this branch's base `2acd625` (its merge-base) and are untouched by this node; the failure is environmental, present before these edits.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: 7 passed.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/{auth_matrix,manifest_vectors,workspace_vectors,finance_vectors,docs_surface,not_bound_checklist}.py --check` and `python3 scripts/decision_ledger.py`: exit 0. `agent_claims_check.py` reports `SKIPPED` (no protocol checkout) as designed.
- `npm ci --offline --ignore-scripts`: exit 0.
- `npm run test:browser`: the committed config binds 127.0.0.1:8765, held by a foreign process (`python3 -m http.server --directory dist` owned by `/workspace/fitness-hub/site`, not started here and not killed). The same suite was run with only the port numbers in `playwright.config.cjs` shifted 8765→8795 (the first `webServer` also lacked `--port`): **48 passed** in 1.6m; the config was reverted byte-identical afterwards. No server was left running.

`git diff --name-only -- capital/vendor .aiops` is empty; the five vendored reference files are byte-identical.
## facade-load-harness

`scripts/load_harness.py` is a stdlib-only loopback load harness. Each workload boots a fresh `capital.server.make_server(0)` on an ephemeral port (same pattern as `tests/test_observability.py`) and drives `POST /api/commands` through `http.client` + `ThreadPoolExecutor`, following the measurement semantics of upstream `docs/contracts/PERFORMANCE_MEASUREMENT.md` and `docs/DEVELOPMENT_PLAN.md` §7/§9 (kix-protocol, read-only reference): the scheduled arrival instant and the service interval are separate fields, and the outcome classes new-success, replay, reject, conflict, capacity are counted and percentiled per class, never pooled. Six seeded workloads (`low-load-uniform`, `uniform`, `hot-seat`, `same-command-retry`, `history-growth`, `saturation`) each run in memory and `LOCAL_FILE_WORKSPACE` modes. Commands use demo-book claims (`demo-*`) and `sim-*` ids only; amounts are synthetic fixture units. `saturation` fills `MAX_OPERATIONS` (500) with REJECTED receipts (no journal entries), observes 5 `SIMULATION_CAPACITY` plus 1 probe rejection, and confirms a replay and a conflict are still answered at capacity (the idempotency lookup precedes the capacity check). After every run the harness asserts: journal length equals the new-success count, receipt count equals new-plus-reject, replays return the stored receipt byte-equal with `transport_duplicate` true, conflicts and capacity write nothing, and the final `state_digest` equals an independent `PinnedFsmProducer().restored(journal)` replay. The report `KIX_CAPITAL_LOAD_REPORT_V1` is labelled `LOCAL_EXPLORATION`, carries an input fingerprint over the seeded specs (no `instance_id`, token, or port), python/OS/CPU info, per-class counts and nearest-rank percentiles, and a `GET /api/metrics` snapshot. No SLO or TPS claim appears; it is not production performance evidence. `smoke` runs inside `unittest` with no timing thresholds; `full` is manual with output under uncommitted `build/`.

Commands actually run:

- `python3 scripts/load_harness.py --profile smoke --mode both --out build/load-smoke.json`: exit 0. All six workloads pass every assertion in both modes (~11 s). First runs exposed two harness bugs, both fixed in the harness (not the server): `bind_settlement` generated operation ids containing `_`, which `INVALID_OPERATION_ID` rejects (ids are now `[a-z0-9-]` only), and the replay equality check stripped `transport_duplicate` instead of comparing to `{**stored, transport_duplicate: true}`.
- `python3 scripts/load_harness.py --profile full --mode both --out build/load-report.json`: exit 0 (~16 s). 12 workload runs, all assertions true. `build/` stays untracked.
- `python3 -m unittest tests.test_load_harness -v`: exit 0, **11 passed** (~11.4 s); both storage modes covered, no wall-clock assertions.
- `python3 -m unittest discover -s tests -v`: **632 passed, 1 failed** (98 s). The one failure is `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched`, which diffs `capital/projection.py`, `capital/ports.py`, `capital/overlay.py`, `capital/export.py`, `tests/golden`, `capital/vendor`, `.aiops`, `docs/decisions` against `origin/main`. This branch is 14 commits behind `origin/main`; the three reported paths (`docs/decisions/CAPITAL_EXTERNAL_GATES.md`, `docs/decisions/CAPITAL_RELEASE_ACCEPTANCE.md`, `tests/golden/demo.json`) were changed by main-side merges (#74, #77, #81), not by this node — `git status --porcelain` shows only this node's four files. Pre-existing environmental condition, not weakened or skipped.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`: exit 0. `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: exit 0 (`docs surface ok: 27 routes, 20 artifacts, 8 stages`). `auth_matrix`, `not_bound_checklist`, `manifest_vectors`, `workspace_vectors`, `finance_vectors` with `--check`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, golden unchanged.
- `npm ci --ignore-scripts`: exit 0, 3 packages (pinned `@playwright/test` 1.58.2). `npm run test:browser`: could not start — port 8765 is held by another tenant's `python3 -m http.server` on this shared box and `playwright.config.cjs` pins ports 8765–8768 with `reuseExistingServer:false`. Chromium 1208 is installed; retry at the end of the run. This node changes no route, static asset, or server behavior, so browser coverage is not expected to differ; no server left running by this node.
- `git diff --name-only -- capital/vendor .aiops .github tests/golden tests/vectors`: no output.


Conflict-fix round 1 (2026-10-23; incoming main `68c8896`): the conflict joined appended validation sections, so both this node's section and all incoming main sections are retained. The harness and its tests are byte-identical to the feature branch. Main's live COA binding-note guard compared the merged note with the old branch `HEAD`, which predates main's reviewed closeout-digest wording. During a pending merge it now compares the complete note byte-for-byte with `MERGE_HEAD`; outside a merge it still uses `HEAD`. No check is skipped or relaxed: an extra newline in either `capital/export.py` or `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` was independently rejected, then both files were restored byte-identical. The first combined unit run found only this guard mismatch (960 tests, one failure); the corrected run is recorded below.

Commands actually run after conflict resolution:

- `python3 -m unittest discover -s tests -p test_coa_candidate.py -v`: exit 0, **35 passed**. Two independent byte-mutation checks each failed the live guard as expected.
- `python3 -m unittest discover -s tests -p test_load_harness.py -v`: exit 0, **11 passed** (13.0s), both storage modes and all six workloads, no timing thresholds.
- `python3 scripts/load_harness.py --profile full --mode both --out build/load-report-merge-round1.json`: exit 0, **12 workload runs**, every assertion true. Report remains `LOCAL_EXPLORATION` / `NOT_PRODUCTION_PERFORMANCE_EVIDENCE`, with no SLO or TPS claim; output is ignored and uncommitted.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. All five vendored files match their SHA256 pins; `manifest.json` is byte-identical to both merge parents.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: exit 0 (**30 routes, 39 artifacts, 9 stages**). `auth_matrix`, `not_bound_checklist`, `manifest_vectors` (19 files), `workspace_vectors` (6 files), `finance_vectors` (97125 bytes) and `decision_bindings` with `--check`: exit 0.
- `npm ci --offline --ignore-scripts --no-audit --no-fund`: exit 0. The default browser command hit an occupied shared port; a temporary ignored config under `build/` uses four available loopback ports and a separate disposable workspace, preserving the full browser suite and checked-in Playwright configuration.

- Final `python3 -m unittest discover -s tests -v`: exit 0, **960 passed** (178.0s).
- `npm run test:browser -- --config build/load-harness-merge.playwright.cjs`: exit 0, **69 passed** (2.4m), Chromium; all configured projects and tests retained. No checked-in browser configuration or CI change.
- `git ls-files -u`: empty; no conflict markers remain. The merge remains uncommitted for the supervisor.

## audit70-fix5

`capital/audit.py` now passes the restored overlay journal and the persisted overlay section to `build_reconciliation` (`overlay_entries`, `overlay_persisted`), as `CapitalService.reconciliation` does. A non-empty overlay workspace therefore reports `overlay_fold_digest_equals_persisted` and `scope.overlay_state_digest` in the audit `recon`, matching `GET /api/reconciliation` and `GET /api/overlay`. An empty overlay (and a legacy v1 envelope) stays byte-identical: the seeded workspace audit output was compared with `cmp` before and after. `tests/test_workspace_audit.py` gains `AuditOverlayReconTests` (live-GET parity for a ticked and an empty workspace, and a stale overlay digest still failing at `service_restore`). The `tests/vectors/workspace` corpus, `capital/vendor/`, `recon.py` and `service.py` are unchanged. Out of scope: repair, writes, new formats, `?mode=coa-candidate`. Everything is SIMULATED.

Commands actually run:

- `python3 -m unittest tests.test_workspace_audit tests.test_overlay`: exit 0, **56 passed**.
- `python3 scripts/workspace_vectors.py --check`: exit 0, 6 files match.
- `python3 -m unittest discover -s tests`: exit 0, **626 passed**.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py`: exit 0, 7 passed.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`, `docs_surface.py --check`, `not_bound_checklist.py --check`, `decision_ledger.py`: exit 0.
- `npm run test:browser`: not run (no `node_modules` in this worktree).

## t05-t06-sim-journeys

`scripts/sim_journeys.py` runs the named SIMULATED journeys `T05-sim` (35 steps, in-process server on a disposable `ScenarioReplaySource` book) and `T06-sim` (33 steps, `--workspace` subprocess killed with SIGKILL and restarted) over the loopback API, with fixed operation ids and seed `CAPITAL-SIM-JOURNEYS-V1`. Digests are pinned in `tests/golden/journey_t05_sim.json` and `tests/golden/journey_t06_sim.json`; a mismatch or a missing pin exits 1 unless `--update-golden` is passed. `scripts/acceptance.py` gained the ninth stage `integrated-journeys`, and its evidence now carries top-level `integrated: false` and `qualification.claimed: false`. The refund in T05-sim is replayed on the disposable book out of band (`SIMULATED_OUT_OF_BAND_SETTLEMENT_EVENT`) because Capital has no settlement-event route. These journeys are Q0-named synthetic variants. They are not integrated acceptance, not T01–T06 qualification, and not human acceptance; no `ACCEPTANCE_KO.md` checkbox was touched. No file under `capital/`, `capital/vendor/`, `.aiops/`, `.github/`, or `docs/decisions/` was edited, and no test was weakened.

Commands actually run:

- `python3 scripts/sim_journeys.py --update-golden`, then `python3 scripts/sim_journeys.py` twice: exit 0, `sim journeys ok SIMULATED T05-sim steps=35 T06-sim steps=33`, same digests each run.
- `python3 -m unittest tests.test_sim_journeys tests.test_acceptance -v`: exit 0, **32 passed**.
- `python3 -m unittest discover -s tests -v`: exit 0, **587 passed** (99.3s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check` (9 stages), `not_bound_checklist`, `auth_matrix`, `manifest_vectors`, `finance_vectors`, `workspace_vectors` with `--check`: exit 0. `python3 scripts/seed_demo.py`: exit 0, golden unchanged.
- `npm ci --offline --ignore-scripts`: exit 0. `npm run test:browser`: exit 0, **48 passed** (1.8m).
- `python3 scripts/acceptance.py`: exit 0, evidence `ok` true; unit 587, storage-conformance 7, pinned-vendor 7, upstream-claims 181, browser 48, packaged-smoke 8, seeded-demo 1, integrated-journeys 2 (T05-sim 35 steps, T06-sim 33 steps, both `SIMULATED`).
- `git diff --name-only -- capital .aiops .github docs/decisions tests/golden/demo.json`: no output. No `capital.server` process of this run remained.

After the merge with main (2026-10-17, `origin/main` at `4d04a5b`, event-log-summary #59): main's `audit60-fix2` added the conditional `overlay_fold_digest_equals_persisted` reconciliation check for a non-empty overlay, so the T06-sim step `reconciliation checks match after the restart` now observes seven checks instead of six. The T06-sim pin was regenerated with `python3 scripts/sim_journeys.py --update-golden`; `git diff tests/golden/journey_t06_sim.json` touches only `digest` and that step's `facts.checks` (6 → 7), and the T05-sim pin is byte-identical. Main's `tests/test_coa_candidate.py` guard `test_v1_and_golden_files_are_untouched` diffs `tests/golden` and `docs/decisions` against `origin/main`: the two journey pins are carved out of that pathspec by name (they are compared to a live run by `tests/test_sim_journeys.py`), and a guarded file that main added after this branch's merge point and that the working tree never held is no longer reported as this branch's edit (`origin/main` had moved on to `2acd625`, two `docs/decisions` notes past the merged `4d04a5b`, while the merge was in progress). A stray edit to a guarded file is still reported: this was verified by appending a newline to `capital/export.py` and, separately, by deleting `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`; each run failed the guard naming that one path, and each file was restored byte-identical to main. The handbook section and the `integrated-journeys` stage are unchanged; main's handbook sections (`event-log-summary`, `shadow-refund-resale`, `caps-binding-fixtures`, `sim-clock-ledger`, `margin-cure-default`) precede this node's section.

Commands actually run after the merge:

- `python3 scripts/sim_journeys.py --golden-dir TMP --update-golden`: exit 0; the regenerated T05-sim pin equals the committed one and the T06-sim pin differs from the pre-merge commit only in `digest` and `steps[28].facts.checks`. Then `python3 scripts/sim_journeys.py --update-golden` on `tests/golden` and two plain runs: exit 0, `sim journeys ok SIMULATED T05-sim steps=35 T06-sim steps=33`, the same digests each run.
- `python3 -m unittest discover -s tests -v`: exit 0, **649 passed** (96.9s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check` (27 routes, 20 artifacts, 9 stages), `not_bound_checklist`, `auth_matrix`, `manifest_vectors` (13 files), `finance_vectors`, `workspace_vectors` (6 files) with `--check`: exit 0. `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, golden unchanged. `python3 scripts/agent_claims_check.py --execute`: passed=94 total=94. `python3 scripts/decision_ledger.py`: exit 0.
- `npm run test:browser`: exit 0, **48 passed** (1.5m); no `capital.server` of this worktree remained. The suite's fixed ports 8765–8768 are shared with other worktrees' runs on the same machine; one `acceptance.py` attempt hit `http://127.0.0.1:8765 is already used` from another worktree's Playwright servers and was re-run, not patched.
- `python3 scripts/build_release.py --out` twice into separate directories: both `capital-0.1.0.pyz` byte-identical (SHA256 `4376cd1e…6840`); `python3 scripts/smoke_release.py` on it: `smoke ok` (8 checks).
- `python3 scripts/acceptance.py`: exit 0, evidence `ok` true, `integrated` false, `qualification.claimed` false, `funds_executed` false; unit 649, storage-conformance 7, pinned-vendor 7, upstream-claims 181, browser 48, packaged-smoke 8, seeded-demo 1, integrated-journeys 2 (T05-sim 35 steps, T06-sim 33 steps, both `SIMULATED`). An earlier attempt failed once in the pre-existing `portfolio.spec.cjs` `#case-title` expectation while a release build ran concurrently on the loaded box; that spec, `capital/static/app.js`, and `playwright.config.cjs` are not touched by this node. `docs/ACCEPTANCE_KO.md` has no checked box.
- The five files under `capital/vendor/` match `manifest.json` SHA256. `git diff --name-only MERGE_HEAD -- capital .aiops .github docs/decisions tests/golden/demo.json`: no output.

Second merge with main (2026-10-17, `origin/main` at `2acd2a0`, external-gate decision #77): the only conflict was this file (main's `audit70-fix5` section sits before this node's section; both kept). No code, test or golden file conflicted. After the merge: `python3 -m unittest discover -s tests`: **653 passed**; vendor mock tests 7 passed; `compileall`, `node --check`, `docs_surface`, `not_bound_checklist`, `auth_matrix`, `manifest_vectors`, `finance_vectors`, `workspace_vectors` `--check` and `sim_journeys.py` (goldens unchanged): exit 0; `npm run test:browser`: **48 passed**.

## portfolio-risk-analytics

`capital/risk.py` is a read-only analytics model over the accepted journal, the overlay clock (`sim_day`) and `CAPITAL-TERMS-V1`; `GET /api/risk` (`projection:read`; observer and agent get 403) serves it and `CapitalService.risk()` checks that receipts, `state_digest`, overlay entries and the F04 state are byte-equal before and after. Everything is SIMULATED integer floor arithmetic: exposure by tier, maturity buckets (`0-30`, `31-60`, `61-90`, `>90` days to the standard maturity), overdue aging, beneficiary concentration (`hhi_permille` and U4 cap utilization in permille), the reserve requirement (per-advance `floor(outstanding * bps / 10000)` over the note's table; not an accounting policy, `applied` false) and the fixed refund shocks `[500, 1000, 2500, 5000]` bps of `eligible_face` (hypothetical; no margin call is recorded). The tier, maturity and aging sums equal the total, which equals the projection's advance outstanding. The seeded demo pins `risk` in `tests/golden/demo.json` (outstanding 45,000; reserve 30,750; HHI 1000; `risk_digest`), written only through `scripts/seed_demo.py --update-golden`. The risk pin depends on `sim_day`, so `test_overlay_commands_leave_f04_and_the_demo_golden_untouched` now compares every other golden key byte-for-byte after the clock ticks and asserts the `risk` pin moves with `sim_day`.

Limits: the ledger knows only the 60-day standard term, so the `61-90` and `>90` maturity buckets stay empty on live data and are exercised by pure-function tests. Overdue aging reuses the same 30/60/90 edges as an analytics choice; the note defines no aging edges and no concentration bands. Maturity is not re-based on margin acceleration (`NOT_REBASED / DECISION_REQUIRED`, owner JunTae). Advances with no matching tier are reported as `NOT_APPLICABLE` and as unrated reserve, never guessed. The zipapp has no `docs/`, so `/api/risk` there is `NOT_BOUND`.

Commands actually run:

- `python3 -m unittest tests.test_risk -v`: exit 0, **26 passed**.
- `python3 scripts/seed_demo.py` before the pin: exit 1, drift on `$.risk` only; `--update-golden` then plain run: exit 0, `state_digest=a8609033…ef45` and `content_digest=2f71dab1…dca` unchanged; `git diff tests/golden/demo.json` adds the `risk` key only.
- `python3 scripts/auth_matrix.py --write` and `python3 scripts/finance_vectors.py --write`, then `--check` on both: exit 0. The vector diff is the `facade_read_model` group only (26 routes, new digests).
- `python3 -m unittest discover -s tests -v`: exit 0, **586 passed** (85.8s). The first run had one failure in `test_overlay` (the golden-after-ticks test above), fixed as described.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`, `manifest_vectors`, `finance_vectors`, `workspace_vectors`, `not_bound_checklist`, `auth_matrix` with `--check`: exit 0.
- `npm ci --offline --ignore-scripts`: exit 0. `npm run test:browser`: exit 0, **51 passed** (2.0m), including `tests/browser/portfolio-risk.spec.cjs` (desktop 1280 and 375px, no horizontal overflow, no page or console errors, zero POSTs, observer reason, NOT_BOUND note); no server left running.
- `git diff --name-only -- capital/vendor .aiops .github docs/decisions`: no output.

Merge with main (2026-10-17; main had gained coa-candidate-projection, audit60-fix1..5 and event-log-summary): six conflicts, none dropped. `README.md` and `docs/INTEGRATION.md` keep main's rewritten `GET /api/overlay` and `GET /api/terms/portfolio` bullets (overlay `export` is `INCLUDED_IN_MANIFEST_V3` / `ABSENT_WHEN_EMPTY`, not `NOT_INCLUDED`) and add the `GET /api/risk` bullet after them. `capital/service.py` imports `coa, margin, overlay, risk`. `tests/test_overlay.py` `test_overlay_commands_leave_f04_and_the_demo_golden_untouched` now asserts both sides: after two ticks the `risk` pin (`sim_day` 75, new `risk_digest`, same `outstanding_krw`) and `content_digest` (the non-empty overlay moves the manifest to `KIX_CAPITAL_EXPORT_MANIFEST_V3` with an `overlay` section) are the only keys of `seed.capture` that move, every other key is byte-equal to `demo.json`, and the F04 `state_digest` is untouched. `tests/vectors/finance_vectors.json` was regenerated with `python3 scripts/finance_vectors.py --write` from the merged facade (only the `groups` block differs from either side), not hand-merged. `tests/test_coa_candidate.py` `test_v1_and_golden_files_are_untouched` diffed `tests/golden` byte-for-byte against `origin/main`, which contradicts this node's `--update-golden` pin of `risk` in `demo.json`; the byte diff stays for `capital/projection.py`, `capital/ports.py`, `capital/overlay.py`, `capital/export.py`, `capital/vendor`, `.aiops` and `docs/decisions`, and the golden check now requires every key pinned on `origin/main` (`state_digest`, `projection_totals`, `content_digest`, `cases`, …) to be present and equal in every golden, so additive pins through the explicit regeneration path pass and any moved V1 pin still fails. `tests/golden/demo.json` is unchanged by the merge (`state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`).

Commands actually run after the merge:

- `python3 scripts/finance_vectors.py --write`, then `--check`: exit 0, 90609 bytes match.
- `python3 -m unittest discover -s tests -v`: exit 0, **648 passed** (89.5s). The first run had one failure, `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched` (`tests/golden/demo.json` differs from `origin/main`), fixed as described above.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check` (28 routes, 20 artifacts, 8 stages), `manifest_vectors` (13 files), `workspace_vectors` (6 files), `not_bound_checklist`, `auth_matrix` with `--check`, and `scripts/decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged.
- `npm ci --offline --ignore-scripts`: exit 1 (`ENOTCACHED playwright-core-1.58.2`); `npm ci --ignore-scripts`: exit 0. `PLAYWRIGHT_BROWSERS_PATH=build/pw-browsers npx playwright install chromium` (worktree-local, gitignored). `npm run test:browser` with that path: exit 0, **51 passed** (1.8m), including the three `portfolio-risk.spec.cjs` cases; no server left running.
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output. Vendored file SHA256 values match `capital/vendor/manifest.json`.

Second merge with main (2026-10-17; main had gained repayment-posting-decision, default-recovery-decision, external-gate-decision, release-acceptance-decision, audit50-fix4 and audit70-fix1..5): three conflicts, all docs, all add-only, none dropped. `README.md` and `docs/INTEGRATION.md` keep main's rewritten `GET /api/overlay` bullet (acceleration rebase now cited to `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`) followed by this node's `GET /api/risk` bullet; this file keeps main's `audit70-fix5` section before this one. No code, test, golden or vector conflicts; `capital/audit.py`, `capital/margin.py`, `tests/test_workspace_audit.py`, `tests/test_coverage.py` and `tests/test_handbook.py` merged cleanly.

Commands actually run after the second merge:

- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check` (28 routes, 20 artifacts, 8 stages), `manifest_vectors` (13 files), `finance_vectors` (90609 bytes), `workspace_vectors` (6 files), `not_bound_checklist`, `auth_matrix` with `--check`, and `scripts/decision_ledger.py`: exit 0; no regeneration needed.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged.
- `python3 -m unittest discover -s tests -v`: exit 0, **652 passed** (84.2s), no failures on the first run.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. Vendored file SHA256 values match `capital/vendor/manifest.json`.
- `PLAYWRIGHT_BROWSERS_PATH=build/pw-browsers npm run test:browser`: exit 0, **51 passed** (1.7m), including the three `portfolio-risk.spec.cjs` cases; no server left running on 8765–8768.
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output.

## operator-console-ux (operator desk)

Browser-only change: `#desk` view in `capital/static` (sim_day control through `POST /api/overlay/commands`, per-case timeline merging the F04 journal and overlay entries, server-reasoned next actions, risk tiles). No server, contract, auth, golden or vendor change. The only client arithmetic is `to_sim_day = from_sim_day + N`.

Commands actually run:

- `python3 -m unittest discover -s tests -v`: exit 0, **657 passed** (99.9s), including the five `tests/test_operator_desk.py` source pins.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (28 routes, 20 artifacts, 8 stages). `python3 scripts/seed_demo.py`: ok, digests unchanged.
- `npm ci`: exit 0. `npm run test:browser`: exit 0, **62 passed** (3.2m): the 51 existing specs plus 11 in `tests/browser/operator-desk.spec.cjs`. Screenshots are under `test-results/operator-desk/{desktop,mobile}/`. No server was left on 8765–8768 or 8911–8921.
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions tests/golden capital/server.py capital/service.py`: no output.

## shadow-participation-slice-uc

`capital/shadow.py` adds three pure integer-floor computations from `CAPITAL_SHADOW_POLICY.md` §3.7, wired into `DecisionNoteShadow` and `GET /api/policy/shadow`: single-claim revenue participation posting, claim-slice size and price, and the ordered UC1-UC4 partition of `undistributed_cash`. All results are `SHADOW_NOT_APPLIED` with the nine false flags and `reconciliation: NOT_COMPARABLE`. The ratio, cap, advance rate and tier rate are read from the settlement and financial-terms notes at runtime; the only constants in code are the CAPITAL-SHADOW-V1 rule constants (10000 bps, 365 days), and an AST test bans the policy numbers. A missing settlement, terms or shadow note, or a non-ADOPTED entry, reports `SHADOW_NOT_BOUND` without numbers. A vector missing an input is `SHADOW_INPUT_UNKNOWN`; a domain breach is `SHADOW_INCONSISTENT`.

Vectors reproduced from the shadow note: V-RP-single (base 95000, participation 19000, cap 75000, payable 19000), V-CP-size (slice max 80750, discount 929, price 79821), V-UC-late-cash-open-refund (uc2 100000), V-UC-late-cash-accepted (uc3 100000, replayed on a disposable `MockSettlement` after a full mock acceptance), V-UC-overpay (uc4 1000, a labelled synthetic literal) and V-UC-split-statement (uc1 49000). `paid_to_date` is 0 with the source label `NOTE_VECTOR_FIRST_POSTING_NO_STORED_STATE` because there is no stored state. The multi-claim base, 90-day window, upward late cash, term end, slice registry, holder priority, impairment, aggregate caps, 180-day timer, D+1 batch and provider return stay `SHADOW_DEFERRED` rows carrying the note's unblock seam.

Resolutions and findings for the upstream candidates:

- UC2 uses `refund_outstanding` only. The settlement note's "when" clause also names `pg_adjustment_outstanding`, but the shadow note's formula and V-UC-late-cash-accepted (uc3 = 100000 while the accepted view has `pg_adjustment_outstanding` = 100000) require it not to. The field is required and validated but is not a partition input.
- The settlement note says largest remainder equals the pinned floor split for two payees. That does not hold in general (gross 99,999 at 500 bps: pinned 95000 / 4999, largest remainder 94999 / 5000). No equivalence is claimed and no reconciliation is attempted.
- `organizer_borne_refunds` is an explicit input; it is not derived from the refund shadow results.
- `expected_days` is a caller-supplied non-negative integer; the notes decide no bound for it.

`/api/policy/simulation`, `state_digest`, receipts and `operation_count` are unchanged (golden digest in `tests/test_shadow_slice_uc.py`, taken on main before this node).

## closeout-evidence-vector

The `closeout-evidence-vector` node supplies the eighth finance input vector, so all eight `FINANCE_PENDING_NODES` candidates now carry vectors. It implements the decided artifact of `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md` (provisional product decision; its ADOPTED entries are the policy, and the generator reads the strip keys, labels and non-claims from that note instead of copying them).

- `scripts/closeout_digest.py --write` emits `tests/vectors/closeout_digest.json` (format `KIX_CAPITAL_CLOSEOUT_DIGEST_V1`, label `INPUT_VECTOR_CANDIDATE`, data label `SIMULATED`, canonical ASCII JSON) from `build/acceptance-evidence.json`. Per acceptance stage it keeps `stage_id`, `command`, `status`, `expected_exit` (0), `test_count` (including the parser-intentional null of `node-check`), `label` `SIMULATED` and `funds_executed` false, plus the seeded-demo `state_digest`, `content_digest`, `debit`, `credit`, the vendor pin commit with its five `verified` flags, and the packaged zipapp `sha256`. The git `head_sha`, tool versions, timestamps, instance ids, paths and hosts are not carried: the digest is an allowlist projection, the 18 strip keys are also deleted at every depth, and they are listed in `stripped_keys`. The interpreter path becomes `python3` and the built zipapp path (it names the capital version) a placeholder. The write gate refuses (exit 1, no file written) unless the evidence is `ok:true`, `SIMULATED`, `funds_executed` false and holds exactly the nine ladder stages (including main's `integrated-journeys`), each passed and not injected.
- `scripts/closeout_digest.py --check` needs no evidence: canonical bytes, format, labels, `semantic_conformance` false, `upstream_nodes_completed` `[]`, `ok:true`, the stage table, no strip key at any depth, and byte equality with the copy embedded in `tests/vectors/finance_vectors.json` group `closeout_digest` (whose candidates-index row must name it). The vendor summary must match the manifest pin, contain exactly the pinned files, and set every file flag and `verified` to boolean `true`, even when the two copies match. Exit 1 on drift or a missing file. `--check-evidence` regenerates from fresh evidence, byte-compares, and names the first differing JSON path.
- `scripts/finance_vectors.py` gained the group `closeout_digest` → `fin-finance-closeout`, which embeds the committed digest as it is. The `candidates` index now has `vectors` non-null and `reason` null for 8 of 8 ids. `semantic_conformance` stays `false` and `upstream_nodes_completed` stays `[]`. `finance_vectors.json` was regenerated only with `--write`; the digest is regenerated first.
- `scripts/docs_surface.py` gained the `VECTOR_NEEDLES` entry for `closeout_digest.json`, and the binding note (`CAPITAL_UPSTREAM_BINDING.md` §3.3 prose and `artifact_map`) now maps `fin-finance-closeout` to `tests/vectors/closeout_digest.json (derived from that evidence)` as the decision's `binding_note` directs; `candidate_ids` and every status token are unchanged. The acceptance ladder is unchanged (no closeout stage: the evidence describes the ladder, so a stage inside it would self-reference).

This is not SEMANTIC_CONFORMANCE, and it completes no upstream node. It is self-asserted evidence from this repository's own tooling, not independent review, CI or human acceptance. `fin-finance-closeout` stays a PENDING candidate and the denominator stays eight. Because `head_sha` and tool versions are stripped by design, the run that produced this digest is recorded here instead. The committed digest comes from the merge-with-main run below: Python 3.13.5, node v20.19.2, npm 11.21.0, Playwright 1.58.2 with Chromium headless shell 145.0.7632.6, on the merge worktree of branch `agent/capital-closeout-evidence-vector` before the merge commit. The pre-merge run that first produced it was Python 3.13.5, node v20.19.2, npm 9.2.0, on a clean worktree of the same branch before any commit.

`tests/test_closeout_digest.py` writes its expectations by hand (the nine stage ids and the exact command text per stage, the strip list, the four non-claims, the labels) and builds its own evidence, so it needs no browser. Mutation checks: an evidence with `ok:false`, a non-`SIMULATED` label, `funds_executed` true, a failed, unrun, missing, extra or injected stage, no printed sha256, unverified vendor files or unrecorded golden digests is refused with no artifact written; an injected `head_sha`, `instance_id`, `host`, `path`, `cwd` or `elapsed_s` key is absent from the bytes; reordered evidence keys, a new `head_sha`, other tool versions and other timestamps give identical bytes, while a changed test count, packaged sha256, golden digest or debit changes them. On temp copies, `--check` exits 1 for an edited stage status (`unit`, `browser`, `seeded-demo`), a removed file, a tampered embedded copy (path named), a stale embedded copy, non-canonical bytes, a dishonest label, a strip key at any depth, a changed strip list, a dropped or reordered stage, a missing group and a candidates index that no longer names the group. A byte scan of the committed file finds no 40-hex head sha (the only 40-hex string is the decided vendor pin commit), no UUID, no timestamp, no host path, no tool version, and `instance_id` only inside `stripped_keys`.

Commands actually run, in order:

- Bootstrap: because the unit stage verifies the committed digest, the first acceptance run needs one to exist. A placeholder digest was generated through `closeout_digest.py --write --evidence <temp file>` from hand-built evidence (in `/tmp`, plausible counts), then `finance_vectors.py --write`. It was replaced by the real one below; nothing of it is committed.
- `python3 scripts/acceptance.py` (placeholder in place): exit 0, `ok=true`. unit 549, storage-conformance 7, pinned-vendor 7, upstream-claims 181 (`CLAIM_CONFORMANCE`), node-check (no count), browser 48, packaged-smoke 8, seeded-demo 1; about 3 min.
- `python3 scripts/closeout_digest.py --write`: 3995 bytes. `python3 scripts/finance_vectors.py --write`: 92748 bytes. `--check` of both: exit 0.
- `python3 scripts/acceptance.py` (second pass): exit 0, `ok=true`, same counts. `python3 scripts/closeout_digest.py --check-evidence`: exit 0, the covered fields byte-match the first pass (`cmp` of the digest written from pass 1 against the file: identical).
- Two `closeout_digest.py --write --file` runs into a temp directory: `cmp` identical to each other and to the committed file. sha256 of `tests/vectors/closeout_digest.json` is `def9f63f…4c54`.
- `closeout_digest.py --check` on temp copies: edited stage status exit 1 (`stage unit is not a clean SIMULATED pass`), removed file exit 1; `--write --evidence <absent>` exit 1.
- `git diff --stat -- capital tests/vectors/manifest tests/vectors/export-dev.key tests/golden .aiops .github`: empty. The five vendored files and `manifest.json` are byte-identical (the pinned-vendor stage and `closeout_digest.py` both verify the pin).

### Merge with main (2026-10-17)

The branch was merged with `origin/main` at `b442b6a` (sim-clock-ledger, margin-cure-default, the audit@60 fixes, coa-candidate-projection, event-log-summary and the repayment-posting decision had landed). Conflicts in `docs/OPERATOR_HANDBOOK_KO.md`, `docs/VALIDATION.md` and `tests/vectors/finance_vectors.json` were resolved by keeping both sides: main's handbook role table, `overlay:command` row and five node sections next to this node's `closeout-evidence-vector` section and its rewritten `finance-vector-pack` sentence; main's four VALIDATION sections next to this one. The generated files were not hand-merged. `tests/vectors/finance_vectors.json` and `tests/vectors/closeout_digest.json` were rebuilt on the merged tree through the `CAPITAL-CLOSEOUT-REGEN-V1` procedure, because main changed two covered fields: the unit stage count (the merged suite has 680 tests, the pre-merge one had 549) and the packaged zipapp `sha256` (main changed `capital/`). The golden `state_digest`, `content_digest` and totals are unchanged, as is every other stage count. `python3 scripts/closeout_digest.py --check-evidence --file <pre-merge digest>` against fresh evidence exited 1 naming exactly `$.packaged.sha256`, `$.stages[0].test_count.passed`, `$.stages[0].test_count.ran`: the drift detector worked as decided.

One test from main was changed, not weakened: `tests/test_coa_candidate.py` `test_v1_and_golden_files_are_untouched` diffed the working tree against `origin/main` over `capital/projection.py`, `capital/ports.py`, `capital/overlay.py`, `capital/export.py`, `tests/golden`, `capital/vendor`, `.aiops` and `docs/decisions`. On main that comparison is empty; on any branch that edits a decision note it fails, and this node must edit `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` (the closeout decision's `binding_note`). Here it also reported `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`, which `origin/main` had gained after the merged commit. The test now checks the same guarded paths against the commit that introduced `capital/coa.py` (`40e2a1c` on main, compared with its own parent), which is the claim the test makes, so edits other nodes make on main or on a later branch do not count; where that history is unavailable (a shallow CI clone) it falls back to the previous working-tree-against-`HEAD` check. Exercised on throwaway histories: a clean coa commit passes although a later commit edits a decision note; a coa commit that touches `docs/decisions` fails; a shallow clone falls back (clean passes, an uncommitted guarded edit fails); a merge in progress whose `MERGE_HEAD` holds the commit passes. In CI (`actions/checkout` depth 1, no `origin/main`) the behaviour is unchanged.

Commands actually run on the merged tree, in order:

- `npx playwright install chromium`: Chromium headless shell 145.0.7632.6 (build 1208) installed into the user cache; it was absent on this machine.
- Quick gates before regeneration: `docs_surface.py --check` (`27 routes, 21 artifacts, 8 stages`), `decision_ledger.py`, `not_bound_checklist.py --check`, `auth_matrix.py --check`, `manifest_vectors.py --check` (13 files), `workspace_vectors.py --check` (6 files), `finance_vectors.py --check`, `closeout_digest.py --check`: all exit 0 with the pre-merge digest still in place.
- `python3 scripts/acceptance.py` (first): `ok=false`, the one failure being the `test_v1_and_golden_files_are_untouched` case above (679 passed, 1 failed). After the test change: `ok=true`; unit 680, storage-conformance 7, pinned-vendor 7, upstream-claims 181 (`CLAIM_CONFORMANCE`), node-check (no count), browser 48, packaged-smoke 8, seeded-demo 1; 3m13s. Two intermediate ladder runs failed only in the browser stage with `http://127.0.0.1:8765 is already used`: another worktree on the same machine (`t05-t06-sim-journeys`) was running its own Playwright servers on 8765-8768; its processes were left alone and the ladder was rerun once the ports were free.
- `python3 scripts/closeout_digest.py --write`: 3995 bytes. `python3 scripts/finance_vectors.py --write`: 93806 bytes. `--check` of both: exit 0.
- `python3 scripts/acceptance.py` (second pass): exit 0, `ok=true`, same counts; only `stages` differs between the two evidence files (`head_sha` and `tool_versions` were equal, output tails and timings were not). `python3 scripts/closeout_digest.py --check-evidence`: exit 0 (`matches the evidence: 3995 bytes`); a digest written from the second-pass evidence into a temp directory is `cmp`-identical to the committed file.
- Two `closeout_digest.py --write --file` runs from the first-pass evidence: `cmp` identical to each other and to the committed file; the same evidence with its top-level keys reversed: identical bytes; evidence with `head_sha` keys injected at the top level and inside a stage: exit 0, neither value in the bytes, identical to the committed file. sha256 of `tests/vectors/closeout_digest.json` is `dabb3d48…74f0`.
- Byte scan of the committed digest: the only 40-hex string is the vendor pin commit, no UUID, no timestamp, no `/home` `/tmp` `/workspace` `/usr` `/opt` path, no Python, node or Playwright version string, `instance_id` only inside `stripped_keys`, no strip key as a dict key at any depth, bytes canonical.
- `closeout_digest.py --check` on temp copies: edited stage status exit 1 (`stage unit is not a clean SIMULATED pass` and `group closeout_digest differs from the digest: $.stages[0].status`), removed file exit 1, tampered embedded copy in a temp pack exit 1 (`$.stages[5].test_count.ran`). `--write --evidence <absent>` exit 1, no file written; `--write` on `ok:false` evidence exit 1 (`evidence ok is not true`), no file written.
- `python3 -m unittest discover -s tests -v`: exit 0, **680 passed** (87.9s). `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, 7 passed. `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0. `npm run test:browser`: exit 0, **48 passed** (1.6m); no `capital.server` from this worktree left running. All eight drift scripts above: exit 0 on the final tree.
- `git diff --stat HEAD -- capital/vendor tests/vectors/manifest tests/vectors/export-dev.key tests/golden/demo.json .aiops .github scripts/acceptance.py` and the same against `MERGE_HEAD`: empty. The five vendored files SHA256-match `manifest.json` (commit `7481b0e1…3cfe`). `origin/main` had moved two further commits (`2acd625`, `614ba7c`) past the merged `b442b6a` while this resolution ran; they are not part of this merge.

No `DECISION_REQUIRED.md` was written: the decision note ADOPTS every item this node needs, and no rate, fee, limit, allocation priority, refund burden, provider, credential or upstream change was needed.

### Second merge with main (2026-10-17, `origin/main` at `2acd2a0`)

Main's `audit70-fix5` and the external-gate and release-acceptance decision notes landed meanwhile. The only conflict was this file (main's `audit70-fix5` section is kept before this node's section; both sides kept). `python3 scripts/acceptance.py` on the merged tree: `ok=true`, unit 684, storage-conformance 7, pinned-vendor 7, upstream-claims 181, browser 48, packaged-smoke 8, seeded-demo 1. `python3 scripts/closeout_digest.py --write` and `python3 scripts/finance_vectors.py --write` regenerated the digest (3995 bytes) and the finance pack (93806 bytes); both `--check` and `closeout_digest.py --check-evidence`: exit 0. No code, test or golden file conflicted.

### PR fix round 1 (2026-10-21)

The blocking review finding was reproduced and fixed: `_vendor()` now compares
every evidence hash to the locked manifest before returning a verified summary.
`verified:true` alone cannot authorize a mismatched hash. The evidence-free
`--check` also requires the manifest commit, exactly the pinned file set, and
boolean `true` for every file flag and the summary, even if the digest and its
embedded copy match. Regression mutations cover each of the five hashes while
retaining `verified:true`, preserve an existing artifact on refusal, and leave no
new artifact when refused. Matching-copy mutations cover each false flag, a
changed commit, missing/extra files, an unverified summary and a non-boolean flag.
Before the fix, these checks produced 16 failing subcases; afterward all 61
closeout tests pass.

Actual local verification from HEAD `e771368`, Python 3.13.5, node v20.19.2,
npm 11.21.0, Playwright 1.58.2 (installed offline from the existing cache):

- `python3 -m unittest discover -s tests -v`: 674 reported, 2 failures, 55 errors.
  All errors report `PermissionError: [Errno 1] Operation not permitted` creating
  sockets. The failures concern server startup and packaged server smoke;
  failed class setups also prevent dependent tests from running. Full log:
  `/tmp/closeout-review-unit.log`.
- `python3 scripts/acceptance.py`: exits 1, `ok:false`. Unit, storage HTTP fuzz,
  browser server startup and packaged smoke fail under the socket restriction;
  pinned-vendor (7), upstream-claims (181), node-check and seeded-demo (1) pass.
  Log: `/tmp/closeout-review-acceptance-pass1.log`.
- Pinned MockCredit discovery: 7 pass. `python3 -m compileall -q capital`,
  `node --check capital/static/app.js`, `scripts/docs_surface.py --check`,
  `scripts/closeout_digest.py --check` and `scripts/finance_vectors.py --check`:
  exit 0.
- `npm run test:browser`: exits 1 before tests run because the configured
  `127.0.0.1` web server cannot create a socket, despite Chromium being available.
  Log: `/tmp/closeout-review-browser.log`.
- `closeout_digest.py --write` against the failed evidence: exit 1,
  `evidence ok is not true`; existing digest bytes preserved. The digest and
  finance pack remain unchanged. A fresh successful two-pass regeneration is
  pending a loopback-capable runner; the structural checks above do not claim
  fresh acceptance. See root `DECISION_REQUIRED.md` for the runner options and
  completion procedure. This is historical evidence from the restricted runner;
  the conflict-fix round below records the current runner and supersedes that pending status.

The five vendored files SHA256-match the locked manifest; those files, the
manifest itself, manifest vectors, export development key, golden demo,
acceptance ladder, `.aiops/` and CI definitions remain byte-identical to HEAD.
No commit, push or post was made. All data and acceptance remain SIMULATED;
there is no SEMANTIC_CONFORMANCE or upstream-completion claim.

### Conflict-fix round 1 (2026-10-23)

This round merges `origin/main` / `MERGE_HEAD` `5c23989` into branch
`agent/capital-closeout-evidence-vector` at pre-merge HEAD `39261c5`.
All six conflict resolutions preserve both sides: the README feature descriptions
and commands; both sets of handbook and validation sections; all four conflicting
`VECTOR_NEEDLES` entries; the historical COA guard plus main's live code/vendor/
decision-note byte guard (the closeout decision's required binding-note update is
byte-guarded against reviewed pre-merge HEAD); and the finance pack, regenerated only with `--write`.
The golden-value comparison includes all pins on main, including its journey pins.

Main already has nine acceptance stages. The digest's explicit stage table and
hand-written command expectations now include `integrated-journeys`, the unit
stage's decision-binding command, storage's crash-replay command, and all four
upstream claim commands. `scripts/acceptance.py` is byte-identical to main; no
stage was added or changed here. Main's new `tests/decision_bindings.json` now
records the five implemented closeout policies as `CONSUMED`, with concrete
module/test consumers and a hand-written regression assertion. Other pending
consumers remain pending.

The old restricted-runner result above is historical. This runner supports
loopback sockets and has cached Chromium. An explicitly SIMULATED, hand-built
temporary evidence fixture bootstraps the nine-stage artifact so unit discovery
can validate its new shape; it is not fresh acceptance evidence. The successful
acceptance run and two-pass regeneration results below replace that bootstrap.
Python 3.13.5, node v20.19.2, npm 11.21.0 and Playwright 1.58.2 are the local tools;
versions stay in this prose and per-run evidence, outside the digest.

Actual round-1 verification (all data SIMULATED):

| Check | Result |
|---|---|
| First `python3 scripts/acceptance.py` | Exit 0, `ok:true`; unit 902, storage 19, pinned vendor 7, upstream claims 269, browser 69, packaged smoke 8, seeded demo 1, integrated journeys 4; node syntax passed with its intentional null count. Log: `/tmp/closeout-merge-acceptance-pass1.log`. |
| `closeout_digest.py --write`, then `finance_vectors.py --write` | Replaced the bootstrap with fresh successful acceptance evidence: 4401-byte digest, 96931-byte finance pack. |
| Two `closeout_digest.py --write --file <temp>` reruns | Byte-identical to each other and the artifact. Digest SHA256 `52ecad56dc0ad3653fd3e3cee442bd1267e8b21c314d232b13f06b4052ffd2b7`. |
| Digest `--check`, `--check-evidence`; finance `--check` | Exit 0; eight of eight candidates have vectors and null reasons. |
| Mutations on temporary copies | Edited unit status and removed artifact each exit 1; changed evidence count exits 1 naming `$.stages[0].test_count.ran`. No committed file mutated by these checks. |
| Fresh artifact byte scan | No run head SHA, tool version, timestamp, instance id or host path; no stripped key at any object depth. The vendor pin and the policy's `stripped_keys`/non-claims disclosures remain as required. |
| Local commands | Pinned vendor discovery: 7 pass; `compileall -q capital` and `node --check capital/static/app.js`: exit 0. Documentation surface: 30 routes, 39 artifacts, 9 stages. Decision ledger/bindings, not-bound checklist, auth matrix, manifest/workspace/pack/forecast vectors, gate faults and crash matrix: all exit 0. Log: `/tmp/closeout-merge-local-checks.log`. |

The first post-regeneration rerun (pass 2) exited 1 solely in the browser stage:
68 passed and one policy-page label expectation timed out. All other stages
passed with the same counts. Its trace records HTTP 200 on the page and API
requests, while the five-second text expectation took 37.4 seconds and the test
hit its 30-second timeout, suggesting a scheduling stall. The evidence is retained
at `build/closeout-acceptance-pass2-failed.json`, with its trace at
`build/closeout-pass2-policy-trace.zip` (both ignored local outputs). A write using
that failed evidence exited 1 (`evidence ok is not true`) and preserved the
successful digest. An isolated, unchanged
`npm run test:browser -- tests/browser/policy-simulator.spec.cjs --project=workspace`
then passed both tests in 4.1 seconds. No timeout, test assertion, CI setting or
production code was changed to obtain a pass.

The final COA guard additionally compares the authorized binding note byte for
byte with this branch's reviewed HEAD. Its focused discovery passed all 35 tests
(`/tmp/closeout-merge-coa-final.log`); other decision notes stay guarded against
main, and the original COA introduction guard and main's golden-value guards
remain. The final full ladder rerun includes this strengthened guard.

The final full rerun (pass 3, `/tmp/closeout-merge-acceptance-pass3.log`) exited 0
with `ok:true`: unit 902, storage 19, pinned vendor 7, upstream claims 269,
browser **69 passed / 0 failed**, packaged smoke 8, seeded demo 1 and integrated
journeys 4; node syntax passed with its intentional null count. Final
`closeout_digest.py --check-evidence`, digest `--check` and finance `--check` all
exit 0. Two additional `--write --file <temp>` regenerations from this final
evidence are byte-identical to each other, the committed digest, and the digest
saved after successful pass 1. Thus the two successful acceptance passes have
identical covered bytes despite the intermediate failed run. The final digest
is still 4401 bytes with the SHA256 above, and the finance pack is 96931 bytes.
The transient timeout is recorded rather than hidden; no failing evidence was
used for a committed artifact.

Vendor files and `manifest.json`, `capital/export.py`, the export development key,
golden demo, `.aiops/` and CI definitions are byte-identical to both pre-merge
HEAD and main. Manifest vectors and the acceptance script are byte-identical to
main, preserving main's new DEV_ONLY keyset fixtures and its nine-stage ladder.
Every main handbook section and validation heading survives. All six conflicts
have been staged as resolved, with no conflict markers. No commit, push or post
is made; merge completion belongs to the supervisor. No SEMANTIC_CONFORMANCE,
real-funds execution, human acceptance or upstream completion is claimed.

### Conflict-fix round 2 (2026-10-23)

This round combines pre-merge HEAD `ab7572c` with `MERGE_HEAD` / `origin/main`
`8c5ad10`. All four conflicts retain both features: the handbook has separate
`closeout-evidence-vector` and `overlay-repayment-posting` sections; decision
bindings test both implemented consumers as `CONSUMED` and retain only the
recovery/writeoff and claim-slice policies as pending; the COA test preserves
its historical guard and main's golden checks, with live byte guards on the
projection, ports, overlay, export, vendor, locked demo/empty goldens and
decision notes. The authorized binding-note change stays pinned to reviewed
HEAD. Every test method from both parents survives. The finance pack is
regenerated through `scripts/finance_vectors.py --write`, retaining main's
updated facade definitions and this node's eighth `closeout_digest` group.
The handbook's stale eight-stage wording now names the existing nine stages;
`scripts/acceptance.py` remains byte-identical to both parents.

The first plain `npm run test:browser` exited 1 before tests because unrelated
workspace services already occupied loopback ports 8765 and 8766. Those services
were left running. Browser and acceptance checks instead run in a private
network namespace, with only its loopback interface enabled:
`unshare --user --map-root-user --net bash -c 'ip link set lo up && COMMAND'`.
The npm command, Playwright config, assertions, timeouts and acceptance stages
are unchanged. `npm ci --no-audit --no-fund` installed the locked dependencies;
`npx playwright install chromium` installed the matching free local browser.

Local verification (SIMULATED only):

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0, 949 tests; `/tmp/closeout-round2-unit.log`. |
| Pinned MockCredit discovery | Exit 0, 7 tests. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Exit 0. |
| Documentation surface, decision ledger/bindings, not-bound checklist, auth matrix, manifest/workspace/forecast vectors | Exit 0; documentation inventory: 30 routes, 39 artifacts, 9 stages. |
| Isolated `npm run test:browser` | Exit 0, 69 passed; `/tmp/closeout-round2-browser-isolated.log`. |
| First isolated `python3 scripts/acceptance.py --evidence build/closeout-round2-pass1.json` | Exit 0, `ok:true`; unit 949, storage 19, vendor 7, upstream claims 269, browser 69, packaged smoke 8, seeded demo 1, journeys 4; node syntax has its intentional null count. `/tmp/closeout-round2-acceptance-pass1.log`. |
| Gate-fault corpus and crash matrix `--check` | Exit 0; 7 fault cases and 23 crash cells match. |
| Digest and finance pack regeneration | Only `--write` used. Digest: 4401 bytes, SHA256 `a82a4665b2f0e3d3d45e8f81684b07e14f5266ee016296e32fd0228a9f118ca1`; finance pack: 97125 bytes. |
| Two additional digest `--write --file <temp>` runs | Byte-identical to each other and the artifact. Digest `--check` / `--check-evidence` and finance `--check` exit 0. |
| Temporary-copy mutations | Edited stage status and removed artifact each make `--check` exit 1; edited evidence count makes `--check-evidence` exit 1 naming `$.stages[0].test_count.ran`; `ok:false` evidence refuses `--write` and preserves existing bytes. |
| Artifact scan and candidate index | No run SHA, tool version, timestamp, instance id, host path or stripped object key. Policy disclosures and vendor pin remain. Eight of eight candidates have vectors, null reasons, `semantic_conformance:false`, `upstream_nodes_completed:[]`. |

Before regeneration, fresh evidence correctly produced exit 1 naming only
`$.packaged.sha256` and the unit stage's passed/ran counts (902 to 949). After
regeneration those bytes match. Actual tools were Python 3.13.5, node v20.19.2,
npm 11.21.1, Playwright 1.58.2 and Chromium headless shell 145.0.7632.6;
the run HEAD was `ab7572cec1930b91b40143f89c44ae993e09bbcb`. These per-run values
remain in this prose and ignored evidence, outside the digest.

The first post-regeneration pass (`build/closeout-round2-pass2.json`, log
`/tmp/closeout-round2-acceptance-pass2.log`) exited 1 solely in the browser stage:
68 passed and one 30-second timeout in `command-fence.spec.cjs`'s manual-refresh
case. Every other stage passed with the same counts. Its preserved trace is
`build/closeout-round2-pass2-command-fence-trace.zip`: the browser's expected-text
assertion matched in about 110 ms (`16177.502` to `16287.089`), but its test-runner
completion arrived around 149 seconds later (`165602.579`). This suggests a
scheduling stall, without establishing its cause. The failed evidence is refused
by `--write` (exit 1, no new artifact); the successful digest remains unchanged.
An isolated, unchanged
`npm run test:browser -- tests/browser/command-fence.spec.cjs --project=workspace`
then passed all five tests in 8.3 seconds, including the timed-out case in 943 ms
(`/tmp/closeout-round2-command-fence-rerun.log`). No assertion, timeout, stage,
configuration or product code was changed to obtain the rerun pass.

The final full rerun (`python3 scripts/acceptance.py` in the same private network
namespace; `/tmp/closeout-round2-acceptance-pass3.log`) exited 0 with `ok:true`:
unit 949, storage 19, vendor 7, upstream claims 269, browser 69, packaged smoke 8,
seeded demo 1 and journeys 4; node syntax passed with its intentional null count.
The default `build/acceptance-evidence.json` is this successful final evidence,
also preserved as `build/closeout-round2-pass3.json`. Its covered bytes are
identical to successful pass 1 and the regenerated artifact. Final digest
`--check-evidence` (default evidence), digest `--check` and finance `--check` all
exit 0. Both additional temporary `--write` runs remain byte-identical, and the
artifact SHA256 and sizes above are unchanged. This completes the required
two-successful-pass regeneration, with the intermediate failure retained.

The five vendored files verify against their SHA256 locks. Vendor and manifest,
manifest vectors, the development export key, golden demo, `.aiops/` and the
acceptance script are byte-identical to both parents. Main's repayment code and
goldens are preserved exactly. All data remains SIMULATED, with no real funds,
SEMANTIC_CONFORMANCE, upstream completion or human-acceptance claim. No commit,
push or external post is made; the supervisor owns the merge commit.

## crash-replay-matrix

Test-only change: `tests/crash_matrix.py` replays a fixed seven-save command script (offer → approve → bind_settlement → draw → advance_day 0→3 → repay → advance_day 3→4 on `sim-cr-a`, fixture `sim-committed` 40000/10000 units) through `FileWorkspace` wrapped in the save-counted `CrashInjectingStorage`. Each of the 23 cells injects a crash before and after a workspace write boundary — journal-append, overlay-entry, temp-file rename (`replace` and `dir-fsync` reuse the `tests/storage_conformance.py` os injector) — plus three torn-payload cells (truncated, payload-byte flip with intact JSON, overlay-section digest-byte flip with intact `payload_sha256`), a stale `.workspace.json.*.tmp` leftover, and one real SIGKILL on the `python3 -m capital.server --workspace` subprocess via the T06-sim `ServerProcess`/`Session` harness with a fire-and-forget overlay write in flight. Every cell restarts (`FileWorkspace.open` → `CapitalService`) and must restore the pinned `state_digest`/`overlay_state_digest` or fail closed `WORKSPACE_UNREADABLE` — never a silent empty book, never a rewrite of torn bytes, writes stay 503 after the boundary. The mid-flight SIGKILL is bivalent by nature, so the pin names the two complete overlay digests it may restore (`overlay_state_digest_one_of`); a torn value can never match. Each restarted cell also runs `capital.audit.audit_workspace` (workspace-offline-audit dep): ok for restored cells, `WORKSPACE_UNREADABLE` with the pinned failing check for torn ones. Outcomes are pinned in `tests/vectors/workspace_crash.json` (format `KIX_CAPITAL_WORKSPACE_CRASH_V1`, label `SIMULATED`, `semantic_conformance` false, `stage5_durable_transactions`/`cross_host_fencing` NOT_BOUND/NOT_CLAIMED; digests only — no instance id, token, port or timestamp). `scripts/acceptance.py` joins the matrix to the `storage-conformance` stage as a second command; `scripts/docs_surface.py` gains the `workspace_crash.json` VECTOR_NEEDLES entry and README keeps its artifact plus `--check` needles. No production code changed; no new file format or schema; envelope v2 only.

Commands actually run:

- `python3 tests/crash_matrix.py --write`: wrote 23 cells to `tests/vectors/workspace_crash.json`. First `--check` attempt failed on three authoring bugs (missing prefix-0 audit expectation for a never-saved directory, a `*_one_of` key lookup, and a byte flip that produced invalid JSON); fixed, regenerated.
- `python3 tests/crash_matrix.py --check`: exit 0, `crash matrix vectors ok: 23 cells match`.
- `python3 -m unittest tests.test_crash_replay -v`: exit 0, **12 passed** (~1.3s), run three times — the SIGKILL cell is deterministic in verdict (it restores one of the two pinned digests).
- `python3 -m unittest discover -s tests -p test_crash_replay.py`: exit 0, 12 passed.
- `python3 -m unittest discover -s tests -v`: exit 0, **704 passed** (97.5s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital tests`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (29 routes, 21 artifacts, 9 stages). `python3 scripts/workspace_vectors.py --check`: 6 files match, no vector bytes changed.
- `python3 scripts/manifest_vectors.py --check` (13 files), `finance_vectors.py --check` (90966 bytes), `auth_matrix.py --check`, `not_bound_checklist.py --check`, `scripts/decision_ledger.py`: exit 0. `python3 scripts/seed_demo.py`: ok, `state_digest`/`content_digest` unchanged.
- `npm ci --ignore-scripts`: exit 0. `npm run test:browser`: exit 0, **62 passed** (1.6m); playwright webServers stopped, none left on 8765–8768.
- `python3 scripts/acceptance.py`: exit 0, evidence `ok` true; `storage-conformance` stage passed=19 (7 conformance + 12 crash-replay) across its two commands; unit 704, pinned-vendor 7, upstream-claims 181, node-check ok, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 2 (T05-sim/T06-sim `SIMULATED`).
- Vendor check: all five `capital/vendor/` SHA256 match `manifest.json`. `git status` modified set: `README.md`, `scripts/acceptance.py`, `scripts/docs_surface.py`, `tests/test_acceptance.py`; new: `tests/crash_matrix.py`, `tests/test_crash_replay.py`, `tests/vectors/workspace_crash.json`. No `capital/`, `.aiops/`, golden or docs/decisions change.

## gate-fake-fault-corpus

`tests/vectors/gate_faults.json` (format `KIX_CAPITAL_GATE_FAULTS_V1`) pins seven scripted `LOCAL_FAKE_GATE` cases replayed through the real loopback facade (`POST /api/commands`, `GET /api/operations/{id}`) with `GateHttpProducer` against `scripts/fake_gate.py`: accept, `error-5xx` (502 `GATE_FAILED`, no application), `malformed-json` (502 `INVALID_JSON`, original receipt kept), `drop-before` and `drop-after` (UNKNOWN, `retry_authorized` false, exactly one upstream POST, never resent), `timeout` (delayed-then-lost, same UNKNOWN shape), and an `operationId` replay whose different body is `409 IDEMPOTENCY_CONFLICT` at both the facade fingerprint check and the gate. `scripts/gate_faults.py --check` re-runs the corpus on `127.0.0.1` and exits nonzero on drift; it rewrites nothing. SIMULATED, `NOT_BOUND`, not SEMANTIC_CONFORMANCE; no funds move.

Commands actually run:

- `python3 scripts/gate_faults.py --check`: exit 0, 7 cases match.
- `python3 -m unittest tests.test_gate_faults`: exit 0, 7 tests (21.2s).
- `python3 -m unittest discover -s tests -p test_gate_producer.py`: exit 0, 14 tests — the producer vectors still pass because a conflicting replay surfaces as `CreditError('IDEMPOTENCY_CONFLICT')` (the FSM detects it; the gate emits HTTP 409).
- `python3 -m unittest discover -s tests -v`: exit 0, **699 passed** (121.9s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, 7 passed.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`, `python3 scripts/seed_demo.py` (digests unchanged), `python3 scripts/docs_surface.py --check` (29 routes, 21 artifacts, 9 stages), `python3 scripts/finance_vectors.py --check` (90966 bytes, after the documented `--write` regeneration for the honest facade-v1.json edit): exit 0.
- `npm ci --ignore-scripts`: exit 0. `npm run test:browser` first run: 61/62 — one `SERVER_NOT_READY` flake (`terms-overlay.spec.cjs` spawned helper on :8892 answered late); the spec passed alone and the second full run: exit 0, **62 passed** (2.0m). No server left running.
- Vendored `capital/vendor` SHA256 values all match `manifest.json`; `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output.

Facade receipts keep the pinned shape (adding a `label` field was reverted because it moved `content_digest` and broke the gate-fake/pinned golden parity test); the `LOCAL_FAKE_GATE` label is carried by every gate receipt and by the UNKNOWN envelope, and `facade-v1.json` declares it as an optional property on all three receipt shapes plus `unknown_operation` in the `/api/commands` response union and the `GATE_FAILED` (502) error.
## read-model-claims-conformance

A third pinned claim table `tests/read_model_claims.json` (format `KIX_CAPITAL_READ_MODEL_CLAIMS_V1`, 39 rows) maps existing Capital read surfaces onto the upstream draft `docs/contracts/READ_MODEL_QUERIES.md` at `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` — the same SHA as the vendor pin. Rows cite `### 2.12 \`get_credit_advance\``, `### 2.13 \`get_credit_claim\`` and `## 8. 비변경` with verbatim needles. The mapping is an honest adapter, recorded in the table `note` and in each row's `route` field: `get_credit_advance` reads through `GET /api/state` case views (literal `CreditMachine.view` dicts), `get_credit_claim` through in-process `CreditMachine.view_claim`. `GET /api/evidence` is deliberately unmapped — its rows are `MockSettlement` claims (the §2.11 object) and §2.13 forbids merging the two objects. No upstream query name is implemented, no route was added, no catalogue promotion: this prepares the parked read-model-credit-queries node only.

`capital/read_model_claims.py` mirrors `capital/agent_claims.py`: thin delegation to `capital/upstream_claims.py` helpers plus the `read.*` check registry and a `route` registry enforced by `validate_table`. It locates the table via the parent of `capital.resources.ROOT`, not `Path(__file__)`. Every check runs its read under a §8 non-mutation guard — `canonical_state()`, journal length, the folded overlay state digest and `len(receipts)` (operation_count) must be unchanged or the claim fails; four dedicated `read.readonly.*` claims assert the guard triple-plus-count outright, including erroring reads. `scripts/read_model_claims_check.py` is a structural clone of `scripts/agent_claims_check.py`: bare invocation prints `SKIPPED` (never a pass), `--execute` prints the count line, `--protocol-dir` verifies citations read-only. `scripts/acceptance.py` runs it as the third command of the unchanged `upstream-claims` stage; `_merge_counts` sums all three count lines (87+94+39=220). `tests/test_read_model_claims.py` adds 12 tests. Results are SIMULATED and labelled CLAIM_CONFORMANCE, never SEMANTIC_CONFORMANCE. Nothing under `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/` was edited.

Commands actually run, in order:

- `python3 scripts/read_model_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=39 total=39 failed=0`.
- `python3 scripts/read_model_claims_check.py`: exit 0, first line `SKIPPED`, JSON status `SKIPPED` label `CLAIM_CONFORMANCE`, no success count.
- `python3 scripts/read_model_claims_check.py --protocol-dir /workspace/capital-run/kixproto-ro`: exit 0, `CLAIM_DRIFT verified=39 total=39`. The checkout was read only; its working tree HEAD `08119a4` carries the draft with all cited headings and needles.
- `python3 -m unittest tests.test_read_model_claims -v`: exit 0, **12 passed** in 2.141s (merged stage evidence `passed=220`).
- `python3 -m unittest discover -s tests -v`: exit 0, **704 passed** in ~98s (one interim run failed `test_acceptance_stage_runs_both_claim_tables` in `tests/test_agent_claims.py`, which pinned the old two-table sum 181; it now asserts the third command and the 87+94+39=220 total).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (29 routes, 20 artifacts, 9 stages).
- `npm ci`: exit 0, added 3 packages. `npm run test:browser`: exit 0, **62 passed** (1.6m). Playwright started and stopped its loopback servers; nothing was left on the test ports.
- `python3 scripts/acceptance.py`: exit 0. Evidence `build/acceptance-evidence.json` `ok` true. Stages: unit 704, storage-conformance 7, pinned-vendor 7, upstream-claims `passed=220 failed=0` label `CLAIM_CONFORMANCE`, node-check, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 2.
- Vendored SHA256 check against `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`: all five files `OK`. `git status` shows no change under `capital/vendor/` or `.aiops/`.

No `DECISION_REQUIRED.md` was written: the node is a cite-only mapping of existing read surfaces; nothing required money, credentials, a new route, an upstream edit, or an undetermined §6/§9 value.

## cashflow-forecast

New read-only route `GET /api/terms/portfolio/forecast` (`capital/forecast.py`, service method, literal child of `/api/terms` — no dispatcher or permission-registry change; inherits `projection:read`). Per drawn advance three legs (`SETTLEMENT_CASH_IN` on `expected_settlement_cash_day`, `CONTRACT_INTEREST` and `PRINCIPAL` at maturity) bucketed 0-7/8-30/31-60/61-90/91+ sim days ahead of the overlay `sim_day`, exact rationals floored once per bucket, `reconciliation.matched` against outstanding principal plus contract interest, `NOT_BOUND` with no numeric sections when the note is unusable. `capital/terms.py` `ledger_terms` gained an optional `expected_settlement_cash_day` kwarg (additive; postings unchanged). Contract `local_terms_portfolio_forecast` + `terms_forecast*` definitions; new `scripts/forecast_vectors.py` pinning `tests/vectors/forecast_vectors.json` on the seeded demo book; auth probe + finance-vector digests regenerated. No golden/vendor/decisions change.

Commands actually run (worktree `agent/capital-cashflow-forecast`):

- `python3 -m unittest tests.test_cashflow_forecast -v`: exit 0, **16 passed** (0.67s) — one fix: the test asserted a bucket for the unscheduled settlement leg (`day`/`bucket` are `null` by design).
- `python3 -m unittest discover -s tests -v`: exit 0, **708 passed** (96.5s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/forecast_vectors.py --check` (6456 bytes), `scripts/finance_vectors.py --check` (91570 bytes), `scripts/auth_matrix.py --check`, `scripts/docs_surface.py --check` (29 routes, 21 artifacts, 9 stages), `scripts/seed_demo.py` (state/content digest unchanged), `scripts/not_bound_checklist.py --check`: all exit 0.
- `npm ci` (3 packages): exit 0. `npm run test:browser`: exit 0, **62 passed** (1.8m); Playwright webServers on 8765–8768 shut down, none left running.
- Vendor SHA256 vs `capital/vendor/manifest.json`: 5/5 match. `git status`: no `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/` modifications.

## t03-t04-sim-journeys

Scripts-only node: `scripts/sim_journeys.py` gains two named SIMULATED journeys over the existing loopback API. `T03-sim` (22 steps, in-process server) is the zero-exception F04 lifecycle `offer -> approve -> bind_settlement -> draw -> advance_day 0->15->30 accrual -> full repay -> close`, with a post-close tick showing no further accrual and a mid-run all-MATCHED reconciliation. `T04-sim` (38 steps, `--workspace` subprocess) is the auditor evidence chain: the seeded demo book replayed over HTTP and cross-pinned to `tests/golden/demo.json` `state_digest`, an auditor session, read-only auditor GETs, `GET /api/export/manifest` (V3) written to a file and re-verified by `python3 -m capital.verify FILE`, `python3 -m capital.verify --workspace DIR` (OFFLINE_WORKSPACE_AUDIT, all checks MATCHED), `GET /api/reconciliation` all MATCHED, and `403 ROLE_FORBIDDEN` for an auditor write. Both carry `label` SIMULATED, `funds_executed` false, `integrated` false and claim no T01-T06 qualification. `tests/golden/journey_t03_sim.json` / `journey_t04_sim.json` pin terminal phases, `sim_day`, `overlay_state_digest` and `risk_digest`; drift exits 1. The `integrated-journeys` acceptance stage now runs all four journeys. No `capital/` change, no new routes, no `post_repayment` (parked per `docs/decisions/CAPITAL_REPAYMENT_POSTING.md`), no funds movement.

Commands actually run (pre-merge, on this branch):

- `python3 scripts/sim_journeys.py`: exit 0, `sim journeys ok SIMULATED T03-sim steps=22 T04-sim steps=38 T05-sim steps=35 T06-sim steps=33`; goldens written via `--update-golden` only.
- `python3 -m unittest tests.test_sim_journeys -v`: exit 0, **32 passed** (13.6s).
- `python3 -m unittest discover -s tests`: exit 0, **691 passed** (102.6s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py`: exit 0, **7 passed**. The five vendored files match `capital/vendor/manifest.json` SHA256.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`, `python3 scripts/docs_surface.py --check` (28 routes, 20 artifacts, 9 stages): exit 0.
- `npm ci --no-audit --no-fund`: exit 0. `npm run test:browser`: exit 0, **62 passed** (1.8m); no server left running.
- `python3 scripts/acceptance.py`: exit 0, evidence `ok` true; unit 691, storage-conformance 7, pinned-vendor 7, upstream-claims 181, node-check pass, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 4 (T03-sim 22, T04-sim 38, T05-sim 35, T06-sim 33 steps, all `SIMULATED`).
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output.

Merge with main (2026-10-20; main had gained covenant-watch and read-model-claims-conformance): two conflicts, both docs, both add-only, neither side dropped. `docs/OPERATOR_HANDBOOK_KO.md` keeps main's `read-model-claims-conformance` handbook-section before this node's `t03-t04-sim-journeys` section, each with its own `<!-- /handbook-section -->` closer; this file keeps main's `read-model-claims-conformance` section before this one. No code, test, golden or vector conflicts; `scripts/acceptance.py` merged cleanly and now runs both sides' stage changes (three claim tables in `upstream-claims`, four journeys in `integrated-journeys`). The pre-merge `upstream-claims 181` figure above is the two-table sum recorded on this branch; the merged stage sums all three tables to 220.

Commands actually run after the merge:

- `python3 scripts/sim_journeys.py`: exit 0, `sim journeys ok SIMULATED T03-sim steps=22 T04-sim steps=38 T05-sim steps=35 T06-sim steps=33`; all four goldens still pin (check mode, nothing rewritten).
- `python3 -m unittest tests.test_sim_journeys -v`: exit 0, **32 passed** (13.5s).
- `python3 -m unittest discover -s tests -v`: exit 0, **710 passed** (103.0s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. The five vendored files match `capital/vendor/manifest.json` SHA256.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (29 routes, 20 artifacts, 9 stages). `python3 scripts/seed_demo.py`: ok, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged.
- `npm run test:browser` (Chromium from the default `~/.cache/ms-playwright` install): exit 0, **62 passed** (1.8m); no server left running.
- `python3 scripts/acceptance.py`: exit 0, evidence `build/acceptance-evidence.json` `ok` true; unit 710, storage-conformance 7, pinned-vendor 7, upstream-claims `passed=220 failed=0` (`CLAIM_CONFORMANCE`), node-check pass, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 4 (T03-sim 22, T04-sim 38, T05-sim 35, T06-sim 33 steps, all `SIMULATED`).
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output.

Second merge with main (2026-10-20; main had gained cashflow-forecast and gate-fake-fault-corpus): one conflict, docs only, add-only, neither side dropped. This file keeps main's `cashflow-forecast` section before this one. Everything else merged cleanly: `capital/forecast.py`, `capital/terms.py` (additive `expected_settlement_cash_day` kwarg), `capital/server.py`, `capital/service.py`, `capital/gate_producer.py`, `capital/contract/facade-v1.json`, `scripts/forecast_vectors.py`, `scripts/gate_faults.py`, `scripts/fake_gate.py`, `scripts/auth_matrix.py`, `scripts/docs_surface.py`, `tests/test_cashflow_forecast.py`, `tests/test_gate_faults.py`, `tests/test_facade_contract.py`, `tests/test_finance_vectors.py`, `tests/auth_matrix.json`, `tests/vectors/forecast_vectors.json`, `tests/vectors/gate_faults.json`, `tests/vectors/finance_vectors.json`, `README.md`, `docs/INTEGRATION.md`, `docs/OPERATOR_HANDBOOK_KO.md`, `docs/CAPITAL_REQUIREMENTS_KO.md` and `docs/SEAMS.md`. The four-journey `integrated-journeys` stage and the three-table `upstream-claims` stage are unchanged.

Commands actually run after the second merge:

- `python3 scripts/sim_journeys.py`: exit 0, `sim journeys ok SIMULATED T03-sim steps=22 T04-sim steps=38 T05-sim steps=35 T06-sim steps=33`; all four goldens still pin (check mode, nothing rewritten).
- `python3 -m unittest tests.test_sim_journeys -v`: exit 0, **32 passed** (13.9s).
- `python3 -m unittest discover -s tests -v`: exit 0, **733 passed** (123.9s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. The five vendored files match `capital/vendor/manifest.json` SHA256.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (29 routes, 22 artifacts, 9 stages). `python3 scripts/seed_demo.py`: ok, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged. `python3 scripts/forecast_vectors.py --check` (6456 bytes), `scripts/finance_vectors.py --check` (91570 bytes), `scripts/gate_faults.py --check` (7 cases), `scripts/auth_matrix.py --check` and `scripts/not_bound_checklist.py --check`: exit 0; no regeneration needed.
- `npm run test:browser` (Chromium from the default `~/.cache/ms-playwright` install): exit 0, **62 passed** (1.8m); no server left running.
- `python3 scripts/acceptance.py`: exit 0, evidence `build/acceptance-evidence.json` `ok` true; unit 733, storage-conformance 7, pinned-vendor 7, upstream-claims `passed=220 failed=0` (`CLAIM_CONFORMANCE`), node-check pass, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 4 (T03-sim 22, T04-sim 38, T05-sim 35, T06-sim 33 steps, all `SIMULATED`).
- `git diff --name-only origin/main -- capital/vendor .aiops .github docs/decisions`: no output.

## fold-fuzz-determinism

Verification-only node: `scripts/fold_fuzz.py` plus the pinned corpus `tests/vectors/fold_fuzz.json` (format `KIX_CAPITAL_FOLD_FUZZ_V1`, label `SIMULATED`). Fixed LCG32 generator (`LCG32-LIFECYCLE-1`, seeds 74810048–74810063, ≤64 commands, six advances per seed) deterministically interleaves legal lifecycle heads covering all ten F04 operations, bound/unbound draws, partial/full repayment, close/default/reject/cancel and logical-day ticks; every seed produces 46 commands (736 total). For each seed the identical sequence is replayed through two fresh `FileWorkspace` directories with separate services and producers; per-prefix checkpoints pin `state_digest`, `overlay_state_digest`, `envelope_sha256`, `receipts_sha256` and `overlay_receipts_sha256`, and the two runs' raw `workspace.json` bytes are compared directly. Copied F04 journals and overlay entries are refolded independently each step; every completed sequence is closed and reopened with a fresh session identity to verify receipt/fingerprint mappings, overlay receipt cores and unchanged file bytes. Synthetic writer identity and the clock replacement are scoped to `capital.store` during saves; envelope byte equality is claimed only under those fixed inputs on the same interpreter and tree. `--check` exits 1 on any command/digest/byte drift and rewrites nothing; `--write` authors only this new corpus; `--file` isolates mutation tests. No `capital/` change, no new command semantics, rejection codes, routes or goldens; no durability or performance claim; CAP-11 stays `NOT_BOUND`. Complements the crash matrix (sequence-order determinism, not crash boundaries).

Commands actually run:

- `python3 -m unittest tests.test_fold_fuzz -v`: exit 0, **12 passed** (86.2s) — generator pins, coverage/legality, independent replays and reloads across `PYTHONHASHSEED` values 1 and 987654321, drift/malformed/no-rewrite checks, capacity-NOT_BOUND and unexpected-rejection failure modes.
- `python3 scripts/fold_fuzz.py --check`: exit 0, `fold fuzz ok SIMULATED: 16 seeds, 736 commands`.
- `python3 scripts/docs_surface.py --check`: exit 0, `docs surface ok: 29 routes, 39 artifacts, 9 stages`.
- `python3 tests/crash_matrix.py --check`: exit 0, `crash matrix vectors ok: 23 cells match`. `python3 scripts/workspace_vectors.py --check`: exit 0, `workspace vectors ok: 6 files match`.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged.
- `python3 -m unittest discover -s tests -v`: exit 0, **817 passed** (193.5s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. All five vendored files match `capital/vendor/manifest.json` SHA256.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `npm run test:browser` (Chromium from `~/.cache/ms-playwright`): exit 0, **62 passed** (2.0m); playwright webServers stopped, none left running.
- `python3 scripts/acceptance.py`: exit 0, evidence `build/acceptance-evidence.json` `ok` true; unit 817, storage-conformance 19, pinned-vendor 7, upstream-claims `passed=220 failed=0`, node-check pass, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 4.
- `git status --short` after all runs: only `README.md`, `docs/INTEGRATION.md`, `docs/VALIDATION.md`, `scripts/docs_surface.py` modified; new `scripts/fold_fuzz.py`, `tests/test_fold_fuzz.py`, `tests/vectors/fold_fuzz.json`. No `capital/`, `.aiops/`, golden or `docs/decisions` change.

## lifecycle-claims-conformance — prior builder evidence (2026-10-23)

Historical run below: its baseline integration blocker is superseded by the
supervisor-authorized main merge and the 2026-10-24 verification recorded below.

Completed the interrupted implementation with twelve executable local lifecycle
analogues in `capital/lifecycle_claims.py`, `tests/lifecycle_claims.json`, and
`scripts/lifecycle_claims_check.py`. Every row and report carries
CLAIM_CONFORMANCE / SIMULATED / funds_executed false. State, receipt and scenario
non-execution flags are asserted against actual responses. The harness uses
stdlib HTTP on disposable 127.0.0.1 servers, temporary workspaces, an event barrier
for dropped replies, explicit shutdown/close/join, and no external services.

| Contract mapping | Executed observation |
|---|---|
| LC-TERM first results | Accepted and business-rejected first receipts survive duplicate submissions; after the rejected command the missing case is successfully created. Changed arguments return IDEMPOTENCY_CONFLICT. Duplicates/conflicts invoke the producer zero times. |
| LC-TERM UNKNOWN | A lost reply remains unresolved across synthetic elapsed time and state reads; only receipt lookup resolves it, returning the exact dropped receipt. Producer TransportLost remains UNKNOWN across repeated absent-receipt reads. |
| LC-CUT retry boundary | The SIMULATED client fences resubmission and emits one original POST; recovery uses GET only. This is client-owned fencing, not a global server prohibition. |
| LC-TERM absent receipt | Repeated lookup of a never-submitted ID returns UNKNOWN and retry_authorized false, with no command POST, journal, receipt or overlay change. |
| LC-CUT local fences | Stale instance command/lookup fail; after restart the old token fails and a fresh token cannot bypass the old instance fence. Local instance IDs are not distributed lease generations or C_g/H_g. |
| LC-CUT restoration | Workspace replay restores the original writer receipt, journal, overlay and state in a new instance with zero producer applications and zero new command POSTs. |
| LC-FACT late facts | The existing late-cash READ_ONLY_FIXTURE retains confirmed but unallocated cash after cancellation, preserves cancelled obligations, and leaves the active book unchanged. This is not provider evidence custody or ingestion. |

The read-only Protocol checkout currently has HEAD
`d84cc50f78a37420ca9d12752ac23f9f9b51c5fc`. The lifecycle source pin from the
interrupted attempt, `e2313ab473ea1b5a7b5b9246a564749188c1c2c8`, exists, and
`git -C /workspace/capital-run/kixproto-ro diff e2313ab473ea1b5a7b5b9246a564749188c1c2c8 -- docs/contracts/STATE_LIFECYCLE.md`
returned exit 0 with no diff. The checker verifies the file against that commit's
exact Git blob, then checks headings and section-local needles. A missing
checkout reports citation SKIPPED even when behavior execution passes. This
source pin is separate from the unchanged 7481b0e FSM vendor pin.

The existing upstream-claims stage runs lifecycle checks fourth and aggregates
failures. Existing stage-count tests, README, integration/requirements/handbook
docs, and the docs-surface registry were extended accordingly. The claim table
lives outside tests/vectors. No facade semantics, routes, golden fixtures, CI
requirements, vendor files, Protocol/Commerce, or .aiops files were changed.
CAP-11/CAP-16, operational closure, provider custody, distributed fencing and
stage5 durability remain NOT_BOUND/out of scope.

The first narrow run exposed two failures and one error caused by the harness
sending an empty token header on bootstrap; the existing facade rejects that
header. The fix omits the token until the normal state response supplies it.
No facade behavior or expectation was weakened. Prior socket-denial evidence
from the interrupted attempt is superseded by this environment's actual loopback
execution below. No financial product values or external access were required.
Baseline integration now requires supervisor action, recorded in root `DECISION_REQUIRED.md`; the
existing byte guard and overlay implementation remain unchanged.

Commands actually run in this continuation (all local simulation):

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_lifecycle_claims tests.test_acceptance tests.test_docs_surface -v` | Initial exit 1: 29 tests, two failures and one error from the bootstrap bug. After the fix: exit 0, 29 passed. After strengthening duplicate and dropped-receipt observations: exit 0, 29 passed again. |
| `npm ci --offline --ignore-scripts --no-audit --no-fund --cache /tmp/capital-dossier-npm-cache` | Exit 0; three pinned packages installed from the existing local cache; lockfile unchanged. Existing Chromium was available. |
| `python3 scripts/lifecycle_claims_check.py` | Exit 0; citation SKIPPED, verified=0/12, no behavior success count. |
| `python3 scripts/lifecycle_claims_check.py --execute` | Exit 0; behavior passed=12 total=12 failed=0; citation SKIPPED. |
| `python3 scripts/lifecycle_claims_check.py --execute --protocol-dir /workspace/capital-run/kixproto-ro` | Exit 0; behavior 12/12 and pinned citations verified=12/12. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 29 routes, 38 artifacts, nine stages. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital` | Exit 0. |
| `node --check capital/static/app.js` | Exit 0. |
| Python SHA256 and `git show HEAD:capital/vendor/<file>` byte comparisons for every manifest entry and manifest.json | Exit 0; all five SHA256 locks and baseline bytes match; manifest unchanged. |
| `git diff --check` | Exit 0. |
| `python3 -m unittest discover -s tests -v` | Exit 1; 821 run, 820 passed, one existing baseline-guard failure: capital/overlay.py differs from origin/main despite being unchanged from this worktree HEAD. |
| `python3 -m unittest tests.test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched -v` | Exit 1; import error because this existing test imports test_overlay as a sibling. The corrected invocation below reaches the guard. |
| `PYTHONPATH=tests:. python3 -m unittest test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched -v` | Exit 1; independently reproduces the same baseline-guard failure. |
| `npm run test:browser` | Exit 0; all 62 Chromium browser tests passed (1.6m). |
| `python3 scripts/build_release.py --out build/lifecycle-dist-a` and `python3 scripts/build_release.py --out build/lifecycle-dist-b` | Both exit 0; identical SHA256 079b6720ae1ee1ba2c53e38eb023c0d035bd7a4073b8b7b153801a62e975abf0. |
| `cmp build/lifecycle-dist-a/capital-*.pyz build/lifecycle-dist-b/capital-*.pyz` | Exit 0; reproducible package bytes. |
| `python3 scripts/smoke_release.py build/lifecycle-dist-a/capital-*.pyz` | Exit 0; all eight smoke checks passed. |
| `python3 -m unittest tests.test_lifecycle_claims tests.test_acceptance tests.test_docs_surface tests.test_agent_claims tests.test_read_model_claims tests.test_handbook -v` | Exit 0; 64 passed after final README and documentation updates. |
| `python3 scripts/acceptance.py` | Exit 1; evidence.ok=false solely from the unchanged baseline guard (unit 820/821). All remaining stages passed: storage 19, vendor 7, upstream claims 232, node syntax, browser 62, packaged smoke 8, seeded demo 1 and integrated journeys 4. |
| Python /proc command-line check restricted to Python Capital/fake-gate servers | Exit 0; no servers remain after verification. |

`build/acceptance-evidence.json` contains the actual commands, captured results
and nonzero unit-stage status. It is an ignored local artifact. The independent
full-suite run and acceptance rerun both reproduce the same sole baseline guard
failure. Root `DECISION_REQUIRED.md` gives the evidence, integration options,
recommendation and decision owner. No tests or guards were weakened, no refs were
moved, and no commits or remote actions were performed.

## ce1-canonical-claims

A fourth pinned claim table `tests/ce1_claims.json` (format `KIX_CAPITAL_CE1_CLAIMS_V1`, 49 rows) binds the pinned `docs/CANONICAL_ENCODING_V1.md` byte rules (kix-protocol `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, the vendor pin; the spec text at that commit is byte-identical to the current checkout's) to Capital's canonical JSON (`capital/store.py` `canonical_bytes`) and digest framing. Each row cites a CE1 section and verbatim needle, carries an `input` form, and names one `ce1.*` check in `capital/ce1_claims.py`: canonical-bytes recomputation (`ce1.encode`), rejection-before-hashing (`ce1.reject`: duplicate and escaped-duplicate keys, NaN/Infinity/-Infinity, fractions, exponents, -0, out-of-range integers, non-ASCII/empty/out-of-grammar keys, non-NFC strings, lone surrogates, >262,144-byte and >64-deep inputs, BOM and NUL bytes, trailing garbage), digest outputs (`ce1.plain_digest`, `ce1.framed_digest`, `ce1.part_tag_digest`), the domain-tag machine-ID grammar (`ce1.domain_tag`), and the digest-family equivalence (`ce1.digest_family`: `service.digest`, `export.sha256_hex` and the workspace checksum are all SHA-256 over the same canonical bytes). The binding gate `decode_input` applies the CE1 input rules before any `canonical_bytes`/digest call; it changes no encoder and does not enforce the pinned Unicode-15.0 assigned-scalar repertoire (that range table is not vendored; NFC and scalar validity are enforced and no row claims repertoire enforcement). The `ensure_ascii` escaping divergence is recorded in four `DOCUMENTED_DIVERGENCE` rows whose checks re-verify the §3.4 rationale needle in `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`; the CE1 `KIX-CE1\0<domain>\0` wire frame is stage-7 adapter scope and no row claims it. `scripts/ce1_claims_check.py` mirrors the upstream CLI (bare → `SKIPPED`, never a pass; `--protocol-dir` read-only). `scripts/acceptance.py` runs it as the fourth command of the unchanged `upstream-claims` stage; the stage sums 87+94+39+49=269. `tests/test_ce1_claims.py` adds 14 tests; the agent/read-model stage tests and `test_handbook.py` now assert the fourth command and the 269 total. Results are SIMULATED and labelled CLAIM_CONFORMANCE, never SEMANTIC_CONFORMANCE. Nothing under `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/` was edited.

Commands actually run, in order:

- `python3 scripts/ce1_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=49 total=49 failed=0`.
- `python3 scripts/ce1_claims_check.py`: exit 0, first line `SKIPPED`, JSON status `SKIPPED` label `CLAIM_CONFORMANCE`, no success count.
- `python3 scripts/ce1_claims_check.py --protocol-dir /workspace/capital-run/kixproto-ro`: exit 0, `CLAIM_DRIFT verified=49 total=49`; the checkout was read only. `--execute --protocol-dir` together also exit 0.
- `python3 -m unittest tests.test_ce1_claims -v`: exit 0, **14 passed** (2.3s). The stage run inside it recorded `upstream-claims passed=269`.
- `python3 -m unittest tests.test_ce1_claims tests.test_handbook tests.test_agent_claims tests.test_read_model_claims tests.test_upstream_claims tests.test_acceptance`: exit 0, **65 passed** — after the fourth stage command was added and the agent/read-model stage sums were extended to 87+94+39+49=269.
- `python3 -m unittest discover -s tests -v`: exit 0, **819 passed** (149.7s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check`: ok (29 routes, 38 artifacts, 9 stages). `python3 scripts/decision_bindings.py --check`: exit 0.
- `npm ci --no-audit --no-fund`: exit 0, 3 packages. `npm run test:browser` (run inside the acceptance ladder, Chromium from `~/.cache/ms-playwright`): **62 passed**; no server left running.
- `python3 scripts/acceptance.py`: exit 0, evidence `build/acceptance-evidence.json` `ok` true; unit 819, storage-conformance 19, pinned-vendor 7, upstream-claims `passed=269 failed=0` (`CLAIM_CONFORMANCE`), node-check pass, browser 62, packaged-smoke 8, seeded-demo 1, integrated-journeys 4.
- `git status`: no `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/` modifications.

Portfolio consistent read: `python3 -m unittest tests.test_portfolio_snapshot -v` covers detached-input component parity, independent cut digests, read-only workspace bytes, deterministic snapshots across sessions, controlled reader/writer ordering for repayment and clock commands, unsupported producers/fixtures, degraded storage, unbound terms, identity, authorization and closed facade schemas. `python3 scripts/docs_surface.py --check` guards the route documentation and the auth matrix includes the route. All data is SIMULATED; no authenticated or cross-process source cut is claimed.

## producer-tuple-preflight

An offline stdlib rehearsal of the exact `kix-compat-manifest/1` producer-tuple check. `capital/compat_preflight.py` validates a synthetic bundle (`tests/vectors/compat/bundle/`, `READ_ONLY_FIXTURE`: miniature OpenAPI contract files, inert generator/SDK bytes, profile, vector, toolchain metadata, manifest and `.sha256` sidecar) against a separately pinned expected tuple (`tests/vectors/compat/expected.json`, format `capital-compat-expected/1` — an external `manifest_sha256` plus the complete manifest tuple). The tuple comparison is exact on types, field sets, values and vector order; every leaf has a one-field mismatch case enumerated in `tests/vectors/compat/mismatches.json`. The checker then independently validates referenced bytes: SHA-256 of every reference, Git blob SHA-1 framing on contract and extension-profile references, the profile path derived from `profile_revision`, the BOOTSTRAP `catalogue-schema-binding only` grant, the catalogue OpenAPI binding and per-schema digest map, `toolchains.json` Node major against declared `node-24`, canonical vector bytes and the sidecar digest. Generator and SDK files are hashed, never executed. Duplicate keys (including `\u`-escaped aliases), forbidden self-digest/finality fields, missing files, non-regular files, absolute/traversal paths and escaping symlinks are rejected; every bundle-controlled path must resolve beneath the fixture root. `kix-canonical-json/1` is implemented here separately from `capital/store.py` legacy canonical bytes and `capital/ce1_claims.py`: Unicode code-point key order, JSON.stringify-compatible escaping that keeps non-ASCII literal, safe integer range, verifier depth limit 32, no trailing newline. The cited contract is `docs/contracts/sdk/COMPATIBILITY_MANIFEST_V1.md` at Protocol research commit `9b462fd2cd6890cd0d8fbc2930f2cc54255e2915` (file SHA-256 `126a8b95e2216dc9d4cc4e8e8d7a3f221657c40c5e0e07e5819a58a7c1987533`, Git blob `442756c8e2d6f106fad6a47a7177c05ed799efaf`); it is a read-only research reference and the executable vendor pin stays `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`.

The opt-in factory `make_preflighted_fake_producer(root, manifest_path, expected_path)` in `capital/gate_producer.py` runs the check first and only then constructs the owned `LOCAL_FAKE_GATE`; a `MISMATCH` raises `PreflightRejected` before the constructor or `start()` runs, so the first command POST is never attempted (a running fake's `post_count` stays zero). `restored()` carries the frozen inputs and rechecks before starting the replacement gate. A byte-consistent bundle keeps `semantic_consumption` `HOLD`, `adoption` `NOT_BOUND` and `semantic_conformance` `false`; a self-declared `SEMANTIC_CONFORMANCE` profile kind cannot authorize anything and is refused with `BOOTSTRAP_REHEARSAL_ONLY`. Reports are labelled `SIMULATED`. `scripts/compat_preflight.py --check` verifies the committed corpus (`corpus.json` pins the file inventory and every digest) and the canonicalization vectors; it writes nothing and exit 0 means byte checks passed only. No generated SDK is consumed, no real producer is contacted, no upstream repository or executable pin changes, and CAP-16 stays `NOT_BOUND`. Nothing under `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/` was edited. This section claims no semantic qualification, no Commerce adoption, no human acceptance, no GitHub CI run, no commit, no push, and no deploy.

Commands actually run:

- `python3 scripts/compat_preflight.py --check`: exit 0, report `byte_agreement` `MATCHED`, `profile_kind` `BOOTSTRAP`, `manifest_sha256` `3b98a3f2…`, zero errors.
- `python3 -m unittest discover -s tests -p 'test_*preflight.py' -v`: exit 0, **19 tests** (14 checker + 5 gate preflight).
- `python3 scripts/gate_faults.py --check`: exit 0, 7 cases match the pinned corpus.
- `python3 scripts/ce1_claims_check.py --execute`: exit 0, `CLAIM_CONFORMANCE passed=49 total=49 failed=0`.
- `python3 scripts/manifest_vectors.py --check` (19 files), `python3 scripts/workspace_vectors.py --check` (6 files), `python3 scripts/pack_vectors.py --check` (9 files), `python3 scripts/finance_vectors.py --check` (92734 bytes), `python3 scripts/forecast_vectors.py --check` (6456 bytes), `python3 scripts/decision_bindings.py --check`: all exit 0.
- `python3 scripts/docs_surface.py --check`: ok (30 routes, 54 artifacts, 9 stages) after registering `compat/` in `VECTOR_NEEDLES` and the README needles.
- `python3 scripts/seed_demo.py`: exit 0, golden digests unchanged.
- `python3 -m unittest discover -s tests -v`: exit 0, **859 passed** (174.7s).
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**.
- `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `npm ci --no-audit --no-fund`: exit 0, 3 packages. `npm run test:browser`: exit 0, **69 passed** (2.5m); Playwright started and stopped its loopback servers.
- Vendored `capital/vendor/` SHA256 values all match `manifest.json` (five files OK); `git status` shows no change under `capital/vendor/`, `.aiops/`, `.github/` or `docs/decisions/`.

## lifecycle-claims-conformance — merge completion and verification (2026-10-24)

Historical evidence from the preceding merge round follows; the conflict-fix
round 1 entry below records the current combined tree and supersedes its command
positions and counts.

The supervisor-supplied six conflicts in README, operator handbook, validation,
acceptance, agent claims tests and read-model claims tests are resolved, retaining
both lifecycle and CE1 additions. The existing `upstream-claims` stage now runs
five commands and aggregates 87+94+39+49+12=281 behavior claims. Plan deviation:
CE1 retains main's fourth position; lifecycle runs fifth. No lifecycle semantics,
facade routes, browser implementation, export construction or CI requirements
were changed by this node.

The first full run found that the supplied pending merge targeted `8c5ad10`,
while the local `origin/main` had advanced to `97b636a`. Its sole failure was the
live baseline guard for `capital/ports.py` and
`docs/decisions/CAPITAL_UPSTREAM_BINDING.md`. A read-only three-way preview, then
application, incorporated the 23 intervening main file updates without a
conflict, retaining this node's additions. The guarded files and
`tests/test_coa_candidate.py` are byte-identical to current main; no guard was
hand-edited or weakened. The final diff against current main contains only the
17 lifecycle implementation, integration, regression and documentation files.
The original pending merge metadata is retained for the supervisor: MERGE_HEAD
is `8c5ad101dc9ba3d2f96a214b8aa6d4ab6116808f`, and incorporated main content is
`97b636ab2bdaf5aae52882129bd6ed11e16869aa`. No commit or branch ref was created
or moved; the supervisor owns final merge ancestry and committing.

The twelve loopback checks retain CLAIM_CONFORMANCE / SIMULATED /
funds_executed false. The lifecycle document still matches the exact blob at
`e2313ab473ea1b5a7b5b9246a564749188c1c2c8`; citations verify headings and
section-local needles independently of behavior execution. Without a checkout,
citation verification is SKIPPED, including with `--execute`. These remain local
analogues, with synthetic client-owned UNKNOWN fencing and an existing
READ_ONLY_FIXTURE late-cash scenario, not operational LC-TERM closure, provider
custody, distributed fencing, stage5 durability or SEMANTIC_CONFORMANCE.

Commands actually run in this continuation (results below are local simulation):

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_lifecycle_claims tests.test_acceptance tests.test_docs_surface -v` | Exit 0; 30 passed after resolving the supplied conflicts. |
| `python3 -m unittest tests.test_lifecycle_claims tests.test_acceptance tests.test_docs_surface tests.test_agent_claims tests.test_read_model_claims tests.test_ce1_claims tests.test_handbook -v` | Exit 0; 79 passed before and after incorporating newer main. Actual upstream stage executions aggregate 281/281. |
| `python3 scripts/lifecycle_claims_check.py` | Exit 0; SKIPPED, verified=0/12; no behavior pass count. Repeated after main integration with the same result. |
| `python3 scripts/lifecycle_claims_check.py --execute` | Exit 0; behavior 12/12; citation SKIPPED. Repeated after main integration with the same result. |
| `python3 scripts/lifecycle_claims_check.py --execute --protocol-dir /workspace/capital-run/kixproto-ro` | Exit 0; behavior 12/12, pinned citations verified=12/12. Repeated after main integration with the same result. JSON labels and exact false non-execution flags also checked. |
| `python3 scripts/docs_surface.py --check` | Exit 0; final surface is 30 routes, 40 artifacts, nine stages (newer main supplies two of those artifacts). |
| `python3 scripts/decision_bindings.py --check` | Exit 0; declared references valid, pending anchors not claimed as implementation. |
| `python3 -m unittest discover -s tests -v` | First run: exit 1, 903 run, 902 passed, the single moving-baseline guard failure described above. After integrating newer main: exit 0, all 972 passed in 172.017s. |
| `PYTHONPATH=tests:. python3 -m unittest test_coa_candidate.V1UnchangedTests -v` | Exit 0; five passed after main integration, including the live baseline and append-only port guards. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed, repeated after main integration. |
| `python3 -m compileall -q capital` | Exit 0, repeated after main integration. |
| `node --check capital/static/app.js` | Exit 0, repeated after main integration. |
| `npm ci --offline --ignore-scripts --no-audit --no-fund` | Exit 0; three pinned packages installed from the local cache; package lock unchanged. Existing Chromium was available. |
| `npm run test:browser` | Exit 1 before tests: unrelated services in other workspaces own ports 8765 and 8766. They were identified read-only and left running. |
| `npm run test:browser -- --config build/lifecycle-playwright.config.cjs` | Exit 0; all 69 Chromium tests passed in 2.2m, including browser UNKNOWN/restart regressions. |
| Python heredoc: SHA256 every vendor manifest entry and compare all five files plus manifest bytes with `git show HEAD:...`, `MERGE_HEAD:...`, and `origin/main:...` | Exit 0; all locks and baseline bytes match; manifest unchanged. Protocol source blob identity was also checked read-only. |
| `git diff --check` and `git diff --check origin/main` | Exit 0; no whitespace issues in this node's changes. |
| `git diff --cached --check` | Exit 2 on three pre-existing Markdown hard-break lines in main's imported `docs/decisions/CAPITAL_UPSTREAM_REPINS.md`; that file is preserved byte-for-byte from main. This is outside the node diff and is not a CI failure. |
| `git ls-files -u` | Exit 0, empty: all supplied conflicts resolved. |

Local browser-port deviation: ignored
`build/lifecycle-playwright.config.cjs` imports the checked-in config and changes
only the four web-server ports/URLs from 8765–8768 to 18765–18768, plus absolute
paths needed for its location under build. It preserves every project, test,
assertion, worker count, timeout and server cleanup rule. Ignored
`build/lifecycle_acceptance.py` loads the existing `scripts/acceptance.py` plan
and appends only `-- --config build/lifecycle-playwright.config.cjs` to its npm
browser command. It preserves all nine required stages and their checks,
aggregation, timeouts and failure handling. These local helpers avoid stopping
unrelated services; they do not alter the checked-in CI configuration.

The first `python3 build/lifecycle_acceptance.py` run exited 1: unit 972,
storage 19, vendor 7, claims 281, JavaScript syntax, packaged smoke 8, seeded demo
1 and integrated journeys 4 all passed, but Chromium reported 68 passed and one
readiness initial-loading timeout. Its actual evidence is retained separately in
ignored `build/lifecycle-acceptance-first.json`. The trace showed successful
initial GETs and pending later GETs at the assertion timeout, not a business
outcome mismatch. Focused rerun command
`npm run test:browser -- --config build/lifecycle-playwright.config.cjs --grep 'readiness separates local capability'`
exited 0 (one passed, test duration 1.3s). No assertion, application behavior or
timeout was changed for the fresh full ladder rerun.

Node files changed against current main:

- Core: `capital/lifecycle_claims.py`, `tests/lifecycle_claims.json`, `scripts/lifecycle_claims_check.py`, `tests/test_lifecycle_claims.py`.
- Integration: `scripts/acceptance.py`, `scripts/docs_surface.py`.
- Existing regression tests: `tests/test_acceptance.py`, `tests/test_agent_claims.py`, `tests/test_read_model_claims.py`, `tests/test_ce1_claims.py`, `tests/test_docs_surface.py`, `tests/test_handbook.py`.
- Documentation: `README.md`, `docs/INTEGRATION.md`, `docs/CAPITAL_REQUIREMENTS_KO.md`, `docs/OPERATOR_HANDBOOK_KO.md`, `docs/VALIDATION.md`.

Final ladder rerun and cleanup:

| Command | Result |
|---|---|
| `python3 build/lifecycle_acceptance.py` | Fresh full rerun: exit 0; all nine stages passed. Unit 972, storage-conformance 19, pinned-vendor 7, upstream claims 281, node syntax pass, Chromium 69, packaged smoke 8, seeded demo 1, integrated journeys 4. |
| Python heredoc: inspect `build/acceptance-evidence.json`, verify vendor SHA256/baseline bytes, scan `/proc` for this worktree's Capital/fake-gate/zipapp servers, verify branch/HEAD and unresolved index entries | Exit 0; evidence `ok: true`, SIMULATED, funds_executed false, integrated false; all nine statuses passed; all five vendor locks and manifest unchanged; no servers remain; branch/HEAD unchanged; no unresolved conflicts. Unrelated services were left running. |

Final successful aggregated evidence is the ignored local
`build/acceptance-evidence.json`; the earlier unsuccessful ladder evidence remains
`build/lifecycle-acceptance-first.json`. The scripts, logs and evidence above
record actual executions. No test was skipped or weakened to obtain this result,
no product decision was invented, and no Protocol, Commerce, vendor or `.aiops/`
content was modified. No commit, push, PR, issue, comment, deployment or external
financial/provider operation was performed.

After recording the final results, `python3 scripts/docs_surface.py --check`
exited 0 (30 routes, 40 artifacts, nine stages),
`python3 -m unittest tests.test_docs_surface -v` exited 0 (nine passed), and
`git diff --check origin/main` exited 0. All 17 node files are recorded in the
index for supervisor review; no commit was created.

## adapter-identity-claims

The fifth `CLAIM_CONFORMANCE` table is `tests/adapter_identity_claims.json`
(`KIX_CAPITAL_ADAPTER_IDENTITY_CLAIMS_V1`, 30 rows). Its own pin is
`e2a029d8ac3af7575888dac22fc4bf173ebec232`; the read-only protocol checkout's
`docs/contracts/ADAPTER_EVENT_IDENTITY.md` SHA256 matches
`e640151bbdff15b67584337e6cdb6e95b2cc9c060f48dcc9de45df84f8de5345`.
The rows execute the ObservationPort fake and explicitly labelled loopback facade
analogues. Conflict diagnostics retain original and incoming facts; original
replay leaves CONFLICT in place, and UNMATCHED binding survives that conflict.
No kernel behavior or SEMANTIC_CONFORMANCE is claimed. Results are SIMULATED.
The method-content fixture divergence remains explicit, and provider/account/
profile-version facade evidence is ISOLATION_ONLY. No upstream or financial
choice was made.

Commands actually run on working tree HEAD `97b636ab2bdaf5aae52882129bd6ed11e16869aa`
(uncommitted node changes; this records local evidence, not CI or independent review):

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_adapter_identity_claims -v` | exit 0, 16 tests passed |
| `python3 -m unittest tests.test_adapter_identity_claims tests.test_agent_claims tests.test_read_model_claims tests.test_ce1_claims tests.test_handbook tests.test_upstream_claims tests.test_observation_port tests.test_coa_candidate -v` | first run: 82 tests, 2 failures and 2 errors; second run after count-line fix: 82 tests, 2 import errors |
| `PYTHONPATH=tests:. python3 -m unittest tests.test_adapter_identity_claims tests.test_agent_claims tests.test_read_model_claims tests.test_ce1_claims tests.test_handbook tests.test_upstream_claims tests.test_observation_port tests.test_coa_candidate -v` | exit 0, 117 passed (28.022s) |
| `python3 scripts/adapter_identity_claims_check.py` | exit 0, first line SKIPPED; no passed count |
| `python3 scripts/adapter_identity_claims_check.py --execute` | exit 0, CLAIM_CONFORMANCE passed=30 total=30 failed=0; RESULTS SIMULATED |
| `python3 scripts/adapter_identity_claims_check.py --protocol-dir /workspace/capital-run/kixproto-ro` | exit 0, CLAIM_DRIFT verified=30 total=30; SOURCE_SHA256 match; checkout read only |
| `npm ci --no-audit --no-fund` | exit 0, 3 packages installed; cached Chromium available |
| `python3 -m compileall -q capital` | exit 0 |
| `node --check capital/static/app.js` | exit 0 |
| `python3 scripts/docs_surface.py --check` | exit 0, 30 routes, 40 artifacts, 9 stages |
| `python3 scripts/observation_vectors.py --check` | exit 0, SIMULATED observation vectors PASS; NOT_BOUND; applied=false; funds_executed=false |
| Python stdlib SHA256 comparison of all five `capital/vendor/manifest.json` entries | all five match |
| `git diff --name-only HEAD -- capital/vendor .aiops docs/decisions` | empty |
| `git diff --check` | exit 0 |

Plan adjustments: the existing acceptance parser requires its count line to end
at `failed=N`; the checker prints `RESULTS SIMULATED` on a separate line. Existing
`test_observation_port` and `test_coa_candidate` use top-level `test_overlay`
imports, so the plan's named-module narrow command requires `PYTHONPATH=tests:.`.
Full discovery supplies that path itself. The first two runs above record those
failures without weakening tests. Existing vector artifacts need no new
`docs_surface.py` entries.

The first `python3 scripts/acceptance.py` run exited 1 (`ok=false`): unit 972,
storage-conformance 19, pinned-vendor 7, upstream-claims 299, node-check,
packaged-smoke 8, seeded-demo 1 and integrated-journeys 4 all passed. Browser
startup failed with `OSError: [Errno 98] Address already in use`. Read-only
`ss -ltnp` and process/cwd inspection identified unrelated services on loopback
8765 and 8766; neither was stopped. `unshare --user --map-root-user --net true`
succeeded, so verification uses an isolated loopback network:
`unshare --user --map-root-user --net bash -c 'ip link set lo up && python3 scripts/acceptance.py'`.
This preserves the test suite, fixed Playwright configuration, nine stages and
timeouts. No artifacts were regenerated from the failed run.

The first isolated run also exited 1 (`ok=false`): browser **69 passed**, and all
non-unit stages passed, but unit exited 124 at the unchanged 300-second limit.
No artifacts were written. Diagnostics:

- `unshare --user --map-root-user --net bash -c 'ip link set lo up && timeout 60 python3 -m unittest discover -s tests -p test_gate_faults.py -v'`: exit 0, 7 passed (32.958s).
- An isolated `scripts.gate_faults.run_corpus()` call with a 45-second bound and
  traceback timer returned `ok=True`, 7 cases, no findings.
- `python3 -m unittest discover -s tests -p test_gate_faults.py -v`: exit 0,
  7 passed (36.741s).
- `unshare --user --map-current-user --keep-caps --net` with loopback enabled and
  `setpriv --inh-caps=-all --ambient-caps=-all --bounding-set=-all` verified the
  original UID 1000 and zero inherited/permitted/effective/bounding/ambient
  capabilities before test execution. Subsequent isolated runs use this form;
  no timeout, assertion, or test selection was changed.

Fresh successful acceptance (before regeneration):

| Command | Result |
|---|---|
| `unshare --user --map-current-user --keep-caps --net bash -c 'ip link set lo up && setpriv --inh-caps=-all --ambient-caps=-all --bounding-set=-all python3 scripts/acceptance.py'` | exit 0, `ok=true`; all 9 stages passed: unit 972, storage-conformance 19, pinned-vendor 7, upstream-claims 299, node-check, browser 69, packaged-smoke 8, seeded-demo 1, integrated-journeys 4 |
| `python3 scripts/closeout_digest.py --write` | exit 0, generated 4462 bytes from that successful evidence |
| `python3 scripts/finance_vectors.py --write` | exit 0, generated 97186 bytes |

Only after those writes was the fifth expected command added to the independent
`tests/test_closeout_digest.py` STAGES list, as planned. The first successful raw
evidence was saved separately for a later comparison. The two committed vector
files were generated by their tools, never hand-edited.

Second successful acceptance and final checks:

| Command | Result |
|---|---|
| `unshare --user --map-current-user --keep-caps --net bash -c 'ip link set lo up && setpriv --inh-caps=-all --ambient-caps=-all --bounding-set=-all python3 scripts/acceptance.py'` (second successful pass) | exit 0, `ok=true`; same 9 passed stages and counts, including 972 unit, 299 CLAIM_CONFORMANCE, 69 browser |
| `python3 scripts/closeout_digest.py --check-evidence` | exit 0, 4462 bytes match the second successful evidence |
| `python3 scripts/closeout_digest.py --check` | exit 0, 4462 bytes, matching embedded finance copy |
| `python3 scripts/finance_vectors.py --check` | exit 0, 97186 bytes match |
| Python stdlib comparison using `scripts.closeout_digest.build_artifact` on the first and second successful evidence | both projections and the committed digest are byte-identical |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | exit 0, 7 passed |
| `python3 -m compileall -q capital` (final rerun) | exit 0 |
| `node --check capital/static/app.js` (final rerun) | exit 0 |
| `python3 scripts/docs_surface.py --check` (final rerun) | exit 0, 30 routes, 40 artifacts, 9 stages |
| `python3 scripts/observation_vectors.py --check` (final rerun) | exit 0, SIMULATED PASS; NOT_BOUND; applied=false; funds_executed=false |
| `git diff --check` (final rerun) | exit 0 |

`npm run test:browser` was executed unchanged by each isolated acceptance run;
the two successful complete ladders both report **69 passed**. Namespace setup
was only a verification environment adjustment for occupied host loopback ports.
No CI/test configuration, timeout, test selection, protected fixture or upstream
reference was changed. No commit, push, PR, issue, comment, or external message
was made.

Final explicit full-suite run:

- `python3 -m unittest discover -s tests -v`: exit 0, **972 passed** (155.375s).
- Python stdlib SHA256 comparison against all five manifest entries, plus byte
  comparison of `manifest.json` with `git show HEAD:capital/vendor/manifest.json`:
  all five hashes match and the manifest is byte-identical.
- `git branch --show-current`: `agent/capital-adapter-identity-claims`.
- `git status --short -- capital/vendor .aiops docs/decisions capital/observation.py capital/ports.py tests/vectors/provider_facts.json`:
  empty. All protected implementation/corpus/reference paths remain untouched.
- Read-only `/proc` command/cwd scan: no `capital.server` or `scripts/fake_gate.py`
  process remains for this worktree. The unrelated host listeners were untouched.
- `git diff --check`: exit 0.

The node is complete with the planned method divergence preserved. The only
implementation/verification adjustments were the separate SIMULATED output line,
the narrow-test import path, and normal-user isolated loopback verification.

## lifecycle-claims-conformance — conflict-fix round 1 (2026-10-24)

This pending merge combines lifecycle HEAD
`a49ff2f517c2722953a0e3e27b801797242e05f3` with main/MERGE_HEAD
`ff123d54f864d1338575f0bf2e6c33eb1061d46f`. The eight supplied conflicts in
README, integration, validation, acceptance, CE1 tests, closeout tests and the
closeout/finance JSON vectors were resolved. Both claim implementations and all
main additions are retained. The existing upstream-claims stage keeps CE1 fourth
and adapter identity fifth, and adds lifecycle sixth:
87+94+39+49+30+12=311 claims. Cleanly merged acceptance, agent, read-model and
handbook assertions also needed the combined order/count. No stage, test,
assertion, timeout or CI requirement was removed or weakened.

README and the operator handbook now describe the six-command stage. Both
integration sections and both preceding validation histories survive; those
histories describe their own trees, not this merged tree. Closeout artifacts
follow CAPITAL-CLOSEOUT-REGEN-V1: preserve main's actual prior snapshot until a
successful combined acceptance run, regenerate with the two existing tools, add
the sixth command to the independent closeout-test expectation, then rerun the
complete ladder and compare its projected bytes. Historical or failed evidence
is never relabelled as a combined success.

Host loopback ports 8765 and 8766 belong to unrelated services and were left
running. Verification uses the already available local user/network namespaces:

```sh
unshare --user --map-current-user --keep-caps --net bash -c 'ip link set lo up && setpriv --inh-caps=-all --ambient-caps=-all --bounding-set=-all python3 scripts/acceptance.py'
```

This retains the normal UID, drops capabilities before Python starts, and runs
the checked-in acceptance plan and unchanged `npm run test:browser` on isolated
loopback. No dependency install, public endpoint or paid service is involved.
All evidence is local SIMULATED / CLAIM_CONFORMANCE; funds_executed and integrated
remain false. This is not SEMANTIC_CONFORMANCE or human product acceptance.

Initial checks and corrections actually executed:

| Command/check | Result |
|---|---|
| Focused acceptance, agent, read-model, CE1, lifecycle, adapter-identity and closeout unittest modules | Exit 0; 136 passed. |
| Handbook and docs-surface unittest modules | First run: 20 tests, one failure from the stale five-command handbook assertion. After updating it to six and retaining the explicit CE1 fourth-position documentation: exit 0, 20 passed. |
| `python3 scripts/lifecycle_claims_check.py` | Exit 0; citation SKIPPED, verified=0/12, no behavior pass count. |
| `python3 scripts/lifecycle_claims_check.py --execute` | Exit 0; behaviors 12/12, citation SKIPPED. |
| `python3 scripts/lifecycle_claims_check.py --execute --protocol-dir /workspace/capital-run/kixproto-ro` | Exit 0; behaviors 12/12, pinned citations 12/12. Each row's CLAIM_CONFORMANCE, SIMULATED and funds_executed false labels checked separately. |
| `python3 scripts/adapter_identity_claims_check.py --execute --protocol-dir /workspace/capital-run/kixproto-ro` | Exit 0; behaviors 30/30, citations 30/30. |
| First isolated complete acceptance run | Exit 1: unit 988 run, 987 passed, one stale handbook assertion loaded before its correction; Chromium 67 passed, two UI update timing failures; all seven other stages passed, including 311 claims. |
| `npm run test:browser -- --grep "advanced UNBOUND\|organizer advances sim_day"` in the same isolated environment | Exit 0; both previously failing cases passed (6.2s total), with unchanged assertions and timeouts. |

The initial failed evidence is retained in ignored
`build/conflict-round1-failed-evidence.json`, with browser traces in
`build/conflict-round1-failed-traces/`. Logs use the ignored
`build/conflict-round1-*.log` paths. No artifact was generated from that failed
run. The first failure summary names the assertion's old expected value even
though Python's traceback reads its corrected source line from disk.

Successful combined verification and regeneration:

| Command/check | Actual result |
|---|---|
| Isolated unchanged `python3 scripts/acceptance.py`, before regeneration | Exit 0; all nine stages passed: unit 988, storage 19, pinned vendor 7, upstream CLAIM_CONFORMANCE 311, JS syntax, Chromium 69, packaged smoke 8, seeded demo 1, integrated journeys 4. Saved as `build/conflict-round1-pre-regen-evidence.json`. |
| `python3 scripts/closeout_digest.py --write` | Exit 0; generated 4516 bytes from that successful evidence. |
| `python3 scripts/finance_vectors.py --write` | Exit 0; generated 97240 bytes. All unrelated groups and candidate metadata remain identical to main. |
| `python3 -m unittest tests.test_closeout_digest -v` after adding lifecycle sixth to the independent STAGES expectation | Exit 0; 61 passed. |
| Isolated unchanged `python3 scripts/acceptance.py`, after regeneration | Exit 0; all nine stages passed again with the same counts: unit 988, storage 19, vendor 7, claims 311, Chromium 69, smoke 8, demo 1, journeys 4, JS syntax pass. |
| `python3 scripts/closeout_digest.py --check-evidence` after the final run | Exit 0; 4516 bytes match the fresh evidence. Both successful evidence projections and the regenerated digest are byte-identical. |
| `python3 scripts/closeout_digest.py --check` and `python3 scripts/finance_vectors.py --check` | Exit 0; matching embedded closeout copy and canonical finance pack. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed standalone, also passed in both successful ladders. |
| `python3 -m compileall -q capital` and `node --check capital/static/app.js` | Exit 0; repeated after regeneration. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 30 routes, 40 artifacts, nine stages. No new vectors paths require registry entries. |
| Python stdlib SHA256 and byte comparisons | All five vendor files and manifest match HEAD, MERGE_HEAD and origin/main. Export construction, ports and their baseline guard tests match main. No changes under vendor or `.aiops/`. |
| `git diff --check origin/main`, `git diff --cached --check`, conflict-marker scan and `git ls-files -u` | Clean whitespace, no conflict markers and no unresolved index entries. |
| Read-only `/proc` scan for this worktree's Capital, fake-gate and zipapp servers | No remaining servers. Unrelated services were left running. |

The final ignored `build/acceptance-evidence.json` has ok true, all nine stages
passed, label SIMULATED, funds_executed false and integrated false. The packaged
LOCAL_SIMULATION_ARTIFACT SHA256 is
`02a9d68e02b43f0fb0c6125807a385e383a1cc8afa25f447e01623281fbb2ae3`.
The full unit command is `python3 -m unittest discover -s tests -v`; it passed
all 988 tests in both successful ladders. The unchanged `npm run test:browser`
passed all 69 Chromium tests in each. Initial failures remain documented above.

The merge remains pending and staged for the supervisor. HEAD and MERGE_HEAD
are unchanged. No commit, push, reset, rebase, merge abort, external message,
Protocol/Commerce edit, deployment, financial/provider operation or consequential
product decision was made.


## overlay-recovery-writeoff — conflict-fix round 2

Merged `origin/main` at `79c5cc19e51367f1e3c8e38b17c168fe5535383e` into
`agent/capital-overlay-recovery-writeoff` (pre-merge HEAD
`a5b2e2d5b5ecfa820462298cf075cbc223ee60f0`) without committing the merge.
Resolved `tests/decision_bindings.json`, `tests/test_decision_bindings.py` and
`tests/vectors/finance_vectors.json`: all ten recovery decisions retain their
built consumers and tests, all five closeout decisions retain main's built
consumers and tests, and only the claim-slice registry remains pending among
those conflict groups. Finance vectors were regenerated with the merged code;
every main group is preserved, with the facade group matching this branch's
complete recovery schema. Main's committed closeout digest and its embedded
copy are unchanged; their check verifies the recorded artifact, not a fresh
run of the full acceptance ladder.

The active requirements and seam registry now describe the implemented
SIMULATED recovery ledger and interest rebase. Earlier node-run limitations
above describe their historical trees; the adopted
`docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` and the recovery implementation
supersede their unbuilt-overlay statements. This round adds no financial
terms, no reserve ledger, no COA postings and no upstream adoption.

Main's live COA byte guard initially rejected the intentional recovery changes
to `capital/overlay.py` (the only failure in the first 1,018-test run). The guard
now SHA256-pins that file to the exact reviewed recovery bytes at the pre-merge
HEAD (`26c8fcdbe6074e39ff3ad1344d92e9575597ee3ab60baf0a21eed17c55d724dd`).
The original historical COA guard, main's live export/projection/vendor/decision
and V2 golden guards, and the append-only ObservationPort check remain active.
The focused COA suite then passed all 36 tests.

Verification for this combined tree (all local results are SIMULATED):

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | Final run: 1,018 passed in 191.200s; first run's sole stale overlay byte-guard failure fixed as above. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `npm run test:browser -- --config build/overlay-recovery-round2.playwright.cjs` | 69 passed in 2.5m; all projects and assertions retained. |
| `python3 scripts/docs_surface.py --check`; `python3 scripts/decision_bindings.py --check` | Both exit 0; docs surface: 30 routes, 40 artifacts, 9 stages. |
| `finance_vectors`, `closeout_digest`, `manifest_vectors`, `workspace_vectors`, `auth_matrix`, `not_bound_checklist` scripts with `--check` | All exit 0; finance artifact 97,310 bytes, closeout 4,516 bytes, 19 manifest and 6 workspace vectors match. |
| `python3 scripts/seed_overlay_recovery.py` | SIMULATED_DISPOSABLE_BOOK, 18 entries; margin call, acceleration, default, recovery, write-off and late recovery; manifest verified and overlay fold reconciliation MATCHED. |
| `python3 scripts/seed_demo.py` | Existing V2 golden matches, `state_digest=a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45`, `content_digest=2f71dab1a6b7ec3640f2c7c133b0b3acbe95036f8094f9f070bea3b37b651dca`, debit = credit = 385,000. |
| Vendor, merge and marker checks | Five SHA256s match; manifest identical to HEAD and MERGE_HEAD; no unmerged index entries or conflict markers; `git diff --check` clean. |

The direct `npm run test:browser` attempt could not start its servers because
unrelated services from `/workspace/hanset-site-main` and `/workspace/pitchboard-site`
already held loopback ports 8765 and 8766. An ignored temporary config cloned the
repository config and changed only the four configured server ports/base URLs
to 18765–18768, plus absolute config-relative paths needed by that temporary
location. No unrelated process was stopped and no tracked browser config, test,
assertion or CI setting was changed. The retry passed the complete 69-test suite;
its four servers exited afterwards. The full acceptance ladder was not rerun.

Merge resolutions and these supporting test/documentation fixes are staged for
the supervisor. No merge commit or push was made. No vendor, `.aiops`, legacy
export, existing V2 demo golden, Protocol or Commerce bytes were edited, and no
real funds, credentials, providers or deployment were used.

## shadow-participation-slice-uc — conflict-fix round 1

Merged `origin/main` (`6d3e2a6466098fcd50adc93566a2e6b3158f2351`) into the reviewed shadow feature, leaving the merge uncommitted for the supervisor. All 14 conflicted paths are resolved. Main's forecast, recovery/writeoff and repayment posting, evidence artifacts, T03–T06 journeys and COA byte guards are preserved. The facade schema retains every main key/value and adds the shadow vector/deferred-row properties. `finance_vectors.json` was regenerated only with `python3 scripts/finance_vectors.py --write` to pin the combined schema. Documentation now distinguishes single-claim shadow computations from deferred state/clock work.

All evidence below is local **SIMULATED** verification; no funds executed, upstream adoption or integrated acceptance is claimed.

| Command / check | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 1,046 tests passed (249.412s), including the shadow note vectors, runtime rate loading, false flags, missing-note/input paths, unchanged state/receipts and byte-pinned policy simulation |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 tests passed |
| `python3 -m compileall -q capital` | exit 0 |
| `node --check capital/static/app.js` | exit 0 |
| `npm run test:browser -- --config=build/playwright-merge-check.cjs` | 69 tests passed (2.4m); Chromium available |
| `python3 scripts/sim_journeys.py` | T03–T06 golden matches: 22 / 38 / 35 / 33 steps; SIMULATED, funds_executed false, integrated false |
| `python3 scripts/docs_surface.py --check` | 30 routes, 40 artifacts, 9 stages |
| `python3 scripts/finance_vectors.py --check` | 97,332 bytes match |
| `python3 scripts/forecast_vectors.py --check` | 6,456 bytes match |
| `python3 scripts/closeout_digest.py --check` | 4,516 bytes; embedded copy matches |
| `python3 scripts/decision_bindings.py --check` | declared references match |
| Vendor SHA256 / manifest / protected paths | All five locked hashes match; manifest byte-identical to main; no vendor or `.aiops/` diff |
| Merge hygiene | No conflict markers or unmerged index entries; `git diff origin/main --check` clean |

The default browser ports 8765/8766 were occupied by unrelated services in other workspaces. The ignored temporary config imports the checked-in config and changes only the four configured server ports/base URLs to 18765–18768, setting the repository working directory explicitly. Test files, assertions and timeouts are unchanged. The first complete browser run had 68 passes and one repayment/close refresh timeout; the complete five-test command-fence file then passed, followed by the clean 69-test full rerun above. No application or test change was needed for that timeout.

## shadow-participation-slice-uc — PR fix round 1 (2026-10-24)

Investigated the supplied CI `TimeoutError` in the live authorization matrix at
merged HEAD `001bae9`. It did not recur: the complete Python suite passed, the
36-test authorization file passed separately, and 20 fresh-server repetitions of
`LiveMatrixTests.test_every_cell` passed all 4,100 route/role requests. The reported
agent request to `/api/scenarios` is denied by the existing authorization check
before the scenario handler or shadow arithmetic runs. These observations do not
establish the cause of the historical timeout; they provide no reproducible
application or merge defect to repair. Application code, tests, CI settings,
timeouts and golden artifacts are unchanged in this round.

All results are local **SIMULATED** verification, with no external execution or
upstream adoption claimed.

| Command / check | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 1,046 passed in 274.633s |
| `python3 -m unittest discover -s tests -p test_auth_matrix.py -v` | 36 passed |
| Twenty fresh-server live matrix sweeps | 20 passed; 205 requests each, including the reported denied agent request |
| `python3 -m unittest discover -s tests -p 'test_shadow*.py' -v` | 57 passed; note vectors, runtime rates, missing inputs/notes, false flags and unchanged simulation golden |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0 |
| `python3 scripts/docs_surface.py --check` | 30 routes, 40 artifacts, 9 stages |
| Finance, forecast, closeout, decision-binding, auth-matrix and not-bound-checklist scripts with `--check` | All exit 0; existing combined-main artifacts match without regeneration |
| Actual loopback `GET /api/policy/shadow` | Three added items computed under SHADOW_NOT_APPLIED; all nine flags false in items, vectors and deferred rows; state_digest, receipts and operation_count unchanged |
| Actual loopback `GET /api/policy/simulation`, compared with a disposable `origin/main` archive | Byte-identical with the same synthetic instance_id: 6,110 bytes, SHA256 `e68616b02581d822964dc969cd05591bfa791f28e6ef43dfca3363c6f1a64d82` |
| Vendor / manifest / legacy export | Five locked SHA256s match; five reference files, manifest and export.py byte-identical to HEAD and origin/main |
| Focused Chromium journey and portfolio files | 21 passed in 32.1s, including both cases that timed out in earlier full runs |
| `npm run test:browser -- --config=/tmp/shadow-fix-browser-tcyi1rdb/playwright.config.cjs` | Final full run: all 69 passed in 2.0m |

The default browser invocation could not bind occupied loopback ports. The
temporary `/tmp/shadow-fix-browser-tcyi1rdb/playwright.config.cjs` imports the
tracked configuration, uses unused loopback ports and a disposable demo workspace,
and relocates config-relative test/report paths. It retains all projects, tests,
assertions and timeouts. Two full runs each passed 68/69 tests, with different
timing failures: first the default journey, then mobile startup. Inspection of the
first trace showed the browser resolving the expected DEFAULTED label at
68,570ms, while the test worker recorded completion at 146,084ms and exceeded its
30s test budget. The second trace showed a 5s startup assertion returning after
about 13.9s. Runner scheduling delays are an inference from those timing gaps,
not an established explanation of the original CI failure. Both affected files
then passed together without code, assertion or timeout changes.
The subsequent complete Chromium run passed all 69 tests. This round changes only
this validation record; no commit, push or external post was made.

## claim-slice-registry — provisional shadow registry

Implemented `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` using its ten
ADOPTED entries and runtime CAPITAL-TERMS-V1 caps/rates/authority threshold.
`capital/slices.py` plans and folds all six kinds into `state.claim_slices`;
empty is key-absent and overlay_schema remains 1. Organizer commands and
`projection:read` listing/quotes are covered by the regenerated auth matrix
and the strict local facade contract. Registry records, shortfall and
holder-first arithmetic remain SIMULATED / SHADOW_NOT_APPLIED; all execution
flags are false. Legal/tax treatment remains a provisional working assumption
pending professional review. No real offering, funds, title or COA posting.

The demo golden uses `ScenarioReplaySource` and the actual demo-book claims.
`demo-delta-mid` gets a synthetic low-cash/held statement through the pinned
settlement FSM, allowing partial organizer service before a simulated refund.
The remaining slice is impaired, recovered from `demo-delta-small`, and resolved.
The distribution order in this disposable scenario is explicit fixture input,
not a newly adopted settlement policy. Late-distribution arithmetic is also
unit-tested with an explicitly synthetic pure observation vector; it is not
reported as an accepted post-refund FSM distribution.

Replay checks F04 witness advances against the exact journal prefix, including
shared reservations and every advance exposure. Guard traces are recomputed
from stamped policy and compact observations. Settlement observations are
stamped and bound, **not re-derived from F04**: the pinned line face must match,
observed line amounts are bounded by face, distributions cannot decrease across
slice entries, and an unchanged claim hash requires exact observation equality.
An additional G4 cross-journal splice check is possible only when that settlement
cut remains unchanged; changed cuts do not claim a historical distribution
journal. Recomputed checksums are integrity evidence, not authentication.
Forged guard/reservation/exposure/prefix witnesses fail restore with
WORKSPACE_UNREADABLE, offline verification with OVERLAY_FOLD_MISMATCH, and
reconciliation with RECON_MISMATCH / claim_slice_link.

Shared accounting applies G0–G4. U3 subtracts slice encumbrance, U4 counts the
face exposure with advances, and a draw re-evaluates when any portfolio slice
exposure remains. The draw checks the incoming reservation plus existing shared
reservations to retain I-BASE across multiple advances. Pre-default set-off,
RECOVERY and SLICE_RECOURSE subtract served holder amounts and both lanes'
source consumption in journal order. Resolved holder service stays held.

Plan adjustments after checking the repository:

- The illustrative §3.4 opening example conflicts with G2: at the adopted rate,
  the remaining base is below the example's advance. Tests enforce G2 and compute
  the admissible face from the note/terms instead of treating that example as an
  exception. Unpledged fixtures never become additional collateral for G2.
- Witness observations are compact mapped-line records under payload.witness;
  the full stamped policy stays under payload.policy, following the existing
  recovery convention and the unchanged 4096-byte global entry bound. The lower
  global capacity bound still refuses an oversized witness without eviction.
- The strict facade contract also needed the six request shapes, receipts,
  listing, optional shadow registry_check/U3 field, route and error rows.
- The predecessor's exact overlay byte pin was extended, preserving both a
  live exact-byte hash and the original recovery hash after reversing only the
  three exact slice dispatch additions. No legacy fold byte is exempted.
- The demo book cannot reach the adopted portfolio cap while respecting all
  beneficiary caps. The cross-beneficiary U4 test explicitly uses a boundary-test
  policy whose portfolio cap equals the adopted single cap; deployed/default
  policy values remain note-loaded. This is synthetic test input, not a product
  term or a real capacity result.
- Local `main` is the initial commit, while HEAD and `origin/main` are `2633e01`.
  The requested `git diff --exit-code main -- capital/vendor capital/export.py
  .aiops` reports pre-existing baseline additions. The corresponding check
  against `origin/main` passes with zero bytes of diff. No refs were changed.

Commands actually run during development (later closeout evidence follows):

| Command | Result |
|---|---|
| `python3 scripts/seed_overlay_slices.py --write` | Golden generated; final journey has 6 overlay entries, verified V3 manifest and MATCHED overlay fold. Initial low-cash distribution used the platform first and failed the partial-holder assertion; corrected the explicit disposable fixture order. |
| `python3 -m unittest discover -s tests -p test_claim_slices.py -v` | Initial 19-test run exposed fixture/idempotency mistakes; corrected. Latest expanded run: 26 passed. |
| `python3 -m unittest discover -s tests -p test_underwriting.py -v` | 14 passed. |
| `python3 -m unittest discover -s tests -p test_recovery.py -v` | 29 passed. |
| `python3 scripts/auth_matrix.py --write` / `--check` | Regenerated and matched. |
| `python3 scripts/docs_surface.py --check` | 31 routes, 40 artifacts, 9 stages; passed. |
| `python3 -m unittest discover -s tests -p test_auth_matrix.py -v` | 36 passed, including live loopback role probes. |
| `python3 -m unittest discover -s tests -v` (first full run) | 1070 tests, 4 failures: overlay byte pin, empty synthetic V3 fixture verification, and missing facade error/route catalogue. Fixed without changing vendor/export bytes or removing checks. |
| `python3 -m unittest discover -s tests -p test_coa_candidate.py -v` | 36 passed after the additive byte guard extension. |
| `python3 -m unittest discover -s tests -p test_dev_keyset.py -v` | Initially exposed the empty fixture verifier regression; fixed the optional rows lookup. 7 passed on rerun. |
| `python3 -m unittest discover -s tests -p test_facade_contract.py -v` | 5 passed after extending the contract. |
| `python3 scripts/pack_vectors.py --write` | 9 existing pack vectors regenerated. |
| `python3 scripts/manifest_vectors.py --check` | 19 matched. |
| `python3 scripts/workspace_vectors.py --check` | 6 matched. |
| `python3 scripts/decision_ledger.py` | All decision notes parsed; ten registry entries ADOPTED. |
| `python3 scripts/not_bound_checklist.py --check` | Passed. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital` | Passed. |
| `node --check capital/static/app.js` | Passed; UI unchanged. |
| `git diff --check` | Passed. |
| `git diff --exit-code origin/main -- capital/vendor capital/export.py .aiops` | Passed, empty diff. |

`git ls-files -z capital/vendor | xargs -0 sha256sum` recorded the unchanged pins:

```text
f4f6b3698dd848538d2efa10b276cb33659eb4877fcbea0feb7429b28456491b  capital/vendor/credit_advance_f04/credit_fsm.py
5e75fcc76fb0857f671b2fa33ca0fc851e9d676d4b5db8f357393367bc725d95  capital/vendor/credit_advance_f04/mock_credit.py
75cd55f773e3e71553392f674d1595af66cf82560565cc5603bf829a9a29e99d  capital/vendor/credit_advance_f04/test_mock_credit.py
b5ff2fca301bf456826dcbc9a6617521d528746efb03b8107f23b818fb4d6def  capital/vendor/manifest.json
9e9c25571fdbe7b90b7539df2cc71afaee83d81905293dc56dbeb9faaf864170  capital/vendor/settlement_f01_f03/mock_settlement.py
c6d7ae79fe0c3289def2d3c195212247d1ab2c2e913feb80612fcd9ff64c77c8  capital/vendor/settlement_f01_f03/settlement_fsm.py
```

Further local verification and environment adjustments:

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` (second full run) | 1072 tests, 11 failures and 1 error, all stale finance-vector contract digests/route coverage after adding the strict facade schema. Regenerated the existing finance artifact and extended the exact GET list/count from 29 to 30 (all routes 41 to 42); no route check was removed. |
| `python3 scripts/finance_vectors.py --write` | Bootstrap regeneration for the new facade contract, using the existing closeout digest; regenerated again after gated closeout evidence below. |
| `python3 -m unittest discover -s tests -p test_finance_vectors.py -v` | 54 passed after regeneration. |
| `python3 scripts/decision_bindings.py --check` | Passed: declared references only; pending anchors are not implementation. |
| `python3 scripts/pack_vectors.py --check` | 9 matched. |
| `python3 scripts/finance_vectors.py --check` | Matched after bootstrap. |
| `npm ci --ignore-scripts` | Installed the 3 existing lockfile dev dependencies; audit reported 0 vulnerabilities. No dependency/lockfile change. |
| Browser port availability probe | Host ports 8765 and 8766 belong to unrelated existing crawler services. Left both untouched. |
| `npm run test:browser` (host namespace) | Failed because the initially available global playwright CLI lacks the `test` command. Installed the lockfile dependencies before retrying. |

The browser and complete acceptance ladder run in a fresh user/network namespace
using `unshare -Urn -- bash -c 'ip link set lo up && exec …'`. This enables only
that namespace's loopback and lets the **unchanged** Playwright configuration,
fixed ports and tests run without interfering with the host services. No CI,
server, browser assertion or Playwright configuration was weakened for this.

| Command | Result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | 69 passed (2.1m), unchanged Chromium suite. All four namespace-local Capital servers stopped afterward. |

| Closeout command | Result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3 scripts/acceptance.py'` (first evidence) | Exit 0, `ok:true`; unit 1072, storage-conformance 19, pinned-vendor 7, upstream-claims 311, browser 69, packaged-smoke 8, seeded-demo 1, integrated-journeys 4; node-check passed. |
| `python3 scripts/closeout_digest.py --write` | Gated by that passing evidence; wrote 4518 bytes. |
| `python3 scripts/finance_vectors.py --write` | Regenerated after closeout; wrote 97980 bytes. |
| `python3 scripts/pack_vectors.py --check` | 9 matched; no repeat/regeneration cycle needed. |

Local detailed logs and the first evidence snapshot are retained under the
ignored `build/claim-slice-registry/` directory. The final acceptance evidence is
`build/acceptance-evidence.json`. These are SIMULATED local verification records,
not production authorization or upstream adoption evidence.

| Additional verification command | Result |
|---|---|
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3 scripts/acceptance.py'` (second attempt) | Unit 1072 and all non-browser stages passed. Browser: 67 passed, 2 failed. Evidence honestly recorded `ok:false`; no gated artifact write was attempted from it. |
| Trace inspection | The existing `portfolio.spec.cjs` reconciliation test timed out waiting for a close-command response after repayment; its unclosed reservation caused the following default test's draw to return `ADVANCE_EXCEEDS_OPEN_FACE`. No slices were registered in either test. Preserved failed evidence and traces under `build/claim-slice-registry/`. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser -- --project=workspace tests/browser/portfolio.spec.cjs'` | All 6 portfolio tests passed (19.6s) on a fresh isolated server, including both previously failing cases. No UI, assertion, timeout or browser configuration change. A full ladder retry follows to obtain passing final evidence. |

| Final verification command | Result |
|---|---|
| `python3 -m unittest discover -s tests` | 1072 tests, OK. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py` | 7 passed. |
| `python3 -m compileall -q capital` and `node --check capital/static/app.js` | Both exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec python3 scripts/acceptance.py'` (final runs) | Three runs. Runs 1 and 2 recorded `ok:false` with a single 30s browser timeout each (`auditor-evidence-desk` unreadable case, then `portfolio.spec` default case) while host load average was 9-10. Both specs pass alone, and nothing in the slice change touches those paths. Run 3, at load 6, was `ok:true`: unit 1072, storage-conformance 19, pinned-vendor 7, upstream-claims 311, node-check passed, browser 69, packaged-smoke 8, seeded-demo 1, integrated-journeys 4. |
| `python3 scripts/closeout_digest.py --check-evidence`, `--check`; `scripts/finance_vectors.py --check`; `scripts/pack_vectors.py --check` | All pass against the final evidence; the committed digests needed no regeneration. |
| `git diff --exit-code origin/main -- capital/vendor capital/export.py .aiops` | Empty diff. |

## fake-idp-session

`capital/idp_fake.py` adds `FakeIdpAuthorizer`, a `LocalRoleAuthorizer` subclass for the opt-in `python3 -m capital.server --authorizer fake-idp`, and `scripts/fake_idp.py` mints HS256 tokens for the four synthetic roles from a committed test-vector key (not a credential, no key or kid parameter, no environment or file key source). Only `POST /api/session` changes: it needs exactly one `Authorization: Bearer` header, the bound role is the verified `role` claim, and a different body role is `403 ROLE_MISMATCH`. A missing token is `401 IDP_TOKEN_REQUIRED`; any rejected token (alg `none` or another alg, bad signature, expired, not yet valid with zero leeway, wrong `iss` or `aud`, unknown `kid`, duplicate/missing/extra claims, non-integer times, lifetime over 3600 s, over 2048 bytes, malformed base64url) is `401 IDP_TOKEN_INVALID` with a closed `reason` slug and never echoes the token. The check runs before the body is read, and nothing is written. Responses carry `mode: LOCAL_FAKE_IDP` while `identity`, `authentication`, `idp`, `kyc`, `agent_grant` and `action_permit` stay `NOT_BOUND`. `sub` must equal one fixed placeholder and the verifier returns only the role, so no subject, name or email reaches the workspace, event log or metrics (asserted against `workspace`, event log, `/api/state`, `/api/metrics`, `/api/export`). Later requests keep the role-scoped `X-Capital-Token`. This is not a security upgrade: the bootstrap organizer token from `GET /api/state` is unchanged, and tokens have no `jti`, so they replay until `exp`. The browser UI cannot present a bearer token, so role switching in the UI gets 401 in fake mode; the browser suite runs the default mode only.

`capital/ports.py` gains `run_authorizer_vectors(factory)` (collects failures, raises one `AssertionError`). `LocalRoleAuthorizer` and `FakeIdpAuthorizer` pass the same vectors, and negative controls (header-trusting and allow-everything authorizers) fail them. `capital/contract/facade-v1.json` gains `IDP_TOKEN_REQUIRED` and `IDP_TOKEN_INVALID` (401) and `session.mode` / `auth.mode` become an enum of the two labels; `tests/vectors/finance_vectors.json` was regenerated with `python3 scripts/finance_vectors.py --write` (digest of the contract file only). `tests/test_coa_candidate.py` no longer lists `capital/ports.py` among files that must equal main, because this node adds to it. `tests/auth_matrix.json`, `capital/auth.py`, `capital/vendor/**` and `.aiops/` are untouched. Everything is SIMULATED; no real IdP, KYC, credential or network call.

Commands actually run:

- `python3 -m unittest tests.test_fake_idp -v`: exit 0, **28 passed**.
- `python3 -m unittest discover -s tests`: **650 tests, 1 failure**, `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched`. It diffs against `origin/main`, which has moved since this branch started, so it lists `docs/decisions/CAPITAL_EXTERNAL_GATES.md`, `docs/decisions/CAPITAL_RELEASE_ACCEPTANCE.md` and `tests/golden/demo.json` from other nodes. `git diff --name-only <merge-base> -- <its file list>` shows only `capital/ports.py`, the intended edit. An earlier run also failed nine `test_finance_vectors` tests until the vectors were regenerated.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py`: exit 0, 7 passed.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/auth_matrix.py --check`, `docs_surface.py --check`, `not_bound_checklist.py --check`, `finance_vectors.py --check`: exit 0.
- `git diff --name-only -- capital/vendor .aiops .github tests/auth_matrix.json`: no output.
- `npm run test:browser`: **not run**. This worktree has no `node_modules` and `127.0.0.1:8765` is held by another process, so the fixed-port config (`reuseExistingServer: false`) would clash. No UI file changed.

Merge with main (2026-10-20; `MERGE_HEAD` `5ec4c95`, `origin/main` moved on to `c9cfd6e` while the merge was in progress): three conflicts, none dropped. `docs/VALIDATION.md` keeps main's `audit70-fix5`, `t05-t06-sim-journeys`, `portfolio-risk-analytics` and `operator-console-ux` sections before this node's section. `tests/test_coa_candidate.py` `test_v1_and_golden_files_are_untouched` takes main's newest form (the `guarded` list, the `added_on_main` carve-out for files main added after the branch's merge point that the working tree never held, and the key-by-key golden pin check) with `capital/ports.py` left out of `guarded` for this node's additive `run_authorizer_vectors`. `tests/vectors/finance_vectors.json` was regenerated with `python3 scripts/finance_vectors.py --write` from the merged facade, not hand-merged. The two commits main gained after `MERGE_HEAD` (`a6e603a` sim-journeys, `c9cfd6e` claim-slice decision) are folded in so their work survives: `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`, `scripts/sim_journeys.py`, `tests/test_sim_journeys.py`, `tests/golden/journey_t05_sim.json`, `tests/golden/journey_t06_sim.json`, `docs/ACCEPTANCE_KO.md`, `docs/OPERATOR_HANDBOOK_KO.md`, `scripts/acceptance.py` and `tests/test_acceptance.py` are byte-identical to `origin/main` (this branch never touched them), the sim-journeys paragraph was added to `README.md`, and the `t05-t06-sim-journeys` section was added to this file in main's order.

Commands actually run after the merge:

- `python3 scripts/finance_vectors.py --write`, then `--check`: exit 0, 90609 bytes match.
- `python3 scripts/sim_journeys.py`: exit 0, `sim journeys ok SIMULATED T05-sim steps=35 T06-sim steps=33`; both pins match a live run.
- `python3 -m unittest discover -s tests -v`: exit 0, **713 passed**. The first run had one failure, `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched` (`docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` absent because `origin/main` had moved past `MERGE_HEAD`), fixed as described above.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. Vendored file SHA256 values match `capital/vendor/manifest.json`.
- `python3 -m compileall -q capital`, `node --check capital/static/app.js`: exit 0.
- `python3 scripts/docs_surface.py --check` (28 routes, 20 artifacts, 9 stages), `manifest_vectors` (13 files), `workspace_vectors` (6 files), `not_bound_checklist`, `auth_matrix` with `--check`, and `scripts/decision_ledger.py`: exit 0.
- `python3 scripts/seed_demo.py`: exit 0, `state_digest=a8609033…ef45`, `content_digest=2f71dab1…dca`, golden unchanged.
- `npm ci --offline --ignore-scripts`: exit 0, 3 packages. `npm run test:browser`: exit 0, **62 passed** (2.3m); no `capital.server` of this worktree remained.
- `git diff --name-only origin/main -- capital/vendor .aiops .github tests/auth_matrix.json`: no output.


## fake-idp-session conflict-fix round 1 (2026-10-25)

Resolved all eleven conflicts against main `51a0d2e8b1b6422d99c3a8f3b7f8bb999ca4090c`.
The merge remains uncommitted for the supervisor. Both implementations survive:
`ObservationPort` precedes the unchanged `run_authorizer_vectors` addition, and
session bearer verification still runs before the session body is read while
main's slice/recovery agent denials keep their original precedence. The COA
compatibility guard retains main's historical, live byte and overlay checks;
its append-only exception now also permits the exact SHA256-pinned source of
`run_authorizer_vectors`, with negative controls for mutations and duplicates.
No existing definition is exempted. A new live fake-IdP test binds an agent from
its verified claim, checks every slice/recovery command denial on both command
routes, and confirms unchanged workspace data.

Main's T03–T06 journey runner, journey tests, T05 golden, acceptance runner and
operator handbook are byte-identical to main. README and this validation log
retain both nodes' documentation. Finance vectors were regenerated from the
merged facade; all vector groups and rows survive, and the only changed values
against main are `contract_digest`, `definitions_digest` and the session route's
`closure_digest` under `facade_read_model`.

All evidence below is local and SIMULATED; identity/authentication remain
NOT_BOUND, and no real funds or provider calls occur.

| Verification | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 1100 passed, 207.923 s. The additional integration test added during this run is covered by the focused run below. |
| `python3 -m unittest tests.test_fake_idp -v` | 29 passed, including the new claim-bound agent slice/recovery denial test. |
| `python3 -m unittest discover -s tests -p test_coa_candidate.py -v` | 36 passed against the final source-pinned compatibility guard. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | 69 passed, 2.6 min. Chromium was available. Host ports 8765/8766 were occupied, so unchanged browser configuration ran in an isolated loopback network namespace. Lockfile dependencies installed with `npm ci --offline --ignore-scripts`. |
| `python3 scripts/docs_surface.py --check` | 31 routes, 40 artifacts, 9 stages; passed. |
| `python3 scripts/auth_matrix.py --check` | Passed; matrix bytes equal main. |
| `python3 scripts/finance_vectors.py --write`, then `--check` | 97980 bytes; matched. |
| `manifest_vectors.py`, `pack_vectors.py`, `workspace_vectors.py`, `observation_vectors.py`, `forecast_vectors.py`, `not_bound_checklist.py`, `decision_bindings.py`, each with `--check` | All passed; 19 manifest, 9 pack and 6 workspace vectors matched. |
| `python3 scripts/sim_journeys.py` | All unchanged pins matched: T03 22, T04 38, T05 35, T06 33 steps. |
| `python3 scripts/seed_demo.py` | Golden matched; debit = credit = 385000 synthetic units. |
| Vendor SHA256 and byte checks | All five files match `capital/vendor/manifest.json`; those files and manifest are byte-identical to main. |
| Protected paths | `capital/export.py`, `capital/auth.py`, `tests/auth_matrix.json`, vendor and `.aiops/` unchanged against main. |
| Merge hygiene | No conflict markers or unmerged index entries. `git diff --check origin/main` passed. Main's existing Markdown hard breaks in `CAPITAL_UPSTREAM_REPINS.md` were retained unchanged. |

No product decision or external action was needed. No merge abort, commit, push,
rebase or reset was performed.


## http-hostile-corpus — conflict-fix round 1 (2026-10-25)

Merged incoming main `e56224a` while preserving both sides. README retains the hostile-HTTP corpus and every incoming main entry; the validation log retains both appended histories; `scripts/docs_surface.py` registers both `http/` and `pack/` alongside main's other artifacts. Regenerated `tests/vectors/finance_vectors.json` with the merged generator: compared with incoming main, only `groups.facade_read_model.contract_digest` changes for this node's `INVALID_TARGET` contract error. All eight candidate groups, including the embedded closeout digest, survive unchanged. The hostile generator, replay tests and all 76 recipes are byte-identical to the feature parent. The existing acceptance ladder's unit stage discovers the corpus replay and `--check` drift tests.

Commands actually run after resolution (all results are local SIMULATED verification):

- `python3 -m unittest discover -s tests -v`: exit 0, **1121 passed** (206.066s), including the legacy COA byte guards, hostile corpus, drift/missing/unexpected-file rejection, and main's tests. No test or CI rule was weakened.
- `python3 -m unittest discover -s tests -p test_http_hostile.py -v`: exit 0, **9 passed**; all 76 requests replayed with pinned outcomes, unchanged state/operation count and healthy server probes.
- `python3 scripts/http_hostile.py --write` followed by `--check`: exit 0; all 76 regenerated recipes byte-identical to the feature parent.
- `python3 scripts/docs_surface.py --check`: exit 0, **31 routes, 116 artifacts, 9 stages**. `auth_matrix`, `manifest_vectors` (19 files), `workspace_vectors` (6 files), `pack_vectors` (9 files), `finance_vectors` (97980 bytes), `closeout_digest` (4518 bytes), `forecast_vectors` (6456 bytes), `decision_bindings` and `not_bound_checklist` with `--check`: exit 0.
- `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v`: exit 0, **7 passed**. The five reference files match every manifest SHA256; those files and `manifest.json` are byte-identical to both merge parents. `.aiops/` is untouched.
- `python3 -m compileall -q capital` and `node --check capital/static/app.js`: exit 0.
- `npm run test:browser`: the checked-in configuration could not bind an occupied shared loopback port. `npm run test:browser -- --config build/http-hostile-merge.playwright.cjs`: exit 0, **69 passed** (2.0m), Chromium. The ignored temporary config retains all projects/tests and uses free loopback ports, the repository working directory and a separate disposable workspace; checked-in browser configuration and CI remain unchanged.

All four conflicted paths are resolved, no conflict markers remain, and the merge is left uncommitted for the supervisor. No Protocol/Commerce reference, vendor file, product terms or deployment was changed.

## fold-fuzz-determinism — conflict-fix round 1 (2026-10-25)

Resolved the append conflict against main `e56224a311dbcae93be363db8a5580311bc25b23` by retaining both conflicted validation additions byte-for-byte. The merge remains uncommitted for the supervisor.

The first replay check correctly exited 1 at seed 74810048, step 37: main's accepted-default path now persists a recovery anchor and recovery-authority receipt fields. Regenerated only the fold-fuzz corpus after two independent replays and reload checks. Generator metadata, all 16 seeds, all 736 commands, checkpoint shapes and every F04 state digest remain unchanged. Changes occur only at or after each sequence's first default: 400 envelope hashes, 400 overlay digests, 400 receipt hashes and 332 overlay-receipt hashes changed. No legacy golden was rewritten. The verification harness now checks the service's full decision-record capacity count, including default anchors; its receipt regression also asserts the default-anchor operation references and recovery-authority principal amounts.

All results are local and SIMULATED. CAP-11 remains NOT_BOUND; these checks claim sequence-order determinism under fixed synthetic writer/clock inputs on the same interpreter and tree, without durability or performance claims. Capital runtime, goldens, decisions, vendor and manifest, CI and `.aiops/` match main. No external action or product decision was required.


| Verification | Actual local result |
|---|---|
| Initial `python3 scripts/fold_fuzz.py --check` | Exit 1, seed 74810048 checkpoint 37 overlay digest drift; input was not rewritten. |
| Initial `python3 -m unittest discover -s tests -v` | Exit 1; 1124 tests, two failures from the stale fold-fuzz hashes, 202.988 s. |
| Candidate corpus comparison with this node's HEAD | Generator, seeds, all commands and every F04 state digest unchanged; affected hashes change only at/after the first default. |
| Final `python3 scripts/fold_fuzz.py --check` | Exit 0; SIMULATED, 16 seeds, 736 commands, independent replays and reloads match. |
| Final `python3 -m unittest discover -s tests -v` | Exit 0; 1124 passed, 319.333 s, including all 12 fold-fuzz tests and both hash-seed subprocess replays. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 41 artifacts, nine stages. |
| `python3 tests/crash_matrix.py --check`; `python3 scripts/workspace_vectors.py --check` | Both exit 0; 23 crash cells and six workspace files match. |
| `python3 scripts/seed_demo.py` | Exit 0; existing golden matches, state_digest `a8609033d8b905c49dd6e5c26b5221a5ad2e5bb67596ef629815c8a230b7ef45`, content_digest `2f71dab1a6b7ec3640f2c7c133b0b3acbe95036f8094f9f070bea3b37b651dca`; debit = credit = 385000 synthetic units. |
| `npm ci --offline --ignore-scripts --no-audit --no-fund` | Exit 0; pinned local dependencies installed without changing the lockfile. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed, 1.8 min. Existing host ports 8765/8766 were occupied; unchanged browser configuration ran inside an isolated loopback network namespace. |
| Vendor integrity | All five SHA256 locks match the manifest; vendored files and manifest are byte-identical to main. |
| Merge hygiene | Both conflicted additions preserved byte-for-byte; no conflict markers or unmerged entries; `git diff --check origin/main` passes. No abort, commit, push, rebase or reset performed. |

## producer-tuple-preflight — conflict-fix round 2 (2026-10-26)

Resolved `docs/SEAMS.md` and `docs/VALIDATION.md` while retaining the producer
preflight additions verbatim and all main lines in order. The fake IdP seam and
main's accumulated validation records survive alongside the preflight rehearsal.
The pending merge combines node HEAD `09fb25ca3dbae762e591aa36b9234f48cfd85608`
with MERGE_HEAD/origin/main `aab0a7364c79ef00d34e031e4a827a817f7ae544`.
No implementation or test change was needed for this combination.

All results below are local SIMULATED / READ_ONLY_FIXTURE evidence. Byte agreement
does not qualify or adopt a producer: semantic consumption remains HOLD,
ProducerPort and CAP-16 remain NOT_BOUND, and semantic_conformance remains false.

| Command / check | Actual result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1144 passed in 259.810 s, including checker mismatch/rejection and fake-gate preflight tests. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `python3 scripts/compat_preflight.py --check` | Exit 0; MATCHED, BOOTSTRAP, zero errors; HOLD / NOT_BOUND. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 57 artifacts, nine stages. |
| `python3 scripts/manifest_vectors.py --check`; `python3 scripts/workspace_vectors.py --check`; `python3 scripts/pack_vectors.py --check` | All exit 0; 19, six and nine files match respectively. |
| `python3 scripts/finance_vectors.py --check`; `python3 scripts/forecast_vectors.py --check`; `python3 scripts/decision_bindings.py --check` | All exit 0; 97980 and 6456 bytes match; declared decision references valid. |
| `python3 scripts/gate_faults.py --check`; `python3 scripts/ce1_claims_check.py --execute` | Both exit 0; seven fault cases and 49/49 local behavior claims. |
| `npm ci --offline --ignore-scripts --no-audit --no-fund` | Exit 0; three pinned packages, lockfile unchanged. |
| `npm run test:browser` | Exit 1 before tests: an existing host loopback listener prevented server startup (address already in use); unrelated services left running. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed in 2.1 min, with the checked-in configuration unchanged inside an isolated loopback network namespace. |
| Vendor integrity | All five SHA256 locks match; five vendored files and manifest byte-identical to HEAD, MERGE_HEAD and origin/main. No changes under `.aiops/`. |
| Merge hygiene | Both sides retained; no conflict markers or unresolved index entries. `git diff --check` and `git diff --check origin/main` pass. |

`git diff --cached --check` reports three existing Markdown hard-break lines in
main's `docs/decisions/CAPITAL_UPSTREAM_REPINS.md`; that decision file is retained
byte-for-byte from main. Local full-suite and browser logs are in ignored
`build/producer-tuple-preflight-round2/`. Only the two conflicted documents were
edited during this round. No Protocol/Commerce changes, executable re-pinning,
external posts, merge abort, commit, push, rebase or reset were performed.

## http-hostile-corpus — conflict-fix round 2 (2026-10-26)

Resolved the append conflict in this file by retaining both the hostile-HTTP round-1 history and main's fold-fuzz round-1 history verbatim. Main's fold-fuzz generator, tests, corpus and integration documentation are preserved. The hostile generator, replay tests, all 76 recipes, server fixes, facade contract and handbook remain byte-identical to this node's merge parent. README and the docs registry retain both corpora. No runtime, test or CI change was needed.

All results below are local SIMULATED verification. Logs are in ignored `build/http-hostile-round2/`. No external action, product decision, Protocol/Commerce modification or `.aiops/` edit was made.

| Verification | Actual local result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1133 passed in 327.037 s, including both corpora, hostile post-state/health probes, drift/missing/unexpected-file rejection and legacy COA byte guards. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed in 3.1 min, using the unchanged browser configuration in an isolated loopback network namespace. |
| `python3 scripts/http_hostile.py --write` then `--check` | Both exit 0; all 76 regenerated recipes are byte-identical to their pre-write bytes and the feature merge parent. |
| `python3 scripts/fold_fuzz.py --check` | Exit 0; SIMULATED, 16 seeds and 736 commands match. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 117 artifacts and nine stages. |
| Vendor integrity | All five SHA256 locks match; those five reference files and `manifest.json` are byte-identical to both merge parents. |
| Merge hygiene | Both conflicted histories preserved verbatim; no conflict markers or unmerged entries; whitespace checks pass against both merge parents. The merge is left uncommitted for the supervisor; no abort, commit, push, rebase or reset performed. |

## producer-tuple-preflight — conflict-fix round 3 (2026-10-27)

Resolved the append conflict in this file by retaining both this node's round-2
record and main's hostile-HTTP round-2 record verbatim (node section first, then
main's). The pending merge combines node HEAD `cd7c2413ed8cbaea4853c3dc162696812e6da66e`
with MERGE_HEAD/origin/main `b3b56fef384a7c7687d2e5c4243d67887f6f93ba`. Main's hostile
HTTP corpus, server fixes, facade contract, handbook and docs-registry entries merged
cleanly alongside the producer preflight; no implementation or test change was needed.

All results below are local SIMULATED / READ_ONLY_FIXTURE evidence. Byte agreement
does not qualify or adopt a producer: semantic consumption remains HOLD,
ProducerPort and CAP-16 remain NOT_BOUND, and semantic_conformance remains false.

| Command / check | Actual result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; 1153 passed in 259.617 s, including checker mismatch/rejection, fake-gate preflight and hostile-HTTP replay tests. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `python3 scripts/compat_preflight.py --check` | Exit 0; MATCHED, BOOTSTRAP, zero errors; HOLD / NOT_BOUND. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 31 routes, 133 artifacts, nine stages. |
| `python3 scripts/http_hostile.py --check`; `python3 scripts/fold_fuzz.py --check` | Both exit 0; 76 hostile files match; SIMULATED 16 seeds, 736 commands. |
| `python3 scripts/manifest_vectors.py --check`; `python3 scripts/workspace_vectors.py --check`; `python3 scripts/pack_vectors.py --check` | All exit 0; 19, six and nine files match respectively. |
| `python3 scripts/finance_vectors.py --check`; `python3 scripts/forecast_vectors.py --check`; `python3 scripts/decision_bindings.py --check` | All exit 0; 97980 and 6456 bytes match; declared decision references valid. |
| `python3 scripts/gate_faults.py --check`; `python3 scripts/ce1_claims_check.py --execute`; `python3 tests/crash_matrix.py --check` | All exit 0; seven fault cases, 49/49 local behavior claims, 23 crash cells. |
| `python3 scripts/seed_demo.py` | Exit 0; golden matches, debit = credit = 385000 synthetic units. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser'` | Exit 0; all 69 Chromium tests passed in 2.1 min. Host ports 8765/8766 were occupied, so the unchanged configuration ran inside an isolated loopback network namespace. |
| Vendor integrity | All five SHA256 locks match; vendored files, manifest and `.aiops/` byte-identical to HEAD and MERGE_HEAD. |
| Merge hygiene | Both sides retained (diff against each parent removes no lines); no conflict markers or unmerged entries. |

Logs are in ignored `build/producer-tuple-preflight-round3/`. Only `docs/VALIDATION.md`
was edited this round. No Protocol/Commerce changes, executable re-pinning, external
posts, merge abort, commit, push, rebase or reset were performed.
