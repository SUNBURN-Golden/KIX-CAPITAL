# Capital local API and future integration

`/api/*` is **Capital's local simulation facade**, not a promoted KIX Protocol catalogue, generated SDK, lending endpoint, or live provider adapter. No fallback to `offer_gift`, `settle_capture`, bank, PG or chain exists.

## Local facade v1

- `GET /api/state`: process identity, synthetic fixtures, current F04 views, pinned source, local CSRF token, capacity and undecided capabilities.
- `POST /api/commands`: strict `{instance_id, operation_id, op, advance_id, args}`. ID must start `sim-`; operation identity is immutable. `X-Capital-Token` from the same process and `Content-Type: application/json` required. Maximum request 8192 bytes; maximum retained operations 500 (demo resource bound, not financial policy).
- `GET /api/operations/{operation_id}?instance_id=…`: original ACCEPTED/REJECTED receipt, UNKNOWN if absent. An absent receipt never authorizes a retry. Session mismatch is 409.
- `GET /api/evidence`: read-only immutable settlement fixture values, per-view digest, source pin, missing live financial measures; no source cut or completeness invented.
- `GET /api/scenarios` and `/api/scenarios/{id}`: nine fixed F01–F03 fixtures, 35 replay steps with per-payee values, expected refusal and public conservation checks. Disposable books are separate from workspace state; GET does not append commands, receipts or reservations. No caller-provided policy or write endpoint. The two allocation orders and 500bps policy are explicit test fixtures, never a selected operating policy.
- `GET /api/preview/{advance_id}?instance_id=…`: restore the current accepted journal into a disposable F04 machine and test draw there. Response binds instance, advance and observed state digest; `write_authorized=false`. No active reservation, receipt or journal mutation. It is a point-in-time diagnostic; an actual later command rechecks all gates.
- `GET /api/readiness`: source-byte integrity and behavior-level mapping of all 20 requirements, local capabilities, missing decisions, upstream prerequisites and release authorization. No upstream node is marked complete. Source equality does not qualify an SDK or service.
- `GET /api/export`: accepted in-memory journal, source pin, fixture digest, state digest and replay match. No import or resume endpoint. Not authenticated financial export, bank reconciliation, accounting evidence or durable recovery.

| op | args |
|---|---|
| offer | fixture_id (`sim-committed`, `sim-pending`, `sim-refund`), amount (integer 1..10^12) |
| approve / reject / cancel / bind_settlement / draw / close / default / reconcile | empty object |
| repay | amount, sequence (next positive integer) |

API wraps the pinned FSM without inventing financial terms. `reject`, `cancel`, `default` use fixed synthetic reason labels. Offer role is fixed `fixture-organizer`. No caller-supplied settlement body, product terms, identities, credentials, filenames or URLs. The refund fixture is explicitly adverse: 10000 synthetic refund face with burden UNDEFINED; it is not a new executed refund policy.

Every bound draw reads the immutable settlement view and does not call settlement mutations. F04 also explicitly permits an unbound draw; it reports UNBOUND and does not claim a COMMITTED observation. UI's guided flow binds first. A process-wide lock serializes commands, snapshot and export in this single-process demo. First transport receipt is returned after later transitions too; GET state is current. Domain errors are stored as REJECTED. Schema/boundary errors reject before applying. Reconcile is read/replay and does not clear UNKNOWN.

Command, recovery and session acknowledgment share the same Web Lock; pending deletion compares the current operation and instance identity so late callbacks cannot erase a newer request. Accepted receipts also validate the inner F04 case, prohibited-effect flags and replay match.

Browser writes persist the pending request **before** one POST and use a Web Lock to avoid same-origin overlapping tabs. Only an identity-bound receipt clears pending. Invalid response/network loss holds UNKNOWN across reload. Storage unavailable/corrupt or Web Locks unavailable disables new writes. Server restart produces a new instance; old requests cannot affect it. Explicit new-session acknowledgment discards the UI pending request but never replays it and does not claim the old outcome known. No automatic polling/retry.

## Upstream adapter replacement prerequisites (NOT_BOUND)

Before consuming promoted commands or finance queries, require exact producer repository/commit/tree, domain/schema, OpenAPI source+generated hashes, generated SDK/toolchain/output hashes, immutable manifest and SEMANTIC_CONFORMANCE profile kind/revision/digest and positive/negative vectors. BOOTSTRAP or a prior profile pass is insufficient. Map command bytes/receipt meanings explicitly; never reuse similar catalogue names.

A future read must carry source mode/profile, operation/order/claim/advance identity, asset/registry and policy revision, source cut, watermark, gap/staleness and completeness. Keep read identity and command outcome separate. Mixed cuts, partial exports, missing pages, stale views and cross-session callbacks remain incomplete. Protocol's stage5/6/7 and Finance design dependencies must actually be adopted and verified before real projection or authenticated export implementation.

Rights/repeated resale/gift/refund/admission remain Protocol/Commerce authority. Financial claim ownership is not ticket ownership. No credit operation grants admission, moves rights or provides a lien. Large-scale RS sharding and optional TL collateral/reward contracts are external future dependencies, not a performance/chain claim by this process.
