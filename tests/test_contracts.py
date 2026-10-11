import json
import unittest
from pathlib import Path
from pydantic import ValidationError
from tests.fixtures import *
from lukart_work.validation.rules import *
from lukart_work.domain.lifecycle import INITIAL,TRANSITIONS

class ContractTests(unittest.TestCase):
    def test_python_version_spec_matches_canonical_pyproject_requirements(self):
        import tomllib
        root = Path(__file__).resolve().parents[1]
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        expected_python = pyproject.get("project", {}).get("requires-python", ">=3.11")
        package_report = json.loads((root / "reports/package-validation.json").read_text(encoding="utf-8"))
        self.assertEqual(package_report["report_schema_version"], 2)
        self.assertEqual(package_report["requires_python"], expected_python)
        self.assertEqual(package_report["python"], package_report["requires_python"])
        self.assertNotIn("runtime_python_version", package_report)
    def code(self,code,fn,*args):
        with self.assertRaises(Violation) as c:fn(*args)
        self.assertEqual(c.exception.code,code)
    def test_23_entities_and_lifecycles(self):
        self.assertEqual(len(ENTITIES),23)
        self.assertEqual(set(TRANSITIONS),{e.__name__ for e in ENTITIES})
        for e in ENTITIES:
            self.assertEqual(set(e.model_fields['status'].annotation.__args__),{s for pair in TRANSITIONS[e.__name__] for s in pair})
    def test_generated_artifacts_use_canonical_lf(self):
        root=Path(__file__).resolve().parents[1]
        paths=(
            list((root/'schemas').glob('*.json'))
            +list((root/'examples').glob('*.json'))
            +[
                root/'docs/02-entity-catalog.md',
                root/'reports/package-validation.json',
                root/'tests/golden_cases/source_to_fact.json',
            ]
        )
        for path in paths:
            with self.subTest(path=path.relative_to(root)):
                self.assertNotIn(b'\r\n',path.read_bytes())
    def test_roundtrip(self):self.assertEqual(parse_entity(case().model_dump_json()),case())
    def test_extra_field_rejected(self):
        d=json.loads(case().model_dump_json());d['ui_state']='FINAL'
        with self.assertRaises(ValidationError):parse_entity(json.dumps(d))
    def test_boolean_revision_rejected(self):
        d=json.loads(case().model_dump_json());d['revision']=True
        with self.assertRaises(ValidationError):parse_entity(json.dumps(d))
    def test_naive_timestamp_rejected(self):
        d=json.loads(case().model_dump_json());d['created_at']='2026-09-14T00:00:00'
        with self.assertRaises(ValidationError):parse_entity(json.dumps(d))
    def test_negative_money(self):
        with self.assertRaises(ValidationError):Money(amount='-1',currency='PLN')
    def test_immutable(self):
        with self.assertRaises(ValidationError):case().title='changed'
    def test_hash_key_order(self):self.assertEqual(digest({'b':2,'a':1}),digest({'a':1,'b':2}))
    def test_valid_graph(self):self.assertEqual(len(validate_graph((case(),party(),evidence(),fact()),{source().id:source()})),4)
    def test_broken_reference(self):self.code('BROKEN_REFERENCE',validate_graph,(case(),fact()),{source().id:source()})
    def test_cross_case(self):
        p=party().model_copy(update={'case_id':uid(555)})
        other=case().model_copy(update={'id':uid(555),'case_id':uid(555)})
        self.code('CROSS_CASE',validate_graph,(case(),other,p,evidence(),fact()),{source().id:source()})
    def test_wrong_reference_type(self):
        f=fact().model_copy(update={'evidence':(ref(party()),)})
        self.code('REFERENCE_TYPE',validate_graph,(case(),party(),f),{source().id:source()})
    def test_missing_source(self):self.code('PROVENANCE_MISSING',validate_graph,(case(),evidence()),{})
    def test_source_hash_changed(self):
        s=source().model_copy(update={'content_hash':'b'*64})
        self.code('INVALID_HASH',validate_graph,(case(),evidence()),{s.id:s})
    def test_duplicate_refs(self):
        f=fact().model_copy(update={'evidence':(ref(evidence()),ref(evidence()))})
        self.code('DUPLICATE_REFERENCE',validate_graph,(case(),party(),evidence(),f),{source().id:source()})
    def test_transition(self):validate_revision(case(),next_rev(case(),'SUSPENDED'))
    def test_transition_skip(self):self.code('INVALID_TRANSITION',validate_revision,case(),next_rev(case(),'ARCHIVED'))
    def test_revision_hash(self):self.code('CONFLICT',validate_revision,case(),next_rev(case()).model_copy(update={'previous_hash':'b'*64}))
    def test_draft_content_locked(self):self.code('IMMUTABLE_CONTENT',validate_revision,draft(),next_rev(draft(),sections=[]))
    def test_fact_confirm_without_acceptance(self):
        with self.assertRaises(ValidationError):next_rev(fact(),'CONFIRMED')
    def test_party_approval_required(self):self.code('HUMAN_APPROVAL_REQUIRED',validate_state,next_rev(party(),'VERIFIED'),{})
    def test_human_approval_happy(self):
        p=party();d=Decision(**common(60),kind='Decision',status='RECORDED',decision_type='IDENTITY',targets=(ref(p),),outcome='ACCEPT',rationale='Review',decided_by=ACTOR)
        new=next_rev(p,'VERIFIED',verification_decision=ref(d).model_dump(mode='json'))
        validate_state(new,{ref(d):d,ref(p):p})
    def test_approval_content_substitution(self):
        p=party();d=Decision(**common(60),kind='Decision',status='RECORDED',decision_type='IDENTITY',targets=(ref(p),),outcome='ACCEPT',rationale='Review',decided_by=ACTOR)
        new=next_rev(p,'VERIFIED',verification_decision=ref(d).model_dump(mode='json'),display_name='Different person')
        self.code('APPROVAL_CONTENT_CHANGED',validate_state,new,{ref(d):d,ref(p):p})
    def test_dag_propagation(self):
        a,b,c=ref(fact()),ref(party()),ref(draft())
        edges=(DependencyEdge(source=a,target=b,input_hash=H),DependencyEdge(source=b,target=c,input_hash=H))
        self.assertEqual(affected((a,),edges),{b,c})
    def test_dag_cycle(self):
        a,b=ref(fact()),ref(party())
        self.code('CYCLE',affected,(a,),(DependencyEdge(source=a,target=b,input_hash=H),DependencyEdge(source=b,target=a,input_hash=H)))
    def test_invalid_kg_predicate(self):
        e=KnowledgeEdge(id=uid(90),tenant_id=uid(1000),case_id=uid(1),predicate='REFERS_TO',source=ref(fact()),target=ref(party()),provenance=PROV)
        self.code('REFERENCE_TYPE',validate_knowledge_edge,e,{})
    def test_idempotent_replay(self):
        l=RevisionLedger();r=l.append(case(),0,0,uid(77));self.assertEqual(r,l.append(case(),0,0,uid(77)));self.assertEqual(len(l.events),1)
    def test_idempotency_conflict(self):
        l=RevisionLedger();l.append(case(),0,0,uid(77));self.code('IDEMPOTENCY_CONFLICT',l.append,case().model_copy(update={'title':'Other'}),0,0,uid(77))
    def test_concurrency_conflict(self):
        l=RevisionLedger();l.append(case(),0,0,uid(77));l.append(next_rev(case(),'SUSPENDED'),1,1,uid(78))
        self.code('CONFLICT',l.append,next_rev(case(),'CLOSED'),1,1,uid(79));self.assertEqual(len(l.events),2)
    def test_creation_cannot_skip_lifecycle(self):self.code('INVALID_TRANSITION',RevisionLedger().append,draft(),0,0,uid(77))
    def test_snapshot(self):
        c=case();snap=Snapshot(schema_version='1.0.0',id=uid(30),tenant_id=c.tenant_id,case_id=c.case_id,case_sequence=1,created_at=NOW,members=(SnapshotMember(ref=ref(c),content_hash=digest(c)),),heads=(ref(c),),sources=(),knowledge_pins=(),rule_set=PIN,policy=PIN)
        validate_snapshot(snap,{ref(c):c})
        self.code('INVALID_HASH',validate_snapshot,snap,{ref(c):c.model_copy(update={'title':'changed'})})
    def test_inference_requires_label(self):
        with self.assertRaises(ValidationError):Statement(id=uid(10),text='Inference',statement_type='INFERENCE',support='INFERRED',refs=(ref(fact()),),citations=())
    def test_abstain(self):AIResult(request_id=uid(88),snapshot_hash=H,disposition='ABSTAIN',proposals=(),section=None,missing_information=('Evidence',),reason='Insufficient data')
    def test_malformed_ai(self):
        with self.assertRaises(ValidationError):AIResult.model_validate_json('{"status":"FINAL"}')
    def test_ai_extra_authority(self):
        d=dict(request_id=str(uid(88)),snapshot_hash=H,disposition='ABSTAIN',proposals=[],section=None,missing_information=[],reason='Unknown',approve=True)
        with self.assertRaises(ValidationError):AIResult.model_validate_json(json.dumps(d))
    def test_ai_unknown_refs(self):
        request=AIRequest(request_id=uid(88),tenant_id=uid(1000),case_id=uid(1),task='EXTRACTION',snapshot_id=uid(30),snapshot_hash=H,input_refs=(),section_contract=None,prompt=PIN,output_contract=PIN,data_policy=PIN)
        p=AIProposal(proposal_id=uid(89),proposed_kind='Fact',statement='Injected',support='SOURCE_BACKED',source_refs=(ref(fact()),),anchors=(),uncertainty='UNKNOWN')
        r=AIResult(request_id=uid(88),snapshot_hash=H,disposition='PROPOSE',proposals=(p,),section=None,missing_information=(),reason=None)
        self.code('BROKEN_REFERENCE',validate_ai,r,request)

