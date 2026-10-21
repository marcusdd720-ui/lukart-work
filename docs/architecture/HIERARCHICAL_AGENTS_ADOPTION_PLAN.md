# Hierarchical AGENTS.md — Adoption Plan
Date: 2026-10-05
Source: docs/IDEAS_BACKLOG.md — "Hierarchical AGENTS.md architecture"
Status: READY_FOR_BOUNDED_PILOT_AFTER_CURRENT_P0
Priority: P1 governance/agent precision

## Live-state justification

Current repository evidence:
- approximately 355 tracked tree entries/files in the inspected main tree;
- distinct subtrees already exist for domain, model runtime, rendering, validation and tests;
- only one repository-wide AGENTS.md is currently present;
- root AGENTS.md already explicitly defines nested AGENTS.md / AGENTS.override.md precedence semantics.

Therefore the original trigger "repository growth / increasing domain specialization" is now materially present enough to justify a bounded pilot.
This is not authorization for full fragmentation.

## Non-negotiable root authority

Root AGENTS.md remains repository-wide governance.
Nested files may specialize local execution but must never weaken:
- evidence-before-conclusion;
- exact-SHA policy;
- fail-closed semantics;
- authorization/human gates;
- security/privacy;
- provenance;
- Planned != Implemented != Validated != Certified;
- protected-main/merge/release rules.

## Recommended pilot order

Do not create every possible nested file at once.

Pilot only two high-signal boundaries after the current Generator/PB01 P0 gate is closed:

1. `lukart_work/validation/AGENTS.md`
   - deterministic validation;
   - no weakening tests/thresholds;
   - validation projection semantics;
   - exact artifact/provenance binding.

2. `tests/AGENTS.md`
   - deterministic fixtures;
   - focused test → regression discipline;
   - no arbitrary sleeps where deterministic synchronization exists;
   - synthetic/private-data boundary;
   - evidence expectations.

Only if those prove useful, evaluate:
- `lukart_work/domain/AGENTS.md`
- `lukart_work/model_runtime/AGENTS.md`
- `lukart_work/rendering/AGENTS.md`

Use `AGENTS.override.md` only when replacement rather than extension is genuinely required.

## Acceptance gate for the pilot

Before enabling the hierarchy as an operational dependency:
1. document exact instruction-discovery/precedence behavior;
2. add fixtures/tests or an audit script proving which AGENTS file applies to representative paths;
3. verify root invariants cannot be silently weakened;
4. measure root instruction-size reduction / ambiguity reduction;
5. test at least one builder and one independent reviewer session;
6. record regressions or conflicts;
7. decide ADOPT / MODIFY / REJECT.

## Rollback

Rollback must be trivial:
- remove nested pilot files;
- root AGENTS.md remains sufficient;
- no Product schema or authority depends on nested instructions.

## Relation to LSAF

Hierarchical AGENTS.md is not the LSAF authority model.
It is an executor-facing instruction-discovery optimization.

LSAF stable contracts, Evidence Ledger, capability routing and authority boundaries must remain valid even if Codex-style hierarchical AGENTS.md disappears or changes in the future.
