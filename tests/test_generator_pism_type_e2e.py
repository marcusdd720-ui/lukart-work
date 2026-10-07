from __future__ import annotations

import base64
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import UUID, uuid5

from lukart_work.finalization.service import FinalizationService
from lukart_work.type_packs.pl_pre_complaint_1 import positive_fixture as complaint_fixture
from lukart_work.type_packs.pl_pre_payment_1 import positive_fixture as payment_fixture
from lukart_work.type_packs.pl_pre_reply_1 import positive_fixture as reply_fixture
from lukart_work.type_packs.runtime import (
    RUNTIME_PROFILES,
    finalization_profiles,
    runtime_profile,
    validate_type_pack,
)
from tests import test_stage02 as core
from tests.test_finalization import FinalizationTests


FIXTURES = {
    "PL-PRE-PAYMENT-1": payment_fixture,
    "PL-PRE-COMPLAINT-1": complaint_fixture,
    "PL-PRE-REPLY-1": reply_fixture,
}


class TypePackRuntimeBridgeTests(unittest.TestCase):
    def test_registry_binds_all_three_contract_pins_to_finalization_profiles(self):
        self.assertEqual(
            {item.type_id for item in RUNTIME_PROFILES},
            set(FIXTURES),
        )
        profiles = finalization_profiles()
        self.assertEqual(len(profiles), 3)
        self.assertEqual(
            {item.document_type.id for item in profiles},
            set(FIXTURES),
        )
        for type_id, fixture_factory in FIXTURES.items():
            with self.subTest(type_id=type_id):
                runtime = runtime_profile(type_id)
                value = validate_type_pack(type_id, fixture_factory())
                self.assertEqual(value.type_pin.document_type_id, type_id)
                self.assertEqual(runtime.document_type.id, type_id)
                self.assertEqual(
                    runtime.document_type.content_hash,
                    runtime.contract_pin,
                )
                self.assertEqual(
                    runtime.finalization_profile.document_type,
                    runtime.document_type,
                )

    def test_unknown_type_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_DOCUMENT_TYPE"):
            runtime_profile("PL-PRE-UNKNOWN-1")


@unittest.skipUnless(
    core.ADMIN_RUNTIME and core.DSN,
    "Generator Pism type E2E requires isolated PostgreSQL",
)
class GeneratorPismTypeE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FinalizationTests.setUpClass()

    @staticmethod
    def _typed_fact(harness: FinalizationTests, fixture):
        party = harness.apply(
            "AddParty",
            {
                "party_type": "PERSON",
                "display_name": fixture.recipient_name,
                "identity_evidence": [],
            },
        )[0].refs[0]

        # Product-input provenance and legal-authority provenance are distinct.
        # Keep the validated type-pack payload as immutable evidence, while the
        # existing Stage09/10 legal citation fixture receives its own exact
        # text/plain source so literal quotation verification remains truthful.
        content = fixture.model_dump_json().encode("utf-8")
        _result, request = harness.apply(
            "RegisterSource",
            {
                "content_base64": base64.b64encode(content).decode("ascii"),
                "media_type": "application/json",
                "retention_policy": core.PIN,
            },
        )
        source_id = uuid5(UUID(request["meta"]["command_id"]), "source")
        checksum = sha256(content).hexdigest()
        anchor = {
            "document_id": str(source_id),
            "document_hash": checksum,
            "locator": {
                "unit": "RECORD",
                "value": fixture.type_pin.document_type_id,
                "fragment_hash": checksum,
            },
        }
        evidence = harness.apply(
            "AddEvidence",
            {
                "evidence_type": "DOCUMENT",
                "description": (
                    "Validated baseline type-pack input "
                    + fixture.type_pin.document_type_id
                ),
                "source": anchor,
                "authenticity": "UNKNOWN",
            },
        )[0].refs[0]
        fact = harness.apply(
            "AddFact",
            {
                "statement": (
                    "Human-supplied bounded input for "
                    + fixture.type_pin.document_type_id
                ),
                "support": "SOURCE_BACKED",
                "evidence": [evidence.model_dump(mode="json")],
                "subjects": [party.model_dump(mode="json")],
                "key_fact": True,
            },
            anchors=[anchor],
        )[0].refs[0]

        legal_bytes = b"Synthetic payment receipt."
        _legal_result, legal_request = harness.apply(
            "RegisterSource",
            {
                "content_base64": base64.b64encode(legal_bytes).decode("ascii"),
                "media_type": "text/plain",
                "retention_policy": core.PIN,
            },
        )
        legal_source_id = uuid5(
            UUID(legal_request["meta"]["command_id"]),
            "source",
        )
        return fact, party, evidence, legal_source_id

    def test_each_baseline_type_reaches_verified_ten_member_package(self):
        for type_id, fixture_factory in FIXTURES.items():
            with self.subTest(type_id=type_id):
                runtime = runtime_profile(type_id)
                fixture = validate_type_pack(type_id, fixture_factory())
                pin = runtime.document_type.model_dump(mode="json")

                # The existing public Stage 03-13 services resolve document type through
                # the canonical VersionPin. Patch only the legacy synthetic test pin;
                # production services themselves are unmodified.
                with patch.object(core, "PIN", pin):
                    harness = FinalizationTests(
                        "test_public_happy_path_persists_exact_bytes_approval_and_release_chain"
                    )
                    harness.setUp()
                    harness.fact = lambda: self._typed_fact(harness, fixture)
                    harness.final_profile = runtime.finalization_profile
                    harness.finalization = FinalizationService(
                        harness.repo,
                        harness.authority,
                        (runtime.finalization_profile,),
                        package_profile=harness.package_profile,
                    )

                    validated, run_id = harness.validated()
                    render_id, _, _ = harness.render(validated, run_id)
                    rendered, _approval = harness.approve(validated, render_id)
                    harness.final_apply(
                        harness.release_request(rendered, render_id)
                    )
                    harness.final_apply(
                        harness.package_request(rendered, render_id)
                    )
                    package = harness.package_query(
                        "GetFinalPackage", render_id
                    )

                    self.assertEqual(
                        package.manifest.document_type,
                        runtime.document_type,
                    )
                    self.assertEqual(len(package.members), 10)
                    self.assertEqual(
                        tuple(item.name for item in package.members),
                        (
                            "final.docx",
                            "final.pdf",
                            "document.json",
                            "validation.json",
                            "sources.json",
                            "evidence-map.json",
                            "argument-map.json",
                            "audit.json",
                            "release.json",
                            "manifest.json",
                        ),
                    )

                    # Restart/read proof: create a fresh service over the same durable
                    # repository and verify every package member hash.
                    restarted = FinalizationService(
                        harness.repo,
                        harness.authority,
                        (runtime.finalization_profile,),
                        package_profile=harness.package_profile,
                    )
                    for member in package.members:
                        body = restarted.query(
                            {
                                "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
                                "operation": "ReadFinalPackageMember",
                                "tenant_id": str(harness.tenant),
                                "case_id": str(harness.case_id),
                                "render_id": str(render_id),
                                "member": member.name,
                            },
                            harness.token,
                        )
                        self.assertIsInstance(body, bytes)
                        self.assertEqual(
                            sha256(body).hexdigest(),
                            member.content_hash,
                        )


if __name__ == "__main__":
    unittest.main()
