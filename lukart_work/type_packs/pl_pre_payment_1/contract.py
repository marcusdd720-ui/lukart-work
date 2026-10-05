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


TYPE_ID = "PL-PRE-PAYMENT-1"
SCHEMA_VERSION = "1.0.0"
PLAN_SECTIONS = (
    "HEADER_AND_PARTIES",
    "PAYMENT_DEMAND",
    "FACTUAL_BASIS",
    "EVIDENCE_AND_ATTACHMENTS",
    "SIGNATURE",
)


class PLPrePayment1Pin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type_id: Literal["PL-PRE-PAYMENT-1"] = TYPE_ID
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    admission_status: Literal["NOT_ADMITTED"] = ADMISSION_STATUS


class PLPrePayment1Input(CommonPreLitigationEnvelope):
    type_pin: PLPrePayment1Pin = Field(default_factory=PLPrePayment1Pin)

    claim_basis: str
    principal_amount_decimal: str
    currency_pln: Literal["PLN"] = "PLN"
    performance_due_date_iso: str
    payment_history: str
    requested_payment_date_human: str
    payment_destination: str

    @field_validator(
        "claim_basis",
        "performance_due_date_iso",
        "payment_history",
        "requested_payment_date_human",
        "payment_destination",
    )
    @classmethod
    def payment_text_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required payment field must not be blank")
        return value

    @field_validator("principal_amount_decimal", mode="before")
    @classmethod
    def positive_decimal_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("principal_amount_decimal must be a decimal string")
        value = value.strip()
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("principal_amount_decimal is not a valid decimal string") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("principal_amount_decimal must be positive and finite")
        return value

    @model_validator(mode="after")
    def no_automated_legal_effects(self) -> "PLPrePayment1Input":
        # Legal effects remain outside this bounded type contract.
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
            "claim_basis",
            "principal_amount_decimal",
            "currency_pln",
            "performance_due_date_iso",
            "payment_history",
            "requested_payment_date_human",
            "payment_destination",
        ),
    }
)
