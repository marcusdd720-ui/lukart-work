# Stage 11 — Rendering Engine acceptance

Status: IMPLEMENTATION UNDER ASSURANCE.

Base: `74364cb7b648feaff30cff465a5beade8d5f3498`.
Source branch: `work/stage11-rendering-engine`.

## Required assurance

Closure requires all of the following on one immutable candidate SHA:

- Stage 11 focused renderer tests PASS with zero failures/errors/skips;
- full historical regression PASS;
- schema export and independent Draft 2020-12 validation PASS;
- package/export equivalence PASS;
- global manifest/integrity PASS;
- generated evidence reproducibility PASS;
- exact candidate promoted to a GitHub-verified `codex/stage11-*` commit with identical tree;
- Stage 10 and Stage 11 exact-SHA workflow-dispatch evidence PASS;
- independent exact-SHA review with P0=0 and P1=0;
- guarded merge and exact-main post-merge verification.

## Focused adversarial coverage

The Stage 11 suite covers:

- all four output formats and exact artifact hashing;
- Polish Unicode PDF round-trip;
- A4 DOCX page size and binder margin;
- no invented FINAL/CERTIFIED state in presentation output;
- HTML escaping of hostile text;
- deterministic byte-for-byte output;
- rejection of wrong and forged authorization bindings;
- rejection of unknown profile pins;
- rejection of empty, duplicate and unsupported output formats;
- no mutation of the immutable semantic input.

This document is builder-side evidence only. It is not an independent review and does not authorize merge by itself.
