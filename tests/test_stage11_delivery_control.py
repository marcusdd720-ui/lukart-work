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

        def fake_api(method, path, payload=None):
            calls.append((method, path, payload))
            return None

        CONTROL.api = fake_api
        try:
            CONTROL.dispatch_candidate_checks(
                "codex/stage11-rendering-engine",
                "a" * 40,
            )
        finally:
            CONTROL.api = original_api

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
