# Stage 11 — Rendering Engine readiness and acceptance contract

Base: verified live main `74364cb7b648feaff30cff465a5beade8d5f3498`.
Mode: synthetic CASE-TESTY only. No real CASE data or private evidence.

## Boundary

Stage 11 follows the closed pre-render Validation Engine. Its purpose is to turn one exact
currently validated semantic Draft into deterministic DOCX/PDF bytes without creating facts,
legal rules, requests, strategy, document approval, FINAL eligibility, certification, filing or
transmission.

The renderer itself receives only `SemanticDocument + RenderProfile`. CASE resolution,
authorization, freshness and storage are application-service responsibilities outside the pure
renderer.

## Acceptance criteria

| ID | Required guarantee |
|---|---|
| S11-01 | exact current VALIDATED Draft and exact successful Stage 10 execution are required |
| S11-02 | every pre-render check is PASS; render remains NOT_RUN before Stage 11 |
| S11-03 | current Stage 10 review/authority/source/dependency state is rechecked fail-closed |
| S11-04 | a HUMAN creates an exact render authorization; AI/SERVICE cannot self-authorize |
| S11-05 | rendering cannot proceed after any intervening CASE mutation |
| S11-06 | Draft semantic content remains immutable across VALIDATED → APPROVED → RENDERED |
| S11-07 | renderer consumes only SemanticDocument + pinned RenderProfile and is byte-deterministic |
| S11-08 | DOCX and PDF are both A4, binder-safe, paginated and render synthetic Polish Unicode |
| S11-09 | exact rendered bytes are stored case-scoped with hashes and retention controls |
| S11-10 | post-render ValidationRun binds exact rendered Draft, exact DOCX/PDF hashes and render PASS |
| S11-11 | nonblocking pre-render findings are rebound; blocking findings can never reach rendering |
| S11-12 | replay, actor binding, RLS/storage integrity, rollback and stale/corrupt byte handling fail closed |
| S11-13 | output is only eligible for later DOCUMENT_APPROVAL; no DOCUMENT_APPROVAL or FINAL is self-awarded |
| S11-14 | focused Stage 11, full regression, schema/package/integrity/reproducibility and exact-head CI pass |
| S11-15 | independent exact-SHA review is required before canonical merge |

## Explicit non-goals

Stage 12 Audit/Provenance, certification, release/FINAL, external filing/transmission and UI remain
outside Stage 11. DOCX/PDF bytes are output artifacts and never become a source of CASE truth.
