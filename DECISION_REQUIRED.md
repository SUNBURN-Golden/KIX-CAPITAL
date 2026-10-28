# Verification baseline integration required

The portfolio-cashflow-desk implementation is display-only and requires no new
financial or product policy. Full verification is blocked by existing branch
drift against the baseline used by an unchanged repository test.

`python3 -m unittest discover -s tests -v` ran 846 tests: 845 passed and
`test_coa_candidate.V1UnchangedTests.test_v1_and_golden_files_are_untouched`
failed. It compares guarded files against `origin/main` and reports:

- `capital/overlay.py`
- `capital/ports.py`
- `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`

All three files are byte-identical to this node's starting HEAD
`cde0bc778573ef8d543f2e1bb70a521e06bf4e44`. The differences already exist between
that HEAD and `origin/main` (`aab0a7364c79ef00d34e031e4a827a817f7ae544`).
The isolated guard reproduces the same failure. This node has not edited these
files, the guard, CI configuration, Git refs, or the upstream repositories.

Needed: the supervisor must choose the intended integration baseline before a
fully green CI result can be claimed.

Options:

1. Integrate/rebase the node onto the supervisor's intended current base, resolve
   any dependency conflicts there, and rerun the unchanged verification suite.
2. If this older dependency cut is intentional, have the repository owner define
   an explicit baseline policy for historical node verification. This builder
   must not move `origin/main`, skip the test, or weaken its assertion.

Recommendation: option 1. The newer baseline contains repayment/recovery and port
changes beyond this node's display-only scope; copying individual guarded files
would bypass dependency integration and introduce out-of-scope behavior.

Decision owner: KIX Capital supervisor/repository owner, who controls Git
integration. No commit, push, PR, issue, comment, or external message was made.
See `docs/VALIDATION.md` for all local results, including the loopback-port
remapping used to avoid unrelated services on ports 8765 and 8766.
