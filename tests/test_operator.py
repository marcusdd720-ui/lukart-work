from __future__ import annotations

from datetime import date
from hashlib import sha256
import unittest
from unittest.mock import Mock
from uuid import uuid4

from lukart_work.contracts.messages import AIRequest, AIResult, DomainError
from lukart_work.operator import GeneratorPismOperator, OperatorTypeBinding
from lukart_work.domain.models import Ref, VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.drafting.manual_provider import ManualAttestedDraftingProvider
from lukart_work.type_packs.runtime import RUNTIME_PROFILES, runtime_profile


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
        tenant_id, case_id, snapshot_id = uuid4(), uuid4(), uuid4()
        snapshot_hash = sha256(b"snapshot").hexdigest()
        request = AIRequest(
            request_id=request_id,
            tenant_id=tenant_id,
            case_id=case_id,
            task="DRAFTING",
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot_hash,
            input_refs=(),
            section_contract=None,
            prompt=pin("prompt"),
            output_contract=pin("output"),
            data_policy=pin("policy"),
        )
        invocation = DraftingInvocation(
            contract="urn:lukart:work:DraftingInvocation:1.0.0",
            section=Ref(kind="Section", id=uuid4(), revision=1),
            evaluation_date=date(2026, 10, 7),
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

    def test_operator_rejects_malformed_and_foreign_type_pins_without_drafting(self):
        operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
        operator.binding = OperatorTypeBinding(runtime_profile("PL-PRE-PAYMENT-1"))
        operator.drafting = Mock()
        operator.drafting.generate.return_value = "SAFE_PROVIDER_RESULT"
        actual = operator.binding.document_type
        good_pin = {"id": actual.id, "version": actual.version, "content_hash": actual.content_hash}
        foreign_pin = {**good_pin, "content_hash": "0" * 64}
        invalid = (
            "{", "[]", [], None, {"type_pin": None},
            {"document_type": "not-an-object"}, {"type_pin": []},
            {"document_type": foreign_pin},
            {"document_type": good_pin, "type_pin": foreign_pin},
        )
        for value in invalid:
            with self.subTest(value=value):
                response = operator.execute_draft(value, "synthetic-token")
                self.assertIsInstance(response, DomainError)
                self.assertEqual(response.code, "SCHEMA_INVALID")
                operator.drafting.generate.assert_not_called()
        self.assertEqual(
            operator.execute_draft({"document_type": good_pin}, "synthetic-token"),
            "SAFE_PROVIDER_RESULT",
        )
        operator.drafting.generate.assert_called_once()

    def test_all_baseline_runtime_profiles_have_real_contract_pins_and_sections(self):
        self.assertEqual(len(RUNTIME_PROFILES), 3)
        for profile in RUNTIME_PROFILES:
            self.assertEqual(profile.document_type.content_hash, profile.contract_pin)
            self.assertTrue(profile.plan_sections)


if __name__ == "__main__":
    unittest.main()
