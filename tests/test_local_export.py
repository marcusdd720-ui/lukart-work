"""Local artifact export uses persisted bytes and preserves scoped denials."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from lukart_work.contracts.messages import DomainError
from lukart_work.operator import GeneratorPismOperator
from lukart_work.rendering.local import export_local
from lukart_work.rendering.service import RenderingEngine
from tests.stage11_render_fixture import build_fixture


class LocalExportTests(unittest.TestCase):
    def test_exact_bytes_preview_and_no_overwrite(self):
        request, records, validation = build_fixture()
        bundle = RenderingEngine().render(request, records, validation)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "document"
            preview = export_local(bundle.docx, bundle.pdf, directory)
            self.assertEqual((directory / "document.docx").read_bytes(), bundle.docx)
            self.assertEqual((directory / "document.pdf").read_bytes(), bundle.pdf)
            self.assertIn('data="document.pdf"', preview.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                export_local(bundle.docx, bundle.pdf, directory)

    def test_invalid_artifact_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "document"
            with self.assertRaises(Exception):
                export_local(b"invalid", b"invalid", directory)
            self.assertFalse(directory.exists())

    def test_denied_scoped_read_writes_nothing(self):
        from lukart_work.core.service import safe_error
        from uuid import UUID
        denied = safe_error("FORBIDDEN", UUID(int=0))
        operator = GeneratorPismOperator.__new__(GeneratorPismOperator)
        operator.finalization = Mock()
        operator.finalization.query.return_value = denied
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "document"
            result = operator.export_local(tenant_id=UUID(int=1), case_id=UUID(int=2),
                render_id=UUID(int=3), token="denied", output=directory)
            self.assertIsInstance(result, DomainError)
            self.assertEqual(result.code, "FORBIDDEN")
            self.assertFalse(directory.exists())
