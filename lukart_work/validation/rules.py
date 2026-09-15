"""Deterministic contract checks. No legal truth, signatures or authorization are inferred."""
import hashlib
import json
from collections import deque
from pydantic import BaseModel, TypeAdapter
from lukart_work.domain.models import *
from lukart_work.domain.lifecycle import TRANSITIONS, INITIAL
from lukart_work.contracts.messages import *

# Authoritative relation field -> allowed target types. Nested common refs checked below.
RELATIONS={
'Case':{},
'Party':{'identity_evidence':('Evidence',),'verification_decision':('Decision',)},
'Institution':{},
'Proceeding':{'institution':('Institution',),'participants.party':('Party',),'participants.represented_by':('Party',),'parent_proceeding':('Proceeding',)},
'Filing':{'proceeding':('Proceeding',),'recipient':('Institution','Party'),'authors':('Party',)},
'Fact':{'evidence':('Evidence',),'subjects':('Party','Institution'),'acceptance':('Decision',)},
'Evidence':{'submitted_in':('Proceeding',)},
'Issue':{'facts':('Fact',),'rules':('LegalRule',),'resolution':('Decision',)},
'LegalSource':{},
'LegalRule':{'sources':('LegalSource',),'review_decision':('Decision',)},
'Claim':{'claimant':('Party',),'issues':('Issue',),'facts':('Fact',),'rules':('LegalRule',),'adoption':('Decision',)},
'Defence':{'claim':('Claim',),'party':('Party',),'facts':('Fact',),'rules':('LegalRule',),'adoption':('Decision',)},
'Argument':{'target':('Claim','Defence'),'premises':('Fact','Claim','Argument'),'rules':('LegalRule',),'assessments.basis':('Fact','Evidence','LegalRule','CounterArgument')},
'CounterArgument':{'target_argument':('Argument',),'premises':('Fact','Claim','LegalRule'),'response_argument':('Argument',)},
'Request':{'filing':('Filing',),'claims':('Claim',),'evidence':('Evidence',),'approval':('Decision',)},
'Deadline':{'proceeding':('Proceeding',),'filing':('Filing',),'trigger':('Fact',),'rules':('LegalRule',),'satisfaction':('Filing','Decision')},
'Risk':{'affected':tuple(c.__name__ for c in ENTITIES),'mitigation':('Decision','Request'),'acceptance':('Decision',)},
'Citation':{'source':('LegalSource',),'supported':('LegalRule','Argument','Claim','Section')},
'DocumentPlan':{'filing':('Filing',),'objectives':('Request',),'recipient':('Institution','Party'),'argument_order':('Argument',),'evidence':('Evidence',),'section_order':('Section',),'approval':('Decision',)},
'Section':{'filing':('Filing',),'arguments':('Argument',),'contract.allowed_inputs':('Fact','Evidence','LegalRule','Argument','Claim','Request','Citation'),'contract.required_inputs':('Fact','Evidence','LegalRule','Argument','Claim','Request','Citation'),'contract.allowed_claims':('Claim',)},
'Draft':{'plan':('DocumentPlan',),'sections.section':('Section',),'sections.statements.refs':('Fact','Evidence','LegalRule','Claim','Argument','Request'),'sections.statements.citations':('Citation',),'supersedes':('Draft',)},
'ValidationFinding':{'target':tuple(c.__name__ for c in ENTITIES),'resolution':('Decision',)},
'Decision':{'targets':tuple(c.__name__ for c in ENTITIES),'supersedes':('Decision',)}
}

class Violation(ValueError):
    def __init__(self,code): self.code=code; super().__init__(code)

def digest(value):
    if isinstance(value,BaseModel): value=value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()

def ref(entity): return Ref(kind=entity.kind,id=entity.id,revision=entity.revision)

def walk(value, cls):
    if isinstance(value,cls): yield value; return
    if isinstance(value,BaseModel):
        for name in type(value).model_fields: yield from walk(getattr(value,name),cls)
    elif isinstance(value,(tuple,list)):
        for v in value: yield from walk(v,cls)

def at(value,path):
    if not path: return list(value) if isinstance(value,tuple) else [value]
    if isinstance(value,tuple): return [y for x in value for y in at(x,path)]
    if value is None: return []
    head,*tail=path
    return at(getattr(value,head),tail)

def strict_json(raw):
    if len(raw.encode('utf-8'))>2_000_000: raise Violation('SCHEMA_INVALID')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise Violation('SCHEMA_INVALID')
            result[k]=v
        return result
    def constant(_):raise Violation('SCHEMA_INVALID')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)

