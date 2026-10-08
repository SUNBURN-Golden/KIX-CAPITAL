# Releases

Local unsigned simulation artifacts. A note here records what a same-tree build produced. It does not publish, sign, or deploy.

`signed: false` and `published: false` are properties of the artifact. `mode` is `LOCAL_SIMULATION_ARTIFACT`. There is no PyPI release, no external signature, and no production deployment. Signing belongs to a later SignaturePort. Hosting and release channels are not chosen here.

The version is only `__version__` in `capital/__init__.py`. `--version` and `GET /api/state` `version` repeat that string. The Protocol pin is the `commit` already stored in `capital/vendor/manifest.json`. Vendor bytes stay on that pin.

Two builds with the same interpreter and the same source tree produce the same SHA256. That check is same-environment only. It is not a cross-platform reproducibility claim.

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
- external signing (SignaturePort is a later node)
- production deployment
