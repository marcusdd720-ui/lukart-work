# Stage 10 — Validation Engine readiness and acceptance contract

Base: verified live main `0d31a47f6481e9eb252b188253ac1ed33effa50c`.
Mode: synthetic CASE-TESTY only. No real CASE data or private evidence.

## Authority and closed stages

Architecture: `docs/00-baseline.md`, especially sections 14–17, 28, 42–48 and 50.
Stage 10 follows GENERATED drafting and precedes Stage 11 rendering.
Earlier stages remain closed; historical pre-review reports are not closure verdicts.

| Stage | Repository evidence |
|---|---|
| 04 | docs/22-stage04-closure.md and merged PR #2 |
| 05 | merged PR #3; docs/26-stage06-readiness.md records Stage 05 merged and post-merge CI GREEN at b8bbe1be40690170c5bb2f400ca774e71952a352 |
| 06 | PR #5 post-merge closure receipt, main 768121f5d8e4d25dc22dda4bed69b2149918d8e3 |
| 07 | PR #6 closure comment 5727034385, main 59392d2830fcead79ff3550cdd6b0c833ac6edcb |
| 08 | PR #7 closure comment 5727605506, main 34771ae9a54e9aad163ba84b22b09be412c8ebc3 |
| 09 | PR #8 closure comment 5737922976; post-merge CI 35409909110, job 105807282620, SUCCESS on the verified base |

Read Stage 09 readiness, implementation and acceptance documents against that exact base.

The following requested documents are **NOT PRESENT IN VERIFIED BASELINE**:

- docs/WORKING_PRINCIPLES.md
- docs/PRIVATE_CASE_OPERATING_STANDARD.md
- docs/CASE_INTAKE_RESPONSE_PROTOCOL_V1.md

The user explicitly authorized continuation using verified live main, the existing baseline and
the current Stage 10 instructions. These documents will not be reconstructed or represented as
verified. Any requirement actually dependent on their unknown contents must be marked
`BLOCKED — MISSING CANONICAL SOURCE`. Their absence alone is not a blocker.

## Existing implementation and gaps

Core provides strict schema parsing, immutable entity revisions, ValidationFinding lifecycle,
ValidationRun, PostgreSQL RLS, transaction-wide case CAS, actor-bound replay, dependency DAG,
audit/outbox and exact snapshot acceptance. The historical Core ValidateDraft entry point is
disabled. Pure evaluate_release requires all checks including render and must remain unchanged.
Stage 09 provides current plan/snapshot/fact/legal authority and citation coverage guards.

Stage 10 must supply an authenticated application boundary, actual layered validation runs,
auditable findings and a pre-render projection. It must never equate GENERATED with VALIDATED,
VALIDATED with APPROVED, or pre-render eligibility with FINAL.

## Acceptance criteria

| ID | Required guarantee and evidence |
|---|---|
| S10-01 | Strict request/schema validation; exact Draft/hash/snapshot/policy binding; reject arbitrary client PASS/status injection |
| S10-02 | Fact authority, evidence support/source bytes, citation/legal applicability, plan/section/objective and contradiction checks; structured checks distinguish proof from semantic review |
| S10-03 | Procedural validation respects Stage 07 rules and unknown/abstention; no invented substantive legal conclusions |
| S10-04 | Language and adversarial input/output contracts are proposal-only; missing review cannot silently PASS; no Stage 16 autonomous adversarial engine |
| S10-05 | INFO/WARNING/ERROR/BLOCKER/CRITICAL; ERROR/BLOCKER/CRITICAL and incomplete checks deny validation; no rendering or FINAL |
| S10-06 | Deterministic finding identity/order, immutable run/target/hash, HUMAN finding resolution, revalidation rather than retroactive PASS |
| S10-07 | Live authority and dependency drift invalidate effective validation; historical successful run remains historical evidence |
| S10-08 | Auth/RLS, exact case CAS, actor-bound idempotency, replay across service instances, atomic rollback and concurrent writers |
| S10-09 | Runs/findings/dependencies/audit/outbox commit atomically; no second writable CASE state |
| S10-10 | Historical schemas, lifecycle and disabled legacy product bypass remain compatible; additive versioned contracts |
| S10-11 | Focused/adversarial tests, full PostgreSQL regression, independent schema validation, package and complete manifest checks |
| S10-12 | Reproducible generated evidence and exact-head GitHub CI; freeze one green SHA for independent review, never self-award independent review or merge |

Stage 11 rendering and Stage 12 certification/provenance expansion are excluded. Stage 10 may
persist only the validation execution/dependency/audit contracts required for its own assurance.

Status: implementation present; exact-head assurance and freeze are tracked in acceptance and Draft PR #9.
