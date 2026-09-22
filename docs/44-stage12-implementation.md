# Stage 12 — Audit / Provenance Implementation

Status: IMPLEMENTATION IN PROGRESS

## Architecture

Stage 12 is an additive read-only projection over the existing canonical Case Core ledger.

Authoritative write path:

Case command
-> Core transaction
-> immutable versioned revisions
-> immutable DomainEvent
-> lw_core.events
-> lw_core.outbox

Stage 12 read path:

authorized AuditRead
-> UnitOfWork.records()
-> UnitOfWork.events()
-> contract/hash/predecessor-chain validation
-> UnitOfWork.outbox()
-> exact revision/head/event/outbox binding
-> deterministic AuditPackage

No second writable audit table, history stream or mutable provenance registry is introduced.

## AuditPackage

AuditPackage 1.0.0 binds:

- tenant_id;
- case_id;
- exact case_sequence;
- deterministically ordered complete revision inventory as Ref + SHA-256 content hash;
- deterministic current heads, each required to exist in the revision inventory;
- complete validated DomainEvent sequence;
- SHA-256 digest of every event;
- exact outbox event IDs in canonical event order;
- chain head hash;
- Stage 12 implementation pin.

The Pydantic contract rejects:

- missing events;
- event/hash count mismatch;
- duplicate event IDs;
- outbox mismatch;
- wrong case scope;
- revision duplication or non-deterministic revision order;
- a head missing from the revision inventory;
- non-deterministic head order;
- case-sequence regression or a missing sequence;
- an event sequence beyond the package case_sequence;
- predecessor-chain mismatch;
- wrong chain head declaration;
- a final event sequence that does not equal package case_sequence.

Repeated events at the same case_sequence are valid because one command may emit a primary event and an additional dependency invalidation event.

verify_audit_package additionally recomputes every event digest from canonical structured content and rejects a forged declared event digest. Revision hashes are produced only after UnitOfWork.records() validates the authoritative stored revision contract and stored content hash.

## AuditService

AuditService:

- obtains identity only from TokenAuthority;
- requires AuditRead;
- rejects AI principals;
- runs inside the existing case-scoped repository transaction and RLS context;
- calls tx.records(), which validates stored revision contracts and hashes;
- calls tx.events(), which validates stored event contract, stored bytes hash and the complete predecessor chain;
- calls tx.outbox() and requires one-to-one equality with the event stream;
- performs no writes.

The transaction lock deliberately creates one coherent case snapshot for package construction.

## Provenance trace

trace(target) performs exact Ref resolution against the case revision set and recursively walks typed Ref and SourceAnchor values.

It verifies source availability through source_bytes(), then returns:

- exact target;
- package hash;
- deterministic revision closure;
- deterministic source anchors;
- audit event IDs whose subjects intersect that closure;
- COMPLETE only when source anchors exist and every traversed revision is represented by an audit event.

Missing revisions or unavailable original source bytes fail closed.

## Privacy

The package contains audit metadata, refs, hashes and event data already stored in the canonical event ledger. It does not copy original source-document bytes into AuditPackage.

## Cryptographic boundary

The predecessor chain and package digest are integrity mechanisms, not signatures.

A verifier can detect inconsistent or partially corrupted package content. The package pins complete revision hashes, but it deliberately does not embed the full revision payloads; authoritative revision-content verification remains a trusted repository read performed by AuditService. Authenticating an exported package to an external party would require a separately authorized signing/attestation mechanism and is outside Stage 12 v1.

## Implementation files

- lukart_work/audit/__init__.py
- lukart_work/audit/contracts.py
- lukart_work/audit/service.py
- tests/test_stage12.py
- docs/43-stage12-readiness.md
- docs/44-stage12-implementation.md
- docs/45-stage12-acceptance.md
