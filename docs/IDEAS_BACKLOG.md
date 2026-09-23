# IDEAS BACKLOG — LUKART WORK

Status: ACTIVE
Purpose: Store promising architectural and operational ideas before they become repository standards.

Rules:

- BACKLOG is not implementation.
- An idea becomes a standard only after a concrete decision need, validation, and evidence.
- Avoid premature complexity.
- Evidence Before Standard.

---

## Hierarchical AGENTS.md architecture

Status: BACKLOG
Priority: MEDIUM
Trigger: repository growth / increasing domain specialization

### Idea

As `lukart-work` grows, evolve from one root-level `AGENTS.md` into a hierarchical instruction model.

Initial state:

- keep one strong root `AGENTS.md` as the repository-wide execution constitution / executable governance adapter.

Future structure may include, for example:

- `tests/AGENTS.md`
- `lukart_work/domain/AGENTS.md`
- `lukart_work/validation/AGENTS.md`
- additional domain-specific `AGENTS.md` files where justified.

Where a local subtree must genuinely replace rather than extend parent instructions,
consider `AGENTS.override.md` according to Codex instruction-discovery semantics.

### Rationale

Use the root `AGENTS.md` for global invariants, execution policy, security, Git discipline,
exact-SHA rules, fail-closed behavior, evidence requirements, provenance, authorization,
and Definition of Done.

Introduce nested instruction files only when:

- repository complexity increases,
- domain-specific rules become materially different,
- local instructions would improve precision,
- duplication in the root file becomes excessive,
- different subsystems require distinct validation or execution constraints,
- the root instruction budget needs to preserve headroom for specialized rules.

Avoid premature fragmentation.

### Adoption rule

Do not split instructions merely because the mechanism exists.

Adopt hierarchical `AGENTS.md` only when repository structure and operational complexity
provide a concrete justification.

Before adoption:

1. identify the concrete decision need;
2. identify the subtree and rule set that need specialization;
3. verify that the split reduces ambiguity or instruction bloat;
4. define which rules remain non-negotiable at repository level;
5. verify instruction loading and precedence;
6. add a regression/audit check if the hierarchy becomes operationally critical.

Evidence Before Standard.

---

## Controlled evolution of UNIVERSUM Execution Kernel

Status: BACKLOG
Priority: HIGH
Trigger: Stage 14 closure / future execution-stage planning

### Idea

Allow `UNIVERSUM Execution Kernel` to be updated and extended automatically only within an explicitly authorized execution scope.

During an active Stage, the kernel may evolve automatically when evidence establishes a concrete need, including:

- fixing a real CI or regression defect;
- applying a minimum safe repair;
- synchronizing generated evidence and manifests;
- improving exact-SHA execution or closure mechanics;
- making narrowly scoped changes required to reach verified closure.

Automatic evolution must remain bounded by the current Stage and its authorized mission.

### Guardrails

Automatic evolution must not become indefinite autonomous expansion.

The kernel must not, without a new explicit scope or HUMAN authorization:

- merge itself into `main`;
- approve its own independent review;
- transfer PASS across a changed SHA;
- introduce unrelated features because they appear useful;
- start future architectural programs such as a Reliability Control Plane;
- broaden scope beyond evidence-backed needs of the current Stage.

After Stage 14 closure, further development should be initiated by a new decision need, roadmap item, or Stage, and should follow the same control path:

`evidence → minimum safe change → targeted verification → exact-SHA CI → independent review → HUMAN merge gate`.

### Rationale

The goal is to preserve the speed benefits of autonomous repair and orchestration while preventing uncontrolled scope growth, self-approval, or trust-boundary erosion.

The kernel should become more capable through evidence-backed iteration, not through open-ended self-expansion.

### Adoption rule

Before making this behavior a repository standard:

1. define which change classes are eligible for autonomous repair;
2. define the exact HUMAN gates that cannot be crossed;
3. define how candidate freeze interacts with later repair;
4. define CI-budget and SHA-churn limits;
5. define how future Stages reopen or extend kernel capabilities;
6. add regression tests proving that autonomous evolution remains bounded by authorized scope.

Evidence Before Standard.
