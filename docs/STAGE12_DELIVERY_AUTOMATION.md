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

1. caller is the repository-owner HUMAN and `comment.performed_via_github_app` is `null`;
2. the comment belongs to an open, non-draft, unmerged PR;
3. PR head and base belong to the same repository, and PR base is `main`;
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

## Exact-SHA candidate CI dispatch

The reviewed Stage 12 product tree already contains the two immutable CI workflows required for exact-candidate assurance:

- `.github/workflows/stage02.yml`;
- `.github/workflows/stage11-assurance.yml`.

The Stage 12 control may dispatch those existing workflows **only as CI evidence** because adding a new workflow to the product branch would change the reviewed tree. This does not import Stage 11 command authority, policy authority, independent-review receipts, landing authority, or Stage 11 receipt semantics.

Successful promotion dispatches both existing workflows with:

- `ref=codex/stage12-audit-provenance`;
- `candidate_sha=<new exact SHA>`;
- one unique 128-bit hexadecimal `dispatch_token`.

Their historical `stage11-dispatch-<token>` run-name prefix is not renamed, because changing either workflow would alter the reviewed product tree. The Stage 12 control treats that prefix only as immutable workflow correlation metadata and emits exclusively `STAGE12_*` receipts.

For each workflow the control records pre-dispatch run IDs, dispatches once, and requires exactly one newly materialized run whose event, workflow path, head SHA and head branch bind to the new candidate. The product branch ref is re-read before and after each dispatch binding.

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
assurance_runs=stage02.yml:<run id>,stage11-assurance.yml:<run id>
main_changed=NO
merge=NOT_PERFORMED
```

This receipt does not claim assurance PASS, independent review PASS, merge authority, or Stage 12 closure.

## Procedure assurance workflow

`.github/workflows/stage12-procedure-assurance.yml` exists only on the procedure-remediation branch/PR. It assures procedure code; it is not dispatched against the Stage 12 product candidate and is never required to exist in the reviewed product tree.

Procedure assurance includes, at minimum:

- focused Stage 09;
- focused Stage 10 P1/P2 regressions;
- full Stage 10 adversarial/integration suite;
- focused Stage 11 rendering regression;
- existing Stage 11 delivery-control regression;
- focused Stage 12 delivery-control regression;
- full repository regression;
- independent JSON Schema validation;
- package verification;
- global manifest refresh plus integrity check;
- whitespace check;
- generated-evidence reproducibility check.

After a signed Stage 12 candidate is created, its own existing `stage02.yml` full regression discovers and executes `tests/test_stage12.py`, while `stage11-assurance.yml` independently rechecks Stage 11 rendering identity.

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
