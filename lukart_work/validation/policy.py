"""Exact normalized executable source pin, including reused closed-stage guards."""
from hashlib import sha256
from pathlib import Path
from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest


def validation_pin():
    root = Path(__file__).resolve().parents[1]
    files = sorted(p for p in root.rglob('*') if p.suffix in ('.py', '.sql'))
    return VersionPin(id='urn:lukart:work:ValidationEngine', version='1.0.0', content_hash=digest({
        p.relative_to(root).as_posix(): sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        for p in files
    }))
