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
