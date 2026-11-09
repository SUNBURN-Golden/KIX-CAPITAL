# Compatibility preflight rehearsal (SIMULATED)

`capital/compat_preflight.py` is a stdlib, offline checker that validates a
synthetic `kix-compat-manifest/1` bundle against a caller-supplied expected
tuple. `make_preflighted_fake_producer` in `capital/gate_producer.py` runs that
check before constructing the owned `LOCAL_FAKE_GATE` adapter. The rehearsal
separates three results that must never be conflated:

- `byte_agreement`: `MATCHED`/`MISMATCH` — local bytes equal the expected tuple.
- `semantic_consumption`: always `HOLD` — a byte match never qualifies a
  producer, and BOOTSTRAP grants catalogue-schema binding only.
- `adoption`: always `NOT_BOUND` — CAP-16 and ProducerPort stay unbound.
- `semantic_conformance`: always `false`, and a bundle that declares
  `SEMANTIC_CONFORMANCE` itself cannot authorize anything. The rehearsal
  factory accepts `BOOTSTRAP` bundles only; a byte-consistent manifest whose
  `profile_kind` declares `SEMANTIC_CONFORMANCE` is rejected with
  `BOOTSTRAP_REHEARSAL_ONLY` before any gate is constructed.

## Research citation (read-only)

The manifest shape and canonical encoding follow the Protocol contract
document `docs/contracts/sdk/COMPATIBILITY_MANIFEST_V1.md` at commit
`9b462fd2cd6890cd0d8fbc2930f2cc54255e2915` (SUNBURN-Golden/kix-protocol).
Cited file digests at that revision:

- Git blob `442756c8e2d6f106fad6a47a7177c05ed799efaf`
- file SHA-256 `126a8b95e2216dc9d4cc4e8e8d7a3f221657c40c5e0e07e5819a58a7c1987533`

The citation is a research reference only. It does not re-pin the vendored
`7481b0e16ce9b903abbffa62249bb91cd9e63cfe` executable reference, does not
consume the upstream `bootstrap-1`/`bootstrap-2` manifests, and edits nothing
in either upstream repository. The upstream decision
(`docs/decisions/CAPITAL_UPSTREAM_BINDING.md`, `producer_sdk_tuple`) is
`DEFERRED`; this node rehearses its shape without reopening it.

## Canonical encoding `kix-canonical-json/1`

Implemented separately from Capital's legacy export encoding
(`capital/store.py` `canonical_bytes`) and the CE1 binding gate
(`capital/ce1_claims.py` `decode_input`). Per the cited revision:

- UTF-8 bytes; invalid UTF-8 rejected (`invalid-utf8`).
- Object keys sorted by Unicode code point; compact `,`/`:` separators; no
  insignificant whitespace.
- Arrays preserve order.
- Strings use JSON.stringify-compatible escaping; non-ASCII is NOT `\u`
  escaped (this diverges from Capital's `ensure_ascii` legacy encoder — both
  are kept, goldens unchanged).
- Numbers are decimal integers only: no leading zeros, no `-0`, no fractions
  or exponents (`non-integer`); range ±9007199254740991 (`integer-range`).
- Duplicate keys rejected (`duplicate-key`), including after `\u` unescaping.
- Trailing bytes/newline rejected; verifier depth limit 32 (an implementation
  bound, not a protocol field bound).

The cited document's CE1-specific key/NFC restrictions are NOT imported into
this format; they belong to `capital/ce1_claims.py` separately.

## Expected tuple input

`check_bundle(root, manifest_path, expected_path)` requires an explicit
expected document (format `capital-compat-expected/1`) that is
cryptographically and structurally independent of the candidate manifest:

- `manifest_sha256`: SHA-256 of the candidate's canonical manifest bytes.
- `tuple`: the complete manifest tuple — `manifest_schema_version`,
  `producer.{repository,source_commit,source_tree,protocol_domain,contract_schema_version}`,
  `profile_kind`, `profile_revision`, `profile_sha256`, both `contract`
  references `{path,gitBlob,sha256}`, `generator.{path,sha256,toolchain}`,
  `sdk_output.{path,sha256}`, ordered `vectors[]{name,path,sha256}`, and
  `source_references`.

Comparison is exact: types, field sets, values, and array order. Every tuple
leaf has a one-field mismatch case in `tests/vectors/compat/mismatches.json`.
Expectations are never derived from the candidate manifest.

## Bundle validation

After tuple comparison the checker independently validates the referenced
bytes: SHA-256 of every referenced file, Git blob SHA-1 framing
(`blob <len>\0<bytes>`) on contract and extension-profile references, the
profile's `catalogue-schema-binding only` grant for BOOTSTRAP, the
catalogue's OpenAPI path/digest binding and per-schema digest map against the
contract file, `toolchains.json` Node major version against declared
`node-24` metadata (a declared toolchain is checked, not an installed
runtime), canonical vector bytes, and the `<manifest>.sha256` sidecar
(lowercase hex + newline). Generator and SDK output files are hashed, never
executed or imported.

Every bundle-controlled path — declared and derived (profile path
`sdk/compat/profiles/<revision>.profile.json`, the manifest sidecar) — must
name a regular file inside the fixture root. Absolute paths, `..` traversal,
backslashes, escaping symlinks, missing files and non-regular files are
rejected (`unsafe-path`, `unreadable-file`, `nonregular-file`). Forbidden
self-digest/finality fields (`manifest_digest`, `manifest_sha256`,
`final_commit`, `delivery_head`, `consumer_head`, and for profiles also
`profile_sha256`, `commit`, `source_commit`, `source_tree`) are rejected even
when every dependent hash is refreshed.

## CLI

```sh
python3 scripts/compat_preflight.py --bundle DIR --manifest RELPATH --expected FILE
python3 scripts/compat_preflight.py --check
```

Both modes emit one JSON report line. Exit `0` means byte checks passed
only; exit `1` means a validation failure; exit `2` means CLI misuse.
Neither mode writes or repairs anything. `--check` verifies the committed
corpus (`tests/vectors/compat/corpus.json` pins every file's SHA-256 and
inventory), the canonical-encoding vectors, and the expected tuple against
the synthetic bundle.

## Fixture contract

`tests/vectors/compat/bundle/` is a miniature synthetic bundle labelled
`READ_ONLY_FIXTURE`: inert generator/SDK bytes, a miniature contract-only and
integration-gate OpenAPI document, a fixture profile reference
(`reference/v0.3-rc1/protocol_contract.json`), an extension profile
reference, one canonical vector, `toolchains.json`, the manifest and its
sidecar. Producer identity is synthetic
(`repository` `capital/READ_ONLY_FIXTURE`, all-ones/all-twos commit/tree
strings) — these are not upstream-generated artifacts, and the bundle's
`x-kix-live-http-server`/`x-kix-production-endpoint`/`servers` markers must
stay absent/false. `expected.json` is pinned independently; nothing
regenerates it from the manifest.

## Non-claims

Local hashes establish byte agreement only. They cannot establish Git
ancestry, delivery provenance, semantic conformance, or Commerce adoption.
No generated SDK is consumed, no real producer is contacted, no executable
pin changes, and nothing is promoted.
