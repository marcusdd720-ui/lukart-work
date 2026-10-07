from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import get_args
from uuid import UUID, uuid5

from lukart_work.contracts.messages import AIResult, CommandResult, DomainError
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.requests import Operation
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor, Ref, VersionPin
from lukart_work.drafting.manual_provider import ManualAttestedDraftingProvider
from lukart_work.facts.contracts import FactOperation
from lukart_work.finalization.contracts import FINAL_PACKAGE_MEMBER_NAMES, FinalPackageProfile, FinalPackageRecord, FinalizationRelease, semantic_profile_pin
from lukart_work.operator import GeneratorPismOperator
from lukart_work.planner.contracts import PlannerOperation
from lukart_work.procedural.contracts import ProceduralOperation
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.storage.objects import RetentionPolicies
from lukart_work.type_packs.pl_pre_payment_1.fixture import positive_fixture
from lukart_work.type_packs.runtime import runtime_profile
from lukart_work.validation.contracts import SEMANTIC_CHECKS
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.rules import digest

ROOT = Path(__file__).resolve().parents[1]
TYPE_ID = "PL-PRE-PAYMENT-1"
NS = UUID("eeea4bd3-6fd0-4b6d-9635-26af6ae48a4e")

def pin(name: str) -> VersionPin:
    return VersionPin(id=f"urn:lukart:operator-e2e:{name}", version="1.0.0", content_hash=sha256(name.encode()).hexdigest())

def current_sha() -> str:
    value = (os.environ.get("TESTED_SHA") or "").strip()
    if not value:
        value = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SystemExit(f"invalid tested SHA: {value!r}")
    return value

