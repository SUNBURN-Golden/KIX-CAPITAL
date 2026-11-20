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

## facts-verifier-input-bounds — bounded reader evidence

This node hardened `capital/facts.py` `verify_dir` and the
`python3 -m capital.verify --facts DIR` CLI with a bounded read phase on branch
`agent/capital-facts-verifier-input-bounds`, based on HEAD
`c4114c751ea149865493bd3c734bc5d3c423ae2e`, with the implementation uncommitted.
`source_cut` and `authentication` remain `NOT_BOUND`; this is not
`k-stage7-authenticated-export`. All inputs below are synthetic local fixtures.
No commit, push, PR, issue or external comment was made.

The original read phase enforced `INPUT_LIMITS` (4096 directory entries, 64 matched
`page-*.json` files, 8 MiB per page, 64 MiB aggregate, 32 JSON levels) before
unbounded reads or accumulation. The page-count bound and pathname race check
are superseded by PR fix round 2 below. Non-regular pages refuse on `lstat` with
`INPUT_NOT_REGULAR` and replacement/vanish/modify observed via inode, size or
mtime fails with `INPUT_CHANGED`. Budget failures carry `INPUT_*` reasons,
distinct from the unchanged semantic reasons (`PAGE_SHAPE`, `*_MISMATCH`,
`UNREADABLE`, `NONCANONICAL_ENCODING`). Page ordering, canonical bytes and the
pinned 133-file corpus are untouched. The bounds are demo technical budgets
sized above the adopted producer caps (`MAX_OPERATIONS=500`,
`OVERLAY_MAX_ENTRIES=2000`, `OVERLAY_ENTRY_MAX_BYTES=4096`,
`ENVELOPE_MAX_BYTES=4MiB`, page limit 500), not financial limits; a synthesized
maximum-supported export (500 journal rows near the 8192-byte request cap plus
2000 foldable overlay clock entries, five sealed pages, ~12 MiB) fits the
defaults and only fails on the fabricated journal op (`JOURNAL_REPLAY_FAILED`),
a semantic reason. An in-place rewrite that also preserves size and stays
within the filesystem timestamp granularity is the documented undetectable
fence case — the mtime arm is exercised in tests via an explicit `os.utime`.

## Commands actually run and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p test_facts_bounds.py -v` | 9 passed (after fixing an invalid rewrite byte and a timestamp-granularity false negative in the test fixture itself). |
| `python3 -m unittest discover -s tests -p 'test_facts*.py' -v` | 23 passed; clean and semantic-tamper corpus outcomes unchanged. |
| `python3 -m unittest discover -s tests -v` | 1,311 passed in 305.422s. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | 7 passed. |
| `python3 -m compileall -q capital` | Exit 0. |
| `node --check capital/static/app.js` | Exit 0. |
| `python3 scripts/facts_vectors.py --check` | Exit 0; 133 files match, no regeneration. |
| `python3 -m capital.verify --facts tests/vectors/facts/clean` | Exit 0; 7 pages, 27 rows. |
| `python3 -m unittest tests.test_handbook tests.test_docs_surface -v` | 26 passed. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 36 routes, 273 artifacts, 9 stages. |
| `npm ci` | Exit 0; 3 lockfile packages, 0 vulnerabilities. |
| `npm run test:browser` | Exit 1 at startup; default loopback port 8765 is held by an unrelated service. |
| `npm run test:browser -- --config playwright.local.config.cjs` | Exit 0; 76 passed in 1.9m on temporary ports 28765–28768 (port-only remap of the tracked config; removed afterward, no listener left). |
| `git diff --exit-code capital/export.py capital/vendor tests/golden docs/decisions` | Exit 0; guarded paths byte-identical. |

`tests/test_facts_bounds.py` (9 tests) covers exact-limit accept and one-over
refusal for each of the five bounds, excessive directory entries, unmatched
exotic files, dangling/live symlinks, fifo and directory pages refused without
following or blocking, replacement/vanish/same-size-rewrite/growth-during-read
as deterministic `INPUT_CHANGED`, over-depth and recursion-limit JSON,
duplicate keys, truncated pages, lexicographic page ordering, the synthesized
maximum export under default bounds, CLI exit codes with no partial success, no
source writes and no leaked file contents.

Vendor files and manifest remain pinned and unmodified; `capital/export.py`,
`capital/overlay.py`, `.aiops/`, `docs/decisions/` and `tests/golden/` are
untouched. No decision note, corpus file or route changed. No product,
financial, legal, provider or deployment decision was needed; the bound values
are documented technical budgets, not financial terms.

## facts-verifier-input-bounds — PR fix round 2 (2026-11-16 KST)

