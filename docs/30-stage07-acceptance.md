# Stage 07 — Procedural Intelligence Engine acceptance

**Status:** PRE-MERGE ACCEPTANCE EVIDENCE — NOT CLOSED  
**Baseline:** `768121f5d8e4d25dc22dda4bed69b2149918d8e3`  
**PR:** #6 — `codex/stage07-procedural-engine`

## Scope accepted for Stage 07

Stage 07 is limited to the Procedural Intelligence Engine:

- organ / jurisdiction / venue applicability;
- standing / authority;
- filing topology and channel requirements;
- formal requirements, signatures, copies and attachments;
- procedural deadline trigger handling;
- explicit applicability states `UNKNOWN / UNRESOLVED / ABSTAIN`;
- deterministic findings and severity;
- exact provenance to LegalRule / LegalSource revisions;
- strict Fact/Evidence boundary for procedural context;
- reuse of existing PostgreSQL RLS, CAS, idempotency, audit and outbox controls.

Stage 08 Document Planner, Stage 09 drafting, rendering, external filing, ROS runtime and deployment remain explicitly excluded.

## Implementation acceptance

The implementation adds `lukart_work.procedural` without altering Stage 06 registry semantics or creating a second writable CASE source of truth.

Canonical legal/procedural authority remains the existing `LegalSource` and `LegalRule` lifecycle. The executable procedural specification is serialized into the canonical `LegalRule.requirement` payload. `ProceduralRuleBinding` is an immutable exact-revision execution projection and must match that canonical payload and source set before execution.

Procedural writes reuse `CommandService.execute`, including authenticated authorization, HUMAN-only mutation for Stage 07, case advisory locking, case-sequence CAS, actor-bound idempotency, immutable audit events, atomic outbox and rollback behavior. The binding projection is stored in the existing RLS-protected `lw_core.objects` store.

`AssessProcedure` is read-only. It does not create Facts, Deadlines, Filings, Plans, Drafts or legal effects.

## Evidence boundary

A user or other unverified statement does not become a procedural FACT.

- `FACT` context requires exact current CONFIRMED source-backed Fact revisions, live HUMAN FACT_ACCEPTANCE, current ACCEPTED non-disputed Evidence and available source bytes.
- `CLAIM / HYPOTHESIS / INTERPRETATION` causes ABSTAIN when the datum is required.
- `UNKNOWN` remains UNKNOWN.
- `UNRESOLVED` remains UNRESOLVED.
- unsupported business-day deadline calculation ABSTAINS because Stage 07 has no authoritative business-calendar provider.

## Verification evidence already obtained

On exact head `d316bd1a270b1e3aa019240e1a5e0963601e3734`, GitHub Actions run `35319253098` executed the strengthened implementation after the Red Team canonical-authority repair.

Observed results:

- Focused Stage 07: **10 tests PASS**.
- Full regression: **194 tests PASS**, 0 failures, 0 errors, 0 skipped.
- Independent JSON Schema validation: **76 schemas PASS**.
- Package verification: **77 checks**, including 76 JSON files, PASS.
- Global manifest refresh: **261 entries**.
- Stage 07 integrity: PASS.
- Whitespace: PASS.
- Reproducibility was the only remaining failing job step because newly generated schemas/reports/manifest had not yet been committed.

The generated workflow artifact from that exact run was downloaded and used as the materialization source for the generated Stage 07 schemas and reports. This document does not treat that earlier run as the final merge gate because later materialization commits change the PR head.

## Red Team result incorporated before freeze

Red Team identified that an independently executable procedural spec stored only in auxiliary binding metadata could behave as a second authority.

Repair: the exact canonical serialized spec is now stored in the canonical `LegalRule.requirement`; execution verifies exact equality between that canonical payload and every binding revision. The golden test asserts this equality.

No remaining Red Team finding is accepted merely by documentation. Final acceptance still requires a clean exact-head CI and exact-SHA review.

## Acceptance matrix

| Control | Pre-freeze result |
|---|---|
| Procedural dimensions: organ/jurisdiction/venue/standing/topology/channel/formal/signature/copies/attachments/deadline | PASS in focused/golden tests |
| User claim cannot silently become FACT | PASS |
| UNKNOWN / UNRESOLVED / ABSTAIN preserved | PASS |
| Exact rule/source provenance | PASS |
| Canonical LegalRule authority; no second rule SSOT | PASS after Red Team repair |
| RLS isolation and object immutability | PASS |
| CAS / concurrent update | PASS |
| Actor-bound idempotency / exact replay | PASS |
| Transaction rollback / audit / outbox atomicity | PASS |
| Cross-scope and SERVICE/AI mutation denial | PASS |
| Full regression / backwards compatibility | PASS on `d316bd1…` |
| Final exact-head reproducibility | PENDING |
| Independent exact-SHA review | PENDING |
| Merge / exact-main post-merge verification | PENDING |

## Gate

This acceptance report authorizes only the final Stage 07 assurance sequence:

`materialize generated evidence → exact-head CI → exact-SHA review → repair loop if required → merge → exact-main verification → closure receipt`.

It does **not** mark Stage 07 CLOSED and does **not** authorize Stage 08 until that sequence is complete.
