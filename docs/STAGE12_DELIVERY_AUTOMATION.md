# Stage 12 Trusted Promotion / Signing Procedure

Status: TRUSTED PROCEDURE CANDIDATE
Scope: `marcusdd720-ui/lukart-work`, Stage 12 only.
Authorized Stage 12 product branch for this procedure: `codex/stage12-audit-provenance`.
Procedure-remediation branch: `codex/stage12-trusted-promotion-procedure` (never a promotion target).
Command namespace: `/stage12`.
Receipt namespace: `STAGE12_*`.

## Objective

Provide the smallest fail-closed procedure needed to append a GitHub-signed, tree-preserving commit to an existing Stage 12 PR head without modifying Stage 12 product files, `main`, Stage 11 policy, or Stage 11 receipts.

This procedure is factory/delivery infrastructure. It is not Stage 12 product code.

## Authority and non-authority

This policy authorizes only the Stage 12 tree-preserving signed-candidate promotion described below after this procedure itself has been independently reviewed and installed through a separately authorized path.

It does not authorize:

- `/stage11` command reuse;
- Stage 11 receipt reuse;
- Stage 11 independent-review receipt reuse;
- force push or destructive ref reset;
- direct or indirect mutation of `main`;
- PR merge;
- repository-protection changes;
- product file changes during signing;
- acceptance of unsigned output;
- acceptance of an output whose parent or tree differs from the required values.

Existing `docs/STAGE11_DELIVERY_AUTOMATION.md`, `scripts/stage11_delivery_control.py`, `.github/workflows/stage11-control.yml`, and their semantics remain unchanged.

## Promotion contract

Invocation:

```text
/stage12 promote source_sha=<sha> source_tree=<tree> base_sha=<sha>
```

The control derives the target branch from the pull request that received the command.

Preconditions:

1. caller is the repository owner;
2. the comment belongs to an open, non-draft, unmerged PR;
3. PR base is `main`;
4. PR head branch is exactly `codex/stage12-audit-provenance`; the procedure-remediation branch is not eligible;
5. current PR head equals `source_sha`;
6. current branch ref equals `source_sha`;
7. current `main` and PR base SHA equal `base_sha`;
8. the source commit tree equals `source_tree`;
9. all SHA inputs are exact lowercase 40-hex values.

Mutation:

- use GitHub GraphQL `createCommitOnBranch`;
- target only the existing Stage 12 PR head branch;
- set `expectedHeadOid=source_sha`;
- provide no file changes, creating a zero-diff child commit;
- never use REST ref PATCH, force update, reset, delete, or the PR merge endpoint.

Required postconditions:

- new commit has exactly one parent and it equals `source_sha`;
- new commit tree equals `source_tree`;
- GitHub commit verification reports `verified=true`;
- PR head and target branch ref both equal the new SHA;
- `main` still equals `base_sha`;
- PR remains open and unmerged.

Any stale expected head must fail before branch mutation. Any failed postcondition is BLOCKED and the resulting state is preserved as evidence; there is no destructive compensation.

## Exact-SHA assurance dispatch

Because a `GITHUB_TOKEN` branch write does not recursively create ordinary push runs, successful promotion explicitly dispatches `.github/workflows/stage12-assurance.yml` with:

- `ref=<exact Stage 12 PR head branch>`;
- `candidate_sha=<new exact SHA>`;
- a unique 128-bit hexadecimal `dispatch_token`.

The control records the pre-dispatch run IDs, dispatches once, then requires exactly one newly materialized run whose:

- display title is `stage12-dispatch-<dispatch_token>`;
- event is `workflow_dispatch`;
- workflow path is `.github/workflows/stage12-assurance.yml`;
- head SHA equals the new candidate SHA;
- head branch equals the Stage 12 PR branch.

The branch ref is re-read before dispatch and after binding the run.

The promotion receipt is intentionally narrow:

```text
STAGE12_PROMOTION: DISPATCH_BOUND
source_sha=<old SHA>
new_sha=<new SHA>
parent_sha=<old SHA>
source_tree=<tree SHA>
new_tree=<tree SHA>
base_sha=<main/base SHA>
verification=VERIFIED
assurance_run_id=<run id>
main_changed=NO
merge=NOT_PERFORMED
```

This receipt does not claim assurance PASS, independent review PASS, merge authority, or Stage 12 closure.

## Stage 12 assurance workflow

`.github/workflows/stage12-assurance.yml` binds the tested source to an exact SHA for push, pull-request, and workflow-dispatch events.

For the Stage 12 signed candidate it runs, at minimum:

- focused Stage 09;
- focused Stage 10 P1/P2 regressions;
- full Stage 10 adversarial/integration suite;
- focused Stage 11 rendering regression;
- existing Stage 11 delivery-control regression;
- focused Stage 12 product tests;
- Stage 12 delivery-control regression;
- full repository regression;
- independent JSON Schema validation;
- package verification;
- global manifest refresh plus integrity check;
- whitespace check;
- generated-evidence reproducibility check.

## Namespace isolation

Stage 11 and Stage 12 remain separate trust domains:

| Binding | Stage 11 | Stage 12 |
|---|---|---|
| command | `/stage11` | `/stage12` |
| product branch | `codex/stage11-*` | `codex/stage12-audit-provenance` (exact current target) |
| control | `scripts/stage11_delivery_control.py` | `scripts/stage12_delivery_control.py` |
| workflow | `stage11-control.yml` | `stage12-control.yml` |
| promotion receipt | `STAGE11_*` | `STAGE12_*` |
| independent review | Stage 11 exact-SHA receipt | separate Stage 12 exact-SHA review |

No Stage 11 receipt is valid Stage 12 evidence.

## Independent procedure review and bootstrap boundary

This procedure must not be used merely because its builder reports PASS.

Before installation/use:

1. freeze an exact procedure candidate SHA;
2. obtain fresh CI on that exact SHA;
3. independently review that exact SHA;
4. establish an authorized way to install the reviewed procedure on the default branch.

If no already-authorized bootstrap path exists, installation is BLOCKED. Do not reuse Stage 11 landing authority, because the Stage 11 policy explicitly does not authorize starting Stage 12.

## Security invariants

The procedure must fail closed for:

- wrong command namespace;
- any branch other than the exact authorized Stage 12 product branch;
- stale PR head;
- stale target ref;
- stale base/main;
- wrong source tree;
- GraphQL expected-head failure;
- resulting parent mismatch;
- resulting tree mismatch;
- unsigned result;
- PR head/ref mismatch after mutation;
- main movement;
- ambiguous or mismatched assurance dispatch;
- any attempted Stage 11 receipt substitution.

No automated failure path may reset, delete, or force-update a ref.
