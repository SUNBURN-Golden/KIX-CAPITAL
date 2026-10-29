# DECISION_REQUIRED: supervisor alignment of the verification baseline

The advance-case-dossier implementation is complete. One verification gate
cannot pass on the current branch against the moved `origin/main` without a
supervisor-owned Git integration/baseline decision. No new financial terms,
provider, credentials, deployment or Protocol/Commerce change is requested.

## What is needed

Choose the approved integration baseline, then rerun the complete local checks.
The builder must not commit, change shared refs, weaken tests, or adopt other
nodes' changes merely to make this test green.

- Node HEAD / branch base: `5c2398937e12f5a88a2cbd747f5a1edf2f97d95a`.
- `origin/main` at diagnosis: `aab0a73` (`fold-fuzz-determinism`, PR #120).
- `tests/test_coa_candidate.py:144` compares guarded files against
  `origin/main`. It reports `capital/overlay.py`, `capital/ports.py`, and
  `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` as different.
- `git diff --name-only HEAD -- capital/projection.py capital/ports.py
  capital/overlay.py capital/export.py capital/vendor .aiops docs/decisions
  tests/golden` has no output: this task did not change any guarded file.
- An isolated run with
  `PYTHONPATH=tests python3 -m unittest test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched -v`
  reproduces the same failure. The guard has not been edited or bypassed.

## Options

1. **Recommended:** the supervisor integrates this node with the approved
   current main, resolves any interaction with the newer overlay/producer
   behavior, and reruns the full checks. This preserves the existing guard and
   tests the actual combined product.
2. The supervisor explicitly accepts verification against the recorded branch
   base as a temporary integration exception. The present full-suite and
   acceptance results must still be reported as failing, not as CI passes.

## Who decides

The KIX Capital program supervisor owns Git integration and the verification
baseline. JunTae decides if integrating another node exposes a consequential
product-policy choice. The builder has left refs, guarded source files,
vendored references, decision notes and CI unchanged.

See `docs/VALIDATION.md` for actual commands, results and environment deviations.

Final full-suite rerun after refreshing the facade-dependent finance vectors:
855 tests ran; 854 passed and only the guarded moved-main comparison failed.
All 76 browser specs, seven vendor tests, vector/docs checks, syntax checks,
reproducible package builds and eight smoke checks passed. No test server
remains running.
