"""Session-bound intake for the unified LEGAL OS case view.

Reuses WORK RegisterSource + IngestionService; never auto-accepts OCR candidates.
No second case store, fake HUMAN approvals, network provider, or original edits.
"""
from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from typing import Any
from uuid import UUID

from lukart_work.contracts.messages import CaseHeadResult, RevisionResult, DomainError
from lukart_work.embedded_document_engine import EmbeddedDocumentEngine, CaseScope, EngineBoundaryError

MAX_CASE_FILE_BYTES = 700 * 1024
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FORMATS = frozenset({
    "application/pdf", "image/png", "image/jpeg", "image/tiff",
    DOCX_MIME, "text/plain",
})


def _uuid_nonzero(raw: Any) -> str:
    if not isinstance(raw, str):
        raise EngineBoundaryError("UPLOAD_IDENTIFIERS_INVALID")
    try:
        parsed = UUID(raw)
    except ValueError as exc:
        raise EngineBoundaryError("UPLOAD_IDENTIFIERS_INVALID") from exc
    if parsed.int == 0 or str(parsed) != raw.lower():
        raise EngineBoundaryError("UPLOAD_IDENTIFIERS_INVALID")
    return str(parsed)


def _validate_content(media_type: Any, encoded: Any) -> None:
    if media_type not in FORMATS or not isinstance(encoded, str):
        raise EngineBoundaryError("UPLOAD_FORMAT_NOT_SUPPORTED")
    if not encoded or len(encoded) > ((MAX_CASE_FILE_BYTES + 2) // 3) * 4:
        raise EngineBoundaryError("UPLOAD_SIZE_LIMIT")
    try:
        data = b64decode(encoded, validate=True)
    except (Base64Error, ValueError) as exc:
        raise EngineBoundaryError("UPLOAD_ENCODING_INVALID") from exc
    if not data or len(data) > MAX_CASE_FILE_BYTES:
        raise EngineBoundaryError("UPLOAD_SIZE_LIMIT")
    signatures = {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/tiff": data.startswith((b"II*\x00", b"MM\x00*")),
        DOCX_MIME: data.startswith(b"PK\x03\x04"),
    }
    if media_type in signatures and not signatures[media_type]:
        raise EngineBoundaryError("UPLOAD_CONTENT_TYPE_MISMATCH")
    if media_type == "text/plain":
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EngineBoundaryError("UPLOAD_TEXT_ENCODING_INVALID") from exc
        if any(ord(ch) < 32 and ch not in "\r\n\t\f" for ch in content):
            raise EngineBoundaryError("UPLOAD_BINARY_TEXT")


def upload_case_source(operator: Any, payload: dict[str, Any], token: str):
    """Explicit user click -> exact native WORK source registration + OCR.

    Client supplies only upload bytes, MIME and command identifiers. Scope and
    retention policy come from live authenticated WORK; no HTTP-supplied HUMAN.
    A failed response MUST NOT be retried automatically: command IDs are kept
    client-side until user explicitly decides to retry.
    """
    expected = {
        "action", "media_type", "content_base64", "expected_case_sequence",
        "command_id", "idempotency_key", "correlation_id", "run_id",
    }
    if not isinstance(payload, dict) or set(payload) != expected or payload.get("action") != "upload_source":
        raise EngineBoundaryError("UPLOAD_REQUEST_INVALID")
    _validate_content(payload["media_type"], payload["content_base64"])
    seq = payload["expected_case_sequence"]
    if type(seq) is not int or seq < 1:
        raise EngineBoundaryError("UPLOAD_SEQUENCE_INVALID")
    ids = {key: _uuid_nonzero(payload[key]) for key in (
        "command_id", "idempotency_key", "correlation_id", "run_id"
    )}
    if len(set(ids.values())) != 4:
        raise EngineBoundaryError("UPLOAD_DUPLICATE_IDENTIFIERS")

    with operator.core.authority.session(token) as principal:
        if principal.actor.kind != "HUMAN":
            raise EngineBoundaryError("UPLOAD_HUMAN_REQUIRED")
        for action in ("GetCaseHead", "GetRevision", "RegisterSource", "IngestSource"):
            principal.require(principal.tenant_id, principal.case_id, action)
        scope = CaseScope(str(principal.tenant_id), str(principal.case_id))
        engine = EmbeddedDocumentEngine(operator)
        head = engine.open_case(scope, token=token)
        if not isinstance(head, CaseHeadResult):
            raise EngineBoundaryError("UPLOAD_CASE_HEAD_NOT_VERIFIED")
        if head.case_sequence != seq:
            raise EngineBoundaryError("UPLOAD_STALE_SEQUENCE")
        case_refs = tuple(ref for ref in head.heads if
                          ref.kind == "Case" and str(ref.id) == scope.case_id)
        if len(case_refs) != 1:
            raise EngineBoundaryError("UPLOAD_CASE_REFERENCE_INVALID")
        revision = operator.query_core({
            "contract": "urn:lukart:work:CoreQuery:1.0.0",
            "operation": "GetRevision",
            "tenant_id": scope.tenant_id, "case_id": scope.case_id,
            "target": case_refs[0].model_dump(mode="json"),
        }, token)
        if not isinstance(revision, RevisionResult):
            raise EngineBoundaryError("UPLOAD_CASE_REVISION_NOT_VERIFIED")
        case = revision.entity
        if (case.kind != "Case" or str(case.id) != scope.case_id
                or case.revision != case_refs[0].revision or case.status != "OPEN"):
            raise EngineBoundaryError("UPLOAD_CASE_NOT_OPEN")
        request = {
            "operation": "UploadAndIngest",
            "run_id": ids["run_id"],
            "request": {
                "contract": "urn:lukart:work:CoreRequest:1.0.0",
                "operation": "RegisterSource",
                "meta": {
                    "command_id": ids["command_id"],
                    "tenant_id": scope.tenant_id,
                    "case_id": scope.case_id,
                    "idempotency_key": ids["idempotency_key"],
                    "correlation_id": ids["correlation_id"],
                    "expected_case_sequence": seq,
                },
                "data": {
                    "content_base64": payload["content_base64"],
                    "media_type": payload["media_type"],
                    "retention_policy": case.retention_policy.model_dump(mode="json"),
                },
                "rationale": "Jawne dodanie materiału do sprawy w LEGAL OS",
            },
        }
        result = operator.upload_source(request, token)
        if isinstance(result, DomainError):
            raise EngineBoundaryError("UPLOAD_WORK_DENIED")
        # Do not label registration or OCR as a legally accepted Fact/Evidence.
        return result
