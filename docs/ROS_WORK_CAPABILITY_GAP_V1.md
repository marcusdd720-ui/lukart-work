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

### 2026-11-03 Stage 11 source-bound golden repair

PR #84 exact-head CI exposed `test_fresh_process_reproduction_is_stable`: the two fresh subprocesses produced identical identities, but four derived metadata hashes no longer matched the frozen golden. Root cause was verified, not guessed: `validation_pin()` hashes every `.py`/`.sql` file under `lukart_work`; the candidate source inventory grew from 74 to 81 files (7 added) and modified `finalization/service.py` plus `operator_host.py` after the previous golden. This necessarily changed the validation pin and dependent validation/projection/model/layout identities. DOCX and PDF byte hashes, semantic digest, draft, plan, profile and renderer pins remained identical to the CI golden.

Only the four source-derived metadata fields (`layout`, `model`, `projection`, `validation`) were refreshed from the exact PR CI output. The test code and DOCX/PDF hashes were not changed. Local Python 3.14.7 reproduced stable metadata and matched the new four golden fields; its DOCX/PDF bytes differ from the CI Python 3.14.9 runtime, so local byte-level rendering is not treated as a PASS. Evidence: `evidence/stage11-render-identity-20261103.json`. Exact-head CI rerun is still required before Stage 11 can be marked PASS.

### 2026-11-03 ROS–WORK contract schema repair

The first PR #84 full regression exposed `CONTRACT_KEYS` in `tests.test_ros_work_integration_contract`. The contract had gained ephemeral `candidate_observation` and `mapping.assess` fields without a contract-version change, while the validator deliberately requires the exact v1 top-level and mapping key sets. The validator also still expected the old `PLANNED_NOT_IMPLEMENTED` / `assess=PLANNED` state despite the explicitly implemented read-only assess candidate. The ephemeral Work/ROS candidate-head and CI snapshot is now kept separately in `evidence/ros-work-candidate-observation-20261103.json`, not in the normative contract.

Repair: preserve the exact v1 normative key set; remove ephemeral candidate observation from the contract (it belongs in evidence, not the normative contract); fold the assess mapping into the existing `mapping.request` field; update the validator to the current read-only-only, production-blocked status; and make the package-read authority explicitly HUMAN-only with SERVICE/AI denied. The focused contract suite now reports **7/7 PASS**. Evidence: `evidence/ros-work-contract-repair-20261103.json`.

The initial Stage 10, Stage 11, Stage 12 and Stage 13 CI failures all traced to the two verified causes recorded in the evidence receipts: contract-schema drift and the stale source-derived Stage 11 golden. The contract/golden fixes are local; exact-head CI must be rerun after the signed repair commit.

### 2026-11-03 Windows embedded-session rejection fix

The combined local suite exposed a Windows TCP reset when an invalid bearer token was rejected before the POST body had been consumed. The handler sent `403` and closed the socket with unread request bytes; Windows could reset the connection before the client received the response. The handler now uses `reject_request` to accept only one well-formed, bounded `Content-Length`, send the rejection first, and drain at most `MAX_BODY + 1` bytes without parsing or dispatch. `body_consumed` distinguishes early authorization failures from post-dispatch denials so the server never drains a body twice.

The Windows case-only host module now reports **7/7 PASS**, including `test_invalid_embedded_session_token_fails_before_dispatch`. The combined local suite reports **190 tests: 73 PASS, 117 SKIP, 0 FAIL**; the skips are PostgreSQL-backed PB02 tests because no isolated local PostgreSQL DSN is configured. Critical Ruff rules, Python compilation, contract/golden JSON parsing and `git diff --check` PASS. Receipt: `evidence/local-regression-20261103.json`.

### 2026-11-03 Stage 11 follow-up golden repair

The first golden refresh was performed before the Windows embedded-session rejection fix changed `lukart_work/operator_host.py`. Because `validation_pin()` hashes every `.py`/`.sql` file under `lukart_work`, that subsequent source change invalidated the four dependent Stage 11 metadata fields again. Exact-head CI run `41726846536`, job `126233780292`, confirmed the failure is limited to `layout`, `model`, `projection`, and `validation`; 19/20 Stage 11 tests passed, including fresh-process identity stability. DOCX/PDF bytes and draft, semantic, plan, profile and renderer pins matched the CI golden and were preserved.

The second refresh uses the exact Python 3.14.9 CI identity values. Current validation source pin is `234de450e000ee88e4693261551ac7d16eb291d0bd7b6ba8466ef0fccae4442c`; current `operator_host.py` SHA-256 is `8127f31ee5257107cb6d6428355fa7a5617df985e58acadd1eb39500bc2115ad`. Windows CPython 3.14.7 and 3.14.9 both reproduce the four metadata fields and the same Windows DOCX/PDF hashes, but those byte hashes differ from the Linux CI golden. The platform cause is not yet isolated; preserve the CI byte values and use exact-head Linux CI as the authority. Evidence: `evidence/stage11-render-identity-20261103.json`. The second signed repair must receive fresh exact-head CI before Stage 11 is PASS.

