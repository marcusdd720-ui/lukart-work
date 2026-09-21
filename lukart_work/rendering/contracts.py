"""Renderer-neutral Stage 11 contracts.

These models are internal product contracts, not legal-domain entities.  They deliberately
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
    body_font_pt: Annotated[int, Field(strict=True, ge=8, le=18)]
    heading_font_pt: Annotated[int, Field(strict=True, ge=9, le=24)]
    title_font_pt: Annotated[int, Field(strict=True, ge=9, le=28)]
    line_spacing_milli: Annotated[int, Field(strict=True, ge=900, le=2000)]
    paragraph_after_pt: Annotated[int, Field(strict=True, ge=0, le=36)]
    section_before_pt: Annotated[int, Field(strict=True, ge=0, le=72)]
    requests_label: Text
    attachments_label: Text

    @model_validator(mode="after")
    def page_contract(self):
        if self.margin_left_mm + self.margin_right_mm >= self.page_width_mm:
            raise ValueError("INVALID_HORIZONTAL_MARGINS")
        if self.margin_top_mm + self.margin_bottom_mm >= self.page_height_mm:
            raise ValueError("INVALID_VERTICAL_MARGINS")
        return self


class LayoutBlock(Value):
    role: RenderRole
    style_token: Text
    text: Text
    refs: tuple[Ref, ...] = ()
    ordinal: Annotated[int | None, Field(strict=True, ge=1)] = None
    keep_with_next: bool = False
    page_break_before: bool = False


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
