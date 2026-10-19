"""Synthetic CASE service E2E and local preview, without document templates."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

# Localize only this public synthetic scenario. Persist Polish inputs before
# snapshot/plan approval and model receipts; never rewrite released artifacts.
POLISH_COMMAND_FIELDS = {
    "AddParty": {"display_name": ("Synthetic Person", "Jan Testowy")},
    "AddEvidence": {"description": ("Synthetic receipt", "Syntetyczne potwierdzenie wpłaty")},
    "AddFact": {"statement": ("A payment is asserted", "Zgłoszono dokonanie wpłaty")},
    "AddRequest": {"text": ("Synthetic requested outcome", "Syntetyczny wniosek testowy")},
}
POLISH_STATEMENTS = {
    "Synthetic source-backed factual statement.": "Syntetyczne stwierdzenie faktyczne oparte na źródle.",
    "Synthetic requested outcome.": "Syntetyczny wniosek testowy.",
    "Synthetic legal proposition.": "Syntetyczne twierdzenie prawne.",
}

def polish_fixture_type(base):
    class PolishE2EFixture(base):
        def request(self, operation, data=None, target=None, **extra):
            data = dict(data or {})
            for field, (original, translated) in POLISH_COMMAND_FIELDS.get(operation, {}).items():
                require(data.get(field) == original, "UNEXPECTED_SYNTHETIC_INPUT:" + operation)
                data[field] = translated
            if operation == "PlanDocument":
                data["sections"] = [dict(section) for section in data["sections"]]
                require(len(data["sections"]) == 1 and data["sections"][0]["title"] == "Synthetic section",
                        "UNEXPECTED_SYNTHETIC_SECTION")
                data["sections"][0]["title"] = "Uzasadnienie"
            return super().request(operation, data, target, **extra)

        @staticmethod
        def statement(text, *args, **kwargs):
            require(text in POLISH_STATEMENTS, "UNEXPECTED_SYNTHETIC_STATEMENT")
            return base.statement(POLISH_STATEMENTS[text], *args, **kwargs)
    return PolishE2EFixture

def verify_polish_document_text(text):
    normalized = " ".join(text.split())
    expected = ("SYNTETYCZNE PISMO TESTOWE", "Jan Testowy", "Wnioski", "Uzasadnienie",
                "Załączniki", "Syntetyczne potwierdzenie wpłaty", *POLISH_STATEMENTS.values())
    require(all(fragment in normalized for fragment in expected), "POLISH_DOCUMENT_TEXT_REQUIRED")
    require("Synthetic" not in normalized and "A payment is asserted" not in normalized,
            "ENGLISH_SYNTHETIC_TEXT_FORBIDDEN")

def verify_polish_artifacts(directory):
    from docx import Document
    from pypdf import PdfReader
    verify_polish_document_text("\n".join(p.text for p in Document(directory / "final.docx").paragraphs))
    verify_polish_document_text("\n".join(page.extract_text() for page in PdfReader(directory / "final.pdf").pages))

def require(condition, label):
    if not condition:
        raise ValueError(label)

def current_sha():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(len(head) == 40 and all(c in "0123456789abcdef" for c in head), "INVALID_CHECKOUT_SHA")
    require(not os.environ.get("TESTED_SHA") or os.environ["TESTED_SHA"] == head, "TESTED_SHA_MISMATCH")
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(), "DIRTY_CHECKOUT")
    return head

def run(output, tested_sha):
    from tests import test_finalization as final
    from lukart_work.operator import GeneratorPismOperator
    require(final.core.ADMIN_RUNTIME and final.core.DSN, "ISOLATED_POSTGRESQL_REQUIRED")
    require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    fixture = polish_fixture_type(final.FinalizationTests)
    fixture.setUpClass()
    h = fixture("test_public_happy_path_persists_exact_bytes_approval_and_release_chain")
    h.setUp()
    h.package_profile = h.package_profile.model_copy(update={"build_revision": tested_sha})
    operator = GeneratorPismOperator(repository=h.repo, authority=h.authority,
        case_profile=h.final_profile, drafting_profiles={"QUICK": h.profile},
        provider=h.provider, package_profile=h.package_profile)
    h.service, h.facts = operator.core, operator.facts
    h.planner, h.procedural = operator.planner, operator.procedural
    h.drafting, h.validation, h.finalization = operator.drafting, operator.validation, operator.finalization
    rendered, render_id = h.released()
    h.final_apply(h.package_request(rendered, render_id))
    package = h.package_query("GetFinalPackage", render_id)
    release = h.final_query("GetFinalRelease", render_id)
    from lukart_work.finalization.contracts import FINAL_PACKAGE_MEMBER_NAMES
    require(tuple(member.name for member in package.members) == FINAL_PACKAGE_MEMBER_NAMES,
            "TEN_MEMBERS_REQUIRED")
    require(release.result.eligibility == "FINAL", "FINAL_REQUIRED")
    preview = operator.export_local(tenant_id=h.tenant, case_id=h.case_id,
        render_id=render_id, token=h.token, output=output / "local")
    directory = output / "package"
    directory.mkdir()
    members = []
    for member in package.members:
        body = h.package_query("ReadFinalPackageMember", render_id, member=member.name)
        require(isinstance(body, bytes), "PACKAGE_MEMBER_BYTES_REQUIRED")
        require(sha256(body).hexdigest() == member.content_hash and len(body) == member.byte_length, "PACKAGE_MEMBER_HASH_OR_SIZE")
        (directory / member.name).write_bytes(body)
        members.append({"name": member.name, "content_hash": member.content_hash, "byte_length": member.byte_length})
    for local_name, member_name in (("document.docx", "final.docx"), ("document.pdf", "final.pdf")):
        require((preview.parent / local_name).read_bytes() == (directory / member_name).read_bytes(),
                "DIRECT_ARTIFACT_MISMATCH")
    verify_polish_artifacts(directory)
    with h.repo.transaction(h.tenant, h.case_id) as tx:
        events, outbox = tx.events(), tx.outbox()
        require(events == outbox, "EVENT_OUTBOX_MISMATCH")
    evidence = {
        "contract": "urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0",
        "result": "PASS", "tested_sha": tested_sha, "synthetic_only": True,
        "execution_scope": "EXISTING_CASE_SERVICE_FIXTURE_AND_AUTHORIZED_LOCAL_EXPORT",
        "human_actor_kind": h.actor.kind, "legal_type_admission": "HUMAN_REQUIRED",
        "type_contract_pin": package.manifest.document_type.content_hash,
        "render_id": str(render_id), "release_id": str(release.id),
        "package_id": str(package.id), "release_eligibility": release.result.eligibility,
        "package_member_count": len(members), "package_members": members,
        "direct_artifacts": {item["name"]: {k:v for k,v in item.items() if k != "name"} for item in members[:2]},
        "final_case_sequence": h.sequence, "event_count": len(events),
    }
    (output / "evidence.json").write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "tested_sha": tested_sha, "preview": str(preview)}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/generator-pism/operator-e2e")
    args = parser.parse_args()
    run(ROOT / args.output, current_sha())

if __name__ == "__main__":
    main()
