# Cross-Repo Contract & Evidence Convergence

> DERIVED VIEW — authoritative semantics live in `contracts/cross_repo/v1/manifest.json`, its schemas and profiles.

Contract: `urn:lukart:cross-repo:convergence:1.0.0`

Architecture: **shared semantics, independent implementations, contract-based conformance**.

## Baselines

| Repository | Commit | Role |
|---|---|---|
| `marcusdd720-ui/lukart-work` | `b4bb235487edef5af18dc83c3430839dad92de6f` | target live main inventory |
| `marcusdd720-ui/lukart-ros` | `451b6226ce2a290277b3ff49f7bb3e540a0f5586` | closed H3/H4 semantic reference only |

## Contract gap matrix

| Area | Inventory | Resolution | Status |
|---|---|---|---|
| schema identity | lukart-work has explicit per-type URNs; no shared cross-repo evidence/result/report identity | explicit neutral schema IDs in this bundle | `CONVERGED` |
| canonical serialization | both repositories sort JSON keys and remove insignificant whitespace, but the profile was implicit | named deterministic canonical JSON profile; adapters preserve historical bytes | `CONVERGED` |
| digest agility | legacy contracts use bare SHA-256 hex values | algorithm-tagged digest envelope supports SHA-256 and SHA-512; legacy values adapt as SHA-256 | `CONVERGED` |
| evidence identity | lukart-work stores content_hash separately from artifact identity; H3 evidence is a bounded reference | immutable evidence envelope with digest-derived evidence_id | `CONVERGED` |
| provenance | lukart-work has rich domain provenance; H3 evidence/result carries execution references | neutral provenance envelope binding producer, operation, implementation digest, inputs and source refs | `CONVERGED` |
| operation result | lukart-work has CommandResult/AIResult/IngestionResult/ReleaseResult; H3 has one operation status vocabulary | neutral result envelope plus backward-compatible adapters | `CONVERGED` |
| reporting | stage reports are machine-readable but stage-specific; text/Markdown are presentation | canonical report envelope; derived Markdown renderer reads only machine-readable bundle data | `CONVERGED` |
| cross-repo conformance | no shared synthetic fixture/gate existed | pinned profiles, synthetic fixtures, adversarial tests and dedicated CI gate | `CONVERGED` |
| runtime coupling | independent repositories | preserved: no lukart_ros import/package/network dependency | `CONVERGED` |

## Normative schema IDs

- `urn:lukart:cross-repo:digest:1.0.0`
- `urn:lukart:cross-repo:provenance:1.0.0`
- `urn:lukart:cross-repo:evidence-envelope:1.0.0`
- `urn:lukart:cross-repo:result-envelope:1.0.0`
- `urn:lukart:cross-repo:report-envelope:1.0.0`

## Invariants

- validation is fail-closed
- success cannot carry errors
- actual effects are a subset of declared effects
- effects are permitted only for success or partial results
- PASS reports require every check to PASS
- evidence_id is derived from the algorithm-tagged content digest
- provenance explicitly binds producer, operation, implementation and inputs
- legacy persisted payloads are adapted, not rewritten
- fixtures contain synthetic CASE-TESTY data only
- Markdown/HTML/PDF are derived views and never authoritative

## Compatibility boundary

Existing `lukart-work` and `lukart-ros` payloads remain authoritative in their own repositories. The convergence layer is an adapter/conformance boundary only: it does not rewrite historical payloads and has no `lukart-work -> lukart-ros` runtime dependency.

Reporting is a derived view over canonical result/evidence/provenance semantics. This Markdown file is not an SSOT.
