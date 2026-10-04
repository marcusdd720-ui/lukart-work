# ROS -> WORK capability gap and Integration Contract v1

Status: **PLANNED / NOT IMPLEMENTED**. This is a bounded integration contract and gap
inventory, not product support, certification, or permission to bypass any WORK HUMAN gate.
The machine-readable contract is
[`contracts/ros_work/v1/integration-contract.json`](../contracts/ros_work/v1/integration-contract.json).

## Evidence boundary

- WORK was inspected at checked-out HEAD
  `07ccc0a51e6297e9ab1ca9f287b4edea5d0df3da` on
  `uaos/generator-pism-p0`.
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
| Trusted render -> persist -> approval -> release -> package | WORK | Missing | Close PB-017 through PB-021 in WORK; ROS cannot supply this authority. |
| Neutral result/evidence/provenance | Existing convergence v1 | Implemented | Reuse without a second cross-repo vocabulary. |

## Blocking gaps and order

1. `RW-GAP-01` / P0: implement the trusted persisted finalization route in WORK (LW-PB-02).
2. `RW-GAP-02` / P1: implement the ROS-operation-to-WORK adapter only after the WORK public
   boundary exists. It must bind exact scope, native capability, ROS request digest,
   idempotency, and WORK case sequence/CAS.
3. `RW-GAP-03` / P1: define and validate CIRP-to-WORK mappings. Imported artifacts are proposals
   or evidence references, never accepted facts, legal applicability, strategy, or approval.
4. `RW-GAP-04` / P1: admit each supported letter type separately with schema/profile/fixture and
   independent legal/domain review.
5. `RW-GAP-05` / P2: refresh and re-pin the ROS baseline through the supervisor before any
   implementation candidate claims current cross-repository conformance.

## Contract operations

- `ros.work.generator.assess.v1` is a planned read-only readiness projection. It may report
  blockers; it may not mutate case state.
- `ros.work.generator.execute.v1` is blocked until PB02 and a supported type are admitted. ROS
  authority is never sufficient by itself; the trusted host must resolve it to a native scoped
  WORK HUMAN capability.
- `ros.work.generator.read-package.v1` is blocked until an immutable scoped package route exists.
  Package read and source-byte export remain different capabilities.

No positive execute/package conformance fixture is permitted while the corresponding gap is
open. Negative contract tests are evidence of fail-closed planning only, not evidence that the
integration or Generator Pism product is implemented.