class GateTests(unittest.TestCase):
    def test_complete_gate_contract(self):self.assertEqual(evaluate_release(*gate_inputs()).eligibility,'FINAL')
    def test_all_nonpass_check_outcomes(self):
        for status in ('FAIL','UNKNOWN','NOT_RUN'):
            a=gate_inputs();a[1]=a[1].model_copy(update={'checks':(a[1].checks[0].model_copy(update={'outcome':status}),)+a[1].checks[1:]})
            self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_missing_and_duplicate_checks(self):
        for change in ('missing','duplicate'):
            a=gate_inputs();a[1]=a[1].model_copy(update={'checks':a[1].checks[:-1] if change=='missing' else a[1].checks+(a[1].checks[0],)})
            self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_all_blocking_severities_including_fake_resolution(self):
        for severity in ('ERROR','BLOCKER','CRITICAL'):
            for status in ('OPEN','RESOLVED','FALSE_POSITIVE'):
                a=gate_inputs();d,run=a[:2]
                f=ValidationFinding(**common(80),kind='ValidationFinding',status=status,run_id=run.id,target=ref(d),target_hash=digest(d),layer='V4',code='TEST',severity=severity,message='Synthetic',path='/')
                a[1]=run.model_copy(update={'findings':(ref(f),)});a[2]=(f,)
                self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_stale(self):
        a=gate_inputs();a[4]=a[4].model_copy(update={'state':'STALE'});self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_changed_render(self):
        a=gate_inputs();a[6]=('b'*64,);self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_changed_draft_hash(self):
        a=gate_inputs();a[1]=a[1].model_copy(update={'draft_hash':'b'*64});self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_ai_cannot_approve(self):
        a=gate_inputs();a[3]=a[3].model_copy(update={'decided_by':Actor(id=uid(900),kind='AI')});self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_wrong_approval_target(self):
        a=gate_inputs();a[3]=a[3].model_copy(update={'targets':(ref(fact()),)});self.assertEqual(evaluate_release(*a).eligibility,'DRAFT')
    def test_unsupported_final(self):
        a=gate_inputs();s=a[0].sections[0];st=s.statements[0].model_copy(update={'support':'UNSUPPORTED','refs':()})
        a[0]=a[0].model_copy(update={'sections':(s.model_copy(update={'statements':(st,)}),)})
        self.assertIn('UNSUPPORTED',evaluate_release(*a).reasons)
    def test_cross_case_approval(self):
        a=gate_inputs();a[3]=a[3].model_copy(update={'case_id':uid(999)})
        self.assertIn('CROSS_CASE',evaluate_release(*a).reasons)
    def test_generated_is_not_rendered(self):
        a=gate_inputs();a[0]=a[0].model_copy(update={'status':'GENERATED'});self.assertIn('NOT_RENDERED',evaluate_release(*a).reasons)

if __name__=='__main__':unittest.main()
