"""Authenticated PB02 composition of validation, rendering, storage and release."""
from __future__ import annotations

import json
from uuid import UUID, uuid5

from pydantic import ValidationError

from lukart_work.contracts import messages as wire
from lukart_work.core.postgres import canonical
from lukart_work.core.service import CommandService, entity_from, safe_error
from lukart_work.domain import models as m
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.rendering.service import (
    RenderedBundle,
    RenderingEngine,
    authorization_binding,
    derive_render_authority,
    renderer_pin,
)
from lukart_work.storage.objects import ObjectStore, RetentionPolicies, artifact_id
from lukart_work.validation.contracts import PRE_RENDER_CHECKS, ValidationExecution, ValidationProjection
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.rules import (
    Violation,
    digest,
    evaluate_release,
    ref,
    resolve,
    strict_json,
)

from .contracts import (
    FinalizationApproval,
    FinalizationProfile,
    FinalizationProjection,
    FinalizationQuery,
    FinalizationRelease,
    FinalizationRequest,
    PersistedRender,
    PersistedRenderArtifact,
    PostRenderManifest,
    semantic_profile_pin,
)


RENDER_CATEGORY = "finalization_render"
APPROVAL_CATEGORY = "finalization_approval"
POST_RENDER_RUN_CATEGORY = "finalization_validation_run"
RELEASE_CATEGORY = "finalization_release"


