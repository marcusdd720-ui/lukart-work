"""New HUMAN amendment boundary only; existing suites are not inherited/repeated."""
import copy
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4
from zipfile import ZipFile

from lukart_work.core.security import Principal
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.domain.models import Actor
from lukart_work.drafting.amendments import CATEGORY, HumanDraftAmendmentReceipt, verify_amendment
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server, CLIENT
from lukart_work.validation.rules import digest, ref, Violation
from tests import test_finalization as fixture


@unittest.skipUnless(fixture.core.ADMIN_RUNTIME and fixture.core.DSN, 'Explicit PostgreSQL test database required')
class DraftAmendmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.FinalizationTests.setUpClass()

    def setUp(self):
        self.h = fixture.FinalizationTests('test_stage10_golden_validated_is_not_rendered_or_final')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.operator = GeneratorPismOperator(repository=self.h.repo, authority=self.h.authority,
            case_profile=self.h.final_profile, drafting_profiles={}, provider=None,
            package_profile=self.h.package_profile)

    def command(self, draft, text='Poprawiona treść projektu: zażółć gęślą jaźń.'):
        return self.h.request('AmendDraft', dict(contract='urn:lukart:work:AmendDraft:1.0.0',
            draft_hash=digest(draft), edits=[dict(statement_id=str(draft.sections[0].statements[0].id),text=text)]),
            ref(draft), rationale='Jawna syntetyczna poprawka HUMAN; nie jest odbiorem rzeczywistego użytkownika')

    def query(self, draft, token=None):
        return self.operator.query_draft(dict(contract='urn:lukart:work:DraftEditorQuery:1.0.0',
            operation='GetDraftForEditing',tenant_id=str(self.h.tenant),case_id=str(self.h.case_id),
            draft=ref(draft).model_dump(mode='json')), token or self.h.token)

    def receipts(self):
        with self.h.repo.transaction(self.h.tenant, self.h.case_id) as tx:
            return tx.objects(CATEGORY, HumanDraftAmendmentReceipt)

    def apply(self, command):
        result=self.h.run_request(command)
        self.assertIsInstance(result,CommandResult,result)
        self.h.sequence=result.case_sequence
        return self.h.get(result.refs[0])

    def test_amendment_preserves_history_trace_and_requires_fresh_review_then_renders(self):
        original_apply=self.h.apply
        def polish_fixture(operation,data=None,*args,**kwargs):
            data=copy.deepcopy(data)
            if data is not None:
                for wanted,field,text in [('AddParty','display_name','Jan Testowy'),
                    ('AddRequest','text','Syntetyczny wniosek testowy'),
                    ('AddSection','title','Uzasadnienie'),
                    ('AddEvidence','description','Syntetyczne potwierdzenie wpłaty')]:
                    if operation==wanted:data[field]=text
            return original_apply(operation,data,*args,**kwargs)
        self.h.apply=polish_fixture
        original_papply=self.h.papply
        def polish_plan(operation,data=None,*args,**kwargs):
            data=copy.deepcopy(data)
            if data and 'sections' in data:
                for section in data['sections']:section['title']='Uzasadnienie'
            return original_papply(operation,data,*args,**kwargs)
        self.h.papply=polish_plan
        old, old_run = self.h.validated()
        before_sources = self.h.get(ref(old))
        command=self.command(old)
        polish_text={'FACTUAL':'Poprawiona treść projektu: zażółć gęślą jaźń.',
            'REQUEST':'Syntetyczny wniosek wynikający z zatwierdzonego planu.',
            'LEGAL':'Syntetyczne twierdzenie prawne z przypisanym odwołaniem.'}
        command['data']['edits']=[dict(statement_id=str(s.id),text=polish_text[s.statement_type])
            for section in old.sections for s in section.statements]
        new = self.apply(command)
        self.assertNotEqual(new.id,old.id)
        self.assertEqual(new.status,'GENERATED')
        self.assertEqual(new.supersedes,ref(old))
        self.assertEqual(self.h.get(ref(old)),before_sources)
        self.assertEqual(new.reproduction,old.reproduction)
        self.assertEqual(new.sections[0].statements[0].refs,old.sections[0].statements[0].refs)
        receipt=self.receipts()[0]
        self.assertEqual(receipt.actor,self.h.actor)
        self.assertEqual(receipt.predecessor_hash,digest(old))
        self.assertFalse(self.h.projection(old_run).eligible_for_approval)
        # No old review, approval or validation is inherited by the edited content.
        denied=self.h.vexecute(self.h.vrequest('ValidateDraft',new,review_id=str(self.h.projection(old_run).execution.review.id)))
        self.assertIsInstance(denied,DomainError)
        review=self.h.review(new)
        result,run,_=self.h.validate(new,review)
        validated=self.h.get(result.refs[0])
        self.assertEqual(validated.status,'VALIDATED')
        render_id,_,_=self.h.render(validated,run)
        docx=self.h.final_query('ReadFinalArtifact',render_id,format='DOCX')
        pdf=self.h.final_query('ReadFinalArtifact',render_id,format='PDF')
        self.assertIn('Poprawiona treść'.encode(),ZipFile(BytesIO(docx)).read('word/document.xml'))
        self.assertNotIn(b'Synthetic',ZipFile(BytesIO(docx)).read('word/document.xml'))
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(self.h.get(ref(old)),old)
        self.assertEqual(len(self.receipts()),1)
        out=Path('build/draft-amendment');out.mkdir(parents=True,exist_ok=True)
        (out/'amended.docx').write_bytes(docx);(out/'amended.pdf').write_bytes(pdf)
        (out/'artifact-evidence.json').write_text(json.dumps(dict(synthetic_only=True,
            actual_human_acceptance=False,final_approval=False,old_hash=digest(old),new_hash=digest(validated),
            receipt_hash=digest(receipt),docx_sha256=__import__('hashlib').sha256(docx).hexdigest(),
            pdf_sha256=__import__('hashlib').sha256(pdf).hexdigest()),indent=2),encoding='utf8')

    def test_service_ai_missing_action_foreign_scope_and_revocation_are_denied(self):
        _,old=self.h.generated()
        command=self.command(old);before=self.h.state()
        principals=[Principal(Actor(id=uuid4(),kind=kind),self.h.tenant,self.h.case_id,self.h.principal.actions)
                    for kind in ('SERVICE','AI')]
        principals += [Principal(self.h.actor,self.h.tenant,self.h.case_id,self.h.principal.actions-{'AmendDraft'}),
                       Principal(self.h.actor,self.h.tenant,uuid4(),self.h.principal.actions)]
        for principal in principals:
            token=self.h.authority.provision(principal)
            result=self.h.run_request(command,token=token)
            self.assertEqual(result.code,'FORBIDDEN')
        revoked=self.h.authority.provision(self.h.principal);self.h.authority.revoke(revoked)
        self.assertEqual(self.h.run_request(command,token=revoked).code,'FORBIDDEN')
        self.assertEqual(self.h.state(),before);self.assertEqual(self.receipts(),())

    def test_stale_hash_sequence_unknown_statement_and_reference_injection_roll_back(self):
        _,old=self.h.generated();original=self.command(old);before=self.h.state()
        variants=[]
        wrong=copy.deepcopy(original);wrong['data']['draft_hash']='0'*64;variants.append(wrong)
        wrong=copy.deepcopy(original);wrong['meta']['expected_case_sequence']-=1;variants.append(wrong)
        wrong=copy.deepcopy(original);wrong['data']['edits'][0]['statement_id']=str(uuid4());variants.append(wrong)
        wrong=copy.deepcopy(original);wrong['data']['edits'][0]['refs']=[];variants.append(wrong)
        wrong=copy.deepcopy(original);wrong['data']['edits']*=2;variants.append(wrong)
        wrong=copy.deepcopy(original);wrong['data']['edits'][0]['text']=' ';variants.append(wrong)
        for command in variants:
            self.assertIsInstance(self.h.run_request(command),DomainError)
            self.assertEqual(self.h.state(),before);self.assertEqual(self.receipts(),())

    def test_replay_survives_restart_changed_payload_and_other_actor_are_rejected(self):
        _,old=self.h.generated();command=self.command(old);new=self.apply(command)
        from lukart_work.core.service import CommandService
        restarted=CommandService(self.h.repo,self.h.authority)
        self.assertEqual(restarted.execute(json.dumps(command),self.h.token).refs,(ref(new),))
        changed=copy.deepcopy(command);changed['data']['edits'][0]['text']='Inny tekst.'
        self.assertEqual(restarted.execute(json.dumps(changed),self.h.token).code,'IDEMPOTENCY_CONFLICT')
        token=self.h.authority.provision(Principal(Actor(id=uuid4(),kind='HUMAN'),self.h.tenant,self.h.case_id,self.h.principal.actions))
        self.assertEqual(restarted.execute(json.dumps(command),token).code,'IDEMPOTENCY_CONFLICT')
        self.assertEqual(len(self.receipts()),1)

    def test_concurrent_writes_have_one_winner_and_cannot_fork_the_predecessor(self):
        _,old=self.h.generated();commands=[self.command(old,text='Poprawka '+str(i)) for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(self.h.run_request,commands))
        self.assertEqual(sum(isinstance(r,CommandResult) for r in results),1)
        self.h.sequence=next(r.case_sequence for r in results if isinstance(r,CommandResult))
        self.assertEqual(self.h.run_request(self.command(old)).code,'STALE')
        self.assertEqual(len(self.receipts()),1)

    def test_missing_receipt_fails_validation_and_editor_read_without_writes(self):
        _,old=self.h.generated();new=self.apply(self.command(old));before=self.h.state()
        from lukart_work.core.postgres import UnitOfWork
        original=UnitOfWork.object
        def missing(tx,category,*args):
            if category==CATEGORY:raise Violation('BROKEN_REFERENCE')
            return original(tx,category,*args)
        with patch.object(UnitOfWork,'object',missing):
            self.assertIsInstance(self.h.vexecute(self.h.vrequest('ValidateDraft',new)),DomainError)
            self.assertIsInstance(self.query(new),DomainError)
        self.assertEqual(self.h.state(),before)

    def test_second_amendment_chain_and_http_read_write_preserve_both_predecessors(self):
        _,old=self.h.generated();first=self.apply(self.command(old));second=self.apply(self.command(first,text='Druga poprawka.'))
        self.assertEqual(second.supersedes,ref(first));self.assertEqual(self.h.get(ref(old)),old)
        self.assertEqual(self.h.get(ref(first)),first)
        server=create_server(self.operator,0);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            command=self.command(second,text='Trzecia poprawka przez autoryzowane API.')
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST','/api/execute_core',json.dumps(command),{
                'Content-Type':'application/json','Authorization':'Bearer '+self.h.token,
                'Host':f'127.0.0.1:{server.server_port}'})
            response=conn.getresponse();result=json.loads(response.read());conn.close()
            self.assertEqual(result['state'],'APPLIED',result)
            final=self.h.get(__import__('lukart_work.domain.models',fromlist=['Ref']).Ref.model_validate_json(json.dumps(result['refs'][0])))
            self.assertEqual(self.query(final).draft_hash,digest(final))
            self.assertTrue(self.query(final).editable)
            self.assertFalse(self.query(first).editable)
            self.assertEqual(len(self.receipts()),3)
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

    def test_partial_write_failure_rolls_back_receipt_planned_revision_sequence_and_audit(self):
        _,old=self.h.generated();command=self.command(old);before=self.h.state()
        from lukart_work.core.service import CommandService
        original=CommandService._validate
        def fail_generated(service,entity,*args):
            if entity.kind=='Draft' and entity.supersedes is not None and entity.status=='GENERATED':
                raise Violation('GATE_DENIED')
            return original(service,entity,*args)
        with patch.object(CommandService,'_validate',fail_generated):
            self.assertEqual(self.h.run_request(command).code,'GATE_DENIED')
        self.assertEqual(self.h.state(),before);self.assertEqual(self.receipts(),())

    def test_receipt_tampering_and_model_trace_substitution_are_denied(self):
        from lukart_work.drafting.contracts import DraftingTrace
        _,old=self.h.generated()
        with self.h.repo.transaction(self.h.tenant,self.h.case_id) as tx:
            traces=tx.objects('drafting_trace',DraftingTrace)
        new=self.apply(self.command(old))
        with self.h.repo.transaction(self.h.tenant,self.h.case_id) as tx:
            self.assertEqual(tx.objects('drafting_trace',DraftingTrace),traces)
            receipt=tx.objects(CATEGORY,HumanDraftAmendmentReceipt)[0]
            records=tx.records()
            with patch.object(tx,'object',return_value=receipt.model_copy(update={'predecessor_hash':'0'*64})):
                with self.assertRaises(Violation):verify_amendment(tx,new,records)
            forged=new.model_copy(update={'reproduction':old.reproduction.model_copy(update={'raw_output_hash':'0'*64})})
            with self.assertRaises(Violation):verify_amendment(tx,forged,records)


