# LUKART WORK / UAOS — Execution Truth Contract

Date: 2026-10-05  
Priority: P0  
Status: DESIGN INPUT / IMPLEMENT AFTER CURRENT CLOSURE GATE  
Compatibility rule: documentation/specification only; no current Generator/PB01 runtime behavior is changed by this contract.

## 1. Root problem

A scheduler/control plane can report `RUNNING` while no real executor is doing useful work.
Therefore control-plane state MUST NOT be accepted as execution truth.

A process existing is not sufficient.
A fresh heartbeat is not sufficient.
An agent saying "I am working" is not sufficient.
A task becomes real execution only when independently observable evidence is bound to the exact task, exact attempt and current execution authority.

## 2. Core invariant — Evidence Before State

No high-trust state may exist without the evidence required to justify it.

In particular:

- `WORKING` requires a valid, non-expired execution authority plus independent liveness and progress evidence;
- `VALIDATED` requires verifier evidence bound to exact inputs and exact outputs;
- `COMMITTED` requires an exact commit/tree identity;
- `CI_VERIFIED` requires a CI result bound to that exact commit;
- `DONE` requires all mandatory gates to be satisfied and no unresolved P0/P1 blocker.

State is a projection of evidence. Evidence is not a decoration added after the state transition.

## 3. Do not overload one status field

A single `RUNNING` enum collapses orthogonal truths and is the primary source of false-green states.

The implementation SHOULD maintain at least these dimensions:

### 3.1 Lifecycle phase
- `QUEUED`
- `LEASED`
- `SPAWN_REQUESTED`
- `PROCESS_VERIFIED`
- `EXECUTING`
- `ARTIFACT_PRODUCED`
- `VALIDATION_RUNNING`
- `COMMITTING`
- `CI_RUNNING`
- `COMPLETED`

### 3.2 Liveness truth
- `UNKNOWN`
- `LIVE`
- `STALE`
- `DEAD`
- `ORPHANED`

### 3.3 Progress truth
- `NONE`
- `OBSERVED`
- `ADVANCING`
- `STALLED`

### 3.4 Assurance truth
- `UNVERIFIED`
- `EVIDENCE_BOUND`
- `VALIDATION_PASSED`
- `CI_PASSED`
- `VERIFIER_ACCEPTED`

### 3.5 Exception / policy states
- `BLOCKED`
- `QUARANTINED`
- `FAILED`
- `CANCELLED`

Legacy UI labels such as `WORKING` or `DONE` MAY remain as derived projections, but they MUST NOT be authoritative storage facts.

## 4. Execution authority — lease + fencing token

Every attempt MUST acquire an authoritative execution lease before it may mutate durable task state.

Required lease identity:

- `task_id`
- `run_id`
- `attempt_id`
- `lease_id`
- `lease_epoch` — monotonically increasing fencing token
- `worker_session_id`
- `worker_instance_id`
- `lease_acquired_at`
- `lease_expires_at`
- `lease_owner_capability_hash`

The durable store is the authority for lease time and lease epoch.

### Fencing rule

Every durable mutation and every externally visible side effect under task authority MUST carry the current `lease_epoch`.

After a lease is revoked, expires or is superseded, any write from an older epoch MUST be rejected.

This prevents a stale/zombie worker from continuing to mutate state after another worker has recovered the task.

## 5. Worker session identity

A worker process is not identified by PID alone.

A WorkerSession SHOULD bind:

- stable worker/agent identity;
- host/device identity;
- session UUID;
- process ID;
- process start timestamp / process-birth identity;
- executable or runtime digest where practical;
- workspace/worktree identity;
- capability profile hash;
- provider/model adapter identity;
- software build/version;
- current lease epoch.

The implementation MUST tolerate PID reuse.

## 6. Evidence-of-Execution record

At minimum:

### Task binding
- `task_id`
- `run_id`
- `attempt_id`
- `task_spec_hash`
- `input_bundle_hash`
- `base_commit_sha`

### Executor binding
- `agent_id`
- `worker_session_id`
- `worker_instance_id`
- `provider_id`
- `model_id`
- `capability_profile_hash`
- `workspace_id`
- branch/worktree
- process identity
- current `lease_epoch`

### Liveness/progress
- `heartbeat_seq`
- `heartbeat_at`
- `progress_seq`
- `progress_at`
- `progress_kind`
- `progress_digest`
- last independently observed tool/process event
- active child process/tool identity where applicable
- trace/span correlation IDs

### Outputs
- artifact hashes
- git diff hash
- commit SHA
- tree SHA
- test result digest
- validation report digest
- CI run ID/result
- completion evidence

## 7. Heartbeat semantics

Heartbeat proves only that a channel/session was recently observable.
It MUST NOT by itself prove productive execution.

Rules:

