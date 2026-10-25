from __future__ import annotations

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
STAGE_PRODUCT_BRANCH = "codex/stage12-audit-provenance"
CANDIDATE_WORKFLOWS = ("stage02.yml", "stage11-assurance.yml")
CANDIDATE_WORKFLOW_PATHS = {
    "stage02.yml": ".github/workflows/stage02.yml",
    "stage11-assurance.yml": ".github/workflows/stage11-assurance.yml",
}
# These immutable workflows already exist in the reviewed Stage 12 product tree.
# Their historical run-name prefix remains unchanged; Stage 12 consumes them only
# as exact-SHA CI evidence and does not consume Stage 11 receipts or authority.
EXISTING_CI_DISPATCH_RUN_NAME_PREFIX = "stage11-dispatch-"
DISPATCH_POLL_ATTEMPTS = 30
DISPATCH_POLL_INTERVAL_SECONDS = 1.0


class ControlError(RuntimeError):
    pass


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected bearer request could disclose the privileged workflow token.
        fp.close()
        raise ControlError("GitHub API redirect refused")


def _require_sha(value: str, field: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ControlError(f"{field} must be an exact 40-char lowercase SHA")
    return value


def parse_command(body: str) -> tuple[str, dict[str, str]]:
    parts = shlex.split(body.strip())
    if len(parts) < 2 or parts[0] != "/stage12":
        raise ControlError("unsupported command namespace")
    if parts[1] != "promote":
        raise ControlError(f"unsupported Stage 12 command: {parts[1]}")
    args: dict[str, str] = {}
    for token in parts[2:]:
        if "=" not in token:
            raise ControlError(f"expected key=value token, got {token!r}")
        key, value = token.split("=", 1)
        if not key or not value or key in args:
            raise ControlError(f"invalid or duplicate argument: {key!r}")
        args[key] = value
    return "promote", args


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
) -> Any:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "api.github.com"
            or parsed.fragment):
        raise ControlError("GitHub API origin is not allowed")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "lukart-stage12-delivery-control",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirects()).open(request, timeout=30) as response:
            raw = response.read()
            return None if not raw else json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # API error payloads may contain private repository or case content.
        exc.close()
        raise ControlError(f"GitHub API {method} failed: {exc.code} (body withheld)") from None


