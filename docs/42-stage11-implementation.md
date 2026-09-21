# Stage 11 — Rendering Engine implementation

## Boundary

`lukart_work.rendering.RenderEngine` is a deterministic presentation boundary. It accepts the existing `RenderRequest` and a trusted expected authorization hash. The request is rejected unless:

1. the request authorization equals the trusted expected value;
2. that value is the canonical binding of the exact `SemanticDocument` and render profile;
3. the profile is the exact registered `COURT_PL_A4` pin;
4. requested output formats are unique and allow-listed.

The renderer never queries the Case repository and never creates or mutates Facts, Evidence, Requests, Drafts, Decisions or Filing state.

## Profile

The initial profile is `COURT_PL_A4:1.0.0` and pins:

- A4 page size;
- 30 mm left binder margin, 20 mm top/right/bottom;
- 11 pt body typography and 1.25 line height;
- page numbering;
- DOCX, PDF, HTML and TXT output.

Profile identity is the SHA-256 digest of the complete normalized profile specification.

## Semantic representation

The renderer serializes exactly the fields already present in `SemanticDocument`: header, typed Party and Request references, ordered SectionText statements, attachments and optional signature-party reference. It does not resolve missing display names or request wording from CASE state because doing so would make the renderer a second source of legal/domain meaning.

## Formats

DOCX is generated as a minimal deterministic OOXML package with fixed ZIP timestamps and explicit A4/margin settings. Unicode text is stored as UTF-8 XML.

PDF is generated with ReportLab in invariant mode. The PDF renderer requires the Ubuntu 24.04 DejaVu Sans font at the profile-pinned path `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`; absence fails closed rather than falling back to a font that cannot represent Polish text. Output is A4 with bounded margins and page numbers. The runtime image is part of the execution environment and the rendered bytes remain hash-bound evidence.

HTML is static escaped markup with no script or external active content. TXT is exact UTF-8 semantic text.

## Post-render verification

Before returning any artifact, the service independently reads back the generated representation:

- TXT must equal the canonical semantic text exactly;
- HTML visible paragraph text must equal the semantic lines;
- DOCX `word/document.xml` paragraphs must equal the semantic lines and carry the semantic hash;
- PDF text is re-read with `pypdf` and must equal the semantic lines; the PDF metadata carries the semantic hash.

Any mismatch is fail-closed and no bundle is returned.

## Result contract

`RenderArtifactRecord` records format, media type, exact bytes SHA-256, byte length, semantic hash and profile pin. `RenderBundle` requires unique formats and consistent semantic/profile bindings and adds a verification hash over the complete artifact records.

Rendered bytes remain external artifacts, not canonical CASE state.
