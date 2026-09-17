# Stage 06 — Document Registry readiness and requirement matrix

Baseline: `b8bbe1be40690170c5bb2f400ca774e71952a352` (Stage 05 merged and post-merge CI GREEN).
Synthetic CASE-TESTY only. No real CASE data, external filing, legal/procedural analysis, drafting,
rendering, deployment or ROS runtime integration is in scope.

## Architecture decision

Stage 06 reuses existing `Filing`, `Evidence`, `SourceDocument`, Core transaction/CAS/audit/outbox
and PostgreSQL RLS boundaries. It does **not** add a `Document` entity or a second writable registry.
The new boundary is `DocumentRegistryService` plus typed request/receipt/query contracts. Append-only
registry receipts live in existing case-scoped `lw_core.objects`. Current registry state is a
deterministic projection of authoritative Filing revisions, accepted Evidence revisions, immutable
sources and receipt history.

Content identity, Filing identity and receipt/event identity remain separate. Identical bytes may
back multiple legitimate Filings. Receipt evidence is different: a submission/acknowledgement
receipt must be an exact current human-reviewed `ACCEPTED Evidence` revision tied to that receipt
source, and its source/hash may not already have been consumed as registry receipt evidence.

## Requirement matrix

| ID | Requirement | Initial state | Stage 06 control |
|---|---|---|---|
| S06-01 | Canonical Filing lifecycle | PRESENT | preserve existing closed transition allowlist |
| S06-02 | Immutable artifact/source binding | PARTIAL | registration receipt + source byte/hash verification |
| S06-03 | Registration identity/history | MISSING | append-only `RegistryReceipt` hash chain |
| S06-04 | SUBMITTED requires evidence, not claim | MISSING | exact current human-reviewed ACCEPTED Evidence + distinct receipt source |
| S06-05 | ACKNOWLEDGED requires independent evidence | MISSING | distinct accepted Evidence/source/hash not consumed before |
| S06-06 | Tenant/case/authority isolation | PRESENT/PARTIAL | reuse Core auth/RLS; HUMAN-only writes |
| S06-07 | CAS/idempotency/replay/rollback | PRESENT | reuse outer `CommandService.execute` transaction |
| S06-08 | Deterministic current-state projection | MISSING | read-only `RegistryProjection` |
| S06-09 | Backward compatibility | PRESENT | historical Filings unchanged, surfaced as unregistered |
| S06-10 | Same artifact bytes != same Filing | MISSING test | explicit duplicate-content/multiple-Filing test |
| S06-11 | Machine-readable evidence | PARTIAL | Stage 06 status + schema-validation reports |
| S06-12 | Global integrity | PRESENT | strict complete manifest/hash checker |

## Threat / failure model

Fail closed on missing/tampered/tombstoned source bytes; stale Filing or Evidence revisions; Evidence
not ACCEPTED or authenticity DISPUTED; illegal lifecycle transitions; receipt-source/artifact hash
aliasing; receipt reuse across a CASE/Filing; cross-tenant/case references; actor/capability spoof;
idempotency conflicts; stale CAS; partial rollback; forged receipt chains and manifest drift.

Registration proves only that an artifact was registered. Human Evidence acceptance does not prove
judicial admissibility or objective truth. Receipt evidence supports the recorded lifecycle event;
it does not establish legal effectiveness. `SUBMITTED != ACKNOWLEDGED != EFFECTIVE`.
