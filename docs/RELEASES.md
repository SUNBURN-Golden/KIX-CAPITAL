# Releases

Local unsigned simulation artifacts. A note here records what a same-tree build produced. It does not publish, sign, or deploy.

`signed: false` and `published: false` are properties of the artifact. `mode` is `LOCAL_SIMULATION_ARTIFACT`. There is no PyPI release, no external signature, and no production deployment. The in-process `SignaturePort` can leave an export manifest unsigned (`NOT_BOUND`) or attach an opt-in `DEV_ONLY` HMAC. That HMAC is integrity for one local workspace key, not authentication and not an external signature of this zipapp. Hosting and release channels are not chosen here.

The version is only `__version__` in `capital/__init__.py`. `--version` and `GET /api/state` `version` repeat that string. The Protocol pin is the `commit` already stored in `capital/vendor/manifest.json`. Vendor bytes stay on that pin.

Two builds with the same interpreter and the same source tree produce the same SHA256. That check is same-environment only. It is not a cross-platform reproducibility claim.

## 0.2.0

- Version source: `capital/__init__.py` `__version__` = `0.2.0`, synchronized with `package.json` and its lockfile.
- Artifact: `build/bundled-a/capital-0.2.0.pyz` (local build only).
- Protocol pin: `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`; vendor bytes and manifest unchanged.
- Mode: `LOCAL_SIMULATION_ARTIFACT`; signed: false; published: false.
- Contents: the existing stdlib simulation, static assets and five pinned vendor files, plus exactly nonrecursive `docs/decisions/*.md`, `docs/CAP_COVERAGE.md` and `scripts/decision_ledger.py`. Raw bytes are hashed per file in `RELEASE-MANIFEST.json`; no tests, keysets or workspace files are added (the pinned vendor test remains).
- Runtime: checkout-free provisional bound terms, decided settlement policy, underwriting and decision index. `notes_source` distinguishes checkout, bundled bytes, explicit override or no readable input. `note_sha256` hashes each actual input: terms/underwriting and decision-body anchor use the financial-terms note, policy uses the settlement-policy note, and rows use their named notes. Missing expected rows remain `PENDING`; readable invalid rows retain `INVALID` and their source/hash. Explicit overrides never fall back, including failure.
- A `.pyz` serves build-time note bytes and does not follow later checkout edits. Bundling grants no upstream adoption or operational authority. Legal/tax entries remain working assumptions pending professional review.
- Verification: same-interpreter byte-identical builds and stdlib loopback smoke with note-derived interest, remainder, sim-day and workspace restart provenance checks; see `BUNDLED_POLICY_RUNTIME_EVIDENCE.md`.
- SHA256: `f3b2f3db744c88fb85b435e03950b4a24450c68397cf5a87438ef25644ca1af2` (same interpreter; local unsigned build).
- Out of scope: publishing, external signing, credentials, deployment, policy changes and upstream adoption.

### 0.2.0 — merged-main rehearsal (2026-10-25)

- Artifact: `build/merge-bundled-a/capital-0.2.0.pyz`; identical second build in `build/merge-bundled-b/`.
- SHA256: `29dc4a74bba45cfac215f1e77b0f2ea7577bdb7e686b0f155c8751d57c020448` (same interpreter; local unsigned build).
- Retains main's repayment posting, default recovery, claim slices and shadow vectors. Their decision-note loaders read the bundled Traversables; absent or malformed inputs stay unbound.
- Authorized archive scope and manifest format are unchanged. `LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`; every rehearsal is SIMULATED/provisional.
- The initial 0.2.0 build record above and 0.1.0 record below remain historical records. Current merge verification is recorded in `BUNDLED_POLICY_RUNTIME_EVIDENCE.md`.

## 0.1.0

- Version source: `capital/__init__.py` `__version__` = `0.1.0` (same string as `package.json`; the Python module is the source).
- Artifact: `dist/capital-0.1.0.pyz`.
- Protocol pin: `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` (vendored files, byte-locked; not edited by this packaging step).
- Mode: `LOCAL_SIMULATION_ARTIFACT`.
- signed: false.
- published: false.
- Contents: stdlib zipapp of the local simulation, the static assets, `capital/vendor/manifest.json`, and the five manifest-listed vendor files including `test_mock_credit.py`. `RELEASE-MANIFEST.json` stores a per-file SHA256 and does not hash itself.
- SHA256: filled in by the local build (`python3 scripts/build_release.py --out dist`). Not a published digest.
- Out of scope: PyPI, external signing, deployment.

## Template

Copy this section for a later local note. Do not invent rates, fees, limits, or a publish target.

### Version

- Version (single-sourced from `capital/__init__.py`):
- Protocol commit (from `capital/vendor/manifest.json`, unchanged by packaging):
- Artifact name: `capital-<version>.pyz`
- SHA256 (local build, same interpreter):
- Mode: `LOCAL_SIMULATION_ARTIFACT`
- signed: false
- published: false

### Contents

- stdlib zipapp of the Capital local simulation
- pinned vendor files, byte-identical to `capital/vendor/manifest.json`
- `RELEASE-MANIFEST.json` per-file sha256

### Out of scope

- PyPI publish
- external signing (the local SignaturePort seam is not an external key; stage7 authentication is not this artifact)
- production deployment
