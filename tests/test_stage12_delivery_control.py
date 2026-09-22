from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage12_delivery_control.py"
SPEC = importlib.util.spec_from_file_location("stage12_delivery_control", SCRIPT)
assert SPEC and SPEC.loader
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


class Stage12DeliveryControlTests(unittest.TestCase):
    BASE = "a" * 40
    SOURCE = "b" * 40
    TREE = "c" * 40
    NEW = "d" * 40
    BRANCH = "codex/stage12-audit-provenance"

    def pr(self, *, head: str | None = None, branch: str | None = None, base: str | None = None):
        return {
            "state": "open",
            "draft": False,
            "merged": False,
            "base": {
                "ref": "main",
                "sha": base or self.BASE,
                "repo": {"id": 1, "full_name": "owner/repo"},
            },
            "head": {
                "ref": branch or self.BRANCH,
                "sha": head or self.SOURCE,
                "repo": {"id": 1, "full_name": "owner/repo"},
            },
        }

    def source_commit(self, *, tree: str | None = None):
        return {"commit": {"tree": {"sha": tree or self.TREE}}}

    def promoted_commit(
        self,
        *,
        verified: bool = True,
        tree: str | None = None,
        parent: str | None = None,
    ):
        return {
            "commit": {
                "verification": {"verified": verified},
                "tree": {"sha": tree or self.TREE},
            },
            "parents": [{"sha": parent or self.SOURCE}],
        }

    def successful_promote(self, *, promoted=None):
        comments: list[str] = []
        seen: dict[str, object] = {}

        def fake_graphql(query, variables):
            seen["query"] = query
            seen["variables"] = variables
            return {"createCommitOnBranch": {"commit": {"oid": self.NEW, "url": "https://example.invalid"}}}

        commits = {
            self.SOURCE: self.source_commit(),
            self.NEW: promoted or self.promoted_commit(),
        }
        refs = [self.SOURCE, self.BASE, self.NEW, self.BASE, self.BASE]
        prs = [self.pr(), self.pr(head=self.NEW), self.pr(head=self.NEW)]

        with patch.object(CONTROL, "_pr", side_effect=prs), \
                patch.object(CONTROL, "_ref_sha", side_effect=refs), \
                patch.object(CONTROL, "_commit", side_effect=lambda sha: commits[sha]), \
                patch.object(CONTROL, "graphql", side_effect=fake_graphql), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(CONTROL, "dispatch_assurance", return_value={"stage02.yml": 777, "stage11-assurance.yml": 778}), \
                patch.object(CONTROL, "_post_comment", side_effect=lambda issue, body: comments.append(body)):
            CONTROL.promote(
                52,
                {
                    "source_sha": self.SOURCE,
                    "source_tree": self.TREE,
                    "base_sha": self.BASE,
                },
            )
        return seen, comments

    def test_command_namespace_is_stage12_only(self):
        command, args = CONTROL.parse_command(
            f"/stage12 promote source_sha={self.SOURCE} source_tree={self.TREE} base_sha={self.BASE}"
        )
        self.assertEqual(command, "promote")
        self.assertEqual(args["source_sha"], self.SOURCE)
        for body in (
            f"/stage11 promote source_sha={self.SOURCE}",
            "/stage12 merge head_sha=x",
            "/stage12 cleanup branch=x",
            "/other promote x=y",
        ):
            with self.subTest(body=body):
                with self.assertRaises(CONTROL.ControlError):
                    CONTROL.parse_command(body)

    def test_stage11_independent_review_receipt_cannot_be_reused(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "requires exactly"):
            CONTROL.promote(
                52,
                {
                    "source_sha": self.SOURCE,
                    "source_tree": self.TREE,
                    "base_sha": self.BASE,
                    "stage11_review_receipt": "STAGE11_INDEPENDENT_REVIEW: PASS",
                },
            )

    def test_sha_requires_exact_lowercase_40_hex(self):
        self.assertEqual(CONTROL._require_sha(self.SOURCE, "source_sha"), self.SOURCE)
        for value in ("a" * 39, "A" * 40, "g" * 40, "a" * 41):
            with self.subTest(value=value):
                with self.assertRaises(CONTROL.ControlError):
                    CONTROL._require_sha(value, "x")

    def test_wrong_stage12_branch_namespace_is_rejected(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "exact authorized Stage 12 product branch"):
            CONTROL._validate_pr_preconditions(
                self.pr(branch="codex/stage11-rendering"),
                self.SOURCE,
                self.BASE,
            )

    def test_cross_repository_head_is_rejected(self):
        pr = self.pr()
        pr["head"]["repo"] = {"id": 2, "full_name": "fork/repo"}
        with self.assertRaisesRegex(CONTROL.ControlError, "same repository"):
            CONTROL._validate_pr_preconditions(pr, self.SOURCE, self.BASE)

    def test_source_sha_mismatch_is_rejected(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "source SHA"):
            CONTROL._validate_pr_preconditions(
                self.pr(head="e" * 40),
                self.SOURCE,
                self.BASE,
            )

    def test_base_or_main_mismatch_is_rejected_before_mutation(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "base SHA"):
            CONTROL._validate_pr_preconditions(
                self.pr(base="e" * 40),
                self.SOURCE,
                self.BASE,
            )

        with patch.object(CONTROL, "_pr", return_value=self.pr()), \
                patch.object(CONTROL, "_ref_sha", side_effect=[self.SOURCE, "e" * 40]), \
                patch.object(CONTROL, "graphql") as graphql:
            with self.assertRaisesRegex(CONTROL.ControlError, "main moved"):
                CONTROL.promote(
                    52,
                    {
                        "source_sha": self.SOURCE,
                        "source_tree": self.TREE,
                        "base_sha": self.BASE,
                    },
                )
        graphql.assert_not_called()

    def test_source_tree_mismatch_is_rejected_before_mutation(self):
        with patch.object(CONTROL, "_pr", return_value=self.pr()), \
                patch.object(CONTROL, "_ref_sha", side_effect=[self.SOURCE, self.BASE]), \
                patch.object(CONTROL, "_commit", return_value=self.source_commit(tree="e" * 40)), \
                patch.object(CONTROL, "graphql") as graphql:
            with self.assertRaisesRegex(CONTROL.ControlError, "source tree mismatch"):
                CONTROL.promote(
                    52,
                    {
                        "source_sha": self.SOURCE,
                        "source_tree": self.TREE,
                        "base_sha": self.BASE,
                    },
                )
        graphql.assert_not_called()

    def test_tree_preserving_mutation_uses_exact_expected_head_and_zero_file_changes(self):
        seen, comments = self.successful_promote()
        variables = seen["variables"]
        mutation_input = variables["input"]
        self.assertEqual(mutation_input["expectedHeadOid"], self.SOURCE)
        self.assertEqual(mutation_input["branch"]["branchName"], self.BRANCH)
        self.assertNotEqual(mutation_input["branch"]["branchName"], "main")
        self.assertEqual(mutation_input["fileChanges"], {})
        self.assertEqual(len(comments), 1)

    def test_stale_expected_head_fails_closed_without_receipt(self):
        with patch.object(CONTROL, "_pr", return_value=self.pr()), \
                patch.object(CONTROL, "_ref_sha", side_effect=[self.SOURCE, self.BASE]), \
                patch.object(CONTROL, "_commit", return_value=self.source_commit()), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(CONTROL, "graphql", side_effect=CONTROL.ControlError("expectedHeadOid mismatch")), \
                patch.object(CONTROL, "_post_comment") as post:
            with self.assertRaisesRegex(CONTROL.ControlError, "expectedHeadOid"):
                CONTROL.promote(
                    52,
                    {
                        "source_sha": self.SOURCE,
                        "source_tree": self.TREE,
                        "base_sha": self.BASE,
                    },
                )
        post.assert_not_called()

    def test_unsigned_result_is_rejected_and_preserved(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "preserved without reset/delete"):
            self._promote_with_bad_result(self.promoted_commit(verified=False))

    def test_resulting_parent_mismatch_is_rejected_and_preserved(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "parent identity"):
            self._promote_with_bad_result(self.promoted_commit(parent="e" * 40))

    def test_resulting_tree_mismatch_is_rejected_and_preserved(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "tree differs"):
            self._promote_with_bad_result(self.promoted_commit(tree="e" * 40))

    def _promote_with_bad_result(self, promoted):
        refs = [self.SOURCE, self.BASE]
        commits = {self.SOURCE: self.source_commit(), self.NEW: promoted}
        with patch.object(CONTROL, "_pr", return_value=self.pr()), \
                patch.object(CONTROL, "_ref_sha", side_effect=refs), \
                patch.object(CONTROL, "_commit", side_effect=lambda sha: commits[sha]), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(
                    CONTROL,
                    "graphql",
                    return_value={"createCommitOnBranch": {"commit": {"oid": self.NEW}}},
                ), \
                patch.object(CONTROL, "dispatch_assurance") as dispatch, \
                patch.object(CONTROL, "_post_comment") as post:
            try:
                CONTROL.promote(
                    52,
                    {
                        "source_sha": self.SOURCE,
                        "source_tree": self.TREE,
                        "base_sha": self.BASE,
                    },
                )
            finally:
                dispatch.assert_not_called()
                post.assert_not_called()

    def test_verification_is_read_back_from_github_commit(self):
        calls: list[str] = []
        commits = {self.SOURCE: self.source_commit(), self.NEW: self.promoted_commit()}

        def fake_commit(sha):
            calls.append(sha)
            return commits[sha]

        refs = [self.SOURCE, self.BASE, self.NEW, self.BASE, self.BASE]
        prs = [self.pr(), self.pr(head=self.NEW), self.pr(head=self.NEW)]
        with patch.object(CONTROL, "_pr", side_effect=prs), \
                patch.object(CONTROL, "_ref_sha", side_effect=refs), \
                patch.object(CONTROL, "_commit", side_effect=fake_commit), \
                patch.object(CONTROL, "_repo", return_value="owner/repo"), \
                patch.object(
                    CONTROL,
                    "graphql",
                    return_value={"createCommitOnBranch": {"commit": {"oid": self.NEW}}},
                ), \
                patch.object(CONTROL, "dispatch_assurance", return_value={"stage02.yml": 1, "stage11-assurance.yml": 2}), \
                patch.object(CONTROL, "_post_comment"):
            CONTROL.promote(
                52,
                {
                    "source_sha": self.SOURCE,
                    "source_tree": self.TREE,
                    "base_sha": self.BASE,
                },
            )
        self.assertEqual(calls, [self.SOURCE, self.NEW])

    def test_receipt_binds_source_new_parent_tree_and_never_uses_stage11_namespace(self):
        _seen, comments = self.successful_promote()
        receipt = comments[0]
        self.assertTrue(receipt.startswith("STAGE12_PROMOTION: DISPATCH_BOUND\n"))
        self.assertNotIn("STAGE11_", receipt)
        for line in (
            f"source_sha={self.SOURCE}",
            f"new_sha={self.NEW}",
            f"parent_sha={self.SOURCE}",
            f"source_tree={self.TREE}",
            f"new_tree={self.TREE}",
            f"base_sha={self.BASE}",
            "verification=VERIFIED",
            "assurance_runs=stage02.yml:777,stage11-assurance.yml:778",
            "main_changed=NO",
            "merge=NOT_PERFORMED",
        ):
            self.assertIn(line, receipt)

    def test_failed_promotion_never_performs_destructive_compensation(self):
        with patch.object(CONTROL, "api") as api:
            with self.assertRaisesRegex(CONTROL.ControlError, "preserved without reset/delete"):
                CONTROL._abort_promotion(self.BRANCH, self.NEW, "synthetic failure")
        api.assert_not_called()

    def test_dispatch_rejects_stage11_branch(self):
        with self.assertRaisesRegex(CONTROL.ControlError, "exact Stage 12 product branch"):
            CONTROL.dispatch_assurance("codex/stage11-rendering", self.NEW)

    def test_dispatch_binds_existing_exact_sha_ci_and_rechecks_ref(self):
        token = "e" * 32
        baseline_stage02 = [{"id": 10}]
        baseline_stage11 = [{"id": 20}]
        correlated_stage02 = [{
            "id": 11,
            "display_title": f"stage11-dispatch-{token}",
            "event": "workflow_dispatch",
            "head_sha": self.NEW,
            "head_branch": self.BRANCH,
            "path": ".github/workflows/stage02.yml",
        }]
        correlated_stage11 = [{
            "id": 21,
            "display_title": f"stage11-dispatch-{token}",
            "event": "workflow_dispatch",
            "head_sha": self.NEW,
            "head_branch": self.BRANCH,
            "path": ".github/workflows/stage11-assurance.yml",
        }]
        posts = []

        def fake_api(method, path, payload=None):
            if method == "POST":
                posts.append((path, payload))
                return None
            self.fail(f"unexpected API call: {method} {path}")

        with patch.object(CONTROL, "_assert_ref_sha") as ref_check, \
                patch.object(
                    CONTROL,
                    "_workflow_dispatch_runs",
                    side_effect=[
                        baseline_stage02, correlated_stage02,
                        baseline_stage11, correlated_stage11,
                    ],
                ), \
                patch.object(CONTROL.secrets, "token_hex", return_value=token), \
                patch.object(CONTROL, "api", side_effect=fake_api):
            run_ids = CONTROL.dispatch_assurance(self.BRANCH, self.NEW)

        self.assertEqual(run_ids, {"stage02.yml": 11, "stage11-assurance.yml": 21})
        self.assertEqual(ref_check.call_count, 6)
        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0][0].endswith("/stage02.yml/dispatches"))
        self.assertTrue(posts[1][0].endswith("/stage11-assurance.yml/dispatches"))
        for _path, payload in posts:
            self.assertEqual(payload["ref"], self.BRANCH)
            self.assertEqual(payload["inputs"]["candidate_sha"], self.NEW)
            self.assertEqual(payload["inputs"]["dispatch_token"], token)

    def test_ambiguous_existing_ci_dispatch_is_rejected(self):
        token = "f" * 32
        run = {
            "id": 21,
            "display_title": f"stage11-dispatch-{token}",
            "event": "workflow_dispatch",
            "head_sha": self.NEW,
            "head_branch": self.BRANCH,
            "path": ".github/workflows/stage02.yml",
        }
        with patch.object(
            CONTROL,
            "_workflow_dispatch_runs",
            return_value=[run, dict(run, id=22)],
        ):
            with self.assertRaisesRegex(CONTROL.ControlError, "ambiguous"):
                CONTROL._wait_for_bound_dispatch_run(
                    "stage02.yml",
                    self.BRANCH,
                    self.NEW,
                    token,
                    set(),
                    attempts=1,
                    interval_seconds=0,
                )

    def test_only_reviewed_tree_workflows_are_candidate_ci(self):
        self.assertEqual(
            CONTROL.CANDIDATE_WORKFLOWS,
            ("stage02.yml", "stage11-assurance.yml"),
        )
        self.assertNotIn("stage12-procedure-assurance.yml", CONTROL.CANDIDATE_WORKFLOWS)

    def test_owner_boundary_is_fail_closed(self):
        event = {
            "comment": {
                "user": {"login": "attacker", "id": 2, "type": "User"},
                "author_association": "OWNER",
            },
            "repository": {"owner": {"login": "owner", "id": 1, "type": "User"}},
        }
        with self.assertRaisesRegex(CONTROL.ControlError, "repository-owner HUMAN"):
            CONTROL._assert_owner_actor(event)

    def test_owner_boundary_requires_id_type_and_owner_association(self):
        valid = {
            "comment": {
                "user": {"login": "owner", "id": 1, "type": "User"},
                "author_association": "OWNER",
                "performed_via_github_app": None,
            },
            "repository": {"owner": {"login": "owner", "id": 1, "type": "User"}},
        }
        CONTROL._assert_owner_actor(valid)
        variants = [
            {**valid, "comment": {**valid["comment"], "author_association": "MEMBER"}},
            {**valid, "comment": {**valid["comment"], "user": {"login": "owner", "id": 2, "type": "User"}}},
            {**valid, "repository": {"owner": {"login": "owner", "id": 1, "type": "Organization"}}},
        ]
        for event in variants:
            with self.assertRaises(CONTROL.ControlError):
                CONTROL._assert_owner_actor(event)

    def test_owner_boundary_rejects_github_app_performed_comment(self):
        event = {
            "comment": {
                "user": {"login": "owner", "id": 1, "type": "User"},
                "author_association": "OWNER",
                "performed_via_github_app": {"id": 99, "slug": "synthetic-app"},
            },
            "repository": {"owner": {"login": "owner", "id": 1, "type": "User"}},
        }
        with self.assertRaisesRegex(CONTROL.ControlError, "repository-owner HUMAN"):
            CONTROL._assert_owner_actor(event)

    def test_stage12_control_workflow_is_isolated_from_stage11_command_namespace(self):
        text = (ROOT / ".github" / "workflows" / "stage12-control.yml").read_text(encoding="utf-8")
        self.assertIn("'/stage12 '", text)
        self.assertIn("scripts/stage12_delivery_control.py", text)
        self.assertNotIn("'/stage11 '", text)
        self.assertNotIn("scripts/stage11_delivery_control.py", text)

    def test_stage12_procedure_assurance_is_not_product_candidate_ci(self):
        text = (ROOT / ".github" / "workflows" / "stage12-procedure-assurance.yml").read_text(encoding="utf-8")
        self.assertIn("run-name: stage12-procedure-", text)
        self.assertIn("tests.test_stage12_delivery_control", text)
        self.assertIn("tests.test_stage11_delivery_control", text)
        self.assertNotIn("tests.test_stage12\n", text)

    def test_control_source_has_no_ref_patch_delete_force_or_pr_merge(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('api("PATCH",', text)
        self.assertNotIn('api("DELETE",', text)
        self.assertNotIn('/merge', text)
        self.assertNotIn('"force": True', text)
        self.assertNotIn('"force": true', text)


if __name__ == "__main__":
    unittest.main()
