# Capital local API and future integration

`/api/*` is **Capital's local simulation facade**, not a promoted KIX Protocol catalogue, generated SDK, lending endpoint, or live provider adapter. No fallback to `offer_gift`, `settle_capture`, bank, PG or chain exists.

## Local facade v1

- `GET /api/state`: process identity, synthetic fixtures, current F04 views, pinned source, local CSRF token, capacity, workspace status and undecided capabilities. `durable` is `false` for the default memory process and `LOCAL_FILE_WORKSPACE` when `--workspace` is selected. That string is a development file label, not stage5 durable transaction recovery.
- `POST /api/commands`: strict `{instance_id, operation_id, op, advance_id, args}`. ID must start `sim-`; operation identity is immutable. `X-Capital-Token` from the same process and `Content-Type: application/json` required. Maximum request 8192 bytes; maximum retained operations 500 (demo resource bound, not financial policy).
- `GET /api/operations/{operation_id}?instance_id=…`: original ACCEPTED/REJECTED receipt, UNKNOWN if absent. An absent receipt never authorizes a retry. Session mismatch is 409.
- `GET /api/evidence`: read-only immutable settlement fixture values, per-view digest, source pin, missing live financial measures; no source cut or completeness invented.
- `GET /api/projection`: read-only local candidate. Omitted `mode` and `mode=simulation` project the accepted F04 journal plus the three immutable settlement views into `SIMULATION_FIXED_V1`. The envelope is `mode=LOCAL_PROJECTION_CANDIDATE`, `accounting_policy=SYNTHETIC_UNADOPTED`, `tax=NOT_BOUND`, `legal=NOT_BOUND`, `operating_ledger=NOT_BOUND`, `funds_executed=false`, `policy_adopted=false`, `workspace_mutated=false`. `cut` is the current `state_digest`. Any other mode, including `operating`, `ledger`, and `operating-ledger`, returns 400 `NOT_BOUND` and does not project. There is no POST. The handler reads copies only: receipts, reservations, `state_digest`, and `operation_count` stay unchanged. This is not `fin-ledger-contract`, not revenue recognition, and not an operating ledger.
- `GET /api/scenarios` and `/api/scenarios/{id}`: nine fixed F01–F03 fixtures, 35 replay steps with per-payee values, expected refusal and public conservation checks. Disposable books are separate from workspace state; GET does not append commands, receipts or reservations. No caller-provided policy or write endpoint. The two allocation orders and 500bps policy are explicit test fixtures, never a selected operating policy.
- `GET /api/preview/{advance_id}?instance_id=…`: restore the current accepted journal into a disposable F04 machine and test draw there. Response binds instance, advance and observed state digest; `write_authorized=false`. No active reservation, receipt or journal mutation. It is a point-in-time diagnostic; an actual later command rechecks all gates.
- `GET /api/readiness`: source-byte integrity and behavior-level mapping of all 20 requirements, local capabilities, missing decisions, upstream prerequisites and release authorization. No upstream node is marked complete. Source equality does not qualify an SDK or service.
- `GET /api/export`: accepted journal, source pin, fixture digest, state digest and replay match. `durable` follows the same memory / `LOCAL_FILE_WORKSPACE` label as state. No import or resume endpoint. Not authenticated financial export, bank reconciliation, accounting evidence, or stage5 durable recovery. Permission `export:read` (organizer and auditor). Observer receives `403 ROLE_FORBIDDEN`.
- `GET /api/reconciliation`: read-only scratch replay of the accepted journal for the calling role. Writes no receipt. `bank_reconciliation` stays `NOT_BOUND`. `durable` on this response stays `false` because the replay is not the workspace file. This is not the POST `reconcile` command, which stores a receipt and is refused to auditor and observer. Permission `reconciliation:read`.

| op | args |
|---|---|
| offer | fixture_id (`sim-committed`, `sim-pending`, `sim-refund`), amount (integer 1..10^12) |
| approve / reject / cancel / bind_settlement / draw / close / default / reconcile | empty object |
| repay | amount, sequence (next positive integer) |

