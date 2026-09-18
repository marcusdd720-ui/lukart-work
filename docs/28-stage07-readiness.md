# Stage 07 — Procedural Intelligence Engine readiness and gap matrix

Baseline: `768121f5d8e4d25dc22dda4bed69b2149918d8e3`, exact live `main` at Stage 07 start.

## Prerequisite gate

Stage 06 Document Registry is treated as CLOSED and is not reopened. The baseline is merge commit of
PR #5 (`e1d217f0b083b916df61337452a7a5ed650aa105` → `main`), and exact Stage 06 head CI run
35315880141 completed with conclusion SUCCESS. The Stage 06 machine report records 184 tests,
0 failures/errors/skips and PASS. Its `stage_06_closed=false` field is the runner's pre-merge
closure guard, consistent with earlier stage semantics; it is not used to overwrite later merge/closure evidence.

The target repository does not contain `docs/WORKING_PRINCIPLES.md`,
`docs/PRIVATE_CASE_OPERATING_STANDARD.md` or `docs/CASE_INTAKE_RESPONSE_PROTOCOL_V1.md`.
Stage 07 therefore preserves the project-level governing constraints supplied for CASE-TESTY and the
existing repository contracts rather than inventing local replacements.

## Inventory

Reusable authoritative state already exists:

- canonical Case Core revisions: `Case`, `Party`, `Institution`, `Proceeding`, `Filing`,
  `Fact`, `Evidence`, `LegalSource`, `LegalRule`, `Deadline`, `Decision`;
- Stage 05 human Facts/Evidence lifecycle and exact provenance;
- Stage 06 Filing registry, without reopening or changing it;
- PostgreSQL case-scoped transaction, advisory lock, case-sequence CAS, actor-bound idempotency,
  immutable revisions/objects/commands/events, audit/outbox and FORCE RLS;
- active `LegalRule` already requires a recorded HUMAN `INTERPRETATION` acceptance decision.

No second writable CASE ledger is required.

## Gap matrix

| ID | Stage 07 requirement | Initial state | Minimal control |
|---|---|---|---|
| S07-01 | organ / jurisdiction / venue applicability | domain refs present, no engine | deterministic conditions over current Case/Proceeding/Institution/Filing |
| S07-02 | standing / authority | participants and representation present | explicit condition category, no inferred authority |
| S07-03 | filing topology / channel | Filing recipient exists, no rules engine | executable rule binding with evidence-bound context |
| S07-04 | formal requirements / signatures / copies / attachments | missing engine | typed deterministic conditions and severity |
| S07-05 | procedural deadline rules / triggers | Deadline entity exists, no calculation path | verified trigger FACT + explicit calendar-day rule; unsupported business calendar ABSTAIN |
| S07-06 | applicability / UNKNOWN / UNRESOLVED / ABSTAIN | partial domain vocabulary | explicit result states; fail closed on non-fact context |
| S07-07 | user statement must not become FACT | Stage 05 guard exists | ProceduralDatum FACT requires exact current CONFIRMED source-backed Fact refs |
| S07-08 | deterministic findings / severity | missing | sorted `ProceduralFinding` projection |
| S07-09 | full provenance | LegalRule/LegalSource refs exist | every finding binds exact rule, sources, rule-binding hash and supporting Fact refs |
| S07-10 | authorization / RLS / CAS / replay / rollback | present in Core | reuse `CommandService.execute` and `lw_core.objects` |
| S07-11 | no second SSOT | required | rule binding is immutable version-bound execution metadata, never independent case history |
| S07-12 | schema / manifest / regression evidence | prior-stage mechanism present | Stage 07 export, schema engine, full runner and global integrity gate |

## Minimal architecture

`lukart_work.procedural` is an application boundary over the canonical Core graph.

A procedural source is admitted as the existing `LegalSource`; a procedural rule is admitted as the
existing `LegalRule`. The canonical LegalRule stores the exact canonical JSON serialization of its
executable procedural spec in `requirement.operand` (`/procedural_spec`). An append-only
`ProceduralRuleBinding` is written atomically into existing case-scoped `lw_core.objects` for each
exact LegalRule revision and is only a validated execution projection of that canonical content. It
cannot be revised independently: the binding chain must be contiguous, source refs must equal the
LegalRule source refs, the serialized spec must equal the canonical LegalRule payload, and the
executable spec is immutable across lifecycle revisions. Canonical rule/source revisions remain the
authoritative legal/procedural records.

`AssessProcedure` is read-only. It evaluates current ACTIVE procedural LegalRules against current
canonical Filing/Proceeding/Institution/Case state plus explicitly classified procedural context.
It does not create Facts, Deadlines, Filings, Plans, Drafts or legal effects.

## Evidence ceiling and threat model

A context datum classified CLAIM, HYPOTHESIS or INTERPRETATION is never treated as FACT and yields
ABSTAIN when a rule needs it. UNKNOWN and UNRESOLVED remain explicit. A FACT datum must cite exact
current CONFIRMED source-backed Fact revisions, current ACCEPTED non-disputed Evidence and available
source bytes; the Fact statement must encode the same key/value pair.

Fail closed on stale refs, missing originals, unverified legal sources, forged/tampered binding chains,
wrong human decision type, cross-scope access, AI/service writes, idempotency conflicts, CAS races,
partial transaction failure and unsupported deadline calendars.

## Explicit non-goals

No Stage 08 Document Planner, Stage 09 drafting, document rendering, external filing/transmission,
ROS runtime integration, deployment, production legal knowledge ingestion or business-day calendar
provider. All Stage 07 fixtures and rule/source content are synthetic.
