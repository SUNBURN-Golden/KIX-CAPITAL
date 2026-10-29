# Verification baseline needs supervisor integration

The SQL auditor implementation and its 35 focused tests are complete. The full
unit suite cannot pass its existing V1 byte guard on this node's current base.
`tests/test_coa_candidate.py::V1UnchangedTests::test_v1_and_golden_files_are_untouched`
compares guarded files against `origin/main`, which has advanced beyond this
node's HEAD (`cde0bc778573ef8d543f2e1bb70a521e06bf4e44`). At verification time,
`origin/main` is `aab0a73` and the guard reports these inherited differences:

- `capital/overlay.py`
- `capital/ports.py`
- `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`

All three files are unchanged from this node's HEAD. `capital/export.py`, the
five vendored references and their manifest, projection/reconciliation code,
existing vectors and goldens also remain unchanged. This is an integration
blocker, not an arithmetic-check failure or an accounting-policy decision.

Options:

1. The supervisor updates/rebases this node onto the current main baseline,
   preserves these uncommitted implementation changes, resolves integration,
   and reruns the unchanged full verification suite.
2. The supervisor provides an isolated checkout at an agreed integration base
   and reruns the unchanged guard and suite there.

Recommendation: option 1. Do not rewrite protected implementations, change git
refs to disguise the difference, skip the guard, or weaken its assertions.

Decision/action owner: the program supervisor, who owns git integration under
the builder instructions. The builder has not committed, pushed, rebased, opened
a PR/issue, or posted a comment. See `docs/VALIDATION.md` for actual command
results and the separate temporary port-only browser-run configuration.
