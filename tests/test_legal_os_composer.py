"""Focused composer boundary tests. Mocked services, NOT a live HUMAN/DB E2E."""
import json
from hashlib import sha256
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from lukart_work import legal_os_composer as compose
from lukart_work.contracts.messages import (
    CaseHeadResult,
    CommandResult,
    DomainError,
    GenerateDocument,
)
from lukart_work.domain.models import Address, Ref, VersionPin
from lukart_work.embedded_document_engine import CaseScope, EngineBoundaryError
from lukart_work.finalization.contracts import (
    FinalPackageRecord, FinalizationProfile, FinalizationProjection, FinalizationRequest,
)
from lukart_work.legal_os_case_view import read_session_case_action
from lukart_work.validation.contracts import ValidationRequest


class Revision:
    def __init__(self, entity):
        self.entity = entity


class ComposerTests(TestCase):
    def setUp(self):
        self.tenant, self.case = uuid4(), uuid4()
        self.scope = CaseScope(str(self.tenant), str(self.case))
        self.pin = VersionPin(id='synthetic-profile', version='1.0.0', content_hash='a' * 64)
        self.profile = FinalizationProfile(profile_id='synthetic-finalization', version='1.0.0',
            document_type=self.pin, header='Pismo syntetyczne', render_profile=self.pin)
        self.address = Address(country='PL', lines=('ul. Syntetyczna 1', 'Miasto Testowe'), postal_code='00-000')
        self.sender = self.entity('Party', display_name='Osoba Syntetyczna A', address=self.address, status='VERIFIED')
        self.recipient = self.entity('Institution', name='Instytucja Syntetyczna B', address=self.address, status='VERIFIED')
        self.filing = self.entity('Filing', document_type=self.pin, authors=(self.ref(self.sender),), recipient=self.ref(self.recipient))
        self.objective = Ref(kind='Request', id=uuid4(), revision=1)
        self.plan = self.entity('DocumentPlan', status='APPROVED', filing=self.ref(self.filing),
            position_scope='Syntetyczny opis sprawy i cel pisma.', input_snapshot_id=uuid4(),
            input_snapshot_hash='b' * 64, objectives=(self.objective,))
        self.draft = self.entity('Draft', snapshot_hash='b' * 64, status='VALIDATED')
        self.render_id = uuid4()
        self.records = {e.id: e for e in (self.sender, self.recipient, self.filing, self.plan, self.draft)}
        self.head = CaseHeadResult(result_type='CASE_HEAD', tenant_id=self.tenant, case_id=self.case,
            case_sequence=8, heads=tuple(self.ref(e) for e in self.records.values()))
        self.required = []
        self.principal = NS(actor=NS(kind='HUMAN'), tenant_id=self.tenant, case_id=self.case,
            require=lambda tenant, case, action: self.required.append((tenant, case, action)))
        @contextmanager
        def session(token):
            if token != 'synthetic-unit-only':
                raise EngineBoundaryError('AUTH_REQUIRED')
            yield self.principal
        self.op = NS(core=NS(authority=NS(session=session)), case_profile=self.profile, binding=None,
            drafting=NS(profiles={'QUICK': object()}),
            finalization=NS(package_profile=object(), repository=NS(storage=True)))
        self.calls = []
        self.op.query_core = self.query
        self.op.query_finalization = Mock()
        for route in compose.EmbeddedDocumentEngine.__init__.__globals__['HUMAN_COMMAND_ROUTES']:
            setattr(self.op, route, Mock(side_effect=lambda request, token, route=route: self.execute(route, request, token)))
        self.patch = patch.object(compose, 'RevisionResult', Revision)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.form = {'description': self.plan.position_scope, 'document_type': self.pin.id,
            'sender': {'name': self.sender.display_name, 'address': self.address.model_dump(mode='json')},
            'recipient': {'name': self.recipient.name, 'address': self.address.model_dump(mode='json')}}

    def entity(self, kind, **fields):
        return NS(kind=kind, id=uuid4(), revision=1, tenant_id=self.tenant, case_id=self.case, **fields)

    def ref(self, entity):
        return Ref(kind=entity.kind, id=entity.id, revision=entity.revision)

    def query(self, request, token):
        if request['operation'] == 'GetCaseHead':
            return self.head
        return Revision(self.records[__import__('uuid').UUID(request['target']['id'])])

    def execute(self, route, request, token):
        self.calls.append((route, deepcopy(request)))
        return CommandResult(command_id=uuid4(), state='APPLIED', case_sequence=9,
            refs=(self.ref(self.draft),), event_ids=(), errors=())

    def payload(self, action, **extra):
        return dict(action=action, expected_case_sequence=8, command_id=str(uuid4()),
                    idempotency_key=str(uuid4()), correlation_id=str(uuid4()), **extra)

    def action(self, payload, token='synthetic-unit-only'):
        return compose.composer_action(self.op, payload, token)

    def test_context_uses_only_configured_profile_and_real_approved_plan(self):
        data = self.action({'action': 'composition_context'})
        self.assertEqual(data['document_types'], [{'id': self.pin.id, 'label': self.profile.header}])
        self.assertEqual(data['profiles'], ['QUICK'])
        self.assertEqual(data['plans'][0]['form'], self.form)
        self.assertEqual(self.calls, [])

    def test_context_does_not_invent_approved_plan(self):
        self.plan.status = 'PROPOSED'
        data = self.action({'action': 'composition_context'})
        self.assertEqual(data['plans'], [])
        self.assertEqual(data['required_gate'], 'APPROVED_WORK_PLAN_REQUIRED')

    def test_session_dispatch_reaches_composer_without_client_scope(self):
        data = read_session_case_action(self.op, {'action': 'composition_context'}, 'synthetic-unit-only')
        self.assertEqual(data['plans'][0]['form'], self.form)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(EngineBoundaryError, 'SESSION_OPERATION_NOT_ALLOWED'):
            read_session_case_action(self.op, {'action': 'composition_context', 'tenant_id': str(self.tenant)}, 'synthetic-unit-only')

    def test_session_dispatch_rejects_ai_before_any_composer_read(self):
        self.principal.actor.kind = 'AI'
        with self.assertRaisesRegex(EngineBoundaryError, 'AI_SESSION_DENIED'):
            read_session_case_action(self.op, {'action': 'composition_context'}, 'synthetic-unit-only')
        self.assertEqual(self.required, [])

    def test_all_required_party_and_address_fields_checked(self):
        for role in ('sender', 'recipient'):
            for field in ('name', 'address'):
                form = deepcopy(self.form); form[role].pop(field)
                with self.subTest(role=role, field=field), self.assertRaises(EngineBoundaryError):
                    compose.validate_form(form)
        form = deepcopy(self.form); form['sender']['address']['postal_code'] = ''
        with self.assertRaises(EngineBoundaryError): compose.validate_form(form)

    def test_save_brief_calls_existing_intake_and_preserves_all_values(self):
        with patch.object(compose, 'upload_case_source', return_value=NS(model_dump=lambda **kw: {'saved': True})) as intake:
            data = self.action(self.payload('save_document_brief', form=self.form, run_id=str(uuid4())))
        import base64
        saved = json.loads(base64.b64decode(intake.call_args.args[1]['content_base64']))
        self.assertEqual(saved, self.form)
        self.assertFalse(data['human_approval_created'])
        self.assertEqual(self.calls, [])

    def test_generate_calls_existing_generator_with_valid_native_contract(self):
        result = self.action(self.payload('generate_document', form=self.form,
            plan_id=str(self.plan.id), plan_revision=1, profile='QUICK'))
        route, request = self.calls[0]
        self.assertEqual(route, 'execute_draft')
        parsed = GenerateDocument.model_validate_json(json.dumps(request))
        self.assertEqual(parsed.plan.id, self.plan.id)
        self.assertEqual(result['draft']['id'], str(self.draft.id))
        self.assertEqual(len(self.calls), 1)

    def test_description_change_cannot_be_silently_ignored(self):
        form = deepcopy(self.form); form['description'] = 'Nowy opis wymagający przeglądu.'
        with self.assertRaisesRegex(EngineBoundaryError, 'DESCRIPTION_REQUIRES_REVIEWED_PLAN'):
            self.action(self.payload('generate_document', form=form, plan_id=str(self.plan.id), plan_revision=1, profile='QUICK'))
        self.assertEqual(self.calls, [])

    def test_party_change_and_unverified_party_are_refused(self):
        self.sender.status = 'UNVERIFIED'
        with self.assertRaisesRegex(EngineBoundaryError, 'VERIFIED_PARTIES'):
            self.action(self.payload('generate_document', form=self.form, plan_id=str(self.plan.id), plan_revision=1, profile='QUICK'))
        self.assertEqual(self.calls, [])

    def test_unknown_type_and_unconfigured_model_profile_are_refused(self):
        form = deepcopy(self.form); form['document_type'] = 'invented'
        with self.assertRaisesRegex(EngineBoundaryError, 'DOCUMENT_TYPE_NOT_CONFIGURED'):
            self.action(self.payload('save_document_brief', form=form, run_id=str(uuid4())))
        with self.assertRaisesRegex(EngineBoundaryError, 'DRAFTING_PROFILE_REQUIRED'):
            self.action(self.payload('generate_document', form=self.form, plan_id=str(self.plan.id), plan_revision=1, profile='FORENSIC'))

    def test_stale_sequence_refused_before_writes(self):
        payload = self.payload('save_document_brief', form=self.form, run_id=str(uuid4()))
        payload['expected_case_sequence'] = 7
        with self.assertRaisesRegex(EngineBoundaryError, 'CASE_STALE'): self.action(payload)
        self.assertEqual(self.calls, [])

    def test_client_scope_and_raw_confirmation_injection_refused(self):
        for extra in ({'tenant_id': str(uuid4())}, {'confirmed': True}, {'actor': 'HUMAN'}):
            with self.assertRaisesRegex(EngineBoundaryError, 'ACTION_DENIED'):
                self.action(dict(action='composition_context', **extra))

    def test_no_ai_session_or_missing_session(self):
        self.principal.actor.kind = 'AI'
        with self.assertRaises(EngineBoundaryError): self.action({'action': 'composition_context'})
        with self.assertRaises(EngineBoundaryError): self.action({'action': 'composition_context'}, token='')

    def test_cross_case_revision_is_refused(self):
        self.sender.case_id = uuid4()
        with self.assertRaisesRegex(EngineBoundaryError, 'REVISION_SCOPE_MISMATCH'):
            self.action({'action': 'composition_context'})

    def test_validation_delegates_to_native_policy_without_fabricated_review(self):
        projection = NS(draft=self.draft, draft_hash='c' * 64)
        with patch.object(compose, '_open', return_value=projection):
            result = self.action(self.payload('validate_document', draft_id=str(self.draft.id), draft_revision=1))
        route, request = self.calls[0]
        self.assertEqual(route, 'execute_validation')
        parsed = ValidationRequest.model_validate_json(json.dumps(request))
        self.assertIsNone(parsed.review_id)
        self.assertEqual(parsed.assessments, ())
        self.assertIn('validation_run_id', result)

    def test_render_delegates_to_native_renderer_without_final_approval(self):
        projection = NS(draft=self.draft, draft_hash='c' * 64)
        with patch.object(compose, '_open', return_value=projection):
            result = self.action(self.payload('render_document', draft_id=str(self.draft.id),
                draft_revision=1, validation_run_id=str(uuid4())))
        route, request = self.calls[0]
        self.assertEqual(route, 'execute_finalization')
        parsed = FinalizationRequest.model_validate_json(json.dumps(request))
        self.assertEqual(parsed.operation, 'RenderDraft')
        self.assertFalse(result['final_approval_created'])


    def finalization_projection(self, *, approval=None, release=None):
        render = NS(
            id=self.render_id, tenant_id=self.tenant, case_id=self.case,
            validated_draft=self.ref(self.draft), validated_draft_hash='c' * 64,
            snapshot_hash='b' * 64, committed_sequence=8,
            artifacts=(
                NS(artifact=NS(format='DOCX', media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', byte_length=12, content_hash='f' * 64)),
                NS(artifact=NS(format='PDF', media_type='application/pdf', byte_length=13, content_hash='a' * 64)),
            ),
        )
        return FinalizationProjection.model_construct(render=render, approval=approval, release=release)

    def finalization_payload(self, action, *, rationale='Human checked the exact rendered files.'):
        return dict(action=action, render_id=str(self.render_id), rationale=rationale,
                    command_id=str(uuid4()), idempotency_key=str(uuid4()),
                    correlation_id=str(uuid4()))

    def test_finalization_context_exposes_only_current_native_human_gate(self):
        self.draft.status = 'VALIDATED'
        self.op.query_finalization.return_value = self.finalization_projection()
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action({'action': 'finalization_context', 'render_id': str(self.render_id)})
        self.assertEqual(data['result_type'], 'FINALIZATION_CONTEXT')
        self.assertTrue(data['current'])
        self.assertTrue(data['can_approve'])
        self.assertFalse(data['can_release'])
        self.assertFalse(data['can_assemble'])
        self.assertEqual(data['next_gate'], 'HUMAN_DOCUMENT_APPROVAL')
        self.assertEqual([item['format'] for item in data['artifacts']], ['DOCX', 'PDF'])
        self.assertEqual(data['artifacts'][1]['content_hash'], 'a' * 64)

    def test_finalization_context_fails_closed_when_case_sequence_advanced(self):
        self.draft.status = 'VALIDATED'
        self.head = self.head.model_copy(update={"case_sequence": 9})
        self.op.query_finalization.return_value = self.finalization_projection()
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action({'action': 'finalization_context', 'render_id': str(self.render_id)})
        self.assertFalse(data['current'])
        self.assertFalse(data['can_approve'])
        self.assertEqual(data['status'], 'STALE_REQUIRES_REVALIDATION')

    def test_approve_document_binds_exact_validated_render_and_human_rationale(self):
        self.draft.status = 'VALIDATED'
        initial = self.finalization_projection()
        approval = NS(rendered_draft=self.ref(self.draft), rendered_draft_hash='c' * 64,
                      committed_sequence=9, approval_hash='d' * 64, actor=NS(kind='HUMAN'))
        updated = self.finalization_projection(approval=approval)
        self.op.query_finalization.side_effect = [initial, updated]
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action(self.finalization_payload('approve_document'))
        route, raw = self.calls[-1]
        request = FinalizationRequest.model_validate_json(json.dumps(raw))
        self.assertEqual(route, 'execute_finalization')
        self.assertEqual(request.operation, 'ApproveFinalDocument')
        self.assertEqual(request.target, self.ref(self.draft))
        self.assertEqual(request.render_id, self.render_id)
        self.assertEqual(request.meta.expected_case_sequence, 8)
        self.assertEqual(request.rationale, 'Human checked the exact rendered files.')
        self.assertEqual(data['result_type'], 'DOCUMENT_APPROVED')
        self.assertEqual(data['case_sequence'], 9)

    def test_release_document_requires_and_binds_existing_human_approval(self):
        self.draft.status = 'RENDERED'
        approval = NS(rendered_draft=self.ref(self.draft), rendered_draft_hash='c' * 64,
                      committed_sequence=8, approval_hash='d' * 64, actor=NS(kind='HUMAN'))
        initial = self.finalization_projection(approval=approval)
        release = NS(committed_sequence=9, result=NS(eligibility='FINAL', receipt=NS()))
        updated = self.finalization_projection(approval=approval, release=release)
        self.op.query_finalization.side_effect = [initial, updated]
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action(self.finalization_payload('release_document', rationale='Release this approved revision.'))
        route, raw = self.calls[-1]
        request = FinalizationRequest.model_validate_json(json.dumps(raw))
        self.assertEqual(route, 'execute_finalization')
        self.assertEqual(request.operation, 'RequestFinalRelease')
        self.assertEqual(request.target, approval.rendered_draft)
        self.assertEqual(request.meta.expected_case_sequence, approval.committed_sequence)
        self.assertEqual(data['result_type'], 'DOCUMENT_RELEASED')
        self.assertEqual(data['eligibility'], 'FINAL')

    def test_package_assembly_requires_final_release_and_verifies_persisted_record(self):
        self.draft.status = 'RENDERED'
        approval = NS(rendered_draft=self.ref(self.draft), rendered_draft_hash='c' * 64,
                      committed_sequence=7, approval_hash='d' * 64, actor=NS(kind='HUMAN'))
        release = NS(committed_sequence=8, result=NS(eligibility='FINAL', receipt=NS()))
        initial = self.finalization_projection(approval=approval, release=release)
        package = FinalPackageRecord.model_construct(
            id=uuid4(), tenant_id=self.tenant, case_id=self.case, render_id=self.render_id,
            release_id=uuid4(), manifest_hash='e' * 64, members=(), committed_sequence=9,
        )
        missing = DomainError(code='BROKEN_REFERENCE', path='', message='Not assembled',
                              retryable=False, correlation_id=uuid4())
        self.op.query_finalization.side_effect = [initial, missing, package]
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action(self.finalization_payload('assemble_package', rationale='Persist the released package.'))
        route, raw = self.calls[-1]
        request = FinalizationRequest.model_validate_json(json.dumps(raw))
        self.assertEqual(route, 'execute_finalization')
        self.assertEqual(request.operation, 'AssembleFinalPackage')
        self.assertEqual(request.meta.expected_case_sequence, release.committed_sequence)
        self.assertEqual(data['result_type'], 'PACKAGE_ASSEMBLED')
        self.assertEqual(data['package']['manifest_hash'], 'e' * 64)

    def test_package_member_read_is_allowlisted_and_hash_bound(self):
        content = b'{"verified":true}'
        package = FinalPackageRecord.model_construct(
            id=uuid4(), tenant_id=self.tenant, case_id=self.case, render_id=self.render_id,
            release_id=uuid4(), manifest_hash='e' * 64,
            members=(NS(name='document.json', media_type='application/json',
                        byte_length=len(content), content_hash=sha256(content).hexdigest()),),
            committed_sequence=9,
        )
        self.op.query_finalization.side_effect = [package, content]
        artifact = self.action({'action': 'read_package_member', 'render_id': str(self.render_id),
                                'member': 'document.json'})
        self.assertEqual(artifact.filename, 'document.json')
        self.assertEqual(artifact.mime_type, 'application/json')
        self.assertEqual(artifact.data, content)
        self.assertEqual(artifact.sha256, sha256(content).hexdigest())
        self.op.query_finalization.reset_mock()
        with self.assertRaisesRegex(EngineBoundaryError, 'PACKAGE_MEMBER_NOT_ALLOWED'):
            self.action({'action': 'read_package_member', 'render_id': str(self.render_id),
                         'member': '../private.txt'})
        self.op.query_finalization.assert_not_called()

    def test_release_and_package_actions_require_prior_native_gates(self):
        self.draft.status = 'VALIDATED'
        self.op.query_finalization.return_value = self.finalization_projection()
        with self.assertRaisesRegex(EngineBoundaryError, 'HUMAN_APPROVAL_REQUIRED'):
            self.action(self.finalization_payload('release_document'))
        self.assertEqual(self.calls, [])
        approval = NS(rendered_draft=self.ref(self.draft), rendered_draft_hash='c' * 64,
                      committed_sequence=8, approval_hash='d' * 64, actor=NS(kind='HUMAN'))
        self.draft.status = 'RENDERED'
        self.op.query_finalization.return_value = self.finalization_projection(approval=approval)
        with self.assertRaisesRegex(EngineBoundaryError, 'FINAL_RELEASE_REQUIRED'):
            self.action(self.finalization_payload('assemble_package'))
        self.assertEqual(self.calls, [])

    def test_stale_render_and_invalid_rationale_never_reach_native_write(self):
        self.draft.status = 'VALIDATED'
        self.head = self.head.model_copy(update={"case_sequence": 9})
        self.op.query_finalization.return_value = self.finalization_projection()
        with self.assertRaisesRegex(EngineBoundaryError, 'FINALIZATION_STALE'):
            self.action(self.finalization_payload('approve_document'))
        self.head = self.head.model_copy(update={"case_sequence": 8})
        with patch.object(compose, 'digest', return_value='c' * 64):
            with self.assertRaisesRegex(EngineBoundaryError, 'RATIONALE_REQUIRED'):
                self.action(self.finalization_payload('approve_document', rationale='x'))
        self.assertEqual(self.calls, [])

    def test_package_read_forbidden_is_not_misreported_as_missing_package(self):
        self.draft.status = 'RENDERED'
        approval = NS(rendered_draft=self.ref(self.draft), rendered_draft_hash='c' * 64,
                      committed_sequence=7, approval_hash='d' * 64, actor=NS(kind='HUMAN'))
        release = NS(committed_sequence=8, result=NS(eligibility='FINAL', receipt=NS()))
        self.op.query_finalization.side_effect = [
            self.finalization_projection(approval=approval, release=release),
            DomainError(code='FORBIDDEN', path='', message='No package read capability',
                        retryable=False, correlation_id=uuid4()),
        ]
        with patch.object(compose, 'digest', return_value='c' * 64):
            data = self.action({'action': 'finalization_context', 'render_id': str(self.render_id)})
        self.assertEqual(data['status'], 'FINAL_RELEASED')
        self.assertFalse(data['package_read_authorized'])
        self.assertFalse(data['can_assemble'])
        self.assertEqual(data['next_gate'], 'PACKAGE_READ_AUTHORITY_REQUIRED')

    def test_package_member_bytes_must_match_persisted_hash(self):
        content = b'{"verified":true}'
        package = FinalPackageRecord.model_construct(
            id=uuid4(), tenant_id=self.tenant, case_id=self.case, render_id=self.render_id,
            release_id=uuid4(), manifest_hash='e' * 64,
            members=(NS(name='document.json', media_type='application/json',
                        byte_length=len(content), content_hash='f' * 64),),
            committed_sequence=9,
        )
        self.op.query_finalization.side_effect = [package, content]
        with self.assertRaisesRegex(EngineBoundaryError, 'PACKAGE_MEMBER_INTEGRITY_FAILURE'):
            self.action({'action': 'read_package_member', 'render_id': str(self.render_id),
                         'member': 'document.json'})

    def test_finalization_commands_and_package_reads_reject_ai_session(self):
        self.principal.actor.kind = 'AI'
        with self.assertRaisesRegex(EngineBoundaryError, 'AI_SESSION_DENIED'):
            read_session_case_action(self.op, self.finalization_payload('approve_document'), 'synthetic-unit-only')
        with self.assertRaisesRegex(EngineBoundaryError, 'AI_SESSION_DENIED'):
            read_session_case_action(self.op, {'action': 'read_package_member',
                'render_id': str(self.render_id), 'member': 'document.json'}, 'synthetic-unit-only')
        self.assertEqual(self.calls, [])

    def test_native_rejection_is_not_success_or_automatic_retry(self):
        self.op.execute_draft.side_effect = None
        self.op.execute_draft.return_value = object()
        with self.assertRaisesRegex(EngineBoundaryError, 'NATIVE_OPERATION_REJECTED'):
            self.action(self.payload('generate_document', form=self.form, plan_id=str(self.plan.id), plan_revision=1, profile='QUICK'))
        self.op.execute_draft.assert_called_once()
