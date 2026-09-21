# Stage 11A — Rendering Architecture Gate

Status: PROPOSED — DECISION GATE
Repository: `marcusdd720-ui/lukart-work`
Base SHA: `74364cb7b648feaff30cff465a5beade8d5f3498`
Scope: architecture of Stage 11 Rendering Engine only
Non-goals: Legal Document Compiler, Legal Semantic IR, AdvocacyPolicy, Workbench UI, Stage 12

## 1. Problem

Stage 11 cannot close because the repository contains trusted delivery/assurance infrastructure,
but the actual Rendering Engine and `tests/test_stage11.py` are not yet implemented.

The architecture baseline already requires:

```
SemanticDocument
+
RenderProfile
->
DOCX / PDF / HTML / TXT
```

and separates legal reasoning from presentation.

The design must therefore solve four production problems at once:

1. deterministic transformation from validated semantic content to a renderable representation;
2. stable legal-document styling independent of drafting/model behavior;
3. exact provenance and artifact identity for every output;
4. adapter isolation so future render formats do not change semantic content.

## 2. Hard constraints

The renderer MUST NOT:

- create, infer, strengthen, weaken or delete legal propositions;
- add facts, legal rules, requests or citations;
- change document strategy;
- silently substitute fonts, tokens or profiles;
- accept implicit `latest` profiles;
- release an artifact when required inputs or profile identity are unknown.

The renderer MUST:

- be deterministic for the same canonical inputs where the target format permits deterministic bytes;
- bind every output to exact `SemanticDocument`, `RenderProfile`, renderer implementation and output format;
- fail closed on unsupported semantic nodes or missing style tokens;
- preserve semantic ordering;
- produce explicit artifact hashes;
- keep semantic identity separate from presentation identity;
- be testable without an AI model or network access.

## 3. Alternatives considered

### Variant A — direct format adapters

```
SemanticDocument + RenderProfile -> DOCX
SemanticDocument + RenderProfile -> PDF
```

Advantages:
- smallest implementation;
- fast initial delivery.

Weaknesses:
- style logic duplicated between formats;
- difficult cross-format equivalence proof;
- high probability of DOCX/PDF drift;
- future format additions multiply presentation logic.

Conclusion: REJECT as the long-term canonical architecture.

### Variant B — normalized RenderTree + isolated adapters

```
SemanticDocument
+
RenderProfile
        |
        v
Normalized RenderTree
        |
        +--> DOCX adapter
        +--> PDF adapter
        +--> HTML adapter
        +--> TXT/Markdown adapter
```

Advantages:
- one canonical presentation interpretation;
- adapters become serialization concerns rather than design engines;
- cross-format semantic and visual invariants can be tested centrally;
- format-specific volatility can be isolated;
- future editor/preview can consume the same tree.

Cost:
- one additional internal representation;
- requires strict versioning and validation.

Conclusion: RECOMMENDED.

### Variant C — external rendering service

```
SemanticDocument -> remote renderer -> artifact
```

Advantages:
- potentially powerful layout engine.

Weaknesses:
- network dependency;
- provider/version drift;
- weaker long-term reproducibility;
- larger security and privacy surface;
- harder exact-SHA assurance.

Conclusion: REJECT for Stage 11 core. May be considered later only as a replaceable adapter.

## 4. Recommended architecture

Adopt Variant B.

### 4.1 Canonical layers

```
Validated Draft
    |
    v
SemanticDocument
    |
    v
RenderProfile
    |
    v
RenderCompiler
    |
    v
Normalized RenderTree
    |
    +--> DOCXAdapter
    +--> PDFAdapter
    +--> HTMLAdapter
    +--> TextAdapter
    |
    v
RenderedArtifact
    |
    v
RenderValidation
```

The name `RenderCompiler` is intentionally limited to presentation compilation.
It is NOT the future Legal Document Compiler.

### 4.2 SemanticDocument

Stage 11 consumes a validated semantic document only.
No drafting occurs in this layer.

Current contract remains the starting point:

