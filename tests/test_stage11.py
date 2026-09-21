"""Stage 11 Rendering Engine assurance on synthetic CASE data and real PostgreSQL."""
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5
from zipfile import ZipFile

import psycopg
from pypdf import PdfReader

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.postgres import UnitOfWork
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor
from lukart_work.rendering.contracts import (
    RenderExecution, RenderingProjection, stage11_actions,
)
from lukart_work.rendering.profiles import (
    official_pl_profile, profile_pin, renderer_pin,
)
from lukart_work.rendering.renderer import render_docx, render_pdf
from lukart_work.rendering.service import RenderingEngineService
from lukart_work.storage.objects import ObjectStore
from lukart_work.validation.rules import digest, ref
from tests import test_stage02 as core
from tests import test_stage10 as validation


class RenderingTests(validation.ValidationTests):
    def setUp(self):
        super().setUp()
        # Stage 09 already pins the future render profile in Draft reproduction evidence.
        self.profile['render_profile'] = profile_pin().model_dump(mode='json')
        self.drafting.profiles['QUICK'] = self.profile
        self.repo.storage = True
        self.authority.revoke(self.token)
        self.principal = Principal(
            self.actor,
            self.tenant,
            self.case_id,
            stage11_actions(self.principal.actions),
        )
        self.token = self.authority.provision(self.principal)
        self.rendering = RenderingEngineService(self.repo, self.authority)

    def rrequest(self, operation, draft, **extras):
        request = self.request(operation, target=ref(draft))
        request.pop('data')
        request.update(
            contract='urn:lukart:work:RenderingRequest:1.0.0',
            profile=profile_pin().model_dump(mode='json'),
            rationale='Synthetic Stage 11 rendering intent',
            **extras,
        )
        return request

    def rexecute(self, request, *, service=None, token=None):
        return (service or self.rendering).execute(
            json.dumps(request), token or self.token
        )

    def rapply(self, request, *, service=None, token=None):
        result = self.rexecute(request, service=service, token=token)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result

    def validated(self, *, issues=(), outcomes=None):
        case, draft = self.generated()
        review = self.review(draft, issues=issues, outcomes=outcomes)
        result, run_id, _ = self.validate(draft, review)
        validated = self.get(result.refs[0])
        self.assertEqual(validated.status, 'VALIDATED')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            run = tx.object('validation_run', run_id, __import__(
                'lukart_work.contracts.messages', fromlist=['ValidationRun']
            ).ValidationRun)
        return case, validated, run

    def authorize(self, draft, run):
        request = self.rrequest(
            'RecordRenderAuthorization',
            draft,
            validation_run_id=str(run.id),
            validation_run_hash=digest(run),
        )
        result = self.rapply(request)
        approved = self.get(result.refs[0])
        authorization_id = uuid5(
            UUID(request['meta']['command_id']), 'render-authorization'
        )
        return approved, authorization_id, request

    def render_approved(self, approved, authorization_id, *, token=None):
        request = self.rrequest(
            'RenderDocument',
            approved,
            authorization_id=str(authorization_id),
            formats=['DOCX', 'PDF'],
        )
        result = self.rapply(request, token=token)
        execution_id = uuid5(
            UUID(request['meta']['command_id']), 'render-execution'
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            execution = tx.object(
                'render_execution', execution_id, RenderExecution
            )
        return result, execution, request

    def projection(self, execution_id, token=None):
        return self.rendering.query(
            json.dumps({
                'contract': 'urn:lukart:work:RenderingQuery:1.0.0',
                'operation': 'GetRendering',
                'tenant_id': str(self.tenant),
                'case_id': str(self.case_id),
                'execution_id': str(execution_id),
            }),
            token or self.token,
        )

    def artifact_bytes(self, execution, format_name):
        artifact = next(
            item for item in execution.artifacts if item.format == format_name
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            return ObjectStore(tx).read(artifact.artifact_id)

    def test_stage11_golden_render_is_exact_bound_and_not_final(self):
        _, validated, source_run = self.validated()
        approved, authorization_id, _ = self.authorize(
            validated, source_run
        )
        self.assertEqual(approved.status, 'APPROVED')
        result, execution, _ = self.render_approved(
            approved, authorization_id
        )
        rendered = self.get(result.refs[0])
        self.assertEqual(rendered.status, 'RENDERED')
        self.assertEqual(rendered.sections, validated.sections)
        self.assertEqual(rendered.plan, validated.plan)
        self.assertEqual(rendered.snapshot_hash, validated.snapshot_hash)
        self.assertEqual(rendered.reproduction, validated.reproduction)
        self.assertEqual(
            execution.semantic_document.sections, validated.sections
        )
        self.assertEqual(
            tuple(a.format for a in execution.artifacts), ('DOCX', 'PDF')
        )
        self.assertTrue(all(c.outcome == 'PASS' for c in execution.run.checks))
        self.assertEqual(execution.manifest.profile, profile_pin())
        self.assertEqual(execution.manifest.renderer, renderer_pin())
        projection = self.projection(execution.id)
        self.assertIsInstance(projection, RenderingProjection, projection)
        self.assertTrue(
            projection.eligible_for_document_approval, projection.reasons
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            decisions = [
                item for item in tx.records().values()
                if item.kind == 'Decision'
                and item.decision_type == 'DOCUMENT_APPROVAL'
            ]
        self.assertEqual(decisions, [])

    def test_stage11_docx_is_a4_binder_safe_paginated_and_semantic(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        _, execution, _ = self.render_approved(approved, authorization_id)
        data = self.artifact_bytes(execution, 'DOCX')
        with ZipFile(BytesIO(data)) as archive:
            document = archive.read('word/document.xml').decode('utf-8')
            footer = archive.read('word/footer1.xml').decode('utf-8')
            relationships = archive.read(
                'word/_rels/document.xml.rels'
            ).decode('utf-8')
        self.assertIn('w:w="11906"', document)
        self.assertIn('w:h="16838"', document)
        self.assertIn('w:left="1701"', document)
        self.assertIn('w:right="1134"', document)
        self.assertIn('Synthetic', document)
        self.assertIn('PAGE', footer)
        self.assertIn('footer1.xml', relationships)

    def test_stage11_pdf_is_parseable_a4_paginated_and_contains_content(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        _, execution, _ = self.render_approved(approved, authorization_id)
        reader = PdfReader(BytesIO(self.artifact_bytes(execution, 'PDF')))
        self.assertGreaterEqual(len(reader.pages), 1)
        page = reader.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=0.3)
        self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=0.3)
        text = '\n'.join(p.extract_text() or '' for p in reader.pages)
        self.assertIn('Synthetic', text)

    def test_stage11_renderer_is_byte_deterministic_and_supports_polish_unicode(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            semantic = self.rendering._semantic_document(
                approved,
                self.principal,
                tx.records(),
            )
        semantic = semantic.model_copy(
            update={'header': semantic.header + '\nZażółć gęślą jaźń'}
        )
        profile = official_pl_profile()
        docx_one, docx_two = (
            render_docx(semantic, profile), render_docx(semantic, profile)
        )
        pdf_one, pdf_two = (
            render_pdf(semantic, profile), render_pdf(semantic, profile)
        )
        self.assertEqual(docx_one, docx_two)
        self.assertEqual(pdf_one, pdf_two)
        with ZipFile(BytesIO(docx_one)) as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        self.assertIn('Zażółć gęślą jaźń', xml)
        extracted = '\n'.join(
            p.extract_text() or '' for p in PdfReader(BytesIO(pdf_one)).pages
        )
        self.assertIn('Zażółć', extracted)

    def test_stage11_stale_validation_run_cannot_authorize_render(self):
        _, validated, run = self.validated()
        self.party()
        request = self.rrequest(
            'RecordRenderAuthorization',
            validated,
            validation_run_id=str(run.id),
            validation_run_hash=digest(run),
        )
        before = self.sequence
        result = self.rexecute(request)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'STALE')
        self.assertEqual(self.sequence, before)

    def test_stage11_validation_hash_substitution_fails_closed(self):
        _, validated, run = self.validated()
        request = self.rrequest(
            'RecordRenderAuthorization',
            validated,
            validation_run_id=str(run.id),
            validation_run_hash='0' * 64,
        )
        result = self.rexecute(request)
        self.assertIsInstance(result, DomainError)
        self.assertIn(result.code, ('STALE', 'INVALID_HASH'))

    def test_stage11_human_authorizes_service_may_render_only_that_authorization(self):
        _, validated, run = self.validated()
        service_actor = Actor(id=uuid4(), kind='SERVICE')
        service_principal = Principal(
            service_actor,
            self.tenant,
            self.case_id,
            stage11_actions(self.principal.actions),
        )
        service_token = self.authority.provision(service_principal)
        denied = self.rrequest(
            'RecordRenderAuthorization',
            validated,
            validation_run_id=str(run.id),
            validation_run_hash=digest(run),
        )
        self.assertEqual(
            self.rexecute(denied, token=service_token).code, 'FORBIDDEN'
        )
        approved, authorization_id, _ = self.authorize(validated, run)
        _, execution, _ = self.render_approved(
            approved, authorization_id, token=service_token
        )
        self.assertEqual(execution.authorization.actor.kind, 'HUMAN')
        self.assertTrue(
            self.projection(execution.id).eligible_for_document_approval
        )

    def test_stage11_case_mutation_after_authorization_blocks_render(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        self.party()
        request = self.rrequest(
            'RenderDocument',
            approved,
            authorization_id=str(authorization_id),
            formats=['DOCX', 'PDF'],
        )
        result = self.rexecute(request)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'STALE')

    def test_stage11_profile_substitution_and_semantic_injection_are_rejected(self):
        _, validated, run = self.validated()
        fake = profile_pin().model_dump(mode='json')
        fake['content_hash'] = '0' * 64
        request = self.rrequest(
            'RecordRenderAuthorization',
            validated,
            validation_run_id=str(run.id),
            validation_run_hash=digest(run),
        )
        request['profile'] = fake
        self.assertEqual(self.rexecute(request).code, 'GATE_DENIED')
        injected = self.rrequest(
            'RecordRenderAuthorization',
            validated,
            validation_run_id=str(run.id),
            validation_run_hash=digest(run),
        )
        injected['document'] = {
            'header': 'caller-controlled semantic document'
        }
        self.assertEqual(self.rexecute(injected).code, 'SCHEMA_INVALID')

    def test_stage11_render_replay_is_exact_and_actor_bound(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        request = self.rrequest(
            'RenderDocument',
            approved,
            authorization_id=str(authorization_id),
            formats=['DOCX', 'PDF'],
        )
        result = self.rapply(request)
        before = self.sequence
        self.assertEqual(self.rexecute(request), result)
        self.assertEqual(self.sequence, before)
        other_actor = Actor(id=uuid4(), kind='HUMAN')
        other = Principal(
            other_actor,
            self.tenant,
            self.case_id,
            stage11_actions(self.principal.actions),
        )
        other_token = self.authority.provision(other)
        conflict = self.rexecute(request, token=other_token)
        self.assertIsInstance(conflict, DomainError)
        self.assertEqual(conflict.code, 'IDEMPOTENCY_CONFLICT')

    def test_stage11_warning_findings_are_rebound_not_silently_dropped(self):
        issue = {
            'check': 'language',
            'code': 'SYNTHETIC_WARNING',
            'severity': 'WARNING',
            'path': '/sections',
            'message': 'Synthetic nonblocking warning',
        }
        _, validated, run = self.validated(issues=(issue,))
        self.assertEqual(len(run.findings), 1)
        approved, authorization_id, _ = self.authorize(validated, run)
        result, execution, _ = self.render_approved(
            approved, authorization_id
        )
        self.assertEqual(len(execution.run.findings), 1)
        finding = self.get(execution.run.findings[0])
        self.assertEqual(finding.target, result.refs[0])
        self.assertEqual(finding.target_hash, digest(self.get(result.refs[0])))
        self.assertEqual(finding.severity, 'WARNING')
        self.assertTrue(
            self.projection(execution.id).eligible_for_document_approval
        )

    def test_stage11_transaction_rollback_removes_bytes_draft_and_run(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        request = self.rrequest(
            'RenderDocument',
            approved,
            authorization_id=str(authorization_id),
            formats=['DOCX', 'PDF'],
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            before_sequence = tx.sequence()
            before_head = next(
                ref(item) for item in tx.heads()
                if item.kind == 'Draft'
            )
            before_artifacts = tx.connection.execute(
                "SELECT count(*) FROM lw_storage.artifacts WHERE category='render'"
            ).fetchone()[0]
        original = UnitOfWork.put_object

        def fail(tx, category, *args, **kwargs):
            original(tx, category, *args, **kwargs)
            if category == 'render_execution':
                raise RuntimeError('synthetic render rollback')

        with patch.object(UnitOfWork, 'put_object', fail):
            with self.assertRaises(RuntimeError):
                self.rexecute(request)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), before_sequence)
            current_head = next(
                ref(item) for item in tx.heads()
                if item.kind == 'Draft'
            )
            self.assertEqual(current_head, before_head)
            after_artifacts = tx.connection.execute(
                "SELECT count(*) FROM lw_storage.artifacts WHERE category='render'"
            ).fetchone()[0]
            self.assertEqual(after_artifacts, before_artifacts)

    def test_stage11_corrupted_render_bytes_fail_closed(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        _, execution, _ = self.render_approved(approved, authorization_id)
        artifact = execution.artifacts[0]
        with psycopg.connect(core.ADMIN) as connection:
            connection.execute(
                'ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob'
            )
            connection.execute(
                'UPDATE lw_storage.blobs SET data=%s WHERE artifact_id=%s',
                (b'corrupted', artifact.artifact_id),
            )
            connection.execute(
                'ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob'
            )
        projection = self.projection(execution.id)
        self.assertFalse(projection.eligible_for_document_approval)
        self.assertIn('RENDER_BYTES_UNAVAILABLE', projection.reasons)

    def test_stage11_render_becomes_stale_after_any_case_mutation(self):
        _, validated, run = self.validated()
        approved, authorization_id, _ = self.authorize(validated, run)
        _, execution, _ = self.render_approved(approved, authorization_id)
        self.assertTrue(
            self.projection(execution.id).eligible_for_document_approval
        )
        self.party()
        projection = self.projection(execution.id)
        self.assertFalse(projection.eligible_for_document_approval)
        self.assertIn('CASE_SEQUENCE_STALE', projection.reasons)

    def test_stage11_product_profile_keeps_release_bypass_closed(self):
        self.assertNotIn(
            'RequestRelease', stage11_actions(self.principal.actions)
        )
        request = self.request('RequestRelease')
        result = self.service.execute(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError)


def load_tests(loader, tests, pattern):
    """Focused Stage 11 module: do not duplicate inherited Stage 10 cases here."""
    suite = unittest.TestSuite()
    for name, value in RenderingTests.__dict__.items():
        if name.startswith('test_') and callable(value):
            suite.addTest(RenderingTests(name))
    return suite
