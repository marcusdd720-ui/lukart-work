"""Explicit native OCR acceptance suite; run with scripts/verify_ocr_intake.py.

Separate from legacy unittest discovery: the dedicated CI gate supplies native
Polish OCR and a disposable database, and treats every skip as failure.
"""
import base64
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4, uuid5

from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.domain.models import Actor
from lukart_work.ingestion.extract import extract
from lukart_work.ingestion.models import ExtractionBody
from lukart_work.ingestion.ocr import OCRConfig, LocalOCR
from lukart_work.ingestion.service import parse_isolated
from lukart_work.operator_ingestion import upload, query
from lukart_work.validation.rules import digest


def scan(text='Zażółć gęślą jaźń.\nPowód: Jan Testowy\nWpłata 100 PLN dnia 2026-10-20.'):
    import fontpkg
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1600, 500), 'white')
    ImageDraw.Draw(image).multiline_text((70, 70), text,
        font=ImageFont.truetype(fontpkg.path('Lato', weight=400, style='normal'), 48),
        fill='black', spacing=24)
    stream = BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


class OCRContractTests(unittest.TestCase):
    def test_legacy_body_serialization_and_hash_are_unchanged(self):
        body = extract('Powód: Jan Testowy'.encode(), 'text/plain')
        value = body.model_dump(mode='json')
        self.assertNotIn('ocr_engine', value)
        self.assertNotIn('extraction_method', value['fragments'][0])
        self.assertEqual(digest(ExtractionBody.model_validate_json(json.dumps(value))), digest(value))

    def test_ocr_requires_engine_and_page_provenance(self):
        value = extract(b'synthetic', 'text/plain').model_dump(mode='json')
        value['fragments'][0]['extraction_method'] = 'OCR'
        with self.assertRaises(ValueError):
            ExtractionBody.model_validate_json(json.dumps(value))

    def test_missing_model_fails_before_starting_a_process(self):
        with patch('lukart_work.ingestion.ocr.subprocess.run') as run:
            with self.assertRaises(ValueError):
                OCRConfig('/missing/tesseract', '/missing/model', '/missing/rasterizer').pin()
        run.assert_not_called()

    def test_text_pdf_never_initializes_ocr(self):
        from tests.test_stage04 import pdf
        with patch('lukart_work.ingestion.ocr.LocalOCR', side_effect=AssertionError('unnecessary OCR')):
            self.assertEqual(extract(pdf(), 'application/pdf', object()).status, 'EXTRACTED')

    def test_pixel_limit_and_timeout_are_enforced(self):
        with self.assertRaises(ValueError):
            LocalOCR._check_image(SimpleNamespace(width=100000, height=100000))
        engine = LocalOCR.__new__(LocalOCR)
        engine.deadline = -1
        with patch('lukart_work.ingestion.ocr.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'OCR_TIMEOUT'):
                engine._run(['unused'])
        run.assert_not_called()

    def test_pillow_preprocessor_changes_the_ocr_pin(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('tesseract', 'pol.traineddata', 'pdftoppm', 'decoder.py', 'libjpeg.so.62.4.0'):
                (root / name).write_bytes(b'synthetic-version-one')
            distribution = SimpleNamespace(version='12.3.0',
                files=(Path('PIL/decoder.py'),Path('pillow.libs/libjpeg.so.62.4.0')),
                locate_file=lambda name: root / Path(name).name)
            config = OCRConfig(str(root/'tesseract'), str(root), str(root/'pdftoppm'))
            with patch('lukart_work.ingestion.ocr.importlib.metadata.distribution', return_value=distribution):
                before = config.pin()
                (root/'decoder.py').write_bytes(b'synthetic-version-two')
                decoded = config.pin()
                self.assertNotEqual(before, decoded)
                (root/'libjpeg.so.62.4.0').write_bytes(b'synthetic-version-two')
                self.assertNotEqual(decoded,config.pin())
                distribution.files=()
                with self.assertRaisesRegex(ValueError,'OCR_PILLOW_PROVENANCE_REQUIRED'):
                    config.pin()


class IntakeBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for browser contract')
    def test_candidate_review_is_prepared_with_exact_result_hash_without_dispatch(self):
        from datetime import datetime, timezone
        from lukart_work.ingestion.models import IngestionResult
        from lukart_work.operator_host import CLIENT
        from lukart_work.facts.contracts import FactEvidenceRequest
        body = extract('Syntetyczna wpłata 100 PLN.'.encode(), 'text/plain')
        result = IngestionResult(contract='urn:lukart:work:IngestionResult:1.0.0',
            tenant_id=uuid4(), case_id=uuid4(), source_id=uuid4(), run_id=uuid4(), source_hash='b'*64,
            source_byte_length=30, actor=Actor(id=uuid4(),kind='HUMAN'), recorded_at=datetime.now(timezone.utc),
            extractor=dict(id='synthetic',version='1.0.0',content_hash='a'*64),
            parser=dict(id='synthetic',version='1.0.0',content_hash='a'*64),python_version='3.14.7',
            body_hash=digest(body),body=body)
        harness = r'''
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto'),elements=new Map();let calls=0;
const document={getElementById(id){if(!elements.has(id))elements.set(id,{
value:'',append(option){if(!this.value)this.value=option.value;},removeAttribute(){},replaceChildren(){this.value='';}});return elements.get(id);},createElement(){return {};}};
const ctx={document,window:{addEventListener(){}},crypto:{randomUUID:crypto.randomUUID,subtle:crypto.webcrypto.subtle},
TextEncoder,fetch(){calls++;},URL:{revokeObjectURL(){}}};
vm.runInNewContext(fs.readFileSync(0,'utf8'),ctx);
const value=JSON.parse(process.env.SYNTHETIC_EXTRACTION),el=id=>document.getElementById(id);
el('tenant').value=value.tenant_id;el('case').value=value.case_id;el('caseSequence').value='2';
ctx.handleIntakeResult('query_ingestion',{},value);
el('candidateRationale').value='Odrzucam syntetyczny przykład po porównaniu ze źródłem';
el('candidateDisposition').value='REJECT';
el('prepareReview').onclick().then(()=>{
 if(calls)throw Error('AUTOMATIC_REVIEW');
 process.stdout.write(el('request').value);
}).catch(e=>{process.stderr.write(String(e));process.exitCode=1;});
'''
        process = subprocess.run([shutil.which('node'), '-e', harness], input=CLIENT.decode(),
            env=dict(os.environ,SYNTHETIC_EXTRACTION=result.model_dump_json()), capture_output=True,
            text=True, timeout=15, check=True)
        request = FactEvidenceRequest.model_validate_json(process.stdout)
        self.assertEqual(request.data.result_hash, digest(result))
        self.assertEqual(request.data.disposition, 'REJECT')
        self.assertEqual(request.meta.expected_case_sequence, 2)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for browser contract')
    def test_prepare_requires_confirmation_and_context_change_drops_pending_upload(self):
        from lukart_work.operator_host import CLIENT
        harness = r'''
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const elements=new Map(),calls=[];let resolve;
const document={getElementById(id){if(!elements.has(id))elements.set(id,{
value:'',append(){},removeAttribute(){},replaceChildren(){}});return elements.get(id);},createElement(){return {};}};
const ctx={document,window:{addEventListener(){}},crypto,
fetch:(url,options)=>{calls.push({url,options});return new Promise(r=>{resolve=r;});},
URL:{revokeObjectURL(){}},btoa:s=>Buffer.from(s,'binary').toString('base64')};
vm.runInNewContext(fs.readFileSync(0,'utf8'),ctx);
const el=id=>document.getElementById(id),tenant='00000000-0000-0000-0000-000000000001',caseId='00000000-0000-0000-0000-000000000002';
(async()=>{
el('tenant').value=tenant;el('case').value=caseId;el('caseTitle').value='Sprawa syntetyczna';
el('policyId').value='synthetic';el('policyVersion').value='1.0.0';el('policyHash').value='a'.repeat(64);
el('token').value='private-test-capability';
el('prepareCase').onclick();if(calls.length)throw Error('AUTOMATIC_CREATE');
const prepared=JSON.parse(el('request').value);
el('confirmCase').onclick();if(calls.length!==1)throw Error('EXPLICIT_CREATE_MISSING');
resolve({ok:true,status:200,headers:{get(){return 'application/json';}},text:async()=>JSON.stringify({state:'APPLIED',case_sequence:1})});
await new Promise(setImmediate);
if(el('caseSequence').value!=='1')throw Error('SEQUENCE_MISSING');
el('sourceFile').value='selected';el('sourceFile').files=[{size:3,type:'text/plain',name:'source.txt',arrayBuffer:async()=>new Uint8Array([97,98,99]).buffer}];
const pending=el('uploadSource').onclick();await new Promise(setImmediate);
if(calls.length!==2||calls[1].url!=='/api/upload_source')throw Error('UPLOAD_MISSING');
const sent=JSON.parse(calls[1].options.body);
el('tenant').value='00000000-0000-0000-0000-000000000003';el('tenant').oninput();
resolve({ok:true,status:200,headers:{get(){return 'application/json';}},text:async()=>JSON.stringify({source_id:'stale',run_id:'stale',ingestion:{body:{status:'EXTRACTED'}}})});
await pending;
for(const id of ['sourceId','ingestionId','caseSequence','sourceFile'])if(el(id).value!=='')throw Error('STALE_'+id);
if(el('result').textContent!=='')throw Error('STALE_RESULT');
process.stdout.write(JSON.stringify({prepared,sent,credentials:calls.map(x=>x.options.credentials)}));
})().catch(e=>{process.stderr.write(String(e));process.exitCode=1;});
'''
        process = subprocess.run([shutil.which('node'), '-e', harness], input=CLIENT.decode(),
            capture_output=True, text=True, timeout=15, check=True)
        result = json.loads(process.stdout)
        from lukart_work.core.requests import CoreRequest
        from lukart_work.operator_ingestion import UploadRequest
        self.assertEqual(CoreRequest.model_validate_json(json.dumps(result['prepared'])).operation, 'CreateCase')
        self.assertEqual(UploadRequest.model_validate_json(json.dumps(result['sent'])).request.operation, 'RegisterSource')
        self.assertEqual(result['credentials'], ['omit', 'omit'])


class UploadAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case = uuid4(), uuid4()
        self.authority = TokenAuthority()
        self.token = self.authority.provision(Principal(Actor(id=uuid4(), kind='HUMAN'),
            self.tenant, self.case, frozenset({'RegisterSource', 'IngestSource', 'ReadIngestion'})))
        self.operator = SimpleNamespace(core=SimpleNamespace(authority=self.authority, execute=Mock()),
                                        ingestion=SimpleNamespace(ingest=Mock(), read=Mock()))
        self.request = dict(operation='UploadAndIngest', run_id=str(uuid4()), request=dict(
            contract='urn:lukart:work:CoreRequest:1.0.0', operation='RegisterSource',
            meta=dict(command_id=str(uuid4()), tenant_id=str(self.tenant), case_id=str(self.case),
                expected_case_sequence=1, idempotency_key=str(uuid4()), correlation_id=str(uuid4())),
            data=dict(content_base64=base64.b64encode(b'synthetic').decode(), media_type='text/plain',
                retention_policy=dict(id='synthetic', version='1.0.0', content_hash='a'*64))))

    def test_foreign_scope_and_missing_ingest_permission_do_not_write(self):
        self.request['request']['meta']['case_id'] = str(uuid4())
        self.assertEqual(upload(self.operator, self.request, self.token).code, 'FORBIDDEN')
        self.request['request']['meta']['case_id'] = str(self.case)
        token = self.authority.provision(Principal(Actor(id=uuid4(), kind='HUMAN'),
            self.tenant, self.case, frozenset({'RegisterSource'})))
        self.assertEqual(upload(self.operator, self.request, token).code, 'FORBIDDEN')
        self.operator.core.execute.assert_not_called()

    def test_ai_and_revoked_tokens_do_not_write(self):
        token = self.authority.provision(Principal(Actor(id=uuid4(), kind='AI'), self.tenant,
            self.case, frozenset({'RegisterSource', 'IngestSource'})))
        self.assertEqual(upload(self.operator, self.request, token).code, 'FORBIDDEN')
        self.authority.revoke(self.token)
        self.assertEqual(upload(self.operator, self.request, self.token).code, 'FORBIDDEN')
        self.operator.core.execute.assert_not_called()

    def test_composition_cannot_execute_createcase_or_accept_ocr_configuration(self):
        self.request['request']['operation'] = 'CreateCase'
        self.assertEqual(upload(self.operator, self.request, self.token).code, 'SCHEMA_INVALID')
        self.request['request']['operation'] = 'RegisterSource'
        self.request['ocr'] = {'tesseract': 'untrusted'}
        self.assertEqual(upload(self.operator, self.request, self.token).code, 'SCHEMA_INVALID')
        self.operator.core.execute.assert_not_called()

    def test_registration_failure_never_starts_ingestion(self):
        from lukart_work.core.service import safe_error
        self.operator.core.execute.return_value = safe_error('CONFLICT', uuid4())
        self.assertEqual(upload(self.operator, self.request, self.token).code, 'CONFLICT')
        self.operator.ingestion.ingest.assert_not_called()

    def test_query_rejects_foreign_scope_before_ingestion(self):
        value = dict(operation='ReadIngestion', tenant_id=str(self.tenant), case_id=str(uuid4()),
                     source_id=str(uuid4()), run_id=str(uuid4()))
        self.assertEqual(query(self.operator, value, self.token).code, 'FORBIDDEN')
        self.operator.ingestion.read.assert_not_called()


@unittest.skipUnless(os.environ.get('LUKART_OCR_TEST_CONFIG'), 'Explicit local OCR binaries/model required')
class OCRRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = OCRConfig(**json.loads(Path(os.environ['LUKART_OCR_TEST_CONFIG']).read_text()))

    def test_single_frame_jpeg_without_n_frames_is_extracted(self):
        from PIL import Image
        stream = BytesIO()
        with Image.open(BytesIO(scan())) as image:
            image.save(stream, format='JPEG', quality=95)
        data = stream.getvalue()
        with Image.open(BytesIO(data)) as image:
            self.assertFalse(hasattr(image, 'n_frames'))
        body = parse_isolated(data, 'image/jpeg', self.config)
        self.assertEqual(body.status, 'EXTRACTED', body)
        self.assertEqual(len(body.fragments), 1)
        self.assertIn('Zażółć gęślą jaźń', body.fragments[0].text)
        self.assertEqual(body.fragments[0].position, '1')
        self.assertEqual(body.fragments[0].extraction_method, 'OCR')
        self.assertEqual(body.ocr_engine, self.config.pin())

    def test_multipage_tiff_preserves_frames_and_page_limit(self):
        from PIL import Image
        from lukart_work.ingestion.ocr import MAX_PAGES
        with Image.open(BytesIO(scan())) as image:
            stream = BytesIO()
            image.save(stream, format='TIFF', save_all=True, append_images=[image.copy()])
        rows = LocalOCR(self.config).image(stream.getvalue())
        self.assertEqual([row[:2] for row in rows], [('PAGE', '1'), ('PAGE', '2')])
        self.assertTrue(all('Zażółć gęślą jaźń' in row[2] for row in rows))
        tiny = Image.new('RGB', (1, 1), 'white')
        stream = BytesIO()
        tiny.save(stream, format='TIFF', save_all=True, append_images=[tiny] * MAX_PAGES)
        with patch.object(LocalOCR, '_text', side_effect=AssertionError('over-limit OCR')):
            with self.assertRaisesRegex(ValueError, 'OCR_IMAGE_LIMIT'):
                LocalOCR(self.config).image(stream.getvalue())

    def test_real_polish_scan_automatically_becomes_unverified_candidates(self):
        data = scan()
        before = sha256(data).hexdigest()
        body = parse_isolated(data, 'image/png', self.config)
        self.assertEqual(body.status, 'EXTRACTED', body)
        self.assertIn('Zażółć gęślą jaźń', body.fragments[0].text)
        self.assertEqual(body.fragments[0].extraction_method, 'OCR')
        self.assertEqual(body.fragments[0].position, '1')
        self.assertEqual(body.ocr_engine, self.config.pin())
        self.assertTrue(body.candidates)
        self.assertTrue(all(c.status == 'CANDIDATE' for c in body.candidates))
        self.assertIn('REVIEW_REQUIRED', body.warnings)
        self.assertEqual(before, sha256(data).hexdigest())

    def test_mixed_multipage_pdf_retains_page_numbers_and_text_layer(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import ImageReader
        output = BytesIO()
        canvas = Canvas(output, pagesize=(800, 500))
        canvas.drawString(40, 440, 'Tekst istniejacy 200 PLN')
        canvas.showPage()
        canvas.drawImage(ImageReader(BytesIO(scan())), 0, 250, width=800, height=250)
        canvas.showPage()
        canvas.save()
        body = parse_isolated(output.getvalue(), 'application/pdf', self.config)
        self.assertEqual(body.status, 'EXTRACTED', body)
        self.assertEqual([f.position for f in body.fragments], ['1', '2'])
        self.assertEqual([f.extraction_method for f in body.fragments], ['TEXT', 'OCR'])
        self.assertIn('Tekst istniejacy', body.fragments[0].text)
        self.assertIn('Zażółć', body.fragments[1].text)

    def test_corrupted_scan_and_oversize_geometry_fail_closed(self):
        self.assertEqual(parse_isolated(b'\x89PNG\r\n\x1a\n', 'image/png', self.config).status, 'FAILED')
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=20000, height=20000)
        stream = BytesIO()
        writer.write(stream)
        body = parse_isolated(stream.getvalue(), 'application/pdf', self.config)
        self.assertEqual(body.status, 'FAILED')
        self.assertFalse(body.candidates)


@unittest.skipUnless(os.environ.get('LUKART_TEST_DSN') and os.environ.get('LUKART_TEST_ADMIN_DSN')
                     and os.environ.get('LUKART_OCR_TEST_CONFIG'), 'Explicit isolated PostgreSQL and OCR required')
class IntakePostgresTests(unittest.TestCase):
    """Authorized synthetic HUMAN fixtures; no legal decisions or FINAL approval."""
    @classmethod
    def setUpClass(cls):
        from tests import test_stage02 as core
        from psycopg.conninfo import conninfo_to_dict
        import psycopg
        from lukart_work.storage.migrations import migrate, grant_runtime
        database = conninfo_to_dict(core.DSN).get('dbname', '')
        if not database.startswith('lukart_ocr_acceptance_'):
            raise RuntimeError('EXPLICIT_DISPOSABLE_OCR_DATABASE_REQUIRED')
        cls.dsn, cls.admin = core.DSN, core.ADMIN_RUNTIME
        with psycopg.connect(cls.admin) as connection:
            migrate(connection)
            grant_runtime(connection, 'lw_core_runtime')

    def setUp(self):
        from tests.test_stage03 import Stage03Tests
        from tests.test_operator_config import OperatorConfigTests
        from lukart_work.operator_config import build_operator
        fixture = Stage03Tests()
        fixture.dsn, fixture.admin = self.dsn, self.admin
        fixture.setUp()
        self.h = fixture
        self.tenant, self.case_id = fixture.tenant, uuid4()
        self.authority = fixture.authority
        actions = fixture.principal.actions | {'IngestSource', 'ReadIngestion', 'ReviewCandidate', 'GetFactEvidenceMatrix'}
        self.token = self.authority.provision(Principal(fixture.actor, self.tenant, self.case_id, actions))
        wiring = OperatorConfigTests()
        wiring.setUp()
        config = OCRConfig(**json.loads(Path(os.environ['LUKART_OCR_TEST_CONFIG']).read_text()))
        self.operator = build_operator(**dict(wiring.values, repository=fixture.repo,
            authority=self.authority, ocr_config=config))

    def test_http_create_upload_ocr_replay_and_original_restart_read(self):
        from http.client import HTTPConnection
        from threading import Thread
        from lukart_work.operator_host import create_server
        from tests.test_stage02 import PIN
        server = create_server(self.operator, 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(route, value, token=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=65)
            try:
                connection.request('POST', '/api/'+route, json.dumps(value),
                    {'Content-Type':'application/json', 'Authorization':'Bearer '+(token or self.token)})
                response = connection.getresponse()
                raw = response.read()
                self.assertEqual(response.status, 200, raw)
                return json.loads(raw)
            finally:
                connection.close()
        try:
            meta = dict(command_id=str(uuid4()), tenant_id=str(self.tenant), case_id=str(self.case_id),
                expected_case_sequence=0, idempotency_key=str(uuid4()), correlation_id=str(uuid4()))
            create = dict(contract='urn:lukart:work:CoreRequest:1.0.0', operation='CreateCase', meta=meta,
                data=dict(title='Syntetyczna sprawa OCR', jurisdiction='PL', retention_policy=PIN))
            denied = self.authority.provision(Principal(Actor(id=uuid4(), kind='SERVICE'), self.tenant,
                self.case_id, frozenset({'CreateCase'})))
            self.assertEqual(request('execute_core', create, denied)['code'], 'FORBIDDEN')
            created = request('execute_core', create)
            self.assertEqual(created['state'], 'APPLIED')
            self.assertEqual(request('execute_core', create), created)
            query_body = dict(contract='urn:lukart:work:CoreQuery:1.0.0', operation='GetCaseHead',
                tenant_id=str(self.tenant), case_id=str(self.case_id))
            self.assertEqual(request('query_core', query_body)['case_sequence'], 1)
            data = scan()
            source_command = dict(contract='urn:lukart:work:CoreRequest:1.0.0', operation='RegisterSource',
                meta=dict(meta, command_id=str(uuid4()), idempotency_key=str(uuid4()), expected_case_sequence=1),
                data=dict(content_base64=base64.b64encode(data).decode(), media_type='image/png', retention_policy=PIN))
            upload_request = dict(operation='UploadAndIngest', request=source_command, run_id=str(uuid4()))
            result = request('upload_source', upload_request)
            self.assertEqual(result['registration']['state'], 'APPLIED')
            self.assertEqual(result['ingestion']['body']['status'], 'EXTRACTED', result)
            self.assertIn('Zażółć', result['ingestion']['body']['fragments'][0]['text'])
            self.assertEqual(result['ingestion']['source_hash'], sha256(data).hexdigest())
            self.assertTrue(all(c['status']=='CANDIDATE' for c in result['ingestion']['body']['candidates']))
            replay = request('upload_source', upload_request)
            self.assertEqual(replay['registration'], result['registration'])
            self.assertEqual(replay['ingestion'], result['ingestion'])
            head = request('query_core', query_body)
            self.assertEqual(head['case_sequence'], 2)
            self.assertEqual({r['kind'] for r in head['heads']}, {'Case'})
            read = dict(operation='ReadIngestion', tenant_id=str(self.tenant), case_id=str(self.case_id),
                source_id=result['source_id'], run_id=result['run_id'])
            self.assertEqual(request('query_ingestion', read), result['ingestion'])
            self.assertEqual(request('query_ingestion', dict(read, case_id=str(uuid4())))['code'], 'FORBIDDEN')
            from uuid import UUID
            from lukart_work.ingestion.service import IngestionService
            from lukart_work.core.postgres import PostgresRepository
            restarted = PostgresRepository(self.dsn, storage=True, retention_policies=self.h.repo.retention_policies)
            saved = IngestionService(restarted, self.authority).read(self.token, UUID(result['source_id']), UUID(result['run_id']))
            self.assertEqual(saved.model_dump(mode='json'), result['ingestion'])
            original = self.operator.query_core(dict(query_body, operation='GetSource', object_id=result['source_id']), self.token)
            self.assertEqual(original, data)
            from lukart_work.ingestion.models import IngestionResult
            extraction = IngestionResult.model_validate_json(json.dumps(result['ingestion']))
            index = next(i for i,c in enumerate(extraction.body.candidates) if c.kind=='FACT')
            review = dict(contract='urn:lukart:work:FactEvidenceRequest:1.0.0',operation='ReviewCandidate',
                meta=dict(meta,command_id=str(uuid4()),idempotency_key=str(uuid4()),expected_case_sequence=2),
                data=dict(source_id=result['source_id'],run_id=result['run_id'],result_hash=digest(extraction),
                    candidate_index=index,expected_review_revision=0,disposition='ADMIT',
                    statement='Źródło zawiera wzmiankę o wpłacie.',description='Syntetyczny skan poddany przeglądowi'),
                rationale='Jawny przegląd syntetycznej fixture HUMAN w izolowanym teście')
            reviewed = request('execute_fact_evidence',review)
            self.assertEqual(reviewed['state'],'APPLIED')
            matrix = request('query_fact_evidence',dict(contract='urn:lukart:work:FactEvidenceQuery:1.0.0',
                operation='GetFactEvidenceMatrix',tenant_id=str(self.tenant),case_id=str(self.case_id)))
            with self.h.repo.transaction(self.tenant,self.case_id) as tx:
                heads = tx.heads()
                self.assertEqual(next(e for e in heads if e.kind=='Fact').status,'CANDIDATE')
                self.assertEqual(next(e for e in heads if e.kind=='Evidence').status,'REGISTERED')
                self.assertFalse(any(e.kind=='Decision' for e in heads))
            self.assertEqual(len(matrix['candidate_reviews']),1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_ocr_review_to_polish_validated_draft_and_downloadable_artifacts(self):
        from tests.test_finalization import FinalizationTests
        from scripts.run_generator_pism_operator_e2e import polish_fixture_type, verify_polish_artifacts
        from tests.test_stage02 import PIN
        from lukart_work.operator import GeneratorPismOperator
        from lukart_work.validation.rules import ref
        class OCRDraftFixture(polish_fixture_type(FinalizationTests)):
            def fact(h):
                party = h.party()
                source = h.request('RegisterSource',dict(content_base64=base64.b64encode(scan()).decode(),
                    media_type='image/png',retention_policy=PIN))
                uploaded = h.operator.upload_source(dict(operation='UploadAndIngest',request=source,run_id=str(uuid4())),h.token)
                h.assertEqual(uploaded.ingestion.body.status,'EXTRACTED')
                h.sequence = uploaded.registration.case_sequence
                extraction = uploaded.ingestion
                index = next(i for i,c in enumerate(extraction.body.candidates) if c.kind=='FACT')
                def review(operation,data=None,target=None):
                    command = h.request(operation,data,target)
                    command.update(contract='urn:lukart:work:FactEvidenceRequest:1.0.0',
                        rationale='Jawna ocena fixture HUMAN w odizolowanym teście OCR')
                    result = h.operator.execute_fact_evidence(command,h.token)
                    h.assertIsInstance(result,CommandResult,result)
                    h.sequence=result.case_sequence
                    return result
                admitted=review('ReviewCandidate',dict(source_id=str(extraction.source_id),run_id=str(extraction.run_id),
                    result_hash=digest(extraction),candidate_index=index,expected_review_revision=0,disposition='ADMIT',
                    statement='Zgłoszono dokonanie wpłaty',description='Syntetyczne potwierdzenie wpłaty',
                    subjects=[party.model_dump(mode='json')]))
                evidence,fact=admitted.refs
                for operation in ('ReviewEvidence','AcceptEvidence'):
                    evidence=review(operation,target=evidence).refs[0]
                fact=h.apply('EditFact',{'evidence':[evidence.model_dump(mode='json')]},fact)[0].refs[0]
                h.extraction=extraction
                return fact,party,evidence,extraction.source_id

            def legal_authority_fixture(h,source_id,**kwargs):
                # Keep the existing synthetic legal fixture separate from OCR evidence.
                _,command=h.apply('RegisterSource',dict(content_base64=base64.b64encode(b'Synthetic payment receipt.').decode(),
                    media_type='text/plain',retention_policy=PIN))
                from uuid import UUID
                legal_source=uuid5(UUID(command['meta']['command_id']),'source')
                return super().legal_authority_fixture(legal_source,**kwargs)
        h=OCRDraftFixture('test_public_happy_path_persists_exact_bytes_approval_and_release_chain')
        h.setUp()
        h.authority.revoke(h.token)
        h.principal=Principal(h.actor,h.tenant,h.case_id,h.principal.actions|{'IngestSource','ReadIngestion','ReviewCandidate'})
        h.token=h.authority.provision(h.principal)
        h.operator=GeneratorPismOperator(repository=h.repo,authority=h.authority,case_profile=h.final_profile,
            drafting_profiles={'QUICK':h.profile},provider=h.provider,package_profile=h.package_profile,
            ocr_config=self.operator.ingestion.ocr_config)
        h.service,h.facts,h.procedural=h.operator.core,h.operator.facts,h.operator.procedural
        h.planner,h.drafting=h.operator.planner,h.operator.drafting
        h.validation,h.finalization=h.operator.validation,h.operator.finalization
        draft,run_id=h.validated()
        render_id,_,_=h.render(draft,run_id)
        projection=h.final_query('GetFinalization',render_id)
        self.assertIsNone(projection.approval)
        directory=Path('build/ocr-createcase')/('draft-'+uuid4().hex)
        directory.mkdir(parents=True)
        artifacts={}
        for format in ('DOCX','PDF'):
            content=h.final_query('ReadFinalArtifact',render_id,format=format)
            self.assertIsInstance(content,bytes)
            (directory/('final.'+format.lower())).write_bytes(content)
            artifacts[format]=sha256(content).hexdigest()
        verify_polish_artifacts(directory)
        with h.repo.transaction(h.tenant,h.case_id) as tx:
            self.assertEqual(tx.events(),tx.outbox())
        (directory/'evidence.json').write_text(json.dumps(dict(scope='SYNTHETIC_OCR_TO_VALIDATED_DRAFT_ONLY',
            actual_human_acceptance=False,final_approval=False,render_id=str(render_id),
            source_hash=h.extraction.source_hash,ocr_pin=h.extraction.body.ocr_engine.model_dump(mode='json'),
            artifact_hashes=artifacts),indent=2),encoding='utf-8')
