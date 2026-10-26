"""Targeted HUMAN review tests: native WORK boundaries, synthetic records only."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4, UUID

from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor
from lukart_work.contracts.messages import CommandResult
from lukart_work.embedded_document_engine import EngineBoundaryError
from lukart_work.legal_os_review import review_action
from tests.test_embedded_document_engine import FakeOperator


class FakeIngestion:
    pass


class FakeMatrix:
    pass


class FakeHead:
    pass


class ReviewTests(TestCase):
    def setUp(self):
        self.tenant, self.case, self.source, self.run = [uuid4() for _ in range(4)]
        self.authority = TokenAuthority()
        self.rights = frozenset(("GetCaseHead", "ReadIngestion", "GetFactEvidenceMatrix", "ReviewCandidate"))
        self.token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="HUMAN"), self.tenant, self.case, self.rights
        ))
        self.operator = FakeOperator()
        self.operator.core = SimpleNamespace(authority=self.authority)
        self.ingestion = FakeIngestion()
        self.ingestion.tenant_id, self.ingestion.case_id = self.tenant, self.case
        self.ingestion.source_id, self.ingestion.run_id = self.source, self.run
        self.ingestion.body = SimpleNamespace(
            status="EXTRACTED", candidates=[
                SimpleNamespace(kind="FACT", quote="Wykonano usługę."),
                SimpleNamespace(kind="DATE", quote="2026-10-26"),
                SimpleNamespace(kind="EVIDENCE", quote="Załączony protokół.")
            ]
        )
        self.matrix = FakeMatrix()
        self.matrix.tenant_id, self.matrix.case_id = self.tenant, self.case
        self.matrix.case_sequence = 9
        self.matrix.candidate_reviews = ()
        self.head = FakeHead()
        self.head.case_sequence = 9
        self.dispatched = []
        self.operator.query_ingestion = lambda request, token: self.ingestion
        self.operator.query_fact_evidence = lambda request, token: self.matrix
        self.operator.query_core = lambda request, token: self.head
        def execute(req, token):
            self.dispatched.append((req, token))
            return CommandResult(command_id=UUID(req["meta"]["command_id"]),
                                 state="APPLIED", case_sequence=10,
                                 refs=(), event_ids=(), errors=())
        self.operator.execute_fact_evidence = execute
        patches=[
            patch("lukart_work.legal_os_review.IngestionResult", FakeIngestion),
            patch("lukart_work.legal_os_review.FactEvidenceMatrix", FakeMatrix),
            patch("lukart_work.legal_os_review.CaseHeadResult", FakeHead),
            patch("lukart_work.legal_os_review.digest", return_value="a"*64),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def context(self):
        return {
            "action":"review_context", "source_id":str(self.source), "run_id":str(self.run)
        }

    def decision(self, **updates):
        value = {
            "action":"review_candidate", "source_id":str(self.source), "run_id":str(self.run),
            "candidate_index":0, "expected_case_sequence":9, "disposition":"ADMIT",
            "statement":"Zlecenie zostało wykonane", "description":"Dokument wykonania",
            "rationale":"Zapoznałem się z cytatem i przyjmuję go do dalszej oceny",
            "command_id":str(uuid4()), "idempotency_key":str(uuid4()),
            "correlation_id":str(uuid4())
        }
        value.update(updates)
        return value

    def test_context_only_contains_reviewable_candidates(self):
        result=review_action(self.operator,self.context(),self.token)
        self.assertEqual(result["result_type"],"REVIEW_CONTEXT")
        self.assertEqual([x["index"] for x in result["candidates"]],[0,2])
        self.assertTrue(all(x["review_status"]=="PENDING" for x in result["candidates"]))
        self.assertEqual(self.dispatched,[])

    def test_human_admit_composes_existing_work_command(self):
        receipt=review_action(self.operator,self.decision(),self.token)
        self.assertEqual(receipt["result_type"],"REVIEW_RECEIPT")
        self.assertEqual(receipt["case_sequence"],10)
        request,token=self.dispatched[0]
        self.assertEqual(request["operation"],"ReviewCandidate")
        self.assertEqual(request["data"]["result_hash"],"a"*64)
        self.assertEqual(request["data"]["expected_review_revision"],0)
        self.assertEqual(request["meta"]["tenant_id"],str(self.tenant))
        self.assertEqual(request["meta"]["case_id"],str(self.case))
        self.assertEqual(token,self.token)

    def test_reject_creates_no_fact_text(self):
        review_action(self.operator,self.decision(disposition="REJECT",
            statement="",description=""),self.token)
        body=self.dispatched[0][0]["data"]
        self.assertNotIn("statement",body)
        self.assertNotIn("description",body)

    def test_non_reviewable_date_cannot_be_admitted(self):
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_NOT_FACT_EVIDENCE"):
            review_action(self.operator,self.decision(candidate_index=1),self.token)
        self.assertEqual(self.dispatched,[])

    def test_stale_case_sequence_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_STALE_OR_INVALID"):
            review_action(self.operator,self.decision(expected_case_sequence=8),self.token)
        self.assertEqual(self.dispatched,[])

    def test_cross_case_source_denied(self):
        self.ingestion.case_id=uuid4()
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_SOURCE_UNAVAILABLE"):
            review_action(self.operator,self.decision(),self.token)
        self.assertEqual(self.dispatched,[])

    def test_non_extracted_document_denied(self):
        self.ingestion.body.status="NEEDS_OCR"
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_SOURCE_UNAVAILABLE"):
            review_action(self.operator,self.context(),self.token)

    def test_no_implicit_approval_on_context(self):
        review_action(self.operator,self.context(),self.token)
        self.assertEqual(len(self.dispatched),0)

    def test_ai_actor_denied(self):
        token=self.authority.provision(Principal(
            Actor(id=uuid4(),kind="AI"),self.tenant,self.case,self.rights))
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_HUMAN_REQUIRED"):
            review_action(self.operator,self.decision(),token)
        self.assertEqual(self.dispatched,[])

    def test_wrong_command_route_and_extra_fields_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_SHAPE_INVALID"):
            review_action(self.operator,{**self.decision(), "tenant_id":str(uuid4())},self.token)
        self.assertEqual(self.dispatched,[])

    def test_missing_rationale_denied(self):
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_TEXT_INVALID"):
            review_action(self.operator,self.decision(rationale=""),self.token)
        self.assertEqual(self.dispatched,[])

    def test_admitted_candidate_cannot_be_double_added(self):
        self.matrix.candidate_reviews=(SimpleNamespace(
            run_id=self.run,source_id=self.source,candidate_index=0,
            revision=1,disposition="ADMIT"
        ),)
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_ALREADY_ADMITTED"):
            review_action(self.operator,self.decision(),self.token)
        self.assertEqual(self.dispatched,[])

    def test_review_revision_derived_from_work(self):
        self.matrix.candidate_reviews=(SimpleNamespace(
            run_id=self.run,source_id=self.source,candidate_index=0,
            revision=2,disposition="REJECT"
        ),)
        review_action(self.operator,self.decision(),self.token)
        self.assertEqual(self.dispatched[0][0]["data"]["expected_review_revision"],2)

    def test_case_head_change_blocks_write(self):
        self.head.case_sequence=10
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_CASE_STALE"):
            review_action(self.operator,self.decision(),self.token)
        self.assertEqual(self.dispatched,[])

    def test_evidence_admission_has_no_fact_statement(self):
        review_action(self.operator,self.decision(candidate_index=2,
            statement="",description="Protokół"),self.token)
        self.assertEqual(self.dispatched[0][0]["data"]["description"],"Protokół")
        self.assertNotIn("statement",self.dispatched[0][0]["data"])

    def test_evidence_forged_statement_rejected(self):
        with self.assertRaisesRegex(EngineBoundaryError,"REVIEW_EVIDENCE_STATEMENT_INVALID"):
            review_action(self.operator,self.decision(candidate_index=2),self.token)
        self.assertEqual(self.dispatched,[])


if __name__ == "__main__":
    import unittest
    unittest.main()
