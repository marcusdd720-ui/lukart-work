# PB02 trusted finalization boundary

Status: **IMPLEMENTED BUILDER CANDIDATE / NOT INDEPENDENTLY VERIFIED / NOT CERTIFIED**.

Repository: `marcusdd720-ui/lukart-work`  
Implementation baseline: `07ccc0a51e6297e9ab1ca9f287b4edea5d0df3da`  
Candidate SHA: **NOT VERIFIED until the external supervisor checkpoints this worktree**.

## Decision need and scope

LW-PB-01 proved that the existing public Core route correctly denied final approval and release,
but PB-017 through PB-020 required a trusted application boundary. PB02 supplies that boundary
without changing the historical LW-PB-01 contract or claiming support for a real legal-document
type.

`FinalizationService` exposes three authenticated HUMAN operations:

1. `RenderDraft` loads the current exact VALIDATED draft, Stage 10 execution and dependency
   hashes, derives `SemanticDocument` server-side, renders DOCX/PDF with the admitted profile,
   validates them, and atomically persists the exact bytes and receipt.
2. `ApproveFinalDocument` reloads and reproduces the persisted render, advances the draft through
   APPROVED to RENDERED, records an exact `DOCUMENT_APPROVAL`, and derives the post-render
   validation run. The caller cannot supply semantic text, PASS results, render hashes, or a
   release receipt.
3. `RequestFinalRelease` reloads the current draft, artifacts, approval and validation evidence,
   invokes the existing pure release evaluator at this single trusted call site, and persists an
   immutable release record whose eligibility is FINAL.

Scoped queries return the projection, release record, or exact DOCX/PDF bytes. FINAL remains a
release qualification; it does not mean SUBMITTED, ACKNOWLEDGED, externally signed, delivered,
or legally certified.

## Enforced invariants

- Native WORK tenant/case capabilities and PostgreSQL RLS remain authoritative.
- AI actors, cross-case access, stale sequence, stale dependency hashes, revoked decisions,
  unsupported profiles, missing storage and unknown contracts fail closed.
- The Stage 10 run must be current, complete, policy-pinned, free of findings, PASS for every
  pre-render check, and explicitly NOT_RUN for render before rendering.
- Render bytes, hashes, lengths, receipt, semantic document, validation projection and profile
  are bound in one persisted record and are reproduced on every read/next transition.
- Approval and release use exact draft/snapshot/artifact/run hashes. Replay is actor-bound and
  idempotent; distinct concurrent commands use the case CAS so only one can commit.
- Artifact writes, domain revisions, objects, audit events, outbox rows, command result and case
  sequence share the repository transaction. Tested write failure rolls the complete unit back.
- Existing historical plan approval remains valid only for a compatible immediately succeeding
  plan revision whose `previous_hash` proves the approved predecessor. This closes the Stage 10
  evidence-revision compatibility gap without accepting arbitrary later plans.

## Verification

Required focused command:

```text
python -B -X utf8 -m unittest -v tests.test_finalization
```

The module deliberately inherits the Stage 10 assurance suite, so it rechecks the upstream
authorization, provenance, drafting and validation behavior using the storage-enabled repository,
then adds finalization-specific happy-path, tamper/injection, rollback, race/CAS, revocation,
scope and evidence-revision tests. A skip is missing evidence, never PASS.

Generated contract schemas are verified with:

```text
python -B -X utf8 verify_package.py
```

The full repository regression remains required before checkpoint handoff. CI, independent
exact-SHA review and certification are **NOT VERIFIED** in the dirty builder worktree.

## Explicit exclusions and next dependency

PB02 does not provide the ten-member final package from PB-021, a real PL type/input/rule/prompt
catalogue, independent legal review, UI/login, deployment, OCR, electronic filing, signature,
delivery or publication. The next product dependency is a scoped immutable package assembler and
read route over the PB02 release plus Stage 12 audit/provenance data. Type admission remains a
separate HUMAN/legal boundary.

The ROS↔WORK Integration Contract v1 remains planning-only. WORK owns all generator state and
HUMAN gates; ROS must not duplicate storage, rendering, release, or package authority.
