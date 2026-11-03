"""One-window document preparation using existing WORK services and gates.

No drafting/renderer replacement, automatic HUMAN decision or second case store.
An input brief remains source material until independently admitted in WORK.
"""
import json
from base64 import b64encode
from uuid import UUID, uuid5

from lukart_work.contracts.messages import CommandResult, RevisionResult
from lukart_work.domain.models import Address
from lukart_work.embedded_document_engine import (
    EmbeddedDocumentEngine,
    EngineBoundaryError,
    make_confirmation,
)
from lukart_work.finalization.contracts import semantic_profile_pin
from lukart_work.legal_os_editor import _heads, _id, _open, _scope
from lukart_work.legal_os_intake import upload_case_source
from lukart_work.validation.policy import validation_pin

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


def composer_action(operator, payload, token):
    if not isinstance(payload, dict):
        raise EngineBoundaryError("COMPOSER_REQUEST_INVALID")
    common = {"action", "expected_case_sequence"} | COMMAND_IDS
    fields = {
        "composition_context": {"action"},
        "save_document_brief": common | {"form", "run_id"},
        "generate_document": common | {"form", "plan_id", "plan_revision", "profile"},
        "validate_document": common | {"draft_id", "draft_revision"},
        "render_document": common | {"draft_id", "draft_revision", "validation_run_id"},
    }
    action = payload.get("action")
    if action not in fields or set(payload) != fields[action]:
        raise EngineBoundaryError("COMPOSER_ACTION_DENIED")
    scope = _scope(operator, token)  # Existing authoritative HUMAN/scope checks.
    head = _heads(operator, scope, token)
    profile = _profile(operator)
    if len(head.heads) > 1000:
        raise EngineBoundaryError("COMPOSER_CASE_LIMIT")
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
