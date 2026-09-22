"""Synthetic Stage 11 rendering fixture. No real case data."""
from uuid import UUID

from lukart_work.contracts.messages import RenderRequest, SemanticDocument
from lukart_work.domain.models import (
    Draft, Ref, Request, Section, SectionContract, SectionText, Statement,
)
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.rendering.service import authorization_binding
from tests.fixtures import H, PIN, anchor, common, evidence, fact, party, ref, uid


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

    base_reproduction = __import__("tests.fixtures", fromlist=["draft"]).draft().reproduction
    d = Draft(
        **common(10),
        kind="Draft",
        status="VALIDATED",
        plan=Ref(kind="DocumentPlan", id=uid(20), revision=1),
        snapshot_id=uid(30),
        snapshot_hash=H,
        sections=(section_text,),
        reproduction=base_reproduction,
        supersedes=None,
    )

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
        tenant_id=d.tenant_id,
        case_id=d.case_id,
        draft=ref(d),
        snapshot_hash=d.snapshot_hash,
        header="WNIOSEK O PONOWNE ROZPATRZENIE SPRAWY",
        parties=(ref(p),),
        requests=(ref(request),),
        sections=d.sections,
        attachments=(anchor(),),
        signature_party=ref(p),
    )

    records = {
        ref(d): d,
        ref(p): p,
        ref(e): e,
        ref(f): f,
        ref(section): section,
        ref(request): request,
    }
    render_profile = profile_pin(OFFICIAL_PL_V1)
    request_contract = RenderRequest(
        document=document,
        profile=render_profile,
        authorization_hash=authorization_binding(document, render_profile),
    )
    return request_contract, records
