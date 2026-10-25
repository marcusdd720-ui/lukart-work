"""Synthetic PDF coverage and admission regressions; no database or OCR service."""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from pypdf import PdfReader, PdfWriter

from lukart_work.domain.models import Actor, VersionPin
from lukart_work.facts.service import FactEvidenceService
from lukart_work.ingestion.extract import extract
from lukart_work.ingestion.models import IngestionResult
from lukart_work.ingestion.service import IngestionService, parse_isolated
from lukart_work.validation.rules import Violation, digest
from tests.test_stage04 import pdf


def mixed_pdf():
    writer = PdfWriter()
    writer.add_page(PdfReader(BytesIO(pdf())).pages[0])
    writer.add_blank_page(width=300, height=300)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class CompletenessTests(TestCase):
    def test_mixed_pdf_without_ocr_is_not_admissible_as_extracted(self):
        for parser in (extract, parse_isolated):
            with self.subTest(parser=parser.__name__):
                body = parser(mixed_pdf(), 'application/pdf')
                self.assertEqual(body.status, 'NEEDS_OCR')
                self.assertIn('OCR_REQUIRED', body.warnings)
                self.assertFalse(body.fragments)
                self.assertFalse(body.candidates)

    def test_incomplete_ocr_cannot_make_mixed_pdf_admissible(self):
        engine = Mock()
        engine.pdf_page.return_value = ''
        engine.pin = VersionPin(id='synthetic-ocr', version='1', content_hash='a' * 64)
        with patch('lukart_work.ingestion.ocr.LocalOCR', return_value=engine):
            body = extract(mixed_pdf(), 'application/pdf', object())
        self.assertEqual(body.status, 'NEEDS_OCR')
        self.assertFalse(body.candidates)

    def test_complete_mixed_pdf_preserves_original_page_numbers(self):
        engine = Mock()
        engine.pdf_page.return_value = 'Synthetic image-only page content'
        engine.pin = VersionPin(id='synthetic-ocr', version='1', content_hash='a' * 64)
        with patch('lukart_work.ingestion.ocr.LocalOCR', return_value=engine):
            body = extract(mixed_pdf(), 'application/pdf', object())
        self.assertEqual(body.status, 'EXTRACTED')
        self.assertNotIn('OCR_REQUIRED', body.warnings)
        self.assertEqual([f.position for f in body.fragments], ['1', '2'])
        self.assertEqual([f.extraction_method for f in body.fragments], ['TEXT', 'OCR'])

    def test_legacy_incomplete_result_is_denied_without_mutating_history(self):
        # Historical immutable results may contain text and OCR_REQUIRED together.
        body = extract(pdf(), 'application/pdf')
        body = body.model_copy(update={'warnings': (*body.warnings, 'OCR_REQUIRED')})
        pin = VersionPin(id='synthetic', version='1', content_hash='a' * 64)
        result = IngestionResult(contract='urn:lukart:work:IngestionResult:1.0.0',
            tenant_id=uuid4(), case_id=uuid4(), run_id=uuid4(), source_id=uuid4(),
            source_hash=sha256(pdf()).hexdigest(), source_byte_length=len(pdf()),
            actor=Actor(id=uuid4(), kind='HUMAN'), recorded_at=datetime.now(timezone.utc),
            extractor=pin, parser=pin, python_version='synthetic', body_hash=digest(body), body=body)
        before = result.model_dump_json()
        service = FactEvidenceService(Mock(), Mock())
        with patch.object(IngestionService, '_read', return_value=result):
            with self.assertRaisesRegex(Violation, 'GATE_DENIED'):
                service._extraction(Mock(), result.source_id, result.run_id, digest(result))
        self.assertEqual(result.model_dump_json(), before)