Both blocking findings are accepted and fixed in the uncommitted working tree
on `agent/capital-facts-verifier-input-bounds`. The incoming main merge is
already resolved (`MERGE_HEAD=d6ccd93130b86f3dbc37c514ed78cc3c01d8c99d`);
it is left uncommitted as requested. Existing main changes are preserved.

`_read_regular` now checks the pathname with `os.lstat` after reading and
requires the same regular file, device, inode, size and mtime as the opened
descriptor. A vanished pathname, atomic replacement or symlink substitution
therefore returns `INPUT_CHANGED:<file>` even when the old descriptor still
reads the original bytes. The regression swaps the pathname after a successful
`os.read`, with identical replacement bytes, size and mtime, and asserts that
the swap actually ran. Separate cases remove the pathname or substitute a
symlink. No replacement target is followed.

The current default input budgets are 4096 directory entries, **2500 matched
pages**, 8 MiB per page, 64 MiB aggregate and JSON depth 32. The producer accepts
`limit=1..500`; 500 journal rows plus 2000 overlay rows can require 2500 pages
at `limit=1`. A valid 66-row book now verifies end to end as 66 one-row pages.
The maximum-size SIMULATED fixture has 2500 pages, maximum page size 11,950
bytes and aggregate size 22,206,087 bytes. All pages and rows pass input and
integrity checks under the defaults; its deliberately fabricated journal fails
only at semantic replay (`JOURNAL_REPLAY_FAILED`). It is not represented as a
valid financial book. Adding a 2501st page yields `INPUT_PAGES` during directory
enumeration, with page reads patched to fail if attempted. The five-page
`limit=500` maximum-size fixture remains covered too. Sampled one-row maximum
pages are byte-compared with `facts.seal`; the 66-page valid book uses the
producer sealer for every page.

README, integration guidance and the operator handbook now document the full
pagination range, current limits and post-read pathname check. Ordering,
canonical bytes, CLI exits and semantic outcomes are preserved; the 133-file
facts corpus was checked without regeneration. These are local technical
budgets, not financial capacity policy or production throughput claims.

