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
