# Stage 12 — Audit / Provenance Acceptance

Status: PENDING FINAL EXACT-SHA EVIDENCE

Stage 12 is not closed merely because code exists.

## Required acceptance criteria

1. AuditPackage is deterministic for unchanged authoritative case state.
2. AuditPackage binds exact tenant, case and case_sequence.
3. AuditPackage binds every authoritative versioned revision as deterministic Ref + SHA-256 content hash.
4. Every current head is present in that revision inventory and deterministically ordered.
5. AuditPackage binds deterministic immutable Core object metadata and command-receipt metadata without embedding their payloads.
6. Stored object/command payload-hash corruption fails closed.
7. The event stream continuously covers every case_sequence through the package case_sequence, while allowing multiple events at one sequence.
8. Every package event is read through the canonical Core event decoder.
9. Stored event contract/hash corruption fails closed.
10. Predecessor-chain corruption fails closed.
11. Declared event digests are recomputed and verified.
12. Event/outbox membership must match exactly.
13. AuditService performs no domain or audit writes.
14. AuditRead authorization is enforced at the service boundary.
15. AI principals cannot act as the audit-read trust boundary.
16. Cross-case/missing-ref access cannot leak another Case.
17. Provenance trace resolves the exact Ref closure.
18. Provenance trace verifies original source availability.
19. Trace identifies audit events for traversed revisions.
20. COMPLETE is not returned when provenance evidence is missing.
21. AuditPackage does not embed original source-document bytes.
22. Focused tests/test_stage12.py executes with no failures, errors or skips in the authoritative CI environment.
23. Full repository regression passes on the exact candidate SHA.
24. Generated/integrity/package checks required by repository CI pass on the exact candidate SHA.
25. Final diff contains no unrelated scope drift.
26. Red Team has no unresolved P0 or P1.
27. Independent exact-SHA review passes.
28. Main is changed only through an authorized guarded landing/merge path.
29. Post-merge exact-SHA validation passes.

## Current evidence state

Implementation and synthetic Stage 12 tests are present on codex/stage12-audit-provenance.

Fresh final candidate SHA: NOT YET ESTABLISHED.
Focused authoritative CI: NOT YET VERIFIED.
Full regression: NOT YET VERIFIED.
Independent review: NOT YET PERFORMED.
Merge: NOT PERFORMED.
Post-merge validation: NOT PERFORMED.
