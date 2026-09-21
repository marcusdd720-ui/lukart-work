"""Deterministic Stage 11 Rendering Engine.

The renderer is deliberately non-generative: it resolves already-approved semantic data,
builds a renderer-neutral model, lays it out, emits DOCX/PDF and validates the resulting
artifacts.  It never changes legal content or case state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from reportlab import pdfbase
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from lukart_work.contracts.messages import RenderRequest, SemanticDocument
from lukart_work.domain.models import Draft, Evidence, Institution, Party, Ref, Request, Section
from lukart_work.validation.rules import Violation, digest

from .contracts import (
    LayoutBlock,
    LayoutTree,
    RenderArtifact,
    RenderBlock,
    RenderBundleMeta,
    RenderModel,
    RenderProfile,
    RenderReceipt,
)
from .profiles import OFFICIAL_PL_V1, profile_font_paths, profile_pin


STYLE_TOKEN = {
    "DOCUMENT_HEADER": "document.heading.primary",
    "PARTY_BLOCK": "document.party_block",
    "REQUEST_HEADING": "document.heading.secondary",
    "REQUEST_ITEM": "document.request",
    "SECTION_HEADING": "document.heading.secondary",
    "BODY": "document.body",
    "LEGAL_BASIS": "document.legal_basis",
    "QUOTE": "document.quote",
    "SIGNATURE": "document.signature",
    "ATTACHMENT_HEADING": "document.heading.secondary",
    "ATTACHMENT_ITEM": "document.attachment",
}

FIXED_DOC_TIME = datetime(2000, 1, 1, 0, 0, 0)
FIXED_ZIP_TIME = (2000, 1, 1, 0, 0, 0)
RENDERER_VERSION = "1.0.0"


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def renderer_pin() -> "VersionPin":
    from lukart_work.domain.models import VersionPin

    root = Path(__file__).resolve().parent
    names = ("contracts.py", "profiles.py", "service.py")
    identity = {
        name: _sha((root / name).read_bytes().replace(b"\r\n", b"\n"))
        for name in names
    }
    return VersionPin(
        id="lukart-work-renderer",
        version=RENDERER_VERSION,
        content_hash=digest(identity),
    )


def _record(records: Mapping[Ref, object], target: Ref, scope: tuple[object, object]):
    item = records.get(target)
    if item is None:
        raise Violation("BROKEN_REFERENCE")
    if (getattr(item, "tenant_id", None), getattr(item, "case_id", None)) != scope:
        raise Violation("CROSS_CASE")
    return item


def _party_text(item: object) -> str:
    if isinstance(item, Party):
        name = item.display_name
    elif isinstance(item, Institution):
        name = item.name
    else:
        raise Violation("REFERENCE_TYPE")
    address = getattr(item, "address", None)
    if address is None:
        return name
    lines = [name, *address.lines]
    if address.postal_code:
        lines.append(address.postal_code)
    return "\n".join(lines)


def _attachment_label(records: Mapping[Ref, object], anchor, scope) -> tuple[str, Ref]:
    matches = [
        (target, item)
        for target, item in records.items()
        if isinstance(item, Evidence)
        and (item.tenant_id, item.case_id) == scope
        and item.source == anchor
    ]
    if len(matches) != 1:
        raise Violation("PROVENANCE_MISSING")
    target, evidence = matches[0]
    return evidence.description, target


def assemble_render_model(
    document: SemanticDocument,
    records: Mapping[Ref, object],
    profile: RenderProfile = OFFICIAL_PL_V1,
) -> RenderModel:
    scope = (document.tenant_id, document.case_id)
    draft = _record(records, document.draft, scope)
    if not isinstance(draft, Draft):
        raise Violation("REFERENCE_TYPE")
    if draft.snapshot_hash != document.snapshot_hash:
        raise Violation("INVALID_HASH")
    if draft.status not in ("VALIDATED", "APPROVED", "RENDERED"):
        raise Violation("GATE_DENIED")

    blocks: list[RenderBlock] = [
        RenderBlock(role="DOCUMENT_HEADER", text=document.header, refs=(document.draft,))
    ]

    for party_ref in document.parties:
        party = _record(records, party_ref, scope)
        blocks.append(RenderBlock(role="PARTY_BLOCK", text=_party_text(party), refs=(party_ref,)))

    if document.requests:
        blocks.append(RenderBlock(role="REQUEST_HEADING", text=profile.requests_label))
        for ordinal, request_ref in enumerate(document.requests, 1):
            request = _record(records, request_ref, scope)
            if not isinstance(request, Request):
                raise Violation("REFERENCE_TYPE")
            blocks.append(
                RenderBlock(
                    role="REQUEST_ITEM",
                    text=request.text,
                    refs=(request_ref,),
                    ordinal=ordinal,
                )
            )

    statement_roles = {
        "FACTUAL": "BODY",
        "LEGAL": "LEGAL_BASIS",
        "REQUEST": "REQUEST_ITEM",
        "INFERENCE": "BODY",
        "STRUCTURAL": "BODY",
    }
    for section_text in document.sections:
        section = _record(records, section_text.section, scope)
        if not isinstance(section, Section):
            raise Violation("REFERENCE_TYPE")
        blocks.append(
            RenderBlock(role="SECTION_HEADING", text=section.title, refs=(section_text.section,))
        )
        request_ordinal = 1
        for statement in section_text.statements:
            role = statement_roles[statement.statement_type]
            ordinal = None
            if role == "REQUEST_ITEM":
                ordinal = request_ordinal
                request_ordinal += 1
            refs = tuple(dict.fromkeys((section_text.section, *statement.refs, *statement.citations)))
            blocks.append(
                RenderBlock(role=role, text=statement.text, refs=refs, ordinal=ordinal)
            )

    if document.attachments:
        blocks.append(RenderBlock(role="ATTACHMENT_HEADING", text=profile.attachments_label))
        for ordinal, anchor in enumerate(document.attachments, 1):
            label, evidence_ref = _attachment_label(records, anchor, scope)
            blocks.append(
                RenderBlock(
                    role="ATTACHMENT_ITEM",
                    text=label,
                    refs=(evidence_ref,),
                    ordinal=ordinal,
                )
            )

    if document.signature_party is not None:
        party = _record(records, document.signature_party, scope)
        blocks.append(
            RenderBlock(
                role="SIGNATURE",
                text=_party_text(party).splitlines()[0],
                refs=(document.signature_party,),
            )
        )

    return RenderModel(
        tenant_id=document.tenant_id,
        case_id=document.case_id,
        draft=document.draft,
        snapshot_hash=document.snapshot_hash,
        blocks=tuple(blocks),
    )


def build_layout(model: RenderModel, profile: RenderProfile = OFFICIAL_PL_V1) -> LayoutTree:
    blocks = []
    for block in model.blocks:
        token = STYLE_TOKEN.get(block.role)
        if token is None:
            raise Violation("SCHEMA_INVALID")
        blocks.append(
            LayoutBlock(
                role=block.role,
                style_token=token,
                text=block.text,
                refs=block.refs,
                ordinal=block.ordinal,
                keep_with_next=block.role
                in ("DOCUMENT_HEADER", "REQUEST_HEADING", "SECTION_HEADING", "ATTACHMENT_HEADING"),
                page_break_before=False,
            )
        )
    return LayoutTree(
        tenant_id=model.tenant_id,
        case_id=model.case_id,
        draft=model.draft,
        snapshot_hash=model.snapshot_hash,
        profile=profile_pin(profile),
        blocks=tuple(blocks),
    )


def _display_text(block: LayoutBlock) -> str:
    return f"{block.ordinal}. {block.text}" if block.ordinal is not None else block.text


def _set_run_font(run, profile: RenderProfile, *, size: int, bold: bool) -> None:
    run.font.name = profile.font_family
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = rpr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{key}"), profile.font_family)


def _normalize_docx(raw: bytes) -> bytes:
    source = BytesIO(raw)
    output = BytesIO()
    with ZipFile(source, "r") as src, ZipFile(
        output, "w", compression=ZIP_DEFLATED, compresslevel=9
    ) as dst:
        for name in sorted(src.namelist()):
            info = ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            dst.writestr(info, src.read(name))
    return output.getvalue()


def render_docx(layout: LayoutTree, profile: RenderProfile = OFFICIAL_PL_V1) -> bytes:
    if layout.profile != profile_pin(profile):
        raise Violation("INVALID_HASH")
    document = Document()
    core = document.core_properties
    core.author = "LUKART WORK"
    core.last_modified_by = "LUKART WORK"
    core.title = ""
    core.subject = ""
    core.keywords = ""
    core.comments = ""
    core.created = FIXED_DOC_TIME
    core.modified = FIXED_DOC_TIME
    core.revision = 1

    section = document.sections[0]
    section.page_width = Mm(profile.page_width_mm)
    section.page_height = Mm(profile.page_height_mm)
    section.top_margin = Mm(profile.margin_top_mm)
    section.right_margin = Mm(profile.margin_right_mm)
    section.bottom_margin = Mm(profile.margin_bottom_mm)
    section.left_margin = Mm(profile.margin_left_mm)

    # Remove the package's initial empty paragraph so artifact identity depends only on layout.
    body = document._element.body
    for paragraph in list(body.findall(qn("w:p"))):
        body.remove(paragraph)

    for block in layout.blocks:
        paragraph = document.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.line_spacing = profile.line_spacing_milli / 1000
        fmt.space_after = Pt(profile.paragraph_after_pt)
        fmt.keep_with_next = block.keep_with_next
        if block.role in ("SECTION_HEADING", "REQUEST_HEADING", "ATTACHMENT_HEADING"):
            fmt.space_before = Pt(profile.section_before_pt)
        if block.role in ("REQUEST_ITEM", "ATTACHMENT_ITEM"):
            fmt.left_indent = Mm(7)
            fmt.first_line_indent = Mm(-5)
        if block.role == "SIGNATURE":
            fmt.space_before = Pt(18)
        if block.role == "DOCUMENT_HEADER":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

        size = profile.body_font_pt
        bold = False
        if block.role == "DOCUMENT_HEADER":
            size, bold = profile.title_font_pt, True
        elif block.role in ("SECTION_HEADING", "REQUEST_HEADING", "ATTACHMENT_HEADING"):
            size, bold = profile.heading_font_pt, True

        run = paragraph.add_run(_display_text(block))
        _set_run_font(run, profile, size=size, bold=bold)

    buffer = BytesIO()
    document.save(buffer)
    return _normalize_docx(buffer.getvalue())


def _register_pdf_fonts(profile: RenderProfile) -> tuple[str, str]:
    regular, bold = profile_font_paths(profile)
    regular_name = f"LUKART-{profile.profile_id}-{profile.version}-Regular"
    bold_name = f"LUKART-{profile.profile_id}-{profile.version}-Bold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, str(regular)))
    if bold_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_name, str(bold)))
    return regular_name, bold_name


def _wrap_pdf(text: str, font_name: str, size: int, max_width: float) -> list[str]:
    lines: list[str] = []
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for raw in raw_lines:
        if raw == "":
            lines.append("")
            continue
        words = raw.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if not current or pdfmetrics.stringWidth(candidate, font_name, size) <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
            if pdfmetrics.stringWidth(current, font_name, size) > max_width:
                # A single pathological token must not escape the page box.
                piece = ""
                for char in current:
                    test = piece + char
                    if piece and pdfmetrics.stringWidth(test, font_name, size) > max_width:
                        lines.append(piece)
                        piece = char
                    else:
                        piece = test
                current = piece
        lines.append(current)
    return lines


def render_pdf(layout: LayoutTree, profile: RenderProfile = OFFICIAL_PL_V1) -> bytes:
    if layout.profile != profile_pin(profile):
        raise Violation("INVALID_HASH")
    regular_name, bold_name = _register_pdf_fonts(profile)
    page_width = profile.page_width_mm * mm
    page_height = profile.page_height_mm * mm
    left = profile.margin_left_mm * mm
    right = page_width - profile.margin_right_mm * mm
    top = page_height - profile.margin_top_mm * mm
    bottom = profile.margin_bottom_mm * mm
    width = right - left

    output = BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=(page_width, page_height),
        invariant=1,
        pageCompression=1,
    )
    pdf.setAuthor("LUKART WORK")
    pdf.setCreator(f"LUKART WORK Renderer {RENDERER_VERSION}")
    pdf.setTitle("")
    pdf.setSubject("")

    y = top

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        y = top

    for block in layout.blocks:
        size = profile.body_font_pt
        font = regular_name
        before = 0.0
        after = profile.paragraph_after_pt
        if block.role == "DOCUMENT_HEADER":
            size, font = profile.title_font_pt, bold_name
        elif block.role in ("SECTION_HEADING", "REQUEST_HEADING", "ATTACHMENT_HEADING"):
            size, font = profile.heading_font_pt, bold_name
            before = profile.section_before_pt
        elif block.role == "SIGNATURE":
            before = 18.0

        line_height = size * (profile.line_spacing_milli / 1000)
        text = _display_text(block)
        block_left = left + (7 * mm if block.role in ("REQUEST_ITEM", "ATTACHMENT_ITEM") else 0)
        available = right - block_left
        lines = _wrap_pdf(text, font, size, available)
        reserve = before + max(1, len(lines)) * line_height + after
        if block.keep_with_next:
            reserve += profile.body_font_pt * (profile.line_spacing_milli / 1000)
        if y - reserve < bottom:
            new_page()

        y -= before
        pdf.setFont(font, size)
        for line in lines:
            if y - line_height < bottom:
                new_page()
                pdf.setFont(font, size)
            if block.role == "DOCUMENT_HEADER":
                pdf.drawCentredString(page_width / 2, y, line)
            else:
                pdf.drawString(block_left, y, line)
            y -= line_height
        y -= after

    pdf.save()
    return output.getvalue()


def _validate_docx(data: bytes) -> None:
    try:
        with ZipFile(BytesIO(data), "r") as package:
            names = set(package.namelist())
            required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
            if not required <= names:
                raise Violation("RENDER_INVALID")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise Violation("RENDER_INVALID")
            for name in names:
                if name.endswith(".rels") and b'TargetMode="External"' in package.read(name):
                    raise Violation("RENDER_INVALID")
    except Violation:
        raise
    except Exception as exc:
        raise Violation("RENDER_INVALID") from exc


def _validate_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise Violation("RENDER_INVALID")
    for forbidden in (b"/JavaScript", b"/JS ", b"/OpenAction", b"/Launch"):
        if forbidden in data:
            raise Violation("RENDER_INVALID")
    if b"/FontFile2" not in data:
        raise Violation("RENDER_FONT_MISSING")


@dataclass(frozen=True)
class RenderedBundle:
    docx: bytes
    pdf: bytes
    meta: RenderBundleMeta


class RenderingEngine:
    def render(
        self,
        request: RenderRequest,
        records: Mapping[Ref, object],
        profile: RenderProfile = OFFICIAL_PL_V1,
    ) -> RenderedBundle:
        if request.profile != profile_pin(profile):
            raise Violation("INVALID_HASH")
        model = assemble_render_model(request.document, records, profile)
        layout = build_layout(model, profile)
        docx = render_docx(layout, profile)
        pdf = render_pdf(layout, profile)
        _validate_docx(docx)
        _validate_pdf(pdf)

        artifacts = (
            RenderArtifact(
                format="DOCX",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content_hash=_sha(docx),
                byte_length=len(docx),
            ),
            RenderArtifact(
                format="PDF",
                media_type="application/pdf",
                content_hash=_sha(pdf),
                byte_length=len(pdf),
            ),
        )
        receipt = RenderReceipt(
            draft=model.draft,
            snapshot_hash=model.snapshot_hash,
            semantic_digest=digest(request.document),
            render_model_digest=digest(model),
            layout_digest=digest(layout),
            render_profile=profile_pin(profile),
            renderer=renderer_pin(),
            artifacts=artifacts,
        )
        meta = RenderBundleMeta(model=model, layout=layout, receipt=receipt)
        return RenderedBundle(docx=docx, pdf=pdf, meta=meta)

    @staticmethod
    def validate(bundle: RenderedBundle) -> None:
        _validate_docx(bundle.docx)
        _validate_pdf(bundle.pdf)
        artifacts = bundle.meta.receipt.artifacts
        if (
            artifacts[0].content_hash != _sha(bundle.docx)
            or artifacts[0].byte_length != len(bundle.docx)
            or artifacts[1].content_hash != _sha(bundle.pdf)
            or artifacts[1].byte_length != len(bundle.pdf)
        ):
            raise Violation("INVALID_HASH")
        if bundle.meta.receipt.render_model_digest != digest(bundle.meta.model):
            raise Violation("INVALID_HASH")
        if bundle.meta.receipt.layout_digest != digest(bundle.meta.layout):
            raise Violation("INVALID_HASH")
