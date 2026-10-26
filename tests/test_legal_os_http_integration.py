"""Single-window HTTP integration test. Synthetic in-memory WORK boundaries only."""
from __future__ import annotations

from contextlib import contextmanager
from base64 import b64encode
from unittest.mock import patch
from datetime import datetime, timezone
from http.client import HTTPConnection
from io import BytesIO
from json import dumps, loads
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4
from zipfile import ZipFile

from lukart_work.contracts.messages import CaseHeadResult
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor, Ref, VersionPin
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server


class RenderTx:
    def __init__(self, record):
        self.record = record

    def sequence(self):
        return 1

    def objects(self, category, cls):
        if category != "finalization_render":
            raise AssertionError("wrong WORK category")
        return (self.record,)


class ScopeRepo:
    def __init__(self, tenant, case, record):
        self.tenant, self.case, self.record = tenant, case, record
        self.reads = 0

    @contextmanager
    def transaction(self, tenant, case):
        if (tenant, case) != (self.tenant, self.case):
            raise AssertionError("unscoped database operation")
        self.reads += 1
        yield RenderTx(self.record)


class CaseHTTPIntegrationTests(TestCase):
    def setUp(self):
        self.tenant, self.case, self.render_id = uuid4(), uuid4(), uuid4()
        self.authority = TokenAuthority()
        principal = Principal(
            Actor(id=uuid4(), kind="HUMAN"),
            self.tenant, self.case,
            frozenset({"GetCaseHead", "GetFinalization", "ReadFinalArtifact"}),
        )
        self.token = self.authority.provision(principal)
        self.record = SimpleNamespace(
            id=self.render_id, tenant_id=self.tenant, case_id=self.case,
            recorded_at=datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc),
            semantic_profile=SimpleNamespace(id="SYNTHETIC_TEST"),
        )
        self.repo = ScopeRepo(self.tenant, self.case, self.record)
        self.counter = {"query": 0, "render": 0}
        self.operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
        self.operator.binding = None
        self.operator.core = SimpleNamespace(authority=self.authority)
        self.operator.finalization = SimpleNamespace(authority=self.authority, repository=self.repo)
        self.pdf = b"%PDF-1.4\nsynthetic\n%%EOF"
        buf = BytesIO()
        with ZipFile(buf, "w") as zipped:
            zipped.writestr("word/document.xml", "<document/>")
        self.docx = buf.getvalue()

        def core_query(request, token):
            self.counter["query"] += 1
            return CaseHeadResult(result_type="CASE_HEAD", tenant_id=self.tenant,
                                  case_id=self.case, case_sequence=1, heads=())

        def final_query(request, token):
            if request["operation"] == "ReadFinalArtifact":
                return self.pdf if request["format"] == "PDF" else self.docx
            return {"status": "SYNTHETIC"}

        self.operator.query_core = core_query
        self.operator.query_finalization = final_query
        self.server = create_server(self.operator, 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def call(self, payload=None, *, token=None, path="/api/embedded_case", method="POST"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            data = dumps(payload or {}, separators=(",", ":")) if method == "POST" else None
            headers = {"Content-Type": "application/json",
                       "Authorization": "Bearer " + (token if token is not None else self.token)}
            conn.request(method, path, data, headers if method == "POST" else {})
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_one_window_case_to_existing_document_bytes(self):
        status, html, _ = self.call(method="GET", path="/case")
        self.assertEqual(status, 200)
        self.assertIn(b"/case.js", html)
        scope = {"tenant_id": str(self.tenant), "case_id": str(self.case)}
        status, data, _ = self.call({"action": "open_case", **scope})
        self.assertEqual(status, 200)
        self.assertEqual(loads(data)["result_type"], "CASE_HEAD")
        status, data, _ = self.call({"action": "list_saved", **scope})
        self.assertEqual(status, 200)
        self.assertEqual(loads(data)["items"][0]["render_id"], str(self.render_id))
        for format, exact in (("PDF", self.pdf), ("DOCX", self.docx)):
            with self.subTest(format=format):
                status, data, headers = self.call({
                    "action": "download", **scope,
                    "render_id": str(self.render_id), "format": format,
                })
                self.assertEqual(status, 200)
                self.assertEqual(data, exact)
                self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.counter["render"], 0)
        self.assertEqual(self.counter["query"], 1)
        self.assertEqual(self.repo.reads, 1)

    def test_session_case_path_needs_no_case_identifiers(self):
        status, html, _ = self.call(method="GET", path="/case")
        self.assertEqual(status, 200)
        self.assertNotIn(b'id="tenant"', html)
        self.assertNotIn(b'id="case"', html)
        status, script, _ = self.call(method="GET", path="/case.js")
        self.assertEqual(status, 200)
        self.assertIn(b"/api/embedded_session", script)
        status, body, _ = self.call({"action": "open_case"}, path="/api/embedded_session")
        self.assertEqual(status, 200)
        self.assertEqual(loads(body)["case_id"], str(self.case))
        status, body, _ = self.call({"action": "list_saved"}, path="/api/embedded_session")
        self.assertEqual(status, 200)
        self.assertEqual(loads(body)["items"][0]["render_id"], str(self.render_id))
        status, pdf, _ = self.call({
            "action": "download", "render_id": str(self.render_id), "format": "PDF",
        }, path="/api/embedded_session")
        self.assertEqual(status, 200)
        self.assertEqual(pdf, self.pdf)
        self.assertEqual(self.counter["render"], 0)

    def test_browser_cannot_override_session_case(self):
        status, _, _ = self.call({
            "action": "list_saved", "tenant_id": str(self.tenant),
            "case_id": str(uuid4()),
        }, path="/api/embedded_session")
        self.assertEqual(status, 403)
        self.assertEqual(self.repo.reads, 0)

    def test_ai_session_cannot_read_case_workspace(self):
        ai_token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="AI"), self.tenant, self.case,
            frozenset({"GetCaseHead", "GetFinalization", "ReadFinalArtifact"}),
        ))
        status, _, _ = self.call({"action": "open_case"},
                                  token=ai_token, path="/api/embedded_session")
        self.assertEqual(status, 403)
        self.assertEqual(self.counter["query"], 0)

    def test_session_upload_text_end_to_end_through_http_into_work(self):
        class FakeRevision:
            def __init__(self, entity):
                self.entity = entity

        actions = {"GetCaseHead", "GetRevision", "RegisterSource", "IngestSource"}
        token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="HUMAN"), self.tenant, self.case, frozenset(actions)
        ))
        policy = VersionPin(id="synthetic-retention", version="1.0.0", content_hash="b"*64)
        original_query = self.operator.query_core
        received = []
        def query(request, presented):
            if request["operation"] == "GetCaseHead":
                return CaseHeadResult(result_type="CASE_HEAD", tenant_id=self.tenant,
                    case_id=self.case, case_sequence=3,
                    heads=(Ref(kind="Case", id=self.case, revision=2),))
            return FakeRevision(SimpleNamespace(kind="Case", id=self.case,
                revision=2, status="OPEN", retention_policy=policy))
        class Result:
            def model_dump_json(self):
                return dumps({"registration":{"state":"APPLIED","case_sequence":4},
                              "ingestion":{"body":{"status":"EXTRACTED","fragments":[],
                                                   "candidates":[]}}})
        self.operator.query_core = query
        def upload(request, presented):
            received.append((request, presented))
            return Result()
        self.operator.upload_source = upload
        payload = {
            "action":"upload_source",
            "expected_case_sequence":3,
            "media_type":"text/plain",
            "content_base64":b64encode("Opis syntetycznej sprawy".encode()).decode(),
            **{k:str(uuid4()) for k in ("command_id","idempotency_key",
                                         "correlation_id","run_id")},
        }
        try:
            with patch("lukart_work.legal_os_intake.RevisionResult", FakeRevision):
                status, body, headers = self.call(
                    payload, token=token, path="/api/embedded_session"
                )
            self.assertEqual(status,200)
            self.assertEqual(loads(body)["registration"]["state"],"APPLIED")
            self.assertEqual(len(received),1)
            self.assertEqual(received[0][0]["request"]["meta"]["case_id"],str(self.case))
            self.assertEqual(received[0][0]["request"]["data"]["retention_policy"],
                             policy.model_dump(mode="json"))
            self.assertEqual(headers["Cache-Control"],"no-store")
            self.assertEqual(self.counter["render"],0)
        finally:
            self.operator.query_core = original_query

    def test_no_token_and_cross_case_listing_denied(self):
        status, _, _ = self.call({
            "action": "list_saved", "tenant_id": str(self.tenant), "case_id": str(self.case),
        }, token="invalid-token")
        self.assertEqual(status, 403)
        status, _, _ = self.call({
            "action": "list_saved", "tenant_id": str(self.tenant), "case_id": str(uuid4()),
        })
        self.assertEqual(status, 403)
        self.assertEqual(self.repo.reads, 0)

    def test_request_cannot_execute_unreviewed_command(self):
        status, _, _ = self.call({
            "action": "execute_finalization",
            "tenant_id": str(self.tenant), "case_id": str(self.case),
        })
        self.assertEqual(status, 403)
        self.assertEqual(self.repo.reads, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
