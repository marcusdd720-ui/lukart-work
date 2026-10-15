# Generator Pism — CASE-first local execution

## Local authenticated operator host

Implemented entry point: `lukart_work.operator_host`. It serves a request UI at
`http://127.0.0.1:8765/` and forwards explicit JSON commands/queries to the existing
CASE services. Paste your process-local capability into the password field. The
host retains existing actor, scope, permission, validation and HUMAN boundaries.
It creates no CASE records or decisions automatically. Tokens are not stored in
browser storage; logs omit requests. Restart requires trusted token provisioning.
Binary service reads download exact bytes; existing local export remains available
through the Python facade. The host does not accept filesystem export paths.

The shell now has explicit tenant/CASE fields and an Open CASE query, plus render
ID controls for persisted PDF preview and DOCX download. These controls issue the
existing scoped queries; they do not create a CASE, draft, approval or release.
The JSON editor still supplies explicit drafting/editing/approval requests to the
existing services. It is not a guided drafting or HUMAN review workflow. The PDF
frame is sandboxed; browser PDF support and the real workflow are NOT VERIFIED.
Clear private session clears the token, request, identifiers, result and artifact
URLs. No browser storage is used. Close the browser session after private work.

Duplicate Host, Origin, Sec-Fetch-Site, Authorization, Content-Type and
Content-Length headers are rejected. Earlier local verification executed 20
focused tests successfully, including 40/40 HTTP 413 attempts. Rejected-upload
draining keeps MAX_BODY unchanged, discards at most MAX_BODY + 1 bytes in chunks
of at most 64 KiB, and has a total one-second deadline. A stalled rejected upload
can occupy the single server thread and authority lock for that bounded period.
An oversized hostile stream may still be disconnected without a delivered 413.

A trusted local Python configuration file must define `build_operator()` returning
`GeneratorPismOperator` with an explicit `case_profile`, the actual repository,
authority, provider, drafting profiles and package profile. Its administrator must
provision only authenticated actors and explicitly authorized CASE capabilities,
and deliver tokens privately. No test imports, synthetic profiles or invented
HUMAN decisions belong in a real CASE configuration. Configuration is executable
trusted host code; never use an uploaded source document as configuration. The host
does not perform migrations, administrative provisioning or legal-type admission.

## Explicit configuration point

`lukart_work.operator_config.build_operator` assembles the existing services from
six explicit trusted objects. `examples/case_operator_host.py` is an unbound
entry-point template: invoking it unchanged must exit with
`HOST_CONFIGURATION_FAILED`. It contains no credentials, CASE identifiers,
actors, grants, profiles or approvals. Copy it into administrator-controlled
configuration outside Git and bind the required objects there:

```python
from functools import partial
from lukart_work.operator_config import build_operator as assemble_operator

build_operator = partial(
    assemble_operator,
    repository=repository,
    authority=authority,
    case_profile=case_profile,
    drafting_profiles=drafting_profiles,
    provider=provider,
    package_profile=package_profile,
)
```

The names on the right are administrator-supplied objects, not provided defaults:

- `repository`: `PostgresRepository` with the actual runtime DSN, `storage=True`
  and explicit `RetentionPolicies`. The SQL identity must be a prepared runtime
  role, not a schema owner, superuser or BYPASSRLS role. Factory construction does
  not connect to SQL, migrate schema or attest deployment permissions.
- `authority`: `TokenAuthority` provisioned through the existing trusted Python
  API for authenticated actors, exact tenant/CASE scopes and explicit actions.
  Deliver fresh capabilities privately. The factory issues no tokens. Creating a
  CASE and finalization commands retain their existing HUMAN requirements.
- `case_profile`: an actual `FinalizationProfile` with the approved exact document
  type and render pins. The factory does not admit a legal document type.
- `drafting_profiles`: a nonempty map of typed `DraftingProfile` objects keyed by
  their profile names. Render and provider/model/generator/parameter pins must
  match the configured CASE profile and provider.
- `provider`: the existing `ManualAttestedDraftingProvider`. A trusted host must
  supply a genuine structured AIResult bound to the exact request and snapshot.
  There is no network model call or paid fallback, and the HTTP shell has no
  endpoint that manufactures provider results.
- `package_profile`: an actual `FinalPackageProfile` with the deployed commit SHA
  and baseline contract hash. Neither value is guessed by the factory.

Missing or mismatched wiring fails closed. Supplying these objects grants no
semantic approval, FINAL eligibility, legal admission or production certification.
No Mock or test-fixture import belongs in deployment configuration.

## Windows 11 requirements and launch

Use an accessible Python 3.11+ interpreter; this session executed Python 3.14.7.
From the repository root, install the declared dependencies and PostgreSQL extra
in a virtual environment: `python -m pip install -e ".[postgres,ingestion]"`.
The prepared PostgreSQL schema, restricted runtime role, pinned font/render assets,
approved profiles, authenticated actors and scoped capabilities are required for
the corresponding operations. The host does not provision those resources.

