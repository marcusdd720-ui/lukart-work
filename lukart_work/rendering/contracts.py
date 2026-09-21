"""Stage 11 additive rendering contracts. Rendering is representation, never legal authority."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.contracts.messages import CommandMeta, SemanticDocument, ValidationRun
from lukart_work.domain.models import Actor, Hash, Ref, Text, Value, VersionPin
from lukart_work.validation.contracts import stage10_actions

RenderFormat = Literal['DOCX', 'PDF']


class RenderStyleToken(Value):
    token: Literal[
        'document.body', 'document.heading.primary', 'document.heading.secondary',
        'document.metadata', 'document.party_block', 'document.request',
        'document.legal_basis', 'document.quote', 'document.signature',
        'document.attachment',
    ]
    font_family: Text
    font_size_pt: int = Field(strict=True, ge=6, le=32)
    bold: bool
    alignment: Literal['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY']
    space_after_pt: int = Field(strict=True, ge=0, le=48)


class RenderProfile(Value):
    profile_id: Literal['OFFICIAL_PL']
    version: Literal['1.0.0']
    page_width_mm: Literal[210]
    page_height_mm: Literal[297]
    margin_inner_mm: int = Field(strict=True, ge=20, le=40)
    margin_outer_mm: int = Field(strict=True, ge=15, le=35)
    margin_top_mm: int = Field(strict=True, ge=15, le=35)
    margin_bottom_mm: int = Field(strict=True, ge=15, le=35)
    styles: tuple[RenderStyleToken, ...]

    @model_validator(mode='after')
    def complete_tokens(self):
        required = {
            'document.body', 'document.heading.primary', 'document.heading.secondary',
            'document.metadata', 'document.party_block', 'document.request',
            'document.legal_basis', 'document.quote', 'document.signature',
            'document.attachment',
        }
        tokens = [style.token for style in self.styles]
        if len(tokens) != len(set(tokens)) or set(tokens) != required:
            raise ValueError('RENDER_STYLE_TOKEN_COVERAGE')
        return self


class RenderingRequest(Value):
    contract: Literal['urn:lukart:work:RenderingRequest:1.0.0']
    operation: Literal['RecordRenderAuthorization', 'RenderDocument']
    meta: CommandMeta
    target: Ref
    profile: VersionPin
    validation_run_id: UUID | None = None
    validation_run_hash: Hash | None = None
    authorization_id: UUID | None = None
    formats: tuple[RenderFormat, ...] = ()
    rationale: Text
    inputs: tuple[Ref, ...] = ()
    anchors: tuple = ()

    @model_validator(mode='after')
    def shape(self):
        if self.target.kind != 'Draft':
            raise ValueError('DRAFT_REQUIRED')
        if self.inputs or self.anchors:
            raise ValueError('APPLICATION_OWNS_PROVENANCE')
        if self.operation == 'RecordRenderAuthorization':
            if self.validation_run_id is None or self.validation_run_hash is None:
                raise ValueError('VALIDATION_BINDING_REQUIRED')
            if self.authorization_id is not None or self.formats:
                raise ValueError('EXTRANEOUS_INPUT')
        else:
            if self.authorization_id is None:
                raise ValueError('AUTHORIZATION_REQUIRED')
            if self.validation_run_id is not None or self.validation_run_hash is not None:
                raise ValueError('EXTRANEOUS_INPUT')
            if len(self.formats) != 2 or set(self.formats) != {'DOCX', 'PDF'}:
                raise ValueError('RENDER_FORMAT_COVERAGE')
        return self


class RenderAuthorization(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    actor: Actor
    validated_draft: Ref
    validated_hash: Hash
    approved_draft: Ref
    approved_hash: Hash
    validation_run_id: UUID
    validation_run_hash: Hash
    profile: VersionPin
    input_sequence: int = Field(strict=True, ge=1)
    committed_sequence: int = Field(strict=True, ge=1)
    recorded_at: datetime
    rationale: Text

    @model_validator(mode='after')
    def binding(self):
        if self.actor.kind != 'HUMAN':
            raise ValueError('HUMAN_AUTHORIZATION_REQUIRED')
        if self.validated_draft.kind != 'Draft' or self.approved_draft.kind != 'Draft':
            raise ValueError('DRAFT_REQUIRED')
        if self.committed_sequence != self.input_sequence + 1:
            raise ValueError('SEQUENCE_BINDING')
        return self


class RenderArtifact(Value):
    format: RenderFormat
    artifact_id: UUID
    content_hash: Hash
    byte_length: int = Field(strict=True, gt=0)
    media_type: Literal[
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/pdf',
    ]


class RenderManifest(Value):
    semantic_hash: Hash
    profile: VersionPin
    renderer: VersionPin
    source_draft_hash: Hash
    authorization_hash: Hash
    artifacts: tuple[RenderArtifact, ...]

    @model_validator(mode='after')
    def coverage(self):
        formats = [artifact.format for artifact in self.artifacts]
        if len(formats) != 2 or set(formats) != {'DOCX', 'PDF'}:
            raise ValueError('RENDER_ARTIFACT_COVERAGE')
        return self


class RenderExecution(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    authorization: RenderAuthorization
    semantic_document: SemanticDocument
    rendered_draft: Ref
    rendered_hash: Hash
    run: ValidationRun
    artifacts: tuple[RenderArtifact, ...]
    manifest: RenderManifest
    input_sequence: int = Field(strict=True, ge=1)
    committed_sequence: int = Field(strict=True, ge=1)
    recorded_at: datetime

    @model_validator(mode='after')
    def binding(self):
        if self.rendered_draft.kind != 'Draft':
            raise ValueError('DRAFT_REQUIRED')
        if self.committed_sequence != self.input_sequence + 1:
            raise ValueError('SEQUENCE_BINDING')
        if self.run.draft != self.rendered_draft or self.run.draft_hash != self.rendered_hash:
            raise ValueError('RUN_BINDING')
        if self.run.render_hashes != tuple(a.content_hash for a in self.artifacts):
            raise ValueError('RENDER_HASH_BINDING')
        if self.manifest.artifacts != self.artifacts:
            raise ValueError('MANIFEST_BINDING')
        return self


class RenderingQuery(Value):
    contract: Literal['urn:lukart:work:RenderingQuery:1.0.0']
    operation: Literal['GetRendering']
    tenant_id: UUID
    case_id: UUID
    execution_id: UUID


class RenderingProjection(Value):
    execution: RenderExecution
    freshness: Literal['CURRENT', 'STALE', 'UNKNOWN']
    eligible_for_document_approval: bool
    reasons: tuple[Text, ...]


def stage11_actions(actions):
    """Stage 11 may render, but still cannot release, certify, file or transmit."""
    return (stage10_actions(actions) - {'RequestRelease'}) | {
        'RecordRenderAuthorization', 'RenderDocument', 'GetRendering'
    }


STAGE11_CONTRACTS = (
    RenderStyleToken, RenderProfile, RenderingRequest, RenderAuthorization,
    RenderArtifact, RenderManifest, RenderExecution, RenderingQuery, RenderingProjection,
)
