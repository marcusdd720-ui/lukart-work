"""Deterministic Stage 07 procedural assessment over authoritative Case Core state."""
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from lukart_work.contracts import messages as wire
from lukart_work.core.postgres import canonical
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.validation.rules import Violation, digest, ref, resolve, strict_json
from .contracts import (
    ProceduralAssessment, ProceduralFinding, ProceduralQuery, ProceduralRequest,
    ProceduralRuleBinding,
)

CATEGORY = 'procedural_rule_binding'
IMPLEMENTATION = m.VersionPin(
    id='urn:lukart:work:ProceduralEngineService',
    version='1.0.0',
    content_hash=sha256(b'lukart-work:procedural-engine:1.0.0').hexdigest(),
)
RULE_STATUS = {
    'ReviewProceduralRule': 'REVIEWED',
    'ActivateProceduralRule': 'ACTIVE',
    'SupersedeProceduralRule': 'SUPERSEDED',
    'WithdrawProceduralRule': 'WITHDRAWN',
}


class ProceduralEngineService(CommandService):
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
        return ProceduralRequest.model_validate_json(json.dumps(value, allow_nan=False))

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if principal.actor.kind != 'HUMAN':
            raise Violation('FORBIDDEN')

    @staticmethod
    def _source(tx, source_id):
        source = tx.object('source', source_id, wire.SourceDocument)
        data = tx.source_bytes(source_id)
        if len(data) != source.byte_length or sha256(data).hexdigest() != source.content_hash:
            raise Violation('INVALID_HASH')
        return source

    @staticmethod
    def _save(entity, old, request, principal, tx, records, heads, service):
        service._validate(entity, old, tx, records, heads, principal)
        tx.append(entity)
        records[ref(entity)] = entity
        heads[(entity.kind, entity.id)] = entity
        return entity

    @classmethod
    def _bindings(cls, tx):
        records = tx.records()
        values = sorted(tx.objects(CATEGORY, ProceduralRuleBinding), key=lambda b: (str(b.rule.id), b.revision))
        previous = {}
        for binding in values:
            old = previous.get(binding.rule.id)
            if binding.revision != (old.revision + 1 if old else 1):
                raise Violation('INVALID_HASH')
            if binding.previous_hash != (digest(old) if old else None):
                raise Violation('INVALID_HASH')
            rule = records.get(binding.rule)
            if rule is None or rule.kind != 'LegalRule' or tuple(rule.sources) != tuple(binding.sources):
                raise Violation('INVALID_HASH')
            if (rule.requirement is None or rule.requirement.operator != 'EQUALS'
                    or rule.requirement.field_path != '/procedural_spec'
                    or rule.requirement.operand != canonical(binding.spec)
                    or rule.requirement.severity != binding.spec.severity):
                raise Violation('INVALID_HASH')
            if old and (old.spec != binding.spec or old.sources != binding.sources):
                raise Violation('INVALID_HASH')
            previous[binding.rule.id] = binding
        return tuple(values)

    @classmethod
    def _binding_for(cls, tx, rule):
        matches = [b for b in cls._bindings(tx) if b.rule == ref(rule)]
        if len(matches) != 1:
            raise Violation('PROVENANCE_MISSING')
        return matches[0]

    @classmethod
    def _append_binding(cls, request, principal, tx, rule, spec, now):
        history = [b for b in cls._bindings(tx) if b.rule.id == rule.id]
        previous = history[-1] if history else None
        binding = ProceduralRuleBinding(
            id=uuid5(rule.id, f'procedural-binding:{rule.revision}'),
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            rule=ref(rule),
            revision=rule.revision,
            previous_hash=digest(previous) if previous else None,
            sources=rule.sources,
            spec=spec,
            actor=principal.actor,
            recorded_at=now,
            implementation=IMPLEMENTATION,
        )
        tx.put_object(CATEGORY, binding.id, binding)
        return binding

    @staticmethod
    def _current_sources(rule, records, heads, tx):
        result = []
        for source_ref in rule.sources:
            source = resolve(source_ref, records, rule.tenant_id, rule.case_id)
            current = heads.get(('LegalSource', source.id))
            if current is None or ref(current) != source_ref or current.status != 'VERIFIED':
                return None
            tx.source_bytes(source.anchor.document_id)
            result.append(source)
        return tuple(result)

    def _register_source(self, request, principal, tx, records, heads, now):
        data = request.data
        source = self._source(tx, data.source_id)
        anchor = m.SourceAnchor(
            document_id=source.id,
            document_hash=source.content_hash,
            locator=m.Locator(
                unit='RECORD',
                value=canonical({'purpose': 'PROCEDURAL_LEGAL_SOURCE', 'source_id': str(source.id)}),
                fragment_hash=source.content_hash,
            ),
        )
        intent = request.model_copy(update={'anchors': (anchor,)})
        entity = entity_from(dict(
            **self._metadata(intent, principal, now, 'LegalSource'),
            status='REGISTERED',
            registry_pin={
                'id': data.registry_id,
                'version': data.registry_version,
                'content_hash': source.content_hash,
            },
            jurisdiction=data.jurisdiction,
            source_type=data.source_type,
            title=data.title,
            identifier=data.identifier,
            effective_period=data.effective_period.model_dump(mode='json'),
            retrieved_at=source.received_at.isoformat(),
            source_uri=data.source_uri,
            content_hash=source.content_hash,
            authority_level=data.authority_level,
            anchor=anchor.model_dump(mode='json'),
        ), m.LegalSource)
        self._save(entity, None, intent, principal, tx, records, heads, self)
        return (ref(entity),), 'RevisionAppended', entity

    def _verify_source(self, request, principal, tx, records, heads, now):
        old = self._target(request, records, heads, 'LegalSource')
        tx.source_bytes(old.anchor.document_id)
        body = old.model_dump(mode='json')
        body.update(self._metadata(request, principal, now, old.kind, old))
        body['status'] = 'VERIFIED'
        entity = entity_from(body, m.LegalSource)
        self._save(entity, old, request, principal, tx, records, heads, self)
        return (ref(entity),), 'RevisionAppended', entity

    def _register_rule(self, request, principal, tx, records, heads, now):
        data = request.data
        for source_ref in data.sources:
            source = resolve(source_ref, records, principal.tenant_id, principal.case_id)
            current = heads.get(('LegalSource', source.id))
            if current is None or ref(current) != source_ref or source.status != 'VERIFIED':
                raise Violation('GATE_DENIED')
            tx.source_bytes(source.anchor.document_id)
        if data.spec.deadline is not None:
            try:
                ZoneInfo(data.spec.deadline.timezone)
            except ZoneInfoNotFoundError:
                raise Violation('SCHEMA_INVALID')
        intent = request.model_copy(update={'inputs': tuple(data.sources)})
        spec_payload = canonical(data.spec)
        entity = entity_from(dict(
            **self._metadata(intent, principal, now, 'LegalRule'),
            status='PROPOSED',
            rule_type='PROCEDURAL',
            statement=data.statement,
            sources=[r.model_dump(mode='json') for r in data.sources],
            jurisdiction=data.jurisdiction,
            effective_period=data.effective_period.model_dump(mode='json'),
            applicable_document_types=[p.model_dump(mode='json') for p in data.applicable_document_types],
            requirement={
                'operator': 'EQUALS',
                'field_path': '/procedural_spec',
                'operand': spec_payload,
                'severity': data.spec.severity,
            },
            interpretation=data.interpretation,
            review_decision=None,
        ), m.LegalRule)
        self._save(entity, None, intent, principal, tx, records, heads, self)
        binding = self._append_binding(request, principal, tx, entity, data.spec, now)
        return (ref(entity),), 'RevisionAppended', binding

    def _transition_rule(self, request, principal, tx, records, heads, now):
        old = self._target(request, records, heads, 'LegalRule')
        if old.rule_type != 'PROCEDURAL':
            raise Violation('GATE_DENIED')
        previous_binding = self._binding_for(tx, old)
        body = old.model_dump(mode='json')
        body.update(self._metadata(request, principal, now, old.kind, old))
        body['status'] = RULE_STATUS[request.operation]
        if request.operation in ('ReviewProceduralRule', 'ActivateProceduralRule'):
            if self._current_sources(old, records, heads, tx) is None:
                raise Violation('GATE_DENIED')
        if request.operation == 'ActivateProceduralRule':
            decision = self._live_decision(request.data.decision, records, heads, principal)
            if (decision.decision_type != 'INTERPRETATION' or decision.outcome != 'ACCEPT'
                    or decision.decided_by.kind != 'HUMAN' or ref(old) not in decision.targets):
                raise Violation('HUMAN_APPROVAL_REQUIRED')
            body['review_decision'] = request.data.decision.model_dump(mode='json')
        entity = entity_from(body, m.LegalRule)
        self._save(entity, old, request, principal, tx, records, heads, self)
        binding = self._append_binding(request, principal, tx, entity, previous_binding.spec, now)
        return (ref(entity),), 'RevisionAppended', binding

    def _apply(self, request, principal, tx, records, heads, now):
        if request.operation == 'RegisterProceduralSource':
            return self._register_source(request, principal, tx, records, heads, now)
        if request.operation == 'VerifyProceduralSource':
            return self._verify_source(request, principal, tx, records, heads, now)
        if request.operation == 'RegisterProceduralRule':
            return self._register_rule(request, principal, tx, records, heads, now)
        return self._transition_rule(request, principal, tx, records, heads, now)

    def _confirmed_datum(self, datum, principal, tx, records, heads):
        expected = canonical({'key': datum.key, 'value': datum.value})
        used = []
        for target in datum.facts:
            current = heads.get(('Fact', target.id))
            if current is None:
                raise Violation('BROKEN_REFERENCE')
            if ref(current) != target:
                raise Violation('STALE')
            if current.status != 'CONFIRMED' or current.support != 'SOURCE_BACKED' or current.statement != expected:
                raise Violation('GATE_DENIED')
            if current.acceptance is None:
                raise Violation('GATE_DENIED')
            decision = self._live_decision(current.acceptance, records, heads, principal)
            if (decision.decision_type != 'FACT_ACCEPTANCE' or decision.outcome != 'ACCEPT'
                    or m.Ref(kind='Fact', id=current.id, revision=current.revision - 1) not in decision.targets):
                raise Violation('GATE_DENIED')
            for evidence_ref in current.evidence:
                evidence = heads.get(('Evidence', evidence_ref.id))
                if evidence is None or ref(evidence) != evidence_ref:
                    raise Violation('STALE')
                if evidence.status != 'ACCEPTED' or evidence.authenticity == 'DISPUTED':
                    raise Violation('GATE_DENIED')
                tx.source_bytes(evidence.source.document_id)
            used.append(target)
        return tuple(used)

    def _current_rule_approval(self, rule, records, heads, principal):
        if rule.review_decision is None or rule.revision < 2:
            return False
        try:
            decision = self._live_decision(rule.review_decision, records, heads, principal)
        except Violation:
            return False
        previous = m.Ref(kind='LegalRule', id=rule.id, revision=rule.revision - 1)
        return (
            decision.decision_type == 'INTERPRETATION'
            and decision.outcome == 'ACCEPT'
            and decision.decided_by.kind == 'HUMAN'
            and previous in decision.targets
        )

    @staticmethod
    def _base_context(case, filing, proceeding, recipient):
        return {
            'case': {
                'id': str(case.id),
                'jurisdiction': case.jurisdiction,
                'status': case.status,
            },
            'filing': {
                'id': str(filing.id),
                'direction': filing.direction,
                'status': filing.status,
                'recipient_id': str(filing.recipient.id),
                'author_ids': [str(x.id) for x in filing.authors],
                'document_type_id': filing.document_type.id,
            },
            'proceeding': None if proceeding is None else {
                'id': str(proceeding.id),
                'proceeding_type': proceeding.proceeding_type,
                'institution_id': str(proceeding.institution.id),
                'participant_ids': [str(p.party.id) for p in proceeding.participants],
                'representative_ids': [str(p.represented_by.id) for p in proceeding.participants if p.represented_by],
                'status': proceeding.status,
            },
            'recipient': None if recipient is None else {
                'id': str(recipient.id),
                'institution_type': recipient.institution_type,
                'jurisdiction': recipient.jurisdiction,
                'status': recipient.status,
            },
        }

    @staticmethod
    def _nested(value, parts):
        current = value
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False, None
        return True, current

    def _path_value(self, path, base, datums):
        parts = [p for p in path.split('/') if p]
        if not parts:
            return 'UNKNOWN', None, ()
        if parts[0] == 'context':
            if len(parts) < 2:
                return 'UNKNOWN', None, ()
            datum = datums.get(parts[1])
            if datum is None:
                return 'UNKNOWN', None, ()
            if datum.classification == 'UNKNOWN':
                return 'UNKNOWN', None, ()
            if datum.classification == 'UNRESOLVED':
                return 'UNRESOLVED', datum.value, ()
            if datum.classification != 'FACT':
                return 'ABSTAIN', datum.value, ()
            value = datum.value
            if len(parts) > 2:
                found, value = self._nested(value, parts[2:])
                if not found:
                    return 'UNKNOWN', None, datum.facts
            return 'FACT', value, datum.facts
        found, value = self._nested(base, parts)
        return ('FACT', value, ()) if found else ('UNKNOWN', None, ())

    def _condition(self, condition, base, datums):
        state, actual, facts = self._path_value(condition.path, base, datums)
        if state != 'FACT':
            return state, actual, facts
        op = condition.operator
        expected = condition.operand
        if op == 'PRESENT':
            passed = actual is not None
        elif op == 'EQUALS':
            passed = actual == expected
        elif op == 'ONE_OF':
            passed = actual in expected
        elif op == 'MIN_INTEGER':
            passed = type(actual) is int and actual >= expected
        elif op == 'MIN_ITEMS':
            passed = isinstance(actual, (list, tuple, dict)) and len(actual) >= expected
        elif op == 'CONTAINS_ALL':
            passed = isinstance(actual, (list, tuple)) and all(item in actual for item in expected)
        else:
            raise Violation('SCHEMA_INVALID')
        return 'TRUE' if passed else 'FALSE', actual, facts

    def _applicability(self, rule, binding, query, case, filing, base, datums):
        if query.evaluation_date < rule.effective_period.start:
            return 'NOT_APPLICABLE'
        if rule.effective_period.end is not None and query.evaluation_date > rule.effective_period.end:
            return 'NOT_APPLICABLE'
        if rule.jurisdiction != case.jurisdiction:
            return 'NOT_APPLICABLE'
        if rule.applicable_document_types and filing.document_type not in rule.applicable_document_types:
            return 'NOT_APPLICABLE'
        if rule.interpretation == 'DISPUTED':
            return 'UNRESOLVED'
        if rule.interpretation == 'UNKNOWN':
            return 'UNKNOWN'
        states = []
        for condition in binding.spec.applies_when:
            state, _, _ = self._condition(condition, base, datums)
            if state == 'FALSE':
                return 'NOT_APPLICABLE'
            if state != 'TRUE':
                states.append(state)
        if 'UNRESOLVED' in states:
            return 'UNRESOLVED'
        if 'ABSTAIN' in states:
            return 'ABSTAIN'
        if 'UNKNOWN' in states:
            return 'UNKNOWN'
        return 'APPLICABLE'

    @staticmethod
    def _finding(binding, rule, *, code, applicability, outcome, severity, path, message,
                 actual=None, expected=None, facts=(), due_at=None):
        return ProceduralFinding(
            code=code,
            category=binding.spec.category,
            applicability=applicability,
            outcome=outcome,
            severity=severity,
            rule=ref(rule),
            sources=rule.sources,
            binding_hash=digest(binding),
            path=path,
            message=message,
            actual=actual,
            expected=expected,
            facts=tuple(facts),
            due_at=due_at,
        )

    def _deadline_finding(self, binding, rule, base, datums):
        spec = binding.spec.deadline
        state, actual, facts = self._path_value('/context/' + spec.trigger_key, base, datums)
        if state != 'FACT':
            outcome = state
            return self._finding(
                binding, rule, code=binding.spec.code, applicability='APPLICABLE',
                outcome=outcome, severity=binding.spec.severity,
                path='/context/' + spec.trigger_key,
                message='DEADLINE_TRIGGER_NOT_ESTABLISHED',
                actual=actual, facts=facts,
            )
        if spec.calendar_mode == 'BUSINESS_DAYS':
            return self._finding(
                binding, rule, code=binding.spec.code, applicability='APPLICABLE',
                outcome='ABSTAIN', severity=binding.spec.severity,
                path='/context/' + spec.trigger_key,
                message='BUSINESS_CALENDAR_NOT_SUPPORTED_IN_STAGE07',
                actual=actual, facts=facts,
            )
        try:
            trigger = date.fromisoformat(actual)
            tz = ZoneInfo(spec.timezone)
            due_clock = time.fromisoformat(spec.due_time)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return self._finding(
                binding, rule, code=binding.spec.code, applicability='APPLICABLE',
                outcome='ABSTAIN', severity=binding.spec.severity,
                path='/context/' + spec.trigger_key,
                message='DEADLINE_TRIGGER_FORMAT_UNSUPPORTED',
                actual=actual, facts=facts,
            )
        due_at = datetime.combine(trigger + timedelta(days=spec.offset_days), due_clock, tzinfo=tz)
        return self._finding(
            binding, rule, code=binding.spec.code, applicability='APPLICABLE',
            outcome='CALCULATED', severity='INFO',
            path='/context/' + spec.trigger_key,
            message='DEADLINE_CALCULATED_FROM_VERIFIED_TRIGGER',
            actual=actual,
            expected={'offset_days': spec.offset_days, 'timezone': spec.timezone,
                      'due_time': spec.due_time, 'calendar_mode': spec.calendar_mode},
            facts=facts, due_at=due_at,
        )

    def assess(self, raw, token):
        try:
            query = ProceduralQuery.model_validate_json(json.dumps(strict_json(raw), allow_nan=False))
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id, query.case_id, query.operation)
                if principal.actor.kind == 'AI':
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(query.tenant_id, query.case_id) as tx:
                    sequence = tx.sequence()
                    if not sequence:
                        raise Violation('BROKEN_REFERENCE')
                    records = tx.records()
                    heads = {(e.kind, e.id): e for e in tx.heads()}
                    filing = resolve(query.filing, records, query.tenant_id, query.case_id)
                    if heads.get(('Filing', filing.id)) != filing:
                        raise Violation('STALE')
                    case = heads.get(('Case', query.case_id))
                    if case is None:
                        raise Violation('BROKEN_REFERENCE')
                    proceeding = heads.get(('Proceeding', filing.proceeding.id)) if filing.proceeding else None
                    recipient = heads.get(('Institution', filing.recipient.id)) if filing.recipient.kind == 'Institution' else None
                    datums = {d.key: d for d in query.context}
                    for datum in query.context:
                        if datum.classification == 'FACT':
                            self._confirmed_datum(datum, principal, tx, records, heads)
                    base = self._base_context(case, filing, proceeding, recipient)
                    bindings = self._bindings(tx)
                    by_rule = {b.rule: b for b in bindings}
                    rules = sorted(
                        (e for e in heads.values() if e.kind == 'LegalRule' and e.rule_type == 'PROCEDURAL' and e.status == 'ACTIVE'),
                        key=lambda e: str(e.id),
                    )
                    findings = []
                    for rule in rules:
                        binding = by_rule.get(ref(rule))
                        if binding is None:
                            raise Violation('PROVENANCE_MISSING')
                        if not self._current_rule_approval(rule, records, heads, principal):
                            findings.append(self._finding(
                                binding, rule, code=binding.spec.code,
                                applicability='ABSTAIN', outcome='ABSTAIN',
                                severity=binding.spec.severity, path='/review_decision',
                                message='PROCEDURAL_RULE_APPROVAL_NOT_CURRENT',
                            ))
                            continue
                        sources = self._current_sources(rule, records, heads, tx)
                        if sources is None:
                            findings.append(self._finding(
                                binding, rule, code=binding.spec.code,
                                applicability='ABSTAIN', outcome='ABSTAIN',
                                severity=binding.spec.severity, path='/sources',
                                message='PROCEDURAL_SOURCE_NOT_CURRENT',
                            ))
                            continue
                        applicability = self._applicability(rule, binding, query, case, filing, base, datums)
                        if applicability != 'APPLICABLE':
                            findings.append(self._finding(
                                binding, rule, code=binding.spec.code,
                                applicability=applicability,
                                outcome='NOT_APPLICABLE' if applicability == 'NOT_APPLICABLE' else applicability,
                                severity='INFO' if applicability == 'NOT_APPLICABLE' else binding.spec.severity,
                                path='/applicability',
                                message='PROCEDURAL_RULE_' + applicability,
                            ))
                            continue
                        if binding.spec.category == 'DEADLINE':
                            findings.append(self._deadline_finding(binding, rule, base, datums))
                            continue
                        for index, condition in enumerate(binding.spec.requirements, 1):
                            state, actual, facts = self._condition(condition, base, datums)
                            if state == 'TRUE':
                                outcome, severity, message = 'SATISFIED', 'INFO', 'PROCEDURAL_REQUIREMENT_SATISFIED'
                            elif state == 'FALSE':
                                outcome, severity, message = 'VIOLATION', binding.spec.severity, 'PROCEDURAL_REQUIREMENT_VIOLATION'
                            else:
                                outcome, severity, message = state, binding.spec.severity, 'PROCEDURAL_REQUIREMENT_' + state
                            findings.append(self._finding(
                                binding, rule, code=f'{binding.spec.code}:{index}',
                                applicability='APPLICABLE', outcome=outcome, severity=severity,
                                path=condition.path, message=message,
                                actual=actual, expected=condition.operand, facts=facts,
                            ))
                    result = ProceduralAssessment(
                        tenant_id=query.tenant_id,
                        case_id=query.case_id,
                        case_sequence=sequence,
                        filing=ref(filing),
                        evaluation_date=query.evaluation_date,
                        findings=tuple(sorted(findings, key=lambda f: (f.category, str(f.rule.id), f.code))),
                        rules_considered=tuple(ref(r) for r in rules),
                    )
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