Launch the administrator's completed configuration; the unbound template is only
a fail-closed configuration example. The path below is a placeholder:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m lukart_work.operator_host --config C:\LUKART\Config\case_operator_host.py --port 8765
# Optional wrapper, where local PowerShell policy permits scripts:
.\scripts\start_case_operator.ps1 -Config C:\LUKART\Config\case_operator_host.py
# If the workspace virtual environment is unavailable, supply an accessible interpreter:
.\scripts\start_case_operator.ps1 -Config C:\LUKART\Config\case_operator_host.py -Python C:\Python314\python.exe
```

The configuration paths above are placeholders, not supplied working credentials.
Required verification: an accessible Python installation, trusted real CASE host
configuration, focused `tests.test_operator_host` and operator regression tests,
then `verify_stage13.py` with exact `TESTED_SHA` and isolated PostgreSQL/egress test
configuration (zero skips). Real CASE launch and authenticated operations need
separate evidence; transport tests cannot establish real CASE readiness.

Current local evidence also includes 13 successful browser/core integration checks
and the separately repaired host integration test using the existing synthetic
HUMAN fixture. Their isolated cluster was identified by PID, listening port,
data_directory and system identifier before use. It retained zero Decision
records and was stopped afterwards. The factory/bootstrap tests use real native
components without a database CASE or HUMAN decisions. Completed unchanged tests
are preserved through source-hash comparison rather than repeated for a claim.
Node.js is needed only for the browser JavaScript contract test, not host runtime.
These observations do not establish a real CASE drafting/render/final-approval
workflow or exact-SHA CI PASS. Browser PDF preview remains NOT VERIFIED.

GitHub annotations for baseline candidate
`90a6f6339d934a75eab03069bce868af4a967790` report that jobs did not start because
recent account payments failed or the spending limit needs attention. Do not
change billing or repository controls, or claim failing repository tests from
that runner-admission failure. New candidate CI must be checked independently.

## Current validation and follow-up (2026-10-15)

The existing `scripts/verify_stage10.py` ran against the working sources based on
`90a6f6339d934a75eab03069bce868af4a967790`: 705 tests, 703 successful,
2 failures, 0 errors and 0 skips. The report remains FAIL and records the tested
source hashes; these uncommitted sources are not a new validated commit SHA.
The isolated PostgreSQL cluster was stopped and its data retained. The complete
log is retained locally at
`build/pr64-postgres-124ee5582b494603bb1100491c36f121/full-stage10.stdout.log`.
The earlier 20 PASS and HTTP 413 40/40 evidence is preserved. Eight additional
configuration/bootstrap tests passed using native components without a database.

Follow-up `PR64-FU-WIN-SOCKET`: the existing
`test_total_deadline_aborts_actual_blocked_socket_read` failed at `closed.wait(1)`.
Both `chat_zero_cost.py` and its test are unchanged from the baseline HEAD.
A local socket-pair diagnostic returned from `shutdown(SHUT_RDWR)` while its
reader stayed blocked for one second; closing the sockets ended the reader.
The proposed additional socket close has NOT been applied or validated.
This transport is already part of PR #64, but the CASE host and explicit factory
use `ManualAttestedDraftingProvider` and do not invoke it. Necessity of this repair
for closing PR #64 is NOT VERIFIED. Keep this independent Windows transport
defect visible; it prevents claiming a full local PASS, not configuration work.

Follow-up `PR64-FU-RENDER-IDENTITY`: fresh-process rendering was stable but differed
from `tests/golden_cases/stage11_render_identity.json`. Comparing the existing
synthetic fixture using the HEAD source pin (read from Git into memory) with the
working source pin produced byte-identical DOCX/PDF and identical render blocks.
Both baseline artifacts already differ from the golden artifact hashes in this
Windows environment. Added executable sources also change the validation,
projection, model and layout provenance pins by design. The golden was last
updated for Linux canonical rendering; this interpreter uses zlib-ng 2.2.4.
The exact cause of the platform artifact difference is NOT VERIFIED. Do not
replace canonical artifact hashes with Windows output or weaken the assertions.
The renderer and golden remain unchanged pending the appropriate follow-up.

These failures remain open validation findings. Neither a refreshed SHA-256
manifest nor focused host tests establish a full regression PASS, production
startup, legal admission or real HUMAN approval. No unchanged full suite needs
to be repeated until the relevant failure or environment changes.

## Historical restricted-session observations (superseded where noted above)

Observed session blockers: workspace Python denied access to its base interpreter;
`py -3.14` and `py -3.11` found no installed interpreter. The wrapper was rejected
by Windows script execution policy. These controls were not changed or bypassed.
GitHub CLI socket access was denied. The connected GitHub API was readable on
2026-10-15 and confirmed PR64 still targets candidate
`90a6f6339d934a75eab03069bce868af4a967790` on the existing feature branch.
Candidate runs 38656601325, 38656601300, 38656601350, 38656601313 and 38656601314
all failed. Their jobs had no executed steps and no assigned runner
(`runner_id=0`, empty runner name). This is failure before repository test
execution, not evidence of failing tests. The API connector rejects the check-run
annotations endpoint; the precise runner-admission reason is NOT VERIFIED.
Do not infer a billing, quota or workflow-code cause, and do not blindly retry.

Continuation checks: Windows PowerShell parser accepted the wrapper; Node parsed
the embedded browser JavaScript. A Node test with synthetic DOM/transport objects
also checked the CASE query, omission of cookies, and suppression of a late
response after session clearing. These are not browser or CASE integration
checks. The attempted
`tests.test_operator_host tests.test_operator` run could not start Python and ran
no tests. Real CASE configuration, authenticated capabilities, runtime startup,
draft/edit/render, genuine HUMAN approval, full regression and exact-SHA CI
remain required. No real HUMAN approval was attempted or recorded.

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
