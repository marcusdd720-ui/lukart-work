from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from lukart_work.domain.models import VersionPin
from lukart_work.finalization.contracts import FinalizationProfile
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin

from .pl_pre_complaint_1.contract import (
    PLAN_SECTIONS as COMPLAINT_SECTIONS,
    SCHEMA_VERSION as COMPLAINT_SCHEMA_VERSION,
    TYPE_CONTRACT_PIN as COMPLAINT_CONTRACT_PIN,
    TYPE_ID as COMPLAINT_TYPE_ID,
    PLPreComplaint1Input,
)
from .pl_pre_payment_1.contract import (
    PLAN_SECTIONS as PAYMENT_SECTIONS,
    SCHEMA_VERSION as PAYMENT_SCHEMA_VERSION,
    TYPE_CONTRACT_PIN as PAYMENT_CONTRACT_PIN,
    TYPE_ID as PAYMENT_TYPE_ID,
    PLPrePayment1Input,
)
from .pl_pre_reply_1.contract import (
    PLAN_SECTIONS as REPLY_SECTIONS,
    SCHEMA_VERSION as REPLY_SCHEMA_VERSION,
    TYPE_CONTRACT_PIN as REPLY_CONTRACT_PIN,
    TYPE_ID as REPLY_TYPE_ID,
    PLPreReply1Input,
)


@dataclass(frozen=True, slots=True)
class TypePackRuntimeProfile:
    """Technical bridge from a bounded type-pack contract to the generic engine.

    This object does not grant legal/domain admission.  It binds the exact
    type-contract digest to the document_type used by planning/drafting and to
    the semantic finalization profile consumed by FinalizationService.
    """

    type_id: str
    schema_version: str
    contract_pin: str
    header: str
    plan_sections: tuple[str, ...]
    input_model: type[BaseModel]

    @property
    def document_type(self) -> VersionPin:
        return VersionPin(
            id=self.type_id,
            version=self.schema_version,
            content_hash=self.contract_pin,
        )

    @property
    def finalization_profile(self) -> FinalizationProfile:
        return FinalizationProfile(
            profile_id=f"urn:lukart:work:type-pack:{self.type_id}:finalization",
            version=self.schema_version,
            document_type=self.document_type,
            header=self.header,
            render_profile=profile_pin(OFFICIAL_PL_V1),
        )

    def validate_input(self, payload: Any) -> BaseModel:
        value = (
            payload
            if isinstance(payload, self.input_model)
            else self.input_model.model_validate(payload)
        )
        pin = value.type_pin
        if (
            pin.document_type_id != self.type_id
            or pin.schema_version != self.schema_version
        ):
            raise ValueError("TYPE_PACK_IDENTITY_MISMATCH")
        return value


RUNTIME_PROFILES: tuple[TypePackRuntimeProfile, ...] = (
    TypePackRuntimeProfile(
        type_id=PAYMENT_TYPE_ID,
        schema_version=PAYMENT_SCHEMA_VERSION,
        contract_pin=PAYMENT_CONTRACT_PIN,
        header="WEZWANIE DO ZAPLATY",
        plan_sections=PAYMENT_SECTIONS,
        input_model=PLPrePayment1Input,
    ),
    TypePackRuntimeProfile(
        type_id=COMPLAINT_TYPE_ID,
        schema_version=COMPLAINT_SCHEMA_VERSION,
        contract_pin=COMPLAINT_CONTRACT_PIN,
        header="REKLAMACJA",
        plan_sections=COMPLAINT_SECTIONS,
        input_model=PLPreComplaint1Input,
    ),
    TypePackRuntimeProfile(
        type_id=REPLY_TYPE_ID,
        schema_version=REPLY_SCHEMA_VERSION,
        contract_pin=REPLY_CONTRACT_PIN,
        header="ODPOWIEDZ NA WEZWANIE",
        plan_sections=REPLY_SECTIONS,
        input_model=PLPreReply1Input,
    ),
)

_BY_TYPE_ID = {profile.type_id: profile for profile in RUNTIME_PROFILES}

if len(_BY_TYPE_ID) != len(RUNTIME_PROFILES):
    raise RuntimeError("DUPLICATE_TYPE_PACK_RUNTIME_PROFILE")


def runtime_profile(type_id: str) -> TypePackRuntimeProfile:
    try:
        return _BY_TYPE_ID[type_id.strip()]
    except (AttributeError, KeyError) as exc:
        raise ValueError("UNSUPPORTED_DOCUMENT_TYPE") from exc


def validate_type_pack(type_id: str, payload: Any) -> BaseModel:
    return runtime_profile(type_id).validate_input(payload)


def finalization_profiles() -> tuple[FinalizationProfile, ...]:
    """Profiles safe to wire technically; legal admission remains a separate gate."""

    return tuple(profile.finalization_profile for profile in RUNTIME_PROFILES)