class HumanHostConfigurationTests(unittest.TestCase):
    def test_service_or_ungranted_human_cannot_be_provisioned_by_the_host_bridge(self):
        import runpy
        from unittest.mock import Mock
        functions=runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/human_case_operator_host.py'))
        factory=functions['build_operator']
        operator=GeneratorPismOperator.__new__(GeneratorPismOperator)
        operator.binding=None;operator.core=SimpleNamespace(authority=Mock())
        for kind,actions in [('SERVICE',frozenset({'CreateCase','AmendDraft','GetRevision','GetCaseHead'})),
                             ('HUMAN',frozenset({'CreateCase','GetRevision','GetCaseHead'}))]:
            identity=dict(authenticate_human=lambda op:Principal(Actor(id=uuid4(),kind=kind),uuid4(),uuid4(),actions))
            modules=Mock(side_effect=[dict(build_operator=lambda:operator),identity])
            with patch.dict(factory.__globals__,trusted_module=modules):
                with self.assertRaises((ValueError,Violation)):factory()
            operator.core.authority.provision.assert_not_called()


class DraftEditorBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required to execute editor browser contract')
    def test_editor_prepares_explicit_text_only_amendment_and_clears_private_state(self):
        harness=r'''
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto').webcrypto;
const elements=new Map(),calls=[];
function element(){return {value:'',children:[],append(...items){this.children.push(...items);},
 replaceChildren(...items){this.children=items;},removeAttribute(){}};}
const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement(){return element();}};
const context={document,crypto,window:{addEventListener(){}},URL:{revokeObjectURL(){}},
 fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,headers:{get(){return 'application/json';}},text:async()=> '{}'};}};
vm.createContext(context);vm.runInContext(fs.readFileSync(0,'utf8'),context);
vm.runInContext(`tenant.value='00000000-0000-0000-0000-000000000001';caseId.value='00000000-0000-0000-0000-000000000002';
handleDraftEditorResult('query_draft',{}, {result_type:'DRAFT_EDITOR',editable:true,case_sequence:7,draft_hash:'${'a'.repeat(64)}',
draft:{kind:'Draft',id:'00000000-0000-0000-0000-000000000003',revision:2,status:'GENERATED',
tenant_id:tenant.value,case_id:caseId.value,supersedes:null,sections:[{section:{id:'section'},statements:[{
id:'00000000-0000-0000-0000-000000000004',text:'Pierwotny tekst.',statement_type:'FACTUAL',refs:[]}]}]}});
editorTextNodes.values().next().value.value='Poprawiony tekst.';
document.getElementById('amendRationale').value='Własna poprawka operatora';document.getElementById('prepareAmend').onclick();`,context);
const prepared=JSON.parse(elements.get('request').value);if(calls.length)throw Error('Implicit mutation');
vm.runInContext(`token.oninput();if(editorDraft!==null||editorTextNodes.size||draftTexts.children.length)throw Error('Private draft retained');`,context);
process.stdout.write(JSON.stringify(prepared));
'''
        process=subprocess.run([shutil.which('node'),'-e',harness],input=CLIENT.decode(),text=True,
            capture_output=True,check=True,timeout=15)
        value=json.loads(process.stdout)
        self.assertEqual(value['operation'],'AmendDraft')
        self.assertEqual(set(value['data']),{'contract','draft_hash','edits'})
        self.assertEqual(set(value['data']['edits'][0]),{'statement_id','text'})
        self.assertEqual(value['meta']['expected_case_sequence'],7)
