"""Only LEGAL OS is visible when the trusted host selects case_only=True."""
import json
from http.client import HTTPConnection
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from lukart_work import operator_host
from lukart_work.core.security import TokenAuthority
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server


class CaseOnlyHostTests(TestCase):
    def setUp(self):
        self.operator=GeneratorPismOperator.__new__(GeneratorPismOperator)
        self.operator.binding=None
        self.authority=TokenAuthority()
        self.operator.core=SimpleNamespace(authority=self.authority)
        self.server=create_server(self.operator,0,case_only=True)
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self,path):
        connection=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            connection.request("GET",path)
            response=connection.getresponse()
            return response.status,response.read()
        finally:
            connection.close()

    def test_root_only_exposes_case_workspace(self):
        status,body=self.get("/")
        self.assertEqual(status,200)
        self.assertIn(b"/case.js",body)
        self.assertIn(b"Moja sprawa",body)
        self.assertNotIn(b"/client.js",body)

    def test_legacy_operator_assets_hidden(self):
        for path in ("/client.js","/client.css"):
            with self.subTest(path=path):
                status,_=self.get(path)
                self.assertEqual(status,404)

    def test_legacy_post_routes_are_not_available_in_case_only_mode(self):
        for path in ("/api/execute_core", "/api/query_core", "/api/upload_source",
                     "/api/embedded_case", "/api/execute_finalization"):
            with self.subTest(path=path):
                connection=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
                try:
                    connection.request("POST",path,"{}",{"Content-Type":"application/json"})
                    response=connection.getresponse()
                    self.assertEqual(response.status,404)
                    response.read()
                finally:
                    connection.close()

    def test_case_js_still_available(self):
        status,script=self.get("/case.js")
        self.assertEqual(status,200)
        self.assertIn(b"/api/embedded_session",script)

    def test_authenticated_embedded_session_reaches_read_only_dispatcher(self):
        token=self.authority.provision(SimpleNamespace(kind="HUMAN"))
        payload={"action":"composition_context"}
        with patch.object(operator_host,"read_session_case_action",return_value={"state":"FOUND"}) as dispatch:
            connection=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
            try:
                connection.request("POST","/api/embedded_session",json.dumps(payload),{
                    "Content-Type":"application/json","Authorization":f"Bearer {token}"
                })
                response=connection.getresponse()
                body=response.read()
            finally:
                connection.close()
        self.assertEqual(response.status,200)
        self.assertEqual(json.loads(body),{"state":"FOUND"})
        dispatch.assert_called_once_with(self.operator,payload,token)

    def test_invalid_embedded_session_token_fails_before_dispatch(self):
        payload={"action":"composition_context"}
        with patch.object(operator_host,"read_session_case_action",return_value={"state":"FOUND"}) as dispatch:
            connection=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
            try:
                connection.request("POST","/api/embedded_session",json.dumps(payload),{
                    "Content-Type":"application/json","Authorization":"Bearer invalid-token"
                })
                response=connection.getresponse()
                body=response.read()
            finally:
                connection.close()
        self.assertEqual(response.status,403)
        self.assertEqual(json.loads(body),{"error":"FORBIDDEN"})
        dispatch.assert_not_called()

    def test_invalid_host_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,"CASE_ONLY_FLAG_INVALID"):
            create_server(self.operator,0,case_only="true")


if __name__=="__main__":
    import unittest
    unittest.main()