def parse_entity(raw):
    return TypeAdapter(EntityPayload).validate_json(json.dumps(strict_json(raw),allow_nan=False))

def resolve(r, records, tenant, case):
    obj=records.get(r)
    if obj is None: raise Violation('BROKEN_REFERENCE')
    if (obj.tenant_id,obj.case_id)!=(tenant,case): raise Violation('CROSS_CASE')
    return obj

def validate_graph(entities, sources):
    records={ref(e):e for e in entities}
    if len(records)!=len(entities): raise Violation('DUPLICATE')
    for e in entities:
        case=next((c for c in entities if c.kind=='Case' and c.id==e.case_id and c.tenant_id==e.tenant_id),None)
        if case is None: raise Violation('BROKEN_REFERENCE')
        for r in walk(e,Ref): resolve(r,records,e.tenant_id,e.case_id)
        for path,kinds in RELATIONS[e.kind].items():
            vals=[v for v in at(e,path.split('.')) if v is not None]
            if any(v.kind not in kinds for v in vals): raise Violation('REFERENCE_TYPE')
            if len(vals)!=len(set(vals)): raise Violation('DUPLICATE_REFERENCE')
        for a in walk(e,SourceAnchor):
            s=sources.get(a.document_id)
            if s is None: raise Violation('PROVENANCE_MISSING')
            if (s.tenant_id,s.case_id)!=(e.tenant_id,e.case_id): raise Violation('CROSS_CASE')
            if s.content_hash!=a.document_hash: raise Violation('INVALID_HASH')
        if e.kind=='DocumentPlan':
            if any(records[r].filing!=e.filing for r in e.section_order): raise Violation('SECTION_OWNERSHIP')
        if e.kind=='LegalSource' and (e.content_hash!=e.anchor.document_hash or e.content_hash!=e.registry_pin.content_hash): raise Violation('INVALID_HASH')
        if e.kind=='Decision' and e.status=='RECORDED' and e.decided_by.kind!='HUMAN':
            raise Violation('HUMAN_REQUIRED')
    return records

def validate_revision(old,new):
    if (old.id,old.kind,old.tenant_id,old.case_id)!=(new.id,new.kind,new.tenant_id,new.case_id): raise Violation('IDENTITY_CHANGE')
    if new.revision!=old.revision+1 or new.previous_hash!=digest(old): raise Violation('CONFLICT')
    if old.created_at!=new.created_at or new.recorded_at<old.recorded_at: raise Violation('TIME_ORDER')
    if old.status!=new.status and (old.status,new.status) not in TRANSITIONS[old.kind]: raise Violation('INVALID_TRANSITION')
    # Material approved content cannot be edited by a same-state revision.
    locked={'DocumentPlan':('APPROVED','SUPERSEDED'),'Draft':('GENERATED','VALIDATED','APPROVED','RENDERED','CERTIFIED'),'Decision':('RECORDED','SUPERSEDED','REVOKED')}
    if old.status in locked.get(old.kind,()):
        exclude={'status','revision','previous_hash','recorded_at','provenance'}
        if old.model_dump(exclude=exclude)!=new.model_dump(exclude=exclude): raise Violation('IMMUTABLE_CONTENT')

def validate_snapshot(snapshot,records):
    for m in snapshot.members:
        e=resolve(m.ref,records,snapshot.tenant_id,snapshot.case_id)
        if digest(e)!=m.content_hash: raise Violation('INVALID_HASH')
    refs={m.ref for m in snapshot.members}
    # Closure may include historical revisions; heads identify exactly one current revision per identity.
    for m in snapshot.members:
        if not set(walk(records[m.ref],Ref))<=refs: raise Violation('SNAPSHOT_NOT_CLOSED')
    if not any(r.kind=='Case' and r.id==snapshot.case_id for r in refs): raise Violation('BROKEN_REFERENCE')

KG_PAIRS={
'SUPPORTED_BY':{('Fact','Evidence'),('Claim','Fact')},'GOVERNED_BY':{('Claim','LegalRule')},
'SUPPORTS':{('Argument','Claim'),('Argument','Defence')},'OPPOSES':{('Argument','Claim'),('Argument','Defence')},
'CHALLENGES':{('CounterArgument','Argument')},'BASED_ON':{('Request','Claim')},
'USES':{('Section','Argument')},'REFERS_TO':{('Citation','LegalSource')}}
def validate_knowledge_edge(edge,records):
    if (edge.source.kind,edge.target.kind) not in KG_PAIRS[edge.predicate]: raise Violation('REFERENCE_TYPE')
    resolve(edge.source,records,edge.tenant_id,edge.case_id);resolve(edge.target,records,edge.tenant_id,edge.case_id)

