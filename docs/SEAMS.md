# Local port seams

Registry of Capital facade ports. A later node adds its port as a new row here and a `typing.Protocol` in `capital/ports.py`. The test in `tests/test_seams.py` fails when a Protocol has no row, or when a row says `ADOPTED` without an upstream receipt reference.

`ADOPTED` means an upstream contract has actually replaced the local implementation and a receipt (commit, review URL, or profile digest) is cited in **Upstream receipt**. None of the rows below are `ADOPTED`. Local classes are stand-ins. They are not SEMANTIC_CONFORMANCE, and they do not bind the CAP-16 exact producer/SDK tuple. That tuple stays `NOT_BOUND`.

`tests/test_producer_port.py` runs positive and negative command vectors through any `ProducerPort` factory (`run_producer_vectors(factory)`). The pinned factory is `PinnedFsmProducer`. A future adapter must pass the same vectors. Passing them is a local gateway check. It is not a SEMANTIC_CONFORMANCE profile, and it does not qualify Commerce or Protocol.

| Port | Local implementation | Upstream contract | Readiness | Status | Upstream receipt |
| --- | --- | --- | --- | --- | --- |
| StoragePort | `InMemoryStorage` and opt-in `FileWorkspace` in `capital/store.py` | `k-stage5-durable-tx` adopted backend. The local JSON file is not that contract. | CAP-11 | NOT_BOUND | NONE |
| ProjectionPort | `SimulationProjection` in `capital/projection.py` | `fin-ledger-contract` and an adopted finance chart. `SIMULATION_FIXED_V1` is `SYNTHETIC_UNADOPTED`. | CAP-13 | NOT_BOUND | NONE |
| AuthorizerPort | `LocalRoleAuthorizer` in `capital/auth.py` | Identity provider plus AgentGrant/ActionPermit. Synthetic loopback roles are not authentication. | CAP-19 | NOT_BOUND | NONE |
| SignaturePort | `UnsignedSigner` default and opt-in `DevHmacSigner` in `capital/export.py` | stage7 authenticated export. Dev HMAC is `DEV_ONLY` integrity, not an external key. | CAP-15 | NOT_BOUND | NONE |
| ProducerPort | `PinnedFsmProducer` in `capital/producer.py` wrapping pinned `CreditMachine` and `SettlementMachine` | Protocol/Commerce producer tuple, promoted catalogue, generated SDK, and a SEMANTIC_CONFORMANCE profile with its own vectors. Local facade namespace is `capital-local-facade/1` (`capital/contract/facade-v1.json`). | CAP-16 | NOT_BOUND | NONE |
| TermsPolicyPort | `DecisionNoteTermsPolicy` in `capital/terms.py` | `f04-mock-deepening` decided revision of CREDIT_ADVANCE_F04 section 5. The local note `docs/decisions/CAPITAL_FINANCIAL_TERMS.md` is a provisional input, not an upstream adoption. | CAP-01, CAP-04 | NOT_BOUND | NONE |
