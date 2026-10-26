"""Focused, synthetic-only tests for the session-bound WORK intake adapter."""
from base64 import b64encode
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from lukart_work.contracts.messages import CaseHeadResult
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor, Ref, VersionPin
from lukart_work.embedded_document_engine import EngineBoundaryError
from lukart_work.legal_os_intake import upload_case_source
from lukart_work.validation.rules import Violation
from tests.test_embedded_document_engine import FakeOperator


class FakeRevision:
    def __init__(self, entity):
        self.entity = entity


class IntakeTests(TestCase):
    def setUp(self):
        self.tenant, self.case = uuid4(), uuid4()
        self.auth = TokenAuthority()
        self.actions = frozenset(("GetCaseHead", "GetRevision", "RegisterSource", "IngestSource"))
        self.token = self.auth.provision(Principal(Actor(id=uuid4(), kind="HUMAN"),
                                                    self.tenant, self.case, self.actions))
        self.policy = VersionPin(id="synthetic-retention", version="1.0.0", content_hash="a"*64)
        self.entity = SimpleNamespace(kind="Case", id=self.case, revision=2, status="OPEN",
                                      retention_policy=self.policy)
        self.head = CaseHeadResult(result_type="CASE_HEAD", tenant_id=self.tenant,
                                   case_id=self.case, case_sequence=3,
                                   heads=(Ref(kind="Case", id=self.case, revision=2),))
        self.operator = FakeOperator()
        self.operator.core = SimpleNamespace(authority=self.auth)
        self.operator.query_core = self.query_core
        self.reads = []
        context = patch("lukart_work.legal_os_intake.RevisionResult", FakeRevision)
        context.start()
        self.addCleanup(context.stop)

    def query_core(self, data, token):
        self.reads.append(data)
        return self.head if data["operation"] == "GetCaseHead" else FakeRevision(self.entity)

    def payload(self, body=b"%PDF-1.4\n%%EOF", mime="application/pdf", **kwargs):
        request = {"action":"upload_source", "media_type":mime,
                   "content_base64":b64encode(body).decode(), "expected_case_sequence":3}
        request.update({name:str(uuid4()) for name in ("command_id","idempotency_key",
                                                       "correlation_id","run_id")})
        request.update(kwargs)
        return request

    def send(self, payload, token=None):
        return upload_case_source(self.operator, payload, token or self.token)

    def test_reuses_work_and_source_retention_without_caller_scope(self):
        self.assertEqual(self.send(self.payload()), {"applied": True})
        kind, actual, token = self.operator.calls[0]
        self.assertEqual(kind, "upload_source")
        self.assertEqual(actual["request"]["meta"]["case_id"], str(self.case))
        self.assertEqual(actual["request"]["meta"]["tenant_id"], str(self.tenant))
        self.assertEqual(actual["request"]["data"]["retention_policy"],
                         self.policy.model_dump(mode="json"))
        self.assertEqual([x["operation"] for x in self.reads], ["GetCaseHead","GetRevision"])

    def test_input_cannot_choose_another_case(self):
        with self.assertRaisesRegex(EngineBoundaryError, "UPLOAD_REQUEST_INVALID"):
            self.send(self.payload(case_id=str(uuid4())))
        self.assertEqual(self.operator.calls, [])

    def test_stale_case_sequence_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError, "UPLOAD_STALE_SEQUENCE"):
            self.send(self.payload(expected_case_sequence=2))
        self.assertEqual(self.operator.calls, [])

    def test_closed_case_denied(self):
        self.entity.status = "CLOSED"
        with self.assertRaisesRegex(EngineBoundaryError, "UPLOAD_CASE_NOT_OPEN"):
            self.send(self.payload())
        self.assertEqual(self.operator.calls, [])

    def test_false_jpeg_and_bmp_rejected(self):
        with self.assertRaisesRegex(EngineBoundaryError, "UPLOAD_CONTENT_TYPE_MISMATCH"):
            self.send(self.payload(mime="image/jpeg"))
        with self.assertRaisesRegex(EngineBoundaryError, "UPLOAD_FORMAT_NOT_SUPPORTED"):
            self.send(self.payload(mime="image/bmp"))
        self.assertEqual(self.operator.calls, [])

    def test_text_without_file_stores_as_source(self):
        self.send(self.payload(body="Syntetyczny opis bez skanu".encode(), mime="text/plain"))
        self.assertEqual(self.operator.calls[0][1]["request"]["data"]["media_type"], "text/plain")

    def test_ai_cannot_upload(self):
        token = self.auth.provision(Principal(Actor(id=uuid4(),kind="AI"),
                                              self.tenant,self.case,self.actions))
        with self.assertRaisesRegex(EngineBoundaryError,"UPLOAD_HUMAN_REQUIRED"):
            self.send(self.payload(),token=token)
        self.assertEqual(self.operator.calls, [])

    def test_insufficient_capability_denied(self):
        token = self.auth.provision(Principal(Actor(id=uuid4(),kind="HUMAN"),
                                              self.tenant,self.case,frozenset(("GetCaseHead",))))
        with self.assertRaises(Violation):
            self.send(self.payload(),token=token)
        self.assertEqual(self.operator.calls, [])

    def test_invalid_uuids_and_binary_text_rejected(self):
        with self.assertRaisesRegex(EngineBoundaryError,"UPLOAD_IDENTIFIERS_INVALID"):
            self.send(self.payload(command_id="invalid"))
        with self.assertRaisesRegex(EngineBoundaryError,"UPLOAD_BINARY_TEXT"):
            self.send(self.payload(body=b"x\x00y",mime="text/plain"))
        self.assertEqual(self.operator.calls, [])


if __name__ == "__main__":
    import unittest
    unittest.main()
