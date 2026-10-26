"""Focused tests of the unified WORK editor: read/modify, never auto approve."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from lukart_work.contracts.messages import CommandResult
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor, Ref
from lukart_work.embedded_document_engine import EngineBoundaryError
from lukart_work.legal_os_editor import edit_action
from tests.test_embedded_document_engine import FakeOperator


class FakeCaseHead:
    pass


class FakeDraftProjection:
    pass


class EditorTests(TestCase):
    def setUp(self):
        self.tenant, self.case, self.draft_id, self.statement = [uuid4() for _ in range(4)]
        self.auth = TokenAuthority()
        self.rights = frozenset(("GetCaseHead", "GetRevision", "AmendDraft"))
        self.token = self.auth.provision(
            Principal(Actor(id=uuid4(), kind="HUMAN"), self.tenant, self.case, self.rights)
        )
        self.operator = FakeOperator()
        self.operator.core = SimpleNamespace(authority=self.auth)
        self.head = FakeCaseHead()
        self.head.case_sequence = 8
        self.head.heads = (Ref(kind="Draft", id=self.draft_id, revision=2),)
        self.projection = FakeDraftProjection()
        self.projection.draft_hash = "a"*64
        self.projection.case_sequence = 8
        self.projection.editable = True
        self.projection.draft = SimpleNamespace(
            id=self.draft_id, tenant_id=self.tenant, case_id=self.case,
            revision=2, status="GENERATED", sections=(
                SimpleNamespace(section=Ref(kind="Section", id=uuid4(), revision=1),
                                statements=(SimpleNamespace(id=self.statement,
                                                            text="Żądanie pierwotne",
                                                            statement_type="REQUEST"),)),
            )
        )
        self.operator.query_core = lambda data,token: self.head
        self.operator.query_draft = lambda data,token: self.projection
        self.dispatched = []
        def write(data,token):
            self.dispatched.append((data,token))
            return CommandResult(command_id=uuid4(),state="APPLIED",case_sequence=9,
                                 refs=(Ref(kind="Draft",id=uuid4(),revision=2),),
                                 event_ids=(),errors=())
        self.operator.execute_core = write
        patches=[
            patch("lukart_work.legal_os_editor.CaseHeadResult",FakeCaseHead),
            patch("lukart_work.legal_os_editor.DraftEditorProjection",FakeDraftProjection),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def payload(self, **values):
        return {
            "action":"amend_draft", "draft_id":str(self.draft_id), "revision":2,
            "draft_hash":"a"*64, "expected_case_sequence":8,
            "edits":[{"statement_id":str(self.statement),"text":"Żądanie zmienione"}],
            "rationale":"Jawna poprawka dokumentu po przeglądzie",
            "command_id":str(uuid4()),"idempotency_key":str(uuid4()),
            "correlation_id":str(uuid4()),**values,
        }

    def send(self,value,token=None):
        return edit_action(self.operator,value,token or self.token)

    def test_list_only_current_drafts(self):
        data=self.send({"action":"list_drafts"})
        self.assertEqual(data["result_type"],"DRAFT_LIST")
        self.assertEqual(data["drafts"],[{"id":str(self.draft_id),"revision":2}])
        self.assertEqual(self.dispatched,[])

    def test_open_exposes_editable_statements(self):
        data=self.send({"action":"open_draft","draft_id":str(self.draft_id),"revision":2})
        self.assertEqual(data["result_type"],"DRAFT_FOR_EDITING")
        self.assertEqual(data["sections"][0]["statements"][0]["text"],"Żądanie pierwotne")
        self.assertTrue(data["editable"])
        self.assertEqual(self.dispatched,[])

    def test_amend_delegates_to_native_work_without_approving(self):
        data=self.send(self.payload())
        self.assertEqual(data["result_type"],"DRAFT_AMENDED")
        self.assertEqual(data["approval"],"NOT_GRANTED")
        self.assertEqual(data["render"],"NOT_STARTED")
        command,token=self.dispatched[0]
        self.assertEqual(command["operation"],"AmendDraft")
        self.assertEqual(command["target"]["id"],str(self.draft_id))
        self.assertEqual(command["meta"]["case_id"],str(self.case))
        self.assertEqual(command["data"]["edits"][0]["text"],"Żądanie zmienione")
        self.assertEqual(token,self.token)

    def test_stale_draft_hash_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_LOCKED_OR_STALE"):
            self.send(self.payload(draft_hash="b"*64))
        self.assertEqual(self.dispatched,[])

    def test_uneditable_draft_denied(self):
        self.projection.editable=False
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_LOCKED_OR_STALE"):
            self.send(self.payload())

    def test_changed_case_sequence_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_CASE_STALE"):
            self.send(self.payload(expected_case_sequence=7))
        self.assertEqual(self.dispatched,[])

    def test_old_revision_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_DRAFT_NOT_CURRENT"):
            self.send({"action":"open_draft","draft_id":str(self.draft_id),"revision":1})
        self.assertEqual(self.dispatched,[])

    def test_missing_rationale_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_RATIONALE_REQUIRED"):
            self.send(self.payload(rationale=""))
        self.assertEqual(self.dispatched,[])

    def test_no_change_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_NO_CHANGE"):
            self.send(self.payload(edits=[{"statement_id":str(self.statement),
                                           "text":"Żądanie pierwotne"}]))
        self.assertEqual(self.dispatched,[])

    def test_other_statement_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_EDIT_INVALID"):
            self.send(self.payload(edits=[{"statement_id":str(uuid4()),
                                           "text":"Nie mój fragment"}]))
        self.assertEqual(self.dispatched,[])

    def test_wrong_scope_denied(self):
        self.projection.draft.case_id=uuid4()
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_SCOPE_OR_REVISION_MISMATCH"):
            self.send(self.payload())
        self.assertEqual(self.dispatched,[])

    def test_ai_denied(self):
        token=self.auth.provision(Principal(
            Actor(id=uuid4(),kind="AI"),self.tenant,self.case,self.rights))
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_HUMAN_REQUIRED"):
            self.send(self.payload(),token=token)
        self.assertEqual(self.dispatched,[])

    def test_browser_cannot_supply_tenant(self):
        with self.assertRaisesRegex(EngineBoundaryError,"EDITOR_ACTION_DENIED"):
            self.send(self.payload(tenant_id=str(uuid4())))
        self.assertEqual(self.dispatched,[])


if __name__ == "__main__":
    import unittest
    unittest.main()
