"""Stage 10 synthetic PostgreSQL assurance; never loads private CASE material."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import unittest
from uuid import UUID, uuid4, uuid5
from unittest.mock import patch
from pydantic import ValidationError
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.postgres import UnitOfWork
from lukart_work.domain.models import Actor
from lukart_work.facts.service import FactEvidenceService
from lukart_work.validation.contracts import (
    ValidationExecution, ValidationProjection, ValidationReview, ValidationReviewProposal, SEMANTIC_CHECKS, stage10_actions,
)
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.service import ValidationEngineService
from lukart_work.validation.rules import digest, ref, Violation
from tests import test_stage09 as drafting


class ValidationTests(drafting.ControlledDraftingTests):
    def setUp(self):
        super().setUp()
        actions = self.principal.actions | {'RecordValidationReview', 'RevokeValidationReview',
            'ResolveValidationFinding', 'GetValidation', 'ReviewEvidence', 'AcceptEvidence'}
        self.principal = Principal(self.actor, self.tenant, self.case_id, frozenset(actions))
        self.token = self.authority.provision(self.principal)
        self.validation = ValidationEngineService(self.repo, self.authority)

    def fact(self):
        fact, party, evidence, source = super().fact()
        service = FactEvidenceService(self.repo, self.authority)
        for operation in ('ReviewEvidence', 'AcceptEvidence'):
            request = self.request(operation, target=evidence)
            request.update(contract='urn:lukart:work:FactEvidenceRequest:1.0.0', rationale='Synthetic Stage 10 evidence review')
            result = service.execute(json.dumps(request), self.token)
            self.assertIsInstance(result, CommandResult, result)
            self.sequence = result.case_sequence
            evidence = result.refs[0]
        fact = self.apply('EditFact', {'evidence': [evidence.model_dump(mode='json')]}, fact)[0].refs[0]
        return fact, party, evidence, source

    def legal_authority_fixture(self, source_id, **kwargs):
        source, rule, citation_ref, approval = super().legal_authority_fixture(source_id, **kwargs)
        # Stage 09 tests a citation identity boundary; Stage 10 additionally checks literal quotation bytes.
        old = self.get(citation_ref)
        quote = 'Synthetic payment receipt.'
        citation = old.model_copy(update={'revision':old.revision + 1, 'previous_hash':digest(old),
            'quotation':quote, 'locator':old.locator.model_copy(update={'unit':'RECORD', 'value':'1', 'fragment_hash':sha256(quote.encode()).hexdigest()})})
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            records = tx.records()
            heads = {(e.kind, e.id):e for e in tx.heads()}
            self.service._validate(citation, old, tx, records, heads, self.principal)
            tx.append(citation)
            tx.set_sequence(tx.sequence() + 1)
        self.sequence += 1
        return source, rule, ref(citation), approval

    def generated(self, legal=True):
        case = self.approved_planning_case(legal=legal)
        def response(invocation):
            result = self.valid_output(case, invocation)
            if legal:
                result['section']['statements'].append(self.statement('Synthetic legal proposition.', 'LEGAL',
                    'SOURCE_BACKED', (case['legal_rule'],), citations=(case['citation'],)))
            return result
        self.provider.responder = response
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return case, self.get(result.refs[0])

    def vrequest(self, operation, draft, **extras):
        request = self.request(operation, target=ref(draft))
        request.pop('data')
        request.update(contract='urn:lukart:work:ValidationRequest:1.0.0', draft_hash=digest(draft),
            snapshot_hash=draft.snapshot_hash, validation_policy=validation_pin().model_dump(mode='json'),
            rationale='Synthetic Stage 10 validation intent', **extras)
        return request

    def vexecute(self, request, service=None, token=None):
        return (service or self.validation).execute(json.dumps(request), token or self.token)

    def vapply(self, request):
        result = self.vexecute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def review(self, draft, issues=(), outcomes=None):
        outcomes = outcomes or {}
        request = self.vrequest('RecordValidationReview', draft,
            assessments=[{'check': c, 'outcome': outcomes.get(c, 'PASS'),
                'rationale': 'Synthetic explicit human assessment of pinned content'} for c in SEMANTIC_CHECKS],
            issues=list(issues))
        self.vapply(request)
        return uuid5(UUID(request['meta']['command_id']), 'review')

    def validate(self, draft, review=None):
        request = self.vrequest('ValidateDraft', draft, review_id=str(review) if review else None)
        result = self.vapply(request)
        run_id = uuid5(UUID(request['meta']['command_id']), 'validation-run')
        return result, run_id, request

    def projection(self, run_id):
        return self.validation.query(json.dumps(dict(contract='urn:lukart:work:ValidationQuery:1.0.0',
            operation='GetValidation', tenant_id=str(self.tenant), case_id=str(self.case_id), run_id=str(run_id))), self.token)

    def state(self):
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            return (tx.sequence(), tx.records(), tx.events(), tx.outbox(),
                tx.objects('validation_execution', ValidationExecution), tx.objects('validation_review', ValidationReview))

    def test_stage10_golden_validated_is_not_rendered_or_final(self):
        _, draft = self.generated()
        review = self.review(draft)
        result, run_id, _ = self.validate(draft, review)
        output = self.get(result.refs[0])
        self.assertEqual(output.status, 'VALIDATED')
        self.assertEqual(output.sections, draft.sections)
        self.assertEqual(self.get(ref(draft)), draft)
        projection = self.projection(run_id)
        self.assertIsInstance(projection, ValidationProjection, projection)
        self.assertTrue(projection.eligible_for_approval, projection.reasons)
        self.assertEqual(projection.execution.run.checks[-1].outcome, 'NOT_RUN')
        self.assertEqual(projection.execution.run.render_hashes, ())
        self.assertEqual(projection.execution.run.draft_hash, digest(draft))
        self.assertEqual(self.state()[2], self.state()[3])

    def test_stage10_missing_review_persists_findings_and_denies_validation(self):
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft)
        self.assertEqual(self.get(result.refs[0]).status, 'GENERATED')
        self.assertEqual(len(result.refs) - 1, len(SEMANTIC_CHECKS))
        projection = self.projection(run_id)
        self.assertFalse(projection.eligible_for_approval)
        self.assertTrue(all(self.get(r).severity == 'BLOCKER' for r in result.refs[1:]))

    def test_stage10_severity_model_cannot_clear_blockers(self):
        _, draft = self.generated()
        for severity in ('INFO', 'WARNING', 'ERROR', 'BLOCKER', 'CRITICAL'):
            with self.subTest(severity=severity):
                issue = dict(check='language', code='SYN-ISSUE', severity=severity, path='/sections', message='Synthetic review issue')
                outcomes = {'language': 'FAIL'} if severity in ('ERROR', 'BLOCKER', 'CRITICAL') else {}
                review = self.review(draft, (issue,), outcomes)
                result, run_id, _ = self.validate(draft, review)
                projection = self.projection(run_id)
                self.assertEqual(projection.eligible_for_approval, severity in ('INFO', 'WARNING'))
                draft = self.get(result.refs[0])

    def test_stage10_client_pass_and_policy_substitution_rejected_without_writes(self):
        _, draft = self.generated()
        before = self.state()
        for changes in ({'assessments': [{'check':'facts','outcome':'PASS','rationale':'forged'}]},
                        {'draft_hash': '0'*64}, {'snapshot_hash': '0'*64}, {'status':'VALIDATED'},
                        {'validation_policy': {'id':'fake','version':'1','content_hash':'0'*64}}):
            request = self.vrequest('ValidateDraft', draft)
            request.update(changes)
            self.assertIsInstance(self.vexecute(request), DomainError)
            self.assertEqual(self.state(), before)

    def test_stage10_exact_replay_and_actor_binding_across_instances(self):
        _, draft = self.generated()
        result, _, request = self.validate(draft)
        before = self.state()
        other = ValidationEngineService(self.repo, self.authority)
        self.assertEqual(self.vexecute(request, service=other), result)
        self.assertEqual(self.state(), before)
        principal = Principal(Actor(id=uuid4(), kind='HUMAN'), self.tenant, self.case_id, self.principal.actions)
        token = self.authority.provision(principal)
        denied = self.vexecute(request, token=token)
        self.assertEqual(denied.code, 'IDEMPOTENCY_CONFLICT')

    def test_stage10_concurrent_same_key_replays_once(self):
        _, draft = self.generated()
        request = self.vrequest('ValidateDraft', draft)
        authority = TokenAuthority()
        token = authority.provision(self.principal)
        other = ValidationEngineService(self.repo, authority)
        with ThreadPoolExecutor(2) as pool:
            one = pool.submit(self.vexecute, request)
            two = pool.submit(self.vexecute, request, other, token)
            self.assertEqual(one.result(), two.result())
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(len(tx.objects('validation_execution', ValidationExecution)), 1)

    def test_stage10_concurrent_distinct_commands_enforce_case_cas(self):
        _, draft = self.generated()
        requests = [self.vrequest('ValidateDraft', draft) for _ in range(2)]
        authority = TokenAuthority()
        token = authority.provision(self.principal)
        other = ValidationEngineService(self.repo, authority)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(self.vexecute, requests[0]), pool.submit(self.vexecute, requests[1], other, token)]
            results = [f.result() for f in futures]
        self.assertEqual(sum(isinstance(r, CommandResult) for r in results), 1)
        self.assertEqual([r.code for r in results if isinstance(r, DomainError)], ['CONFLICT'])

    def test_stage10_transaction_rollback_after_findings_and_run(self):
        _, draft = self.generated()
        before = self.state()
        original = UnitOfWork.put_object
        def fail(tx, category, *args, **kwargs):
            original(tx, category, *args, **kwargs)
            if category == 'validation_execution':
                raise RuntimeError('synthetic injected rollback')
        with patch.object(UnitOfWork, 'put_object', fail):
            with self.assertRaises(RuntimeError):
                self.vexecute(self.vrequest('ValidateDraft', draft))
        self.assertEqual(self.state(), before)

    def test_stage10_live_snapshot_and_plan_approval_revocation(self):
        case, draft = self.generated()
        approval = self.get(case['plan']).approval
        self.apply('RevokeDecision', target=approval)
        before = self.state()
        self.assertIsInstance(self.vexecute(self.vrequest('ValidateDraft', draft)), DomainError)
        self.assertEqual(self.state(), before)

    def test_stage10_success_becomes_stale_after_case_mutation(self):
        _, draft = self.generated()
        _, run_id, _ = self.validate(draft, self.review(draft))
        self.assertTrue(self.projection(run_id).eligible_for_approval)
        self.party()
        projection = self.projection(run_id)
        self.assertFalse(projection.eligible_for_approval)
        self.assertIn('CASE_SEQUENCE_STALE', projection.reasons)

    def test_stage10_review_revocation_after_success_and_historical_replay(self):
        _, draft = self.generated()
        review = self.review(draft)
        result, run_id, request = self.validate(draft, review)
        self.vapply(self.vrequest('RevokeValidationReview', draft, review_id=str(review)))
        self.assertFalse(self.projection(run_id).eligible_for_approval)
        self.assertEqual(self.vexecute(request), result)
        self.assertFalse(self.projection(run_id).eligible_for_approval)

    def test_stage10_findings_resolution_does_not_rewrite_failed_run(self):
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft)
        finding = self.get(result.refs[1])
        decision = self.decision('FINDING_RESOLUTION', [ref(finding)])
        request = self.request('ResolveValidationFinding', target=ref(finding))
        request.pop('data')
        request.update(contract='urn:lukart:work:ValidationRequest:1.0.0', validation_policy=validation_pin().model_dump(mode='json'),
            decision=decision.model_dump(mode='json'), resolution='FALSE_POSITIVE', rationale='Synthetic explicit review')
        resolved = self.vapply(request)
        self.assertEqual(self.get(resolved.refs[0]).status, 'FALSE_POSITIVE')
        self.assertEqual(self.get(ref(finding)), finding)
        self.assertFalse(self.projection(run_id).eligible_for_approval)

    def test_stage10_missing_procedural_rules_never_pass_vacuously(self):
        _, draft = self.generated(legal=False)
        result, run_id, _ = self.validate(draft, self.review(draft))
        self.assertFalse(self.projection(run_id).eligible_for_approval)
        self.assertIn('PROCEDURAL_RULE_COVERAGE_UNKNOWN', {self.get(r).code for r in result.refs[1:]})

    def test_stage10_ai_service_and_cross_case_denied(self):
        _, draft = self.generated()
        before = self.state()
        for kind in ('AI', 'SERVICE'):
            token = self.authority.provision(Principal(Actor(id=uuid4(), kind=kind), self.tenant, self.case_id, self.principal.actions))
            self.assertEqual(self.vexecute(self.vrequest('ValidateDraft', draft), token=token).code, 'FORBIDDEN')
        request = self.vrequest('ValidateDraft', draft)
        request['meta']['case_id'] = str(uuid4())
        self.assertEqual(self.vexecute(request).code, 'FORBIDDEN')
        self.assertEqual(before, self.state())

    def test_stage10_product_profile_and_legacy_bypass_closed(self):
        _, draft = self.generated()
        self.assertNotIn('RequestRelease', stage10_actions(self.principal.actions))
        self.assertIsInstance(self.service.execute(json.dumps(self.request('ValidateDraft', target=ref(draft))), self.token), DomainError)

    def test_stage10_execution_date_expiry_and_source_drift(self):
        _, draft = self.generated()
        _, run_id, _ = self.validate(draft, self.review(draft))
        now = self.validation.clock()
        self.validation.clock = lambda: now + timedelta(days=1)
        self.assertIn('EVALUATION_DATE_STALE', self.projection(run_id).reasons)

    def test_stage10_source_disappearance_invalidates_success(self):
        _, draft = self.generated()
        _, run_id, _ = self.validate(draft, self.review(draft))
        with patch.object(UnitOfWork, 'source_bytes', side_effect=Violation('PROVENANCE_MISSING')):
            projection = self.projection(run_id)
        self.assertFalse(projection.eligible_for_approval)
        self.assertIn('AUTHORITY_OR_SOURCE_STALE', projection.reasons)

    def test_stage10_legal_authority_revocation_denies_new_run(self):
        case, draft = self.generated()
        self.apply('RevokeDecision', target=case['legal_approval'])
        before = self.state()
        self.assertIsInstance(self.vexecute(self.vrequest('ValidateDraft', draft)), DomainError)
        self.assertEqual(before, self.state())

    def test_stage10_snapshot_revocation_denies_new_run(self):
        case, draft = self.generated()
        self.apply('RevokeDecision', target=case['snapshot_acceptance'])
        before = self.state()
        self.assertIsInstance(self.vexecute(self.vrequest('ValidateDraft', draft)), DomainError)
        self.assertEqual(before, self.state())

    def test_stage10_rejected_resolution_without_live_human_decision(self):
        _, draft = self.generated()
        result, _, _ = self.validate(draft)
        finding = self.get(result.refs[1])
        decision = self.decision('FINDING_RESOLUTION', [ref(finding)])
        self.apply('RevokeDecision', target=decision)
        request = self.request('ResolveValidationFinding', target=ref(finding))
        request.pop('data')
        request.update(contract='urn:lukart:work:ValidationRequest:1.0.0', validation_policy=validation_pin().model_dump(mode='json'),
            decision=decision.model_dump(mode='json'), resolution='RESOLVED', rationale='Synthetic revoked resolution')
        before = self.state()
        self.assertIsInstance(self.vexecute(request), DomainError)
        self.assertEqual(before, self.state())

    def test_stage10_finding_ids_manifest_and_audit_are_reproducible(self):
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft)
        projection = self.projection(run_id)
        execution = projection.execution
        self.assertEqual(digest(execution.manifest), execution.run.execution_manifest_hash)
        self.assertEqual(execution.manifest.draft_hash, digest(draft))
        for target in result.refs[1:]:
            finding = self.get(target)
            check = finding.path.split('/')[-1]
            expected = uuid5(run_id, digest((check, finding.code, finding.path, finding.severity, finding.message)))
            self.assertEqual(finding.id, expected)
            self.assertEqual(finding.provenance.method, 'VALIDATION')
            self.assertEqual(finding.provenance.inputs, (ref(draft),))

    def test_stage10_procedural_violation_and_unknown_are_not_overridden_by_review(self):
        original = self.proc_apply
        def proc(operation, data=None, target=None):
            if operation == 'RegisterProceduralRule':
                data['spec']['requirements'] = [
                    {'path':'/case/status', 'operator':'EQUALS', 'operand':'CLOSED'},
                    {'path':'/context/signature', 'operator':'PRESENT', 'operand':None}]
            return original(operation, data, target)
        self.proc_apply = proc
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft, self.review(draft))
        codes = {self.get(r).code for r in result.refs[1:]}
        self.assertTrue({'PROCEDURAL_FALSE', 'PROCEDURAL_UNKNOWN'} <= codes)
        self.assertFalse(self.projection(run_id).eligible_for_approval)

    def test_stage10_claim_context_never_becomes_procedural_fact(self):
        original = self.proc_apply
        def proc(operation, data=None, target=None):
            if operation == 'RegisterProceduralRule':
                data['spec']['requirements'] = [{'path':'/context/signature', 'operator':'PRESENT', 'operand':None}]
            return original(operation, data, target)
        self.proc_apply = proc
        _, draft = self.generated()
        review = self.review(draft)
        request = self.vrequest('ValidateDraft', draft, review_id=str(review),
            procedural_context=[{'key':'signature','classification':'CLAIM','value':True,'facts':[]}])
        result = self.vapply(request)
        self.assertIn('PROCEDURAL_ABSTAIN', {self.get(r).code for r in result.refs[1:]})

    def test_stage10_fake_fact_context_rejected_atomically(self):
        case, draft = self.generated()
        request = self.vrequest('ValidateDraft', draft,
            procedural_context=[{'key':'signature','classification':'FACT','value':True,
                'facts':[case['fact'].model_dump(mode='json')]}])
        before = self.state()
        self.assertIsInstance(self.vexecute(request), DomainError)
        self.assertEqual(before, self.state())

    def test_stage10_review_duplicate_incomplete_and_contradictory_outcomes_rejected(self):
        _, draft = self.generated()
        assessments = [{'check':c,'outcome':'PASS','rationale':'Synthetic review'} for c in SEMANTIC_CHECKS]
        before = self.state()
        variants = [dict(assessments=assessments[:-1]), dict(assessments=assessments + assessments[:1]),
            dict(assessments=assessments, issues=[dict(check='language',code='SYN',severity='CRITICAL',path='/',message='Synthetic defect')])]
        for kwargs in variants:
            self.assertIsInstance(self.vexecute(self.vrequest('RecordValidationReview', draft, **kwargs)), DomainError)
            self.assertEqual(before, self.state())

    def test_stage10_cross_case_sql_objects_and_runtime_immutability(self):
        import psycopg
        _, draft = self.generated()
        _, run_id, _ = self.validate(draft)
        with self.repo.transaction(self.tenant, uuid4()) as tx:
            self.assertEqual(tx.objects('validation_execution', ValidationExecution), ())
        with self.assertRaises(psycopg.Error):
            with self.repo.transaction(self.tenant, self.case_id) as tx:
                tx.connection.execute("UPDATE lw_core.objects SET payload='{}' WHERE category='validation_execution'")
        self.assertIsInstance(self.projection(run_id), ValidationProjection)

    def test_stage10_review_provider_proposal_is_not_a_command(self):
        _, draft = self.generated()
        proposal = dict(task='LANGUAGE_REVIEW', draft=ref(draft).model_dump(mode='json'), draft_hash=digest(draft),
            snapshot_hash=draft.snapshot_hash, policy=validation_pin().model_dump(mode='json'),
            assessments=[{'check':'language','outcome':'PASS','rationale':'Synthetic proposal'}], issues=[],
            disposition='PROPOSE', reason='Synthetic proposal-only output')
        ValidationReviewProposal.model_validate_json(json.dumps(proposal))
        before = self.state()
        self.assertIsInstance(self.vexecute(proposal), DomainError)
        proposal['assessments'][0]['check'] = 'legal_basis'
        with self.assertRaises(ValidationError):
            ValidationReviewProposal.model_validate_json(json.dumps(proposal))
        self.assertEqual(before, self.state())

    def test_stage10_fabricated_quotation_cannot_be_overridden_by_human_pass(self):
        original = self.legal_authority_fixture
        def fixture(source_id, **kwargs):
            source, rule, citation_ref, approval = original(source_id, **kwargs)
            old = self.get(citation_ref)
            citation = old.model_copy(update={'revision':old.revision+1, 'previous_hash':digest(old),
                'quotation':'Synthetic fabricated quotation absent from source'})
            with self.repo.transaction(self.tenant, self.case_id) as tx:
                tx.append(citation)
                tx.set_sequence(tx.sequence()+1)
            self.sequence += 1
            return source, rule, ref(citation), approval
        self.legal_authority_fixture = fixture
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft, self.review(draft))
        self.assertIn('QUOTATION_BYTES_MISMATCH', {self.get(r).code for r in result.refs[1:]})
        self.assertFalse(self.projection(run_id).eligible_for_approval)

    def test_stage10_supported_deadline_context_expires_within_same_day(self):
        before_deadline = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        trigger_date = before_deadline.date().isoformat()
        original_fact = self.fact
        def fact_fixture():
            fact, party, evidence, source = original_fact()
            statement = json.dumps({'key':'trigger','value':trigger_date}, sort_keys=True, separators=(',', ':'))
            fact = self.apply('EditFact', {'statement':statement}, fact)[0].refs[0]
            return fact, party, evidence, source
        self.fact = fact_fixture
        original_proc = self.proc_apply
        def proc(operation, data=None, target=None):
            if operation == 'RegisterProceduralRule':
                data['spec'].update(category='DEADLINE', requirements=[], deadline={
                    'trigger_key':'trigger','offset_days':0,'timezone':'UTC','due_time':'12:00', 'calendar_mode':'CALENDAR_DAYS'})
            return original_proc(operation, data, target)
        self.proc_apply = proc
        case, draft = self.generated()
        self.validation.clock = lambda: before_deadline
        review = self.review(draft)
        request = self.vrequest('ValidateDraft', draft, review_id=str(review), procedural_context=[{
            'key':'trigger','classification':'FACT','value':trigger_date,'facts':[case['fact'].model_dump(mode='json')]}])
        result = self.vapply(request)
        run_id = uuid5(UUID(request['meta']['command_id']), 'validation-run')
        self.assertEqual(self.get(result.refs[0]).status, 'VALIDATED')
        self.assertTrue(self.projection(run_id).eligible_for_approval)
        self.validation.clock = lambda: before_deadline + timedelta(hours=3)
        projection = self.projection(run_id)
        self.assertFalse(projection.eligible_for_approval)
        self.assertIn('PROCEDURAL_STATE_STALE', projection.reasons)

    def test_stage10_unverifiable_locator_denies_quotation(self):
        original = self.legal_authority_fixture
        def fixture(source_id, **kwargs):
            source, rule, citation_ref, approval = original(source_id, **kwargs)
            old = self.get(citation_ref)
            citation = old.model_copy(update={'revision':old.revision+1, 'previous_hash':digest(old),
                'locator':old.locator.model_copy(update={'unit':'BYTE_RANGE','value':'900:901'})})
            with self.repo.transaction(self.tenant, self.case_id) as tx:
                tx.append(citation)
                tx.set_sequence(tx.sequence()+1)
            self.sequence += 1
            return source, rule, ref(citation), approval
        self.legal_authority_fixture = fixture
        _, draft = self.generated()
        result, run_id, _ = self.validate(draft, self.review(draft))
        self.assertIn('QUOTATION_LOCATOR_UNSUPPORTED', {self.get(r).code for r in result.refs[1:]})
        self.assertFalse(self.projection(run_id).eligible_for_approval)

    def test_stage10_query_database_failure_returns_only_safe_code(self):
        import psycopg
        with patch.object(self.repo, 'transaction', side_effect=psycopg.OperationalError('SYNTHETIC-DRIVER-DETAIL')):
            result = self.projection(uuid4())
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'UNKNOWN')
        self.assertNotIn('SYNTHETIC-DRIVER-DETAIL', result.model_dump_json())


def load_tests(loader, tests, pattern):
    # Reuse synthetic fixture helpers, not inherited Stage 02/09 tests counted twice.
    return unittest.TestSuite(ValidationTests(name) for name in sorted(ValidationTests.__dict__)
                             if name.startswith('test_stage10_'))


if __name__ == '__main__':
    unittest.main()
