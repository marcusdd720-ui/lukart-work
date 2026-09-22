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

## Legal Document Compiler / controlled legal language architecture

Status: BACKLOG — DO NOT IMPLEMENT INSIDE STAGE 11
Priority: P0 immediately after Stage 11 closure
Trigger: successful Stage 11 merge + post-merge validation

### Problem

For identical case inputs, a generative drafting pass can still produce different wording,
argument emphasis or rhetorical strength.  A strong prompt alone is not a durable
15+ year reproducibility mechanism.

### Candidate architecture

Evaluate, do not assume, the following options:

1. prompt + linguistic review;
2. `LegalDraftingPolicy + Legal Surface Realizer`;
3. `Legal Document Compiler + Legal Semantic IR + AdvocacyPolicy +
   Semantic Equivalence Gate + Language Quality Gate v2`.

The third option is currently the most promising hypothesis, not an adopted standard.

### Required properties

- same approved input identity -> same approved artifact;
- every semantic change has an explicit reason;
- `DocumentChangeManifest`;
- separate semantic and presentation digests;
- assertiveness proportional to evidence and legal-authority strength;
- no unsupported certainty;
- no unjustified hedging;
- no emotional or theatrical aggression;
- professional, firm Polish legal language;
- legal-language transformation may not add facts, law, intent or requests;
- semantic-equivalence verification after language realization;
- golden corpus and adversarial evaluation before promotion into the Canon.

### Adoption gate

After Stage 11:

1. define a controlled benchmark;
2. compare the candidate architectures;
3. measure semantic stability, fact/law/request preservation, language quality,
   reproducibility, maintenance complexity, latency and cost;
4. adversarially test failure modes;
5. choose the simplest architecture that meets the measurable target;
6. promote only with evidence.

Evidence Before Standard.