- no valid heartbeat => never project `LIVE`;
- heartbeat without independent process/session binding => untrusted;
- fresh heartbeat with unchanged progress sequence beyond a policy threshold => `STALLED`, not healthy `WORKING`;
- shell waiting with no child and no progress => stale candidate;
- process exists but no progress proof => insufficient;
- queued work + zero valid execution lease => P0 mismatch;
- lease with no observable executor => P0 mismatch;
- executor with stale lease epoch => reject writes and recover.

Use authoritative store time for cross-node lease expiry. Local monotonic clocks may be used for local interval measurement but MUST NOT be compared across hosts.

## 8. Progress evidence

Progress evidence MUST be externally observable whenever practical and MUST NOT rely solely on natural-language agent self-report.

Examples:

- new or changed file digest;
- tool invocation completed;
- test phase advanced;
- child process completed;
- artifact created;
- durable workflow step checkpointed;
- commit/tree changed;
- deterministic validator produced a report.

A long-running step may emit bounded progress checkpoints without pretending the step is complete.

## 9. Evidence-Carrying Execution (ECE)

LUKART SHOULD represent critical execution observations as append-only Execution Receipts.

Each receipt contains canonical structured data and:

- `receipt_id`
- `receipt_type`
- `sequence`
- `recorded_at`
- `task_id/run_id/attempt_id`
- `lease_epoch`
- `payload_hash`
- `previous_receipt_hash`
- `receipt_hash`
- observer identity
- optional cryptographic signature where the trust boundary justifies it.

`receipt_hash = H(canonical_receipt_without_hash || previous_receipt_hash)`

This is a tamper-evident evidence chain, NOT a blockchain and NOT a proof that an AI decision is correct.

High-trust transitions MUST reference the receipt(s) that justify them.

## 10. Independent observer

Agent self-report is a claim, not authority.

Where practical, liveness/progress observations SHOULD be produced by a host/runtime observer, durable workflow engine, CI system, repository adapter or other component outside the model's reasoning context.

The same model invocation that performed the work MUST NOT be the sole authority declaring the work correctly completed.

## 11. Independent completion verifier

`DONE` requires an independent verifier lane.

The verifier MUST be able to evaluate completion using:

- TaskSpec/acceptance contract;
- exact source/base identity;
- produced diff/artifacts;
- deterministic tests/validators;
- evidence receipts;
- exact commit/tree;
- policy gates.

The verifier SHOULD NOT require access to the builder's conversational context.

This is the **Contextless Completion** principle: a future worker, different model or human reviewer must be able to reconstruct why completion was accepted from durable artifacts alone.

## 12. Side-effect safety

Retries are inevitable. Duplicate externally visible effects are not acceptable.

For each side-effecting operation:

- define an idempotency key derived from stable task/run/operation identity;
- record intent before/atomically with dispatch where possible;
- record result/receipt after completion;
- use transactional outbox/inbox patterns when crossing database/message boundaries;
- support safe replay;
- reject stale `lease_epoch`;
- define compensation or manual-recovery semantics for non-idempotent external systems.

Do not claim generic "exactly once" execution across arbitrary external systems. The target is exactly-once observable effect where the boundary supports it, otherwise idempotent-at-least-once with evidence.

## 13. Retry and recovery semantics

- bounded retry budget;
- exponential/backoff policy with jitter where appropriate;
- retry classification: transient / permanent / policy-blocked;
- dead-letter/quarantine after budget exhaustion;
- deterministic stale-lease expiry;
- orphan recovery is idempotent;
- worker restart must not restart already committed durable steps;
- recovery must preserve exact input/version identity;
- cancellation must be durable and fenced.

## 14. Workspace isolation

Use an adapter interface:

- native Git worktree as baseline;
- container/sandbox when stronger isolation is required;
- Workmux or equivalent only as an optional accelerator;
- no runtime may receive ambient credentials it does not need;
- network disabled/allow-listed by default for high-risk lanes where feasible.

No workspace/sandbox provider may become an irreplaceable core dependency.

## 15. Durable execution backend boundary

LUKART MUST own a stable internal `DurableExecutionAdapter` contract.

Candidate implementations may include DBOS, Temporal, Restate, Hatchet, Hermes-style local queueing or a future replacement.

The LUKART contract, evidence model, TaskSpec, authorization rules and completion gates MUST remain valid if the backend is replaced.

Minimum adapter capabilities:

- start/resume execution;
- claim/lease/fence execution authority;
- durable step/checkpoint recording;
- heartbeat/progress observation;
- retry/backoff;
- cancel;
- signal/human approval;
- query current durable truth;
- emit/attach Execution Receipts;
- expose trace correlation;
- recover after worker/process/host failure.

## 16. Observability

Every run SHOULD have one end-to-end trace identity spanning scheduler, worker, model/tool calls, repository actions, validators and CI.

Prefer open telemetry conventions so observability remains vendor-neutral.

Dashboards MUST distinguish at least:

