# Stage 06 — Document Registry implementation

## Boundary

`lukart_work.registry` is an application service over authoritative Core state. No new SQL table or
domain `Document` entity is introduced.

- `RegistryRequest:1.0.0` carries explicit write intent.
- `RegistryReceipt:1.0.0` is append-only, Filing-scoped and SHA-256 chained.
- `RegistryQuery:1.0.0` returns a read-only `RegistryProjection:1.0.0`.
- Existing Core authentication, capability authorization, case-sequence CAS, actor-bound replay,
  audit/outbox and transaction rollback remain authoritative.
- Receipts use existing `lw_core.objects` RLS/immutability under `filing_registry_receipt`.

## Artifact and Filing identity

Registration verifies the authoritative `SourceDocument` bytes/hash/length and freezes that identity
into every registry receipt. Multiple Filing IDs may legitimately reference identical artifact bytes.
Historical pre-Stage-06 Filings are not rewritten; projection surfaces them as `unregistered_filings`
and Stage 06 transitions refuse them.

## Submission / acknowledgement evidence

A receipt source alone is insufficient. `RecordSubmission` and `RecordAcknowledgement` require an
exact current `Evidence` revision that:

1. is `ACCEPTED` through Stage 05's human review lifecycle;
2. is not `authenticity=DISPUTED`;
3. points to exactly the supplied receipt SourceDocument id/hash;
4. is current, not stale;
5. uses bytes distinct from the filed artifact;
6. uses a receipt source/hash not previously consumed by another registry receipt in the CASE.

Acknowledgement additionally requires a prior submitted Filing and evidence bytes distinct from the
submission receipt. Exact command replay resolves before these uniqueness checks and remains safe.

`RecordSubmission` also requires an explicit timezone-aware `submitted_at` supplied by the HUMAN
operator from the accepted receipt evidence. The service never substitutes command time or
`SourceDocument.received_at` as the event time. The supplied event time must not be later than the
receipt source's trusted `received_at` or the command's `recorded_at`. `RegistryReceipt.event_at`
binds that event time to the exact accepted Evidence revision, while `recorded_at` remains the
separate system/audit timestamp. Projection verifies `Filing.submitted_at == RegistryReceipt.event_at`
and fails closed on drift. This is an evidence-bound human attestation, not independent proof of
judicial admissibility, objective truth or legal effectiveness.

## Lifecycle

The existing Filing transition allowlist is unchanged. Stage 06 exposes `RegisterFiling`,
`PrepareFiling`, `MarkFilingReady`, `RecordSubmission`, `RecordAcknowledgement`, `WithdrawFiling`.
No generic status setter exists.

## Projection and chain verification

Registry state is recomputed from current Filing heads plus immutable receipt history. The service
verifies receipt sequence, previous hash, Filing revision, constant artifact identity, exact historic
accepted Evidence revision and SourceDocument bytes. Forged/stale/tampered chains fail closed.
The projection is not writable and is not a second source of truth.

## Non-goals

No deadline engine, organ/channel selection, formal-requirements engine, filing-topology legal
analysis, drafting, rendering, external transmission, ROS runtime dependency, UI or deployment.
