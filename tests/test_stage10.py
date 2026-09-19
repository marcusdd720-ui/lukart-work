"""Stage 10 synthetic PostgreSQL assurance; never loads private CASE material."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import unittest
from uuid import UUID, uuid4, uuid5
from unittest.mock import patch
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.postgres import UnitOfWork
from lukart_work.domain.models import Actor
from lukart_work.facts.service import FactEvidenceService
from lukart_work.validation.contracts import (
    ValidationExecution, ValidationProjection, ValidationReview, SEMANTIC_CHECKS, stage10_actions,
)
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.service import ValidationEngineService
from lukart_work.validation.rules import digest, ref
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


def load_tests(loader, tests, pattern):
    # Reuse synthetic fixture helpers, not inherited Stage 02/09 tests counted twice.
    return unittest.TestSuite(ValidationTests(name) for name in sorted(ValidationTests.__dict__)
                             if name.startswith('test_stage10_'))


if __name__ == '__main__':
    unittest.main()
