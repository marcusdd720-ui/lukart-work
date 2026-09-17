"""Technology-neutral cross-repo evidence/result contracts and adapters."""
from __future__ import annotations
import hashlib,json,math,re
from collections.abc import Mapping,Sequence
from datetime import datetime,timezone
from typing import Annotated,Literal,Union
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,model_validator

VERSION='1.0.0'; EVIDENCE_ID='urn:lukart:crossrepo:EvidenceEnvelope'; RESULT_ID='urn:lukart:crossrepo:OperationResultEnvelope'
WORK_EVIDENCE='urn:lukart:work:Evidence:1.0.0'; WORK_COMMAND='urn:lukart:work:CommandResult:1.0.0'; WORK_INGESTION='urn:lukart:work:IngestionResult:1.0.0'
ROS_ID='lukart.operation-contract.v1'; ROS_VERSION='1.0'
Ident=Annotated[str,StringConstraints(min_length=1,max_length=256,pattern=r'^[A-Za-z0-9._:/@+\-]+$')]
Text=Annotated[str,StringConstraints(min_length=1,max_length=4096)]; H64=Annotated[str,StringConstraints(pattern=r'^[0-9a-f]{64}$')]; H128=Annotated[str,StringConstraints(pattern=r'^[0-9a-f]{128}$')]; H40=Annotated[str,StringConstraints(pattern=r'^[0-9a-f]{40}$')]
class Error(ValueError):
 def __init__(self,code): self.code=code; super().__init__(code)
class V(BaseModel): model_config=ConfigDict(extra='forbid',frozen=True,strict=True)
class D256(V): algorithm:Literal['sha-256']; value:H64
class D512(V): algorithm:Literal['sha-512']; value:H128
Digest=Annotated[Union[D256,D512],Field(discriminator='algorithm')]
SCHEMA_VERSION=VERSION; EVIDENCE_SCHEMA_ID=EVIDENCE_ID; RESULT_SCHEMA_ID=RESULT_ID; ConvergenceError=Error; Sha256Digest=D256; WORK_EVIDENCE_SCHEMA_ID=WORK_EVIDENCE; WORK_COMMAND_RESULT_SCHEMA_ID=WORK_COMMAND; WORK_INGESTION_SCHEMA_ID=WORK_INGESTION; ROS_OPERATION_SCHEMA_ID=ROS_ID; ROS_OPERATION_SCHEMA_VERSION=ROS_VERSION
class SourceContract(V): schema_id:Ident; version:Text
class Actor(V): kind:Literal['HUMAN','SERVICE','AI','SYSTEM','UNKNOWN']; id:Ident
class Input(V): kind:Ident; ref:Ident; digest:Digest|None=None
class Provenance(V):
 producer:Ident; operation_id:Ident; method:Ident; actor:Actor|None=None; inputs:Annotated[tuple[Input,...],Field(max_length=64)]=(); source_digests:Annotated[tuple[Digest,...],Field(max_length=64)]=(); recorded_at:str|None=None; source_contract:SourceContract
 @model_validator(mode='after')
 def ts(self):
  if self.recorded_at is not None: timestamp(self.recorded_at)
  return self
class Content(V): digest:Digest; media_type:Text|None=None; byte_length:Annotated[int,Field(strict=True,ge=0)]|None=None
class Evidence(V): evidence_id:Ident; kind:Ident; ref:Ident; content:Content; source_revision:H40|None=None; locator:Text|None=None; provenance:Provenance
class EvidenceEnvelope(V):
 schema_id:Literal[EVIDENCE_ID]; schema_version:Literal[VERSION]; evidence:Evidence; envelope_digest:Digest
 @model_validator(mode='after')
 def bound(self):
  if digest_value({'schema_id':self.schema_id,'schema_version':self.schema_version,'evidence':self.evidence.model_dump(mode='json')},self.envelope_digest.algorithm)!=self.envelope_digest.value: raise ValueError('ENVELOPE_DIGEST_MISMATCH')
  return self
class Artifact(V): kind:Ident; ref:Ident; revision:Annotated[int,Field(strict=True,ge=1)]|None=None; digest:Digest|None=None
class NormalizedError(V): code:Ident; category:Ident; retryable:bool; message:Annotated[str,StringConstraints(min_length=1,max_length=512)]
class Outcome(V):
 operation_id:Ident; operation:Ident; status:Literal['success','failure','partial','skipped','blocked']; summary:Annotated[str,StringConstraints(max_length=1024)]; artifacts:Annotated[tuple[Artifact,...],Field(max_length=64)]=(); evidence:Annotated[tuple[EvidenceEnvelope,...],Field(max_length=64)]=(); errors:Annotated[tuple[NormalizedError,...],Field(max_length=64)]=(); provenance:Provenance
 @model_validator(mode='after')
 def semantics(self):
  if self.status=='success' and self.errors: raise ValueError('SUCCESS_WITH_ERRORS')
  if self.status=='failure' and not self.errors: raise ValueError('FAILURE_WITHOUT_ERROR')
  return self