- header;
- parties;
- requests;
- sections;
- attachments;
- signature party;
- exact draft reference;
- exact snapshot hash.

Stage 11 may extend the rendering contract only where required to represent presentation semantics
already present in validated content. It must not add legal meaning.

### 4.3 RenderProfile

`RenderProfile` is a strict, versioned, content-addressed configuration.

It maps semantic tokens to visual values, for example:

```
document.body
document.heading.primary
document.heading.secondary
document.metadata
document.party_block
document.request
document.legal_basis
document.quote
document.evidence_reference
document.signature
document.attachment
```

A profile MUST define:

- page size;
- margins;
- default font family;
- fallback policy;
- font size;
- line spacing;
- paragraph spacing;
- heading hierarchy;
- list indentation;
- page-break rules;
- widow/orphan behavior where supported;
- keep-with-next rules where supported;
- header/footer rules;
- signature spacing;
- metadata behavior;
- locale/language;
- target format constraints.

Unknown or missing required tokens are blocking errors.

### 4.4 Normalized RenderTree

The `RenderTree` is an immutable, renderer-neutral presentation representation.

Minimum node families:

- Document;
- Block;
- Paragraph;
- Heading;
- PartyBlock;
- RequestBlock;
- LegalBasisBlock;
- QuoteBlock;
- EvidenceReferenceBlock;
- List;
- ListItem;
- AttachmentList;
- SignatureBlock;
- PageBreak;
- InlineText.

Every node carries:

- stable node identifier;
- semantic role/token;
- source semantic reference;
- normalized text;
- resolved style token reference;
- deterministic order.

The tree MUST contain no legal inference logic.

### 4.5 Identity model

Stage 11 introduces separate identities:

`semantic_digest`
: hash of the canonical semantic document relevant to rendering.

`profile_digest`
: hash of the exact canonical RenderProfile.

`render_tree_digest`
: hash of the canonical normalized RenderTree.

`presentation_digest`
: hash binding render tree + profile + output format + renderer version.

`artifact_byte_hash`
: SHA-256 of the exact emitted bytes.

This separation allows the system to distinguish:

- legal/semantic change;
- style/layout change;
- serializer-only byte change.

## 5. Determinism contract

For identical:

- semantic document;
- render profile;
- renderer version;
- adapter version;
- output format;

the system SHOULD produce identical artifact bytes.

Where a format introduces volatile metadata, the adapter MUST normalize it where technically feasible.
If byte determinism cannot be guaranteed for a specific format, this limitation MUST be explicit,
and `presentation_digest` remains the canonical presentation identity while `artifact_byte_hash`
identifies the concrete emitted artifact.

No output may be called reproducible merely because it looks visually similar.

## 6. DOCX strategy

DOCX is a package of XML parts and therefore requires normalization of:

- ZIP entry ordering;
- ZIP timestamps;
- document properties/timestamps;
- relationship identifiers where generated;
- style identifiers;
- numbering identifiers;
- metadata fields.

Stage 11 should prefer deterministic generation rather than post-hoc visual cleanup.

DOCX styling MUST be driven entirely by RenderProfile tokens, not scattered direct formatting.

## 7. PDF strategy

PDF output MUST be generated from the same RenderTree and RenderProfile, not by separately rebuilding
the document structure.

PDF adapter requirements:

- deterministic metadata where feasible;
- embedded or strictly resolved approved fonts where licensing permits;
- explicit page-size/margin rules;
- stable pagination tests for golden cases;
- no automatic font substitution without a blocking finding or explicitly approved fallback.

The implementation choice for the PDF serialization library is NOT fixed by this gate.
It must be validated empirically for deterministic output, Unicode/Polish support and long-term maintainability.

## 8. Font policy

The renderer MUST NOT select fonts opportunistically.

A RenderProfile specifies an allowed font family and fallback policy.
If an approved font is unavailable, the renderer fails closed unless the exact profile explicitly
permits a deterministic fallback.

The project must not distribute third-party font files unless licensing explicitly permits it.
Tests may verify font identity without checking font binaries into the repository.

