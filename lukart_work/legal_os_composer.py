"""One-window document preparation using existing WORK services and gates.

No drafting/renderer replacement, automatic HUMAN decision or second case store.
An input brief remains source material until independently admitted in WORK.
"""
import json
from base64 import b64encode
from hashlib import sha256
from uuid import UUID, uuid5

from lukart_work.contracts.messages import CommandResult, DomainError, RevisionResult
from lukart_work.domain.models import Address
from lukart_work.embedded_document_engine import (
    EmbeddedDocumentEngine,
    EngineBoundaryError,
    MAX_ARTIFACT_SIZE,
    SavedArtifact,
    make_confirmation,
)
from lukart_work.finalization.contracts import (
    FINAL_PACKAGE_MEMBER_NAMES,
    FinalPackageRecord,
    FinalizationProjection,
    FinalizationRequest,
    semantic_profile_pin,
)
from lukart_work.legal_os_editor import _heads, _id, _open, _scope
from lukart_work.legal_os_intake import upload_case_source
from lukart_work.validation.policy import validation_pin
from lukart_work.validation.rules import digest

COMMAND_IDS = {"command_id", "idempotency_key", "correlation_id"}


def validate_form(raw):
    if not isinstance(raw, dict) or set(raw) != {"description", "document_type", "sender", "recipient"}:
        raise EngineBoundaryError("COMPOSER_FORM_INVALID")
    result = {}
    for key, limit in (("description", 20000), ("document_type", 2000)):
        value = raw[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise EngineBoundaryError("COMPOSER_REQUIRED_DATA")
        if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value):
            raise EngineBoundaryError("COMPOSER_INVALID_TEXT")
        result[key] = value.strip()
    for role in ("sender", "recipient"):
        party = raw[role]
        if not isinstance(party, dict) or set(party) != {"name", "address"}:
            raise EngineBoundaryError("COMPOSER_PARTY_REQUIRED")
        name = party["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 500 or any(ord(c) < 32 for c in name):
            raise EngineBoundaryError("COMPOSER_PARTY_REQUIRED")
        try:
            address = Address.model_validate_json(json.dumps(party["address"], allow_nan=False))
        except (ValueError, TypeError):
            raise EngineBoundaryError("COMPOSER_ADDRESS_REQUIRED") from None
        if not address.postal_code or not address.postal_code.strip() or any(not line.strip() for line in address.lines):
            raise EngineBoundaryError("COMPOSER_ADDRESS_REQUIRED")
        result[role] = {"name": name.strip(), "address": address.model_dump(mode="json")}
    return result


def _revision(operator, scope, token, reference):
    value = operator.query_core({"contract": "urn:lukart:work:CoreQuery:1.0.0", "operation": "GetRevision",
        "tenant_id": scope.tenant_id, "case_id": scope.case_id,
        "target": reference.model_dump(mode="json")}, token)
    if not isinstance(value, RevisionResult):
        raise EngineBoundaryError("COMPOSER_REVISION_UNAVAILABLE")
    entity = value.entity
    if (entity.kind, entity.id, entity.revision, str(entity.tenant_id), str(entity.case_id)) != (
        reference.kind, reference.id, reference.revision, scope.tenant_id, scope.case_id):
        raise EngineBoundaryError("COMPOSER_REVISION_SCOPE_MISMATCH")
    return entity


def _profile(operator):
    profile = getattr(operator, "case_profile", None)
    if profile is None or getattr(operator, "binding", None) is not None:
        raise EngineBoundaryError("COMPOSER_CASE_PROFILE_REQUIRED")
    return profile


def _meta(scope, sequence, payload):
    ids = {name: _id(payload[name]) for name in COMMAND_IDS}
    if len(set(ids.values())) != 3:
        raise EngineBoundaryError("COMPOSER_COMMAND_IDS_CONFLICT")
    return dict(ids, tenant_id=scope.tenant_id, case_id=scope.case_id, expected_case_sequence=sequence)


def _execute(operator, scope, route, request, token):
    engine = EmbeddedDocumentEngine(operator)
    result = engine.execute_confirmed(scope, route, request, make_confirmation(scope, route, request), token=token)
    if not isinstance(result, CommandResult) or result.state not in ("APPLIED", "REPLAYED"):
        # ABSTAIN/rejection is not success. Do not retry a write automatically.
        raise EngineBoundaryError("COMPOSER_NATIVE_OPERATION_REJECTED")
    return result




PACKAGE_MEDIA_TYPES = {
    "final.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "final.pdf": "application/pdf",
    **{name: "application/json" for name in FINAL_PACKAGE_MEMBER_NAMES if name.endswith(".json")},
}


def _finalization_projection(operator, scope, token, render_id):
    result = operator.query_finalization({
        "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
        "operation": "GetFinalization",
        "tenant_id": scope.tenant_id,
        "case_id": scope.case_id,
        "render_id": _id(render_id),
    }, token)
    if isinstance(result, DomainError) or not isinstance(result, FinalizationProjection):
        raise EngineBoundaryError("COMPOSER_FINALIZATION_READ_REJECTED")
    render = result.render
    if (str(render.tenant_id), str(render.case_id), str(render.id)) != (
        scope.tenant_id, scope.case_id, _id(render_id)
    ):
        raise EngineBoundaryError("COMPOSER_FINALIZATION_SCOPE_MISMATCH")
    return result


def _package_record(operator, scope, token, render_id, *, allow_forbidden=False):
    result = operator.query_finalization({
        "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
        "operation": "GetFinalPackage",
        "tenant_id": scope.tenant_id,
        "case_id": scope.case_id,
        "render_id": _id(render_id),
    }, token)
    if isinstance(result, DomainError):
        if result.code == "BROKEN_REFERENCE":
            return None
        if result.code == "FORBIDDEN" and allow_forbidden:
            return "FORBIDDEN"
        raise EngineBoundaryError("COMPOSER_PACKAGE_READ_REJECTED")
    if not isinstance(result, FinalPackageRecord) or (
        str(result.tenant_id), str(result.case_id), str(result.render_id)
    ) != (scope.tenant_id, scope.case_id, _id(render_id)):
        raise EngineBoundaryError("COMPOSER_PACKAGE_SCOPE_MISMATCH")
    return result


def _package_summary(package):
    if package is None:
        return None
    return {
        "package_id": str(package.id),
        "committed_sequence": package.committed_sequence,
        "manifest_hash": package.manifest_hash,
        "members": [
            {
                "name": member.name,
                "media_type": member.media_type,
                "byte_length": member.byte_length,
                "content_hash": member.content_hash,
            }
            for member in package.members
        ],
    }


def _current_finalization_draft(operator, scope, token, head, projection, expected_sequence):
    if projection.approval is None:
        draft_ref = projection.render.validated_draft
        expected_hash = projection.render.validated_draft_hash
        expected_status = "VALIDATED"
    else:
        draft_ref = projection.approval.rendered_draft
        expected_hash = projection.approval.rendered_draft_hash
        expected_status = "RENDERED"
    if head.case_sequence != expected_sequence or draft_ref not in head.heads:
        raise EngineBoundaryError("COMPOSER_FINALIZATION_STALE")
    draft = _revision(operator, scope, token, draft_ref)
    if (
        draft.status != expected_status
        or digest(draft) != expected_hash
        or draft.snapshot_hash != projection.render.snapshot_hash
    ):
        raise EngineBoundaryError("COMPOSER_FINALIZATION_BINDING_MISMATCH")
    return draft, draft_ref


def _finalization_context(operator, scope, token, render_id, head):
    projection = _finalization_projection(operator, scope, token, render_id)
    render, approval, release = projection.render, projection.approval, projection.release
    package_read_authorized = True
    package_result = (
        _package_record(operator, scope, token, render_id, allow_forbidden=True)
        if release is not None else None
    )
    if package_result == "FORBIDDEN":
        package_read_authorized = False
        package = None
    else:
        package = package_result
    latest_sequence = (
        package.committed_sequence if package is not None else
        release.committed_sequence if release is not None else
        approval.committed_sequence if approval is not None else
        render.committed_sequence
    )
    draft_ref = approval.rendered_draft if approval is not None else render.validated_draft
    expected_hash = approval.rendered_draft_hash if approval is not None else render.validated_draft_hash
    expected_status = "RENDERED" if approval is not None else "VALIDATED"
    draft = None
    if draft_ref in head.heads:
        draft = _revision(operator, scope, token, draft_ref)
    draft_bound = draft is not None and (
        draft.status == expected_status
        and digest(draft) == expected_hash
        and draft.snapshot_hash == render.snapshot_hash
    )
    current = head.case_sequence == latest_sequence and draft_bound
    finalization = getattr(operator, "finalization", None)
    repository = getattr(finalization, "repository", None)
    package_configured = (
        finalization is not None
        and getattr(finalization, "package_profile", None) is not None
        and bool(getattr(repository, "storage", False))
    )
    can_approve = bool(
        current and approval is None and release is None and package is None
        and draft is not None and draft.status == "VALIDATED"
    )
    can_release = bool(
        current and approval is not None and release is None and package is None
        and draft is not None and draft.status == "RENDERED"
    )
    can_assemble = bool(
        current and release is not None and package is None and package_configured
        and package_read_authorized
        and draft is not None and draft.status == "RENDERED"
    )
    if package is not None:
        status = "PACKAGE_READY"
        next_gate = "PACKAGE_READ"
    elif release is not None:
        status = "FINAL_RELEASED" if current else "FINAL_RELEASED_CASE_ADVANCED"
        next_gate = (
            "ASSEMBLE_PACKAGE" if can_assemble else
            "PACKAGE_READ_AUTHORITY_REQUIRED" if not package_read_authorized else
            "PACKAGE_PROFILE_OR_CURRENT_CASE_REQUIRED"
        )
    elif approval is not None:
        status = "DOCUMENT_APPROVED" if current else "DOCUMENT_APPROVED_CASE_ADVANCED"
        next_gate = "REQUEST_FINAL_RELEASE" if can_release else "CURRENT_CASE_REQUIRED"
    elif current:
        status = "RENDERED_PENDING_HUMAN_APPROVAL"
        next_gate = "HUMAN_DOCUMENT_APPROVAL"
    else:
        status = "STALE_REQUIRES_REVALIDATION"
        next_gate = "REVALIDATE_AND_RENDER"
    return {
        "result_type": "FINALIZATION_CONTEXT",
        "render_id": str(render.id),
        "case_sequence": head.case_sequence,
        "render_sequence": render.committed_sequence,
        "artifacts": [
            {
                "format": item.artifact.format,
                "media_type": item.artifact.media_type,
                "byte_length": item.artifact.byte_length,
                "content_hash": item.artifact.content_hash,
            }
            for item in render.artifacts
        ],
        "draft_status": getattr(draft, "status", "UNKNOWN"),
        "current": current,
        "status": status,
        "next_gate": next_gate,
        "can_approve": can_approve,
        "can_release": can_release,
        "can_assemble": can_assemble,
        "approval": None if approval is None else {
            "committed_sequence": approval.committed_sequence,
            "approval_hash": approval.approval_hash,
            "actor_kind": approval.actor.kind,
        },
        "release": None if release is None else {
            "committed_sequence": release.committed_sequence,
            "eligibility": release.result.eligibility,
            "receipt_hash": digest(release.result.receipt),
        },
        "package": _package_summary(package),
        "package_configured": package_configured,
        "package_read_authorized": package_read_authorized,
    }


def _finalization_rationale(value):
    if (
        not isinstance(value, str)
        or not 8 <= len(value.strip()) <= 4000
        or any(ord(char) < 32 and char not in "\n\r\t" for char in value)
    ):
        raise EngineBoundaryError("COMPOSER_FINALIZATION_RATIONALE_REQUIRED")
    return value.strip()


def _finalization_command(operator, scope, token, payload, operation, head):
    render_id = _id(payload["render_id"])
    projection = _finalization_projection(operator, scope, token, render_id)
    package = _package_record(operator, scope, token, render_id) if projection.release is not None else None
    if operation == "ApproveFinalDocument":
        if projection.approval is not None or projection.release is not None or package is not None:
            raise EngineBoundaryError("COMPOSER_DOCUMENT_ALREADY_APPROVED")
        expected_sequence = projection.render.committed_sequence
    else:
        if projection.approval is None:
            raise EngineBoundaryError("COMPOSER_HUMAN_APPROVAL_REQUIRED")
        if operation == "RequestFinalRelease":
            if projection.release is not None or package is not None:
                raise EngineBoundaryError("COMPOSER_FINAL_RELEASE_ALREADY_EXISTS")
            expected_sequence = projection.approval.committed_sequence
        else:
            if projection.release is None:
                raise EngineBoundaryError("COMPOSER_FINAL_RELEASE_REQUIRED")
            if package is not None:
                raise EngineBoundaryError("COMPOSER_PACKAGE_ALREADY_EXISTS")
            expected_sequence = projection.release.committed_sequence
    draft, draft_ref = _current_finalization_draft(
        operator, scope, token, head, projection, expected_sequence
    )
    if operation == "AssembleFinalPackage":
        finalization = getattr(operator, "finalization", None)
        repository = getattr(finalization, "repository", None)
        if (
            finalization is None
            or getattr(finalization, "package_profile", None) is None
            or not bool(getattr(repository, "storage", False))
        ):
            raise EngineBoundaryError("COMPOSER_PACKAGE_STORAGE_NOT_CONFIGURED")
    request = FinalizationRequest.model_validate_json(json.dumps({
        "contract": "urn:lukart:work:FinalizationRequest:1.0.0",
        "operation": operation,
        "meta": _meta(scope, head.case_sequence, payload),
        "target": draft_ref.model_dump(mode="json"),
        "draft_hash": digest(draft),
        "snapshot_hash": draft.snapshot_hash,
        "render_id": render_id,
        "rationale": _finalization_rationale(payload["rationale"]),
    }, allow_nan=False)).model_dump(mode="json")
    result = _execute(operator, scope, "execute_finalization", request, token)
    if operation == "ApproveFinalDocument":
        updated = _finalization_projection(operator, scope, token, render_id)
        if updated.approval is None or updated.approval.committed_sequence != result.case_sequence:
            raise EngineBoundaryError("COMPOSER_APPROVAL_RECEIPT_NOT_VERIFIED")
        return {"result_type": "DOCUMENT_APPROVED", "render_id": render_id,
                "case_sequence": result.case_sequence}
    if operation == "RequestFinalRelease":
        updated = _finalization_projection(operator, scope, token, render_id)
        if (
            updated.release is None
            or updated.release.committed_sequence != result.case_sequence
            or updated.release.result.eligibility != "FINAL"
        ):
            raise EngineBoundaryError("COMPOSER_RELEASE_RECEIPT_NOT_VERIFIED")
        return {"result_type": "DOCUMENT_RELEASED", "render_id": render_id,
                "case_sequence": result.case_sequence, "eligibility": "FINAL"}
    package = _package_record(operator, scope, token, render_id)
    if package is None or package.committed_sequence != result.case_sequence:
        raise EngineBoundaryError("COMPOSER_PACKAGE_RECEIPT_NOT_VERIFIED")
    return {"result_type": "PACKAGE_ASSEMBLED", "render_id": render_id,
            "case_sequence": result.case_sequence, "package": _package_summary(package)}


def _read_package_member(operator, scope, token, render_id, member):
    if not isinstance(member, str) or member not in FINAL_PACKAGE_MEMBER_NAMES:
        raise EngineBoundaryError("COMPOSER_PACKAGE_MEMBER_NOT_ALLOWED")
    package = _package_record(operator, scope, token, render_id)
    if package is None:
        raise EngineBoundaryError("COMPOSER_PACKAGE_NOT_ASSEMBLED")
    result = operator.query_finalization({
        "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
        "operation": "ReadFinalPackageMember",
        "tenant_id": scope.tenant_id,
        "case_id": scope.case_id,
        "render_id": _id(render_id),
        "member": member,
    }, token)
    if not isinstance(result, bytes) or not result or len(result) > MAX_ARTIFACT_SIZE:
        raise EngineBoundaryError("COMPOSER_PACKAGE_MEMBER_READ_REJECTED")
    expected = next((item for item in package.members if item.name == member), None)
    if expected is None or len(result) != expected.byte_length or sha256(result).hexdigest() != expected.content_hash:
        raise EngineBoundaryError("COMPOSER_PACKAGE_MEMBER_INTEGRITY_FAILURE")
    return SavedArtifact(member, PACKAGE_MEDIA_TYPES[member], result, expected.content_hash)


def composer_action(operator, payload, token):
    if not isinstance(payload, dict):
        raise EngineBoundaryError("COMPOSER_REQUEST_INVALID")
    common = {"action", "expected_case_sequence"} | COMMAND_IDS
    command = {"action"} | COMMAND_IDS
    fields = {
        "composition_context": {"action"},
        "save_document_brief": common | {"form", "run_id"},
        "generate_document": common | {"form", "plan_id", "plan_revision", "profile"},
        "validate_document": common | {"draft_id", "draft_revision"},
        "render_document": common | {"draft_id", "draft_revision", "validation_run_id"},
        "finalization_context": {"action", "render_id"},
        "approve_document": command | {"render_id", "rationale"},
        "release_document": command | {"render_id", "rationale"},
        "assemble_package": command | {"render_id", "rationale"},
        "read_package_member": {"action", "render_id", "member"},
    }
    action = payload.get("action")
    if action not in fields or set(payload) != fields[action]:
        raise EngineBoundaryError("COMPOSER_ACTION_DENIED")
    scope = _scope(operator, token)  # Existing authoritative HUMAN/scope checks.
    if action == "read_package_member":
        return _read_package_member(operator, scope, token, payload["render_id"], payload["member"])
    head = _heads(operator, scope, token)
    if len(head.heads) > 1000:
        raise EngineBoundaryError("COMPOSER_CASE_LIMIT")
    if action == "finalization_context":
        return _finalization_context(operator, scope, token, payload["render_id"], head)
    finalization_operations = {
        "approve_document": "ApproveFinalDocument",
        "release_document": "RequestFinalRelease",
        "assemble_package": "AssembleFinalPackage",
    }
    if action in finalization_operations:
        return _finalization_command(operator, scope, token, payload, finalization_operations[action], head)
    profile = _profile(operator)
    if action == "composition_context":
        plans = []
        for reference in head.heads:
            if reference.kind != "DocumentPlan":
                continue
            plan = _revision(operator, scope, token, reference)
            if plan.status != "APPROVED":
                continue
            filing = _revision(operator, scope, token, plan.filing)
            if filing.document_type != profile.document_type:
                continue
            item = {"id": str(plan.id), "revision": plan.revision,
                    "label": "Zatwierdzony plan · " + plan.position_scope[:100]}
            if len(filing.authors) == 1:
                sender = _revision(operator, scope, token, filing.authors[0])
                recipient = _revision(operator, scope, token, filing.recipient)
                if all(p.status == "VERIFIED" and p.address is not None for p in (sender, recipient)):
                    item["form"] = {"description": plan.position_scope, "document_type": profile.document_type.id,
                        **{key: {"name": getattr(p, "display_name", getattr(p, "name", None)),
                                 "address": p.address.model_dump(mode="json")}
                           for key, p in (("sender", sender), ("recipient", recipient))}}
            plans.append(item)
            if len(plans) > 100:
                raise EngineBoundaryError("COMPOSER_PLAN_LIMIT")
        configured = getattr(operator.drafting, "profiles", {})
        return {"result_type": "COMPOSITION_CONTEXT", "case_sequence": head.case_sequence,
            "document_types": [{"id": profile.document_type.id, "label": profile.header}],
            "profiles": [name for name in ("QUICK", "PROFESSIONAL", "FORENSIC") if name in configured],
            "plans": plans, "required_gate": None if plans else "APPROVED_WORK_PLAN_REQUIRED"}
    if type(payload["expected_case_sequence"]) is not int or payload["expected_case_sequence"] != head.case_sequence:
        raise EngineBoundaryError("COMPOSER_CASE_STALE")
    meta = _meta(scope, head.case_sequence, payload)
    if action in ("save_document_brief", "generate_document"):
        form = validate_form(payload["form"])
        if form["document_type"] != profile.document_type.id:
            raise EngineBoundaryError("COMPOSER_DOCUMENT_TYPE_NOT_CONFIGURED")
    if action == "save_document_brief":
        # Persist the complete user input as an original source through WORK.
        # Never silently turn these declarations into VERIFIED parties/facts.
        body = json.dumps({"description": form["description"], "document_type": form["document_type"],
                           "sender": form["sender"], "recipient": form["recipient"]}, ensure_ascii=False, indent=2)
        result = upload_case_source(operator, {"action": "upload_source", "media_type": "text/plain",
            "content_base64": b64encode(body.encode("utf-8")).decode("ascii"),
            "expected_case_sequence": head.case_sequence, "run_id": _id(payload["run_id"]),
            **{name: meta[name] for name in COMMAND_IDS}}, token)
        return {"result_type": "DOCUMENT_BRIEF_SAVED", "native_result": result.model_dump(mode="json"),
                "next_gate": "REVIEW_SOURCE_AND_APPROVE_PLAN_IN_WORK", "human_approval_created": False}
    if action == "generate_document":
        plan_id = _id(payload["plan_id"])
        references = [r for r in head.heads if r.kind == "DocumentPlan" and str(r.id) == plan_id
                      and type(payload["plan_revision"]) is int and r.revision == payload["plan_revision"]]
        if len(references) != 1:
            raise EngineBoundaryError("COMPOSER_CURRENT_PLAN_REQUIRED")
        plan = _revision(operator, scope, token, references[0])
        filing = _revision(operator, scope, token, plan.filing)
        if plan.status != "APPROVED" or filing.document_type != profile.document_type or len(filing.authors) != 1:
            raise EngineBoundaryError("COMPOSER_APPROVED_PLAN_REQUIRED")
        sender = _revision(operator, scope, token, filing.authors[0])
        recipient = _revision(operator, scope, token, filing.recipient)
        for key, entity in (("sender", sender), ("recipient", recipient)):
            name = getattr(entity, "display_name", getattr(entity, "name", None))
            if entity.status != "VERIFIED" or entity.address is None or form[key] != {
                    "name": name, "address": entity.address.model_dump(mode="json")}:
                raise EngineBoundaryError("COMPOSER_VERIFIED_PARTIES_MUST_MATCH_FORM")
        if form["description"] != plan.position_scope:
            raise EngineBoundaryError("COMPOSER_DESCRIPTION_REQUIRES_REVIEWED_PLAN")
        if payload["profile"] not in operator.drafting.profiles:
            raise EngineBoundaryError("COMPOSER_DRAFTING_PROFILE_REQUIRED")
        request = {"operation": "GenerateDocument", "meta": meta,
            "document_type": profile.document_type.model_dump(mode="json"),
            "objective_ids": [str(r.id) for r in plan.objectives],
            "snapshot_id": str(plan.input_snapshot_id), "snapshot_hash": plan.input_snapshot_hash,
            "plan": references[0].model_dump(mode="json"), "profile": payload["profile"]}
        result = _execute(operator, scope, "execute_draft", request, token)
        refs = [r for r in result.refs if r.kind == "Draft"]
        if len(refs) != 1:
            raise EngineBoundaryError("COMPOSER_DRAFT_OUTPUT_REQUIRED")
        return {"result_type": "DOCUMENT_GENERATED", "draft": refs[0].model_dump(mode="json"),
                "case_sequence": result.case_sequence}
    projection = _open(operator, scope, token, _id(payload["draft_id"]), payload["draft_revision"])
    draft = projection.draft
    target = {"kind": "Draft", "id": str(draft.id), "revision": draft.revision}
    if action == "validate_document":
        request = {"contract": "urn:lukart:work:ValidationRequest:1.0.0", "operation": "ValidateDraft",
            "meta": meta, "target": target, "draft_hash": projection.draft_hash,
            "snapshot_hash": draft.snapshot_hash, "validation_policy": validation_pin().model_dump(mode="json"),
            "rationale": "Sprawdzenie projektu z interfejsu Moja sprawa"}
        result = _execute(operator, scope, "execute_validation", request, token)
        refs = [r for r in result.refs if r.kind == "Draft"]
        if len(refs) != 1:
            raise EngineBoundaryError("COMPOSER_VALIDATION_OUTPUT_REQUIRED")
        return {"result_type": "DOCUMENT_VALIDATED", "draft": refs[0].model_dump(mode="json"),
                "validation_run_id": str(uuid5(UUID(meta["command_id"]), "validation-run")),
                "case_sequence": result.case_sequence, "render_authorization": "CHECKED_BY_WORK_ON_RENDER"}
    request = {"contract": "urn:lukart:work:FinalizationRequest:1.0.0", "operation": "RenderDraft",
        "meta": meta, "target": target, "draft_hash": projection.draft_hash,
        "snapshot_hash": draft.snapshot_hash, "validation_run_id": _id(payload["validation_run_id"]),
        "semantic_profile": semantic_profile_pin(profile).model_dump(mode="json"),
        "rationale": "Przygotowanie DOCX i PDF w tej samej sprawie"}
    result = _execute(operator, scope, "execute_finalization", request, token)
    return {"result_type": "DOCUMENT_RENDERED", "render_id": str(uuid5(UUID(meta["command_id"]), "persisted-render")),
            "case_sequence": result.case_sequence, "final_approval_created": False}
