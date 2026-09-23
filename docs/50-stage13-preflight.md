# Stage 13 — Hardcore Preflight

Status: PREFLIGHTED — PRE-FINAL CI; MANIFEST SYNCHRONIZATION AND FINAL EXACT-SHA GATES PENDING

Evidence snapshot przed tą dokumentacyjno-manifestową synchronizacją:
- repository: `marcusdd720-ui/lukart-work`;
- PR: #55;
- base SHA: `6985c9623d3ac30a6e0b9b569bd7702b66fa324b`;
- observed candidate SHA: `a2b9026cf59995774c9fd84c14510cc1b171c068`;
- observed candidate tree: `dafbf5ecbf18636b23cfd4679fb22c51acc3079a`;
- PR state: OPEN / DRAFT / unmerged;
- mergeable at observation: true;
- changed files: 12;
- additions/deletions: +1810 / -4.

Synthetic CASE-TESTY only.

## Exact diff topology

Stage 13 scope at the observed candidate consists of the Stage 13 workflow,
documentation, local model runtime adapter, benchmark/verifier, tests, plus the bounded
Stage 11 provenance-golden repair required because Stage 13 expanded executable source
covered by `validation_pin()`.

No real CASE data is present.
No `main` mutation or merge has been performed.

This report update together with canonical manifest synchronization creates a new exact SHA.
Therefore all machine-verifiable final gates must be executed again on that new SHA.
No PASS is transferred automatically.

## Critical controls

| Control | Result | Evidence / blocker |
|---|---|---|
| repository / base identity | PASS | live PR base `6985c962...` |
| Stage 12 baseline closure | PASS | Stage 13 branched from closed Stage 12 main |
| synthetic-only scope | PASS | Stage 13 fixtures/evidence are synthetic |
| provider separation from CASE state | PASS | adapter receives no repository/ledger/authority writer |
| provider receipt binding | PASS | request/provider/model/generator/parameter binding covered by tests |
| prompt provenance binding | PASS | prompt-builder VersionPin bound to request |
| model availability / digest drift | PASS | pre/post `/api/tags` checks; drift fails closed |
| atomic model-byte attestation | LIMITATION / P2 | Ollama generate response does not attest installed digest atomically |
| endpoint / SSRF policy | PASS | allowlist, loopback default, userinfo/path/query/fragment rejection |
| proxy bypass risk | PASS | stdlib transport does not use proxy environment |
| resource bounds | PASS | prompt/request/response limits and bounded concurrency |
| timeout / retry semantics | PASS | finite timeout; no implicit retry |
| cancellation / duplicate execution | PASS | bounded cancellation and in-flight reservation |
| options immutability | PASS | nested options deeply frozen after hash binding |
| output trust boundary | PASS | strict JSON + Pydantic + request/snapshot binding |
| foreign-fork self-hosted execution | PASS | same-repository PR guard |
| workflow permissions | PASS | `contents: read`, checkout credentials not persisted |
| privacy / logging | PASS | no prompt/response/credential logging |
| baseline benchmark | PASS | run `35788342721`, exact SHA `6968c9df...` |
| focused Stage 13 tests | PASS on pre-finalization SHA | run `35832948690` |
| full regression | PASS on pre-finalization SHA | 470 tests, 0 failures/errors/skips |
| JSON Schema validation | PASS on pre-finalization SHA | run `35832948690` |
| package verification | PASS on pre-finalization SHA | run `35832948690` |
| performance artifact | PASS on pre-finalization SHA | run `35832948690`, artifact `10738482694` |
| manifest refresh | PASS | workflow generated canonical Stage 13 manifest |
| manifest integrity | PENDING FINAL SHA | manifest is synchronized by this repair; fresh CI required |
| reproducibility / clean diff | PENDING FINAL SHA | must pass with zero diff after synchronization |
| live Ollama execution | NOT EXECUTED | no live endpoint/model evidence |
| physically disconnected offline execution | NOT EXECUTED | no physical offline-run evidence |
| exact-SHA independent review | PENDING | builder review cannot satisfy this gate |
| commit signing / promotion candidate | PENDING | final candidate not yet frozen/promoted |
| human merge authorization | REQUIRED LATER | merge requires explicit HUMAN authority |
| guarded landing | NOT PERFORMED | gate not reached |
| post-landing verification | NOT PERFORMED | landing not performed |
| Closure Receipt | NOT ELIGIBLE | final exact-SHA gates remain open |

## Repair evidence

### Stage 11 provenance golden

Failure on `98e6bd...`:
`test_fresh_process_reproduction_is_stable`.

Evidence showed byte-identical DOCX/PDF and stable fresh-process output.
The drift affected validation/projection/model/layout provenance because `validation_pin()`
covers executable source under `lukart_work/`, and Stage 13 added `model_runtime`.
Golden provenance was refreshed without weakening renderer assertions.

### Post-implementation benchmark

Failure on `09a1b7e...`:
`ModuleNotFoundError: No module named 'tests'`.

Root cause:
direct script execution placed `scripts/` rather than repository root on `sys.path`.
A second latent defect was also found: `ThreadPoolExecutor` was referenced without import.

Repair on `a2b9026...`:
- deterministic repo-root bootstrap for direct benchmark execution;
- missing `ThreadPoolExecutor` import;
- direct-process regression test for `POST_IMPLEMENTATION`.

Run `35832948690` subsequently passed benchmark and performance-evidence validation.

### Manifest

The only failing final step on `a2b9026...` was `Generated evidence is reproducible`.
The workflow diff showed the tracked manifest lacked Stage 13 paths and repair deltas.
The workflow artifact contains the generated canonical manifest and is used as the basis
for this synchronization.

## Preflight decision

`PREFLIGHTED: YES`

`ALL_CRITICAL_CONTROLS_PASS: NO`

`SEND_READY: NO`

`PROMOTION_READY: NO`

Najbliższy gate po tej synchronizacji:
fresh exact-SHA Stage 13 CI na nowym candidate.

Wymagane po nim:
- zero skipped mandatory gates;
- clean manifest/reproducibility;
- final delta Red Team;
- independent exact-SHA review;
- HUMAN merge gate;
- guarded landing;
- post-landing verification;
- Stage 13 Closure Receipt.

No merge is authorized or performed by this preflight.
