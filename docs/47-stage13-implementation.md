# Stage 13 — Local Model Runtime Implementation

Status: IMPLEMENTED — CI / independent review pending

Baseline branch starts from `main@6985c9623d3ac30a6e0b9b569bd7702b66fa324b`.

## Boundary

Stage 13 reuses the existing Stage 09 trust boundary:

`ControlledDraftingService -> AttestedDraftingProvider -> OllamaProvider -> Ollama API`.

The adapter never receives a repository, UnitOfWork, authorization token or ledger writer.
It therefore cannot mutate Canonical Case state. It only returns an untrusted `AIResult`
payload plus a `ModelExecutionReceipt`, both of which are validated again by the existing
Controlled Drafting pipeline before a Draft can be committed.

Prompt assembly is injected as a `prompt_builder(DraftingInvocation) -> str` whose
`VersionPin` is mandatory and must equal `AIRequest.prompt` for every request.
This prevents the adapter from reaching into Case storage to gather undeclared context
while binding the selected prompt-builder identity to existing Stage 09 provenance.
The host remains responsible for constructing the already-authorized, bounded prompt.

## Ollama contract

The implementation uses:
- `GET /api/tags` for model availability and exact model digest evidence;
- `POST /api/generate` with `stream=false`;
- the existing `AIResult` JSON Schema as Ollama structured-output `format`.

The model digest is read immediately before and after generation. A missing model,
digest mismatch or digest drift fails closed and no execution receipt is released.

Inference is `NON-DETERMINISTIC BY DESIGN`. Deterministic evidence remains:
request binding, provider/model/generator pins, generation-parameter hash, raw-output
hashes already recorded by Stage 09, ledger events, downstream render artifacts and
audit/provenance structures.

## Network and SSRF boundary

Default endpoint is configurable but must pass an explicit host allowlist.
`local_only=True` additionally requires loopback resolution. The adapter rejects:
userinfo, query strings, fragments and endpoint paths. The direct stdlib HTTP transport
does not honor proxy environment variables.

Remote/LAN operation requires both:
1. `local_only=False`;
2. the exact host in `allowed_hosts`.

No shell or subprocess command is constructed from endpoint or model names.

## Failure behavior

The adapter has bounded:
- connect timeout;
- response timeout;
- maximum response bytes;
- maximum prompt bytes;
- concurrency.

There is no implicit retry. This prevents retry storms and duplicate inference.
Backpressure fails closed with `ProviderBusy`.

Cancellation is keyed by request ID. The production transport closes the active HTTP
connection; injected transports receive the same cancellation signal. A cancelled request
cannot release an execution receipt.

Provider exceptions are still suppressed by the existing Stage 09 service into its safe
terminal rejection path, so endpoint details and response bodies are not exposed through
the CASE API.

## Privacy

No prompt, response body, token, endpoint credential or CASE content is logged.
The Ollama adapter needs no credential. The default local-only configuration cannot
address non-loopback hosts.

No cache is implemented. This intentionally avoids stale/private prompt caching in
application memory beyond the bounded execution receipt map.

## Current evidence ceiling

Implemented code and deterministic unit tests exist on the Stage 13 branch.
Live Ollama execution is NOT YET EXECUTED.
Offline operation with a physically disconnected network is NOT YET EXECUTED.
Performance improvement is NOT YET CLAIMED.
Exact-SHA CI and independent review remain required.

## Evidence limitation: model digest

The adapter observes the installed Ollama model digest through `/api/tags` immediately
before and after generation and requires both observations to equal the configured model
VersionPin hash. This detects ordinary model replacement/drift and fails closed.

The current Ollama generate response does not itself contain the installed model digest.
Therefore Stage 13 does NOT claim atomic cryptographic proof of the exact model bytes
executing between those two observations. This limitation is tracked by the Red Team and
must not be overstated in a closure receipt.
