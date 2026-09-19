"""Stage 10 additive pre-render contracts. Reviews are attributable assessments, not truth."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from lukart_work.domain.models import Value, Ref, Hash, Text, Actor, Severity, VersionPin
from lukart_work.contracts.messages import CommandMeta, ValidationRun, Snapshot
from lukart_work.domain.models import Draft
from lukart_work.procedural.contracts import ProceduralDatum

SemanticCheck = Literal['facts', 'evidence', 'legal_basis', 'procedure', 'contradictions', 'language', 'adversarial']
SEMANTIC_CHECKS = ('facts', 'evidence', 'legal_basis', 'procedure', 'contradictions', 'language', 'adversarial')
PRE_RENDER_CHECKS = ('schema', 'facts', 'evidence', 'legal_basis', 'procedure', 'contradictions', 'citations', 'requests', 'language', 'document', 'adversarial')


class ReviewIssue(Value):
    check: SemanticCheck
    code: Text
    severity: Severity
    path: Text
    message: Text


class ReviewAssessment(Value):
    check: SemanticCheck
    outcome: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_RUN']
    rationale: Text


class ValidationReviewProposal(Value):
    """Untrusted review-provider output. No public command persists this as authority."""
    task: Literal['LANGUAGE_REVIEW', 'ADVERSARIAL_REVIEW']
    draft: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    policy: VersionPin
    assessments: tuple[ReviewAssessment, ...]
    issues: tuple[ReviewIssue, ...]
    disposition: Literal['PROPOSE', 'ABSTAIN']
    reason: Text

    @model_validator(mode='after')
    def boundary(self):
        expected = 'language' if self.task == 'LANGUAGE_REVIEW' else 'adversarial'
        if self.draft.kind != 'Draft' or any(a.check != expected for a in self.assessments) or any(i.check != expected for i in self.issues):
            raise ValueError('REVIEW_TASK_BOUNDARY')
        if self.disposition == 'ABSTAIN' and (self.assessments or self.issues):
            raise ValueError('ABSTAIN_IS_NOT_ASSESSMENT')
        if self.disposition == 'PROPOSE' and (len(self.assessments) != 1):
            raise ValueError('REVIEW_COVERAGE')
        return self


class ValidationReviewInput(Value):
    task: Literal['LANGUAGE_REVIEW', 'ADVERSARIAL_REVIEW']
    draft: Draft
    draft_hash: Hash
    snapshot: Snapshot
    policy: VersionPin
    instruction: Literal['PROPOSAL_ONLY_NO_DOMAIN_WRITES']

    @model_validator(mode='after')
    def binding(self):
        from .rules import digest
        if (self.draft_hash != digest(self.draft) or self.draft.snapshot_id != self.snapshot.id
                or self.draft.snapshot_hash != digest(self.snapshot)
                or (self.draft.tenant_id, self.draft.case_id) != (self.snapshot.tenant_id, self.snapshot.case_id)):
            raise ValueError('REVIEW_INPUT_BINDING')
        return self


class ValidationRequest(Value):
    contract: Literal['urn:lukart:work:ValidationRequest:1.0.0']
    operation: Literal['ValidateDraft', 'RecordValidationReview', 'RevokeValidationReview', 'ResolveValidationFinding']
    meta: CommandMeta
    target: Ref
    draft_hash: Hash | None = None
    snapshot_hash: Hash | None = None
    validation_policy: VersionPin
    review_id: UUID | None = None
    assessments: tuple[ReviewAssessment, ...] = ()
    issues: tuple[ReviewIssue, ...] = ()
    decision: Ref | None = None
    resolution: Literal['RESOLVED', 'FALSE_POSITIVE'] | None = None
    rationale: Text
    inputs: tuple[Ref, ...] = ()
    anchors: tuple = ()
    procedural_context: tuple[ProceduralDatum, ...] = ()

    @model_validator(mode='after')
    def shape(self):
        if self.inputs or self.anchors:
            raise ValueError('APPLICATION_OWNS_PROVENANCE')
        if self.operation != 'ValidateDraft' and self.procedural_context:
            raise ValueError('EXTRANEOUS_INPUT')
        if len({d.key for d in self.procedural_context}) != len(self.procedural_context):
            raise ValueError('DUPLICATE_CONTEXT_KEY')
        if self.operation == 'ResolveValidationFinding':
            if self.target.kind != 'ValidationFinding' or self.decision is None or self.resolution is None:
                raise ValueError('RESOLUTION_REQUIRED')
            if self.draft_hash or self.snapshot_hash or self.review_id or self.assessments or self.issues:
                raise ValueError('EXTRANEOUS_INPUT')
        else:
            if self.target.kind != 'Draft' or self.draft_hash is None or self.snapshot_hash is None:
                raise ValueError('DRAFT_BINDING_REQUIRED')
            if self.decision or self.resolution:
                raise ValueError('EXTRANEOUS_INPUT')
            if self.operation != 'RecordValidationReview' and (self.assessments or self.issues):
                raise ValueError('CLIENT_PASS_FORBIDDEN')
            if self.operation == 'RecordValidationReview':
                checks = [a.check for a in self.assessments]
                if len(checks) != len(set(checks)) or set(checks) != set(SEMANTIC_CHECKS):
                    raise ValueError('REVIEW_COVERAGE')
                if self.review_id is not None:
                    raise ValueError('APPLICATION_OWNS_ID')
                for issue in self.issues:
                    assessment = next(a for a in self.assessments if a.check == issue.check)
                    if issue.severity in ('ERROR', 'BLOCKER', 'CRITICAL') and assessment.outcome == 'PASS':
                        raise ValueError('CONTRADICTORY_REVIEW')
            if self.operation == 'RevokeValidationReview' and self.review_id is None:
                raise ValueError('REVIEW_REQUIRED')
        return self


class ValidationReview(Value):
    id: UUID
    tenant_id: UUID
    case_id: UUID
    draft: Ref
    draft_hash: Hash
    snapshot_hash: Hash
    policy: VersionPin
    evaluation_date: date
    actor: Actor
    recorded_at: datetime
    assessments: tuple[ReviewAssessment, ...]
    issues: tuple[ReviewIssue, ...]
    rationale: Text


class ValidationReviewRevocation(Value):
    review_id: UUID
    actor: Actor
    recorded_at: datetime
    rationale: Text


class ValidationManifest(Value):
    policy: VersionPin
    draft_hash: Hash
    snapshot_hash: Hash
    dependency_hashes: tuple[tuple[Ref, Hash], ...]
    review_hash: Hash | None
    evaluation_date: date
    procedural_context: tuple[ProceduralDatum, ...]


class ValidationExecution(Value):
    id: UUID
    run: ValidationRun
    output_draft: Ref
    output_hash: Hash
    evaluation_date: date
    input_sequence: int = Field(ge=1)
    committed_sequence: int = Field(ge=1)
    review: ValidationReview | None
    dependencies: tuple[Ref, ...]
    validator: VersionPin
    manifest: ValidationManifest


class ValidationQuery(Value):
    contract: Literal['urn:lukart:work:ValidationQuery:1.0.0']
    operation: Literal['GetValidation']
    tenant_id: UUID
    case_id: UUID
    run_id: UUID


class ValidationProjection(Value):
    execution: ValidationExecution
    freshness: Literal['CURRENT', 'STALE', 'UNKNOWN']
    eligible_for_approval: bool
    reasons: tuple[Text, ...]


def stage10_actions(actions):
    """Product profile excludes historical generation/release bypasses."""
    return (frozenset(actions) - {'RequestRelease', 'AddPlan', 'AddSection', 'PrepareSection', 'ApprovePlan'}) | {
        'ValidateDraft', 'RecordValidationReview', 'RevokeValidationReview', 'ResolveValidationFinding', 'GetValidation'
    }


STAGE10_CONTRACTS = (ValidationReviewInput, ValidationReviewProposal, ValidationRequest, ValidationReview,
                     ValidationReviewRevocation, ValidationExecution, ValidationQuery, ValidationProjection)
STAGE10_CONTRACTS += (ValidationManifest,)
