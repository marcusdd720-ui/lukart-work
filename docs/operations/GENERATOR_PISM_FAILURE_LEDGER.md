# Generator Pism — Failure & Recovery Ledger

Status: ACTIVE
Scope: Generator Pism v1.0 closure and its execution/control plane
Policy: **no incident disappears after a workaround**. Every failure remains OPEN until its systemic cause is eliminated and verified.

## Status model

- `OPEN` — cause not eliminated.
- `MITIGATED` — current run unblocked, systemic cause remains.
- `VERIFYING` — permanent fix implemented, awaiting exact evidence.
- `ELIMINATED` — permanent fix passed its stated closure evidence.
- `REJECTED` — reported symptom proven not to be a real defect.

## Mandatory record fields

Each incident MUST bind:
`failure_id → first_observed_at → project/task/run/SHA → symptom → evidence → root_cause → immediate_recovery → permanent_fix → owner → verification → status`.

A failure may not be marked ELIMINATED because "the next run happened to pass".

---

## Failure register

### GP-F001 — Generated evidence reproducibility drift
- Severity: P0 closure blocker
- First observed: 2026-10-05
- Affected candidate: historical/current pre-fix PR #57 heads
- Symptom: product tests passed but `Generated evidence is reproducible` failed.
- Evidence: diffs in `reports/manifest.sha256.json`, `reports/package-validation.json`, `reports/stage10-schema-validation.json`, `reports/stage10-status.json`.
- Root cause: committed generated evidence did not match clean CI regeneration.
- Immediate recovery: synchronize all four generated artifacts from CI output.
- Current verification candidate: `ce1096d6232cc89f6f3457f334da62f5f4e9948b`.
- Verification: all four mandatory exact-candidate workflows SUCCESS; reproducibility step PASS.
- Permanent fix still required: generated-evidence production must be deterministic across supported runtime/toolchain or explicitly pin the toolchain that owns the evidence.
- Status: **MITIGATED**
- Owner: Execution/Evidence lane
- Elimination DoD: two fresh independent candidate regenerations produce byte-identical committed evidence without manual synchronization.

### GP-F002 — Immutable candidate identity drift / stale certification inheritance risk
- Severity: P0 promotion integrity
- First observed: 2026-10-05
- Symptom: PR body referenced signed candidate `873b3c...` while PR head had advanced several commits.
- Root cause: freeze/review/signing state was not mechanically bound to one immutable CandidateIdentity.
- Immediate recovery: treat every new commit as a new candidate; do not inherit old PASS/review/signing.
- Status: **OPEN**
- Permanent fix: CandidateIdentity must bind commit SHA, tree SHA, acceptance digest, workflow/policy digests and evidence manifest.
- Elimination DoD: promotion gate rejects stale evidence for a newer SHA in automated conformance test.

### GP-F003 — Superseded workflow consumes only self-hosted executor
- Severity: P0 liveness
- First observed: 2026-10-06
- Symptom: current candidate `ce1096...` queued while old SHA work consumed the sole runner.
- Root cause: no latest-candidate ownership / cancellation policy.
- Immediate recovery: user cancelled obsolete GitHub Actions runs using `gh run cancel`.
- Status: **MITIGATED**
- Permanent fix: native GitHub Actions `concurrency` + `cancel-in-progress: true` + stale-candidate rejection.
- Related issue: #60.
- Elimination DoD: fault-injection proves a new PR head automatically cancels/supersedes old work and reaches executor without manual action.

### GP-F004 — Duplicate push + pull_request validation
- Severity: P1 capacity waste
- First observed: 2026-10-06
- Symptom: same candidate produced redundant expensive workflow runs.
- Root cause: overlapping workflow triggers without dedup/concurrency design.
- Immediate recovery: manual cancellation of duplicate push runs.
- Status: **OPEN**
- Permanent fix: deduplicate trigger policy so one candidate executes one required validation set.
- Elimination DoD: same SHA pushed to PR produces no redundant full-suite executions.

