"""Versioned, renderer/provider-independent domain contracts. No persistence side effects."""
from __future__ import annotations
from datetime import date, datetime
from typing import Annotated, Literal, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1, max_length=20000)]
Hash = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[int, Field(strict=True, ge=1)]
Kind = Literal['Case','Party','Institution','Proceeding','Filing','Fact','Evidence','Issue','LegalSource','LegalRule','Claim','Defence','Argument','CounterArgument','Request','Deadline','Risk','Citation','DocumentPlan','Section','Draft','ValidationFinding','Decision']
Severity = Literal['INFO','WARNING','ERROR','BLOCKER','CRITICAL']
Support = Literal['SOURCE_BACKED','INFERRED','UNSUPPORTED']

class Value(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)

class Ref(Value):
    kind: Kind
    id: UUID
    revision: Positive

class Actor(Value):
    id: UUID
    kind: Literal['HUMAN','SERVICE','AI']

class VersionPin(Value):
    id: Text
    version: Text
    content_hash: Hash

class Locator(Value):
    """A source location must be nonempty and address immutable source bytes."""
    unit: Literal['PAGE','PARAGRAPH','ARTICLE','BYTE_RANGE','RECORD']
    value: Text
    fragment_hash: Hash

class SourceAnchor(Value):
    document_id: UUID
    document_hash: Hash
    locator: Locator

class Provenance(Value):
    actor: Actor
    operation_id: UUID
    method: Literal['MANUAL','EXTRACTION','DERIVATION','IMPORT','VALIDATION']
    inputs: tuple[Ref, ...]
    anchors: tuple[SourceAnchor, ...]
    rationale: Text
    tool: VersionPin | None = None

class Money(Value):
    amount: Annotated[str, StringConstraints(pattern=r'^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$')]
    currency: Annotated[str, StringConstraints(pattern=r'^[A-Z]{3}$')]

class Address(Value):
    country: Annotated[str, StringConstraints(pattern=r'^[A-Z]{2}$')]
    lines: Annotated[tuple[Text, ...], Field(min_length=1)]
    postal_code: Text | None = None

class TimeRange(Value):
    start: date
    end: date | None = None
    @model_validator(mode='after')
    def ordered(self):
        if self.end is not None and self.end < self.start: raise ValueError('DATE_RANGE')
        return self

class Entity(Value):
    schema_version: Literal['1.0.0']
    id: UUID
    tenant_id: UUID
    case_id: UUID
    revision: Positive
    previous_hash: Hash | None
    created_at: datetime
    recorded_at: datetime
    provenance: Provenance
    @model_validator(mode='after')
    def metadata(self):
        if self.created_at.tzinfo is None or self.recorded_at.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
        if self.recorded_at < self.created_at: raise ValueError('TIME_ORDER')
        if (self.revision == 1) != (self.previous_hash is None): raise ValueError('REVISION_CHAIN')
        return self

class Case(Entity):
    kind: Literal['Case']
    status: Literal['OPEN','SUSPENDED','CLOSED','ARCHIVED']
    title: Text
    jurisdiction: Text
    owner_id: UUID
    retention_policy: VersionPin
    @model_validator(mode='after')
    def self_id(self):
        if self.id != self.case_id: raise ValueError('CASE_ID')
        return self

class Party(Entity):
    kind: Literal['Party']
    status: Literal['UNVERIFIED','VERIFIED','DISPUTED','INACTIVE']
    party_type: Literal['PERSON','ORGANIZATION','UNKNOWN']
    display_name: Text
    address: Address | None = None
    identity_evidence: tuple[Ref, ...]
    verification_decision: Ref | None = None

class Institution(Entity):
    kind: Literal['Institution']
    status: Literal['UNVERIFIED','VERIFIED','INACTIVE']
    institution_type: Literal['COURT','AUTHORITY','OMBUDSMAN','OTHER','UNKNOWN']
    name: Text
    jurisdiction: Text
    address: Address | None = None
    registry_identifier: Text | None = None

class Participation(Value):
    party: Ref
    role: Text
    represented_by: Ref | None = None

class Proceeding(Entity):
    kind: Literal['Proceeding']
    status: Literal['PLANNED','PENDING','STAYED','CONCLUDED','CANCELLED']
    proceeding_type: Text
    institution: Ref
    participants: Annotated[tuple[Participation, ...], Field(min_length=1)]
    reference_number: Text | None = None
    parent_proceeding: Ref | None = None

