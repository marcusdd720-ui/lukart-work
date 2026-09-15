"""Real PostgreSQL tests. Skips are explicit when no isolated database is configured."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import base64
import json
import os
from pathlib import Path
import threading
import unittest
from typing import get_args
from uuid import uuid4, uuid5

from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.requests import Operation
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor, Ref
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.validation.rules import digest, ref

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local-stage02/connection.json'
CONFIG = json.loads(LOCAL.read_text(encoding='utf-8-sig')) if LOCAL.exists() else {}
DSN = os.environ.get('LUKART_TEST_DSN') or CONFIG.get('runtime_dsn')
ADMIN = os.environ.get('LUKART_TEST_ADMIN_DSN') or CONFIG.get('admin_dsn')
PIN = {'id': 'synthetic', 'version': '1.0.0', 'content_hash': 'a' * 64}
READS = {'GetRevision', 'GetCaseHead', 'GetSnapshot', 'GetProvenance', 'GetAffectedDrafts', 'GetSource'}
ACTIONS = frozenset(get_args(Operation)) | READS


class ParsingTests(unittest.TestCase):
    def test_public_append_revision_is_not_an_intent(self):
        from lukart_work.core.requests import parse_request
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            parse_request(json.dumps({'contract': 'urn:lukart:work:CoreRequest:1.0.0', 'operation': 'AppendRevision',
                'meta': {'command_id': str(uuid4()), 'tenant_id': str(uuid4()), 'case_id': str(uuid4()),
                         'idempotency_key': str(uuid4()), 'expected_case_sequence': 0, 'correlation_id': str(uuid4())}}))


@unittest.skipUnless(DSN, 'PostgreSQL integration NOT EXECUTED: configure LUKART_TEST_DSN or local cluster')
class Stage02Tests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case_id = uuid4(), uuid4()
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        self.principal = Principal(self.actor, self.tenant, self.case_id, ACTIONS)
        self.token = self.authority.provision(self.principal)
        self.repo = PostgresRepository(DSN)
        self.service = CommandService(self.repo, self.authority)
        self.sequence = 0
        self.create_case()

    def request(self, operation, data=None, target=None, **extra):
        return dict(contract='urn:lukart:work:CoreRequest:1.0.0', operation=operation,
                    meta=dict(command_id=str(uuid4()), tenant_id=str(self.tenant), case_id=str(self.case_id),
                              idempotency_key=str(uuid4()), expected_case_sequence=self.sequence, correlation_id=str(uuid4())),
                    target=target.model_dump(mode='json') if target else None, data=data or {}, **extra)

    def run_request(self, request, *, service=None, token=None):
        return (service or self.service).execute(json.dumps(request), token or self.token)

    def apply(self, operation, data=None, target=None, **extra):
        request = self.request(operation, data, target, **extra)
        result = self.run_request(request)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result, request

    def query(self, operation, target=None, object_id=None, token=None):
        return self.service.query(json.dumps(dict(contract='urn:lukart:work:CoreQuery:1.0.0', operation=operation,
                tenant_id=str(self.tenant), case_id=str(self.case_id), target=target.model_dump(mode='json') if target else None,
                object_id=str(object_id) if object_id else None)), token or self.token)

    def get(self, target):
        value = self.query('GetRevision', target)
        self.assertNotIsInstance(value, DomainError, value)
        return value.entity

    def create_case(self):
        result, _ = self.apply('CreateCase', {'title': 'Synthetic Stage 02 case', 'jurisdiction': 'PL', 'retention_policy': PIN})
        self.case_ref = result.refs[0]

    def party(self):
        result, _ = self.apply('AddParty', {'party_type': 'PERSON', 'display_name': 'Synthetic Person', 'identity_evidence': []})
        return result.refs[0]

    def decision(self, kind, targets, **extras):
        result, _ = self.apply('RecordDecision', dict(decision_type=kind, targets=[r.model_dump(mode='json') for r in targets],
                            outcome='ACCEPT', rationale='Synthetic human decision', **extras))
        return result.refs[0]

    def fact(self):
        party = self.party()
        content = b'Synthetic payment receipt.'
        _, request = self.apply('RegisterSource', dict(content_base64=base64.b64encode(content).decode(), media_type='text/plain', retention_policy=PIN))
        source_id = uuid5(__import__('uuid').UUID(request['meta']['command_id']), 'source')
        anchor = dict(document_id=str(source_id), document_hash=sha256(content).hexdigest(),
                      locator=dict(unit='RECORD', value='1', fragment_hash=sha256(content).hexdigest()))
        result, _ = self.apply('AddEvidence', dict(evidence_type='DOCUMENT', description='Synthetic receipt', source=anchor, authenticity='UNKNOWN'))
        evidence = result.refs[0]
        result, _ = self.apply('AddFact', dict(statement='A payment is asserted', support='SOURCE_BACKED', evidence=[evidence.model_dump(mode='json')],
                         subjects=[party.model_dump(mode='json')], key_fact=True), anchors=[anchor])
        return result.refs[0], party, evidence, source_id

    def snapshot(self):
        result, request = self.apply('CreateSnapshot', dict(rule_set=PIN, policy=PIN, knowledge_pins=[]))
        snapshot_id = uuid5(__import__('uuid').UUID(request['meta']['command_id']), 'snapshot')
        value = self.query('GetSnapshot', object_id=snapshot_id)
        return value.snapshot

    def accept(self, snapshot):
        decision = self.decision('SNAPSHOT_ACCEPTANCE', [self.case_ref], snapshot_target=dict(
            tenant_id=str(self.tenant), case_id=str(self.case_id), snapshot_id=str(snapshot.id), snapshot_hash=digest(snapshot)))
        self.apply('AcceptSnapshot', {'snapshot_id': str(snapshot.id), 'decision': decision.model_dump(mode='json')})
        return decision

    def assert_error(self, request, code, **kwargs):
        result = self.run_request(request, **kwargs)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, code)
        return result

    def approved_plan(self):
        fact, party, evidence, source_id = self.fact()
        identity = self.decision('IDENTITY', [party])
        party = self.apply('VerifyParty', {'decision': identity.model_dump(mode='json')}, party)[0].refs[0]
        fact = self.apply('ReviewFact', target=fact)[0].refs[0]
        acceptance = self.decision('FACT_ACCEPTANCE', [fact])
        fact = self.apply('ConfirmFact', {'decision': acceptance.model_dump(mode='json')}, fact)[0].refs[0]
        self.assertEqual(self.get(fact).status, 'CONFIRMED')
        filing = self.apply('AddFiling', dict(document_type=PIN, direction='OUTGOING', recipient=party.model_dump(mode='json'), authors=[party.model_dump(mode='json')]))[0].refs[0]
        issue = self.apply('AddIssue', dict(question='Synthetic issue', facts=[fact.model_dump(mode='json')], rules=[]))[0].refs[0]
        claim = self.apply('AddClaim', dict(claim_type='ASSERTION', statement='Synthetic assertion', claimant=party.model_dump(mode='json'), issues=[issue.model_dump(mode='json')],
                         facts=[fact.model_dump(mode='json')], rules=[], support='SOURCE_BACKED'))[0].refs[0]
        request = self.apply('AddRequest', dict(filing=filing.model_dump(mode='json'), request_type='DISMISSAL', text='Synthetic request',
                         claims=[claim.model_dump(mode='json')], evidence=[evidence.model_dump(mode='json')]))[0].refs[0]
        section = self.apply('AddSection', dict(filing=filing.model_dump(mode='json'), section_type='facts', title='Facts', arguments=[],
                         contract=dict(allowed_inputs=[fact.model_dump(mode='json')], required_inputs=[fact.model_dump(mode='json')], allowed_claims=[], forbidden=['NEW_FACT'], requirements=[])))[0].refs[0]
        section = self.apply('PrepareSection', target=section)[0].refs[0]
        snapshot = self.snapshot()
        self.assertEqual(self.repo.get_snapshot(self.tenant, self.case_id, snapshot.id), snapshot)
        self.assertEqual(self.repo.get_revision(self.tenant, self.case_id, fact), self.get(fact))
        self.assertEqual(self.repo.get_heads(self.tenant, self.case_id)[0], self.sequence)
        snapshot_decision = self.accept(snapshot)
        plan = self.apply('AddPlan', dict(filing=filing.model_dump(mode='json'), objectives=[request.model_dump(mode='json')], recipient=party.model_dump(mode='json'),
                         argument_order=[], evidence=[evidence.model_dump(mode='json')], section_order=[section.model_dump(mode='json')],
                         position_scope='Synthetic scope', input_snapshot_id=str(snapshot.id), input_snapshot_hash=digest(snapshot)))[0].refs[0]
        plan = self.apply('ReviewPlan', target=plan)[0].refs[0]
        decision = self.decision('PLAN_APPROVAL', [plan])
        plan = self.apply('ApprovePlan', {'decision': decision.model_dump(mode='json')}, plan)[0].refs[0]
        return fact, party, source_id, plan, snapshot_decision

    def test_full_core_golden_all_guards_and_plan_approval(self):
        fact, party, source_id, plan, _ = self.approved_plan()
        self.assertEqual(self.get(plan).status, 'APPROVED')
        self.assertEqual(self.query('GetSource', object_id=source_id), b'Synthetic payment receipt.')
        self.assertEqual(self.query('GetProvenance', fact).completeness, 'COMPLETE')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(len(tx.events()), self.sequence)
            self.assertEqual(tx.events(), tx.outbox())
        self.assert_error(self.request('RequestRelease'), 'GATE_DENIED')
        self.apply('DisputeFact', target=fact)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            events = tx.events()
            self.assertEqual(events[-1].event_type, 'DependenciesInvalidated')
            self.assertIn(plan, events[-1].subjects)
            self.assertEqual(events[-2].audit.sequence, events[-1].audit.sequence)
            self.assertEqual(tx.outbox(), events)
        self.assertEqual(self.get(plan).status, 'APPROVED')  # historical content is unchanged

    def test_replay_after_restart_and_conflicting_body(self):
        import subprocess
        import sys
        result, request = self.apply('AddParty', dict(party_type='PERSON', display_name='Original', identity_evidence=[]))
        restarted_auth = TokenAuthority()
        token = restarted_auth.provision(self.principal)
        restarted = CommandService(PostgresRepository(DSN), restarted_auth)
        self.assertEqual(restarted.execute(json.dumps(request), token), result)
        process = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'tests.stage02_restart_probe'],
            input=json.dumps({'request': request, 'actor': self.actor.model_dump(mode='json')}),
            capture_output=True, text=True, cwd=ROOT, timeout=30, check=True)
        self.assertEqual(CommandResult.model_validate_json(process.stdout), result)
        request['data']['display_name'] = 'Changed'
        self.assert_error(request, 'IDEMPOTENCY_CONFLICT')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(len(tx.events()), 2)

    def test_revoked_token_cannot_replay(self):
        result, request = self.apply('AddParty', dict(party_type='PERSON', display_name='Original', identity_evidence=[]))
        self.authority.revoke(self.token)
        self.assert_error(request, 'FORBIDDEN')

    def test_untrusted_actor_and_metadata_rejected(self):
        for extra in ({'id': str(uuid4())}, {'status': 'VERIFIED'}, {'provenance': {'actor': {'kind': 'HUMAN'}}}, {'revision': 99}):
            with self.subTest(extra=extra):
                self.assert_error(self.request('AddParty', dict(party_type='PERSON', display_name='Original', identity_evidence=[], **extra)), 'SCHEMA_INVALID')

    def test_scope_authorization_for_writes_and_reads(self):
        other = self.authority.provision(Principal(self.actor, uuid4(), uuid4(), ACTIONS))
        self.assert_error(self.request('EditCase', {'title': 'Foreign'}, self.case_ref), 'FORBIDDEN', token=other)
        self.assertEqual(self.query('GetRevision', self.case_ref, token=other).code, 'FORBIDDEN')

    def test_rbac_explicit_action_grants(self):
        reader = self.authority.provision(Principal(self.actor, self.tenant, self.case_id, frozenset(READS)))
        self.assertEqual(self.query('GetRevision', self.case_ref, token=reader).entity.title, 'Synthetic Stage 02 case')
        self.assert_error(self.request('CloseCase', target=self.case_ref), 'FORBIDDEN', token=reader)

    def test_two_real_connections_same_sequence_one_commit(self):
        barrier = threading.Barrier(2)
        requests = [self.request('AddParty', dict(party_type='PERSON', display_name=str(i), identity_evidence=[])) for i in range(2)]
        def worker(request):
            authority = TokenAuthority()
            token = authority.provision(self.principal)
            service = CommandService(PostgresRepository(DSN), authority)
            barrier.wait(timeout=10)
            return service.execute(json.dumps(request), token)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, requests))
        self.assertEqual(sum(isinstance(r, CommandResult) for r in results), 1)
        self.assertEqual([r.code for r in results if isinstance(r, DomainError)], ['CONFLICT'])
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), 2)
            self.assertEqual(len(tx.events()), 2)

    def test_database_failure_rolls_back_entire_unit_of_work(self):
        repo = self.repo
        class FaultRepository:
            @contextmanager
            def transaction(self, tenant, case):
                with repo.transaction(tenant, case) as tx:
                    original = tx.finish
                    def failing(*args):
                        original(*args)
                        # Database FK failure at outbox write, after all successful writes.
                        tx.connection.execute('INSERT INTO lw_core.outbox VALUES (%s,%s,%s)', (tenant, case, uuid4()))
                    tx.finish = failing
                    yield tx
        service = CommandService(FaultRepository(), self.authority)
        request = self.request('AddParty', dict(party_type='PERSON', display_name='Must roll back', identity_evidence=[]))
        self.assert_error(request, 'UNKNOWN', service=service)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), 1)
            self.assertEqual(len(tx.records()), 1)
            self.assertEqual(len(tx.heads()), 1)
            self.assertEqual(len(tx.events()), 1)
            self.assertEqual(len(tx.outbox()), 1)
        self.assertIsInstance(self.run_request(request), CommandResult)

    def test_rls_read_write_and_no_scope_deny(self):
        import psycopg
        with psycopg.connect(DSN) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM lw_core.revisions').fetchone()[0], 0)
        with self.repo.transaction(uuid4(), uuid4()) as tx:
            self.assertEqual(tx.connection.execute('SELECT count(*) FROM lw_core.revisions').fetchone()[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                tx.connection.execute('INSERT INTO lw_core.cases VALUES (%s,%s,1)', (self.tenant, uuid4()))

    def test_append_only_runtime_cannot_modify_revision(self):
        import psycopg
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                tx.connection.execute("UPDATE lw_core.revisions SET payload='{}'")

    def test_verified_party_cannot_be_edited_in_place(self):
        party = self.party()
        decision = self.decision('IDENTITY', [party])
        party = self.apply('VerifyParty', {'decision': decision.model_dump(mode='json')}, party)[0].refs[0]
        self.assert_error(self.request('EditParty', {'display_name': 'Substitution'}, party), 'GATE_DENIED')

    def test_revoked_decision_rejected_for_verification(self):
        party = self.party()
        decision = self.decision('IDENTITY', [party])
        self.apply('RevokeDecision', target=decision)
        self.assert_error(self.request('VerifyParty', {'decision': decision.model_dump(mode='json')}, party), 'GATE_DENIED')

    def test_historical_revisions_survive_and_stale_target_conflicts(self):
        party = self.party()
        newer = self.apply('EditParty', {'display_name': 'New name'}, party)[0].refs[0]
        self.assertEqual(self.get(party).display_name, 'Synthetic Person')
        self.assertEqual(self.get(newer).display_name, 'New name')
        self.assert_error(self.request('EditParty', {'display_name': 'Lost update'}, party), 'CONFLICT')

    def test_closed_and_archived_case_guards(self):
        closed = self.apply('CloseCase', target=self.case_ref)[0].refs[0]
        self.assert_error(self.request('AddParty', dict(party_type='PERSON', display_name='No', identity_evidence=[])), 'GATE_DENIED')
        opened = self.apply('ReopenCase', target=closed)[0].refs[0]
        closed = self.apply('CloseCase', target=opened)[0].refs[0]
        archived = self.apply('ArchiveCase', target=closed)[0].refs[0]
        self.assert_error(self.request('ReopenCase', target=archived), 'GATE_DENIED')

    def test_snapshot_current_heads_checked_before_acceptance(self):
        party = self.party()
        snapshot = self.snapshot()
        decision = self.decision('SNAPSHOT_ACCEPTANCE', [self.case_ref], snapshot_target=dict(
            tenant_id=str(self.tenant), case_id=str(self.case_id), snapshot_id=str(snapshot.id), snapshot_hash=digest(snapshot)))
        self.apply('EditParty', {'display_name': 'Changed after freeze'}, party)
        self.assert_error(self.request('AcceptSnapshot', {'snapshot_id': str(snapshot.id), 'decision': decision.model_dump(mode='json')}), 'STALE')

    def test_snapshot_hash_substitution_and_missing_acceptance(self):
        snapshot = self.snapshot()
        request = self.request('RecordDecision', dict(decision_type='SNAPSHOT_ACCEPTANCE', targets=[self.case_ref.model_dump(mode='json')],
            outcome='ACCEPT', rationale='False hash', snapshot_target=dict(tenant_id=str(self.tenant), case_id=str(self.case_id), snapshot_id=str(snapshot.id), snapshot_hash='0'*64)))
        self.assert_error(request, 'INVALID_HASH')
        self.assert_error(self.request('AcceptSnapshot', {'snapshot_id': str(snapshot.id), 'decision': self.case_ref.model_dump(mode='json')}), 'GATE_DENIED')

    def test_fact_cannot_confirm_without_correct_human_decision(self):
        fact, party, _, _ = self.fact()
        reviewed = self.apply('ReviewFact', target=fact)[0].refs[0]
        identity = self.decision('IDENTITY', [party])
        self.assert_error(self.request('ConfirmFact', {'decision': identity.model_dump(mode='json')}, reviewed), 'GATE_DENIED')

    def test_duplicate_json_unknown_contract_and_safe_errors(self):
        raw = json.dumps(self.request('EditCase', {'title': 'Private PII'}, self.case_ref))
        for payload in ('{"operation":"a","operation":"b"}', raw.replace('CoreRequest:1.0.0', 'CoreRequest:99.0.0'), '['*1000 + ']'*1000):
            result = self.service.execute(payload, self.token)
            self.assertEqual(result.code, 'SCHEMA_INVALID')
            self.assertNotIn('Private PII', result.model_dump_json())

    def test_source_cross_case_download_denied(self):
        _, _, _, source_id = self.fact()
        token = self.authority.provision(Principal(self.actor, self.tenant, uuid4(), ACTIONS))
        self.assertEqual(self.query('GetSource', object_id=source_id, token=token).code, 'FORBIDDEN')

    def test_unknown_source_and_type_guard_rollback(self):
        party = self.party()
        request = self.request('AddFact', dict(statement='Unsupported', support='SOURCE_BACKED', evidence=[party.model_dump(mode='json')], subjects=[], key_fact=True), inputs=[party.model_dump(mode='json')])
        self.assert_error(request, 'GATE_DENIED')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), self.sequence)

    def test_actor_is_server_assigned(self):
        party = self.party()
        value = self.get(party)
        self.assertEqual(value.provenance.actor, self.actor)
        self.assertEqual(value.recorded_at.utcoffset().total_seconds(), 0)

    def test_release_validation_and_generation_fail_closed(self):
        for operation in ('GenerateDocument', 'ValidateDraft', 'RequestRelease'):
            self.assert_error(self.request(operation), 'GATE_DENIED')

    def test_fact_transition_preserves_provenance(self):
        fact, _, _, _ = self.fact()
        before = self.get(fact)
        reviewed = self.apply('ReviewFact', target=fact)[0].refs[0]
        after = self.get(reviewed)
        self.assertEqual(after.provenance.anchors, before.provenance.anchors)
        self.assertEqual(after.provenance.inputs, before.provenance.inputs)
        self.assertNotEqual(after.provenance.operation_id, before.provenance.operation_id)

    def test_revoking_superseding_decision_does_not_resurrect_old(self):
        party = self.party()
        first = self.decision('IDENTITY', [party])
        second = self.decision('IDENTITY', [party], supersedes=first.model_dump(mode='json'))
        self.apply('RevokeDecision', target=second)
        self.assert_error(self.request('VerifyParty', {'decision': first.model_dump(mode='json')}, party), 'GATE_DENIED')

    def test_unknown_stored_contract_preserves_payload_and_denies_read(self):
        from lukart_work.core.postgres import canonical
        from lukart_work.contracts.messages import SourceDocument
        from datetime import datetime, timezone
        from lukart_work.domain.models import VersionPin
        source_id = uuid4()
        source = SourceDocument(id=source_id, tenant_id=self.tenant, case_id=self.case_id, content_hash=sha256(b'x').hexdigest(),
            media_type='text/plain', byte_length=1, object_key='historical', received_at=datetime.now(timezone.utc), actor=self.actor,
            retention_policy=VersionPin.model_validate_json(json.dumps(PIN)))
        raw = canonical(source)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            tx.connection.execute('INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (self.tenant, self.case_id, 'source', source_id, 'urn:lukart:work:SourceDocument:99.0.0', raw, sha256(raw.encode()).hexdigest(), b'x'))
        self.assertEqual(self.query('GetSource', object_id=source_id).code, 'UNKNOWN')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.connection.execute('SELECT payload FROM lw_core.objects WHERE object_id=%s', (source_id,)).fetchone()[0], raw)

    def test_corrupt_source_bytes_fail_closed(self):
        from lukart_work.core.postgres import canonical, urn
        from lukart_work.contracts.messages import SourceDocument
        from datetime import datetime, timezone
        from lukart_work.domain.models import VersionPin
        source_id = uuid4()
        source = SourceDocument(id=source_id, tenant_id=self.tenant, case_id=self.case_id, content_hash=sha256(b'original').hexdigest(),
            media_type='text/plain', byte_length=8, object_key='historical', received_at=datetime.now(timezone.utc), actor=self.actor,
            retention_policy=VersionPin.model_validate_json(json.dumps(PIN)))
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            tx.connection.execute('INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (self.tenant, self.case_id, 'source', source_id, urn(SourceDocument), canonical(source), digest(source), b'changed!'))
        self.assertEqual(self.query('GetSource', object_id=source_id).code, 'PROVENANCE_MISSING')

    def test_machine_cannot_record_human_decision(self):
        party = self.party()
        machine = self.authority.provision(Principal(Actor(id=uuid4(), kind='SERVICE'), self.tenant, self.case_id, ACTIONS))
        request = self.request('RecordDecision', dict(decision_type='IDENTITY', targets=[party.model_dump(mode='json')], outcome='ACCEPT', rationale='Machine assertion'))
        self.assert_error(request, 'FORBIDDEN', token=machine)

    def test_review_r1_dispute_party_after_revocation_preserves_history(self):
        party = self.party()
        decision = self.decision('IDENTITY', [party])
        verified = self.apply('VerifyParty', {'decision': decision.model_dump(mode='json')}, party)[0].refs[0]
        original = self.get(verified)
        self.apply('RevokeDecision', target=decision)
        disputed = self.apply('DisputeParty', target=verified)[0].refs[0]
        self.assertEqual(self.get(disputed).status, 'DISPUTED')
        self.assertIsNone(self.get(disputed).verification_decision)
        self.assertEqual(self.get(verified), original)
        replacement = self.decision('IDENTITY', [disputed])
        renewed = self.apply('VerifyParty', {'decision': replacement.model_dump(mode='json')}, disputed)[0].refs[0]
        self.assertEqual(self.get(renewed).status, 'VERIFIED')

    def test_review_r1_dispute_fact_after_revocation_preserves_sources(self):
        fact, _, _, _ = self.fact()
        reviewed = self.apply('ReviewFact', target=fact)[0].refs[0]
        decision = self.decision('FACT_ACCEPTANCE', [reviewed])
        confirmed = self.apply('ConfirmFact', {'decision': decision.model_dump(mode='json')}, reviewed)[0].refs[0]
        original = self.get(confirmed)
        self.apply('RevokeDecision', target=decision)
        disputed = self.apply('DisputeFact', target=confirmed)[0].refs[0]
        self.assertEqual(self.get(disputed).status, 'DISPUTED')
        self.assertIsNone(self.get(disputed).acceptance)
        self.assertEqual(self.get(disputed).provenance.anchors, original.provenance.anchors)
        self.assertEqual(self.get(confirmed), original)

    def test_review_r1_snapshot_acceptance_revocation_invalidates_plan(self):
        _, _, _, plan, acceptance = self.approved_plan()
        self.apply('RevokeDecision', target=acceptance)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            events = tx.events()
            self.assertEqual(events[-1].event_type, 'DependenciesInvalidated')
            self.assertIn(plan, events[-1].subjects)
            self.assertEqual(events[-1].audit.sequence, self.sequence)
            self.assertEqual(tx.outbox(), events)
        self.assertEqual(self.get(plan).status, 'APPROVED')

    def test_review_r1_replay_rejects_unknown_contract_and_changed_bytes(self):
        from lukart_work.core.postgres import canonical, urn
        from lukart_work.core.requests import CoreRequest
        for contract, saved_hash, expected in (
            ('urn:lukart:work:CommandResult:99.0.0', None, 'UNKNOWN'),
            (urn(CommandResult), '0' * 64, 'INVALID_HASH'),
        ):
            with self.subTest(expected=expected):
                request = self.request('AddParty', dict(party_type='PERSON', display_name='Synthetic', identity_evidence=[]))
                parsed = CoreRequest.model_validate_json(json.dumps(request))
                input_hash = digest({'request': parsed.model_dump(mode='json'), 'actor': self.actor.model_dump(mode='json')})
                result = CommandResult(command_id=parsed.meta.command_id, state='APPLIED', case_sequence=self.sequence,
                                       refs=(), event_ids=(), errors=())
                raw = canonical(result)
                with self.repo.transaction(self.tenant, self.case_id) as tx:
                    tx.connection.execute('INSERT INTO lw_core.commands VALUES (%s,%s,%s,%s,%s,%s,%s)',
                        (self.tenant, self.case_id, parsed.meta.idempotency_key, input_hash, contract, raw, saved_hash or digest(result)))
                self.assert_error(request, expected)
                with self.repo.transaction(self.tenant, self.case_id) as tx:
                    self.assertEqual(tx.connection.execute('SELECT payload FROM lw_core.commands WHERE idempotency_key=%s', (parsed.meta.idempotency_key,)).fetchone()[0], raw)

    def test_review_r1_outbox_validates_event_contract_hash_and_chain(self):
        from lukart_work.core.postgres import canonical, urn
        from lukart_work.contracts.messages import DomainEvent
        from lukart_work.validation.rules import Violation
        for mode, expected in (('contract', 'UNKNOWN'), ('hash', 'INVALID_HASH'), ('chain', 'INVALID_HASH')):
            with self.subTest(mode=mode), self.repo.transaction(self.tenant, self.case_id) as tx:
                # Savepoint contains the deliberate corrupt synthetic row; no original is modified.
                tx.connection.execute('SAVEPOINT corrupt_event')
                template = tx.events()[-1].model_dump(mode='json')
                template['audit'].update(event_id=str(uuid4()), sequence=self.sequence + 1,
                                          previous_event_hash='0' * 64 if mode == 'chain' else tx.last_event_hash())
                event = DomainEvent.model_validate_json(json.dumps(template))
                raw = canonical(event)
                contract = 'urn:lukart:work:DomainEvent:99.0.0' if mode == 'contract' else urn(DomainEvent)
                saved_hash = '0' * 64 if mode == 'hash' else digest(event)
                tx.connection.execute('INSERT INTO lw_core.events (tenant_id,case_id,event_id,sequence,contract,payload,content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (self.tenant, self.case_id, event.audit.event_id, event.audit.sequence, contract, raw, saved_hash))
                tx.connection.execute('INSERT INTO lw_core.outbox VALUES (%s,%s,%s)', (self.tenant, self.case_id, event.audit.event_id))
                with self.assertRaises(Violation) as raised:
                    tx.outbox()
                self.assertEqual(raised.exception.code, expected)
                tx.connection.execute('ROLLBACK TO SAVEPOINT corrupt_event')

    def test_review_r1_audit_pin_covers_real_rule_artifact(self):
        from lukart_work.core.policy import policy_artifact, rule_pin, POLICY_FILES
        import tempfile
        root = ROOT / 'lukart_work'
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.events()[0].audit.rule_version, rule_pin())
        self.assertEqual(rule_pin().content_hash, digest(policy_artifact()))
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder)
            for name in POLICY_FILES:
                destination = changed / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root / name).read_bytes())
            self.assertEqual(rule_pin(changed), rule_pin())
            path = changed / 'validation/rules.py'
            path.write_bytes(path.read_bytes() + b'\n# synthetic policy change\n')
            self.assertNotEqual(rule_pin(changed).content_hash, rule_pin().content_hash)
