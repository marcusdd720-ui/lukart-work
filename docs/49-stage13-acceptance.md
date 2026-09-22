# Stage 13 — Acceptance / Evidence Matrix

Status: DRAFT — REQUIRED CI, PERFORMANCE EVIDENCE AND INDEPENDENT REVIEW PENDING

## Offline Capability Matrix

| Function | Online | Offline | Local LLM | Remote LLM | Current blocker / evidence ceiling |
|---|---|---|---|---|---|
| CASE contracts / validation | yes | yes after dependencies installed | n/a | n/a | regression CI pending |
| deterministic DOCX/PDF rendering | yes | yes after dependencies/fonts installed | n/a | n/a | performance run pending |
| canonical persistence using local PostgreSQL | yes | local-host capable | n/a | n/a | production-equivalent offline benchmark not measured |
| filesystem artifact storage | yes | local-host capable | n/a | n/a | environment-specific |
| Stage 09 controlled drafting | yes | provider-dependent | adapter path implemented | existing hosted path may be used separately | Stage 13 CI pending |
| Ollama inference adapter | yes on allowed endpoint | designed for loopback/local host | implemented | no remote provider added by Stage 13 | live Ollama execution NOT EXECUTED |
| current public legal research | yes | no, unless an authoritative current local corpus is separately available | n/a | n/a | REMOTE_REQUIRED for freshness in current architecture |
| GitHub CI / assurance | yes | no | n/a | n/a | REMOTE_OPTIONAL for product runtime, REQUIRED for repository promotion |

Stage 13 MUST NOT label the entire CASE lifecycle `OFFLINE READY`. The implementation establishes an offline-capable local-model execution path and explicitly identifies remaining remote-required capabilities.

## Dependency Matrix

| Dependency | Local | Remote | Optional | Required | Fail behavior |
|---|---|---|---|---|---|
| Python/Pydantic runtime | yes | no after install | no | yes | fail closed |
| local PostgreSQL | yes | possible | deployment choice | yes for PostgreSQL-backed CASE operations | fail closed |
| local filesystem/object storage | yes | possible | deployment choice | operation-dependent | fail closed |
| rendering dependencies/fonts | yes | no after install | no for rendering | rendering-only | fail closed |
| Ollama | yes | LAN only if explicitly allowlisted and local_only disabled | yes for non-LLM operations | local inference only | fail closed |
| hosted LLM provider | no | yes | yes | no for local-model mode | provider-specific |
| public current legal sources | local corpus not implemented | yes | no when fresh legal research is required | task-dependent | UNKNOWN/ABSTAIN when freshness cannot be established |
| GitHub Actions | no | yes | runtime: yes | promotion: yes | promotion blocked without evidence |

## Performance report

No synthetic or estimated numbers are inserted. Values remain `NOT MEASURED` until artifacts are produced by exact-SHA execution.

| Operacja | Baseline | Po Stage 13 | Delta | p50 | p95 | p99 | Peak RAM | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| cold import | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| canonical digest | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| AIRequest validation | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| ModelExecutionReceipt validation | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| render DOCX+PDF bundle | n/a | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| render bundle validation | n/a | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| revision-ledger test harness replay | n/a | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| Ollama config validation | n/a | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| deterministic digest concurrency 4x64 | n/a | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | PENDING |
| live Ollama inference | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | n/a | NOT EXECUTED |

## Determinism

`DETERMINISTIC`:
- validation and domain contracts;
- canonical hashes/serialization where defined;
- execution receipts;
- render model/layout/artifact identity;
- ledger/replay semantics covered by prior Stages;
- benchmark fixture inputs.

`NON-DETERMINISTIC BY DESIGN`:
- raw LLM inference output.

No byte-exact LLM-output reproducibility claim is made.

## Critical promotion gates

- exact-SHA baseline artifact: PENDING;
- focused Stage 13 tests: PENDING;
- full regression: PENDING;
- schema/package/integrity/reproducibility: PENDING;
- performance artifact: PENDING;
- manifest stabilized: PENDING;
- final exact-SHA Red Team delta check: PENDING;
- independent exact-SHA review: PENDING;
- merge/landing authorization: HUMAN GATE;
- post-landing verification: PENDING.

Current status is not `SEND_READY`.
