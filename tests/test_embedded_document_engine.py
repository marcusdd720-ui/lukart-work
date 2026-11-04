"""Focused contract checks for the hidden WORK facade; synthetic test doubles only."""
from __future__ import annotations
import io
import unittest
from uuid import uuid4
from zipfile import ZipFile
from lukart_work.embedded_document_engine import (
    CaseScope, EmbeddedDocumentEngine, EngineBoundaryError,
    HumanCommandConfirmation, make_confirmation,
)


def minimal_docx():
    out = io.BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    return out.getvalue()


class FakeOperator:
    def __init__(self):
        self.calls = []
        self.file = {"DOCX": minimal_docx(), "PDF": b"%PDF-1.4\n%%EOF"}

    def query_core(self, payload, token):
        self.calls.append(("query_core", payload, token))
        return {"state": "FOUND"}

    def query_finalization(self, payload, token):
        self.calls.append(("query_finalization", payload, token))
        if payload["operation"] == "ReadFinalArtifact":
            return self.file[payload["format"]]
        return {"state": "DRAFT"}

    def __getattr__(self, name):
        if name in {"execute_core", "execute_fact_evidence", "execute_procedural",
                    "execute_plan", "execute_draft", "execute_validation",
                    "execute_finalization", "upload_source"}:
            def dispatch(payload, token):
                self.calls.append((name, payload, token))
                return {"applied": True}
            return dispatch
        raise AttributeError(name)


class TestHiddenEngine(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOperator()
        self.engine = EmbeddedDocumentEngine(self.fake)
        self.scope = CaseScope(str(uuid4()), str(uuid4()))
        self.render_id = str(uuid4())

    def test_case_head_is_query_only(self):
        self.assertEqual(self.engine.open_case(self.scope, token="secret"), {"state": "FOUND"})
        route, payload, _ = self.fake.calls[0]
        self.assertEqual(route, "query_core")
        self.assertEqual(payload["operation"], "GetCaseHead")

    def test_read_existing_pdf_does_not_render(self):
        file = self.engine.download_saved(self.scope, self.render_id, "PDF", token="secret")
        self.assertEqual(file.data, self.fake.file["PDF"])
        self.assertEqual(file.filename, "dokument.pdf")
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.fake.calls[0][1]["operation"], "ReadFinalArtifact")

    def test_read_existing_docx_structure(self):
        file = self.engine.download_saved(self.scope, self.render_id, "DOCX", token="secret")
        self.assertEqual(file.data, self.fake.file["DOCX"])
        self.assertEqual(len(file.sha256), 64)

    def test_reject_invalid_identity(self):
        with self.assertRaises(EngineBoundaryError):
            CaseScope("not-uuid", str(uuid4()))

    def test_reject_unknown_format_without_dispatch(self):
        with self.assertRaisesRegex(EngineBoundaryError, "UNSUPPORTED_EXPORT_FORMAT"):
            self.engine.download_saved(self.scope, self.render_id, "HTML", token="secret")
        self.assertEqual(self.fake.calls, [])

    def test_auth_required(self):
        with self.assertRaisesRegex(EngineBoundaryError, "AUTH_REQUIRED"):
            self.engine.open_case(self.scope, token="")
        self.assertEqual(self.fake.calls, [])

    def test_backend_denial_not_success(self):
        self.fake.file["PDF"] = {"error": "FORBIDDEN"}
        with self.assertRaisesRegex(EngineBoundaryError, "WORK_ARTIFACT_READ_REJECTED"):
            self.engine.download_saved(self.scope, self.render_id, "PDF", token="secret")

    def test_non_docx_zip_rejected(self):
        buf = io.BytesIO()
        with ZipFile(buf, "w") as z:
            z.writestr("anything", "wrong")
        self.fake.file["DOCX"] = buf.getvalue()
        with self.assertRaisesRegex(EngineBoundaryError, "DOCX_STRUCTURE_INVALID"):
            self.engine.download_saved(self.scope, self.render_id, "DOCX", token="secret")

    def test_approved_existing_command_can_pass_to_work(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}, "operation": "SomeStrictWORKCommand"}
        confirmation = make_confirmation(self.scope, "execute_core", req)
        self.assertEqual(self.engine.execute_confirmed(self.scope, "execute_core", req, confirmation, token="secret"), {"applied": True})
        self.assertEqual(self.fake.calls[-1][0], "execute_core")

    def test_changed_command_is_blocked_without_work_call(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}, "amount": "1200"}
        confirmation = make_confirmation(self.scope, "execute_core", req)
        req["amount"] = "1201"
        with self.assertRaisesRegex(EngineBoundaryError, "CONFIRMATION_STALE"):
            self.engine.execute_confirmed(self.scope, "execute_core", req, confirmation, token="secret")
        self.assertEqual(self.fake.calls, [])

    def test_cross_case_command_denied(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": str(uuid4())}}
        confirmation = make_confirmation(self.scope, "execute_draft", req)
        with self.assertRaisesRegex(EngineBoundaryError, "COMMAND_SCOPE_MISMATCH"):
            self.engine.execute_confirmed(self.scope, "execute_draft", req, confirmation, token="secret")
        self.assertEqual(self.fake.calls, [])

    def test_no_implicit_confirmation(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}}
        with self.assertRaisesRegex(EngineBoundaryError, "CONFIRMATION_SCOPE_MISMATCH"):
            self.engine.execute_confirmed(self.scope, "execute_draft", req, None, token="secret")
        self.assertEqual(self.fake.calls, [])

    def test_unknown_command_route_not_dispatched(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}}
        with self.assertRaisesRegex(EngineBoundaryError, "COMMAND_ROUTE_NOT_ALLOWED"):
            make_confirmation(self.scope, "run_python", req)

    def test_upload_scope_nested(self):
        req = {"operation": "UploadAndIngest", "request": {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}}}
        confirmation = make_confirmation(self.scope, "upload_source", req)
        self.engine.execute_confirmed(self.scope, "upload_source", req, confirmation, token="secret")
        self.assertEqual(self.fake.calls[-1][0], "upload_source")

    def test_exact_scope_for_confirmation(self):
        req = {"meta": {"tenant_id": self.scope.tenant_id, "case_id": self.scope.case_id}}
        other = CaseScope(str(uuid4()), str(uuid4()))
        confirmation = HumanCommandConfirmation(other, "execute_draft", "0"*64)
        with self.assertRaisesRegex(EngineBoundaryError, "CONFIRMATION_SCOPE_MISMATCH"):
            self.engine.execute_confirmed(self.scope, "execute_draft", req, confirmation, token="secret")


if __name__ == "__main__":
    unittest.main()
