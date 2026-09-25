"""UNIVERSUM: minimal deterministic Factory execution kernel."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable

SHA=re.compile(r"^[0-9a-f]{40}$")
def check_sha(v,n):
    if not SHA.fullmatch(v): raise ValueError(f"{n}: exact lowercase 40-hex SHA required")

class FailureClass(str,Enum):
    INFRA="INFRA";RUNNER="RUNNER";QUEUE="QUEUE";TEST="TEST";CODE="CODE";CONFIG="CONFIG";MANIFEST="MANIFEST";PROVENANCE="PROVENANCE";SCHEMA="SCHEMA";PERFORMANCE="PERFORMANCE";AUTHORIZATION="AUTHORIZATION";EXTERNAL_DEPENDENCY="EXTERNAL_DEPENDENCY";UNKNOWN="UNKNOWN"
class GateState(str,Enum):
    UNKNOWN="UNKNOWN";PENDING="PENDING";PASS="PASS";FAIL="FAIL";STALE="STALE";NOT_REQUIRED="NOT_REQUIRED"
class ClosureState(str,Enum):
    RESTORE_CURRENT_STATE="RESTORE_CURRENT_STATE";IDENTIFY_DELTA="IDENTIFY_DELTA";CLASSIFY_FAILURE="CLASSIFY_FAILURE";IDENTIFY_CRITICAL_PATH="IDENTIFY_CRITICAL_PATH";MINIMUM_SAFE_REPAIR="MINIMUM_SAFE_REPAIR";TARGETED_VERIFICATION="TARGETED_VERIFICATION";CLOSURE_BUNDLE="CLOSURE_BUNDLE";MANIFEST="MANIFEST";CANDIDATE_FREEZE="CANDIDATE_FREEZE";FINAL_EXACT_SHA_CI="FINAL_EXACT_SHA_CI";INDEPENDENT_REVIEW="INDEPENDENT_REVIEW";HUMAN_MERGE_GATE="HUMAN_MERGE_GATE";LANDING="LANDING";POST_LANDING_VERIFICATION="POST_LANDING_VERIFICATION";CLOSURE_RECEIPT="CLOSURE_RECEIPT";CLOSED="CLOSED";BLOCKED="BLOCKED"
class NextAction(str,Enum):
    MINIMUM_SAFE_REPAIR="MINIMUM_SAFE_REPAIR";RESOLVE_EXECUTION_ENVIRONMENT="RESOLVE_EXECUTION_ENVIRONMENT";TARGETED_VERIFICATION="TARGETED_VERIFICATION";FULL_REGRESSION="FULL_REGRESSION";BUILD_CLOSURE_BUNDLE="BUILD_CLOSURE_BUNDLE";STABILIZE_MANIFEST="STABILIZE_MANIFEST";FREEZE_CANDIDATE="FREEZE_CANDIDATE";FINAL_EXACT_SHA_CI="FINAL_EXACT_SHA_CI";INDEPENDENT_REVIEW_BOUNDARY="INDEPENDENT_REVIEW_BOUNDARY";HUMAN_MERGE_GATE="HUMAN_MERGE_GATE";LAND="LAND";POST_LANDING_VERIFICATION="POST_LANDING_VERIFICATION";POST_LANDING_REPAIR="POST_LANDING_REPAIR";WRITE_CLOSURE_RECEIPT="WRITE_CLOSURE_RECEIPT";CLOSED="CLOSED"
class FullCIReason(str,Enum):
    NEW_SEMANTIC_DEFECT="NEW_SEMANTIC_DEFECT";PIPELINE_DESIGN_GAP="PIPELINE_DESIGN_GAP";MANIFEST_ORDERING_GAP="MANIFEST_ORDERING_GAP";DOC_FREEZE_GAP="DOC_FREEZE_GAP";INFRA_FAILURE="INFRA_FAILURE";OTHER_JUSTIFIED="OTHER_JUSTIFIED"
class FrozenMutationReason(str,Enum):
    P0_P1="P0_P1";FINAL_GATE_DEFECT="FINAL_GATE_DEFECT";CANONICAL_REQUIREMENT="CANONICAL_REQUIREMENT"
class SupersessionClass(str,Enum):
    CURRENT="CURRENT";SUPERSEDED="SUPERSEDED";PROTECTED_EVIDENCE="PROTECTED_EVIDENCE"

FINAL_CI_WORKFLOW="stage14.yml"
INDEPENDENT_REVIEW_WORKFLOW="independent-review"

def _sha(v,n):
    if not SHA.fullmatch(v): raise ValueError(f"{n}: exact lowercase 40-hex SHA required")

@dataclass(frozen=True)
class RestoredState:
    main_sha:str;main_tree:str;previous_stage:int;previous_stage_closed:bool
    def __post_init__(self):
        _sha(self.main_sha,"main_sha");_sha(self.main_tree,"main_tree")
class LiveStateRestore:
    @staticmethod
    def restore(**k):
        s=RestoredState(**k)
        if not s.previous_stage_closed: raise ValueError("previous stage not closed")
        return s

@dataclass(frozen=True)
class Delta:
    paths:tuple[str,...];semantic:bool;manifest_only:bool;documentation_only:bool;workflow_sensitive:bool;targeted_suites:tuple[str,...]
class DeltaClassifier:
    @classmethod
    def classify(cls,paths:Iterable[str]):
        p=tuple(sorted({x.replace("\\","/") for x in paths}))
        if not p:return Delta((),False,False,False,False,())
        m=p==("reports/manifest.sha256.json",);d=all(x.startswith("docs/") for x in p);w=any(x.startswith(".github/workflows/") for x in p)
        s=w or any(x.startswith(("lukart_work/","contracts/","schemas/","scripts/")) for x in p)
        q={f"stage{int(z.group(1)):02d}" for x in p if (z:=re.search(r"stage(\d+)",x,re.I))}
        if s and not q:q.add("affected")
        return Delta(p,s,m,d,w,tuple(sorted(q)))

class FailureClassifier:
    ORDER=((FailureClass.AUTHORIZATION,{"authorization","permission","policy"}),(FailureClass.PROVENANCE,{"provenance","identity","binding"}),(FailureClass.SCHEMA,{"schema","contract"}),(FailureClass.MANIFEST,{"manifest"}),(FailureClass.RUNNER,{"runner","runner_unavailable"}),(FailureClass.QUEUE,{"queue","queued"}),(FailureClass.INFRA,{"infra","service","database"}),(FailureClass.PERFORMANCE,{"performance","benchmark"}),(FailureClass.CONFIG,{"config"}),(FailureClass.TEST,{"test","assertion"}),(FailureClass.CODE,{"code","exception","syntax"}),(FailureClass.EXTERNAL_DEPENDENCY,{"external","dependency"}))
    @classmethod
    def classify(cls,signals):
        v={x.strip().lower() for x in signals if x and x.strip()}
        return next((k for k,t in cls.ORDER if v&t),FailureClass.UNKNOWN)

@dataclass(frozen=True)
class EvidenceRecord:
    source_sha:str;tree_sha:str;workflow:str;terminal:bool;passed:bool;invalidated:bool=False
    def __post_init__(self):_sha(self.source_sha,"source_sha");_sha(self.tree_sha,"tree_sha")
class EvidenceReusePolicy:
    @staticmethod
    def can_reuse(r,*,source_sha,tree_sha,workflow):
        _sha(source_sha,"source_sha");_sha(tree_sha,"tree_sha")
        return (r.source_sha,r.tree_sha,r.workflow)==(source_sha,tree_sha,workflow) and r.terminal and r.passed and not r.invalidated

@dataclass(frozen=True)
class WorkflowExecution:
    run_id:int;source_sha:str;terminal:bool;passed:bool;required_evidence:bool=False
    def __post_init__(self):_sha(self.source_sha,"source_sha")
class SupersessionAnalyzer:
    @staticmethod
    def classify(r,*,candidate_sha):
        _sha(candidate_sha,"candidate_sha")
        if r.source_sha==candidate_sha:return SupersessionClass.CURRENT
        if r.required_evidence and r.terminal and r.passed:return SupersessionClass.PROTECTED_EVIDENCE
        return SupersessionClass.SUPERSEDED
    @classmethod
    def blocks_candidate(cls,r,*,candidate_sha):
        return cls.classify(r,candidate_sha=candidate_sha)==SupersessionClass.CURRENT and not (r.terminal and r.passed)

@dataclass
class CIBudget:
    full_ci_run_count:int=0;reasons:list[FullCIReason]=field(default_factory=list)
    def consume(self,reason=None):
        if self.full_ci_run_count>=2 and reason is None:raise ValueError("third full CI needs reason")
        self.full_ci_run_count+=1
        if reason is not None:self.reasons.append(reason)
@dataclass
class CandidateFreeze:
    frozen_sha:str|None=None
    @property
    def frozen(self):return self.frozen_sha is not None
    def freeze(self,sha):
        _sha(sha,"candidate_sha")
        if self.frozen and self.frozen_sha!=sha:raise ValueError("candidate already frozen")
        self.frozen_sha=sha
    def mutation_allowed(self,reason):return not self.frozen or reason in set(FrozenMutationReason)

@dataclass(frozen=True)
class ClosureBundle:
    implementation_docs:bool;acceptance:bool;red_team:bool;preflight:bool;generated_evidence:bool;golden_updates_justified:bool
    @property
    def complete(self):return all(vars(self).values())
class ClosureBundlePlanner:
    REQUIRED_FIELDS=("implementation_docs","acceptance","red_team","preflight","generated_evidence","golden_updates_justified")
    @classmethod
    def missing(cls,b):return tuple(n for n in cls.REQUIRED_FIELDS if not getattr(b,n))
    @classmethod
    def ready(cls,b):return not cls.missing(b)

EMPTY=ClosureBundle(False,False,False,False,False,False)
@dataclass(frozen=True)
class ExecutionSnapshot:
    current_sha:str;current_tree:str;focused_tests:GateState=GateState.PENDING;full_regression:GateState=GateState.PENDING;closure_bundle:ClosureBundle=EMPTY;manifest:GateState=GateState.PENDING;candidate_frozen:bool=False;final_exact_sha_ci:GateState=GateState.PENDING;final_exact_sha_evidence:EvidenceRecord|None=None;independent_review:GateState=GateState.PENDING;independent_review_evidence:EvidenceRecord|None=None;human_merge_required:bool=True;human_merge_authorized:bool=False;landed:bool=False;post_landing:GateState=GateState.PENDING;closure_receipt_written:bool=False;active_failure:FailureClass|None=None;runner_available:bool=True
    def __post_init__(self):
        _sha(self.current_sha,"current_sha");_sha(self.current_tree,"current_tree")
        if self.human_merge_required is not True:raise ValueError("HUMAN merge gate is mandatory")
@dataclass(frozen=True)
class PlanStep:state:ClosureState;action:NextAction;reason:str

class CriticalPathPlanner:
    EXEC={FailureClass.INFRA,FailureClass.RUNNER,FailureClass.QUEUE,FailureClass.EXTERNAL_DEPENDENCY}
    @staticmethod
    def _bound_pass(s,e,workflow):
        return e is not None and EvidenceReusePolicy.can_reuse(e,source_sha=s.current_sha,tree_sha=s.current_tree,workflow=workflow)
    @classmethod
    def plan(cls,s):
        P=PlanStep
        if s.active_failure in cls.EXEC or not s.runner_available:return P(ClosureState.CLASSIFY_FAILURE,NextAction.RESOLVE_EXECUTION_ENVIRONMENT,"execution environment")
        if s.active_failure not in (None,FailureClass.MANIFEST):return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"classified failure")
        if s.focused_tests==GateState.FAIL:return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"focused fail")
        if s.focused_tests!=GateState.PASS:return P(ClosureState.TARGETED_VERIFICATION,NextAction.TARGETED_VERIFICATION,"targeted first")
        if s.full_regression==GateState.FAIL:return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"regression fail")
        if s.full_regression!=GateState.PASS:return P(ClosureState.TARGETED_VERIFICATION,NextAction.FULL_REGRESSION,"full regression")
        if not s.closure_bundle.complete:return P(ClosureState.CLOSURE_BUNDLE,NextAction.BUILD_CLOSURE_BUNDLE,"closure batch")
        if s.manifest!=GateState.PASS:return P(ClosureState.MANIFEST,NextAction.STABILIZE_MANIFEST,"manifest before freeze")
        if not s.candidate_frozen:return P(ClosureState.CANDIDATE_FREEZE,NextAction.FREEZE_CANDIDATE,"freeze")
        if s.final_exact_sha_ci==GateState.FAIL:return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"final CI fail")
        if s.final_exact_sha_ci!=GateState.PASS:return P(ClosureState.FINAL_EXACT_SHA_CI,NextAction.FINAL_EXACT_SHA_CI,"final exact-SHA CI")
        if not cls._bound_pass(s,s.final_exact_sha_evidence,FINAL_CI_WORKFLOW):return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"unbound final exact-SHA CI PASS")
        if s.independent_review==GateState.FAIL:return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"review fail")
        if s.independent_review!=GateState.PASS:return P(ClosureState.INDEPENDENT_REVIEW,NextAction.INDEPENDENT_REVIEW_BOUNDARY,"independent boundary")
        if not cls._bound_pass(s,s.independent_review_evidence,INDEPENDENT_REVIEW_WORKFLOW):return P(ClosureState.MINIMUM_SAFE_REPAIR,NextAction.MINIMUM_SAFE_REPAIR,"unbound independent review PASS")
        if not s.human_merge_authorized:return P(ClosureState.HUMAN_MERGE_GATE,NextAction.HUMAN_MERGE_GATE,"HUMAN gate")
        if not s.landed:return P(ClosureState.LANDING,NextAction.LAND,"landing")
        if s.post_landing==GateState.FAIL:return P(ClosureState.POST_LANDING_VERIFICATION,NextAction.POST_LANDING_REPAIR,"post fail")
        if s.post_landing!=GateState.PASS:return P(ClosureState.POST_LANDING_VERIFICATION,NextAction.POST_LANDING_VERIFICATION,"post verify")
        if not s.closure_receipt_written:return P(ClosureState.CLOSURE_RECEIPT,NextAction.WRITE_CLOSURE_RECEIPT,"receipt")
        return P(ClosureState.CLOSED,NextAction.CLOSED,"closed")
class NextActionResolver(CriticalPathPlanner):pass
class HumanGateResolver:
    @staticmethod
    def merge_permitted(*,independent_review,human_merge_required,human_merge_authorized):
        return independent_review==GateState.PASS and human_merge_required is True and human_merge_authorized is True
@dataclass
class ExecutionMetrics:
    candidate_sha_count:int=0;full_ci_run_count:int=0;targeted_test_run_count:int=0;repair_loop_count:int=0;manual_intervention_count:int=0;superseded_run_count:int=0;avoidable_ci_count:int=0;manifest_loop_count:int=0;closure_gate_count:int=0
    def as_mapping(self):return dict(vars(self))
