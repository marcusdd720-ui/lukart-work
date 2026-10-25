"""Real PostgreSQL acceptance for human candidate/fact/evidence workflows."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from typing import get_args
import unittest
import psycopg
from unittest.mock import patch
from uuid import uuid4
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.postgres import UnitOfWork
from lukart_work.domain.models import Actor
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.facts.contracts import FactOperation, FactEvidenceMatrix, CandidateReviewRecord
from lukart_work.facts.service import FactEvidenceService
from lukart_work.validation.rules import digest
from tests import test_stage02 as core
from tests import test_stage03 as storage
from tests import test_stage04 as ingestion


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 05 requires isolated PostgreSQL')
class FactEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage.Stage03Tests.setUpClass.__func__(cls)

    def setUp(self):
        ingestion.IngestionTests.setUp(self)
        self.authority.revoke(self.token)
        self.principal = Principal(self.actor, self.tenant, self.case_id,
            self.principal.actions | frozenset(get_args(FactOperation)) | {'GetFactEvidenceMatrix'})
        self.token = self.authority.provision(self.principal)
        self.facts = FactEvidenceService(self.repo, self.authority)

    def frequest(self, operation, data=None, target=None, **extra):
        request = self.request(operation, data, target, rationale='Synthetic explicit human review', **extra)
        request['contract'] = 'urn:lukart:work:FactEvidenceRequest:1.0.0'
        return request

    def fexecute(self, request, token=None, service=None):
        return (service or self.facts).execute(json.dumps(request), token or self.token)

    def fapply(self, operation, data=None, target=None):
        request = self.frequest(operation, data, target)
        result = self.fexecute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result, request

    def matrix(self, token=None, tenant=None, case=None):
        return self.facts.matrix(json.dumps(dict(contract='urn:lukart:work:FactEvidenceQuery:1.0.0',
            operation='GetFactEvidenceMatrix', tenant_id=str(tenant or self.tenant), case_id=str(case or self.case_id))), token or self.token)

    def candidate_data(self, result, kind='FACT', disposition='ADMIT', expected=0):
        index = next(i for i,c in enumerate(result.body.candidates) if c.kind == kind)
        data = dict(source_id=str(result.source_id), run_id=str(result.run_id), result_hash=digest(result),
            candidate_index=index, expected_review_revision=expected, disposition=disposition)
        if disposition == 'ADMIT':
            data['description'] = 'Synthetic source fragment reviewed by a human'
            if kind == 'FACT': data['statement'] = 'A payment is asserted in the source.'
        return data

    def admit(self, result=None, kind='FACT'):
        result = result or self.ingest()
        applied, request = self.fapply('ReviewCandidate', self.candidate_data(result, kind))
        return applied.refs, request, result

    def reviewed_fact(self):
        refs, _, extraction = self.admit()
        evidence, fact = refs
        evidence = self.fapply('ReviewEvidence', target=evidence)[0].refs[0]
        evidence = self.fapply('AcceptEvidence', target=evidence)[0].refs[0]
        fact = self.fapply('UpdateFact', {'evidence': [evidence.model_dump(mode='json')]}, fact)[0].refs[0]
        fact = self.fapply('ReviewFact', target=fact)[0].refs[0]
        return fact, evidence, extraction

    def confirmed(self):
        fact, evidence, extraction = self.reviewed_fact()
        decision = self.decision('FACT_ACCEPTANCE', [fact])
        fact = self.fapply('ConfirmFact', {'decision': decision.model_dump(mode='json')}, fact)[0].refs[0]
        return fact, evidence, extraction, decision

    def test_unread_pdf_page_denies_candidate_review_without_writes(self):
        from tests.test_ingestion_completeness import mixed_pdf
        source = self.source(mixed_pdf(), 'application/pdf')
        extraction = self.ingest(source)
        self.assertEqual(extraction.body.status, 'NEEDS_OCR')
        before = storage.raw_state(self.admin)
        request = self.frequest('ReviewCandidate', dict(source_id=str(source),
            run_id=str(extraction.run_id), result_hash=digest(extraction), candidate_index=0,
            expected_review_revision=0, disposition='ADMIT',
            description='Synthetic incomplete source', statement='Synthetic assertion'))
        result = self.fexecute(request)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'GATE_DENIED')
        self.assertEqual(storage.raw_state(self.admin), before)
        self.assertFalse(self.matrix().candidate_reviews)

    def test_golden_explicit_admission_and_confirmation_preserve_history(self):
        snapshot = self.snapshot()
        self.accept(snapshot)
        before = storage.raw_state(self.admin)
        fact, evidence, extraction, decision = self.confirmed()
        matrix = self.matrix()
        self.assertIsInstance(matrix, FactEvidenceMatrix)
        self.assertEqual(matrix.facts[0].status, 'CONFIRMED')
        self.assertTrue(matrix.facts[0].confirmation_current)
        self.assertTrue(matrix.facts[0].acceptance_live)
        self.assertEqual(matrix.evidence[0].authenticity, 'UNKNOWN')
        self.assertEqual(matrix.candidate_reviews[0].disposition, 'ADMIT')
        self.assertEqual(self.get(matrix.candidate_reviews[0].created[1]).status, 'CANDIDATE')
        self.assertEqual(self.ingestion.read(self.token, extraction.source_id, extraction.run_id), extraction)
        after = storage.raw_state(self.admin)
        for table in ('lw_core.revisions', 'lw_core.objects', 'lw_core.events', 'lw_core.commands'):
            self.assertTrue(all(row in after[table] for row in before[table]))
        new_snapshot = self.snapshot()
        self.accept(new_snapshot)

    def test_rejection_reconsideration_and_no_duplicate_admission(self):
        extraction = self.ingest()
        result, request = self.fapply('ReviewCandidate', self.candidate_data(extraction, disposition='REJECT'))
        self.assertFalse(result.refs)
        self.assertFalse(self.matrix().facts)
        admitted, _ = self.fapply('ReviewCandidate', self.candidate_data(extraction, expected=1))
        reviews = self.matrix().candidate_reviews
        self.assertEqual([r.disposition for r in reviews], ['REJECT', 'ADMIT'])
        self.assertEqual(reviews[1].previous_hash, digest(reviews[0]))
        repeat = self.frequest('ReviewCandidate', self.candidate_data(extraction, expected=2))
        self.assertEqual(self.fexecute(repeat).code, 'GATE_DENIED')
        self.assertEqual(self.fexecute(request), result)  # historical receipt replay is not a new decision

    def test_wrong_pin_index_kind_scope_and_missing_source_fail_closed(self):
        extraction = self.ingest()
        data = self.candidate_data(extraction)
        changes = [dict(result_hash='0'*64), dict(candidate_index=9999),
            dict(source_id=str(uuid4())), dict(run_id=str(uuid4())),
            dict(candidate_index=next(i for i,c in enumerate(extraction.body.candidates) if c.kind == 'DATE'))]
        for change in changes:
            self.assertIsInstance(self.fexecute(self.frequest('ReviewCandidate', dict(data, **change))), DomainError)
        self.storage.delete(self.token, extraction.source_id)
        self.assertIsInstance(self.fexecute(self.frequest('ReviewCandidate', data)), DomainError)
        self.assertFalse(self.matrix().facts)

    def test_no_implicit_approval_and_forbidden_status_injection(self):
        refs, _, _ = self.admit()
        self.assertEqual(self.get(refs[0]).status, 'REGISTERED')
        self.assertEqual(self.get(refs[1]).status, 'CANDIDATE')
        self.assertFalse(self.matrix().facts[0].confirmation_current)
        for op, target, data in [('ConfirmFact', refs[1], {'decision': refs[0].model_dump(mode='json')}),
            ('AcceptEvidence', refs[0], {}), ('UpdateEvidence', refs[0], {'source': {}}),
            ('UpdateFact', refs[1], {'status': 'CONFIRMED'})]:
            self.assertIsInstance(self.fexecute(self.frequest(op, data, target)), DomainError)

    def test_fact_lifecycle_rejection_and_evidence_exclusion(self):
        refs, _, _ = self.admit()
        evidence, fact = refs
        fact = self.fapply('MarkFactExtracted', target=fact)[0].refs[0]
        fact = self.fapply('ReviewFact', target=fact)[0].refs[0]
        fact = self.fapply('DisputeFact', target=fact)[0].refs[0]
        fact = self.fapply('ReviewFact', target=fact)[0].refs[0]
        fact = self.fapply('RejectFact', target=fact)[0].refs[0]
        self.assertEqual(self.get(fact).status, 'REJECTED')
        self.assertIsInstance(self.fexecute(self.frequest('ReviewFact', target=fact)), DomainError)
        self.assertIsInstance(self.fexecute(self.frequest('UpdateFact', {'statement': 'no'}, fact)), DomainError)
        evidence = self.fapply('ExcludeEvidence', target=evidence)[0].refs[0]
        self.assertEqual(self.get(evidence).status, 'EXCLUDED')
        self.assertIsInstance(self.fexecute(self.frequest('ReviewEvidence', target=evidence)), DomainError)

    def test_evidence_challenge_invalidates_current_confirmation_without_rewriting(self):
        fact, evidence, extraction, decision = self.confirmed()
        original = self.get(fact)
        changed = self.fapply('ChallengeEvidence', target=evidence)[0]
        row = self.matrix().facts[0]
        self.assertFalse(row.confirmation_current)
        self.assertIn('STALE_EVIDENCE', row.issues)
        self.assertIn('EVIDENCE_NOT_ACCEPTED', row.issues)
        self.assertEqual(self.get(fact), original)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertTrue(any(e.event_type == 'DependenciesInvalidated' and fact in e.subjects for e in tx.events()))
        self.fapply('ExcludeEvidence', target=changed.refs[0])

    def test_revoked_and_wrong_decision_changed_content_fail_closed(self):
        fact, evidence, extraction, decision = self.confirmed()
        self.apply('RevokeDecision', target=decision)
        self.assertFalse(self.matrix().facts[0].acceptance_live)
        self.assertFalse(self.matrix().facts[0].confirmation_current)
        self.assertEqual(self.get(fact).status, 'CONFIRMED')
        disputed = self.fapply('DisputeFact', target=fact)[0].refs[0]
        reviewed = self.fapply('ReviewFact', target=disputed)[0].refs[0]
        new_decision = self.decision('FACT_ACCEPTANCE', [reviewed])
        modified = self.fapply('UpdateFact', {'statement': 'Human corrected statement'}, reviewed)[0].refs[0]
        self.assertIsInstance(self.fexecute(self.frequest('ConfirmFact', {'decision': new_decision.model_dump(mode='json')}, modified)), DomainError)

    def test_stale_evidence_requires_explicit_relink_before_confirmation(self):
        refs, _, _ = self.admit()
        evidence, fact = refs
        reviewed = self.fapply('ReviewFact', target=fact)[0].refs[0]
        decision = self.decision('FACT_ACCEPTANCE', [reviewed])
        self.assertEqual(self.fexecute(self.frequest('ConfirmFact', {'decision': decision.model_dump(mode='json')}, reviewed)).code, 'GATE_DENIED')
        evidence = self.fapply('ReviewEvidence', target=evidence)[0].refs[0]
        evidence = self.fapply('AcceptEvidence', target=evidence)[0].refs[0]
        self.assertEqual(self.fexecute(self.frequest('ConfirmFact', {'decision': decision.model_dump(mode='json')}, reviewed)).code, 'GATE_DENIED')

    def test_disputed_authenticity_and_accepted_content_lock(self):
        refs, _, _ = self.admit(kind='EVIDENCE')
        evidence = self.fapply('ReviewEvidence', target=refs[0])[0].refs[0]
        evidence = self.fapply('UpdateEvidence', {'authenticity':'DISPUTED'}, evidence)[0].refs[0]
        self.assertEqual(self.fexecute(self.frequest('AcceptEvidence', target=evidence)).code, 'GATE_DENIED')
        evidence = self.fapply('UpdateEvidence', {'authenticity':'UNKNOWN'}, evidence)[0].refs[0]
        evidence = self.fapply('AcceptEvidence', target=evidence)[0].refs[0]
        self.assertIsInstance(self.fexecute(self.frequest('UpdateEvidence', {'description':'changed'}, evidence)), DomainError)

    def test_deleted_extraction_and_original_mark_projection_unavailable(self):
        fact, evidence, extraction, _ = self.confirmed()
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            target = self.ingestion._target(tx, extraction.run_id)
        self.storage.delete(self.token, target)
        matrix = self.matrix()
        self.assertFalse(matrix.facts[0].confirmation_current)
        self.assertIn('PROVENANCE_UNAVAILABLE', matrix.facts[0].issues)
        self.assertTrue(matrix.evidence[0].source_available)
        self.assertFalse(matrix.evidence[0].provenance_available)
        self.assertIn('EXTRACTION_UNAVAILABLE', matrix.evidence[0].issues)
        self.storage.delete(self.token, extraction.source_id)
        self.assertFalse(self.matrix().evidence[0].source_available)

    def test_receipt_and_dependency_sql_rls_and_runtime_immutability(self):
        self.admit()
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(len(tx.objects('candidate_review', CandidateReviewRecord)), 1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                tx.connection.execute("UPDATE lw_core.objects SET content_hash='forged' WHERE category='candidate_review'")
        with self.repo.transaction(self.tenant, uuid4()) as tx:
            self.assertEqual(tx.connection.execute("SELECT object_id FROM lw_core.objects WHERE category IN ('candidate_review','dependency')").fetchall(), [])

    def test_authorization_scope_service_ai_and_revocation(self):
        extraction = self.ingest()
        request = self.frequest('ReviewCandidate', self.candidate_data(extraction))
        for principal in [Principal(self.actor, uuid4(), self.case_id, self.principal.actions),
            Principal(self.actor, self.tenant, uuid4(), self.principal.actions),
            Principal(self.actor, self.tenant, self.case_id, frozenset()),
            *[Principal(Actor(id=uuid4(), kind=k), self.tenant, self.case_id, self.principal.actions) for k in ('AI','SERVICE')]]:
            token = self.authority.provision(principal)
            self.assertEqual(self.fexecute(request, token).code, 'FORBIDDEN')
        self.assertIsInstance(self.matrix(tenant=uuid4()), DomainError)
        self.authority.revoke(self.token)
        self.assertEqual(self.fexecute(request).code, 'FORBIDDEN')

    def test_cas_concurrency_and_exact_actor_bound_replay(self):
        extraction = self.ingest()
        first = self.frequest('ReviewCandidate', self.candidate_data(extraction))
        second = self.frequest('ReviewCandidate', self.candidate_data(extraction))
        def send(request):
            authority = TokenAuthority()
            token = authority.provision(self.principal)
            return self.fexecute(request, token, FactEvidenceService(self.repo, authority))
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(send, [first, second]))
        self.assertEqual(sum(isinstance(r, CommandResult) for r in results), 1)
        self.assertEqual(sum(isinstance(r, DomainError) and r.code == 'CONFLICT' for r in results), 1)
        index = next(i for i,r in enumerate(results) if isinstance(r, CommandResult))
        request, result = [first,second][index], results[index]
        self.assertEqual(self.fexecute(request), result)
        other = self.authority.provision(Principal(Actor(id=uuid4(), kind='HUMAN'), self.tenant, self.case_id, self.principal.actions))
        self.assertEqual(self.fexecute(request, other).code, 'IDEMPOTENCY_CONFLICT')

    def test_atomic_failure_rolls_back_entities_receipt_sequence_audit_outbox(self):
        extraction = self.ingest()
        before = storage.raw_state(self.admin)
        original = UnitOfWork.finish
        def fail_after_finish(tx, *args):
            original(tx, *args)
            raise RuntimeError('Synthetic rollback')
        with patch.object(UnitOfWork, 'finish', fail_after_finish), self.assertRaises(RuntimeError):
            self.fexecute(self.frequest('ReviewCandidate', self.candidate_data(extraction)))
        self.assertEqual(storage.raw_state(self.admin), before)

    def test_matrix_used_in_and_closed_case_read_only(self):
        fact, evidence, extraction, _ = self.confirmed()
        # A decision explicitly targets the historical reviewed fact; projection lists its use.
        self.assertTrue(any(r.kind == 'Decision' for r in self.matrix().facts[0].used_in))
        self.apply('CloseCase', target=self.case_ref)
        self.assertIsInstance(self.matrix(), FactEvidenceMatrix)
        self.assertEqual(self.fexecute(self.frequest('DisputeFact', target=fact)).code, 'GATE_DENIED')

    def test_forged_envelope_and_legacy_contract_are_rejected(self):
        refs, _, _ = self.admit()
        for update in [dict(contract='urn:lukart:work:CoreRequest:1.0.0'), dict(rationale=' '),
                       dict(data={'approval':True}), dict(inputs=[refs[0].model_dump(mode='json')])]:
            request = self.frequest('ReviewFact', target=refs[1])
            request.update(update)
            self.assertEqual(self.fexecute(request).code, 'SCHEMA_INVALID')

    def test_restart_preserves_matrix_and_receipt(self):
        self.confirmed()
        matrix = self.matrix()
        env = dict(os.environ, LW_RESTART_DSN=self.dsn, LW_RESTART_TENANT=str(self.tenant),
            LW_RESTART_CASE=str(self.case_id), LW_RESTART_ACTOR=str(self.actor.id))
        code = "import os,json; from uuid import UUID; from lukart_work.core.postgres import PostgresRepository; from lukart_work.core.security import TokenAuthority,Principal; from lukart_work.domain.models import Actor; from lukart_work.facts.service import FactEvidenceService; a=TokenAuthority(); p=Principal(Actor(id=UUID(os.environ['LW_RESTART_ACTOR']),kind='HUMAN'),UUID(os.environ['LW_RESTART_TENANT']),UUID(os.environ['LW_RESTART_CASE']),frozenset(['GetFactEvidenceMatrix'])); q=dict(contract='urn:lukart:work:FactEvidenceQuery:1.0.0',operation='GetFactEvidenceMatrix',tenant_id=str(p.tenant_id),case_id=str(p.case_id)); r=FactEvidenceService(PostgresRepository(os.environ['LW_RESTART_DSN'],storage=True),a).matrix(json.dumps(q),a.provision(p)); print(r.model_dump_json())"
        result = subprocess.run([sys.executable,'-B','-c',code],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,'restart failure; raw output suppressed')
        self.assertEqual(FactEvidenceMatrix.model_validate_json(result.stdout),matrix)


for _name in ('request','run_request','apply','query','get','create_case','party','decision','fact','snapshot','accept'):
    setattr(FactEvidenceTests,_name,getattr(core.Stage02Tests,_name))
for _name in ('source','ingest'):
    setattr(FactEvidenceTests,_name,getattr(ingestion.IngestionTests,_name))
