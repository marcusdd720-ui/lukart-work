"""Stage 09 Controlled Drafting configuration and immutable trace contracts."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from lukart_work.contracts.messages import AIRequest, AIResult, DomainError
from lukart_work.domain.models import Actor, Hash, Ref, Value, VersionPin


class DraftingProfile(Value):
    profile: Literal['QUICK', 'PROFESSIONAL', 'FORENSIC']
    prompt: VersionPin
    model: VersionPin
    provider: VersionPin
    generator: VersionPin
    output_contract: VersionPin
    data_policy: VersionPin
    validators: tuple[VersionPin, ...]
    render_profile: VersionPin
    model_parameters_hash: Hash

    @model_validator(mode='after')
    def validator_pins(self):
        if len(self.validators) != len(set(self.validators)):
            raise ValueError('DUPLICATE_VALIDATOR')
        return self


class ModelExecutionReceipt(Value):
    contract: Literal['urn:lukart:work:ModelExecutionReceipt:1.0.0']
    request_id: UUID
    provider: VersionPin
    model: VersionPin
    generator: VersionPin
    model_parameters_hash: Hash


class DraftingInvocation(Value):
    contract: Literal['urn:lukart:work:DraftingInvocation:1.0.0']
    section: Ref
    evaluation_date: date
    request: AIRequest

    @model_validator(mode='after')
    def binding(self):
        if self.section.kind != 'Section' or self.request.task != 'DRAFTING':
            raise ValueError('DRAFTING_BINDING')
        return self


class DraftingTrace(Value):
    contract: Literal['urn:lukart:work:DraftingTrace:1.0.0']
    id: UUID
    tenant_id: UUID
    case_id: UUID
    command_id: UUID
    actor: Actor
    recorded_at: datetime
    profile: DraftingProfile
    invocations: tuple[DraftingInvocation, ...]
    results: tuple[AIResult, ...]
    execution_receipts: tuple[ModelExecutionReceipt, ...]
    raw_outputs: tuple[str, ...]
    input_hash: Hash
    raw_output_hash: Hash

    @model_validator(mode='after')
    def complete_trace(self):
        if self.recorded_at.tzinfo is None:
            raise ValueError('TIMEZONE_REQUIRED')
        if (
            not self.invocations
            or len(self.invocations) != len(self.results)
            or len(self.results) != len(self.execution_receipts)
            or len(self.results) != len(self.raw_outputs)
        ):
            raise ValueError('INCOMPLETE_TRACE')
        request_ids = tuple(item.request.request_id for item in self.invocations)
        if len(set(request_ids)) != len(request_ids):
            raise ValueError('DUPLICATE_REQUEST')
        if request_ids != tuple(result.request_id for result in self.results):
            raise ValueError('TRACE_MISMATCH')
        if request_ids != tuple(receipt.request_id for receipt in self.execution_receipts):
            raise ValueError('EXECUTION_RECEIPT_MISMATCH')
        return self


class DraftingRejectionTrace(Value):
    contract: Literal['urn:lukart:work:DraftingRejectionTrace:1.0.0']
    id: UUID
    tenant_id: UUID
    case_id: UUID
    command_id: UUID
    actor: Actor
    recorded_at: datetime
    profile: DraftingProfile
    invocations: tuple[DraftingInvocation, ...]
    results: tuple[AIResult, ...]
    execution_receipts: tuple[ModelExecutionReceipt, ...]
    raw_outputs: tuple[str, ...]
    error: DomainError
    input_hash: Hash
    raw_output_hash: Hash

    @model_validator(mode='after')
    def rejection_trace(self):
        if self.recorded_at.tzinfo is None:
            raise ValueError('TIMEZONE_REQUIRED')
        if not self.invocations:
            raise ValueError('INCOMPLETE_TRACE')
        if (
            len(self.results) > len(self.raw_outputs)
            or len(self.raw_outputs) > len(self.invocations)
            or len(self.execution_receipts) > len(self.invocations)
        ):
            raise ValueError('INCOMPLETE_TRACE')
        request_ids = tuple(item.request.request_id for item in self.invocations)
        if len(set(request_ids)) != len(request_ids):
            raise ValueError('DUPLICATE_REQUEST')
        if request_ids[:len(self.results)] != tuple(result.request_id for result in self.results):
            raise ValueError('TRACE_MISMATCH')
        if request_ids[:len(self.execution_receipts)] != tuple(
            receipt.request_id for receipt in self.execution_receipts
        ):
            raise ValueError('EXECUTION_RECEIPT_MISMATCH')
        return self
