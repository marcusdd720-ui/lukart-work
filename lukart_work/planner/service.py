"""Stage 08 deterministic Document Planner over accepted immutable snapshots."""
import json
from uuid import UUID, uuid5

from pydantic import ValidationError

from lukart_work.contracts import messages as wire
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.validation.rules import (
    Violation, affected, digest, ref, resolve, strict_json, validate_snapshot_acceptance,
)
from .contracts import DocumentPlanProjection, PlannerQuery, PlannerRequest


class DocumentPlannerService(CommandService):
    def _parse_request(self, raw):
        value = strict_json(raw)
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > 64:
                raise Violation('SCHEMA_INVALID')
            if isinstance(item, dict):
                stack.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                stack.extend((v, depth + 1) for v in item)
        return PlannerRequest.model_validate_json(json.dumps(value, allow_nan=False))

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if principal.actor.kind != 'HUMAN':
            raise Violation('FORBIDDEN')

    def _save(self, entity, old, request, principal, tx, records, heads):
        self._validate(entity, old, tx, records, heads, principal)
        tx.append(entity)
        records[ref(entity)] = entity
        heads[(entity.kind, entity.id)] = entity
        return entity

    def _accepted_snapshot(self, data, principal, tx, records, heads):
        snapshot = tx.object('snapshot', data.snapshot_id, wire.Snapshot)
        if digest(snapshot) != data.snapshot_hash:
            raise Violation('INVALID_HASH')
        acceptance = tx.object('acceptance', snapshot.id, m.Decision)
        live = self._live_decision(ref(acceptance), records, heads, principal)
        validate_snapshot_acceptance(snapshot, live, records)
        self._snapshot_heads(snapshot, heads)
        for source in snapshot.sources:
            tx.source_bytes(source.id)
        return snapshot, live

    @staticmethod
    def _require_member(target, members, records, tenant_id, case_id, kind=None):
        if target not in members:
            raise Violation('SNAPSHOT_NOT_CLOSED')
        entity = resolve(target, records, tenant_id, case_id)
        if kind and entity.kind != kind:
            raise Violation('REFERENCE_TYPE')
        return entity

    def _dependencies(self, request, tx, entity, snapshot, records):
        inputs = {member.ref: member.content_hash for member in snapshot.members}
        acceptance = tx.object('acceptance', snapshot.id, m.Decision)
        inputs[ref(acceptance)] = digest(acceptance)
        if entity.approval is not None:
            inputs[entity.approval] = digest(records[entity.approval])
        for target, content_hash in inputs.items():
            edge = wire.DependencyEdge(source=target, target=ref(entity), input_hash=content_hash)
            tx.put_object('dependency', uuid5(request.meta.command_id, digest(edge)), edge)
        affected((), tx.objects('dependency', wire.DependencyEdge))

    def _plan(self, request, principal, tx, records, heads, now):
        data = request.data
        snapshot, _ = self._accepted_snapshot(data, principal, tx, records, heads)
        members = {member.ref for member in snapshot.members}

        filing = self._require_member(
            data.filing, members, records, principal.tenant_id, principal.case_id, 'Filing'
        )
        if heads.get(('Filing', filing.id)) != filing:
            raise Violation('STALE')
        recipient = self._require_member(
            filing.recipient, members, records, principal.tenant_id, principal.case_id
        )

        for target in data.objectives:
            objective = self._require_member(
                target, members, records, principal.tenant_id, principal.case_id, 'Request'
            )
            if objective.filing != data.filing or objective.status in ('WITHDRAWN', 'RESOLVED'):
                raise Violation('GATE_DENIED')
        for target in data.argument_order:
            argument = self._require_member(
                target, members, records, principal.tenant_id, principal.case_id, 'Argument'
            )
            if argument.status == 'WITHDRAWN':
                raise Violation('GATE_DENIED')
        for target in data.evidence:
            evidence = self._require_member(
                target, members, records, principal.tenant_id, principal.case_id, 'Evidence'
            )
            if evidence.status == 'EXCLUDED':
                raise Violation('GATE_DENIED')

        computed_inputs = {
            data.filing, filing.recipient, *data.objectives, *data.argument_order, *data.evidence,
            *(r for section in data.sections for r in (
                *section.arguments, *section.allowed_inputs, *section.required_inputs, *section.allowed_claims
            )),
        }
        if not computed_inputs <= members:
            raise Violation('SNAPSHOT_NOT_CLOSED')
        intent = request.model_copy(update={
            'inputs': tuple(sorted(computed_inputs, key=lambda r: (r.kind, str(r.id), r.revision)))
        })

        section_refs = []
        for index, blueprint in enumerate(data.sections):
            section_id = uuid5(request.meta.command_id, f'section:{index}')
            meta = self._metadata(intent, principal, now, 'Section')
            meta['id'] = str(section_id)
            planned = entity_from(dict(
                **meta,
                status='PLANNED',
                filing=data.filing.model_dump(mode='json'),
                section_type=blueprint.section_type,
                title=blueprint.title,
                arguments=[r.model_dump(mode='json') for r in blueprint.arguments],
                contract={
                    'allowed_inputs': [r.model_dump(mode='json') for r in blueprint.allowed_inputs],
                    'required_inputs': [r.model_dump(mode='json') for r in blueprint.required_inputs],
                    'allowed_claims': [r.model_dump(mode='json') for r in blueprint.allowed_claims],
                    'forbidden': list(blueprint.forbidden),
                    'requirements': list(blueprint.requirements),
                },
            ), m.Section)
            self._save(planned, None, intent, principal, tx, records, heads)

            ready_body = planned.model_dump(mode='json')
            ready_body.update(self._metadata(intent, principal, now, 'Section', planned))
            ready_body['status'] = 'READY'
            ready = entity_from(ready_body, m.Section)
            self._save(ready, planned, intent, principal, tx, records, heads)
            section_refs.append(ref(ready))

        plan = entity_from(dict(
            **self._metadata(intent, principal, now, 'DocumentPlan'),
            status='PROPOSED',
            filing=data.filing.model_dump(mode='json'),
            input_snapshot_id=str(snapshot.id),
            input_snapshot_hash=digest(snapshot),
            objectives=[r.model_dump(mode='json') for r in data.objectives],
            recipient=filing.recipient.model_dump(mode='json'),
            position_scope=data.position_scope,
            argument_order=[r.model_dump(mode='json') for r in data.argument_order],
            evidence=[r.model_dump(mode='json') for r in data.evidence],
            section_order=[r.model_dump(mode='json') for r in section_refs],
            approval=None,
        ), m.DocumentPlan)
        self._save(plan, None, intent, principal, tx, records, heads)
        self._dependencies(request, tx, plan, snapshot, records)
        return (ref(plan), *section_refs), 'RevisionAppended', plan

    def _transition(self, request, principal, tx, records, heads, now):
        old = self._target(request, records, heads, 'DocumentPlan')
        statuses = {
            'ReviewDocumentPlan': 'REVIEWED',
            'ApproveDocumentPlan': 'APPROVED',
            'SupersedeDocumentPlan': 'SUPERSEDED',
        }
        body = old.model_dump(mode='json')
        body.update(self._metadata(request, principal, now, old.kind, old))
        body['status'] = statuses[request.operation]
        if request.operation == 'ApproveDocumentPlan':
            decision = self._live_decision(request.data.decision, records, heads, principal)
            if (
                decision.decision_type != 'PLAN_APPROVAL'
                or decision.outcome != 'ACCEPT'
                or decision.decided_by.kind != 'HUMAN'
                or ref(old) not in decision.targets
            ):
                raise Violation('HUMAN_APPROVAL_REQUIRED')
            body['approval'] = request.data.decision.model_dump(mode='json')
        entity = entity_from(body, m.DocumentPlan)
        self._save(entity, old, request, principal, tx, records, heads)
        snapshot = tx.object('snapshot', entity.input_snapshot_id, wire.Snapshot)
        self._dependencies(request, tx, entity, snapshot, records)
        return (ref(entity),), 'PlanApproved' if entity.status == 'APPROVED' else 'RevisionAppended', entity

    def _apply(self, request, principal, tx, records, heads, now):
        if request.operation == 'PlanDocument':
            return self._plan(request, principal, tx, records, heads, now)
        return self._transition(request, principal, tx, records, heads, now)

    def get_plan(self, raw, token):
        try:
            query = PlannerQuery.model_validate_json(json.dumps(strict_json(raw), allow_nan=False))
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id, query.case_id, query.operation)
                if principal.actor.kind == 'AI':
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(query.tenant_id, query.case_id) as tx:
                    sequence = tx.sequence()
                    if not sequence:
                        raise Violation('BROKEN_REFERENCE')
                    records = tx.records()
                    plan = resolve(query.plan, records, query.tenant_id, query.case_id)
                    if plan.kind != 'DocumentPlan':
                        raise Violation('REFERENCE_TYPE')
                    sections = tuple(resolve(r, records, query.tenant_id, query.case_id) for r in plan.section_order)
                    snapshot = tx.object('snapshot', plan.input_snapshot_id, wire.Snapshot)
                    if digest(snapshot) != plan.input_snapshot_hash:
                        raise Violation('INVALID_HASH')
                    approval_current = False
                    heads = {(e.kind, e.id): e for e in tx.heads()}
                    if (
                        plan.status == 'APPROVED'
                        and plan.approval is not None
                        and heads.get(('DocumentPlan', plan.id)) == plan
                    ):
                        try:
                            decision = self._live_decision(plan.approval, records, heads, principal)
                            snapshot_acceptance = tx.object('acceptance', snapshot.id, m.Decision)
                            live_snapshot_acceptance = self._live_decision(
                                ref(snapshot_acceptance), records, heads, principal
                            )
                            validate_snapshot_acceptance(snapshot, live_snapshot_acceptance, records)
                            approval_current = (
                                decision.decision_type == 'PLAN_APPROVAL'
                                and decision.outcome == 'ACCEPT'
                                and decision.decided_by.kind == 'HUMAN'
                            )
                        except Violation:
                            approval_current = False
                    principal.require(query.tenant_id, query.case_id, query.operation)
                    return DocumentPlanProjection(
                        tenant_id=query.tenant_id,
                        case_id=query.case_id,
                        case_sequence=sequence,
                        plan=plan,
                        sections=sections,
                        snapshot_hash=digest(snapshot),
                        approval_current=approval_current,
                    )
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('UNKNOWN', UUID(int=0))
            raise