class OperatorE2E:
    def __init__(self, tested_sha: str, output: Path):
        dsn = os.environ.get("LUKART_TEST_DSN")
        if not dsn:
            raise SystemExit("LUKART_TEST_DSN is required; use an isolated synthetic PostgreSQL database")
        self.tested_sha = tested_sha
        self.output = output
        self.fixture = positive_fixture()
        self.runtime = runtime_profile(TYPE_ID)
        self.tenant, self.case_id = self.fixture.tenant_id, self.fixture.case_id
        self.actor = Actor(id=uuid5(NS, "human-operator"), kind="HUMAN")
        self.sequence = 0
        self.counter = 0
        self.retention_pin = pin("retention")
        self.rule_pin = pin("rules")
        self.prompt_pin = pin("prompt")
        self.model_pin = pin("manual-host-model")
        self.provider_pin = pin("manual-provider")
        self.generator_pin = pin("controlled-generator")
        self.output_pin = pin("ai-result-contract")
        self.data_policy_pin = pin("synthetic-data-only")
        self.validator_pin = pin("operator-verifier")
        self.model_parameters_hash = sha256(b"generator-pism-operator-e2e").hexdigest()

        self.authority = TokenAuthority()
        actions = (
            frozenset(get_args(Operation))
            | frozenset(get_args(FactOperation))
            | frozenset(get_args(PlannerOperation))
            | frozenset(get_args(ProceduralOperation))
            | frozenset({
                "GetRevision","GetCaseHead","GetSnapshot","GetProvenance","GetAffectedDrafts","GetSource",
                "GetDocumentPlan","AssessProcedure","RecordValidationReview","RevokeValidationReview",
                "ResolveValidationFinding","GetValidation","RenderDraft","ApproveFinalDocument",
                "RequestFinalRelease","AssembleFinalPackage","GetFinalization","GetFinalRelease",
                "ReadFinalArtifact","GetFinalPackage","ReadFinalPackageMember","AuditRead",
            })
        )
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.provider = ManualAttestedDraftingProvider(
            provider=self.provider_pin, model=self.model_pin, generator=self.generator_pin,
            model_parameters_hash=self.model_parameters_hash,
        )
        drafting_profile = {
            "profile":"QUICK","prompt":self.prompt_pin.model_dump(mode="json"),
            "model":self.model_pin.model_dump(mode="json"),"provider":self.provider_pin.model_dump(mode="json"),
            "generator":self.generator_pin.model_dump(mode="json"),"output_contract":self.output_pin.model_dump(mode="json"),
            "data_policy":self.data_policy_pin.model_dump(mode="json"),"validators":[self.validator_pin.model_dump(mode="json")],
            "render_profile":profile_pin(OFFICIAL_PL_V1).model_dump(mode="json"),
            "model_parameters_hash":self.model_parameters_hash,
        }
        package_profile = FinalPackageProfile(
            profile_id="urn:lukart:work:generator-pism-e2e-package", version="1.0.0",
            build_revision=tested_sha,
            baseline_contract_hash=sha256((ROOT/"acceptance"/"product-baseline-v1.json").read_bytes()).hexdigest(),
        )
        self.repo = PostgresRepository(dsn, storage=True, retention_policies=RetentionPolicies())
        self.operator = GeneratorPismOperator(
            repository=self.repo, authority=self.authority, type_id=TYPE_ID,
            drafting_profiles={"QUICK":drafting_profile}, provider=self.provider, package_profile=package_profile,
        )
        assert self.operator.validate_intake(self.fixture) == self.fixture

    def _ids(self, label):
        self.counter += 1
        command_id = uuid5(NS, f"{self.tested_sha}:{self.counter}:{label}")
        return command_id, uuid5(command_id,"idempotency"), uuid5(command_id,"correlation")

    def meta(self, label):
        c,i,r = self._ids(label)
        return {"command_id":str(c),"tenant_id":str(self.tenant),"case_id":str(self.case_id),
                "idempotency_key":str(i),"expected_case_sequence":self.sequence,"correlation_id":str(r)}

    @staticmethod
    def _assert_command(value, label):
        if isinstance(value, DomainError):
            raise AssertionError(f"{label}: domain error {value.code}: {value}")
        if not isinstance(value, CommandResult) or value.state != "APPLIED":
            raise AssertionError(f"{label}: unexpected result {value!r}")
        return value

    def core_apply(self, operation, data=None, target=None, *, inputs=(), anchors=()):
        req={"contract":"urn:lukart:work:CoreRequest:1.0.0","operation":operation,"meta":self.meta(f"core:{operation}"),
             "target":target.model_dump(mode="json") if target else None,"data":data or {},
             "inputs":[x.model_dump(mode="json") if hasattr(x,"model_dump") else x for x in inputs],
             "anchors":list(anchors),"rationale":"Synthetic Generator Pism operator E2E"}
        res=self._assert_command(self.operator.execute_core(req,self.token),operation); self.sequence=res.case_sequence
        return res,req

    def fact_apply(self, operation, target, data=None):
        req={"contract":"urn:lukart:work:FactEvidenceRequest:1.0.0","operation":operation,"meta":self.meta(f"facts:{operation}"),
             "target":target.model_dump(mode="json"),"data":data or {},"inputs":[],"anchors":[],
             "rationale":"Synthetic explicit HUMAN fact/evidence review"}
        res=self._assert_command(self.operator.execute_fact_evidence(req,self.token),operation); self.sequence=res.case_sequence
        return res

    def proc_apply(self, operation, data=None, target=None):
        req={"contract":"urn:lukart:work:ProceduralRequest:1.0.0","operation":operation,"meta":self.meta(f"procedure:{operation}"),
             "target":target.model_dump(mode="json") if target else None,"data":data or {},"inputs":[],"anchors":[],
             "rationale":"Synthetic explicit HUMAN procedural intent"}
        res=self._assert_command(self.operator.execute_procedural(req,self.token),operation); self.sequence=res.case_sequence
        return res

    def plan_apply(self, operation, data=None, target=None):
        req={"contract":"urn:lukart:work:PlannerRequest:1.0.0","operation":operation,"meta":self.meta(f"plan:{operation}"),
             "target":target.model_dump(mode="json") if target else None,"data":data or {},
             "rationale":"Synthetic Generator Pism planning intent"}
        res=self._assert_command(self.operator.execute_plan(req,self.token),operation); self.sequence=res.case_sequence
        return res

    def get(self, target):
        val=self.operator.query_core({"contract":"urn:lukart:work:CoreQuery:1.0.0","operation":"GetRevision",
            "tenant_id":str(self.tenant),"case_id":str(self.case_id),"target":target.model_dump(mode="json"),"object_id":None},self.token)
        if isinstance(val,DomainError): raise AssertionError(f"GetRevision {target}: {val.code}")
        return val.entity

    def snapshot(self):
        _,req=self.core_apply("CreateSnapshot",{"rule_set":self.rule_pin.model_dump(mode="json"),
            "policy":self.data_policy_pin.model_dump(mode="json"),"knowledge_pins":[]})
        sid=uuid5(UUID(req["meta"]["command_id"]),"snapshot")
        val=self.operator.query_core({"contract":"urn:lukart:work:CoreQuery:1.0.0","operation":"GetSnapshot",
            "tenant_id":str(self.tenant),"case_id":str(self.case_id),"target":None,"object_id":str(sid)},self.token)
        if isinstance(val,DomainError): raise AssertionError(f"GetSnapshot: {val.code}")
        return val.snapshot

    def decision(self, decision_type, targets, **extra):
        data={"decision_type":decision_type,"targets":[x.model_dump(mode="json") for x in targets],
              "outcome":"ACCEPT","rationale":f"Synthetic HUMAN {decision_type} decision",**extra}
        return self.core_apply("RecordDecision",data)[0].refs[0]

    def final_request(self, operation, draft, **extra):
        return {"contract":"urn:lukart:work:FinalizationRequest:1.0.0","operation":operation,
                "meta":self.meta(f"final:{operation}"),
                "target":Ref(kind="Draft",id=draft.id,revision=draft.revision).model_dump(mode="json"),
                "draft_hash":digest(draft),"snapshot_hash":draft.snapshot_hash,
                "rationale":"Synthetic explicit HUMAN finalization intent",**extra}

    def run(self):
        self.core_apply("CreateCase",{"title":"Generator Pism public operator E2E","jurisdiction":"PL",
                                     "retention_policy":self.retention_pin.model_dump(mode="json")})
        sender=self.core_apply("AddParty",{"party_type":"PERSON","display_name":self.fixture.sender_name,"identity_evidence":[]})[0].refs[0]
        sender_dec=self.decision("IDENTITY",[sender])
        sender=self.core_apply("VerifyParty",{"decision":sender_dec.model_dump(mode="json")},sender)[0].refs[0]
        recipient=self.core_apply("AddParty",{"party_type":"PERSON","display_name":self.fixture.recipient_name,"identity_evidence":[]})[0].refs[0]
        recipient_dec=self.decision("IDENTITY",[recipient])
        recipient=self.core_apply("VerifyParty",{"decision":recipient_dec.model_dump(mode="json")},recipient)[0].refs[0]

        source_bytes=b"Synthetic payment receipt."; source_hash=sha256(source_bytes).hexdigest()
        _,src_req=self.core_apply("RegisterSource",{"content_base64":base64.b64encode(source_bytes).decode("ascii"),
            "media_type":"text/plain","retention_policy":self.retention_pin.model_dump(mode="json")})
        source_id=uuid5(UUID(src_req["meta"]["command_id"]),"source")
        anchor={"document_id":str(source_id),"document_hash":source_hash,
                "locator":{"unit":"RECORD","value":"1","fragment_hash":source_hash}}
        evidence=self.core_apply("AddEvidence",{"evidence_type":"DOCUMENT","description":"Synthetic accepted payment evidence",
            "source":anchor,"authenticity":"UNKNOWN"})[0].refs[0]
        evidence=self.fact_apply("ReviewEvidence",evidence).refs[0]
        evidence=self.fact_apply("AcceptEvidence",evidence).refs[0]
        fact=self.core_apply("AddFact",{"statement":"Synthetic payment remained outstanding at the accepted due date.",
            "support":"SOURCE_BACKED","evidence":[evidence.model_dump(mode="json")],
            "subjects":[recipient.model_dump(mode="json")],"event_date":"2026-09-30","key_fact":True},anchors=[anchor])[0].refs[0]
        fact=self.fact_apply("ReviewFact",fact).refs[0]
        fact_dec=self.decision("FACT_ACCEPTANCE",[fact])
        fact=self.fact_apply("ConfirmFact",fact,{"decision":fact_dec.model_dump(mode="json")}).refs[0]

        legal_source=self.proc_apply("RegisterProceduralSource",{"source_id":str(source_id),
            "registry_id":"urn:lukart:operator-e2e:legal-source","registry_version":"2026-10-08","jurisdiction":"PL",
            "source_type":"LAW","title":"Synthetic operator E2E legal source","identifier":"SYN-OP-E2E-LAW",
            "effective_period":{"start":"2026-01-01","end":None},"source_uri":"https://example.invalid/operator-e2e-law",
            "authority_level":"BINDING"}).refs[0]
        legal_source=self.proc_apply("VerifyProceduralSource",target=legal_source).refs[0]
        legal_rule=self.proc_apply("RegisterProceduralRule",{"sources":[legal_source.model_dump(mode="json")],
            "statement":"Synthetic source-backed rule for operator E2E.","jurisdiction":"PL",
            "effective_period":{"start":"2026-01-01","end":None},
            "applicable_document_types":[self.runtime.document_type.model_dump(mode="json")],"interpretation":"SETTLED",
            "spec":{"category":"FORMAL_REQUIREMENT","code":"SYN-OP-E2E","applies_when":[],
                    "requirements":[{"path":"/case/status","operator":"PRESENT","operand":None}],
                    "severity":"BLOCKER","deadline":None}}).refs[0]
        reviewed_rule=self.proc_apply("ReviewProceduralRule",target=legal_rule).refs[0]
        int_dec=self.decision("INTERPRETATION",[reviewed_rule])
        legal_rule=self.proc_apply("ActivateProceduralRule",{"decision":int_dec.model_dump(mode="json")},reviewed_rule).refs[0]

        citation=self.core_apply("AddCitation",{"source":legal_source.model_dump(mode="json"),
            "locator":{"unit":"RECORD","value":"1","fragment_hash":source_hash},
            "supported":legal_rule.model_dump(mode="json"),"quotation":source_bytes.decode()},
            inputs=(legal_source,legal_rule))[0].refs[0]
        citation=self.core_apply("BindCitation",target=citation)[0].refs[0]
        citation=self.core_apply("VerifyCitation",target=citation)[0].refs[0]

        filing=self.core_apply("AddFiling",{"document_type":self.runtime.document_type.model_dump(mode="json"),
            "direction":"OUTGOING","recipient":recipient.model_dump(mode="json"),"authors":[sender.model_dump(mode="json")]})[0].refs[0]
        issue=self.core_apply("AddIssue",{"question":"Synthetic outstanding payment issue",
            "facts":[fact.model_dump(mode="json")],"rules":[legal_rule.model_dump(mode="json")]})[0].refs[0]
        claim=self.core_apply("AddClaim",{"claim_type":"ASSERTION","statement":"Synthetic payment claim",
            "claimant":sender.model_dump(mode="json"),"issues":[issue.model_dump(mode="json")],
            "facts":[fact.model_dump(mode="json")],"rules":[legal_rule.model_dump(mode="json")],"support":"SOURCE_BACKED"})[0].refs[0]
        objective=self.core_apply("AddRequest",{"filing":filing.model_dump(mode="json"),"request_type":"PAYMENT_DEMAND",
            "text":"Synthetic requested payment outcome.","claims":[claim.model_dump(mode="json")],
            "evidence":[evidence.model_dump(mode="json")]})[0].refs[0]

        snap=self.snapshot()
        snap_dec=self.decision("SNAPSHOT_ACCEPTANCE",[Ref(kind="Case",id=self.case_id,revision=1)],
            snapshot_target={"tenant_id":str(self.tenant),"case_id":str(self.case_id),"snapshot_id":str(snap.id),"snapshot_hash":digest(snap)})
        self.core_apply("AcceptSnapshot",{"snapshot_id":str(snap.id),"decision":snap_dec.model_dump(mode="json")})

        allowed=[fact.model_dump(mode="json"),evidence.model_dump(mode="json"),claim.model_dump(mode="json"),
                 objective.model_dump(mode="json"),legal_rule.model_dump(mode="json"),citation.model_dump(mode="json")]
        sections=[]
        for idx,stype in enumerate(self.runtime.plan_sections):
            sections.append({"section_type":stype,"title":stype.replace("_"," ").title(),"arguments":[],
                "allowed_inputs":allowed,
                "required_inputs":([fact.model_dump(mode="json"),evidence.model_dump(mode="json"),objective.model_dump(mode="json"),
                                    legal_rule.model_dump(mode="json"),citation.model_dump(mode="json")] if idx==0
                                   else [fact.model_dump(mode="json"),evidence.model_dump(mode="json")]),
                "allowed_claims":[claim.model_dump(mode="json")],
                "forbidden":["UNSUPPORTED_ASSERTION","UNMARKED_INFERENCE","NEW_FACT","NEW_LEGAL_RULE"],
                "requirements":(["REQUESTS","ATTACHMENTS","CITATIONS"] if idx==0 else [])})
        planned=self.plan_apply("PlanDocument",{"snapshot_id":str(snap.id),"snapshot_hash":digest(snap),
            "filing":filing.model_dump(mode="json"),"objectives":[objective.model_dump(mode="json")],
            "position_scope":"Synthetic bounded payment-demand scope","argument_order":[],
            "evidence":[evidence.model_dump(mode="json")],"sections":sections})
        proposed_plan,section_refs=planned.refs[0],tuple(planned.refs[1:])
        reviewed_plan=self.plan_apply("ReviewDocumentPlan",target=proposed_plan).refs[0]
        plan_dec=self.decision("PLAN_APPROVAL",[reviewed_plan])
        approved_plan=self.plan_apply("ApproveDocumentPlan",{"decision":plan_dec.model_dump(mode="json")},reviewed_plan).refs[0]

        draft_meta=self.meta("draft:GenerateDocument")
        draft_req={"operation":"GenerateDocument","meta":draft_meta,"document_type":self.runtime.document_type.model_dump(mode="json"),
                   "objective_ids":[str(objective.id)],"snapshot_id":str(snap.id),"snapshot_hash":digest(snap),
                   "plan":approved_plan.model_dump(mode="json"),"profile":"QUICK"}
        draft_cmd=UUID(draft_meta["command_id"])
        for idx,sref in enumerate(section_refs):
            statements=[{"id":str(uuid5(draft_cmd,f"provided-fact:{idx}")),"text":"Synthetic source-backed payment fact.",
                         "statement_type":"FACTUAL","support":"SOURCE_BACKED",
                         "refs":[fact.model_dump(mode="json"),evidence.model_dump(mode="json")],"citations":[],"inference_label":None}]
            if idx==0:
                statements += [
                    {"id":str(uuid5(draft_cmd,"provided-request")),"text":"Synthetic requested payment outcome.","statement_type":"REQUEST",
                     "support":"SOURCE_BACKED","refs":[objective.model_dump(mode="json")],"citations":[],"inference_label":None},
                    {"id":str(uuid5(draft_cmd,"provided-legal")),"text":"Synthetic legal proposition supported by the verified source.",
                     "statement_type":"LEGAL","support":"SOURCE_BACKED","refs":[legal_rule.model_dump(mode="json")],
                     "citations":[citation.model_dump(mode="json")],"inference_label":None},
                ]
            self.provider.supply(AIResult.model_validate({"request_id":str(uuid5(draft_cmd,f"drafting-request:{idx}")),
                "snapshot_hash":digest(snap),"disposition":"PROPOSE","proposals":[],
                "section":{"section":sref.model_dump(mode="json"),"statements":statements},
                "missing_information":[],"reason":None}))
        draft_res=self._assert_command(self.operator.execute_draft(draft_req,self.token),"GenerateDocument"); self.sequence=draft_res.case_sequence
        draft=self.get(draft_res.refs[0]); assert draft.status=="GENERATED"

        review_meta=self.meta("validation:RecordValidationReview")
        review_req={"contract":"urn:lukart:work:ValidationRequest:1.0.0","operation":"RecordValidationReview","meta":review_meta,
            "target":Ref(kind="Draft",id=draft.id,revision=draft.revision).model_dump(mode="json"),
            "draft_hash":digest(draft),"snapshot_hash":draft.snapshot_hash,"validation_policy":validation_pin().model_dump(mode="json"),
            "review_id":None,"assessments":[{"check":c,"outcome":"PASS","rationale":"Synthetic explicit HUMAN semantic assessment"} for c in SEMANTIC_CHECKS],
            "issues":[],"decision":None,"resolution":None,"rationale":"Synthetic explicit HUMAN validation review",
            "inputs":[],"anchors":[],"procedural_context":[]}
        rr=self._assert_command(self.operator.execute_validation(review_req,self.token),"RecordValidationReview"); self.sequence=rr.case_sequence
        review_id=uuid5(UUID(review_meta["command_id"]),"review")
        val_meta=self.meta("validation:ValidateDraft")
        val_req={"contract":"urn:lukart:work:ValidationRequest:1.0.0","operation":"ValidateDraft","meta":val_meta,
            "target":Ref(kind="Draft",id=draft.id,revision=draft.revision).model_dump(mode="json"),
            "draft_hash":digest(draft),"snapshot_hash":draft.snapshot_hash,"validation_policy":validation_pin().model_dump(mode="json"),
            "review_id":str(review_id),"assessments":[],"issues":[],"decision":None,"resolution":None,
            "rationale":"Synthetic Generator Pism validation","inputs":[],"anchors":[],"procedural_context":[]}
        vr=self._assert_command(self.operator.execute_validation(val_req,self.token),"ValidateDraft"); self.sequence=vr.case_sequence
        validated=self.get(vr.refs[0]); assert validated.status=="VALIDATED"
        run_id=uuid5(UUID(val_meta["command_id"]),"validation-run")

        render_req=self.final_request("RenderDraft",validated,validation_run_id=str(run_id),
            semantic_profile=semantic_profile_pin(self.runtime.finalization_profile).model_dump(mode="json"))
        rres=self._assert_command(self.operator.execute_finalization(render_req,self.token),"RenderDraft"); self.sequence=rres.case_sequence
        render_id=uuid5(UUID(render_req["meta"]["command_id"]),"persisted-render")
        def fq(operation, **extra):
            q={"contract":"urn:lukart:work:FinalizationQuery:1.0.0","operation":operation,
               "tenant_id":str(self.tenant),"case_id":str(self.case_id),"render_id":str(render_id),
               "format":None,"member":None}; q.update(extra)
            return self.operator.query_finalization(q,self.token)
        docx=fq("ReadFinalArtifact",format="DOCX"); pdf=fq("ReadFinalArtifact",format="PDF")
        assert isinstance(docx,bytes) and docx.startswith(b"PK")
        assert isinstance(pdf,bytes) and pdf.startswith(b"%PDF")
        areq=self.final_request("ApproveFinalDocument",validated,render_id=str(render_id))
        ares=self._assert_command(self.operator.execute_finalization(areq,self.token),"ApproveFinalDocument"); self.sequence=ares.case_sequence
        rendered=self.get(ares.refs[0]); assert rendered.status=="RENDERED"
        rel_req=self.final_request("RequestFinalRelease",rendered,render_id=str(render_id))
        rel_res=self._assert_command(self.operator.execute_finalization(rel_req,self.token),"RequestFinalRelease"); self.sequence=rel_res.case_sequence
        release=fq("GetFinalRelease"); assert isinstance(release,FinalizationRelease) and release.result.eligibility=="FINAL"
        pkg_req=self.final_request("AssembleFinalPackage",rendered,render_id=str(render_id))
        pkg_res=self._assert_command(self.operator.execute_finalization(pkg_req,self.token),"AssembleFinalPackage"); self.sequence=pkg_res.case_sequence
        package=fq("GetFinalPackage"); assert isinstance(package,FinalPackageRecord)
        assert tuple(x.name for x in package.members)==FINAL_PACKAGE_MEMBER_NAMES

        package_dir=self.output/"package"; package_dir.mkdir(parents=True,exist_ok=True); members=[]
        for member in package.members:
            body=fq("ReadFinalPackageMember",member=member.name)
            assert isinstance(body,bytes)
            assert sha256(body).hexdigest()==member.content_hash and len(body)==member.byte_length
            (package_dir/member.name).write_bytes(body)
            members.append({"name":member.name,"content_hash":member.content_hash,"byte_length":member.byte_length})
        assert members[0]["content_hash"]==sha256(docx).hexdigest()
        assert members[1]["content_hash"]==sha256(pdf).hexdigest()
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            events=tx.events(); outbox=tx.outbox(); assert events==outbox; event_count=len(events)
        evidence={"contract":"urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0","result":"PASS",
            "tested_sha":self.tested_sha,"synthetic_only":True,"human_actor_kind":self.actor.kind,
            "type_id":TYPE_ID,"type_contract_pin":self.runtime.contract_pin,
            "operator_path":["validate_intake","execute_core","execute_fact_evidence","execute_procedural","execute_plan",
                             "execute_draft","execute_validation","execute_finalization","query_finalization"],
            "render_id":str(render_id),"release_id":str(release.id),"release_eligibility":release.result.eligibility,
            "package_id":str(package.id),"package_member_count":len(package.members),"package_members":members,
            "direct_artifacts":{"final.docx":{"content_hash":sha256(docx).hexdigest(),"byte_length":len(docx)},
                                "final.pdf":{"content_hash":sha256(pdf).hexdigest(),"byte_length":len(pdf)}},
            "final_case_sequence":self.sequence,"event_count":event_count,"legal_type_admission":"HUMAN_REQUIRED"}
        self.output.mkdir(parents=True,exist_ok=True)
        ep=self.output/"evidence.json"; ep.write_text(json.dumps(evidence,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps({"result":"PASS","tested_sha":self.tested_sha,"type_id":TYPE_ID,
                          "render_id":str(render_id),"package_members":len(package.members),"evidence":str(ep)},sort_keys=True))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",default="build/generator-pism/operator-e2e")
    a=p.parse_args(); OperatorE2E(current_sha(),ROOT/a.output).run()

if __name__=="__main__":
    main()
