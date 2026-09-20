# Stage 10 — acceptance and freeze evidence

Status: FUNCTIONAL ASSURANCE COMPLETE; exact-head reproducibility freeze pending. This file does not award closure or independent review.
The durable exact-head continuation receipt is maintained in Draft PR #9.

Base: `0d31a47f6481e9eb252b188253ac1ed33effa50c`.
Branch: `codex/stage10-validation-engine`. Scope: synthetic CASE-TESTY only.

## Evidence to require before freeze

- all Stage 10 focused/adversarial integration tests on real PostgreSQL;
- full historical regression with zero failures/errors/skips;
- exported typed contracts checked by independent Draft 2020-12 JSON Schema engine;
- package/export equivalence and complete global integrity manifest;
- byte-reproducible generated evidence on the exact candidate GitHub head;
- authoritative CI run/job and artifact digest;
- explicit remaining findings and Stage 11/12 boundaries;
- a separate independent exact-SHA review after builder freeze, never performed by this builder.

## Builder Red Team and repair log

1. Missing review and empty procedural coverage must not be vacuous PASS. Both persist blockers.
2. Resolving a finding must not retroactively clear a failed run. Immutable run references and
   severity remain binding; fresh validation is mandatory.
3. A review of GENERATED content must remain revocable after the Draft becomes VALIDATED.
   Revocation now accepts the exact historical reviewed revision without requiring it to be head.
4. A manifest hash alone is insufficient for reconstruction. The complete typed manifest is stored
   with the execution and checked against the canonical run and immutable dependency hashes.
5. Original source bytes alone do not prove ingestion lineage. Validation also invokes Stage 05
   extraction/provenance availability checks.
6. Review-provider output must not cross task/authority boundaries. Task-specific proposal schemas
   and a non-command input/output boundary prevent direct PASS or domain persistence.
7. Procedural context must not turn CLAIM into FACT. Stage 07 evidence-bound checks are run inside
   the validation transaction and snapshot membership is enforced.
8. A deadline can elapse within one UTC day. Queries re-evaluate procedural predicates and deadlines,
   in addition to conservative case-sequence/date/authority invalidation.
9. VERIFIED citation metadata does not prove literal quotation bytes. Stage 10 checks the quotation
   and fragment hash against text/plain source bytes; unsupported quoted formats remain blocking.
10. Database failures in the read projection must preserve Core's safe-error boundary. Driver details
    are now mapped to UNKNOWN, with a focused fault-injection test.

Source candidate `9a41ac47c260d6aabf4c6a0fbe6c292be7e89704` passed 30 focused Stage 10 tests and
347 full regression tests (zero failures/errors/skips), 94 schemas and 95 package checks in
CI `35437512988`, job `105882583179`. Only generated-evidence materialization remained.
The subsequent safe-error repair requires a fresh full exact-head run and does not inherit that PASS.

## Final source assurance and evidence materialization

The repaired source candidate `3f835b646981650a54783af174fd665b9fe45f6a` passed:

- focused Stage 10: 31 tests;
- historical focused Stage 09: 66 tests;
- full regression: 348 tests, zero failures/errors/skips;
- independent Draft 2020-12 schema validation: 94 schemas;
- package/export verification: 95 checks / 94 JSON files;
- integrity and whitespace checks.

Evidence: push CI `35450531059`, job `105916778114`. Only the generated-evidence bootstrap gate
failed before materialization. Its `stage10-generated` artifact (ID `10585579025`, SHA-256
`1cf28489af2165be87f4c9c75982278161f6fc6aa084e228b116200add8d7844`) supplies the exact reports now
checked in, with source and schema hashes verified locally. The final workflow additionally rejects
untracked generated evidence. A fresh all-green push CI on the materialization commit remains
mandatory. The immutable frozen SHA, final run/job and artifact digest are recorded in PR #9 to
avoid a self-referential report commit.

Builder Red Team: the findings listed above are repaired and covered by the focused suite; no known
implementation blocker remains. This is not an independent exact-SHA review.

Initial checkpoint CI `35436308696`, job `105879438841`, passed focused Stage 09, focused Stage 10,
full regression, schema/package and integrity steps, then failed generated-evidence reproducibility
because new reports had not yet been committed. This is a bootstrap failure, not a waiver or green
candidate. Later source changes require fresh exact-head evidence.

A local test failed in inherited CreateCase setup with DomainError UNKNOWN before Stage 10 code.
Direct diagnosis returned ConnectionTimeout for both local test database roles. GitHub PostgreSQL
CI is the authoritative integration environment; no local functional PASS is claimed.

No Stage 11 renderer, Stage 12 certification/provenance engine, or Stage 13+ work is included.
The three requested operating documents remain NOT PRESENT IN VERIFIED BASELINE; execution relies
on the verified baseline and the user's explicit authorization recorded in readiness.
