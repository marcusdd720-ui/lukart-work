"""Stage 08 Document Planner acceptance on real PostgreSQL; synthetic data only."""
import json
from typing import get_args
import unittest
from unittest.mock import patch
from uuid import uuid4

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.security import Principal
from lukart_work.domain.models import Actor
from lukart_work.planner.contracts import DocumentPlanProjection, PlannerOperation
from lukart_work.planner.service import DocumentPlannerService
from lukart_work.validation.rules import digest
from tests import test_stage02 as core


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 08 requires isolated PostgreSQL')
class DocumentPlannerTests(core.Stage02Tests):
    def setUp(self):
        super().setUp()
        self.authority.revoke(self.token)
        actions = self.principal.actions | frozenset(get_args(PlannerOperation)) | {'GetDocumentPlan'}
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.planner = DocumentPlannerService(self.repo, self.authority)

    def prequest(self, operation, data=None, target=None):
        request = self.request(operation, data, target)
        request['contract'] = 'urn:lukart:work:PlannerRequest:1.0.0'
        request['rationale'] = 'Synthetic Stage 08 planning intent'
        return request

    def pexecute(self, request, token=None):
        return self.planner.execute(json.dumps(request), token or self.token)

    def papply(self, operation, data=None, target=None):
        result = self.pexecute(self.prequest(operation, data, target))
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def projection(self, plan, token=None, tenant=None, case_id=None):
        payload = {
            'contract': 'urn:lukart:work:PlannerQuery:1.0.0',
            'operation': 'GetDocumentPlan',
            'tenant_id': str(tenant or self.tenant),
            'case_id': str(case_id or self.case_id),
            'plan': plan.model_dump(mode='json'),
        }
        return self.planner.get_plan(json.dumps(payload), token or self.token)

    def planning_case(self):
        fact, party, evidence, _ = self.fact()
        filing = self.apply('AddFiling', {
            'document_type': core.PIN,
            'direction': 'OUTGOING',
            'recipient': party.model_dump(mode='json'),
            'authors': [party.model_dump(mode='json')],
        })[0].refs[0]
        issue = self.apply('AddIssue', {
            'question': 'Synthetic Stage 08 issue',
            'facts': [fact.model_dump(mode='json')],
            'rules': [],
        })[0].refs[0]
        claim = self.apply('AddClaim', {
            'claim_type': 'ASSERTION',
            'statement': 'Synthetic Stage 08 assertion',
            'claimant': party.model_dump(mode='json'),
            'issues': [issue.model_dump(mode='json')],
            'facts': [fact.model_dump(mode='json')],
            'rules': [],
            'support': 'SOURCE_BACKED',
        })[0].refs[0]
        objective = self.apply('AddRequest', {
            'filing': filing.model_dump(mode='json'),
            'request_type': 'SYNTHETIC_RELIEF',
            'text': 'Synthetic requested outcome',
            'claims': [claim.model_dump(mode='json')],
            'evidence': [evidence.model_dump(mode='json')],
        })[0].refs[0]
        snapshot = self.snapshot()
        acceptance = self.accept(snapshot)
        return fact, party, evidence, filing, claim, objective, snapshot, acceptance

    @staticmethod
    def section(fact, evidence, claim, objective, *, title='Factual basis'):
        return {
            'section_type': 'FACTUAL_BACKGROUND',
            'title': title,
            'arguments': [],
            'allowed_inputs': [
                fact.model_dump(mode='json'),
                evidence.model_dump(mode='json'),
                claim.model_dump(mode='json'),
                objective.model_dump(mode='json'),
            ],
            'required_inputs': [fact.model_dump(mode='json')],
            'allowed_claims': [claim.model_dump(mode='json')],
            'forbidden': [
                'UNSUPPORTED_ASSERTION', 'UNMARKED_INFERENCE', 'NEW_FACT', 'NEW_LEGAL_RULE',
            ],
            'requirements': ['CHRONOLOGICAL'],
        }

    def plan_data(self, fact, evidence, filing, claim, objective, snapshot, **changes):
        data = {
            'snapshot_id': str(snapshot.id),
            'snapshot_hash': digest(snapshot),
            'filing': filing.model_dump(mode='json'),
            'objectives': [objective.model_dump(mode='json')],
            'position_scope': 'Synthetic Stage 08 scope',
            'argument_order': [],
            'evidence': [evidence.model_dump(mode='json')],
            'sections': [self.section(fact, evidence, claim, objective)],
        }
        data.update(changes)
        return data

    def test_golden_plan_is_derived_after_snapshot_and_provenance_bound(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        request = self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        ))
        result = self.pexecute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        self.assertEqual(len(result.refs), 2)
        plan_ref, section_ref = result.refs
        plan = self.get(plan_ref)
        section = self.get(section_ref)
        members = {m.ref for m in snapshot.members}
        self.assertNotIn(section_ref, members)
        self.assertEqual(plan.section_order, (section_ref,))
        self.assertEqual(section.status, 'READY')
        declared = {
            *section.arguments,
            *section.contract.allowed_inputs,
            *section.contract.required_inputs,
            *section.contract.allowed_claims,
        }
        self.assertTrue(declared <= members)
        self.assertEqual(plan.input_snapshot_hash, digest(snapshot))
        self.assertEqual(self.pexecute(request), result)
        projection = self.projection(plan_ref)
        self.assertIsInstance(projection, DocumentPlanProjection, projection)
        self.assertEqual(projection.plan, plan)
        self.assertEqual(projection.sections, (section,))
        self.assertFalse(projection.approval_current)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertFalse(any(e.kind == 'Draft' for e in tx.heads()))

    def test_review_approval_and_revocation_are_live_authority(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        plan = self.papply('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        )).refs[0]
        reviewed = self.papply('ReviewDocumentPlan', target=plan).refs[0]
        decision = self.decision('PLAN_APPROVAL', [reviewed])
        approved = self.papply('ApproveDocumentPlan', {
            'decision': decision.model_dump(mode='json')
        }, reviewed).refs[0]
        self.assertTrue(self.projection(approved).approval_current)
        self.apply('RevokeDecision', target=decision)
        self.assertFalse(self.projection(approved).approval_current)

    def test_revoked_snapshot_acceptance_blocks_new_plan(self):
        fact, _, evidence, filing, claim, objective, snapshot, acceptance = self.planning_case()
        self.apply('RevokeDecision', target=acceptance)
        result = self.pexecute(self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        )))
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'GATE_DENIED')

    def test_unsafe_section_contract_and_claim_escape_are_rejected(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        unsafe = self.section(fact, evidence, claim, objective)
        unsafe['forbidden'] = ['NEW_FACT']
        result = self.pexecute(self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot, sections=[unsafe]
        )))
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'SCHEMA_INVALID')

        escaped = self.section(fact, evidence, claim, objective)
        escaped['allowed_inputs'] = [
            fact.model_dump(mode='json'), evidence.model_dump(mode='json'), objective.model_dump(mode='json')
        ]
        result = self.pexecute(self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot, sections=[escaped]
        )))
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'SCHEMA_INVALID')

    def test_reference_outside_snapshot_fails_closed_without_fact_promotion(self):
        fact, party, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        outside = self.apply('AddFact', {
            'statement': 'Synthetic post-snapshot user assertion',
            'support': 'UNSUPPORTED',
            'evidence': [],
            'subjects': [party.model_dump(mode='json')],
            'key_fact': False,
        })[0].refs[0]
        section = self.section(fact, evidence, claim, objective)
        section['allowed_inputs'].append(outside.model_dump(mode='json'))
        result = self.pexecute(self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot, sections=[section]
        )))
        self.assertIsInstance(result, DomainError)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.records()[outside].status, 'CANDIDATE')
            self.assertFalse(any(e.kind == 'DocumentPlan' for e in tx.heads()))

    def test_idempotency_conflict_and_case_sequence_cas(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        request = self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        ))
        first = self.pexecute(request)
        self.assertIsInstance(first, CommandResult, first)
        self.sequence = first.case_sequence
        self.assertEqual(self.pexecute(request), first)

        changed = json.loads(json.dumps(request))
        changed['data']['position_scope'] = 'Different synthetic scope'
        conflict = self.pexecute(changed)
        self.assertIsInstance(conflict, DomainError)
        self.assertEqual(conflict.code, 'IDEMPOTENCY_CONFLICT')

        stale = self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        ))
        stale['meta']['expected_case_sequence'] = self.sequence - 1
        result = self.pexecute(stale)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'CONFLICT')

    def test_ai_and_cross_scope_access_are_denied(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        ai = Principal(
            Actor(id=uuid4(), kind='AI'), self.tenant, self.case_id,
            self.principal.actions,
        )
        ai_token = self.authority.provision(ai)
        result = self.pexecute(self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        )), ai_token)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'FORBIDDEN')

        other_tenant, other_case = uuid4(), uuid4()
        other = Principal(self.actor, other_tenant, other_case, self.principal.actions)
        other_token = self.authority.provision(other)
        result = self.projection(
            self.case_ref, token=other_token, tenant=other_tenant, case_id=other_case
        )
        self.assertIsInstance(result, DomainError)

    def test_transaction_rolls_back_sections_plan_audit_and_outbox(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        before_sequence = self.sequence
        request = self.prequest('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        ))
        with patch.object(DocumentPlannerService, '_dependencies', side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaises(RuntimeError):
                self.pexecute(request)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), before_sequence)
            self.assertFalse(any(e.kind in ('DocumentPlan', 'Section') for e in tx.heads()))
            command_id = request['meta']['command_id']
            self.assertFalse(any(str(e.audit.command_id) == command_id for e in tx.events()))

    def test_approved_plan_can_be_superseded_without_content_rewrite(self):
        fact, _, evidence, filing, claim, objective, snapshot, _ = self.planning_case()
        plan = self.papply('PlanDocument', self.plan_data(
            fact, evidence, filing, claim, objective, snapshot
        )).refs[0]
        reviewed = self.papply('ReviewDocumentPlan', target=plan).refs[0]
        decision = self.decision('PLAN_APPROVAL', [reviewed])
        approved = self.papply('ApproveDocumentPlan', {
            'decision': decision.model_dump(mode='json')
        }, reviewed).refs[0]
        approved_entity = self.get(approved)
        superseded = self.papply('SupersedeDocumentPlan', target=approved).refs[0]
        superseded_entity = self.get(superseded)
        left = approved_entity.model_dump(exclude={'status', 'revision', 'previous_hash', 'recorded_at', 'provenance'})
        right = superseded_entity.model_dump(exclude={'status', 'revision', 'previous_hash', 'recorded_at', 'provenance'})
        self.assertEqual(left, right)
        self.assertEqual(superseded_entity.status, 'SUPERSEDED')
