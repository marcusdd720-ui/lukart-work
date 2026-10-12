from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common import (
    ADMISSION_STATUS,
    FORBIDDEN_AUTOMATIONS,
    REQUIRED_HUMAN_GATES,
    CommonPreLitigationEnvelope,
    strict_iso_date,
    canonical_pin,
)


TYPE_ID = "PL-PRE-COMPLAINT-1"
SCHEMA_VERSION = "1.0.0"
PLAN_SECTIONS = (
    "HEADER_AND_PARTIES",
    "CONTRACT_AND_PERFORMANCE",
    "DOCUMENTED_DEFECT",
    "HUMAN_SELECTED_REMEDY",
    "EVIDENCE_AND_ATTACHMENTS",
    "SIGNATURE",
)


class PLPreComplaint1Pin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type_id: Literal["PL-PRE-COMPLAINT-1"] = TYPE_ID
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    admission_status: Literal["NOT_ADMITTED"] = ADMISSION_STATUS


class PLPreComplaint1Input(CommonPreLitigationEnvelope):
    type_pin: PLPreComplaint1Pin = Field(default_factory=PLPreComplaint1Pin)

    contract_subject: str
    performance_date_iso: str
    documented_defect: str
    prior_correspondence: tuple[str, ...]
    requested_remedy: str
    requested_response_date_human: str

    @field_validator(
        "contract_subject",
        "performance_date_iso",
        "documented_defect",
        "requested_remedy",
        "requested_response_date_human",
    )
    @classmethod
    def complaint_text_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required complaint field must not be blank")
        return value

    @field_validator("performance_date_iso")
    @classmethod
    def performance_date_must_be_valid(cls, value: str) -> str:
        return strict_iso_date(value)

    @field_validator("prior_correspondence")
    @classmethod
    def prior_correspondence_required(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("prior_correspondence must be non-empty")
        return value

    @model_validator(mode="after")
    def human_remedy_only(self) -> "PLPreComplaint1Input":
        # requested_remedy is HUMAN-selected; the contract adds no statutory entitlement.
        return self


TYPE_CONTRACT_PIN = canonical_pin(
    {
        "document_type_id": TYPE_ID,
        "schema_version": SCHEMA_VERSION,
        "admission_status": ADMISSION_STATUS,
        "required_human_gates": REQUIRED_HUMAN_GATES,
        "plan_sections": PLAN_SECTIONS,
        "forbidden_automations": FORBIDDEN_AUTOMATIONS,
        "type_fields": (
            "contract_subject",
            "performance_date_iso",
            "documented_defect",
            "prior_correspondence",
            "requested_remedy",
            "requested_response_date_human",
        ),
    }
)
