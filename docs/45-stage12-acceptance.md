# Stage 12 — Audit / Provenance Acceptance

Status: PENDING FINAL EXACT-SHA EVIDENCE

Stage 12 is not closed merely because code exists.

## Required acceptance criteria

1. AuditPackage is deterministic for unchanged authoritative case state.
2. AuditPackage binds exact tenant, case, case_sequence and current heads.
3. Every package event is read through the canonical Core event decoder.
4. Stored event contract/hash corruption fails closed.
5. Predecessor-chain corruption fails closed.
6. Declared event digests are recomputed and verified.
7. Event/outbox membership must match exactly.
8. AuditService performs no domain or audit writes.
9. AuditRead authorization is enforced at the service boundary.
10. AI principals cannot act as the audit-read trust boundary.
11. Cross-case/missing-ref access cannot leak another Case.
12. Provenance trace resolves the exact Ref closure.
13. Provenance trace verifies original source availability.
14. Trace identifies audit events for traversed revisions.
15. COMPLETE is not returned when provenance evidence is missing.
16. AuditPackage does not embed original source-document bytes.
17. Focused tests/test_stage12.py executes with no failures, errors or skips in the authoritative CI environment.
18. Full repository regression passes on the exact candidate SHA.
19. Generated/integrity/package checks required by repository CI pass on the exact candidate SHA.
20. Final diff contains no unrelated scope drift.
21. Red Team has no unresolved P0 or P1.
22. Independent exact-SHA review passes.
23. Main is changed only through an authorized guarded landing/merge path.
24. Post-merge exact-SHA validation passes.

## Current evidence state

Implementation and initial synthetic tests are present on codex/stage12-audit-provenance.

Fresh final candidate SHA: NOT YET ESTABLISHED.
Focused authoritative CI: NOT YET VERIFIED.
Full regression: NOT YET VERIFIED.
Independent review: NOT YET PERFORMED.
Merge: NOT PERFORMED.
Post-merge validation: NOT PERFORMED.
