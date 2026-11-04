import base64,importlib.util,json,os,sys,tempfile,unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from lukart_work.core.security import TokenAuthority
from lukart_work.core.service import safe_error
from lukart_work.operator import GeneratorPismOperator
from native_windows.frontend import create_frontend_server
from native_windows.windows_identity import WindowsHumanAuthManager,WindowsHumanIdentityPolicy,account_name_to_sid


def _is_local_admin():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


@unittest.skipUnless(
    sys.platform == "win32" and importlib.util.find_spec("spnego") and _is_local_admin(),
    "Windows SSPI extra and local Administrators token required",
)
class SspiHttpTests(unittest.TestCase):
    def test_real_windows_sid_to_http_only_human_cookie(self):
        import spnego
        domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME", "")
        sid = account_name_to_sid(domain + "\\" + os.environ.get("USERNAME", ""))
        tenant, case, actor = str(uuid4()), str(uuid4()), str(uuid4())
        document = {
            "schema": "urn:lukart:work:WindowsHumanIdentityPolicy:1.0.0",
            "policy_id": "SYNTHETIC",
            "session_ttl_seconds": 300,
            "principals": [{
                "sid": sid,
                "actor_id": actor,
                "tenant_id": tenant,
                "case_id": case,
                "actions": ["GetCaseHead"],
                "enabled": True,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(json.dumps(document), encoding="utf-8")
            authority = TokenAuthority()
            manager = WindowsHumanAuthManager(authority, WindowsHumanIdentityPolicy.from_path(policy_path))
            operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
            operator.binding = None
            operator.core = SimpleNamespace(authority=authority)
            operator.query_core = Mock(return_value=safe_error("FORBIDDEN", uuid4()))
            server = create_frontend_server(operator, manager, 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_port
                host = f"localhost:{port}"
                connection = HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request("GET", "/", headers={"Host": host})
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                self.assertEqual(response.getheader("WWW-Authenticate"), "Negotiate")
                handshake_cookie = next(
                    item.split(";", 1)[0]
                    for item in response.headers.get_all("Set-Cookie")
                    if item.startswith("LUKART_NEGOTIATE=")
                )
                response.read()
                connection.close()

                client = spnego.client(
                    protocol="negotiate",
                    hostname="localhost",
                    service="HTTP",
                    options=spnego.NegotiateOptions.use_sspi,
                )
                client_token = client.step()
                session_cookie = None
                for _ in range(5):
                    connection = HTTPConnection("127.0.0.1", port, timeout=10)
                    connection.request(
                        "GET",
                        "/",
                        headers={
                            "Host": host,
                            "Cookie": handshake_cookie,
                            "Authorization": "Negotiate " + base64.b64encode(client_token).decode(),
                        },
                    )
                    response = connection.getresponse()
                    body = response.read()
                    cookies = response.headers.get_all("Set-Cookie") or []
                    if response.status == 200:
                        session_cookie = next(
                            item.split(";", 1)[0] for item in cookies if item.startswith("LUKART_SESSION=")
                        )
                        self.assertNotIn(b"LUKART_SESSION", body)
                        self.assertIn(b"NATIVE-SSPI-SESSION", body)
                        self.assertTrue(any("HttpOnly" in item and "SameSite=Strict" in item for item in cookies))
                        connection.close()
                        break
                    self.assertEqual(response.status, 401)
                    challenge = response.getheader("WWW-Authenticate")
                    client_token = client.step(
                        base64.b64decode(challenge.split(" ", 1)[1]) if challenge != "Negotiate" else None
                    )
                    handshake_cookie = next(
                        item.split(";", 1)[0] for item in cookies if item.startswith("LUKART_NEGOTIATE=")
                    )
                    connection.close()

                self.assertIsNotNone(session_cookie)
                token = session_cookie.split("=", 1)[1]
                connection = HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request(
                    "POST",
                    "/api/query_core",
                    body="{}",
                    headers={
                        "Host": host,
                        "Origin": "http://" + host,
                        "Sec-Fetch-Site": "same-origin",
                        "Cookie": session_cookie,
                        "Content-Type": "application/json",
                        "Authorization": "Bearer NATIVE-SSPI-SESSION",
                    },
                )
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, body)
                connection.close()
                operator.query_core.assert_called_once_with({}, token)
                with authority.session(token) as principal:
                    self.assertEqual(principal.actor.kind, "HUMAN")
                    self.assertEqual(str(principal.actor.id), actor)
                    self.assertEqual(str(principal.tenant_id), tenant)
                    self.assertEqual(str(principal.case_id), case)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


def load_tests(loader, tests, pattern):
    if sys.platform != "win32" or importlib.util.find_spec("spnego") is None or not _is_local_admin():
        return unittest.TestSuite()
    return tests


if __name__ == "__main__":
    unittest.main()
