"""Stage 11 rendering result contracts. Rendered bytes stay outside canonical CASE state."""
from typing import Literal
from pydantic import Field, model_validator
from lukart_work.domain.models import Value, VersionPin, Hash

RenderFormat = Literal["DOCX", "PDF", "HTML", "TXT"]


class RenderArtifactRecord(Value):
    format: RenderFormat
    media_type: Literal[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "text/html; charset=utf-8",
        "text/plain; charset=utf-8",
    ]
    content_hash: Hash
    byte_length: int = Field(strict=True, ge=1)
    semantic_hash: Hash
    profile: VersionPin


class RenderBundle(Value):
    semantic_hash: Hash
    profile: VersionPin
    artifacts: tuple[RenderArtifactRecord, ...] = Field(min_length=1)
    verification_hash: Hash

    @model_validator(mode="after")
    def bindings(self):
        formats = [artifact.format for artifact in self.artifacts]
        if len(formats) != len(set(formats)):
            raise ValueError("DUPLICATE_RENDER_FORMAT")
        if any(artifact.semantic_hash != self.semantic_hash or artifact.profile != self.profile for artifact in self.artifacts):
            raise ValueError("RENDER_BINDING_MISMATCH")
        return self


STAGE11_CONTRACTS = (RenderArtifactRecord, RenderBundle)