def api(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    return _request(method, f"{API}/repos/{_repo()}{path}", payload)


def graphql(query: str, variables: dict[str, Any]) -> Any:
    result = _request("POST", GRAPHQL, {"query": query, "variables": variables})
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        raise ControlError(f"GraphQL failed: {errors}")
    if not isinstance(result, dict) or "data" not in result:
        raise ControlError("GraphQL response is malformed")
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


def _commit(sha: str) -> dict[str, Any]:
    return api("GET", f"/commits/{sha}")


def _pr(issue_number: int) -> dict[str, Any]:
    pr = _try_get(f"/pulls/{issue_number}")
    if not isinstance(pr, dict):
        raise ControlError("Stage 12 command must be attached to a pull request")
    return pr


def _post_comment(issue_number: int, body: str) -> None:
    api("POST", f"/issues/{issue_number}/comments", {"body": body})


def _event() -> dict[str, Any]:
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not path:
        raise ControlError("GITHUB_EVENT_PATH is missing")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_owner_actor(event: dict[str, Any]) -> None:
    comment = event.get("comment", {})
    actor = comment.get("user", {})
    owner = event.get("repository", {}).get("owner", {})
    association = comment.get("author_association")
    if (
        actor.get("login") != owner.get("login")
        or actor.get("id") != owner.get("id")
        or actor.get("type") != "User"
        or owner.get("type") != "User"
        or association != "OWNER"
        or comment.get("performed_via_github_app") is not None
    ):
        raise ControlError(
            "only the authenticated repository-owner HUMAN boundary may invoke Stage 12 control"
        )


def _ref_sha(branch: str) -> str | None:
    ref = _ref(branch)
    if not isinstance(ref, dict):
        return None
    value = ref.get("object", {}).get("sha")
    return value if isinstance(value, str) else None


def _assert_ref_sha(branch: str, expected_sha: str, phase: str) -> None:
    actual = _ref_sha(branch)
    if actual != expected_sha:
        raise ControlError(
            f"Stage 12 branch moved {phase}: expected={expected_sha}, actual={actual!r}"
        )


def _paged_items(path: str, key: str, *, context: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        request_path = path if page == 1 else f"{path}&page={page}"
        data = api("GET", request_path)
        batch = data.get(key) if isinstance(data, dict) else None
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ControlError(f"{context} listing is malformed")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def _workflow_dispatch_runs(workflow: str) -> list[dict[str, Any]]:
    if workflow not in CANDIDATE_WORKFLOWS:
        raise ControlError(f"untrusted Stage 12 candidate workflow: {workflow}")
    workflow_id = urllib.parse.quote(workflow, safe="")
    return _paged_items(
        f"/actions/workflows/{workflow_id}/runs?event=workflow_dispatch&per_page=100",
        "workflow_runs",
        context=f"Stage 12 candidate CI runs for {workflow}",
    )


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
    expected_title = f"{EXISTING_CI_DISPATCH_RUN_NAME_PREFIX}{dispatch_token}"
    expected_path = CANDIDATE_WORKFLOW_PATHS[workflow]
    for attempt in range(attempts):
        correlated: list[dict[str, Any]] = []
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
                raise ControlError("ambiguous Stage 12 assurance dispatch correlation")
            run = correlated[0]
            if (
                run.get("head_sha") != candidate_sha
                or run.get("head_branch") != branch
                or run.get("path") != expected_path
            ):
                raise ControlError(
                    "Stage 12 assurance dispatch bound to wrong source: "
                    f"head_sha={run.get('head_sha')!r}, "
                    f"head_branch={run.get('head_branch')!r}, "
                    f"path={run.get('path')!r}"
                )
            return run["id"]
        if attempt + 1 < attempts and interval_seconds > 0:
            time.sleep(interval_seconds)
    raise ControlError("Stage 12 assurance workflow run did not materialize")


def dispatch_assurance(branch: str, candidate_sha: str) -> dict[str, int]:
    if branch != STAGE_PRODUCT_BRANCH:
        raise ControlError("Stage 12 assurance branch is not the exact Stage 12 product branch")
    candidate_sha = _require_sha(candidate_sha, "candidate_sha")
    dispatch_token = secrets.token_hex(16)
    if not DISPATCH_TOKEN_RE.fullmatch(dispatch_token):
        raise ControlError("generated dispatch token is invalid")

    bound: dict[str, int] = {}
    _assert_ref_sha(branch, candidate_sha, "before candidate CI dispatch")
    for workflow in CANDIDATE_WORKFLOWS:
        baseline_ids = {
            run["id"]
            for run in _workflow_dispatch_runs(workflow)
            if type(run.get("id")) is int
        }
        _assert_ref_sha(branch, candidate_sha, f"before dispatch of {workflow}")
        workflow_id = urllib.parse.quote(workflow, safe="")
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
        bound[workflow] = _wait_for_bound_dispatch_run(
            workflow,
            branch,
            candidate_sha,
            dispatch_token,
            baseline_ids,
        )
        _assert_ref_sha(branch, candidate_sha, f"after binding {workflow}")
    _assert_ref_sha(branch, candidate_sha, "after candidate CI dispatch binding")
    return bound


def _abort_promotion(target: str, promoted_sha: str, reason: str) -> None:
    raise ControlError(
        "Stage 12 promotion BLOCKED: "
        f"{reason}; target preserved without reset/delete: {target}; "
        f"promoted_sha={promoted_sha}"
    )


def _validate_pr_preconditions(
    pr: dict[str, Any],
    source_sha: str,
    base_sha: str,
) -> str:
    if pr.get("state") != "open" or pr.get("draft") is not False or pr.get("merged"):
        raise ControlError("Stage 12 PR must be open, non-draft and unmerged")
    base = pr.get("base", {})
    head = pr.get("head", {})
    branch = head.get("ref")
    head_repo = head.get("repo", {})
    base_repo = base.get("repo", {})
    if (
        head_repo.get("id") is None
        or head_repo.get("id") != base_repo.get("id")
        or head_repo.get("full_name") != base_repo.get("full_name")
    ):
        raise ControlError("Stage 12 PR head and base must belong to the same repository")
    if base.get("ref") != "main":
        raise ControlError("Stage 12 PR base must be main")
    if branch != STAGE_PRODUCT_BRANCH:
        raise ControlError("Stage 12 PR head is not the exact authorized Stage 12 product branch")
    if head.get("sha") != source_sha:
        raise ControlError("Stage 12 source SHA does not equal current PR head")
    if base.get("sha") != base_sha:
        raise ControlError("Stage 12 base SHA does not equal current PR base")
    return branch


def promote(issue_number: int, args: dict[str, str]) -> None:
    required = {"source_sha", "source_tree", "base_sha"}
    if set(args) != required:
        raise ControlError(f"promote requires exactly {sorted(required)}")

    source_sha = _require_sha(args["source_sha"], "source_sha")
    source_tree = _require_sha(args["source_tree"], "source_tree")
    base_sha = _require_sha(args["base_sha"], "base_sha")

    pr = _pr(issue_number)
    branch = _validate_pr_preconditions(pr, source_sha, base_sha)

    if _ref_sha(branch) != source_sha:
        raise ControlError("Stage 12 target branch moved before promotion")
    if _ref_sha("main") != base_sha:
        raise ControlError("main moved before Stage 12 promotion")

    source_commit = _commit(source_sha)
    actual_source_tree = source_commit.get("commit", {}).get("tree", {}).get("sha")
    if actual_source_tree != source_tree:
        raise ControlError(
            f"Stage 12 source tree mismatch: expected={source_tree}, "
            f"actual={actual_source_tree!r}"
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
                "branchName": branch,
            },
            "message": {
                "headline": "stage12: create GitHub-verified tree-preserving candidate",
                "body": (
                    f"Source {source_sha}\n"
                    f"Tree {source_tree}\n"
                    "No product file changes."
                ),
            },
            "fileChanges": {},
            "expectedHeadOid": source_sha,
        }
    }

    data = graphql(mutation, variables)
    promoted_sha = (
        data.get("createCommitOnBranch", {}).get("commit", {}).get("oid")
        if isinstance(data, dict)
        else None
    )
    if not isinstance(promoted_sha, str) or not SHA_RE.fullmatch(promoted_sha):
        raise ControlError("GraphQL did not return an exact promoted SHA")

    try:
        promoted = _commit(promoted_sha)
        verification = promoted.get("commit", {}).get("verification", {})
        new_tree = promoted.get("commit", {}).get("tree", {}).get("sha")
        parents = promoted.get("parents")
        if not verification.get("verified"):
            raise ControlError("resulting Stage 12 commit is not GitHub verified")
        if new_tree != source_tree:
            raise ControlError("resulting Stage 12 tree differs from source tree")
        if (
            not isinstance(parents, list)
            or len(parents) != 1
            or parents[0].get("sha") != source_sha
        ):
            raise ControlError("resulting Stage 12 parent identity is wrong")

        if _ref_sha(branch) != promoted_sha:
            raise ControlError("Stage 12 target ref does not point to promoted SHA")
        post_pr = _pr(issue_number)
        _validate_pr_preconditions(post_pr, promoted_sha, base_sha)
        if _ref_sha("main") != base_sha:
            raise ControlError("main changed during Stage 12 promotion")

        assurance_runs = dispatch_assurance(branch, promoted_sha)

        final_pr = _pr(issue_number)
        _validate_pr_preconditions(final_pr, promoted_sha, base_sha)
        if _ref_sha("main") != base_sha:
            raise ControlError("main changed during assurance binding")
    except ControlError as exc:
        _abort_promotion(branch, promoted_sha, str(exc))

    receipt = "\n".join(
        [
            "STAGE12_PROMOTION: DISPATCH_BOUND",
            f"source_sha={source_sha}",
            f"new_sha={promoted_sha}",
            f"parent_sha={source_sha}",
            f"source_tree={source_tree}",
            f"new_tree={source_tree}",
            f"base_sha={base_sha}",
            "verification=VERIFIED",
            "assurance_runs=" + ",".join(
                f"{name}:{assurance_runs[name]}" for name in CANDIDATE_WORKFLOWS
            ),
            "main_changed=NO",
            "merge=NOT_PERFORMED",
        ]
    )
    _post_comment(issue_number, receipt)


def main() -> int:
    event = _event()
    _assert_owner_actor(event)
    body = event.get("comment", {}).get("body", "")
    issue_number = event.get("issue", {}).get("number")
    if type(issue_number) is not int:
        raise ControlError("issue number is missing")
    command, args = parse_command(body)
    if command == "promote":
        promote(issue_number, args)
        return 0
    raise ControlError("unsupported Stage 12 command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ControlError as exc:
        print(f"STAGE12_CONTROL: BLOCKED\nreason={exc}", file=sys.stderr)
        raise SystemExit(2)
