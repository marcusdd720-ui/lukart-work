"""Transport composition over existing authorized source and ingestion services."""
import json
from typing import Literal
from uuid import UUID, uuid5

from pydantic import ValidationError
from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.requests import CoreRequest
from lukart_work.core.service import safe_error
from lukart_work.domain.models import Value
from lukart_work.ingestion.models import IngestionResult
from lukart_work.validation.rules import Violation


class UploadRequest(Value):
    operation: Literal['UploadAndIngest']
    request: CoreRequest
    run_id: UUID


class IngestionQuery(Value):
    operation: Literal['ReadIngestion', 'IngestSource']
    tenant_id: UUID
    case_id: UUID
    source_id: UUID
    run_id: UUID


class UploadResult(Value):
    source_id: UUID
    run_id: UUID
    registration: CommandResult
    ingestion: IngestionResult | DomainError


def upload(operator, request, token):
    try:
        value = UploadRequest.model_validate_json(json.dumps(request))
        command = value.request
        if command.operation != 'RegisterSource':
            raise Violation('SCHEMA_INVALID')
        with operator.core.authority.session(token) as principal:
            for action in ('RegisterSource', 'IngestSource'):
                principal.require(command.meta.tenant_id, command.meta.case_id, action)
            if principal.actor.kind == 'AI':
                raise Violation('FORBIDDEN')
            registration = operator.core.execute(command.model_dump_json(), token)
            if not isinstance(registration, CommandResult):
                return registration
            if registration.state not in ('APPLIED', 'REPLAYED'):
                raise Violation('GATE_DENIED')
            source_id = uuid5(command.meta.command_id, 'source')
            result = operator.ingestion.ingest(token, source_id, value.run_id)
            return UploadResult(source_id=source_id, run_id=value.run_id,
                                registration=registration, ingestion=result)
    except Violation as error:
        return safe_error(error.code, UUID(int=0))
    except (ValueError, TypeError, ValidationError):
        return safe_error('SCHEMA_INVALID', UUID(int=0))


def query(operator, request, token):
    try:
        value = IngestionQuery.model_validate_json(json.dumps(request))
        with operator.core.authority.session(token) as principal:
            principal.require(value.tenant_id, value.case_id, value.operation)
            method = operator.ingestion.read if value.operation == 'ReadIngestion' else operator.ingestion.ingest
            return method(token, value.source_id, value.run_id)
    except Violation as error:
        return safe_error(error.code, UUID(int=0))
    except (ValueError, TypeError, ValidationError):
        return safe_error('SCHEMA_INVALID', UUID(int=0))