def affected(changed,edges):
    adjacency={}
    for edge in edges: adjacency.setdefault(edge.source,set()).add(edge.target)
    visiting=set();done=set()
    def visit(n):
        if n in visiting: raise Violation('CYCLE')
        if n in done:return
        visiting.add(n)
        for x in adjacency.get(n,()):visit(x)
        visiting.remove(n);done.add(n)
    for n in adjacency:visit(n)
    found=set();queue=deque(changed)
    while queue:
        for n in adjacency.get(queue.popleft(),()):
            if n not in found:found.add(n);queue.append(n)
    return frozenset(found)

def validate_ai(result,request):
    if result.request_id!=request.request_id or result.snapshot_hash!=request.snapshot_hash: raise Violation('STALE')
    allowed=set(request.input_refs)
    for p in result.proposals:
        if not set(p.source_refs)<=allowed: raise Violation('BROKEN_REFERENCE')
        if p.support=='SOURCE_BACKED' and not (p.source_refs or p.anchors): raise Violation('PROVENANCE_MISSING')
    if result.section:
        if request.task!='DRAFTING' or request.section_contract is None: raise Violation('FORBIDDEN')
        c=request.section_contract
        used={r for s in result.section.statements for r in s.refs}
        if not used<=set(c.allowed_inputs) or not set(c.required_inputs)<=used: raise Violation('FORBIDDEN')
        if any(s.support=='UNSUPPORTED' for s in result.section.statements): raise Violation('UNSUPPORTED')
        if any(r.kind=='Claim' and r not in c.allowed_claims for r in used): raise Violation('FORBIDDEN')

def evaluate_release(draft,run,findings,approval,freshness,expected_policy,render_hashes):
    """Pure evaluator over trusted repository-loaded inputs. Not a public authorization endpoint."""
    reasons=[]
    scope=(draft.tenant_id,draft.case_id)
    if (run.tenant_id,run.case_id)!=scope or (approval.tenant_id,approval.case_id)!=scope:reasons.append('CROSS_CASE')
    if run.draft!=ref(draft) or run.draft_hash!=digest(draft) or run.snapshot_hash!=draft.snapshot_hash:reasons.append('STALE_RUN')
    if run.policy!=expected_policy:reasons.append('POLICY_MISMATCH')
    checks=[c.check for c in run.checks]
    if len(checks)!=len(set(checks)) or set(checks)!=set(REQUIRED_CHECKS) or any(c.outcome!='PASS' for c in run.checks):reasons.append('CHECKS_INCOMPLETE')
    if set(run.findings)!={ref(f) for f in findings} or len(findings)!=len(run.findings):reasons.append('FINDINGS_INCOMPLETE')
    for f in findings:
        if (f.tenant_id,f.case_id)!=scope or f.run_id!=run.id or f.target!=ref(draft) or f.target_hash!=digest(draft):reasons.append('FINDING_BINDING')
        if f.severity in ('ERROR','BLOCKER','CRITICAL'):reasons.append('BLOCKING_FINDING')
    if approval.status!='RECORDED' or approval.outcome!='ACCEPT' or approval.decision_type!='DOCUMENT_APPROVAL' or approval.decided_by.kind!='HUMAN' or ref(draft) not in approval.targets:reasons.append('HUMAN_APPROVAL_REQUIRED')
    if freshness.target!=ref(draft) or freshness.snapshot_hash!=draft.snapshot_hash or freshness.state!='CURRENT' or freshness.changed_inputs:reasons.append('STALE')
    if draft.status!='RENDERED':reasons.append('NOT_RENDERED')
    if not render_hashes or tuple(run.render_hashes)!=tuple(render_hashes):reasons.append('RENDER_MISMATCH')
    if not draft.sections:reasons.append('EMPTY_DOCUMENT')
    if any(s.support=='UNSUPPORTED' for section in draft.sections for s in section.statements):reasons.append('UNSUPPORTED')
    return ReleaseResult(eligibility='DRAFT' if reasons else 'FINAL',reasons=tuple(sorted(set(reasons))),draft=ref(draft),snapshot_hash=draft.snapshot_hash,render_hashes=tuple(render_hashes))

