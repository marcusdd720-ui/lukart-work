"""Focused tests: LEGAL OS displays actual CASE title only from current WORK head."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from lukart_work.embedded_document_engine import EngineBoundaryError
from lukart_work.legal_os_case_view import read_case_action, CASE_HTML, CASE_JS


class Head:
    def __init__(self, heads):
        self.heads = heads


class Revision:
    def __init__(self, entity):
        self.entity = entity


class ReadOnlyOperator:
    def __init__(self, case_id, revision=2):
        self.case_id = case_id
        self.revision = revision
        self.calls = []
        self.head = Head([SimpleNamespace(kind="Case", id=UUID(case_id), revision=revision)])
        self.record = Revision(SimpleNamespace(
            kind="Case", id=UUID(case_id), revision=revision, title="Sprawa syntetyczna", status="OPEN"
        ))

    def query_core(self, data, token):
        self.calls.append((data, token))
        if data["operation"] == "GetCaseHead":
            return self.head
        if data["operation"] == "GetRevision":
            return self.record
        raise AssertionError("unknown WORK query")


class CaseTitleTests(TestCase):
    def setUp(self):
        self.tenant = str(uuid4())
        self.case = str(uuid4())
        self.operator = ReadOnlyOperator(self.case)
        self.payload = {"action": "case_title", "tenant_id": self.tenant,
                        "case_id": self.case, "case_revision": 2}
        self.mock_types = [
            patch("lukart_work.legal_os_case_view.CaseHeadResult", Head),
            patch("lukart_work.legal_os_case_view.RevisionResult", Revision),
        ]
        for mock_type in self.mock_types:
            mock_type.start()
            self.addCleanup(mock_type.stop)

    def test_reads_current_work_case_revision(self):
        result = read_case_action(self.operator, self.payload, "synthetic")
        self.assertEqual(result.entity.title, "Sprawa syntetyczna")
        self.assertEqual([p["operation"] for p, _ in self.operator.calls],
                         ["GetCaseHead", "GetRevision"])
        self.assertEqual(self.operator.calls[1][0]["target"]["id"], self.case)

    def test_stale_case_revision_is_rejected_without_revision_read(self):
        self.payload["case_revision"] = 1
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_REVISION_NOT_CURRENT"):
            read_case_action(self.operator, self.payload, "synthetic")
        self.assertEqual(len(self.operator.calls), 1)

    def test_boolean_revision_is_rejected(self):
        self.payload["case_revision"] = True
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_REVISION_INVALID"):
            read_case_action(self.operator, self.payload, "synthetic")
        self.assertEqual(self.operator.calls, [])

    def test_wrong_case_entity_is_rejected(self):
        self.operator.record = Revision(SimpleNamespace(
            kind="Case", id=uuid4(), revision=2, title="Obca", status="OPEN"
        ))
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_REVISION_MISMATCH"):
            read_case_action(self.operator, self.payload, "synthetic")

    def test_missing_current_case_head_is_rejected(self):
        self.operator.head = Head([])
        with self.assertRaisesRegex(EngineBoundaryError, "CASE_REVISION_NOT_CURRENT"):
            read_case_action(self.operator, self.payload, "synthetic")

    def test_read_only_frontend_displays_title(self):
        self.assertIn(b'id="case-title"', CASE_HTML)
        self.assertIn(b'case_title', CASE_JS)
        self.assertNotIn(b'execute_finalization', CASE_JS)


if __name__ == "__main__":
    import unittest
    unittest.main()
