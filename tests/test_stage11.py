"""Stage 11 rendering assurance: deterministic, semantic-preserving, fail-closed output."""
import unittest
from hashlib import sha256
from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

from pypdf import PdfReader

from lukart_work.contracts.messages import RenderRequest, SemanticDocument
from lukart_work.domain.models import Ref, SectionText, Statement
from lukart_work.rendering import RenderEngine, RenderError, authorization_binding, court_pl_profile
from lukart_work.validation.rules import digest


def uid(value):
    return UUID(int=value)


def semantic_document(header="Syntetyczne pismo – Łódź"):
    factual = Statement(
        id=uid(100), text="Zażółć gęślą jaźń.", statement_type="FACTUAL",
        support="SOURCE_BACKED", refs=(Ref(kind="Fact", id=uid(10), revision=2),), citations=(),
    )
    request = Statement(
        id=uid(101), text="Wnoszę o uwzględnienie syntetycznego żądania.",
        statement_type="REQUEST", support="SOURCE_BACKED",
        refs=(Ref(kind="Request", id=uid(11), revision=1),), citations=(),
    )
    return SemanticDocument(
        tenant_id=uid(900), case_id=uid(901),
        draft=Ref(kind="Draft", id=uid(20), revision=3),
        snapshot_hash="a" * 64, header=header,
        parties=(Ref(kind="Party", id=uid(1), revision=1),),
        requests=(Ref(kind="Request", id=uid(11), revision=1),),
        sections=(SectionText(
            section=Ref(kind="Section", id=uid(30), revision=1),
            statements=(factual, request),
        ),),
        attachments=(), signature_party=Ref(kind="Party", id=uid(1), revision=1),
    )


def render_request(document=None):
    document = document or semantic_document()
    profile = court_pl_profile()
    auth = authorization_binding(document, profile)
    return RenderRequest(document=document, profile=profile, authorization_hash=auth), auth


class Stage11RenderingTests(unittest.TestCase):
    def setUp(self):
        self.engine = RenderEngine()

    def test_stage11_all_formats_are_bound_and_semantic_preserving(self):
        request, auth = render_request()
        result = self.engine.render(request, expected_authorization_hash=auth,
                                    formats=("DOCX", "PDF", "HTML", "TXT"))
        self.assertEqual(result.record.semantic_hash, digest(request.document))
        self.assertEqual([a.format for a in result.record.artifacts], ["DOCX", "PDF", "HTML", "TXT"])
        for artifact in result.record.artifacts:
            data = result.bytes_by_format[artifact.format]
            self.assertEqual(artifact.content_hash, sha256(data).hexdigest())
            self.assertEqual(artifact.byte_length, len(data))
            self.assertEqual(artifact.semantic_hash, result.record.semantic_hash)
        self.assertTrue(result.bytes_by_format["PDF"].startswith(b"%PDF-"))
        self.assertTrue(result.bytes_by_format["DOCX"].startswith(b"PK"))

    def test_stage11_unicode_polish_roundtrips_pdf(self):
        request, auth = render_request()
        result = self.engine.render(request, expected_authorization_hash=auth, formats=("PDF",))
        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(result.bytes_by_format["PDF"])).pages)
        self.assertIn("Syntetyczne pismo – Łódź", text)
        self.assertIn("Zażółć gęślą jaźń.", text)

    def test_stage11_docx_is_a4_with_binder_margin_and_no_semantic_invention(self):
        request, auth = render_request()
        result = self.engine.render(request, expected_authorization_hash=auth, formats=("DOCX",))
        with ZipFile(BytesIO(result.bytes_by_format["DOCX"])) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn('w:pgSz w:w="11906" w:h="16838"', xml)
        self.assertIn('w:left="1700"', xml)
        self.assertIn('w:right="1133"', xml)
        self.assertNotIn("FINAL", xml)
        self.assertNotIn("CERTIFIED", xml)

    def test_stage11_html_escapes_untrusted_text_and_has_no_active_content(self):
        request, auth = render_request(semantic_document("<script>alert(1)</script>"))
        result = self.engine.render(request, expected_authorization_hash=auth, formats=("HTML",))
        html = result.bytes_by_format["HTML"].decode("utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("javascript:", html.lower())

    def test_stage11_bytes_are_deterministic_for_same_input(self):
        request, auth = render_request()
        first = self.engine.render(request, expected_authorization_hash=auth, formats=("DOCX", "PDF", "HTML", "TXT"))
        second = self.engine.render(request, expected_authorization_hash=auth, formats=("DOCX", "PDF", "HTML", "TXT"))
        self.assertEqual(first.bytes_by_format, second.bytes_by_format)
        self.assertEqual(first.record, second.record)

    def test_stage11_rejects_wrong_authorization(self):
        request, auth = render_request()
        with self.assertRaisesRegex(RenderError, "RENDER_AUTHORIZATION_MISMATCH"):
            self.engine.render(request, expected_authorization_hash="b" * 64)

    def test_stage11_rejects_self_consistent_but_untrusted_authorization(self):
        request, _ = render_request()
        forged = request.model_copy(update={"authorization_hash": "b" * 64})
        with self.assertRaisesRegex(RenderError, "RENDER_AUTHORIZATION_INVALID"):
            self.engine.render(forged, expected_authorization_hash="b" * 64)

    def test_stage11_rejects_unknown_profile(self):
        request, _ = render_request()
        altered = request.profile.model_copy(update={"version": "9.9.9"})
        forged = request.model_copy(update={
            "profile": altered,
            "authorization_hash": authorization_binding(request.document, altered),
        })
        with self.assertRaisesRegex(RenderError, "UNKNOWN_RENDER_PROFILE"):
            self.engine.render(forged, expected_authorization_hash=forged.authorization_hash)

    def test_stage11_rejects_duplicate_or_unknown_formats(self):
        request, auth = render_request()
        for formats in ((), ("PDF", "PDF"), ("SVG",)):
            with self.subTest(formats=formats):
                with self.assertRaisesRegex(RenderError, "RENDER_FORMAT_INVALID"):
                    self.engine.render(request, expected_authorization_hash=auth, formats=formats)

    def test_stage11_rendering_does_not_mutate_semantic_document(self):
        request, auth = render_request()
        before = request.document.model_dump_json()
        self.engine.render(request, expected_authorization_hash=auth, formats=("PDF", "DOCX"))
        self.assertEqual(request.document.model_dump_json(), before)


if __name__ == "__main__":
    unittest.main()
