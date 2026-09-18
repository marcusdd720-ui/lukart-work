# Stage 07 — Procedural Intelligence Engine implementation

## Boundary

The implementation adds `lukart_work.procedural` only. It does not alter Stage 06 registry code,
Core SQL schema, historical domain lifecycle contracts, DocumentPlan, Draft, renderer or external
filing paths.

Published Stage 07 contracts:

- `ProceduralRequest:1.0.0` — explicit HUMAN write intent for procedural sources/rules;
- `ProceduralRuleBinding:1.0.0` — immutable exact-rule-revision execution binding;
- `ProceduralQuery:1.0.0` — read-only `AssessProcedure`;
- `ProceduralFinding:1.0.0` — deterministic result with applicability/outcome/severity/provenance;
- `ProceduralAssessment:1.0.0` — sorted case-scoped projection.

## Canonical state and no second SSOT

Legal source and rule lifecycle is stored only as existing `LegalSource` and `LegalRule` revisions.
The binding object is auxiliary execution metadata for an exact LegalRule revision. It cannot have an
independent lifecycle or change its spec/sources across LegalRule lifecycle revisions. Reads verify
the entire binding chain against the canonical revision ledger before evaluating any rule.

Writes use the existing `CommandService.execute` transaction, therefore they inherit authenticated
capability checks, HUMAN-only Stage 07 mutation, actor-bound idempotency, expected-case-sequence CAS,
case advisory locking, rollback, immutable audit events and outbox. Objects use existing FORCE RLS.

## Source and rule lifecycle

`RegisterProceduralSource` binds immutable SourceDocument bytes/hash into a canonical
`LegalSource`. `VerifyProceduralSource` is an explicit lifecycle transition and rechecks source
bytes.

`RegisterProceduralRule` accepts only exact current VERIFIED LegalSource refs and produces a
canonical PROPOSED PROCEDURAL LegalRule plus its exact execution binding atomically.
`ReviewProceduralRule` moves to REVIEWED without changing executable content.
`ActivateProceduralRule` requires a live RECORDED HUMAN Decision of type `INTERPRETATION`,
outcome ACCEPT, targeting the exact reviewed revision. Existing Core state validation provides the
same approval-content immutability rule used elsewhere. Supersede/withdraw remain explicit lifecycle
operations.

## Procedural context and Fact boundary

Built-in context derives only from current canonical Case/Proceeding/Filing/Institution revisions.

Additional `ProceduralDatum` values are explicitly classified:
`FACT | CLAIM | HYPOTHESIS | INTERPRETATION | UNKNOWN | UNRESOLVED`.

Only FACT can satisfy a condition. A FACT datum requires one or more exact current Fact refs, and each
referenced Fact must be CONFIRMED, SOURCE_BACKED, have a live human FACT_ACCEPTANCE decision, current
ACCEPTED non-disputed Evidence and available original source bytes. Its canonical statement must equal
the datum key/value. The engine never promotes or writes a Fact.

CLAIM/HYPOTHESIS/INTERPRETATION → ABSTAIN when required.
UNKNOWN → UNKNOWN.
UNRESOLVED → UNRESOLVED.

## Applicability and findings

Rule applicability checks, in deterministic order:

1. LegalRule effective period;
2. Case jurisdiction;
3. optional exact document-type pins;
4. rule interpretation state;
5. explicit `applies_when` conditions.

The engine supports `PRESENT`, `EQUALS`, `ONE_OF`, `MIN_INTEGER`, `MIN_ITEMS` and
`CONTAINS_ALL`. Findings carry exact LegalRule ref, exact LegalSource refs, binding hash and supporting
Fact refs. Results are sorted deterministically.

Categories cover:
ORGAN, JURISDICTION, VENUE, STANDING_AUTHORITY, FILING_TOPOLOGY, CHANNEL,
FORMAL_REQUIREMENT, SIGNATURE, COPIES, ATTACHMENTS and DEADLINE.

## Deadlines

Stage 07 calculates only an explicit calendar-day offset from an evidence-bound FACT trigger. The rule
pins timezone and due clock; the result is `CALCULATED`, not VERIFIED and does not create/update a
canonical Deadline entity. A missing/unverified trigger remains UNKNOWN/UNRESOLVED/ABSTAIN.

`BUSINESS_DAYS` is modeled but deliberately returns ABSTAIN because Stage 07 has no authoritative
business-calendar provider. This prevents memory/default calendar assumptions from becoming a legal
deadline.

## Assurance

The golden synthetic case exercises all eleven procedural categories. Adversarial tests cover
claim-to-fact isolation, exact Fact binding, applicability uncertainty, interpretation uncertainty,
deadline abstention, verified-source and decision gates, replay/idempotency, concurrent CAS, RLS,
object immutability, forged bindings, transaction rollback, actor/scope authorization and deterministic
replay.

Stage 07 adds no real CASE data and no actual legal rule content.
