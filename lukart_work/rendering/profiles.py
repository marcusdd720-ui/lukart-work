"""Versioned semantic render profiles. No legal or factual logic belongs here."""
from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

COURT_PL_SPEC = {
    "id": "COURT_PL_A4",
    "page": {"width_mm": 210, "height_mm": 297},
    "margins_mm": {"top": 20, "bottom": 20, "left": 30, "right": 20},
    "font_family": "Bitstream Vera",
    "body_pt": 11,
    "heading_pt": 13,
    "line_height": 1.25,
    "page_numbers": True,
    "formats": ["DOCX", "PDF", "HTML", "TXT"],
}


def court_pl_profile() -> VersionPin:
    return VersionPin(
        id="urn:lukart:work:render-profile:COURT_PL_A4",
        version="1.0.0",
        content_hash=digest(COURT_PL_SPEC),
    )


def profile_spec(pin: VersionPin) -> dict:
    expected = court_pl_profile()
    if pin != expected:
        raise ValueError("UNKNOWN_RENDER_PROFILE")
    return COURT_PL_SPEC
