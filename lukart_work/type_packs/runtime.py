from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from lukart_work.domain.models import VersionPin
from lukart_work.finalization.contracts import FinalizationProfile
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin



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


# Rejected catalogue entries are not executable registrations. Historical
# records keep their original pins and remain readable through finalization.
RUNTIME_PROFILES: tuple[TypePackRuntimeProfile, ...] = ()

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
