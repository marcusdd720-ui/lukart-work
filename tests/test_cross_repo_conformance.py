import copy
import json
import unittest
from pathlib import Path

from lukart_work.convergence import (
    ContractError,
    adapt_lukart_ros_operation_v1,
    adapt_lukart_work_command_result_v1,
    adapt_lukart_work_ingestion_v1,
    build_evidence_envelope,
    build_report,
    canonical_json,
    digest_bytes,
    digest_value,
    strict_json_loads,
    validate_evidence_envelope,
    validate_report_envelope,
    validate_result_envelope,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "cross_repo" / "v1" / "fixtures"


def fixture(name):
    return strict_json_loads((FIXTURES / name).read_text(encoding="utf-8"))


def provenance():
    impl = {"id": "synthetic-tool", "version": "1.0.0"}
    return {
        "schema_id": "urn:lukart:cross-repo:provenance:1.0.0",
        "schema_version": "1.0.0",
        "producer": "lukart-work",
        "operation_id": "synthetic-op",
        "method": "execution",
        "implementation": {**impl, "digest": digest_value(impl)},
        "inputs": [],
        "source_refs": ["fixture:synthetic"],
    }


class CrossRepoConformanceTests(unittest.TestCase):
    def test_canonical_json_is_deterministic(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')

    def test_sha256_digest_is_algorithm_tagged(self):
        result = digest_bytes(b"abc")
        self.assertEqual(result["algorithm"], "sha-256")
        self.assertEqual(len(result["value"]), 64)

    def test_sha512_digest_is_supported(self):
        self.assertEqual(len(digest_bytes(b"abc", "sha-512")["value"]), 128)

    def test_unknown_digest_algorithm_fails_closed(self):
        with self.assertRaises(ContractError):
            digest_bytes(b"abc", "md5")

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(ContractError) as ctx:
            strict_json_loads('{"a":1,"a":2}')
        self.assertEqual(ctx.exception.code, "DUPLICATE_JSON_KEY")

    def test_non_finite_json_is_rejected(self):
        with self.assertRaises(ContractError):
            strict_json_loads('{"a":NaN}')

    def test_ros_fixture_converges_to_success(self):
        result = adapt_lukart_ros_operation_v1(fixture("ros-operation-success.json"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["actual_effects"], ["write-artifact"])
        self.assertEqual(result["source_contract"]["schema_id"], "lukart.operation-contract.v1")

    def test_ros_declared_effects_must_equal_allowed_effects(self):
        payload = fixture("ros-operation-success.json")
        payload["constraints"]["allowed_side_effects"] = ["write-artifact", "commit"]
        with self.assertRaises(ContractError) as ctx:
            adapt_lukart_ros_operation_v1(payload)
        self.assertEqual(ctx.exception.code, "DECLARED_EFFECTS_MISMATCH")

    def test_ros_privacy_scope_is_fail_closed(self):
        payload = fixture("ros-operation-success.json")
        payload["privacy"]["scope"] = "OTHER-CASE"
        with self.assertRaises(ContractError):
            adapt_lukart_ros_operation_v1(payload)

    def test_ros_required_evidence_is_enforced(self):
        payload = fixture("ros-operation-success.json")
        payload["evidence"]["items"] = []
        with self.assertRaises(ContractError) as ctx:
            adapt_lukart_ros_operation_v1(payload)
        self.assertEqual(ctx.exception.code, "MISSING_REQUIRED_EVIDENCE")

    def test_work_ingestion_fixture_converges_to_success(self):
        result = adapt_lukart_work_ingestion_v1(fixture("work-ingestion-success.json"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["operation"], "IngestSource")
        self.assertEqual(
            result["source_contract"]["schema_id"],
            "urn:lukart:work:IngestionResult:1.0.0",
        )

    def test_work_ingestion_body_tamper_is_rejected(self):
        payload = fixture("work-ingestion-success.json")
        payload["body"]["warnings"] = []
        with self.assertRaises(ContractError) as ctx:
            adapt_lukart_work_ingestion_v1(payload)
        self.assertEqual(ctx.exception.code, "SOURCE_DIGEST_MISMATCH")

    def test_work_command_fixture_converges_to_success(self):
        source = fixture("work-command-applied.json")
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["actual_effects"], ["case-state"])
        self.assertEqual(
            result["source_contract"]["schema_id"],
            "urn:lukart:work:CommandResult:1.0.0",
        )

    def test_work_command_replay_has_no_actual_effect(self):
        source = fixture("work-command-applied.json")
        source["payload"]["state"] = "REPLAYED"
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["actual_effects"], [])

    def test_result_rejects_undeclared_effect(self):
        source = fixture("work-command-applied.json")
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        result["actual_effects"] = ["undeclared"]
        with self.assertRaises(ContractError) as ctx:
            validate_result_envelope(result)
        self.assertEqual(ctx.exception.code, "UNDECLARED_EFFECT")

    def test_success_result_rejects_errors(self):
        source = fixture("work-command-applied.json")
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        result["errors"] = [{
            "code": "SYNTHETIC", "category": "test",
            "retryable": False, "message": "Synthetic error.",
        }]
        with self.assertRaises(ContractError) as ctx:
            validate_result_envelope(result)
        self.assertEqual(ctx.exception.code, "SUCCESS_WITH_ERRORS")

    def test_evidence_id_is_content_addressed(self):
        envelope = build_evidence_envelope(
            b"synthetic bytes", media_type="text/plain", provenance=provenance()
        )
        self.assertTrue(envelope["evidence_id"].startswith("urn:lukart:evidence:sha-256:"))

    def test_evidence_must_be_immutable(self):
        envelope = build_evidence_envelope(
            b"synthetic bytes", media_type="text/plain", provenance=provenance()
        )
        envelope["immutable"] = False
        with self.assertRaises(ContractError) as ctx:
            validate_evidence_envelope(envelope)
        self.assertEqual(ctx.exception.code, "IMMUTABILITY_REQUIRED")

    def test_pass_report_requires_all_checks_pass(self):
        source = fixture("work-command-applied.json")
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        report = build_report(
            report_id="synthetic-report",
            subject="cross-repo-contract",
            checks=[{"id": "schema", "outcome": "PASS", "evidence": []}],
            result=result,
            provenance=provenance(),
            derived_from=[digest_value(result)],
        )
        self.assertEqual(report["outcome"], "PASS")

    def test_report_outcome_mismatch_is_rejected(self):
        source = fixture("work-command-applied.json")
        result = adapt_lukart_work_command_result_v1(
            source["payload"], operation=source["operation"]
        )
        report = build_report(
            report_id="synthetic-report",
            subject="cross-repo-contract",
            checks=[{"id": "schema", "outcome": "PASS", "evidence": []}],
            result=result,
            provenance=provenance(),
            derived_from=[digest_value(result)],
        )
        report["outcome"] = "FAIL"
        with self.assertRaises(ContractError) as ctx:
            validate_report_envelope(report)
        self.assertEqual(ctx.exception.code, "REPORT_OUTCOME_MISMATCH")


if __name__ == "__main__":
    unittest.main()
