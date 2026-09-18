"""Stage 07 Procedural Intelligence contracts over canonical Case Core state."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from lukart_work.core.requests import CoreRequest
from lukart_work.domain.models import (
    Actor, Hash, Ref, Severity, Text, TimeRange, Value, VersionPin,
)

ProceduralOperation = Literal[
    'RegisterProceduralSource', 'VerifyProceduralSource',
    'RegisterProceduralRule', 'ReviewProceduralRule', 'ActivateProceduralRule',
    'SupersedeProceduralRule', 'WithdrawProceduralRule',
]
ProceduralCategory = Literal[
    'ORGAN', 'JURISDICTION', 'VENUE', 'STANDING_AUTHORITY',
    'FILING_TOPOLOGY', 'CHANNEL', 'FORMAL_REQUIREMENT',
    'SIGNATURE', 'COPIES', 'ATTACHMENTS', 'DEADLINE',
]
DatumClassification = Literal[
    'FACT', 'CLAIM', 'HYPOTHESIS', 'INTERPRETATION', 'UNKNOWN', 'UNRESOLVED',
]


class ProceduralCondition(Value):
    path: Text
    operator: Literal['PRESENT', 'EQUALS', 'ONE_OF', 'MIN_INTEGER', 'MIN_ITEMS', 'CONTAINS_ALL']
    operand: JsonValue | None = None

    @model_validator(mode='after')
    def shape(self):
        if not self.path.startswith('/'):
            raise ValueError('CONDITION_PATH')
        if self.operator == 'PRESENT' and self.operand is not None:
            raise ValueError('CONDITION_OPERAND')
        if self.operator in ('MIN_INTEGER', 'MIN_ITEMS') and (type(self.operand) is not int or self.operand < 0):
            raise ValueError('CONDITION_OPERAND')
        if self.operator in ('ONE_OF', 'CONTAINS_ALL') and not isinstance(self.operand, list):
            raise ValueError('CONDITION_OPERAND')
        if self.operator == 'EQUALS' and self.operand is None:
            raise ValueError('CONDITION_OPERAND')
        return self


class DeadlineRule(Value):
    trigger_key: Text
    offset_days: Annotated[int, Field(ge=0)]
    timezone: Text
    due_time: Annotated[str, Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')]
    calendar_mode: Literal['CALENDAR_DAYS', 'BUSINESS_DAYS']


class ProceduralRuleSpec(Value):
    category: ProceduralCategory
    code: Text
    applies_when: tuple[ProceduralCondition, ...] = ()
    requirements: tuple[ProceduralCondition, ...] = ()
    severity: Severity
    deadline: DeadlineRule | None = None

    @model_validator(mode='after')
    def mode(self):
        if self.category == 'DEADLINE':
            if self.deadline is None or self.requirements:
                raise ValueError('DEADLINE_SPEC')
        elif self.deadline is not None or not self.requirements:
            raise ValueError('REQUIREMENTS_REQUIRED')
        return self


class RegisterProceduralSourceData(Value):
    source_id: UUID
    registry_id: Text
    registry_version: Text
    jurisdiction: Text
    source_type: Literal['LAW', 'CASE_LAW', 'OFFICIAL_GUIDANCE', 'DOCTRINE', 'SECONDARY_SOURCE', 'USER_MATERIAL']
    title: Text
    identifier: Text
    effective_period: TimeRange
    source_uri: Annotated[str, Field(pattern=r'^https?://[^\s]+$')]
    authority_level: Literal['BINDING', 'PERSUASIVE', 'INFORMATIONAL', 'UNKNOWN']


class RegisterProceduralRuleData(Value):
    sources: Annotated[tuple[Ref, ...], Field(min_length=1)]
    statement: Text
    jurisdiction: Text
    effective_period: TimeRange
    applicable_document_types: tuple[VersionPin, ...] = ()
    interpretation: Literal['SETTLED', 'DISPUTED', 'UNKNOWN']
    spec: ProceduralRuleSpec

    @model_validator(mode='after')
    def source_kinds(self):
        if any(r.kind != 'LegalSource' for r in self.sources):
            raise ValueError('LEGAL_SOURCE_REQUIRED')
        return self


class ActivateProceduralRuleData(Value):
    decision: Ref

    @model_validator(mode='after')
    def decision_kind(self):
        if self.decision.kind != 'Decision':
            raise ValueError('DECISION_REQUIRED')
        return self


class ProceduralTransitionData(Value):
    pass


class ProceduralRequest(CoreRequest):
    contract: Literal['urn:lukart:work:ProceduralRequest:1.0.0']
    operation: ProceduralOperation
    data: RegisterProceduralSourceData | RegisterProceduralRuleData | ActivateProceduralRuleData | ProceduralTransitionData
    rationale: Text = Field(...)

    @model_validator(mode='after')
    def action_payload(self):
        if self.operation == 'RegisterProceduralSource':
            expected = RegisterProceduralSourceData
        elif self.operation == 'RegisterProceduralRule':
            expected = RegisterProceduralRuleData
        elif self.operation == 'ActivateProceduralRule':
            expected = ActivateProceduralRuleData
        else:
            expected = ProceduralTransitionData
        parsed = expected.model_validate_json(self.data.model_dump_json(exclude_unset=True))
        object.__setattr__(self, 'data', parsed)
        if not self.rationale.strip() or self.inputs or self.anchors:
            raise ValueError('EXPLICIT_PROCEDURAL_INTENT_REQUIRED')
        if self.operation in ('RegisterProceduralSource', 'RegisterProceduralRule'):
            if self.target is not None:
                raise ValueError('TARGET_FORBIDDEN')
        elif self.operation == 'VerifyProceduralSource':
            if self.target is None or self.target.kind != 'LegalSource':
                raise ValueError('LEGAL_SOURCE_TARGET_REQUIRED')
        elif self.target is None or self.target.kind != 'LegalRule':
            raise ValueError('LEGAL_RULE_TARGET_REQUIRED')
        return self


class ProceduralRuleBinding(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    rule: Ref
    revision: Annotated[int, Field(ge=1)]
    previous_hash: Hash | None
    sources: Annotated[tuple[Ref, ...], Field(min_length=1)]
    spec: ProceduralRuleSpec
    actor: Actor
    recorded_at: datetime
    implementation: VersionPin

    @model_validator(mode='after')
    def chain(self):
        if self.rule.kind != 'LegalRule' or self.rule.revision != self.revision:
            raise ValueError('RULE_BINDING')
        if any(r.kind != 'LegalSource' for r in self.sources):
            raise ValueError('RULE_BINDING')
        if self.actor.kind != 'HUMAN' or self.recorded_at.tzinfo is None:
            raise ValueError('HUMAN_REVIEW_REQUIRED')
        if (self.revision == 1) != (self.previous_hash is None):
            raise ValueError('BINDING_CHAIN')
        return self


class ProceduralDatum(Value):
    key: Text
    classification: DatumClassification
    value: JsonValue | None = None
    facts: tuple[Ref, ...] = ()

    @model_validator(mode='after')
    def evidence_boundary(self):
        if any(r.kind != 'Fact' for r in self.facts):
            raise ValueError('FACT_REFERENCE_REQUIRED')
        if self.classification == 'FACT':
            if self.value is None or not self.facts:
                raise ValueError('FACT_EVIDENCE_REQUIRED')
        elif self.facts:
            raise ValueError('NONFACT_REFERENCE_FORBIDDEN')
        if self.classification == 'UNKNOWN' and self.value is not None:
            raise ValueError('UNKNOWN_HAS_VALUE')
        return self


class ProceduralQuery(Value):
    contract: Literal['urn:lukart:work:ProceduralQuery:1.0.0']
    operation: Literal['AssessProcedure']
    tenant_id: UUID
    case_id: UUID
    filing: Ref
    evaluation_date: date
    context: tuple[ProceduralDatum, ...] = ()

    @model_validator(mode='after')
    def scope(self):
        if self.filing.kind != 'Filing':
            raise ValueError('FILING_REQUIRED')
        keys = [d.key for d in self.context]
        if len(keys) != len(set(keys)):
            raise ValueError('DUPLICATE_CONTEXT_KEY')
        return self


class ProceduralFinding(Value):
    code: Text
    category: ProceduralCategory
    applicability: Literal['APPLICABLE', 'NOT_APPLICABLE', 'UNKNOWN', 'UNRESOLVED', 'ABSTAIN']
    outcome: Literal['SATISFIED', 'VIOLATION', 'CALCULATED', 'NOT_APPLICABLE', 'UNKNOWN', 'UNRESOLVED', 'ABSTAIN']
    severity: Severity
    rule: Ref
    sources: tuple[Ref, ...]
    binding_hash: Hash
    path: Text
    message: Text
    actual: JsonValue | None = None
    expected: JsonValue | None = None
    facts: tuple[Ref, ...] = ()
    due_at: datetime | None = None

    @model_validator(mode='after')
    def time(self):
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError('TIMEZONE_REQUIRED')
        return self


class ProceduralAssessment(Value):
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    filing: Ref
    evaluation_date: date
    findings: tuple[ProceduralFinding, ...]
    rules_considered: tuple[Ref, ...]
