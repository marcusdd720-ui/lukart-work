"""Real disposable PostgreSQL E2E for the unified LEGAL OS session host.

One synthetic case only: WORK CreateCase -> /case -> HTTP import text ->
stored source/OCR -> HUMAN review -> immutable original + candidate Fact/Evidence.
No renderer golden checks; no real or private case data.
"""
from __future__ import annotations

import base64
import json
from hashlib import sha256
from http.client import HTTPConnection
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from uuid import UUID, uuid4

import psycopg

from lukart_work.contracts.messages import CommandResult
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.facts.service import FactEvidenceService
from lukart_work.ingestion.service import IngestionService
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server
from lukart_work.storage.migrations import migrate, grant_runtime
from lukart_work.storage.objects import RetentionPolicies
from tests import test_stage02 as core
from tests import test_stage03 as storage


@skipUnless(core.ADMIN and core.DSN, "Real PostgreSQL E2E requires disposable CI DB")
class LegalOSRealPostgresE2E(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin, cls.dsn = storage.fresh_database()
        with psycopg.connect(cls.admin) as connection:
            migrate(connection)
            grant_runtime(connection, "lw_core_runtime")

    def setUp(self):
        self.tenant, self.case, self.actor_id = uuid4(), uuid4(), uuid4()
        self.policy = core.PIN
        self.authority = TokenAuthority()
        self.actions = core.ACTIONS | frozenset((
            "IngestSource", "ReadIngestion", "ReviewCandidate",
            "GetFactEvidenceMatrix", "GetFinalization", "ReadFinalArtifact",
        ))
        self.principal = Principal(
            Actor(id=self.actor_id, kind="HUMAN"),
            self.tenant, self.case, self.actions
        )
        self.token = self.authority.provision(self.principal)
        self.repository = PostgresRepository(
            self.dsn, storage=True,
            retention_policies=RetentionPolicies([(core.PIN, 0)])
        )
        operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
        operator.binding = None
        operator.core = CommandService(self.repository, self.authority)
        operator.ingestion = IngestionService(self.repository, self.authority)
        operator.facts = FactEvidenceService(self.repository, self.authority)
        operator.finalization = SimpleNamespace(
            repository=self.repository, authority=self.authority
        )
        self.operator = operator
        request = {
            "contract": "urn:lukart:work:CoreRequest:1.0.0",
            "operation": "CreateCase",
            "meta": {
                "command_id": str(uuid4()),
                "tenant_id": str(self.tenant),
                "case_id": str(self.case),
                "idempotency_key": str(uuid4()),
                "expected_case_sequence": 0,
                "correlation_id": str(uuid4()),
            },
            "data": {
                "title": "LUKART LEGAL OS — sprawa syntetyczna",
                "jurisdiction": "PL", "retention_policy": self.policy,
            },
            "rationale": "Utworzenie tylko syntetycznej sprawy E2E",
        }
        created = operator.execute_core(request, self.token)
        self.assertIsInstance(created, CommandResult, created)
        self.assertEqual(created.state, "APPLIED")
        self.assertEqual(created.case_sequence, 1)
        self.server = create_server(operator, 0, case_only=True)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self, path):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("GET", path)
            res = conn.getresponse()
            return res.status, res.read()
        finally:
            conn.close()

    def action(self, payload, token=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=75)
        try:
            conn.request("POST", "/api/embedded_session", json.dumps(payload),
                {"Content-Type": "application/json",
                 "Authorization": "Bearer " + (token or self.token)})
            res = conn.getresponse()
            body = res.read()
            return res.status, json.loads(body.decode("utf-8"))
        finally:
            conn.close()

    def test_real_database_case_to_original_to_reviewed_candidate(self):
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"/case.js", html)
        self.assertNotIn(b"/client.js", html)

        status, case = self.action({"action": "open_case"})
        self.assertEqual(status, 200, case)
        self.assertEqual(case["result_type"], "CASE_HEAD")
        self.assertEqual(case["case_sequence"], 1)

        original = ("Powód: Osoba Syntetyczna\n"
                    "Wykonano usługę 2026-10-01. "
                    "Potwierdzono odbiór w protokole.").encode("utf-8")
        req = {
            "action": "upload_source", "media_type": "text/plain",
            "content_base64": base64.b64encode(original).decode(),
            "expected_case_sequence": 1,
            **{k: str(uuid4()) for k in (
                "command_id", "idempotency_key", "correlation_id", "run_id"
            )}
        }
        status, saved = self.action(req)
        self.assertEqual(status, 200, saved)
        self.assertIn(saved["registration"]["state"], ("APPLIED", "REPLAYED"))
        self.assertEqual(saved["ingestion"]["body"]["status"], "EXTRACTED")
        self.assertEqual(saved["registration"]["case_sequence"], 2)
        source_id = saved["source_id"]
        run_id = saved["run_id"]
        with self.repository.transaction(self.tenant, self.case) as tx:
            restored = tx.source_bytes(UUID(source_id))
        self.assertEqual(restored, original)
        self.assertEqual(sha256(restored).hexdigest(),
                         saved["ingestion"]["source_hash"])

        status, review = self.action({
            "action": "review_context", "source_id": source_id, "run_id": run_id
        })
        self.assertEqual(status, 200, review)
        self.assertEqual(review["result_type"], "REVIEW_CONTEXT")
        self.assertEqual(review["case_sequence"], 2)
        candidates = [x for x in review["candidates"] if x["kind"] == "FACT"]
        self.assertTrue(candidates, "synthetic parser should produce FACT candidate")
        candidate = candidates[0]
        self.assertEqual(candidate["review_status"], "PENDING")

        status, result = self.action({
            "action": "review_candidate",
            "source_id": source_id,
            "run_id": run_id,
            "candidate_index": candidate["index"],
            "expected_case_sequence": review["case_sequence"],
            "disposition": "ADMIT",
            "statement": "Według dokumentu syntetycznego wykonano usługę.",
            "description": "Materiał syntetyczny do dalszej oceny",
            "rationale": "Jawnie sprawdzony cytat, bez potwierdzenia prawdziwości",
            **{k: str(uuid4()) for k in (
                "command_id", "idempotency_key", "correlation_id"
            )}
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["result_type"], "REVIEW_RECEIPT")
        self.assertEqual(result["state"], "APPLIED")
        self.assertEqual(result["candidate_kind"], "FACT")

        matrix = self.operator.query_fact_evidence({
            "contract": "urn:lukart:work:FactEvidenceQuery:1.0.0",
            "operation": "GetFactEvidenceMatrix",
            "tenant_id": str(self.tenant),
            "case_id": str(self.case),
        }, self.token)
        self.assertEqual(len(matrix.facts), 1)
        self.assertEqual(matrix.facts[0].status, "CANDIDATE")
        self.assertFalse(matrix.facts[0].confirmation_current)
        self.assertFalse(matrix.facts[0].acceptance_live)

        status, again = self.action({
            "action": "review_context", "source_id": source_id, "run_id": run_id
        })
        self.assertEqual(status, 200, again)
        reviewed = [x for x in again["candidates"]
                    if x["index"] == candidate["index"]][0]
        self.assertEqual(reviewed["review_status"], "ADMIT")
        with self.repository.transaction(self.tenant, self.case) as tx:
            self.assertEqual(tx.source_bytes(UUID(source_id)), original)

    def test_case_only_exposes_no_legacy_mutation_api(self):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", "/api/execute_core", "{}",
                         {"Content-Type": "application/json",
                          "Authorization": "Bearer " + self.token})
            res = conn.getresponse()
            self.assertEqual(res.status, 404)
            res.read()
        finally:
            conn.close()

    def test_session_scope_blocks_foreign_case(self):
        other = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="HUMAN"), self.tenant, uuid4(),
            self.actions
        ))
        status, result = self.action({"action": "open_case"}, token=other)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["result_type"], "DOMAIN_ERROR")


if __name__ == "__main__":
    import unittest
    unittest.main()
