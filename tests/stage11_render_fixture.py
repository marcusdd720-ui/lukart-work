"""Synthetic Stage 11 rendering fixture. No real case data."""
from uuid import UUID

from lukart_work.contracts.messages import CheckResult, RenderRequest, SemanticDocument, ValidationRun
from lukart_work.domain.models import (
    Decision, DocumentPlan, Draft, Ref, Request, Section, SectionContract, SectionText, Statement,
)
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.rendering.service import authorization_binding, derive_render_authority
from lukart_work.validation.contracts import PRE_RENDER_CHECKS, ValidationExecution, ValidationManifest, ValidationProjection
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.rules import digest
from tests.fixtures import ACTOR, H, NOW, anchor, common, evidence, fact, next_rev, party, ref, uid


def build_fixture():
    p = party().model_copy(update={"display_name": "Łukasz Testowy"})
    e = evidence()
    f = fact()

    section_ref = Ref(kind="Section", id=uid(21), revision=1)
    statement_fact = Statement(
        id=uid(40),
        text="Zażółć gęślą jaźń — wpłata została wykazana dokumentem źródłowym.",
        statement_type="FACTUAL",
        support="SOURCE_BACKED",
        refs=(ref(f), ref(e)),
        citations=(),
    )
    statement_legal = Statement(
        id=uid(41),
        text="Organ powinien odnieść się do kompletnego materiału dowodowego.",
        statement_type="LEGAL",
        support="SOURCE_BACKED",
        refs=(ref(f),),
        citations=(),
    )
    section_text = SectionText(
        section=section_ref,
        statements=(statement_fact, statement_legal),
    )

    render_profile = profile_pin(OFFICIAL_PL_V1)
    plan_approval_ref = Ref(kind="Decision", id=uid(22), revision=1)
    plan = DocumentPlan(
        **common(20),
        kind="DocumentPlan",
        status="APPROVED",
        filing=Ref(kind="Filing", id=uid(70), revision=1),
        input_snapshot_id=uid(30),
        input_snapshot_hash=H,
        objectives=(ref(f),),
        recipient=ref(p),
        position_scope="Syntetyczny zakres testowy.",
        argument_order=(),
        evidence=(ref(e),),
        section_order=(section_ref,),
        approval=plan_approval_ref,
    )
    plan_approval = Decision(
        **common(22),
        kind="Decision",
        status="RECORDED",
        decision_type="PLAN_APPROVAL",
        targets=(ref(plan),),
        outcome="ACCEPT",
        rationale="Syntetyczne zatwierdzenie planu.",
        decided_by=ACTOR,
        supersedes=None,
        snapshot_target=None,
        render_target=None,
    )
    base_reproduction = __import__("tests.fixtures", fromlist=["draft"]).draft().reproduction
    reproduction = base_reproduction.model_copy(update={"render_profile": render_profile})
    generated = Draft(
        **common(10),
        kind="Draft",
        status="GENERATED",
        plan=ref(plan),
        snapshot_id=uid(30),
        snapshot_hash=H,
        sections=(section_text,),
        reproduction=reproduction,
        supersedes=None,
    )
    validated = next_rev(generated, status="VALIDATED")

    section = Section(
        **common(21),
        kind="Section",
        status="READY",
        filing=Ref(kind="Filing", id=uid(70), revision=1),
        section_type="UZASADNIENIE",
        title="Uzasadnienie",
        arguments=(),
        contract=SectionContract(
            allowed_inputs=(ref(f), ref(e)),
            required_inputs=(),
            allowed_claims=(),
            forbidden=("UNSUPPORTED_ASSERTION", "UNMARKED_INFERENCE", "NEW_FACT", "NEW_LEGAL_RULE"),
            requirements=("CITATIONS",),
        ),
    )

    request = Request(
        **common(12),
        kind="Request",
        status="REVIEWED",
        filing=Ref(kind="Filing", id=uid(70), revision=1),
        request_type="RECONSIDERATION",
        text="Wnoszę o ponowne rozpatrzenie sprawy i zmianę zaskarżonego rozstrzygnięcia.",
        claims=(Ref(kind="Claim", id=uid(71), revision=1),),
        evidence=(ref(e),),
        approval=None,
        amount=None,
    )

    document = SemanticDocument(
        tenant_id=validated.tenant_id,
        case_id=validated.case_id,
        draft=ref(validated),
        snapshot_hash=validated.snapshot_hash,
        header="WNIOSEK O PONOWNE ROZPATRZENIE SPRAWY",
        parties=(ref(p),),
        requests=(ref(request),),
        sections=validated.sections,
        attachments=(anchor(),),
        signature_party=ref(p),
    )

    records = {
        ref(generated): generated,
        ref(validated): validated,
        ref(plan): plan,
        ref(plan_approval): plan_approval,
        ref(p): p,
        ref(e): e,
        ref(f): f,
        ref(section): section,
        ref(request): request,
    }
    policy = validation_pin()
    dependencies = tuple(sorted(
        (ref(generated), ref(plan), ref(plan_approval), ref(section), ref(request), ref(p), ref(e), ref(f)),
        key=lambda item: (item.kind, str(item.id), item.revision),
    ))
    manifest = ValidationManifest(
        policy=policy,
        draft_hash=digest(generated),
        snapshot_hash=H,
        dependency_hashes=tuple((target, digest(records[target])) for target in dependencies),
        review_hash=None,
        evaluation_date=NOW.date(),
        procedural_context=(),
    )
    run = ValidationRun(
        id=uid(50),
        tenant_id=validated.tenant_id,
        case_id=validated.case_id,
        draft=ref(generated),
        draft_hash=digest(generated),
        snapshot_hash=H,
        policy=policy,
        completed_at=NOW,
        checks=tuple(CheckResult(check=name, outcome="PASS", validator=policy) for name in PRE_RENDER_CHECKS)
            + (CheckResult(check="render", outcome="NOT_RUN", validator=policy),),
        findings=(),
        render_hashes=(),
        execution_manifest_hash=digest(manifest),
    )
    execution = ValidationExecution(
        id=run.id,
        run=run,
        output_draft=ref(validated),
        output_hash=digest(validated),
        evaluation_date=NOW.date(),
        input_sequence=1,
        committed_sequence=2,
        review=None,
        dependencies=dependencies,
        validator=policy,
        manifest=manifest,
    )
    validation = ValidationProjection(
        execution=execution,
        freshness="CURRENT",
        eligible_for_approval=True,
        reasons=(),
    )
    authority = derive_render_authority(document, records, validation, render_profile)
    request_contract = RenderRequest(
        document=document,
        profile=render_profile,
        authorization_hash=authorization_binding(document, render_profile, authority),
    )
    return request_contract, records, validation