class RevisionLedger:
    """Executable sequential contract harness ONLY. Production transaction/RLS/outbox in 02/03."""
    def __init__(self):self.records={};self.heads={};self.sequences={};self.keys={};self.events=[]
    def append(self,entity,expected_revision,expected_sequence,idempotency_key):
        scope=(entity.tenant_id,entity.case_id);key=(*scope,idempotency_key)
        h=digest({'entity':entity.model_dump(mode='json'),'expected_revision':expected_revision,'expected_sequence':expected_sequence})
        if key in self.keys:
            old_hash,result=self.keys[key]
            if h!=old_hash:raise Violation('IDEMPOTENCY_CONFLICT')
            return result
        seq=self.sequences.get(scope,0)
        if seq!=expected_sequence:raise Violation('CONFLICT')
        identity=(*scope,entity.kind,entity.id);old=self.heads.get(identity)
        if old:
            if old.revision!=expected_revision:raise Violation('CONFLICT')
            validate_revision(old,entity)
        elif expected_revision!=0 or entity.revision!=1 or entity.status!=INITIAL[entity.kind]:raise Violation('INVALID_TRANSITION')
        result=(seq+1,digest(entity))
        self.records[ref(entity)]=entity;self.heads[identity]=entity;self.sequences[scope]=seq+1
        self.keys[key]=(h,result);self.events.append((scope,seq+1,ref(entity),digest(entity)))
        return result

# Checks requiring authoritative case graph; complement schema and closed transition table.
ACCEPTANCE={
 ('Party','VERIFIED'):('verification_decision','IDENTITY'),
 ('Fact','CONFIRMED'):('acceptance','FACT_ACCEPTANCE'),
 ('Claim','ADOPTED'):('adoption','STRATEGY'),
 ('Defence','ADOPTED'):('adoption','STRATEGY'),
 ('Request','APPROVED'):('approval','REQUEST_APPROVAL'),
 ('DocumentPlan','APPROVED'):('approval','PLAN_APPROVAL'),
 ('LegalRule','ACTIVE'):('review_decision','INTERPRETATION'),
 ('Risk','ACCEPTED'):('acceptance','RISK_ACCEPTANCE')}
def validate_state(e,records):
    guard=ACCEPTANCE.get((e.kind,e.status))
    if guard:
        field,decision_type=guard;r=getattr(e,field)
        if r is None:raise Violation('HUMAN_APPROVAL_REQUIRED')
        d=resolve(r,records,e.tenant_id,e.case_id)
        # Approval targets immediately preceding immutable reviewed content.
        previous=Ref(kind=e.kind,id=e.id,revision=e.revision-1) if e.revision>1 else None
        if d.kind!='Decision' or d.decision_type!=decision_type or d.status!='RECORDED' or d.outcome!='ACCEPT' or d.decided_by.kind!='HUMAN' or previous not in d.targets:raise Violation('HUMAN_APPROVAL_REQUIRED')
        prior=resolve(previous,records,e.tenant_id,e.case_id)
        excluded={'status','revision','previous_hash','recorded_at','provenance',field}
        if prior.model_dump(exclude=excluded)!=e.model_dump(exclude=excluded):raise Violation('APPROVAL_CONTENT_CHANGED')
    if e.kind=='Claim' and e.status=='ADOPTED' and e.support=='UNSUPPORTED':raise Violation('UNSUPPORTED')
    if e.kind=='Issue' and e.status=='RESOLVED' and e.resolution is None:raise Violation('RESOLUTION_REQUIRED')
    if e.kind=='CounterArgument' and e.status=='ANSWERED' and e.response_argument is None:raise Violation('RESOLUTION_REQUIRED')
    if e.kind=='Filing' and e.status in ('SUBMITTED','ACKNOWLEDGED') and (e.submitted_at is None or e.submission_receipt is None):raise Violation('RECEIPT_REQUIRED')
    if e.kind=='LegalRule' and e.rule_type=='PROCEDURAL' and e.requirement is None:raise Violation('REQUIREMENT_REQUIRED')
    if e.kind=='ValidationFinding' and e.status!='OPEN' and e.resolution is None:raise Violation('RESOLUTION_REQUIRED')
    if e.kind=='Draft' and e.status!='PLANNED':
        plan=resolve(e.plan,records,e.tenant_id,e.case_id)
        if plan.status!='APPROVED':raise Violation('PLAN_NOT_APPROVED')
        if not e.sections or tuple(x.section for x in e.sections)!=plan.section_order:raise Violation('SECTION_ORDER')
        for section in e.sections:
            contract=resolve(section.section,records,e.tenant_id,e.case_id).contract
            used={r for statement in section.statements for r in statement.refs}
            if not used<=set(contract.allowed_inputs) or not set(contract.required_inputs)<=used:raise Violation('SECTION_CONTRACT')
