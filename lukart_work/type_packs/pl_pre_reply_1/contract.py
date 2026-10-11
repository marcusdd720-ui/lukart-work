from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common import (
    ADMISSION_STATUS,
    FORBIDDEN_AUTOMATIONS,
    REQUIRED_HUMAN_GATES,
    CommonPreLitigationEnvelope,
    canonical_pin,
)


TYPE_ID = "PL-PRE-REPLY-1"
SCHEMA_VERSION = "1.0.0"
PLAN_SECTIONS = (
    "HEADER_AND_PARTIES",
    "INCOMING_DEMAND_REFERENCE",
    "HUMAN_APPROVED_POSITION",
    "ADMITTED_AND_DISPUTED_ITEMS",
    "EVIDENCE_AND_ATTACHMENTS",
    "SIGNATURE",
)


class PLPreReply1Pin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type_id: Literal["PL-PRE-REPLY-1"] = TYPE_ID
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    admission_status: Literal["NOT_ADMITTED"] = ADMISSION_STATUS


class PositionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: Literal["ADMITTED", "DISPUTED"]
    description: str
    amount_decimal: str | None = None

    @field_validator("description")
    @classmethod
    def description_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("position item description must not be blank")
        return value

    @field_validator("amount_decimal", mode="before")
    @classmethod
    def amount_if_present_is_decimal_string(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("amount_decimal must be a decimal string")
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount_decimal is not a valid decimal string") from exc
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("amount_decimal must be finite and non-negative")
        return value.strip()


class PLPreReply1Input(CommonPreLitigationEnvelope):
    type_pin: PLPreReply1Pin = Field(default_factory=PLPreReply1Pin)

    incoming_demand_source_ref: str
    incoming_demand_date_iso: str
    asserted_amount_decimal: str
    admitted_and_disputed_items: tuple[PositionItem, ...]
    response_position_human: str
    supporting_evidence: tuple[str, ...]

    @field_validator(
        "incoming_demand_source_ref",
        "incoming_demand_date_iso",
        "response_position_human",
    )
    @classmethod
    def reply_text_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required reply field must not be blank")
        return value

    @field_validator("asserted_amount_decimal", mode="before")
    @classmethod
    def asserted_amount_decimal_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("asserted_amount_decimal must be a decimal string")
        value = value.strip()
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("asserted_amount_decimal is not a valid decimal string") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("asserted_amount_decimal must be positive and finite")
        return value

    @field_validator("admitted_and_disputed_items", "supporting_evidence")
    @classmethod
    def reply_collections_non_empty(cls, value: tuple) -> tuple:
        if not value:
            raise ValueError("required reply collection must be non-empty")
        return value

    @model_validator(mode="after")
    def human_position_only(self) -> "PLPreReply1Input":
        # No admission/defence/legal effect may be generated outside HUMAN-approved position.
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
            "incoming_demand_source_ref",
            "incoming_demand_date_iso",
            "asserted_amount_decimal",
            "admitted_and_disputed_items",
            "response_position_human",
            "supporting_evidence",
        ),
    }
)
