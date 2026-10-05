# Durable Execution — BUILD vs ADOPT Decision Record

Date: 2026-10-05  
Status: RESEARCHED DESIGN INPUT / PILOT ONLY AFTER CURRENT PB01 CLOSURE GATE  
Decision class: P0 runtime architecture  
Cost policy: zero-cost/self-hostable baseline required

## Executive decision

Do **not** build a proprietary durable-execution engine from first principles.

LUKART should own:
- its task/acceptance contracts;
- evidence model;
- execution truth semantics;
- authority/security policy;
- completion/validation gates;
- provider routing;
- a backend-neutral DurableExecutionAdapter;
- the conformance and chaos suite.

LUKART should **adopt** a proven durable-execution substrate behind that adapter.

### Recommended pilot order

1. **DBOS + PostgreSQL — PRIMARY PILOT**
2. **Temporal — REFERENCE / ESCALATION CANDIDATE**
3. **Hatchet — SECONDARY PILOT CANDIDATE**
4. **Restate — WATCH / SPECIALIZED CANDIDATE**
5. **Hermes Kanban — LOCAL-LANE PATTERN / UX REFERENCE, not distributed authority**

This is not a permanent vendor choice. Promotion requires LUKART conformance evidence.

## Why DBOS is the primary pilot

Current LUKART characteristics:
- Python-heavy repository;
- PostgreSQL already appears in the project/tooling;
- need for low operational complexity;
- zero-cost self-hosted baseline;
- need for durable workflows, queues, retries and recovery;
- requirement to avoid coupling business logic to a specific model/provider.

DBOS is a strong fit because:
- Python support is first-class;
- workflow/step state can be checkpointed durably;
- Postgres is the production durability substrate;
- queues and recovery are built around durable workflow state;
- it can be embedded with less operational surface than a full external orchestration cluster;
- MIT-licensed open-source SDK/runtime repositories reduce lock-in risk.

### DBOS risks to validate

- younger ecosystem than Temporal;
- LUKART must independently validate crash/replay/idempotency semantics;
- database contention, queue scaling and failure modes must be measured under LUKART load;
- external side effects still require explicit idempotency/outbox/fencing design;
- LUKART must not expose DBOS-specific types in stable domain contracts.

## Temporal position

Temporal remains the reliability reference implementation to benchmark against.

Strengths:
- mature durable workflow model and event history;
- worker crash recovery/replay;
- task queues, heartbeats, retries, cancellation and long-running workflows;
- strong production ecosystem and observability;
- self-hostable open-source service;
- current AI-agent integrations.

Costs:
- substantially larger operational/control-plane footprint;
- workflow determinism/replay rules add development discipline;
- likely excessive as the first substrate for the current LUKART footprint.

Decision:
- do not make Temporal mandatory now;
- keep the adapter/conformance suite strong enough that Temporal can replace DBOS if scale or reliability evidence requires it.

## Hatchet position

Strengths:
- MIT;
- Postgres durability;
- background tasks + durable workflows;
- worker slots/capability routing;
- self-hosting;
- attractive operational model.

Risks:
- recent changelog demonstrates that durable listeners, heartbeats and reconnect paths can themselves contain liveness bugs;
- must pass LUKART stale-worker, duplicate-delivery and soak tests before trust.

Decision:
- retain as an alternate benchmark/pilot, not primary authority yet.

## Restate position

Strengths:
- durable services/workflows/state;
- multi-agent orchestration patterns;
- durable human approvals;
- one-binary operational model;
- language-neutral service composition.

Risks:
- core runtime licensing differs from the permissive-MIT preference;
- introduces a distinct durable runtime/protocol;
- adoption value must materially exceed DBOS/Temporal for LUKART's actual workload.

Decision:
- watch and benchmark specific multi-agent/service patterns; do not bind core contracts to it.

## Hermes Kanban position

Hermes Kanban is a highly relevant design reference for LUKART's immediate P0 because it demonstrates:
- durable task lifecycle;
- separate worker processes;
- retry/max-runtime/priority controls;
- dependencies and idempotency;
- heartbeats;
- a canonical board/audit trail;
- a strong ownership rule in which the orchestrator remains owner and a coding agent is only an isolated execution lane;
- independent reconciliation before completion.

Limit:
- its local SQLite-centered design is excellent for a local durable board but is not, by itself, the preferred long-term distributed authority for LUKART multi-machine execution.

Decision:
- adopt the lifecycle/ownership patterns;
- do not clone the implementation wholesale.

## DeepSeek Harness position

The "everything is a plugin" design is strategically valuable.

Adopt conceptually:
- model adapters;
- tool adapters;
- skill adapters;
- sandbox adapters;
- storage adapters;
- scheduler/runtime adapters;
- UI adapters.

Do not adopt as an irreplaceable core while APIs are preview/fast-changing.

LUKART should preserve a smaller stable internal ABI and treat external harnesses as plugins behind it.

## OpenRig / OpenMuse position

