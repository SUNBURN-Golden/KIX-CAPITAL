# Validation scope

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
