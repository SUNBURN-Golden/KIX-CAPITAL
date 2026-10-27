# facts-cursor-export implementation evidence

This node implements the SIMULATED typed facts candidate. `source_cut` and
`authentication` remain `NOT_BOUND`; it is not `k-stage7-authenticated-export`.
All books and journeys below use synthetic local fixtures. No upstream or
vendor file, financial term, credential, production service or real funds changed.

The run used branch `agent/capital-facts-cursor-export`, based on HEAD
`aab0a7364c79ef00d34e031e4a827a817f7ae544`, with the implementation uncommitted.
No commit, push, PR, issue or external comment was made.

## Commands actually run and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p test_facts_export.py -v` | 8 passed. |
| `python3 -m unittest discover -s tests -p 'test_facts*.py' -v` | 14 passed; repeated successfully after integration. |
| `python3 -m unittest discover -s tests -v` | Initial run: 1,138 tests, 4 failures described below. Clean rerun inside acceptance: 1,138 passed. |
| `python3 -m unittest discover -s tests -p test_auth.py -v` | 15 passed after extending the instance-fenced probe. |
| `python3 -m unittest discover -s tests -p test_finance_vectors.py -v` | 54 passed after extending the route counts. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed, also passed in acceptance. |
| `python3 -m compileall -q capital` | Exit 0, repeated after artifact regeneration. |
| `node --check capital/static/app.js` | Exit 0, also passed in acceptance. |
| `npm ci` | Exit 0; 3 existing lockfile packages installed, audit reported 0 vulnerabilities. |
| `npm run test:browser` | First default-port attempt: exit 1, EADDRINUSE. Acceptance rerun with the port-only adaptation below: 69 passed. |
| `python3 build/facts_local_ci.py acceptance` | Runs `python3 scripts/acceptance.py`; all 9 stages passed, `build/acceptance-evidence.json` has `ok:true`. Counts: unit 1,138; storage 19; vendor 7; upstream claims 311; browser 69; packaged smoke 8; seeded demo 1; integrated simulated journeys 4; node syntax exit 0. |
| `python3 scripts/facts_vectors.py --write` and `--check` | 133 corpus files written explicitly; subsequent byte check passed. |
| `python3 scripts/auth_matrix.py --write` and `--check` | Generated route matrix and doc blocks; check passed. |
| `python3 scripts/docs_surface.py --check` | 33 routes, 174 artifacts, 9 stages; passed. |
| `python3 scripts/manifest_vectors.py --check` | 19 existing files matched, with no regeneration. |
| `python3 scripts/closeout_digest.py --write` | Generated 4,518 bytes from the fresh, passing acceptance evidence. |
| `python3 scripts/finance_vectors.py --write` | Generated 98,712 bytes, including the fresh closeout and added facade definitions. |
| `python3 scripts/pack_vectors.py --write` | Regenerated the 9 owned pack artifacts. |
| `python3 scripts/finance_vectors.py --check`, `python3 scripts/closeout_digest.py --check`, `python3 scripts/closeout_digest.py --check-evidence`, `python3 scripts/pack_vectors.py --check` | All exit 0 after regeneration. |
| `python3 scripts/fold_fuzz.py --check` | Passed: 16 seeds, 736 commands; also passed in the clean full-suite rerun. |
| `python3 -m capital.verify --facts tests/vectors/facts/clean` | Exit 0; 7 pages, 27 rows, integrity verified. |
| `python3 -m capital.verify --facts tests/vectors/facts/semantic/row-amount` | Expected exit 1, `ROW_MISMATCH:0`. |
| `python3 scripts/build_release.py --out build/facts-dist-a` and `--out build/facts-dist-b` | Both produced SHA256 `945082dc2224dddf8637c65343c7e097bf592b2cc61f278a97e6f626cadf87a3`. |
| `cmp build/facts-dist-a/capital-*.pyz build/facts-dist-b/capital-*.pyz` | Exit 0; byte-identical. |
| `python3 scripts/smoke_release.py build/facts-dist-a/capital-*.pyz` | All 8 checks passed. |
| `python3 -m unittest tests.test_closeout_digest tests.test_finance_vectors tests.test_evidence_pack tests.test_auth_matrix tests.test_docs_surface tests.test_handbook -v` | 188 passed after artifact regeneration. |
| `git diff --exit-code capital/export.py capital/vendor tests/golden tests/vectors/manifest playwright.config.cjs` | Exit 0 after the local wrapper restored the config. |
| `git diff --check` | Exit 0. |

