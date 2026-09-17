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
from lukart_work.core.postgres import UnitOfWork
from lukart_work.core.security import Principal
from lukart_work.domain.models import Actor
from lukart_work.registry.contracts import RegistryOperation, RegistryProjection
from lukart_work.registry.service import DocumentRegistryService
from tests import test_stage02 as core


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 06 requires isolated PostgreSQL')
class DocumentRegistryTests(core.Stage02Tests):
    def setUp(self):
        super().setUp()
        self.authority.revoke(self.token)
        actions = self.principal.actions | frozenset(get_args(RegistryOperation)) | {'GetDocumentRegistry'}
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.registry_service = DocumentRegistryService(self.repo, self.authority)

    def rrequest(self, operation, data=None, target=None):
        request = self.request(
            operation,
            data,
            target,
            rationale='Synthetic Stage 06 registry operation',
        )
        request['contract'] = 'urn:lukart:work:RegistryRequest:1.0.0'
        return request

    def rexecute(self, request, token=None, service=None):
        return (service or self.registry_service).execute(json.dumps(request), token or self.token)

    def rapply(self, operation, data=None, target=None):
        request = self.rrequest(operation, data, target)
        result = self.rexecute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result, request

    def projection(self, token=None, tenant=None, case=None, filing_id=None, service=None):
        query = dict(
            contract='urn:lukart:work:RegistryQuery:1.0.0',
            operation='GetDocumentRegistry',
            tenant_id=str(tenant or self.tenant),
            case_id=str(case or self.case_id),
            filing_id=str(filing_id) if filing_id else None,
        )
        return (service or self.registry_service).registry(json.dumps(query), token or self.token)

    def source(self, content):
        result, request = self.apply(
            'RegisterSource',
            dict(
                content_base64=base64.b64encode(content).decode(),
                media_type='application/octet-stream',
                retention_policy=core.PIN,
            ),
        )
        self.assertFalse(result.refs)
        return uuid5(UUID(request['meta']['command_id']), 'source')

    def principals(self):
        author = self.party()
        recipient = self.apply(
            'AddInstitution',
            dict(
                institution_type='AUTHORITY',
                name='Synthetic Registry Authority',
                jurisdiction='PL',
            ),
        )[0].refs[0]
        return author, recipient

    def register(self, content=b'SYNTHETIC-FILING-BYTES', direction='OUTGOING', source_id=None):
        author, recipient = self.principals()
        source_id = source_id or self.source(content)
        result, request = self.rapply(
            'RegisterFiling',
            dict(
                source_id=str(source_id),
                document_type=core.PIN,
                direction=direction,
                recipient=recipient.model_dump(mode='json'),
                authors=[author.model_dump(mode='json')],
            ),
        )
        return result.refs[0], source_id, author, recipient, request

    def ready(self):
        filing, artifact, author, recipient, _ = self.register()
        filing = self.rapply('PrepareFiling', target=filing)[0].refs[0]
        filing = self.rapply('MarkFilingReady', target=filing)[0].refs[0]
        return filing, artifact, author, recipient

    def submitted(self):
        filing, artifact, author, recipient = self.ready()
        receipt = self.source(b'SYNTHETIC-SUBMISSION-RECEIPT')
        filing = self.rapply('RecordSubmission', {'receipt_source_id': str(receipt)}, filing)[0].refs[0]
        return filing, artifact, receipt, author, recipient

    def test_golden_registry_submission_acknowledgement_withdrawal_and_history(self):
        fixture = json.loads((Path(__file__).parent / 'golden_cases/document_registry.json').read_text())
        filing, artifact, _, _ = self.ready()
        submission = self.source(fixture['submission_receipt_text'].encode())
        filing = self.rapply('RecordSubmission', {'receipt_source_id': str(submission)}, filing)[0].refs[0]
        acknowledgement = self.source(fixture['acknowledgement_receipt_text'].encode())
        filing = self.rapply(
            'RecordAcknowledgement',
            {'receipt_source_id': str(acknowledgement)},
            filing,
        )[0].refs[0]
        filing = self.rapply('WithdrawFiling', target=filing)[0].refs[0]
        result = self.projection(filing_id=filing.id)
        self.assertIsInstance(result, RegistryProjection)
        self.assertEqual(len(result.filings), 1)
        entry = result.filings[0]
        self.assertEqual(entry.status, 'WITHDRAWN')
        self.assertEqual(entry.artifact_source_id, artifact)
        self.assertEqual(entry.submission_receipt.document_id, submission)
        self.assertEqual(entry.acknowledgement_receipt.document_id, acknowledgement)
        self.assertEqual([r.event for r in result.history], fixture['expected_lifecycle'])
        self.assertEqual(entry.receipt_count, 6)
        self.assertEqual([r.sequence for r in result.history], list(range(1, 7)))
        self.assertTrue(all(r.filing.revision == r.sequence for r in result.history))
        self.assertFalse(result.unregistered_filings)

    def test_incoming_and_identical_bytes_can_be_two_distinct_filings(self):
        artifact = self.source(b'IDENTICAL-SYNTHETIC-BYTES')
        first, _, _, _, _ = self.register(direction='INCOMING', source_id=artifact)
        second, _, _, _, _ = self.register(direction='OUTGOING', source_id=artifact)
        self.assertNotEqual(first.id, second.id)
        result = self.projection()
        entries = {e.filing.id: e for e in result.filings}
        self.assertEqual(entries[first.id].artifact_hash, entries[second.id].artifact_hash)
        self.assertEqual(entries[first.id].artifact_source_id, artifact)
        self.assertEqual(entries[second.id].artifact_source_id, artifact)
        self.assertNotEqual(entries[first.id].filing, entries[second.id].filing)

    def test_submission_requires_existing_independent_receipt_source(self):
        filing, artifact, _, _ = self.ready()
        before = self.sequence
        error = self.rexecute(
            self.rrequest('RecordSubmission', {'receipt_source_id': str(uuid4())}, filing)
        )
        self.assertIsInstance(error, DomainError)
        self.assertEqual(error.code, 'BROKEN_REFERENCE')
        self.assertEqual(self.sequence, before)
        self.assertEqual(self.projection(filing_id=filing.id).filings[0].status, 'READY')
        same_artifact = self.rexecute(
            self.rrequest('RecordSubmission', {'receipt_source_id': str(artifact)}, filing)
        )
        self.assertIsInstance(same_artifact, DomainError)
        self.assertEqual(same_artifact.code, 'GATE_DENIED')

    def test_acknowledgement_requires_submission_and_separate_evidence(self):
        filing, _, _, _ = self.ready()
        ack_source = self.source(b'SYNTHETIC-EARLY-ACK')
        early = self.rexecute(
            self.rrequest('RecordAcknowledgement', {'receipt_source_id': str(ack_source)}, filing)
        )
        self.assertIsInstance(early, DomainError)
        self.assertEqual(early.code, 'GATE_DENIED')

        submission = self.source(b'SYNTHETIC-SUBMISSION')
        filing = self.rapply('RecordSubmission', {'receipt_source_id': str(submission)}, filing)[0].refs[0]
        reused = self.rexecute(
            self.rrequest('RecordAcknowledgement', {'receipt_source_id': str(submission)}, filing)
        )
        self.assertIsInstance(reused, DomainError)
        self.assertEqual(reused.code, 'GATE_DENIED')

    def test_illegal_transition_and_artifact_tamper_fail_closed(self):
        filing, artifact, _, _, _ = self.register()
        illegal = self.rexecute(self.rrequest('MarkFilingReady', target=filing))
        self.assertIsInstance(illegal, DomainError)
        self.assertEqual(illegal.code, 'INVALID_TRANSITION')
        with psycopg.connect(core.ADMIN) as connection:
            connection.execute(
                "UPDATE lw_core.objects SET original_bytes=%s WHERE tenant_id=%s AND case_id=%s AND category='source' AND object_id=%s",
                (b'TAMPERED', self.tenant, self.case_id, artifact),
            )
        tampered = self.rexecute(self.rrequest('PrepareFiling', target=filing))
        self.assertIsInstance(tampered, DomainError)
        self.assertEqual(tampered.code, 'PROVENANCE_MISSING')

    def test_exact_replay_idempotency_conflict_and_concurrent_cas(self):
        author, recipient = self.principals()
        artifact = self.source(b'SYNTHETIC-REPLAY')
        request = self.rrequest(
            'RegisterFiling',
            dict(
                source_id=str(artifact),
                document_type=core.PIN,
                direction='OUTGOING',
                recipient=recipient.model_dump(mode='json'),
                authors=[author.model_dump(mode='json')],
            ),
        )
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
        self.assertEqual(len(applied), 1)
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].code, 'CONFLICT')
        self.sequence = applied[0].case_sequence

    def test_human_write_authority_cross_case_receipt_and_ai_query_denied(self):
        filing, _, _, _ = self.ready()
        foreign_tenant, foreign_case = uuid4(), uuid4()
        foreign_actor = Actor(id=uuid4(), kind='HUMAN')
        actions = self.principal.actions
        foreign = Principal(foreign_actor, foreign_tenant, foreign_case, actions)
        foreign_token = self.authority.provision(foreign)

        foreign_request = self.request(
            'CreateCase',
            {'title': 'Foreign synthetic case', 'jurisdiction': 'PL', 'retention_policy': core.PIN},
        )
        foreign_request['meta']['tenant_id'] = str(foreign_tenant)
        foreign_request['meta']['case_id'] = str(foreign_case)
        foreign_request['meta']['expected_case_sequence'] = 0
        foreign_result = self.service.execute(json.dumps(foreign_request), foreign_token)
        self.assertIsInstance(foreign_result, CommandResult)
        foreign_source_request = dict(
            contract='urn:lukart:work:CoreRequest:1.0.0',
            operation='RegisterSource',
            meta=dict(
                command_id=str(uuid4()),
                tenant_id=str(foreign_tenant),
                case_id=str(foreign_case),
                idempotency_key=str(uuid4()),
                expected_case_sequence=foreign_result.case_sequence,
                correlation_id=str(uuid4()),
            ),
            target=None,
            data=dict(
                content_base64=base64.b64encode(b'FOREIGN-SYNTHETIC-RECEIPT').decode(),
                media_type='application/octet-stream',
                retention_policy=core.PIN,
            ),
        )
        foreign_source_result = self.service.execute(json.dumps(foreign_source_request), foreign_token)
        self.assertIsInstance(foreign_source_result, CommandResult)
        foreign_source = uuid5(UUID(foreign_source_request['meta']['command_id']), 'source')
        cross_case = self.rexecute(
            self.rrequest('RecordSubmission', {'receipt_source_id': str(foreign_source)}, filing)
        )
        self.assertIsInstance(cross_case, DomainError)
        self.assertEqual(cross_case.code, 'BROKEN_REFERENCE')

        service_actor = Actor(id=uuid4(), kind='SERVICE')
        service_token = self.authority.provision(
            Principal(service_actor, self.tenant, self.case_id, actions)
        )
        receipt = self.source(b'SYNTHETIC-AUTHORITY-RECEIPT')
        denied = self.rexecute(
            self.rrequest('RecordSubmission', {'receipt_source_id': str(receipt)}, filing),
            token=service_token,
        )
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, 'FORBIDDEN')

        ai_actor = Actor(id=uuid4(), kind='AI')
        ai_token = self.authority.provision(Principal(ai_actor, self.tenant, self.case_id, actions))
        query = self.projection(token=ai_token)
        self.assertIsInstance(query, DomainError)
        self.assertEqual(query.code, 'FORBIDDEN')

    def test_legacy_filing_is_explicitly_unregistered_not_reinterpreted(self):
        author, recipient = self.principals()
        legacy = self.apply(
            'AddFiling',
            dict(
                document_type=core.PIN,
                direction='OUTGOING',
                recipient=recipient.model_dump(mode='json'),
                authors=[author.model_dump(mode='json')],
            ),
        )[0].refs[0]
        result = self.projection(filing_id=legacy.id)
        self.assertFalse(result.filings)
        self.assertEqual(result.unregistered_filings, (legacy,))
        self.assertFalse(result.history)

    def test_transaction_rollback_leaves_no_partial_filing_or_receipt(self):
        author, recipient = self.principals()
        artifact = self.source(b'SYNTHETIC-ROLLBACK')
        request = self.rrequest(
            'RegisterFiling',
            dict(
                source_id=str(artifact),
                document_type=core.PIN,
                direction='OUTGOING',
                recipient=recipient.model_dump(mode='json'),
                authors=[author.model_dump(mode='json')],
            ),
        )
        with patch.object(UnitOfWork, 'finish', side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic rollback'):
                self.rexecute(request)
        result = self.projection()
        self.assertFalse(result.filings)
        self.assertFalse(result.history)
        self.assertFalse(result.unregistered_filings)

    def test_receipt_chain_tamper_is_detected(self):
        filing, _, _, _, _ = self.register()
        with psycopg.connect(core.ADMIN) as connection:
            row = connection.execute(
                "SELECT object_id,payload FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt'",
                (self.tenant, self.case_id),
            ).fetchone()
            payload = json.loads(row[1])
            payload['artifact_hash'] = '0' * 64
            connection.execute(
                "UPDATE lw_core.objects SET payload=%s WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt' AND object_id=%s",
                (json.dumps(payload, sort_keys=True, separators=(',', ':')), self.tenant, self.case_id, row[0]),
            )
        result = self.projection(filing_id=filing.id)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'INVALID_HASH')


if __name__ == '__main__':
    unittest.main()
