# AGENTS.md — LUKART WORK
## Enterprise Execution Policy

Policy-Version: 1.0
Status: ACTIVE
Scope: Entire repository unless a more specific nested AGENTS.md or AGENTS.override.md applies
Canonical governance: docs/ENTERPRISE_EXECUTION_CONSTITUTION.md
Repository: lukart-work
Operating model: build-first, evidence-first, fail-closed, exact-SHA

---

## 1. Instruction contract

This file is the executable repository-level instruction layer for Codex and other coding agents.

For any material code, schema, workflow, storage, validation, security, legal-authority, provenance, or release-gate change, read and apply:

`docs/ENTERPRISE_EXECUTION_CONSTITUTION.md`

before modifying the repository.

For simple read-only questions, this root policy is sufficient unless the task explicitly requires deeper governance review.

Higher-priority platform, system, developer, and explicit user instructions always prevail.

Nested AGENTS.md files may specialize local behavior, but they must not intentionally weaken repository-wide safety, evidence, provenance, authorization, exact-SHA, or fail-closed invariants.

---

## 2. Core invariants

Mandatory principles:

- Build First.
- Evidence Before Conclusion.
- Decision Need First.
- Problem First.
- Measurement Before Conclusion.
- Validation Before Trust.
- Incremental Validation.
- Evidence Before Standard.
- Factory != Product.
- Planned != Implemented != Validated != Certified.
- Root cause -> minimal fix -> focused test -> regression -> fresh SHA.
- Definition of Done includes integration evidence where applicable.
- If a required control cannot be established, fail closed.
- Unknown is not PASS.
- Missing evidence is not evidence of success.

Never claim DONE, PASS, VALIDATED, READY, MERGEABLE, CERTIFIED, or PRODUCTION READY unless the evidence required for that state has been verified.

If something was not verified, say `NOT VERIFIED`.

---

## 3. Autonomous execution and confirmation policy

Within a clearly authorized Stage, remediation, review, bug fix, or implementation scope, proceed autonomously.

Do not ask redundant user confirmation for routine, reversible, low-risk operations required by the authorized task, including:

- repository reads,
- Git history inspection,
- `git fetch`,
- safe `git pull`,
- reading remote refs,
- checkout/switch to an existing authorized working branch,
- reading `main`,
- reading PR metadata,
- comparing commits/branches,
- inspecting diffs,
- calculating hashes,
- running tests,
- running linters/static checks,
- running validation,
- reading CI/logs/artifacts,
- reproducing failures,
- exact-SHA review,
- focused remediation already inside the authorized scope,
- regression-test additions required by that remediation.

If the current task already authorizes the action, do not ask again.

Human approval is required before:

1. widening scope beyond the authorized Stage/remediation;
2. making a new architecture or methodology decision;
3. deleting persistent data;
4. rewriting Git history;
5. force-push;
6. destructive reset/clean;
7. direct modification of `main`;
8. merge to `main`;
9. release/deployment/publication;
10. changing branch protection, repository rules, permissions, secrets, or credentials;
11. weakening a security or validation control;
12. bypassing signing, repository policy, or platform approval gates;
13. incurring external cost or contractual commitment;
14. choosing among materially different unresolved design alternatives;
15. performing another materially irreversible operation.

Never attempt to bypass ChatGPT/Codex system approval prompts. Minimize them by grouping safe work where possible.

---

## 4. Scope discipline

Before editing, establish:

- repository identity,
- current branch,
- current HEAD SHA,
- authorized objective,
- Stage/remediation/review scope,
- relevant baseline/base SHA where applicable,
- acceptance criteria.

Do not opportunistically refactor unrelated code.

If an unrelated defect is found:

- record it,
- classify it,
- keep it out of the current patch unless required for correctness or safety.

Do not silently expand scope.

---

## 5. Repository state is authoritative

Never rely on remembered repository state, stale chat summaries, assumed file contents, assumed CI status, or another agent's report.

Inspect the actual repository.

For material work, bind conclusions to:

- repository,
- branch,
- exact commit SHA,
- relevant PR,
- relevant CI/workflow run where applicable.

A branch name alone is not sufficient evidence.

---

## 6. Exact-SHA policy

Any validation or review of a candidate must identify the exact commit SHA.

Prefer statements such as:

`commit <SHA> passed the required checks`

not:

`the branch is green`.

If HEAD changes after review, the previous review does not automatically apply to the new HEAD.

Re-review the new exact SHA or validate the delta explicitly.

Never transfer PASS/VALIDATED status from one SHA to another without evidence.

---

## 7. Git safety

Treat `main` as protected even when GitHub settings do not technically enforce protection.

Do not:

- commit directly to `main`,
- force-push `main`,
- rewrite `main`,
- bypass required review/check/signing rules,
- silently discard unrelated local changes.

Before editing:

- inspect branch,
- inspect working tree,
- preserve unrelated user work.

Commands such as `git reset --hard`, `git clean -fd`, `git push --force`, branch deletion, or history rewriting require explicit authorization.

