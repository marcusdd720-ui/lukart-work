"""Stage 11 canonical rendering profile and implementation identity."""
from __future__ import annotations

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest
from .contracts import FontPolicy, PageSpec, RenderProfile, TokenStyle

_RENDERING_FILES = (
    "rendering/contracts.py",
    "rendering/policy.py",
    "rendering/compiler.py",
    "rendering/adapters.py",
    "rendering/service.py",
)


def official_pl_profile() -> RenderProfile:
    styles = (
        TokenStyle(token="document.body", font_size_pt=11, alignment="JUSTIFY", line_spacing=1.15,
                   space_after_pt=6, first_line_indent_mm=8),
        TokenStyle(token="document.heading.primary", font_size_pt=14, bold=True, alignment="CENTER",
                   line_spacing=1.1, space_before_pt=0, space_after_pt=14, keep_with_next=True),
        TokenStyle(token="document.heading.secondary", font_size_pt=11, bold=True, alignment="LEFT",
                   line_spacing=1.1, space_before_pt=10, space_after_pt=5, keep_with_next=True),
        TokenStyle(token="document.metadata", font_size_pt=9, alignment="RIGHT",
                   line_spacing=1.0, space_after_pt=3),
        TokenStyle(token="document.party_block", font_size_pt=10, alignment="LEFT",
                   line_spacing=1.05, space_after_pt=5),
        TokenStyle(token="document.request", font_size_pt=11, bold=True, alignment="JUSTIFY",
                   line_spacing=1.15, space_before_pt=4, space_after_pt=6, left_indent_mm=5),
        TokenStyle(token="document.legal_basis", font_size_pt=11, alignment="JUSTIFY",
                   line_spacing=1.15, space_after_pt=6, first_line_indent_mm=8),
        TokenStyle(token="document.quote", font_size_pt=10, italic=True, alignment="JUSTIFY",
                   line_spacing=1.1, space_before_pt=4, space_after_pt=6, left_indent_mm=8),
        TokenStyle(token="document.evidence_reference", font_size_pt=9, alignment="LEFT",
                   line_spacing=1.0, space_after_pt=4, left_indent_mm=5),
        TokenStyle(token="document.signature", font_size_pt=10, alignment="RIGHT",
                   line_spacing=1.0, space_before_pt=18, space_after_pt=0),
        TokenStyle(token="document.attachment", font_size_pt=9, alignment="LEFT",
                   line_spacing=1.0, space_before_pt=8, space_after_pt=3),
    )
    return RenderProfile(
        schema_version="1.0.0",
        profile_id="OFFICIAL_PL",
        version="1.0.0",
        locale="pl-PL",
        page=PageSpec(size="A4", margin_top_mm=24, margin_right_mm=22,
                      margin_bottom_mm=24, margin_left_mm=25),
        font=FontPolicy(
            family="DejaVu Serif",
            fallback_families=("Liberation Serif",),
            allow_fallback=True,
        ),
        styles=styles,
        header_text="",
        footer_text="",
    )


def profile_pin() -> VersionPin:
    profile = official_pl_profile()
    return VersionPin(id=profile.profile_id, version=profile.version, content_hash=digest(profile))


def resolve_profile(pin: VersionPin) -> RenderProfile:
    expected = profile_pin()
    if pin != expected:
        raise ValueError("UNKNOWN_RENDER_PROFILE")
    return official_pl_profile()


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


def renderer_artifact(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    files = {}
    for relative in _RENDERING_FILES:
        path = root / relative
        data = path.read_bytes().replace(b"\r\n", b"\n")
        files[relative] = sha256(data).hexdigest()
    return {
        "profile": "SHA-256 source identity; CRLF normalized to LF",
        "files": files,
        "dependencies": {
            "python-docx": _package_version("python-docx"),
            "reportlab": _package_version("reportlab"),
        },
    }


def renderer_pin(root=None) -> VersionPin:
    return VersionPin(
        id="lukart-work-renderer",
        version="1.0.0",
        content_hash=digest(renderer_artifact(root)),
    )


def adapter_pin(output_format: str, root=None) -> VersionPin:
    if output_format not in {"DOCX", "PDF"}:
        raise ValueError("UNSUPPORTED_FORMAT")
    renderer = renderer_pin(root)
    dependency = "python-docx" if output_format == "DOCX" else "reportlab"
    return VersionPin(
        id=f"lukart-work-{output_format.lower()}-adapter",
        version="1.0.0",
        content_hash=digest({
            "renderer": renderer.content_hash,
            "format": output_format,
            "dependency": dependency,
            "dependency_version": _package_version(dependency),
        }),
    )


def stage11_actions(actions=frozenset()):
    return frozenset(actions) | {"RenderDocument", "GetValidation"}
