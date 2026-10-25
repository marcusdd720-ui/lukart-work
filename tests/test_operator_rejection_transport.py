"""Synthetic regressions for early POST rejection without losing HTTP responses."""
from email.message import Message
from http.client import HTTPConnection, HTTPResponse
from time import monotonic
import unittest
from unittest.mock import Mock

from lukart_work.operator_host import MAX_BODY
from tests import test_operator_host as host_tests


class RejectedTransportTests(unittest.TestCase):
    setUp = host_tests.OperatorHostTests.setUp
    close = host_tests.OperatorHostTests.close
    request = host_tests.OperatorHostTests.request
    headers = host_tests.OperatorHostTests.headers

    def test_browser_denials_deliver_403_with_allowed_size_uploads(self):
        for header in ({"Origin": "https://foreign.invalid"}, {"Host": "foreign.invalid"},
                       {"Sec-Fetch-Site": "cross-site"}):
            for attempt in range(3):
                with self.subTest(header=next(iter(header)), attempt=attempt):
                    status, body, _ = self.request("{}" + " " * (MAX_BODY - 2), self.headers(**header))
                    self.assertEqual((status, body), (403, b'{"error":"FORBIDDEN"}'))
        self.operator.query_core.assert_not_called()
        self.assertEqual(self.request(headers=self.headers())[0], 200)

    def test_other_early_rejections_deliver_response_without_dispatch(self):
        for headers, path, expected in (
            ({}, "/api/query_core", 403),
            (self.headers(Authorization="Bearer invalid"), "/api/query_core", 403),
            (self.headers(), "/api/unknown", 404),
            (self.headers(**{"Content-Type": "text/plain"}), "/api/query_core", 400),
        ):
            with self.subTest(status=expected, path=path):
                self.assertEqual(self.request("{}" + " " * (MAX_BODY - 2), headers, path)[0], expected)
        self.operator.query_core.assert_not_called()

    def test_authenticated_huge_content_length_delivers_400_without_dispatch(self):
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                status, body, _ = self.request("x" * MAX_BODY,
                    self.headers(**{"Content-Length": "9" * 5000}))
                self.assertEqual((status, body), (400, b'{"error":"INVALID_REQUEST"}'))
        self.operator.query_core.assert_not_called()
        self.assertEqual(self.request(headers=self.headers())[0], 200)

    def test_incomplete_forbidden_upload_has_bounded_drain_and_recovery(self):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.putrequest("POST", "/api/query_core")
            for key, value in self.headers(Origin="https://foreign.invalid").items():
                conn.putheader(key, value)
            conn.putheader("Content-Length", str(MAX_BODY))
            conn.endheaders(b"x")
            response = HTTPResponse(conn.sock)
            started = monotonic()
            response.begin()
            self.assertEqual(response.status, 403)
            self.assertEqual(response.read(), b'{"error":"FORBIDDEN"}')
            self.operator.query_core.assert_not_called()
            self.assertEqual(self.request(headers=self.headers())[0], 200)
            self.assertLess(monotonic() - started, 3)
        finally:
            conn.close()

    def test_ambiguous_or_huge_framing_never_creates_unbounded_drain(self):
        for lengths, transfer in ((["2", "3"], None), (["9" * 5000], None),
                                  (["-1"], None), (["2"], "chunked"), (["2"], None)):
            with self.subTest(length_count=len(lengths), transfer=transfer):
                handler = self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
                handler.headers = Message()
                for value in lengths:
                    handler.headers["Content-Length"] = value
                if transfer:
                    handler.headers["Transfer-Encoding"] = transfer
                handler.reject_body = Mock()
                handler.reject_request(403, b'{"error":"FORBIDDEN"}')
                budget = handler.reject_body.call_args.args[0]
                self.assertGreaterEqual(budget, 0)
                self.assertLessEqual(budget, MAX_BODY + 1)
                self.assertEqual(budget, 2 if lengths == ["2"] and transfer is None else MAX_BODY + 1)
