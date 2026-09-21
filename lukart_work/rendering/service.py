"""Stage 11 authenticated rendering application boundary over validated CASE state."""
from __future__ import annotations

import json
from uuid import UUID, uuid5

from pydantic import ValidationError

from lukart_work.contracts import messages as w
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.storage.objects import ObjectStore, RetentionPolicies, artifact_id
from lukart_work.validation.contracts import (
    PRE_RENDER_CHECKS, ValidationExecution, ValidationReviewRevocation,
)
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.rules import Violation, digest, ref, resolve, strict_json
from lukart_work.validation.service import BLOCKING, ValidationEngineService

from .contracts import (
    RenderArtifact, RenderAuthorization, RenderExecution, RenderManifest,
    RenderingProjection, RenderingQuery, RenderingRequest,
)
from .profiles import official_pl_profile, profile_pin, renderer_pin
from .renderer import render


AUTH_CATEGORY = 'render_authorization'
EXECUTION_CATEGORY = 'render_execution'


class RenderingEngineService(CommandService):
    """Render exact validated content without inventing facts, law, strategy or approval."""

    def _parse_request(self, raw):
        return RenderingRequest.model_validate_json(
            json.dumps(strict_json(raw), allow_nan=False)
        )

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if request.profile != profile_pin():
            raise Violation('GATE_DENIED')
        if request.operation == 'RecordRenderAuthorization':
            if principal.actor.kind != 'HUMAN':
                raise Violation('FORBIDDEN')
        elif request.operation == 'RenderDocument':
            if principal.actor.kind not in ('HUMAN', 'SERVICE'):
                raise Violation('FORBIDDEN')

    def _current_draft(self, request, principal, records, heads, status):
        draft = self._target(request, records, heads, 'Draft')
        if draft.status != status:
            raise Violation('GATE_DENIED')
        if draft.reproduction.render_profile != request.profile:
            raise Violation('GATE_DENIED')
        return draft

    def _validation_gate(self, request, draft, principal, tx, records, heads, now):
        if request.validation_run_id is None or request.validation_run_hash is None:
            raise Violation('SCHEMA_INVALID')
        execution = tx.object(
            'validation_execution', request.validation_run_id, ValidationExecution
        )
        run = tx.object('validation_run', request.validation_run_id, w.ValidationRun)
        if (
            execution.id != request.validation_run_id
            or execution.run != run
            or digest(run) != request.validation_run_hash
            or execution.output_draft != ref(draft)
            or execution.output_hash != digest(draft)
            or run.policy != validation_pin()
            or request.meta.expected_case_sequence != execution.committed_sequence
            or execution.evaluation_date != now.date()
        ):
            raise Violation('STALE')
        checks = {check.check: check for check in run.checks}
        if (
            set(checks) != set(w.REQUIRED_CHECKS)
            or checks['render'].outcome != 'NOT_RUN'
            or any(checks[name].outcome != 'PASS' for name in PRE_RENDER_CHECKS)
        ):
            raise Violation('GATE_DENIED')
        if len(run.findings) != len(set(run.findings)):
            raise Violation('INVALID_HASH')
        for finding_ref in run.findings:
            finding = resolve(
                finding_ref, records, principal.tenant_id, principal.case_id
            )
            if (
                finding.kind != 'ValidationFinding'
                or finding.run_id != run.id
                or finding.severity in BLOCKING
            ):
                raise Violation('GATE_DENIED')
        if execution.review is None:
            raise Violation('GATE_DENIED')
        if any(
            item.review_id == execution.review.id
            for item in tx.objects(
                'validation_review_revocation', ValidationReviewRevocation
            )
        ):
            raise Violation('GATE_DENIED')
        if (
            digest(execution.manifest) != run.execution_manifest_hash
            or execution.manifest.draft_hash != run.draft_hash
            or execution.manifest.snapshot_hash != run.snapshot_hash
            or execution.manifest.review_hash != digest(execution.review)
        ):
            raise Violation('INVALID_HASH')
        for target, content_hash in execution.manifest.dependency_hashes:
            if target not in records or digest(records[target]) != content_hash:
                raise Violation('STALE')

        engine = ValidationEngineService(
            self.repository, self.authority, clock=lambda: now
        )
        context = engine._context(draft, principal, tx, now)
        outcomes, issues = engine._checks(
            draft,
            principal,
            tx,
            now,
            execution.review,
            context,
            execution.manifest.procedural_context,
        )
        if any(outcome != 'PASS' for outcome in outcomes.values()):
            raise Violation('GATE_DENIED')
        if any(issue[3] in BLOCKING for issue in issues):
            raise Violation('GATE_DENIED')
        return execution, run

    def _semantic_document(self, draft, principal, records):
        plan = resolve(
            draft.plan, records, principal.tenant_id, principal.case_id
        )
        filing = resolve(
            plan.filing, records, principal.tenant_id, principal.case_id
        )
        recipient = resolve(
            filing.recipient, records, principal.tenant_id, principal.case_id
        )
        authors = tuple(
            resolve(author, records, principal.tenant_id, principal.case_id)
            for author in filing.authors
        )

        def label(entity):
            for name in ('display_name', 'name', 'title'):
                value = getattr(entity, name, None)
                if value:
                    return value
            return str(entity.id)

        header = '\n'.join((
            filing.document_type.id,
            'Adresat: ' + label(recipient),
            'Nadawca: ' + ', '.join(label(author) for author in authors),
        ))
        parties = []
        for target in (*filing.authors, filing.recipient):
            if target.kind == 'Party' and target not in parties:
                parties.append(target)
        attachments = []
        seen = set()
        for target in plan.evidence:
            evidence = resolve(
                target, records, principal.tenant_id, principal.case_id
            )
            if evidence.kind != 'Evidence':
                raise Violation('REFERENCE_TYPE')
            key = evidence.source.model_dump_json()
            if key not in seen:
                seen.add(key)
                attachments.append(evidence.source)
        signature = next(
            (target for target in filing.authors if target.kind == 'Party'), None
        )
        return w.SemanticDocument(
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            draft=ref(draft),
            snapshot_hash=draft.snapshot_hash,
            header=header,
            parties=tuple(parties),
            requests=plan.objectives,
            sections=draft.sections,
            attachments=tuple(attachments),
            signature_party=signature,
        )

    def _approve(self, request, principal, tx, records, heads, now):
        draft = self._current_draft(
            request, principal, records, heads, 'VALIDATED'
        )
        execution, run = self._validation_gate(
            request, draft, principal, tx, records, heads, now
        )
        body = draft.model_dump(mode='json')
        body.update(self._metadata(request, principal, now, 'Draft', draft))
        body['provenance'].update(
            method='RENDER_AUTHORIZATION',
            inputs=[ref(draft).model_dump(mode='json')],
            tool=profile_pin().model_dump(mode='json'),
        )
        body['status'] = 'APPROVED'
        approved = entity_from(body, m.Draft)
        self._validate(approved, draft, tx, records, heads, principal)
        tx.append(approved)
        records[ref(approved)] = approved
        heads[(approved.kind, approved.id)] = approved

        authorization = RenderAuthorization(
            id=uuid5(request.meta.command_id, 'render-authorization'),
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            actor=principal.actor,
            validated_draft=ref(draft),
            validated_hash=digest(draft),
            approved_draft=ref(approved),
            approved_hash=digest(approved),
            validation_run_id=run.id,
            validation_run_hash=digest(run),
            profile=profile_pin(),
            input_sequence=request.meta.expected_case_sequence,
            committed_sequence=request.meta.expected_case_sequence + 1,
            recorded_at=now,
            rationale=request.rationale,
        )
        tx.put_object(AUTH_CATEGORY, authorization.id, authorization)
        edge = w.DependencyEdge(
            source=ref(draft), target=ref(approved), input_hash=digest(draft)
        )
        tx.put_object(
            'dependency',
            uuid5(request.meta.command_id, digest(edge)),
            edge,
        )
        return (ref(approved),), 'RenderAuthorized', authorization

    def _authorization(self, request, approved, principal, tx, records):
        authorization = tx.object(
            AUTH_CATEGORY, request.authorization_id, RenderAuthorization
        )
        if (
            authorization.id != request.authorization_id
            or (authorization.tenant_id, authorization.case_id)
            != (principal.tenant_id, principal.case_id)
            or authorization.actor.kind != 'HUMAN'
            or authorization.approved_draft != ref(approved)
            or authorization.approved_hash != digest(approved)
            or authorization.profile != request.profile
            or request.meta.expected_case_sequence
            != authorization.committed_sequence
        ):
            raise Violation('STALE')
        validated = resolve(
            authorization.validated_draft,
            records,
            principal.tenant_id,
            principal.case_id,
        )
        if (
            validated.status != 'VALIDATED'
            or digest(validated) != authorization.validated_hash
            or approved.revision != validated.revision + 1
            or approved.previous_hash != digest(validated)
        ):
            raise Violation('INVALID_HASH')
        run = tx.object(
            'validation_run', authorization.validation_run_id, w.ValidationRun
        )
        if digest(run) != authorization.validation_run_hash:
            raise Violation('INVALID_HASH')
        return authorization, validated, run

    def _render(self, request, principal, tx, records, heads, now):
        approved = self._current_draft(
            request, principal, records, heads, 'APPROVED'
        )
        authorization, validated, source_run = self._authorization(
            request, approved, principal, tx, records
        )

        # No domain mutation may occur between the human authorization and rendering.
        # The one sequence increment since Stage 10 is the authorization itself.
        if request.meta.expected_case_sequence != authorization.committed_sequence:
            raise Violation('STALE')

        semantic = self._semantic_document(approved, principal, records)
        profile = official_pl_profile()
        formats = tuple(name for name in ('DOCX', 'PDF') if name in request.formats)
        rendered_bytes = render(semantic, profile, formats)

        case = heads[('Case', principal.case_id)]
        store = ObjectStore(tx)
        policies = self.repository.retention_policies or RetentionPolicies()
        execution_id = uuid5(request.meta.command_id, 'render-execution')
        artifacts = []
        for format_name in ('DOCX', 'PDF'):
            data, media_type = rendered_bytes[format_name]
            name = f'render/{approved.id}/{format_name.lower()}'
            version = str(execution_id)
            target = artifact_id(tx.scope, 'render', name, version)
            item = store.put(
                target,
                'render',
                name,
                version,
                data,
                case.retention_policy,
                principal.actor.id,
                now,
                policies,
            )
            artifacts.append(RenderArtifact(
                format=format_name,
                artifact_id=item.artifact_id,
                content_hash=item.content_hash,
                byte_length=item.byte_length,
                media_type=media_type,
            ))
        artifacts = tuple(artifacts)

        body = approved.model_dump(mode='json')
        body.update(self._metadata(request, principal, now, 'Draft', approved))
        body['provenance'].update(
            method='RENDERING',
            inputs=[ref(approved).model_dump(mode='json')],
            tool=renderer_pin().model_dump(mode='json'),
        )
        body['status'] = 'RENDERED'
        rendered_draft = entity_from(body, m.Draft)
        self._validate(
            rendered_draft, approved, tx, records, heads, principal
        )
        tx.append(rendered_draft)
        records[ref(rendered_draft)] = rendered_draft
        heads[(rendered_draft.kind, rendered_draft.id)] = rendered_draft

        run_id = uuid5(request.meta.command_id, 'render-validation-run')
        findings = []
        for old_ref in source_run.findings:
            old = resolve(
                old_ref, records, principal.tenant_id, principal.case_id
            )
            if old.severity in BLOCKING:
                raise Violation('GATE_DENIED')
            item = self._metadata(
                request, principal, now, 'ValidationFinding'
            )
            item['provenance'].update(
                method='RENDER_VALIDATION',
                inputs=[
                    ref(rendered_draft).model_dump(mode='json'),
                    ref(old).model_dump(mode='json'),
                ],
                tool=renderer_pin().model_dump(mode='json'),
            )
            identity = (
                old.layer, old.code, old.severity, old.message, old.path
            )
            item.update(
                id=str(uuid5(run_id, digest(identity))),
                status='OPEN',
                run_id=str(run_id),
                target=ref(rendered_draft).model_dump(mode='json'),
                target_hash=digest(rendered_draft),
                layer=old.layer,
                code=old.code,
                severity=old.severity,
                message=old.message,
                path=old.path,
                resolution=None,
            )
            finding = entity_from(item, m.ValidationFinding)
            self._validate(
                finding, None, tx, records, heads, principal
            )
            tx.append(finding)
            records[ref(finding)] = finding
            findings.append(finding)

        manifest = RenderManifest(
            semantic_hash=digest(semantic),
            profile=profile_pin(),
            renderer=renderer_pin(),
            source_draft_hash=digest(approved),
            authorization_hash=digest(authorization),
            artifacts=artifacts,
        )
        prechecks = tuple(
            check for check in source_run.checks if check.check != 'render'
        )
        run = w.ValidationRun(
            id=run_id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            draft=ref(rendered_draft),
            draft_hash=digest(rendered_draft),
            snapshot_hash=rendered_draft.snapshot_hash,
            policy=source_run.policy,
            completed_at=now,
            checks=prechecks + (
                w.CheckResult(
                    check='render',
                    outcome='PASS',
                    validator=renderer_pin(),
                ),
            ),
            findings=tuple(ref(finding) for finding in findings),
            render_hashes=tuple(
                artifact.content_hash for artifact in artifacts
            ),
            execution_manifest_hash=digest(manifest),
        )
        execution = RenderExecution(
            id=execution_id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            authorization=authorization,
            semantic_document=semantic,
            rendered_draft=ref(rendered_draft),
            rendered_hash=digest(rendered_draft),
            run=run,
            artifacts=artifacts,
            manifest=manifest,
            input_sequence=request.meta.expected_case_sequence,
            committed_sequence=request.meta.expected_case_sequence + 1,
            recorded_at=now,
        )
        tx.put_object('validation_run', run.id, run)
        tx.put_object(EXECUTION_CATEGORY, execution.id, execution)
        edge = w.DependencyEdge(
            source=ref(approved),
            target=ref(rendered_draft),
            input_hash=digest(approved),
        )
        tx.put_object(
            'dependency',
            uuid5(request.meta.command_id, digest(edge)),
            edge,
        )
        return (
            ref(rendered_draft),
            *(ref(finding) for finding in findings),
        ), 'DocumentRendered', execution

    def _apply(self, request, principal, tx, records, heads, now):
        if request.operation == 'RecordRenderAuthorization':
            return self._approve(
                request, principal, tx, records, heads, now
            )
        if request.operation == 'RenderDocument':
            return self._render(
                request, principal, tx, records, heads, now
            )
        raise Violation('FORBIDDEN')

    def query(self, raw, token):
        try:
            query = RenderingQuery.model_validate_json(
                json.dumps(strict_json(raw), allow_nan=False)
            )
            with self.authority.session(token) as principal:
                principal.require(
                    query.tenant_id, query.case_id, query.operation
                )
                with self.repository.transaction(
                    query.tenant_id, query.case_id
                ) as tx:
                    execution = tx.object(
                        EXECUTION_CATEGORY,
                        query.execution_id,
                        RenderExecution,
                    )
                    run = tx.object(
                        'validation_run', execution.run.id, w.ValidationRun
                    )
                    records = tx.records()
                    heads = {
                        (entity.kind, entity.id): entity
                        for entity in tx.heads()
                    }
                    reasons = []
                    if (
                        execution.id != query.execution_id
                        or execution.run != run
                        or digest(execution.manifest)
                        != run.execution_manifest_hash
                        or digest(execution.semantic_document)
                        != execution.manifest.semantic_hash
                        or execution.manifest.profile != profile_pin()
                        or execution.manifest.renderer != renderer_pin()
                    ):
                        reasons.append('EXECUTION_IDENTITY_INVALID')
                    draft = records.get(execution.rendered_draft)
                    if (
                        draft is None
                        or digest(draft) != execution.rendered_hash
                        or heads.get(('Draft', execution.rendered_draft.id))
                        != draft
                        or draft.status != 'RENDERED'
                    ):
                        reasons.append('RENDERED_DRAFT_STALE')
                    if tx.sequence() != execution.committed_sequence:
                        reasons.append('CASE_SEQUENCE_STALE')
                    checks = {check.check: check for check in run.checks}
                    if (
                        set(checks) != set(w.REQUIRED_CHECKS)
                        or any(
                            check.outcome != 'PASS'
                            for check in run.checks
                        )
                    ):
                        reasons.append('CHECKS_INCOMPLETE')
                    if tuple(
                        artifact.content_hash
                        for artifact in execution.artifacts
                    ) != run.render_hashes:
                        reasons.append('RENDER_HASH_MISMATCH')
                    store = ObjectStore(tx)
                    for artifact in execution.artifacts:
                        try:
                            data = store.read(artifact.artifact_id)
                            if (
                                len(data) != artifact.byte_length
                                or __import__('hashlib').sha256(data).hexdigest()
                                != artifact.content_hash
                            ):
                                raise Violation('INVALID_HASH')
                        except (Violation, ValueError, KeyError, TypeError):
                            reasons.append('RENDER_BYTES_UNAVAILABLE')
                    principal.require(
                        query.tenant_id, query.case_id, query.operation
                    )
                    reasons = tuple(sorted(set(reasons)))
                    return RenderingProjection(
                        execution=execution,
                        freshness='CURRENT' if not reasons else 'STALE',
                        eligible_for_document_approval=not reasons,
                        reasons=reasons,
                    )
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (
            ValidationError, ValueError, KeyError, TypeError,
            RecursionError, OverflowError,
        ):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('UNKNOWN', UUID(int=0))
            raise
