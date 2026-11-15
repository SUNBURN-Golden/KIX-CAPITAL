# Event stress measurement binding V1

SIMULATED · provisional · applied=false · funds_executed=false · production NOT_AUTHORIZED.

This is an implementation mapping authored by Codex for `event-stress-report` on
2026-11-03, not independent review or authorship by the requested decision lane.
The six product decisions in [CAPITAL_EVENT_STRESS.md](CAPITAL_EVENT_STRESS.md)
remain authoritative. This note introduces no rates, limits, refund burden,
allocation priority, legal terms, or production authority.

The `CAPITAL_EVENT_STRESS_MEASUREMENT_V1` adapter freezes baseline
`DecisionNoteTermsPolicy.ledger_terms` and `margin_terms(refund_after_draw=False)`.
It copies obligations and sets the measurement projection's refund to baseline
open refund plus the absolute increment once per full claim identity. The
projection is **not a settlement record**. Original claims remain complete and
unchanged; source obligation conservation, refund equations, cash equations and
reclassification invariants are checked before numeric eligibility is reported.

Within the supported domain, `margin.eligible_face` gives mapped outstanding less
hypothetical refund, and `margin.measure` floors that value times the frozen
advance rate over `BPS_SCALE`. Thus its borrowing base equals
`terms._borrowing_base` at the frozen tier; the single-member relative evaluator
also agrees when its increment equals the requested absolute amount. See
`tests/test_event_stress.py` for equivalence, rounding, zero shock, tier freeze,
shared collateral, outside coverage, capacity and immutable capture proofs.
These are local synthetic tests, not semantic conformance or financial advice.

Numeric refund mapping requires valid source equations, `refund_accepted=0`,
`refund_outstanding=refund_face`, `fixture_reclassified=false`, exact mapped
payees, and hypothetical refund no greater than mapped outstanding. Above gross
or KRW max_atoms rejects the whole request. Within gross but above mapped
outstanding is `REFUND_MAPPING_NOT_BOUND` before measurement or aggregation.
Accepted refunds, reclassification, unresolved holders/slices and conflicting
payee mappings remain non-computed. Missing financial policy is UNAVAILABLE,
even for an empty advance book; unrelated fees and forecast readiness do not gate.

The captured fixture universe defines claim coverage, including outside claims
and unfinanced fixtures. Their existing beneficiary map supports eligible face;
no rate is invented for an unfinanced claim. Portfolio/event borrowing base,
headroom and hypothetical breaches aggregate only recorded drawn advances.
Undrawn cases remain relationship witnesses. Existing NOTED reservations prevent
collateral reuse; approval itself creates no reservation.
Exposure is included once for every recorded draw, including defaulted and repaid
cases, using its unchanged current outstanding. A computed breach is diagnostic.

More than one recorded draw or live reservation on a claim (including closed
draw history), slice encumbrances, or a future
multi-claim advance without proven allocation cannot receive allocated bases or
headroom. V1's captured F04 relationships have exactly one claim per advance;
malformed/extra relationship shapes reject or become unavailable, never flatten
into invented multi-claim allocation. Eligible face remains unique per claim.
Per-advance contextual measurements are explicitly NON_ADDITIVE. Partial results
propagate nulls and assert no complete portfolio safety conclusion. No supported
subtotal is advertised as a full total.

The mapping note and source policy note are read and hashed at evaluation time.
Loaded financial note provenance accompanies frozen parsed policy hashes.
Historical policy authentication remains NOT_BOUND. No live routes, commands,
postings, optimization, frontier search or financial execution are added.

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "event-stress-measurement-binding",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "date": "2026-11-03",
  "provisional": true,
  "binding_version": "CAPITAL_EVENT_STRESS_MEASUREMENT_V1",
  "mode": "SIMULATED",
  "applied": false,
  "funds_executed": false,
  "production": "NOT_AUTHORIZED",
  "entries": {
    "absolute_refund_measurement": {
      "status": "ADOPTED",
      "value": {
        "adapter_version": "CAPITAL_EVENT_STRESS_MEASUREMENT_V1",
        "measurement": "capital.margin.measure",
        "allocation": "NOT_BOUND"
      },
      "provided_by": "Codex implementation mapping; not independent policy review",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08", "CAP-20"],
      "rationale": "Bind the authorized absolute shock to existing margin arithmetic only within its proven monetary domain; introduce no financial policy.",
      "provisional": true,
      "basis": "IMPLEMENTATION_MAPPING"
    }
  }
}
```
