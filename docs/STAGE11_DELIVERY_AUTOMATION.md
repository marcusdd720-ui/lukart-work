# Stage 11 Delivery Automation Policy

Status: TRUSTED BOOTSTRAP POLICY
Scope: `marcusdd720-ui/lukart-work`, Stage 11 only.
Target branch: `main`.
Stage branches: `codex/stage11-*`.
Work staging branches: `work/stage11-*`.

## Objective

Reduce manual stops around promotion, exact-SHA candidate assurance, commit verification,
merge, post-merge verification and branch cleanup without weakening fail-closed,
independent-review, provenance or repository-integrity requirements.

## Non-authority

This policy does not authorize force-push to `main`, direct writes to `main`, bypassing
failed checks, rewriting historical evidence, changing repository protection, weakening
tests, exposing secrets, or starting Stage 12.

The delivery-control workflow is trusted procedure code. Stage 11 product promotion is
not allowed to modify that procedure, this policy, or any workflow under
`.github/workflows/`.

## Exact-SHA candidate assurance contract

The candidate SHA is a first-class identity and must be validated directly.

1. Promotion creates a GitHub-verified commit on a `codex/stage11-*` branch.
2. The control does **not** rely on the resulting `GITHUB_TOKEN` branch update to
   recursively trigger CI.
3. After verifying signature and source-tree identity, the trusted control explicitly
   dispatches both required assurance workflows with:
   - `ref=<codex/stage11-* branch>`;
   - `candidate_sha=<exact promoted SHA>`.
4. Each dispatched workflow:
   - requires a lowercase 40-hex `candidate_sha`;
   - requires the dispatch event SHA to equal `candidate_sha`;
   - checks out `candidate_sha` explicitly;
   - asserts `git rev-parse HEAD == candidate_sha` before running assurance.
5. Pull-request runs also check out the PR head SHA explicitly so their tested source is
   not silently replaced by GitHub's synthetic PR merge commit.
6. The authoritative pre-merge Stage 11 gate is the pair of successful check-runs bound
   to the exact candidate SHA:
   - `validation`;
   - `stage11-rendering`.
7. Missing, stale, nonterminal, failed, or differently bound evidence blocks merge.

This design deliberately uses `workflow_dispatch`, which GitHub allows to create a new
workflow run even when the dispatch originates from a workflow authenticated with
`GITHUB_TOKEN`. No PAT or long-lived GitHub App credential is required for this path.

## Promotion transaction contract

Promotion is fail-closed.

1. The work branch must be strictly ahead of the supplied base and not behind it.
2. Trusted procedure/workflow paths cannot be promoted.
3. The promoted GitHub commit must be `verified=true`.
4. The promoted commit tree must equal the exact source tree.
5. Both exact-SHA assurance dispatches must be accepted before the work staging branch is
   moved to the verified promoted commit.
6. If verification or dispatch setup fails, the target branch is rolled back to the
   supplied base (and removed when it was created by that failed attempt).
7. No failure may be converted into implicit PASS.

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
4. Required post-merge checks are terminal SUCCESS on the exact resulting `main` SHA.
5. Tree/content identity is consistent with the reviewed candidate where the merge is
   content-only.
6. A post-merge verification receipt records exact identities and known limitations.

Push-triggered post-merge workflows use the resulting `main` commit SHA directly.

## Cleanup contract

The Stage 11 branch may be deleted only after post-merge PASS and only when:

1. the branch still points to the reviewed candidate SHA;
2. that SHA is an ancestor of the verified resulting `main`;
3. the merged PR is CLOSED/MERGED;
4. no newer commit appeared on the branch;
5. cleanup itself is idempotent and fail-closed.

## Standing authorization for Stage 11

Within this exact Stage 11 scope, guarded merge and guarded branch cleanup may proceed
automatically after all machine-verifiable gates and the exact-SHA independent review
PASS. No additional human confirmation is required for those two bounded actions.

Any deviation from this policy requires a new decision.

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

Mutable names such as `latest` or branch names are never sufficient evidence by
themselves.

## Long-term design rule

Event delivery is orchestration, not evidence.

A workflow being triggered does not prove what source it tested. Every critical assurance
path must bind the tested source to an immutable SHA and assert that identity inside the
runner before executing candidate code.

Exact identity first. Trigger second. Evidence last.
