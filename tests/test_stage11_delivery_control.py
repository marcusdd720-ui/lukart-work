from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage11_delivery_control.py"
SPEC = importlib.util.spec_from_file_location("stage11_delivery_control", SCRIPT)
assert SPEC and SPEC.loader
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)

WORKFLOW_DISPATCH_TOKEN_EXPRESSION = "${{ inputs.dispatch_token || github.sha }}"


def _workflow_dispatch_title(workflow: str, dispatch_token: str) -> str:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / workflow
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.startswith("run-name:")]
    if len(lines) != 1:
        raise AssertionError(f"{workflow} must declare exactly one run-name")
    template = lines[0].removeprefix("run-name: ")
    if WORKFLOW_DISPATCH_TOKEN_EXPRESSION not in template:
        raise AssertionError(f"{workflow} run-name lacks the canonical dispatch expression")
    return template.replace(WORKFLOW_DISPATCH_TOKEN_EXPRESSION, dispatch_token)


class Stage11DeliveryControlTests(unittest.TestCase):
    def test_parse_promote(self) -> None:
        command, args = CONTROL.parse_command(
            "/stage11 promote source=work/stage11-rendering "
            "source_sha=" + "a" * 40 + " "
            "target=codex/stage11-rendering base_sha=" + "b" * 40
        )
        self.assertEqual(command, "promote")
        self.assertEqual(args["source"], "work/stage11-rendering")

    def test_parse_rejects_duplicate_argument(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.parse_command("/stage11 merge head_sha=x head_sha=y base_sha=z")

    def test_parse_rejects_unknown_command(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.parse_command("/stage11 force head_sha=x")

    def test_sha_requires_exact_lowercase_40_hex(self) -> None:
        self.assertEqual(CONTROL._require_sha("a" * 40, "x"), "a" * 40)
        for value in ("a" * 39, "A" * 40, "g" * 40, "a" * 41):
            with self.subTest(value=value):
                with self.assertRaises(CONTROL.ControlError):
                    CONTROL._require_sha(value, "x")

    def test_promotion_rejects_traversal(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.validate_promote_paths(["../escape.txt"])

    def test_promotion_rejects_trusted_control_paths(self) -> None:
        for path in sorted(CONTROL.FORBIDDEN_PROMOTION_PATHS):
            with self.subTest(path=path):
                with self.assertRaises(CONTROL.ControlError):
                    CONTROL.validate_promote_paths([path])

    def test_promotion_rejects_all_workflow_changes(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.validate_promote_paths([".github/workflows/stage11.yml"])

    def test_promotion_accepts_stage11_product_paths(self) -> None:
        CONTROL.validate_promote_paths(
            [
                "lukart_work/rendering/service.py",
                "tests/test_stage11.py",
                "lukart_work/rendering/contracts.py",
            ]
        )

    def test_dispatch_candidate_checks_binds_exact_sha_and_stage_branch(self) -> None:
        branch = "codex/stage11-rendering-engine"
        sha = "a" * 40
        token = "e" * 32
        calls = []
        posted = set()
        run_ids = {"stage02.yml": 101, "stage11-assurance.yml": 102}

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "POST" and path.endswith("/dispatches"):
                workflow = path.split("/")[3]
                posted.add(workflow)
                return None
            if method == "GET" and "/runs?" in path:
                workflow = path.split("/")[3]
                if workflow not in posted:
                    return {"workflow_runs": []}
                return {
                    "workflow_runs": [
                        {
                            "id": run_ids[workflow],
                            "display_title": _workflow_dispatch_title(workflow, token),
                            "event": "workflow_dispatch",
                            "head_sha": sha,
                            "head_branch": branch,
                            "path": f".github/workflows/{workflow}",
                        }
                    ]
                }
            raise AssertionError((method, path, payload))

        with patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL, "_ref", return_value={"object": {"sha": sha}}), \
                patch.object(CONTROL.secrets, "token_hex", return_value=token):
            result = CONTROL.dispatch_candidate_checks(branch, sha)

        self.assertEqual(result, run_ids)
        dispatches = [call for call in calls if call[0] == "POST"]
        self.assertEqual(len(dispatches), 2)
        for _, path, payload in dispatches:
            self.assertTrue(path.endswith("/dispatches"))
            self.assertEqual(payload["ref"], branch)
            self.assertEqual(payload["inputs"]["candidate_sha"], sha)
            self.assertEqual(payload["inputs"]["dispatch_token"], token)

    def test_dispatch_candidate_checks_rejects_untrusted_ref_or_sha(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.dispatch_candidate_checks("main", "a" * 40)
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.dispatch_candidate_checks(
                "codex/stage11-rendering-engine",
                "A" * 40,
            )

    def test_dispatch_candidate_checks_rejects_moved_candidate_branch(self) -> None:
        with patch.object(CONTROL, "_ref", return_value={"object": {"sha": "b" * 40}}), \
                patch.object(CONTROL.secrets, "token_hex", return_value="e" * 32):
            with self.assertRaisesRegex(
                CONTROL.ControlError,
                "candidate branch moved",
            ):
                CONTROL.dispatch_candidate_checks(
                    "codex/stage11-rendering-engine",
                    "a" * 40,
                )

    def test_check_gate_binds_required_workflows_to_exact_sha_and_event(self) -> None:
        sha = "a" * 40
        branch = "codex/stage11-rendering-engine"
        original_api = CONTROL.api

        def fake_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {
                            "name": "validation",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                        },
                        {
                            "name": "stage11-rendering",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                        },
                        {
                            "name": "control",
                            "status": "in_progress",
                            "conclusion": None,
                            "app": {"slug": "github-actions"},
                        },
                        {
                            "name": "stage11-rendering",
                            "status": "completed",
                            "conclusion": "failure",
                            "app": {"slug": "github-actions"},
                        },
                    ]
                }
            if path == (
                f"/actions/runs?head_sha={sha}"
                "&event=workflow_dispatch&per_page=100"
            ):
                return {
                    "workflow_runs": [
                        {
                            "path": ".github/workflows/stage02.yml",
                            "event": "workflow_dispatch",
                            "head_sha": sha,
                            "head_branch": branch,
                            "status": "completed",
                            "conclusion": "success",
                        },
                        {
                            "path": ".github/workflows/stage11-assurance.yml",
                            "event": "workflow_dispatch",
                            "head_sha": sha,
                            "head_branch": branch,
                            "status": "completed",
                            "conclusion": "success",
                        },
                    ]
                }
            raise AssertionError(path)

        CONTROL.api = fake_api
        try:
            CONTROL._check_gate(sha, required_event="workflow_dispatch", expected_branch=branch)
        finally:
            CONTROL.api = original_api

    def test_check_gate_rejects_untrusted_or_wrong_provenance(self) -> None:
        sha = "a" * 40
        branch = "codex/stage11-rendering-engine"
        original_api = CONTROL.api

        def fake_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {
                            "name": "validation",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "untrusted-check-producer"},
                        },
                        {
                            "name": "stage11-rendering",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                        },
                    ]
                }
            return {"workflow_runs": []}

        CONTROL.api = fake_api
        try:
            with self.assertRaisesRegex(
                CONTROL.ControlError,
                "required trusted GitHub Actions checks",
            ):
                CONTROL._check_gate(sha, required_event="workflow_dispatch", expected_branch=branch)
        finally:
            CONTROL.api = original_api

        def fake_wrong_event_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {
                            "name": "validation",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                        },
                        {
                            "name": "stage11-rendering",
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                        },
                    ]
                }
            return {
                "workflow_runs": [
                    {
                        "path": ".github/workflows/stage02.yml",
                        "event": "pull_request",
                        "head_sha": sha,
                        "head_branch": branch,
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {
                        "path": ".github/workflows/stage11-assurance.yml",
                        "event": "pull_request",
                        "head_sha": sha,
                        "head_branch": branch,
                        "status": "completed",
                        "conclusion": "success",
                    },
                ]
            }

        CONTROL.api = fake_wrong_event_api
        try:
            with self.assertRaisesRegex(
                CONTROL.ControlError,
                "workflow provenance",
            ):
                CONTROL._check_gate(sha, required_event="workflow_dispatch", expected_branch=branch)
        finally:
            CONTROL.api = original_api

        def fake_wrong_branch_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {"name": "validation", "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
                        {"name": "stage11-rendering", "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
                    ]
                }
            return {
                "workflow_runs": [
                    {"path": ".github/workflows/stage02.yml", "event": "workflow_dispatch", "head_sha": sha,
                     "head_branch": "codex/stage11-other", "status": "completed", "conclusion": "success"},
                    {"path": ".github/workflows/stage11-assurance.yml", "event": "workflow_dispatch", "head_sha": sha,
                     "head_branch": "codex/stage11-other", "status": "completed", "conclusion": "success"},
                ]
            }

        CONTROL.api = fake_wrong_branch_api
        try:
            with self.assertRaisesRegex(CONTROL.ControlError, "workflow provenance"):
                CONTROL._check_gate(sha, required_event="workflow_dispatch", expected_branch=branch)
        finally:
            CONTROL.api = original_api

        def fake_exact_failure_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {"name": "validation", "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
                        {"name": "stage11-rendering", "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
                    ]
                }
            return {
                "workflow_runs": [
                    {"path": ".github/workflows/stage02.yml", "event": "workflow_dispatch", "head_sha": sha,
                     "head_branch": branch, "status": "completed", "conclusion": "failure"},
                    {"path": ".github/workflows/stage11-assurance.yml", "event": "workflow_dispatch", "head_sha": sha,
                     "head_branch": branch, "status": "completed", "conclusion": "success"},
                ]
            }

        CONTROL.api = fake_exact_failure_api
        try:
            with self.assertRaisesRegex(CONTROL.ControlError, "workflow provenance"):
                CONTROL._check_gate(sha, required_event="workflow_dispatch", expected_branch=branch)
        finally:
            CONTROL.api = original_api

    def test_check_gate_paginates_and_rejects_failure_on_second_page(self) -> None:
        sha = "a" * 40
        branch = "codex/stage11-rendering-engine"
        actions_path = (
            f"/actions/runs?head_sha={sha}"
            "&event=workflow_dispatch&per_page=100"
        )
        first_page = [
            {
                "path": ".github/workflows/stage02.yml" if index % 2 == 0
                        else ".github/workflows/stage11-assurance.yml",
                "event": "workflow_dispatch",
                "head_sha": sha,
                "head_branch": branch,
                "status": "completed",
                "conclusion": "success",
            }
            for index in range(100)
        ]

        def fake_api(method, path, payload=None):
            if path == f"/commits/{sha}/check-runs?per_page=100":
                return {
                    "check_runs": [
                        {"name": "validation", "status": "completed", "conclusion": "success",
                         "app": {"slug": "github-actions"}},
                        {"name": "stage11-rendering", "status": "completed", "conclusion": "success",
                         "app": {"slug": "github-actions"}},
                    ]
                }
            if path == actions_path:
                return {"workflow_runs": first_page}
            if path == actions_path + "&page=2":
                return {
                    "workflow_runs": [{
                        "path": ".github/workflows/stage02.yml",
                        "event": "workflow_dispatch",
                        "head_sha": sha,
                        "head_branch": branch,
                        "status": "completed",
                        "conclusion": "failure",
                    }]
                }
            raise AssertionError(path)

        with patch.object(CONTROL, "api", side_effect=fake_api):
            with self.assertRaisesRegex(CONTROL.ControlError, "workflow provenance"):
                CONTROL._check_gate(
                    sha,
                    required_event="workflow_dispatch",
                    expected_branch=branch,
                )

    def test_workflow_dispatch_run_listing_paginates(self) -> None:
        workflow = "stage02.yml"
        first_path = (
            "/actions/workflows/stage02.yml/runs"
            "?event=workflow_dispatch&per_page=100"
        )
        first_page = [{"id": index + 1} for index in range(100)]

        def fake_api(method, path, payload=None):
            if path == first_path:
                return {"workflow_runs": first_page}
            if path == first_path + "&page=2":
                return {"workflow_runs": [{"id": 101}]}
            raise AssertionError(path)

        with patch.object(CONTROL, "api", side_effect=fake_api):
            runs = CONTROL._workflow_dispatch_runs(workflow)
        self.assertEqual([run["id"] for run in runs], list(range(1, 102)))

    def test_promotion_preserves_target_when_ci_dispatch_fails(self) -> None:
        source_sha = "a" * 40
        base_sha = "b" * 40
        promoted_sha = "c" * 40
        source = "work/stage11-rendering-engine"
        target = "codex/stage11-rendering-engine"
        api_calls = []

        originals = {
            "_ref": CONTROL._ref,
            "api": CONTROL.api,
            "_commit": CONTROL._commit,
            "_tree_map": CONTROL._tree_map,
            "_blob_bytes": CONTROL._blob_bytes,
            "graphql": CONTROL.graphql,
            "dispatch_candidate_checks": CONTROL.dispatch_candidate_checks,
            "_post_comment": CONTROL._post_comment,
            "_procedure_identity": CONTROL._procedure_identity,
            "_repo": CONTROL._repo,
        }

        def fake_ref(branch):
            if branch == source:
                return {"object": {"sha": source_sha}}
            if branch == target:
                return None
            if branch == "main":
                return {"object": {"sha": base_sha}}
            raise AssertionError(branch)

        def fake_api(method, path, payload=None):
            api_calls.append((method, path, payload))
            if method == "GET" and path == f"/compare/{base_sha}...{source_sha}":
                return {
                    "behind_by": 0,
                    "ahead_by": 1,
                    "files": [
                        {
                            "filename": "lukart_work/rendering/service.py",
                            "status": "modified",
                        }
                    ],
                }
            return None

        def fake_commit(sha):
            if sha == source_sha:
                return {"commit": {"tree": {"sha": "tree-1"}}}
            if sha == promoted_sha:
                return {
                    "commit": {
                        "tree": {"sha": "tree-1"},
                        "verification": {"verified": True},
                    }
                }
            raise AssertionError(sha)

        try:
            CONTROL._ref = fake_ref
            CONTROL._repo = lambda: "owner/repo"
            CONTROL.api = fake_api
            CONTROL._commit = fake_commit
            CONTROL._tree_map = lambda commit: {
                "lukart_work/rendering/service.py": {
                    "sha": "blob-1",
                    "mode": "100644",
                }
            }
            CONTROL._blob_bytes = lambda blob_sha: b"content"
            CONTROL.graphql = lambda query, variables: {
                "createCommitOnBranch": {"commit": {"oid": promoted_sha}}
            }
            CONTROL.dispatch_candidate_checks = lambda branch, sha: (_ for _ in ()).throw(
                CONTROL.ControlError("dispatch failed")
            )
            CONTROL._post_comment = lambda issue_number, body: (_ for _ in ()).throw(
                AssertionError("promotion receipt must not be posted")
            )
            CONTROL._procedure_identity = lambda: ("policy", "procedure")

            with self.assertRaisesRegex(CONTROL.ControlError, "dispatch failed"):
                CONTROL.promote(
                    123,
                    {
                        "source": source,
                        "source_sha": source_sha,
                        "target": target,
                        "base_sha": base_sha,
                    },
                )
        finally:
            for name, value in originals.items():
                setattr(CONTROL, name, value)

        target_ref = "heads%2Fcodex%2Fstage11-rendering-engine"
        self.assertFalse(any(
            method in {"PATCH", "DELETE"} and path == f"/git/refs/{target_ref}"
            for method, path, payload in api_calls
        ))
        self.assertFalse(
            any(
                method == "PATCH"
                and path == "/git/refs/heads%2Fwork%2Fstage11-rendering-engine"
                for method, path, payload in api_calls
            )
        )

    def test_stage11_control_bootstrap_uses_pinned_checkout_without_bearer_git_auth(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "stage11-control.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            text,
        )
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("runs-on: [self-hosted, Linux, X64, lukart-stage11]", text)
        self.assertNotIn("runs-on: ubuntu-", text)
        self.assertNotIn("AUTHORIZATION: bearer", text)
        self.assertNotIn("git remote add origin", text)
        self.assertNotIn("git -c http.extraheader=", text)

    def test_required_assurance_workflows_have_exact_sha_dispatch_guards(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in (
            root / ".github" / "workflows" / "stage02.yml",
            root / ".github" / "workflows" / "stage11-assurance.yml",
        ):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("workflow_dispatch:", text)
                self.assertIn("candidate_sha:", text)
                self.assertIn("dispatch_token:", text)
                run_name_lines = [line.strip() for line in text.splitlines() if line.startswith("run-name:")]
                self.assertEqual(run_name_lines, [CONTROL.DISPATCH_RUN_NAME_WORKFLOW])
                self.assertEqual(
                    _workflow_dispatch_title(path.name, "e" * 32),
                    CONTROL._dispatch_run_title("e" * 32),
                )
                drifted = text.replace(
                    CONTROL.DISPATCH_RUN_NAME_WORKFLOW,
                    "run-name: stage11-other-${{ inputs.dispatch_token || github.sha }}",
                    1,
                )
                drifted_line = [
                    line.strip() for line in drifted.splitlines() if line.startswith("run-name:")
                ]
                self.assertEqual(len(drifted_line), 1)
                drifted_title = drifted_line[0].removeprefix("run-name: ").replace(
                    WORKFLOW_DISPATCH_TOKEN_EXPRESSION,
                    "e" * 32,
                )
                self.assertNotEqual(drifted_title, CONTROL._dispatch_run_title("e" * 32))
                with patch.object(
                    CONTROL,
                    "_workflow_dispatch_runs",
                    return_value=[{
                        "id": 901,
                        "display_title": drifted_title,
                        "event": "workflow_dispatch",
                        "head_sha": "c" * 40,
                        "head_branch": "codex/stage11-test",
                        "path": f".github/workflows/{path.name}",
                    }],
                ):
                    with self.assertRaisesRegex(CONTROL.ControlError, "did not materialize"):
                        CONTROL._wait_for_bound_dispatch_run(
                            path.name,
                            "codex/stage11-test",
                            "c" * 40,
                            "e" * 32,
                            set(),
                            attempts=1,
                            interval_seconds=0,
                        )
                self.assertIn("Resolve exact tested source", text)
                self.assertIn("ref: ${{ steps.source.outputs.sha }}", text)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("Assert exact tested source", text)
                self.assertIn('[[ "${EVENT_SHA}" == "${sha}" ]]', text)


    def test_dispatch_run_correlation_fail_closed_matrix(self) -> None:
        branch = "codex/stage11-test"
        sha = "c" * 40
        token = "e" * 32
        workflow = "stage02.yml"
        canonical = {
            "id": 101,
            "display_title": _workflow_dispatch_title(workflow, token),
            "event": "workflow_dispatch",
            "head_sha": sha,
            "head_branch": branch,
            "path": ".github/workflows/stage02.yml",
        }

        def wait(runs, baseline_ids=frozenset()):
            with patch.object(CONTROL, "_workflow_dispatch_runs", return_value=runs):
                return CONTROL._wait_for_bound_dispatch_run(
                    workflow,
                    branch,
                    sha,
                    token,
                    set(baseline_ids),
                    attempts=1,
                    interval_seconds=0,
                )

        self.assertEqual(wait([canonical]), 101)

        rejected = (
            ("baseline_same_sha_and_token", [canonical], {101}, "did not materialize"),
            (
                "wrong_correlation_token",
                [canonical | {"id": 102, "display_title": _workflow_dispatch_title(workflow, "f" * 32)}],
                set(),
                "did not materialize",
            ),
            (
                "wrong_workflow_path",
                [canonical | {"id": 102, "path": ".github/workflows/stage11-assurance.yml"}],
                set(),
                "wrong source",
            ),
            (
                "wrong_event",
                [canonical | {"id": 102, "event": "push"}],
                set(),
                "did not materialize",
            ),
            (
                "wrong_branch",
                [canonical | {"id": 102, "head_branch": "codex/stage11-other"}],
                set(),
                "wrong source",
            ),
            (
                "wrong_head_sha",
                [canonical | {"id": 102, "head_sha": "d" * 40}],
                set(),
                "wrong source",
            ),
            ("no_materialized_run", [], set(), "did not materialize"),
            (
                "ambiguous_two_correlated_runs",
                [canonical, canonical | {"id": 102}],
                set(),
                "ambiguous correlated",
            ),
        )
        for name, runs, baseline, pattern in rejected:
            with self.subTest(name=name):
                with self.assertRaisesRegex(CONTROL.ControlError, pattern):
                    wait(runs, baseline)


class P1RegressionTests(unittest.TestCase):
    SHA = "a" * 40
    BASE = "b" * 40
    OWNER = {"id": 123, "login": "owner", "type": "User"}

    def receipt(self):
        return {
            "user": dict(self.OWNER), "author_association": "OWNER",
            "performed_via_github_app": None,
            "body": f"STAGE11_INDEPENDENT_REVIEW: PASS\nsha={self.SHA}\n"
                    f"base_sha={self.BASE}\np0=0\np1=0\nmerge=NOT_PERFORMED",
        }

    def accepted(self, receipt):
        return CONTROL._has_independent_review([receipt], self.SHA, self.BASE, self.OWNER)

    def test_receipt_accepts_only_exact_structured_owner_attestation(self):
        self.assertTrue(self.accepted(self.receipt()))

    def test_receipt_rejects_untrusted_author_and_identity_spoofing(self):
        for change in (
            {"user": {"id": 456, "login": "attacker", "type": "User"}},
            {"user": {"id": 456, "login": "owner", "type": "User"}},
            {"user": {"id": 123, "login": "attacker", "type": "User"}},
            {"user": {"id": 123, "login": "owner", "type": "Bot"}},
            {"user": None}, {"user": {}}, {"author_association": "CONTRIBUTOR"},
            {"performed_via_github_app": {"slug": "untrusted-app"}},
        ):
            with self.subTest(change=change):
                self.assertFalse(self.accepted(self.receipt() | change))
        self.assertFalse(CONTROL._has_independent_review([self.receipt()], self.SHA, self.BASE, {}))

    def test_receipt_rejects_wrong_sha_base_and_nonzero_findings(self):
        body = self.receipt()["body"]
        for old, new in ((self.SHA, "c" * 40), (self.BASE, "c" * 40),
                         ("p0=0", "p0=1"), ("p1=0", "p1=3")):
            with self.subTest(new=new):
                self.assertFalse(self.accepted(self.receipt() | {"body": body.replace(old, new)}))

    def test_receipt_rejects_malformed_duplicate_and_substring_collisions(self):
        body = self.receipt()["body"]
        malformed = [
            None, 123, "", body + "\np1=0", body + "\np1=3", body + f"\nsha={self.SHA}",
            body + f"\nbase_sha={self.BASE}", body + "\np0=0", body + "\nunknown=value",
            body.replace("p1=0", "p1=00"), body.replace("p1=0", "p1=0 extra"),
            body.replace("p1=0\n", ""), body.replace("p1=0", "p1:0"),
            body.replace("sha=", "untrusted_sha="),
            body.replace(self.SHA, self.SHA + "0"), body.replace(self.BASE, "0" + self.BASE),
            body.replace("PASS", "PASS_WITH_FINDINGS"), body.replace("\np0=", "\n p0="),
            body.replace("p1=0", "p1=1\nnote=p1=0"),
            body.replace("merge=NOT_PERFORMED", "merge=PERFORMED"),
            body + "\n\n", "```\n" + body + "\n```",
        ]
        for value in malformed:
            with self.subTest(body=value):
                self.assertFalse(self.accepted(self.receipt() | {"body": value}))

    def test_merge_rejects_invalid_receipt_before_merge_api(self):
        pr = {"state": "open", "draft": False, "base": {"ref": "main", "sha": self.BASE},
              "head": {"ref": "codex/stage11-rendering", "sha": self.SHA}}
        for receipt in (self.receipt() | {"user": {}},
                        self.receipt() | {"body": self.receipt()["body"].replace(self.BASE, "d" * 40)}):
            with self.subTest(receipt=receipt), patch.object(CONTROL, "_pr_from_event", return_value=pr), \
                    patch.object(CONTROL, "_commit", return_value={"commit": {"verification": {"verified": True}}}), \
                    patch.object(CONTROL, "_check_gate"), patch.object(CONTROL, "_comments", return_value=[receipt]), \
                    patch.object(CONTROL, "api", return_value={"owner": self.OWNER}) as api:
                with self.assertRaisesRegex(CONTROL.ControlError, "review"):
                    CONTROL.merge({}, 17, {"head_sha": self.SHA, "base_sha": self.BASE})
                self.assertEqual(api.call_args_list, [unittest.mock.call("GET", "")])

    def test_stage11_missing_tests_fail_closed_for_ordinary_branches(self):
        for branch in ("codex/stage11-rendering", "codex/stage11-postmerge-assurance-remediation-verified",
                       "codex/stage11-procedure-bootstrap-pr15-copy"):
            with self.subTest(branch=branch), self.assertRaises(CONTROL.ControlError):
                CONTROL.require_stage11_tests(branch, False, base_sha=CONTROL.PROCEDURE_BOOTSTRAP_BASE,
                                             changed_paths=list(CONTROL.PROCEDURE_BOOTSTRAP_PATHS))

    def test_stage11_bootstrap_exception_requires_exact_base_and_procedure_only_diff(self):
        branch = CONTROL.PROCEDURE_BOOTSTRAP_BRANCH
        base = CONTROL.PROCEDURE_BOOTSTRAP_BASE
        paths = list(CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        files = [{"filename": path, "status": "modified"} for path in paths]
        self.assertEqual(len(paths), 10)
        self.assertIn(".github/workflows/stage02.yml", CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        self.assertIn(".github/workflows/stage11-assurance.yml", CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        self.assertIn(".github/workflows/stage11-control.yml", CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        self.assertIn("lukart_work/ingestion/service.py", CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        self.assertIn("tests/test_stage04.py", CONTROL.PROCEDURE_BOOTSTRAP_PATHS)
        self.assertEqual(CONTROL.require_stage11_tests(branch, False, base_sha=base,
                         changed_paths=paths), "PROCEDURE_ONLY_BOOTSTRAP")
        self.assertEqual(CONTROL.require_stage11_tests("main", False, base_sha=base,
                         changed_paths=paths), "PROCEDURE_ONLY_BOOTSTRAP")
        self.assertEqual(
            CONTROL.validate_landing_paths(branch, base, files, paths),
            "PROCEDURE_ONLY_BOOTSTRAP",
        )
        self.assertEqual(
            CONTROL.validate_landing_paths(
                "codex/stage11-product", self.BASE,
                [{"filename": "product.py", "status": "modified"}], ["product.py"],
            ),
            "STANDARD",
        )
        workflow = (SCRIPT.parents[1] / ".github/workflows/stage11-assurance.yml").read_text(encoding="utf-8")
        self.assertIn('branch in (PROCEDURE_BOOTSTRAP_BRANCH, "main")', workflow)
        self.assertIn('lineage[1:] != [PROCEDURE_BOOTSTRAP_BASE]', workflow)
        self.assertIn('"--name-status"', workflow)
        self.assertIn('status != "M"', workflow)
        self.assertIn("direct child of the exact bootstrap base", workflow)

        for wrong_base, changed in (
            (self.BASE, paths),
            (base, []),
            (base, ["lukart_work/rendering/service.py"]),
            (base, ["tests/test_stage11.py"]),
            (base, ["AGENTS.md"]),
            (base, paths[:-1]),
        ):
            with self.subTest(base=wrong_base, paths=changed), self.assertRaises(CONTROL.ControlError):
                CONTROL.require_stage11_tests(branch, False, base_sha=wrong_base, changed_paths=changed)
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.require_stage11_tests("main", False, base_sha=base, changed_paths=[])
        for bad_branch, bad_base, bad_files, bad_paths in (
            ("codex/stage11-other", base, files, paths),
            (branch, self.BASE, files, paths),
            (branch, base, files[:-1], paths[:-1]),
            (branch, base, files + [{"filename": "product.py", "status": "modified"}], paths + ["product.py"]),
            (branch, base, [dict(files[0], status="removed")] + files[1:], paths),
        ):
            with self.subTest(branch=bad_branch, base=bad_base), self.assertRaises(CONTROL.ControlError):
                CONTROL.validate_landing_paths(bad_branch, bad_base, bad_files, bad_paths)
        self.assertEqual(CONTROL.require_stage11_tests(branch, True), "RENDERING_TESTS_REQUIRED")

        bootstrap_sha = "e" * 40
        candidate_commit = {"commit": {"verification": {"verified": True}}}
        compare = {"behind_by": 0, "ahead_by": 1, "files": files}
        with patch.object(CONTROL, "_assert_ref_sha") as assert_ref, \
                patch.object(CONTROL, "_commit", return_value=candidate_commit), \
                patch.object(CONTROL, "api", return_value=compare), \
                patch.object(CONTROL, "_check_gate") as gate:
            CONTROL.check_procedure_bootstrap_candidate(branch, bootstrap_sha, base)
        assert_ref.assert_called_once_with(branch, bootstrap_sha, "during procedure bootstrap gate")
        gate.assert_called_once_with(bootstrap_sha, required_event="push", expected_branch=branch)

        for bad_branch, bad_base in (("codex/stage11-other", base), (branch, self.BASE)):
            with self.subTest(bootstrap_branch=bad_branch, bootstrap_base=bad_base), \
                    self.assertRaises(CONTROL.ControlError):
                CONTROL.check_procedure_bootstrap_candidate(bad_branch, bootstrap_sha, bad_base)

    def test_actual_workflow_step_rejects_missing_empty_skipped_and_failed_tests(self):
        workflow = (SCRIPT.parents[1] / ".github/workflows/stage11-assurance.yml").read_text(encoding="utf-8")
        code = textwrap.dedent(workflow.split("python -B -X utf8 - <<'PY'\n", 1)[1].split("          PY", 1)[0])
        cases = [
            (None, False), ("", False),
            ("import unittest\nclass T(unittest.TestCase):\n @unittest.skip('missing evidence')\n def test_x(self): pass\n", False),
            ("import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.fail('regression')\n", False),
            ("import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.assertEqual(1, 1)\n", True),
        ]
        for content, success in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts").mkdir()
                (root / "scripts/stage11_delivery_control.py").write_bytes(SCRIPT.read_bytes())
                (root / "tests").mkdir()
                (root / "tests/__init__.py").write_text("", encoding="utf-8")
                if content is not None:
                    (root / "tests/test_stage11.py").write_text(content, encoding="utf-8")
                env = dict(os.environ, REF_NAME="codex/stage11-rendering", PR_HEAD_REF="")
                result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code],
                                        cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)

    def test_dispatch_binding_rejects_target_movement_before_between_and_after_dispatches(self):
        branch = "codex/stage11-test"
        sha = "c" * 40
        newer = "d" * 40
        token = "e" * 32
        workflows = ("stage02.yml", "stage11-assurance.yml")

        for race in ("before_first", "between_dispatches", "after_second"):
            with self.subTest(race=race):
                refs = {branch: sha}
                posted = set()
                get_counts = {workflow: 0 for workflow in workflows}

                def fake_ref(name):
                    return {"object": {"sha": refs[name]}} if name in refs else None

                def fake_api(method, path, payload=None):
                    if method == "POST" and path.endswith("/dispatches"):
                        workflow = path.split("/")[3]
                        posted.add(workflow)
                        return None
                    if method == "GET" and "/runs?" in path:
                        workflow = path.split("/")[3]
                        get_counts[workflow] += 1
                        if race == "before_first" and workflow == workflows[0] and get_counts[workflow] == 1:
                            refs[branch] = newer
                        if workflow not in posted:
                            return {"workflow_runs": []}
                        run = {
                            "id": 100 + workflows.index(workflow),
                            "display_title": _workflow_dispatch_title(workflow, token),
                            "event": "workflow_dispatch",
                            "head_sha": sha,
                            "head_branch": branch,
                            "path": f".github/workflows/{workflow}",
                        }
                        if race == "between_dispatches" and workflow == workflows[0]:
                            refs[branch] = newer
                        if race == "after_second" and workflow == workflows[1]:
                            refs[branch] = newer
                        return {"workflow_runs": [run]}
                    raise AssertionError((method, path, payload))

                with patch.object(CONTROL, "_ref", side_effect=fake_ref), \
                        patch.object(CONTROL, "api", side_effect=fake_api), \
                        patch.object(CONTROL.secrets, "token_hex", return_value=token):
                    with self.assertRaisesRegex(CONTROL.ControlError, "candidate branch moved"):
                        CONTROL.dispatch_candidate_checks(branch, sha)
                self.assertEqual(refs[branch], newer)

    def test_dispatch_binding_rejects_correlated_run_for_wrong_head(self):
        branch = "codex/stage11-test"
        sha = "c" * 40
        newer = "d" * 40
        token = "e" * 32
        posted = set()

        def fake_api(method, path, payload=None):
            if method == "POST" and path.endswith("/dispatches"):
                posted.add(path.split("/")[3])
                return None
            if method == "GET" and "/runs?" in path:
                workflow = path.split("/")[3]
                if workflow not in posted:
                    return {"workflow_runs": []}
                return {
                    "workflow_runs": [
                        {
                            "id": 101,
                            "display_title": _workflow_dispatch_title(workflow, token),
                            "event": "workflow_dispatch",
                            "head_sha": newer,
                            "head_branch": branch,
                            "path": f".github/workflows/{workflow}",
                        }
                    ]
                }
            raise AssertionError((method, path, payload))

        with patch.object(CONTROL, "_ref", return_value={"object": {"sha": sha}}), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL.secrets, "token_hex", return_value=token):
            with self.assertRaisesRegex(CONTROL.ControlError, "wrong source"):
                CONTROL.dispatch_candidate_checks(branch, sha)

    def test_promotion_blocks_target_move_after_dispatch_binding_before_receipt(self):
        source = "work/stage11-test"
        target = "codex/stage11-test"
        source_sha = self.SHA
        base_sha = self.BASE
        promoted_sha = "c" * 40
        newer_target = "d" * 40
        refs = {source: source_sha, target: base_sha, "main": base_sha}
        comments = []

        def fake_ref(branch):
            return {"object": {"sha": refs[branch]}} if branch in refs else None

        def fake_api(method, path, payload=None):
            if method == "GET" and path == f"/compare/{base_sha}...{source_sha}":
                return {
                    "behind_by": 0,
                    "ahead_by": 1,
                    "files": [{"filename": "product.py", "status": "added"}],
                }
            if method in {"PATCH", "DELETE"}:
                self.fail(f"unexpected destructive ref mutation: {method} {path}")
            raise AssertionError((method, path, payload))

        def fake_commit(sha):
            if sha == source_sha:
                return {"commit": {"tree": {"sha": "tree"}}}
            if sha == promoted_sha:
                return {
                    "commit": {
                        "tree": {"sha": "tree"},
                        "verification": {"verified": True},
                    }
                }
            raise AssertionError(sha)

        def fake_graphql(query, variables):
            refs[target] = promoted_sha
            return {"createCommitOnBranch": {"commit": {"oid": promoted_sha}}}

        def fake_dispatch(branch, sha):
            refs[target] = newer_target
            return {"stage02.yml": 201, "stage11-assurance.yml": 202}

        with patch.object(CONTROL, "_ref", side_effect=fake_ref), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL, "_commit", side_effect=fake_commit), \
                patch.object(CONTROL, "_tree_map", return_value={"product.py": {"sha": "blob", "mode": "100644"}}), \
                patch.object(CONTROL, "_blob_bytes", return_value=b"content"), \
                patch.object(CONTROL, "graphql", side_effect=fake_graphql), \
                patch.object(CONTROL, "dispatch_candidate_checks", side_effect=fake_dispatch), \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"):
            with self.assertRaisesRegex(CONTROL.ControlError, "candidate branch moved"):
                CONTROL.promote(
                    17,
                    {
                        "source": source,
                        "source_sha": source_sha,
                        "target": target,
                        "base_sha": base_sha,
                    },
                )

        self.assertEqual(refs[target], newer_target)
        self.assertEqual(refs[source], source_sha)
        self.assertEqual(comments, [])

    def test_promotion_never_rewrites_source_ref_after_concurrent_source_advance(self):
        source = "work/stage11-test"
        target = "codex/stage11-test"
        source_sha = self.SHA
        newer_source = "e" * 40
        base_sha = self.BASE
        promoted_sha = "c" * 40
        refs = {source: source_sha, target: base_sha, "main": base_sha}
        calls = []
        comments = []

        def fake_ref(branch):
            return {"object": {"sha": refs[branch]}} if branch in refs else None

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET" and path == f"/compare/{base_sha}...{source_sha}":
                return {
                    "behind_by": 0,
                    "ahead_by": 1,
                    "files": [{"filename": "product.py", "status": "added"}],
                }
            if method in {"PATCH", "DELETE"}:
                self.fail(f"unexpected destructive ref mutation: {method} {path}")
            raise AssertionError((method, path, payload))

        def fake_commit(sha):
            if sha == source_sha:
                return {"commit": {"tree": {"sha": "tree"}}}
            if sha == promoted_sha:
                return {
                    "commit": {
                        "tree": {"sha": "tree"},
                        "verification": {"verified": True},
                    }
                }
            raise AssertionError(sha)

        def fake_graphql(query, variables):
            self.assertEqual(variables["input"]["expectedHeadOid"], base_sha)
            refs[target] = promoted_sha
            return {"createCommitOnBranch": {"commit": {"oid": promoted_sha}}}

        def fake_dispatch(branch, sha):
            self.assertEqual((branch, sha), (target, promoted_sha))
            refs[source] = newer_source
            return {"stage02.yml": 201, "stage11-assurance.yml": 202}

        with patch.object(CONTROL, "_ref", side_effect=fake_ref), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL, "_commit", side_effect=fake_commit), \
                patch.object(CONTROL, "_tree_map", return_value={"product.py": {"sha": "blob", "mode": "100644"}}), \
                patch.object(CONTROL, "_blob_bytes", return_value=b"content"), \
                patch.object(CONTROL, "graphql", side_effect=fake_graphql), \
                patch.object(CONTROL, "dispatch_candidate_checks", side_effect=fake_dispatch), \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)), \
                patch.object(CONTROL, "_procedure_identity", return_value=("policy", "procedure")), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"):
            CONTROL.promote(
                17,
                {
                    "source": source,
                    "source_sha": source_sha,
                    "target": target,
                    "base_sha": base_sha,
                },
            )

        self.assertEqual(refs[source], newer_source)
        self.assertFalse(any(method in {"PATCH", "DELETE"} for method, _, _ in calls))
        self.assertEqual(len(comments), 1)
        self.assertTrue(comments[0].startswith("STAGE11_PROMOTION: DISPATCH_BOUND\n"))
        self.assertNotIn("STAGE11_PROMOTION: PASS", comments[0])
        self.assertIn("source_ref_mutation=NONE", comments[0])
        self.assertIn("stage02.yml:201", comments[0])
        self.assertIn("stage11-assurance.yml:202", comments[0])

    def test_promotion_failure_never_overwrites_concurrent_ref_updates(self):
        source, target = "work/stage11-test", "codex/stage11-test"
        promoted, newer = "c" * 40, "d" * 40
        token = "e" * 32
        scenario_count = 0

        for existing in (False, True):
            for failure in ("signature", "tree", "first_dispatch", "second_dispatch"):
                for concurrent in (False, True):
                    scenario_count += 1
                    with self.subTest(existing=existing, failure=failure, concurrent=concurrent):
                        refs = {source: self.SHA, "main": self.BASE}
                        if existing:
                            refs[target] = self.BASE
                        calls = []
                        events = []
                        dispatched = set()
                        bound = set()

                        def api(method, path, payload=None):
                            calls.append((method, path, payload))
                            if method == "GET" and path.startswith("/compare/"):
                                return {
                                    "behind_by": 0,
                                    "ahead_by": 1,
                                    "files": [{"filename": "product.py", "status": "added"}],
                                }
                            if method == "POST" and path == "/git/refs":
                                refs[target] = payload["sha"]
                                return None
                            if method == "GET" and "/actions/workflows/" in path and "/runs?" in path:
                                workflow = path.split("/")[3]
                                if workflow not in dispatched:
                                    return {"workflow_runs": []}
                                if workflow not in bound:
                                    bound.add(workflow)
                                    events.append(f"{workflow}:bound")
                                return {
                                    "workflow_runs": [{
                                        "id": 201 + CONTROL.CANDIDATE_WORKFLOWS.index(workflow),
                                        "display_title": _workflow_dispatch_title(workflow, token),
                                        "event": "workflow_dispatch",
                                        "head_sha": promoted,
                                        "head_branch": target,
                                        "path": f".github/workflows/{workflow}",
                                    }]
                                }
                            if method == "POST" and path.endswith("/dispatches"):
                                workflow = path.split("/")[3]
                                events.append(f"{workflow}:dispatch")
                                if failure == "first_dispatch" and workflow == "stage02.yml":
                                    if concurrent:
                                        refs[target] = newer
                                    raise CONTROL.ControlError("injected first dispatch failure")
                                if failure == "second_dispatch" and workflow == "stage11-assurance.yml":
                                    self.assertIn("stage02.yml", bound)
                                    if concurrent:
                                        refs[target] = newer
                                    raise CONTROL.ControlError("injected second dispatch failure")
                                dispatched.add(workflow)
                                return None
                            self.fail(f"unsafe/unexpected mutation: {method} {path}")

                        def commit(sha):
                            if sha == self.SHA:
                                return {"commit": {"tree": {"sha": "tree"}}}
                            if failure in {"signature", "tree"} and concurrent:
                                refs[target] = newer
                            return {
                                "commit": {
                                    "tree": {"sha": "wrong" if failure == "tree" else "tree"},
                                    "verification": {"verified": failure != "signature"},
                                }
                            }

                        def graphql(query, variables):
                            self.assertEqual(variables["input"]["expectedHeadOid"], self.BASE)
                            refs[target] = promoted
                            return {"createCommitOnBranch": {"commit": {"oid": promoted}}}

                        with patch.object(
                                CONTROL,
                                "_ref",
                                side_effect=lambda b: {"object": {"sha": refs[b]}} if b in refs else None,
                            ), patch.object(
                                CONTROL, "api", side_effect=api
                            ), patch.object(
                                CONTROL, "_commit", side_effect=commit
                            ), patch.object(
                                CONTROL, "graphql", side_effect=graphql
                            ), patch.object(
                                CONTROL,
                                "_tree_map",
                                return_value={"product.py": {"sha": "blob", "mode": "100644"}},
                            ), patch.object(
                                CONTROL, "_blob_bytes", return_value=b"content"
                            ), patch.object(
                                CONTROL.secrets, "token_hex", return_value=token
                            ), patch.object(
                                CONTROL, "_post_comment"
                            ) as comment, patch.object(
                                CONTROL, "_repo", return_value="owner/repo"
                            ):
                            with self.assertRaisesRegex(CONTROL.ControlError, "target preserved"):
                                CONTROL.promote(
                                    17,
                                    {
                                        "source": source,
                                        "target": target,
                                        "source_sha": self.SHA,
                                        "base_sha": self.BASE,
                                    },
                                )

                        if failure == "first_dispatch":
                            self.assertEqual(events, ["stage02.yml:dispatch"])
                        elif failure == "second_dispatch":
                            self.assertEqual(
                                events,
                                [
                                    "stage02.yml:dispatch",
                                    "stage02.yml:bound",
                                    "stage11-assurance.yml:dispatch",
                                ],
                            )
                            self.assertIn("stage02.yml", bound)
                            self.assertNotIn("stage11-assurance.yml", bound)
                        else:
                            self.assertEqual(events, [])

                        self.assertEqual(refs[target], newer if concurrent else promoted)
                        self.assertEqual(refs[source], self.SHA)
                        self.assertFalse(any(c[0] in {"PATCH", "DELETE"} for c in calls))
                        self.assertFalse(any(
                            c[0] == "PATCH"
                            and isinstance(c[2], dict)
                            and c[2].get("force") is True
                            for c in calls
                        ))
                        comment.assert_not_called()

        self.assertEqual(scenario_count, 16)


