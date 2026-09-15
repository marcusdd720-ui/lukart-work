"""Authenticated intent handlers, authoritative guard orchestration and safe queries."""
import base64
import binascii
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import ValidationError
from lukart_work.domain import models as m
from lukart_work.domain.lifecycle import INITIAL
from lukart_work.contracts import messages as wire
from lukart_work.validation.rules import (
    Violation, digest, ref, walk, resolve, validate_graph, validate_revision,
    validate_state, validate_snapshot, validate_snapshot_acceptance, strict_json, affected,
)
from .requests import parse_request, CoreQuery
from .policy import rule_pin

ADD = {
    'CreateCase': m.Case, 'AddParty': m.Party, 'AddInstitution': m.Institution,
    'AddProceeding': m.Proceeding, 'AddFiling': m.Filing, 'AddEvidence': m.Evidence,
    'AddFact': m.Fact, 'AddIssue': m.Issue, 'AddClaim': m.Claim,
    'AddRequest': m.Request, 'AddSection': m.Section, 'AddPlan': m.DocumentPlan,
}
EDIT = {'EditCase': m.Case, 'EditParty': m.Party, 'EditFact': m.Fact}
CHANGE = {
    'SuspendCase': ('Case', 'SUSPENDED'), 'CloseCase': ('Case', 'CLOSED'),
    'ReopenCase': ('Case', 'OPEN'), 'ArchiveCase': ('Case', 'ARCHIVED'),
    'DisputeParty': ('Party', 'DISPUTED'), 'VerifyParty': ('Party', 'VERIFIED'),
    'ReviewFact': ('Fact', 'REVIEWED'), 'ConfirmFact': ('Fact', 'CONFIRMED'),
    'DisputeFact': ('Fact', 'DISPUTED'), 'PrepareSection': ('Section', 'READY'),
    'ReviewPlan': ('DocumentPlan', 'REVIEWED'), 'ApprovePlan': ('DocumentPlan', 'APPROVED'),
    'SupersedePlan': ('DocumentPlan', 'SUPERSEDED'),
    'RevokeDecision': ('Decision', 'REVOKED'),
}
APPROVAL = {'VerifyParty': 'verification_decision', 'ConfirmFact': 'acceptance', 'ApprovePlan': 'approval'}
METADATA = set(m.Entity.model_fields) | {'kind', 'status'}
MANAGED = METADATA | {'verification_decision', 'acceptance', 'approval', 'adoption', 'resolution', 'review_decision'}
ERROR_CODES = set(wire.DomainError.model_fields['code'].annotation.__args__)


def safe_error(code, correlation_id):
    if code not in ERROR_CODES:
        code = 'GATE_DENIED'
    return wire.DomainError(code=code, path='', message=code, retryable=code == 'CONFLICT', correlation_id=correlation_id)


def entity_from(data, cls):
    return cls.model_validate_json(json.dumps(data, allow_nan=False))


