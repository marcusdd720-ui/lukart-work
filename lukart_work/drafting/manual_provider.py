from __future__ import annotations

from uuid import UUID

from lukart_work.contracts.messages import AIResult
from lukart_work.domain.models import VersionPin
from lukart_work.drafting.contracts import (
    DraftingInvocation,
    ModelExecutionReceipt,
)


class ManualAttestedDraftingProvider:
    """Fail-closed host-supplied drafting lane.

    The host registers an already structured AIResult for an exact request id.
    No network call, vendor SDK, credential, or model execution occurs here.
    ControlledDraftingService still validates the result against the frozen
    snapshot and records the normal immutable drafting trace.
    """

    def __init__(
        self,
        *,
        provider: VersionPin,
        model: VersionPin,
        generator: VersionPin,
        model_parameters_hash: str,
    ):
        self.provider = provider
        self.model = model
        self.generator = generator
        self.model_parameters_hash = model_parameters_hash
        self._results: dict[UUID, AIResult] = {}
        self._consumed: set[UUID] = set()

    def supply(self, result: AIResult) -> None:
        if result.request_id in self._results or result.request_id in self._consumed:
            raise ValueError("MANUAL_RESULT_ALREADY_BOUND")
        self._results[result.request_id] = result

    def propose(self, invocation: DraftingInvocation) -> AIResult:
        request_id = invocation.request.request_id
        try:
            result = self._results.pop(request_id)
        except KeyError as exc:
            raise ValueError("MANUAL_RESULT_REQUIRED") from exc
        if result.request_id != request_id:
            raise ValueError("MANUAL_RESULT_REQUEST_MISMATCH")
        if result.snapshot_hash != invocation.request.snapshot_hash:
            raise ValueError("MANUAL_RESULT_SNAPSHOT_MISMATCH")
        self._consumed.add(request_id)
        return result

    def execution_receipt(self, request_id: UUID) -> ModelExecutionReceipt:
        if request_id not in self._consumed:
            raise ValueError("MANUAL_RESULT_NOT_EXECUTED")
        return ModelExecutionReceipt(
            contract="urn:lukart:work:ModelExecutionReceipt:1.0.0",
            request_id=request_id,
            provider=self.provider,
            model=self.model,
            generator=self.generator,
            model_parameters_hash=self.model_parameters_hash,
        )
