"""Stage 11 PostgreSQL integration assurance; synthetic data only.

This module is discovered by the full regression workflow, which provides isolated PostgreSQL.
The Stage 11 focused workflow intentionally runs only tests.test_stage11 and therefore has no skips.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import unittest
from uuid import uuid4

from lukart_work.contracts.messages import DomainError
from lukart_work.core.security import Principal
from lukart_work.domain.models import Actor
from lukart_work.rendering.contracts import (
    RenderedArtifact,
    RenderingExecution,
    RenderingResult,
)
from lukart_work.rendering.policy import profile_pin
from lukart_work.rendering.service import RenderingEngineService
from lukart_work.storage.objects import ObjectStore
from lukart_work.validation.rules import digest
from tests import test_stage02 as core
from tests import test_stage10 as validation


@unittest.skipUnless(core.ADMIN and core.DSN, "Stage 11 integration requires isolated PostgreSQL")
class Stage11IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.helper = validation.ValidationTests(methodName="test_stage10_golden_validated_is_not_rendered_or_final")
        self.helper.setUp()
        self.helper.repo.storage = True
        self.helper.authority.revoke(self.helper.token)
        actions = self.helper.principal.actions | {"RenderDocument"}
        self.helper.principal = Principal(
            self.helper.actor,
            self.helper.tenant,
            self.helper.case_id,
            frozenset(actions),
        )
        self.helper.token = self.helper.authority.provision(self.helper.principal)
        self.clock_value = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)
        self.renderer = RenderingEngineService(
            self.helper.repo,
            self.helper.authority,
            clock=lambda: self.clock_value,
        )

    def validated(self):
        case, draft = self.helper.generated()
        review = self.helper.review(draft)
        result, run_id, _ = self.helper.validate(draft, review)
        validated = self.helper.get(result.refs[0])
        self.assertEqual(validated.status, "VALIDATED")
        return case, validated, run_id

    def request(self, draft, run_id, *, formats=("DOCX", "PDF"), profile=None, key=None):
        profile = profile or profile_pin()
        return {
            "contract": "urn:lukart:work:RenderingRequest:1.0.0",
            "operation": "RenderDocument",
            "meta": {
                "command_id": str(uuid4()),
                "tenant_id": str(self.helper.tenant),
                "case_id": str(self.helper.case_id),
                "idempotency_key": str(key or uuid4()),
                "expected_case_sequence": self.helper.sequence,
                "correlation_id": str(uuid4()),
            },
            "draft": {
                "kind": "Draft",
                "id": str(draft.id),
                "revision": draft.revision,
            },
            "draft_hash": digest(draft),
            "validation_run_id": str(run_id),
            "profile": profile.model_dump(mode="json"),
            "formats": list(formats),
            "retention_policy": core.PIN,
        }

    def test_render_binds_validated_draft_profile_storage_and_exact_bytes(self):
        _, draft, run_id = self.validated()
        before_sequence = self.helper.sequence
        result = self.renderer.render(json.dumps(self.request(draft, run_id)), self.helper.token)
        self.assertIsInstance(result, RenderingResult, result)
        self.assertFalse(result.replayed)
        self.assertEqual(self.helper.sequence, before_sequence)
        self.assertEqual({a.format for a in result.execution.artifacts}, {"DOCX", "PDF"})
        self.assertEqual(result.execution.render_tree.semantic_digest, result.execution.semantic_document.model_copy().model_dump() and digest(result.execution.semantic_document))
        self.assertEqual(result.execution.render_tree.profile_digest, profile_pin().content_hash)

        with self.helper.repo.transaction(self.helper.tenant, self.helper.case_id) as tx:
            self.assertEqual(tx.sequence(), before_sequence)
            executions = tx.objects("rendering_execution", RenderingExecution)
            self.assertEqual(executions, (result.execution,))
            artifacts = tx.objects("rendered_artifact", RenderedArtifact)
            self.assertEqual({a.artifact_id for a in artifacts}, {a.artifact_id for a in result.execution.artifacts})
            store = ObjectStore(tx)
            for artifact in artifacts:
                data = store.read(artifact.artifact_id)
                self.assertEqual(sha256(data).hexdigest(), artifact.artifact_byte_hash)
                self.assertEqual(len(data), artifact.byte_length)
                if artifact.format == "DOCX":
                    self.assertTrue(data.startswith(b"PK"))
                else:
                    self.assertTrue(data.startswith(b"%PDF-"))

    def test_exact_replay_and_distinct_command_reuse_same_artifacts(self):
        _, draft, run_id = self.validated()
        key = uuid4()
        request = self.request(draft, run_id, key=key)
        first = self.renderer.render(json.dumps(request), self.helper.token)
        self.assertIsInstance(first, RenderingResult, first)
        second = self.renderer.render(json.dumps(request), self.helper.token)
        self.assertIsInstance(second, RenderingResult, second)
        self.assertTrue(second.replayed)
        self.assertEqual(second.execution, first.execution)

        third_request = self.request(draft, run_id)
        third = self.renderer.render(json.dumps(third_request), self.helper.token)
        self.assertIsInstance(third, RenderingResult, third)
        self.assertFalse(third.replayed)
        self.assertEqual(
            tuple(a.artifact_id for a in third.execution.artifacts),
            tuple(a.artifact_id for a in first.execution.artifacts),
        )
        self.assertEqual(
            tuple(a.presentation_digest for a in third.execution.artifacts),
            tuple(a.presentation_digest for a in first.execution.artifacts),
        )

        with self.helper.repo.transaction(self.helper.tenant, self.helper.case_id) as tx:
            self.assertEqual(len(tx.objects("rendered_artifact", RenderedArtifact)), 2)
            self.assertEqual(len(tx.objects("rendering_execution", RenderingExecution)), 2)

    def test_stale_validation_profile_substitution_and_ai_authority_fail_closed(self):
        _, draft, run_id = self.validated()

        tampered = profile_pin().model_copy(update={"content_hash": "0" * 64})
        denied = self.renderer.render(
            json.dumps(self.request(draft, run_id, profile=tampered)),
            self.helper.token,
        )
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "GATE_DENIED")

        self.helper.apply("AddParty", {
            "party_type": "PERSON",
            "display_name": "Synthetic concurrent mutation",
            "identity_evidence": [],
        })
        stale = self.renderer.render(json.dumps(self.request(draft, run_id)), self.helper.token)
        self.assertIsInstance(stale, DomainError)
        self.assertEqual(stale.code, "GATE_DENIED")

        actor = Actor(id=uuid4(), kind="AI")
        principal = Principal(actor, self.helper.tenant, self.helper.case_id, self.helper.principal.actions)
        token = self.helper.authority.provision(principal)
        ai = self.renderer.render(json.dumps(self.request(draft, run_id)), token)
        self.assertIsInstance(ai, DomainError)
        self.assertEqual(ai.code, "GATE_DENIED")


if __name__ == "__main__":
    unittest.main()
