from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from lukart_work.core.service import CommandService
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.finalization.service import FinalizationService
from lukart_work.planner.service import DocumentPlannerService
from lukart_work.validation.service import ValidationEngineService

from .drafting.manual_provider import ManualAttestedDraftingProvider
from .type_packs.runtime import TypePackRuntimeProfile, runtime_profile


@dataclass(frozen=True, slots=True)
class OperatorTypeBinding:
    runtime: TypePackRuntimeProfile

    @property
    def document_type(self):
        return self.runtime.document_type

    @property
    def plan_sections(self) -> tuple[str, ...]:
        return self.runtime.plan_sections


class GeneratorPismOperator:
    """Narrow production facade over the existing WORK services.

    It deliberately does not manufacture HUMAN decisions. The caller must use
    the existing authenticated commands for evidence/snapshot/plan/document
    approval and finalization. This facade only binds one admitted technical
    type-pack identity to the generic engines and routes public requests.
    """

    def __init__(
        self,
        *,
        repository,
        authority,
        type_id: str,
        drafting_profiles: dict[str, Any],
        provider: ManualAttestedDraftingProvider,
        package_profile,
        clock=None,
    ):
        runtime = runtime_profile(type_id)
        self.binding = OperatorTypeBinding(runtime)
        self.core = CommandService(repository, authority, clock)
        self.planner = DocumentPlannerService(repository, authority, clock)
        self.drafting = ControlledDraftingService(
            repository, authority, provider, drafting_profiles, clock
        )
        self.validation = ValidationEngineService(repository, authority, clock)
        self.finalization = FinalizationService(
            repository,
            authority,
            (runtime.finalization_profile,),
            clock,
            package_profile=package_profile,
        )

    def validate_intake(self, payload: Any):
        return self.binding.runtime.validate_input(payload)

    def _require_type_pin(self, raw: str | dict[str, Any]) -> None:
        value = json.loads(raw) if isinstance(raw, str) else raw
        pin = value.get("document_type") or value.get("type_pin")
        if pin is None:
            return
        expected = self.binding.document_type
        if isinstance(pin, dict):
            observed = (
                pin.get("id") or pin.get("document_type_id"),
                pin.get("version") or pin.get("schema_version"),
                pin.get("content_hash") or pin.get("contract_pin"),
            )
            wanted = (expected.id, expected.version, expected.content_hash)
            if observed != wanted:
                raise ValueError("OPERATOR_TYPE_PIN_MISMATCH")

    def execute_core(self, request, token):
        return self.core.execute(json.dumps(request) if isinstance(request, dict) else request, token)

    def execute_plan(self, request, token):
        return self.planner.execute(json.dumps(request) if isinstance(request, dict) else request, token)

    def execute_draft(self, request, token):
        return self.drafting.execute(json.dumps(request) if isinstance(request, dict) else request, token)

    def execute_validation(self, request, token):
        return self.validation.execute(json.dumps(request) if isinstance(request, dict) else request, token)

    def execute_finalization(self, request, token):
        return self.finalization.execute(json.dumps(request) if isinstance(request, dict) else request, token)

    def query_finalization(self, request, token):
        return self.finalization.query(json.dumps(request) if isinstance(request, dict) else request, token)