| Local check | Round-2 result |
|---|---|
| `python3 -m unittest discover -s tests -v` | Exit 0; all 1585 tests passed in 525.367 seconds. |
| `python3 -m unittest discover -s tests -p 'test_facts*.py' -v` | Exit 0; 26 passed, including all 12 boundary tests. |
| `python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v` | Exit 0; seven passed. |
| `python3 -m compileall -q capital`; `node --check capital/static/app.js` | Both exit 0. |
| `python3 scripts/docs_surface.py --check` | Exit 0; 38 routes, 276 artifacts, nine stages. |
| `python3 scripts/facts_vectors.py --check` | Exit 0; 133 canonical/intentional-tamper files unchanged. |
| `python3 -m capital.verify --facts tests/vectors/facts/clean` | Exit 0; seven pages, 27 rows, authentication `NOT_BOUND`. |
| Focused `test_handbook.py` and `test_docs_surface.py` discovery | Exit 0; 15 plus 15 passed after the documentation update. |
| `unshare -Urn -- bash -c 'ip link set lo up && exec npm run test:browser -- --output=/tmp/facts-bounds-r2-browser-results --reporter=list'` | Exit 0; all 85 Chromium tests passed in 2.2 minutes. Tracked configuration and assertions unchanged; only loopback enabled in the isolated namespace. |
| Vendor SHA256 and byte comparisons | All five files match manifest pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`; manifest and legacy export match both HEAD and incoming main. `.aiops/` is unchanged. |

Browser output is retained in `/tmp/facts-bounds-r2-browser.log` and
`/tmp/facts-bounds-r2-browser-results`; full unit output is in
`/tmp/facts-bounds-r2-unit.log`. Both tracked report symlinks were
restored to the merge index bytes after the run. Pre-existing local browser
artifacts and the port-remap configuration were preserved under
`/tmp/facts-bounds-r2-existing-browser-5gk526mh`; any regenerated report was
preserved under `/tmp/facts-bounds-r2-final-browser-7sg8qihh` before restoration.

All inputs and replay results remain `SIMULATED`, source authority and
authentication `NOT_BOUND`. No financial terms, real provider, credentials,
deployment or funds were introduced. No commit, push or external post was made.

## facts-verifier-input-bounds — PR fix round 3 (2026-11-20 KST)

The supplied acceptance log ends at the missing `build/acceptance-evidence.json`
upload. A separate CI run from the same runner rollout records Playwright 1.58.2
failing Chromium setup on Ubuntu 26.04 before the same upload error. The
previous PR head used `ubuntu-latest`. This branch already includes main's
`4b0c8b4` runner fix, which pins both jobs that install Chromium to Ubuntu 24.04
and retains the required artifact and every test step. Local Playwright package
checks reproduced the Ubuntu 26.04 installation error in a network namespace
and resolved the Chromium installation plan for Ubuntu 24.04 in a dry run.

The defaults are 4096 directory entries, 2500 matched pages, 8 MiB per page,
64 MiB aggregate, and 32 levels of JSON nesting. A bounded scan of each page's
bytes now checks nesting before decoding and ignores delimiters in quoted strings.
Even input beyond the decoder's recursion limit returns `INPUT_JSON_DEPTH`.
Duplicate keys and truncated shallow pages still return `UNREADABLE`. The reader
requires no-follow and nonblocking opens and compares device, inode, size, mtime
and ctime across `lstat` and `fstat`. Tests substitute a symlink and a FIFO before
open and retain the existing cases for swaps after open. The accuracy of in-place
change detection depends on the filesystem's timestamp resolution.

| Local check | Result |
|---|---|
| Full acceptance ladder on Python 3.12 | All nine stages passed, including 1,602 unit tests and 113 Chromium tests. `build/acceptance-evidence.json` reports `ok: true`. |
| Facts unit tests and corpus byte check | 26 passed. All 133 corpus files matched, and the clean CLI run verified 7 pages and 27 rows. |
| Replayable maximum page-count fixture | 2,500 pages and 2,500 rows verified. The largest page was 5,251 bytes and the aggregate was 11,317,587 bytes. |
| Default directory and aggregate boundaries | 4,096 entries verified and 4,097 refused before page reads. Exactly 64 MiB reached semantic checks and one byte over returned `INPUT_TOTAL_TOO_LARGE`. |
| Oversize CLI input | A sparse file one byte above 8 MiB gave exit 1 and `INPUT_PAGE_TOO_LARGE` with zero accepted pages and no contents in the output. |
| File metadata change | Rewriting a page in place and restoring its size and mtime still returned `INPUT_CHANGED` after ctime changed. |
| Vendored F04 tests | 8 passed. |
| Docs surface, compileall, JavaScript syntax, and diff checks | Passed. |
| Browser suite | All 113 Chromium tests passed. |
| Release | Two builds matched byte for byte. All 11 packaged smoke checks passed. |

The full ladder used a disposable checkout of `227b1d5` with the round-3
verifier and test changes applied and only loopback enabled. The evidence file
describes that local working tree.

The checked-out baseline was already merged with `origin/main` at `b24f175`.
Main's earlier vendor repin to `8ba7f6c` is present in that baseline. All 69
file hashes match its manifest, and the vendor tree, manifest and legacy export
match both HEAD and `origin/main`. The local verification evidence is `SIMULATED`
with authentication `NOT_BOUND`.

## Supervisor conflict resolution

The merge with main at `68bc735` preserves the bounds of 4096 directory
entries, 2500 pages, 8 MiB per page, 64 MiB aggregate, and 32 JSON nesting
levels. Both `capital.verify --facts` and the facts input to
`capital.evidence_crosscut` capture pages through `facts.read_page_files`
and replay them through `facts.verify_raw_pages`. The latter applies page
count, byte and depth budgets to already-captured pages as well.

The cross-cut check hashes captured files in page-name order and extracts the
comparison data from those bytes. A complete, nonempty capture still has a
digest when its verification fails. A filesystem refusal leaves the digest
null and the dependent cross-cut checks `NOT_CHECKED`. The regression tests
cover an oversized page, a dangling
symlink, a malformed page with a complete capture, and a page changed after
capture. The fixtures are `SIMULATED` and authentication stays `NOT_BOUND`.

| Local check | Measured result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 1,624 passed on the full rerun with `PYTHONDONTWRITEBYTECODE=1`. |
| Facts and cross-cut checks | 26 facts tests and 18 cross-cut tests passed. All 133 corpus files match, and the clean CLI verified seven pages and 27 rows. |
| Replayable maximum page count | 2,500 pages and 2,500 rows verified. The largest page was 8,123 bytes and the aggregate was 18,866,587 bytes. |
| `npm run test:browser` | 113 passed from a temporary checkout of the merge index with browser output directed to temporary paths. |
| Vendored F04 and SHA256 checks | Eight tests passed and all 69 SHA256 pins match. Both merge parents have the same vendor tree and manifest at `8ba7f6c`. |
| Static and documentation checks | `compileall`, `node --check`, `docs_surface.py --check` and Git whitespace checks passed. |

The first unit run overlapped a focused test invocation that updated an import
cache during the fold-fuzz file snapshot. The full rerun passed that check
with its assertions intact. The merge resolution is staged for the supervisor.