class OperationResultEnvelope(V):
 schema_id:Literal[RESULT_ID]; schema_version:Literal[VERSION]; result:Outcome; envelope_digest:Digest
 @model_validator(mode='after')
 def bound(self):
  if digest_value({'schema_id':self.schema_id,'schema_version':self.schema_version,'result':self.result.model_dump(mode='json')},self.envelope_digest.algorithm)!=self.envelope_digest.value: raise ValueError('ENVELOPE_DIGEST_MISMATCH')
  return self

def _json(v):
 if isinstance(v,BaseModel): v=v.model_dump(mode='json')
 if v is None or isinstance(v,(str,bool,int)): return v
 if isinstance(v,float): raise Error('NON_FINITE_NUMBER' if not math.isfinite(v) else 'FLOAT_NOT_CANONICAL')
 if isinstance(v,Mapping):
  if not all(isinstance(k,str) for k in v): raise Error('NON_STRING_KEY')
  return {k:_json(x) for k,x in v.items()}
 if isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray)): return [_json(x) for x in v]
 raise Error('NON_JSON_VALUE')
def canonical_json(v): return json.dumps(_json(v),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def strict_json(raw,max_bytes=2_000_000):
 if len(raw.encode())>max_bytes: raise Error('INPUT_TOO_LARGE')
 def pairs(items):
  d={}
  for k,v in items:
   if k in d: raise Error('DUPLICATE_JSON_KEY')
   d[k]=v
  return d
 def constant(_): raise Error('NON_FINITE_NUMBER')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
def digest_value(v,algorithm='sha-256'):
 b=canonical_json(v).encode()
 if algorithm=='sha-256': return hashlib.sha256(b).hexdigest()
 if algorithm=='sha-512': return hashlib.sha512(b).hexdigest()
 raise Error('UNSUPPORTED_DIGEST_ALGORITHM')
def digest_ref(v,algorithm='sha-256'):
 if algorithm=='sha-256': return D256(algorithm=algorithm,value=digest_value(v,algorithm))
 if algorithm=='sha-512': return D512(algorithm=algorithm,value=digest_value(v,algorithm))
 raise Error('UNSUPPORTED_DIGEST_ALGORITHM')
def legacy(v,field):
 if not isinstance(v,str) or not re.fullmatch(r'[0-9a-f]{64}',v): raise Error('INVALID_LEGACY_SHA256:'+field)
 return D256(algorithm='sha-256',value=v)
def obj(v,field):
 if isinstance(v,BaseModel): v=v.model_dump(mode='json')
 if not isinstance(v,Mapping): raise Error('OBJECT_REQUIRED:'+field)
 return v
def exact(v,required,optional=(),field='object'):
 keys=set(v); req=set(required); opt=set(optional)
 if not req<=keys or keys-req-opt: raise Error('INVALID_KEYS:'+field)
def ident(v,field):
 if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9._:/@+\-]{1,256}',v): raise Error('INVALID_IDENTIFIER:'+field)
 return v
def timestamp(v):
 if not isinstance(v,str): raise Error('INVALID_TIMESTAMP')
 try: d=datetime.fromisoformat(v.replace('Z','+00:00'))
 except ValueError as e: raise Error('INVALID_TIMESTAMP') from e
 if d.tzinfo is None: raise Error('INVALID_TIMESTAMP')
 return d.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def source(schema,version): return SourceContract(schema_id=schema,version=version)
def actor(v):
 if v is None:return None
 v=obj(v,'actor'); exact(v,{'id','kind'},field='actor')
 if v['kind'] not in ('HUMAN','SERVICE','AI'): raise Error('INVALID_ACTOR_KIND')
 return Actor(kind=v['kind'],id=ident(str(v['id']),'actor.id'))
def inputs(v):
 if not isinstance(v,Sequence) or isinstance(v,(str,bytes,bytearray)) or len(v)>64: raise Error('INVALID_INPUT_REFS')
 out=[]
 for i,x in enumerate(v):
  x=obj(x,f'inputs[{i}]'); exact(x,{'kind','id','revision'},field=f'inputs[{i}]'); out.append(Input(kind=ident(x['kind'],'input.kind'),ref=ident(str(x['id']),'input.id')))
 return tuple(out)
