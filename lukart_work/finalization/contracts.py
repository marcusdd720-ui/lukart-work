"""PB02 contracts for the trusted persisted finalization route.

These contracts do not admit a legal document type.  A trusted host supplies an
exact FinalizationProfile for a synthetic or independently admitted type.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from lukart_work.audit.contracts import AuditPackage
from lukart_work.contracts.messages import (
    CommandMeta,
    ReleaseResult,
    SemanticDocument,
    SourceDocument,
    ValidationRun,
    ValidationRunPin,
)
from lukart_work.domain.models import Actor, Draft, Hash, Ref, SourceAnchor, Text, Value, VersionPin
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
    operation: Literal[
        "RenderDraft",
        "ApproveFinalDocument",
        "RequestFinalRelease",
        "AssembleFinalPackage",
    ]
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
    operation: Literal[
        "GetFinalization",
        "GetFinalRelease",
        "ReadFinalArtifact",
        "GetFinalPackage",
        "ReadFinalPackageMember",
    ]
    tenant_id: UUID
    case_id: UUID
    render_id: UUID
    format: Literal["DOCX", "PDF"] | None = None
    member: Literal[
        "final.docx",
        "final.pdf",
        "document.json",
        "validation.json",
        "sources.json",
        "evidence-map.json",
        "argument-map.json",
        "audit.json",
        "release.json",
        "manifest.json",
    ] | None = None

    @model_validator(mode="after")
    def shape(self):
        if (self.operation == "ReadFinalArtifact") != (self.format is not None):
            raise ValueError("FORMAT_REQUIRED")
        if (self.operation == "ReadFinalPackageMember") != (self.member is not None):
            raise ValueError("MEMBER_REQUIRED")
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


FINAL_PACKAGE_MEMBER_NAMES = (
    "final.docx",
    "final.pdf",
    "document.json",
    "validation.json",
    "sources.json",
    "evidence-map.json",
    "argument-map.json",
    "audit.json",
    "release.json",
    "manifest.json",
)

CommitSHA = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class FinalPackageProfile(Value):
    """Deployment-supplied package provenance; no Git state is guessed at runtime."""

    profile_id: Text
    version: Text
    build_revision: CommitSHA
    baseline_contract_hash: Hash


class FinalDocumentRecord(Value):
    contract: Literal["urn:lukart:work:FinalDocumentRecord:1.0.0"]
    profile: FinalPackageProfile
    document_type: VersionPin
    draft: Draft
    render: PersistedRender

    @model_validator(mode="after")
    def bindings(self):
        if (
            self.draft.status != "RENDERED"
            or self.draft.id != self.render.validated_draft.id
            or self.draft.snapshot_id != self.render.snapshot_id
            or self.draft.snapshot_hash != self.render.snapshot_hash
        ):
            raise ValueError("DOCUMENT_BINDING")
        return self


class FinalValidationRecord(Value):
    contract: Literal["urn:lukart:work:FinalValidationRecord:1.0.0"]
    pre_render: ValidationProjection
    approval: FinalizationApproval

    @model_validator(mode="after")
    def bindings(self):
        if (
            self.approval.manifest.input_validation.id != self.pre_render.execution.run.id
            or self.approval.manifest.input_validation_projection_hash != digest(self.pre_render)
            or any(item.outcome != "PASS" for item in self.approval.post_render_run.checks)
        ):
            raise ValueError("VALIDATION_BINDING")
        return self


class FinalSourcesRecord(Value):
    contract: Literal["urn:lukart:work:FinalSourcesRecord:1.0.0"]
    sources: tuple[SourceDocument, ...]
    anchors: tuple[SourceAnchor, ...]

    @model_validator(mode="after")
    def bindings(self):
        source_ids = tuple(item.id for item in self.sources)
        anchor_ids = {item.document_id for item in self.anchors}
        if (
            len(set(source_ids)) != len(source_ids)
            or source_ids != tuple(sorted(source_ids, key=str))
            or set(source_ids) != anchor_ids
        ):
            raise ValueError("SOURCE_BINDING")
        return self


class FinalTraceNode(Value):
    ref: Ref
    content_hash: Hash
    links: tuple[Ref, ...]
    anchors: tuple[SourceAnchor, ...]


class FinalStatementTrace(Value):
    statement_id: UUID
    section: Ref
    statement_type: Literal["FACTUAL", "LEGAL", "REQUEST", "INFERENCE", "STRUCTURAL"]
    refs: tuple[Ref, ...]
    citations: tuple[Ref, ...]


class FinalEvidenceMap(Value):
    contract: Literal["urn:lukart:work:FinalEvidenceMap:1.0.0"]
    statements: tuple[FinalStatementTrace, ...]
    nodes: tuple[FinalTraceNode, ...]

    @model_validator(mode="after")
    def unique(self):
        if len({item.statement_id for item in self.statements}) != len(self.statements):
            raise ValueError("DUPLICATE_STATEMENT")
        refs = tuple(item.ref for item in self.nodes)
        if len(set(refs)) != len(refs):
            raise ValueError("DUPLICATE_TRACE_NODE")
        return self


class FinalArgumentMap(Value):
    contract: Literal["urn:lukart:work:FinalArgumentMap:1.0.0"]
    objectives: tuple[Ref, ...]
    arguments: tuple[Ref, ...]
    nodes: tuple[FinalTraceNode, ...]

    @model_validator(mode="after")
    def unique(self):
        roots = self.objectives + self.arguments
        node_refs = tuple(item.ref for item in self.nodes)
        if len(set(roots)) != len(roots) or len(set(node_refs)) != len(node_refs):
            raise ValueError("DUPLICATE_TRACE_NODE")
        if not set(roots) <= set(node_refs):
            raise ValueError("TRACE_ROOT_MISSING")
        return self


class FinalPackageMember(Value):
    name: Literal[
        "final.docx",
        "final.pdf",
        "document.json",
        "validation.json",
        "sources.json",
        "evidence-map.json",
        "argument-map.json",
        "audit.json",
        "release.json",
        "manifest.json",
    ]
    artifact_id: UUID
    media_type: Text
    content_hash: Hash
    byte_length: Annotated[int, Field(ge=1)]


class FinalPackageManifest(Value):
    contract: Literal["urn:lukart:work:FinalPackageManifest:1.0.0"]
    package_id: UUID
    tenant_id: UUID
    case_id: UUID
    render_id: UUID
    release_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    profile: FinalPackageProfile
    document_type: VersionPin
    release_hash: Hash
    audit_package_hash: Hash
    members: Annotated[tuple[FinalPackageMember, ...], Field(min_length=9, max_length=9)]

    @model_validator(mode="after")
    def bindings(self):
        if tuple(item.name for item in self.members) != FINAL_PACKAGE_MEMBER_NAMES[:-1]:
            raise ValueError("PACKAGE_MEMBER_ORDER")
        if len({item.artifact_id for item in self.members}) != len(self.members):
            raise ValueError("DUPLICATE_PACKAGE_MEMBER")
        return self


class FinalPackageRecord(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    render_id: UUID
    release_id: UUID
    manifest: FinalPackageManifest
    manifest_hash: Hash
    members: Annotated[tuple[FinalPackageMember, ...], Field(min_length=10, max_length=10)]
    actor: Actor
    recorded_at: datetime
    committed_sequence: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def bindings(self):
        if (
            (self.tenant_id, self.case_id, self.render_id, self.release_id)
            != (
                self.manifest.tenant_id,
                self.manifest.case_id,
                self.manifest.render_id,
                self.manifest.release_id,
            )
            or self.manifest.package_id != self.id
            or self.manifest_hash != digest(self.manifest)
            or tuple(item.name for item in self.members) != FINAL_PACKAGE_MEMBER_NAMES
            or self.members[:-1] != self.manifest.members
            or self.members[-1].content_hash != self.manifest_hash
        ):
            raise ValueError("PACKAGE_BINDING")
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
    FinalPackageProfile,
    FinalDocumentRecord,
    FinalValidationRecord,
    FinalSourcesRecord,
    FinalTraceNode,
    FinalStatementTrace,
    FinalEvidenceMap,
    FinalArgumentMap,
    FinalPackageMember,
    FinalPackageManifest,
    FinalPackageRecord,
)
