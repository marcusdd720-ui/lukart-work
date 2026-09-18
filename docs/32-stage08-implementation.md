# Stage 08 — Document Planner implementation

## Boundary

Stage 08 adds `lukart_work.planner` as a deterministic application boundary over the existing canonical
`DocumentPlan` and `Section` entities. It does not implement drafting, Statement generation,
rendering, external filing, ROS runtime or deployment.

Published Stage 08 contracts:

- `PlannerRequest:1.0.0` — explicit HUMAN planning intent;
- `PlannerQuery:1.0.0` — read-only exact plan projection;
- `DocumentPlanProjection:1.0.0` — canonical plan + derived sections + effective approval state.

## Accepted-snapshot rule

`PlanDocument` requires an exact immutable snapshot and its hash. The snapshot must have a current
RECORDED HUMAN `SNAPSHOT_ACCEPTANCE` decision. The planner revalidates the decision at execution time,
rechecks snapshot heads and verifies source bytes.

The snapshot contains the canonical CASE inputs. Planning artifacts are derived after freeze:

- `Section` is not required to be a snapshot member;
- Filing, recipient, objectives, arguments, evidence and every semantic ref declared by a Section must
  be exact members of the snapshot;
- a post-snapshot ref cannot be injected into a Section contract.

This removes the historical snapshot/Section cycle without weakening the frozen-input boundary.

## Planning operation

In one existing Core transaction `PlanDocument`:

1. verifies the accepted snapshot;
2. resolves and validates the exact Filing and recipient;
3. verifies Request ownership and non-withdrawn state;
4. rejects withdrawn Arguments and excluded Evidence;
5. validates every Section blueprint against the snapshot;
6. creates deterministic Section IDs from the command ID and section index;
7. stores each Section as PLANNED then READY;
8. creates one canonical DocumentPlan in PROPOSED state;
9. records dependency edges from exact snapshot members and snapshot acceptance to the plan;
10. commits through existing CAS/idempotency/audit/outbox machinery.

No Fact, Evidence, Claim, Argument, Request or LegalRule is promoted or rewritten by this operation.

## Safe Section contracts

Stage 08 requires every Section blueprint to explicitly forbid:

- `UNSUPPORTED_ASSERTION`;
- `UNMARKED_INFERENCE`;
- `NEW_FACT`;
- `NEW_LEGAL_RULE`.

`required_inputs ⊆ allowed_inputs` and `allowed_claims ⊆ allowed_inputs`. Section arguments must be
inside the plan's explicit argument order.

These are planning constraints for Stage 09; they are not generated prose.

## Review and approval

`ReviewDocumentPlan` advances PROPOSED → REVIEWED.

`ApproveDocumentPlan` requires a current RECORDED HUMAN `PLAN_APPROVAL` ACCEPT Decision targeting
the exact REVIEWED plan revision. Existing state validation freezes approved content.

The read projection reports `approval_current=true` only when both:

- the PLAN_APPROVAL is still current; and
- the underlying SNAPSHOT_ACCEPTANCE is still current.

Revocation or supersession therefore invalidates effective approval without rewriting historical
DocumentPlan revisions.

`SupersedeDocumentPlan` preserves immutable approved content and uses the existing SUPERSEDED state.

## Persistence and concurrency

Stage 08 introduces no new SQL schema. All mutations reuse `CommandService.execute` and inherit:

- authenticated case-scoped authorization;
- FORCE RLS;
- advisory transaction locking;
- expected-case-sequence CAS;
- actor-bound idempotency;
- append-only revisions;
- atomic audit events and outbox;
- rollback on any failure.

## Drafting boundary

Stage 08 creates no `Draft` and no `Statement`.

The existing Draft guard is adjusted only so that derived Section entities themselves do not need to
be members of the pre-planning snapshot. It still requires all Section-declared semantic refs and all
actually used draft refs to be members of that frozen snapshot.

Controlled prose generation remains Stage 09.