class Filing(Entity):
    kind: Literal['Filing']
    status: Literal['PLANNED','PREPARING','READY','SUBMITTED','ACKNOWLEDGED','WITHDRAWN']
    document_type: VersionPin
    direction: Literal['INCOMING','OUTGOING']
    proceeding: Ref | None = None
    recipient: Ref
    authors: Annotated[tuple[Ref, ...], Field(min_length=1)]
    submitted_at: datetime | None = None
    submission_receipt: SourceAnchor | None = None

class Fact(Entity):
    kind: Literal['Fact']
    status: Literal['CANDIDATE','EXTRACTED','REVIEWED','CONFIRMED','DISPUTED','REJECTED']
    statement: Text
    support: Support
    evidence: tuple[Ref, ...]
    subjects: tuple[Ref, ...]
    event_date: date | None = None
    amount: Money | None = None
    key_fact: bool
    acceptance: Ref | None = None
    @model_validator(mode='after')
    def backed(self):
        if self.support == 'SOURCE_BACKED' and not self.evidence: raise ValueError('EVIDENCE_REQUIRED')
        if self.status == 'CONFIRMED' and (self.support != 'SOURCE_BACKED' or self.acceptance is None): raise ValueError('CONFIRMATION_REQUIRES_ACCEPTANCE')
        if not self.provenance.anchors and not self.provenance.inputs: raise ValueError('FACT_PROVENANCE')
        return self

class Evidence(Entity):
    kind: Literal['Evidence']
    status: Literal['REGISTERED','REVIEWED','ACCEPTED','CHALLENGED','EXCLUDED']
    evidence_type: Literal['DOCUMENT','TESTIMONY','IMAGE','RECORDING','OTHER']
    description: Text
    source: SourceAnchor
    authenticity: Literal['UNKNOWN','VERIFIED','DISPUTED']
    submitted_in: Ref | None = None

class Issue(Entity):
    kind: Literal['Issue']
    status: Literal['IDENTIFIED','ANALYZING','UNRESOLVED','RESOLVED','CLOSED']
    question: Text
    facts: tuple[Ref, ...]
    rules: tuple[Ref, ...]
    resolution: Ref | None = None

class LegalSource(Entity):
    """Case-local pinned admission of a knowledge registry source revision."""
    kind: Literal['LegalSource']
    status: Literal['REGISTERED','VERIFIED','SUPERSEDED','RETRACTED']
    registry_pin: VersionPin
    jurisdiction: Text
    source_type: Literal['LAW','CASE_LAW','OFFICIAL_GUIDANCE','DOCTRINE','SECONDARY_SOURCE','USER_MATERIAL']
    title: Text
    identifier: Text
    effective_period: TimeRange
    retrieved_at: datetime
    source_uri: Annotated[str, StringConstraints(pattern=r'^https?://[^\s]+$')]
    content_hash: Hash
    authority_level: Literal['BINDING','PERSUASIVE','INFORMATIONAL','UNKNOWN']
    anchor: SourceAnchor

class Requirement(Value):
    operator: Literal['PRESENT','EQUALS','MIN_ITEMS']
    field_path: Annotated[str, StringConstraints(pattern=r'^/[A-Za-z0-9_/-]+$')]
    operand: Text | None = None
    severity: Severity

class LegalRule(Entity):
    kind: Literal['LegalRule']
    status: Literal['PROPOSED','REVIEWED','ACTIVE','SUPERSEDED','WITHDRAWN']
    rule_type: Literal['SUBSTANTIVE','PROCEDURAL','INTERPRETIVE']
    statement: Text
    sources: Annotated[tuple[Ref, ...], Field(min_length=1)]
    jurisdiction: Text
    effective_period: TimeRange
    applicable_document_types: tuple[VersionPin, ...]
    requirement: Requirement | None = None
    interpretation: Literal['SETTLED','DISPUTED','UNKNOWN']
    review_decision: Ref | None = None

class Claim(Entity):
    kind: Literal['Claim']
    status: Literal['PROPOSED','REVIEWED','ADOPTED','DISPUTED','WITHDRAWN','RESOLVED']
    claim_type: Literal['ASSERTION','REMEDY']
    statement: Text
    claimant: Ref
    issues: Annotated[tuple[Ref, ...], Field(min_length=1)]
    facts: tuple[Ref, ...]
    rules: tuple[Ref, ...]
    support: Support
    amount: Money | None = None
    adoption: Ref | None = None

class Defence(Entity):
    kind: Literal['Defence']
    status: Literal['PROPOSED','REVIEWED','ADOPTED','WITHDRAWN','RESOLVED']
    claim: Ref
    party: Ref
    statement: Text
    facts: tuple[Ref, ...]
    rules: tuple[Ref, ...]
    adoption: Ref | None = None

