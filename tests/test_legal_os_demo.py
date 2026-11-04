"""New demo smoke checks only; no historical suite or WORK sessions."""
import json
import threading
from unittest import TestCase
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lukart_work.legal_os_demo import make_server


class DemoSmoke(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)

    def call(self, path, data=None, origin=True):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = self.url
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read(), response.headers
        except HTTPError as exc:
            try:
                return exc.code, exc.read(), exc.headers
            finally:
                exc.close()

    def test_real_http_page_and_explicit_demo_identity(self):
        status, page, headers = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn('id="compose-sender-name"', page.decode())
        self.assertNotIn('id="token"', page.decode())
        self.assertNotIn('/case.js', page.decode())
        self.assertIn("brak połączenia z WORK", page.decode())
        self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
        self.assertFalse(json.loads(self.call("/health")[1])["work_connected"])

    def test_existing_composer_validation_and_invalid_input(self):
        party = {"name": "Osoba Syntetyczna", "address": {"lines": ["ul. Syntetyczna 1", "Miasto Testowe"], "postal_code": "00-000", "country": "PL"}}
        form = {"description": "Wyłącznie przykład syntetyczny", "document_type": "synthetic-request", "sender": party, "recipient": party}
        status, body, _ = self.call("/demo/validate", form)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["generator_invoked"])
        self.assertFalse(json.loads(body)["saved"])
        form["description"] = ""
        self.assertEqual(self.call("/demo/validate", form)[0], 400)

    def test_production_routes_and_cross_origin_denied(self):
        for path in ("/api/embedded_session", "/api/generate", "/api/approve", "/api/download"):
            self.assertEqual(self.call(path, {"action": "generate_document"})[0], 403)
        self.assertEqual(self.call("/demo/validate", {}, origin=False)[0], 403)
        self.assertEqual(self.call("/../connection.json")[0], 404)
