"""Offline WORK snapshot adapter and evidence-bound drafting experiment.

No database writes, model calls, real HUMAN approval, FINAL or submission API.
Only the built-in synthetic fixture runner is exposed through the command line.
Hashes prove integrity, never authenticity or legal truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from typing import Mapping

from lukart_work.contracts.messages import Snapshot
from lukart_work.domain.models import Decision, Entity, Fact, LegalRule, Ref, VersionPin
from lukart_work.validation.rules import (
    Violation, digest, ref, validate_graph, validate_snapshot_acceptance, validate_state,
)


CATALOGUE = {
    "payment": ("Wezwanie do zapłaty", ("principal", "due_date", "destination")),
    "complaint": ("Reklamacja wykonania umowy", ("defect", "remedy")),
    "reply": ("Odpowiedź na wezwanie do zapłaty", ("incoming", "position")),
}


def document_pin(document_type: str) -> VersionPin:
    if document_type not in CATALOGUE:
        raise Violation("DOCUMENT_TYPE_UNSUPPORTED")
    return VersionPin(id=f"SYNTHETIC-{document_type}", version="1.0.0",
                      content_hash=digest(CATALOGUE[document_type]))


@dataclass(frozen=True)
class CaseView:
    """Offline projection of existing scoped WORK reads, not a second SSOT."""

    snapshot: Snapshot
    records: tuple[Entity, ...]
    sources: Mapping[str, bytes]
    acceptance: Decision

    def checked(self) -> dict[Ref, Entity]:
        records = {ref(item): item for item in self.records}
        if len(records) != len(self.records):
            raise Violation("DUPLICATE_REVISION")
        if set(records) != {member.ref for member in self.snapshot.members}:
            raise Violation("SNAPSHOT_RECORD_SET")
        validate_snapshot_acceptance(self.snapshot, self.acceptance, records)
        validate_graph(self.records, {item.id: item for item in self.snapshot.sources})
        # An offline acceptance object is not independently authenticated.
        # Live imports must use the authoritative scoped service, not this demo.
        expected_sources = {str(item.id): item for item in self.snapshot.sources}
        if set(expected_sources) != set(self.sources):
            raise Violation("SOURCE_SET")
        for identity, source in expected_sources.items():
            content = self.sources[identity]
            if len(content) != source.byte_length or sha256(content).hexdigest() != source.content_hash:
                raise Violation("SOURCE_BYTES_MISMATCH")
        return records


@dataclass(frozen=True)
class Intake:
    document_type: str
    evaluation_date: date
    sender: str
    recipient: str
    place: str
    request: str
    # Names resolve exact snapshot facts; no free-form model factual statements.
    fields: Mapping[str, Ref]
    rule: Ref


@dataclass(frozen=True)
class Proposal:
    input_hash: str
    text: str
    plan: tuple[str, ...]
    trace: tuple[dict, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class CodeIdentity:
    baseline_sha: str
    runtime_sha256: str
    source_state: str

    def checked(self):
        for value, length in ((self.baseline_sha, 40), (self.runtime_sha256, 64)):
            if len(value) != length or any(char not in "0123456789abcdef" for char in value):
                raise Violation("EXACT_CODE_IDENTITY_REQUIRED")
        if self.source_state not in ("CLEAN", "UNCOMMITTED"):
            raise Violation("EXACT_CODE_IDENTITY_REQUIRED")
        return {"baseline_sha": self.baseline_sha, "runtime_sha256": self.runtime_sha256,
                "source_state": self.source_state}


def _current_decision(decision, records, heads):
    if (decision is None or decision.kind != "Decision"
            or decision.status != "RECORDED"
            or decision.outcome != "ACCEPT" or decision.decided_by.kind != "HUMAN"
            or ref(decision) not in heads
            or any(item.kind == "Decision" and item.supersedes == ref(decision)
                   for item in records.values())):
        raise Violation("HUMAN_APPROVAL_REQUIRED")


def propose(view: CaseView, intake: Intake) -> Proposal:
    records = view.checked()
    # Real data are outside this candidate. A jurisdiction marker alone is NOT
    # a privacy classifier; the CLI additionally accepts no user case input.
    cases = [item for item in records.values() if item.kind == "Case"]
    if len(cases) != 1 or cases[0].jurisdiction != "SYNTHETIC":
        raise Violation("SYNTHETIC_ONLY")
    if intake.document_type not in CATALOGUE:
        raise Violation("DOCUMENT_TYPE_UNSUPPORTED")
    title, required = CATALOGUE[intake.document_type]
    if set(intake.fields) != set(required):
        raise Violation("TYPE_FIELDS_MISSING_OR_UNKNOWN")
    for value in (intake.sender, intake.recipient, intake.place, intake.request):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise Violation("FORMAL_INPUT_MISSING")
    heads = set(view.snapshot.heads)
    trace, paragraphs = [], []
    for name in required:
        target = intake.fields[name]
        fact = records.get(target)
        if target not in heads or not isinstance(fact, Fact) or fact.status != "CONFIRMED":
            raise Violation("CONFIRMED_CURRENT_FACT_REQUIRED")
        validate_state(fact, records)
        _current_decision(records.get(fact.acceptance), records, heads)
        if fact.support != "SOURCE_BACKED" or not fact.evidence:
            raise Violation("EVIDENCE_REQUIRED")
        anchors = []
        for evidence_ref in fact.evidence:
            evidence = records.get(evidence_ref)
            if (evidence_ref not in heads or evidence is None or evidence.kind != "Evidence"
                    or evidence.status != "ACCEPTED" or evidence.authenticity != "VERIFIED"):
                raise Violation("ACCEPTED_EVIDENCE_REQUIRED")
            anchor = evidence.source
            # The demo only admits complete literal UTF-8 source bytes, not OCR
            # guesses or approximate locators. No source field becomes truth.
            content = view.sources.get(str(anchor.document_id))
            if (content is None or anchor.locator.unit != "BYTE_RANGE"
                    or anchor.locator.value != f"0:{len(content)}"
                    or sha256(content).hexdigest() != anchor.locator.fragment_hash
                    or fact.statement != content.decode("utf-8")):
                raise Violation("SOURCE_LOCATOR_OR_LITERAL_MISMATCH")
            anchors.append(anchor.model_dump(mode="json"))
        paragraphs.append(fact.statement)
        trace.append({"field": name, "text_hash": digest(fact.statement),
                      "fact": target.model_dump(mode="json"), "anchors": anchors})
    rule = records.get(intake.rule)
    if (intake.rule not in heads or not isinstance(rule, LegalRule)
            or rule.status != "ACTIVE" or rule.jurisdiction != "SYNTHETIC"
            or document_pin(intake.document_type) not in rule.applicable_document_types
            or not rule.effective_period.start <= intake.evaluation_date
            or (rule.effective_period.end is not None
                and intake.evaluation_date > rule.effective_period.end)):
        raise Violation("LEGAL_APPLICABILITY_UNKNOWN")
    validate_state(rule, records)
    _current_decision(records.get(rule.review_decision), records, heads)
    for source_ref in rule.sources:
        source = records.get(source_ref)
        if (source_ref not in heads or source is None or source.kind != "LegalSource"
                or source.status != "VERIFIED" or source.jurisdiction != rule.jurisdiction
                or source.authority_level == "UNKNOWN"
                or source.effective_period.start > intake.evaluation_date
                or (source.effective_period.end is not None
                    and source.effective_period.end < intake.evaluation_date)):
            raise Violation("LEGAL_SOURCE_INVALID")
        content = view.sources.get(str(source.anchor.document_id))
        if content is None or sha256(content).hexdigest() != source.content_hash:
            raise Violation("LEGAL_SOURCE_BYTES_MISMATCH")
    trace.append({"field": "legal_basis", "rule": intake.rule.model_dump(mode="json"),
                  "sources": [item.model_dump(mode="json") for item in rule.sources]})
    # User declarations are explicit separate input fields; this experiment has
    # no strategic judgment and cannot turn them into approved claims/requests.
    text = "\n\n".join((
        f"{intake.place}, {intake.evaluation_date.isoformat()}",
        f"Nadawca: {intake.sender}", f"Adresat: {intake.recipient}", title,
        intake.request, *paragraphs, f"Podstawa wskazana do analizy: {rule.statement}",
        intake.sender,
    )) + "\n"
    input_hash = digest({"snapshot": digest(view.snapshot),
        "type": intake.document_type, "date": intake.evaluation_date.isoformat(),
        "sender": intake.sender, "recipient": intake.recipient, "place": intake.place,
        "request": intake.request,
        "fields": {name: target.model_dump(mode="json") for name, target in intake.fields.items()},
        "rule": intake.rule.model_dump(mode="json")})
    return Proposal(input_hash, text, ("formalities", "request", *required, "legal_basis", "signature"),
                    tuple(trace), ("SYNTHETIC_ONLY", "HUMAN_STRATEGY_REQUIRED",
                    "HUMAN_SEMANTIC_REVIEW_REQUIRED", "NO_FINAL_RELEASE",
                    "LIVE_LEGAL_OS_INTEGRATION_NOT_VERIFIED"))


def write_candidate(proposal: Proposal, output: Path, *, identity: CodeIdentity) -> Path:
    """Publish a fresh local draft directory; never reuse an earlier PASS report."""
    code = identity.checked()
    output.mkdir(parents=True, exist_ok=False)
    files = {
        "document.md": proposal.text.encode("utf-8"),
        "preview.html": ("<!doctype html><meta charset=utf-8><title>Podgląd pisma</title>"
            "<style>body{max-width:44rem;margin:3rem auto;font:18px/1.6 serif;white-space:pre-wrap}</style>"
            "<main>" + escape(proposal.text) + "</main>").encode("utf-8"),
        "trace.json": json.dumps(proposal.trace, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
        "plan.json": json.dumps(proposal.plan, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    for name, content in files.items():
        (output / name).write_bytes(content)
    manifest = {"schema_version": "generator-next-demo/1", "code_identity": code,
        "scope": "SYNTHETIC_OFFLINE_WORK_CONTRACT_DRAFT_ONLY", "input_hash": proposal.input_hash,
        "risks": proposal.risks, "release": "NOT_GRANTED", "human_decisions": "SIMULATED_FIXTURE_ONLY",
        "files": {name: {"sha256": sha256(content).hexdigest(), "bytes": len(content)}
                  for name, content in files.items()}}
    # Last file is the completion marker; interrupted writes cannot look complete.
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return output / "preview.html"


def verify_candidate(output: Path, *, expected_input_hash: str, identity: CodeIdentity) -> dict:
    """Restart-safe byte verification only; no human/legal authenticity claim."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Violation("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"), object_pairs_hook=pairs)
    if (manifest.get("schema_version") != "generator-next-demo/1"
            or manifest.get("input_hash") != expected_input_hash or manifest.get("code_identity") != identity.checked()
            or manifest.get("release") != "NOT_GRANTED"
            or manifest.get("scope") != "SYNTHETIC_OFFLINE_WORK_CONTRACT_DRAFT_ONLY"
            or manifest.get("human_decisions") != "SIMULATED_FIXTURE_ONLY"):
        raise Violation("MANIFEST_BINDING_MISMATCH")
    required = {"document.md", "preview.html", "trace.json", "plan.json"}
    if set(manifest["files"]) != required:
        raise Violation("PACKAGE_MEMBER_SET")
    if {item.name for item in output.iterdir()} != required | {"manifest.json"}:
        raise Violation("PACKAGE_MEMBER_SET")
    for name in required:
        path = output / name
        if path.is_symlink() or not path.is_file():
            raise Violation("PACKAGE_MEMBER_INVALID")
        content = path.read_bytes()
        if manifest["files"][name] != {"sha256": sha256(content).hexdigest(), "bytes": len(content)}:
            raise Violation("ARTIFACT_TAMPERED")
    return {"result": "BYTE_INTEGRITY_ONLY", "input_hash": expected_input_hash,
            "code_identity": identity.checked(), "release": "NOT_GRANTED", "files_checked": len(required)}
