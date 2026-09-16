"""Bounded deterministic P0 adapters. No network, filesystem extraction or model calls."""
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from .models import ExtractionBody, ExtractedFragment, IngestionCandidate

MAX_TEXT = 500000
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


class NoDoctype(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError('XML_DOCTYPE_FORBIDDEN')


def identify(data, declared):
    if data.startswith(b'%PDF-'):
        return 'application/pdf', 'PDF'
    if data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'II*\x00', b'MM\x00*')):
        return 'image/*', 'IMAGE'
    if data.startswith(b'PK'):
        with ZipFile(BytesIO(data)) as archive:
            return (DOCX, 'DOCUMENT') if 'word/document.xml' in archive.namelist() else ('application/zip', 'UNKNOWN')
    if declared == 'message/rfc822':
        return declared, 'EMAIL'
    if declared == 'text/plain':
        # A MIME assertion alone cannot turn arbitrary binary bytes into text.
        text = data.decode('utf-8-sig')
        if any(ord(c) < 32 and c not in '\n\r\t\f' for c in text):
            raise ValueError('BINARY_TEXT')
        return declared, 'TEXT'
    return 'application/octet-stream', 'UNKNOWN'


def docx_fragments(data):
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > 1000 or len(set(names)) != len(names) or sum(e.file_size for e in entries) > 16000000:
            raise ValueError('ARCHIVE_LIMIT')
        if any(e.flag_bits & 1 or e.file_size > 4000000 for e in entries):
            raise ValueError('ARCHIVE_LIMIT')
        xml = archive.read('word/document.xml')
        if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
            raise ValueError('XML_ENTITY')
        root = ET.fromstring(xml, parser=ET.XMLParser(target=NoDoctype()))
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        rows = []
        for i, paragraph in enumerate(root.iter(ns + 'p'), 1):
            parts = []
            for item in paragraph.iter():
                if item.tag == ns + 't':
                    parts.append(item.text or '')
                elif item.tag == ns + 'tab':
                    parts.append('\t')
                elif item.tag in (ns + 'br', ns + 'cr'):
                    parts.append('\n')
            rows.append(('PARAGRAPH', str(i), ''.join(parts)))
        return rows


def email_fragments(data):
    message = BytesParser(policy=policy.default).parsebytes(data)
    if not any(message.get(h) for h in ('From', 'To', 'Subject', 'Date')):
        raise ValueError('INVALID_EMAIL')
    rows = [('HEADER', h, str(message[h])) for h in ('From', 'To', 'Subject', 'Date') if message.get(h)]
    partial = False
    for i, part in enumerate(message.walk(), 1):
        if i > 1000 or part.defects:
            raise ValueError('MIME_LIMIT_OR_DEFECT')
        if part.is_multipart():
            continue
        if part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment':
            raw = part.get_payload(decode=True)
            rows.append(('MIME_PART', str(i), raw.decode(part.get_content_charset() or 'ascii', errors='strict')))
        else:
            partial = True
    return rows, partial


def candidates_for(fragments):
    items = []
    patterns = (
        ('DATE', r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\b'),
        ('AMOUNT', r'\b\d+(?:[ .,]\d{3})*(?:[,.]\d{1,4})?\s*(?:PLN|EUR|USD|zł)\b'),
        ('PARTY', r'(?im)^(?:Powód|Pozwany|Strona|Nadawca|Odbiorca):\s*[^\r\n]+'),
    )
    for fragment in fragments:
        text = fragment.text
        if fragment.unit == 'HEADER' and fragment.position in ('From', 'To'):
            items.append(IngestionCandidate(kind='PARTY', fragment=fragment.index, start=0, end=len(text), quote=text))
        # Quotes are proposals only: no inference that a sentence is a true fact.
        for kind in ('FACT', 'EVIDENCE'):
            items.append(IngestionCandidate(kind=kind, fragment=fragment.index, start=0, end=len(text), quote=text))
        for kind, pattern in patterns:
            for match in re.finditer(pattern, text):
                items.append(IngestionCandidate(kind=kind, fragment=fragment.index,
                    start=match.start(), end=match.end(), quote=match.group()))
                if len(items) > 4000:
                    raise ValueError('CANDIDATE_LIMIT')
    return tuple(items)


def extract(data, declared):
    """Called only in a disposable worker; callers receive closed, safe outcomes."""
    media, classification = identify(data, declared)
    warnings = ['UNTRUSTED_SOURCE', 'REVIEW_REQUIRED']
    status, rows = 'EXTRACTED', []
    if classification == 'TEXT':
        rows = [('LINE', str(i), text) for i, text in enumerate(data.decode('utf-8-sig').splitlines(), 1)]
    elif classification == 'DOCUMENT':
        rows = docx_fragments(data)
        warnings.append('PARTIAL_EXTRACTION')  # Headers, drawings, footnotes are not flattened silently.
    elif classification == 'EMAIL':
        rows, partial = email_fragments(data)
        if partial:
            warnings.append('PARTIAL_EXTRACTION')
    elif classification == 'PDF':
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError('PDF_LIMIT_OR_ENCRYPTED')
        for i, page in enumerate(reader.pages, 1):
            rows.append(('PAGE', str(i), page.extract_text() or ''))
        # Text order/layout and images cannot be certified by a text extractor.
        warnings.append('PARTIAL_EXTRACTION')
        if any(not text.strip() for _, _, text in rows):
            warnings.append('OCR_REQUIRED')
    elif classification == 'IMAGE':
        status = 'NEEDS_OCR'
        warnings.append('OCR_REQUIRED')
    else:
        status = 'UNSUPPORTED'
        warnings.append('UNSUPPORTED_FORMAT')
    if sum(len(text) for _, _, text in rows) > MAX_TEXT or len(rows) > 1000:
        raise ValueError('TEXT_LIMIT')
    fragments = tuple(ExtractedFragment(index=i, unit=unit, position=position,
        text=text, text_hash=sha256(text.encode()).hexdigest())
        for i, (unit, position, text) in enumerate(row for row in rows if row[2].strip()))
    if status == 'EXTRACTED' and not fragments:
        status = 'NEEDS_OCR' if classification == 'PDF' else 'EMPTY'
        warnings.append('OCR_REQUIRED' if classification == 'PDF' else 'NO_TEXT')
    return ExtractionBody(media_type=media, classification=classification, status=status,
        fragments=fragments, candidates=candidates_for(fragments), warnings=tuple(dict.fromkeys(warnings)))
