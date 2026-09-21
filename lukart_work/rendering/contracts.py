"""Stage 11 deterministic rendering contracts.

Rendering never creates legal meaning. It transforms already validated semantic content
into a normalized presentation tree and concrete output artifacts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.contracts.messages import CommandMeta
from lukart_work.domain.models import Hash, Ref, SourceAnchor, Text, Value, VersionPin

RenderToken = Literal[
    "document.body",
    "document.heading.primary",
    "document.heading.secondary",
    "document.metadata",
    "document.party_block",
    "document.request",
    "document.legal_basis",
    "document.quote",
    "document.evidence_reference",
    "document.signature",
    "document.attachment",
]
REQUIRED_RENDER_TOKENS = (
    "document.body",
    "document.heading.primary",
    "document.heading.secondary",
    "document.metadata",
    "document.party_block",
    "document.request",
    "document.legal_basis",
    "document.quote",
    "document.evidence_reference",
    "document.signature",
    "document.attachment",
)
OutputFormat = Literal["DOCX", "PDF"]
Alignment = Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"]


class PageSpec(Value):
    size: Literal["A4"]
    margin_top_mm: Annotated[float, Field(gt=0, le=60)]
    margin_right_mm: Annotated[float, Field(gt=0, le=60)]
    margin_bottom_mm: Annotated[float, Field(gt=0, le=60)]
    margin_left_mm: Annotated[float, Field(gt=0, le=60)]


class FontPolicy(Value):
    family: Text
    fallback_families: tuple[Text, ...] = ()
    allow_fallback: bool = False

    @model_validator(mode="after")
    def unique(self):
        if self.family in self.fallback_families or len(set(self.fallback_families)) != len(self.fallback_families):
            raise ValueError("DUPLICATE_FONT_FAMILY")
        return self


class TokenStyle(Value):
    token: RenderToken
    font_size_pt: Annotated[float, Field(ge=7, le=30)]
    bold: bool = False
    italic: bool = False
    alignment: Alignment = "LEFT"
    line_spacing: Annotated[float, Field(ge=1.0, le=2.5)] = 1.15
    space_before_pt: Annotated[float, Field(ge=0, le=72)] = 0
    space_after_pt: Annotated[float, Field(ge=0, le=72)] = 0
    left_indent_mm: Annotated[float, Field(ge=0, le=80)] = 0
    first_line_indent_mm: Annotated[float, Field(ge=0, le=30)] = 0
    keep_with_next: bool = False


class RenderProfile(Value):
    schema_version: Literal["1.0.0"]
    profile_id: Text
    version: Text
    locale: Literal["pl-PL"]
    page: PageSpec
    font: FontPolicy
    styles: tuple[TokenStyle, ...]
    header_text: str = ""
    footer_text: str = ""

    @model_validator(mode="after")
    def complete(self):
        tokens = [style.token for style in self.styles]
        if len(tokens) != len(set(tokens)):
            raise ValueError("DUPLICATE_STYLE_TOKEN")
        if set(tokens) != set(REQUIRED_RENDER_TOKENS):
            raise ValueError("INCOMPLETE_STYLE_TOKENS")
        return self


class SemanticBlock(Value):
    id: UUID
    role: RenderToken
    text: Text
    source_refs: tuple[Ref, ...] = ()


class SemanticDocumentV2(Value):
    schema_version: Literal["1.0.0"]
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    title: Text
    blocks: Annotated[tuple[SemanticBlock, ...], Field(min_length=1)]
    attachments: tuple[SourceAnchor, ...] = ()
    signature_party: Ref | None = None

    @model_validator(mode="after")
    def binding(self):
        if self.draft.kind != "Draft":
            raise ValueError("REFERENCE_TYPE")
        ids = [block.id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_BLOCK")
        return self


class RenderBlock(Value):
    id: UUID
    kind: Literal[
        "PARAGRAPH",
        "HEADING",
        "METADATA",
        "PARTY",
        "REQUEST",
        "LEGAL_BASIS",
        "QUOTE",
        "EVIDENCE_REFERENCE",
        "SIGNATURE",
        "ATTACHMENT",
    ]
    token: RenderToken
    text: Text
    source_refs: tuple[Ref, ...] = ()


class RenderTree(Value):
    schema_version: Literal["1.0.0"]
    semantic_digest: Hash
    profile_digest: Hash
    blocks: Annotated[tuple[RenderBlock, ...], Field(min_length=1)]


class RenderingRequest(Value):
    contract: Literal["urn:lukart:work:RenderingRequest:1.0.0"]
    operation: Literal["RenderDocument"]
    meta: CommandMeta
    draft: Ref
    draft_hash: Hash
    validation_run_id: UUID
    profile: VersionPin
    formats: Annotated[tuple[OutputFormat, ...], Field(min_length=1, max_length=2)]
    retention_policy: VersionPin

    @model_validator(mode="after")
    def shape(self):
        if self.draft.kind != "Draft":
            raise ValueError("REFERENCE_TYPE")
        if len(set(self.formats)) != len(self.formats):
            raise ValueError("DUPLICATE_FORMAT")
        return self


class RenderedArtifact(Value):
    artifact_id: UUID
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    validation_run_id: UUID
    semantic_digest: Hash
    profile: VersionPin
    profile_digest: Hash
    renderer: VersionPin
    adapter: VersionPin
    format: OutputFormat
    media_type: Literal[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
    ]
    render_tree_digest: Hash
    presentation_digest: Hash
    resource_hashes: tuple[Hash, ...]
    artifact_byte_hash: Hash
    byte_length: Annotated[int, Field(gt=0)]
    created_at: datetime


class RenderingExecution(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    input_case_sequence: Annotated[int, Field(ge=1)]
    draft: Ref
    draft_hash: Hash
    validation_run_id: UUID
    semantic_document: SemanticDocumentV2
    render_tree: RenderTree
    artifacts: Annotated[tuple[RenderedArtifact, ...], Field(min_length=1)]
    renderer: VersionPin
    completed_at: datetime


class RenderingResult(Value):
    execution: RenderingExecution
    replayed: bool = False


STAGE11_CONTRACTS = (
    PageSpec,
    FontPolicy,
    TokenStyle,
    RenderProfile,
    SemanticBlock,
    SemanticDocumentV2,
    RenderBlock,
    RenderTree,
    RenderingRequest,
    RenderedArtifact,
    RenderingExecution,
    RenderingResult,
)
