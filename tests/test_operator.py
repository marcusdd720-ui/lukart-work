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
from lukart_work.type_packs.runtime import RUNTIME_PROFILES, TypePackRuntimeProfile
from pydantic import BaseModel


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
        operator.binding = OperatorTypeBinding(TypePackRuntimeProfile(
            type_id="urn:test:explicit-profile", schema_version="1.0.0",
            contract_pin=sha256(b"explicit-test-contract").hexdigest(),
            header="Test", plan_sections=("FACTS",), input_model=BaseModel,
        ))
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

    def test_builtin_runtime_catalogue_is_empty(self):
        self.assertEqual(RUNTIME_PROFILES, ())

    def test_case_profile_requires_case_commands_and_retains_exact_pin_guard(self):
        from lukart_work.finalization.contracts import FinalizationProfile
        from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
        profile = FinalizationProfile(
            profile_id="urn:test:case-profile", version="1.0.0",
            document_type=pin("case-document"), header="Case",
            render_profile=profile_pin(OFFICIAL_PL_V1))
        operator = GeneratorPismOperator(repository=Mock(), authority=Mock(),
            case_profile=profile, drafting_profiles={}, provider=Mock(), package_profile=None)
        with self.assertRaisesRegex(ValueError, "CASE_COMMANDS_REQUIRED"):
            operator.validate_intake({})
        operator.drafting = Mock()
        denied = operator.execute_draft({"document_type": pin("foreign").model_dump(mode="json")}, "token")
        self.assertEqual(denied.code, "SCHEMA_INVALID")
        operator.drafting.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