API wraps the pinned FSM without inventing financial terms. `reject`, `cancel`, `default` use fixed synthetic reason labels. Offer role is fixed `fixture-organizer`. No caller-supplied settlement body, product terms, identities, credentials, filenames or URLs. The refund fixture is explicitly adverse: 10000 synthetic refund face with burden UNDEFINED; it is not a new executed refund policy.

Every bound draw reads the immutable settlement view and does not call settlement mutations. F04 also explicitly permits an unbound draw; it reports UNBOUND and does not claim a COMMITTED observation. UI's guided flow binds first. A process-wide lock serializes commands, snapshot and export in this single-process demo. First transport receipt is returned after later transitions too; GET state is current. Domain errors are stored as REJECTED. Schema/boundary errors reject before applying. Reconcile is read/replay and does not clear UNKNOWN.

Command, recovery and session acknowledgment share the same Web Lock; pending deletion compares the current operation and instance identity so late callbacks cannot erase a newer request. Accepted receipts also validate the inner F04 case, prohibited-effect flags and replay match.

Browser writes persist the pending request **before** one POST and use a Web Lock to avoid same-origin overlapping tabs. Only an identity-bound receipt clears pending. Invalid response/network loss holds UNKNOWN across reload. Storage unavailable/corrupt or Web Locks unavailable disables new writes. Server restart produces a new instance; old requests cannot affect it. A stale tab that still holds the previous instance receives `SESSION_CHANGED` on receipt lookup and keeps UNKNOWN. Explicit new-session acknowledgment discards the UI pending request but never replays it and does not claim the old outcome known. When the restarted process loaded `LOCAL_FILE_WORKSPACE`, that acknowledgment says the workspace was restored rather than calling the book empty. No automatic polling/retry.

The idempotency fingerprint is `operation_id`, `op`, `advance_id`, and `args`. It does not include `instance_id`, `role`, or `role_provenance`. Repeating that command on the new instance returns the stored receipt with `transport_duplicate=true`, the original inner `instance_id`, and the original role label. A different payload for the same `operation_id` is `IDEMPOTENCY_CONFLICT`. Authorization still requires the current `instance_id`.

## Opt-in local file workspace

Default storage is in-memory (`workspace.kind=MEMORY`, `durable=false`). `python3 -m capital.server --workspace DIR` selects one development file. It is not a database, not inbox/outbox, and not cross-host fencing. `k-stage5-durable-tx` stays NOT_BOUND. The word manifest here is the workspace envelope below, not the byte-locked `capital/vendor/manifest.json`.

`DIR/workspace.json` is canonical JSON (`sort_keys`). `DIR/workspace.json.lock` is an exclusive non-blocking `fcntl.flock` held until process shutdown. The write is a temp file in the same directory, `fsync`, `os.replace`, then a directory `fsync`. `payload_sha256` is SHA-256 of the canonical payload bytes.

```json
{"format":"KIX_CAPITAL_LOCAL_WORKSPACE_V1","payload":{"case_fixtures":{},"journal":[],"receipts":{},"state_digest":""},"payload_sha256":"","saved_at":"","saved_by_instance":""}
```

`payload.receipts` maps operation id to `{fingerprint, receipt}`. `payload.journal` is `CreditMachine.export_journal()`. `payload.case_fixtures` maps advance id to the synthetic fixture id. `payload.state_digest` must equal the digest of the machine restored from that journal. A new `instance_id` is always generated after restore. Stored receipts keep the instance that wrote them.

| code | when | server behavior |
|---|---|---|
| `WORKSPACE_UNREADABLE` | truncated, tampered, bad checksum, duplicate JSON key, journal/receipt/fixture/digest mismatch | reads stay up, including an explicit workspace status; POST `/api/commands` is 503; the file is not replaced with an empty book |
| `WORKSPACE_LOCKED` | another process holds the lock | this process does not read through the lock and does not accept writes |
| `WORKSPACE_WRITE_FAILED` | the temp file or replace failed after a command was applied in this process | that receipt stays queryable here; further commands are 503; a later process loads the last complete file and does not see the unpersisted command |

