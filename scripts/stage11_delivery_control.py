from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
STAGE_BRANCH_PREFIX = "codex/stage11-"
WORK_BRANCH_PREFIX = "work/stage11-"
REQUIRED_STAGE11_CHECKS = ("validation", "stage11-rendering")
CANDIDATE_WORKFLOWS = ("stage02.yml", "stage11-assurance.yml")
FORBIDDEN_PROMOTION_PATHS = {
    "scripts/stage11_delivery_control.py",
    "docs/STAGE11_DELIVERY_AUTOMATION.md",
}
FORBIDDEN_PROMOTION_PREFIXES = (
    ".github/workflows/",
)


class ControlError(RuntimeError):
    pass


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


def dispatch_candidate_checks(branch: str, sha: str) -> None:
    if not branch.startswith(STAGE_BRANCH_PREFIX):
        raise ControlError("candidate CI branch is outside Stage 11 namespace")
    candidate_sha = _require_sha(sha, "candidate_sha")
    for workflow in CANDIDATE_WORKFLOWS:
        workflow_id = urllib.parse.quote(workflow, safe="")
        api(
            "POST",
            f"/actions/workflows/{workflow_id}/dispatches",
            {
                "ref": branch,
                "inputs": {"candidate_sha": candidate_sha},
            },
        )


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
        target_created = True
    else:
        if target_ref["object"]["sha"] != base_sha:
            raise ControlError("target branch moved; base_sha is stale")
        target_created = False

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
        quoted = urllib.parse.quote(f"heads/{target}", safe="")
        api("PATCH", f"/git/refs/{quoted}", {"sha": base_sha, "force": True})
        if target_created:
            api("DELETE", f"/git/refs/{quoted}")
        raise ControlError(
            "promotion rollback: resulting commit was not GitHub-verified or tree identity differed"
        )

    # GITHUB_TOKEN pushes do not recursively trigger ordinary push workflows.
    # Dispatch the trusted exact-SHA assurance workflows explicitly. Both workflows
    # fail closed unless the dispatch ref resolves to this exact promoted SHA.
    try:
        dispatch_candidate_checks(target, promoted_sha)
    except Exception:
        quoted = urllib.parse.quote(f"heads/{target}", safe="")
        api("PATCH", f"/git/refs/{quoted}", {"sha": base_sha, "force": True})
        if target_created:
            api("DELETE", f"/git/refs/{quoted}")
        raise

    # Replace the unsigned Work staging head only after both exact-SHA CI dispatches
    # have been accepted. This preserves a retryable source if dispatch fails.
    source_quoted = urllib.parse.quote(f"heads/{source}", safe="")
    api("PATCH", f"/git/refs/{source_quoted}", {"sha": promoted_sha, "force": True})

    policy_digest, procedure_digest = _procedure_identity()
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_PROMOTION: PASS",
                f"source={source}",
                f"source_sha={source_sha}",
                f"target={target}",
                f"base_sha={base_sha}",
                f"promoted_sha={promoted_sha}",
                f"tree_sha={promoted['commit']['tree']['sha']}",
                f"source_reset_sha={promoted_sha}",
                f"policy_sha256={policy_digest}",
                f"procedure_sha256={procedure_digest}",
                "ci_dispatch=REQUESTED",
                f"required_checks={','.join(REQUIRED_STAGE11_CHECKS)}",
                "signature=VERIFIED",
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


def _has_receipt(comments: list[dict[str, Any]], prefix: str, sha: str) -> bool:
    needle = f"sha={sha}"
    for comment in comments:
        body = str(comment.get("body", ""))
        if body.startswith(prefix) and needle in body:
            return True
    return False


