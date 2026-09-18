"""Stage 06 Document Registry contracts; published Core/Filing contracts stay unchanged."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator

from lukart_work.core.requests import CoreRequest
from lukart_work.domain.models import Actor, Hash, Ref, SourceAnchor, Text, Value, VersionPin

RegistryOperation = Literal[
    'RegisterFiling','PrepareFiling','MarkFilingReady','RecordSubmission',
    'RecordAcknowledgement','WithdrawFiling',
]

class RegisterFilingData(Value):
    source_id: UUID
    document_type: VersionPin
    direction: Literal['INCOMING','OUTGOING']
    proceeding: Ref | None = None
    recipient: Ref
    authors: Annotated[tuple[Ref,...], Field(min_length=1)]

class ReceiptEvidenceData(Value):
    receipt_source_id: UUID
    evidence: Ref
    @model_validator(mode='after')
    def evidence_kind(self):
        if self.evidence.kind != 'Evidence': raise ValueError('EVIDENCE_REQUIRED')
        return self

class SubmissionEvidenceData(ReceiptEvidenceData):
    submitted_at: datetime
    @model_validator(mode='after')
    def submission_time(self):
        if self.submitted_at.tzinfo is None: raise ValueError('SUBMISSION_TIMEZONE_REQUIRED')
        return self

class RegistryTransitionData(Value):
    pass

class RegistryRequest(CoreRequest):
    contract: Literal['urn:lukart:work:RegistryRequest:1.0.0']
    operation: RegistryOperation
    data: RegisterFilingData | SubmissionEvidenceData | ReceiptEvidenceData | RegistryTransitionData
    rationale: Text
    @model_validator(mode='after')
    def action_payload(self):
        expected=(RegisterFilingData if self.operation=='RegisterFiling'
            else SubmissionEvidenceData if self.operation=='RecordSubmission'
            else ReceiptEvidenceData if self.operation=='RecordAcknowledgement'
            else RegistryTransitionData)
        parsed=expected.model_validate_json(self.data.model_dump_json(exclude_unset=True))
        object.__setattr__(self,'data',parsed)
        if not self.rationale.strip() or self.inputs or self.anchors: raise ValueError('EXPLICIT_REGISTRY_INTENT_REQUIRED')
        if self.operation=='RegisterFiling':
            if self.target is not None: raise ValueError('TARGET_FORBIDDEN')
        elif self.target is None or self.target.kind!='Filing': raise ValueError('FILING_TARGET_REQUIRED')
        return self

class RegistryReceipt(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    filing: Ref
    sequence: Annotated[int,Field(ge=1)]
    previous_hash: Hash | None
    event: Literal['REGISTERED','PREPARED','READY','SUBMITTED','ACKNOWLEDGED','WITHDRAWN']
    receipt_class: Literal['REGISTRY','SUBMISSION','ACKNOWLEDGEMENT']
    actor: Actor
    recorded_at: datetime
    event_at: datetime | None = None
    operation: RegistryOperation
    input_hash: Hash
    implementation: VersionPin
    artifact_source_id: UUID
    artifact_hash: Hash
    artifact_byte_length: Annotated[int,Field(ge=0)]
    evidence_anchor: SourceAnchor | None = None
    evidence: Ref | None = None
    @model_validator(mode='after')
    def invariants(self):
        if self.filing.kind!='Filing' or self.actor.kind!='HUMAN' or self.recorded_at.tzinfo is None: raise ValueError('RECEIPT_IDENTITY')
        if self.event_at is not None and self.event_at.tzinfo is None: raise ValueError('RECEIPT_EVENT_TIME')
        if (self.sequence==1)!=(self.previous_hash is None): raise ValueError('RECEIPT_CHAIN')
        expected='SUBMISSION' if self.event=='SUBMITTED' else 'ACKNOWLEDGEMENT' if self.event=='ACKNOWLEDGED' else 'REGISTRY'
        if self.receipt_class!=expected: raise ValueError('RECEIPT_CLASS')
        if self.event=='SUBMITTED':
            if self.evidence_anchor is None or self.evidence is None or self.evidence.kind!='Evidence' or self.event_at is None: raise ValueError('RECEIPT_EVIDENCE_REQUIRED')
            if self.evidence_anchor.document_id==self.artifact_source_id: raise ValueError('RECEIPT_EVIDENCE_REQUIRED')
        elif self.event=='ACKNOWLEDGED':
            if self.evidence_anchor is None or self.evidence is None or self.evidence.kind!='Evidence' or self.event_at is not None: raise ValueError('RECEIPT_EVIDENCE_REQUIRED')
            if self.evidence_anchor.document_id==self.artifact_source_id: raise ValueError('RECEIPT_EVIDENCE_REQUIRED')
        elif self.evidence_anchor is not None or self.evidence is not None or self.event_at is not None: raise ValueError('UNEXPECTED_RECEIPT_EVIDENCE')
        return self

class RegistryQuery(Value):
    contract: Literal['urn:lukart:work:RegistryQuery:1.0.0']
    operation: Literal['GetDocumentRegistry']
    tenant_id: UUID
    case_id: UUID
    filing_id: UUID | None = None

class FilingRegistryEntry(Value):
    filing: Ref
    direction: Literal['INCOMING','OUTGOING']
    status: Literal['PLANNED','PREPARING','READY','SUBMITTED','ACKNOWLEDGED','WITHDRAWN']
    document_type: VersionPin
    proceeding: Ref | None
    recipient: Ref
    authors: tuple[Ref,...]
    artifact_source_id: UUID
    artifact_hash: Hash
    artifact_byte_length: Annotated[int,Field(ge=0)]
    submitted_at: datetime | None
    submission_receipt: SourceAnchor | None
    submission_evidence: Ref | None
    acknowledgement_receipt: SourceAnchor | None
    acknowledgement_evidence: Ref | None
    receipt_count: Annotated[int,Field(ge=1)]

class RegistryProjection(Value):
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int,Field(ge=1)]
    filings: tuple[FilingRegistryEntry,...]
    history: tuple[RegistryReceipt,...]
    unregistered_filings: tuple[Ref,...]
