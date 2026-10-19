"""Transport and synthetic CASE regressions; no HUMAN decisions are recorded."""
from http.client import HTTPConnection, HTTPResponse
import json
import os
import shutil
import socket
import subprocess
from threading import Thread
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import safe_error
from lukart_work.domain.models import Actor
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import CLIENT, create_server, MAX_BODY


class OperatorHostTests(unittest.TestCase):
    def setUp(self):
        self.authority = TokenAuthority()
        self.token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="SERVICE"), uuid4(), uuid4(), frozenset()))
        self.operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
        self.operator.binding = None
        self.operator.core = SimpleNamespace(authority=self.authority)
        self.operator.query_core = Mock(return_value=safe_error("FORBIDDEN", uuid4()))
        self.server = create_server(self.operator, 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, body="{}", headers=None, path="/api/query_core", method="POST"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body, headers or {})
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def headers(self, **extra):
        return {"Content-Type": "application/json", "Authorization": "Bearer " + self.token, **extra}

    def test_authenticated_dispatch_preserves_service_denial(self):
        status, body, headers = self.request(headers=self.headers())
        self.assertEqual(status, 200)
        self.assertIn(b"FORBIDDEN", body)
        self.operator.query_core.assert_called_once_with({}, self.token)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_missing_wrong_and_revoked_tokens_do_not_dispatch(self):
        for headers in ({}, self.headers(Authorization="Bearer invalid")):
            self.assertEqual(self.request(headers=headers)[0], 403)
        self.authority.revoke(self.token)
        self.assertEqual(self.request(headers=self.headers())[0], 403)
        self.operator.query_core.assert_not_called()

    def test_browser_and_rebinding_boundaries(self):
        for extra in ({"Origin": "https://foreign.invalid"}, {"Host": "foreign.invalid"},
                      {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request(headers=self.headers(**extra))[0], 403)
        self.operator.query_core.assert_not_called()

    def test_invalid_payload_and_body_limit(self):
        for body in ("{", "[]", '{"a":1,"a":2}'):
            self.assertEqual(self.request(body, self.headers())[0], 400)
        self.assertEqual(self.request("x" * (MAX_BODY + 1), self.headers())[0], 413)
        self.operator.query_core.assert_not_called()

    def test_oversized_upload_returns_413_forty_times_then_accepts_request(self):
        for attempt in range(40):
            with self.subTest(attempt=attempt):
                status, body, _ = self.request("x" * (MAX_BODY + 1), self.headers())
                self.assertEqual((status, body), (413, b'{"error":"BODY_LIMIT"}'))
        self.operator.query_core.assert_not_called()
        self.assertEqual(self.request(headers=self.headers())[0], 200)
        self.operator.query_core.assert_called_once_with({}, self.token)

    def test_incomplete_rejected_upload_cannot_hold_single_thread(self):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.putrequest("POST", "/api/query_core")
            for key, value in self.headers().items():
                conn.putheader(key, value)
            conn.putheader("Content-Length", str(MAX_BODY + 1))
            conn.endheaders(b"x")
            # Retain the raw socket while reading 413, so the peer does not
            # send EOF and the server must enforce its drain deadline.
            response = HTTPResponse(conn.sock)
            started = monotonic()
            response.begin()
            self.assertEqual(response.status, 413)
            self.assertEqual(response.read(), b'{"error":"BODY_LIMIT"}')
            self.operator.query_core.assert_not_called()
            self.assertEqual(self.request(headers=self.headers())[0], 200)
            self.assertLess(monotonic() - started, 3)
            self.operator.query_core.assert_called_once_with({}, self.token)
        finally:
            conn.close()

    def test_truncated_allowed_upload_is_not_dispatched(self):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.putrequest("POST", "/api/query_core")
            for key, value in self.headers().items():
                conn.putheader(key, value)
            conn.putheader("Content-Length", "10")
            conn.endheaders(b"{")
            conn.sock.shutdown(socket.SHUT_WR)
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            self.assertEqual(response.read(), b'{"error":"INVALID_REQUEST"}')
        finally:
            conn.close()
        self.operator.query_core.assert_not_called()
        self.assertEqual(self.request(headers=self.headers())[0], 200)

    def test_rejected_body_drain_has_byte_chunk_and_time_limits(self):
        handler = self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
        handler.reply = Mock()
        handler.connection = Mock()
        handler.rfile = Mock()
        handler.rfile.read1.side_effect = lambda size: b"x" * size
        with patch("lukart_work.operator_host.monotonic", return_value=10):
            handler.reject_body(MAX_BODY * 100)
        sizes = [call.args[0] for call in handler.rfile.read1.call_args_list]
        self.assertEqual(sum(sizes), MAX_BODY + 1)
        self.assertLessEqual(max(sizes), 65536)
        handler.reply.assert_called_once_with(413, b'{"error":"BODY_LIMIT"}')
        handler.connection.shutdown.assert_called_once_with(socket.SHUT_WR)
        handler.connection.settimeout.assert_called_with(1)
        handler.rfile.reset_mock()
        with patch("lukart_work.operator_host.monotonic", side_effect=(10, 12)):
            handler.reject_body(MAX_BODY + 1)
        handler.rfile.read1.assert_not_called()

    def test_ambiguous_security_headers_are_rejected(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        for name, values, status in (
            ("Host", (expected, "foreign.invalid"), 403),
            ("Origin", ("http://" + expected, "https://foreign.invalid"), 403),
            ("Sec-Fetch-Site", ("same-origin", "cross-site"), 403),
            ("Content-Type", ("application/json", "text/plain"), 400),
            ("Authorization", ("Bearer " + self.token, "Bearer invalid"), 403),
            ("Content-Length", ("2", "3"), 400),
        ):
            with self.subTest(header=name):
                conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                try:
                    conn.putrequest("POST", "/api/query_core", skip_host=True)
                    headers = {"Host": expected, **self.headers(), "Content-Length": "2"}
                    headers.pop(name, None)
                    for key, value in headers.items():
                        conn.putheader(key, value)
                    for value in values:
                        conn.putheader(name, value)
                    conn.endheaders(b"{}")
                    response = conn.getresponse()
                    self.assertEqual(response.status, status)
                    response.read()
                finally:
                    conn.close()
        self.operator.query_core.assert_not_called()

    def test_bytes_returned_exactly_and_unknown_route_blocked(self):
        self.operator.query_core.return_value = b"exact-source-bytes"
        status, body, headers = self.request(headers=self.headers())
        self.assertEqual((status, body), (200, b"exact-source-bytes"))
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(self.request(headers=self.headers(), path="/api/export_local")[0], 404)

    def test_public_shell_contains_no_credentials_or_case_data(self):
        status, body, headers = self.request(method="GET", path="/", body=None)
        self.assertEqual(status, 200)
        self.assertNotIn(self.token.encode(), body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_service_exception_does_not_disclose_private_details(self):
        self.operator.query_core.side_effect = RuntimeError("private CASE content")
        status, body, _ = self.request(headers=self.headers())
        self.assertEqual(status, 500)
        self.assertEqual(body, b'{"error":"SERVICE_FAILED"}')

    def test_optional_type_bridge_cannot_be_hosted(self):
        self.operator.binding = object()
        with self.assertRaisesRegex(ValueError, "TRUSTED_CASE_OPERATOR_REQUIRED"):
            create_server(self.operator, 0)


class OperatorBrowserContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Browser contract execution requires Node.js")
    def test_open_case_emits_valid_core_query(self):
        from lukart_work.core.requests import CoreQuery
        harness = r'''
const fs=require('node:fs'),vm=require('node:vm'),elements=new Map(),calls=[];
const document={getElementById(id){if(!elements.has(id))elements.set(id,{
value:'',append(){},removeAttribute(){},replaceChildren(...children){this.children=children;}});return elements.get(id);},createElement(){return {};}};
vm.runInNewContext(fs.readFileSync(0,'utf8'),{document,window:{addEventListener(){}},
fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,
headers:{get(){return 'application/json';}},text:async()=> '{}'};},URL:{revokeObjectURL(){}}});
document.getElementById('tenant').value='00000000-0000-0000-0000-000000000001';
document.getElementById('case').value='00000000-0000-0000-0000-000000000002';
document.getElementById('open').onclick();
process.stdout.write(JSON.stringify(calls));
'''
        process = subprocess.run([shutil.which("node"), "-e", harness],
            input=CLIENT.decode(), text=True, capture_output=True, check=True, timeout=10)
        calls = json.loads(process.stdout)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["url"], "/api/query_core")
        self.assertEqual(calls[0]["options"]["credentials"], "omit")
        query = CoreQuery.model_validate_json(calls[0]["options"]["body"])
        self.assertEqual(query.operation, "GetCaseHead")
        self.assertEqual(str(query.tenant_id), "00000000-0000-0000-0000-000000000001")
        self.assertEqual(str(query.case_id), "00000000-0000-0000-0000-000000000002")


@unittest.skipUnless(os.environ.get("LUKART_TEST_DSN"), "Explicit isolated PostgreSQL DSN required")
class OperatorHostPostgresTests(unittest.TestCase):
    """Synthetic HUMAN fixture; no decisions, approvals or release."""

    request = OperatorHostTests.request
    headers = OperatorHostTests.headers
    close = OperatorHostTests.close

    def setUp(self):
        from lukart_work.finalization.contracts import FinalizationProfile
        from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
        from tests.test_stage02 import Stage02Tests
        fixture = Stage02Tests("test_scope_authorization_for_writes_and_reads")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.tenant, self.case_id = fixture.tenant, uuid4()
        self.authority = fixture.authority
        self.token = self.authority.provision(Principal(
            fixture.actor, self.tenant, self.case_id,
            frozenset({"CreateCase", "GetCaseHead"})))
        self.operator = GeneratorPismOperator(
            repository=fixture.repo,
            authority=self.authority, case_profile=FinalizationProfile(
                profile_id="urn:test:http-case", version="1.0.0",
                document_type={"id": "urn:test:document", "version": "1.0.0", "content_hash": "a" * 64},
                header="Synthetic transport test", render_profile=profile_pin(OFFICIAL_PL_V1)),
            drafting_profiles={}, provider=None, package_profile=None)
        self.server = create_server(self.operator, 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def test_authenticated_case_query_and_foreign_scope_denial(self):
        command = {"contract": "urn:lukart:work:CoreRequest:1.0.0", "operation": "CreateCase",
            "meta": {"command_id": str(uuid4()), "tenant_id": str(self.tenant),
                "case_id": str(self.case_id), "idempotency_key": str(uuid4()),
                "expected_case_sequence": 0, "correlation_id": str(uuid4())},
            "data": {"title": "Synthetic HUMAN transport CASE", "jurisdiction": "PL",
                "retention_policy": {"id": "synthetic", "version": "1.0.0", "content_hash": "a" * 64}}}
        status, body, _ = self.request(json.dumps(command), self.headers(), "/api/execute_core")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "APPLIED")
        query = {"contract": "urn:lukart:work:CoreQuery:1.0.0", "operation": "GetCaseHead",
            "tenant_id": str(self.tenant), "case_id": str(self.case_id)}
        status, body, _ = self.request(json.dumps(query), self.headers())
        self.assertEqual(status, 200)
        head = json.loads(body)
        self.assertEqual(head["result_type"], "CASE_HEAD")
        self.assertEqual(head["case_sequence"], 1)
        for field in ("tenant_id", "case_id"):
            foreign = dict(query, **{field: str(uuid4())})
            status, body, _ = self.request(json.dumps(foreign), self.headers())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["code"], "FORBIDDEN")
        self.authority.revoke(self.token)
        self.assertEqual(self.request(json.dumps(query), self.headers())[0], 403)


class OperatorGuidedCaseUIContractTests(unittest.TestCase):
    """Static safety contract for the non-automatic, human-gated CASE wizard."""

    def test_guided_case_creation_never_auto_dispatches(self):
        from lukart_work.operator_host import PAGE, CLIENT
        html = PAGE.decode('utf-8')
        js = CLIENT.decode('utf-8')
        for field in ('caseTitle', 'policyId', 'policyVersion', 'policyHash',
                      'prepareCase', 'advanced', 'send'):
            self.assertIn(f'id="{field}"', html)
        self.assertIn("route.value='execute_core';request.value=JSON.stringify(body,null,2)", js)
        self.assertNotIn("submit('execute_core',body)", js)
        self.assertIn('expected_case_sequence:0', js)
        self.assertIn("rationale:'Jawna decyzja", js)
        self.assertIn("function clearPrivate()", js)
        self.assertIn('caseTitle.value=''', js)
        for contract in ('PlannerQuery:1.0.0', 'ValidationQuery:1.0.0',
                         'FinalizationQuery:1.0.0'):
            self.assertIn(contract, js)
        self.assertIn('Number.isSafeInteger(revision)', js)
        self.assertIn('function idReady(...ids)', js)

    def test_guided_case_does_not_weaken_existing_boundaries(self):
        from lukart_work.operator_host import create_server, CLIENT, MAX_BODY
        self.assertGreater(MAX_BODY, 0)
        self.assertIn("credentials:'omit'", CLIENT.decode())
        self.assertTrue(callable(create_server))
