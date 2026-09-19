# Stage 09 — Controlled Drafting implementation

## Architecture

`lukart_work.drafting.ControlledDraftingService` is an application boundary over the canonical Case Core. It consumes an exact `GenerateDocument` command, an accepted immutable Snapshot and an APPROVED DocumentPlan. It calls a trusted ModelProvider only after authorization, CAS and live-authority validation.

Each READY Section becomes one deterministic `DraftingInvocation` containing `AIRequest(task=DRAFTING)`, exact snapshot identity/hash, explicit allowed input refs and the SectionContract.

Provider output is parsed as `AIResult`. The application rejects domain proposals, extra authority/status fields, unsupported assertions, STRUCTURAL factual hiding, unmarked inference, out-of-contract refs and incomplete plan objectives/arguments.

## Two-gate execution

Before the provider call, Stage 09 checks tenant/case authorization, HUMAN actor, exact case sequence, current APPROVED plan, live HUMAN PLAN_APPROVAL, current accepted snapshot, exact source bytes and READY section heads.

After proposal generation, a new transaction repeats replay/CAS/live-authority/snapshot/plan/section validation. Any intervening case mutation, plan/snapshot/approval drift or invocation drift fails as STALE/CONFLICT and no Draft is committed.

Sequential replay checks the idempotency record before any provider call. A PostgreSQL session advisory lock keyed by tenant/case/idempotency key serializes identical external-call commands across independent service/authority instances without holding the Case transaction open during the provider call. The terminal ABSTAIN outcome is persisted in the existing command/audit/outbox path so its exact replay also performs no second provider call.

## SectionContract enforcement

- `allowed_inputs`: every Statement ref/citation must stay inside the contract;
- `required_inputs`: every required ref must actually be used;
- `allowed_claims`: Claim refs outside the explicit claim allow-list fail;
- `UNSUPPORTED_ASSERTION`: unsupported output fails;
- `UNMARKED_INFERENCE`: INFERENCE must use INFERRED support, explicit refs and an inference label;
- `NEW_FACT` / `NEW_LEGAL_RULE`: model domain proposals are rejected and model STRUCTURAL statements are not accepted;
- `REQUESTS`: at least one REQUEST statement is required;
- `CITATIONS`: at least one citation must be present;
- `ATTACHMENTS`: at least one Evidence ref must be used;
- `CHRONOLOGICAL`: referenced Facts must expose event_date and appear in nondecreasing order.

Every legal Statement must reference at least one current ACTIVE LegalRule whose exact activation still has a live HUMAN INTERPRETATION approval. Each used LegalRule must be covered by a current VERIFIED Citation whose current VERIFIED LegalSource is one of that rule's sources. These authority checks run before the provider call and again before commit.

## Persistence

The service writes canonical Draft revisions only through the existing PostgreSQL repository. The resulting head is `GENERATED`; there is no FINAL state in Stage 09. The internal PLANNED→GENERATED lifecycle remains append-only history.

Accepted provider JSON is canonicalized, stored in `DraftingTrace.raw_outputs`, and hashed into the Draft ReproductionManifest. The trace is audit evidence, not an authority source.

Statement UUIDs are assigned deterministically by the application from the command id and statement position. Provider-supplied UUIDs are never persisted as canonical Statement IDs.

Draft, trace, dependency edges, audit event, outbox and idempotency result commit atomically. A failure rolls the transaction back.

## Explicit non-goals

No rendering, document release/finalization, certification, external filing/transmission, ROS runtime integration or Stage 10+ behavior is added.