class Assessment(Value):
    dimension: Literal['LEGAL_SUPPORT','FACTUAL_SUPPORT','EVIDENCE_SUPPORT','COUNTERARGUMENT_EXPOSURE','PROCEDURAL_RELEVANCE','OVERALL_CONFIDENCE']
    level: Literal['LOW','MEDIUM','HIGH','UNKNOWN']
    basis: tuple[Ref, ...]
    rationale: Text

class Argument(Entity):
    kind: Literal['Argument']
    status: Literal['PROPOSED','REVIEWED','ADOPTED','CHALLENGED','WITHDRAWN']
    target: Ref
    polarity: Literal['SUPPORTS','OPPOSES']
    conclusion: Text
    premises: Annotated[tuple[Ref, ...], Field(min_length=1)]
    rules: tuple[Ref, ...]
    support: Support
    assessments: tuple[Assessment, ...]

class CounterArgument(Entity):
    kind: Literal['CounterArgument']
    status: Literal['IDENTIFIED','REVIEWED','ANSWERED','UNRESOLVED','DISMISSED']
    target_argument: Ref
    statement: Text
    premises: tuple[Ref, ...]
    support: Support
    response_argument: Ref | None = None

class Request(Entity):
    kind: Literal['Request']
    status: Literal['PROPOSED','REVIEWED','APPROVED','WITHDRAWN','RESOLVED']
    filing: Ref
    request_type: Text
    text: Text
    claims: Annotated[tuple[Ref, ...], Field(min_length=1)]
    evidence: tuple[Ref, ...]
    approval: Ref | None = None
    amount: Money | None = None

class Deadline(Entity):
    kind: Literal['Deadline']
    status: Literal['UNKNOWN','CALCULATED','VERIFIED','SATISFIED','EXPIRED','CANCELLED']
    proceeding: Ref | None = None
    filing: Ref | None = None
    trigger: Ref
    rules: tuple[Ref, ...]
    due_at: datetime | None = None
    timezone: Text
    calendar_pin: VersionPin
    computation_trace: tuple[Text, ...]
    satisfaction: Ref | None = None
    @model_validator(mode='after')
    def due(self):
        if self.status in ('CALCULATED','VERIFIED','EXPIRED') and self.due_at is None: raise ValueError('DUE_REQUIRED')
        if self.due_at is not None and self.due_at.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
        return self

class Risk(Entity):
    kind: Literal['Risk']
    status: Literal['OPEN','MITIGATING','ACCEPTED','RESOLVED']
    category: Literal['FACTUAL','EVIDENTIARY','LEGAL','PROCEDURAL','PRIVACY','OPERATIONAL']
    description: Text
    severity: Severity
    affected: Annotated[tuple[Ref, ...], Field(min_length=1)]
    mitigation: Ref | None = None
    acceptance: Ref | None = None

class Citation(Entity):
    kind: Literal['Citation']
    status: Literal['PROPOSED','BOUND','VERIFIED','INVALID']
    source: Ref
    locator: Locator
    supported: Ref
    quotation: Text | None = None

class DocumentPlan(Entity):
    kind: Literal['DocumentPlan']
    status: Literal['PROPOSED','REVIEWED','APPROVED','SUPERSEDED','REJECTED']
    filing: Ref
    input_snapshot_id: UUID
    input_snapshot_hash: Hash
    objectives: Annotated[tuple[Ref, ...], Field(min_length=1)]
    recipient: Ref
    position_scope: Text
    argument_order: tuple[Ref, ...]
    evidence: tuple[Ref, ...]
    section_order: Annotated[tuple[Ref, ...], Field(min_length=1)]
    approval: Ref | None = None

class SectionContract(Value):
    allowed_inputs: tuple[Ref, ...]
    required_inputs: tuple[Ref, ...]
    allowed_claims: tuple[Ref, ...]
    forbidden: tuple[Literal['UNSUPPORTED_ASSERTION','UNMARKED_INFERENCE','NEW_FACT','NEW_LEGAL_RULE'], ...]
    requirements: tuple[Literal['CHRONOLOGICAL','CITATIONS','REQUESTS','ATTACHMENTS'], ...]
    @model_validator(mode='after')
    def subset(self):
        if not set(self.required_inputs) <= set(self.allowed_inputs): raise ValueError('REQUIRED_NOT_ALLOWED')
        return self

class Section(Entity):
    kind: Literal['Section']
    status: Literal['PLANNED','READY','RETIRED']
    filing: Ref
    section_type: Text
    title: Text
    arguments: tuple[Ref, ...]
    contract: SectionContract