### GP-F005 — Missing bounded timeout on long self-hosted assurance work
- Severity: P1 liveness
- First observed: 2026-10-06
- Symptom: long-running assurance can occupy sole runner without a hard bounded termination.
- Root cause: missing job-level timeout on at least Stage 13 path observed during audit.
- Status: **OPEN**
- Permanent fix: bounded timeout + stale/no-progress detection.
- Elimination DoD: injected hung test is terminated and classified automatically within declared SLA.

### GP-F006 — Terminal CI FAIL had no durable remediation owner
- Severity: P0 autonomy
- First observed: 2026-10-06
- Symptom: CI reached terminal FAIL and stopped; no actor automatically performed evidence → root cause → repair → fresh SHA → rerun.
- Root cause: notification/state existed without executable next-role ownership.
- Immediate recovery: manual control-plane intervention.
- Status: **OPEN**
- Permanent fix: durable `RepairTask` owner created automatically on recoverable terminal FAIL.
- Elimination DoD: injected deterministic CI failure autonomously creates repair ownership and reaches a verified repaired candidate or a true HUMAN_REQUIRED boundary.

### GP-F007 — Control workflow shares the blocked executor
- Severity: P0 recovery deadlock
- First observed: 2026-10-06
- Symptom: `stage11-control` can have Actions permissions but itself depends on the same self-hosted runner it may need to recover.
- Root cause: recovery/control plane not failure-domain independent from worker plane.
- Status: **OPEN**
- Permanent fix: move control/recovery logic to independent GitHub-hosted/control-plane execution lane or durable external orchestrator.
- Elimination DoD: worker pool outage still allows control plane to cancel/reassign/quarantine work.

### GP-F008 — CI PASS did not auto-dispatch Independent Verifier
- Severity: P0 process continuity
- First observed: 2026-10-06
- Symptom: all exact-SHA workflows PASS, but no verifier was assigned; active execution count became zero.
- Root cause: no durable Next-Role / Next-Task dispatch after gate transition.
- Current candidate: `ce1096d6232cc89f6f3457f334da62f5f4e9948b`.
- Status: **OPEN**
- Immediate recovery: evaluate and attach an independent review agent without changing candidate SHA.
- Permanent fix: gate transition `CI_PASS → INDEPENDENT_REVIEW_READY → assigned verifier` must be automatic.
- Elimination DoD: test candidate reaches verifier assignment automatically within one control-plane cycle.

### GP-F009 — Copilot reviewer request not materialized
- Severity: P1 reviewer availability
- First observed: 2026-10-06
- Symptom: request for `copilot-pull-request-reviewer[bot]` returned without error, but GitHub review-request list remained empty.
- Root cause: current repository/account does not presently expose a usable Copilot review entitlement/assignment path, or draft/entitlement policy prevented assignment.
- Status: **OPEN**
- Permanent disposition: either verify entitlement/configure correctly or classify Copilot as unavailable for this lane and use another reviewer.
- Elimination DoD: a real external reviewer identity is visible on the PR and produces an exact-SHA review, or the route is formally REJECTED with evidence.

### GP-F010 — No independent review executor attached to private repo
- Severity: P0 release blocker
- First observed: 2026-10-06
- Symptom: current candidate has green CI but no qualified independent reviewer can be auto-started.
- Root cause: reviewer capability was planned but not provisioned/connected before reaching the gate.
- Best current ADOPT candidate: self-hosted **The-PR-Agent / PR-Agent OSS** with a separate zero-cost model provider (Groq first; OpenRouter/Ollama alternative) and GitHub read/comment authority.
- Fast external fallback: Greptile Starter if privacy review and GitHub App installation are accepted.
- Status: **OPEN**
- Elimination DoD: one qualified independent reviewer executes against exact candidate SHA and emits a review artifact bound to that SHA.

