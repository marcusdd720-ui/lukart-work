"""Local copies and a browser preview of existing, authorized render bytes."""
from hashlib import sha256
from pathlib import Path
import json

from .service import _validate_docx, _validate_pdf


def export_local(docx: bytes, pdf: bytes, output) -> Path:
    # Validate both before creating any output; never overwrite previous exports.
    _validate_docx(docx)
    _validate_pdf(pdf)
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "document.docx").write_bytes(docx)
    (directory / "document.pdf").write_bytes(pdf)
    (directory / "hashes.json").write_text(json.dumps({
        "document.docx": sha256(docx).hexdigest(),
        "document.pdf": sha256(pdf).hexdigest(),
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (directory / "preview.html").write_text(
        '<!doctype html><html lang="pl"><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; object-src \'self\'; style-src \'unsafe-inline\'">'
        '<title>Podgląd dokumentu</title><body>'
        '<p><a href="document.docx" download>Pobierz DOCX</a> · '
        '<a href="document.pdf" download>Pobierz PDF</a></p>'
        '<object data="document.pdf" type="application/pdf" '
        'style="width:100%;height:90vh">'
        '<a href="document.pdf">Otwórz PDF</a></object></body></html>',
        encoding="utf-8",
    )
    return directory / "preview.html"
