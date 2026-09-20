# Stage 10 remediation after independent review

Historical candidate: `7daa84aca62b91b0b8513843560313bfc4325202`.
Independent exact-SHA review: **FAIL/BLOCKED**. This verdict is permanent for that
candidate. The earlier freeze/continuation receipt and acceptance history are not
rewritten. Base remains `0d31a47f6481e9eb252b188253ac1ed33effa50c`.

## Root causes and bounded changes

P1: procedural rule applicability checked the rule's dates and jurisdiction, while
source availability checked only current version, VERIFIED status and bytes.
Citation-specific source checks did not cover uncited procedural sources.

Stage 10 now checks every source of every applicable procedural rule directly:
exact current LegalSource reference, VERIFIED status, source byte integrity,
jurisdiction matching both case and rule, and inclusive effective-period bounds.
The temporal point is the UTC execution date already used by Stage 10 for rule
and citation applicability. A future or expired source cannot borrow the rule's
validity. Unavailable and inapplicable sources produce BLOCKER findings. The same
procedure check runs in GetValidation, so subsequent source expiry denies current
eligibility. Historical ValidationRun evidence is not rewritten.

P2: generic procedural code/path tuples discarded rule identity before set-based
deduplication. Procedural finding paths now start with
`/rules/{rule_id}/revisions/{revision}`, followed by the original condition path
or the exact source identity. Distinct rules remain distinct even at the same
condition path. Existing sorting and UUIDv5 generation consume this stable path.
No public schema, historical lifecycle, SQL or Stage 07 implementation is changed.

## Required evidence for a new candidate

Seven additional PostgreSQL tests cover the two independent-review P1 cases,
future sources, a valid uncited source, inclusive date endpoints and query expiry,
two violated rules at the same path, and stale/unverified/unavailable sources.
The last test exercises the procedure checker with controlled faults inside a
real PostgreSQL fixture; the expired, foreign, future and positive cases use the
public validation and query entry points.

CI runs these seven tests separately, all Stage 10 tests, historical Stage 09,
the full regression, schema/package/integrity checks and generated-evidence
reproducibility. In-memory results cannot satisfy this gate.

The source/remediation commits and the new exact-head CI run, job, artifact digest
and frozen candidate SHA will be appended in a new continuation receipt on PR #9.
This avoids self-referential generated reports. The original receipt is retained.
No new candidate inherits PASS from the failed historical SHA or from a different
commit. Builder assurance is not independent review. PR #9 remains draft and must
not be merged; Stage 11 is not started.

The three operating documents named in Stage 10 readiness remain
NOT PRESENT IN VERIFIED BASELINE. None is reconstructed by this remediation.
