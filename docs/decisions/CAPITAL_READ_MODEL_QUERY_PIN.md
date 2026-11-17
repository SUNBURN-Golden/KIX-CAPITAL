# Read-model query draft citation registration

PROVISIONAL PRODUCT DECISION. SIMULATED local consumer rehearsal only;
production is NOT_AUTHORIZED and all real-provider execution remains NOT_BOUND.

This addendum applies the explicitly requested read-model-credit-queries scope
and JunTae's adopted 2026-11-02 policy. It supersedes only the read-model table's
membership in CAPITAL_UPSTREAM_REPINS.md §3.2 and §3.6: the table now belongs to
its own EXECUTABLE_CITATION surface at the full SHA below. The older note remains
historical evidence; its vendor, AI and governance requirements still apply.
The five vendor reference files and manifest remain at 7481b0e with their locked
SHA256 values. AI citations remain at e2a029d. This does not vendor the draft,
change Protocol/Commerce, claim adoption, authenticate receipts or authorize funds.

The source is kix-protocol docs/contracts/READ_MODEL_QUERIES.md draft 0.1,
§2.11–2.13, §3 and §8. The exact citation pin is the task's planned 244595d;
this registration records that already-authorized consumption scope. No new
upstream revision is selected. Future changes require the existing atomic
source/table/vector/evidence procedure; automatic fallback remains forbidden.
Visibility and paging remain UNDETERMINED. No list routes are authorized.
Without --protocol-dir, the read-model acceptance command reports SKIPPED and
contributes no passed rows. A supplied checkout is read-only citation evidence,
not runtime upstream execution. The current registered draft pin is HOLD.

The re-pin checker consumes this addendum alongside the original eight adopted
entries, hashes both policy inputs and rejects changes to either policy beyond
the declared candidate SHA replacement. Its tests cover independent and combined
vendor, AI and read-model citation moves and missing or weakened registrations.

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decision_id": "read-model-query-pin-decision",
  "decided_by": "JunTae 2026-11-02 adopted policy; read-model-credit-queries task scope",
  "date": "2026-11-09",
  "provisional": true,
  "entries": {
    "read_model_query_pin": {
      "status": "ADOPTED",
      "value": {
        "surface": "read_model_draft_pin",
        "previous_surface": "vendor_pin",
        "pin": {
          "sha": "244595db1524cbb1a01148baa07d6d28cd1b8dc6",
          "class": "EXECUTABLE_CITATION",
          "vendored": false,
          "bound_tables": [
            "tests/read_model_claims.json"
          ]
        },
        "source_doc": "docs/contracts/READ_MODEL_QUERIES.md",
        "assessment": "HOLD"
      },
      "provided_by": "JunTae 2026-11-02 adopted policy; explicit read-model-credit-queries scope",
      "date": "2026-11-09",
      "cap_rows": [
        "CAP-15",
        "CAP-16"
      ],
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "rationale": "Register the explicitly requested draft citation separately from the SHA256-locked vendor surface; preserve one active pin per surface."
    }
  }
}
```
