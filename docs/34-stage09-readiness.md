# Stage 09 — Controlled Drafting readiness and gap matrix

Baseline: live `main` after Stage 08 closure. Stage 08 remains CLOSED absent new evidence.

## Scope

Stage 09 owns controlled prose generation only. It does not render, release, file, transmit, or execute Stage 10+ behavior.

Authority boundary:

1. exact accepted immutable Snapshot;
2. current HUMAN SNAPSHOT_ACCEPTANCE;
3. exact current APPROVED DocumentPlan;
4. current HUMAN PLAN_APPROVAL;
5. READY Sections and their SectionContracts;
6. HUMAN-authenticated GenerateDocument command with case-sequence CAS.

The model/provider is proposal-only. It cannot create or approve canonical domain facts, claims, evidence, legal rules, plans, decisions, statuses, or filings.

## Inventory

The existing Case Core already provides canonical Draft, SectionText, Statement and ReproductionManifest types, PostgreSQL transaction/RLS, append-only revisions, case-sequence CAS, actor-bound idempotency, audit/outbox, immutable snapshots and live Decision checks. Stage 08 provides deterministic DocumentPlan and SectionContract construction.

No SQL migration and no second writable source of truth are required.

## Gap matrix

| ID | Requirement | Initial WIP state | Stage 09 control |
|---|---|---|---|
| S09-01 | GenerateDocument application boundary | partial | ControlledDraftingService |
| S09-02 | exact AIRequest task=DRAFTING per Section | partial | deterministic DraftingInvocation |
| S09-03 | model is proposal-only | partial | reject AIProposal/domain-write attempts and provider status fields |
| S09-04 | no model-controlled UUID persistence | partial | application rewrites Statement UUIDs deterministically |
| S09-05 | accepted snapshot + approved plan authority | partial | pre-call and pre-commit revalidation |
| S09-06 | SectionContract enforcement | partial | allowed/required/claim refs plus forbidden semantics and typed requirements |
| S09-07 | citation/legal coverage | partial | ACTIVE LegalRule + VERIFIED Citation coverage per cited rule |
| S09-08 | inference boundary | partial | INFERRED label + explicit refs; unmarked inference rejected |
| S09-09 | objective/argument preservation | partial | every planned Request/Argument must remain represented |
| S09-10 | replay/concurrency | partial | replay gate before provider; second CAS/live-authority gate before commit |
| S09-11 | ABSTAIN | partial | return ABSTAIN without Draft persistence |
| S09-12 | raw output audit/reproduction | partial | exact canonical provider JSON stored in DraftingTrace and hashed |
| S09-13 | rollback/audit/outbox | Core present | same PostgreSQL transaction as Draft/trace/dependencies/event |
| S09-14 | rendering/release/filing boundary | historical APIs exist | Stage 09 service exposes GenerateDocument only |

## Evidence ceiling

Generated prose does not establish truth. A generated Statement remains text inside a Draft and does not mutate the lifecycle or epistemic status of any referenced Fact, Claim, Evidence, LegalRule, Request or Decision.

ABSTAIN remains ABSTAIN. Unsupported or unverifiable output fails closed.