### GP-F011 — Closure Sentinel did not alert promptly when verifier lane was missing
- Severity: P1 human supervision
- First observed: 2026-10-06
- Symptom: project sat at `CI PASS / verifier missing` without the expected immediate user-facing blocker alert.
- Root cause: hourly condition-watch + insufficiently strict no-progress/next-role escalation semantics.
- Status: **OPEN**
- Permanent fix: Mission Control must detect `ready gate + no owner` as `UNOWNED_READY_WORK` and alert/repair automatically.
- Elimination DoD: synthetic unowned-ready task triggers assignment or HUMAN_REQUIRED notification within one configured control cycle.

### GP-F012 — Automation priority drift
- Severity: P1 portfolio governance
- First observed: 2026-10-06
- Symptom: orchestrator priority omitted Generator CV despite canonical portfolio decision.
- Root cause: automation prompt drift from portfolio SSOT.
- Immediate recovery: P0 Orchestrator prompt updated to `Generator Pism → Generator CV → WORK↔ROS → UAOS → BUILD-vs-ADOPT`.
- Status: **VERIFYING**
- Elimination DoD: priority is derived from one canonical durable portfolio source instead of duplicated prompt text.

---

## Reviewer route decision — 2026-10-06

### Route A — Self-hosted PR-Agent OSS + Groq
Decision: **PRIMARY / ADOPT**

Rationale:
- open-source PR review agent;
- supports private repositories when self-hosted;
- supports Groq via LiteLLM;
- can also use OpenRouter, Ollama and xAI/Grok;
- separates reviewer identity/model lane from the builder;
- can publish review evidence back to GitHub;
- fits 0 PLN policy if the selected provider is VERIFIED_FREE and no paid fallback is configured.

Constraints:
- GitHub token and provider key must remain in secret storage;
- reviewer must be configured read/review only, not promotion authority;
- exact reviewed SHA must be recorded;
- same provider/model that authored the patch cannot be the sole independent reviewer.

### Route B — Greptile Starter
Decision: **FAST FALLBACK / POC**

Rationale:
- current free Starter offers one active developer, limited monthly credits, unlimited repositories;
- purpose-built AI PR review.

Constraints:
- external SaaS / GitHub App receives private repository context;
- privacy/data handling must be accepted before use;
- quota is limited;
- must never become product SSOT or promotion authority.

### Route C — GitHub Copilot Code Review
Decision: **VERIFY ENTITLEMENT / CURRENTLY NOT USABLE**

Observed:
- standard reviewer request did not result in a requested reviewer on PR #57.

### Route D — CodeRabbit
Decision: **REJECT FOR 0 PLN PRIVATE-REPO BASELINE**

Reason:
- private-repo production plans are paid; free perpetual reviews are for public/open-source use, with trial-only path for private commercial usage.

---

## Operating rule

Every new Generator Pism failure must be appended to this ledger before closure work is considered complete.

The active closeout objective is not "zero observed failures"; it is:

**zero unresolved P0/P1 failure mechanisms capable of causing false-green completion, silent stall, stale authority, lost work, or unowned next steps.**


### GP-F013 — Reviewer workflow bootstrap requires trusted/default-branch presence
- Severity: P1 reviewer bootstrap
- First observed: 2026-10-06
- Symptom: isolated PR #62 added a new PR-Agent workflow, but no review workflow run was created; only workflows already trusted/present in the repository baseline were scheduled.
- Root cause: GitHub Actions trust/trigger semantics prevent using a brand-new unmerged workflow as an immediate privileged reviewer lane with repository secrets.
- Immediate recovery: do not merge reviewer infrastructure into main merely to unblock PR #57; use an existing trusted dispatch lane or local isolated reviewer execution.
- Status: **OPEN**
- Permanent fix: pre-provision a reviewed, least-privilege independent-review workflow/control-plane lane before a product reaches the review gate.
- Elimination DoD: a future candidate reaches CI PASS and an already-trusted reviewer workflow starts automatically without changing the candidate or main baseline.

