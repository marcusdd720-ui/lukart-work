# Stage 09 — Controlled Drafting acceptance

Status: IMPLEMENTATION UNDER CI ASSURANCE.

The Stage 09 candidate is not CLOSED merely because implementation files or tests exist. Closure requires exact-head CI PASS, generated-evidence reproducibility PASS, exact-SHA review without blockers, merge, exact-main verification and a closure receipt.

## Required evidence

Focused assurance covers:

- golden synthetic GenerateDocument path;
- Draft head remains GENERATED;
- model output is proposal-only and cannot persist domain writes/status authority;
- application-controlled Statement UUIDs;
- sequential and cross-instance replay before model call;
- ABSTAIN without Draft, with auditable terminal replay evidence;
- structural/new-fact hiding rejection;
- inference and unsupported-output rejection;
- refs outside approved SectionContract/snapshot rejection;
- Request objective preservation;
- live plan-approval revocation before model call;
- live legal-rule HUMAN interpretation approval plus VERIFIED citation/source coverage;
- revoked legal authority rejected before model call;
- plan approval, snapshot acceptance and generic case-sequence mutations between proposal and commit;
- AI actor denial;
- transaction rollback of Draft/trace/audit/outbox.

Full regression, schema validation, package verification, manifest integrity and reproducibility remain CI gates. Synthetic fixtures only.


## Red Team / repair evidence before freeze

The pre-freeze repair loop found and corrected:

1. a result-validation loop referenced an undefined invocation variable;
2. strict DraftingProfile configuration was being parsed through the wrong Pydantic input mode;
3. inherited Core regression initially ran under a product-restricted principal rather than preserving historical Core authority;
4. ABSTAIN returned without terminal idempotency/audit evidence, allowing the same command to call the provider again;
5. sequential replay did not prove cross-process behavior, so external-call idempotency now uses a PostgreSQL advisory lock and is tested with independent authority/service instances;
6. legal drafting initially checked only LegalRule.status == ACTIVE and therefore could reuse historical authority after its HUMAN INTERPRETATION Decision was revoked;
7. legal citation coverage is now explicit: current ACTIVE rule + live HUMAN approval + current VERIFIED Citation + current VERIFIED source belonging to that rule;
8. proposal-to-commit races now explicitly cover plan-approval change, snapshot-acceptance change and generic case-sequence mutation.

No repair expands Stage 09 into rendering, release, final validation or external filing.
