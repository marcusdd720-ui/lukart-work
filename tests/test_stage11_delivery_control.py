from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage11_delivery_control.py"
SPEC = importlib.util.spec_from_file_location("stage11_delivery_control", SCRIPT)
assert SPEC and SPEC.loader
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


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
        calls = []
        original_api = CONTROL.api
        original_ref = CONTROL._ref

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            return None

        CONTROL.api = fake_api
        CONTROL._ref = lambda branch: {"object": {"sha": "a" * 40}}
        try:
            CONTROL.dispatch_candidate_checks(
                "codex/stage11-rendering-engine",
                "a" * 40,
            )
        finally:
            CONTROL.api = original_api
            CONTROL._ref = original_ref

        self.assertEqual(
            calls,
            [
                (
                    "POST",
                    "/actions/workflows/stage02.yml/dispatches",
                    {
                        "ref": "codex/stage11-rendering-engine",
                        "inputs": {"candidate_sha": "a" * 40},
                    },
                ),
                (
                    "POST",
                    "/actions/workflows/stage11-assurance.yml/dispatches",
                    {
                        "ref": "codex/stage11-rendering-engine",
                        "inputs": {"candidate_sha": "a" * 40},
                    },
                ),
            ],
        )

    def test_dispatch_candidate_checks_rejects_untrusted_ref_or_sha(self) -> None:
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.dispatch_candidate_checks("main", "a" * 40)
        with self.assertRaises(CONTROL.ControlError):
            CONTROL.dispatch_candidate_checks(
                "codex/stage11-rendering-engine",
                "A" * 40,
            )

    def test_dispatch_candidate_checks_rejects_moved_candidate_branch(self) -> None:
        original_ref = CONTROL._ref
        CONTROL._ref = lambda branch: {"object": {"sha": "b" * 40}}
        try:
            with self.assertRaisesRegex(
                CONTROL.ControlError,
                "candidate branch moved",
            ):
                CONTROL.dispatch_candidate_checks(
                    "codex/stage11-rendering-engine",
                    "a" * 40,
                )
        finally:
            CONTROL._ref = original_ref

    def test_check_gate_binds_required_workflows_to_exact_sha_and_event(self) -> None:
        sha = "a" * 40
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
                            "status": "completed",
                            "conclusion": "success",
                        },
                        {
                            "path": ".github/workflows/stage11-assurance.yml",
                            "event": "workflow_dispatch",
                            "head_sha": sha,
                            "status": "completed",
                            "conclusion": "success",
                        },
                    ]
                }
            raise AssertionError(path)

        CONTROL.api = fake_api
        try:
            CONTROL._check_gate(sha, required_event="workflow_dispatch")
        finally:
            CONTROL.api = original_api

    def test_check_gate_rejects_untrusted_or_wrong_provenance(self) -> None:
        sha = "a" * 40
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
                CONTROL._check_gate(sha, required_event="workflow_dispatch")
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
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {
                        "path": ".github/workflows/stage11-assurance.yml",
                        "event": "pull_request",
                        "head_sha": sha,
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
                CONTROL._check_gate(sha, required_event="workflow_dispatch")
        finally:
            CONTROL.api = original_api

    def test_promotion_rolls_back_target_when_ci_dispatch_fails(self) -> None:
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
        self.assertIn(
            (
                "PATCH",
                f"/git/refs/{target_ref}",
                {"sha": base_sha, "force": True},
            ),
            api_calls,
        )
        self.assertIn(("DELETE", f"/git/refs/{target_ref}", None), api_calls)
        self.assertFalse(
            any(
                method == "PATCH"
                and path == "/git/refs/heads%2Fwork%2Fstage11-rendering-engine"
                for method, path, payload in api_calls
            )
        )

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
                self.assertIn("Resolve exact tested source", text)
                self.assertIn("ref: ${{ steps.source.outputs.sha }}", text)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("Assert exact tested source", text)
                self.assertIn('[[ "${EVENT_SHA}" == "${sha}" ]]', text)


if __name__ == "__main__":
    unittest.main()