### GP-F014 — Local recovery/reviewer lane depends on Desktop Commander quota
- Severity: P1 control-plane availability
- First observed: 2026-10-06
- Symptom: local Groq key exists encrypted with Windows DPAPI, but remote execution/read through Desktop Commander is paused because the monthly remote-call allowance is exhausted.
- Root cause: critical recovery/bootstrap capability depends on a quota-limited human-desktop control channel.
- Immediate recovery: HUMAN executes one bounded local PowerShell bootstrap command when required.
- Status: **OPEN**
- Permanent fix: Mission Control must have at least one independent zero-cost execution/control lane that does not depend on Desktop Commander quota.
- Elimination DoD: loss/exhaustion of Desktop Commander cannot prevent independent review, stale-run recovery, or provider dispatch.


### GP-F015 — PowerShell → WSL multiline command quoting corrupted reviewer bootstrap
- Severity: P1 reviewer bootstrap
- First observed: 2026-10-06 18:18 Europe/Warsaw
- Symptom: local reviewer bootstrap reached `wsl.exe bash -lc $Bash`, then Bash failed with `syntax error: unexpected end of file`.
- Evidence: user-visible PowerShell output showed Bash parse failure before PR-Agent/Docker review execution.
- Root cause: nested PowerShell + WSL + Bash multiline quoting/here-doc transport was not robust; the Bash program was truncated/misparsed before execution.
- Immediate recovery: replace inline `bash -lc` transport with a temporary script file and execute `wsl.exe bash <script>`.
- Status: **OPEN**
- Permanent fix: Mission Control bootstrap must avoid nested shell quoting for nontrivial scripts; use generated script files or a structured process API with explicit argv/env.
- Elimination DoD: reviewer bootstrap executes twice successfully with no quoting/parsing drift and secrets remain undisclosed.


### GP-F016 — PR-Agent review exceeded Groq Free TPM budget
- Severity: P1 independent-review blocker
- First observed: 2026-10-06 18:xx Europe/Warsaw
- Candidate under review: `ce1096d6232cc89f6f3457f334da62f5f4e9948b`
- Symptom: PR-Agent reached LiteLLM/Groq successfully, then exited with code `1`.
- Evidence: Groq returned `rate_limit_exceeded`: TPM limit `8000`, request `29317` tokens for `openai/gpt-oss-120b`.
- Log location: `C:\Users\LukaszA\AppData\Local\Temp\lukart-pr57-review\pr57-review.log`
- Root cause: PR-Agent default `config.max_model_tokens=32000` allowed a packed review prompt far above the user's free-tier 8k TPM limit; large-PR chunking cannot help unless the model-token budget itself is lowered enough to force smaller chunks.
- Immediate recovery: keep the same reviewer/provider but cap each call to a free-tier-safe token budget and enable large-PR chunking; no paid upgrade.
- Planned retry settings: `CONFIG__MAX_MODEL_TOKENS=5500`, bounded output tokens, chunking enabled, no duplicate same-model fallback.
- Status: **MITIGATED / RETRY REQUIRED**
- Owner: Independent Review lane
- Permanent fix: provider capability registry must include live TPM/RPM/context constraints and automatically derive per-call token budget before dispatch.
- Elimination DoD: exact-SHA review completes under 0 PLN without rate-limit failure, with explicit coverage reporting for any omitted files.


### GP-F017 — Baseline type packs exist but remain NOT_ADMITTED / product E2E not proven
- Severity: P0 product-completion blocker
- First observed: 2026-10-06 independent read-only preflight of candidate `ce1096d6232cc89f6f3457f334da62f5f4e9948b`.
- Evidence:
  - `lukart_work/type_packs/common.py` sets global `ADMISSION_STATUS = "NOT_ADMITTED"`;
  - all three pins encode literal `admission_status: NOT_ADMITTED`;
  - `tests/test_baseline_type_packs.py` explicitly asserts all three remain `NOT_ADMITTED`;
  - `scripts/verify_product_baseline.py --product-e2e` is intentionally specified to exit 1 and reports product E2E BLOCKED / independent review NOT_VERIFIED / certification NOT_VERIFIED.
