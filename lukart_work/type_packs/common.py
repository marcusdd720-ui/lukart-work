from __future__ import annotations

from datetime import date
from hashlib import sha256
from json import dumps
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


ADMISSION_STATUS = "NOT_ADMITTED"
REQUIRED_HUMAN_GATES = (
    "HG-01",
    "HG-02",
    "HG-03",
    "HG-04",
    "HG-05",
    "HG-06",
    "HG-07",
    "HG-08",
    "HG-09",
)
FORBIDDEN_AUTOMATIONS = (
    "automatic_statutory_interest",
    "automatic_limitation_period",
    "automatic_delivery_effectiveness",
    "automatic_legal_truth_certification",
    "automatic_signature",
    "automatic_external_filing",
)


def canonical_pin(payload: dict[str, Any]) -> str:
    encoded = dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def strict_iso_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("date must be YYYY-MM-DD")
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid ISO calendar date") from exc
    return value


class CommonPreLitigationEnvelope(BaseModel):
    """Shared fail-closed input envelope for the three LW-PB-01 type packs."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    case_id: UUID
    human_capability_pin: str
    retention_policy_pin: str
    pl_jurisdiction_confirmation: Literal["PL"]
    evaluation_date_iso: str
    evaluation_timezone: str

    sender_name: str
    sender_role: str
    sender_address: str
    recipient_name: str
    recipient_role: str
    recipient_address: str
    document_place: str
    document_date_iso: str
    case_reference: str | None = None
    representative_authority_ref: str | None = None

    source_refs: tuple[str, ...]
    accepted_evidence_refs: tuple[str, ...]
    confirmed_fact_refs: tuple[str, ...]
    strategy_request_approval_ref: str
    legal_source_refs: tuple[str, ...]
    procedural_coverage_ref: str

    accepted_snapshot_id: str
    accepted_snapshot_hash: str
    approved_plan_ref: str
    approved_plan_hash: str

    prompt_pin: str
    generator_pin: str
    model_provider_pin: str
    generator_parameters_hash: str
    validation_policy_pin: str
    render_profile_pin: str

    attachment_inventory: tuple[str, ...]
    signature_party: str

    @field_validator(
        "human_capability_pin",
        "retention_policy_pin",
        "evaluation_date_iso",
        "evaluation_timezone",
        "sender_name",
        "sender_role",
        "sender_address",
        "recipient_name",
        "recipient_role",
        "recipient_address",
        "document_place",
        "document_date_iso",
        "strategy_request_approval_ref",
        "procedural_coverage_ref",
        "accepted_snapshot_id",
        "accepted_snapshot_hash",
        "approved_plan_ref",
        "approved_plan_hash",
        "prompt_pin",
        "generator_pin",
        "model_provider_pin",
        "generator_parameters_hash",
        "validation_policy_pin",
        "render_profile_pin",
        "signature_party",
    )
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text value must not be blank")
        return value

    @field_validator("evaluation_date_iso", "document_date_iso")
    @classmethod
    def dates_must_be_valid(cls, value: str) -> str:
        return strict_iso_date(value)

    @field_validator("evaluation_timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("unknown evaluation time zone") from exc
        return value

    @field_validator(
        "source_refs",
        "accepted_evidence_refs",
        "confirmed_fact_refs",
        "legal_source_refs",
    )
    @classmethod
    def non_empty_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("required reference collection must be non-empty")
        return value

    @model_validator(mode="after")
    def fail_closed_unknowns(self) -> "CommonPreLitigationEnvelope":
        if self.procedural_coverage_ref.upper() in {"UNKNOWN", "NOT_RUN", "MISSING"}:
            raise ValueError("procedural coverage must be explicitly admitted")
        return self
