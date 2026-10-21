# Generator Pism: authorized OCR / CreateCase continuation

Base: `368298ce2b9ab4f6273ca278da907f522cea5fae` (merged PR #64).
Scope: the operator's 2026-10-20 request in `_1_2_3.txt`. Existing baseline reports,
legal admission, source originals, decisions and historical acceptance remain unchanged.
This is an implementation extension, not a replacement architecture or a production certificate.

## Implemented flow

The existing operator shell prepares CreateCase and provides a separate explicit
confirmation button. Existing Core checks still enforce HUMAN, exact capability
scope, retention, sequence, actor-bound replay and transactional audit/outbox.
No identity, permission or HUMAN decision is provisioned by HTTP.

The document form composes RegisterSource and IngestionService through
`upload_source`. Both capabilities are checked before registering bytes. These
remain two transactions: a successful registration survives a later extraction
failure. The exact prepared command/run identifiers remain in the editor for an
idempotent retry after a transport failure. A failed immutable extraction can be
retried as a new run. Existing artifacts are never overwritten.

`query_ingestion` reads a stored result or explicitly starts a new extraction run.
The shell shows source/run identifiers, recognized text, candidate positions and
outcomes. Preparing a candidate review computes the exact canonical result hash;
only a separate send invokes ReviewCandidate. ADMIT still produces REGISTERED
Evidence / CANDIDATE Fact. ReviewEvidence, AcceptEvidence, ReviewFact, a genuine
FACT_ACCEPTANCE decision and ConfirmFact remain separate existing operations.
The matrix query displays their current status. No OCR result confirms a fact.

Changing token/tenant/case clears selected documents, review text and result IDs,
invalidates pending responses and revokes artifact URLs. No browser storage is used.

## Trusted OCR configuration

The existing host administrator may pass the following optional object to
`operator_config.build_operator` (alongside its six existing trusted components):

```python
from lukart_work.ingestion.ocr import OCRConfig

ocr_config = OCRConfig(
    tesseract="/absolute/path/to/tesseract",
    tessdata="/absolute/path/to/tessdata",  # contains pol.traineddata
    pdftoppm="/absolute/path/to/pdftoppm",
)
```

These are administrator-supplied absolute paths, never HTTP input. No tools or
models are downloaded at runtime. Pillow 13.0.0 is explicitly pinned in the
ingestion extra (it was already installed in the tested environment). The OCR pin
binds actual engine/model/rasterizer bytes and Pillow preprocessing code/native
libraries. The ingestion implementation and pypdf implementation retain their
existing pins. Without configuration the historical NEEDS_OCR outcome remains.
Missing binaries/model or the wrong Pillow version fail host construction closed.

PDF pages with text retain their text layer. Pages without text use the configured
local Polish Tesseract via the existing Poppler rasterizer. PNG/JPEG and multipage
TIFF use the same engine. Each OCR fragment records PAGE, page number, recognized
text SHA-256 and extraction_method=OCR; the source result retains original source
SHA-256/length and actor/run provenance. OCR text goes to the existing candidate
parser. PARTIAL_EXTRACTION / REVIEW_REQUIRED remain explicit: layout, correctness
and completeness require review, including pages whose text layer is incomplete.

Bounds: existing 1 MiB HTTP body limit unchanged (form files up to 700 KiB);
existing 16 MiB source/worker limit; 20 OCR pages; 20 million pixels per page;
150 dpi PDF rasterization; 400,000 UTF-8 bytes per OCR output; 500,000 aggregate
characters; 10 seconds per native invocation, a 40-second native-operation budget
and 60-second OCR worker deadline. Existing non-OCR worker deadline remains
15 seconds. Native children inherit the existing Unix memory/process CPU bounds;
equivalent OS-level Windows job memory/tree guarantees are NOT VERIFIED.

## Compatibility and verification

The IngestionResult schema adds optional OCR provenance. Default TEXT/None values
are omitted from serialized output, preserving legacy body/result hashes and
stored replay. No data migration or rewriting of stored results is performed.
New OCR results require the updated reader; old strict-schema readers must not
be used to consume new OCR fields.

Focused tests: `tests.ocr_intake_acceptance`; affected existing extraction/storage tests:
`tests.test_stage04`, and relevant Stage05 candidate review controls. Runtime tests
require `LUKART_OCR_TEST_CONFIG` pointing to JSON containing the three trusted
paths. Integration tests also require isolated admin/runtime DSNs whose database
name begins `lukart_ocr_acceptance_`; they reject the shared test database. HUMAN
test fixtures are synthetic test actors, not evidence of an actual user's
identity, semantic acceptance, legal admission or product acceptance.

The dedicated `generator-ocr-intake.yml` check installs only free local OCR tools
on the existing GitHub-hosted Ubuntu platform and uses its own PostgreSQL service
database. `scripts/verify_ocr_intake.py` requires a clean exact-SHA checkout, native
Polish OCR configuration and disposable DSNs. It executes the 40 targeted cases
and fails on every skip. Native acceptance is intentionally separate from legacy
test discovery; the existing legacy gates are unchanged and do not claim OCR
coverage. Both this new check and the existing required checks must pass before
merge. No branch protection or security policy is changed.

Historical 714-test evidence in `reports/stage10-status.json` is retained. New
validation must bind to the new exact SHA or explicitly verified source delta;
the historical PASS must not be relabeled as a new full-suite PASS.

## Remaining product gates

The existing resumed local panel is explicitly read-only and pinned to its own
source/artifacts. This change does not upgrade its identity or restart it. A real
write-capable configuration requires the administrator's authenticated HUMAN,
proper case-scoped capabilities, admitted profiles and request-bound provider.
No SERVICE actor may be relabeled as HUMAN to unlock CreateCase.

The shell retains advanced explicit contracts for planning/drafting/validation.
The guided text editor now prepares the explicit HUMAN AmendDraft operation,
preserving earlier projects and sources and requiring a fresh review/validation.
See `docs/DRAFT_AMENDMENT_HUMAN_ACCEPTANCE.md` for the contract and trusted HUMAN
configuration bridge. The existing manual attested provider and all legal/final
approval gates remain mandatory.
Do not declare PRODUCT_READY until those product requirements, actual HUMAN
acceptance and required exact-SHA GitHub checks are independently satisfied.