class CommandService:
    def __init__(self, repository, authority, clock=None):
        self.repository = repository
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, raw, token):
        correlation = UUID(int=0)
        try:
            request = parse_request(raw)
            correlation = request.meta.correlation_id
            with self.authority.session(token) as principal:
                principal.require(request.meta.tenant_id, request.meta.case_id, request.operation)
                if principal.actor.kind == 'AI':
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(principal.tenant_id, principal.case_id) as tx:
                    # Actor is part of the replay identity; an authorized different actor
                    # cannot reuse another human's accepted command result.
                    input_hash = digest({'request': request.model_dump(mode='json'), 'actor': principal.actor.model_dump(mode='json')})
                    replay = tx.replay(request.meta.idempotency_key, input_hash)
                    if replay is not None:
                        return replay
                    sequence = tx.sequence()
                    if sequence != request.meta.expected_case_sequence:
                        raise Violation('CONFLICT')
                    records = tx.records()
                    heads = {(e.kind, e.id): e for e in tx.heads()}
                    case = heads.get(('Case', principal.case_id))
                    self._case_guard(request, principal, case)
                    instant = self.clock()
                    if instant.tzinfo is None:
                        raise Violation('SCHEMA_INVALID')
                    now = instant.astimezone(timezone.utc)
                    tx.set_sequence(sequence + 1)
                    subjects, event_type, output = self._apply(request, principal, tx, records, heads, now)
                    event_id = uuid5(request.meta.command_id, 'event')
                    event = wire.DomainEvent(event_type=event_type, subjects=subjects, audit=wire.AuditEvent(
                        event_id=event_id, tenant_id=principal.tenant_id, case_id=principal.case_id,
                        sequence=sequence + 1, actor=principal.actor, timestamp=now,
                        operation=request.operation, command_id=request.meta.command_id,
                        correlation_id=correlation, input_hash=input_hash, output_hash=digest(output),
                        previous_event_hash=tx.last_event_hash(),
                        source_versions=tuple(sorted(set(request.inputs) | set(walk(output, m.Ref)), key=lambda r: (r.kind, str(r.id), r.revision))),
                        model_provider=None, rule_version=rule_pin(),
                    ))
                    events = [event]
                    changed_targets = (request.target,) if request.target is not None else ()
                    if isinstance(output, m.Decision) and output.supersedes is not None:
                        changed_targets += (output.supersedes,)
                    if changed_targets:
                        edges = tx.objects('dependency', wire.DependencyEdge)
                        invalidated = tuple(sorted(affected(changed_targets, edges), key=lambda r: (r.kind, str(r.id), r.revision)))
                        if invalidated:
                            audit = event.audit.model_dump(mode='json')
                            audit.update(event_id=str(uuid5(request.meta.command_id, 'invalidated')), previous_event_hash=digest(event),
                                         output_hash=digest([r.model_dump(mode='json') for r in invalidated]))
                            events.append(wire.DomainEvent(event_type='DependenciesInvalidated', subjects=invalidated,
                                                          audit=wire.AuditEvent.model_validate_json(json.dumps(audit))))
                    result = wire.CommandResult(command_id=request.meta.command_id, state='APPLIED', case_sequence=sequence + 1,
                                                refs=subjects, event_ids=tuple(e.audit.event_id for e in events), errors=())
                    tx.finish(request, input_hash, result, events)
                    principal.require(request.meta.tenant_id, request.meta.case_id, request.operation)
                return result
        except Violation as error:
            return safe_error(error.code, correlation)
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError, OverflowError, binascii.Error):
            return safe_error('SCHEMA_INVALID', correlation)
        except Exception as error:
            # Driver messages can contain payloads/PII. Return only a fixed code.
            # Programming errors outside the database are not silently turned into PASS.
            if type(error).__module__.startswith('psycopg'):
                return safe_error('CONFLICT' if getattr(error, 'sqlstate', '') in ('23505', '40001', '40P01') else 'UNKNOWN', correlation)
            raise

    def _case_guard(self, request, principal, case):
        if request.operation == 'CreateCase':
            if case is not None or request.meta.expected_case_sequence != 0:
                raise Violation('CONFLICT')
            if principal.actor.kind != 'HUMAN':
                raise Violation('FORBIDDEN')
        elif case is None:
            raise Violation('BROKEN_REFERENCE')
        elif case.status == 'ARCHIVED':
            raise Violation('GATE_DENIED')
        elif case.status == 'CLOSED' and request.operation not in ('ReopenCase', 'ArchiveCase'):
            raise Violation('GATE_DENIED')
        if request.operation in ('ReopenCase', 'ArchiveCase', 'RevokeDecision', 'SupersedePlan') and principal.actor.kind != 'HUMAN':
            raise Violation('FORBIDDEN')

    def _metadata(self, request, principal, now, kind, old=None):
        entity_id = principal.case_id if kind == 'Case' else uuid5(request.meta.command_id, kind)
        inputs = request.inputs if 'inputs' in request.model_fields_set or old is None else old.provenance.inputs
        anchors = request.anchors if 'anchors' in request.model_fields_set or old is None else old.provenance.anchors
        return dict(schema_version='1.0.0', id=str(old.id if old else entity_id),
                    tenant_id=str(principal.tenant_id), case_id=str(principal.case_id),
                    revision=old.revision + 1 if old else 1, previous_hash=digest(old) if old else None,
                    created_at=old.created_at.isoformat() if old else now.isoformat(), recorded_at=now.isoformat(),
                    provenance=dict(actor=principal.actor.model_dump(mode='json'), operation_id=str(request.meta.command_id),
                                    method='MANUAL', inputs=[r.model_dump(mode='json') for r in inputs],
                                    anchors=[a.model_dump(mode='json') for a in anchors], rationale=request.rationale, tool=None), kind=kind)

    def _target(self, request, records, heads, kind=None):
        if request.target is None or (kind and request.target.kind != kind):
            raise Violation('SCHEMA_INVALID')
        old = resolve(request.target, records, request.meta.tenant_id, request.meta.case_id)
        if heads.get((old.kind, old.id)) != old:
            raise Violation('CONFLICT')
        return old

    def _live_decision(self, target, records, heads, principal):
        decision = resolve(target, records, principal.tenant_id, principal.case_id)
        if decision.kind != 'Decision' or decision.status != 'RECORDED' or heads.get(('Decision', decision.id)) != decision:
            raise Violation('GATE_DENIED')
        # A separately recorded superseding decision also invalidates the old approval.
        if any(e.kind == 'Decision' and e.status == 'RECORDED' and e.supersedes == target for e in records.values()):
            raise Violation('GATE_DENIED')
        return decision

    def _validate(self, entity, old, tx, records, heads, principal):
        if old is None:
            if entity.revision != 1 or entity.status != INITIAL[entity.kind]:
                raise Violation('INVALID_TRANSITION')
        else:
            validate_revision(old, entity)
        candidate = dict(records)
        candidate[ref(entity)] = entity
        sources = {s.id: s for s in tx.objects('source', wire.SourceDocument)}
        validate_graph(tuple(candidate.values()), sources)
        for anchor in walk(entity, m.SourceAnchor):
            tx.source_bytes(anchor.document_id)
        # Provenance describes historical inputs, not active approval authority.
        authority_refs = (r for name in type(entity).model_fields if name != 'provenance'
                          for r in walk(getattr(entity, name), m.Ref))
        if entity.kind == 'DocumentPlan' and entity.status == 'SUPERSEDED':
            authority_refs = ()  # Preserve immutable historical approval, without reusing its authority.
        for target in authority_refs:
            if target.kind == 'Decision':
                if entity.kind == 'Decision' and target == entity.supersedes:
                    continue
                self._live_decision(target, records, heads, principal)
        validate_state(entity, candidate)
        if entity.kind == 'Fact' and entity.status == 'CONFIRMED':
            for target in entity.evidence:
                current = heads.get(('Evidence', target.id))
                if current is None or current.status in ('CHALLENGED', 'EXCLUDED'):
                    raise Violation('GATE_DENIED')
        if entity.kind == 'DocumentPlan' and entity.status == 'APPROVED':
            snapshot = tx.object('snapshot', entity.input_snapshot_id, wire.Snapshot)
            decision = tx.object('acceptance', snapshot.id, m.Decision)
            self._live_decision(ref(decision), records, heads, principal)
            validate_snapshot_acceptance(snapshot, decision, records)
            if digest(snapshot) != entity.input_snapshot_hash:
                raise Violation('INVALID_HASH')
            required = {entity.filing, entity.recipient, *entity.objectives, *entity.argument_order, *entity.evidence, *entity.section_order}
            if not required <= {member.ref for member in snapshot.members}:
                raise Violation('GATE_DENIED')
            self._snapshot_heads(snapshot, heads)
        return entity

    @staticmethod
    def _snapshot_heads(snapshot, heads):
        # New approvals may be recorded after freeze. Existing input identities
        # must still have the versions actually selected when the snapshot was made.
        if any(ref(heads.get((r.kind, r.id))) != r for r in snapshot.heads if heads.get((r.kind, r.id)) is not None):
            raise Violation('STALE')
        if any((r.kind, r.id) not in heads for r in snapshot.heads):
            raise Violation('STALE')

    def _apply(self, request, principal, tx, records, heads, now):
        operation = request.operation
        data = dict(request.data)
        if operation in ('GenerateDocument', 'ValidateDraft', 'RequestRelease'):
            raise Violation('GATE_DENIED')
        if operation == 'RegisterSource':
            if request.target is not None or set(data) != {'content_base64', 'media_type', 'retention_policy'}:
                raise Violation('SCHEMA_INVALID')
            content = base64.b64decode(data['content_base64'], validate=True)
            source_id = uuid5(request.meta.command_id, 'source')
            source = wire.SourceDocument(id=source_id, tenant_id=principal.tenant_id, case_id=principal.case_id,
                       content_hash=sha256(content).hexdigest(), media_type=data['media_type'], byte_length=len(content),
                       object_key=f'case-core/{source_id}', received_at=now, actor=principal.actor,
                       retention_policy=m.VersionPin.model_validate_json(json.dumps(data['retention_policy'])))
            tx.put_object('source', source.id, source, content)
            return (), 'RevisionAppended', source
        if operation == 'CreateSnapshot':
            if request.target is not None or set(data) != {'rule_set', 'policy', 'knowledge_pins'}:
                raise Violation('SCHEMA_INVALID')
            # All current heads plus the complete historical closure, no live reads later.
            selected = {ref(e) for e in heads.values()}
            pending = list(selected)
            while pending:
                entity = records[pending.pop()]
                for target in walk(entity, m.Ref):
                    if target not in selected:
                        selected.add(target)
                        pending.append(target)
            ordered = sorted(selected, key=lambda r: (r.kind, str(r.id), r.revision))
            source_ids = {a.document_id for target in ordered for a in walk(records[target], m.SourceAnchor)}
            sources = tuple(tx.object('source', i, wire.SourceDocument) for i in sorted(source_ids, key=str))
            for current in heads.values():
                if current.kind != 'Decision' and not (current.kind == 'DocumentPlan' and current.status == 'SUPERSEDED'):
                    targets = (r for name in type(current).model_fields if name != 'provenance'
                               for r in walk(getattr(current, name), m.Ref))
                    for target in targets:
                        if target.kind == 'Decision':
                            self._live_decision(target, records, heads, principal)
            for source in sources:
                tx.source_bytes(source.id)
            snapshot = wire.Snapshot.model_validate_json(json.dumps(dict(
                schema_version='1.0.0', id=str(uuid5(request.meta.command_id, 'snapshot')),
                tenant_id=str(principal.tenant_id), case_id=str(principal.case_id),
                case_sequence=request.meta.expected_case_sequence, created_at=now.isoformat(),
                members=[{'ref': r.model_dump(mode='json'), 'content_hash': digest(records[r])} for r in ordered],
                heads=[ref(e).model_dump(mode='json') for e in heads.values()],
                sources=[s.model_dump(mode='json') for s in sources], **data)))
            validate_snapshot(snapshot, records)
            tx.put_object('snapshot', snapshot.id, snapshot)
            return (), 'RevisionAppended', snapshot
        if operation == 'AcceptSnapshot':
            if request.target is not None or set(data) != {'snapshot_id', 'decision'}:
                raise Violation('SCHEMA_INVALID')
            snapshot = tx.object('snapshot', UUID(data['snapshot_id']), wire.Snapshot)
            decision_ref = m.Ref.model_validate_json(json.dumps(data['decision']))
            decision = self._live_decision(decision_ref, records, heads, principal)
            validate_snapshot_acceptance(snapshot, decision, records)
            self._snapshot_heads(snapshot, heads)
            for source in snapshot.sources:
                tx.source_bytes(source.id)
            tx.put_object('acceptance', snapshot.id, decision)
            return (decision_ref,), 'SnapshotAccepted', snapshot
        if operation == 'RecordDecision':
            if request.target is not None or principal.actor.kind != 'HUMAN' or set(data) & (METADATA | {'decided_by'}):
                raise Violation('FORBIDDEN')
            if data.get('decision_type') in ('CERTIFICATION', 'DOCUMENT_APPROVAL'):
                raise Violation('GATE_DENIED')
            proposal = entity_from(dict(data, **self._metadata(request, principal, now, 'Decision'),
                                        status='PROPOSED', decided_by=principal.actor.model_dump(mode='json')), m.Decision)
            for target in proposal.targets:
                current = heads.get((target.kind, target.id))
                if current is None or ref(current) != target:
                    raise Violation('STALE')
            if proposal.decision_type == 'SNAPSHOT_ACCEPTANCE':
                snapshot = tx.object('snapshot', proposal.snapshot_target.snapshot_id, wire.Snapshot)
                if digest(snapshot) != proposal.snapshot_target.snapshot_hash:
                    raise Violation('INVALID_HASH')
                self._snapshot_heads(snapshot, heads)
            self._validate(proposal, None, tx, records, heads, principal)
            tx.append(proposal)
            records[ref(proposal)] = proposal
            body = proposal.model_dump(mode='json')
            body.update(revision=2, previous_hash=digest(proposal), status='RECORDED')
            recorded = entity_from(body, m.Decision)
            self._validate(recorded, proposal, tx, records, heads, principal)
            tx.append(recorded)
            return (ref(recorded),), 'DecisionRecorded', recorded
        old = None
        if operation in ADD:
            if request.target is not None or set(data) & MANAGED:
                raise Violation('SCHEMA_INVALID')
            cls = ADD[operation]
            if operation == 'CreateCase':
                if 'owner_id' in data and data['owner_id'] != str(principal.actor.id):
                    raise Violation('FORBIDDEN')
                data['owner_id'] = str(principal.actor.id)
            entity = entity_from(dict(data, **self._metadata(request, principal, now, cls.__name__), status=INITIAL[cls.__name__]), cls)
        elif operation in EDIT:
            cls = EDIT[operation]
            old = self._target(request, records, heads, cls.__name__)
            if set(data) & MANAGED or (old.kind == 'Case' and 'owner_id' in data):
                raise Violation('FORBIDDEN')
            if old.kind == 'Party' and old.status == 'VERIFIED' or old.kind == 'Fact' and old.status == 'CONFIRMED':
                raise Violation('GATE_DENIED')
            body = old.model_dump(mode='json')
            body.update(data)
            body.update(self._metadata(request, principal, now, old.kind, old))
            entity = entity_from(body, cls)
        elif operation in CHANGE:
            kind, status = CHANGE[operation]
            old = self._target(request, records, heads, kind)
            expected_fields = {'decision'} if operation in APPROVAL else set()
            if set(data) != expected_fields:
                raise Violation('SCHEMA_INVALID')
            body = old.model_dump(mode='json')
            body.update(self._metadata(request, principal, now, old.kind, old))
            body['status'] = status
            if operation == 'DisputeParty':
                body['verification_decision'] = None
            elif operation == 'DisputeFact':
                body['acceptance'] = None
            if operation in APPROVAL:
                if principal.actor.kind != 'HUMAN':
                    raise Violation('FORBIDDEN')
                body[APPROVAL[operation]] = data['decision']
            entity = entity_from(body, type(old))
        else:
            raise Violation('FORBIDDEN')
        self._validate(entity, old, tx, records, heads, principal)
        tx.append(entity)
        if entity.kind == 'DocumentPlan':
            snapshot = tx.object('snapshot', entity.input_snapshot_id, wire.Snapshot)
            if digest(snapshot) != entity.input_snapshot_hash:
                raise Violation('INVALID_HASH')
            # These are explicit frozen inputs of this plan, not semantic KG edges.
            inputs = {member.ref: member.content_hash for member in snapshot.members}
            if entity.approval is not None:
                inputs[entity.approval] = digest(records[entity.approval])
            # Acceptance is necessarily recorded after the frozen snapshot.
            # Its withdrawal invalidates plans even though it is not a member.
            acceptance = next((d for d in tx.objects('acceptance', m.Decision)
                               if d.snapshot_target and d.snapshot_target.snapshot_id == snapshot.id), None)
            if acceptance is not None:
                inputs[ref(acceptance)] = digest(acceptance)
            for target, content_hash in inputs.items():
                edge = wire.DependencyEdge(source=target, target=ref(entity), input_hash=content_hash)
                tx.put_object('dependency', uuid5(request.meta.command_id, digest(edge)), edge)
            affected((), tx.objects('dependency', wire.DependencyEdge))
        return (ref(entity),), 'PlanApproved' if operation == 'ApprovePlan' else 'RevisionAppended', entity

    def query(self, raw, token):
        try:
            query = CoreQuery.model_validate_json(json.dumps(strict_json(raw)))
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id, query.case_id, query.operation)
                with self.repository.transaction(query.tenant_id, query.case_id) as tx:
                    if not tx.sequence():
                        raise Violation('BROKEN_REFERENCE')
                    records = tx.records()
                    if query.operation == 'GetCaseHead':
                        result = wire.CaseHeadResult(result_type='CASE_HEAD', tenant_id=query.tenant_id, case_id=query.case_id,
                                                    case_sequence=tx.sequence(), heads=tuple(ref(e) for e in tx.heads()))
                    elif query.operation == 'GetSnapshot':
                        if query.object_id is None:
                            raise Violation('SCHEMA_INVALID')
                        snapshot = tx.object('snapshot', query.object_id, wire.Snapshot)
                        result = wire.SnapshotResult(result_type='SNAPSHOT', snapshot=snapshot, content_hash=digest(snapshot))
                    elif query.operation == 'GetSource':
                        if query.object_id is None:
                            raise Violation('SCHEMA_INVALID')
                        result = tx.source_bytes(query.object_id)
                    else:
                        if query.target is None:
                            raise Violation('SCHEMA_INVALID')
                        entity = resolve(query.target, records, query.tenant_id, query.case_id)
                        if query.operation == 'GetRevision':
                            result = wire.RevisionResult(result_type='REVISION', entity=entity)
                        elif query.operation == 'GetProvenance':
                            visited, anchors, pending = set(), set(), [query.target]
                            while pending:
                                target = pending.pop()
                                if target in visited:
                                    continue
                                visited.add(target)
                                item = records[target]
                                anchors.update(walk(item, m.SourceAnchor))
                                pending.extend(walk(item, m.Ref))
                            for anchor in anchors:
                                tx.source_bytes(anchor.document_id)
                            result = wire.ProvenanceResult(result_type='PROVENANCE', tenant_id=query.tenant_id, case_id=query.case_id,
                                target=query.target, sources=tuple(sorted(anchors, key=lambda a: a.model_dump_json())),
                                revisions=tuple(sorted(visited, key=lambda r: (r.kind, str(r.id), r.revision))),
                                completeness='COMPLETE' if anchors else 'INCOMPLETE')
                        else:
                            # Draft creation belongs to Stage 09. If a future adapter has
                            # inserted drafts without a dependency index, never report CURRENT.
                            edges = tx.objects('dependency', wire.DependencyEdge)
                            consumers = affected((query.target,), edges)
                            assessments = tuple(wire.FreshnessAssessment(target=ref(e), snapshot_hash=e.snapshot_hash,
                                current_case_sequence=tx.sequence(), state='STALE' if ref(e) in consumers else 'UNKNOWN',
                                changed_inputs=(query.target,) if ref(e) in consumers else ())
                                for e in tx.heads() if e.kind == 'Draft')
                            result = wire.AffectedDraftsResult(result_type='AFFECTED_DRAFTS', tenant_id=query.tenant_id,
                                        case_id=query.case_id, case_sequence=tx.sequence(), assessments=assessments)
                    principal.require(query.tenant_id, query.case_id, query.operation)
                return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('UNKNOWN', UUID(int=0))
            raise
