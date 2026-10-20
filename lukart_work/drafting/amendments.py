"""Explicit HUMAN text amendments; the original model trace remains immutable."""
import json
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid5
from typing import Literal

from pydantic import Field, model_validator

from lukart_work.contracts.messages import DependencyEdge
from lukart_work.domain import models as m
from lukart_work.validation.rules import Violation, digest, ref, resolve

CATEGORY = 'human_draft_amendment'
RECEIPT_PREFIX = 'urn:lukart:work:HumanDraftAmendmentReceipt:'


def sections_hash(sections):
    return digest([section.model_dump(mode='json') for section in sections])


class DraftTextEdit(m.Value):
    statement_id: UUID
    text: m.Text

    @model_validator(mode='after')
    def nonblank(self):
        if not self.text.strip():
            raise ValueError('TEXT_REQUIRED')
        return self


class AmendDraft(m.Value):
    contract: Literal['urn:lukart:work:AmendDraft:1.0.0']
    draft_hash: m.Hash
    edits: tuple[DraftTextEdit, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def unique(self):
        if len({e.statement_id for e in self.edits}) != len(self.edits):
            raise ValueError('DUPLICATE_STATEMENT')
        return self


class DraftEditorQuery(m.Value):
    contract: Literal['urn:lukart:work:DraftEditorQuery:1.0.0']
    operation: Literal['GetDraftForEditing']
    tenant_id: UUID
    case_id: UUID
    draft: m.Ref


class DraftEditorProjection(m.Value):
    result_type: Literal['DRAFT_EDITOR'] = 'DRAFT_EDITOR'
    draft: m.Draft
    draft_hash: m.Hash
    case_sequence: int = Field(ge=1)
    validation_policy: m.VersionPin
    semantic_profile: m.VersionPin
    editable: bool
    review_id: UUID | None = None
    validation_run_id: UUID | None = None
    render_id: UUID | None = None


class HumanDraftAmendmentReceipt(m.Value):
    contract: Literal['urn:lukart:work:HumanDraftAmendmentReceipt:1.0.0']
    id: UUID
    tenant_id: UUID
    case_id: UUID
    command_id: UUID
    actor: m.Actor
    recorded_at: datetime
    predecessor: m.Ref
    predecessor_hash: m.Hash
    output: m.Ref
    sections_hash: m.Hash
    original_reproduction_hash: m.Hash
    edits: tuple[DraftTextEdit, ...]
    rationale: m.Text

    @model_validator(mode='after')
    def binding(self):
        if (self.actor.kind != 'HUMAN' or self.recorded_at.tzinfo is None
                or self.predecessor.kind != 'Draft' or self.output.kind != 'Draft'
                or self.output.revision != 2 or self.output.id == self.predecessor.id
                or not self.rationale.strip()):
            raise ValueError('HUMAN_AMENDMENT_BINDING')
        return self


def edited_sections(old, edits):
    changes = {e.statement_id: e.text for e in edits}
    statements = [s for section in old.sections for s in section.statements]
    if (len({s.id for s in statements}) != len(statements)
            or not changes.keys() <= {s.id for s in statements}
            or not any(s.text != changes.get(s.id, s.text) for s in statements)):
        raise Violation('SCHEMA_INVALID')
    return tuple(section.model_copy(update={'statements': tuple(
        statement.model_copy(update={'text': changes.get(statement.id, statement.text)})
        for statement in section.statements)}) for section in old.sections)


def verify_amendment(tx, draft, records):
    """Check the immutable generated revision, including after validation revisions."""
    seen = set()
    while draft.supersedes is not None:
        if draft.id in seen or len(seen) >= 1000:
            raise Violation('PROVENANCE_MISSING')
        seen.add(draft.id)
        generated_ref = m.Ref(kind='Draft', id=draft.id, revision=2)
        generated = draft if ref(draft) == generated_ref else resolve(
            generated_ref, records, draft.tenant_id, draft.case_id)
        predecessor = resolve(generated.supersedes, records, draft.tenant_id, draft.case_id)
        receipt_id = uuid5(generated.provenance.operation_id, 'human-draft-amendment')
        receipt = tx.object(CATEGORY, receipt_id, HumanDraftAmendmentReceipt)
        tool = m.VersionPin(id=RECEIPT_PREFIX + str(receipt_id), version='1.0.0', content_hash=digest(receipt))
        if (receipt.id != receipt_id or receipt.command_id != generated.provenance.operation_id
                or (receipt.tenant_id, receipt.case_id) != (draft.tenant_id, draft.case_id)
                or receipt.actor != generated.provenance.actor
                or generated.provenance.method != 'MANUAL' or generated.provenance.tool != tool
                or receipt.recorded_at != generated.created_at
                or receipt.rationale != generated.provenance.rationale
                or receipt.predecessor != ref(predecessor) or receipt.predecessor_hash != digest(predecessor)
                or generated.status != 'GENERATED'
                or receipt.output != generated_ref or receipt.sections_hash != sections_hash(generated.sections)
                or receipt.original_reproduction_hash != digest(predecessor.reproduction)
                or generated.reproduction != predecessor.reproduction
                or generated.plan != predecessor.plan
                or (generated.snapshot_id, generated.snapshot_hash) != (predecessor.snapshot_id, predecessor.snapshot_hash)
                or generated.sections != edited_sections(predecessor, receipt.edits)
                or draft.sections != generated.sections or draft.reproduction != generated.reproduction
                or draft.plan != generated.plan or draft.supersedes != generated.supersedes
                or (draft.snapshot_id, draft.snapshot_hash) != (generated.snapshot_id, generated.snapshot_hash)):
            raise Violation('PROVENANCE_MISSING')
        draft = predecessor


def amend(service, request, principal, tx, records, heads, now):
    from .service import ControlledDraftingService
    from lukart_work.core.service import entity_from

    if principal.actor.kind != 'HUMAN':
        raise Violation('FORBIDDEN')
    if request.inputs or request.anchors or not request.rationale.strip():
        raise Violation('SCHEMA_INVALID')
    data = AmendDraft.model_validate_json(json.dumps(request.data))
    old = service._target(request, records, heads, 'Draft')
    if old.status not in ('GENERATED', 'VALIDATED'):
        raise Violation('GATE_DENIED')
    if digest(old) != data.draft_hash:
        raise Violation('INVALID_HASH')
    if any(r.predecessor.id == old.id for r in tx.objects(CATEGORY, HumanDraftAmendmentReceipt)):
        raise Violation('STALE')
    verify_amendment(tx, old, records)
    plan = resolve(old.plan, records, principal.tenant_id, principal.case_id)
    filing = resolve(plan.filing, records, principal.tenant_id, principal.case_id)
    context = SimpleNamespace(operation='AmendDraft', plan=old.plan, snapshot_id=old.snapshot_id,
        snapshot_hash=old.snapshot_hash, document_type=filing.document_type,
        objective_ids=tuple(r.id for r in plan.objectives))
    drafting = ControlledDraftingService(service.repository, service.authority, None, {})
    _, _, snapshot, plan, sections, approval, acceptance = drafting._context(context, principal, tx, now.date())
    updated = edited_sections(old, data.edits)
    output = m.Ref(kind='Draft', id=uuid5(request.meta.command_id, 'Draft'), revision=2)
    receipt_id = uuid5(request.meta.command_id, 'human-draft-amendment')
    receipt = HumanDraftAmendmentReceipt(contract='urn:lukart:work:HumanDraftAmendmentReceipt:1.0.0',
        id=receipt_id, tenant_id=principal.tenant_id, case_id=principal.case_id,
        command_id=request.meta.command_id, actor=principal.actor, recorded_at=now,
        predecessor=ref(old), predecessor_hash=digest(old), output=output,
        sections_hash=sections_hash(updated), original_reproduction_hash=digest(old.reproduction),
        edits=data.edits, rationale=request.rationale)
    tx.put_object(CATEGORY, receipt.id, receipt)
    body = old.model_dump(mode='json')
    body.update(service._metadata(request, principal, now, 'Draft'))
    body.update(status='PLANNED', sections=[s.model_dump(mode='json') for s in updated],
                supersedes=ref(old).model_dump(mode='json'))
    body['provenance'].update(inputs=[ref(old).model_dump(mode='json')],
        tool=m.VersionPin(id=RECEIPT_PREFIX + str(receipt_id), version='1.0.0', content_hash=digest(receipt)).model_dump(mode='json'))
    planned = entity_from(body, m.Draft)
    service._validate(planned, None, tx, records, heads, principal)
    tx.append(planned)
    records[ref(planned)] = planned
    body.update(revision=2, previous_hash=digest(planned), status='GENERATED')
    generated = entity_from(body, m.Draft)
    service._validate(generated, planned, tx, records, heads, principal)
    tx.append(generated)
    records[ref(generated)] = generated
    drafting._dependencies(request, tx, generated, snapshot, plan, sections, approval, acceptance)
    edge = DependencyEdge(source=ref(old), target=ref(generated), input_hash=digest(old))
    tx.put_object('dependency', uuid5(request.meta.command_id, digest(edge)), edge)
    return (ref(generated),), 'RevisionAppended', generated


def query_editor(operator, raw, token):
    from pydantic import ValidationError
    from lukart_work.core.service import safe_error
    from lukart_work.validation.rules import strict_json
    from lukart_work.validation.policy import validation_pin
    from lukart_work.validation.contracts import ValidationReview, ValidationExecution
    from lukart_work.finalization.contracts import semantic_profile_pin, PersistedRender
    try:
        query = DraftEditorQuery.model_validate_json(json.dumps(strict_json(raw)))
        if query.draft.kind != 'Draft':
            raise Violation('SCHEMA_INVALID')
        with operator.core.authority.session(token) as principal:
            for action in ('GetRevision', 'GetCaseHead'):
                principal.require(query.tenant_id, query.case_id, action)
            with operator.core.repository.transaction(query.tenant_id, query.case_id) as tx:
                records = tx.records()
                draft = resolve(query.draft, records, query.tenant_id, query.case_id)
                verify_amendment(tx, draft, records)
                policy = validation_pin()
                reviews = [r for r in tx.objects('validation_review', ValidationReview)
                           if r.draft == ref(draft) and r.draft_hash == digest(draft) and r.policy == policy]
                executions = [e for e in tx.objects('validation_execution', ValidationExecution)
                    if e.output_draft == ref(draft) and e.output_hash == digest(draft)
                    and e.validator == policy and e.committed_sequence == tx.sequence()]
                renders = [r for r in tx.objects('finalization_render', PersistedRender)
                           if r.validated_draft.id == draft.id]
                children = tx.objects(CATEGORY, HumanDraftAmendmentReceipt)
                current = next((h for h in tx.heads() if h.kind == 'Draft' and h.id == draft.id), None)
                return DraftEditorProjection(draft=draft, draft_hash=digest(draft), case_sequence=tx.sequence(),
                    validation_policy=policy, semantic_profile=semantic_profile_pin(operator.case_profile),
                    editable=(principal.actor.kind == 'HUMAN' and 'AmendDraft' in principal.actions
                        and draft.status in ('GENERATED', 'VALIDATED') and current == draft
                        and not any(r.predecessor.id == draft.id for r in children)),
                    review_id=max(reviews, key=lambda r: r.recorded_at).id if reviews else None,
                    validation_run_id=executions[-1].id if executions else None,
                    render_id=renders[-1].id if renders else None)
    except Violation as error:
        return safe_error(error.code, UUID(int=0))
    except (ValidationError, ValueError, KeyError, TypeError, RecursionError):
        return safe_error('SCHEMA_INVALID', UUID(int=0))
    except Exception as error:
        if type(error).__module__.startswith('psycopg'):
            return safe_error('UNKNOWN', UUID(int=0))
        raise