def evidence_envelope(e,algorithm='sha-256'):
 base={'schema_id':EVIDENCE_ID,'schema_version':VERSION,'evidence':e.model_dump(mode='json')}; return EvidenceEnvelope(schema_id=EVIDENCE_ID,schema_version=VERSION,evidence=e,envelope_digest=digest_ref(base,algorithm))
def result_envelope(r,algorithm='sha-256'):
 base={'schema_id':RESULT_ID,'schema_version':VERSION,'result':r.model_dump(mode='json')}; return OperationResultEnvelope(schema_id=RESULT_ID,schema_version=VERSION,result=r,envelope_digest=digest_ref(base,algorithm))

def adapt_work_evidence(value):
 v=obj(value,'work_evidence'); required={'schema_version','id','tenant_id','case_id','revision','previous_hash','created_at','recorded_at','provenance','kind','status','evidence_type','description','source','authenticity'}; exact(v,required,{'submitted_in'},'work_evidence')
 if v['schema_version']!='1.0.0' or v['kind']!='Evidence': raise Error('UNSUPPORTED_WORK_EVIDENCE_CONTRACT')
 s=obj(v['source'],'source'); exact(s,{'document_id','document_hash','locator'},field='source'); loc=obj(s['locator'],'locator'); exact(loc,{'unit','value','fragment_hash'},field='locator'); p=obj(v['provenance'],'provenance'); exact(p,{'actor','operation_id','method','inputs','anchors','rationale'},{'tool'},'provenance')
 e=Evidence(evidence_id=ident(str(v['id']),'id'),kind=ident(v['evidence_type'],'evidence_type'),ref=ident(str(v['id']),'id'),content=Content(digest=legacy(loc['fragment_hash'],'source.locator.fragment_hash')),locator=f"{loc['unit']}:{loc['value']}",provenance=Provenance(producer='lukart-work',operation_id=ident(str(p['operation_id']),'operation_id'),method=ident(p['method'],'method'),actor=actor(p['actor']),inputs=inputs(p['inputs']),source_digests=(legacy(s['document_hash'],'source.document_hash'),),recorded_at=timestamp(v['recorded_at']),source_contract=source(WORK_EVIDENCE,'1.0.0')))
 return evidence_envelope(e)

def adapt_work_command_result(value,*,operation):
 v=obj(value,'command'); exact(v,{'command_id','state','case_sequence','refs','event_ids','errors'},field='command'); status={'APPLIED':'success','REPLAYED':'success','REJECTED':'failure'}.get(v['state'])
 if status is None: raise Error('UNSUPPORTED_COMMAND_STATE')
 arts=[]
 for i,x in enumerate(v['refs']): x=obj(x,f'refs[{i}]'); exact(x,{'kind','id','revision'},field=f'refs[{i}]'); arts.append(Artifact(kind=ident(x['kind'],'ref.kind'),ref=ident(str(x['id']),'ref.id'),revision=x['revision']))
 arts += [Artifact(kind='event',ref=ident(str(x),'event')) for x in v['event_ids']]
 errs=[]
 for i,x in enumerate(v['errors']): x=obj(x,f'errors[{i}]'); exact(x,{'code','path','message','retryable','correlation_id'},field=f'errors[{i}]'); errs.append(NormalizedError(code=ident(x['code'],'error.code'),category='domain',retryable=x['retryable'],message=x['message']))
 opid=ident(str(v['command_id']),'command_id'); r=Outcome(operation_id=opid,operation=ident(operation,'operation'),status=status,summary=f"Command result: {v['state']}",artifacts=tuple(arts),errors=tuple(errs),provenance=Provenance(producer='lukart-work',operation_id=opid,method='command',source_contract=source(WORK_COMMAND,'1.0.0'))); return result_envelope(r)

