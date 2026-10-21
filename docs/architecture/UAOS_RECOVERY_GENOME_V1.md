# UAOS Recovery Genome / Incident Learning Fabric v1

Status: DESIGN CONTRACT — NOT YET RUNTIME CERTIFIED

## Purpose

Prevent repeated execution failures across LUKART WORK, LUKART ROS, UAOS, BUILD-vs-ADOPT and future products by converting each real incident into reusable recovery knowledge.

This contract extends Execution Truth. It does not replace task authority, verification, signing, promotion or HUMAN gates.

## Core rule

A recoverable technical failure must never terminate as silent IDLE while qualified work remains.

Canonical loop:

FAILURE -> CLASSIFY -> MATCH KNOWN INCIDENT -> BOUNDED REMEDIATION -> VERIFY -> NEW CANDIDATE IDENTITY -> EXACT-SHA EVIDENCE -> LEARN

Only these may terminate execution:

- CLOSED
- HUMAN_REQUIRED
- QUARANTINED_FATAL after bounded recovery is exhausted and evidence proves no safe technical path remains.

## 1. Incident Fingerprint

Every material failure creates a normalized fingerprint independent of provider wording:

- project_id
- task_kind
- execution_phase
- failing invariant/test/check
- failure_class: PRODUCT | INFRASTRUCTURE | EVIDENCE | AUTHORITY | HUMAN
- normalized error signature
- relevant path set
- exact candidate SHA
- environment identity
- provider/executor identity
- reproducibility status

Secrets, raw credentials and private case content are excluded.

Fingerprint IDs are content-addressed.

## 2. Recovery Genome Record

A successful recovery emits an append-only record:

- incident_fingerprint_id
- root_cause
- remediation_class
- exact changes or operational actions
- preconditions
- forbidden shortcuts
- focused tests
- regression tests
- verification evidence
- resulting candidate SHA
- outcome
- confidence
- blast radius
- recurrence counter
- supersedes / superseded_by

No recovery is marked LEARNED until independent verification passes.

## 3. Lesson -> Guardrail

Every accepted recovery must produce at least one guardrail:

- deterministic test,
- admission rule,
- state invariant,
- CI assertion,
- scheduler rule,
- provider-routing rule,
- or explicit HUMAN gate.

A documentation-only lesson without an enforceable guardrail is KNOWLEDGE_ONLY, not CERTIFIED_RECOVERY.

## 4. Cross-Agent Learning

Before a builder or repair agent invents a new fix, the supervisor searches the Recovery Genome for:

1. exact fingerprint match,
2. same failing invariant,
3. same phase + failure class,
4. semantically similar incident.

Reuse is permitted only when preconditions match.

The applying agent must emit:

- reused_recovery_id,
- match_reason,
- deviations,
- expected guardrails,
- verification plan.

A prior PASS is never transferred between SHAs. Only the remediation method may be reused.

## 5. Agent separation

- SUPERVISOR: identifies incident and selects candidate recovery.
- REPAIR AGENT: performs bounded remediation.
- BUILDER: performs product change only when required.
- VERIFIER: independently validates result.
- LEARNING CURATOR: promotes a verified recovery into the Genome.
- PROMOTER: remains separate and requires existing authority.

Builder != verifier != promoter.

An agent may learn from another agent's evidence, but may not inherit its authority.

## 6. Stale-state anti-deadlock

Project state must be reconciled against external truth before quarantine or idle decisions.

Required comparison:

- ledger candidate SHA
- repository/PR live head SHA
- active execution SHA
- GitHub exact-SHA CI state
- latest independently verified candidate

If repository live head is newer than the task's quarantined SHA, the old quarantine is STALE_EVIDENCE and cannot block the newer candidate.

The supervisor must create a reconciliation event and re-evaluate the live head instead of retrying the obsolete SHA.

## 7. Evidence drift protocol

Generated evidence drift is classified separately from product failure.

When:

- focused tests PASS,
- full regression PASS,
- package verification PASS,
- but reproducibility fails because generated manifests/evidence differ,

the system must:

1. capture generated artifact from exact-SHA CI,
2. compare only deterministic generated outputs,
3. reject unexplained product-file changes,
4. synchronize generated evidence only from the exact tested tree,
5. create a new candidate SHA,
6. rerun exact-SHA CI.

Never manually guess generated hashes.

## 8. Provider exhaustion

Quota/rate-limit/provider outage is INFRASTRUCTURE, not PRODUCT.

Fallback order is policy-driven and bounded.

Paid fallback remains blocked unless explicitly authorized.

When all allowed executors are unavailable, deterministic work, CI inspection, evidence reconciliation and HUMAN-independent maintenance continue where possible.

## 9. Recovery confidence

Suggested levels:

- R0 OBSERVED — incident recorded only.
- R1 REPRODUCED — deterministic reproduction exists.
- R2 REPAIRED — bounded fix passes focused checks.
- R3 VERIFIED — independent verification passes.
- R4 REUSABLE — second independent incident successfully uses the same recovery.
- R5 CERTIFIED — repeated use plus chaos/restart tests show stable behavior.

Only R3+ may be auto-suggested.
Only R4+ may be auto-applied without a fresh design review, subject to blast-radius policy.

## 10. Anti-learning protections

The system must never learn:

- test weakening,
- disabling checks,
- deleting evidence to obtain PASS,
- changing requirements after failure,
- broadening authority,
- paid fallback without approval,
- provider-specific lock-in as product truth,
- manual state edits that bypass the ledger.

Such attempts are recorded as NEGATIVE_LESSONS.

## 11. Current incident seed: Generator Pism

Incident family: GENERATED_EVIDENCE_DRIFT / STALE_EXECUTION_STATE.

Observed sequence:

- obsolete candidate SHA remained quarantined in UAOS,
- repository PR head advanced,
- product regression and package verification passed on the newer head,
- generated manifest reproducibility failed because reports/manifest.sha256.json lagged the exact tested tree.

Required guardrails:

- live-head reconciliation before quarantine remains authoritative,
- candidate identity is exact SHA,
- generated manifest comes only from exact-SHA CI output,
- stale quarantine cannot block a newer head,
- successful manifest repair still requires fresh exact-SHA CI and independent verification.

## 12. Definition of Done

Incident Learning Fabric v1 is not IMPLEMENTED merely because this document exists.

Runtime implementation requires:

- durable incident ledger,
- deterministic fingerprinting,
- recovery lookup,
- bounded auto-application,
- stale-SHA reconciliation,
- guardrail enforcement,
- negative-learning rules,
- independent verifier integration,
- restart/replay tests,
- cross-project test fixture,
- evidence that one verified recovery is reused successfully in a second incident.

Planned != Implemented != Validated != Certified.
