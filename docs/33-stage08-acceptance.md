# Stage 08 — Document Planner acceptance

Status: PRE-REVIEW ACCEPTANCE — functional assurance passed; generated-evidence freeze pending.

Baseline: `59392d2830fcead79ff3550cdd6b0c833ac6edcb` (Stage 07 CLOSED main).

Candidate evidence run:
- head: `e7c9ff1a42c79b4d18b285bc464848607cda308a`
- GitHub Actions run: `35323408131`
- Focused Stage 08: PASS.
- Full regression: 244 tests PASS, 0 failures/errors/skips.
- Independent Draft 2020-12 JSON Schema validation: 79 schemas PASS.
- Package verification: 80 checks / 79 JSON files PASS.
- Global integrity: 280 manifest entries PASS.
- Whitespace: PASS.
- Generated evidence reproducibility: FAIL only because newly generated Stage 08 schemas/reports/manifest were not yet committed.

The reproducibility failure is a materialization gate, not a waiver. Stage 08 is not CLOSED and this
document does not authorize merge. Generated artifacts must be committed, reproducibility rerun on
the resulting exact SHA, and the final exact SHA must receive an independent review pass.

## Accepted implementation properties

- `PlanDocument` consumes an exact currently accepted immutable snapshot.
- Sections are derived after snapshot freeze; every semantic Section ref remains pinned to the input snapshot.
- planning does not promote Facts/Evidence or create Claims, Arguments, Requests, LegalRules, Drafts or Statements.
- safe Section contracts fail closed on unsupported assertion, unmarked inference, new fact and new legal rule.
- PLAN_APPROVAL and SNAPSHOT_ACCEPTANCE are revalidated as live HUMAN authority.
- historical APPROVED plans do not report effective approval after supersession.
- Stage 08 product authorization excludes the legacy generic Core planning operations while retaining
  their contract members for backwards compatibility.
- writes reuse PostgreSQL RLS, CAS, actor-bound idempotency, append-only history, audit/outbox and rollback.
- Stage 09 drafting, rendering, external filing, ROS runtime and deployment remain outside Stage 08.

## Repair evidence before candidate run

CI and Red Team found and repaired:
1. inherited Stage 02 tests were initially executed under a Stage 08 restricted principal; the restricted
   profile is now tested separately so historical regression semantics remain unchanged;
2. plan creation initially emitted a non-canonical `DocumentPlanCreated` event, which the closed audit
   contract correctly rejected; Stage 08 now records canonical `RevisionAppended`;
3. the post-snapshot adversarial fixture initially attempted to create an invalid unsupported Fact; it now
   uses a valid post-snapshot Request and verifies both snapshot rejection and no Fact promotion;
4. effective plan approval now requires a current plan head and live snapshot acceptance;
5. a product authorization profile prevents bypass through legacy generic Core planning operations.

## Remaining gates

1. materialize exact generated Stage 08 schemas/reports;
2. refresh and commit the final global manifest;
3. exact-head CI with reproducibility PASS;
4. independent exact-SHA review;
5. repair loop if any finding;
6. merge;
7. post-merge exact-main verification;
8. closure receipt.
