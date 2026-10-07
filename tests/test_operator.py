from __future__ import annotations

from hashlib import sha256
import unittest
from uuid import uuid4

from lukart_work.contracts.messages import AIRequest, AIResult
from lukart_work.domain.models import VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.drafting.manual_provider import ManualAttestedDraftingProvider
from lukart_work.type_packs.runtime import RUNTIME_PROFILES


def pin(name: str) -> VersionPin:
    return VersionPin(id=name, version="1.0.0", content_hash=sha256(name.encode()).hexdigest())


class ManualProviderTests(unittest.TestCase):
    def test_manual_provider_is_exact_request_bound_and_receipted(self):
        provider = ManualAttestedDraftingProvider(
            provider=pin("manual"),
            model=pin("host-model"),
            generator=pin("generator"),
            model_parameters_hash=sha256(b"params").hexdigest(),
        )
        request_id = uuid4()
        snapshot_hash = sha256(b"snapshot").hexdigest()
        request = AIRequest(
            request_id=request_id,
            task="DRAFTING",
            snapshot_hash=snapshot_hash,
            allowed_refs=(),
            allowed_sources=(),
            section_contract=None,
            prompt="bounded",
            profile="QUICK",
        )
        invocation = DraftingInvocation(
            contract="urn:lukart:work:DraftingInvocation:1.0.0",
            section={"kind": "Section", "id": str(uuid4()), "revision": 1},
            evaluation_date="2026-10-07",
            request=request,
        )
        result = AIResult(
            request_id=request_id,
            snapshot_hash=snapshot_hash,
            disposition="ABSTAIN",
            proposals=(),
            section=None,
            missing_information=(),
            reason="HUMAN supplied provider abstained",
        )
        provider.supply(result)
        self.assertEqual(provider.propose(invocation), result)
        receipt = provider.execution_receipt(request_id)
        self.assertEqual(receipt.request_id, request_id)
        self.assertEqual(receipt.provider, pin("manual"))
        with self.assertRaisesRegex(ValueError, "MANUAL_RESULT_REQUIRED"):
            provider.propose(invocation)

    def test_all_baseline_runtime_profiles_have_real_contract_pins_and_sections(self):
        self.assertEqual(len(RUNTIME_PROFILES), 3)
        for profile in RUNTIME_PROFILES:
            self.assertEqual(profile.document_type.content_hash, profile.contract_pin)
            self.assertTrue(profile.plan_sections)


if __name__ == "__main__":
    unittest.main()