Prefer non-destructive alternatives.

---

## 8. Change policy

Use the smallest durable patch that resolves the identified root cause.

Preferred sequence:

1. reproduce;
2. identify invariant and root cause;
3. implement the minimal correction;
4. add focused regression coverage;
5. run focused validation;
6. run affected broader regression tests;
7. inspect the final diff;
8. capture evidence;
9. record the new exact SHA.

Do not weaken tests to obtain green CI.

Do not redefine expected behavior merely to match defective implementation unless explicitly authorized.

---

## 9. Testing and determinism

Every meaningful behavioral change requires appropriate verification.

Default hierarchy:

1. focused test;
2. regression test for the defect;
3. affected module/service tests;
4. repository-level checks when appropriate;
5. CI validation when required.

A behavioral fix without regression coverage requires explicit justification.

Prefer deterministic tests:

- controlled clocks,
- explicit fixtures,
- seeded randomness,
- isolated state,
- reproducible inputs,
- no arbitrary sleeps when a deterministic synchronization mechanism is available.

Any intentional nondeterminism must be bounded and documented.

---

## 10. Concurrency, transactions, replay

For concurrent or retryable operations, consider:

- races,
- duplicate execution,
- idempotency,
- stale writes,
- optimistic concurrency / CAS,
- transaction boundaries,
- ordering,
- retry behavior,
- partial failures,
- audit/outbox consistency.

Do not claim concurrency safety without targeted evidence.

Logical multi-step state changes should be atomic where feasible. Otherwise define compensating behavior and recoverable failure semantics.

Critical workflows should be replayable where architecture requires it.

---

## 11. Authorization and security

Authorization must be enforced at the authoritative execution boundary, not only in UI or prompt logic.

Fail closed when authorization is ambiguous.

Never:

- expose secrets,
- commit credentials,
- print tokens unnecessarily,
- weaken authentication/TLS/security checks for convenience,
- disable security controls merely to pass CI,
- bypass repository policy.

If a secret appears in tracked content, treat it as a potential security incident and avoid reproducing it.

---

## 12. Provenance and domain traceability

Preserve traceability for important derived information.

Where applicable, maintain links across:

Source -> Extraction -> Fact -> Evidence -> Legal Rule/Authority -> Claim/Defence -> Argument -> Decision -> Filing/Document -> Validation

Moving or re-associating a fact/evidence object must not silently destroy original provenance.

Do not conflate:

- allegation,
- extracted statement,
- fact,
- evidence,
- inference,
- legal conclusion,
- decision.

Machine confidence is not legal truth.

---

## 13. Legal-authority controls

Legal-source handling must account for, where applicable:

- jurisdiction,
- authority identity,
- source version,
- effective date,
- validity period,
- territorial scope,
- procedural applicability,
- supersession,
- retrieval provenance,
- citation.

A source is not applicable merely because it exists.

If jurisdictional or temporal applicability cannot be established, fail closed or require a human decision according to the domain contract.

Keep the core jurisdiction-neutral where feasible; isolate jurisdiction-specific rules in explicit authority/rule/adapter/policy layers.

---

## 14. Human decision boundaries

Where architecture reserves a decision for HUMAN, automation must not silently cross that boundary.

Agents may prepare, validate, compare, summarize, and surface options where authorized.

Agents must not fabricate or record a human decision that did not occur.

Semantic or legal judgments explicitly designated HUMAN remain HUMAN-controlled.

---

## 15. Schemas, contracts, migrations, compatibility

Treat schemas and public contracts as compatibility boundaries.

Changes require:

- explicit intent,
- compatibility analysis,
- tests,
- validation,
- versioning/migration where applicable.

Do not silently reinterpret existing fields.

Data migrations must be deterministic where feasible, testable, recoverable/restart-safe where practical, and must validate preconditions.

Consider:

- backward compatibility,
- stored-data compatibility,
- API/schema compatibility,
- replay compatibility,
- audit compatibility.

Breaking changes must be explicit.

---

## 16. CI and workflow security

CI success is necessary when required, but not automatically sufficient.

Verify:

- the workflow ran for the intended SHA,
- required jobs actually ran,
- required gates were not skipped,
- expected configuration was used.

Treat workflow definitions as security-sensitive.

Review workflow changes for:

- token permissions,
- trusted vs untrusted checkout,
- `pull_request` vs `pull_request_target`,
- secret exposure,
- command injection,
- artifact trust,
- branch trust,
- dependency/action pinning.

Do not infer candidate validity from an unrelated workflow run.

---

## 17. Artifact integrity and auditability

Where artifacts act as evidence, use hashes where appropriate; prefer SHA-256 unless repository policy defines another standard.

Do not infer file equality from names.

Material operations should be reconstructable after the fact where architecture requires it.

Useful evidence can include:

- actor,
- operation,
- timestamp,
- object/version,
- source,
- correlation/execution ID,
- exact SHA,
- validation result,
- artifact hash.

