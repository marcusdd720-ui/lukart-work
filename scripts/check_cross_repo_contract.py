"""Independent cross-repository contract, schema and fixture gate."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from lukart_work.convergence.contract import (
    adapt_lukart_ros_operation_v1,
    adapt_lukart_work_command_result_v1,
    adapt_lukart_work_ingestion_v1,
    build_report,
    digest_value,
    strict_json_loads,
)

BASE = ROOT / "contracts" / "cross_repo" / "v1"


def load(path: Path):
    return strict_json_loads(path.read_text(encoding="utf-8"))


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


manifest = load(BASE / "manifest.json")
assert manifest["contract_id"] == "urn:lukart:cross-repo:convergence:1.0.0"
assert manifest["architecture"] == (
    "shared semantics, independent implementations, contract-based conformance"
)
assert all(row["status"] == "CONVERGED" for row in manifest["gap_matrix"])

for artifact in manifest["normative_artifacts"]:
    path = ROOT / artifact["path"]
    assert path.is_file(), "MISSING_NORMATIVE_ARTIFACT:" + artifact["path"]
    assert normalized_sha256(path) == artifact["sha256"], (
        "NORMATIVE_ARTIFACT_DRIFT:" + artifact["path"]
    )

schemas = {}
registry = Registry()
for path in sorted((BASE / "schemas").glob("*.schema.json")):
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    schemas[schema["$id"]] = schema
    registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
assert set(schemas) == set(manifest["schema_ids"]), "SCHEMA_ID_SET_MISMATCH"

fixtures = BASE / "fixtures"
ros = load(fixtures / "ros-operation-success.json")
ingestion = load(fixtures / "work-ingestion-success.json")
command = load(fixtures / "work-command-applied.json")

# The compatibility fixtures must first conform to the actual target-repo legacy schemas.
Draft202012Validator(load(ROOT / "schemas" / "IngestionResult.schema.json")).validate(ingestion)
Draft202012Validator(load(ROOT / "schemas" / "CommandResult.schema.json")).validate(
    command["payload"]
)

results = [
    adapt_lukart_ros_operation_v1(ros),
    adapt_lukart_work_ingestion_v1(ingestion),
    adapt_lukart_work_command_result_v1(command["payload"], operation=command["operation"]),
]
result_schema = schemas["urn:lukart:cross-repo:result-envelope:1.0.0"]
for result in results:
    Draft202012Validator(result_schema, registry=registry).validate(result)

pin = {"id": "cross-repo-conformance", "version": "1.0.0"}
provenance = {
    "schema_id": "urn:lukart:cross-repo:provenance:1.0.0",
    "schema_version": "1.0.0",
    "producer": "lukart-work",
    "operation_id": "cross-repo-conformance",
    "method": "validation",
    "implementation": {**pin, "digest": digest_value(pin)},
    "inputs": [result["source_contract"]["digest"] for result in results],
    "source_refs": ["synthetic-fixtures"],
}
report = build_report(
    report_id="cross-repo-conformance",
    subject="cross-repo-contract",
    checks=[
        {"id": "ros-adapter", "outcome": "PASS", "evidence": results[0]["evidence"][:1]},
        {
            "id": "work-ingestion-adapter",
            "outcome": "PASS",
            "evidence": results[1]["evidence"][:1],
        },
        {"id": "work-command-adapter", "outcome": "PASS", "evidence": []},
    ],
    result=results[0],
    provenance=provenance,
    derived_from=[result["source_contract"]["digest"] for result in results],
)
Draft202012Validator(
    schemas["urn:lukart:cross-repo:report-envelope:1.0.0"], registry=registry
).validate(report)

# Independent implementations means no import/runtime dependency on lukart-ros.
tree = ast.parse((ROOT / "lukart_work" / "convergence" / "contract.py").read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        assert "lukart_ros" not in (node.module or ""), "HARD_RUNTIME_DEPENDENCY"
    if isinstance(node, ast.Import):
        assert all("lukart_ros" not in alias.name for alias in node.names), (
            "HARD_RUNTIME_DEPENDENCY"
        )

profiles = [load(path) for path in sorted((BASE / "profiles").glob("*.json"))]
assert {profile["source"]["repository"] for profile in profiles} == {
    "marcusdd720-ui/lukart-ros",
    "marcusdd720-ui/lukart-work",
}
assert any(
    profile["source"]["commit"] == "451b6226ce2a290277b3ff49f7bb3e540a0f5586"
    for profile in profiles
)
assert any(
    profile["source"]["commit"] == "b4bb235487edef5af18dc83c3430839dad92de6f"
    for profile in profiles
)

print(
    json.dumps(
        {
            "adapted_results": len(results),
            "contract": manifest["contract_id"],
            "fixtures": len(list(fixtures.glob("*.json"))),
            "profiles": len(profiles),
            "report": report["outcome"],
            "result": "PASS",
            "runtime_dependency_lukart_ros": False,
            "schemas": len(schemas),
        },
        sort_keys=True,
    )
)
