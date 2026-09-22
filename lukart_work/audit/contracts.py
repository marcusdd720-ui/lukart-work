"""Stage 12 immutable audit/provenance projection contracts."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lukart_work.contracts.messages import DomainEvent
from lukart_work.domain.models import Hash, Ref, SourceAnchor, Text, Value, VersionPin


class AuditRevisionPin(Value):
    ref: Ref
    content_hash: Hash


class AuditObjectPin(Value):
    category: Text
    object_id: UUID
    contract: Text
    content_hash: Hash


class AuditCommandPin(Value):
    idempotency_key: UUID
    input_hash: Hash
    contract: Text
    content_hash: Hash


class AuditPackage(Value):
    contract: Literal['urn:lukart:work:AuditPackage:1.0.0']
    tenant_id: UUID
    case_id: UUID
    case_sequence: Annotated[int, Field(ge=1)]
    heads: tuple[Ref, ...]
    revisions: tuple[AuditRevisionPin, ...]
    objects: tuple[AuditObjectPin, ...]
    commands: tuple[AuditCommandPin, ...]
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

        revision_refs = tuple(item.ref for item in self.revisions)
        revision_keys = tuple((r.kind, str(r.id), r.revision) for r in revision_refs)
        if len(set(revision_refs)) != len(revision_refs) or revision_keys != tuple(sorted(revision_keys)):
            raise ValueError('AUDIT_REVISION_ORDER')
        if len(set(self.heads)) != len(self.heads) or any(head not in set(revision_refs) for head in self.heads):
            raise ValueError('AUDIT_HEADS')
        head_keys = tuple((r.kind, str(r.id), r.revision) for r in self.heads)
        if head_keys != tuple(sorted(head_keys)):
            raise ValueError('AUDIT_HEAD_ORDER')

        object_keys = tuple((item.category, str(item.object_id)) for item in self.objects)
        if len(set(object_keys)) != len(object_keys) or object_keys != tuple(sorted(object_keys)):
            raise ValueError('AUDIT_OBJECT_ORDER')
        command_keys = tuple(str(item.idempotency_key) for item in self.commands)
        if len(set(command_keys)) != len(command_keys) or command_keys != tuple(sorted(command_keys)):
            raise ValueError('AUDIT_COMMAND_ORDER')

        previous = None
        last_sequence = 0
        for event, event_hash in zip(self.events, self.event_hashes):
            audit = event.audit
            if (audit.tenant_id, audit.case_id) != (self.tenant_id, self.case_id):
                raise ValueError('CROSS_CASE')
            if audit.sequence < last_sequence or audit.sequence > last_sequence + 1:
                raise ValueError('AUDIT_SEQUENCE')
            if audit.previous_event_hash != previous:
                raise ValueError('AUDIT_CHAIN')
            previous = event_hash
            last_sequence = audit.sequence
        if last_sequence != self.case_sequence:
            raise ValueError('AUDIT_SEQUENCE')
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


STAGE12_CONTRACTS = (AuditRevisionPin, AuditObjectPin, AuditCommandPin, AuditPackage, AuditTrace)
