"""Stage 06 Document Registry acceptance on real PostgreSQL with synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from pathlib import Path
import unittest
from typing import get_args
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5

import psycopg

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.postgres import PostgresRepository, UnitOfWork
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.registry.contracts import RegistryOperation, RegistryProjection, RegistryReceipt
from lukart_work.registry.service import DocumentRegistryService
from lukart_work.validation.rules import digest
from tests import test_stage02 as core


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 06 requires isolated PostgreSQL')
class DocumentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case_id = uuid4(), uuid4()
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        actions = core.ACTIONS | frozenset(get_args(RegistryOperation)) | {'GetDocumentRegistry'}
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.repo = PostgresRepository(core.DSN)
        self.service = CommandService(self.repo, self.authority)
        self.registry_service = DocumentRegistryService(self.repo, self.authority)
        self.sequence = 0
        self.apply('CreateCase', {'title': 'Synthetic Stage 06 case', 'jurisdiction': 'PL', 'retention_policy': core.PIN})

    def request(self, operation, data=None, target=None, *, contract='urn:lukart:work:CoreRequest:1.0.0'):
        return dict(
            contract=contract,
            operation=operation,
            meta=dict(
                command_id=str(uuid4()),
                tenant_id=str(self.tenant),
                case_id=str(self.case_id),
                idempotency_key=str(uuid4()),
                expected_case_sequence=self.sequence,
                correlation_id=str(uuid4()),
            ),
            target=target.model_dump(mode='json') if target else None,
            data=data or {},
        )

    def apply(self, operation, data=None, target=None):
        result = self.service.execute(json.dumps(self.request(operation, data, target)), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result

    def rrequest(self, operation, data=None, target=None):
        request = self.request(operation, data, target, contract='urn:lukart:work:RegistryRequest:1.0.0')
        request['rationale'] = 'Synthetic Stage 06 registry operation'
        return request

    def rexecute(self, request, token=None):
        return self.registry_service.execute(json.dumps(request), token or self.token)

    def rapply(self, operation, data=None, target=None):
        request = self.rrequest(operation, data, target)
        result = self.rexecute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result

    def projection(self, token=None, filing_id=None):
        query = dict(
            contract='urn:lukart:work:RegistryQuery:1.0.0',
            operation='GetDocumentRegistry',
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            filing_id=str(filing_id) if filing_id else None,
        )
        return self.registry_service.registry(json.dumps(query), token or self.token)

    def source(self, content):
        request = self.request('RegisterSource', dict(
            content_base64=base64.b64encode(content).decode(),
            media_type='application/octet-stream',
            retention_policy=core.PIN,
        ))
        result = self.service.execute(json.dumps(request), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return uuid5(UUID(request['meta']['command_id']), 'source')

    def principals(self):
        author = self.apply('AddParty', {
            'party_type': 'PERSON', 'display_name': 'Synthetic Stage 06 Author', 'identity_evidence': [],
        }).refs[0]
        recipient = self.apply('AddInstitution', {
            'institution_type': 'AUTHORITY', 'name': 'Synthetic Registry Authority', 'jurisdiction': 'PL',
        }).refs[0]
        return author, recipient

    def register(self, content=b'SYNTHETIC-FILING-BYTES', direction='OUTGOING', source_id=None):
        author, recipient = self.principals()
        source_id = source_id or self.source(content)
        result = self.rapply('RegisterFiling', {
            'source_id': str(source_id), 'document_type': core.PIN, 'direction': direction,
            'recipient': recipient.model_dump(mode='json'), 'authors': [author.model_dump(mode='json')],
        })
        return result.refs[0], source_id, author, recipient

    def make_ready(self, content=b'SYNTHETIC-FILING-BYTES'):
        filing, artifact, author, recipient = self.register(content=content)
        filing = self.rapply('PrepareFiling', target=filing).refs[0]
        filing = self.rapply('MarkFilingReady', target=filing).refs[0]
        return filing, artifact, author, recipient

    def test_golden_registry_submission_acknowledgement_withdrawal_and_history(self):
        fixture = json.loads((Path(__file__).parent / 'golden_cases/document_registry.json').read_text())
        filing, artifact, _, _ = self.make_ready()
        submission = self.source(fixture['submission_receipt_text'].encode())
        filing = self.rapply('RecordSubmission', {'receipt_source_id': str(submission)}, filing).refs[0]
        acknowledgement = self.source(fixture['acknowledgement_receipt_text'].encode())
        filing = self.rapply('RecordAcknowledgement', {'receipt_source_id': str(acknowledgement)}, filing).refs[0]
        filing = self.rapply('WithdrawFiling', target=filing).refs[0]
        result = self.projection(filing_id=filing.id)
        self.assertIsInstance(result, RegistryProjection)
        entry = result.filings[0]
        self.assertEqual(entry.status, 'WITHDRAWN')
        self.assertEqual(entry.artifact_source_id, artifact)
        self.assertEqual(entry.submission_receipt.document_id, submission)
        self.assertEqual(entry.acknowledgement_receipt.document_id, acknowledgement)
        self.assertEqual([r.event for r in result.history], fixture['expected_lifecycle'])
        self.assertEqual(entry.receipt_count, 6)
        self.assertTrue(all(r.filing.revision == r.sequence for r in result.history))
        self.assertFalse(result.unregistered_filings)

    def test_identical_bytes_can_back_distinct_incoming_and_outgoing_filings(self):
        artifact = self.source(b'IDENTICAL-SYNTHETIC-BYTES')
        first, _, _, _ = self.register(direction='INCOMING', source_id=artifact)
        second, _, _, _ = self.register(direction='OUTGOING', source_id=artifact)
        self.assertNotEqual(first.id, second.id)
        entries = {e.filing.id: e for e in self.projection().filings}
        self.assertEqual(entries[first.id].artifact_hash, entries[second.id].artifact_hash)
        self.assertEqual(entries[first.id].artifact_source_id, artifact)
        self.assertEqual(entries[second.id].artifact_source_id, artifact)

    def test_receipt_evidence_is_distinct_by_id_hash_and_filing_scope(self):
        filing, artifact, _, _ = self.make_ready()
        missing = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(uuid4())}, filing))
        self.assertIsInstance(missing, DomainError)
        self.assertEqual(missing.code, 'BROKEN_REFERENCE')
        same_artifact = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(artifact)}, filing))
        self.assertIsInstance(same_artifact, DomainError)
        self.assertEqual(same_artifact.code, 'GATE_DENIED')
        cloned_artifact = self.source(b'SYNTHETIC-FILING-BYTES')
        cloned = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(cloned_artifact)}, filing))
        self.assertIsInstance(cloned, DomainError)
        self.assertEqual(cloned.code, 'GATE_DENIED')

        submission_bytes = b'SYNTHETIC-UNIQUE-SUBMISSION-RECEIPT'
        submission = self.source(submission_bytes)
        filing = self.rapply('RecordSubmission', {'receipt_source_id': str(submission)}, filing).refs[0]
        cloned_submission = self.source(submission_bytes)
        bad_ack = self.rexecute(self.rrequest('RecordAcknowledgement', {'receipt_source_id': str(cloned_submission)}, filing))
        self.assertIsInstance(bad_ack, DomainError)
        self.assertEqual(bad_ack.code, 'GATE_DENIED')

        second, _, _, _ = self.make_ready(content=b'SYNTHETIC-SECOND-FILING')
        reused = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(submission)}, second))
        self.assertIsInstance(reused, DomainError)
        self.assertEqual(reused.code, 'GATE_DENIED')
        cloned_cross_filing = self.source(submission_bytes)
        reused_clone = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(cloned_cross_filing)}, second))
        self.assertIsInstance(reused_clone, DomainError)
        self.assertEqual(reused_clone.code, 'GATE_DENIED')

        acknowledgement = self.source(b'SYNTHETIC-INDEPENDENT-ACK')
        filing = self.rapply('RecordAcknowledgement', {'receipt_source_id': str(acknowledgement)}, filing).refs[0]
        self.assertEqual(self.projection(filing_id=filing.id).filings[0].status, 'ACKNOWLEDGED')

    def test_illegal_transition_and_artifact_rows_are_database_immutable(self):
        filing, artifact, _, _ = self.register()
        illegal = self.rexecute(self.rrequest('MarkFilingReady', target=filing))
        self.assertIsInstance(illegal, DomainError)
        self.assertEqual(illegal.code, 'INVALID_TRANSITION')
        with psycopg.connect(core.ADMIN, autocommit=True) as connection:
            with self.assertRaises(psycopg.errors.IntegrityConstraintViolation):
                connection.execute(
                    "UPDATE lw_core.objects SET original_bytes=%s WHERE tenant_id=%s AND case_id=%s AND category='source' AND object_id=%s",
                    (b'TAMPERED', self.tenant, self.case_id, artifact),
                )
        prepared = self.rapply('PrepareFiling', target=filing).refs[0]
        self.assertEqual(self.projection(filing_id=filing.id).filings[0].filing, prepared)

    def test_exact_replay_idempotency_conflict_and_concurrent_cas(self):
        author, recipient = self.principals()
        artifact = self.source(b'SYNTHETIC-REPLAY')
        request = self.rrequest('RegisterFiling', {
            'source_id': str(artifact), 'document_type': core.PIN, 'direction': 'OUTGOING',
            'recipient': recipient.model_dump(mode='json'), 'authors': [author.model_dump(mode='json')],
        })
        first = self.rexecute(request)
        self.assertIsInstance(first, CommandResult)
        self.sequence = first.case_sequence
        self.assertEqual(self.rexecute(request), first)
        self.assertEqual(len(self.projection(filing_id=first.refs[0].id).history), 1)
        changed = json.loads(json.dumps(request))
        changed['data']['direction'] = 'INCOMING'
        conflict = self.rexecute(changed)
        self.assertIsInstance(conflict, DomainError)
        self.assertEqual(conflict.code, 'IDEMPOTENCY_CONFLICT')
        filing = first.refs[0]
        left = self.rrequest('PrepareFiling', target=filing)
        right = self.rrequest('PrepareFiling', target=filing)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.rexecute, (left, right)))
        applied = [r for r in results if isinstance(r, CommandResult)]
        denied = [r for r in results if isinstance(r, DomainError)]
        self.assertEqual((len(applied), len(denied), denied[0].code), (1, 1, 'CONFLICT'))
        self.sequence = applied[0].case_sequence

    def test_cross_case_receipt_and_nonhuman_authority_are_denied(self):
        filing, _, _, _ = self.make_ready()
        foreign_tenant, foreign_case = uuid4(), uuid4()
        foreign_actor = Actor(id=uuid4(), kind='HUMAN')
        actions = self.principal.actions
        foreign_token = self.authority.provision(Principal(foreign_actor, foreign_tenant, foreign_case, actions))
        create = self.request('CreateCase', {'title': 'Foreign synthetic case', 'jurisdiction': 'PL', 'retention_policy': core.PIN})
        create['meta'].update(tenant_id=str(foreign_tenant), case_id=str(foreign_case), expected_case_sequence=0)
        foreign_result = self.service.execute(json.dumps(create), foreign_token)
        self.assertIsInstance(foreign_result, CommandResult)
        foreign_source_request = dict(
            contract='urn:lukart:work:CoreRequest:1.0.0', operation='RegisterSource',
            meta=dict(command_id=str(uuid4()), tenant_id=str(foreign_tenant), case_id=str(foreign_case),
                      idempotency_key=str(uuid4()), expected_case_sequence=foreign_result.case_sequence,
                      correlation_id=str(uuid4())), target=None,
            data=dict(content_base64=base64.b64encode(b'FOREIGN-SYNTHETIC-RECEIPT').decode(),
                      media_type='application/octet-stream', retention_policy=core.PIN),
        )
        self.assertIsInstance(self.service.execute(json.dumps(foreign_source_request), foreign_token), CommandResult)
        foreign_source = uuid5(UUID(foreign_source_request['meta']['command_id']), 'source')
        cross_case = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(foreign_source)}, filing))
        self.assertIsInstance(cross_case, DomainError)
        self.assertEqual(cross_case.code, 'BROKEN_REFERENCE')
        service_token = self.authority.provision(Principal(Actor(id=uuid4(), kind='SERVICE'), self.tenant, self.case_id, actions))
        receipt = self.source(b'SYNTHETIC-AUTHORITY-RECEIPT')
        denied = self.rexecute(self.rrequest('RecordSubmission', {'receipt_source_id': str(receipt)}, filing), token=service_token)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, 'FORBIDDEN')
        ai_token = self.authority.provision(Principal(Actor(id=uuid4(), kind='AI'), self.tenant, self.case_id, actions))
        query = self.projection(token=ai_token)
        self.assertIsInstance(query, DomainError)
        self.assertEqual(query.code, 'FORBIDDEN')

    def test_legacy_filing_is_explicitly_unregistered(self):
        author, recipient = self.principals()
        legacy = self.apply('AddFiling', {
            'document_type': core.PIN, 'direction': 'OUTGOING',
            'recipient': recipient.model_dump(mode='json'), 'authors': [author.model_dump(mode='json')],
        }).refs[0]
        result = self.projection(filing_id=legacy.id)
        self.assertFalse(result.filings)
        self.assertEqual(result.unregistered_filings, (legacy,))
        self.assertFalse(result.history)

    def test_transaction_rollback_leaves_no_partial_registry_state(self):
        author, recipient = self.principals()
        artifact = self.source(b'SYNTHETIC-ROLLBACK')
        request = self.rrequest('RegisterFiling', {
            'source_id': str(artifact), 'document_type': core.PIN, 'direction': 'OUTGOING',
            'recipient': recipient.model_dump(mode='json'), 'authors': [author.model_dump(mode='json')],
        })
        with patch.object(UnitOfWork, 'finish', side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic rollback'):
                self.rexecute(request)
        result = self.projection()
        self.assertFalse(result.filings)
        self.assertFalse(result.history)
        self.assertFalse(result.unregistered_filings)

    def test_receipt_rows_are_immutable_and_forged_chain_is_detected(self):
        filing, _, _, _ = self.register()
        original = self.projection(filing_id=filing.id).history[0]
        with psycopg.connect(core.ADMIN, autocommit=True) as connection:
            row = connection.execute(
                "SELECT object_id,payload FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt'",
                (self.tenant, self.case_id),
            ).fetchone()
            with self.assertRaises(psycopg.errors.IntegrityConstraintViolation):
                connection.execute(
                    "UPDATE lw_core.objects SET payload=%s WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt' AND object_id=%s",
                    (row[1], self.tenant, self.case_id, row[0]),
                )
            forged_data = original.model_dump(mode='json')
            forged_data.update(id=str(uuid4()), sequence=2, previous_hash='0' * 64,
                               event='PREPARED', operation='PrepareFiling')
            forged = RegistryReceipt.model_validate(forged_data)
            raw = json.dumps(forged.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            connection.execute(
                "INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.tenant, self.case_id, 'filing_registry_receipt', forged.id,
                 'urn:lukart:work:RegistryReceipt:1.0.0', raw, digest(forged), None),
            )
        result = self.projection(filing_id=filing.id)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'INVALID_HASH')


if __name__ == '__main__':
    unittest.main()
