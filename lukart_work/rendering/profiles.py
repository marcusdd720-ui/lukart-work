"""Versioned render profiles.  No document content belongs here."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import reportlab

from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

from .contracts import RenderProfile


def _reportlab_font(name: str) -> Path:
    path = Path(reportlab.__file__).resolve().parent / "fonts" / name
    if not path.is_file():
        raise RuntimeError(f"RENDER_FONT_MISSING:{name}")
    return path


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


_REGULAR = _reportlab_font("Vera.ttf")
_BOLD = _reportlab_font("VeraBd.ttf")

OFFICIAL_PL_V1 = RenderProfile(
    profile_id="OFFICIAL_PL",
    version="1.0.0",
    locale="pl-PL",
    page_width_mm=210,
    page_height_mm=297,
    margin_top_mm=22,
    margin_right_mm=20,
    margin_bottom_mm=22,
    margin_left_mm=25,
    font_family="Bitstream Vera Sans",
    font_regular_sha256=_hash(_REGULAR),
    font_bold_sha256=_hash(_BOLD),
    body_font_pt=11,
    heading_font_pt=12,
    title_font_pt=13,
    line_spacing_milli=1150,
    paragraph_after_pt=6,
    section_before_pt=10,
    requests_label="Wnioski",
    attachments_label="Załączniki",
)


def profile_font_paths(profile: RenderProfile) -> tuple[Path, Path]:
    if (profile.profile_id, profile.version) != (OFFICIAL_PL_V1.profile_id, OFFICIAL_PL_V1.version):
        raise RuntimeError("RENDER_PROFILE_UNSUPPORTED")
    regular, bold = _REGULAR, _BOLD
    if _hash(regular) != profile.font_regular_sha256 or _hash(bold) != profile.font_bold_sha256:
        raise RuntimeError("RENDER_FONT_HASH_MISMATCH")
    return regular, bold


def profile_pin(profile: RenderProfile = OFFICIAL_PL_V1) -> VersionPin:
    return VersionPin(id=f"render-profile:{profile.profile_id}", version=profile.version, content_hash=digest(profile))
