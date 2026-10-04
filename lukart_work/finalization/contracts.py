"""PB02 contracts for the trusted persisted finalization route.

These contracts do not admit a legal document type.  A trusted host supplies an
exact FinalizationProfile for a synthetic or independently admitted type.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from lukart_work.contracts.messages import (
    CommandMeta,
    ReleaseResult,
    SemanticDocument,
    ValidationRun,
    ValidationRunPin,
)
from lukart_work.domain.models import Actor, Hash, Ref, SourceAnchor, Text, Value, VersionPin
from lukart_work.rendering.contracts import RenderArtifact, RenderBundleMeta
from lukart_work.validation.contracts import ValidationProjection
from lukart_work.validation.rules import digest


class FinalizationProfile(Value):
    profile_id: Text
    version: Text
    document_type: VersionPin
    header: Text
    render_profile: VersionPin


def semantic_profile_pin(profile: FinalizationProfile) -> VersionPin:
    return VersionPin(
        id=profile.profile_id,
        version=profile.version,
        content_hash=digest(profile),
    )


class FinalizationRequest(Value):
    contract: Literal["urn:lukart:work:FinalizationRequest:1.0.0"]
    operation: Literal["RenderDraft", "ApproveFinalDocument", "RequestFinalRelease"]
    meta: CommandMeta
    target: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    validation_run_id: UUID | None = None
    render_id: UUID | None = None
    semantic_profile: VersionPin | None = None
    rationale: Text
    inputs: tuple[Ref, ...] = ()
    anchors: tuple[SourceAnchor, ...] = ()

    @model_validator(mode="after")
    def shape(self):
        if self.target.kind != "Draft" or self.inputs or self.anchors:
            raise ValueError("APPLICATION_OWNS_PROVENANCE")
        if self.operation == "RenderDraft":
            if self.validation_run_id is None or self.semantic_profile is None or self.render_id is not None:
                raise ValueError("RENDER_BINDING_REQUIRED")
        elif self.render_id is None or self.validation_run_id is not None or self.semantic_profile is not None:
            raise ValueError("FINALIZATION_BINDING_REQUIRED")
        return self


class FinalizationQuery(Value):
    contract: Literal["urn:lukart:work:FinalizationQuery:1.0.0"]
    operation: Literal["GetFinalization", "GetFinalRelease", "ReadFinalArtifact"]
    tenant_id: UUID
    case_id: UUID
    render_id: UUID
    format: Literal["DOCX", "PDF"] | None = None

    @model_validator(mode="after")
    def shape(self):
        if (self.operation == "ReadFinalArtifact") != (self.format is not None):
            raise ValueError("FORMAT_REQUIRED")
        return self


class PersistedRenderArtifact(Value):
    artifact_id: UUID
    artifact: RenderArtifact


class PersistedRender(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    validated_draft: Ref
    validated_draft_hash: Hash
    snapshot_id: UUID
    snapshot_hash: Hash
    semantic_profile: VersionPin
    document: SemanticDocument
    validation: ValidationProjection
    meta: RenderBundleMeta
    artifacts: tuple[PersistedRenderArtifact, PersistedRenderArtifact]
    actor: Actor
    recorded_at: datetime
    committed_sequence: int

    @model_validator(mode="after")
    def bindings(self):
        receipt = self.meta.receipt
        if (
            self.document.draft != self.validated_draft
            or self.document.snapshot_hash != self.snapshot_hash
            or receipt.draft != self.validated_draft
            or receipt.snapshot_hash != self.snapshot_hash
            or tuple(item.artifact for item in self.artifacts) != receipt.artifacts
            or self.committed_sequence < 1
        ):
            raise ValueError("RENDER_BINDING")
        if tuple(item.artifact.format for item in self.artifacts) != ("DOCX", "PDF"):
            raise ValueError("ARTIFACT_ORDER")
        return self


class PostRenderManifest(Value):
    input_validation: ValidationRunPin
    input_validation_projection_hash: Hash
    render_receipt_hash: Hash
    rendered_draft: Ref
    rendered_draft_hash: Hash
    approval: Ref
    approval_hash: Hash
    artifacts: tuple[RenderArtifact, RenderArtifact]
    policy: VersionPin


class FinalizationApproval(Value):
    render_id: UUID
    tenant_id: UUID
    case_id: UUID
    rendered_draft: Ref
    rendered_draft_hash: Hash
    approval: Ref
    approval_hash: Hash
    post_render_run: ValidationRun
    manifest: PostRenderManifest
    actor: Actor
    recorded_at: datetime
    committed_sequence: int

    @model_validator(mode="after")
    def bindings(self):
        if (
            self.rendered_draft.kind != "Draft"
            or self.post_render_run.draft != self.rendered_draft
            or self.post_render_run.draft_hash != self.rendered_draft_hash
            or self.manifest.rendered_draft != self.rendered_draft
            or self.manifest.rendered_draft_hash != self.rendered_draft_hash
            or self.manifest.approval != self.approval
            or self.manifest.approval_hash != self.approval_hash
            or self.post_render_run.execution_manifest_hash != digest(self.manifest)
            or self.committed_sequence < 1
        ):
            raise ValueError("APPROVAL_BINDING")
        return self


class FinalizationRelease(Value):
    id: UUID
    render_id: UUID
    tenant_id: UUID
    case_id: UUID
    result: ReleaseResult
    approval: Ref
    approval_hash: Hash
    audit_previous_event_hash: Hash
    actor: Actor
    recorded_at: datetime
    committed_sequence: int

    @model_validator(mode="after")
    def bindings(self):
        if (
            self.result.eligibility != "FINAL"
            or self.result.receipt is None
            or self.result.receipt.approval != self.approval
            or self.result.receipt.approval_hash != self.approval_hash
            or self.committed_sequence < 1
        ):
            raise ValueError("RELEASE_BINDING")
        return self


class FinalizationProjection(Value):
    render: PersistedRender
    approval: FinalizationApproval | None
    release: FinalizationRelease | None

    @model_validator(mode="after")
    def bindings(self):
        if self.approval is not None and self.approval.render_id != self.render.id:
            raise ValueError("APPROVAL_BINDING")
        if self.release is not None and self.release.render_id != self.render.id:
            raise ValueError("RELEASE_BINDING")
        if self.release is not None and self.approval is None:
            raise ValueError("APPROVAL_REQUIRED")
        return self


FINALIZATION_CONTRACTS = (
    FinalizationProfile,
    FinalizationRequest,
    FinalizationQuery,
    PersistedRenderArtifact,
    PersistedRender,
    PostRenderManifest,
    FinalizationApproval,
    FinalizationRelease,
    FinalizationProjection,
)
