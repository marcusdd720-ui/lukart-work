"""LUKART LEGAL OS: in-process, UI-free facade for the existing WORK operator.

This module deliberately never provisions a HUMAN actor, bypasses a domain gate,
creates a second case store, or runs the legacy operator HTML screen.
The trusted LEGAL OS host supplies the existing GeneratorPismOperator instance.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from io import BytesIO
from json import dumps
from typing import Any, Mapping
from uuid import UUID
from zipfile import BadZipFile, ZipFile


READ_CASE_CONTRACT = "urn:lukart:work:CoreQuery:1.0.0"
READ_ARTIFACT_CONTRACT = "urn:lukart:work:FinalizationQuery:1.0.0"
# Only existing WORK operations are delegated; no approvals are manufactured.
HUMAN_COMMAND_ROUTES = frozenset({
    "execute_core", "execute_fact_evidence", "execute_procedural",
    "execute_plan", "execute_draft", "execute_validation",
    "execute_finalization", "upload_source",
})
MAX_COMMAND_SIZE = 1024 * 1024
MAX_ARTIFACT_SIZE = 32 * 1024 * 1024


class EngineBoundaryError(ValueError):
    """Stable, non-sensitive error code for the trusted host UI."""


def _uuid(value: str | UUID) -> str:
    try:
        result = UUID(str(value))
        if result.int == 0:
            raise ValueError("nil")
        return str(result)
    except (TypeError, ValueError, AttributeError) as exc:
        raise EngineBoundaryError("INVALID_CASE_IDENTITY") from exc


def _token(token: str) -> str:
    if not isinstance(token, str) or not token.strip():
        raise EngineBoundaryError("AUTH_REQUIRED")
    return token


def _canonical_request(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, dict):
        raise EngineBoundaryError("REQUEST_OBJECT_REQUIRED")
    try:
        data = dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EngineBoundaryError("INVALID_COMMAND") from exc
    if not data or len(data) > MAX_COMMAND_SIZE:
        raise EngineBoundaryError("COMMAND_SIZE_LIMIT")
    return data


@dataclass(frozen=True)
class CaseScope:
    tenant_id: str
    case_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _uuid(self.tenant_id))
        object.__setattr__(self, "case_id", _uuid(self.case_id))


@dataclass(frozen=True)
class HumanCommandConfirmation:
    """Exact UI intention, NOT an authority token or stored HUMAN decision.

    The trusted LEGAL OS host must create this only after an explicit owner action.
    WORK remains the sole authority for authenticating the actor and validating
    stored HUMAN decisions, scopes, revisions and idempotency.
    """
    scope: CaseScope
    route: str
    request_sha256: str


def make_confirmation(scope: CaseScope, route: str, request: dict[str, Any]) -> HumanCommandConfirmation:
    """Call from trusted UI action handler, not from an automated drafting agent."""
    if route not in HUMAN_COMMAND_ROUTES:
        raise EngineBoundaryError("COMMAND_ROUTE_NOT_ALLOWED")
    return HumanCommandConfirmation(scope, route, sha256(_canonical_request(request)).hexdigest())


@dataclass(frozen=True)
class SavedArtifact:
    """Exact previously persisted bytes, never a new render."""
    filename: str
    mime_type: str
    data: bytes
    sha256: str


class EmbeddedDocumentEngine:
    """Private application-service boundary, invoked inside the LEGAL OS host.

    The supplied operator must originate from trusted WORK host configuration.
    Do not expose these Python methods as raw unauthenticated HTTP routes.
    """

    def __init__(self, operator: Any):
        required = ("query_core", "query_finalization", *HUMAN_COMMAND_ROUTES)
        if operator is None or any(not callable(getattr(operator, method, None)) for method in required):
            raise EngineBoundaryError("TRUSTED_WORK_OPERATOR_REQUIRED")
        self._operator = operator

    def open_case(self, scope: CaseScope, *, token: str) -> Any:
        """Read canonical WORK case head; no parallel LEGAL OS case state."""
        request = {
            "contract": READ_CASE_CONTRACT,
            "operation": "GetCaseHead",
            "tenant_id": scope.tenant_id,
            "case_id": scope.case_id,
        }
        return self._operator.query_core(request, _token(token))

    def get_render(self, scope: CaseScope, render_id: str | UUID, *, token: str) -> Any:
        """Read existing renderer status, never create an artifact."""
        return self._operator.query_finalization({
            "contract": READ_ARTIFACT_CONTRACT,
            "operation": "GetFinalization",
            "tenant_id": scope.tenant_id,
            "case_id": scope.case_id,
            "render_id": _uuid(render_id),
        }, _token(token))

    def download_saved(self, scope: CaseScope, render_id: str | UUID,
                       file_format: str, *, token: str) -> SavedArtifact:
        """Retrieve WORK-authorized immutable PDF/DOCX; never re-render."""
        if file_format not in ("PDF", "DOCX"):
            raise EngineBoundaryError("UNSUPPORTED_EXPORT_FORMAT")
        result = self._operator.query_finalization({
            "contract": READ_ARTIFACT_CONTRACT,
            "operation": "ReadFinalArtifact",
            "tenant_id": scope.tenant_id,
            "case_id": scope.case_id,
            "render_id": _uuid(render_id),
            "format": file_format,
        }, _token(token))
        if not isinstance(result, bytes):
            # The WORK DomainError is a rejection, not an empty or successful file.
            raise EngineBoundaryError("WORK_ARTIFACT_READ_REJECTED")
        if not result or len(result) > MAX_ARTIFACT_SIZE:
            raise EngineBoundaryError("ARTIFACT_SIZE_LIMIT")
        if file_format == "PDF":
            if not result.startswith(b"%PDF-"):
                raise EngineBoundaryError("PDF_SIGNATURE_INVALID")
            mime = "application/pdf"
        else:
            if not result.startswith(b"PK\x03\x04"):
                raise EngineBoundaryError("DOCX_SIGNATURE_INVALID")
            try:
                with ZipFile(BytesIO(result)) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise EngineBoundaryError("DOCX_STRUCTURE_INVALID")
            except BadZipFile as exc:
                raise EngineBoundaryError("DOCX_STRUCTURE_INVALID") from exc
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return SavedArtifact("dokument." + file_format.lower(), mime, result, sha256(result).hexdigest())

    def execute_confirmed(self, scope: CaseScope, route: str, request: dict[str, Any],
                          confirmation: HumanCommandConfirmation, *, token: str) -> Any:
        """Forward EXACT owner-reviewed commands to existing WORK gates.

        Exact intent is checked twice: confirmation hash and request tenant/case.
        WORK then independently enforces real principal/HUMAN, sequence, approvals,
        business constraints and transactional replay. Do not auto-retry writes.
        """
        if route not in HUMAN_COMMAND_ROUTES:
            raise EngineBoundaryError("COMMAND_ROUTE_NOT_ALLOWED")
        if not isinstance(confirmation, HumanCommandConfirmation) or (
            confirmation.scope != scope or confirmation.route != route
        ):
            raise EngineBoundaryError("CONFIRMATION_SCOPE_MISMATCH")
        raw = _canonical_request(request)
        if not compare_digest(sha256(raw).hexdigest(), confirmation.request_sha256):
            raise EngineBoundaryError("CONFIRMATION_STALE")
        # upload_source wraps a complete CoreRequest one level deeper.
        meta = request.get("request", {}).get("meta") if route == "upload_source" else request.get("meta")
        if not isinstance(meta, dict):
            raise EngineBoundaryError("COMMAND_SCOPE_REQUIRED")
        if (_uuid(meta.get("tenant_id")), _uuid(meta.get("case_id"))) != (
            scope.tenant_id, scope.case_id
        ):
            raise EngineBoundaryError("COMMAND_SCOPE_MISMATCH")
        return getattr(self._operator, route)(deepcopy(request), _token(token))
