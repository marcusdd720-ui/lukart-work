# Stage 11 Delivery Automation Policy

Status: BOOTSTRAP POLICY
Scope: `marcusdd720-ui/lukart-work`, Stage 11 only.
Target branch: `main`.
Stage branches: `codex/stage11-*`.

## Objective

Reduce manual stops around commit verification, merge, post-merge verification and branch cleanup
without weakening exact-SHA, fail-closed or independent-review requirements.

## Non-authority

This policy does not authorize force-push, direct writes to `main`, bypassing failed checks,
rewriting historical evidence, changing repository protection, weakening tests, exposing secrets,
or starting Stage 12.

## Guarded merge contract

A Stage 11 merge is eligible only when all of the following are true:

1. PR targets `main` and its head branch matches `codex/stage11-*`.
2. PR is open and not draft.
3. Current PR head SHA equals the explicitly supplied reviewed SHA.
4. Current base SHA equals the explicitly supplied expected base SHA.
5. The reviewed head commit is GitHub `verified=true`.
6. Required Stage 11 checks for that exact head SHA are terminal SUCCESS.
7. An exact-SHA independent review result is recorded for that same head SHA.
8. Merge uses merge-commit semantics and binds the expected head SHA.
9. Any mismatch, stale state, missing evidence or unknown state blocks the merge.

## Post-merge contract

After merge, Stage 11 remains open until:

1. `main` contains the resulting merge commit.
2. The merge commit is GitHub verified.
3. The merge parents bind the pre-merge base and reviewed candidate.
4. Required post-merge checks are terminal SUCCESS on the exact resulting main SHA.
5. Tree/content identity is consistent with the reviewed candidate where the merge is content-only.
6. A post-merge verification receipt records exact identities and known limitations.

## Cleanup contract

The Stage 11 branch may be deleted only after post-merge PASS and only when:

1. the branch still points to the reviewed candidate SHA;
2. that SHA is an ancestor of the verified resulting `main`;
3. the merged PR is CLOSED/MERGED;
4. no newer commit appeared on the branch;
5. cleanup itself is idempotent and fail-closed.

## Standing authorization for Stage 11

Within this exact Stage 11 scope, guarded merge and guarded branch cleanup may proceed automatically
after all machine-verifiable gates and the exact-SHA independent review PASS. No additional human
confirmation is required for those two bounded actions. Any deviation from this policy requires a
new decision.

## Evidence identities

Every PASS must bind, where applicable:

- repository SHA;
- source tree identity;
- expected base SHA;
- artifact/manifest digests;
- policy identity;
- verification-procedure identity;
- required check identities;
- resulting merge SHA;
- resulting main SHA.

Mutable names such as `latest` or branch names are never sufficient evidence by themselves.
