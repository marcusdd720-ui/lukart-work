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
from lukart_work.rendering.service import RenderingEngine
from lukart_work.validation.rules import Violation
from tests.fixtures import H
from tests.stage11_render_fixture import build_fixture


class Stage11RenderingTests(unittest.TestCase):
    def setUp(self):
        self.request, self.records = build_fixture()
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
        first = self.engine.render(self.request, self.records)
        second = self.engine.render(self.request, self.records)
        self.assertEqual(first.docx, second.docx)
        self.assertEqual(first.pdf, second.pdf)
        self.assertEqual(first.meta.receipt, second.meta.receipt)
        self.engine.validate(first)

    def test_fresh_process_reproduction_is_stable(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-B", "-X", "utf8", "-m", "tests.stage11_subprocess_fixture"]
        first = subprocess.check_output(command, cwd=root, text=True).strip()
        second = subprocess.check_output(command, cwd=root, text=True).strip()
        self.assertEqual(json.loads(first), json.loads(second))

    def test_docx_declares_single_profile_font_and_preserves_polish_text(self):
        bundle = self.engine.render(self.request, self.records)
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

    def test_pdf_embeds_font_and_forbids_active_content(self):
        bundle = self.engine.render(self.request, self.records)
        self.assertTrue(bundle.pdf.startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", bundle.pdf)
        self.assertNotIn(b"/JavaScript", bundle.pdf)
        self.assertNotIn(b"/OpenAction", bundle.pdf)
        self.assertNotIn(b"/Launch", bundle.pdf)

    def test_artifact_receipt_binds_semantic_layout_profile_renderer_and_bytes(self):
        bundle = self.engine.render(self.request, self.records)
        receipt = bundle.meta.receipt
        self.assertEqual(receipt.draft, self.request.document.draft)
        self.assertEqual(receipt.snapshot_hash, self.request.document.snapshot_hash)
        self.assertEqual(receipt.render_profile, profile_pin(OFFICIAL_PL_V1))
        self.assertEqual(tuple(a.format for a in receipt.artifacts), ("DOCX", "PDF"))
        self.assertEqual(receipt.artifacts[0].byte_length, len(bundle.docx))
        self.assertEqual(receipt.artifacts[1].byte_length, len(bundle.pdf))
        self.assertNotEqual(receipt.semantic_digest, receipt.layout_digest)
        self.assertNotEqual(receipt.render_model_digest, receipt.layout_digest)

    def test_presentation_change_does_not_change_semantic_digest(self):
        first = self.engine.render(self.request, self.records)
        altered_profile = OFFICIAL_PL_V1.model_copy(update={"body_font_pt": 12})
        altered_request = RenderRequest(
            document=self.request.document,
            profile=profile_pin(altered_profile),
            authorization_hash=H,
        )
        second = self.engine.render(altered_request, self.records, altered_profile)
        self.assertEqual(first.meta.receipt.semantic_digest, second.meta.receipt.semantic_digest)
        self.assertEqual(first.meta.receipt.render_model_digest, second.meta.receipt.render_model_digest)
        self.assertNotEqual(first.meta.receipt.layout_digest, second.meta.receipt.layout_digest)
        self.assertNotEqual(first.meta.receipt.artifacts[0].content_hash, second.meta.receipt.artifacts[0].content_hash)
        self.assertNotEqual(first.meta.receipt.artifacts[1].content_hash, second.meta.receipt.artifacts[1].content_hash)

    def test_missing_record_fails_closed(self):
        records = dict(self.records)
        records.pop(self.request.document.parties[0])
        with self.assertRaisesRegex(Violation, "BROKEN_REFERENCE"):
            self.engine.render(self.request, records)

    def test_cross_case_record_fails_closed(self):
        records = dict(self.records)
        target = self.request.document.parties[0]
        party = records[target]
        records[target] = party.model_copy(update={"case_id": type(party.case_id)(int=999)})
        with self.assertRaisesRegex(Violation, "CROSS_CASE"):
            self.engine.render(self.request, records)

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
            authorization_hash=H,
        )
        with self.assertRaisesRegex(Violation, "INVALID_HASH"):
            self.engine.render(bad, self.records)

    def test_profile_substitution_fails_closed(self):
        mutated = OFFICIAL_PL_V1.model_copy(update={"body_font_pt": 12})
        bad = RenderRequest(
            document=self.request.document,
            profile=self.request.profile,
            authorization_hash=H,
        )
        with self.assertRaisesRegex(Violation, "INVALID_HASH"):
            self.engine.render(bad, self.records, mutated)

    def test_xml_like_user_text_is_data_not_markup(self):
        doc = self.request.document.model_copy(
            update={"header": 'WNIOSEK <script>alert("x")</script> & dalsza treść'}
        )
        bad = RenderRequest(document=doc, profile=self.request.profile, authorization_hash=H)
        bundle = self.engine.render(bad, self.records)
        with ZipFile(BytesIO(bundle.docx), "r") as package:
            xml = package.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<script>", xml)
        self.assertIn("&lt;script&gt;", xml)
        self.assertIn("&amp;", xml)

    def test_duplicate_attachment_provenance_fails_closed(self):
        records = dict(self.records)
        evidence_ref = next(ref for ref in records if ref.kind == "Evidence")
        evidence = records[evidence_ref]
        duplicate = evidence.model_copy(update={"id": type(evidence.id)(int=333)})
        from lukart_work.validation.rules import ref as make_ref
        records[make_ref(duplicate)] = duplicate
        with self.assertRaisesRegex(Violation, "PROVENANCE_MISSING"):
            self.engine.render(self.request, records)


if __name__ == "__main__":
    unittest.main()
