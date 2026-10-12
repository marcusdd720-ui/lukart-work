from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lukart_work.core.service import CommandService, safe_error
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.facts.service import FactEvidenceService
from lukart_work.finalization.service import FinalizationService
from lukart_work.planner.service import DocumentPlannerService
from lukart_work.procedural.service import ProceduralEngineService
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
    approval and finalization. This facade binds one admitted technical
    type-pack identity to the generic engines and routes the public application
    services required by the end-to-end document path.
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
        self.facts = FactEvidenceService(repository, authority, clock)
        self.procedural = ProceduralEngineService(repository, authority, clock)
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

    @staticmethod
    def _raw(request: str | dict[str, Any]) -> str:
        return json.dumps(request) if isinstance(request, dict) else request

    def validate_intake(self, payload: Any):
        return self.binding.runtime.validate_input(payload)

    def _require_type_pin(self, raw: str | dict[str, Any]) -> None:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(value, dict):
            raise ValueError("OPERATOR_REQUEST_OBJECT_REQUIRED")
        expected = self.binding.document_type
        wanted = (expected.id, expected.version, expected.content_hash)
        for field in ("document_type", "type_pin"):
            if field not in value:
                continue
            pin = value[field]
            if not isinstance(pin, dict):
                raise ValueError("OPERATOR_TYPE_PIN_INVALID")
            observed = (
                pin.get("id") or pin.get("document_type_id"),
                pin.get("version") or pin.get("schema_version"),
                pin.get("content_hash") or pin.get("contract_pin"),
            )
            if observed != wanted:
                raise ValueError("OPERATOR_TYPE_PIN_MISMATCH")

    def execute_core(self, request, token):
        return self.core.execute(self._raw(request), token)

    def query_core(self, request, token):
        return self.core.query(self._raw(request), token)

    def execute_fact_evidence(self, request, token):
        return self.facts.execute(self._raw(request), token)

    def execute_procedural(self, request, token):
        return self.procedural.execute(self._raw(request), token)

    def query_procedural(self, request, token):
        return self.procedural.query(self._raw(request), token)

    def execute_plan(self, request, token):
        return self.planner.execute(self._raw(request), token)

    def query_plan(self, request, token):
        return self.planner.get_plan(self._raw(request), token)

    def execute_draft(self, request, token):
        try:
            self._require_type_pin(request)
        except (ValueError, TypeError, KeyError, AttributeError):
            return safe_error("SCHEMA_INVALID", UUID(int=0))
        return self.drafting.generate(self._raw(request), token)

    def execute_validation(self, request, token):
        return self.validation.execute(self._raw(request), token)

    def query_validation(self, request, token):
        return self.validation.query(self._raw(request), token)

    def execute_finalization(self, request, token):
        return self.finalization.execute(self._raw(request), token)

    def query_finalization(self, request, token):
        return self.finalization.query(self._raw(request), token)