The five vendor files were additionally hashed with Python `hashlib.sha256` and
compared to `capital/vendor/manifest.json`: 5/5 matched pin
`7481b0e16ce9b903abbffa62249bb91cd9e63cfe`.

## Fixes and deviations

The initial full run found an auth route probe missing `instance_id`, and two
finance assertions retaining the old 30 GET / 42 total route counts. The probes
and exact counts were extended to 32 GET / 44 total routes. A fourth failure was
the fold-fuzz read-only guard observing that finance test edit and its import
cache during the running suite. The clean rerun held the tree stable and passed.
No assertion or CI gate was weakened.

Unrelated applications occupied loopback ports 8765 and 8766. The ignored local
wrapper `build/facts_local_ci.py` temporarily substituted 18765–18768 throughout
`playwright.config.cjs`, including the default server command, then ran the
unmodified acceptance script. It retained every browser project/test and
`reuseExistingServer:false`, and restored the exact original config bytes in
`finally`. No unrelated listener was stopped. `ss -ltnp` confirmed that none of
the four temporary test server ports remained listening after acceptance.

The implementation follows the adopted separate-digest and empty-overlay-absent
policy. The corpus uses the built-in seed book plus a logical clock and default
anchor, so offline verification needs only the trusted built-in fixtures. The
row-reorder attack swaps adjacent JOURNAL/OVERLAY rows while preserving each
source list, specifically reaching the final row-rebuild check. No product or
financial decision was needed.

## PR fix round 1 after the main merge

Verified the uncommitted fix on branch `agent/capital-facts-cursor-export`, HEAD
`84c5766`. The reported failure was the fold-fuzz subprocess exceeding its
120-second test timeout. The unchanged checker passed locally in 25.2 seconds,
so that timeout did not reproduce in this workspace. Profiling identified
redundant journal deep copies and repeated digest calculations in `capture`.
The fix replays detached journals from the parsed, checksum-verified envelope,
compares them to the live journals before replay, and reuses computed digests.
All seeds, commands, prefix checks, independent replays, file writes, reloads,
hash-seed runs and the 120-second timeout remain in place. The corpus was not
regenerated. A new regression checks that checksum-valid persisted F04 and
overlay journals differing from the live book are both refused.

| Check | Fix-round result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 1,148 passed in 283.025 seconds, including the reported subprocess test. |
| `python3 -m unittest discover -s tests -p test_fold_fuzz.py -v` | 13 passed, including the added divergence regression and both hash-seed subprocesses. |
| `python3 scripts/fold_fuzz.py --check` | Exit 0; 16 seeds, 736 commands; standalone elapsed 23.4 seconds. This is a local observation, not a performance guarantee. |
| `python3 -m unittest discover -s tests -p 'test_facts*.py' -v` | 14 passed. |
| `python3 scripts/facts_vectors.py --check` | 133 canonical/intentional-tamper files matched. |
| `python3 -m capital.verify --facts tests/vectors/facts/clean` | Exit 0; 7 pages, 27 rows. |
| `python3 -m capital.verify --facts tests/vectors/facts/corrupt/entry-byte` | Expected exit 1, `PAGE_DIGEST_MISMATCH`. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `python3 scripts/docs_surface.py --check`; `python3 scripts/auth_matrix.py --check` | Both exit 0; docs surface reports 33 routes, 250 artifacts, 9 stages. |
| `PYTHONDONTWRITEBYTECODE=1 python3 build/facts_local_ci.py browser` | Runs `npm run test:browser` using the previously documented temporary loopback port remap. Initial run alongside unit tests: 68 passed, first auditor panel visibility assertion timed out; its captured page snapshot contains the loaded panel. Isolated full rerun: all 69 passed in 2.3 minutes, without assertion or timeout changes. Config restored afterward. |

The five vendor SHA256 pins and manifest bytes, legacy `capital/export.py`,
goldens, facts vectors and fold-fuzz corpus remain unchanged. No CI configuration
or existing test assertion was changed. No commit, push or external post was made.
All facts results remain SIMULATED, with source authority and authentication
NOT_BOUND. No product decision was needed.
