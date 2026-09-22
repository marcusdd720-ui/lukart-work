"""Stage 12 immutable audit/provenance projection contracts."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.contracts.messages import DomainEvent
from lukart_work.domain.models import Hash, Ref, SourceAnchor, Value, VersionPin


class AuditPackage(Value):
    contract: Literal['urn:lukart:work:AuditPackage:1.0.0']
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    heads: tuple[Ref, ...]
    events: tuple[DomainEvent, ...]
    event_hashes: tuple[Hash, ...]
    outbox_event_ids: tuple[UUID, ...]
    chain_head_hash: Hash
    implementation: VersionPin

    @model_validator(mode='after')
    def coherent(self):
        if not self.events or len(self.events) != len(self.event_hashes):
            raise ValueError('AUDIT_EVENT_COUNT')
        ids = tuple(event.audit.event_id for event in self.events)
        if len(set(ids)) != len(ids) or self.outbox_event_ids != ids:
            raise ValueError('AUDIT_OUTBOX_MISMATCH')
        if self.chain_head_hash != self.event_hashes[-1]:
            raise ValueError('AUDIT_CHAIN_HEAD')
        if len(set(self.heads)) != len(self.heads):
            raise ValueError('DUPLICATE_HEAD')
        previous = None
        last_sequence = 0
        for event, event_hash in zip(self.events, self.event_hashes):
            audit = event.audit
            if (audit.tenant_id, audit.case_id) != (self.tenant_id, self.case_id):
                raise ValueError('CROSS_CASE')
            if audit.sequence < last_sequence or audit.sequence > self.case_sequence:
                raise ValueError('AUDIT_SEQUENCE')
            if audit.previous_event_hash != previous:
                raise ValueError('AUDIT_CHAIN')
            previous = event_hash
            last_sequence = audit.sequence
        return self


class AuditTrace(Value):
    contract: Literal['urn:lukart:work:AuditTrace:1.0.0']
    tenant_id: UUID
    case_id: UUID
    target: Ref
    package_hash: Hash
    revisions: tuple[Ref, ...]
    sources: tuple[SourceAnchor, ...]
    event_ids: tuple[UUID, ...]
    completeness: Literal['COMPLETE', 'INCOMPLETE', 'UNKNOWN']

    @model_validator(mode='after')
    def coherent(self):
        if self.target not in self.revisions:
            raise ValueError('TRACE_TARGET_MISSING')
        if len(set(self.revisions)) != len(self.revisions):
            raise ValueError('DUPLICATE_REVISION')
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError('DUPLICATE_EVENT')
        return self


STAGE12_CONTRACTS = (AuditPackage, AuditTrace)
