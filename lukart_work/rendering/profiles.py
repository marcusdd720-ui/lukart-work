"""Versioned render profiles. No document content belongs here.

OFFICIAL_PL_V1 binds exact font bytes. A host with a different or missing font must fail
closed and requires an explicit profile-version change rather than silent substitution.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import fontpkg

from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

from .contracts import RenderProfile, StyleSpec

_REGULAR = Path(fontpkg.path("Lato", weight=400, style="normal"))
_BOLD = Path(fontpkg.path("Lato", weight=700, style="normal"))


def _style(
    token: str,
    *,
    size: int,
    bold: bool = False,
    before: int = 0,
    after: int = 6,
    left: int = 0,
    hanging: int = 0,
    alignment: str = "LEFT",
    keep_with_next: bool = False,
    keep_together: bool = False,
    widow_control: bool = True,
    page_break_before: bool = False,
) -> StyleSpec:
    return StyleSpec(
        token=token,
        font_size_pt=size,
        bold=bold,
        line_spacing_milli=1150,
        space_before_pt=before,
        space_after_pt=after,
        left_indent_mm=left,
        hanging_indent_mm=hanging,
        alignment=alignment,
        keep_with_next=keep_with_next,
        keep_together=keep_together,
        widow_control=widow_control,
        page_break_before=page_break_before,
    )


def _hash(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"RENDER_FONT_MISSING:{path}")
    return sha256(path.read_bytes()).hexdigest()


_REGULAR_SHA256 = _hash(_REGULAR)
_BOLD_SHA256 = _hash(_BOLD)


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
    font_family="Lato",
    font_regular_sha256=_REGULAR_SHA256,
    font_bold_sha256=_BOLD_SHA256,
    styles=(
        _style("document.heading.primary", size=13, bold=True, after=10, alignment="CENTER", keep_with_next=True),
        _style("document.heading.secondary", size=12, bold=True, before=10, after=6, keep_with_next=True),
        _style("document.party_block", size=11, after=8, keep_together=True),
        _style("document.request", size=11, left=7, hanging=5, after=5, keep_together=True),
        _style("document.body", size=11, after=6, alignment="JUSTIFY"),
        _style("document.legal_basis", size=11, after=6, alignment="JUSTIFY", keep_together=True),
        _style("document.quote", size=10, left=7, after=6, keep_together=True),
        _style("document.signature", size=11, before=18, after=0, keep_together=True),
        _style("document.attachment", size=11, left=7, hanging=5, after=4, keep_together=True),
    ),
    header_text=None,
    footer_text=None,
    page_numbers=True,
    header_footer_font_pt=9,
    footer_offset_mm=10,
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


def profile_styles(profile: RenderProfile) -> dict[str, StyleSpec]:
    styles = {style.token: style for style in profile.styles}
    if len(styles) != len(profile.styles):
        raise RuntimeError("RENDER_STYLE_DUPLICATE")
    return styles


def profile_pin(profile: RenderProfile = OFFICIAL_PL_V1) -> VersionPin:
    return VersionPin(
        id=f"render-profile:{profile.profile_id}",
        version=profile.version,
        content_hash=digest(profile),
    )
