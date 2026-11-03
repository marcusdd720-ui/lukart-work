# ROS -> WORK capability gap and Integration Contract v1

Status: **PARTIALLY IMPLEMENTED ? READ-ONLY ASSESS ONLY / PRODUCTION BLOCKED**. This is a bounded integration contract and gap
inventory, not product support, certification, or permission to bypass any WORK HUMAN gate.
The machine-readable contract is
[`contracts/ros_work/v1/integration-contract.json`](../contracts/ros_work/v1/integration-contract.json).

## Evidence boundary

- WORK PB03 execution began from checked-out HEAD
  `7b8f0352da4840ce57abddbee19ac6c7774fd965` on
  `uaos/generator-pism-p0`. The PB03 candidate SHA remains **NOT VERIFIED** until the external
  supervisor checkpoints the dirty worktree.
- ROS was inspected read-only at the locally observed `refs/remotes/origin/main`
  `75ab7ebc45421cb49374ebb169449f3367b8be73`.
- The supervisor owns fetch/checkout, so ROS remote freshness is **NOT VERIFIED** in this run.
  Every ROS conclusion is bounded to that exact locally available commit and the Git blob pins
  recorded in the contract.
- Existing cross-repository convergence v1 remains the shared evidence/result/provenance
  vocabulary. This package does not create a competing envelope.

## Decision

Use ROS as an optional orchestrating client and WORK as the authoritative Generator Pism
domain. Keep the repositories independently deployable. An adapter may translate an allowlisted
ROS operation request into public WORK commands, but native WORK authorization, case sequence,
HUMAN decisions, validation, storage, render, release, and package records remain authoritative.

The rejected alternatives are a shared database, importing either repository as the other's
runtime package, using ROS presentation renderers for WORK DOCX/PDF, and treating ROS CIRP or
operation success as WORK legal truth or FINAL authority. Each would duplicate an existing
capability or cross a trust boundary.

## Capability inventory

| Capability | Owner | Observed state | Integration decision |
|---|---|---|---|
| Operation envelope, CAS precondition, idempotency, timeout, effects/evidence | ROS | Implemented at pinned ROS baseline | Reuse through an adapter; do not fork semantics. |
| Canonical Case Ledger | ROS | Implemented contract | Do not replace or dual-write WORK case state. Exchange immutable references only. |
| CIRP strategy/filing contracts | ROS | Implemented contracts | Optional future input artifacts only after explicit Ref/revision/legal/HUMAN mapping. |
| Reasoning presentation renderer | ROS | JSON/Markdown/evidence-list presentation | Do not use for WORK final DOCX/PDF. |
| Stages 03-13 generator components | WORK | Components implemented | WORK remains the Generator Pism authority. |
| Trusted render -> persist -> approval -> release -> package | WORK | PB02/PB03 builder candidate implemented; independent exact-SHA review and CI pending | WORK remains authoritative; ROS cannot supply this authority. |
| Neutral result/evidence/provenance | Existing convergence v1 | Implemented | Reuse without a second cross-repo vocabulary. |

## Blocking gaps and order

1. `RW-GAP-01` / P0: PB02/PB03 builder code now covers the trusted persisted finalization and
   package route. Checkpoint, full regression, CI and independent exact-SHA review remain open;
   this is not product certification.
2. `RW-GAP-02` / P1: the read-only assess adapter is implemented as a local candidate. It binds
   exact tenant/case UUID scope, a trusted native WORK read capability, ROS request digest and
   idempotency, and a bounded timeout. Execute and package-read adapters remain blocked pending
   independent PB02/PB03 acceptance, per-type admission, and separate native WORK capabilities.
3. `RW-GAP-03` / P1: define and validate CIRP-to-WORK mappings. Imported artifacts are proposals
   or evidence references, never accepted facts, legal applicability, strategy, or approval.
4. `RW-GAP-04` / P1: admit each supported letter type separately with schema/profile/fixture and
   independent legal/domain review.
5. `RW-GAP-05` / P2: refresh and re-pin the ROS baseline through the supervisor before any
   implementation candidate claims current cross-repository conformance.

## Contract operations

- `ros.work.generator.assess.v1` is implemented as a read-only candidate mapping to native
  `CoreQuery.GetCaseHead`. It may report blockers; it may not mutate case state. Local tests and
  schema validation pass; current dirty-worktree exact-SHA CI and independent review remain pending.
- `ros.work.generator.execute.v1` is blocked until PB02/PB03 are independently accepted and a
  supported type is admitted. ROS
  authority is never sufficient by itself; the trusted host must resolve it to a native scoped
  WORK HUMAN capability.
- `ros.work.generator.read-package.v1` now has a WORK-side PB03 builder route, but remains blocked
  on checkpoint/review and the unimplemented ROS adapter. Package read and source-byte export
  remain different capabilities.

No positive execute/package conformance fixture is permitted while the corresponding gap is
open. Negative contract tests are evidence of fail-closed planning only, not evidence that the
integration or Generator Pism product is implemented.