- Important distinction: PB02/PB03 finalization/package code is materially implemented and tested; this finding concerns the missing proof/admission of the three real product types through the full public product path.
- Root cause: builder-candidate implementation and product-admission contract/evidence are not yet converged.
- Status: **OPEN**
- Required resolution: prove each type through the authoritative public E2E path and independent legal/type review, then change admission state only from evidence; if a missing adapter/dispatch/profile is discovered, build only that verified delta.
- Elimination DoD: T01-style E2E PASS independently for each of PL-PRE-PAYMENT-1, PL-PRE-COMPLAINT-1 and PL-PRE-REPLY-1; admission pins/status and acceptance contract updated from exact evidence; no HUMAN/legal gate bypass.


### GP-F018 — Acceptance contract drifted behind implemented finalization/audit transaction capabilities
- Severity: P0 closure-truth integrity
- First observed: 2026-10-06 read-only closure-gap audit of candidate `ce1096d6232cc89f6f3457f334da62f5f4e9948b`.
- Symptom: `acceptance/product-baseline-v1.json` still marks PB-017..PB-023 as planned/partial/component-only, while the candidate contains substantial authoritative implementations and tests for trusted render, persistent exact bytes, HUMAN final approval, release, ten-member final package, audit/provenance, replay/CAS/race/rollback/restart/tamper handling.
- Evidence examples:
  - `FinalizationService` owns RenderDraft → ApproveFinalDocument → RequestFinalRelease → AssembleFinalPackage with HUMAN-only guard and repository-derived authority;
  - `tests/test_finalization.py` covers caller injection rejection, exact bytes, rollback, race/CAS, revocation, restart, ten-member package, tamper and capability separation;
  - `tests/test_stage12.py` covers deterministic audit chain, trace-to-source, tamper, scope and privacy;
  - Stage09/10 tests cover actor-bound replay, CAS, provider/receipt mismatch, stale/revoked authority and transaction rollback.
- Root cause: acceptance SSOT was frozen before successor PB02/PB03 implementation and has not yet been reconciled through independent review.
- Status: **OPEN / EVIDENCE RECONCILIATION REQUIRED**
- Important: do not mark PB-017..PB-023 PASS solely from builder tests; independently map each Definition of Done to exact code/test evidence first.
- Permanent fix: machine-readable acceptance status must be regenerated/reconciled from exact candidate evidence and independent verification, not manually lag implementation.
- Elimination DoD: PB-017..PB-023 each have exact evidence mapping and independent verdict; contract status is updated accordingly on the final candidate without inheriting stale evidence.

### GP-F019 — Type-pack-to-public-pipeline adapter/admission delta is the remaining product path
- Severity: P0 product-completion
- First observed: 2026-10-06 closure-gap audit.
- Symptom: three real type packs define bounded validated inputs and fixtures but are not wired as admitted profiles through the full public CreateCase → ... → FinalizationService → FinalPackage path.
- Evidence:
  - all type packs remain `NOT_ADMITTED`;
  - `FinalizationProfile` explicitly says it does not admit a legal document type; trusted host must supply an independently admitted profile;
  - current type-pack tests validate schema/negative cases but not authoritative public E2E;
  - existing PB02/PB03 finalization path is generic and already implemented.
- Root cause: missing narrow product integration/admission layer, not missing generic finalization infrastructure.
- Status: **OPEN**
- Build policy: implement only the missing adapter/profile/fixture/evidence delta; do not rebuild planner, drafting, validation, rendering, storage, release or package engines.
- Elimination DoD: each of PL-PRE-PAYMENT-1, PL-PRE-COMPLAINT-1 and PL-PRE-REPLY-1 executes through authoritative public E2E to the ten-member final package with exact evidence and independent legal/type admission.


