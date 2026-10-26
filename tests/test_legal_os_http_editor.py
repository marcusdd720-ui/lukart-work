"""One-window HTTP synthetic workflow: session -> list drafts -> edit -> native WORK."""
from http.client import HTTPConnection
from json import dumps, loads
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from lukart_work.contracts.messages import CaseHeadResult, CommandResult
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor, Ref
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server


class FakeProjection:
    pass


class SessionEditorHTTPTests(TestCase):
    def setUp(self):
        self.tenant, self.case, self.draft_id, self.statement = [uuid4() for _ in range(4)]
        self.authority=TokenAuthority()
        self.rights=frozenset(("GetCaseHead","GetRevision","AmendDraft"))
        self.token=self.authority.provision(Principal(
            Actor(id=uuid4(),kind="HUMAN"),self.tenant,self.case,self.rights
        ))
        self.operator=GeneratorPismOperator.__new__(GeneratorPismOperator)
        self.operator.binding=None
        self.operator.core=SimpleNamespace(authority=self.authority)
        self.calls=[]
        def query(request, token):
            self.calls.append(("query_core",request))
            return CaseHeadResult(result_type="CASE_HEAD",tenant_id=self.tenant,case_id=self.case,
                case_sequence=3,heads=(Ref(kind="Draft",id=self.draft_id,revision=2),))
        self.operator.query_core=query
        draft=SimpleNamespace(
            tenant_id=self.tenant,case_id=self.case,id=self.draft_id,
            revision=2,status="GENERATED",
            sections=(SimpleNamespace(section=Ref(kind="Section",id=uuid4(),revision=1),
                statements=(SimpleNamespace(id=self.statement,text="Treść początkowa",
                     statement_type="REQUEST"),)),)
        )
        self.projection=FakeProjection()
        self.projection.draft=draft
        self.projection.draft_hash="a"*64
        self.projection.case_sequence=3
        self.projection.editable=True
        self.operator.query_draft=lambda payload,token:self.projection
        def execute(request,token):
            self.calls.append(("execute_core",request))
            return CommandResult(command_id=uuid4(),state="APPLIED",case_sequence=4,
                refs=(Ref(kind="Draft",id=uuid4(),revision=2),),event_ids=(),errors=())
        self.operator.execute_core=execute
        self.patch=patch("lukart_work.legal_os_editor.DraftEditorProjection",FakeProjection)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.server=create_server(self.operator,0)
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def call(self, payload):
        conn=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            conn.request("POST","/api/embedded_session",dumps(payload),
                {"Content-Type":"application/json","Authorization":"Bearer "+self.token})
            response=conn.getresponse()
            return response.status,response.read()
        finally:
            conn.close()

    def test_one_window_http_proceeds_through_work_without_renderer(self):
        status,body=self.call({"action":"list_drafts"})
        self.assertEqual(status,200)
        listing=loads(body)
        self.assertEqual(listing["result_type"],"DRAFT_LIST")
        self.assertEqual(listing["drafts"][0]["id"],str(self.draft_id))
        status,body=self.call({"action":"open_draft",
            "draft_id":str(self.draft_id),"revision":2})
        self.assertEqual(status,200)
        projection=loads(body)
        self.assertEqual(projection["result_type"],"DRAFT_FOR_EDITING")
        self.assertEqual(projection["sections"][0]["statements"][0]["text"],"Treść początkowa")
        request={
            "action":"amend_draft","draft_id":str(self.draft_id),"revision":2,
            "draft_hash":"a"*64,"expected_case_sequence":3,
            "edits":[{"statement_id":str(self.statement),"text":"Treść zaktualizowana"}],
            "rationale":"Jawna poprawka właścicielska",
            "command_id":str(uuid4()),"idempotency_key":str(uuid4()),"correlation_id":str(uuid4())
        }
        status,body=self.call(request)
        self.assertEqual(status,200)
        result=loads(body)
        self.assertEqual(result["result_type"],"DRAFT_AMENDED")
        self.assertEqual(result["approval"],"NOT_GRANTED")
        self.assertEqual(result["render"],"NOT_STARTED")
        writes=[c for c in self.calls if c[0]=="execute_core"]
        self.assertEqual(len(writes),1)
        self.assertEqual(writes[0][1]["operation"],"AmendDraft")

    def test_forged_case_in_session_action_rejected(self):
        status,_=self.call({"action":"open_draft",
            "draft_id":str(self.draft_id),"revision":2,"case_id":str(uuid4())})
        self.assertEqual(status,403)
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    import unittest
    unittest.main()
