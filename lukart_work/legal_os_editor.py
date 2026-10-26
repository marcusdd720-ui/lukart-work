"""Session-bound document editor via existing WORK GetDraftForEditing / AmendDraft.

No parallel document storage, no auto-approval, no render, no AI authority.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from lukart_work.contracts.messages import CaseHeadResult, CommandResult
from lukart_work.domain.models import Ref
from lukart_work.drafting.amendments import DraftEditorProjection
from lukart_work.embedded_document_engine import EmbeddedDocumentEngine, CaseScope, EngineBoundaryError


def _id(value):
    if not isinstance(value, str):
        raise EngineBoundaryError("EDITOR_INVALID_ID")
    try:
        identifier = UUID(value)
        if not identifier.int or str(identifier) != value.lower():
            raise ValueError("noncanonical")
        return str(identifier)
    except (ValueError, TypeError) as exc:
        raise EngineBoundaryError("EDITOR_INVALID_ID") from exc


def _scope(operator, token):
    with operator.core.authority.session(token) as principal:
        if principal.actor.kind != "HUMAN":
            raise EngineBoundaryError("EDITOR_HUMAN_REQUIRED")
        for action in ("GetCaseHead", "GetRevision"):
            principal.require(principal.tenant_id, principal.case_id, action)
        return CaseScope(str(principal.tenant_id), str(principal.case_id))


def _heads(operator, scope, token):
    head = EmbeddedDocumentEngine(operator).open_case(scope, token=token)
    if not isinstance(head, CaseHeadResult):
        raise EngineBoundaryError("EDITOR_CASE_NOT_FOUND")
    return head


def _open(operator, scope, token, draft_id, revision):
    head = _heads(operator, scope, token)
    if type(revision) is not int or revision < 1:
        raise EngineBoundaryError("EDITOR_REVISION_INVALID")
    matching = [r for r in head.heads if r.kind == "Draft"
                and str(r.id) == draft_id and r.revision == revision]
    if len(matching) != 1:
        raise EngineBoundaryError("EDITOR_DRAFT_NOT_CURRENT")
    result = operator.query_draft({
        "contract": "urn:lukart:work:DraftEditorQuery:1.0.0",
        "operation": "GetDraftForEditing",
        "tenant_id": scope.tenant_id, "case_id": scope.case_id,
        "draft": {"kind": "Draft", "id": draft_id, "revision": revision},
    }, token)
    if not isinstance(result, DraftEditorProjection):
        raise EngineBoundaryError("EDITOR_READ_REJECTED")
    if (str(result.draft.tenant_id) != scope.tenant_id
            or str(result.draft.case_id) != scope.case_id
            or str(result.draft.id) != draft_id
            or result.draft.revision != revision
            or result.case_sequence != head.case_sequence):
        raise EngineBoundaryError("EDITOR_SCOPE_OR_REVISION_MISMATCH")
    return result


def edit_action(operator: Any, payload: dict, token: str):
    if not isinstance(payload, dict):
        raise EngineBoundaryError("EDITOR_REQUEST_INVALID")
    action = payload.get("action")
    allowed = {
        "list_drafts": {"action"},
        "open_draft": {"action", "draft_id", "revision"},
        "amend_draft": {"action", "draft_id", "revision", "draft_hash", "expected_case_sequence",
                        "edits", "rationale", "command_id", "idempotency_key", "correlation_id"},
    }
    if action not in allowed or set(payload) != allowed[action]:
        raise EngineBoundaryError("EDITOR_ACTION_DENIED")
    scope = _scope(operator, token)
    if action == "list_drafts":
        head = _heads(operator, scope, token)
        return {"result_type": "DRAFT_LIST", "case_sequence": head.case_sequence,
                "drafts": [{"id": str(r.id), "revision": r.revision}
                           for r in head.heads if r.kind == "Draft"][:100]}
    draft_id = _id(payload["draft_id"])
    revision = payload["revision"]
    projection = _open(operator, scope, token, draft_id, revision)
    if action == "open_draft":
        return {
            "result_type": "DRAFT_FOR_EDITING",
            "draft_id": draft_id,
            "revision": revision,
            "draft_hash": projection.draft_hash,
            "case_sequence": projection.case_sequence,
            "editable": projection.editable,
            "status": projection.draft.status,
            "sections": [{
                "section_id": str(section.section.id),
                "statements": [{
                    "statement_id": str(statement.id),
                    "text": statement.text,
                    "statement_type": statement.statement_type
                } for statement in section.statements]
            } for section in projection.draft.sections],
        }
    with operator.core.authority.session(token) as principal:
        principal.require(principal.tenant_id, principal.case_id, "AmendDraft")
    if not projection.editable or payload["draft_hash"] != projection.draft_hash:
        raise EngineBoundaryError("EDITOR_LOCKED_OR_STALE")
    if type(payload["expected_case_sequence"]) is not int or (
        payload["expected_case_sequence"] != projection.case_sequence
    ):
        raise EngineBoundaryError("EDITOR_CASE_STALE")
    rationale = payload["rationale"]
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
        raise EngineBoundaryError("EDITOR_RATIONALE_REQUIRED")
    changes = payload["edits"]
    if not isinstance(changes, list) or not 1 <= len(changes) <= 1000:
        raise EngineBoundaryError("EDITOR_EDITS_REQUIRED")
    available = {str(st.id): st.text for sec in projection.draft.sections for st in sec.statements}
    edits, seen = [], set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"statement_id", "text"}:
            raise EngineBoundaryError("EDITOR_EDIT_INVALID")
        statement_id = _id(change["statement_id"])
        text = change["text"]
        if (statement_id not in available or statement_id in seen
                or not isinstance(text, str) or not text.strip()
                or len(text) > 100000):
            raise EngineBoundaryError("EDITOR_EDIT_INVALID")
        seen.add(statement_id)
        if text != available[statement_id]:
            edits.append({"statement_id": statement_id, "text": text})
    if not edits:
        raise EngineBoundaryError("EDITOR_NO_CHANGE")
    ids = [_id(payload[name]) for name in ("command_id", "idempotency_key", "correlation_id")]
    if len(set(ids)) != 3:
        raise EngineBoundaryError("EDITOR_COMMAND_ID_CONFLICT")
    request = {
        "contract": "urn:lukart:work:CoreRequest:1.0.0",
        "operation": "AmendDraft",
        "meta": {
            "command_id": ids[0], "idempotency_key": ids[1], "correlation_id": ids[2],
            "tenant_id": scope.tenant_id, "case_id": scope.case_id,
            "expected_case_sequence": projection.case_sequence
        },
        "target": {"kind": "Draft", "id": draft_id, "revision": revision},
        "data": {"contract": "urn:lukart:work:AmendDraft:1.0.0",
                 "draft_hash": projection.draft_hash, "edits": edits},
        "rationale": rationale.strip()
    }
    result = operator.execute_core(request, token)
    if not isinstance(result, CommandResult) or result.state not in ("APPLIED", "REPLAYED"):
        raise EngineBoundaryError("EDITOR_WORK_REJECTED")
    outputs = tuple(ref for ref in result.refs if ref.kind == "Draft")
    if len(outputs) != 1:
        raise EngineBoundaryError("EDITOR_OUTPUT_MISSING")
    return {
        "result_type": "DRAFT_AMENDED",
        "state": result.state,
        "case_sequence": result.case_sequence,
        "draft": outputs[0].model_dump(mode="json"),
        "approval": "NOT_GRANTED",
        "render": "NOT_STARTED",
    }
