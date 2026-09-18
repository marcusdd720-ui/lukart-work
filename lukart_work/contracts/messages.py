"""Wire messages. Authentication and authorization come from trusted adapters, never AI."""
from typing import Annotated, Literal, Union
from datetime import datetime
from uuid import UUID
from pydantic import Field, model_validator
from lukart_work.domain.models import *

class SourceDocument(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    content_hash: Hash
    media_type: Text
    byte_length: Annotated[int, Field(ge=0)]
    object_key: Text
    received_at: datetime
    actor: Actor
    retention_policy: VersionPin

class SnapshotMember(Value):
    ref: Ref
    content_hash: Hash

class Snapshot(Value):
    schema_version: Literal['1.0.0']
    id: UUID
    tenant_id: UUID
    case_id: UUID
    case_sequence: Positive
    created_at: datetime
    members: Annotated[tuple[SnapshotMember, ...], Field(min_length=1)]
    heads: Annotated[tuple[Ref, ...], Field(min_length=1)]
    sources: tuple[SourceDocument, ...]
    knowledge_pins: tuple[VersionPin, ...]
    rule_set: VersionPin
    policy: VersionPin
    @model_validator(mode='after')
    def unique(self):
        keys=[m.ref for m in self.members]
        if len(keys)!=len(set(keys)): raise ValueError('DUPLICATE_SNAPSHOT_MEMBER')
        if len({(r.kind,r.id) for r in self.heads})!=len(self.heads) or not set(self.heads)<=set(keys): raise ValueError('INVALID_SNAPSHOT_HEADS')
        if any((s.tenant_id,s.case_id)!=(self.tenant_id,self.case_id) for s in self.sources): raise ValueError('CROSS_CASE')
        if len({s.id for s in self.sources}) != len(self.sources): raise ValueError('DUPLICATE_SOURCE')
        return self

class KnowledgeEdge(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    predicate: Literal['SUPPORTED_BY','GOVERNED_BY','SUPPORTS','OPPOSES','CHALLENGES','BASED_ON','USES','REFERS_TO']
    source: Ref
    target: Ref
    provenance: Provenance

class DependencyEdge(Value):
    """Input revision -> derived revision. Not a knowledge predicate."""
    source: Ref
    target: Ref
    input_hash: Hash

class FreshnessAssessment(Value):
    target: Ref
    snapshot_hash: Hash
    current_case_sequence: Positive
    state: Literal['CURRENT','STALE','UNKNOWN']
    changed_inputs: tuple[Ref, ...]

class CommandMeta(Value):
    command_id: UUID
    tenant_id: UUID
    case_id: UUID
    idempotency_key: UUID
    expected_case_sequence: Annotated[int, Field(ge=0,strict=True)]
    correlation_id: UUID

class CreateCase(Value):
    operation: Literal['CreateCase']
    meta: CommandMeta
    case: Case

class AppendRevision(Value):
    operation: Literal['AppendRevision']
    meta: CommandMeta
    expected_revision: Annotated[int, Field(ge=0,strict=True)]
    entity: EntityPayload

class AcceptSnapshot(Value):
    operation: Literal['AcceptSnapshot']
    meta: CommandMeta
    snapshot: Snapshot
    decision: Ref

class GenerateDocument(Value):
    operation: Literal['GenerateDocument']
    meta: CommandMeta
    document_type: VersionPin
    objective_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    snapshot_id: UUID
    snapshot_hash: Hash
    plan: Ref
    profile: Literal['QUICK','PROFESSIONAL','FORENSIC']

class ValidateDraft(Value):
    operation: Literal['ValidateDraft']
    meta: CommandMeta
    draft: Ref
    snapshot_hash: Hash
    validation_policy: VersionPin

class RequestRelease(Value):
    operation: Literal['RequestRelease']
    meta: CommandMeta
    draft: Ref
    render_hashes: Annotated[tuple[Hash, ...], Field(min_length=1)]
    run_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    approval: Ref

Command = Annotated[Union[CreateCase,AppendRevision,AcceptSnapshot,GenerateDocument,ValidateDraft,RequestRelease], Field(discriminator='operation')]

class Query(Value):
    operation: Literal['GetRevision','GetSnapshot','GetCaseHead','GetProvenance','GetAffectedDrafts']
    tenant_id: UUID
    case_id: UUID
    target: Ref | None = None
    snapshot_id: UUID | None = None
    @model_validator(mode='after')
    def required_target(self):
        if self.operation in ('GetRevision','GetProvenance','GetAffectedDrafts') and self.target is None: raise ValueError('TARGET_REQUIRED')
        if self.operation=='GetSnapshot' and self.snapshot_id is None: raise ValueError('SNAPSHOT_REQUIRED')
        return self

class DomainError(Value):
    code: Literal['SCHEMA_INVALID','INVALID_TRANSITION','BROKEN_REFERENCE','CROSS_CASE','PROVENANCE_MISSING','UNSUPPORTED','STALE','CONFLICT','IDEMPOTENCY_CONFLICT','FORBIDDEN','GATE_DENIED','UNKNOWN','DUPLICATE','INVALID_HASH','CYCLE']
    path: str
    message: Text
    retryable: bool
    correlation_id: UUID

class CommandResult(Value):
    command_id: UUID
    state: Literal['APPLIED','REPLAYED','REJECTED']
    case_sequence: Annotated[int, Field(ge=0)]
    refs: tuple[Ref, ...]
    event_ids: tuple[UUID, ...]
    errors: tuple[DomainError, ...]

class AuditEvent(Value):
    event_id: UUID
    tenant_id: UUID
    case_id: UUID
    sequence: Positive
    actor: Actor
    timestamp: datetime
    operation: Text
    command_id: UUID
    correlation_id: UUID
    input_hash: Hash
    output_hash: Hash
    previous_event_hash: Hash | None
    source_versions: tuple[Ref, ...]
    model_provider: VersionPin | None
    rule_version: VersionPin

class DomainEvent(Value):
    event_type: Literal['RevisionAppended','SnapshotAccepted','PlanApproved','DraftGenerated','DraftingAbstained','DependenciesInvalidated','ValidationCompleted','ReleaseDenied','ReleaseGranted','DecisionRecorded']
    audit: AuditEvent
    subjects: tuple[Ref, ...]

class AIProposal(Value):
    proposal_id: UUID
    proposed_kind: Literal['Fact','Evidence','Issue','Claim','Defence','Argument','CounterArgument','Request','Risk']
    statement: Text
    support: Support
    source_refs: tuple[Ref, ...]
    anchors: tuple[SourceAnchor, ...]
    uncertainty: Literal['LOW','MEDIUM','HIGH','UNKNOWN']

class AIRequest(Value):
    request_id: UUID
    tenant_id: UUID
    case_id: UUID
    task: Literal['EXTRACTION','LEGAL_REASONING','DRAFTING','ADVERSARIAL_REVIEW','LANGUAGE_REVIEW']
    snapshot_id: UUID
    snapshot_hash: Hash
    input_refs: tuple[Ref, ...]
    section_contract: SectionContract | None
    prompt: VersionPin
    output_contract: VersionPin
    data_policy: VersionPin

class AIResult(Value):
    request_id: UUID
    snapshot_hash: Hash
    disposition: Literal['PROPOSE','ABSTAIN']
    proposals: tuple[AIProposal, ...]
    section: SectionText | None
    missing_information: tuple[Text, ...]
    reason: Text | None
    @model_validator(mode='after')
    def abstain(self):
        if self.disposition=='ABSTAIN' and (self.proposals or self.section is not None or not self.reason): raise ValueError('INVALID_ABSTENTION')
        if self.disposition=='PROPOSE' and not self.proposals and self.section is None: raise ValueError('EMPTY_PROPOSAL')
        return self

Check = Literal['schema','facts','evidence','legal_basis','procedure','contradictions','citations','requests','language','document','adversarial','render']
REQUIRED_CHECKS=('schema','facts','evidence','legal_basis','procedure','contradictions','citations','requests','language','document','adversarial','render')
class CheckResult(Value):
    check: Check
    outcome: Literal['PASS','FAIL','UNKNOWN','NOT_RUN']
    validator: VersionPin

class ValidationRun(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    policy: VersionPin
    completed_at: datetime
    checks: tuple[CheckResult, ...]
    findings: tuple[Ref, ...]
    render_hashes: tuple[Hash, ...]
    execution_manifest_hash: Hash

class ValidationRunPin(Value):
    id: UUID
    content_hash: Hash

class ReleaseReceipt(Value):
    """Immutable evaluation evidence; persistence/authentication belong to the future service."""
    target: RenderTarget
    approval: Ref
    approval_hash: Hash
    runs: Annotated[tuple[ValidationRunPin, ...], Field(min_length=1)]
    policy: VersionPin
    case_sequence: Positive

    @model_validator(mode='after')
    def bindings(self):
        if self.approval.kind != 'Decision': raise ValueError('REFERENCE_TYPE')
        if len({r.id for r in self.runs}) != len(self.runs): raise ValueError('DUPLICATE_RUN')
        return self

class ReleaseResult(Value):
    eligibility: Literal['FINAL','DRAFT']
    reasons: tuple[Text, ...]
    draft: Ref
    snapshot_hash: Hash
    render_hashes: tuple[Hash, ...]
    receipt: ReleaseReceipt | None = None

    @model_validator(mode='after')
    def receipt_required(self):
        if self.eligibility == 'FINAL':
            if self.reasons or self.receipt is None: raise ValueError('RECEIPT_REQUIRED')
            target = self.receipt.target
            if (target.draft, target.snapshot_hash, target.render_hashes) != (self.draft, self.snapshot_hash, self.render_hashes):
                raise ValueError('RECEIPT_MISMATCH')
        elif self.receipt is not None:
            raise ValueError('DENIED_RECEIPT')
        return self

class SemanticDocument(Value):
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    snapshot_hash: Hash
    header: Text
    parties: tuple[Ref, ...]
    requests: tuple[Ref, ...]
    sections: tuple[SectionText, ...]
    attachments: tuple[SourceAnchor, ...]
    signature_party: Ref | None

class RenderRequest(Value):
    document: SemanticDocument
    profile: VersionPin
    authorization_hash: Hash

CONTRACTS=(SourceDocument,Snapshot,KnowledgeEdge,DependencyEdge,FreshnessAssessment,CreateCase,AppendRevision,AcceptSnapshot,GenerateDocument,ValidateDraft,RequestRelease,Query,DomainError,CommandResult,AuditEvent,DomainEvent,AIRequest,AIResult,ValidationRun,ReleaseResult,SemanticDocument,RenderRequest)

class CaseHeadResult(Value):
    result_type: Literal['CASE_HEAD']
    tenant_id: UUID
    case_id: UUID
    case_sequence: Positive
    heads: tuple[Ref, ...]

class RevisionResult(Value):
    result_type: Literal['REVISION']
    entity: EntityPayload

class SnapshotResult(Value):
    result_type: Literal['SNAPSHOT']
    snapshot: Snapshot
    content_hash: Hash

class ProvenanceResult(Value):
    result_type: Literal['PROVENANCE']
    tenant_id: UUID
    case_id: UUID
    target: Ref
    sources: tuple[SourceAnchor, ...]
    revisions: tuple[Ref, ...]
    completeness: Literal['COMPLETE','INCOMPLETE','UNKNOWN']

class AffectedDraftsResult(Value):
    result_type: Literal['AFFECTED_DRAFTS']
    tenant_id: UUID
    case_id: UUID
    case_sequence: Positive
    assessments: tuple[FreshnessAssessment, ...]

CONTRACTS += (CaseHeadResult,RevisionResult,SnapshotResult,ProvenanceResult,AffectedDraftsResult)
CONTRACTS += (SnapshotTarget,RenderTarget,ValidationRunPin,ReleaseReceipt)
