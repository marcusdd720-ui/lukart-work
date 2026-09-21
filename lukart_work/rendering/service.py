"""Stage 11 fail-closed rendering service over exact validated draft state."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid5

from pydantic import ValidationError

from lukart_work.core.service import safe_error
from lukart_work.storage.objects import ObjectStore, RetentionPolicies, artifact_id
from lukart_work.validation.contracts import ValidationExecution
from lukart_work.validation.rules import Violation, digest, strict_json
from .adapters import render_format
from .compiler import build_semantic_document, compile_render_tree
from .contracts import (
    RenderedArtifact,
    RenderingExecution,
    RenderingRequest,
    RenderingResult,
)
from .policy import adapter_pin, profile_pin, renderer_pin, resolve_profile

_BLOCKING = {"ERROR", "BLOCKER", "CRITICAL"}


class RenderingEngineService:
    def __init__(self, repository, authority, clock=None):
        self.repository = repository
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _parse(self, raw):
        return RenderingRequest.model_validate_json(json.dumps(strict_json(raw), allow_nan=False))

    @staticmethod
    def _validate_validation(execution: ValidationExecution, draft, records, case_sequence):
        run = execution.run
        expected_hash = digest(draft)
        if (
            execution.output_draft.kind != "Draft"
            or execution.output_draft.id != draft.id
            or execution.output_draft.revision != draft.revision
            or execution.output_hash != expected_hash
            or run.draft != execution.output_draft
            or run.draft_hash != expected_hash
            or run.snapshot_hash != draft.snapshot_hash
            or execution.committed_sequence != case_sequence
        ):
            raise Violation("STALE")
        if draft.status != "VALIDATED":
            raise Violation("GATE_DENIED")
        outcomes = {check.check: check.outcome for check in run.checks}
        if outcomes.get("render") != "NOT_RUN":
            raise Violation("GATE_DENIED")
        required = {check.check for check in run.checks if check.check != "render"}
        if not required or any(outcomes.get(name) != "PASS" for name in required):
            raise Violation("GATE_DENIED")
        for finding_ref in run.findings:
            finding = records.get(finding_ref)
            if finding is None:
                raise Violation("BROKEN_REFERENCE")
            if finding.severity in _BLOCKING and finding.status == "OPEN":
                raise Violation("GATE_DENIED")

    def render(self, raw, token):
        correlation = UUID(int=0)
        try:
            request = self._parse(raw)
            correlation = request.meta.correlation_id
            request_hash = digest(request)
            execution_id = uuid5(request.meta.idempotency_key, "rendering-execution")

            with self.authority.session(token) as principal:
                principal.require(request.meta.tenant_id, request.meta.case_id, request.operation)
                if principal.actor.kind == "AI":
                    raise Violation("FORBIDDEN")
                with self.repository.transaction(request.meta.tenant_id, request.meta.case_id) as tx:
                    if tx.sequence() != request.meta.expected_case_sequence:
                        raise Violation("CONFLICT")
                    if not getattr(tx, "storage", False):
                        raise Violation("GATE_DENIED")

                    previous = next(
                        (item for item in tx.objects("rendering_execution", RenderingExecution)
                         if item.id == execution_id),
                        None,
                    )
                    store = ObjectStore(tx)
                    if previous is not None:
                        if previous.request_hash != request_hash:
                            raise Violation("IDEMPOTENCY_CONFLICT")
                        for artifact in previous.artifacts:
                            data = store.read(artifact.artifact_id)
                            if sha256(data).hexdigest() != artifact.artifact_byte_hash:
                                raise Violation("INVALID_HASH")
                        principal.require(request.meta.tenant_id, request.meta.case_id, request.operation)
                        return RenderingResult(execution=previous, replayed=True)

                    records = tx.records()
                    draft = records.get(request.draft)
                    if draft is None:
                        raise Violation("BROKEN_REFERENCE")
                    if digest(draft) != request.draft_hash:
                        raise Violation("INVALID_HASH")
                    if (draft.tenant_id, draft.case_id) != (
                        request.meta.tenant_id, request.meta.case_id
                    ):
                        raise Violation("CROSS_CASE")

                    validation = tx.object(
                        "validation_execution", request.validation_run_id, ValidationExecution
                    )
                    self._validate_validation(validation, draft, records, tx.sequence())

                    case_head = next((item for item in tx.heads() if item.kind == "Case"), None)
                    if case_head is None:
                        raise Violation("BROKEN_REFERENCE")
                    if request.retention_policy != case_head.retention_policy:
                        raise Violation("GATE_DENIED")

                    try:
                        profile = resolve_profile(request.profile)
                    except ValueError as exc:
                        raise Violation("GATE_DENIED") from exc
                    if request.profile != profile_pin() or digest(profile) != request.profile.content_hash:
                        raise Violation("INVALID_HASH")

                    semantic = build_semantic_document(draft, records)
                    tree = compile_render_tree(semantic, profile)
                    tree_digest = digest(tree)
                    renderer = renderer_pin()
                    now = self.clock()
                    if now.tzinfo is None:
                        raise Violation("SCHEMA_INVALID")

                    artifacts = []
                    policies = self.repository.retention_policies or RetentionPolicies()
                    for output_format in request.formats:
                        adapter = adapter_pin(output_format)
                        try:
                            first = render_format(output_format, tree, profile)
                            second = render_format(output_format, tree, profile)
                        except ValueError as exc:
                            raise Violation("GATE_DENIED") from exc
                        if (
                            first.data != second.data
                            or first.media_type != second.media_type
                            or first.resource_hashes != second.resource_hashes
                        ):
                            raise Violation("INVALID_HASH")

                        presentation_digest = digest({
                            "render_tree_digest": tree_digest,
                            "profile_digest": tree.profile_digest,
                            "renderer": renderer.model_dump(mode="json"),
                            "adapter": adapter.model_dump(mode="json"),
                            "format": output_format,
                            "resource_hashes": first.resource_hashes,
                        })
                        name = f"render/{draft.id}/{output_format.lower()}"
                        target = artifact_id(
                            store.scope, "render", name, presentation_digest
                        )
                        metadata = store.put(
                            target,
                            "render",
                            name,
                            presentation_digest,
                            first.data,
                            request.retention_policy,
                            principal.actor.id,
                            now,
                            policies,
                        )
                        artifact = RenderedArtifact(
                            artifact_id=target,
                            tenant_id=draft.tenant_id,
                            case_id=draft.case_id,
                            draft=request.draft,
                            draft_hash=request.draft_hash,
                            snapshot_hash=draft.snapshot_hash,
                            validation_run_id=request.validation_run_id,
                            semantic_digest=tree.semantic_digest,
                            profile=request.profile,
                            profile_digest=tree.profile_digest,
                            renderer=renderer,
                            adapter=adapter,
                            format=output_format,
                            media_type=first.media_type,
                            render_tree_digest=tree_digest,
                            presentation_digest=presentation_digest,
                            resource_hashes=first.resource_hashes,
                            artifact_byte_hash=metadata.content_hash,
                            byte_length=metadata.byte_length,
                            created_at=now,
                        )
                        tx.put_object("rendered_artifact", target, artifact)
                        artifacts.append(artifact)

                    execution = RenderingExecution(
                        id=execution_id,
                        tenant_id=draft.tenant_id,
                        case_id=draft.case_id,
                        input_case_sequence=tx.sequence(),
                        request_hash=request_hash,
                        draft=request.draft,
                        draft_hash=request.draft_hash,
                        validation_run_id=request.validation_run_id,
                        semantic_document=semantic,
                        render_tree=tree,
                        artifacts=tuple(artifacts),
                        renderer=renderer,
                        completed_at=now,
                    )
                    tx.put_object("rendering_execution", execution.id, execution)
                    principal.require(request.meta.tenant_id, request.meta.case_id, request.operation)
                    return RenderingResult(execution=execution, replayed=False)
        except Violation as error:
            return safe_error(error.code, correlation)
        except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
            return safe_error("SCHEMA_INVALID", correlation)
        except Exception as error:
            if type(error).__module__.startswith("psycopg"):
                return safe_error("CONFLICT" if getattr(error, "sqlstate", "") == "23505" else "UNKNOWN", correlation)
            raise
