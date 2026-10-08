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
