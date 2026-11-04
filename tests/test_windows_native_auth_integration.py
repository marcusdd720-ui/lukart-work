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

@unittest.skipUnless(sys.platform=="win32" and importlib.util.find_spec("spnego"),"Windows SSPI extra required")
class SspiHttpTests(unittest.TestCase):
 def test_real_windows_sid_to_http_only_human_cookie(self):
  import spnego
  domain=os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME","");sid=account_name_to_sid(domain+"\\"+os.environ.get("USERNAME",""))
  tenant,case,actor=str(uuid4()),str(uuid4()),str(uuid4())
  d={"schema":"urn:lukart:work:WindowsHumanIdentityPolicy:1.0.0","policy_id":"SYNTHETIC","session_ttl_seconds":300,
     "principals":[{"sid":sid,"actor_id":actor,"tenant_id":tenant,"case_id":case,"actions":["GetCaseHead"],"enabled":True}]}
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"policy.json";p.write_text(json.dumps(d),encoding="utf-8")
   authority=TokenAuthority();manager=WindowsHumanAuthManager(authority,WindowsHumanIdentityPolicy.from_path(p))
   op=GeneratorPismOperator.__new__(GeneratorPismOperator);op.binding=None;op.core=SimpleNamespace(authority=authority)
   op.query_core=Mock(return_value=safe_error("FORBIDDEN",uuid4()))
   server=create_frontend_server(op,manager,0);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    port=server.server_port;host=f"localhost:{port}";c=HTTPConnection("127.0.0.1",port,timeout=10)
    c.request("GET","/",headers={"Host":host});r=c.getresponse();self.assertEqual(r.status,401)
    self.assertEqual(r.getheader("WWW-Authenticate"),"Negotiate")
    handshake=next(x.split(";",1)[0] for x in r.headers.get_all("Set-Cookie") if x.startswith("LUKART_NEGOTIATE="));r.read();c.close()
    client=spnego.client(protocol="negotiate",hostname="localhost",service="HTTP",options=spnego.NegotiateOptions.use_sspi)
    client_token=client.step();session=None
    for _ in range(5):
     c=HTTPConnection("127.0.0.1",port,timeout=10)
     c.request("GET","/",headers={"Host":host,"Cookie":handshake,"Authorization":"Negotiate "+base64.b64encode(client_token).decode()})
     r=c.getresponse();body=r.read();cookies=r.headers.get_all("Set-Cookie") or []
     if r.status==200:
      session=next(x.split(";",1)[0] for x in cookies if x.startswith("LUKART_SESSION="))
      self.assertNotIn(b"LUKART_SESSION",body);self.assertIn(b"NATIVE-SSPI-SESSION",body)
      self.assertTrue(any("HttpOnly" in x and "SameSite=Strict" in x for x in cookies));c.close();break
     self.assertEqual(r.status,401);challenge=r.getheader("WWW-Authenticate")
     client_token=client.step(base64.b64decode(challenge.split(" ",1)[1]) if challenge!="Negotiate" else None)
     handshake=next(x.split(";",1)[0] for x in cookies if x.startswith("LUKART_NEGOTIATE="));c.close()
    self.assertIsNotNone(session);token=session.split("=",1)[1]
    c=HTTPConnection("127.0.0.1",port,timeout=10)
    c.request("POST","/api/query_core",body="{}",headers={"Host":host,"Origin":"http://"+host,
      "Sec-Fetch-Site":"same-origin","Cookie":session,"Content-Type":"application/json",
      "Authorization":"Bearer NATIVE-SSPI-SESSION"})
    r=c.getresponse();body=r.read();self.assertEqual(r.status,200,body);c.close()
    op.query_core.assert_called_once_with({},token)
    with authority.session(token) as principal:
     self.assertEqual(principal.actor.kind,"HUMAN");self.assertEqual(str(principal.actor.id),actor)
     self.assertEqual(str(principal.tenant_id),tenant);self.assertEqual(str(principal.case_id),case)
   finally:server.shutdown();server.server_close();thread.join(timeout=5)

def load_tests(loader, tests, pattern):
    if sys.platform != "win32" or importlib.util.find_spec("spnego") is None:
        return unittest.TestSuite()
    return tests

if __name__=="__main__":unittest.main()
