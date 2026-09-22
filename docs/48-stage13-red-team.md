# Stage 13 — Builder Red Team

Status: REPAIR LOOP COMPLETE FOR IDENTIFIED CODE FINDINGS; CI PENDING

Reviewed implementation SHA before this report commit:
`6f94e2faf38f674f9aba57633320389ecb0e0384`

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

Unresolved P0: 0.

Unresolved P1 from builder Red Team: 0.

P2: 1 documented evidence-ceiling limitation (RT-10).

## Adversarial scenarios covered by implementation/tests

- remote endpoint denied in local-only mode;
- endpoint userinfo/path/query rejection;
- strict method/path allowlist;
- duplicate-key outer JSON rejection;
- missing model;
- model digest drift;
- malformed/empty/partial/wrong-model response;
- request/snapshot substitution;
- prompt-size and request-size bounding;
- timeout with no implicit retry;
- concurrency backpressure;
- duplicate in-flight request ID;
- cancellation propagation and bounded cancellation state;
- deep immutability of generation options;
- execution receipt bound to provider/model/generator/parameter hash;
- prompt-builder VersionPin bound to the request.

## Evidence ceiling

The builder Red Team is not an independent review.

The tests above exist in source but are NOT YET VERIFIED by an executed runner for the current candidate.

A real Ollama endpoint/model has NOT been executed.

A physically disconnected network test has NOT been executed.

No performance PASS is claimed.

Final Red Team must be re-bound to the exact frozen candidate after manifest stabilization and fresh CI.