class PostMergeRemediationRegressionTests(unittest.TestCase):
    HEAD = "a" * 40
    BASE = "b" * 40
    LANDED = "c" * 40
    BRANCH = "codex/stage11-remediation-test"
    OWNER = {"id": 123, "login": "owner", "type": "User"}

    def review_receipt(self):
        return {
            "user": dict(self.OWNER),
            "author_association": "OWNER",
            "performed_via_github_app": None,
            "body": (
                "STAGE11_INDEPENDENT_REVIEW: PASS\n"
                f"sha={self.HEAD}\n"
                f"base_sha={self.BASE}\n"
                "p0=0\n"
                "p1=0\n"
                "merge=NOT_PERFORMED"
            ),
        }

    def pr(self, *, state="open"):
        return {
            "state": state,
            "draft": False,
            "base": {"ref": "main", "sha": self.BASE},
            "head": {"ref": self.BRANCH, "sha": self.HEAD},
            "merged": False,
        }

    def head_commit(self):
        return {
            "commit": {
                "verification": {"verified": True},
                "tree": {"sha": "candidate-tree"},
            }
        }

    def landed_commit(self):
        return {
            "commit": {
                "verification": {"verified": True},
                "tree": {"sha": "candidate-tree"},
            },
            "parents": [{"sha": self.BASE}],
        }

    def test_atomic_landing_binds_expected_base_sha_and_avoids_pr_merge_api(self):
        calls = []
        comments = []
        seen_variables = {}

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET" and path == "":
                return {"owner": dict(self.OWNER)}
            if method == "GET" and path == f"/compare/{self.BASE}...{self.HEAD}":
                return {
                    "behind_by": 0,
                    "ahead_by": 1,
                    "files": [{"filename": "product.py", "status": "modified"}],
                }
            if method == "PATCH" and path == "/pulls/17":
                self.assertEqual(payload, {"state": "closed"})
                return {"state": "closed"}
            self.fail(f"unexpected API call: {method} {path} {payload}")

        def fake_graphql(query, variables):
            seen_variables.update(variables)
            self.assertEqual(variables["input"]["expectedHeadOid"], self.BASE)
            self.assertEqual(variables["input"]["branch"]["branchName"], "main")
            return {"createCommitOnBranch": {"commit": {"oid": self.LANDED}}}

        with patch.object(CONTROL, "_pr_from_event", return_value=self.pr()), \
                patch.object(CONTROL, "_commit", side_effect=lambda sha: (
                    self.head_commit() if sha == self.HEAD else self.landed_commit()
                )), \
                patch.object(CONTROL, "_check_gate"), \
                patch.object(CONTROL, "_comments", return_value=[self.review_receipt()]), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL, "_ref", return_value={"object": {"sha": self.BASE}}), \
                patch.object(CONTROL, "_tree_map", return_value={
                    "product.py": {"sha": "blob", "mode": "100644"}
                }), \
                patch.object(CONTROL, "_blob_bytes", return_value=b"content"), \
                patch.object(CONTROL, "graphql", side_effect=fake_graphql), \
                patch.object(
                    CONTROL,
                    "dispatch_post_landing_checks",
                    return_value={"stage02.yml": 301, "stage11-assurance.yml": 302},
                ), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(CONTROL, "_procedure_identity", return_value=("policy", "procedure")), \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)):
            CONTROL.merge({}, 17, {"head_sha": self.HEAD, "base_sha": self.BASE})

        self.assertEqual(seen_variables["input"]["expectedHeadOid"], self.BASE)
        self.assertFalse(any(method == "PUT" and "/merge" in path for method, path, _ in calls))
        self.assertEqual(len(comments), 1)
        self.assertTrue(comments[0].startswith("STAGE11_LANDING: DISPATCH_BOUND\n"))
        self.assertIn("landing_mode=ATOMIC_EXPECTED_HEAD", comments[0])
        self.assertIn("stage02.yml:301", comments[0])
        self.assertIn("stage11-assurance.yml:302", comments[0])

    def test_atomic_landing_rejects_last_moment_base_drift_without_main_mutation(self):
        calls = []

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET" and path == "":
                return {"owner": dict(self.OWNER)}
            if method == "GET" and path == f"/compare/{self.BASE}...{self.HEAD}":
                return {
                    "behind_by": 0,
                    "ahead_by": 1,
                    "files": [{"filename": "product.py", "status": "modified"}],
                }
            self.fail(f"unexpected API call after CAS failure: {method} {path} {payload}")

        def fail_cas(query, variables):
            self.assertEqual(variables["input"]["expectedHeadOid"], self.BASE)
            raise CONTROL.ControlError("expectedHeadOid mismatch")

        with patch.object(CONTROL, "_pr_from_event", return_value=self.pr()), \
                patch.object(CONTROL, "_commit", return_value=self.head_commit()), \
                patch.object(CONTROL, "_check_gate"), \
                patch.object(CONTROL, "_comments", return_value=[self.review_receipt()]), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL, "_ref", return_value={"object": {"sha": self.BASE}}), \
                patch.object(CONTROL, "_tree_map", return_value={
                    "product.py": {"sha": "blob", "mode": "100644"}
                }), \
                patch.object(CONTROL, "_blob_bytes", return_value=b"content"), \
                patch.object(CONTROL, "graphql", side_effect=fail_cas), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(CONTROL, "_post_comment") as post:
            with self.assertRaisesRegex(CONTROL.ControlError, "atomic base-SHA landing failed"):
                CONTROL.merge({}, 17, {"head_sha": self.HEAD, "base_sha": self.BASE})

        self.assertFalse(any(method in {"PUT", "PATCH", "POST", "DELETE"} for method, _, _ in calls))
        post.assert_not_called()

    def test_post_landing_dispatch_binds_main_to_exact_sha(self):
        token = "e" * 32
        posted = set()
        run_ids = {"stage02.yml": 401, "stage11-assurance.yml": 402}

        def fake_api(method, path, payload=None):
            if method == "POST" and path.endswith("/dispatches"):
                workflow = path.split("/")[3]
                self.assertEqual(payload["ref"], "main")
                self.assertEqual(payload["inputs"]["candidate_sha"], self.LANDED)
                self.assertEqual(payload["inputs"]["dispatch_token"], token)
                posted.add(workflow)
                return None
            if method == "GET" and "/runs?" in path:
                workflow = path.split("/")[3]
                if workflow not in posted:
                    return {"workflow_runs": []}
                return {
                    "workflow_runs": [{
                        "id": run_ids[workflow],
                        "display_title": _workflow_dispatch_title(workflow, token),
                        "event": "workflow_dispatch",
                        "head_sha": self.LANDED,
                        "head_branch": "main",
                        "path": f".github/workflows/{workflow}",
                    }]
                }
            self.fail(f"unexpected API call: {method} {path} {payload}")

        with patch.object(CONTROL, "_ref", return_value={"object": {"sha": self.LANDED}}), \
                patch.object(CONTROL, "api", side_effect=fake_api), \
                patch.object(CONTROL.secrets, "token_hex", return_value=token):
            self.assertEqual(
                CONTROL.dispatch_post_landing_checks(self.LANDED),
                run_ids,
            )

    def test_post_landing_gate_prefers_dispatch_and_allows_complete_bootstrap_push(self):
        calls = []

        def dispatch_success(sha, *, required_event, expected_branch):
            self.assertEqual(expected_branch, "main")
            calls.append(required_event)
            if required_event == "workflow_dispatch":
                return None
            self.fail("push fallback should not be consulted after dispatch success")

        with patch.object(CONTROL, "_check_gate", side_effect=dispatch_success):
            self.assertEqual(
                CONTROL._check_post_landing_gate(self.LANDED),
                "workflow_dispatch",
            )
        self.assertEqual(calls, ["workflow_dispatch"])

        calls.clear()
        def push_fallback(sha, *, required_event, expected_branch):
            self.assertEqual(expected_branch, "main")
            calls.append(required_event)
            if required_event == "workflow_dispatch":
                raise CONTROL.ControlError("no dispatched post-landing run")
            return None

        with patch.object(CONTROL, "_check_gate", side_effect=push_fallback):
            self.assertEqual(CONTROL._check_post_landing_gate(self.LANDED), "push")
        self.assertEqual(calls, ["workflow_dispatch", "push"])

    def test_cleanup_is_non_destructive_and_does_not_require_source_sha_identity(self):
        main_sha = self.LANDED
        refs_seen = []
        comments = []

        def fake_ref(branch):
            refs_seen.append(branch)
            if branch == "main":
                return {"object": {"sha": main_sha}}
            if branch == self.BRANCH:
                return {"object": {"sha": self.HEAD}}
            self.fail(f"cleanup consulted unrelated source ref: {branch}")

        def fake_commit(sha):
            if sha == main_sha:
                return self.landed_commit()
            if sha == self.HEAD:
                return self.head_commit()
            self.fail(f"unexpected commit lookup: {sha}")

        closed_pr = self.pr(state="closed")
        with patch.object(CONTROL, "_pr_from_event", return_value=closed_pr), \
                patch.object(CONTROL, "_ref", side_effect=fake_ref), \
                patch.object(CONTROL, "_commit", side_effect=fake_commit), \
                patch.object(CONTROL, "_check_gate"), \
                patch.object(CONTROL, "_comments") as receipt_input, \
                patch.object(CONTROL, "_procedure_identity", return_value=("policy", "procedure")), \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)), \
                patch.object(CONTROL, "api") as api:
            with self.assertRaisesRegex(CONTROL.ControlError, "expected base SHA"):
                CONTROL.cleanup(
                    {},
                    17,
                    {"branch": self.BRANCH, "branch_sha": self.HEAD, "main_sha": main_sha, "base_sha": "d" * 40},
                )
            CONTROL.cleanup(
                {},
                17,
                {"branch": self.BRANCH, "branch_sha": self.HEAD, "main_sha": main_sha, "base_sha": self.BASE},
            )

        receipt_input.assert_not_called()
        api.assert_not_called()
        self.assertNotIn("work/stage11-remediation-test", refs_seen)
        self.assertEqual(len(comments), 2)
        self.assertTrue(comments[0].startswith("STAGE11_POST_MERGE_VERIFICATION: PASS\n"))
        self.assertIn("ref_disposition=PRESERVED_NO_CAS_DELETE", comments[1])
        self.assertIn("source_ref_mutation=NONE", comments[1])

    def test_cleanup_rechecks_head_after_assurance_and_never_deletes_newer_ref(self):
        main_sha = self.LANDED
        newer = "d" * 40
        counts = {"main": 0, self.BRANCH: 0}
        comments = []

        def fake_ref(branch):
            counts[branch] += 1
            if branch == "main":
                return {"object": {"sha": main_sha}}
            if branch == self.BRANCH:
                sha = self.HEAD if counts[branch] == 1 else newer
                return {"object": {"sha": sha}}
            self.fail(f"unexpected ref: {branch}")

        def fake_commit(sha):
            if sha == main_sha:
                return self.landed_commit()
            if sha == self.HEAD:
                return self.head_commit()
            self.fail(f"unexpected commit: {sha}")

        with patch.object(CONTROL, "_pr_from_event", return_value=self.pr(state="closed")), \
                patch.object(CONTROL, "_ref", side_effect=fake_ref), \
                patch.object(CONTROL, "_commit", side_effect=fake_commit), \
                patch.object(CONTROL, "_check_gate"), \
                patch.object(CONTROL, "_comments") as receipt_input, \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)), \
                patch.object(CONTROL, "api") as api:
            with self.assertRaisesRegex(CONTROL.ControlError, "candidate branch moved"):
                CONTROL.cleanup(
                    {},
                    17,
                    {"branch": self.BRANCH, "branch_sha": self.HEAD, "main_sha": main_sha, "base_sha": self.BASE},
                )

        receipt_input.assert_not_called()
        api.assert_not_called()
        self.assertEqual(comments, [])
        self.assertEqual(counts[self.BRANCH], 2)



if __name__ == "__main__":
    unittest.main()
