"""Fail-closed checks for the planned ROS <-> WORK integration contract v1."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "ros_work" / "v1" / "integration-contract.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def validate_contract(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("CONTRACT_OBJECT_REQUIRED")
    required = {
        "contract_id", "contract_version", "status", "observed_date", "architecture",
        "baselines", "composes", "ownership", "capabilities", "operations", "mapping",
        "gaps", "invariants", "non_goals", "acceptance",
    }
    if set(value) != required:
        raise ValueError("CONTRACT_KEYS")
    if value["contract_id"] != "urn:lukart:ros-work:generator-integration:1.0.0":
        raise ValueError("CONTRACT_ID")
    if value["contract_version"] != "1.0.0" or value["status"] != "PLANNED_NOT_IMPLEMENTED":
        raise ValueError("NO_FALSE_IMPLEMENTATION")
    try:
        observed_date = date.fromisoformat(value["observed_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("OBSERVED_DATE") from exc
    if observed_date.isoformat() != value["observed_date"]:
        raise ValueError("OBSERVED_DATE")
    if value["architecture"] != (
        "independent repositories, composed contracts, no runtime package dependency"
    ):
        raise ValueError("ARCHITECTURE")
    if value["composes"] != [
        "lukart.operation-contract.v1@1.0",
        "urn:lukart:cross-repo:convergence:1.0.0",
        "LW-PB-01",
    ]:
        raise ValueError("COMPOSITION")

    baselines = value["baselines"]
    if not isinstance(baselines, list) or len(baselines) != 2:
        raise ValueError("BASELINES")
    repositories = {item.get("repository") for item in baselines}
    if repositories != {"marcusdd720-ui/lukart-work", "marcusdd720-ui/lukart-ros"}:
        raise ValueError("BASELINE_REPOSITORIES")
    for item in baselines:
        if set(item) != {"repository", "ref", "commit", "freshness"}:
            raise ValueError("BASELINE_KEYS")
        if not SHA40.fullmatch(item["commit"]):
            raise ValueError("BASELINE_SHA")
    work = next(item for item in baselines if item["repository"].endswith("lukart-work"))
    ros = next(item for item in baselines if item["repository"].endswith("lukart-ros"))
    if work["ref"] != "uaos/generator-pism-p0" or work["freshness"] != "OBSERVED_CHECKED_OUT_HEAD":
        raise ValueError("WORK_BASELINE")
    if ros["ref"] != "refs/remotes/origin/main":
        raise ValueError("ROS_BASELINE_REF")
    if ros["freshness"] != "OBSERVED_LOCAL_REMOTE_REF_REMOTE_NOT_FETCHED":
        raise ValueError("ROS_FRESHNESS_MUST_BE_EXPLICIT")

    expected_owners = {
        "operation_envelope", "generator_domain_and_human_gates", "case_state_and_final_package",
        "neutral_evidence_result_and_provenance_envelopes", "legal_and_semantic_decisions",
    }
    if set(value["ownership"]) != expected_owners:
        raise ValueError("OWNERSHIP")
    if value["ownership"] != {
        "operation_envelope": "lukart-ros",
        "generator_domain_and_human_gates": "lukart-work",
        "case_state_and_final_package": "lukart-work",
        "neutral_evidence_result_and_provenance_envelopes": "cross-repo-convergence-v1",
        "legal_and_semantic_decisions": "HUMAN",
    }:
        raise ValueError("HUMAN_BOUNDARY")

    capabilities = value["capabilities"]
    ids = [item.get("id") for item in capabilities]
    if len(ids) != len(set(ids)) or set(ids) != {
        "CAP-ROS-OPERATION", "CAP-ROS-LEDGER", "CAP-ROS-CIRP", "CAP-ROS-RENDERER",
        "CAP-WORK-GENERATOR-PIPELINE", "CAP-WORK-DOCX-PDF", "CAP-CROSS-REPO-EVIDENCE",
    }:
        raise ValueError("CAPABILITY_COVERAGE")
    for item in capabilities:
        if set(item) != {"id", "owner", "state", "decision", "source", "source_blob"}:
            raise ValueError("CAPABILITY_KEYS")
        if not SHA40.fullmatch(item["source_blob"]):
            raise ValueError("CAPABILITY_SOURCE_PIN")
        if not all(isinstance(item[key], str) and item[key] for key in ("owner", "state", "decision", "source")):
            raise ValueError("CAPABILITY_VALUE")

    operations = value["operations"]
    if [item.get("id") for item in operations] != [
        "ros.work.generator.assess.v1",
        "ros.work.generator.execute.v1",
        "ros.work.generator.read-package.v1",
    ]:
        raise ValueError("OPERATION_ALLOWLIST")
    operation_keys = {"id", "effect", "state", "required_authority", "required_gates", "output"}
    if any(set(item) != operation_keys for item in operations):
        raise ValueError("OPERATION_KEYS")
    if any(
        not isinstance(item[key], str) or not item[key]
        for item in operations for key in ("effect", "state", "required_authority", "output")
    ):
        raise ValueError("OPERATION_VALUE")
    if operations[0]["effect"] != "READ_ONLY" or operations[0]["state"] != "PLANNED":
        raise ValueError("ASSESS_BOUNDARY")
    if operations[0]["required_gates"] != []:
        raise ValueError("ASSESS_GATES")
    for item in operations[1:]:
        if not item["state"].startswith("BLOCKED_BY_"):
            raise ValueError("WRITE_OPERATIONS_MUST_REMAIN_BLOCKED")
    if operations[1]["required_gates"] != [f"HG-{index:02}" for index in range(1, 10)]:
        raise ValueError("EXECUTE_GATES")
    if operations[2]["required_gates"] != ["HG-09"]:
        raise ValueError("PACKAGE_GATES")

    mapping_keys = {"request", "scope", "authority", "concurrency", "idempotency", "evidence", "result"}
    if set(value["mapping"]) != mapping_keys or not all(
        isinstance(item, str) and item for item in value["mapping"].values()
    ):
        raise ValueError("MAPPING")

    gaps = value["gaps"]
    gap_ids = [item.get("id") for item in gaps]
    if gap_ids != [f"RW-GAP-{index:02}" for index in range(1, 6)]:
        raise ValueError("GAP_ORDER")
    gap_keys = {"id", "severity", "state", "description", "owner", "dependency"}
    if any(set(item) != gap_keys for item in gaps) or any(
        not isinstance(item[key], str) or not item[key]
        for item in gaps for key in gap_keys
    ):
        raise ValueError("GAP_VALUE")
    if gaps[0]["severity"] != "P0" or not gaps[0]["state"].startswith("BLOCKING_"):
        raise ValueError("PB03_ACCEPTANCE_BLOCKER")
    for key in ("invariants", "non_goals", "acceptance"):
        items = value[key]
        if not items or len(items) != len(set(items)) or not all(
            isinstance(item, str) and item for item in items
        ):
            raise ValueError(key.upper())


class RosWorkIntegrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_is_complete_and_fail_closed(self):
        validate_contract(self.contract)

    def test_work_baseline_and_source_blobs_are_exact(self):
        work = next(
            item for item in self.contract["baselines"]
            if item["repository"] == "marcusdd720-ui/lukart-work"
        )
        baseline_object = subprocess.run(
            ["git", "cat-file", "-e", f"{work['commit']}^{{commit}}"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shallow = subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=ROOT,
            text=True,
        ).strip() == "true"
        if shallow:
            # A shallow checkout may contain the baseline commit object while
            # intentionally omitting intermediate ancestry. Never infer a
            # negative ancestry result from an incomplete graph. Instead bind
            # both the available baseline (when present) and the exact tested
            # HEAD to the pinned capability blobs.
            source_refs = ["HEAD"]
            if baseline_object.returncode == 0:
                source_refs.insert(0, work["commit"])
        else:
            self.assertEqual(
                baseline_object.returncode,
                0,
                "BASELINE_COMMIT_MISSING_IN_FULL_REPOSITORY",
            )
            baseline_is_ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", work["commit"], "HEAD"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(baseline_is_ancestor.returncode, 0)
            source_refs = [work["commit"]]
        for item in self.contract["capabilities"]:
            if item["owner"] == "lukart-ros":
                continue
            for source_ref in source_refs:
                actual = subprocess.check_output(
                    ["git", "rev-parse", f"{source_ref}:{item['source']}"],
                    cwd=ROOT,
                    text=True,
                ).strip()
                self.assertEqual(
                    actual,
                    item["source_blob"],
                    f"{item['id']}@{source_ref}",
                )

    def test_existing_convergence_contract_is_composed_not_duplicated(self):
        self.assertIn("urn:lukart:cross-repo:convergence:1.0.0", self.contract["composes"])
        self.assertEqual(
            self.contract["ownership"]["neutral_evidence_result_and_provenance_envelopes"],
            "cross-repo-convergence-v1",
        )

    def test_no_runtime_lukart_ros_dependency_exists(self):
        imports = []
        for path in (ROOT / "lukart_work").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?:from|import)\s+lukart_ros\b", text):
                imports.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(imports, [])

    def test_write_and_package_operations_cannot_be_marked_ready(self):
        for index in (1, 2):
            bad = deepcopy(self.contract)
            bad["operations"][index]["state"] = "READY"
            with self.assertRaises(ValueError):
                validate_contract(bad)

    def test_unknown_operation_and_false_ros_freshness_are_rejected(self):
        mutations = (
            lambda value: value["operations"].append(deepcopy(value["operations"][0])),
            lambda value: value["baselines"][1].update(freshness="REMOTE_VERIFIED"),
            lambda value: value.update(status="IMPLEMENTED"),
            lambda value: value["ownership"].update(legal_and_semantic_decisions="AI"),
            lambda value: value.update(observed_date="2026-02-30"),
            lambda value: value["mapping"].update(authority=""),
            lambda value: value["operations"][1]["required_gates"].pop(),
            lambda value: value["gaps"][0].update(dependency=""),
            lambda value: value["gaps"][0].update(state="RESOLVED"),
            lambda value: value["acceptance"].append(value["acceptance"][0]),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.__code__.co_firstlineno):
                bad = deepcopy(self.contract)
                mutation(bad)
                with self.assertRaises(ValueError):
                    validate_contract(bad)


if __name__ == "__main__":
    unittest.main()
