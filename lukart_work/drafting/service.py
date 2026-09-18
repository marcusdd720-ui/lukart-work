"""Stage 09 Controlled Drafting: model proposals are validated before any Draft commit."""
import json
from datetime import timezone
from uuid import UUID, uuid5

from pydantic import ValidationError

from lukart_work.contracts import messages as wire
from lukart_work.core.policy import rule_pin
from lukart_work.core.service import CommandService, safe_error
from lukart_work.domain import models as m
from lukart_work.validation.rules import (
    Violation,
    digest,
    ref,
    resolve,
    strict_json,
    validate_ai,
    validate_snapshot_acceptance,
    validate_section_inputs,
    walk,
)
from .contracts import DraftingInvocation, DraftingProfile, DraftingTrace


TRACE_CATEGORY = 'drafting_trace'


class ControlledDraftingService(CommandService):
    """Human-triggered drafting through a trusted ModelProvider, never direct AI writes."""

    def __init__(self, repository, authority, model_provider, profiles, clock=None):
        super().__init__(repository, authority, clock)
        self.model_provider = model_provider
        self.profiles = dict(profiles)

    @staticmethod
    def _parse_generate(raw):
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
        return wire.GenerateDocument.model_validate_json(json.dumps(value, allow_nan=False))

    def _profile(self, name):
        profile = self.profiles.get(name)
        if profile is None:
            raise Violation('GATE_DENIED')
        if isinstance(profile, DraftingProfile):
            return profile
        return DraftingProfile.model_validate_json(
            json.dumps(profile, allow_nan=False, sort_keys=True, separators=(',', ':'))
        )

    def _context(self, request, principal, tx):
        records = tx.records()
        heads = {(entity.kind, entity.id): entity for entity in tx.heads()}
        case = heads.get(('Case', principal.case_id))
        self._case_guard(request, principal, case)

        plan = resolve(request.plan, records, principal.tenant_id, principal.case_id)
        if plan.kind != 'DocumentPlan' or plan.status != 'APPROVED':
            raise Violation('GATE_DENIED')
        if heads.get(('DocumentPlan', plan.id)) != plan or plan.approval is None:
            raise Violation('STALE')
        plan_approval = self._live_decision(plan.approval, records, heads, principal)
        previous = m.Ref(kind='DocumentPlan', id=plan.id, revision=plan.revision - 1)
        if (
            plan_approval.decision_type != 'PLAN_APPROVAL'
            or plan_approval.outcome != 'ACCEPT'
            or plan_approval.decided_by.kind != 'HUMAN'
            or previous not in plan_approval.targets
        ):
            raise Violation('GATE_DENIED')

        snapshot = tx.object('snapshot', request.snapshot_id, wire.Snapshot)
        if digest(snapshot) != request.snapshot_hash:
            raise Violation('INVALID_HASH')
        if (plan.input_snapshot_id, plan.input_snapshot_hash) != (snapshot.id, digest(snapshot)):
            raise Violation('SNAPSHOT_MISMATCH')
        snapshot_decision = tx.object('acceptance', snapshot.id, m.Decision)
        live_snapshot_decision = self._live_decision(
            ref(snapshot_decision), records, heads, principal
        )
        validate_snapshot_acceptance(snapshot, live_snapshot_decision, records)
        self._snapshot_heads(snapshot, heads)
        for source in snapshot.sources:
            tx.source_bytes(source.id)

        filing = resolve(plan.filing, records, principal.tenant_id, principal.case_id)
        if filing.kind != 'Filing' or filing.document_type != request.document_type:
            raise Violation('GATE_DENIED')
        expected_objectives = tuple(target.id for target in plan.objectives)
        if (
            len(request.objective_ids) != len(set(request.objective_ids))
            or tuple(request.objective_ids) != expected_objectives
        ):
            raise Violation('GATE_DENIED')

        members = {member.ref for member in snapshot.members}
        sections = []
        for section_ref in plan.section_order:
            section = resolve(section_ref, records, principal.tenant_id, principal.case_id)
            if section.kind != 'Section' or section.status != 'READY':
                raise Violation('GATE_DENIED')
            if heads.get(('Section', section.id)) != section:
                raise Violation('STALE')
            declared = {
                *section.arguments,
                *section.contract.allowed_inputs,
                *section.contract.required_inputs,
                *section.contract.allowed_claims,
            }
            if not declared <= members:
                raise Violation('SNAPSHOT_NOT_CLOSED')
            sections.append(section)
        return records, heads, snapshot, plan, tuple(sections), plan_approval, live_snapshot_decision

    @staticmethod
    def _invocations(request, principal, snapshot, sections, profile):
        return tuple(
            DraftingInvocation(
                contract='urn:lukart:work:DraftingInvocation:1.0.0',
                section=ref(section),
                request=wire.AIRequest(
                request_id=uuid5(request.meta.command_id, f'drafting-request:{index}'),
                tenant_id=principal.tenant_id,
                case_id=principal.case_id,
                task='DRAFTING',
                snapshot_id=snapshot.id,
                snapshot_hash=digest(snapshot),
                input_refs=section.contract.allowed_inputs,
                section_contract=section.contract,
                prompt=profile.prompt,
                output_contract=profile.output_contract,
                data_policy=profile.data_policy,
                ),
            )
            for index, section in enumerate(sections)
        )

    @staticmethod
    def _validate_results(request, invocations, results, plan, sections, records):
        if len(results) != len(sections):
            raise Violation('GATE_DENIED')
        normalized_sections = []
        used_objectives = set()
        used_arguments = set()
        for section_index, (invocation, result, section) in enumerate(
            zip(invocations, results, sections)
        ):
            ai_request = invocation.request
            if invocation.section != ref(section):
                raise Violation('GATE_DENIED')
            validate_ai(result, ai_request)
            if result.disposition != 'PROPOSE' or result.proposals or result.section is None:
                raise Violation('GATE_DENIED')
            if result.section.section != ref(section):
                raise Violation('GATE_DENIED')
            validate_section_inputs(result.section, section.contract)

            statements = []
            for statement_index, statement in enumerate(result.section.statements):
                if statement.statement_type == 'STRUCTURAL':
                    # Structural prose is assembled outside the model from Section metadata.
                    raise Violation('GATE_DENIED')
                if statement.support == 'UNSUPPORTED':
                    raise Violation('UNSUPPORTED')
                if (statement.statement_type == 'INFERENCE') != (statement.support == 'INFERRED'):
                    raise Violation('GATE_DENIED')
                if statement.statement_type == 'FACTUAL' and not any(
                    target.kind in ('Fact', 'Evidence') for target in statement.refs
                ):
                    raise Violation('GATE_DENIED')
                if statement.statement_type == 'LEGAL':
                    rules = [target for target in statement.refs if target.kind == 'LegalRule']
                    if not rules or not statement.citations:
                        raise Violation('GATE_DENIED')
                    if any(resolve(target, records, plan.tenant_id, plan.case_id).status != 'ACTIVE'
                           for target in rules):
                        raise Violation('GATE_DENIED')
                    covered_rules = set()
                    for citation_ref in statement.citations:
                        citation = resolve(citation_ref, records, plan.tenant_id, plan.case_id)
                        if citation.kind != 'Citation' or citation.status != 'VERIFIED':
                            raise Violation('GATE_DENIED')
                        if citation.supported not in statement.refs and citation.supported != ref(section):
                            raise Violation('GATE_DENIED')
                        if citation.supported.kind == 'LegalRule':
                            covered_rules.add(citation.supported)
                    if not set(rules) <= covered_rules:
                        raise Violation('GATE_DENIED')
                if statement.statement_type == 'REQUEST':
                    requests = {target for target in statement.refs if target.kind == 'Request'}
                    if not requests:
                        raise Violation('GATE_DENIED')
                    used_objectives.update(requests)
                used_arguments.update(target for target in statement.refs if target.kind == 'Argument')

                body = statement.model_dump(mode='json')
                body['id'] = str(uuid5(
                    request.meta.command_id,
                    f'statement:{section_index}:{statement_index}',
                ))
                statements.append(m.Statement.model_validate_json(json.dumps(body)))
            requirements = set(section.contract.requirements)
            if 'REQUESTS' in requirements and not any(
                item.statement_type == 'REQUEST' for item in statements
            ):
                raise Violation('SECTION_CONTRACT')
            if 'CITATIONS' in requirements and not any(item.citations for item in statements):
                raise Violation('SECTION_CONTRACT')
            if 'ATTACHMENTS' in requirements and not any(
                target.kind == 'Evidence' for item in statements for target in item.refs
            ):
                raise Violation('SECTION_CONTRACT')
            if 'CHRONOLOGICAL' in requirements:
                dates = []
                for item in statements:
                    for target in item.refs:
                        if target.kind == 'Fact':
                            fact = resolve(target, records, plan.tenant_id, plan.case_id)
                            if fact.event_date is None:
                                raise Violation('SECTION_CONTRACT')
                            dates.append(fact.event_date)
                if not dates or dates != sorted(dates):
                    raise Violation('SECTION_CONTRACT')

            normalized_sections.append(m.SectionText(
                section=ref(section),
                statements=tuple(statements),
            ))

        if not set(plan.objectives) <= used_objectives:
            raise Violation('GATE_DENIED')
        if not set(plan.argument_order) <= used_arguments:
            raise Violation('GATE_DENIED')
        return tuple(normalized_sections)

    @staticmethod
    def _provenance_inputs(plan, sections, plan_approval, snapshot_approval):
        values = {
            ref(plan),
            ref(plan_approval),
            ref(snapshot_approval),
            *(ref(section) for section in sections),
            *(target for section in sections for target in (
                *section.arguments,
                *section.contract.allowed_inputs,
                *section.contract.required_inputs,
                *section.contract.allowed_claims,
            )),
        }
        return tuple(sorted(values, key=lambda target: (
            target.kind, str(target.id), target.revision
        )))

    @staticmethod
    def _metadata(request, principal, now, profile, inputs, old=None):
        draft_id = old.id if old is not None else uuid5(request.meta.command_id, 'draft')
        return dict(
            schema_version='1.0.0',
            id=str(draft_id),
            tenant_id=str(principal.tenant_id),
            case_id=str(principal.case_id),
            revision=old.revision + 1 if old is not None else 1,
            previous_hash=digest(old) if old is not None else None,
            created_at=(old.created_at if old is not None else now).isoformat(),
            recorded_at=now.isoformat(),
            provenance=dict(
                actor=principal.actor.model_dump(mode='json'),
                operation_id=str(request.meta.command_id),
                method='DERIVATION',
                inputs=[target.model_dump(mode='json') for target in inputs],
                anchors=[],
                rationale='Controlled drafting from an approved plan and accepted snapshot',
                tool=profile.generator.model_dump(mode='json'),
            ),
            kind='Draft',
        )

    def _dependencies(
        self, request, tx, draft, snapshot, plan, sections, plan_approval, snapshot_approval
    ):
        sources = {
            *(member.ref for member in snapshot.members),
            ref(plan),
            ref(plan_approval),
            ref(snapshot_approval),
            *(ref(section) for section in sections),
        }
        for source in sorted(sources, key=lambda target: (
            target.kind, str(target.id), target.revision
        )):
            edge = wire.DependencyEdge(
                source=source,
                target=ref(draft),
                input_hash=digest(tx.records()[source]) if source in tx.records() else digest(
                    {'kind': source.kind, 'id': str(source.id), 'revision': source.revision}
                ),
            )
            tx.put_object(
                'dependency',
                uuid5(request.meta.command_id, digest(edge)),
                edge,
            )

    def _commit(
        self, request, principal, input_hash, profile, invocations, results, raw_outputs
    ):
        with self.repository.transaction(principal.tenant_id, principal.case_id) as tx:
            replay = tx.replay(request.meta.idempotency_key, input_hash)
            if replay is not None:
                return replay
            sequence = tx.sequence()
            if sequence != request.meta.expected_case_sequence:
                raise Violation('CONFLICT')
            (
                records,
                heads,
                snapshot,
                plan,
                sections,
                plan_approval,
                snapshot_approval,
            ) = self._context(request, principal, tx)
            current_invocations = self._invocations(
                request, principal, snapshot, sections, profile
            )
            if current_invocations != invocations:
                raise Violation('STALE')
            normalized_sections = self._validate_results(
                request, invocations, results, plan, sections, records
            )

            trace_input_hash = digest([
                item.model_dump(mode='json') for item in invocations
            ])
            raw_output_hash = digest(raw_outputs)
            reproduction = m.ReproductionManifest(
                knowledge=snapshot.knowledge_pins,
                rule_set=snapshot.rule_set,
                prompts=(profile.prompt,),
                models=(profile.model,),
                provider=profile.provider,
                model_parameters_hash=profile.model_parameters_hash,
                generator=profile.generator,
                validators=profile.validators,
                render_profile=profile.render_profile,
                input_hash=trace_input_hash,
                raw_output_hash=raw_output_hash,
            )
            inputs = self._provenance_inputs(
                plan, sections, plan_approval, snapshot_approval
            )
            now = self.clock()
            if now.tzinfo is None:
                raise Violation('SCHEMA_INVALID')
            now = now.astimezone(timezone.utc)

            tx.set_sequence(sequence + 1)
            planned = m.Draft.model_validate_json(json.dumps(dict(
                **self._metadata(request, principal, now, profile, inputs),
                status='PLANNED',
                plan=ref(plan).model_dump(mode='json'),
                snapshot_id=str(snapshot.id),
                snapshot_hash=digest(snapshot),
                sections=[section.model_dump(mode='json') for section in normalized_sections],
                reproduction=reproduction.model_dump(mode='json'),
                supersedes=None,
            )))
            self._validate(planned, None, tx, records, heads, principal)
            tx.append(planned)
            records[ref(planned)] = planned
            heads[(planned.kind, planned.id)] = planned

            generated_body = planned.model_dump(mode='json')
            generated_body.update(self._metadata(
                request, principal, now, profile, inputs, planned
            ))
            generated_body['status'] = 'GENERATED'
            generated = m.Draft.model_validate_json(json.dumps(generated_body))
            self._validate(generated, planned, tx, records, heads, principal)
            tx.append(generated)
            records[ref(generated)] = generated
            heads[(generated.kind, generated.id)] = generated

            trace = DraftingTrace(
                contract='urn:lukart:work:DraftingTrace:1.0.0',
                id=uuid5(request.meta.command_id, 'drafting-trace'),
                tenant_id=principal.tenant_id,
                case_id=principal.case_id,
                command_id=request.meta.command_id,
                actor=principal.actor,
                recorded_at=now,
                profile=profile,
                invocations=invocations,
                results=results,
                raw_outputs=raw_outputs,
                input_hash=trace_input_hash,
                raw_output_hash=raw_output_hash,
            )
            tx.put_object(TRACE_CATEGORY, trace.id, trace)
            self._dependencies(
                request, tx, generated, snapshot, plan, sections,
                plan_approval, snapshot_approval
            )

            event_namespace = uuid5(
                request.meta.command_id,
                f'{principal.tenant_id}/{principal.case_id}',
            )
            event = wire.DomainEvent(
                event_type='DraftGenerated',
                subjects=(ref(generated),),
                audit=wire.AuditEvent(
                    event_id=uuid5(event_namespace, 'event'),
                    tenant_id=principal.tenant_id,
                    case_id=principal.case_id,
                    sequence=sequence + 1,
                    actor=principal.actor,
                    timestamp=now,
                    operation=request.operation,
                    command_id=request.meta.command_id,
                    correlation_id=request.meta.correlation_id,
                    input_hash=input_hash,
                    output_hash=digest(generated),
                    previous_event_hash=tx.last_event_hash(),
                    source_versions=tuple(sorted(
                        set(walk(generated, m.Ref)),
                        key=lambda target: (
                            target.kind, str(target.id), target.revision
                        ),
                    )),
                    model_provider=profile.provider,
                    rule_version=rule_pin(),
                ),
            )
            result = wire.CommandResult(
                command_id=request.meta.command_id,
                state='APPLIED',
                case_sequence=sequence + 1,
                refs=(ref(generated),),
                event_ids=(event.audit.event_id,),
                errors=(),
            )
            tx.finish(request, input_hash, result, (event,))
            principal.require(
                request.meta.tenant_id, request.meta.case_id, request.operation
            )
        return result

    def generate(self, raw, token):
        correlation = UUID(int=0)
        try:
            request = self._parse_generate(raw)
            correlation = request.meta.correlation_id
            profile = self._profile(request.profile)
            with self.authority.session(token) as principal:
                principal.require(
                    request.meta.tenant_id, request.meta.case_id, request.operation
                )
                if principal.actor.kind != 'HUMAN':
                    raise Violation('FORBIDDEN')
                input_hash = digest({
                    'request': request.model_dump(mode='json'),
                    'actor': principal.actor.model_dump(mode='json'),
                })
                with self.repository.transaction(
                    principal.tenant_id, principal.case_id
                ) as tx:
                    replay = tx.replay(request.meta.idempotency_key, input_hash)
                    if replay is not None:
                        return replay
                    if tx.sequence() != request.meta.expected_case_sequence:
                        raise Violation('CONFLICT')
                    (
                        _,
                        _,
                        snapshot,
                        _,
                        sections,
                        _,
                        _,
                    ) = self._context(request, principal, tx)
                    invocations = self._invocations(
                        request, principal, snapshot, sections, profile
                    )

                results = []
                raw_outputs = []
                for invocation in invocations:
                    raw_value = self.model_provider.propose(invocation)
                    raw_json = json.dumps(
                        raw_value, sort_keys=True, separators=(',', ':'),
                        ensure_ascii=False, allow_nan=False,
                    )
                    if len(raw_json.encode('utf-8')) > 2_000_000:
                        raise Violation('SCHEMA_INVALID')
                    result = wire.AIResult.model_validate_json(raw_json)
                    if result.disposition == 'ABSTAIN':
                        return result
                    results.append(result)
                    raw_outputs.append(raw_json)
                return self._commit(
                    request, principal, input_hash, profile,
                    invocations, tuple(results), tuple(raw_outputs),
                )
        except Violation as error:
            return safe_error(error.code, correlation)
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
            return safe_error('SCHEMA_INVALID', correlation)
        except Exception:
            # Provider/runtime details may contain case data; never return them.
            return safe_error('UNKNOWN', correlation)
