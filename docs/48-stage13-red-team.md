# Stage 13 — Builder Red Team

Status: BUILDER RED TEAM COMPLETE; PRE-FINAL CI EVIDENCE EXECUTED; FINAL EXACT-SHA RE-BIND PENDING

Base:
`6985c9623d3ac30a6e0b9b569bd7702b66fa324b`

Scope: synthetic CASE-TESTY only.

## Findings and repair history

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| RT-01 | P1 | immutable-options hardening referenced `MappingProxyType` without import | fixed; import added |
| RT-02 | P1 | finite-timeout validation referenced `math.isfinite` without import | fixed; import added |
| RT-03 | P1 | oversized/invalid request body could fail before transport cleanup after active registration | fixed; body serialization/size validation moved before active registration |
| RT-04 | P1 | top-level immutable mapping did not freeze nested option structures, allowing parameter-hash drift | fixed; deep JSON freeze/thaw added |
| RT-05 | P1 | cancellation of arbitrary non-active IDs could grow cancellation state without bound | fixed; only active request IDs can be cancelled |
| RT-06 | P1 | prompt builder identity was not bound to `AIRequest.prompt` | fixed; builder VersionPin is mandatory and checked per request |
| RT-07 | P1 | duplicate in-flight request IDs could interleave when concurrency > 1 | fixed; explicit `_inflight` reservation added |
| RT-08 | P1 | whole HTTP request body had no independent hard bound | fixed; `max_request_bytes` added |
| RT-09 | P1 | self-hosted workflow could execute pull-request code without rejecting foreign fork heads | fixed; same-repository PR guard added |
| RT-10 | P2 | Ollama `/api/generate` does not return the installed model digest, so exact model bytes cannot be atomically attested during generation | documented evidence ceiling; pre/post `/api/tags` digest equality is required and drift fails closed |
| RT-11 | P1 | Stage 11 golden provenance became stale because `validation_pin()` covers executable `.py/.sql` source under `lukart_work/` and Stage 13 added `model_runtime` code | repaired; byte-identical DOCX/PDF confirmed and golden provenance refreshed |
| RT-12 | P1 | direct benchmark execution could not import `tests` and also referenced `ThreadPoolExecutor` without import | repaired; deterministic repo-root bootstrap, missing import and direct-script regression test added |

Unresolved P0: 0.

Unresolved P1 from builder Red Team at the current evidence ceiling: 0.

P2: 1 documented evidence-ceiling limitation (RT-10).

## Adversarial scenarios covered

- remote endpoint denied in local-only mode;
- endpoint userinfo/path/query rejection;
- strict method/path allowlist;
- duplicate-key outer JSON rejection;
- missing model;
- model digest drift;
- malformed/empty/partial/wrong-model response;
- request/snapshot substitution;
- prompt-size, request-size and response-size bounding;
- timeout with no implicit retry;
- concurrency backpressure;
- duplicate in-flight request ID;
- cancellation propagation and bounded cancellation state;
- deep immutability of generation options;
- execution receipt bound to provider/model/generator/parameter hash;
- prompt-builder VersionPin bound to the request;
- direct execution of the post-implementation benchmark;
- fresh-process Stage 11 renderer determinism after Stage 13 provenance expansion.

## Wykonane evidence przed finalizacją manifestu

Run `35832948690` na exact SHA
`a2b9026cf59995774c9fd84c14510cc1b171c068` wykonał:

- focused Stage 13 tests: PASS;
- full repository regression: PASS, 470/470 bez failures/errors/skips;
- JSON Schema validation: PASS;
- package verification: PASS;
- post-implementation benchmark: PASS;
- performance evidence validation: PASS;
- manifest refresh: PASS;
- whitespace: PASS;
- reproducibility clean-diff: FAIL wyłącznie z powodu oczekującej synchronizacji
  `reports/manifest.sha256.json`.

## Evidence ceiling

Builder Red Team nie jest independent review.

Live Ollama endpoint/model nie został wykonany.
Fizycznie odłączony test offline nie został wykonany.
Atomic model-byte attestation podczas inferencji nie jest udowodniona.

Finalny Red Team delta check musi zostać związany z exact SHA powstałym po tej
dokumentacyjno-manifestowej synchronizacji i świeżym CI. Żaden wcześniejszy PASS
nie jest automatycznie przenoszony.
