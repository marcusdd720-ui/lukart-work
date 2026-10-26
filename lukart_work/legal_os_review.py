"""Session-scoped HUMAN OCR candidate review for unified LUKART LEGAL OS.

Composes existing IngestionService + FactEvidenceService; does not reinterpret
an OCR hypothesis as a confirmed fact or create secondary evidence storage.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import UUID

from lukart_work.contracts.messages import CaseHeadResult, DomainError, CommandResult
from lukart_work.embedded_document_engine import CaseScope, EmbeddedDocumentEngine, EngineBoundaryError
from lukart_work.ingestion.models import IngestionResult
from lukart_work.facts.contracts import FactEvidenceMatrix
from lukart_work.validation.rules import digest

ACTIONS = {"review_context", "review_candidate"}
ID_FIELDS = ("source_id", "run_id")
COMMAND_IDS = ("command_id", "idempotency_key", "correlation_id")
REVIEW_LIMIT = 4000


def _uuid(value: Any) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError("not a string")
        parsed = UUID(value)
        if not parsed.int or str(parsed) != value.lower():
            raise ValueError("noncanonical uuid")
        return str(parsed)
    except (ValueError, TypeError) as exc:
        raise EngineBoundaryError("REVIEW_INVALID_IDENTIFIER") from exc


def _strings(payload, *fields):
    for key in fields:
        if not isinstance(payload[key], str) or not payload[key].strip() or len(payload[key]) > 4000:
            raise EngineBoundaryError("REVIEW_TEXT_INVALID")


def review_action(operator: Any, payload: dict[str, Any], token: str):
    context_shape = {"action", *ID_FIELDS}
    decision_shape = context_shape | {
        "candidate_index", "expected_case_sequence", "disposition",
        "statement", "description", "rationale", *COMMAND_IDS
    }
    if not isinstance(payload, dict) or payload.get("action") not in ACTIONS:
        raise EngineBoundaryError("REVIEW_ACTION_INVALID")
    allowed = context_shape if payload["action"] == "review_context" else decision_shape
    if set(payload) != allowed:
        raise EngineBoundaryError("REVIEW_SHAPE_INVALID")
    source_id, run_id = (_uuid(payload[key]) for key in ID_FIELDS)

    with operator.core.authority.session(token) as principal:
        if principal.actor.kind != "HUMAN":
            raise EngineBoundaryError("REVIEW_HUMAN_REQUIRED")
        tenant_id, case_id = principal.tenant_id, principal.case_id
        rights = ["GetCaseHead", "ReadIngestion", "GetFactEvidenceMatrix"]
        if payload["action"] == "review_candidate":
            rights.append("ReviewCandidate")
        for action in rights:
            principal.require(tenant_id, case_id, action)
        scope = CaseScope(str(tenant_id), str(case_id))

        extraction = operator.query_ingestion({
            "operation": "ReadIngestion",
            "tenant_id": scope.tenant_id, "case_id": scope.case_id,
            "source_id": source_id, "run_id": run_id,
        }, token)
        if (not isinstance(extraction, IngestionResult)
                or str(extraction.tenant_id) != scope.tenant_id
                or str(extraction.case_id) != scope.case_id
                or str(extraction.source_id) != source_id
                or str(extraction.run_id) != run_id
                or extraction.body.status != "EXTRACTED"):
            raise EngineBoundaryError("REVIEW_SOURCE_UNAVAILABLE")

        matrix = operator.query_fact_evidence({
            "contract": "urn:lukart:work:FactEvidenceQuery:1.0.0",
            "operation": "GetFactEvidenceMatrix",
            "tenant_id": scope.tenant_id, "case_id": scope.case_id,
        }, token)
        if not isinstance(matrix, FactEvidenceMatrix) or (
            matrix.tenant_id != tenant_id or matrix.case_id != case_id
        ):
            raise EngineBoundaryError("REVIEW_MATRIX_UNAVAILABLE")

        latest = {}
        for record in matrix.candidate_reviews:
            if str(record.run_id) == run_id and str(record.source_id) == source_id:
                index = record.candidate_index
                if index not in latest or record.revision > latest[index].revision:
                    latest[index] = record

        if payload["action"] == "review_context":
            candidates = tuple({
                "index": i,
                "kind": candidate.kind,
                "quote": candidate.quote[:500],
                "review_revision": latest[i].revision if i in latest else 0,
                "review_status": latest[i].disposition if i in latest else "PENDING",
            } for i, candidate in enumerate(extraction.body.candidates)
                if candidate.kind in ("FACT", "EVIDENCE"))
            return {
                "result_type": "REVIEW_CONTEXT",
                "source_id": source_id,
                "run_id": run_id,
                "case_sequence": matrix.case_sequence,
                "candidates": candidates[:REVIEW_LIMIT],
            }

        index = payload["candidate_index"]
        expected_sequence = payload["expected_case_sequence"]
        if (type(index) is not int or type(expected_sequence) is not int
                or index < 0 or expected_sequence != matrix.case_sequence
                or index >= len(extraction.body.candidates)):
            raise EngineBoundaryError("REVIEW_STALE_OR_INVALID")
        candidate = extraction.body.candidates[index]
        if candidate.kind not in ("FACT", "EVIDENCE"):
            raise EngineBoundaryError("REVIEW_NOT_FACT_EVIDENCE")
        if index in latest and latest[index].disposition == "ADMIT":
            raise EngineBoundaryError("REVIEW_ALREADY_ADMITTED")
        disposition = payload["disposition"]
        if disposition not in ("ADMIT", "REJECT"):
            raise EngineBoundaryError("REVIEW_DISPOSITION_INVALID")
        _strings(payload, "rationale")
        statement, description = payload["statement"], payload["description"]
        if not isinstance(statement, str) or not isinstance(description, str):
            raise EngineBoundaryError("REVIEW_TEXT_INVALID")
        data = {
            "source_id": source_id,
            "run_id": run_id,
            "result_hash": digest(extraction),
            "candidate_index": index,
            "expected_review_revision": latest[index].revision if index in latest else 0,
            "disposition": disposition,
        }
        if disposition == "ADMIT":
            _strings(payload, "description")
            data["description"] = description.strip()
            if candidate.kind == "FACT":
                _strings(payload, "statement")
                data["statement"] = statement.strip()
            elif statement.strip():
                raise EngineBoundaryError("REVIEW_EVIDENCE_STATEMENT_INVALID")
        elif statement.strip() or description.strip():
            raise EngineBoundaryError("REVIEW_REJECT_FIELDS_INVALID")

        ids = {name: _uuid(payload[name]) for name in COMMAND_IDS}
        if len(set(ids.values())) != 3:
            raise EngineBoundaryError("REVIEW_DUPLICATE_COMMAND_IDS")

        # Validate current CASE head just before WORK CAS; a race is still
        # independently rejected by the native CommandService.
        head = EmbeddedDocumentEngine(operator).open_case(scope, token=token)
        if not isinstance(head, CaseHeadResult) or head.case_sequence != expected_sequence:
            raise EngineBoundaryError("REVIEW_CASE_STALE")
        request = {
            "contract": "urn:lukart:work:FactEvidenceRequest:1.0.0",
            "operation": "ReviewCandidate",
            "meta": {
                "command_id": ids["command_id"],
                "idempotency_key": ids["idempotency_key"],
                "correlation_id": ids["correlation_id"],
                "tenant_id": scope.tenant_id,
                "case_id": scope.case_id,
                "expected_case_sequence": expected_sequence,
            },
            "data": data,
            "rationale": payload["rationale"].strip(),
        }
        result = operator.execute_fact_evidence(request, token)
        if not isinstance(result, CommandResult) or result.state not in ("APPLIED", "REPLAYED"):
            raise EngineBoundaryError("REVIEW_WORK_REJECTED")
        return {
            "result_type": "REVIEW_RECEIPT",
            "state": result.state,
            "case_sequence": result.case_sequence,
            "disposition": disposition,
            "candidate_index": index,
            "candidate_kind": candidate.kind,
        }
