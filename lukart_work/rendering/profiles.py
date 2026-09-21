"""Versioned render profiles. No document content belongs here.

OFFICIAL_PL_V1 binds exact font bytes.  A host with a different or missing font must fail
closed and requires an explicit profile-version change rather than silent substitution.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

from .contracts import RenderProfile

_FONT_ROOT = Path("/usr/share/fonts/truetype/liberation")
_REGULAR = _FONT_ROOT / "LiberationSerif-Regular.ttf"
_BOLD = _FONT_ROOT / "LiberationSerif-Bold.ttf"
_REGULAR_SHA256 = "9caef765d2e891c10dd73658894f01e660fe0c1c83e0bda7d6edf561d8f623d4"
_BOLD_SHA256 = "443a4dbd694b6e4689925947b456e0532e10b19c90fa32eb39ea6c2cd9db9ebd"


def _hash(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"RENDER_FONT_MISSING:{path}")
    return sha256(path.read_bytes()).hexdigest()


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
    font_family="Liberation Serif",
    font_regular_sha256=_REGULAR_SHA256,
    font_bold_sha256=_BOLD_SHA256,
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
    if profile.font_regular_sha256 != _REGULAR_SHA256 or profile.font_bold_sha256 != _BOLD_SHA256:
        raise RuntimeError("RENDER_PROFILE_FONT_PIN_INVALID")
    actual_regular = _hash(_REGULAR)
    actual_bold = _hash(_BOLD)
    if actual_regular != profile.font_regular_sha256 or actual_bold != profile.font_bold_sha256:
        raise RuntimeError(
            f"RENDER_FONT_HASH_MISMATCH:regular={actual_regular}:bold={actual_bold}"
        )
    return _REGULAR, _BOLD


def profile_pin(profile: RenderProfile = OFFICIAL_PL_V1) -> VersionPin:
    return VersionPin(
        id=f"render-profile:{profile.profile_id}",
        version=profile.version,
        content_hash=digest(profile),
    )
