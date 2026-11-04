import base64,json,tempfile,unittest
from pathlib import Path
from uuid import uuid4
from lukart_work.core.security import TokenAuthority
from lukart_work.validation.rules import Violation
from lukart_work.windows_identity import WindowsHumanAuthManager,WindowsHumanIdentityPolicy,WindowsIdentityError
SID="S-1-5-21-1-2-3-1001"
def doc(actions=None,enabled=True):
 return {"schema":"urn:lukart:work:WindowsHumanIdentityPolicy:1.0.0","policy_id":"TEST","session_ttl_seconds":60,
 "principals":[{"sid":SID,"actor_id":str(uuid4()),"tenant_id":str(uuid4()),"case_id":str(uuid4()),
 "actions":actions or ["GetCaseHead"],"enabled":enabled}]}
def load(d):
 td=tempfile.TemporaryDirectory();p=Path(td.name)/"p.json";p.write_text(json.dumps(d),encoding="utf-8")
 return td,WindowsHumanIdentityPolicy.from_path(p)
class FakeContext:
 def __init__(self):self.complete=False;self.client_principal="TESTDOMAIN\\operator"
 def step(self,t):
  if t==b"c1":return b"s1"
  if t==b"c2":self.complete=True;return None
  raise ValueError("bad")
class PolicyTests(unittest.TestCase):
 def test_exact_sid_maps_to_human_case_scope(self):
  td,p=load(doc(["GetCaseHead","GetRevision"]));self.addCleanup(td.cleanup);v=p.resolve_sid(SID)
  self.assertEqual(v.actor.kind,"HUMAN");self.assertEqual(v.actions,frozenset({"GetCaseHead","GetRevision"}));self.assertEqual(len(p.digest),64)
 def test_unknown_disabled_wildcard_duplicate_fail_closed(self):
  td,p=load(doc(enabled=False));self.addCleanup(td.cleanup)
  with self.assertRaises(WindowsIdentityError):p.resolve_sid(SID)
  with self.assertRaises(WindowsIdentityError):p.resolve_sid("S-1-5-21-1-2-3-9")
  td2=tempfile.TemporaryDirectory();self.addCleanup(td2.cleanup);path=Path(td2.name)/"p.json"
  path.write_text(json.dumps(doc(["*"])),encoding="utf-8")
  with self.assertRaises(WindowsIdentityError):WindowsHumanIdentityPolicy.from_path(path)
  d=doc();d["principals"].append(d["principals"][0]);path.write_text(json.dumps(d),encoding="utf-8")
  with self.assertRaises(WindowsIdentityError):WindowsHumanIdentityPolicy.from_path(path)
 def test_boolean_ttl_unknown_field_and_relative_path_rejected(self):
  td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);path=Path(td.name)/"p.json"
  for d in ({**doc(),"session_ttl_seconds":True},{**doc(),"unexpected":1}):
   path.write_text(json.dumps(d),encoding="utf-8")
   with self.assertRaises(WindowsIdentityError):WindowsHumanIdentityPolicy.from_path(path)
  with self.assertRaises(WindowsIdentityError):WindowsHumanIdentityPolicy.from_path(Path("relative.json"))
class ManagerTests(unittest.TestCase):
 def setUp(self):
  self.td,self.policy=load(doc());self.addCleanup(self.td.cleanup);self.authority=TokenAuthority()
  self.manager=WindowsHumanAuthManager(self.authority,self.policy,context_factory=FakeContext,sid_resolver=lambda _:SID)
  self.addCleanup(self.manager.close)
 def handshake(self,m=None):
  m=m or self.manager;a=m.authenticate(session_token=None,handshake_id=None,authorization=None)
  b=m.authenticate(session_token=None,handshake_id=a.handshake_id,authorization="Negotiate "+base64.b64encode(b"c1").decode())
  c=m.authenticate(session_token=None,handshake_id=b.handshake_id,authorization="Negotiate "+base64.b64encode(b"c2").decode())
  self.assertEqual((a.state,b.state,c.state),("CHALLENGE","CONTINUE","AUTHENTICATED"));return c.session_token
 def test_human_capability_has_exact_case_scope(self):
  token=self.handshake()
  with self.authority.session(token) as p:self.assertEqual(p.actor.kind,"HUMAN");self.assertEqual(p.actions,frozenset({"GetCaseHead"}))
  self.assertEqual(self.manager.authenticate(session_token=token,handshake_id=None,authorization=None).state,"AUTHENTICATED")
 def test_malformed_token_denied(self):
  a=self.manager.authenticate(session_token=None,handshake_id=None,authorization=None)
  self.assertEqual(self.manager.authenticate(session_token=None,handshake_id=a.handshake_id,authorization="Negotiate !!!").state,"DENIED")
 def test_expired_session_revoked(self):
  now=[0.0];m=WindowsHumanAuthManager(self.authority,self.policy,context_factory=FakeContext,sid_resolver=lambda _:SID,clock=lambda:now[0])
  self.addCleanup(m.close);token=self.handshake(m);now[0]=61
  self.assertEqual(m.authenticate(session_token=token,handshake_id=None,authorization=None).state,"CHALLENGE")
  with self.assertRaises(Violation):
   with self.authority.session(token):pass
 def test_close_revokes_token(self):
  token=self.handshake();self.manager.close()
  with self.assertRaises(Violation):
   with self.authority.session(token):pass
if __name__=="__main__":unittest.main()