class FinalizationService(CommandService):
    """A trusted host boundary; no caller supplies semantic text, PASS or a receipt."""

    def __init__(self, repository, authority, profiles, clock=None):
        super().__init__(repository, authority, clock)
        checked = tuple(
            item if isinstance(item, FinalizationProfile) else FinalizationProfile.model_validate(item)
            for item in profiles
        )
        self.profiles = {canonical(item.document_type): item for item in checked}
        if len(self.profiles) != len(checked):
            raise ValueError("DUPLICATE_PROFILE")
        self.renderer = RenderingEngine()

    def _parse_request(self, raw):
        return FinalizationRequest.model_validate_json(
            json.dumps(strict_json(raw), allow_nan=False)
        )

    def _case_guard(self, request, principal, case):
        super()._case_guard(request, principal, case)
        if principal.actor.kind != "HUMAN":
            raise Violation("FORBIDDEN")

    def _profile(self, document_type, expected_pin):
        profile = self.profiles.get(canonical(document_type))
        if profile is None or semantic_profile_pin(profile) != expected_pin:
            raise Violation("GATE_DENIED")
        if profile.render_profile != profile_pin(OFFICIAL_PL_V1):
            raise Violation("GATE_DENIED")
        return profile

    @staticmethod
    def _validation_projection(request, principal, tx, records, heads, draft, now):
        execution = tx.object("validation_execution", request.validation_run_id, ValidationExecution)
        run = tx.object("validation_run", request.validation_run_id, wire.ValidationRun)
        if execution.id != request.validation_run_id or run != execution.run:
            raise Violation("INVALID_HASH")
        if (
            execution.output_draft != ref(draft)
            or execution.output_hash != digest(draft)
            or execution.validator != validation_pin()
            or run.policy != validation_pin()
            or execution.manifest.policy != validation_pin()
            or digest(execution.manifest) != run.execution_manifest_hash
            or execution.committed_sequence != request.meta.expected_case_sequence
            or execution.evaluation_date != now.date()
        ):
            raise Violation("STALE")
        if tuple(target for target, _ in execution.manifest.dependency_hashes) != execution.dependencies:
            raise Violation("INVALID_HASH")
        for target, expected_hash in execution.manifest.dependency_hashes:
            entity = resolve(target, records, principal.tenant_id, principal.case_id)
            if digest(entity) != expected_hash:
                raise Violation("STALE")
            if target == run.draft and target.id == draft.id:
                continue
            if heads.get((target.kind, target.id)) != entity:
                raise Violation("STALE")
        if heads.get(("Draft", draft.id)) != draft or draft.status != "VALIDATED":
            raise Violation("STALE")
        checks = {item.check: item for item in run.checks}
        if (
            len(checks) != len(run.checks)
            or set(checks) != set(PRE_RENDER_CHECKS) | {"render"}
            or any(checks[name].outcome != "PASS" for name in PRE_RENDER_CHECKS)
            or checks["render"].outcome != "NOT_RUN"
            or run.findings
            or run.render_hashes
        ):
            raise Violation("GATE_DENIED")
        return ValidationProjection(
            execution=execution,
            freshness="CURRENT",
            eligible_for_approval=True,
            reasons=(),
        )

    @staticmethod
    def _semantic_document(principal, records, draft, profile):
        plan = resolve(draft.plan, records, principal.tenant_id, principal.case_id)
        filing = resolve(plan.filing, records, principal.tenant_id, principal.case_id)
        if plan.kind != "DocumentPlan" or plan.status != "APPROVED" or filing.kind != "Filing":
            raise Violation("GATE_DENIED")
        if filing.document_type != profile.document_type or not filing.authors:
            raise Violation("GATE_DENIED")
        parties = tuple(dict.fromkeys((*filing.authors, filing.recipient)))
        for target in (*parties, *plan.objectives, *plan.evidence):
            resolve(target, records, principal.tenant_id, principal.case_id)
        attachments = tuple(records[target].source for target in plan.evidence)
        return wire.SemanticDocument(
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            draft=ref(draft),
            snapshot_hash=draft.snapshot_hash,
            header=profile.header,
            parties=parties,
            requests=plan.objectives,
            sections=draft.sections,
            attachments=attachments,
            signature_party=filing.authors[0],
        )

    @staticmethod
    def _validated_render_records(records, validation):
        """Hide historical Evidence revisions from the attachment resolver.

        Stage 10 pins the exact accepted Evidence revisions in its dependency
        manifest.  Older revisions can legitimately share the same source
        anchor, but they are not render authority and must not make attachment
        resolution ambiguous.
        """
        evidence_refs = {
            target
            for target in validation.execution.dependencies
            if target.kind == "Evidence"
        }
        return {
            target: item
            for target, item in records.items()
            if not isinstance(item, m.Evidence) or target in evidence_refs
        }

    def _render(self, request, principal, tx, records, heads, now):
        if not getattr(self.repository, "storage", False):
            raise Violation("GATE_DENIED")
        draft = self._target(request, records, heads, "Draft")
        if (
            draft.status != "VALIDATED"
            or digest(draft) != request.draft_hash
            or draft.snapshot_hash != request.snapshot_hash
        ):
            raise Violation("INVALID_HASH")
        validation = self._validation_projection(
            request, principal, tx, records, heads, draft, now
        )
        render_records = self._validated_render_records(records, validation)
        plan = resolve(draft.plan, records, principal.tenant_id, principal.case_id)
        filing = resolve(plan.filing, records, principal.tenant_id, principal.case_id)
        profile = self._profile(filing.document_type, request.semantic_profile)
        if draft.reproduction.render_profile != profile.render_profile:
            raise Violation("GATE_DENIED")
        document = self._semantic_document(principal, records, draft, profile)
        authority = derive_render_authority(
            document, render_records, validation, profile.render_profile
        )
        render_request = wire.RenderRequest(
            document=document,
            profile=profile.render_profile,
            authorization_hash=authorization_binding(
                document, profile.render_profile, authority
            ),
        )
        bundle = self.renderer.render(render_request, render_records, validation)
        self.renderer.validate(bundle)
        render_id = uuid5(request.meta.command_id, "persisted-render")
        case = heads[("Case", principal.case_id)]
        policies = self.repository.retention_policies or RetentionPolicies()
        store = ObjectStore(tx)
        persisted = []
        for suffix, data, artifact in (
            ("final.docx", bundle.docx, bundle.meta.receipt.artifacts[0]),
            ("final.pdf", bundle.pdf, bundle.meta.receipt.artifacts[1]),
        ):
            name = f"finalization/{render_id}/{suffix}"
            target = artifact_id(store.scope, "render", name, "1")
            item = store.put(
                target,
                "render",
                name,
                "1",
                data,
                case.retention_policy,
                principal.actor.id,
                now,
                policies,
            )
            if (item.content_hash, item.byte_length) != (artifact.content_hash, artifact.byte_length):
                raise Violation("INVALID_HASH")
            persisted.append(PersistedRenderArtifact(artifact_id=target, artifact=artifact))
        record = PersistedRender(
            id=render_id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            validated_draft=ref(draft),
            validated_draft_hash=digest(draft),
            snapshot_id=draft.snapshot_id,
            snapshot_hash=draft.snapshot_hash,
            semantic_profile=semantic_profile_pin(profile),
            document=document,
            validation=validation,
            meta=bundle.meta,
            artifacts=tuple(persisted),
            actor=principal.actor,
            recorded_at=now,
            committed_sequence=request.meta.expected_case_sequence + 1,
        )
        tx.put_object(RENDER_CATEGORY, record.id, record)
        return (ref(draft),), "RevisionAppended", record

    def _load_render(self, tx, records, principal, render_id):
        record = tx.object(RENDER_CATEGORY, render_id, PersistedRender)
        if (record.tenant_id, record.case_id) != (principal.tenant_id, principal.case_id):
            raise Violation("CROSS_CASE")
        data = tuple(ObjectStore(tx).read(item.artifact_id) for item in record.artifacts)
        bundle = RenderedBundle(docx=data[0], pdf=data[1], meta=record.meta)
        self.renderer.validate(bundle)
        render_request = wire.RenderRequest(
            document=record.document,
            profile=record.meta.receipt.render_profile,
            authorization_hash=record.meta.receipt.authorization_hash,
        )
        render_records = self._validated_render_records(records, record.validation)
        reproduced = self.renderer.render(
            render_request, render_records, record.validation
        )
        if reproduced != bundle:
            raise Violation("INVALID_HASH")
        return record, bundle

    def _transition_draft(self, request, principal, tx, records, heads, now, old, status):
        body = old.model_dump(mode="json")
        body.update(self._metadata(request, principal, now, "Draft", old))
        body["status"] = status
        revised = entity_from(body, m.Draft)
        self._validate(revised, old, tx, records, heads, principal)
        tx.append(revised)
        records[ref(revised)] = revised
        heads[("Draft", revised.id)] = revised
        return revised

    def _approve(self, request, principal, tx, records, heads, now):
        draft = self._target(request, records, heads, "Draft")
        if (
            draft.status != "VALIDATED"
            or digest(draft) != request.draft_hash
            or draft.snapshot_hash != request.snapshot_hash
        ):
            raise Violation("INVALID_HASH")
        render, _bundle = self._load_render(tx, records, principal, request.render_id)
        if (
            render.validated_draft != ref(draft)
            or render.validated_draft_hash != digest(draft)
            or render.committed_sequence != request.meta.expected_case_sequence
        ):
            raise Violation("STALE")
        approved = self._transition_draft(
            request, principal, tx, records, heads, now, draft, "APPROVED"
        )
        rendered = self._transition_draft(
            request, principal, tx, records, heads, now, approved, "RENDERED"
        )
        render_hashes = tuple(item.artifact.content_hash for item in render.artifacts)
        target = m.RenderTarget(
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            snapshot_id=rendered.snapshot_id,
            snapshot_hash=rendered.snapshot_hash,
            draft=ref(rendered),
            draft_hash=digest(rendered),
            render_hashes=render_hashes,
        )
        proposal = entity_from(
            dict(
                self._metadata(request, principal, now, "Decision"),
                status="PROPOSED",
                decision_type="DOCUMENT_APPROVAL",
                targets=[ref(rendered).model_dump(mode="json")],
                outcome="ACCEPT",
                rationale=request.rationale,
                decided_by=principal.actor.model_dump(mode="json"),
                supersedes=None,
                snapshot_target=None,
                render_target=target.model_dump(mode="json"),
            ),
            m.Decision,
        )
        self._validate(proposal, None, tx, records, heads, principal)
        tx.append(proposal)
        records[ref(proposal)] = proposal
        heads[("Decision", proposal.id)] = proposal
        body = proposal.model_dump(mode="json")
        body.update(revision=2, previous_hash=digest(proposal), status="RECORDED")
        decision = entity_from(body, m.Decision)
        self._validate(decision, proposal, tx, records, heads, principal)
        tx.append(decision)
        records[ref(decision)] = decision
        heads[("Decision", decision.id)] = decision

        pre_run = render.validation.execution.run
        post_run_id = uuid5(request.meta.command_id, "post-render-validation")
        checks = tuple(
            wire.CheckResult(
                check=item.check,
                outcome="PASS",
                validator=renderer_pin() if item.check == "render" else item.validator,
            )
            for item in pre_run.checks
        )
        manifest = PostRenderManifest(
            input_validation=wire.ValidationRunPin(id=pre_run.id, content_hash=digest(pre_run)),
            input_validation_projection_hash=digest(render.validation),
            render_receipt_hash=digest(render.meta.receipt),
            rendered_draft=ref(rendered),
            rendered_draft_hash=digest(rendered),
            approval=ref(decision),
            approval_hash=digest(decision),
            artifacts=tuple(item.artifact for item in render.artifacts),
            policy=validation_pin(),
        )
        post_run = wire.ValidationRun(
            id=post_run_id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            draft=ref(rendered),
            draft_hash=digest(rendered),
            snapshot_hash=rendered.snapshot_hash,
            policy=validation_pin(),
            completed_at=now,
            checks=checks,
            findings=(),
            render_hashes=render_hashes,
            execution_manifest_hash=digest(manifest),
        )
        approval = FinalizationApproval(
            render_id=render.id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            rendered_draft=ref(rendered),
            rendered_draft_hash=digest(rendered),
            approval=ref(decision),
            approval_hash=digest(decision),
            post_render_run=post_run,
            manifest=manifest,
            actor=principal.actor,
            recorded_at=now,
            committed_sequence=request.meta.expected_case_sequence + 1,
        )
        tx.put_object(POST_RENDER_RUN_CATEGORY, post_run.id, post_run)
        tx.put_object(APPROVAL_CATEGORY, render.id, approval)
        return (ref(rendered), ref(decision)), "DecisionRecorded", approval

    def _release(self, request, principal, tx, records, heads, now):
        draft = self._target(request, records, heads, "Draft")
        if (
            draft.status != "RENDERED"
            or digest(draft) != request.draft_hash
            or draft.snapshot_hash != request.snapshot_hash
        ):
            raise Violation("INVALID_HASH")
        render, _bundle = self._load_render(tx, records, principal, request.render_id)
        approval_record = tx.object(APPROVAL_CATEGORY, render.id, FinalizationApproval)
        if (
            approval_record.committed_sequence != request.meta.expected_case_sequence
            or approval_record.rendered_draft != ref(draft)
            or approval_record.rendered_draft_hash != digest(draft)
            or approval_record.manifest.render_receipt_hash != digest(render.meta.receipt)
        ):
            raise Violation("STALE")
        approval = self._live_decision(approval_record.approval, records, heads, principal)
        if digest(approval) != approval_record.approval_hash:
            raise Violation("INVALID_HASH")
        stored_run = tx.object(
            POST_RENDER_RUN_CATEGORY,
            approval_record.post_render_run.id,
            wire.ValidationRun,
        )
        if stored_run != approval_record.post_render_run:
            raise Violation("INVALID_HASH")
        freshness = wire.FreshnessAssessment(
            target=ref(draft),
            snapshot_hash=draft.snapshot_hash,
            current_case_sequence=request.meta.expected_case_sequence,
            state="CURRENT",
            changed_inputs=(),
        )
        result = evaluate_release(
            draft,
            stored_run,
            (),
            approval,
            freshness,
            validation_pin(),
            tuple(item.artifact.content_hash for item in render.artifacts),
        )
        if result.eligibility != "FINAL" or result.receipt is None:
            raise Violation("GATE_DENIED")
        previous = tx.last_event_hash()
        if previous is None:
            raise Violation("PROVENANCE_MISSING")
        release = FinalizationRelease(
            id=uuid5(request.meta.command_id, "final-release"),
            render_id=render.id,
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            result=result,
            approval=ref(approval),
            approval_hash=digest(approval),
            audit_previous_event_hash=previous,
            actor=principal.actor,
            recorded_at=now,
            committed_sequence=request.meta.expected_case_sequence + 1,
        )
        tx.put_object(RELEASE_CATEGORY, render.id, release)
        return (ref(draft),), "ReleaseGranted", release

    def _apply(self, request, principal, tx, records, heads, now):
        if request.operation == "RenderDraft":
            return self._render(request, principal, tx, records, heads, now)
        if request.operation == "ApproveFinalDocument":
            return self._approve(request, principal, tx, records, heads, now)
        if request.operation == "RequestFinalRelease":
            return self._release(request, principal, tx, records, heads, now)
        raise Violation("FORBIDDEN")

    @staticmethod
    def _optional(tx, category, object_id, cls):
        try:
            return tx.object(category, object_id, cls)
        except Violation as error:
            if error.code == "BROKEN_REFERENCE":
                return None
            raise

    def query(self, raw, token):
        try:
            query = FinalizationQuery.model_validate_json(
                json.dumps(strict_json(raw), allow_nan=False)
            )
            action = {
                "GetFinalization": "GetFinalization",
                "GetFinalRelease": "GetFinalRelease",
                "ReadFinalArtifact": "ReadFinalArtifact",
            }[query.operation]
            with self.authority.session(token) as principal:
                principal.require(query.tenant_id, query.case_id, action)
                if principal.actor.kind == "AI":
                    raise Violation("FORBIDDEN")
                with self.repository.transaction(query.tenant_id, query.case_id) as tx:
                    records = tx.records()
                    render, _bundle = self._load_render(tx, records, principal, query.render_id)
                    approval = self._optional(
                        tx, APPROVAL_CATEGORY, render.id, FinalizationApproval
                    )
                    release = self._optional(
                        tx, RELEASE_CATEGORY, render.id, FinalizationRelease
                    )
                    if query.operation == "ReadFinalArtifact":
                        item = next(
                            artifact
                            for artifact in render.artifacts
                            if artifact.artifact.format == query.format
                        )
                        result = ObjectStore(tx).read(item.artifact_id)
                    elif query.operation == "GetFinalRelease":
                        if release is None:
                            raise Violation("BROKEN_REFERENCE")
                        result = release
                    else:
                        result = FinalizationProjection(
                            render=render, approval=approval, release=release
                        )
                    principal.require(query.tenant_id, query.case_id, action)
                return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, TypeError, KeyError, StopIteration, RecursionError):
            return safe_error("SCHEMA_INVALID", UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith("psycopg"):
                return safe_error(
                    "CONFLICT"
                    if getattr(error, "sqlstate", "") in ("23505", "40001", "40P01")
                    else "UNKNOWN",
                    UUID(int=0),
                )
            raise
