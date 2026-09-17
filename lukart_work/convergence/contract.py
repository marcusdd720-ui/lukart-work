"""Technology-neutral cross-repository evidence/result convergence.

No dependency on ``lukart_ros``. Existing persisted payloads are adapted, never
rewritten. The shared layer owns only durable wire semantics.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
CANONICALIZATION_ID = "urn:lukart:canonical-json:sorted-utf8-v1"
DIGEST_SCHEMA_ID = "urn:lukart:cross-repo:digest:1.0.0"
PROVENANCE_SCHEMA_ID = "urn:lukart:cross-repo:provenance:1.0.0"
EVIDENCE_SCHEMA_ID = "urn:lukart:cross-repo:evidence-envelope:1.0.0"
RESULT_SCHEMA_ID = "urn:lukart:cross-repo:result-envelope:1.0.0"
REPORT_SCHEMA_ID = "urn:lukart:cross-repo:report-envelope:1.0.0"
STATUSES = {"success", "failure", "partial", "skipped", "blocked"}
DIGEST_LENGTHS = {"sha-256": 64, "sha-512": 128}
ID_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,256}$")
HEX_RE = re.compile(r"^[0-9a-f]+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_KEYS = {
    "api_key", "authorization", "cookie", "credential", "credentials", "password",
    "private_key", "secret", "token", "access_token", "refresh_token", "bearer_token",
}
MAX_ITEMS, MAX_STRING, MAX_BYTES, MAX_DEPTH = 256, 100_000, 16 * 1024 * 1024, 16


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _secret(key):
    value = key.strip().lower().replace("-", "_")
    return value in SECRET_KEYS or value.endswith(
        ("_token", "_password", "_secret", "_api_key", "_private_key", "_credential")
    )


def _bounded(value, depth=0):
    if depth > MAX_DEPTH:
        raise ContractError("MAX_DEPTH")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("NON_FINITE_NUMBER")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise ContractError("MAX_STRING")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS:
            raise ContractError("MAX_ITEMS")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("NON_STRING_KEY")
            if _secret(key):
                raise ContractError("RAW_SECRET_FIELD")
            _bounded(item, depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_ITEMS:
            raise ContractError("MAX_ITEMS")
        for item in value:
            _bounded(item, depth + 1)
        return
    raise ContractError("NON_JSON_VALUE")


def strict_json_loads(text):
    """Parse JSON at a contract boundary and reject ambiguous/non-finite input."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ContractError("INVALID_JSON")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def constant(_):
        raise ContractError("NON_FINITE_NUMBER")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, UnicodeError, TypeError) as error:
        raise ContractError("INVALID_JSON") from error
    _bounded(value)
    return value


