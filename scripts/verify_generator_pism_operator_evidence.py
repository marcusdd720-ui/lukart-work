"""Offline integrity verification; metadata cannot authenticate HUMAN or DB issuance."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pypdf import PdfReader

from lukart_work.audit.contracts import AuditPackage
from lukart_work.audit.service import verify_audit_package
from lukart_work.core.postgres import canonical
from lukart_work.core.requests import strict_json
from lukart_work.finalization.contracts import (
    FINAL_PACKAGE_MEMBER_NAMES, FinalArgumentMap, FinalDocumentRecord,
    FinalEvidenceMap, FinalPackageManifest, FinalSourcesRecord,
    FinalValidationRecord, FinalizationRelease,
)
from lukart_work.rendering.service import RenderedBundle, RenderingEngine
from lukart_work.validation.rules import digest as object_digest, ref

EXPECTED = FINAL_PACKAGE_MEMBER_NAMES
MAX_MEMBER_BYTES = 20_000_000


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def require(condition, code):
    # assert is deliberately forbidden here: python -O must not remove gates.
    if not condition:
        raise ValueError(code)


def read_bytes(path):
    require(path.is_file() and not path.is_symlink(), "REGULAR_MEMBER_REQUIRED")
    require(0 < path.stat().st_size <= MAX_MEMBER_BYTES, "MEMBER_SIZE")
    with path.open("rb") as stream:
        value = stream.read(MAX_MEMBER_BYTES + 1)
    require(0 < len(value) <= MAX_MEMBER_BYTES, "MEMBER_SIZE")
    return value


def verify_member(data, item):
    require(isinstance(item, dict), "MEMBER_METADATA")
    length = item.get("byte_length")
    require(type(length) is int and length == len(data), "MEMBER_LENGTH")
    require(item.get("content_hash") == digest(data), "MEMBER_HASH")


def parse_typed(data, cls):
    strict_json(data.decode("utf-8"))
    value = cls.model_validate_json(data)
    require(canonical(value).encode("utf-8") == data, "CANONICAL_MEMBER_REQUIRED")
    return value


def validate_formats(docx, pdf):
    # Parse actual structures instead of accepting only PK/%PDF magic bytes.
    with ZipFile(BytesIO(docx)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and len(names) <= 1000, "DOCX_DUPLICATE_OR_SIZE")
        require(sum(info.file_size for info in archive.infolist()) <= MAX_MEMBER_BYTES,
                "DOCX_EXPANDED_SIZE")
        require(archive.testzip() is None, "DOCX_CRC")
        for name in names:
            if name.endswith((".xml", ".rels")):
                data = archive.read(name)
                require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
                        "DOCX_ENTITY_DENIED")
                root = ElementTree.fromstring(data)
                if name.endswith(".rels"):
                    require(all(item.get("TargetMode") != "External" for item in root),
                            "DOCX_EXTERNAL_RELATIONSHIP")
    reader = PdfReader(BytesIO(pdf), strict=True)
    require(not reader.is_encrypted and len(reader.pages) >= 1, "PDF_DOCUMENT_REQUIRED")
    visited = set()
    def visit(value, depth=0):
        require(depth <= 40 and len(visited) <= 10000, "PDF_OBJECT_BUDGET")
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if hasattr(value, "get_object"):
            resolved = value.get_object()
            if resolved is not value:
                visit(resolved, depth + 1)
                return
        if isinstance(value, dict):
            require(not set(value).intersection({"/JavaScript", "/JS", "/OpenAction", "/AA",
                    "/Launch", "/EmbeddedFiles", "/RichMedia", "/XFA"}), "PDF_ACTIVE_CONTENT")
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, depth + 1)
    visit(reader.trailer)


def verify(evidence_path, package_dir, expected_sha):
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha) is not None, "EXPECTED_SHA")
    evidence_bytes = read_bytes(evidence_path)
    e = strict_json(evidence_bytes.decode("utf-8"))
    require(isinstance(e, dict), "EVIDENCE_OBJECT")
    require(e.get("contract") == "urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0",
            "EVIDENCE_CONTRACT")
    require(e.get("result") == "PASS" and e.get("tested_sha") == expected_sha, "EVIDENCE_SHA")
    require(e.get("synthetic_only") is True and e.get("human_actor_kind") == "HUMAN", "HUMAN_METADATA")
    require(e.get("legal_type_admission") == "HUMAN_REQUIRED" and
            e.get("release_eligibility") == "FINAL", "RELEASE_METADATA")
    members = e.get("package_members")
    require(type(e.get("package_member_count")) is int and e["package_member_count"] == 10 and
            isinstance(members, list) and len(members) == 10 and
            all(isinstance(item, dict) for item in members) and
            tuple(item.get("name") for item in members) == EXPECTED, "TEN_MEMBERS_REQUIRED")
    data = {name: read_bytes(package_dir / name) for name in EXPECTED}
    for item in members:
        verify_member(data[item["name"]], item)
    direct = e.get("direct_artifacts")
    require(isinstance(direct, dict) and set(direct) == {"final.docx", "final.pdf"}, "DIRECT_ARTIFACTS")
    for name, item in direct.items():
        verify_member(data[name], item)
    parsers = {
        "document.json": FinalDocumentRecord, "validation.json": FinalValidationRecord,
        "sources.json": FinalSourcesRecord, "evidence-map.json": FinalEvidenceMap,
        "argument-map.json": FinalArgumentMap, "audit.json": AuditPackage,
        "release.json": FinalizationRelease, "manifest.json": FinalPackageManifest,
    }
    parsed = {name: parse_typed(data[name], cls) for name, cls in parsers.items()}
    manifest = parsed["manifest.json"]
    document = parsed["document.json"]
    validation = parsed["validation.json"]
    release = parsed["release.json"]
    audit = parsed["audit.json"]
    for expected, actual in zip(manifest.members, members[:-1]):
        require({"name": expected.name, "content_hash": expected.content_hash,
                 "byte_length": expected.byte_length} == actual, "MANIFEST_MEMBER_METADATA")
        verify_member(data[expected.name], expected.model_dump(mode="json"))
    require(manifest.profile.build_revision == expected_sha and document.profile == manifest.profile,
            "BUILD_REVISION")
    require(document.document_type == manifest.document_type and
            document.document_type.content_hash == e.get("type_contract_pin"), "DOCUMENT_TYPE")
    scope = (manifest.tenant_id, manifest.case_id)
    require(scope == (release.tenant_id, release.case_id) ==
            (document.draft.tenant_id, document.draft.case_id) ==
            (document.render.tenant_id, document.render.case_id) ==
            (validation.approval.tenant_id, validation.approval.case_id) ==
            (audit.tenant_id, audit.case_id), "CROSS_CASE")
    require(str(manifest.package_id) == e.get("package_id") and
            str(manifest.render_id) == e.get("render_id") and
            str(manifest.release_id) == e.get("release_id") and
            release.render_id == document.render.id == validation.approval.render_id == manifest.render_id and
            release.id == manifest.release_id, "PACKAGE_IDENTITY")
    require(manifest.release_hash == object_digest(release) and
            manifest.audit_package_hash == object_digest(audit), "MANIFEST_TYPED_HASHES")
    require(validation.pre_render == document.render.validation and
            release.result.draft == ref(document.draft) == validation.approval.rendered_draft and
            release.result.snapshot_hash == document.draft.snapshot_hash and
            release.approval == validation.approval.approval and
            release.approval_hash == validation.approval.approval_hash and
            release.actor.kind == validation.approval.actor.kind == "HUMAN", "FINAL_RELEASE_BINDING")
    artifact_hashes = tuple(digest(data[name]) for name in EXPECTED[:2])
    require(release.result.render_hashes == artifact_hashes and
            release.result.receipt is not None and
            release.result.receipt.target.draft_hash == object_digest(document.draft), "RELEASE_ARTIFACTS")
    require(audit.case_sequence == manifest.case_sequence == release.committed_sequence and
            type(e.get("final_case_sequence")) is int and
            e["final_case_sequence"] == manifest.case_sequence + 1 and
            e.get("event_count") == len(audit.events) + 1, "PACKAGE_SEQUENCE")
    verify_audit_package(audit, expected_implementation=audit.implementation)
    validate_formats(data["final.docx"], data["final.pdf"])
    RenderingEngine.validate(RenderedBundle(data["final.docx"], data["final.pdf"], document.render.meta))
    return {
        "contract": "urn:lukart:work:GeneratorPismIndependentVerifier:1.0.0", "result": "PASS",
        "scope": "OFFLINE_PACKAGE_INTEGRITY_ONLY", "tested_sha": expected_sha,
        "evidence_hash": digest(evidence_bytes), "verified_members": members,
        "human_decision_authenticity": "NOT_VERIFIED", "repository_issuance": "NOT_VERIFIED",
        "checks": ["exact-sha", "typed-canonical-json", "cross-case-binding", "typed-final-release",
                   "ten-member-package", "manifest-member-byte-hashes", "parsed-docx-pdf",
                   "render-receipt-binding", "audit-chain"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True)
    p.add_argument("--package-dir", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    out = Path(a.output)
    # A failed rerun must never leave an earlier PASS report for this destination.
    require(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    report = verify(Path(a.evidence), Path(a.package_dir), a.expected_sha)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": "PASS", "tested_sha": a.expected_sha, "output": str(out)}))


if __name__ == "__main__":
    main()