## Addendum ? 2026-11-03 local candidate state

The 2026-10-04 observation above is historical. Current local candidate heads were re-inspected:

- WORK `integration/legal-os-hidden-document-engine-v1`: `64c42579819381988707f9b45c496ce84c01eb1e` (dirty, uncommitted).
- ROS `h2/ros-work-native-corequery-verified-20261103`: `fc4c27b043cf9af4de4c420e3d6b37f9d0e1cc60` (dirty, uncommitted; Draft PR #381).
- The WORK `CaseHeadResult.schema.json` blob remains `aa97dd4ef4865948fe7c393c224b0bacdca421a2`, matching the adapter pin.

Implemented locally: WORK case workspace/composer, case-only host mode and read-only saved-render listing; ROS read-only assess adapter to native `CoreQuery.GetCaseHead`. The adapter deliberately does not map execute or package-read.

Local WORK verification: 64 Python unit tests PASS, including the case-only HTTP host authenticated-session dispatch and invalid-token rejection; composer DOM/HTTP 5/5 PASS; local synthetic-draft JavaScript 6/6 PASS; Ruff PASS; Mypy PASS for the three changed source modules; integration-contract JSON structure check PASS. Logs and SHA-256 manifest are in `evidence/legal-os-e2e-20261103/`. These are synthetic/local checks, not a live authenticated HUMAN session.

Local ROS verification: adapter tests 64 PASS; H4 isolation plus durable escrow tests 21 PASS; native CoreQuery schema check PASS; Ruff, Mypy, `uv lock --check` and diff whitespace checks PASS. Full repository regression was still running when this addendum was prepared; its final result must be recorded separately.

The existing remote CI runs for committed ROS head `fc4c27b043cf9af4de4c420e3d6b37f9d0e1cc60` do not validate the dirty local working tree. No CI has yet validated the current WORK dirty tree. No independent exact-SHA review has accepted the current local candidates.

Still NOT VERIFIED / BLOCKED: real authenticated HUMAN end-to-end acceptance; isolated live PostgreSQL-backed operator-host execution on these exact candidates; PB02/PB03 independent acceptance; supported document-type legal/domain admission; CIRP-to-WORK mapping; execute adapter; package-read adapter; production release/deployment. No real client data or credentials were used. No merge, release or deployment occurred.

### 2026-11-03 local security hardening delta

A local review found that `FinalizationService.query` rejected AI actors but permitted a scoped SERVICE actor to call `ReadFinalArtifact`, `GetFinalPackage`, and `ReadFinalPackageMember` when that actor held the corresponding action grant. The local integration candidate now requires `HUMAN` for those three byte/package-read operations, after the exact action and tenant/case checks and before opening a repository transaction. A regression test grants a SERVICE actor all three actions and proves all three requests fail with `FORBIDDEN` without database access.

Validation receipt: `evidence/legal-os-e2e-20261103/read-authorization-fix.json`. After the patch, the 64-test case-only/composer/demo integration suite reports 64 PASS, 0 SKIP. The finalization module reports 2 PASS and 117 SKIP; the skips are PostgreSQL-backed PB02 tests because no isolated PostgreSQL test DSN is configured. Critical Ruff rules and Python compilation PASS. Full Ruff findings are unchanged from the branch baseline. Mypy is NOT VERIFIED because the available type-check environment lacks `pydantic`; no dependency installation was attempted.

This is a local, uncommitted security correction only. It does not grant native WORK capabilities, close PB02/PB03, admit a document type, authorize positive execute/package reads, or establish production readiness. The separate draft WORK PR #83 was not modified, rebased, merged or pushed.

### 2026-11-03 product-baseline readiness check

The exact committed baseline blob `14c9ec8ac3eb00f4e6a0b12b09f7cf8588ab828d` (SHA-256 `275832c6f74ea2200d9eede57bd4362d92d0b991d655c56980390b44e3373aa2`) was parsed from the current WORK candidate. Its authoritative state is `contract=IMPLEMENTED_BUILDER_CANDIDATE`, `product=PLANNED`, `independent_review=NOT_VERIFIED`, `certification=NOT_VERIFIED`. All three catalogue types (`PL-PRE-PAYMENT-1`, `PL-PRE-COMPLAINT-1`, `PL-PRE-REPLY-1`) remain `NOT SUPPORTED / FUTURE`. Of 25 requirements, 11 are PARTIAL, 8 are component-only, 2 are PLANNED, and 4 are planned product boundary/write/bundle items; 24 have only component evidence or are not verified, 1 has an unverified product timeline, and 0 are certified. HG-04 is not demonstrated as a complete enforced product gate; HG-09 public final approval is currently `GATE_DENIED`; HG-10 requires an independent verifier and distinct promoter.

Machine-readable extraction: `evidence/legal-os-e2e-20261103/product-baseline-status.json`. This baseline is a hard product-admission blocker, not a failing unit test. No code change may convert these statuses to SUPPORTED/ACCEPTED without the required independent legal/type review and explicit HUMAN product admission.