def canonical_json(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    _bounded(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as error:
        raise ContractError("NON_JSON_VALUE") from error


def canonical_bytes(value):
    return canonical_json(value).encode("utf-8")


def digest_bytes(data, algorithm="sha-256"):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ContractError("INVALID_BYTES")
    if algorithm not in DIGEST_LENGTHS:
        raise ContractError("UNSUPPORTED_DIGEST_ALGORITHM")
    fn = hashlib.sha256 if algorithm == "sha-256" else hashlib.sha512
    return {"algorithm": algorithm, "value": fn(data).hexdigest()}


def digest_value(value, algorithm="sha-256"):
    return digest_bytes(canonical_bytes(value), algorithm)


def _map(value):
    if not isinstance(value, Mapping):
        raise ContractError("SCHEMA_INVALID")
    return value


def _seq(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractError("SCHEMA_INVALID")
    if len(value) > MAX_ITEMS:
        raise ContractError("MAX_ITEMS")
    return value


def _exact(value, allowed, required=None):
    required = allowed if required is None else required
    if not required <= set(value) or set(value) - allowed:
        raise ContractError("SCHEMA_INVALID")


def _text(value, *, identifier=False, maximum=MAX_STRING):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ContractError("SCHEMA_INVALID")
    if identifier and not ID_RE.fullmatch(value):
        raise ContractError("SCHEMA_INVALID")
    return value


def _ids(value):
    items = [_text(item, identifier=True) for item in _seq(value)]
    if len(items) != len(set(items)):
        raise ContractError("DUPLICATE")
    return items


def validate_digest(value):
    value = _map(value)
    _exact(value, {"algorithm", "value"})
    algorithm = _text(value["algorithm"], identifier=True)
    hexdigest = _text(value["value"], maximum=128)
    length = DIGEST_LENGTHS.get(algorithm)
    if length is None:
        raise ContractError("UNSUPPORTED_DIGEST_ALGORITHM")
    if len(hexdigest) != length or not HEX_RE.fullmatch(hexdigest):
        raise ContractError("INVALID_DIGEST")
    return {"algorithm": algorithm, "value": hexdigest}


def content_id(digest):
    digest = validate_digest(digest)
    return f"urn:lukart:evidence:{digest['algorithm']}:{digest['value']}"


def _pin(identifier, version):
    body = {"id": identifier, "version": version}
    return {**body, "digest": digest_value(body)}


def validate_provenance(value):
    value = _map(value)
    keys = {
        "schema_id", "schema_version", "producer", "operation_id", "method",
        "implementation", "inputs", "source_refs",
    }
    _exact(value, keys)
    if value["schema_id"] != PROVENANCE_SCHEMA_ID or value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA")
    method = _text(value["method"], identifier=True)
    if method not in {"manual", "import", "derivation", "execution", "validation"}:
        raise ContractError("SCHEMA_INVALID")
    impl = _map(value["implementation"])
    _exact(impl, {"id", "version", "digest"})
    refs = [_text(item, identifier=True) for item in _seq(value["source_refs"])]
    if len(refs) != len(set(refs)):
        raise ContractError("DUPLICATE")
    return {
        "schema_id": PROVENANCE_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "producer": _text(value["producer"], identifier=True),
        "operation_id": _text(value["operation_id"], identifier=True),
        "method": method,
        "implementation": {
            "id": _text(impl["id"], identifier=True),
            "version": _text(impl["version"], identifier=True),
            "digest": validate_digest(impl["digest"]),
        },
        "inputs": [validate_digest(item) for item in _seq(value["inputs"])],
        "source_refs": refs,
    }


def validate_evidence_envelope(value):
    value = _map(value)
    keys = {
        "schema_id", "schema_version", "evidence_id", "content_digest", "byte_length",
        "media_type", "immutable", "provenance", "locators",
    }
    _exact(value, keys)
    if value["schema_id"] != EVIDENCE_SCHEMA_ID or value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA")
    digest = validate_digest(value["content_digest"])
    if value["evidence_id"] != content_id(digest):
        raise ContractError("CONTENT_ADDRESS_MISMATCH")
    size = value["byte_length"]
    if type(size) is not int or not 0 <= size <= MAX_BYTES or value["immutable"] is not True:
        raise ContractError("IMMUTABILITY_REQUIRED")
    locators = []
    for raw in _seq(value["locators"]):
        raw = _map(raw)
        _exact(raw, {"kind", "value", "fragment_digest"}, {"kind", "value"})
        item = {"kind": _text(raw["kind"], identifier=True), "value": _text(raw["value"])}
        if "fragment_digest" in raw:
            item["fragment_digest"] = validate_digest(raw["fragment_digest"])
        locators.append(item)
    return {
        "schema_id": EVIDENCE_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "evidence_id": value["evidence_id"], "content_digest": digest, "byte_length": size,
        "media_type": _text(value["media_type"], maximum=256), "immutable": True,
        "provenance": validate_provenance(value["provenance"]), "locators": locators,
    }


def build_evidence_envelope(data, *, media_type, provenance, locators=(), algorithm="sha-256"):
    digest = digest_bytes(data, algorithm)
    return validate_evidence_envelope({
        "schema_id": EVIDENCE_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "evidence_id": content_id(digest), "content_digest": digest,
        "byte_length": len(data), "media_type": media_type, "immutable": True,
        "provenance": dict(provenance), "locators": [dict(item) for item in locators],
    })


def _evidence_ref(raw):
    raw = _map(raw)
    _exact(raw, {"kind", "ref", "digest", "source_revision"}, {"kind", "ref"})
    out = {"kind": _text(raw["kind"], identifier=True), "ref": _text(raw["ref"], identifier=True)}
    if "digest" in raw:
        out["digest"] = validate_digest(raw["digest"])
    if "source_revision" in raw:
        revision = _text(raw["source_revision"], maximum=40)
        if not SHA40_RE.fullmatch(revision):
            raise ContractError("SCHEMA_INVALID")
        out["source_revision"] = revision
    return out


def _error(raw):
    raw = _map(raw)
    _exact(raw, {"code", "category", "retryable", "message"})
    if type(raw["retryable"]) is not bool:
        raise ContractError("SCHEMA_INVALID")
    return {
        "code": _text(raw["code"], identifier=True),
        "category": _text(raw["category"], identifier=True),
        "retryable": raw["retryable"],
        "message": _text(raw["message"], maximum=1024),
    }


def validate_result_envelope(value):
    value = _map(value)
    keys = {
        "schema_id", "schema_version", "operation_id", "operation", "status", "summary",
        "declared_effects", "actual_effects", "artifacts", "evidence", "errors",
        "provenance", "source_contract",
    }
    _exact(value, keys)
    if value["schema_id"] != RESULT_SCHEMA_ID or value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA")
    status = _text(value["status"], identifier=True)
    if status not in STATUSES:
        raise ContractError("INVALID_STATUS")
    declared, actual = _ids(value["declared_effects"]), _ids(value["actual_effects"])
    if set(actual) - set(declared):
        raise ContractError("UNDECLARED_EFFECT")
    if actual and status not in {"success", "partial"}:
        raise ContractError("EFFECT_STATUS_MISMATCH")
    errors = [_error(item) for item in _seq(value["errors"])]
    if status == "success" and errors:
        raise ContractError("SUCCESS_WITH_ERRORS")
    source = _map(value["source_contract"])
    _exact(source, {"schema_id", "schema_version", "digest"})
    return {
        "schema_id": RESULT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "operation_id": _text(value["operation_id"], identifier=True),
        "operation": _text(value["operation"], identifier=True), "status": status,
        "summary": _text(value["summary"], maximum=4096), "declared_effects": declared,
        "actual_effects": actual, "artifacts": _ids(value["artifacts"]),
        "evidence": [_evidence_ref(item) for item in _seq(value["evidence"])], "errors": errors,
        "provenance": validate_provenance(value["provenance"]),
        "source_contract": {
            "schema_id": _text(source["schema_id"], identifier=True),
            "schema_version": _text(source["schema_version"], identifier=True),
            "digest": validate_digest(source["digest"]),
        },
    }


def validate_report_envelope(value):
    value = _map(value)
    keys = {
        "schema_id", "schema_version", "report_id", "subject", "outcome", "checks",
        "result", "provenance", "derived_from",
    }
    _exact(value, keys)
    if value["schema_id"] != REPORT_SCHEMA_ID or value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA")
    checks = []
    for raw in _seq(value["checks"]):
        raw = _map(raw)
        _exact(raw, {"id", "outcome", "evidence"})
        outcome = _text(raw["outcome"], identifier=True)
        if outcome not in {"PASS", "FAIL", "UNKNOWN", "SKIPPED"}:
            raise ContractError("INVALID_STATUS")
        checks.append({
            "id": _text(raw["id"], identifier=True), "outcome": outcome,
            "evidence": [_evidence_ref(item) for item in _seq(raw["evidence"])],
        })
    outcome = _text(value["outcome"], identifier=True)
    if not checks or outcome not in {"PASS", "FAIL"}:
        raise ContractError("SCHEMA_INVALID")
    if (outcome == "PASS") != all(item["outcome"] == "PASS" for item in checks):
        raise ContractError("REPORT_OUTCOME_MISMATCH")
    return {
        "schema_id": REPORT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "report_id": _text(value["report_id"], identifier=True),
        "subject": _text(value["subject"], identifier=True), "outcome": outcome,
        "checks": checks, "result": validate_result_envelope(value["result"]),
        "provenance": validate_provenance(value["provenance"]),
        "derived_from": [validate_digest(item) for item in _seq(value["derived_from"])],
    }


def _provenance(producer, operation_id, implementation, inputs, source_refs):
    return validate_provenance({
        "schema_id": PROVENANCE_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "producer": producer, "operation_id": operation_id, "method": "execution",
        "implementation": implementation, "inputs": list(inputs), "source_refs": list(source_refs),
    })


def adapt_lukart_ros_operation_v1(payload):
    root = _map(payload)
    top = {
        "request", "context", "preconditions", "constraints", "idempotency",
        "effects", "output", "evidence", "errors", "privacy",
    }
    _exact(root, top)
    request = _map(root["request"])
    _exact(request, {"schema_id", "version", "operation_id", "operation", "input"})
    if request["schema_id"] != "lukart.operation-contract.v1" or request["version"] != "1.0":
        raise ContractError("UNSUPPORTED_SOURCE_CONTRACT")
    operation_id = _text(request["operation_id"], identifier=True)
    operation = _text(request["operation"], identifier=True)
    _bounded(_map(request["input"]))

    context = _map(root["context"])
    _exact(context, {"repository", "branch", "worktree", "case_id", "runtime"})
    for item in context.values():
        _text(item, identifier=True)

    pre = _map(root["preconditions"])
    _exact(pre, {"authority_ref", "lock_ref", "expected_head"})
    _text(pre["authority_ref"], identifier=True)
    _text(pre["lock_ref"], identifier=True)
    if not SHA40_RE.fullmatch(_text(pre["expected_head"], maximum=40)):
        raise ContractError("SCHEMA_INVALID")

    constraints = _map(root["constraints"])
    _exact(constraints, {"timeout_ms", "allowed_side_effects", "privacy_scope", "evidence_required"})
    if type(constraints["timeout_ms"]) is not int or not 1 <= constraints["timeout_ms"] <= 300_000:
        raise ContractError("SCHEMA_INVALID")
    allowed, required = _ids(constraints["allowed_side_effects"]), _ids(constraints["evidence_required"])
    privacy_scope = _text(constraints["privacy_scope"], identifier=True)

    idem = _map(root["idempotency"])
    _exact(idem, {"key", "replay", "duplicate_handling"})
    _text(idem["key"], identifier=True)
    if idem["replay"] != "exact" or idem["duplicate_handling"] != "replay-or-block":
        raise ContractError("SCHEMA_INVALID")

    privacy = _map(root["privacy"])
    _exact(privacy, {"scope", "data_classification", "cross_scope_allowed"})
    if _text(privacy["scope"], identifier=True) != privacy_scope or privacy["cross_scope_allowed"] is not False:
        raise ContractError("PRIVACY_SCOPE_MISMATCH")
    _text(privacy["data_classification"], identifier=True)

    effects = _map(root["effects"])
    _exact(effects, {"declared", "actual"})
    declared, actual = _ids(effects["declared"]), _ids(effects["actual"])
    if declared != allowed:
        raise ContractError("DECLARED_EFFECTS_MISMATCH")

    output = _map(root["output"])
    _exact(output, {"status", "summary", "artifacts"})
    status = _text(output["status"], identifier=True)
    if status not in STATUSES:
        raise ContractError("INVALID_STATUS")
    _text(output["summary"], maximum=1024)
    _ids(output["artifacts"])

    section = _map(root["evidence"])
    _exact(section, {"items"})
    evidence = []
    for raw in _seq(section["items"]):
        raw = _map(raw)
        _exact(raw, {"kind", "ref", "sha", "digest"}, {"kind", "ref"})
        item = {"kind": _text(raw["kind"], identifier=True), "ref": _text(raw["ref"], identifier=True)}
        if "digest" in raw:
            item["digest"] = validate_digest({"algorithm": "sha-256", "value": raw["digest"]})
        if "sha" in raw:
            revision = _text(raw["sha"], maximum=40)
            if not SHA40_RE.fullmatch(revision):
                raise ContractError("SCHEMA_INVALID")
            item["source_revision"] = revision
        evidence.append(item)

    errors = _map(root["errors"])
    _exact(errors, {"items"})
    errors = [_error(item) for item in _seq(errors["items"])]
    if status == "success":
        if set(required) - {item["kind"] for item in evidence}:
            raise ContractError("MISSING_REQUIRED_EVIDENCE")
        if "commit" in actual and not any(
            item["kind"] == "commit" and "source_revision" in item for item in evidence
        ):
            raise ContractError("MISSING_COMMIT_REVISION")

    source_digest = digest_value(root)
    return validate_result_envelope({
        "schema_id": RESULT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "operation_id": operation_id, "operation": operation, "status": status,
        "summary": output["summary"], "declared_effects": declared, "actual_effects": actual,
        "artifacts": output["artifacts"], "evidence": evidence, "errors": errors,
        "provenance": _provenance(
            "lukart-ros", operation_id, _pin("lukart-ros-operation-contract-v1-adapter", "1.0.0"),
            (source_digest,), ("lukart.operation-contract.v1",),
        ),
        "source_contract": {
            "schema_id": "lukart.operation-contract.v1", "schema_version": "1.0",
            "digest": source_digest,
        },
    })


def adapt_lukart_work_ingestion_v1(payload):
    root = _map(payload)
    keys = {
        "contract", "tenant_id", "case_id", "run_id", "source_id", "source_hash",
        "source_byte_length", "actor", "recorded_at", "extractor", "parser",
        "python_version", "body_hash", "body",
    }
    _exact(root, keys)
    if root["contract"] != "urn:lukart:work:IngestionResult:1.0.0":
        raise ContractError("UNSUPPORTED_SOURCE_CONTRACT")
    run_id, source_id = _text(root["run_id"], identifier=True), _text(root["source_id"], identifier=True)
    source_hash = validate_digest({"algorithm": "sha-256", "value": root["source_hash"]})
    body_hash = validate_digest({"algorithm": "sha-256", "value": root["body_hash"]})
    body = _map(root["body"])
    if digest_value(body) != body_hash:
        raise ContractError("SOURCE_DIGEST_MISMATCH")
    disposition = _text(body.get("status"), identifier=True)
    status_map = {
        "EXTRACTED": "success", "FAILED": "partial", "NEEDS_OCR": "partial",
        "UNSUPPORTED": "partial", "EMPTY": "partial",
    }
    if disposition not in status_map:
        raise ContractError("INVALID_STATUS")
    extractor = _map(root["extractor"])
    _exact(extractor, {"id", "version", "content_hash"})
    implementation = {
        "id": _text(extractor["id"], identifier=True),
        "version": _text(extractor["version"], identifier=True),
        "digest": validate_digest({"algorithm": "sha-256", "value": extractor["content_hash"]}),
    }
    source_digest = digest_value(root)
    errors = [] if disposition != "FAILED" else [{
        "code": "INGESTION_FAILED", "category": "ingestion", "retryable": False,
        "message": "Source ingestion failed closed.",
    }]
    return validate_result_envelope({
        "schema_id": RESULT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "operation_id": run_id, "operation": "IngestSource", "status": status_map[disposition],
        "summary": f"Ingestion {disposition.lower()}; warnings={len(_seq(body.get('warnings', ())))}",
        "declared_effects": ["record-ingestion-result"], "actual_effects": ["record-ingestion-result"],
        "artifacts": [f"ingestion:{run_id}"],
        "evidence": [
            {"kind": "source", "ref": f"source:{source_id}", "digest": source_hash},
            {"kind": "ingestion-result", "ref": f"ingestion:{run_id}", "digest": source_digest},
        ],
        "errors": errors,
        "provenance": _provenance(
            "lukart-work", run_id, implementation, (source_hash,), (f"source:{source_id}",)
        ),
        "source_contract": {
            "schema_id": "urn:lukart:work:IngestionResult:1.0.0", "schema_version": "1.0.0",
            "digest": source_digest,
        },
    })


def _ref(raw):
    raw = _map(raw)
    _exact(raw, {"kind", "id", "revision"})
    if type(raw["revision"]) is not int or raw["revision"] < 1:
        raise ContractError("SCHEMA_INVALID")
    return f"{_text(raw['kind'], identifier=True)}:{_text(raw['id'], identifier=True)}:{raw['revision']}"


def adapt_lukart_work_command_result_v1(payload, *, operation):
    root = _map(payload)
    _exact(root, {"command_id", "state", "case_sequence", "refs", "event_ids", "errors"})
    command_id, state = _text(root["command_id"], identifier=True), _text(root["state"], identifier=True)
    status_map = {"APPLIED": "success", "REPLAYED": "success", "REJECTED": "failure"}
    if state not in status_map:
        raise ContractError("INVALID_STATUS")
    sequence = root["case_sequence"]
    if type(sequence) is not int or sequence < 0:
        raise ContractError("SCHEMA_INVALID")
    errors = []
    for raw in _seq(root["errors"]):
        raw = _map(raw)
        _exact(raw, {"code", "path", "message", "retryable", "correlation_id"})
        errors.append(_error({
            "code": raw["code"], "category": "domain",
            "retryable": raw["retryable"], "message": raw["message"],
        }))
    artifacts = [_ref(item) for item in _seq(root["refs"])]
    artifacts += [f"event:{_text(item, identifier=True)}" for item in _seq(root["event_ids"])]
    source_digest = digest_value(root)
    return validate_result_envelope({
        "schema_id": RESULT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "operation_id": command_id, "operation": _text(operation, identifier=True),
        "status": status_map[state], "summary": f"Command {state.lower()} at case sequence {sequence}",
        "declared_effects": ["case-state"], "actual_effects": ["case-state"] if state == "APPLIED" else [],
        "artifacts": artifacts, "evidence": [], "errors": errors,
        "provenance": _provenance(
            "lukart-work", command_id, _pin("lukart-work-command-result-v1-adapter", "1.0.0"),
            (source_digest,), (f"case-sequence:{sequence}",),
        ),
        "source_contract": {
            "schema_id": "urn:lukart:work:CommandResult:1.0.0", "schema_version": "1.0.0",
            "digest": source_digest,
        },
    })


def build_report(*, report_id, subject, checks, result, provenance, derived_from):
    checks = [dict(item) for item in checks]
    return validate_report_envelope({
        "schema_id": REPORT_SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "report_id": report_id, "subject": subject,
        "outcome": "PASS" if checks and all(item.get("outcome") == "PASS" for item in checks) else "FAIL",
        "checks": checks, "result": dict(result), "provenance": dict(provenance),
        "derived_from": [dict(item) for item in derived_from],
    })
