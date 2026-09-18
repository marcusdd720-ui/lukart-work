"""Stage 08 Document Planner contracts over accepted immutable case snapshots."""
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.core.requests import CoreRequest
from lukart_work.domain.models import DocumentPlan, Ref, Section, Text, Value

PlannerOperation = Literal[
    'PlanDocument', 'ReviewDocumentPlan', 'ApproveDocumentPlan', 'SupersedeDocumentPlan',
]


class SectionBlueprint(Value):
    section_type: Text
    title: Text
    arguments: tuple[Ref, ...] = ()
    allowed_inputs: tuple[Ref, ...] = ()
    required_inputs: tuple[Ref, ...] = ()
    allowed_claims: tuple[Ref, ...] = ()
    forbidden: tuple[
        Literal['UNSUPPORTED_ASSERTION', 'UNMARKED_INFERENCE', 'NEW_FACT', 'NEW_LEGAL_RULE'], ...
    ]
    requirements: tuple[Literal['CHRONOLOGICAL', 'CITATIONS', 'REQUESTS', 'ATTACHMENTS'], ...] = ()

    @model_validator(mode='after')
    def safe_contract(self):
        if not set(self.required_inputs) <= set(self.allowed_inputs):
            raise ValueError('REQUIRED_NOT_ALLOWED')
        if not set(self.allowed_claims) <= set(self.allowed_inputs):
            raise ValueError('CLAIM_NOT_ALLOWED_INPUT')
        required_forbidden = {
            'UNSUPPORTED_ASSERTION', 'UNMARKED_INFERENCE', 'NEW_FACT', 'NEW_LEGAL_RULE',
        }
        if not required_forbidden <= set(self.forbidden):
            raise ValueError('UNSAFE_SECTION_CONTRACT')
        if len(self.arguments) != len(set(self.arguments)):
            raise ValueError('DUPLICATE_REFERENCE')
        if len(self.allowed_inputs) != len(set(self.allowed_inputs)):
            raise ValueError('DUPLICATE_REFERENCE')
        if len(self.required_inputs) != len(set(self.required_inputs)):
            raise ValueError('DUPLICATE_REFERENCE')
        if len(self.allowed_claims) != len(set(self.allowed_claims)):
            raise ValueError('DUPLICATE_REFERENCE')
        return self


class PlanDocumentData(Value):
    snapshot_id: UUID
    snapshot_hash: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    filing: Ref
    objectives: Annotated[tuple[Ref, ...], Field(min_length=1)]
    position_scope: Text
    argument_order: tuple[Ref, ...] = ()
    evidence: tuple[Ref, ...] = ()
    sections: Annotated[tuple[SectionBlueprint, ...], Field(min_length=1)]

    @model_validator(mode='after')
    def shape(self):
        if self.filing.kind != 'Filing':
            raise ValueError('FILING_REQUIRED')
        if any(r.kind != 'Request' for r in self.objectives):
            raise ValueError('REQUEST_REQUIRED')
        if any(r.kind != 'Argument' for r in self.argument_order):
            raise ValueError('ARGUMENT_REQUIRED')
        if any(r.kind != 'Evidence' for r in self.evidence):
            raise ValueError('EVIDENCE_REQUIRED')
        for refs in (self.objectives, self.argument_order, self.evidence):
            if len(refs) != len(set(refs)):
                raise ValueError('DUPLICATE_REFERENCE')
        section_arguments = {r for s in self.sections for r in s.arguments}
        if not section_arguments <= set(self.argument_order):
            raise ValueError('SECTION_ARGUMENT_OUTSIDE_PLAN')
        return self


class ApproveDocumentPlanData(Value):
    decision: Ref

    @model_validator(mode='after')
    def decision_kind(self):
        if self.decision.kind != 'Decision':
            raise ValueError('DECISION_REQUIRED')
        return self


class PlannerTransitionData(Value):
    pass


class PlannerRequest(CoreRequest):
    contract: Literal['urn:lukart:work:PlannerRequest:1.0.0']
    operation: PlannerOperation
    data: PlanDocumentData | ApproveDocumentPlanData | PlannerTransitionData
    rationale: Text = Field(...)

    @model_validator(mode='after')
    def payload(self):
        expected = (
            PlanDocumentData if self.operation == 'PlanDocument'
            else ApproveDocumentPlanData if self.operation == 'ApproveDocumentPlan'
            else PlannerTransitionData
        )
        parsed = expected.model_validate_json(self.data.model_dump_json(exclude_unset=True))
        object.__setattr__(self, 'data', parsed)
        if not self.rationale.strip() or self.inputs or self.anchors:
            raise ValueError('EXPLICIT_PLANNING_INTENT_REQUIRED')
        if self.operation == 'PlanDocument':
            if self.target is not None:
                raise ValueError('TARGET_FORBIDDEN')
        elif self.target is None or self.target.kind != 'DocumentPlan':
            raise ValueError('DOCUMENT_PLAN_TARGET_REQUIRED')
        return self


class PlannerQuery(Value):
    contract: Literal['urn:lukart:work:PlannerQuery:1.0.0']
    operation: Literal['GetDocumentPlan']
    tenant_id: UUID
    case_id: UUID
    plan: Ref

    @model_validator(mode='after')
    def plan_kind(self):
        if self.plan.kind != 'DocumentPlan':
            raise ValueError('DOCUMENT_PLAN_REQUIRED')
        return self


class DocumentPlanProjection(Value):
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    plan: DocumentPlan
    sections: tuple[Section, ...]
    snapshot_hash: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    approval_current: bool
