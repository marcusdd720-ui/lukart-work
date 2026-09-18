# Stage 08 — Document Planner readiness and gap matrix

Baseline: `59392d2830fcead79ff3550cdd6b0c833ac6edcb`, exact live `main` after Stage 07 closure.

## Prerequisite gate

Stage 07 Procedural Intelligence Engine is CLOSED. PR #6 merged. Its final reviewed head
`9bd8542a2a80398a4fd185c7e682166c1f2e1795` passed GitHub Actions run 35321591891
with 195 full-regression tests, 76 Draft 2020-12 schemas, 77 package checks, 262 manifest entries
and reproducibility PASS. Post-merge compare from the reviewed head to merge commit
`59392d2830fcead79ff3550cdd6b0c833ac6edcb` contains no file changes.

Stage 08 does not reopen Stage 07 absent new evidence.

## Inventory

The canonical domain already contains:

- `DocumentPlan` with snapshot pin, objectives, recipient, position scope, argument order,
  evidence, section order and PLAN_APPROVAL;
- `Section` and `SectionContract`;
- closed lifecycle for Plan and Section;
- immutable accepted snapshots and HUMAN `SNAPSHOT_ACCEPTANCE`;
- HUMAN `PLAN_APPROVAL` state guard;
- PostgreSQL RLS, authorization, case-sequence CAS, actor-bound idempotency, audit/outbox and rollback;
- dependency invalidation used by historical plan/draft paths.

No second CASE source of truth is needed.

## Gap matrix

| ID | Stage 08 requirement | Initial state | Minimal control |
|---|---|---|---|
| S08-01 | deterministic DocumentPlan construction | domain model only | Planner application boundary |
| S08-02 | plan only from frozen accepted inputs | partial Core checks | exact accepted snapshot + hash + current acceptance |
| S08-03 | sections created after snapshot | historical guard required Section in snapshot | treat Section as derived artifact; require every declared semantic ref in snapshot |
| S08-04 | no new facts/law/claims during planning | no dedicated boundary | section contracts fail closed on NEW_FACT/NEW_LEGAL_RULE/UNSUPPORTED_ASSERTION/UNMARKED_INFERENCE |
| S08-05 | objective / recipient / filing consistency | graph checks partial | exact Filing and Request ownership validation |
| S08-06 | plan review / approval | generic Core operations exist | dedicated HUMAN planner transitions + live PLAN_APPROVAL |
| S08-07 | revoked snapshot/plan approvals | historical revisions remain immutable | revalidate live Decision heads at use/read time |
| S08-08 | deterministic section order and provenance | model exists | deterministic UUIDs/order + exact refs |
| S08-09 | CAS/idempotency/RLS/audit/outbox | Core present | reuse CommandService transaction |
| S08-10 | drafting boundary | must remain excluded | no Draft/Statement/render generation |
| S08-11 | schema/integrity/regression evidence | prior-stage mechanism | Stage 08 schemas, runner, manifest and CI |

## Minimal architecture

`lukart_work.planner` is an application layer over the canonical Case Core.

`PlanDocument` consumes an exact accepted snapshot and explicit existing refs. In one transaction it
creates derived `Section` revisions and one canonical `DocumentPlan`. It does not create or mutate
Fact, Evidence, Claim, Argument, Request, LegalRule, Draft or rendered document content.

Sections are derived planning artifacts and therefore are created after the input snapshot. They are
not required to be snapshot members. Every semantic ref declared by a Section — arguments,
allowed/required inputs and allowed claims — must be an exact member of the frozen snapshot.

## Evidence ceiling

Planning can select and order existing canonical material; it cannot establish truth.

- a Fact status is not upgraded by inclusion in a plan;
- Evidence is not made admissible by inclusion;
- Request/Claim/Argument meaning is not rewritten;
- no legal rule is invented;
- no text draft is generated;
- revoked/superseded human authority fails closed.

## Explicit non-goals

No Stage 09 Controlled Drafting, no Statement generation, no LLM drafting, no render,
no external filing/transmission, no ROS runtime integration, no deployment.
All Stage 08 fixtures are synthetic.
