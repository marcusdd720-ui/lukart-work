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
   - `candidate_sha=<exact promoted SHA>`;
   - a unique 128-bit `dispatch_token` used only to correlate the concrete GitHub
     workflow run created by that dispatch.
4. Each dispatched workflow:
   - requires a lowercase 40-hex `candidate_sha`;
   - exposes the correlation token in the single canonical deterministic format
     `stage11-dispatch-<dispatch_token>` (`run-name: stage11-dispatch-${{ inputs.dispatch_token || github.sha }}`);
   - requires the dispatch event SHA to equal `candidate_sha`;
   - checks out `candidate_sha` explicitly;
   - asserts `git rev-parse HEAD == candidate_sha` before running assurance.
   The control does not treat HTTP acceptance of `workflow_dispatch` as evidence.
   Before completing promotion setup it must observe exactly one newly materialized
   correlated run for each required workflow and verify its workflow path, event,
   branch and `head_sha == candidate_sha`.
5. Pull-request runs also check out the PR head SHA explicitly so their tested source is
   not silently replaced by GitHub's synthetic PR merge commit.
6. The authoritative pre-merge Stage 11 gate is the pair of successful checks bound
   to the exact candidate SHA:
   - `validation` from `.github/workflows/stage02.yml`;
   - `stage11-rendering` from `.github/workflows/stage11-assurance.yml`.
7. Gate verification checks both the trusted check producer (`github-actions`) and the
   workflow-run provenance. Pre-merge evidence must come from `workflow_dispatch` runs
   whose workflow path and `head_sha` match the expected candidate exactly.
8. Missing, stale, nonterminal, failed, untrusted, wrong-event, wrong-workflow, or
   differently bound evidence blocks merge.

This design deliberately uses `workflow_dispatch`, which GitHub allows to create a new
workflow run even when the dispatch originates from a workflow authenticated with
`GITHUB_TOKEN`. No PAT or long-lived GitHub App credential is required for this path.

### Stage 11 test presence and bounded procedure bootstrap

Missing `tests/test_stage11.py` fails assurance, including ordinary `codex/stage11-*`
branches. When present, the suite must execute at least one test with no failures,
errors or skips. Delivery-control tests cannot substitute for rendering tests.

The sole pre-merge procedure-only exception is the existing PR #17 branch
`codex/stage11-procedure-bootstrap-pr15`. It requires ancestor base
`f9b55b1562bb9b3bf2d1db1a5cdb84690619082f` and a nonempty complete diff from that
base restricted to the eight `PROCEDURE_BOOTSTRAP_PATHS` in the control script.
Those are the three existing Stage 10/11 workflow files, this policy, the control
script, its guard tests, and the two existing generated evidence reports.
Any product/test deletion or other path outside that list blocks the exception.
The workflow reports `PROCEDURE_ONLY_BOOTSTRAP`; this is not rendering validation.
The exception does not apply to `main` or similarly named branches. Post-merge
rendering assurance without product tests remains blocked; this pre-merge bootstrap
does not award Stage 11 completion or authorize a merge.

## Promotion transaction contract

Promotion is fail-closed.

1. The work branch must be strictly ahead of the supplied base and not behind it.
2. Trusted procedure/workflow paths cannot be promoted.
3. The promoted GitHub commit must be `verified=true`.
4. The promoted commit tree must equal the exact source tree.
5. Both exact-SHA assurance dispatches must be correlated to concrete newly created
   GitHub Actions runs whose `head_sha` equals the promoted SHA. The target ref is
   rechecked before each dispatch, after each correlated run is observed, and after
   the pair is bound.
6. Promotion never rewrites the `work/stage11-*` source ref. The exact source SHA is
   immutable input evidence; a concurrent source advance is preserved rather than
   force-reset to the promoted SHA.