class Statement(Value):
    id: UUID
    text: Text
    statement_type: Literal['FACTUAL','LEGAL','REQUEST','INFERENCE','STRUCTURAL']
    support: Support
    refs: tuple[Ref, ...]
    citations: tuple[Ref, ...]
    inference_label: Text | None = None
    @model_validator(mode='after')
    def trace(self):
        if self.statement_type != 'STRUCTURAL' and self.support == 'SOURCE_BACKED' and not self.refs: raise ValueError('TRACE_REQUIRED')
        if self.support == 'INFERRED' and (not self.refs or not self.inference_label): raise ValueError('INFERENCE_LABEL_REQUIRED')
        return self

class SectionText(Value):
    section: Ref
    statements: Annotated[tuple[Statement, ...], Field(min_length=1)]

class ReproductionManifest(Value):
    knowledge: tuple[VersionPin, ...]
    rule_set: VersionPin
    prompts: tuple[VersionPin, ...]
    models: tuple[VersionPin, ...]
    provider: VersionPin
    model_parameters_hash: Hash
    generator: VersionPin
    validators: tuple[VersionPin, ...]
    render_profile: VersionPin
    input_hash: Hash
    raw_output_hash: Hash

class Draft(Entity):
    kind: Literal['Draft']
    status: Literal['PLANNED','GENERATED','VALIDATED','APPROVED','RENDERED','CERTIFIED']
    plan: Ref
    snapshot_id: UUID
    snapshot_hash: Hash
    sections: tuple[SectionText, ...]
    reproduction: ReproductionManifest
    supersedes: Ref | None = None

class ValidationFinding(Entity):
    kind: Literal['ValidationFinding']
    status: Literal['OPEN','RESOLVED','FALSE_POSITIVE']
    run_id: UUID
    target: Ref
    target_hash: Hash
    layer: Literal['V1','V2','V3','V4','V5','V6','V7','V8','V9','V10','RENDER']
    code: Text
    severity: Severity
    message: Text
    path: Text
    resolution: Ref | None = None

class SnapshotTarget(Value):
    """Exact immutable input approved by a human; not a new canonical entity."""
    tenant_id: UUID
    case_id: UUID
    snapshot_id: UUID
    snapshot_hash: Hash

class RenderTarget(SnapshotTarget):
    draft: Ref
    draft_hash: Hash
    render_hashes: Annotated[tuple[Hash, ...], Field(min_length=1)]

    @model_validator(mode='after')
    def binding(self):
        if self.draft.kind != 'Draft': raise ValueError('REFERENCE_TYPE')
        if len(set(self.render_hashes)) != len(self.render_hashes): raise ValueError('DUPLICATE_RENDER')
        return self

class Decision(Entity):
    kind: Literal['Decision']
    status: Literal['PROPOSED','RECORDED','SUPERSEDED','REVOKED']
    decision_type: Literal['IDENTITY','FACT_ACCEPTANCE','STRATEGY','REQUEST_APPROVAL','INTERPRETATION','PLAN_APPROVAL','DOCUMENT_APPROVAL','RISK_ACCEPTANCE','FINDING_RESOLUTION','SNAPSHOT_ACCEPTANCE','CERTIFICATION']
    targets: Annotated[tuple[Ref, ...], Field(min_length=1)]
    outcome: Literal['ACCEPT','REJECT','ABSTAIN']
    rationale: Text
    decided_by: Actor
    supersedes: Ref | None = None
    snapshot_target: SnapshotTarget | None = None
    render_target: RenderTarget | None = None

    @model_validator(mode='after')
    def artifact_target(self):
        if (self.decision_type == 'SNAPSHOT_ACCEPTANCE') != (self.snapshot_target is not None):
            raise ValueError('SNAPSHOT_TARGET_REQUIRED')
        if (self.decision_type == 'DOCUMENT_APPROVAL') != (self.render_target is not None):
            raise ValueError('RENDER_TARGET_REQUIRED')
        for target in (self.snapshot_target, self.render_target):
            if target is not None and (target.tenant_id, target.case_id) != (self.tenant_id, self.case_id):
                raise ValueError('CROSS_CASE')
        if self.render_target is not None and self.targets != (self.render_target.draft,):
            raise ValueError('APPROVAL_TARGET_MISMATCH')
        return self

ENTITIES = (Case,Party,Institution,Proceeding,Filing,Fact,Evidence,Issue,LegalSource,LegalRule,Claim,Defence,Argument,CounterArgument,Request,Deadline,Risk,Citation,DocumentPlan,Section,Draft,ValidationFinding,Decision)
EntityPayload = Annotated[Union[tuple(ENTITIES)], Field(discriminator='kind')]
