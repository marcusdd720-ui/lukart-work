# Stage 10 — Validation Engine implementation

`ValidationEngineService` is an authenticated pre-render application boundary over the existing
PostgreSQL Case Core. It accepts only versioned `ValidationRequest` commands. It reuses the
existing transaction, RLS, case-sequence CAS, immutable revisions, actor-bound replay and atomic
audit/outbox commit. No SQL migration or second CASE state store is introduced.

## Execution and authority

1. A HUMAN principal submits an exact current GENERATED or VALIDATED Draft reference, its hash,
   snapshot hash, current executable policy pin and expected case sequence.
2. Stage 09 guards revalidate current approved plan, live HUMAN plan/snapshot/legal authority,
   exact snapshot and section heads and source bytes. Malformed, stale or unauthorized input
   is rejected without partial writes.
3. Stage 10 runs structured checks and loads an optional exact, current HUMAN review from storage.
   It never accepts caller-supplied machine PASS results in ValidateDraft.
4. Every finding is constructed by the application, ordered deterministically and keyed by UUIDv5
   over the command-derived run ID and complete finding identity. The target revision/hash, run,
   severity and content remain immutable. Validation provenance identifies the exact input Draft
   and executable policy.
5. Run, execution manifest, findings, dependencies, optional GENERATED-to-VALIDATED revision,
   event, outbox and idempotency result commit in one transaction. Any failure rolls back all of them.

Sequential and concurrent exact replay returns the original command result. It does not claim
current eligibility: callers must use `GetValidation`, which rechecks current state. Another actor
or changed command cannot reuse an idempotency identity. Distinct concurrent commands require CAS.

## Layer coverage and evidence ceiling

| Layer | Deterministic enforcement | Semantic boundary |
|---|---|---|
| V1 schema | strict typed input, exact hashes, canonical graph and refs | model validity does not prove truth |
| V2 facts | CONFIRMED, source-backed, live HUMAN acceptance; unsupported prose rejected | HUMAN assessment of dates, amounts, parties, events and prose-to-source meaning |
| V3 evidence | exact ACCEPTED Evidence, non-disputed authenticity, original bytes and Stage 05 extraction/provenance checks | HUMAN assessment of actual evidentiary support/admissibility |
| V4 legal/citations | Stage 09 rule/source/citation authority and applicability, legal statement coverage | HUMAN assessment that legal propositions actually support the asserted conclusion |
| V5 procedure | Stage 07 predicates on canonical context and pinned evidence-bound procedural facts | explicit HUMAN completeness assessment, no invented rule coverage |
| V6 logic | conflicting identical-text type/support/reference bindings; unsupported/incorrect inference guards | HUMAN contradiction and reasoning review; no claim to general automated natural-language logic |
| V7 document/requests | section order, SectionContracts, planned objectives and argument preservation, unique statement IDs | no layout or rendered-document validation |
| V8 language | review completion and finding handling | explicit HUMAN language assessment; model output remains proposal-only |
| V9 adversarial | review completion and finding handling | explicit HUMAN adversarial assessment; Stage 16 autonomous adversarial engine is not implemented |
| V10 pre-render gate | complete PASS on all pre-render checks and no ERROR/BLOCKER/CRITICAL | eligibility for later approval only |

INFO and WARNING findings are retained without blocking. ERROR, BLOCKER and CRITICAL block.
UNKNOWN, NOT_RUN and FAIL block. Missing procedural rules are UNKNOWN coverage, not vacuous PASS.
Unsupported business calendars and unresolved context fail closed through Stage 07 semantics.
Literal quotations additionally require matching UTF-8 bytes and fragment SHA-256 in a text/plain
source. The supported exact locators are RECORD `1` (whole source) and BYTE_RANGE `start:end`;
unknown locations and out-of-range spans block. A quoted non-text source is blocked as QUOTATION_EXTRACTION_UNSUPPORTED until a verified
extraction adapter provides that proof. Source jurisdiction/effective dates are checked separately
from rule applicability. Human PASS cannot override a fabricated quotation.
Calculated deadlines are compared with execution time; queries re-evaluate procedural conditions,
including deadlines that elapse later on the same day.

`procedural_context` accepts Stage 07 typed datums. FACT values must match exact CONFIRMED fact
content and current evidence/authority and belong to the Draft snapshot. CLAIM, HYPOTHESIS and
INTERPRETATION never become FACT. The exact context is included in the execution manifest.

## Review boundary and finding lifecycle

`ValidationReviewInput` binds an immutable Draft and Snapshot to a policy and one review task.
`ValidationReviewProposal` is an untrusted LANGUAGE_REVIEW or ADVERSARIAL_REVIEW proposal. It cannot
contain another task's assessment or domain writes and cannot be executed as a command. ABSTAIN
contains no purported completed assessment. No external model call is performed by Stage 10.

`RecordValidationReview` is a separate explicit HUMAN action. It records all seven semantic checks,
their rationales and issues against one exact Draft/hash/snapshot/policy/date. It is an auditable
assessment, not automatic truth, independent review, legal certification or document approval.
Review IDs are `uuid5(command_id, 'review')`; run IDs are `uuid5(command_id, 'validation-run')`.
Both are generated by the application, not provider-assigned canonical identities.

`RevokeValidationReview` appends a revocation, including after the Draft has moved to VALIDATED
or its input authority has drifted. Historical review bytes remain intact.
`ResolveValidationFinding` requires a live HUMAN FINDING_RESOLUTION Decision targeting the exact
OPEN finding. It appends RESOLVED or FALSE_POSITIVE. Neither resolution nor revocation rewrites a
historical run into PASS: a fresh command and review of the current Draft are required.

## Freshness, reproducibility and compatibility

`GetValidation` verifies run/execution/manifest/hash bindings, current output head, all dependency
heads, live plan/snapshot/review authority, current source bytes, policy, UTC evaluation date and
case sequence. Any intervening case mutation conservatively invalidates eligibility, including a
new rule or review. This intentionally sacrifices some reuse to prevent stale authorization.
The stored VALIDATED lifecycle revision is historical; it is never a substitute for live eligibility.

The manifest stores exact dependency hashes, Draft/snapshot hashes, review hash, procedural context,
evaluation date and a SHA-256 policy pin over normalized Python/SQL source bytes. Execution time,
command identity and actor are recorded through the canonical run/audit chain. Reproduction means
identical pinned inputs and clock/command conditions, not identical hashes across different runs.

Historical entity models, lifecycle tables, SQL, ValidationRun and release contracts are unchanged.
New contracts use new 1.0.0 identities. `stage10_actions` excludes legacy plan/release bypasses;
the legacy Core ValidateDraft remains disabled. Product hosts must provision scoped actions.

The canonical run explicitly contains `render=NOT_RUN` and empty render hashes. Historical
`evaluate_release` continues requiring render PASS plus exact rendered content and HUMAN approval.
Stage 10 exposes no approval, rendering, FINAL, certification, filing or transmission operation.
Stage 12 receives only the existing audit and Stage 10 execution evidence contract, not a new audit engine.

## Authority-source exception

The three requested operating documents listed in `37-stage10-readiness.md` are
`NOT PRESENT IN VERIFIED BASELINE`. The user explicitly authorized the verified baseline and
current task instructions as the execution basis. No missing document was reconstructed.