7. If verification or dispatch binding fails, fail closed and preserve the target ref
   and failed promoted commit as evidence. Do not reset or delete the target, including
   a branch created by this attempt. REST ref PATCH/DELETE do not supply expected-head
   compare-and-swap; a preceding HEAD read cannot prevent a concurrent lost update.
   Recovery requires a separately authorized and concurrency-safe operation.
8. Promotion emits `STAGE11_PROMOTION: DISPATCH_BOUND`, not a PASS receipt. This means
   only that the verified candidate and exact-SHA dispatch runs were bound while the
   target was observed at the candidate SHA. Candidate assurance, independent review
   and merge gates remain separate and mandatory.
9. No failure may be converted into implicit PASS.

## Guarded merge contract

A Stage 11 merge is eligible only when all of the following are true:

1. PR targets `main` and its head branch matches `codex/stage11-*`.
2. PR is open and not draft.
3. Current PR head SHA equals the explicitly supplied reviewed SHA.
4. Current base SHA equals the explicitly supplied expected base SHA.
5. The reviewed head commit is GitHub `verified=true`.
6. Required Stage 11 checks for that exact head SHA are terminal SUCCESS.
7. An authenticated independent review receipt binds that exact head and base SHA,
   with `p0=0` and `p1=0` as described below.
8. Merge uses merge-commit semantics and binds the expected head SHA.
9. Any mismatch, stale state, missing evidence or unknown state blocks the merge.

### Independent review receipt authentication

The existing repository-owner HUMAN boundary attests a separately performed independent
review. The merge control loads repository owner identity from GitHub's repository API
and comment identity from its issue-comments API. Both numeric user ID and exact login
must match, both identities must be `User`, association must be `OWNER`, and an
app-authored receipt is rejected. Identity declarations inside the body carry no trust.
An organization owner, missing metadata or unavailable identity fails closed.

The complete body must have this exact header and exactly these five unique fields
(field order may vary; values may not). Unknown, duplicate or malformed fields,
additional prose, nonzero findings and substring matches are rejected:

```text
STAGE11_INDEPENDENT_REVIEW: PASS
sha=<exact 40-character lowercase candidate SHA>
base_sha=<exact 40-character lowercase base SHA>
p0=0
p1=0
merge=NOT_PERFORMED
```

Authentication proves who attested the result; it does not prove that an independent
review occurred. The owner must attest only an actual separate review. Builder
preflight is not independent review and must never be relabeled as this receipt.
Historical receipts for other heads/bases do not transfer. This remediation does not
create a review receipt or authorize merge.

### P1 remediation evidence lineage

Failed candidate `02d4209a80cde62144377d1f573b7b076b1b2026` remains immutable history.
Its independent review was BLOCKED (`p0=0`, `p1=3`, merge not performed), as supplied
in the explicit remediation authorization. Root causes were destructive compensation
without CAS, optional rendering-test execution, and unauthenticated substring matching.

Candidate `48b8b67bf6174f991de49e1bc7a70d433a6adeec` repaired those three findings, but
Case 1 adversarial review identified two additional P1 concurrency windows: mutable
target movement during the two-dispatch binding window could produce premature promotion
completion, and the final source `force=true` reset could overwrite a newer concurrent
source update. This remediation removes source-ref mutation entirely, correlates each
dispatch to its concrete exact-SHA run, adds target rechecks across the binding window,
and replaces promotion PASS with a narrower `DISPATCH_BOUND` receipt.

Fresh exact-SHA CI and a new independent Case 1 review are required; no PASS transfers
from either failed candidate.

## Post-merge contract

After merge, Stage 11 remains open until:

1. `main` contains the resulting merge commit.
2. The merge commit is GitHub verified.
3. The merge parents bind the pre-merge base and reviewed candidate.
4. Required post-merge checks are terminal SUCCESS on the exact resulting `main` SHA.
5. Post-merge workflow provenance is verified against the expected workflow paths and the
   `push` event for that exact `main` SHA.
6. Tree/content identity is consistent with the reviewed candidate where the merge is
   content-only.
7. A post-merge verification receipt records exact identities and known limitations.

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
