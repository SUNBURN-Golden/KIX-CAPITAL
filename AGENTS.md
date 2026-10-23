# Repository verification notes

- `tests/test_coa_candidate.py` byte-guards `capital/export.py` against the main baseline. Add signature adapters in `capital/keyset.py` behind the existing `SignaturePort` rather than changing legacy export construction.
- New files under `tests/vectors/` require hand-maintained entries in `scripts/docs_surface.py` and matching README needles. Run `python3 scripts/docs_surface.py --check`.
- Dev keysets are local DEV_ONLY shared-HMAC fixtures, not authentication. Runtime files require exact mode 0600; committed synthetic fixtures must be copied to mode 0600 temporary files before loading.
