# Portfolio history comparison: integration baseline required

The implementation and narrow tests are complete. Full CI readiness is blocked by
the existing `test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched`
guard against `origin/main`.

This node's HEAD is `cde0bc778573ef8d543f2e1bb70a521e06bf4e44`;
the locally available `origin/main` is
`aab0a7364c79ef00d34e031e4a827a817f7ae544` (12 newer commits). The guard reports
`capital/overlay.py`, `capital/ports.py`, and
`docs/decisions/CAPITAL_UPSTREAM_BINDING.md`. These files are byte-identical to
the node's HEAD and have no builder edits. The five vendor files and manifest
are unchanged. No test or CI gate has been weakened.

Final verification: narrow suite 105/105; full unit suite 864/865 (this single
guard failure); Chromium browser suite 69/69 with the temporary port override;
acceptance 7/9 stages (unit guard and default browser port collision fail).
Storage conformance, vendor tests, all 269 claim checks, package smoke, seeded
demo and all four SIMULATED journeys pass. The default acceptance ladder remains
failed and is not reported as a pass.

Needed: a supervisor-selected integration baseline that includes the intervening
main changes, followed by verification of this node on that baseline. The builder
has left all task edits uncommitted and has performed no git/GitHub mutation.

Options:

1. Apply the completed task diff to the supervisor's current integration worktree,
   resolve any integration differences, and rerun the narrow and local CI checks.
2. Update/rebase this node branch onto the selected main baseline while preserving
   its uncommitted task edits, then resolve and rerun the same checks.

Recommendation: option 1, so the supervisor can review integration alongside the
other merged nodes without altering this node's protected baseline files in isolation.
Decision owner: the KIX Capital program supervisor/repository integrator.

The default browser ports 8765/8766 also belong to unrelated local services. The
unchanged browser suite can run with the temporary config documented in
`docs/VALIDATION.md`, which changes only its four server ports/base URLs to
18765–18768. No unrelated service was stopped and no committed CI configuration
was changed. This is a local runner accommodation, not a product-policy decision.

Results remain SIMULATED. No new financial, legal, accounting, provider, ownership,
or deployment decision is proposed. See `docs/VALIDATION.md` for executed commands
and results; full CI readiness is not claimed.
