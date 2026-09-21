from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DISPATCH_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
DISPATCH_POLL_ATTEMPTS = 30
DISPATCH_POLL_INTERVAL_SECONDS = 1.0
DISPATCH_RUN_NAME_PREFIX = "stage11-dispatch-"
DISPATCH_RUN_NAME_WORKFLOW = (
    f"run-name: {DISPATCH_RUN_NAME_PREFIX}"
    "${{ inputs.dispatch_token || github.sha }}"
)
STAGE_BRANCH_PREFIX = "codex/stage11-"
WORK_BRANCH_PREFIX = "work/stage11-"
REQUIRED_STAGE11_CHECKS = ("validation", "stage11-rendering")
REQUIRED_STAGE11_WORKFLOWS = {
    "validation": ".github/workflows/stage02.yml",
    "stage11-rendering": ".github/workflows/stage11-assurance.yml",
}
CANDIDATE_WORKFLOWS = ("stage02.yml", "stage11-assurance.yml")
# Bounded procedure-only exception for the current remediation branch.  The
# historical PR #17 bootstrap exception is retired after merge; ordinary Stage 11
# branches still require real rendering tests.
PROCEDURE_BOOTSTRAP_BRANCH = "codex/stage11-postmerge-assurance-remediation"
PROCEDURE_BOOTSTRAP_BASE = "74364cb7b648feaff30cff465a5beade8d5f3498"
PROCEDURE_BOOTSTRAP_PATHS = frozenset({
    "docs/STAGE11_DELIVERY_AUTOMATION.md",
    "scripts/stage11_delivery_control.py",
    "tests/test_stage11_delivery_control.py",
})
FORBIDDEN_PROMOTION_PATHS = {
    "scripts/stage11_delivery_control.py",
    "docs/STAGE11_DELIVERY_AUTOMATION.md",
}
FORBIDDEN_PROMOTION_PREFIXES = (
    ".github/workflows/",
)


class ControlError(RuntimeError):
    pass

def _dispatch_run_title(dispatch_token: str) -> str:
    if not DISPATCH_TOKEN_RE.fullmatch(dispatch_token):
        raise ControlError("dispatch_token is invalid")
    return f"{DISPATCH_RUN_NAME_PREFIX}{dispatch_token}"



def require_stage11_tests(
    branch: str, tests_present: bool, *, base_sha: str = "", changed_paths: list[str] | None = None
) -> str:
    if tests_present:
        return "RENDERING_TESTS_REQUIRED"
    if (
        branch == PROCEDURE_BOOTSTRAP_BRANCH
        and base_sha == PROCEDURE_BOOTSTRAP_BASE
        and changed_paths
        and set(changed_paths) <= PROCEDURE_BOOTSTRAP_PATHS
    ):
        return "PROCEDURE_ONLY_BOOTSTRAP"
    raise ControlError("tests/test_stage11.py is required; no applicable procedure-only exception")


def _abort_promotion(target: str, promoted_sha: str, reason: str) -> None:
    # GitHub REST ref PATCH/DELETE have no expected-head CAS. Even a preceding
    # GET cannot make destructive compensation safe against a concurrent writer.
    # Preserve the failed commit and ref; recovery needs a separately guarded action.
    raise ControlError(
        f"promotion BLOCKED: {reason}; target preserved without reset/delete: "
        f"{target}; failed_promoted_sha={promoted_sha}; recovery required"
    )