def _check_gate(sha: str) -> None:
    data = api("GET", f"/commits/{sha}/check-runs?per_page=100")
    runs = data.get("check_runs", [])
    if not runs:
        raise ControlError("no check-runs found for candidate")
    nonterminal = [r["name"] for r in runs if r.get("status") != "completed"]
    failing = [
        r["name"]
        for r in runs
        if r.get("status") == "completed"
        and r.get("conclusion") not in {"success", "neutral", "skipped"}
    ]
    if nonterminal or failing:
        raise ControlError(
            f"checks are not terminal-green: pending={nonterminal}, failing={failing}"
        )
    by_name = {}
    for run in runs:
        by_name.setdefault(run["name"], []).append(run)
    missing = []
    for name in REQUIRED_STAGE11_CHECKS:
        if not any(
            r.get("status") == "completed" and r.get("conclusion") == "success"
            for r in by_name.get(name, [])
        ):
            missing.append(name)
    if missing:
        raise ControlError(f"required Stage 11 checks missing/not-success: {missing}")


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
    _check_gate(head_sha)

    comments = _comments(issue_number)
    if not _has_receipt(comments, "STAGE11_INDEPENDENT_REVIEW: PASS", head_sha):
        raise ControlError("exact-SHA independent review PASS receipt is missing")

    result = api(
        "PUT",
        f"/pulls/{issue_number}/merge",
        {"sha": head_sha, "merge_method": "merge"},
    )
    if not result.get("merged"):
        raise ControlError(f"GitHub did not merge PR: {result}")
    merge_sha = result["sha"]
    merged = _commit(merge_sha)
    parents = [p["sha"] for p in merged.get("parents", [])]
    if (
        not merged["commit"]["verification"].get("verified")
        or parents != [base_sha, head_sha]
        or merged["commit"]["tree"]["sha"] != head["commit"]["tree"]["sha"]
    ):
        raise ControlError(
            "merge completed but exact post-merge identity verification failed; Stage 11 is BLOCKED"
        )

    policy_digest, procedure_digest = _procedure_identity()
    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_MERGE: PASS",
                f"sha={merge_sha}",
                f"base_sha={base_sha}",
                f"head_sha={head_sha}",
                f"tree_sha={merged['commit']['tree']['sha']}",
                f"policy_sha256={policy_digest}",
                f"procedure_sha256={procedure_digest}",
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
    if not pr.get("merged") or pr.get("state") != "closed":
        raise ControlError("PR is not merged/closed")
    if pr.get("merge_commit_sha") != main_sha:
        raise ControlError("main_sha does not equal PR merge commit")

    main_ref = _ref("main")
    branch_ref = _ref(branch)
    source_branch = WORK_BRANCH_PREFIX + branch[len(STAGE_BRANCH_PREFIX):]
    source_ref = _ref(source_branch)
    if not main_ref or main_ref["object"]["sha"] != main_sha:
        raise ControlError("main moved after post-merge verification")
    if not branch_ref or branch_ref["object"]["sha"] != branch_sha:
        raise ControlError("branch moved or is missing")
    if source_ref and source_ref["object"]["sha"] != branch_sha:
        raise ControlError("Work staging branch diverged after final promotion")

    main_commit = _commit(main_sha)
    branch_commit = _commit(branch_sha)
    parents = [p["sha"] for p in main_commit.get("parents", [])]
    if len(parents) != 2 or parents[1] != branch_sha:
        raise ControlError("merge commit does not bind the requested Stage 11 branch SHA")
    if main_commit["commit"]["tree"]["sha"] != branch_commit["commit"]["tree"]["sha"]:
        raise ControlError("merge tree differs from reviewed Stage 11 candidate tree")

    _check_gate(main_sha)
    comments = _comments(issue_number)
    if not _has_receipt(
        comments, "STAGE11_POST_MERGE_VERIFICATION: PASS", main_sha
    ):
        raise ControlError("post-merge PASS receipt is missing")

    quoted = urllib.parse.quote(f"heads/{branch}", safe="")
    api("DELETE", f"/git/refs/{quoted}")
    if source_ref:
        source_quoted = urllib.parse.quote(f"heads/{source_branch}", safe="")
        api("DELETE", f"/git/refs/{source_quoted}")

    _post_comment(
        issue_number,
        "\n".join(
            [
                "STAGE11_CLEANUP: PASS",
                f"sha={main_sha}",
                f"deleted_branch={branch}",
                f"deleted_branch_sha={branch_sha}",
                f"deleted_work_branch={source_branch if source_ref else 'NOT_PRESENT'}",
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
