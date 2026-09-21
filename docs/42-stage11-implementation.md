# Stage 11 — Rendering Engine implementation

## Application boundary

`RenderingEngineService` adds two commands:

- `RecordRenderAuthorization` — HUMAN-only, exact validated Draft + exact Stage 10 run;
- `RenderDocument` — exact previously authorized APPROVED Draft; HUMAN or trusted SERVICE may
  execute the mechanical render.

`GetRendering` returns a freshness projection. It reports eligibility for a later human
`DOCUMENT_APPROVAL`; it never reports FINAL.

## Trust and freshness

Render authorization requires the exact current VALIDATED Draft, its pinned render profile, the
exact Stage 10 ValidationRun hash, all pre-render checks PASS, render NOT_RUN, no blocking finding,
current unrevoked human review, exact manifest/dependency hashes, current plan/snapshot/legal/source
authority and the exact Stage 10 committed case sequence.

Authorization creates only the immutable VALIDATED → APPROVED Draft revision plus a
`RenderAuthorization` object. Rendering requires that authorization and rejects any CASE sequence
change after it. The application constructs `SemanticDocument` from canonical state; callers
cannot inject one.

## Pure renderer

`lukart_work.rendering.renderer` accepts only `SemanticDocument + RenderProfile`.

The `OFFICIAL_PL:1.0.0` profile uses A4, 30 mm inner margin, 20 mm outer/top/bottom margins and
semantic style tokens. The renderer emits deterministic DOCX and PDF. DOCX is a deterministic
OOXML ZIP with fixed member timestamps and a page-number footer. PDF uses ReportLab invariant mode,
A4 geometry and embedded Vera-family fonts. No renderer code resolves legal or CASE entities.

## Persistence and post-render assurance

Rendered bytes are stored in the existing case-scoped `ObjectStore` category `render`, preserving
exact byte length, SHA-256, retention and RLS boundaries. The APPROVED → RENDERED Draft transition
does not edit semantic content.

A new render ValidationRun:

- binds the exact RENDERED Draft/hash and snapshot;
- carries all pre-render PASS results forward;
- records `render=PASS` under the exact renderer pin;
- binds exact DOCX/PDF hashes;
- rebinds any INFO/WARNING findings to the rendered Draft rather than dropping them;
- is bound by `RenderManifest` and `RenderExecution`.

No `DOCUMENT_APPROVAL`, ReleaseReceipt, FINAL, certification, filing or transmission is created.
