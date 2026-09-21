"""Deterministic representation-only DOCX/PDF renderer.

This module consumes SemanticDocument + RenderProfile only. It does not resolve CASE
state, infer legal meaning, alter statements, or grant any lifecycle authority.
"""
from io import BytesIO
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lukart_work.contracts.messages import SemanticDocument

from .contracts import RenderProfile


DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
PDF_MIME = 'application/pdf'
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _style(profile, token):
    return next(style for style in profile.styles if style.token == token)


def _lines(document):
    rows = [('document.heading.primary', document.header)]
    for index, section in enumerate(document.sections, 1):
        rows.append(('document.heading.secondary', f'Sekcja {index}'))
        for statement in section.statements:
            token = {
                'REQUEST': 'document.request',
                'LEGAL': 'document.legal_basis',
                'INFERENCE': 'document.quote',
            }.get(statement.statement_type, 'document.body')
            text = statement.text
            if statement.statement_type == 'INFERENCE' and statement.inference_label:
                text = f'{statement.inference_label}: {text}'
            rows.append((token, text))
    if document.attachments:
        rows.append(('document.heading.secondary', 'Załączniki'))
        for index, anchor in enumerate(document.attachments, 1):
            rows.append((
                'document.attachment',
                f'{index}. źródło {anchor.document_id}; {anchor.locator.unit} {anchor.locator.value}',
            ))
    if document.signature_party is not None:
        rows.append(('document.signature', f'Podpis: {document.signature_party.id}'))
    return tuple(rows)


def _twips(mm):
    return int(round(mm / 25.4 * 1440))


def _word_alignment(value):
    return {'LEFT': 'left', 'CENTER': 'center', 'RIGHT': 'right', 'JUSTIFY': 'both'}[value]


def _docx_paragraph(text, style):
    parts = str(text).split('\n') or ['']
    runs = []
    for index, part in enumerate(parts):
        if index:
            runs.append('<w:br/>')
        runs.append(
            '<w:t xml:space="preserve">' + escape(part, quote=False) + '</w:t>'
        )
    bold = '<w:b/>' if style.bold else ''
    size = style.font_size_pt * 2
    return (
        '<w:p><w:pPr>'
        f'<w:jc w:val="{_word_alignment(style.alignment)}"/>'
        f'<w:spacing w:after="{style.space_after_pt * 20}" w:line="276" w:lineRule="auto"/>'
        '</w:pPr><w:r><w:rPr>'
        f'<w:rFonts w:ascii="{escape(style.font_family, quote=True)}" '
        f'w:hAnsi="{escape(style.font_family, quote=True)}" '
        f'w:eastAsia="{escape(style.font_family, quote=True)}"/>'
        f'{bold}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        '</w:rPr>' + ''.join(runs) + '</w:r></w:p>'
    )


def render_docx(document: SemanticDocument, profile: RenderProfile) -> bytes:
    body = ''.join(
        _docx_paragraph(text, _style(profile, token))
        for token, text in _lines(document)
    )
    section = (
        '<w:sectPr>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        f'<w:pgSz w:w="{_twips(profile.page_width_mm)}" w:h="{_twips(profile.page_height_mm)}"/>'
        f'<w:pgMar w:top="{_twips(profile.margin_top_mm)}" '
        f'w:right="{_twips(profile.margin_outer_mm)}" '
        f'w:bottom="{_twips(profile.margin_bottom_mm)}" '
        f'w:left="{_twips(profile.margin_inner_mm)}" '
        'w:header="567" w:footer="567" w:gutter="0"/>'
        '</w:sectPr>'
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<w:body>{body}{section}</w:body></w:document>'
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>'
    )
    files = {
        '[Content_Types].xml': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '</Types>'
        ),
        '_rels/.rels': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        ),
        'word/document.xml': document_xml,
        'word/styles.xml': styles_xml,
        'word/_rels/document.xml.rels': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
            '</Relationships>'
        ),
        'word/footer1.xml': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
            '<w:fldSimple w:instr="PAGE"><w:r><w:rPr><w:sz w:val="16"/></w:rPr>'
            '<w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>'
        ),
    }
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = ZipInfo(name, _ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name].encode('utf-8'))
    return buffer.getvalue()


def _register_pdf_fonts():
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    root = Path(reportlab.__file__).resolve().parent / 'fonts'
    if 'LUKART_VERA' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('LUKART_VERA', str(root / 'Vera.ttf')))
    if 'LUKART_VERA_BOLD' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('LUKART_VERA_BOLD', str(root / 'VeraBd.ttf')))


def _wrap(text, font, size, width):
    from reportlab.pdfbase import pdfmetrics
    lines = []
    for logical in str(text).split('\n'):
        words = logical.split()
        if not words:
            lines.append('')
            continue
        current = words[0]
        for word in words[1:]:
            candidate = current + ' ' + word
            if pdfmetrics.stringWidth(candidate, font, size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_pdf(document: SemanticDocument, profile: RenderProfile) -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm

    _register_pdf_fonts()
    width = profile.page_width_mm * mm
    height = profile.page_height_mm * mm
    left = profile.margin_inner_mm * mm
    right = profile.margin_outer_mm * mm
    top = profile.margin_top_mm * mm
    bottom = profile.margin_bottom_mm * mm
    usable = width - left - right
    buffer = BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=(width, height),
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle('LUKART rendered document')
    pdf.setAuthor('LUKART ROS')
    pdf.setCreator('LUKART Rendering Engine 1.0.0')

    y = height - top
    page = 1

    def footer():
        pdf.setFont('LUKART_VERA', 8)
        pdf.drawCentredString(width / 2, bottom / 2, str(page))

    for token, text in _lines(document):
        style = _style(profile, token)
        font = 'LUKART_VERA_BOLD' if style.bold else 'LUKART_VERA'
        line_height = style.font_size_pt * 1.35
        wrapped = _wrap(text, font, style.font_size_pt, usable)
        needed = len(wrapped) * line_height + style.space_after_pt
        if y - needed < bottom:
            footer()
            pdf.showPage()
            page += 1
            y = height - top
        pdf.setFont(font, style.font_size_pt)
        for line in wrapped:
            if style.alignment == 'CENTER':
                x = width / 2
                pdf.drawCentredString(x, y, line)
            elif style.alignment == 'RIGHT':
                x = width - right
                pdf.drawRightString(x, y, line)
            else:
                pdf.drawString(left, y, line)
            y -= line_height
        y -= style.space_after_pt
    footer()
    pdf.save()
    return buffer.getvalue()


def render(document: SemanticDocument, profile: RenderProfile, formats=('DOCX', 'PDF')):
    if tuple(formats) != tuple(dict.fromkeys(formats)) or set(formats) != {'DOCX', 'PDF'}:
        raise ValueError('RENDER_FORMAT_COVERAGE')
    result = {}
    for format_name in formats:
        if format_name == 'DOCX':
            result[format_name] = (render_docx(document, profile), DOCX_MIME)
        elif format_name == 'PDF':
            result[format_name] = (render_pdf(document, profile), PDF_MIME)
        else:
            raise ValueError('UNSUPPORTED_RENDER_FORMAT')
    return result
