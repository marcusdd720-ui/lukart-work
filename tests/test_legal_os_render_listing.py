"""Targeted security tests for WORK-backed saved-render discovery."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from uuid import UUID, uuid4

from lukart_work.embedded_document_engine import (
    CaseScope, EmbeddedDocumentEngine, EngineBoundaryError, SavedRenderList,
)
from lukart_work.legal_os_case_view import read_case_action
from tests.test_embedded_document_engine import FakeOperator


class ScopedPrincipal:
    def __init__(self, kind="HUMAN", allowed=True):
        self.actor = SimpleNamespace(kind=kind)
        self.allowed = allowed
        self.checks = []

    def require(self, tenant_id, case_id, action):
        self.checks.append((tenant_id, case_id, action))
        if not self.allowed:
            raise EngineBoundaryError("DENIED")


class ScopedAuthority:
    def __init__(self, principal):
        self.principal = principal

    @contextmanager
    def session(self, token):
        if token != "synthetic-token":
            raise EngineBoundaryError("DENIED")
        yield self.principal


class RenderTx:
    def __init__(self, records, sequence=2):
        self.records = records
        self.seq = sequence
        self.calls = 0

    def sequence(self):
        return self.seq

    def objects(self, category, cls):
        self.calls += 1
        self.category = category
        self.cls = cls
        return tuple(self.records)


class ScopedRepo:
    def __init__(self, tx, tenant_id, case_id):
        self.tx = tx
        self.tenant_id = UUID(tenant_id)
        self.case_id = UUID(case_id)
        self.calls = []

    @contextmanager
    def transaction(self, tenant_id, case_id):
        self.calls.append((tenant_id, case_id))
        if (tenant_id, case_id) != (self.tenant_id, self.case_id):
            raise EngineBoundaryError("CROSS_CASE")
        yield self.tx


class RenderListingTests(TestCase):
    def setUp(self):
        self.tenant_id = str(uuid4())
        self.case_id = str(uuid4())
        self.scope = CaseScope(self.tenant_id, self.case_id)
        self.record_id = uuid4()
        self.record = SimpleNamespace(
            id=self.record_id,
            tenant_id=UUID(self.tenant_id),
            case_id=UUID(self.case_id),
            recorded_at=datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc),
            semantic_profile=SimpleNamespace(id="TEST_PL"),
        )
        self.principal = ScopedPrincipal()
        self.tx = RenderTx([self.record])
        self.repo = ScopedRepo(self.tx, self.tenant_id, self.case_id)
        self.operator = FakeOperator()
        self.operator.finalization = SimpleNamespace(
            authority=ScopedAuthority(self.principal), repository=self.repo
        )
        self.engine = EmbeddedDocumentEngine(self.operator)

    def test_lists_existing_render_without_regeneration(self):
        result = self.engine.list_saved(self.scope, token="synthetic-token")
        self.assertIsInstance(result, SavedRenderList)
        self.assertEqual(result.result_type, "SAVED_RENDERS")
        self.assertEqual([x.render_id for x in result.items], [self.record_id])
        self.assertEqual(result.items[0].label, "Zapisany projekt")
        self.assertEqual(self.operator.calls, [])
        self.assertEqual(len(self.repo.calls), 1)
        self.assertEqual(len(self.principal.checks), 2)
        self.assertTrue(all(x[2] == "GetFinalization" for x in self.principal.checks))

    def test_empty_list_is_not_error(self):
        self.tx.records = []
        result = self.engine.list_saved(self.scope, token="synthetic-token")
        self.assertEqual(result.items, ())

    def test_cross_case_record_fails_closed(self):
        self.record.case_id = uuid4()
        with self.assertRaisesRegex(EngineBoundaryError, "CROSS_CASE_RENDER"):
            self.engine.list_saved(self.scope, token="synthetic-token")

    def test_unauthorized_session_does_not_enter_database(self):
        self.principal.allowed = False
        with self.assertRaisesRegex(EngineBoundaryError, "DENIED"):
            self.engine.list_saved(self.scope, token="synthetic-token")
        self.assertEqual(self.repo.calls, [])

    def test_ai_principal_cannot_discover_documents(self):
        self.principal.actor.kind = "AI"
        with self.assertRaisesRegex(EngineBoundaryError, "HUMAN_OR_SERVICE_REQUIRED"):
            self.engine.list_saved(self.scope, token="synthetic-token")
        self.assertEqual(self.repo.calls, [])

    def test_list_limit_fails_closed(self):
        self.tx.records = [self.record] * 101
        with self.assertRaisesRegex(EngineBoundaryError, "RENDER_LIST_LIMIT"):
            self.engine.list_saved(self.scope, token="synthetic-token")

    def test_missing_case_denied(self):
        self.tx.seq = 0
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_NOT_FOUND"):
            self.engine.list_saved(self.scope, token="synthetic-token")

    def test_exact_case_action_shape_and_dispatch(self):
        result = read_case_action(self.operator, {
            "action": "list_saved",
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
        }, "synthetic-token")
        self.assertEqual(result.items[0].render_id, self.record_id)
        self.assertEqual(self.operator.calls, [])

    def test_extra_field_rejected_before_backend(self):
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_OPERATION_NOT_ALLOWED"):
            read_case_action(self.operator, {
                "action": "list_saved",
                "tenant_id": self.tenant_id,
                "case_id": self.case_id,
                "approval": True,
            }, "synthetic-token")
        self.assertEqual(self.repo.calls, [])

    def test_bad_token_rejected(self):
        with self.assertRaises(EngineBoundaryError):
            self.engine.list_saved(self.scope, token="bad")
        self.assertEqual(self.repo.calls, [])

    def test_correct_scope_sent_as_uuids(self):
        self.engine.list_saved(self.scope, token="synthetic-token")
        self.assertEqual(self.repo.calls, [(UUID(self.tenant_id), UUID(self.case_id))])


if __name__ == "__main__":
    import unittest
    unittest.main()
