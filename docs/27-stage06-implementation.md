# Stage 06 — Document Registry implementation

## Boundaries

`lukart_work.registry` is an application service over existing authoritative Core state.
No new SQL table or domain `Document` entity is introduced.

- `RegistryRequest:1.0.0` is the only Stage 06 write-intent contract.
- `RegistryReceipt:1.0.0` is append-only, case/filing scoped and chained by SHA-256.
- `RegistryQuery:1.0.0` produces `RegistryProjection:1.0.0`.
- Core remains responsible for authentication, capability authorization, case sequence CAS,
  actor-bound idempotency replay, audit event chaining, outbox and transactional rollback.
- PostgreSQL `lw_core.objects` stores receipts under `filing_registry_receipt`; existing RLS and
  case scope apply.

## Content, Filing and receipt identity

Registration verifies authoritative source bytes and records source id, digest and byte length.
That identity is copied unchanged to every later receipt. The service permits multiple Filing ids
to point at the same source bytes, but rejects mutation/tamper of the registered source.

Historical pre-Stage-06 Filings are not rewritten. The projection returns them explicitly as
`unregistered_filings`; they cannot use Stage 06 state-changing operations until a Stage 06
registration history exists.

## Lifecycle

Existing domain transitions are preserved without modification. Stage 06 exposes:
`RegisterFiling`, `PrepareFiling`, `MarkFilingReady`, `RecordSubmission`,
`RecordAcknowledgement`, and `WithdrawFiling`.

Submission requires a verified receipt source distinct from the Filing artifact. Acknowledgement
requires an already-submitted Filing and a separate verified source distinct from both the Filing
artifact and submission receipt. These records are evidentiary chain-of-custody artifacts only;
the service does not infer legal effectiveness.

## Projection

The registry query is read-only. It recomputes current state from Filing heads and validated
receipt chains, verifies referenced source bytes, and refuses stale/tampered chains. It is not a
write authority or second SSOT.

## Non-goals

No court/channel selection, deadline computation, formal-requirements engine, filing-topology legal
analysis, drafting, rendering, external submission, ROS runtime dependency, UI or deployment.
