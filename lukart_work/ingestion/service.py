"""Authenticated extraction and immutable replay over Stage 03 storage."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from uuid import UUID
from pydantic import ValidationError
from lukart_work.contracts.messages import SourceDocument
from lukart_work.core.postgres import canonical
from lukart_work.core.service import safe_error
from lukart_work.domain.models import VersionPin
from lukart_work.storage.objects import ObjectStore, artifact_id, RetentionPolicies, MAX_BYTES
from lukart_work.validation.rules import Violation, digest
from .models import ExtractionBody, IngestionResult


def implementation_pin():
    root = Path(__file__).parent
    contents = b''.join(p.name.encode() + b'\0' + p.read_bytes().replace(b'\r\n', b'\n')
                        for p in sorted(root.glob('*.py')))
    return VersionPin(id='lukart-ingestion', version='1.0.0', content_hash=sha256(contents).hexdigest())


def parser_pin():
    # Bind installed parser code, not a caller's claimed package version.
    import pypdf
    root = Path(pypdf.__file__).parent
    contents = b''.join(p.relative_to(root).as_posix().encode() + b'\0' + p.read_bytes().replace(b'\r\n', b'\n')
                        for p in sorted(root.rglob('*.py')))
    version = importlib.metadata.version('pypdf')
    if version != '6.10.0':
        raise Violation('GATE_DENIED')
    return VersionPin(id='pypdf', version=version, content_hash=sha256(contents).hexdigest())


def _worker_env():
    allowed = {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'LANG', 'LC_ALL', 'PYTHONUTF8'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    # setup-python can require its private lib directory for a child interpreter.
    # Never inherit caller-controlled LD_LIBRARY_PATH; derive the only allowed
    # loader path from the trusted interpreter prefix itself.
    runtime_lib = Path(sys.base_prefix) / 'lib'
    if sys.platform != 'win32' and runtime_lib.is_dir():
        env['LD_LIBRARY_PATH'] = str(runtime_lib)
    return env


def parse_isolated(data, media_type, ocr_config=None):
    failed = lambda: ExtractionBody(media_type='application/octet-stream', classification='UNKNOWN', status='FAILED',
        fragments=(), candidates=(), warnings=('UNTRUSTED_SOURCE', 'REVIEW_REQUIRED', 'PARSER_REJECTED'))
    try:
        process = subprocess.run([sys.executable, '-B', '-m', 'lukart_work.ingestion.worker'],
            input=json.dumps({'data': base64.b64encode(data).decode(), 'media_type': media_type,
                              'ocr': ocr_config.payload() if ocr_config else None}).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60 if ocr_config else 15,
            cwd=Path(__file__).resolve().parents[2],
            env=_worker_env())
        if process.returncode or len(process.stdout) > 8 * 1024 * 1024:
            return failed()
        return ExtractionBody.model_validate_json(process.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, ValidationError):
        return failed()


class IngestionService:
    """Trusted host supplies repository and authority, never an arbitrary parser callback."""
    def __init__(self, repository, authority, ocr_config=None):
        self.repository, self.authority = repository, authority
        if ocr_config is not None:
            from .ocr import OCRConfig
            if not isinstance(ocr_config, OCRConfig):
                raise ValueError('TRUSTED_OCR_CONFIGURATION_REQUIRED')
            ocr_config.pin()
        self.ocr_config = ocr_config

    def _run(self, token, action, source_id, run_id, callback):
        try:
            if not isinstance(source_id, UUID) or not isinstance(run_id, UUID):
                raise Violation('SCHEMA_INVALID')
            with self.authority.session(token) as p:
                p.require(p.tenant_id, p.case_id, action)
                if p.actor.kind == 'AI' or not self.repository.storage:
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(p.tenant_id, p.case_id) as tx:
                    if not tx.sequence():
                        raise Violation('BROKEN_REFERENCE')
                    source = tx.object('source', source_id, SourceDocument)
                    data = tx.source_bytes(source_id)
                    if len(data) > MAX_BYTES:
                        raise Violation('SCHEMA_INVALID')
                    result = callback(tx, p, source, data)
                    p.require(p.tenant_id, p.case_id, action)
                return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValueError, TypeError, ValidationError, OverflowError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('CONFLICT' if getattr(error, 'sqlstate', '') == '23505' else 'UNKNOWN', UUID(int=0))
            raise

    @staticmethod
    def _target(tx, run_id):
        return artifact_id(tx.scope, 'raw_output', 'ingestion/' + str(run_id), '1')

    def _read(self, tx, source, run_id):
        store = ObjectStore(tx)
        target = self._target(tx, run_id)
        item = store.metadata(target)
        result = IngestionResult.model_validate_json(store.read(target))
        if ((result.tenant_id, result.case_id) != tx.scope or result.run_id != run_id or
            result.source_id != source.id or result.source_hash != source.content_hash or
            result.source_byte_length != source.byte_length or result.actor.id != item.actor_id or
            result.recorded_at != item.created_at):
            raise Violation('INVALID_HASH')
        return result

    def read(self, token, source_id, run_id):
        return self._run(token, 'ReadIngestion', source_id, run_id,
            lambda tx, p, source, data: self._read(tx, source, run_id))

    def ingest(self, token, source_id, run_id):
        def apply(tx, p, source, data):
            # Extraction is a new case operation; CLOSED/ARCHIVED cannot acquire results.
            case = next((e for e in tx.heads() if e.kind == 'Case'), None)
            if case is None or case.status in ('CLOSED', 'ARCHIVED'):
                raise Violation('GATE_DENIED')
            target = self._target(tx, run_id)
            exists = tx.connection.execute('SELECT 1 FROM lw_storage.artifacts WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s',
                (*tx.scope, target)).fetchone()
            if exists:
                old = self._read(tx, source, run_id)
                if old.actor != p.actor:
                    raise Violation('CONFLICT')
                return old  # Replay original pin/output after an implementation upgrade.
            extractor, parser = implementation_pin(), parser_pin()
            body = parse_isolated(data, source.media_type, self.ocr_config)
            now = datetime.now(timezone.utc)
            result = IngestionResult(contract='urn:lukart:work:IngestionResult:1.0.0',
                tenant_id=p.tenant_id, case_id=p.case_id, run_id=run_id, source_id=source.id,
                source_hash=source.content_hash, source_byte_length=source.byte_length,
                actor=p.actor, recorded_at=now, extractor=extractor, parser=parser,
                python_version=platform.python_version(), body_hash=digest(body), body=body)
            ObjectStore(tx).put(target, 'raw_output', 'ingestion/' + str(run_id), '1', canonical(result).encode(),
                source.retention_policy, p.actor.id, now, self.repository.retention_policies or RetentionPolicies())
            return result
        return self._run(token, 'IngestSource', source_id, run_id, apply)
