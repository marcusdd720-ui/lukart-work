"""Stage 11 pure rendering assurance: no database and no private CASE material."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from lukart_work.domain.models import Ref
from lukart_work.rendering.adapters import render_docx, render_format, render_pdf
from lukart_work.rendering.compiler import compile_render_tree
from lukart_work.rendering.contracts import (
    RenderProfile,
    SemanticBlock,
    SemanticDocumentV2,
)
from lukart_work.rendering.policy import (
    official_pl_profile,
    profile_pin,
    renderer_pin,
)
from lukart_work.validation.rules import digest


class Stage11RenderingTests(unittest.TestCase):
    def document(self):
        draft = Ref(kind="Draft", id=uuid4(), revision=3)
        blocks = (
            SemanticBlock(
                id=uuid4(),
                role="document.heading.primary",
                text="Wniosek o ponowne rozpatrzenie sprawy",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.metadata",
                text="Sygnatura testowa",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.heading.secondary",
                text="Uzasadnienie",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.body",
                text="Zażółć gęślą jaźń. Materiał dowodowy potwierdza wskazaną okoliczność.",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.legal_basis",
                text="Podstawa prawna została wskazana w zweryfikowanym materiale źródłowym.",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.request",
                text="Wnoszę o ponowne rozpatrzenie sprawy.",
                source_refs=(draft,),
            ),
            SemanticBlock(
                id=uuid4(),
                role="document.signature",
                text="Jan Testowy",
                source_refs=(draft,),
            ),
        )
        return SemanticDocumentV2(
            schema_version="1.0.0",
            tenant_id=uuid4(),
            case_id=uuid4(),
            draft=draft,
            draft_hash="1" * 64,
            snapshot_hash="2" * 64,
            title="Wniosek",
            blocks=blocks,
        )

    def test_profile_is_complete_content_addressed_and_strict(self):
        profile = official_pl_profile()
        self.assertEqual(digest(profile), profile_pin().content_hash)
        self.assertEqual(len(profile.styles), 11)
        broken = profile.model_dump(mode="json")
        broken["styles"] = broken["styles"][:-1]
        with self.assertRaises(ValueError):
            RenderProfile.model_validate(broken)

    def test_render_tree_is_deterministic_and_semantics_are_preserved(self):
        document = self.document()
        profile = official_pl_profile()
        first = compile_render_tree(document, profile)
        second = compile_render_tree(document, profile)
        self.assertEqual(first, second)
        self.assertEqual(first.semantic_digest, digest(document))
        self.assertEqual(first.profile_digest, digest(profile))
        self.assertEqual(
            [block.text for block in first.blocks],
            [block.text for block in document.blocks],
        )
        self.assertEqual(
            [block.source_refs for block in first.blocks],
            [block.source_refs for block in document.blocks],
        )

    def test_docx_is_byte_deterministic_and_normalized(self):
        tree = compile_render_tree(self.document(), official_pl_profile())
        one = render_docx(tree, official_pl_profile())
        two = render_docx(tree, official_pl_profile())
        self.assertEqual(one, two)
        self.assertTrue(one.data.startswith(b"PK"))
        self.assertEqual(one.resource_hashes, ())
        self.assertEqual(
            one.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with ZipFile(BytesIO(one.data), "r") as archive:
            names = archive.namelist()
            self.assertEqual(names, sorted(names))
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))
            styles = archive.read("word/styles.xml")
            self.assertIn(b"LW_00_document_body", styles)
            core = archive.read("docProps/core.xml")
            self.assertIn(b"2000-01-01T00:00:00Z", core)

    def test_pdf_is_byte_deterministic_and_binds_font_resources(self):
        tree = compile_render_tree(self.document(), official_pl_profile())
        one = render_pdf(tree, official_pl_profile())
        two = render_pdf(tree, official_pl_profile())
        self.assertEqual(one, two)
        self.assertTrue(one.data.startswith(b"%PDF-"))
        self.assertEqual(one.media_type, "application/pdf")
        self.assertEqual(len(one.resource_hashes), 4)
        self.assertTrue(all(len(value) == 64 for value in one.resource_hashes))
        self.assertEqual(
            sha256(one.data).hexdigest(),
            sha256(two.data).hexdigest(),
        )

    def test_missing_approved_font_fails_closed(self):
        tree = compile_render_tree(self.document(), official_pl_profile())
        with patch("lukart_work.rendering.adapters._candidate_roots", return_value=()):
            with self.assertRaisesRegex(ValueError, "APPROVED_FONT_UNAVAILABLE"):
                render_pdf(tree, official_pl_profile())

    def test_unsupported_format_is_rejected(self):
        tree = compile_render_tree(self.document(), official_pl_profile())
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_FORMAT"):
            render_format("HTML", tree, official_pl_profile())

    def test_renderer_identity_is_stable_and_source_bound(self):
        first = renderer_pin()
        second = renderer_pin()
        self.assertEqual(first, second)
        self.assertEqual(len(first.content_hash), 64)


if __name__ == "__main__":
    unittest.main()