Adopt security concepts:
- host-enforced least privilege;
- isolated execution identities;
- deny-by-default network where practical;
- bounded resource permissions;
- exact-action approval for sensitive operations;
- credentials outside model context;
- append-only/tamper-evident audit evidence.

Do not permit the LLM to be the final authority on its own permissions.

## Target architecture

```text
User / Project Intent
        |
        v
TaskSpec + Acceptance Contract
        |
        v
LUKART Control Plane
(queues, policy, priority, dependency graph)
        |
        v
DurableExecutionAdapter  <------------------------------+
        |                                                |
        +--> DBOS pilot                                  |
        +--> Temporal adapter (future/reference)         |
        +--> Hatchet adapter (candidate)                 |
        +--> Restate adapter (candidate)                 |
        +--> local/Hermes-style adapter                  |
                                                         |
        v                                                |
Execution Authority                                     |
(lease + lease_epoch/fencing)                           |
        |                                                |
        v                                                |
Isolated Worker Fabric                                  |
(worktree/container/sandbox)                            |
        |                                                |
        +--> ModelAdapter -------------------------------+
        +--> ToolAdapter
        +--> SkillAdapter
        +--> ProviderAdapter
        |
        v
Execution Receipts / Evidence Chain
        |
        v
Independent Validator / Reviewer
        |
        v
Commit -> CI -> Promotion Gate
```

## LUKART-specific differentiator: Evidence-Carrying Execution

The durable engine should guarantee that work can resume.

LUKART adds a stricter contract: **the system must also be able to prove why it believes work is happening and why it accepted completion.**

Each critical transition is backed by an append-only, hash-linked Execution Receipt produced by an appropriate observer.

This gives:
- forensic reconstruction;
- stale/zombie worker rejection;
- provider-independent completion evidence;
- cross-machine auditability;
- long-term migration evidence;
- ability to compare different durable engines against the same truth model.

This is not intended as blockchain technology. It is a compact tamper-evident evidence ledger.

## Second differentiator: Contextless Completion

A completion decision must be reproducible without the builder's chat history.

A fresh verifier must be able to answer:

1. What exactly was requested?
2. What exact source/input version was used?
3. Which executor had authority?
4. What changed?
5. Which tests/validators ran?
6. What evidence proves the result?
7. Which exact commit/tree/artifacts were accepted?
8. Were any policy exceptions used?

If those questions cannot be answered from durable state/artifacts, the task is not certifiably DONE.

## Third differentiator: Runtime N-versioning

Do not confuse provider/model redundancy with runtime redundancy.

Over a 15+ year horizon, LUKART should be able to run the same conformance workload against multiple runtime backends.

Maintain:
- one stable DurableExecutionAdapter contract;
- one backend-independent conformance suite;
- at least one recoverable alternate implementation path;
- exportable TaskSpec/evidence/event data.

This allows DBOS -> Temporal, Temporal -> future engine, or local -> cloud migration without rewriting LUKART's legal/business/product semantics.

## Required pilot before adoption

After PB01 closure, build one narrow vertical slice only:

`TaskSpec -> enqueue -> lease -> real worker -> progress evidence -> artifact -> independent validation -> commit -> CI -> DONE`

Fault-inject that slice before expanding scope.

Mandatory pilot faults:
- worker killed after claim;
- worker killed during model/tool call;
- stale worker continues after lease takeover;
- duplicate dispatch;
- external call times out;
- process hangs while heartbeat channel remains alive;
- database reconnect;
- verifier killed and restarted;
- CI failure;
- machine restart.

Promotion criterion:
**zero false-green DONE states under the fault suite.**

## Rejected strategies

### Build our own full scheduler/runtime now
Rejected: duplicates solved infrastructure, increases P0 surface, delays product delivery.

### Pick Hermes/DeepSeek/Temporal/DBOS as permanent product architecture
Rejected: provider/runtime lock-in conflicts with 15+ year requirement.

### Keep `RUNNING` as the main truth field
Rejected: cannot distinguish queued/claimed/live/stalled/productive/verified states.

### Use heartbeat as proof of work
Rejected: heartbeat proves contact, not progress.

### Let the builder self-certify DONE
Rejected: circular trust.

### Use chat/memory as authoritative project state
Rejected: ephemeral, provider-specific, hard to audit/replay.

### Assume "exactly once" for arbitrary external side effects
Rejected: unsafe abstraction. Use idempotency, outbox/inbox, fencing and explicit recovery semantics.

## Decision

**ADOPT proven durable execution; BUILD LUKART's evidence/authority/conformance layer.**

Primary pilot: **DBOS + PostgreSQL behind DurableExecutionAdapter**.

Reliability reference: **Temporal**.

Local task-board/lifecycle reference: **Hermes Kanban**.

Plugin modularity reference: **DeepSeek Harness**.

Security reference: **OpenRig/OpenMuse patterns**.

No runtime/provider receives permanent architectural authority.
