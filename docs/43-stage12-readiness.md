# Stage 12 — Audit / Provenance Readiness

Status: IMPLEMENTATION IN PROGRESS

Baseline SHA: 774f094ad03b9504a9a6ea82355e4a5abf40bf50

## Decision need

Stage 12 must make material Case operations reconstructable and provenance-queryable without creating a second writable history store.

## Existing authoritative capabilities

The existing Case Core already provides:

- immutable DomainEvent records in lw_core.events;
- an append-oriented predecessor hash chain;
- event IDs bound to tenant, case and case sequence;
- actor, operation, command, correlation, input hash and output hash;
- source-version and rule-version pins;
- atomic event + outbox persistence in the Core transaction;
- immutable versioned revisions and deterministic current heads;
- RLS isolation beneath application authorization;
- GetProvenance traversal from an exact Ref to referenced revisions and SourceAnchor values.

These capabilities remain authoritative. Stage 12 must extend them, not replace them.

## Gaps to close

1. No dedicated Audit / Provenance module exists.
2. No authorized read-only audit package API exists.
3. No deterministic package binds case sequence, complete revision hashes, immutable object metadata, command receipts, current heads, the full verified event chain and outbox membership.
4. No standalone package integrity verifier exists.
5. No Stage 12 trace binds provenance traversal to the audit events that recorded the relevant revisions.
6. No dedicated Stage 12 adversarial/integration regression exists.
7. No Stage 12 acceptance evidence exists.

## Trust boundaries

- lw_core.events remains the only writable audit ledger.
- Canonical versioned revisions remain in Case Core; Stage 12 only pins their exact Ref + content hash.
- Immutable Core objects and command receipts remain in their canonical tables; Stage 12 pins only identifiers, contracts and hashes, never original object payloads or source bytes.
- AuditService is read-only and cannot create, update or delete domain/audit state.
- AuditRead is an explicit capability.
- AI principals are not accepted as the audit-read trust boundary.
- Missing event/outbox/revision/provenance evidence fails closed.
- The event stream must continuously cover every case_sequence from 1 through the package case_sequence; multiple events at one sequence remain allowed.
- Every current head must be present in the deterministically ordered revision inventory.
- The audit package contains hashes and structured audit metadata, not original source bytes.
- Package hashing and the predecessor chain provide integrity evidence. They are not a digital signature and do not independently authenticate an exported package outside the trusted service boundary.

## Target acceptance

Stage 12 can close only after:

- deterministic package generation;
- complete revision Ref/hash inventory and head binding;
- deterministic immutable object metadata and command-receipt inventories;
- continuous case-sequence coverage;
- full event-hash verification;
- exact event/outbox correspondence;
- provenance trace to immutable sources;
- authorization and case isolation;
- corruption/tamper rejection;
- no raw source-byte leakage in the package;
- focused Stage 12 tests;
- full repository regression;
- package/schema/integrity checks where applicable;
- Red Team with no unresolved P0/P1;
- fresh exact-SHA CI;
- independent exact-SHA review;
- guarded merge/landing and post-merge verification.