### GP-F020 — Scheduler carried agent intelligence instead of launching canonical agent contracts
- Severity: P0/P1 execution-architecture integrity
- First observed: 2026-10-07
- Symptom: worker behavior, recovery logic and project instructions were embedded directly in automation task prompts. Scheduler and agent responsibility were conflated, making behavior hard to version, reuse, review and recover consistently.
- Root cause: execution cadence mechanism was incorrectly used as the agent definition.
- Immediate recovery: create canonical versioned agent contracts in `marcusdd720-ui/lukart-ros` and reduce automations to thin launchers.
- Canonical candidate: LUKART ROS Draft PR #345, exact ref `18845cd4b40254b9ba1e0eba3037d57b09b0be99`.
- New contracts:
  - `LUKART_AGENT_RUNTIME_CONTRACT_v1.md`
  - `A1_GENERATOR_PISM_BUILDER_v1.md`
  - `A2_GENERATOR_PISM_VERIFIER_v1.md`
  - `A3_LATAM_CV_BUILDER_v1.md`
  - `A4_PROVIDER_ROUTER_v1.md`
  - `A5_RECOVERY_SPECIALIST_v1.md`
- Status: **VERIFYING**
- Permanent fix: scheduler owns only cadence/launch; agent contract owns identity, mission, queue, error-state machine, retry budget, recovery, handoff, no-idle behavior, cost/security boundaries and DoD.
- Elimination DoD: all active workers load pinned canonical contracts successfully for multiple cycles, and a synthetic/repeated failure follows DETECT -> CAPTURE -> CLASSIFY -> RECOVER -> VERIFY -> CONTINUE/ESCALATE without scheduler-specific business logic.


### GP-F021 — Type-pack E2E fixture conflated product evidence source with legal-quotation source
- Severity: P1 closure-test wiring defect
- First observed: 2026-10-07 preflight of closure candidate `1b4ec1e7ee4a12731581e2220756929bd4091f83`.
- Symptom: new type-pack E2E helper returned the JSON type-pack evidence source as the source consumed by the existing Stage09/10 legal-authority fixture.
- Evidence: Stage10 citation validation accepts literal quotation extraction only from `text/plain`; for `RECORD:1` it binds `fragment_hash` to SHA-256 of the complete source bytes. The existing legal fixture expects exact bytes `Synthetic payment receipt.`, while the new helper supplied `application/json` fixture bytes.
- Root cause: two semantically distinct provenance roles were incorrectly collapsed into one source id during test integration.
- Immediate recovery: keep type-pack JSON as its own accepted evidence source and register a separate immutable `text/plain` legal-authority source with the exact bytes expected by the existing public citation lifecycle.
- Product impact: none observed in generic engine; defect is in the new closure E2E fixture wiring.
- Owner: A1 Generator Pism Builder.
- Status: **MITIGATED / FRESH SHA VERIFICATION REQUIRED**
- Elimination DoD: fresh exact-SHA full regression executes all three type-pack E2E cases with Stage10 citation verification PASS; no source-role conflation remains.


### GP-F022 — Restart/read E2E called FinalizationService.query with the wrong wire type
- Severity: P1 closure-test wiring defect
- First observed: 2026-10-07 read-only preflight of closure candidate `04c35f40fd511552bacff344234d5ebe31dbd54d`.
- Symptom: the new restart/read loop passed a Python mapping directly to `FinalizationService.query`, while the public service contract accepts canonical JSON text and runs `strict_json(raw)`.
- Root cause: the new closure test bypassed the same JSON wire encoding used by the existing public query helpers.
- Immediate recovery: serialize the `FinalizationQuery` mapping with `json.dumps(...)` before calling the restarted service.
- Product impact: none observed in FinalizationService; defect is isolated to the new E2E test.
- Owner: A1 Generator Pism Builder.
- Status: **MITIGATED / FRESH SHA VERIFICATION REQUIRED**
- Elimination DoD: fresh exact-SHA regression executes restart/read for every member of all three type packages without wire-contract error.
