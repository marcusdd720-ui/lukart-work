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

## Legal Document Compiler / Controlled Legal Language Architecture

Status: BACKLOG — ARCHITECTURE GATE REQUIRED
Priority: P0 PRODUCT QUALITY
Trigger: Stage 11 Rendering Engine closure

### Problem

For identical case state and approved legal inputs, LUKART must not rely on a fresh unconstrained LLM generation to obtain a final legal document.

The system must separate:

- legal/semantic content;
- rhetorical realization;
- presentation/rendering;
- approved artifact identity.

Any change between document versions must be explainable by an explicit input, policy, authority, strategy or presentation delta.

### Candidate architecture

Evaluate, rather than assume, the following stack:

- `Legal Semantic IR` — intermediate legal-semantic representation;
- `LegalDraftingPolicy` — versioned legal writing policy;
- `AdvocacyPolicy` — calibrated assertiveness/formality based on document type, recipient, procedural posture and evidence/legal strength;
- `Legal Surface Realizer` — converts approved semantics into professional legal language without changing legal meaning;
- `Semantic Equivalence Gate` — blocks language rewrites that add/remove/change facts, legal bases, requests, intent or certainty;
- `Language Quality Gate v2` — detects unsupported certainty, weak hedging, rhetorical overstatement, emotional/colloquial language, redundancy, vague references and missing legal consequence;
- `DocumentChangeManifest` — machine-readable reason for every material version change;
- `semantic_digest` and `presentation_digest` — separate semantic and visual identity;
- exact-input -> exact-approved-artifact reuse;
- controlled Polish legal-writing gold corpus.

### Canonical writing objective candidate

LUKART should not aim for rhetorical aggression.

Candidate standard:

> Maksymalna siła argumentacyjna uzasadniona materiałem sprawy, bez retorycznego przekraczania poziomu dowodów i prawa.

The system should write as firmly as verified facts, evidence, law and procedure justify — neither weaker nor stronger.

### Adoption rule

Do not promote this architecture into the canonical product merely because it sounds technically strong.

Before adoption:

1. compare at least a simple prompt/review baseline, a policy+surface-realizer design and a compiler/semantic-IR design;
2. run controlled benchmark cases;
3. measure semantic stability, fact/legal/request preservation, assertiveness calibration, unsupported certainty, weak hedging, redundancy, reproducibility, cost and maintenance complexity;
4. reject variants whose complexity is not justified by measured benefit;
5. require an explicit architecture decision gate before standardization.

Evidence Before Standard.
