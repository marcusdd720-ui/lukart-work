# Stage 09 — Controlled Drafting acceptance

Status: IMPLEMENTATION UNDER CI ASSURANCE.

The Stage 09 candidate is not CLOSED merely because implementation files or tests exist. Closure requires exact-head CI PASS, generated-evidence reproducibility PASS, exact-SHA review without blockers, merge, exact-main verification and a closure receipt.

## Required evidence

Focused assurance covers:

- golden synthetic GenerateDocument path;
- Draft head remains GENERATED;
- model output is proposal-only and cannot persist domain writes/status authority;
- application-controlled Statement UUIDs;
- replay before model call;
- ABSTAIN without Draft;
- structural/new-fact hiding rejection;
- inference and unsupported-output rejection;
- refs outside approved SectionContract/snapshot rejection;
- Request objective preservation;
- live plan-approval revocation before model call;
- case-sequence mutation between proposal and commit;
- AI actor denial;
- transaction rollback of Draft/trace/audit/outbox.

Full regression, schema validation, package verification, manifest integrity and reproducibility remain CI gates. Synthetic fixtures only.
