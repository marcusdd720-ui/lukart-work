"""New Stage 05 contracts; published Core/domain contracts remain unchanged."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from lukart_work.core.requests import CoreRequest
from lukart_work.domain.models import Value, Text, Hash, Ref, Actor, Money, SourceAnchor

FactOperation = Literal['ReviewCandidate', 'MarkFactExtracted', 'ReviewFact', 'ConfirmFact',
    'DisputeFact', 'RejectFact', 'UpdateFact', 'ReviewEvidence', 'AcceptEvidence',
    'ChallengeEvidence', 'ExcludeEvidence', 'UpdateEvidence']


class CandidateReviewData(Value):
    source_id: UUID
    run_id: UUID
    result_hash: Hash
    candidate_index: Annotated[int, Field(ge=0)]
    expected_review_revision: Annotated[int, Field(ge=0)]
    disposition: Literal['ADMIT', 'REJECT']
    statement: Text | None = None
    description: Text | None = None
    subjects: tuple[Ref, ...] = ()


class FactEditData(Value):
    statement: Text | None = None
    support: Literal['SOURCE_BACKED', 'INFERRED', 'UNSUPPORTED'] | None = None
    evidence: tuple[Ref, ...] | None = None
    subjects: tuple[Ref, ...] | None = None
    event_date: date | None = None
    amount: Money | None = None
    key_fact: bool | None = None


class EvidenceEditData(Value):
    description: Text | None = None
    authenticity: Literal['UNKNOWN', 'VERIFIED', 'DISPUTED'] | None = None
    submitted_in: Ref | None = None


class ConfirmFactData(Value):
    decision: Ref


class TransitionData(Value):
    pass


class FactEvidenceRequest(CoreRequest):
    contract: Literal['urn:lukart:work:FactEvidenceRequest:1.0.0']
    operation: FactOperation
    data: CandidateReviewData | ConfirmFactData | FactEditData | EvidenceEditData | TransitionData
    rationale: Text = Field(...)

    @model_validator(mode='after')
    def action_payload(self):
        expected = {'ReviewCandidate': CandidateReviewData, 'ConfirmFact': ConfirmFactData,
                    'UpdateFact': FactEditData, 'UpdateEvidence': EvidenceEditData}.get(self.operation, TransitionData)
        # Reparse by the operation, so empty/update payload ambiguity is not meaningful.
        parsed = expected.model_validate_json(self.data.model_dump_json(exclude_unset=True))
        object.__setattr__(self, 'data', parsed)
        if not self.rationale.strip() or self.inputs or self.anchors:
            raise ValueError('EXPLICIT_REVIEW_REQUIRED')
        if self.operation.startswith('Update') and not parsed.model_fields_set:
            raise ValueError('EMPTY_UPDATE')
        return self


class CandidateReviewRecord(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    run_id: UUID
    source_id: UUID
    result_hash: Hash
    candidate_index: Annotated[int, Field(ge=0)]
    candidate_kind: Literal['FACT', 'EVIDENCE']
    revision: Annotated[int, Field(ge=1)]
    previous_hash: Hash | None
    disposition: Literal['ADMIT', 'REJECT']
    actor: Actor
    recorded_at: datetime
    rationale: Text
    anchor: SourceAnchor
    created: tuple[Ref, ...]

    @model_validator(mode='after')
    def receipt(self):
        if self.actor.kind != 'HUMAN' or self.recorded_at.tzinfo is None:
            raise ValueError('HUMAN_REVIEW_REQUIRED')
        if (self.revision == 1) != (self.previous_hash is None):
            raise ValueError('REVIEW_CHAIN')
        kinds = tuple(r.kind for r in self.created)
        expected = () if self.disposition == 'REJECT' else ('Evidence', 'Fact') if self.candidate_kind == 'FACT' else ('Evidence',)
        if kinds != expected:
            raise ValueError('REVIEW_OUTPUT')
        return self


class FactEvidenceQuery(Value):
    contract: Literal['urn:lukart:work:FactEvidenceQuery:1.0.0']
    tenant_id: UUID
    case_id: UUID
    operation: Literal['GetFactEvidenceMatrix']


class EvidenceAssessment(Value):
    evidence: Ref
    status: Literal['REGISTERED', 'REVIEWED', 'ACCEPTED', 'CHALLENGED', 'EXCLUDED']
    authenticity: Literal['UNKNOWN', 'VERIFIED', 'DISPUTED']
    source_available: bool
    provenance_available: bool
    issues: tuple[str, ...]


class FactAssessment(Value):
    fact: Ref
    statement: Text
    status: Literal['CANDIDATE','EXTRACTED','REVIEWED','CONFIRMED','DISPUTED','REJECTED']
    support: Literal['SOURCE_BACKED', 'INFERRED', 'UNSUPPORTED']
    evidence: tuple[Ref, ...]
    acceptance_live: bool
    confirmation_current: bool
    issues: tuple[str, ...]
    used_in: tuple[Ref, ...]


class FactEvidenceMatrix(Value):
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    facts: tuple[FactAssessment, ...]
    evidence: tuple[EvidenceAssessment, ...]
    candidate_reviews: tuple[CandidateReviewRecord, ...]
