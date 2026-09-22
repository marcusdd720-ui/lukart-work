# Stage 13 — Performance / Offline / Local Model Readiness

Status: BASELINE INSTRUMENTATION

Authoritative baseline:
- main SHA: `6985c9623d3ac30a6e0b9b569bd7702b66fa324b`
- tree SHA: `483583a7c9eceaf17955bf29f800e651990cfba7`
- Stage 12 closure receipt: PR #52, `STAGE12_CLOSURE_RECEIPT: CLOSED`
- Stage 12 closure: PASS
- unresolved Stage 12 P0/P1: 0/0

## Decision need

Stage 13 must establish measurable performance evidence and a fail-closed local-model boundary without weakening any Case, evidence, authorization, ledger, replay, rendering, validation or provenance guarantee established by Stages 01–12.

The baseline-instrumentation commit is deliberately non-semantic. It adds measurement and readiness evidence only. Local-provider implementation follows only after a baseline run is bound to an exact SHA.

## Current architecture inventory

Existing authoritative model boundary:
- `lukart_work.contracts.ports.ModelProvider.propose(AIRequest) -> AIResult`.
- Stage 09 uses the stricter `AttestedDraftingProvider` boundary with `propose(DraftingInvocation)` plus `execution_receipt(request_id)`.
- `ModelExecutionReceipt` already binds request, provider, model, generator and model-parameters hash.
- `ControlledDraftingService` validates the provider receipt against the selected `DraftingProfile` before committing a generated Draft.
- `AuditEvent.model_provider` records the provider VersionPin.
- model output remains untrusted and is schema/domain validated before Case state is changed.

No concrete hosted/local/Ollama adapter exists on the live baseline. No product dependency on an external LLM client library exists in `pyproject.toml`.

## Offline dependency inventory — baseline

| Dependency | Function | Network | SaaS | Local equivalent | Classification | Fail behavior |
|---|---|---:|---:|---|---|---|
| PostgreSQL adapter | canonical Case persistence | host-dependent | no | yes | LOCAL_CAPABLE | fail closed |
| filesystem/object storage adapter | source/artifact bytes | host-dependent | no | yes | LOCAL_CAPABLE | fail closed |
| Python/Pydantic runtime | contracts/validation | no after install | no | yes | LOCAL_REQUIRED | fail closed |
| DOCX/PDF rendering dependencies | deterministic rendering | no after install | no | yes | LOCAL_REQUIRED | fail closed |
| ModelProvider implementation | model inference | implementation-dependent | implementation-dependent | not implemented | UNKNOWN | fail closed in Stage 09 service |
| Ollama | optional local inference | loopback/local host | no | yes | NOT IMPLEMENTED | not applicable |
| GitHub Actions | CI / assurance only | yes | yes | local execution possible | REMOTE_OPTIONAL | does not affect runtime CASE semantics |

Stage 13 MUST NOT claim OFFLINE READY until a local provider is implemented and outbound-network denial is covered by tests.

## Readiness / gap matrix

| Requirement | Current evidence | Gap | Risk | Planned acceptance |
|---|---|---|---|---|
| latency / throughput baseline | no Stage 13 benchmark | UNKNOWN | regressions invisible | exact-SHA baseline JSON with repeated measurements |
| peak Python memory | no Stage 13 measurement | UNKNOWN | hidden memory regression | tracemalloc peak for bounded microbenchmarks |
| cold import/start path | not measured | UNKNOWN | poor local startup | repeated subprocess import measurement |
| AI contract validation cost | contracts exist | not measured | local-provider overhead unknown | repeated AIRequest/receipt validation benchmark |
| provider abstraction | Protocol exists | no concrete provider adapter | provider coupling may leak into CASE logic | adapter behind existing provider contract |
| Ollama readiness | none | no endpoint/config/error contract | unsafe implicit network behavior | explicit loopback-default configuration, bounded timeouts, typed failures |
| local-only mode | none | outbound calls not centrally constrained | privacy leakage | fail-closed endpoint policy + tests |
| timeout/retry | Stage 09 catches provider failure | adapter semantics undefined | hangs/retry storms | bounded timeout; no implicit infinite retry |
| malformed model output | Stage 09 schema validation exists | adapter response normalization absent | untrusted output propagation | strict JSON extraction + malformed/empty rejection tests |
| provider switching | profile pins provider/model | no runtime adapter matrix | semantic drift | same AIResult/receipt contracts across deterministic and Ollama adapters |
| determinism | downstream contracts/pins exist | LLM nondeterminism not separated | false reproducibility claims | explicit NON-DETERMINISTIC BY DESIGN for inference; deterministic receipts/hashes |
| privacy/logging | service suppresses provider exceptions | adapter absent | prompt/secret leakage | no prompt/body logging in adapter; no credentials required by Ollama adapter |
| SSRF/arbitrary endpoint | adapter absent | endpoint rules absent | local network pivot | default loopback-only; remote endpoints denied unless explicit opt-in |
| benchmark gaming | no benchmark | no policy in code | misleading PASS | benchmark operates on production contracts and cannot disable validation |

## Baseline methodology

The baseline harness measures existing production contracts without introducing model-runtime behavior:
1. cold Python import/start of key modules;
2. canonical digest throughput;
3. AIRequest validation/round-trip;
4. ModelExecutionReceipt validation/round-trip.

Each warm benchmark records iteration count, min, max, mean, p50, p95, p99 and tracemalloc peak bytes. Cold import uses repeated subprocess executions. No absolute CI time is treated as a product SLO; the baseline is evidence for relative regression analysis on comparable runners.

## Open non-blocking inventory

Several older Stage 11 draft PRs remain open. They predate the Stage 12 landing and are not Stage 13 sources of truth. Stage 13 branches exclusively from the live main SHA above and does not merge/rebase those draft PRs.

## Promotion invariant

Any semantic Stage 13 implementation must follow:

`baseline exact SHA -> implementation -> focused tests -> full regression -> Red Team -> preflight -> exact-SHA CI -> independent review -> guarded landing -> post-landing verification`.

No PASS may be transferred across different SHAs.