- queued tasks;
- claimed leases;
- live executors;
- advancing executors;
- stalled executors;
- verification backlog;
- retries;
- quarantined/dead-letter tasks;
- provider/model failures;
- completion rate and recovery rate.

## 17. Mandatory chaos and soak gates

A clean unit test is not reliability proof.

Before certification, exercise at least:

1. kill worker mid-step;
2. kill worker immediately after external side effect but before acknowledgment;
3. lease expires while old worker is still alive;
4. duplicate dispatcher delivery;
5. provider timeout / 429 / 5xx;
6. network loss;
7. database reconnect;
8. disk-full / write failure where practical;
9. process/PID reuse simulation;
10. stale heartbeat with no progress;
11. two workers competing for one task;
12. cancellation during execution;
13. verifier crash/restart;
14. CI failure after successful local validation;
15. machine restart;
16. 24h and 72h soak runs for the production lane.

Success criteria must be evidence-backed: no false `DONE`, no stale worker authority, no unbounded retry storm, no silent task disappearance.

## 18. Versioning and 15+ year compatibility

- durable records and event/receipt schemas are versioned;
- old records remain readable through migrations/upcasters;
- provider/model identifiers never appear in core business contracts as required constants;
- plugin/backend-specific metadata lives behind adapters/extensions;
- serialized canonical data has an explicit format/version;
- hashes specify algorithm/version;
- changes to state/evidence semantics require migration and conformance tests;
- repository/runtime upgrades preserve replay/audit capability.

## 19. Conformance suite

Every execution backend MUST pass the same LUKART conformance suite before production use.

The suite MUST test:

- lease/fencing semantics;
- crash recovery;
- duplicate dispatch;
- idempotent effect handling;
- stale worker rejection;
- heartbeat vs progress distinction;
- cancellation;
- human approval pause/resume;
- independent validation;
- evidence receipt integrity;
- exact artifact/commit binding;
- backend replacement compatibility.

Backend branding does not constitute certification.

## 20. Promotion gate

No implementation may be promoted from pilot to production merely because its demo succeeds.

Required:

- focused tests PASS;
- regression suite PASS;
- adversarial/chaos suite PASS;
- no P0/P1 findings;
- exact-SHA evidence;
- independent review;
- rollback path;
- sustained soak evidence appropriate to the lane.

## 21. Integration dependency

This contract is the P0 prerequisite for LSAF provider routing and higher-order autonomy.

Control-plane status must never become authority without matching execution evidence.


## 22. Immutable Candidate Identity and Promotion Truth

A branch name, pull-request number, tag label, dashboard status or human phrase such as "frozen candidate" is not a promotion identity.

Every promotion candidate MUST have an immutable CandidateIdentity bound to exact inputs.

Recommended fields:

- repository stable identity;
- base commit SHA;
- candidate commit SHA;
- candidate tree SHA;
- TaskSpec / acceptance-contract digest;
- product/domain contract digest set;
- policy/gate version digest;
- workflow-definition digest set;
- dependency/lockfile digest where relevant;
- toolchain/runtime image digest where relevant;
- generated-schema/evidence manifest digest;
- build/provenance metadata.

`candidate_id = H(canonical(CandidateIdentity))`

Rules:

- every commit after a freeze creates a new `candidate_id`;
- evidence from candidate A MUST NOT certify candidate B;
- a PR may contain many candidates over time, but only one exact candidate may be under promotion review;
- branch refs and PR heads are discovery pointers only, never assurance authority;
- CI/review/validation receipts MUST bind the exact `candidate_id` and exact candidate SHA/tree;
- a clean generated-evidence reproduction check is mandatory before promotion;
- if a required generated artifact changes during CI, promotion fails until that deterministic change is committed into a new candidate;
- rebases, dependency changes, workflow changes, policy changes and generated-schema changes invalidate the previous promotion evidence unless an explicit equivalence rule is proven by contract.

A UI may show "current candidate", but it MUST also show the exact immutable identity.

## 23. Evidence Quorum / Truth Mesh for P0 Transitions

For high-risk transitions, one subsystem must not be able to create truth by itself.

LUKART SHOULD support a policy-defined evidence quorum assembled from independent observer classes, for example:

- durable-execution observer;
- host/process observer;
- repository observer;
- deterministic validator;
- CI system;
- security/policy engine;
- independent reviewer.

A transition such as `WORKING`, `VALIDATED` or `DONE` is derived only when the required observer classes have produced compatible receipts for the same task/run/attempt/candidate identity.

This is not majority voting between language models. It is cross-plane corroboration between different sources of operational truth.

Risk tiers may require different quorums:

- low-risk synthetic research: durable runtime + progress observer;
- code mutation: runtime + repository + tests;
- P0 promotion: repository + deterministic validation + CI + independent review + policy gate;
- legal/client release: product-specific HUMAN/legal authority remains mandatory and cannot be replaced by machine quorum.

The quorum policy itself is versioned and evidence-bound.
