"""Stage 11 semantic-document builder and deterministic RenderTree compiler."""
from __future__ import annotations

from hashlib import sha256
from uuid import uuid5

from lukart_work.domain import models as m
from lukart_work.validation.rules import digest, resolve
from .contracts import (
    RenderBlock,
    RenderProfile,
    RenderTree,
    SemanticBlock,
    SemanticDocumentV2,
)

_KIND_BY_TOKEN = {
    "document.body": "PARAGRAPH",
    "document.heading.primary": "HEADING",
    "document.heading.secondary": "HEADING",
    "document.metadata": "METADATA",
    "document.party_block": "PARTY",
    "document.request": "REQUEST",
    "document.legal_basis": "LEGAL_BASIS",
    "document.quote": "QUOTE",
    "document.evidence_reference": "EVIDENCE_REFERENCE",
    "document.signature": "SIGNATURE",
    "document.attachment": "ATTACHMENT",
}


def _display_name(entity) -> str:
    if entity.kind in {"Party", "Institution"}:
        return entity.display_name if entity.kind == "Party" else entity.name
    raise ValueError("UNSUPPORTED_DISPLAY_ENTITY")


def _block_id(draft: m.Draft, ordinal: int, role: str, text: str):
    key = sha256(f"{ordinal}|{role}|{text}".encode("utf-8")).hexdigest()
    return uuid5(draft.id, key)


def build_semantic_document(draft: m.Draft, records: dict[m.Ref, m.Entity]) -> SemanticDocumentV2:
    tenant, case = draft.tenant_id, draft.case_id
    plan = resolve(draft.plan, records, tenant, case)
    if plan.kind != "DocumentPlan" or plan.status != "APPROVED":
        raise ValueError("PLAN_NOT_APPROVED")
    filing = resolve(plan.filing, records, tenant, case)
    if filing.kind != "Filing":
        raise ValueError("REFERENCE_TYPE")

    blocks: list[SemanticBlock] = []
    ordinal = 0

    def add(role: str, text: str, refs=()):
        nonlocal ordinal
        text = str(text).strip()
        if not text:
            raise ValueError("EMPTY_RENDER_TEXT")
        blocks.append(SemanticBlock(
            id=_block_id(draft, ordinal, role, text),
            role=role,
            text=text,
            source_refs=tuple(refs),
        ))
        ordinal += 1

    title = filing.document_type.id
    add("document.heading.primary", title, (plan.filing,))
    add("document.metadata", plan.position_scope, (draft.plan,))

    recipient = resolve(plan.recipient, records, tenant, case)
    add("document.party_block", _display_name(recipient), (plan.recipient,))

    for request_ref in plan.objectives:
        request = resolve(request_ref, records, tenant, case)
        if request.kind != "Request":
            raise ValueError("REFERENCE_TYPE")
        add("document.request", request.text, (request_ref,))

    for section_text in draft.sections:
        section = resolve(section_text.section, records, tenant, case)
        if section.kind != "Section":
            raise ValueError("REFERENCE_TYPE")
        add("document.heading.secondary", section.title, (section_text.section,))
        for statement in section_text.statements:
            role = {
                "LEGAL": "document.legal_basis",
                "REQUEST": "document.request",
                "FACTUAL": "document.body",
                "INFERENCE": "document.body",
                "STRUCTURAL": "document.body",
            }[statement.statement_type]
            add(role, statement.text, statement.refs)
            for citation_ref in statement.citations:
                citation = resolve(citation_ref, records, tenant, case)
                if citation.kind != "Citation" or citation.status != "VERIFIED":
                    raise ValueError("CITATION_NOT_VERIFIED")
                source = resolve(citation.source, records, tenant, case)
                if source.kind != "LegalSource":
                    raise ValueError("REFERENCE_TYPE")
                cite_text = f"{source.identifier}; {citation.locator.unit}: {citation.locator.value}"
                add("document.evidence_reference", cite_text, (citation_ref, citation.source))

    attachments = []
    for evidence_ref in plan.evidence:
        evidence = resolve(evidence_ref, records, tenant, case)
        if evidence.kind != "Evidence":
            raise ValueError("REFERENCE_TYPE")
        attachments.append(evidence.source)
        add("document.attachment", evidence.description, (evidence_ref,))

    signature_party = filing.authors[0] if filing.authors else None
    if signature_party is not None:
        signer = resolve(signature_party, records, tenant, case)
        add("document.signature", _display_name(signer), (signature_party,))

    return SemanticDocumentV2(
        schema_version="1.0.0",
        tenant_id=tenant,
        case_id=case,
        draft=m.Ref(kind="Draft", id=draft.id, revision=draft.revision),
        draft_hash=digest(draft),
        snapshot_hash=draft.snapshot_hash,
        title=title,
        blocks=tuple(blocks),
        attachments=tuple(attachments),
        signature_party=signature_party,
    )


def compile_render_tree(document: SemanticDocumentV2, profile: RenderProfile) -> RenderTree:
    styles = {style.token: style for style in profile.styles}
    blocks = []
    for block in document.blocks:
        if block.role not in styles:
            raise ValueError("MISSING_STYLE_TOKEN")
        kind = _KIND_BY_TOKEN.get(block.role)
        if kind is None:
            raise ValueError("UNSUPPORTED_RENDER_TOKEN")
        blocks.append(RenderBlock(
            id=block.id,
            kind=kind,
            token=block.role,
            text=block.text,
            source_refs=block.source_refs,
        ))
    return RenderTree(
        schema_version="1.0.0",
        semantic_digest=digest(document),
        profile_digest=digest(profile),
        blocks=tuple(blocks),
    )
