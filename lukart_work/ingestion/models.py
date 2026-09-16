"""Versioned ingestion output; positions refer to extracted text, not original bytes."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from lukart_work.domain.models import Value, Hash, Actor, VersionPin


class ExtractedFragment(Value):
    index: Annotated[int, Field(ge=0)]
    unit: Literal['LINE', 'PARAGRAPH', 'PAGE', 'MIME_PART', 'HEADER']
    position: Annotated[str, Field(min_length=1, max_length=200)]
    text: Annotated[str, Field(min_length=1, max_length=100000)]
    text_hash: Hash


class IngestionCandidate(Value):
    kind: Literal['DATE', 'AMOUNT', 'PARTY', 'FACT', 'EVIDENCE']
    status: Literal['CANDIDATE'] = 'CANDIDATE'
    fragment: Annotated[int, Field(ge=0)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    quote: Annotated[str, Field(min_length=1, max_length=100000)]


class ExtractionBody(Value):
    media_type: str
    classification: Literal['TEXT', 'DOCUMENT', 'EMAIL', 'PDF', 'IMAGE', 'UNKNOWN']
    status: Literal['EXTRACTED', 'NEEDS_OCR', 'UNSUPPORTED', 'FAILED', 'EMPTY']
    fragments: tuple[ExtractedFragment, ...] = Field(max_length=1000)
    candidates: tuple[IngestionCandidate, ...] = Field(max_length=4000)
    warnings: tuple[Literal['UNTRUSTED_SOURCE', 'REVIEW_REQUIRED', 'PARTIAL_EXTRACTION',
        'OCR_REQUIRED', 'UNSUPPORTED_FORMAT', 'PARSER_REJECTED', 'NO_TEXT'], ...]
    contradiction_check: Literal['NOT_RUN'] = 'NOT_RUN'

    @model_validator(mode='after')
    def check_links(self):
        from hashlib import sha256
        if self.status != 'EXTRACTED' and (self.fragments or self.candidates):
            raise ValueError('INVALID_EXTRACTION_STATUS')
        if self.status == 'EXTRACTED' and not self.fragments:
            raise ValueError('EMPTY_EXTRACTION')
        for i, fragment in enumerate(self.fragments):
            if fragment.index != i or sha256(fragment.text.encode()).hexdigest() != fragment.text_hash:
                raise ValueError('INVALID_FRAGMENT')
        for candidate in self.candidates:
            if candidate.fragment >= len(self.fragments):
                raise ValueError('INVALID_CANDIDATE')
            text = self.fragments[candidate.fragment].text
            if not 0 <= candidate.start < candidate.end <= len(text) or text[candidate.start:candidate.end] != candidate.quote:
                raise ValueError('INVALID_CANDIDATE')
        return self


class IngestionResult(Value):
    contract: Literal['urn:lukart:work:IngestionResult:1.0.0']
    tenant_id: UUID
    case_id: UUID
    run_id: UUID
    source_id: UUID
    source_hash: Hash
    source_byte_length: Annotated[int, Field(ge=0)]
    actor: Actor
    recorded_at: datetime
    extractor: VersionPin
    parser: VersionPin
    python_version: Annotated[str, Field(min_length=1, max_length=100)]
    body_hash: Hash
    body: ExtractionBody

    @model_validator(mode='after')
    def check_body(self):
        from lukart_work.validation.rules import digest
        if self.recorded_at.tzinfo is None or digest(self.body) != self.body_hash:
            raise ValueError('INVALID_RESULT')
        return self
