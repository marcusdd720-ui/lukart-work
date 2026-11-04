"""Stage 02 only: immutable historical files, serving and integrity denial."""
import json
import threading
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lukart_work import legal_os_demo as demo


class ExampleDownloads(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo.make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)

    def get(self, path, base=None, form=None):
        url = base or self.url
        headers = {"Origin": url, "Content-Type": "application/json"}
        request = Request(url + path, headers=headers, data=None if form is None else json.dumps(form).encode())
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read(), response.headers
        except HTTPError as response:
            try:
                return response.code, response.read(), response.headers
            finally:
                response.close()

    def test_exact_pair_and_real_pdf_raster_downloads(self):
        for name, (mime, expected) in demo.EXAMPLE_FILES.items():
            status, data, headers = self.get("/demo/example/" + name)
            self.assertEqual(status, 200)
            self.assertEqual(sha256(data).hexdigest(), expected)
            self.assertEqual(headers["Content-Type"], mime)
            self.assertIn(name, headers["Content-Disposition"])
            self.assertEqual(headers["X-Content-SHA256"], expected)
            if not name.endswith(".png"):
                self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        _, pdf, headers = self.get("/demo/example/preview.pdf")
        self.assertEqual(sha256(pdf).hexdigest(), demo.EXAMPLE_FILES["przyklad-demonstracyjny.pdf"][1])
        self.assertTrue(headers["Content-Disposition"].startswith("inline;"))
        page = self.get("/")[1].decode()
        self.assertIn("PRZYKŁAD DEMONSTRACYJNY — NIEGENEROWANY NA ŻYWO", page)
        self.assertIn('id="example-title"', page)
        self.assertIn('src="/demo/example/przyklad-demonstracyjny.png"', page)

    def test_form_changes_never_change_example_bytes(self):
        name = "przyklad-demonstracyjny.pdf"
        before = self.get("/demo/example/" + name)[1]
        party = {"name": "Inna Osoba Syntetyczna", "address": {"lines": ["ul. Testowa 999", "Miasto Testowe"], "postal_code": "00-000", "country": "PL"}}
        form = {"description": "Inny opis wyłącznie syntetyczny", "document_type": "synthetic-letter", "sender": party, "recipient": party}
        self.assertEqual(self.get("/demo/validate", form=form)[0], 200)
        self.assertEqual(before, self.get("/demo/example/" + name)[1])

    def test_only_fixed_example_files_are_exposed(self):
        for suffix in ("../legal_os_demo.py", "SOURCE_MANIFEST.json", "przyklad-demonstracyjny.pdf?case=other", "%2e%2e/connection.json"):
            self.assertEqual(self.get("/demo/example/" + suffix)[0], 404)

    def test_incomplete_or_tampered_pair_denies_all_examples(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name in demo.EXAMPLE_FILES:
                (root / name).write_bytes((demo.EXAMPLE_DIR / name).read_bytes())
            for kind in ("tampered", "missing"):
                docx = root / "przyklad-demonstracyjny.docx"
                if kind == "tampered":
                    docx.write_bytes(b"not the approved synthetic example")
                else:
                    docx.unlink()
                with patch.object(demo, "EXAMPLE_DIR", root):
                    server = demo.make_server(0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    url = f"http://127.0.0.1:{server.server_port}"
                    self.assertIn("PRZYKŁAD ZABLOKOWANY", self.get("/", base=url)[1].decode())
                    for name in demo.EXAMPLE_FILES:
                        self.assertEqual(self.get("/demo/example/" + name, base=url)[0], 404)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(3)
