"""Offline event-context regression for native workflow concurrency ownership.

This evaluates the workflow's property/OR group expressions, not GitHub's
remote scheduler. Actual cancellation remains an integration gate.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("stage02.yml", "stage13.yml")


def context(event, branch="feature/recovery", *, ref_type="branch", workflow="assurance", sha="a" * 40,
            repository="owner/work", head_repository="owner/work"):
    pull_request = event == "pull_request"
    return {"github": {"workflow": workflow, "event_name": event, "sha": sha, "repository": repository,
        "ref_type": ref_type, "head_ref": branch if pull_request else "",
        "ref_name": "17/merge" if pull_request else branch,
        "ref": "refs/pull/17/merge" if pull_request else f"refs/{'tags' if ref_type == 'tag' else 'heads'}/{branch}",
        "event": {"pull_request": {"number": 17, "head": {"repo": {"full_name": head_repository}}}
                  if pull_request else {}}}}


def group_for(workflow, event_context):
    text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    group = re.search(r"(?m)^concurrency:\s*\n\s+group:\s*(.+)$", text).group(1)

    def evaluate(match):
        for alternative in match.group(1).split("||"):
            value = event_context
            for key in alternative.strip().split("."):
                value = value.get(key, "") if isinstance(value, dict) else ""
            if value:
                return str(value)
        return ""
    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", evaluate, group)


class CandidateOwnershipTests(unittest.TestCase):
    def test_push_and_pr_share_owner_for_same_head_branch(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertEqual(group_for(workflow, context("push")),
                                 group_for(workflow, context("pull_request")))

    def test_dispatch_on_same_branch_shares_owner(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertEqual(group_for(workflow, context("push")),
                                 group_for(workflow, context("workflow_dispatch")))

    def test_new_candidate_supersedes_same_workflow_branch(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertEqual(group_for(workflow, context("push", sha="a" * 40)),
                                 group_for(workflow, context("push", sha="b" * 40)))
                text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
                self.assertIn("cancel-in-progress: true", text)

    def test_other_branch_keeps_its_own_execution(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertNotEqual(group_for(workflow, context("push", branch="feature/one")),
                                    group_for(workflow, context("push", branch="feature/two")))

    def test_tag_and_branch_with_same_name_do_not_cancel_each_other(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertNotEqual(group_for(workflow, context("push", branch="release", ref_type="branch")),
                                    group_for(workflow, context("push", branch="release", ref_type="tag")))

    def test_separate_workflows_are_independent(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertNotEqual(group_for(workflow, context("push", workflow="Stage 10")),
                                    group_for(workflow, context("push", workflow="Stage 13")))

    def test_fork_cannot_cancel_trusted_push_with_same_branch_name(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                self.assertNotEqual(group_for(workflow, context("push", branch="main")),
                    group_for(workflow, context("pull_request", branch="main", head_repository="fork/work")))


if __name__ == "__main__":
    unittest.main()
