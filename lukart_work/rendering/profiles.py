"""Pinned Stage 11 legal-document visual profile and executable renderer identity."""
from hashlib import sha256
from pathlib import Path

from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

from .contracts import RenderProfile, RenderStyleToken


def official_pl_profile():
    def style(token, size, *, bold=False, alignment='LEFT', after=6):
        return RenderStyleToken(
            token=token,
            font_family='LUKART_VERA',
            font_size_pt=size,
            bold=bold,
            alignment=alignment,
            space_after_pt=after,
        )
    return RenderProfile(
        profile_id='OFFICIAL_PL',
        version='1.0.0',
        page_width_mm=210,
        page_height_mm=297,
        margin_inner_mm=30,
        margin_outer_mm=20,
        margin_top_mm=20,
        margin_bottom_mm=20,
        styles=(
            style('document.body', 11, alignment='JUSTIFY', after=6),
            style('document.heading.primary', 14, bold=True, after=12),
            style('document.heading.secondary', 12, bold=True, after=8),
            style('document.metadata', 9, after=4),
            style('document.party_block', 10, after=6),
            style('document.request', 11, bold=True, after=8),
            style('document.legal_basis', 10, after=6),
            style('document.quote', 10, after=6),
            style('document.signature', 11, alignment='RIGHT', after=6),
            style('document.attachment', 9, after=3),
        ),
    )


def profile_pin():
    profile = official_pl_profile()
    return VersionPin(
        id='urn:lukart:work:RenderProfile:OFFICIAL_PL',
        version=profile.version,
        content_hash=digest(profile),
    )


def renderer_pin():
    root = Path(__file__).resolve().parent
    files = sorted(path for path in root.glob('*.py') if path.is_file())
    return VersionPin(
        id='urn:lukart:work:RenderingEngine',
        version='1.0.0',
        content_hash=digest({
            path.name: sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for path in files
        }),
    )
