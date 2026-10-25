"""Synthetic transport regressions; no network, credentials or provider calls."""
from __future__ import annotations

import importlib.util
import io
import os
from email.message import Message
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.response import addinfourl


ROOT = Path(__file__).resolve().parents[1]


def controls():
    for stage in (11, 12):
        spec = importlib.util.spec_from_file_location(
            f"stage{stage}_transport", ROOT / "scripts" / f"stage{stage}_delivery_control.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module


def response(url, status, body=b"{}", location=None):
    headers = Message()
    if location:
        headers["Location"] = location
    result = addinfourl(io.BytesIO(body), headers, url, status)
    result.msg = "synthetic response"
    return result


class DeliveryTransportSecurityTests(unittest.TestCase):
    def test_redirects_cannot_forward_bearer_to_another_origin(self):
        for control in controls():
            for status in (301, 302, 303, 307, 308):
                with self.subTest(control=control.__name__, status=status):
                    seen = []

                    def transport(handler, request):
                        seen.append((request.full_url, request.get_header("Authorization")))
                        if len(seen) == 1:
                            return response(request.full_url, status,
                                            location="https://untrusted.invalid/collect")
                        return response(request.full_url, 200)

                    with patch.dict(os.environ, {"GH_TOKEN": "synthetic-test-capability"}), \
                         patch("urllib.request.HTTPSHandler.https_open", transport):
                        with self.assertRaises(control.ControlError):
                            control._request("GET", "https://api.github.com/repos/example/repo")
                    self.assertEqual(len(seen), 1)

    def test_untrusted_urls_fail_before_any_transport(self):
        urls = (
            "http://api.github.com/repos/example/repo",
            "https://api.github.com.untrusted.invalid/repos/example/repo",
            "https://user@api.github.com/repos/example/repo",
            "https://api.github.com:444/repos/example/repo",
            "https://untrusted.invalid/collect",
        )
        for control in controls():
            for url in urls:
                with self.subTest(control=control.__name__, url=url), \
                     patch.dict(os.environ, {"GH_TOKEN": "synthetic-test-capability"}), \
                     patch("urllib.request.HTTPSHandler.https_open") as transport:
                    with self.assertRaises(control.ControlError):
                        control._request("GET", url)
                    transport.assert_not_called()

    def test_http_error_body_is_not_exposed_but_404_is_recognizable(self):
        for control in controls():
            def transport(handler, request):
                return response(request.full_url, 404,
                                b'{"private": "synthetic-private-response-marker"}')

            with self.subTest(control=control.__name__), \
                 patch.dict(os.environ, {"GH_TOKEN": "synthetic-test-capability",
                                         "GITHUB_REPOSITORY": "example/repo"}), \
                 patch("urllib.request.HTTPSHandler.https_open", transport):
                with self.assertRaises(control.ControlError) as caught:
                    control._request("GET", "https://api.github.com/repos/example/repo")
                self.assertNotIn("synthetic-private-response-marker", str(caught.exception))
                self.assertIn(" 404 ", str(caught.exception))
                self.assertIsNone(control._try_get("/synthetic-missing"))

    def test_allowed_json_and_empty_responses_remain_supported(self):
        for control in controls():
            for url, status, body, expected in (
                ("https://api.github.com/graphql", 200, b'{"data": {}}', {"data": {}}),
                ("https://api.github.com/repos/example/repo", 204, b"", None),
            ):
                seen = []

                def transport(handler, request):
                    seen.append(request.get_header("Authorization"))
                    return response(request.full_url, status, body)

                with self.subTest(control=control.__name__, url=url), \
                     patch.dict(os.environ, {"GH_TOKEN": "synthetic-test-capability"}), \
                     patch("urllib.request.HTTPSHandler.https_open", transport):
                    self.assertEqual(control._request("GET", url), expected)
                    self.assertEqual(seen, ["Bearer synthetic-test-capability"])


if __name__ == "__main__":
    unittest.main()
