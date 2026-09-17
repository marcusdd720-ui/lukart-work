"""Stage 06 Document Registry acceptance on real PostgreSQL; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
import base64, json, unittest
from pathlib import Path
from typing import get_args
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5
import psycopg

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.postgres import PostgresRepository, UnitOfWork
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.registry.contracts import RegistryOperation, RegistryProjection
from lukart_work.registry.service import DocumentRegistryService
from lukart_work.validation.rules import digest
from tests import test_stage02 as core

@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 06 requires isolated PostgreSQL')
class DocumentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case_id, self.sequence = uuid4(), uuid4(), 0
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        actions = core.ACTIONS | frozenset(get_args(RegistryOperation)) | {'GetDocumentRegistry'}
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.repo = PostgresRepository(core.DSN)
        self.service = CommandService(self.repo, self.authority)
        self.registry_service = DocumentRegistryService(self.repo, self.authority)
        self.apply('CreateCase', {'title':'Synthetic Stage 06 case','jurisdiction':'PL','retention_policy':core.PIN})

    def request(self, operation, data=None, target=None, contract='urn:lukart:work:CoreRequest:1.0.0'):
        return {'contract':contract,'operation':operation,'meta':{
            'command_id':str(uuid4()),'tenant_id':str(self.tenant),'case_id':str(self.case_id),
            'idempotency_key':str(uuid4()),'expected_case_sequence':self.sequence,'correlation_id':str(uuid4())},
            'target':target.model_dump(mode='json') if target else None,'data':data or {}}

    def apply(self, operation, data=None, target=None):
        result=self.service.execute(json.dumps(self.request(operation,data,target)),self.token)
        self.assertIsInstance(result,CommandResult,result); self.sequence=result.case_sequence; return result

    def rrequest(self, operation, data=None, target=None):
        r=self.request(operation,data,target,'urn:lukart:work:RegistryRequest:1.0.0')
        r['rationale']='Synthetic Stage 06 registry operation'; return r

    def rexecute(self, request, token=None):
        return self.registry_service.execute(json.dumps(request),token or self.token)

    def rapply(self, operation, data=None, target=None):
        result=self.rexecute(self.rrequest(operation,data,target))
        self.assertIsInstance(result,CommandResult,result); self.sequence=result.case_sequence; return result

    def projection(self, token=None, filing_id=None):
        q={'contract':'urn:lukart:work:RegistryQuery:1.0.0','operation':'GetDocumentRegistry',
           'tenant_id':str(self.tenant),'case_id':str(self.case_id),'filing_id':str(filing_id) if filing_id else None}
        return self.registry_service.registry(json.dumps(q),token or self.token)

    def source(self, content):
        r=self.request('RegisterSource',{'content_base64':base64.b64encode(content).decode(),
            'media_type':'application/octet-stream','retention_policy':core.PIN})
        result=self.service.execute(json.dumps(r),self.token); self.assertIsInstance(result,CommandResult,result)
        self.sequence=result.case_sequence; return uuid5(UUID(r['meta']['command_id']),'source')

    def principals(self):
        author=self.apply('AddParty',{'party_type':'PERSON','display_name':'Synthetic Stage 06 Author','identity_evidence':[]}).refs[0]
        recipient=self.apply('AddInstitution',{'institution_type':'AUTHORITY','name':'Synthetic Registry Authority','jurisdiction':'PL'}).refs[0]
        return author,recipient

    def register(self, content=b'SYNTHETIC-FILING-BYTES', direction='OUTGOING', source_id=None):
        author,recipient=self.principals(); source_id=source_id or self.source(content)
        result=self.rapply('RegisterFiling',{'source_id':str(source_id),'document_type':core.PIN,'direction':direction,
            'recipient':recipient.model_dump(mode='json'),'authors':[author.model_dump(mode='json')]})
        return result.refs[0],source_id,author,recipient

    def ready(self, content=b'SYNTHETIC-FILING-BYTES'):
        filing,artifact,author,recipient=self.register(content=content)
        filing=self.rapply('PrepareFiling',target=filing).refs[0]
        filing=self.rapply('MarkFilingReady',target=filing).refs[0]
        return filing,artifact,author,recipient

    def test_golden_registry_submission_acknowledgement_withdrawal_and_history(self):
        f=json.loads((Path(__file__).parent/'golden_cases/document_registry.json').read_text())
        filing,artifact,_,_=self.ready(); submission=self.source(f['submission_receipt_text'].encode())
        filing=self.rapply('RecordSubmission',{'receipt_source_id':str(submission)},filing).refs[0]
        acknowledgement=self.source(f['acknowledgement_receipt_text'].encode())
        filing=self.rapply('RecordAcknowledgement',{'receipt_source_id':str(acknowledgement)},filing).refs[0]
        filing=self.rapply('WithdrawFiling',target=filing).refs[0]; result=self.projection(filing_id=filing.id)
        self.assertIsInstance(result,RegistryProjection); entry=result.filings[0]
        self.assertEqual((entry.status,entry.artifact_source_id),('WITHDRAWN',artifact))
        self.assertEqual(entry.submission_receipt.document_id,submission); self.assertEqual(entry.acknowledgement_receipt.document_id,acknowledgement)
        self.assertEqual([x.event for x in result.history],f['expected_lifecycle']); self.assertEqual(entry.receipt_count,6)
        self.assertTrue(all(x.filing.revision==x.sequence for x in result.history)); self.assertFalse(result.unregistered_filings)

    def test_identical_bytes_can_back_distinct_incoming_and_outgoing_filings(self):
        artifact=self.source(b'IDENTICAL-SYNTHETIC-BYTES')
        first,_,_,_=self.register(direction='INCOMING',source_id=artifact); second,_,_,_=self.register(direction='OUTGOING',source_id=artifact)
        self.assertNotEqual(first.id,second.id); entries={e.filing.id:e for e in self.projection().filings}
        self.assertEqual(entries[first.id].artifact_hash,entries[second.id].artifact_hash)
        self.assertEqual((entries[first.id].artifact_source_id,entries[second.id].artifact_source_id),(artifact,artifact))

    def test_receipt_evidence_is_distinct_by_id_hash_and_filing_scope(self):
        filing,artifact,_,_=self.ready()
        missing=self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(uuid4())},filing)); self.assertEqual(missing.code,'BROKEN_REFERENCE')
        same=self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(artifact)},filing)); self.assertEqual(same.code,'GATE_DENIED')
        cloned_artifact=self.source(b'SYNTHETIC-FILING-BYTES')
        self.assertEqual(self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(cloned_artifact)},filing)).code,'GATE_DENIED')
        receipt_bytes=b'SYNTHETIC-UNIQUE-SUBMISSION-RECEIPT'; submission=self.source(receipt_bytes)
        filing=self.rapply('RecordSubmission',{'receipt_source_id':str(submission)},filing).refs[0]
        cloned_submission=self.source(receipt_bytes)
        self.assertEqual(self.rexecute(self.rrequest('RecordAcknowledgement',{'receipt_source_id':str(cloned_submission)},filing)).code,'GATE_DENIED')
        second,_,_,_=self.ready(content=b'SYNTHETIC-SECOND-FILING')
        self.assertEqual(self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(submission)},second)).code,'GATE_DENIED')
        cloned_cross=self.source(receipt_bytes)
        self.assertEqual(self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(cloned_cross)},second)).code,'GATE_DENIED')
        ack=self.source(b'SYNTHETIC-INDEPENDENT-ACK'); filing=self.rapply('RecordAcknowledgement',{'receipt_source_id':str(ack)},filing).refs[0]
        self.assertEqual(self.projection(filing_id=filing.id).filings[0].status,'ACKNOWLEDGED')

    def test_illegal_transition_and_artifact_rows_are_database_immutable(self):
        filing,artifact,_,_=self.register(); self.assertEqual(self.rexecute(self.rrequest('MarkFilingReady',target=filing)).code,'INVALID_TRANSITION')
        with psycopg.connect(core.ADMIN,autocommit=True) as c:
            with self.assertRaises(psycopg.errors.IntegrityConstraintViolation):
                c.execute("UPDATE lw_core.objects SET original_bytes=%s WHERE tenant_id=%s AND case_id=%s AND category='source' AND object_id=%s",(b'TAMPERED',self.tenant,self.case_id,artifact))
        prepared=self.rapply('PrepareFiling',target=filing).refs[0]; self.assertEqual(self.projection(filing_id=filing.id).filings[0].filing,prepared)

    def test_exact_replay_idempotency_conflict_and_concurrent_cas(self):
        author,recipient=self.principals(); artifact=self.source(b'SYNTHETIC-REPLAY')
        request=self.rrequest('RegisterFiling',{'source_id':str(artifact),'document_type':core.PIN,'direction':'OUTGOING',
            'recipient':recipient.model_dump(mode='json'),'authors':[author.model_dump(mode='json')]})
        first=self.rexecute(request); self.assertIsInstance(first,CommandResult); self.sequence=first.case_sequence
        self.assertEqual(self.rexecute(request),first); self.assertEqual(len(self.projection(filing_id=first.refs[0].id).history),1)
        changed=json.loads(json.dumps(request)); changed['data']['direction']='INCOMING'; self.assertEqual(self.rexecute(changed).code,'IDEMPOTENCY_CONFLICT')
        left=self.rrequest('PrepareFiling',target=first.refs[0]); right=self.rrequest('PrepareFiling',target=first.refs[0])
        with ThreadPoolExecutor(max_workers=2) as p: results=list(p.map(self.rexecute,(left,right)))
        applied=[r for r in results if isinstance(r,CommandResult)]; denied=[r for r in results if isinstance(r,DomainError)]
        self.assertEqual((len(applied),len(denied),denied[0].code),(1,1,'CONFLICT')); self.sequence=applied[0].case_sequence

    def test_cross_case_receipt_and_nonhuman_authority_are_denied(self):
        filing,_,_,_=self.ready(); foreign_tenant,foreign_case=uuid4(),uuid4(); actions=self.principal.actions
        foreign_token=self.authority.provision(Principal(Actor(id=uuid4(),kind='HUMAN'),foreign_tenant,foreign_case,actions))
        create=self.request('CreateCase',{'title':'Foreign synthetic case','jurisdiction':'PL','retention_policy':core.PIN})
        create['meta'].update(tenant_id=str(foreign_tenant),case_id=str(foreign_case),expected_case_sequence=0)
        foreign_result=self.service.execute(json.dumps(create),foreign_token); self.assertIsInstance(foreign_result,CommandResult)
        sr={'contract':'urn:lukart:work:CoreRequest:1.0.0','operation':'RegisterSource','meta':{
            'command_id':str(uuid4()),'tenant_id':str(foreign_tenant),'case_id':str(foreign_case),'idempotency_key':str(uuid4()),
            'expected_case_sequence':foreign_result.case_sequence,'correlation_id':str(uuid4())},'target':None,'data':{
            'content_base64':base64.b64encode(b'FOREIGN-SYNTHETIC-RECEIPT').decode(),'media_type':'application/octet-stream','retention_policy':core.PIN}}
        self.assertIsInstance(self.service.execute(json.dumps(sr),foreign_token),CommandResult); foreign_source=uuid5(UUID(sr['meta']['command_id']),'source')
        self.assertEqual(self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(foreign_source)},filing)).code,'BROKEN_REFERENCE')
        service_token=self.authority.provision(Principal(Actor(id=uuid4(),kind='SERVICE'),self.tenant,self.case_id,actions)); receipt=self.source(b'SYNTHETIC-AUTHORITY-RECEIPT')
        self.assertEqual(self.rexecute(self.rrequest('RecordSubmission',{'receipt_source_id':str(receipt)},filing),service_token).code,'FORBIDDEN')
        ai_token=self.authority.provision(Principal(Actor(id=uuid4(),kind='AI'),self.tenant,self.case_id,actions)); self.assertEqual(self.projection(ai_token).code,'FORBIDDEN')

    def test_legacy_filing_is_explicitly_unregistered(self):
        author,recipient=self.principals(); legacy=self.apply('AddFiling',{'document_type':core.PIN,'direction':'OUTGOING',
            'recipient':recipient.model_dump(mode='json'),'authors':[author.model_dump(mode='json')]}).refs[0]
        result=self.projection(filing_id=legacy.id); self.assertFalse(result.filings); self.assertEqual(result.unregistered_filings,(legacy,)); self.assertFalse(result.history)

    def test_transaction_rollback_leaves_no_partial_registry_state(self):
        author,recipient=self.principals(); artifact=self.source(b'SYNTHETIC-ROLLBACK')
        request=self.rrequest('RegisterFiling',{'source_id':str(artifact),'document_type':core.PIN,'direction':'OUTGOING',
            'recipient':recipient.model_dump(mode='json'),'authors':[author.model_dump(mode='json')]})
        with patch.object(UnitOfWork,'finish',side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaisesRegex(RuntimeError,'synthetic rollback'): self.rexecute(request)
        result=self.projection(); self.assertFalse(result.filings); self.assertFalse(result.history); self.assertFalse(result.unregistered_filings)

    def test_receipt_rows_are_immutable_and_forged_chain_is_detected(self):
        filing,_,_,_=self.register(); original=self.projection(filing_id=filing.id).history[0]
        with psycopg.connect(core.ADMIN,autocommit=True) as c:
            row=c.execute("SELECT object_id,payload FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt'",(self.tenant,self.case_id)).fetchone()
            with self.assertRaises(psycopg.errors.IntegrityConstraintViolation):
                c.execute("UPDATE lw_core.objects SET payload=%s WHERE tenant_id=%s AND case_id=%s AND category='filing_registry_receipt' AND object_id=%s",(row[1],self.tenant,self.case_id,row[0]))
            forged_id=uuid4(); forged_data=original.model_dump(mode='json')
            forged_data.update(id=str(forged_id),sequence=2,previous_hash='0'*64,event='PREPARED',operation='PrepareFiling')
            raw=json.dumps(forged_data,sort_keys=True,separators=(',',':'),ensure_ascii=False)
            c.execute("INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(self.tenant,self.case_id,'filing_registry_receipt',forged_id,
                'urn:lukart:work:RegistryReceipt:1.0.0',raw,digest(forged_data),None))
        result=self.projection(filing_id=filing.id); self.assertIsInstance(result,DomainError); self.assertEqual(result.code,'INVALID_HASH')

if __name__=='__main__': unittest.main()
