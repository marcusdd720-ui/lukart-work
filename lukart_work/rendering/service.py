"""Deterministic Stage 11 renderer: SemanticDocument + pinned profile -> presentation bytes."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from html import escape, unescape
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_STORED, ZipInfo

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from lukart_work.contracts.messages import RenderRequest, SemanticDocument
from lukart_work.domain.models import Ref, SourceAnchor, VersionPin
from lukart_work.validation.rules import digest
from .contracts import RenderArtifactRecord, RenderBundle
from .profiles import court_pl_profile, profile_spec


class RenderError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedBundle:
    record: RenderBundle
    bytes_by_format: dict[str, bytes]


MEDIA = {
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "PDF": "application/pdf",
    "HTML": "text/html; charset=utf-8",
    "TXT": "text/plain; charset=utf-8",
}


def authorization_binding(document: SemanticDocument, profile: VersionPin) -> str:
    """Binding created by a trusted pre-render authorization boundary."""
    return digest({"semantic_hash": digest(document), "profile": profile.model_dump(mode="json")})


def _ref_text(ref: Ref) -> str:
    return f"{ref.kind}:{ref.id}@{ref.revision}"


def _anchor_text(anchor: SourceAnchor) -> str:
    loc = anchor.locator
    return f"SourceDocument:{anchor.document_id}#{loc.unit}:{loc.value}"


def _block_lines(text: str) -> list[str]:
    # Newlines are presentation data. Preserve order but never invent content.
    return text.splitlines() or [""]


def _semantic_lines(document: SemanticDocument) -> list[str]:
    # Internal revision identifiers are provenance, not user-facing legal text.
    # The complete SemanticDocument (including those refs) remains bound by
    # semantic_hash; visible bytes contain only presentation-ready text plus
    # neutral structural labels that do not disclose internal UUIDs.
    lines = _block_lines(document.header)
    for section in document.sections:
        lines.append("")
        for statement in section.statements:
            lines.extend(_block_lines(statement.text))
    if document.attachments:
        lines += ["", "Załączniki:"]
        lines.extend(f"{index}. Załącznik" for index, _ in enumerate(document.attachments, start=1))
    if document.signature_party is not None:
        lines += ["", "____________________________", "Podpis"]
    return lines


def _semantic_text(document: SemanticDocument) -> str:
    return "\n".join(_semantic_lines(document)).rstrip() + "\n"


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_STORED
    info.create_system = 0
    info.external_attr = 0
    return info


def _docx(document: SemanticDocument, semantic_hash: str, spec: dict) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = []
    for line in _semantic_lines(document):
        text = escape(line)
        body.append(
            '<w:p><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr>'
            f'<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
        )
    left = int(spec["margins_mm"]["left"] * 56.6929133858)
    right = int(spec["margins_mm"]["right"] * 56.6929133858)
    top = int(spec["margins_mm"]["top"] * 56.6929133858)
    bottom = int(spec["margins_mm"]["bottom"] * 56.6929133858)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{ns}"><w:body>'
        + "".join(body)
        + f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="{top}" w:right="{right}" '
          f'w:bottom="{bottom}" w:left="{left}" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        + '</w:body></w:document>'
    )
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>
</Relationships>'''
    custom = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="2" name="LUKARTSemanticSHA256"><vt:lpwstr>{semantic_hash}</vt:lpwstr></property>
</Properties>'''
    out = BytesIO()
    with ZipFile(out, "w") as archive:
        for name, value in (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", rels),
            ("word/document.xml", document_xml),
            ("docProps/custom.xml", custom),
        ):
            archive.writestr(_zip_info(name), value.encode("utf-8"))
    return out.getvalue()


def _html(document: SemanticDocument, semantic_hash: str, spec: dict) -> bytes:
    margins = spec["margins_mm"]
    parts = [
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">',
        f'<meta name="lukart-semantic-sha256" content="{semantic_hash}">',
        '<style>@page{size:A4;margin:%dmm %dmm %dmm %dmm}body{font-family:serif;font-size:11pt;line-height:1.25}'
        'p{margin:0 0 7pt 0}.blank{height:7pt}</style></head><body>'
        % (margins["top"], margins["right"], margins["bottom"], margins["left"]),
    ]
    for line in _semantic_lines(document):
        parts.append('<div class="blank"></div>' if not line else f"<p>{escape(line)}</p>")
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


_FONT = "LUKART-DejaVuSans"
_FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _ensure_pdf_font():
    if _FONT in pdfmetrics.getRegisteredFontNames():
        return
    # Ubuntu 24.04 runner/runtime dependency. Fail closed rather than silently
    # substitute a font that cannot represent Polish legal text.
    if not _FONT_PATH.is_file():
        raise RenderError("RENDER_FONT_UNAVAILABLE")
    pdfmetrics.registerFont(TTFont(_FONT, str(_FONT_PATH)))


def _pdf(document: SemanticDocument, semantic_hash: str, spec: dict) -> bytes:
    _ensure_pdf_font()
    out = BytesIO()
    canvas = Canvas(out, pagesize=A4, invariant=1, pageCompression=0)
    canvas.setTitle(document.header[:200])
    canvas.setSubject("lukart-semantic-sha256:" + semantic_hash)
    left = spec["margins_mm"]["left"] * mm
    right = spec["margins_mm"]["right"] * mm
    top = spec["margins_mm"]["top"] * mm
    bottom = spec["margins_mm"]["bottom"] * mm
    width, height = A4
    font_size = spec["body_pt"]
    leading = font_size * spec["line_height"]
    page = 1

    def footer():
        canvas.setFont(_FONT, 8)
        canvas.drawCentredString(width / 2, 10 * mm, f"Page {page}")

    y = height - top
    canvas.setFont(_FONT, font_size)
    for raw in _semantic_lines(document):
        if not raw:
            y -= leading
            continue
        words = raw.split(" ")
        current = ""
        rendered = []
        max_width = width - left - right
        for word in words:
            if pdfmetrics.stringWidth(word, _FONT, font_size) > max_width:
                raise RenderError("RENDER_UNBREAKABLE_TOKEN")
            candidate = word if not current else current + " " + word
            if pdfmetrics.stringWidth(candidate, _FONT, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    rendered.append(current)
                current = word
        if current:
            rendered.append(current)
        for line in rendered or [""]:
            if y < bottom + 12 * mm:
                footer()
                canvas.showPage()
                page += 1
                canvas.setFont(_FONT, font_size)
                y = height - top
            canvas.drawString(left, y, line)
            y -= leading
    footer()
    canvas.save()
    return out.getvalue()


def _txt(document: SemanticDocument) -> bytes:
    return _semantic_text(document).encode("utf-8")


def _extract_docx(data: bytes) -> str:
    with ZipFile(BytesIO(data), "r") as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for paragraph in root.findall(".//w:p", ns):
        lines.append("".join(node.text or "" for node in paragraph.findall(".//w:t", ns)))
    return "\n".join(lines).rstrip() + "\n"


def _extract_html(data: bytes) -> str:
    raw = data.decode("utf-8")
    body = raw.split("<body>", 1)[1].split("</body>", 1)[0]
    body = body.replace('<div class="blank"></div>', "\n")
    parts = []
    while "<p>" in body:
        _, body = body.split("<p>", 1)
        value, body = body.split("</p>", 1)
        parts.append(unescape(value))
    # Rebuild using semantic nonblank lines; blank layout nodes do not carry semantic text.
    return "\n".join(parts)


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    lines = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            if not line.startswith("Page "):
                lines.append(line)
    return "\n".join(lines)


def _verify(format_name: str, data: bytes, document: SemanticDocument, semantic_hash: str):
    expected_lines = [line for line in _semantic_lines(document) if line]
    if format_name == "TXT":
        if data.decode("utf-8") != _semantic_text(document):
            raise RenderError("RENDER_SEMANTIC_MISMATCH")
    elif format_name == "HTML":
        if _extract_html(data).splitlines() != expected_lines:
            raise RenderError("RENDER_SEMANTIC_MISMATCH")
        if semantic_hash.encode() not in data:
            raise RenderError("RENDER_BINDING_MISSING")
    elif format_name == "DOCX":
        if [line for line in _extract_docx(data).splitlines() if line] != expected_lines:
            raise RenderError("RENDER_SEMANTIC_MISMATCH")
        with ZipFile(BytesIO(data), "r") as archive:
            if semantic_hash.encode() not in archive.read("docProps/custom.xml"):
                raise RenderError("RENDER_BINDING_MISSING")
    elif format_name == "PDF":
        # PDF layout may wrap one semantic paragraph over several visual lines.
        # Compare the ordered visible text after whitespace normalization rather
        # than treating visual line breaks as semantic changes.
        actual_text = " ".join(_extract_pdf(data).split())
        expected_text = " ".join(" ".join(expected_lines).split())
        if actual_text != expected_text:
            raise RenderError("RENDER_SEMANTIC_MISMATCH")
        if semantic_hash.encode() not in data:
            raise RenderError("RENDER_BINDING_MISSING")


class RenderEngine:
    """Presentation-only renderer. It never resolves CASE facts or mutates domain state."""

    def render(self, request: RenderRequest, *, expected_authorization_hash: str,
               formats: tuple[str, ...] = ("DOCX", "PDF")) -> RenderedBundle:
        if request.authorization_hash != expected_authorization_hash:
            raise RenderError("RENDER_AUTHORIZATION_MISMATCH")
        if request.profile != court_pl_profile():
            raise RenderError("UNKNOWN_RENDER_PROFILE")
        if expected_authorization_hash != authorization_binding(request.document, request.profile):
            raise RenderError("RENDER_AUTHORIZATION_INVALID")
        spec = profile_spec(request.profile)
        allowed = tuple(spec["formats"])
        if not formats or len(formats) != len(set(formats)) or any(fmt not in allowed for fmt in formats):
            raise RenderError("RENDER_FORMAT_INVALID")
        semantic_hash = digest(request.document)
        rendered = {}
        for fmt in formats:
            if fmt == "DOCX":
                data = _docx(request.document, semantic_hash, spec)
            elif fmt == "PDF":
                data = _pdf(request.document, semantic_hash, spec)
            elif fmt == "HTML":
                data = _html(request.document, semantic_hash, spec)
            else:
                data = _txt(request.document)
            _verify(fmt, data, request.document, semantic_hash)
            rendered[fmt] = data
        artifacts = tuple(
            RenderArtifactRecord(
                format=fmt, media_type=MEDIA[fmt], content_hash=sha256(rendered[fmt]).hexdigest(),
                byte_length=len(rendered[fmt]), semantic_hash=semantic_hash, profile=request.profile,
            )
            for fmt in formats
        )
        verification_hash = digest({
            "semantic_hash": semantic_hash,
            "profile": request.profile.model_dump(mode="json"),
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        })
        return RenderedBundle(
            record=RenderBundle(
                semantic_hash=semantic_hash, profile=request.profile,
                artifacts=artifacts, verification_hash=verification_hash,
            ),
            bytes_by_format=rendered,
        )
