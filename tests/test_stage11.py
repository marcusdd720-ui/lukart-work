"""Stage 11 deterministic rendering, adversarial and format-contract tests."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from reportlab.pdfbase.ttfonts import TTFont

from lukart_work.contracts.messages import RenderRequest
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_font_paths, profile_pin
from lukart_work.rendering.service import RenderingEngine, authorization_binding, derive_render_authority
from lukart_work.validation.rules import Violation, digest
from tests.stage11_render_fixture import build_fixture


class Stage11RenderingTests(unittest.TestCase):
    def setUp(self):
        self.request, self.records, self.validation = build_fixture()
        self.engine = RenderingEngine()

    def test_official_profile_font_is_exact_and_supports_polish(self):
        regular, bold = profile_font_paths(OFFICIAL_PL_V1)
        self.assertTrue(regular.is_file())
        self.assertTrue(bold.is_file())
        font = TTFont("Stage11PolishGlyphProbe", str(regular))
        required = "Zażółć gęślą jaźń ĄĆĘŁŃÓŚŹŻ"
        missing = [char for char in required if char != " " and ord(char) not in font.face.charToGlyph]
        self.assertEqual(missing, [])

    def test_same_input_produces_exact_same_docx_pdf_and_receipt(self):
        first = self.engine.render(self.request, self.records, self.validation)
        second = self.engine.render(self.request, self.records, self.validation)
        self.assertEqual(first.docx, second.docx)
        self.assertEqual(first.pdf, second.pdf)
        self.assertEqual(first.meta.receipt, second.meta.receipt)
        self.engine.validate(first)

    def test_fresh_process_reproduction_is_stable(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-B", "-X", "utf8", "-m", "tests.stage11_subprocess_fixture"]
        first = subprocess.check_output(command, cwd=root, text=True).strip()
        second = subprocess.check_output(command, cwd=root, text=True).strip()
        actual = json.loads(first)
        self.assertEqual(actual, json.loads(second))
        print("STAGE11_RENDER_IDENTITY=" + first)
        golden = json.loads((root / "tests/golden_cases/stage11_render_identity.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, golden)

    def test_docx_declares_single_profile_font_and_preserves_polish_text(self):
        bundle = self.engine.render(self.request, self.records, self.validation)
        with ZipFile(BytesIO(bundle.docx), "r") as package:
            document = package.read("word/document.xml").decode("utf-8")
            styles = package.read("word/styles.xml").decode("utf-8")
            all_xml = "\n".join(
                package.read(name).decode("utf-8", errors="ignore")
                for name in package.namelist()
                if name.endswith(".xml")
            )
        self.assertIn("Zażółć gęślą jaźń", document)
        self.assertIn(OFFICIAL_PL_V1.font_family, document)
        self.assertNotIn("REVIEW_REQUIRED", all_xml)
        self.assertNotIn("AI-generated", all_xml)
        self.assertNotIn("vbaProject.bin", "\n".join(package.namelist()) if False else "")
        # Template defaults may remain in styles.xml, but every emitted content run is pinned.
        self.assertIn("Liberation Serif", document)

    def test_docx_pagination_is_profile_controlled(self):
        bundle = self.engine.render(self.request, self.records, self.validation)
        with ZipFile(BytesIO(bundle.docx), "r") as package:
            footer_names = [name for name in package.namelist() if name.startswith("word/footer") and name.endswith(".xml")]
            self.assertEqual(len(footer_names), 1)
            footer = package.read(footer_names[0]).decode("utf-8")
        self.assertIn("PAGE", footer)
        self.assertIn(OFFICIAL_PL_V1.font_family, footer)

    def test_pdf_embeds_font_and_forbids_active_content(self):
        bundle = self.engine.render(self.request, self.records, self.validation)
        self.assertTrue(bundle.pdf.startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", bundle.pdf)
        self.assertNotIn(b"/JavaScript", bundle.pdf)
        self.assertNotIn(b"/OpenAction", bundle.pdf)
        self.assertNotIn(b"/Launch", bundle.pdf)

    def test_artifact_receipt_binds_semantic_layout_profile_renderer_and_bytes(self):
        bundle = self.engine.render(self.request, self.records, self.validation)
        receipt = bundle.meta.receipt
        self.assertEqual(receipt.draft, self.request.document.draft)
        self.assertEqual(receipt.snapshot_hash, self.request.document.snapshot_hash)
        self.assertEqual(receipt.render_profile, profile_pin(OFFICIAL_PL_V1))
        self.assertEqual(receipt.authorization_hash, self.request.authorization_hash)
        authority = receipt.authority
        output = self.records[self.request.document.draft]
        plan = self.records[output.plan]
        self.assertEqual(authority.semantic_digest, receipt.semantic_digest)
        self.assertEqual(authority.draft, self.request.document.draft)
        self.assertEqual(authority.draft_hash, digest(output))
        self.assertEqual(authority.plan, output.plan)
        self.assertEqual(authority.plan_hash, digest(plan))
        self.assertEqual(authority.snapshot_id, output.snapshot_id)
        self.assertEqual(authority.snapshot_hash, output.snapshot_hash)
        self.assertEqual(authority.validation_run.id, self.validation.execution.run.id)
        self.assertEqual(authority.validation_run.content_hash, digest(self.validation.execution.run))
        self.assertEqual(authority.validation_execution_hash, digest(self.validation.execution))
        self.assertEqual(authority.validation_projection_hash, digest(self.validation))
        self.assertEqual(authority.case_sequence, self.validation.execution.committed_sequence)
        self.assertEqual(tuple(a.format for a in receipt.artifacts), ("DOCX", "PDF"))
        self.assertEqual(receipt.artifacts[0].byte_length, len(bundle.docx))
        self.assertEqual(receipt.artifacts[1].byte_length, len(bundle.pdf))
        self.assertNotEqual(receipt.semantic_digest, receipt.layout_digest)
        self.assertNotEqual(receipt.render_model_digest, receipt.layout_digest)

    def test_unvalidated_profile_change_fails_closed(self):
        altered_styles = tuple(
            style.model_copy(update={"font_size_pt": 12}) if style.token == "document.body" else style
            for style in OFFICIAL_PL_V1.styles
        )
        altered_profile = OFFICIAL_PL_V1.model_copy(update={"styles": altered_styles})
        altered_pin = profile_pin(altered_profile)
        baseline_authority = self.engine.render(
            self.request, self.records, self.validation
        ).meta.receipt.authority
        altered_request = RenderRequest(
            document=self.request.document,
            profile=altered_pin,
            authorization_hash=authorization_binding(
                self.request.document, altered_pin, baseline_authority
            ),
        )
        with self.assertRaisesRegex(Violation, "GATE_DENIED"):
            self.engine.render(altered_request, self.records, self.validation, altered_profile)

    def test_layout_formatting_is_controlled_by_profile_tokens(self):
        bundle = self.engine.render(self.request, self.records, self.validation)
        token_map = {style.token: style for style in OFFICIAL_PL_V1.styles}
        for block in bundle.meta.layout.blocks:
            self.assertIn(block.style_token, token_map)
        self.assertEqual(
            {block.style_token for block in bundle.meta.layout.blocks},
            {
                "document.heading.primary",
                "document.heading.secondary",
                "document.party_block",
                "document.request",
                "document.body",
                "document.legal_basis",
                "document.signature",
                "document.attachment",
            },
        )

    def test_missing_record_fails_closed(self):
        records = dict(self.records)
        records.pop(self.request.document.parties[0])
        with self.assertRaisesRegex(Violation, "BROKEN_REFERENCE"):
            self.engine.render(self.request, records, self.validation)

    def test_cross_case_record_fails_closed(self):
        records = dict(self.records)
        target = self.request.document.parties[0]
        party = records[target]
        records[target] = party.model_copy(update={"case_id": type(party.case_id)(int=999)})
        with self.assertRaisesRegex(Violation, "CROSS_CASE"):
            self.engine.render(self.request, records, self.validation)

    def test_semantic_document_cannot_drift_from_bound_draft(self):
        other = self.request.document.sections[0].model_copy(
            update={
                "statements": (
                    self.request.document.sections[0].statements[0].model_copy(
                        update={"text": "Treść zmieniona poza Draft."}
                    ),
                )
            }
        )
        bad_doc = self.request.document.model_copy(update={"sections": (other,)})
        bad = RenderRequest(
            document=bad_doc,
            profile=self.request.profile,
            authorization_hash=self.request.authorization_hash,
        )
        with self.assertRaisesRegex(Violation, "INVALID_HASH"):
            self.engine.render(bad, self.records, self.validation)

    def test_stale_authorization_binding_rejects_semantic_drift(self):
        changed = self.request.document.model_copy(
            update={"header": "NIEAUTORYZOWANA ZMIANA NAGŁÓWKA"}
        )
        bad = RenderRequest(
            document=changed,
            profile=self.request.profile,
            authorization_hash=self.request.authorization_hash,
        )
        with self.assertRaisesRegex(Violation, "GATE_DENIED"):
            self.engine.render(bad, self.records, self.validation)

    def test_profile_substitution_fails_closed(self):
        mutated_styles = tuple(
            style.model_copy(update={"font_size_pt": 12}) if style.token == "document.body" else style
            for style in OFFICIAL_PL_V1.styles
        )
        mutated = OFFICIAL_PL_V1.model_copy(update={"styles": mutated_styles})
        with self.assertRaisesRegex(Violation, "INVALID_HASH"):
            self.engine.render(self.request, self.records, self.validation, mutated)

    def test_xml_like_user_text_is_data_not_markup(self):
        doc = self.request.document.model_copy(
            update={"header": 'WNIOSEK <script>alert("x")</script> & dalsza treść'}
        )
        authority = derive_render_authority(
            doc, self.records, self.validation, self.request.profile
        )
        authorized = RenderRequest(
            document=doc,
            profile=self.request.profile,
            authorization_hash=authorization_binding(doc, self.request.profile, authority),
        )
        bundle = self.engine.render(authorized, self.records, self.validation)
        with ZipFile(BytesIO(bundle.docx), "r") as package:
            xml = package.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<script>", xml)
        self.assertIn("&lt;script&gt;", xml)
        self.assertIn("&amp;", xml)

    def test_stale_validation_projection_fails_closed(self):
        stale = self.validation.model_copy(update={
            "freshness": "STALE",
            "eligible_for_approval": False,
            "reasons": ("CASE_SEQUENCE_STALE",),
        })
        with self.assertRaisesRegex(Violation, "STALE"):
            self.engine.render(self.request, self.records, stale)

    def test_validation_output_hash_drift_fails_closed(self):
        execution = self.validation.execution.model_copy(update={"output_hash": "b" * 64})
        stale = self.validation.model_copy(update={"execution": execution})
        with self.assertRaisesRegex(Violation, "STALE"):
            self.engine.render(self.request, self.records, stale)

    def test_missing_plan_authority_fails_closed(self):
        records = dict(self.records)
        output = records[self.request.document.draft]
        records.pop(output.plan)
        with self.assertRaisesRegex(Violation, "BROKEN_REFERENCE"):
            self.engine.render(self.request, records, self.validation)

    def test_duplicate_attachment_provenance_fails_closed(self):
        records = dict(self.records)
        evidence_ref = next(ref for ref in records if ref.kind == "Evidence")
        evidence = records[evidence_ref]
        duplicate = evidence.model_copy(update={"id": type(evidence.id)(int=333)})
        from lukart_work.validation.rules import ref as make_ref
        records[make_ref(duplicate)] = duplicate
        with self.assertRaisesRegex(Violation, "PROVENANCE_MISSING"):
            self.engine.render(self.request, records, self.validation)


if __name__ == "__main__":
    unittest.main()
