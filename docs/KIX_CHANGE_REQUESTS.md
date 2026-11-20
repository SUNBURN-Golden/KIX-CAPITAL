# KIX settlement and credit contract gaps

Capital's `SIMULATED` seam follows Protocol delivery
`8ba7f6c36373ac0ec49246f51f7471c164ac3a28`. B5 `REQUESTER`, frozen claim
snapshots, settlement variance and shared exposure are defined on this pin.
Callers supply tolerance and limit. The gaps below describe the upstream
behavior Capital would need before extending the seam.

| Missing upstream shape | Why Capital needs it | Protocol section to extend | Current Capital behavior |
| --- | --- | --- | --- |
| Settlement refund attribution in a frozen F04 claim view | Identify how much of a variance is attributable to a refund while retaining the original frozen face. | `CREDIT_ADVANCE_F04.md` §§2, 7.11 | `NOT_BOUND`. The observation reports `refund_component: NOT_BOUND`. |
| Refund attribution on a credit advance or shared exposure view | Attribute exposure to refunds across caller-grouped claims without changing the recorded F04 exposure. | `CREDIT_ADVANCE_F04.md` §7.12 | `NOT_BOUND`. The observation reports `refund_component: NOT_BOUND`. |
| Variance disposition | Determine whether a residual has an authoritative reconciliation outcome. | `CREDIT_ADVANCE_F04.md` §7.11 | `NOT_BOUND`. The observation carries `SETTLEMENT_VARIANCE_NOT_BOUND`. |
| Variance repair | Identify an authorized corrective transition and its effect on a frozen claim. | `CREDIT_ADVANCE_F04.md` §7.11 | `NOT_BOUND`. The observation carries `repair: NONE`. |
| Shared-exposure disposition | Determine what an over-limit observation means for a group across claims. | `CREDIT_ADVANCE_F04.md` §7.12 | `NOT_BOUND`. The observation carries `SHARED_EXPOSURE_NOT_BOUND`. |
| Shared-exposure repair | Identify any authorized change to exposure or reservation following a group observation. | `CREDIT_ADVANCE_F04.md` §7.12 | `NOT_BOUND`. The observation carries `repair: NONE`. |
| Authoritative cross-machine read cut | Establish whether the settlement and credit views belong to one consistent cut. | `CREDIT_ADVANCE_F04.md` §§7.11–7.12 and `READ_MODEL_QUERIES.md` §4 | `NOT_BOUND`. The caller supplies the views. |
| Snapshot freshness and source authority | Tell which supplied view can support a current comparison. | `CREDIT_ADVANCE_F04.md` §§7.11–7.12 and `READ_MODEL_QUERIES.md` §4 | `NOT_BOUND`. Observations reflect the views as supplied. |
| Legal debtor and creditor identity | Identify the parties behind claim and exposure labels for any legal attribution. | `SETTLEMENT_DISTRIBUTION_F01_F03.md` §7.1 and `CREDIT_ADVANCE_F04.md` §§5, 7.12 | `NOT_BOUND`. `legal_debtor_bound` is false. |
| Authoritative shared-exposure group membership | Determine which advance and claim IDs belong to a debtor or pool and whether the set is complete. | `CREDIT_ADVANCE_F04.md` §7.12 | `NOT_BOUND`. `group_id` and membership come from the caller. |
| Legal refund debtor | Identify the party with the refund obligation and distinguish it from the mock requester's role. | `SETTLEMENT_DISTRIBUTION_F01_F03.md` §§5, 7.1, 7.6 and `CREDIT_ADVANCE_F04.md` §5 | `NOT_BOUND`. Partial refunds carry the mock `REQUESTER` bearer label. |
| Requester setoff mechanics and authorization | Determine how a requester's refund cost or shortfall would be set off and who can authorize the operation. | `SETTLEMENT_DISTRIBUTION_F01_F03.md` §§5, 7.6 and `CREDIT_ADVANCE_F04.md` §§3, 5 | `NOT_BOUND`. The mock records refund obligation and acceptance only. |
| Refund-versus-credit-note priority | Know how a refund and an outstanding or proposed note interact when both reference the same claim. | `SETTLEMENT_DISTRIBUTION_F01_F03.md` §§5, 7.6 and `CREDIT_ADVANCE_F04.md` §§3, 5 | `NOT_BOUND`. F04 rejects a positive non-reclassified refund face with `REFUND_OBLIGATION_OPEN` when opening an offer or note. Existing frozen notes keep their face. |
| Applied reason-class refund disposition | Evaluate whether evidence for a reason class can produce an upstream refund effect. | `SETTLEMENT_DISTRIBUTION_F01_F03.md` §§5, 7.6 | `NOT_BOUND`. The separate Capital reason-class overlay is `SHADOW_NOT_APPLIED`. |

## Pending adoption

| Binding | Current Capital behavior |
| --- | --- |
| `READ_MODEL_QUERIES` and `READ_MODEL_SOURCE_MAP` | `NOT_BOUND`. Capital reads its local fixtures. |
| Stage-5 durable runtime | `NOT_BOUND`. Database-free reference verification only. |
| CAP-16 upstream producer tuple and semantic profile | `NOT_BOUND`. The local gate uses the pinned BOOTSTRAP delivery. |