def _require_sha(value: str, field: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ControlError(f"{field} must be an exact 40-char lowercase SHA")
    return value


def parse_command(body: str) -> tuple[str, dict[str, str]]:
    parts = shlex.split(body.strip())
    if len(parts) < 2 or parts[0] != "/stage11":
        raise ControlError("unsupported command")
    command = parts[1]
    if command not in {"promote", "merge", "cleanup"}:
        raise ControlError(f"unsupported Stage 11 command: {command}")
    args: dict[str, str] = {}
    for token in parts[2:]:
        if "=" not in token:
            raise ControlError(f"expected key=value token, got {token!r}")
        key, value = token.split("=", 1)
        if not key or not value or key in args:
            raise ControlError(f"invalid or duplicate argument: {key!r}")
        args[key] = value
    return command, args


def validate_promote_paths(paths: list[str]) -> None:
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise ControlError(f"unsafe path: {path}")
        if normalized in FORBIDDEN_PROMOTION_PATHS or any(
            normalized.startswith(prefix) for prefix in FORBIDDEN_PROMOTION_PREFIXES
        ):
            raise ControlError(f"trusted delivery-control path cannot be promoted: {path}")


def _token() -> str:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise ControlError("GH_TOKEN is missing")
    return token


def _repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo.count("/") != 1:
        raise ControlError("GITHUB_REPOSITORY is invalid")
    return repo


def _request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    accept: str = "application/vnd.github+json",
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "lukart-stage11-delivery-control",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ControlError(f"GitHub API {method} {url} failed: {exc.code} {body}") from exc


def api(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    return _request(method, f"{API}/repos/{_repo()}{path}", payload)


def graphql(query: str, variables: dict[str, Any]) -> Any:
    result = _request("POST", GRAPHQL, {"query": query, "variables": variables})
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        raise ControlError(f"GraphQL failed: {errors}")
    return result["data"]


def _try_get(path: str) -> Any | None:
    try:
        return api("GET", path)
    except ControlError as exc:
        if " 404 " in str(exc):
            return None
        raise


def _ref(branch: str) -> dict[str, Any] | None:
    quoted = urllib.parse.quote(f"heads/{branch}", safe="")
    return _try_get(f"/git/ref/{quoted}")


def _post_comment(issue_number: int, body: str) -> None:
    api("POST", f"/issues/{issue_number}/comments", {"body": body})


def _local_digest(path: str) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def _procedure_identity() -> tuple[str, str]:
    return (
        _local_digest("docs/STAGE11_DELIVERY_AUTOMATION.md"),
        _local_digest("scripts/stage11_delivery_control.py"),
    )


def _assert_ref_sha(branch: str, expected_sha: str, phase: str) -> None:
    ref = _ref(branch)
    actual = ref.get("object", {}).get("sha") if isinstance(ref, dict) else None
    if actual != expected_sha:
        raise ControlError(
            f"candidate branch moved {phase}: expected={expected_sha}, actual={actual!r}"
        )


def _workflow_dispatch_runs(workflow: str) -> list[dict[str, Any]]:
    workflow_id = urllib.parse.quote(workflow, safe="")
    data = api(
        "GET",
        f"/actions/workflows/{workflow_id}/runs?event=workflow_dispatch&per_page=100",
    )
    runs = data.get("workflow_runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        raise ControlError(f"workflow run listing is malformed for {workflow}")
    return [run for run in runs if isinstance(run, dict)]


def _wait_for_bound_dispatch_run(
    workflow: str,
    branch: str,
    candidate_sha: str,
    dispatch_token: str,
    baseline_ids: set[int],
    *,
    attempts: int = DISPATCH_POLL_ATTEMPTS,
    interval_seconds: float = DISPATCH_POLL_INTERVAL_SECONDS,
) -> int:
    expected_title = _dispatch_run_title(dispatch_token)
    expected_path = f".github/workflows/{workflow}"
    for attempt in range(attempts):
        correlated = []
        for run in _workflow_dispatch_runs(workflow):
            run_id = run.get("id")
            if type(run_id) is not int or run_id in baseline_ids:
                continue
            if (
                run.get("display_title") == expected_title
                and run.get("event") == "workflow_dispatch"
            ):
                correlated.append(run)
        if correlated:
            if len(correlated) != 1:
                raise ControlError(
                    f"ambiguous correlated workflow_dispatch runs for {workflow}"
                )
            run = correlated[0]
            if (
                run.get("head_sha") != candidate_sha
                or run.get("head_branch") != branch
                or run.get("path") != expected_path
            ):
                raise ControlError(
                    f"workflow_dispatch bound to wrong source for {workflow}: "
                    f"head_sha={run.get('head_sha')!r}, "
                    f"head_branch={run.get('head_branch')!r}, path={run.get('path')!r}"
                )
            return run["id"]
        if attempt + 1 < attempts and interval_seconds > 0:
            time.sleep(interval_seconds)
    raise ControlError(
        f"workflow_dispatch run did not materialize for exact candidate: {workflow}"
    )


def dispatch_candidate_checks(branch: str, sha: str) -> dict[str, int]:
    if not branch.startswith(STAGE_BRANCH_PREFIX):
        raise ControlError("candidate CI branch is outside Stage 11 namespace")
    candidate_sha = _require_sha(sha, "candidate_sha")
    dispatch_token = secrets.token_hex(16)
    if not DISPATCH_TOKEN_RE.fullmatch(dispatch_token):
        raise ControlError("generated dispatch token is invalid")

    bound_runs: dict[str, int] = {}
    _assert_ref_sha(branch, candidate_sha, "before exact-SHA CI dispatch")

    for workflow in CANDIDATE_WORKFLOWS:
        workflow_id = urllib.parse.quote(workflow, safe="")
        baseline_ids = {
            run["id"]
            for run in _workflow_dispatch_runs(workflow)
            if type(run.get("id")) is int
        }
        _assert_ref_sha(branch, candidate_sha, f"before dispatch of {workflow}")
        api(
            "POST",
            f"/actions/workflows/{workflow_id}/dispatches",
            {
                "ref": branch,
                "inputs": {
                    "candidate_sha": candidate_sha,
                    "dispatch_token": dispatch_token,
                },
            },
        )
        bound_runs[workflow] = _wait_for_bound_dispatch_run(
            workflow,
            branch,
            candidate_sha,
            dispatch_token,
            baseline_ids,
        )
        _assert_ref_sha(branch, candidate_sha, f"after binding {workflow}")

    _assert_ref_sha(branch, candidate_sha, "after exact-SHA CI dispatch binding")
    return bound_runs


def _event() -> dict[str, Any]:
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not path:
        raise ControlError("GITHUB_EVENT_PATH is missing")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_owner_actor(event: dict[str, Any]) -> None:
    actor = event.get("comment", {}).get("user", {}).get("login")
    owner = event.get("repository", {}).get("owner", {}).get("login")
    if actor != owner:
        raise ControlError(f"only repository owner may invoke Stage 11 control; actor={actor!r}")


def _commit(sha: str) -> dict[str, Any]:
    return api("GET", f"/commits/{sha}")


def _tree_map(commit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tree_sha = commit["commit"]["tree"]["sha"]
    tree = api("GET", f"/git/trees/{tree_sha}?recursive=1")
    return {
        item["path"]: item
        for item in tree.get("tree", [])
        if item.get("type") == "blob"
    }


def _blob_bytes(blob_sha: str) -> bytes:
    blob = api("GET", f"/git/blobs/{blob_sha}")
    if blob.get("encoding") != "base64":
        raise ControlError(f"unsupported blob encoding for {blob_sha}")
    return base64.b64decode(blob["content"], validate=False)


def promote(issue_number: int, args: dict[str, str]) -> None:
    required = {"source", "source_sha", "target", "base_sha"}
    if set(args) != required:
        raise ControlError(f"promote requires exactly {sorted(required)}")
    source = args["source"]
    target = args["target"]
    source_sha = _require_sha(args["source_sha"], "source_sha")
    base_sha = _require_sha(args["base_sha"], "base_sha")
    if not source.startswith(WORK_BRANCH_PREFIX):
        raise ControlError(f"source must match {WORK_BRANCH_PREFIX}*")
    if not target.startswith(STAGE_BRANCH_PREFIX):
        raise ControlError(f"target must match {STAGE_BRANCH_PREFIX}*")

    source_ref = _ref(source)
    if not source_ref or source_ref["object"]["sha"] != source_sha:
        raise ControlError("source branch moved or is missing")

    target_ref = _ref(target)
    if target_ref is None:
        main = _ref("main")
        if not main or main["object"]["sha"] != base_sha:
            raise ControlError("first promotion base_sha must equal current main")
        api("POST", "/git/refs", {"ref": f"refs/heads/{target}", "sha": base_sha})
    else:
        if target_ref["object"]["sha"] != base_sha:
            raise ControlError("target branch moved; base_sha is stale")

    compare = api("GET", f"/compare/{base_sha}...{source_sha}")
    if compare.get("behind_by") != 0 or int(compare.get("ahead_by", 0)) < 1:
        raise ControlError("source must be strictly ahead of target base and not behind")

    files = compare.get("files", [])
    if not files:
        raise ControlError("promotion contains no file changes")
    paths: list[str] = []
    deletions: list[dict[str, str]] = []
    addition_paths: set[str] = set()
    for item in files:
        path = item["filename"]
        paths.append(path)
        status = item.get("status")
        if status == "removed":
            deletions.append({"path": path})
        else:
            addition_paths.add(path)
        previous = item.get("previous_filename")
        if status == "renamed" and previous:
            paths.append(previous)
            deletions.append({"path": previous})
    validate_promote_paths(paths)

    source_commit = _commit(source_sha)
    source_tree = _tree_map(source_commit)
    additions: list[dict[str, str]] = []
    for path in sorted(addition_paths):
        entry = source_tree.get(path)
        if not entry:
            raise ControlError(f"missing promoted blob in source tree: {path}")
        if entry.get("mode") not in {"100644", "100755"}:
            raise ControlError(f"unsupported promoted file mode {entry.get('mode')} for {path}")
        raw = _blob_bytes(entry["sha"])
        additions.append(
            {"path": path, "contents": base64.b64encode(raw).decode("ascii")}
        )

    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid url }
      }
    }
    """
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": _repo(),
                "branchName": target,
            },
            "message": {
                "headline": "stage11: promote exact Work tree",
                "body": f"Source {source}@{source_sha}",
            },
            "fileChanges": {
                "additions": additions,
                "deletions": deletions,
            },
            "expectedHeadOid": base_sha,
        }
    }
    data = graphql(mutation, variables)
    promoted_sha = data["createCommitOnBranch"]["commit"]["oid"]
    promoted = _commit(promoted_sha)
    verification = promoted["commit"]["verification"]
    same_tree = promoted["commit"]["tree"]["sha"] == source_commit["commit"]["tree"]["sha"]

    if not verification.get("verified") or not same_tree:
        _abort_promotion(
            target, promoted_sha,
            "resulting commit was not GitHub-verified or tree identity differed",
        )

    # GITHUB_TOKEN pushes do not recursively trigger ordinary push workflows.
    # Dispatch the trusted exact-SHA assurance workflows explicitly, then bind each
    # dispatch to the concrete workflow run GitHub materialized for promoted_sha.
    # The Work source ref is immutable input evidence for this operation and is never
    # rewritten by promotion.
    try:
        bound_runs = dispatch_candidate_checks(target, promoted_sha)
    except Exception as exc:
        _abort_promotion(target, promoted_sha, f"CI dispatch binding failed: {exc}")

    _assert_ref_sha(target, promoted_sha, "before promotion dispatch receipt")

    policy_digest, procedure_digest = _procedure_identity()
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_PROMOTION: DISPATCH_BOUND",
                f"source={source}",
                f"source_sha={source_sha}",
                "source_ref_mutation=NONE",
                f"target={target}",
                f"target_observed_sha={promoted_sha}",
                f"base_sha={base_sha}",
                f"promoted_sha={promoted_sha}",
                f"tree_sha={promoted['commit']['tree']['sha']}",
                f"policy_sha256={policy_digest}",
                f"procedure_sha256={procedure_digest}",
                "ci_dispatch=BOUND",
                "dispatch_runs=" + ",".join(
                    f"{workflow}:{bound_runs[workflow]}"
                    for workflow in CANDIDATE_WORKFLOWS
                ),
                f"required_checks={','.join(REQUIRED_STAGE11_CHECKS)}",
                "signature=VERIFIED",
                "candidate_assurance=REQUIRED_BEFORE_MERGE",
            ]
        ),
    )


def _pr_from_event(event: dict[str, Any]) -> dict[str, Any]:
    if "pull_request" not in event.get("issue", {}):
        raise ControlError("merge/cleanup commands must be posted on a pull request")
    number = int(event["issue"]["number"])
    return api("GET", f"/pulls/{number}")


def _comments(issue_number: int) -> list[dict[str, Any]]:
    data = api("GET", f"/issues/{issue_number}/comments?per_page=100")
    return list(data)


def _has_independent_review(
    comments: list[dict[str, Any]], sha: str, base_sha: str, owner: dict[str, Any]
) -> bool:
    expected = {
        "sha": _require_sha(sha, "review_sha"),
        "base_sha": _require_sha(base_sha, "review_base_sha"),
        "p0": "0", "p1": "0", "merge": "NOT_PERFORMED",
    }
    # Owner attestation is the existing HUMAN trust boundary. Identity comes
    # from GitHub metadata, never from text supplied inside the receipt.
    if type(owner.get("id")) is not int or not owner.get("login") or owner.get("type") != "User":
        return False
    for comment in comments:
        user = comment.get("user")
        if not isinstance(user, dict) or (
            type(user.get("id")) is not int
            or user.get("id") != owner["id"]
            or user.get("login") != owner["login"]
            or user.get("type") != "User"
            or comment.get("author_association") != "OWNER"
            or comment.get("performed_via_github_app") is not None
        ):
            continue
        body = comment.get("body")
        if not isinstance(body, str):
            continue
        lines = body.splitlines()
        if not lines or lines[0] != "STAGE11_INDEPENDENT_REVIEW: PASS":
            continue
        fields: dict[str, str] = {}
        for line in lines[1:]:
            key, separator, value = line.partition("=")
            if not separator or key in fields or key not in expected:
                break
            fields[key] = value
        else:
            if fields == expected:
                return True
    return False


def _check_gate(sha: str, *, required_event: str) -> None:
    candidate_sha = _require_sha(sha, "gate_sha")
    if required_event not in {"workflow_dispatch", "push"}:
        raise ControlError(f"unsupported gate event: {required_event}")

    data = api("GET", f"/commits/{candidate_sha}/check-runs?per_page=100")
    runs = data.get("check_runs", [])
    if not runs:
        raise ControlError("no check-runs found for candidate")

    trusted_runs = [
        run
        for run in runs
        if run.get("app", {}).get("slug") == "github-actions"
    ]
    nonterminal = [
        run["name"]
        for run in trusted_runs
        if run.get("status") != "completed"
    ]
    failing = [
        run["name"]
        for run in trusted_runs
        if run.get("status") == "completed"
        and run.get("conclusion") not in {"success", "neutral", "skipped"}
    ]
    if nonterminal or failing:
        raise ControlError(
            f"checks are not terminal-green: pending={nonterminal}, failing={failing}"
        )

    by_name: dict[str, list[dict[str, Any]]] = {}
    for run in trusted_runs:
        by_name.setdefault(run["name"], []).append(run)
    missing = []
    for name in REQUIRED_STAGE11_CHECKS:
        if not any(
            run.get("status") == "completed" and run.get("conclusion") == "success"
            for run in by_name.get(name, [])
        ):
            missing.append(name)
    if missing:
        raise ControlError(
            f"required trusted GitHub Actions checks missing/not-success: {missing}"
        )

    query_event = urllib.parse.quote(required_event, safe="")
    action_runs = api(
        "GET",
        f"/actions/runs?head_sha={candidate_sha}&event={query_event}&per_page=100",
    ).get("workflow_runs", [])
    workflow_failures = []
    for check_name, expected_path in REQUIRED_STAGE11_WORKFLOWS.items():
        matching = [
            run
            for run in action_runs
            if run.get("head_sha") == candidate_sha
            and run.get("event") == required_event
            and run.get("path") == expected_path
        ]
        if not any(
            run.get("status") == "completed" and run.get("conclusion") == "success"
            for run in matching
        ):
            workflow_failures.append(
                {
                    "check": check_name,
                    "path": expected_path,
                    "event": required_event,
                }
            )
    if workflow_failures:
        raise ControlError(
            "required exact-SHA workflow provenance missing/not-success: "
            f"{workflow_failures}"
        )


def merge(event: dict[str, Any], issue_number: int, args: dict[str, str]) -> None:
    required = {"head_sha", "base_sha"}
    if set(args) != required:
        raise ControlError(f"merge requires exactly {sorted(required)}")
    head_sha = _require_sha(args["head_sha"], "head_sha")
    base_sha = _require_sha(args["base_sha"], "base_sha")
    pr = _pr_from_event(event)
    if pr.get("state") != "open" or pr.get("draft"):
        raise ControlError("PR must be OPEN and not draft")
    if pr["base"]["ref"] != "main" or pr["base"]["sha"] != base_sha:
        raise ControlError("PR base changed")
    if not pr["head"]["ref"].startswith(STAGE_BRANCH_PREFIX):
        raise ControlError("PR head is outside Stage 11 branch namespace")
    if pr["head"]["sha"] != head_sha:
        raise ControlError("PR head changed")

    head = _commit(head_sha)
    if not head["commit"]["verification"].get("verified"):
        raise ControlError("Stage 11 candidate commit is not GitHub-verified")
    _check_gate(head_sha, required_event="workflow_dispatch")

    comments = _comments(issue_number)
    owner = api("GET", "").get("owner", {})
    if not _has_independent_review(comments, head_sha, base_sha, owner):
        raise ControlError("authenticated exact-SHA/base independent review PASS receipt is missing")

    # GitHub's pull-request merge API can atomically pin the PR head SHA but not
    # the base SHA.  Using it here would leave a TOCTOU window where main can move
    # after the preflight read and before the merge write.  Instead, replay the
    # exact reviewed tree onto main with createCommitOnBranch(expectedHeadOid=...).
    # GitHub performs that expected-head comparison atomically and signs the
    # resulting commit.  No main mutation occurs when the expected base is stale.
    main_ref = _ref("main")
    if not main_ref or main_ref["object"]["sha"] != base_sha:
        raise ControlError("main moved before atomic landing")

    compare = api("GET", f"/compare/{base_sha}...{head_sha}")
    if compare.get("behind_by") != 0 or int(compare.get("ahead_by", 0)) < 1:
        raise ControlError("reviewed candidate must be strictly ahead of the exact base")

    files = compare.get("files", [])
    if not files:
        raise ControlError("reviewed candidate contains no file changes")
    candidate_tree = _tree_map(head)
    additions: list[dict[str, str]] = []
    deletions: list[dict[str, str]] = []
    paths: list[str] = []
    addition_paths: set[str] = set()
    for item in files:
        path = item["filename"]
        paths.append(path)
        status = item.get("status")
        if status == "removed":
            deletions.append({"path": path})
        else:
            addition_paths.add(path)
        previous = item.get("previous_filename")
        if status == "renamed" and previous:
            paths.append(previous)
            deletions.append({"path": previous})
    validate_promote_paths(paths)

    for path in sorted(addition_paths):
        entry = candidate_tree.get(path)
        if not entry:
            raise ControlError(f"missing reviewed blob in candidate tree: {path}")
        if entry.get("mode") not in {"100644", "100755"}:
            raise ControlError(
                f"unsupported reviewed file mode {entry.get('mode')} for {path}"
            )
        additions.append(
            {
                "path": path,
                "contents": base64.b64encode(_blob_bytes(entry["sha"])).decode("ascii"),
            }
        )

    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid url }
      }
    }
    """
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": _repo(),
                "branchName": "main",
            },
            "message": {
                "headline": "stage11: atomically land reviewed candidate",
                "body": (
                    f"PR #{issue_number}\n"
                    f"Reviewed head {head_sha}\n"
                    f"Expected base {base_sha}"
                ),
            },
            "fileChanges": {
                "additions": additions,
                "deletions": deletions,
            },
            "expectedHeadOid": base_sha,
        }
    }
    try:
        data = graphql(mutation, variables)
    except Exception as exc:
        raise ControlError(
            f"atomic base-SHA landing failed before main mutation: {exc}"
        ) from exc

    landed_sha = data["createCommitOnBranch"]["commit"]["oid"]
    landed = _commit(landed_sha)
    parents = [p["sha"] for p in landed.get("parents", [])]
    if (
        not landed["commit"]["verification"].get("verified")
        or parents != [base_sha]
        or landed["commit"]["tree"]["sha"] != head["commit"]["tree"]["sha"]
    ):
        raise ControlError(
            "atomic landing completed but exact post-landing identity verification "
            "failed; Stage 11 is BLOCKED"
        )

    closed = api("PATCH", f"/pulls/{issue_number}", {"state": "closed"})
    if closed.get("state") != "closed":
        raise ControlError(
            "atomic landing completed but PR close failed; Stage 11 is BLOCKED"
        )

    policy_digest, procedure_digest = _procedure_identity()
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_LANDING: PASS",
                f"sha={landed_sha}",
                f"base_sha={base_sha}",
                f"head_sha={head_sha}",
                f"tree_sha={landed['commit']['tree']['sha']}",
                f"policy_sha256={policy_digest}",
                f"procedure_sha256={procedure_digest}",
                "landing_mode=ATOMIC_EXPECTED_HEAD",
                "signature=VERIFIED",
                "post_merge=REQUIRED",
            ]
        ),
    )


