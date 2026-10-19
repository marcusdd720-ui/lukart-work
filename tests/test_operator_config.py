"""Trusted wiring tests with real components; no database or HUMAN decisions."""
from hashlib import sha256
from http.client import HTTPConnection
from pathlib import Path
import runpy
import subprocess
import sys
from threading import Thread
import unittest

from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import TokenAuthority
from lukart_work.domain.models import VersionPin
from lukart_work.drafting.contracts import DraftingProfile
from lukart_work.drafting.manual_provider import ManualAttestedDraftingProvider
from lukart_work.finalization.contracts import FinalizationProfile, FinalPackageProfile
from lukart_work.operator_config import build_operator
from lukart_work.operator_host import create_server
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.storage.objects import RetentionPolicies


def pin(name):
    return VersionPin(id="urn:test:" + name, version="1.0.0",
                      content_hash=sha256(name.encode()).hexdigest())


class OperatorConfigTests(unittest.TestCase):
    def setUp(self):
        # Port 1 is not a database fixture. Any accidental SQL connection fails.
        self.repository = PostgresRepository(
            "host=127.0.0.1 port=1 dbname=unconfigured user=unconfigured connect_timeout=1",
            storage=True, retention_policies=RetentionPolicies())
        profile = DraftingProfile(
            profile="QUICK", prompt=pin("prompt"), model=pin("model"),
            provider=pin("provider"), generator=pin("generator"),
            output_contract=pin("output"), data_policy=pin("policy"),
            validators=(), render_profile=profile_pin(OFFICIAL_PL_V1),
            model_parameters_hash=sha256(b"test-only-parameters").hexdigest())
        self.values = dict(
            repository=self.repository, authority=TokenAuthority(),
            case_profile=FinalizationProfile(
                profile_id="urn:test:case-profile", version="1.0.0",
                document_type=pin("document"), header="Synthetic wiring test",
                render_profile=profile.render_profile),
            drafting_profiles={"QUICK": profile},
            provider=ManualAttestedDraftingProvider(
                provider=profile.provider, model=profile.model, generator=profile.generator,
                model_parameters_hash=profile.model_parameters_hash),
            package_profile=FinalPackageProfile(
                profile_id="urn:test:package", version="1.0.0",
                build_revision="a" * 40, baseline_contract_hash=sha256(b"test-baseline").hexdigest()))

    def test_explicit_components_are_retained_without_database_io(self):
        operator = build_operator(**self.values)
        self.assertIs(operator.core.repository, self.repository)
        self.assertIs(operator.core.authority, self.values["authority"])
        self.assertIs(operator.drafting.model_provider, self.values["provider"])
        self.assertEqual(operator.case_profile, self.values["case_profile"])
        self.assertIsNone(operator.binding)

    def test_missing_or_wrong_components_fail_closed(self):
        with self.assertRaises(TypeError):
            build_operator()
        for name in ("repository", "authority", "case_profile", "provider", "package_profile"):
            with self.subTest(component=name), self.assertRaisesRegex(ValueError, "TRUSTED_CASE_COMPONENT_REQUIRED"):
                build_operator(**dict(self.values, **{name: None}))

    def test_storage_and_retention_configuration_are_required(self):
        for repository in (PostgresRepository("unconfigured"),
                           PostgresRepository("unconfigured", storage=True)):
            with self.subTest(storage=repository.storage), self.assertRaisesRegex(
                    ValueError, "CASE_STORAGE_CONFIGURATION_REQUIRED"):
                build_operator(**dict(self.values, repository=repository))

    def test_drafting_profiles_must_be_explicit_and_identified(self):
        for profiles, error in (({}, "EXPLICIT_DRAFTING_PROFILES_REQUIRED"),
                                ({"QUICK": {}}, "DRAFTING_PROFILE_IDENTITY_MISMATCH"),
                                ({"FORENSIC": self.values["drafting_profiles"]["QUICK"]},
                                 "DRAFTING_PROFILE_IDENTITY_MISMATCH")):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                build_operator(**dict(self.values, drafting_profiles=profiles))

    def test_provider_identity_and_parameter_pins_must_match(self):
        original = self.values["drafting_profiles"]["QUICK"]
        for field in ("provider", "model", "generator", "model_parameters_hash"):
            value = "0" * 64 if field == "model_parameters_hash" else pin("foreign")
            changed = original.model_copy(update={field: value})
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "DRAFTING_PROVIDER_BINDING_MISMATCH"):
                build_operator(**dict(self.values, drafting_profiles={"QUICK": changed}))

    def test_render_profile_mismatch_is_rejected(self):
        profile = self.values["case_profile"].model_copy(update={"render_profile": pin("foreign-render")})
        with self.assertRaisesRegex(ValueError, "CASE_RENDER_PROFILE_MISMATCH"):
            build_operator(**dict(self.values, case_profile=profile))

    def test_unbound_example_and_cli_fail_closed_without_credentials(self):
        root = Path(__file__).resolve().parents[1]
        example = root / "examples" / "case_operator_host.py"
        with self.assertRaises(TypeError):
            runpy.run_path(str(example))["build_operator"]()
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m",
            "lukart_work.operator_host", "--config", str(example)],
            cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "HOST_CONFIGURATION_FAILED: trusted CASE services and capabilities required\n")
        self.assertEqual(result.stdout, "")

    def test_real_components_serve_shell_and_deny_unprovisioned_capability(self):
        server = create_server(build_operator(**self.values), 0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for method, path, body, headers, status in (
                ("GET", "/", None, {}, 200),
                ("POST", "/api/query_core", "{}", {
                    "Content-Type": "application/json", "Authorization": "Bearer unprovisioned"}, 403),
            ):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                try:
                    connection.request(method, path, body, headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, status)
                    response.read()
                finally:
                    connection.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
