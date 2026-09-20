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
                            "display_title": f"stage11-dispatch-{token}",
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
                self.assertIn("run-name: stage11-", text)
                self.assertIn("Resolve exact tested source", text)
                self.assertIn("ref: ${{ steps.source.outputs.sha }}", text)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("Assert exact tested source", text)
                self.assertIn('[[ "${EVENT_SHA}" == "${sha}" ]]', text)


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
        for branch in ("codex/stage11-rendering", "codex/stage11-procedure-bootstrap-pr15-copy", "main"):
            with self.subTest(branch=branch), self.assertRaises(CONTROL.ControlError):
                CONTROL.require_stage11_tests(branch, False, base_sha=CONTROL.PROCEDURE_BOOTSTRAP_BASE,
                                             changed_paths=list(CONTROL.PROCEDURE_BOOTSTRAP_PATHS))

    def test_stage11_bootstrap_exception_requires_exact_base_and_procedure_only_diff(self):
        branch = CONTROL.PROCEDURE_BOOTSTRAP_BRANCH
        base = CONTROL.PROCEDURE_BOOTSTRAP_BASE
        self.assertEqual(CONTROL.require_stage11_tests(branch, False, base_sha=base,
                         changed_paths=list(CONTROL.PROCEDURE_BOOTSTRAP_PATHS)), "PROCEDURE_ONLY_BOOTSTRAP")
        for wrong_base, paths in ((self.BASE, list(CONTROL.PROCEDURE_BOOTSTRAP_PATHS)),
                                  (base, []), (base, ["lukart_work/rendering/service.py"]),
                                  (base, ["tests/test_stage11.py"]), (base, ["AGENTS.md"])):
            with self.subTest(base=wrong_base, paths=paths), self.assertRaises(CONTROL.ControlError):
                CONTROL.require_stage11_tests(branch, False, base_sha=wrong_base, changed_paths=paths)
        self.assertEqual(CONTROL.require_stage11_tests(branch, True), "RENDERING_TESTS_REQUIRED")

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
                            "display_title": f"stage11-dispatch-{token}",
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
                            "display_title": f"stage11-dispatch-{token}",
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
        for existing in (False, True):
            for failure in ("signature", "tree", "first_dispatch", "second_dispatch"):
                for concurrent in (False, True):
                    with self.subTest(existing=existing, failure=failure, concurrent=concurrent):
                        refs = {source: self.SHA, "main": self.BASE}
                        if existing:
                            refs[target] = self.BASE
                        calls = []

                        def api(method, path, payload=None):
                            calls.append((method, path, payload))
                            if method == "GET" and path.startswith("/compare/"):
                                return {"behind_by": 0, "ahead_by": 1, "files": [
                                    {"filename": "product.py", "status": "added"}]}
                            if method == "POST" and path == "/git/refs":
                                refs[target] = payload["sha"]
                                return None
                            self.fail(f"unsafe/unexpected mutation: {method} {path}")

                        def dispatch(branch, sha):
                            self.assertEqual((branch, sha), (target, promoted))
                            if failure in {"first_dispatch", "second_dispatch"}:
                                if concurrent:
                                    refs[target] = newer
                                raise CONTROL.ControlError("injected dispatch failure")
                            self.fail("dispatch must not run after signature/tree failure")

                        def commit(sha):
                            if sha == self.SHA:
                                return {"commit": {"tree": {"sha": "tree"}}}
                            if failure in {"signature", "tree"} and concurrent:
                                refs[target] = newer
                            return {"commit": {"tree": {"sha": "wrong" if failure == "tree" else "tree"},
                                               "verification": {"verified": failure != "signature"}}}

                        def graphql(query, variables):
                            self.assertEqual(variables["input"]["expectedHeadOid"], refs[target])
                            refs[target] = promoted
                            return {"createCommitOnBranch": {"commit": {"oid": promoted}}}

                        with patch.object(CONTROL, "_ref", side_effect=lambda b: {"object": {"sha": refs[b]}} if b in refs else None), \
                                patch.object(CONTROL, "api", side_effect=api), patch.object(CONTROL, "_commit", side_effect=commit), \
                                patch.object(CONTROL, "graphql", side_effect=graphql), \
                                patch.object(CONTROL, "_tree_map", return_value={"product.py": {"sha": "blob", "mode": "100644"}}), \
                                patch.object(CONTROL, "_blob_bytes", return_value=b"content"), \
                                patch.object(CONTROL, "dispatch_candidate_checks", side_effect=dispatch), \
                                patch.object(CONTROL, "_post_comment") as comment, \
                                patch.object(CONTROL, "_repo", return_value="owner/repo"):
                            with self.assertRaisesRegex(CONTROL.ControlError, "target preserved"):
                                CONTROL.promote(17, {"source": source, "target": target,
                                                     "source_sha": self.SHA, "base_sha": self.BASE})
                        self.assertEqual(refs[target], newer if concurrent else promoted)
                        self.assertEqual(refs[source], self.SHA)
                        self.assertFalse(any(c[0] in {"PATCH", "DELETE"} for c in calls))
                        comment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
