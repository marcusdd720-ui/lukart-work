"""Focused transport coverage for the authorized PDF preview callback."""
import json
from threading import Thread
import unittest
from unittest.mock import Mock
from lukart_work.operator_host import create_server
from tests import test_operator_host as host_tests


class PdfPreviewTransportTests(unittest.TestCase):
    request=host_tests.OperatorHostTests.request
    headers=host_tests.OperatorHostTests.headers
    close=host_tests.OperatorHostTests.close

    def setUp(self):
        host_tests.OperatorHostTests.setUp(self)
        self.close()
        self.renderer=Mock(return_value={'kind':'LOCAL_PDF_PREVIEW','pages':[]})
        self.operator.query_finalization=Mock(return_value=b'%PDF-test-artifact')
        self.start(self.renderer)

    def start(self,renderer):
        self.server=create_server(self.operator,0,pdf_preview=renderer)
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def read(self,format='PDF',headers=None):
        return self.request(json.dumps({'operation':'ReadFinalArtifact','format':format}),
            headers if headers is not None else self.headers(Accept='application/vnd.lukart.local-pdf-preview+json'),
            '/api/query_finalization')

    def test_preview_runs_after_authenticated_artifact_read(self):
        status,body,_=self.read()
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['kind'],'LOCAL_PDF_PREVIEW')
        self.renderer.assert_called_once_with(b'%PDF-test-artifact')

    def test_missing_token_never_reads_or_renders(self):
        self.assertEqual(self.read(headers={'Content-Type':'application/json'})[0],403)
        self.operator.query_finalization.assert_not_called()
        self.renderer.assert_not_called()

    def test_original_pdf_download_without_preview_accept_is_unchanged(self):
        status,body,headers=self.read(headers=self.headers())
        self.assertEqual((status,body,headers['Content-Type']),
                         (200,b'%PDF-test-artifact','application/octet-stream'))
        self.renderer.assert_not_called()

    def test_docx_download_never_uses_pdf_renderer(self):
        self.operator.query_finalization.return_value=b'PK-test-docx'
        self.assertEqual(self.read('DOCX')[:2],(200,b'PK-test-docx'))
        self.renderer.assert_not_called()

    def test_non_pdf_bytes_fail_before_renderer(self):
        self.operator.query_finalization.return_value=b'not-pdf'
        self.assertEqual(self.read()[0],422)
        self.renderer.assert_not_called()

    def test_unconfigured_preview_is_explicit_and_download_remains_available(self):
        self.close();self.start(None)
        self.assertEqual(self.read()[:2],(503,b'{"error":"PDF_PREVIEW_NOT_CONFIGURED"}'))
        self.assertEqual(self.read(headers=self.headers())[:2],(200,b'%PDF-test-artifact'))

    def test_denied_query_result_is_not_rendered(self):
        from lukart_work.core.service import safe_error
        from uuid import UUID
        self.operator.query_finalization.return_value=safe_error('FORBIDDEN',UUID(int=0))
        self.assertEqual(json.loads(self.read()[1])['code'],'FORBIDDEN')
        self.renderer.assert_not_called()
