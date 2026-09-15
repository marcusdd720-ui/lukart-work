"""Independent regressions for AGR-01-001 through AGR-01-007 only."""
import unittest
from pydantic import ValidationError
from tests.fixtures import *
from lukart_work.validation.rules import *


def document_graph():
    c,p,ev,f=case(),party(),evidence(),fact()
    inst=Institution(**common(200),kind='Institution',status='UNVERIFIED',institution_type='COURT',name='Court',jurisdiction='PL')
    filing=Filing(**common(201),kind='Filing',status='PLANNED',document_type=PIN,direction='OUTGOING',recipient=ref(inst),authors=(ref(p),))
    issue=Issue(**common(202),kind='Issue',status='IDENTIFIED',question='Question',facts=(ref(f),),rules=())
    claim=Claim(**common(203),kind='Claim',status='PROPOSED',claim_type='ASSERTION',statement='Assertion',claimant=ref(p),issues=(ref(issue),),facts=(ref(f),),rules=(),support='SOURCE_BACKED')
    request=Request(**common(204),kind='Request',status='PROPOSED',filing=ref(filing),request_type='test',text='Request',claims=(ref(claim),),evidence=())
    legal=LegalSource(**common(205),kind='LegalSource',status='REGISTERED',registry_pin=PIN,jurisdiction='PL',source_type='LAW',title='Synthetic source',identifier='TEST',effective_period=TimeRange(start=NOW.date()),retrieved_at=NOW,source_uri='https://example.invalid/test',content_hash=H,authority_level='UNKNOWN',anchor=anchor())
    citation=Citation(**common(206),kind='Citation',status='BOUND',source=ref(legal),locator=anchor().locator,supported=ref(claim))
    contract=SectionContract(allowed_inputs=(ref(f),ref(citation)),required_inputs=(ref(f),ref(citation)),allowed_claims=(),forbidden=(),requirements=('CITATIONS',))
    section=Section(**common(207),kind='Section',status='READY',filing=ref(filing),section_type='facts',title='Facts',arguments=(),contract=contract)
    inputs=(c,p,ev,f,inst,filing,issue,claim,request,legal,citation,section)
    snap=Snapshot(schema_version='1.0.0',id=uid(300),tenant_id=c.tenant_id,case_id=c.case_id,case_sequence=12,created_at=NOW,members=tuple(SnapshotMember(ref=ref(x),content_hash=digest(x)) for x in inputs),heads=tuple(ref(x) for x in inputs),sources=(source(),),knowledge_pins=(PIN,),rule_set=PIN,policy=PIN)
    acceptance=Decision(**common(301),kind='Decision',status='RECORDED',decision_type='SNAPSHOT_ACCEPTANCE',targets=(ref(c),),outcome='ACCEPT',rationale='Reviewed exact input',decided_by=ACTOR,snapshot_target=SnapshotTarget(tenant_id=c.tenant_id,case_id=c.case_id,snapshot_id=snap.id,snapshot_hash=digest(snap)))
    proposed=DocumentPlan(**common(302),kind='DocumentPlan',status='PROPOSED',filing=ref(filing),input_snapshot_id=snap.id,input_snapshot_hash=digest(snap),objectives=(ref(request),),recipient=ref(inst),position_scope='Test',argument_order=(),evidence=(ref(ev),),section_order=(ref(section),))
    reviewed=next_rev(proposed,'REVIEWED')
    approval=Decision(**common(303),kind='Decision',status='RECORDED',decision_type='PLAN_APPROVAL',targets=(ref(reviewed),),outcome='ACCEPT',rationale='Reviewed plan',decided_by=ACTOR)
    plan=next_rev(reviewed,'APPROVED',approval=ref(approval).model_dump(mode='json'))
    statement=Statement(id=uid(304),text='Supported assertion',statement_type='FACTUAL',support='SOURCE_BACKED',refs=(ref(f),),citations=(ref(citation),))
    draft_obj=draft().model_copy(update={'plan':ref(plan),'snapshot_id':snap.id,'snapshot_hash':digest(snap),'sections':(SectionText(section=ref(section),statements=(statement,)),)})
    entities=inputs+(acceptance,proposed,reviewed,approval,plan,draft_obj)
    return dict(entities=entities,records={ref(x):x for x in entities},snapshot=snap,acceptance=acceptance,plan=plan,draft=draft_obj,section=section,citation=citation,filing=filing,request=request,institution=inst)


