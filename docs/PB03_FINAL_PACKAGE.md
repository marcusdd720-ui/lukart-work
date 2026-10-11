# PB03 immutable final package boundary

Status: **IMPLEMENTED BUILDER CANDIDATE / NOT INDEPENDENTLY VERIFIED / NOT CERTIFIED**.

Repository: `marcusdd720-ui/lukart-work`
Implementation baseline: `7b8f0352da4840ce57abddbee19ac6c7774fd965`
Candidate SHA: **NOT VERIFIED until the external supervisor checkpoints this worktree**.

## Scope and decision

PB02 established the trusted render, persistence, HUMAN approval and FINAL release boundary.
PB03 closes the next bounded dependency, PB-021: after an exact repository-issued release, an
authenticated HUMAN operation assembles and persists one immutable package. It does not admit a
real Polish letter type, replace legal review, submit a filing, sign or deliver a document, or
implement a ROS adapter.

`AssembleFinalPackage` accepts only the current rendered Draft identity, snapshot hash, render id,
case sequence and rationale. The application reloads every semantic, validation, approval,
release, source and audit record. Callers cannot supply package members, trace maps, hashes,
manifest fields, build identity or PASS evidence.

## Exact package

The package contains exactly these ordered members:

1. `final.docx`
2. `final.pdf`
3. `document.json`
4. `validation.json`
5. `sources.json`
6. `evidence-map.json`
7. `argument-map.json`
8. `audit.json`
9. `release.json`
10. `manifest.json`

The first nine members are hashed and length-bound by `manifest.json`. The manifest does not hash
itself; its SHA-256 is stored in the authoritative `FinalPackageRecord`, avoiding a digest cycle.
The record also binds the release, render, case scope, exact deployment-supplied build revision,
LW-PB-01 contract digest and committed case sequence.

JSON members use deterministic canonical UTF-8 serialization. DOCX/PDF bytes must reproduce the
persisted PB02 render exactly. Source identities are exported, while source bytes remain in scoped
storage and are re-read only to verify provenance. Evidence and argument maps contain exact Ref
revisions, content hashes, links and source anchors; they do not promote allegations or machine
inferences into legal truth.

## Enforcement

- Assembly is allowed only immediately after the exact current FINAL release. Any intervening case
  mutation, revoked approval, stale hash, missing source, audit gap or corrupted artifact blocks.
- All ten writes, the package record, case CAS, command receipt, audit event and outbox entry share
  one PostgreSQL transaction. An injected member-write failure rolls the unit back.
- Reads require separate `GetFinalPackage` or `ReadFinalPackageMember` capabilities and native WORK
  tenant/case scope. Every read revalidates stored bytes, render reproduction, typed JSON,
  manifest/release bindings and the Stage 12 audit chain.
- Citation creation/binding/verification now uses public HUMAN Core operations so package audit
  evidence has no synthetic sequence gaps.
- Package profile provenance is injected by the trusted deployment. Runtime code never guesses a
  Git SHA.

## Verification

Focused package regressions:

```text
python -B -X utf8 -m unittest -v \
  tests.test_finalization.FinalPackageContractTests \
  tests.test_finalization.FinalizationTests.test_final_package_has_ten_verified_members_and_survives_restart \
  tests.test_finalization.FinalizationTests.test_package_requires_release_and_rolls_back_partial_member_writes \
  tests.test_finalization.FinalizationTests.test_package_reads_require_distinct_capabilities_and_detect_tamper
```

Full PB02/PB03 and repository regression, schema export verification, independent exact-SHA review
and CI remain required before any merge/admission conclusion. A skip is missing evidence, not PASS.

## Remaining product gates

All three LW-PB-01 real letter types remain `NOT SUPPORTED / FUTURE`. Per-type schemas, formal
input profiles, rules, prompts, fixtures and independent HUMAN legal/domain admission are still
required. The ROS↔WORK adapter and CIRP mappings remain unimplemented; ROS must continue to treat
WORK authorization, HUMAN gates, release and package bytes as authoritative.
