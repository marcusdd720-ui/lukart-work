# Generator Pism — CASE-first local execution

The rejected payment, complaint and reply packs have been removed. The built-in
runtime catalogue is empty and rejects their identifiers. No replacement
templates are registered. Historical records and evidence retain their pins.

Hosts construct the existing operator with an explicit trusted
`case_profile: FinalizationProfile`, repository, authority, provider and execution
profiles. They use authenticated CASE commands for sources, evidence, HUMAN
decisions, snapshot, plan, drafting, validation and rendering. An intake payload
cannot substitute for those records (`CASE_COMMANDS_REQUIRED`).

`operator.export_local(tenant_id=..., case_id=..., render_id=..., token=...,
output=...)` reads persisted DOCX/PDF through the existing scoped finalization
query. It writes a fresh directory containing exact bytes, hashes and
`preview.html`. Open the HTML locally for the PDF preview and DOCX/PDF downloads.
This operation does not approve or release a document.

The E2E script below now exercises existing synthetic CASE service fixtures and
the operator's authorized local export. Its evidence declares that scope; it
does not demonstrate admission of a legal document type or real HUMAN decisions.
Full regression and CI are pending after the authorized implementation phase.

## Historical v1 runbook context

Status: technical execution runbook. Legal/type admission remains HUMAN_REQUIRED.

## Purpose

This runbook exercises the production `GeneratorPismOperator` facade end to end on synthetic data:

`intake → case/evidence → procedure → plan → controlled draft → HUMAN semantic review → validation → render → HUMAN final approval → FINAL release → 10-member package`.

It does not use customer data, does not make network model calls and does not bypass HUMAN decisions.

## Preconditions

- exact repository checkout;
- Python 3.14;
- isolated PostgreSQL prepared with `scripts/prepare_ci_database.py`;
- `LUKART_TEST_ADMIN_DSN`, `LUKART_TEST_RUNTIME_PASSWORD`, `LUKART_TEST_DSN`;
- `LUKART_TEST_EGRESS_HOST_PASSWORD`, `LUKART_TEST_EGRESS_DSN` for the isolated egress host role;
- dependencies installed with `python -m pip install '.[postgres,ingestion]'`.

Never point this E2E at a production/client database.

## Execute

```bash
export TESTED_SHA="$(git rev-parse HEAD)"
python -B -X utf8 scripts/prepare_ci_database.py
python -B -X utf8 scripts/run_generator_pism_operator_e2e.py --output build/generator-pism/operator-e2e
python -B -X utf8 scripts/verify_generator_pism_operator_evidence.py \
  --evidence build/generator-pism/operator-e2e/evidence.json \
  --package-dir build/generator-pism/operator-e2e/package \
  --expected-sha "$TESTED_SHA" \
  --output build/generator-pism/operator-e2e/verifier.json
```

## PASS contract

PASS requires exact type-pack intake, authenticated production-service calls through `GeneratorPismOperator`, exact request-bound drafting, HUMAN evidence/fact/legal/snapshot/plan/review/final-approval decisions, VALIDATED pre-render state, persisted hash-verified DOCX/PDF, FINAL release, exactly 10 durable package members, event/outbox equality and independent exact-SHA verification.

## Scope boundary

This proves the technical Generator Pism v1.0 execution path. It does not by itself admit a real Polish legal document type, certify legal advice, sign a document, file it externally or authorize automatic submission. Those remain explicit HUMAN/domain gates.
# Offline verifier repair scope

The verifier validates canonical typed package records, exact member bytes and
manifest lengths/hashes, cross-case/render/release/approval bindings, audit chain,
and parsed DOCX/PDF structures with render-receipt hashes. Its checks remain
enabled under `python -O`; duplicate JSON keys are rejected. Output destinations
must be fresh, so a failed rerun cannot reuse a prior report as its result.

`PASS` from this verifier means `OFFLINE_PACKAGE_INTEGRITY_ONLY`. Self-contained
package metadata cannot independently authenticate the HUMAN decisions, database
issuance or source originals. Those require separate evidence and existing gates.
Synthetic native-contract positive fixtures prove verifier behavior only; they
are not a production operator E2E, real HUMAN review or live AI execution.