Historical evidence must not be silently mutated.

---

## 18. Generated documents

Generated documents are product artifacts and must be validated.

Never fabricate:

- facts,
- dates,
- evidence,
- quotations,
- case numbers,
- procedural events,
- legal authorities,
- citations.

Unknown information must remain unknown.

Do not add visible document labels or watermarks such as:

- REVIEW_REQUIRED,
- REVIEWED,
- AI-generated,
- Generated by LUKART,
- visible provenance banners,

unless the user explicitly authorizes them.

Internal provenance belongs in structured metadata/audit/evidence systems, not automatically on the visible final document.

---

## 19. Dependencies and external sources

Before adding a production dependency, evaluate necessity, maintenance quality, security posture, license, compatibility, and operational impact.

Do not add a large framework for trivial functionality.

External data/tool/agent output is untrusted until validated.

Prefer authoritative primary legal/technical sources where available and preserve retrieval context when required.

---

## 20. Review policy

Review the actual diff, not only the author's summary.

Check as applicable:

- correctness,
- regression risk,
- boundary conditions,
- authorization,
- security,
- data integrity,
- provenance,
- failure behavior,
- tests,
- concurrency,
- compatibility,
- scope creep.

Independent review must remain independent.

Implementation-agent statements are evidence candidates, not independent verification.

For high-impact code, perform adversarial review against malformed input, stale versions, wrong jurisdiction, expired authority, unauthorized access, replay, duplicate execution, races, partial transaction failure, corrupted provenance, schema mismatch, time boundaries, and unexpected ordering.

---

## 21. Merge gate

Do not merge merely because local tests pass.

Typical merge readiness requires:

- authorized scope complete,
- final diff inspected,
- focused tests PASS,
- regression tests PASS,
- required CI PASS for the exact candidate SHA,
- no unresolved P0/P1 blocker,
- exact candidate SHA recorded,
- independent review completed where required,
- repository policy satisfied,
- signing requirements satisfied where required.

Merge to `main` itself requires explicit human authorization unless explicitly delegated.

Never bypass required commit signatures or repository policy.

---

## 22. Post-merge Definition of Done

Merge is not automatically DONE.

Where applicable, verify:

- `main` contains the intended change,
- required post-merge CI ran on merged state,
- post-merge checks passed,
- no integration regression appeared,
- release artifacts correspond to the correct SHA where relevant.

Definition of Done = implementation + validation + integration evidence.

---

## 23. Repository-specific verification

This is a Python 3.11+ repository.

Inspect the current README and current Stage documentation before choosing the authoritative verifier because Stage-specific commands evolve.

Baseline repository checks currently include commands such as:

`python -m unittest discover -v`

and Stage-specific `scripts/verify_stage*.py` runners.

Do not assume an older Stage runner validates a newer Stage.

Every SKIP that repository policy defines as missing evidence must remain FAIL.

---

## 24. Living standard

Methodological changes are hypotheses until validated.

For a material methodology change:

1. define decision need;
2. define the problem;
3. define the hypothesis;
4. define measurement;
5. validate incrementally;
6. collect evidence;
7. decide whether to adopt.

Do not promote sophistication into standard without evidence.

---

## 25. Hierarchical AGENTS.md policy

Current default: one strong root `AGENTS.md`.

Introduce nested instruction files only when repository scale or domain specialization creates a concrete need.

Potential future locations include:

- `tests/AGENTS.md`
- `lukart_work/domain/AGENTS.md`
- `lukart_work/validation/AGENTS.md`

Use `AGENTS.override.md` only when a local scope truly needs to replace, rather than merely extend, parent instructions.

Avoid premature fragmentation.

Keep the root policy concise enough to preserve instruction-budget headroom for future nested rules.

---

## 26. Required end-of-task report

For material repository changes, report:

- STATUS,
- repository,
- branch,
- baseline/base SHA when relevant,
- final HEAD SHA,
- files changed,
- tests executed,
- test results,
- CI result if applicable,
- findings,
- unresolved blockers,
- whether `main` changed,
- whether merge occurred.

If any item was not verified, write `NOT VERIFIED`.

---

## 27. Stop conditions

Stop the affected operation and surface the issue when:

- repository identity is uncertain,
- target branch is uncertain,
- authorized scope cannot be determined,
- required source data is missing,
- repository state contradicts task assumptions,
- a required security control fails,
- provenance is lost,
- exact candidate SHA cannot be established,
- required CI belongs to another SHA,
- policy compliance cannot be verified,
- required human decision boundary is reached,
- merge would require bypassing repository policy.

---

## 28. Final operating rule

When speed conflicts with integrity, choose integrity.

When evidence is insufficient, collect evidence.

When an irreversible action is not clearly authorized, do not perform it.

When an authorized operation is routine, safe, reversible, and required for the task, perform it without unnecessary confirmation.

BUILD.
VERIFY.
PROVE.
THEN CONCLUDE.