## 9. Validation model

Stage 11 needs a dedicated render validation layer.

Minimum blocking checks:

- semantic document identity matches the validated draft;
- exact profile pin resolves;
- all semantic roles resolve to style tokens;
- no unsupported node type;
- no missing required text;
- no duplicated/dropped semantic node;
- semantic order preserved;
- adapter reports exact format/media type;
- artifact byte hash is correct;
- presentation digest is correct;
- repeated same-input render is stable under the supported determinism contract;
- no hidden change in semantic digest.

Golden layout tests should additionally check:

- page count;
- heading hierarchy;
- list nesting;
- mandatory blocks;
- deterministic paragraph ordering;
- stable page-break behavior for controlled fixtures.

Pixel-perfect screenshot tests are supplementary, not the sole correctness proof.

## 10. Artifact contract

A future typed `RenderedArtifact` should bind at minimum:

```
tenant_id
case_id
draft_ref
snapshot_hash
semantic_digest
profile_pin
profile_digest
renderer_pin
adapter_pin
format
media_type
render_tree_digest
presentation_digest
artifact_byte_hash
byte_length
created_at
```

The artifact bytes belong in the existing storage category `render`.

## 11. Fail-closed rules

Rendering MUST fail when:

- draft is not eligible for rendering;
- input snapshot identity is stale or mismatched;
- profile pin cannot be resolved exactly;
- required style token is absent;
- unsupported semantic node is encountered;
- adapter attempts silent fallback;
- output hash cannot be established;
- semantic or presentation identity cannot be reconstructed;
- deterministic rerender contract fails for a format declared deterministic.

## 12. Security and privacy

Rendering is a local transformation boundary.

Stage 11 core:

- must not send document content to external rendering providers;
- must not accept authorization from AI-generated payloads;
- must preserve tenant/case scope;
- must not log sensitive document body text in normal operational logs;
- must store render bytes through the existing scoped storage boundary.

## 13. Relationship to future Legal Document Compiler

The following remain explicitly DEFERRED:

- Legal Semantic IR;
- LegalDraftingPolicy;
- AdvocacyPolicy;
- Legal Surface Realizer;
- Semantic Equivalence Gate for language transformation;
- Legal Writing Gold Corpus;
- rhetorical optimization.

Stage 11 must expose clean interfaces so those future layers can produce `SemanticDocument`
without requiring renderer redesign.

## 14. Acceptance criteria for Stage 11 implementation

Stage 11 implementation is acceptable only when all of the following exist:

1. typed and versioned rendering contracts;
2. `RenderProfile` with strict token resolution;
3. deterministic `RenderCompiler` producing normalized `RenderTree`;
4. DOCX adapter;
5. PDF adapter;
6. artifact identity and storage binding;
7. focused Stage 11 tests in `tests/test_stage11.py`;
8. adversarial render tests;
9. full historical regression;
10. schema/package/manifest reproducibility checks;
11. exact-SHA CI;
12. independent exact-SHA review;
13. merge with expected-head protection;
14. post-merge exact-main validation.

No Stage 12 work is included.

## 15. Recommended implementation order

```
11.1 contracts + identity model
11.2 RenderProfile + design tokens
11.3 RenderCompiler + RenderTree
11.4 DOCX adapter
11.5 PDF adapter
11.6 artifact persistence binding
11.7 render validation
11.8 deterministic/golden/adversarial tests
11.9 full regression + evidence materialization
11.10 exact-SHA review / merge / post-merge
```

## 16. Decision

RECOMMENDATION: ADOPT Variant B — normalized RenderTree with isolated format adapters.

Reason:
it is the smallest architecture that prevents cross-format drift while preserving the baseline
separation between legal semantics and presentation. It provides a stable 15+ year extension point
for future formats, preview/editor functions and the future Legal Document Compiler without pulling
those deferred features into Stage 11.

This document does not itself authorize implementation. Promotion from PROPOSED to ACCEPTED requires
the architecture decision gate.
