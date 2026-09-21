"""Renderer-neutral Stage 11 contracts.

These models are internal product contracts, not legal-domain entities. They deliberately
separate semantic content identity, layout identity and concrete artifact identity.
"""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.domain.models import Hash, Ref, Text, Value, VersionPin

RenderRole = Literal[
    "DOCUMENT_HEADER",
    "PARTY_BLOCK",
    "REQUEST_HEADING",
    "REQUEST_ITEM",
    "SECTION_HEADING",
    "BODY",
    "LEGAL_BASIS",
    "QUOTE",
    "SIGNATURE",
    "ATTACHMENT_HEADING",
    "ATTACHMENT_ITEM",
]

StyleToken = Literal[
    "document.heading.primary",
    "document.heading.secondary",
    "document.party_block",
    "document.request",
    "document.body",
    "document.legal_basis",
    "document.quote",
    "document.signature",
    "document.attachment",
]

REQUIRED_STYLE_TOKENS = (
    "document.heading.primary",
    "document.heading.secondary",
    "document.party_block",
    "document.request",
    "document.body",
    "document.legal_basis",
    "document.quote",
    "document.signature",
    "document.attachment",
)


class RenderBlock(Value):
    role: RenderRole
    text: Text
    refs: tuple[Ref, ...] = ()
    ordinal: Annotated[int | None, Field(strict=True, ge=1)] = None

    @model_validator(mode="after")
    def ordinal_contract(self):
        list_role = self.role in ("REQUEST_ITEM", "ATTACHMENT_ITEM")
        if list_role != (self.ordinal is not None):
            raise ValueError("ORDINAL_CONTRACT")
        if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in self.text):
            raise ValueError("CONTROL_CHARACTER")
        return self


class RenderModel(Value):
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    snapshot_hash: Hash
    blocks: Annotated[tuple[RenderBlock, ...], Field(min_length=1, max_length=5000)]

    @model_validator(mode="after")
    def draft_contract(self):
        if self.draft.kind != "Draft":
            raise ValueError("REFERENCE_TYPE")
        return self


class StyleSpec(Value):
    token: StyleToken
    font_size_pt: Annotated[int, Field(strict=True, ge=8, le=28)]
    bold: bool
    line_spacing_milli: Annotated[int, Field(strict=True, ge=900, le=2000)]
    space_before_pt: Annotated[int, Field(strict=True, ge=0, le=72)]
    space_after_pt: Annotated[int, Field(strict=True, ge=0, le=36)]
    left_indent_mm: Annotated[int, Field(strict=True, ge=0, le=50)]
    hanging_indent_mm: Annotated[int, Field(strict=True, ge=0, le=20)]
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"]
    keep_with_next: bool
    keep_together: bool
    widow_control: bool
    page_break_before: bool

    @model_validator(mode="after")
    def indentation_contract(self):
        if self.hanging_indent_mm > self.left_indent_mm:
            raise ValueError("INVALID_HANGING_INDENT")
        return self


class RenderProfile(Value):
    profile_id: Text
    version: Text
    locale: Literal["pl-PL"]
    page_width_mm: Annotated[int, Field(strict=True, ge=100, le=500)]
    page_height_mm: Annotated[int, Field(strict=True, ge=100, le=500)]
    margin_top_mm: Annotated[int, Field(strict=True, ge=5, le=80)]
    margin_right_mm: Annotated[int, Field(strict=True, ge=5, le=80)]
    margin_bottom_mm: Annotated[int, Field(strict=True, ge=5, le=80)]
    margin_left_mm: Annotated[int, Field(strict=True, ge=5, le=80)]
    font_family: Text
    font_regular_sha256: Hash
    font_bold_sha256: Hash
    styles: Annotated[tuple[StyleSpec, ...], Field(min_length=9, max_length=9)]
    requests_label: Text
    attachments_label: Text

    @model_validator(mode="after")
    def profile_contract(self):
        if self.margin_left_mm + self.margin_right_mm >= self.page_width_mm:
            raise ValueError("INVALID_HORIZONTAL_MARGINS")
        if self.margin_top_mm + self.margin_bottom_mm >= self.page_height_mm:
            raise ValueError("INVALID_VERTICAL_MARGINS")
        tokens = tuple(style.token for style in self.styles)
        if len(set(tokens)) != len(tokens) or set(tokens) != set(REQUIRED_STYLE_TOKENS):
            raise ValueError("STYLE_TOKEN_SET")
        return self


class LayoutBlock(Value):
    role: RenderRole
    style_token: StyleToken
    text: Text
    refs: tuple[Ref, ...] = ()
    ordinal: Annotated[int | None, Field(strict=True, ge=1)] = None


class LayoutTree(Value):
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    snapshot_hash: Hash
    profile: VersionPin
    blocks: Annotated[tuple[LayoutBlock, ...], Field(min_length=1, max_length=5000)]


class RenderArtifact(Value):
    format: Literal["DOCX", "PDF"]
    media_type: Literal[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
    ]
    content_hash: Hash
    byte_length: Annotated[int, Field(strict=True, ge=1)]


class RenderReceipt(Value):
    draft: Ref
    snapshot_hash: Hash
    authorization_hash: Hash
    semantic_digest: Hash
    render_model_digest: Hash
    layout_digest: Hash
    render_profile: VersionPin
    renderer: VersionPin
    artifacts: Annotated[tuple[RenderArtifact, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def artifacts_contract(self):
        formats = tuple(a.format for a in self.artifacts)
        if formats != ("DOCX", "PDF"):
            raise ValueError("ARTIFACT_ORDER")
        if len({a.content_hash for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("DUPLICATE_ARTIFACT_HASH")
        return self


class RenderBundleMeta(Value):
    model: RenderModel
    layout: LayoutTree
    receipt: RenderReceipt