def cleanup(event: dict[str, Any], issue_number: int, args: dict[str, str]) -> None:
    required = {"branch", "branch_sha", "main_sha"}
    if set(args) != required:
        raise ControlError(f"cleanup requires exactly {sorted(required)}")
    branch = args["branch"]
    branch_sha = _require_sha(args["branch_sha"], "branch_sha")
    main_sha = _require_sha(args["main_sha"], "main_sha")
    if not branch.startswith(STAGE_BRANCH_PREFIX):
        raise ControlError("cleanup branch is outside Stage 11 namespace")

    pr = _pr_from_event(event)
    if pr.get("state") != "closed":
        raise ControlError("PR is not closed after atomic landing")
    if pr.get("base", {}).get("ref") != "main":
        raise ControlError("cleanup PR base is not main")
    if (
        pr.get("head", {}).get("ref") != branch
        or pr.get("head", {}).get("sha") != branch_sha
    ):
        raise ControlError("cleanup PR head does not bind the requested Stage 11 candidate")

    main_ref = _ref("main")
    branch_ref = _ref(branch)
    if not main_ref or main_ref["object"]["sha"] != main_sha:
        raise ControlError("main moved after post-merge verification")
    if not branch_ref or branch_ref["object"]["sha"] != branch_sha:
        raise ControlError("branch moved or is missing")

    main_commit = _commit(main_sha)
    branch_commit = _commit(branch_sha)
    parents = [p["sha"] for p in main_commit.get("parents", [])]
    if len(parents) != 1:
        raise ControlError("atomic landing commit must have exactly one base parent")
    if not main_commit["commit"]["verification"].get("verified"):
        raise ControlError("atomic landing commit is not GitHub-verified")
    if not branch_commit["commit"]["verification"].get("verified"):
        raise ControlError("reviewed Stage 11 candidate is not GitHub-verified")
    if main_commit["commit"]["tree"]["sha"] != branch_commit["commit"]["tree"]["sha"]:
        raise ControlError("landing tree differs from reviewed Stage 11 candidate tree")

    _check_gate(main_sha, required_event="push")

    # Re-read both refs after all potentially slow assurance calls.  There is no
    # compare-and-swap delete in the GitHub REST/GraphQL ref APIs, so deletion
    # after a successful read would still be vulnerable to a concurrent writer.
    # Stage 11 therefore completes cleanup non-destructively: exact refs are
    # verified and preserved.  Optional later branch retirement is explicitly
    # outside the assurance transaction.
    _assert_ref_sha("main", main_sha, "before post-merge receipt")
    _assert_ref_sha(branch, branch_sha, "before non-destructive cleanup receipt")

    policy_digest, procedure_digest = _procedure_identity()
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_POST_MERGE_VERIFICATION: PASS",
                f"sha={main_sha}",
                f"candidate_sha={branch_sha}",
                f"tree_sha={main_commit['commit']['tree']['sha']}",
                f"policy_sha256={policy_digest}",
                f"procedure_sha256={procedure_digest}",
                "signature=VERIFIED",
                "workflow_provenance=BOUND_TO_PUSH",
            ]
        ),
    )
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_CLEANUP: PASS",
                f"sha={main_sha}",
                f"preserved_branch={branch}",
                f"preserved_branch_sha={branch_sha}",
                "ref_disposition=PRESERVED_NO_CAS_DELETE",
                "source_ref_mutation=NONE",
            ]
        ),
    )


def main() -> int:
    event = _event()
    issue_number = int(event["issue"]["number"])
    try:
        _assert_owner_actor(event)
        command, args = parse_command(event["comment"]["body"])
        if command == "promote":
            promote(issue_number, args)
        elif command == "merge":
            merge(event, issue_number, args)
        else:
            cleanup(event, issue_number, args)
        return 0
    except Exception as exc:
        message = f"STAGE11_CONTROL: BLOCKED\nreason={type(exc).__name__}: {exc}"
        try:
            _post_comment(issue_number, message)
        except Exception:
            pass
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
