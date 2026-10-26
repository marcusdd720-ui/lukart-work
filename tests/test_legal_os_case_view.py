"""Focused tests for the embedded LEGAL OS case workspace (no Word/PDF rechecks)."""
from __future__ import annotations

import unittest
from uuid import uuid4
from lukart_work.embedded_document_engine import EngineBoundaryError, SavedArtifact
from lukart_work.legal_os_case_view import CASE_HTML, CASE_JS, CASE_CSS, read_case_action
from tests.test_embedded_document_engine import FakeOperator


class CaseWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.operator = FakeOperator()
        self.scope = {"tenant_id": str(uuid4()), "case_id": str(uuid4())}
        self.render = str(uuid4())

    def request(self, action, **extra):
        return dict(action=action, **self.scope, **extra)

    def test_workspace_is_local_and_has_single_case_view(self):
        page = CASE_HTML.decode("utf-8")
        self.assertIn("Moja sprawa", page)
        self.assertIn("/case.js", page)
        self.assertIn("Generator Pism 2.0: silnik wewnętrzny", page)
        self.assertNotIn("execute_core", page)
        self.assertNotIn("Zatwierdź wszystko", page)

    def test_no_automatic_human_approval_in_client(self):
        javascript = CASE_JS.decode("utf-8")
        self.assertNotIn("execute_finalization", javascript)
        self.assertNotIn("make_confirmation", javascript)
        self.assertIn('credentials:"omit"', javascript)

    def test_css_provided(self):
        self.assertIn(b".panel", CASE_CSS)

    def test_case_read_goes_to_existing_work_backend(self):
        result = read_case_action(self.operator, self.request("open_case"), "synthetic")
        self.assertEqual(result, {"state": "FOUND"})
        self.assertEqual(self.operator.calls[0][0], "query_core")
        self.assertEqual(self.operator.calls[0][1]["operation"], "GetCaseHead")

    def test_render_status_is_existing_work_query(self):
        read_case_action(self.operator, self.request("get_render", render_id=self.render), "synthetic")
        self.assertEqual(self.operator.calls[0][1]["operation"], "GetFinalization")

    def test_saved_pdf_is_not_rerendered(self):
        file = read_case_action(self.operator, self.request("download", render_id=self.render, format="PDF"), "synthetic")
        self.assertIsInstance(file, SavedArtifact)
        self.assertEqual(file.data, self.operator.file["PDF"])
        self.assertEqual(len(self.operator.calls), 1)
        self.assertEqual(self.operator.calls[0][1]["operation"], "ReadFinalArtifact")

    def test_saved_docx_exact_bytes(self):
        file = read_case_action(self.operator, self.request("download", render_id=self.render, format="DOCX"), "synthetic")
        self.assertEqual(file.data, self.operator.file["DOCX"])

    def test_unknown_action_denied_without_dispatch(self):
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_OPERATION_NOT_ALLOWED"):
            read_case_action(self.operator, self.request("execute_draft"), "synthetic")
        self.assertEqual(self.operator.calls, [])

    def test_extra_fields_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_OPERATION_NOT_ALLOWED"):
            read_case_action(self.operator, self.request("open_case", fake_approval=True), "synthetic")
        self.assertEqual(self.operator.calls, [])

    def test_missing_fields_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_OPERATION_NOT_ALLOWED"):
            read_case_action(self.operator, {"action": "download", **self.scope}, "synthetic")
        self.assertEqual(self.operator.calls, [])

    def test_non_object_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_REQUEST_OBJECT_REQUIRED"):
            read_case_action(self.operator, ["open_case"], "synthetic")

    def test_wrong_case_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "INVALID_CASE_IDENTITY"):
            read_case_action(self.operator, {"action": "open_case", "tenant_id": "bad", "case_id": self.scope["case_id"]}, "synthetic")
        self.assertEqual(self.operator.calls, [])

    def test_empty_token_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "AUTH_REQUIRED"):
            read_case_action(self.operator, self.request("open_case"), "")
        self.assertEqual(self.operator.calls, [])

    def test_unknown_document_format_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "UNSUPPORTED_EXPORT_FORMAT"):
            read_case_action(self.operator, self.request("download", render_id=self.render, format="ODT"), "synthetic")
        self.assertEqual(self.operator.calls, [])


if __name__ == "__main__":
    unittest.main()