`workspace.status=ACTIVE` is the only writable file state. Degraded mode is fail-closed. It is not a silent empty start.

## Upstream adapter replacement prerequisites (NOT_BOUND)

Before consuming promoted commands or finance queries, require exact producer repository/commit/tree, domain/schema, OpenAPI source+generated hashes, generated SDK/toolchain/output hashes, immutable manifest and SEMANTIC_CONFORMANCE profile kind/revision/digest and positive/negative vectors. BOOTSTRAP or a prior profile pass is insufficient. Map command bytes/receipt meanings explicitly; never reuse similar catalogue names.

A future read must carry source mode/profile, operation/order/claim/advance identity, asset/registry and policy revision, source cut, watermark, gap/staleness and completeness. Keep read identity and command outcome separate. Mixed cuts, partial exports, missing pages, stale views and cross-session callbacks remain incomplete. Protocol's stage5/6/7 and Finance design dependencies must actually be adopted and verified before real projection or authenticated export implementation.

Rights/repeated resale/gift/refund/admission remain Protocol/Commerce authority. Financial claim ownership is not ticket ownership. No credit operation grants admission, moves rights or provides a lien. Large-scale RS sharding and optional TL collateral/reward contracts are external future dependencies, not a performance/chain claim by this process.

## Local authorization boundary v1

This is a **local authorization boundary**, not authentication and not an entitlement policy.

- Synthetic roles are `organizer`, `auditor`, and `observer`, defined in `capital/auth.py` behind `AuthorizerPort`. `LocalRoleAuthorizer` is the only implementation. A real identity provider would replace that port later.
- The role travels as `X-Capital-Role` next to the unchanged loopback `X-Capital-Token`. There are no accounts, passwords, personal data, sessions, token issuance, or credential stores. A missing role header means `organizer`, so existing same-origin callers keep working. An unknown or duplicated role header fails closed with `403 ROLE_UNKNOWN`.
- Every `/api/commands` operation maps to `command:{op}`. Sensitive and ordinary GETs map to `state:read`, `reference:read`, `projection:read`, `receipt:read`, `export:read`, or `reconciliation:read`. `GET /api/projection` is `projection:read` (organizer, auditor, and observer). `command:submit` is the coarse gate checked before a command body is read. An unmapped permission is denied. An unmapped GET path is `404`.
- `organizer` holds the placeholder matrix. `auditor` may read state, reference, projection, receipts, export, and reconciliation, and cannot write. `observer` may read state, reference, the local projection candidate, and receipts only. Observer cannot read export or reconciliation. The server enforces this. A denied command returns `403 ROLE_FORBIDDEN` and does not change `operation_count`, the journal, or an existing receipt. Receipts that do get written carry `role` and `role_provenance=SYNTHETIC_LOCAL_ROLE`. A duplicate returns the original role. The idempotency fingerprint is `operation_id`, `op`, `advance_id`, and `args`. It excludes `instance_id`, `role`, and `role_provenance`.
- Those two receipt fields are stored in the workspace payload and come back on save/restore. A file written before the label, with neither field, loads each such receipt as `role=UNLABELED` and `role_provenance=UNLABELED`. `UNLABELED` is not a session role: `X-Capital-Role: UNLABELED` is `403 ROLE_UNKNOWN`. Loading does not rewrite the file. The next accepted command persists the labeled copy.
- `/api/state` still gives the loopback token to any same-origin page, and its `auth` block reports `identity: NOT_BOUND`. The machine `state_digest` does not include that block. This seam is access control for synthetic roles. It does not establish who a person is.
- Real IdP, KYC, and credential flows stay **NOT_BOUND**. Which real person may approve, draw, or default a real advance is not decided here. The matrix is a synthetic placeholder. Vendor files under `capital/vendor/` are not part of this boundary and stay byte-identical.
