"""Application intent envelope; domain revisions are constructed by handlers.

This is separate from Stage 01's internal AppendRevision contract. No wire
operation accepts arbitrary revision metadata, status, actor or timestamps.
"""
import json
from typing import Literal
from uuid import UUID
from pydantic import Field, JsonValue
from lukart_work.domain.models import Ref, Value, SourceAnchor, Text
from lukart_work.contracts.messages import CommandMeta
from lukart_work.validation.rules import strict_json, Violation

Operation = Literal[
    'CreateCase', 'EditCase', 'SuspendCase', 'CloseCase', 'ReopenCase', 'ArchiveCase',
    'AddParty', 'EditParty', 'VerifyParty', 'DisputeParty',
    'AddInstitution', 'AddProceeding', 'AddFiling', 'AddEvidence',
    'AddFact', 'EditFact', 'ReviewFact', 'ConfirmFact', 'DisputeFact',
    'AddIssue', 'AddClaim', 'AddRequest', 'AddSection', 'PrepareSection',
    'AddCitation', 'BindCitation', 'VerifyCitation',
    'AddPlan', 'ReviewPlan', 'ApprovePlan', 'SupersedePlan',
    'RecordDecision', 'RevokeDecision', 'RegisterSource', 'CreateSnapshot', 'AcceptSnapshot',
    'GenerateDocument', 'ValidateDraft', 'RequestRelease',
]


class CoreRequest(Value):
    contract: Literal['urn:lukart:work:CoreRequest:1.0.0']
    operation: Operation
    meta: CommandMeta
    target: Ref | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
    inputs: tuple[Ref, ...] = ()
    anchors: tuple[SourceAnchor, ...] = ()
    rationale: Text = 'Manual Case Core operation'


def parse_request(raw):
    value = strict_json(raw)
    # JSON nesting is checked before schema parsing, with recursion caught by the service.
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 64:
            raise Violation('SCHEMA_INVALID')
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return CoreRequest.model_validate_json(json.dumps(value, allow_nan=False))


class CoreQuery(Value):
    contract: Literal['urn:lukart:work:CoreQuery:1.0.0']
    operation: Literal['GetRevision', 'GetCaseHead', 'GetSnapshot', 'GetProvenance', 'GetAffectedDrafts', 'GetSource']
    tenant_id: UUID
    case_id: UUID
    target: Ref | None = None
    object_id: UUID | None = None