class RemediationTests(unittest.TestCase):
    def rejects(self,code,fn,*args,**kwargs):
        with self.assertRaises(Violation) as error:fn(*args,**kwargs)
        self.assertEqual(error.exception.code,code)

    def test_agr_001_snapshot_acceptance_exact_binding(self):
        g=document_graph();s=g['snapshot'];a=g['acceptance']
        meta=CommandMeta(command_id=uid(400),tenant_id=s.tenant_id,case_id=s.case_id,idempotency_key=uid(401),expected_case_sequence=12,correlation_id=uid(402))
        command=AcceptSnapshot(operation='AcceptSnapshot',meta=meta,snapshot=s,decision=ref(a))
        validate_accept_snapshot(command,g['records'])
        for changes in ({'id':uid(999)},{'case_sequence':13}):
            with self.subTest(changes=changes):
                self.rejects('SNAPSHOT_APPROVAL_MISMATCH',validate_accept_snapshot,command.model_copy(update={'snapshot':s.model_copy(update=changes)}),g['records'])
        self.rejects('CROSS_CASE',validate_accept_snapshot,command.model_copy(update={'meta':meta.model_copy(update={'tenant_id':uid(999)})}),g['records'])
        with self.assertRaises(ValidationError):
            Decision.model_validate_json(a.model_copy(update={'snapshot_target':None}).model_dump_json())

    def test_agr_001_snapshot_acceptance_requires_human_accept(self):
        g=document_graph()
        for change in ({'outcome':'ABSTAIN'},{'outcome':'REJECT'},{'status':'REVOKED'},{'decided_by':Actor(id=uid(900),kind='AI')}):
            with self.subTest(change=change):
                self.rejects('HUMAN_APPROVAL_REQUIRED',validate_snapshot_acceptance,g['snapshot'],g['acceptance'].model_copy(update=change),g['records'])

    def test_agr_002_approval_cannot_be_reused_for_another_render(self):
        args=gate_inputs();result=evaluate_release(*args)
        self.assertEqual(result.eligibility,'FINAL')
        self.assertEqual(result.receipt.approval_hash,digest(args[3]))
        self.assertEqual(result.receipt.runs[0].content_hash,digest(args[1]))
        self.assertEqual(result.receipt.case_sequence,args[4].current_case_sequence)
        args[1]=args[1].model_copy(update={'render_hashes':('b'*64,)})
        args[6]=('b'*64,)
        denied=evaluate_release(*args)
        self.assertIn('RENDER_APPROVAL_MISMATCH',denied.reasons)
        self.assertIsNone(denied.receipt)
        args[3]=args[3].model_copy(update={'render_target':args[3].render_target.model_copy(update={'render_hashes':args[6]})})
        self.assertEqual(evaluate_release(*args).eligibility,'FINAL')

    def test_agr_002_receipt_and_approval_fail_closed(self):
        args=gate_inputs();result=evaluate_release(*args)
        for changes in ({'receipt':None},{'render_hashes':('b'*64,)},{'eligibility':'DRAFT'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                ReleaseResult.model_validate_json(result.model_copy(update=changes).model_dump_json())
        for changes in ({'snapshot_id':uid(999)},{'draft_hash':'b'*64},{'tenant_id':uid(999)}):
            with self.subTest(changes=changes):
                a=gate_inputs();a[3]=a[3].model_copy(update={'render_target':a[3].render_target.model_copy(update=changes)})
                self.assertIn('RENDER_APPROVAL_MISMATCH',evaluate_release(*a).reasons)

    def finding(self):
        return ValidationFinding(**common(500),kind='ValidationFinding',status='OPEN',run_id=uid(50),target=ref(fact()),target_hash=digest(fact()),layer='V4',code='TEST',severity='BLOCKER',message='Test',path='/')

    def test_agr_003_finding_content_is_immutable(self):
        f=self.finding()
        changes={'severity':'INFO','run_id':str(uid(99)),'target':ref(party()).model_dump(mode='json'),'target_hash':'b'*64,'layer':'V1','code':'OTHER','message':'Other','path':'/other'}
        for field,value in changes.items():
            with self.subTest(field=field):self.rejects('IMMUTABLE_CONTENT',validate_revision,f,next_rev(f,**{field:value}))

    def test_agr_003_resolution_requires_exact_human_decision(self):
        f=self.finding()
        decision=Decision(**common(501),kind='Decision',status='RECORDED',decision_type='FINDING_RESOLUTION',targets=(ref(f),),outcome='ACCEPT',rationale='Reviewed',decided_by=ACTOR)
        new=next_rev(f,'RESOLVED',resolution=ref(decision).model_dump(mode='json'))
        records={ref(f):f,ref(decision):decision}
        validate_revision(f,new);validate_state(new,records)
        records[ref(decision)]=decision.model_copy(update={'targets':(ref(party()),)})
        self.rejects('HUMAN_APPROVAL_REQUIRED',validate_state,new,records)

    def test_agr_004_reuse_fact_and_citation_across_statements(self):
        g=document_graph();d=g['draft'];s=d.sections[0]
        second=s.statements[0].model_copy(update={'id':uid(800)})
        new=d.model_copy(update={'sections':(s.model_copy(update={'statements':s.statements+(second,)}),)})
        entities=g['entities'][:-1]+(new,)
        validate_graph(entities,{source().id:source()})
        duplicate=s.statements[0].model_copy(update={'refs':(ref(fact()),ref(fact()))})
        bad=d.model_copy(update={'sections':(s.model_copy(update={'statements':(duplicate,)}),)})
        self.rejects('DUPLICATE_REFERENCE',validate_graph,g['entities'][:-1]+(bad,),{source().id:source()})

    def test_agr_004_participation_uniqueness_is_party_and_role(self):
        g=document_graph()
        participants=(Participation(party=ref(party()),role='a',represented_by=ref(party())),Participation(party=ref(party()),role='b',represented_by=ref(party())))
        p=Proceeding(**common(600),kind='Proceeding',status='PLANNED',proceeding_type='test',institution=ref(g['institution']),participants=participants)
        validate_graph(g['entities']+(p,),{source().id:source()})
        bad=p.model_copy(update={'participants':(participants[0],participants[0])})
        self.rejects('DUPLICATE_REFERENCE',validate_graph,g['entities']+(bad,),{source().id:source()})

    def test_agr_005_required_citation_is_counted_in_ai_and_domain(self):
        g=document_graph();d=g['draft'];section=d.sections[0];contract=g['section'].contract
        request=AIRequest(request_id=uid(700),tenant_id=d.tenant_id,case_id=d.case_id,task='DRAFTING',snapshot_id=d.snapshot_id,snapshot_hash=d.snapshot_hash,input_refs=contract.allowed_inputs,section_contract=contract,prompt=PIN,output_contract=PIN,data_policy=PIN)
        result=AIResult(request_id=request.request_id,snapshot_hash=d.snapshot_hash,disposition='PROPOSE',proposals=(),section=section,missing_information=(),reason=None)
        validate_ai(result,request)
        validate_state(d,g['records'],snapshot=g['snapshot'],snapshot_approval=g['acceptance'])
        for citations in ((),(Ref(kind='Citation',id=uid(999),revision=1),)):
            with self.subTest(citations=citations):
                bad_section=section.model_copy(update={'statements':(section.statements[0].model_copy(update={'citations':citations}),)})
                self.rejects('SECTION_CONTRACT',validate_ai,result.model_copy(update={'section':bad_section}),request)
                self.rejects('SECTION_CONTRACT',validate_state,d.model_copy(update={'sections':(bad_section,)}),g['records'],snapshot=g['snapshot'],snapshot_approval=g['acceptance'])

    def test_agr_006_snapshot_source_closure(self):
        g=document_graph();snap=g['snapshot'];records=g['records']
        validate_snapshot(snap,records)
        for sources,code in (((),'PROVENANCE_MISSING'),((source().model_copy(update={'content_hash':'b'*64}),),'INVALID_HASH'),((source().model_copy(update={'tenant_id':uid(999)}),),'CROSS_CASE')):
            with self.subTest(code=code):self.rejects(code,validate_snapshot,snap.model_copy(update={'sources':sources}),records)
        with self.assertRaises(ValidationError):Snapshot.model_validate_json(snap.model_copy(update={'sources':(source(),source())}).model_dump_json())

    def test_agr_006_plan_draft_snapshot_and_acceptance(self):
        g=document_graph()
        self.rejects('SNAPSHOT_ACCEPTANCE_REQUIRED',validate_state,g['draft'],g['records'])
        for changes in ({'snapshot_id':uid(999)},{'snapshot_hash':'b'*64}):
            with self.subTest(changes=changes):
                self.rejects('SNAPSHOT_MISMATCH',validate_state,g['draft'].model_copy(update=changes),g['records'],snapshot=g['snapshot'],snapshot_approval=g['acceptance'])

    def test_agr_006_used_input_must_belong_to_snapshot(self):
        g=document_graph();snap=g['snapshot']
        # A valid smaller snapshot does not contain the citation/section/plan inputs.
        es=(case(),party(),evidence(),fact())
        smaller=snap.model_copy(update={'members':tuple(SnapshotMember(ref=ref(e),content_hash=digest(e)) for e in es),'heads':tuple(ref(e) for e in es)})
        acceptance=g['acceptance'].model_copy(update={'snapshot_target':g['acceptance'].snapshot_target.model_copy(update={'snapshot_hash':digest(smaller)})})
        plan=g['plan'].model_copy(update={'input_snapshot_hash':digest(smaller)})
        records=dict(g['records']);records[ref(plan)]=plan
        d=g['draft'].model_copy(update={'snapshot_hash':digest(smaller)})
        self.rejects('SNAPSHOT_NOT_CLOSED',validate_state,d,records,snapshot=smaller,snapshot_approval=acceptance)

    def test_agr_007_proceeding_parent_cycles(self):
        g=document_graph()
        p=Proceeding(**common(600),kind='Proceeding',status='PLANNED',proceeding_type='test',institution=ref(g['institution']),participants=(Participation(party=ref(party()),role='a'),))
        child=Proceeding(**common(601),kind='Proceeding',status='PLANNED',proceeding_type='test',institution=p.institution,participants=p.participants,parent_proceeding=ref(p))
        validate_graph(g['entities']+(p,child),{source().id:source()})
        for parent in (ref(p),ref(child)):
            with self.subTest(parent=parent):self.rejects('CYCLE',validate_graph,g['entities']+(p.model_copy(update={'parent_proceeding':parent}),child),{source().id:source()})

    def test_agr_007_deadline_satisfaction(self):
        deadline=Deadline(**common(650),kind='Deadline',status='SATISFIED',trigger=ref(fact()),rules=(),due_at=NOW,timezone='Europe/Warsaw',calendar_pin=PIN,computation_trace=())
        self.rejects('RESOLUTION_REQUIRED',validate_state,deadline,{})
        g=document_graph();validate_state(deadline.model_copy(update={'satisfaction':ref(g['filing'])}),g['records'])

    def test_agr_007_plan_filing_ownership(self):
        g=document_graph();plan=g['plan']
        validate_graph(g['entities'],{source().id:source()})
        bad=plan.model_copy(update={'recipient':ref(party())})
        self.rejects('RECIPIENT_MISMATCH',validate_graph,tuple(bad if x==plan else x for x in g['entities']),{source().id:source()})
        other=g['filing'].model_copy(update={'id':uid(999)})
        request=g['request'].model_copy(update={'filing':ref(other)})
        entities=tuple(request if x==g['request'] else x for x in g['entities'])+(other,)
        self.rejects('REQUEST_OWNERSHIP',validate_graph,entities,{source().id:source()})


if __name__=='__main__':unittest.main()