### 2026-11-03 Stage 12/13 generated-evidence repair

The exact-head PR #84 run `41727832431` completed all Stage 09/10/11/12 tests and the independent JSON Schema validation, then failed only at **Generated evidence is reproducible**. The checked-in Stage 10 report still recorded 727 tests, while exact-head CI ran **859/859 PASS, 0 FAIL, 0 ERROR, 0 SKIP**. The global manifest was also stale: the candidate adds source and test files and changes hashes for the finalization service, operator host and ROS/WORK contract tests.

The four files were taken from the exact-head CI artifact `13274038447`, not manually reconstructed: `reports/stage10-status.json`, `reports/manifest.sha256.json`, `reports/stage10-schema-validation.json`, and `reports/package-validation.json`. Their artifact hashes and the failure diagnosis are recorded in `evidence/stage12-generated-evidence-repair-20261103.json`. Local `scripts/check_stage10_integrity.py` now reports **PASS: 479 manifest entries; Stage 10 evidence and schema hashes consistent**. The evidence receipt itself and this documentation update must be included before regenerating the final manifest, so the next exact-head CI can verify the committed tree reproducibly.

The CI schema validator passed all **118 schemas** with `jsonschema 4.26.0 Draft202012Validator`. Package verification reports **113 PASS / 2 REJECTED_AS_EXPECTED / 0 FAIL** across 118 JSON files. Stage 13 exact-head run `41727832113` also reports **859/859 PASS**, zero skips, and nine post-implementation synthetic benchmark operations with `network_io=NOT_USED`; it makes no live Ollama claim. Its only failed step was the same stale-manifest reproducibility check. Artifact `13274634531`, SHA-256 `2ce6a014f1638a3e5ae0c5e214ba8ec701153305c75088c9c47b0d69aba61e6c`. `stage_10_closed` remains explicitly **false**; independent product acceptance and release authority are not inferred from these engineering gates.

### 2026-11-04 Stage 11 source-bound identity refresh — review-fix candidate 5fa4971

Exact candidate 5fa49714a3b7e64e2ffda16170399362adf6f874 changes two WORK Python source files after the preceding identity baseline: lukart_work/legal_os_case_view.py (restored Polish UI text and package-member status copy) and lukart_work/legal_os_demo.py (a bounded 256 KiB request cap for valid multibyte demo forms). The rendering engine, semantic content, plan/profile inputs and test fixture were not changed. validation_pin() inventories all 81 .py/.sql sources under lukart_work, so these source edits necessarily change the dependent validation, projection, model and layout provenance identities even though the rendered document bytes and semantic digest remain unchanged.

Exact-SHA Stage 11 CI on 5fa49714a3b7e64e2ffda16170399362adf6f874 (run 41845304018, job 126627133230) executed 20 tests: 19 passed, 1 failed, 0 errors, 0 skipped. The sole failure is the expected-vs-actual comparison in test_fresh_process_reproduction_is_stable; the test first compares two fresh subprocess outputs and that comparison passed. CI emitted the exact identity recorded in evidence/stage11-render-identity-refresh-20261104-5fa4971.json.

Only the four source-derived metadata fields (layout, model, projection, validation) were updated in tests/golden_cases/stage11_render_identity.json. The CI DOCX/PDF hashes, semantic digest, draft, plan, profile and renderer pins were asserted unchanged and preserved. Two fresh local Windows subprocesses reproduced the exact four CI source-derived fields and all unchanged non-artifact fields. Windows DOCX/PDF bytes differ from Linux CI; the canonical Linux CI hashes remain in the golden and were not replaced by local outputs.

This is an exact-source provenance metadata migration, not a rendering behavior change and not a PASS on the pre-refresh SHA. Fresh exact-head Stage 11/12/13 CI is required. Stage 12 must regenerate the exact-SHA Stage 10 report and integrity manifest; local full regression is not substituted because this Windows checkout lacks the isolated PostgreSQL DSN and its local Stage 10 run had 410 skips. Evidence receipt: evidence/stage11-render-identity-refresh-20261104-5fa4971.json.

The product remains uncertified. PB02/PB03 independent exact-SHA acceptance, per-document-type legal admission, trusted native scoped HUMAN authority, and the full ROS -> WORK -> OCR -> Generator -> DOCX/PDF -> HUMAN -> FINAL/package -> FINISH process crash/recovery/replay proof remain separate blockers.
