# Generator Pism v1.0 — Operator GO-LIVE Runbook

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