def adapt_work_ingestion_result(value):
 v=obj(value,'ingestion'); exact(v,{'contract','tenant_id','case_id','run_id','source_id','source_hash','source_byte_length','actor','recorded_at','extractor','parser','python_version','body_hash','body'},field='ingestion')
 if v['contract']!=WORK_INGESTION: raise Error('UNSUPPORTED_WORK_INGESTION_CONTRACT')
 body=obj(v['body'],'body'); status={'EXTRACTED':'success','FAILED':'failure','NEEDS_OCR':'blocked','UNSUPPORTED':'skipped','EMPTY':'blocked'}.get(body.get('status'))
 if status is None: raise Error('UNSUPPORTED_INGESTION_STATUS')
 sd,bd=legacy(v['source_hash'],'source_hash'),legacy(v['body_hash'],'body_hash'); opid=ident(str(v['run_id']),'run_id'); ref=ident(str(v['source_id']),'source_id'); a=actor(v['actor']); ts=timestamp(v['recorded_at']); sc=source(WORK_INGESTION,'1.0.0')
 ev=evidence_envelope(Evidence(evidence_id=ref,kind='source-document',ref=ref,content=Content(digest=sd,media_type=body.get('media_type'),byte_length=v['source_byte_length']),provenance=Provenance(producer='lukart-work',operation_id=opid,method='ingestion',actor=a,recorded_at=ts,source_contract=sc)))
 errs=(NormalizedError(code='INGESTION_FAILED',category='ingestion',retryable=False,message='Source ingestion failed.'),) if body.get('status')=='FAILED' else ()
 r=Outcome(operation_id=opid,operation='IngestSource',status=status,summary=f"Ingestion result: {body.get('status')}",artifacts=(Artifact(kind='ingestion-body',ref=bd.value,digest=bd),),evidence=(ev,),errors=errs,provenance=Provenance(producer='lukart-work',operation_id=opid,method='ingestion',actor=a,inputs=(Input(kind='source-document',ref=ref,digest=sd),),source_digests=(sd,bd),recorded_at=ts,source_contract=sc)); return result_envelope(r)

def adapt_ros_operation_envelope(value):
 v=obj(value,'ros'); root={'request','context','preconditions','constraints','idempotency','effects','output','evidence','errors','privacy'}; exact(v,root,field='ros'); q=obj(v['request'],'request'); exact(q,{'schema_id','version','operation_id','operation','input'},field='request')
 if q['schema_id']!=ROS_ID or q['version']!=ROS_VERSION: raise Error('UNSUPPORTED_ROS_OPERATION_CONTRACT')
 out=obj(v['output'],'output'); exact(out,{'status','summary','artifacts'},field='output'); status=out['status']
 if status not in ('success','failure','partial','skipped','blocked'): raise Error('NON_TERMINAL_ROS_RESULT')
 privacy=obj(v['privacy'],'privacy'); exact(privacy,{'scope','data_classification','cross_scope_allowed'},field='privacy')
 if privacy['cross_scope_allowed'] is not False: raise Error('CROSS_SCOPE_NOT_ALLOWED')
 opid=ident(q['operation_id'],'operation_id'); sc=source(ROS_ID,ROS_VERSION); ev=[]; items=obj(v['evidence'],'evidence'); exact(items,{'items'},field='evidence')
 if not isinstance(items['items'],Sequence) or isinstance(items['items'],(str,bytes,bytearray)) or len(items['items'])>64: raise Error('INVALID_ROS_EVIDENCE')
 for i,x in enumerate(items['items']):
  x=obj(x,f'evidence[{i}]'); exact(x,{'kind','ref'},{'sha','digest'},f'evidence[{i}]')
  if 'digest' not in x: raise Error('EVIDENCE_DIGEST_REQUIRED')
  rev=x.get('sha');
  if rev is not None and (not isinstance(rev,str) or not re.fullmatch(r'[0-9a-f]{40}',rev)): raise Error('INVALID_SOURCE_REVISION')
  ref=ident(x['ref'],'evidence.ref'); ev.append(evidence_envelope(Evidence(evidence_id=ref,kind=ident(x['kind'],'evidence.kind'),ref=ref,content=Content(digest=legacy(x['digest'],'evidence.digest')),source_revision=rev,provenance=Provenance(producer='lukart-ros',operation_id=opid,method='operation',source_contract=sc))))
 arts=tuple(Artifact(kind='artifact',ref=ident(x,'artifact')) for x in out['artifacts']); errobj=obj(v['errors'],'errors'); exact(errobj,{'items'},field='errors'); errs=[]
 for x in errobj['items']: x=obj(x,'error'); exact(x,{'code','category','retryable','message'},field='error'); errs.append(NormalizedError(code=ident(x['code'],'error.code'),category=ident(x['category'],'error.category'),retryable=x['retryable'],message=x['message']))
 if status=='failure' and not errs: raise Error('FAILURE_WITHOUT_ERROR')
 if status=='success' and errs: raise Error('SUCCESS_WITH_ERRORS')
 r=Outcome(operation_id=opid,operation=ident(q['operation'],'operation'),status=status,summary=out['summary'],artifacts=arts,evidence=tuple(ev),errors=tuple(errs),provenance=Provenance(producer='lukart-ros',operation_id=opid,method='operation',source_contract=sc)); return result_envelope(r)

def render_markdown(result):
 r=OperationResultEnvelope.model_validate(result); return f"# Operation {r.result.operation}\n\n- status: {r.result.status}\n- operation_id: {r.result.operation_id}\n- evidence: {len(r.result.evidence)}\n- artifacts: {len(r.result.artifacts)}\n- errors: {len(r.result.errors)}\n\n{r.result.summary}\n"
