from datetime import datetime, timezone
from uuid import UUID
from lukart_work.domain.models import *
from lukart_work.contracts.messages import *
from lukart_work.validation.rules import digest,ref

def uid(i):return UUID(int=i)
NOW=datetime(2026,9,14,tzinfo=timezone.utc)
H='a'*64
PIN=VersionPin(id='fixture',version='1.0.0',content_hash=H)
ACTOR=Actor(id=uid(900),kind='HUMAN')
PROV=Provenance(actor=ACTOR,operation_id=uid(901),method='MANUAL',inputs=(),anchors=(),rationale='Synthetic test input')

def common(i):return dict(schema_version='1.0.0',id=uid(i),tenant_id=uid(1000),case_id=uid(1),revision=1,previous_hash=None,created_at=NOW,recorded_at=NOW,provenance=PROV)
def case():return Case(**common(1),kind='Case',status='OPEN',title='Synthetic case',jurisdiction='PL',owner_id=uid(900),retention_policy=PIN)
def party():return Party(**common(2),kind='Party',status='UNVERIFIED',party_type='PERSON',display_name='Test Party',identity_evidence=())
def source():return SourceDocument(id=uid(100),tenant_id=uid(1000),case_id=uid(1),content_hash=H,media_type='text/plain',byte_length=5,object_key='synthetic/source',received_at=NOW,actor=ACTOR,retention_policy=PIN)
def anchor():return SourceAnchor(document_id=uid(100),document_hash=H,locator=Locator(unit='RECORD',value='1',fragment_hash=H))
def evidence():return Evidence(**common(3),kind='Evidence',status='REGISTERED',evidence_type='DOCUMENT',description='Test receipt',source=anchor(),authenticity='UNKNOWN')
def fact():
    c=common(4);c['provenance']=PROV.model_copy(update={'anchors':(anchor(),)})
    return Fact(**c,kind='Fact',status='CANDIDATE',statement='Payment asserted',support='SOURCE_BACKED',evidence=(ref(evidence()),),subjects=(ref(party()),),key_fact=True)
def next_rev(e,status=None,**changes):
    data=e.model_dump(mode='json');data.update(revision=e.revision+1,previous_hash=digest(e),status=status or e.status)
    data.update(changes)
    import json
    return type(e).model_validate_json(json.dumps(data))
def draft():
    statement=Statement(id=uid(40),text='Synthetic supported statement',statement_type='FACTUAL',support='SOURCE_BACKED',refs=(ref(fact()),),citations=())
    return Draft(**common(10),kind='Draft',status='RENDERED',plan=Ref(kind='DocumentPlan',id=uid(20),revision=1),snapshot_id=uid(30),snapshot_hash=H,sections=(SectionText(section=Ref(kind='Section',id=uid(21),revision=1),statements=(statement,)),),reproduction=ReproductionManifest(knowledge=(),rule_set=PIN,prompts=(PIN,),models=(PIN,),provider=PIN,model_parameters_hash=H,generator=PIN,validators=(PIN,),render_profile=PIN,input_hash=H,raw_output_hash=H))
def gate_inputs():
    d=draft()
    a=Decision(**common(11),kind='Decision',status='RECORDED',decision_type='DOCUMENT_APPROVAL',targets=(ref(d),),outcome='ACCEPT',rationale='Synthetic acceptance',decided_by=ACTOR)
    run=ValidationRun(id=uid(50),tenant_id=d.tenant_id,case_id=d.case_id,draft=ref(d),draft_hash=digest(d),snapshot_hash=H,policy=PIN,completed_at=NOW,checks=tuple(CheckResult(check=x,outcome='PASS',validator=PIN) for x in REQUIRED_CHECKS),findings=(),render_hashes=(H,),execution_manifest_hash=H)
    fresh=FreshnessAssessment(target=ref(d),snapshot_hash=H,current_case_sequence=1,state='CURRENT',changed_inputs=())
    return [d,run,(),a,fresh,PIN,(H,)]
