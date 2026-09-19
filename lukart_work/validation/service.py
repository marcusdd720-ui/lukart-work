"""Stage 10 authenticated, atomic pre-render validation over canonical PostgreSQL state."""
import json
from types import SimpleNamespace
from uuid import UUID, uuid5
from pydantic import ValidationError
from lukart_work.contracts import messages as w
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.procedural.service import ProceduralEngineService
from .contracts import (
    ValidationRequest, ValidationReview, ValidationReviewRevocation, ValidationExecution,
    ValidationQuery, ValidationProjection, PRE_RENDER_CHECKS, SEMANTIC_CHECKS,
)
from .policy import validation_pin
from .rules import Violation, digest, ref, resolve, walk, strict_json, validate_graph, validate_state

LAYERS = dict(zip(PRE_RENDER_CHECKS, ('V1','V2','V3','V4','V5','V6','V4','V7','V8','V7','V9')))
BLOCKING = {'ERROR', 'BLOCKER', 'CRITICAL'}


class ValidationEngineService(CommandService):
    def _parse_request(self, raw):
        return ValidationRequest.model_validate_json(json.dumps(strict_json(raw), allow_nan=False))

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if principal.actor.kind != 'HUMAN':
            raise Violation('FORBIDDEN')
        if request.validation_policy != validation_pin():
            raise Violation('GATE_DENIED')

    def _context(self, draft, principal, tx, now):
        """Reuse the exact closed Stage 09 current authority guards without invoking a model."""
        records = tx.records()
        plan = resolve(draft.plan, records, principal.tenant_id, principal.case_id)
        filing = resolve(plan.filing, records, principal.tenant_id, principal.case_id)
        request = SimpleNamespace(
            operation='ValidateDraft', plan=draft.plan, snapshot_id=draft.snapshot_id,
            snapshot_hash=draft.snapshot_hash, document_type=filing.document_type,
            objective_ids=tuple(r.id for r in plan.objectives),
        )
        drafting = ControlledDraftingService(self.repository, self.authority, None, {})
        # Stage 09's case guard takes no validation-specific envelope fields.
        return drafting, drafting._context(request, principal, tx, now.date())

    def _bound_draft(self, request, principal, tx, records, heads):
        draft = self._target(request, records, heads, 'Draft')
        if draft.status not in ('GENERATED', 'VALIDATED'):
            raise Violation('GATE_DENIED')
        if digest(draft) != request.draft_hash or draft.snapshot_hash != request.snapshot_hash:
            raise Violation('INVALID_HASH')
        return draft

    @staticmethod
    def _review(tx, review_id, draft, policy, evaluation_date):
        if review_id is None:
            return None
        review = tx.object('validation_review', review_id, ValidationReview)
        if (review.id != review_id or review.draft != ref(draft) or review.draft_hash != digest(draft)
                or review.snapshot_hash != draft.snapshot_hash or review.policy != policy
                or review.evaluation_date != evaluation_date or review.actor.kind != 'HUMAN'):
            raise Violation('STALE')
        if any(r.review_id == review_id for r in tx.objects('validation_review_revocation', ValidationReviewRevocation)):
            raise Violation('GATE_DENIED')
        return review

    def _procedure(self, tx, principal, records, heads, plan, now, add):
        """Execute Stage 07 predicates inside the same case transaction, no untrusted assessment import."""
        engine = ProceduralEngineService(self.repository, self.authority)
        case = heads[('Case', principal.case_id)]
        filing = records[plan.filing]
        proceeding = heads.get(('Proceeding', filing.proceeding.id)) if filing.proceeding else None
        recipient = heads.get(('Institution', filing.recipient.id)) if filing.recipient.kind == 'Institution' else None
        base = engine._base_context(case, filing, proceeding, recipient)
        rules = sorted((e for e in heads.values() if e.kind == 'LegalRule' and e.rule_type == 'PROCEDURAL' and e.status == 'ACTIVE'), key=lambda e: str(e.id))
        if not rules:
            add('procedure', 'PROCEDURAL_RULE_COVERAGE_UNKNOWN', '/rules', 'BLOCKER')
        for rule in rules:
            binding = engine._binding_for(tx, rule)
            if not engine._current_rule_approval(rule, records, heads, principal) or engine._current_sources(rule, records, heads, tx) is None:
                add('procedure', 'PROCEDURAL_AUTHORITY_UNAVAILABLE', '/rules/' + str(rule.id), 'BLOCKER')
                continue
            state = engine._applicability(rule, binding, SimpleNamespace(evaluation_date=now.date()), case, filing, base, {})
            if state == 'NOT_APPLICABLE':
                continue
            if state != 'APPLICABLE':
                add('procedure', 'PROCEDURAL_' + state, '/rules/' + str(rule.id), 'BLOCKER')
                continue
            if binding.spec.category == 'DEADLINE':
                finding = engine._deadline_finding(binding, rule, base, {})
                # A calculated date alone does not prove compliance with the deadline.
                add('procedure', 'DEADLINE_COMPLIANCE_UNRESOLVED', finding.path, 'BLOCKER')
                continue
            for condition in binding.spec.requirements:
                outcome, _, _ = engine._condition(condition, base, {})
                if outcome != 'TRUE':
                    add('procedure', 'PROCEDURAL_' + outcome, condition.path,
                        binding.spec.severity if outcome == 'FALSE' else 'BLOCKER')

    def _checks(self, draft, principal, tx, now, review, context):
        drafting, (records, heads, snapshot, plan, sections, _, acceptance) = context
        issues = []
        def add(check, code, path, severity='ERROR', message=None):
            issues.append((check, code, path, severity, message or code))
        def guard(check, code, path, fn):
            try:
                fn()
            except (Violation, ValidationError, ValueError, KeyError, TypeError):
                add(check, code, path, 'BLOCKER')

        sources = {s.id: s for s in tx.objects('source', w.SourceDocument)}
        guard('schema', 'SCHEMA_GRAPH_INVALID', '/', lambda: validate_graph(tuple(records.values()), sources))
        guard('document', 'DOCUMENT_CONTRACT_INVALID', '/sections', lambda: validate_state(draft, records, snapshot=snapshot, snapshot_approval=acceptance))
        statements = [s for section in draft.sections for s in section.statements]
        if len({s.id for s in statements}) != len(statements):
            add('document', 'DUPLICATE_STATEMENT_ID', '/sections', 'BLOCKER')
        used = {r for s in statements for r in s.refs}
        for target in sorted(used, key=lambda r: (r.kind, str(r.id), r.revision)):
            entity = records[target]
            if entity.kind == 'Fact':
                guard('facts', 'FACT_AUTHORITY_INVALID', '/facts/' + str(entity.id),
                      lambda: drafting._confirmed_fact(target, records, heads, principal))
            evidence_refs = entity.evidence if entity.kind in ('Fact', 'Request') else ((target,) if entity.kind == 'Evidence' else ())
            for evidence_ref in evidence_refs:
                evidence = records[evidence_ref]
                if (heads.get(('Evidence', evidence.id)) != evidence or evidence.status != 'ACCEPTED' or evidence.authenticity == 'DISPUTED'):
                    add('evidence', 'EVIDENCE_NOT_ACCEPTED_CURRENT', '/evidence/' + str(evidence.id), 'BLOCKER')
                guard('evidence', 'SOURCE_BYTES_UNAVAILABLE', '/evidence/' + str(evidence.id), lambda: tx.source_bytes(evidence.source.document_id))
        request = SimpleNamespace(meta=SimpleNamespace(command_id=UUID(int=0)))
        invocations = tuple(SimpleNamespace(section=ref(s), request=w.AIRequest(
            request_id=uuid5(draft.id, str(i)), tenant_id=draft.tenant_id, case_id=draft.case_id,
            task='DRAFTING', snapshot_id=draft.snapshot_id, snapshot_hash=draft.snapshot_hash,
            input_refs=s.contract.allowed_inputs, section_contract=s.contract,
            prompt=validation_pin(), output_contract=validation_pin(), data_policy=validation_pin(),
        )) for i, s in enumerate(sections))
        results = tuple(w.AIResult(request_id=inv.request.request_id, snapshot_hash=draft.snapshot_hash,
            disposition='PROPOSE', proposals=(), section=section, missing_information=(), reason=None)
            for inv, section in zip(invocations, draft.sections))
        guard('document', 'DRAFTING_INVARIANT_FAILED', '/sections', lambda: drafting._validate_results(
            request, principal, invocations, results, plan, sections, records, heads, now.date()))
        if not set(plan.objectives) <= {r for s in statements if s.statement_type == 'REQUEST' for r in s.refs}:
            add('requests', 'MISSING_REQUEST', '/objectives', 'BLOCKER')
        for i, statement in enumerate(statements):
            for citation_ref in statement.citations:
                guard('citations', 'CITATION_INVALID', '/statements/' + str(i), lambda: drafting._verified_citation(citation_ref, records, heads, principal))
            if statement.statement_type == 'LEGAL':
                for target in statement.refs:
                    if target.kind == 'LegalRule':
                        guard('legal_basis', 'LEGAL_RULE_INVALID', '/statements/' + str(i), lambda: drafting._legal_rule(target, records, heads, principal, heads[('Case', principal.case_id)], records[plan.filing], now.date()))
            if statement.support == 'UNSUPPORTED':
                add('facts', 'UNSUPPORTED_STATEMENT', '/statements/' + str(i), 'BLOCKER')
        # The same semantic statement cannot carry incompatible support/type declarations.
        by_text = {}
        for s in statements:
            key = ' '.join(s.text.casefold().split())
            signature = (s.statement_type, s.support, frozenset(s.refs), frozenset(s.citations))
            if key in by_text and by_text[key] != signature:
                add('contradictions', 'CONFLICTING_STATEMENT_BINDING', '/sections', 'BLOCKER')
            by_text[key] = signature
        self._procedure(tx, principal, records, heads, plan, now, add)
        outcomes = {check: 'PASS' for check in PRE_RENDER_CHECKS}
        if review is None:
            for check in SEMANTIC_CHECKS:
                outcomes[check] = 'NOT_RUN'
                add(check, 'SEMANTIC_REVIEW_NOT_RUN', '/review/' + check, 'BLOCKER')
        else:
            for assessment in review.assessments:
                outcomes[assessment.check] = assessment.outcome
                if assessment.outcome != 'PASS':
                    add(assessment.check, 'SEMANTIC_REVIEW_' + assessment.outcome, '/review/' + assessment.check, 'BLOCKER')
            for issue in review.issues:
                add(issue.check, issue.code, issue.path, issue.severity, issue.message)
        for check, _, _, severity, _ in issues:
            if severity in BLOCKING and outcomes[check] == 'PASS':
                outcomes[check] = 'FAIL'
        return outcomes, sorted(set(issues))

    def _apply(self, request, principal, tx, records, heads, now):
        if request.operation == 'ResolveValidationFinding':
            finding = self._target(request, records, heads, 'ValidationFinding')
            if finding.status != 'OPEN':
                raise Violation('GATE_DENIED')
            self._live_decision(request.decision, records, heads, principal)
            body = finding.model_dump(mode='json')
            body.update(self._metadata(request, principal, now, finding.kind, finding))
            body.update(status=request.resolution, resolution=request.decision.model_dump(mode='json'))
            revised = entity_from(body, m.ValidationFinding)
            self._validate(revised, finding, tx, records, heads, principal)
            tx.append(revised)
            return (ref(revised),), 'RevisionAppended', revised
        if request.operation == 'RevokeValidationReview':
            # Revocation must remain possible after snapshot or approval drift.
            draft = resolve(request.target, records, principal.tenant_id, principal.case_id)
            if digest(draft) != request.draft_hash or draft.snapshot_hash != request.snapshot_hash:
                raise Violation('INVALID_HASH')
            review = tx.object('validation_review', request.review_id, ValidationReview)
            if review.draft != ref(draft) or review.draft_hash != digest(draft):
                raise Violation('GATE_DENIED')
            revocation = ValidationReviewRevocation(review_id=review.id, actor=principal.actor, recorded_at=now, rationale=request.rationale)
            tx.put_object('validation_review_revocation', uuid5(request.meta.command_id, 'revocation'), revocation)
            return (ref(draft),), 'RevisionAppended', revocation
        draft = self._bound_draft(request, principal, tx, records, heads)
        context = self._context(draft, principal, tx, now)
        if request.operation == 'RecordValidationReview':
            review = ValidationReview(id=uuid5(request.meta.command_id, 'review'), tenant_id=draft.tenant_id,
                case_id=draft.case_id, draft=ref(draft), draft_hash=digest(draft), snapshot_hash=draft.snapshot_hash,
                policy=validation_pin(), evaluation_date=now.date(), actor=principal.actor, recorded_at=now,
                assessments=tuple(sorted(request.assessments, key=lambda a: a.check)),
                issues=tuple(sorted(request.issues, key=lambda i: (i.check, i.code, i.path, i.severity, i.message))), rationale=request.rationale)
            tx.put_object('validation_review', review.id, review)
            return (ref(draft),), 'RevisionAppended', review
        review = self._review(tx, request.review_id, draft, validation_pin(), now.date())
        outcomes, issues = self._checks(draft, principal, tx, now, review, context)
        run_id = uuid5(request.meta.command_id, 'validation-run')
        findings = []
        for check, code, path, severity, message in issues:
            body = self._metadata(request, principal, now, 'ValidationFinding')
            body.update(id=str(uuid5(run_id, digest((check, code, path, severity, message)))), status='OPEN',
                run_id=str(run_id), target=ref(draft).model_dump(mode='json'), target_hash=digest(draft),
                layer=LAYERS[check], code=code, severity=severity, message=message, path=path, resolution=None)
            finding = entity_from(body, m.ValidationFinding)
            self._validate(finding, None, tx, records, heads, principal)
            tx.append(finding)
            records[ref(finding)] = finding
            findings.append(finding)
        output = draft
        if all(value == 'PASS' for value in outcomes.values()) and draft.status == 'GENERATED':
            body = draft.model_dump(mode='json')
            body.update(self._metadata(request, principal, now, 'Draft', draft))
            body['status'] = 'VALIDATED'
            output = entity_from(body, m.Draft)
            self._validate(output, draft, tx, records, heads, principal)
            tx.append(output)
        # Pin every selected snapshot/plan/authority input and all current procedural inputs.
        _, (_, context_heads, snapshot, plan, sections, plan_approval, acceptance) = context
        dependencies = {ref(draft), ref(plan), ref(plan_approval), ref(acceptance), *(ref(s) for s in sections), *snapshot.heads}
        dependencies.update(ref(e) for e in context_heads.values() if e.kind in ('LegalRule', 'LegalSource', 'Decision'))
        ordered = tuple(sorted(dependencies, key=lambda r: (r.kind, str(r.id), r.revision)))
        manifest = {'policy': validation_pin().model_dump(mode='json'), 'draft_hash': digest(draft),
                    'dependencies': [(r.model_dump(mode='json'), digest(records[r])) for r in ordered],
                    'review_hash': digest(review) if review else None, 'evaluation_date': now.date().isoformat()}
        run = w.ValidationRun(id=run_id, tenant_id=draft.tenant_id, case_id=draft.case_id,
            draft=ref(draft), draft_hash=digest(draft), snapshot_hash=draft.snapshot_hash,
            policy=validation_pin(), completed_at=now,
            checks=tuple(w.CheckResult(check=check, outcome=outcomes[check], validator=validation_pin()) for check in PRE_RENDER_CHECKS)
                + (w.CheckResult(check='render', outcome='NOT_RUN', validator=validation_pin()),),
            findings=tuple(ref(f) for f in findings), render_hashes=(), execution_manifest_hash=digest(manifest))
        execution = ValidationExecution(id=run_id, run=run, output_draft=ref(output), output_hash=digest(output),
            evaluation_date=now.date(), input_sequence=request.meta.expected_case_sequence,
            committed_sequence=request.meta.expected_case_sequence + 1, review=review,
            dependencies=ordered, validator=validation_pin())
        tx.put_object('validation_run', run_id, run)
        tx.put_object('validation_execution', run_id, execution)
        # Persist the exact manifest as a typed execution-derived object via the run's binding.
        for target in ordered:
            if target == ref(output):
                continue
            edge = w.DependencyEdge(source=target, target=ref(output), input_hash=digest(records[target]))
            tx.put_object('dependency', uuid5(run_id, digest(edge)), edge)
        return (ref(output), *(ref(f) for f in findings)), 'ValidationCompleted', execution

    def query(self, raw, token):
        try:
            query = ValidationQuery.model_validate_json(json.dumps(strict_json(raw)))
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id, query.case_id, query.operation)
                with self.repository.transaction(query.tenant_id, query.case_id) as tx:
                    execution = tx.object('validation_execution', query.run_id, ValidationExecution)
                    run = tx.object('validation_run', query.run_id, w.ValidationRun)
                    if execution.id != query.run_id or run != execution.run:
                        raise Violation('INVALID_HASH')
                    records = tx.records()
                    heads = {(e.kind, e.id): e for e in tx.heads()}
                    output = records[execution.output_draft]
                    reasons = []
                    if execution.validator != validation_pin() or digest(output) != execution.output_hash:
                        reasons.append('POLICY_OR_OUTPUT_DRIFT')
                    if heads.get(('Draft', output.id)) != output:
                        reasons.append('DRAFT_SUPERSEDED')
                    if self.clock().date() != execution.evaluation_date:
                        reasons.append('EVALUATION_DATE_STALE')
                    for target in execution.dependencies:
                        if target == run.draft and target.id == output.id:
                            continue
                        if heads.get((target.kind, target.id)) != records[target]:
                            reasons.append('DEPENDENCY_STALE')
                    try:
                        self._context(output, principal, tx, self.clock())
                        if execution.review:
                            self._review(tx, execution.review.id, records[run.draft], validation_pin(), execution.evaluation_date)
                    except (Violation, ValueError, KeyError):
                        reasons.append('AUTHORITY_OR_SOURCE_STALE')
                    # Any subsequent case mutation is conservative invalidation, including new rules/reviews.
                    if tx.sequence() != execution.committed_sequence:
                        reasons.append('CASE_SEQUENCE_STALE')
                    fresh = not reasons
                    if any(c.outcome != 'PASS' for c in run.checks if c.check != 'render'):
                        reasons.append('CHECKS_INCOMPLETE')
                    if any(records[r].severity in BLOCKING for r in run.findings):
                        reasons.append('BLOCKING_FINDING')
                    if output.status != 'VALIDATED':
                        reasons.append('NOT_VALIDATED')
                    principal.require(query.tenant_id, query.case_id, query.operation)
                    return ValidationProjection(execution=execution, freshness='CURRENT' if fresh else 'STALE',
                        eligible_for_approval=not reasons, reasons=tuple(sorted(set(reasons))))
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, KeyError, TypeError, RecursionError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
