# LUKART LEGAL OS — optional zero-cost AI drafting provider candidate

**STATUS: DRAFT CODE / SYNTHETIC TEST ONLY / NO LIVE PROVIDER CERTIFICATION**.

This branch includes the opt-in `lukart_work/model_runtime/chat_zero_cost.py`, a
provider-neutral OpenAI-compatible remote chat completion adapter that
implements existing `AttestedDraftingProvider` (Stage 09). It does not
replace `ControlledDraftingService`, core case transactions, validation,
HUMAN legal approvals, DOCX/PDF renderer or finalization.

The adapter refuses to send ANY request unless a trusted integration host
supplies a fresh, exactly scoped `ZeroCostScopeAdmission` and a secret
supplier. The host (not AI/user content) must verify the provider's official
no-charge tariff, remaining free quota, **disabled paid fallback**, right to
use API commercially, identity/model, data protection rules and legitimate
HUMAN authorization to export the case data, per request, *before* issuing
the grant. No implicit billing or credential reads from repository/env.

Only two exact official HTTPS chat API origins are hard-allowlisted. JSON
mode, bounded response/usage, pinned parameters, exact request/snapshot
binding, one-call/no-auto-retry, TLS and no proxy env are required.
Server-reported model *name* is checked but cannot prove stable model weights.
An external metadata/policy authority and model-revision admission remain
separate requirements. The model's output is a proposal; the existing WORK
pipeline validates all section citations, facts, plan targets and HUMAN gates.

Tests in `tests/test_chat_zero_cost.py` use a synthetic fake transport and
never send a network packet or incur a charge. For a live test, configure
independent trusted admission and privacy callbacks after verifying free
account status, use a synthetic case, inspect real provider usage and billing,
and pin results to an exact SHA. Until then `LIVE_PROVIDER=NOT_VERIFIED`,
`REAL_CASE_EXPORT=DENIED`, `PRODUCT_CLOSED=NO`.

## Local repair candidate on PR #68 base `78e11f508b17a19d35f6a2fb78cbaa1b97467242`

Wire results use strict JSON validation after duplicate-key rejection. Synthetic
positive `ABSTAIN` and `PROPOSE` tests now exercise actual UUID/array wire values.
A PostgreSQL-backed `PROPOSE` through the existing `ControlledDraftingService`
has a separate test; without the isolated DSNs it is **NOT VERIFIED**, not PASS.

Admissions bind `request_id`, `snapshot_hash`, the canonical SHA-256 of the
entire `DraftingInvocation` (including request, pins, refs, section and evaluation
date), and SHA-256 of the exact serialized chat body. `chat_wire_body` serializes
once to immutable UTF-8 bytes: the system instruction, JSON envelope, model,
parameters and user prompt are all included in `reserved_wire_bytes`. Every
binding and actual body length is checked before secret retrieval or connection.
A changed prompt under the same prompt pin is denied.

The trusted `admission_resolver` is called again after prompt construction,
after secret retrieval and after TLS connection, immediately before POST. Its
fresh result must equal the initial reservation, including `authority_revision`,
body hash and budgets; revocation, changed scope, quota or revision fails closed.
Resolver/committer diagnostics are not exposed. Resolver expiry is checked after
it returns, and expiry is checked again after the committer returns.

A separate, mandatory trusted-host `reservation_committer(invocation, grant,
body) -> ZeroCostScopeAdmission` defines the send authority boundary. Immediately
before POST it must **atomically** compare the current authorization revision,
lawful HUMAN consent, zero-cost entitlement and remaining vendor quota, verify
exact invocation/body/budgets, and durably commit this one-use reservation. Its
return must be the identical valid grant. The host transaction is the authority
linearization point: committed authority must cover the bounded single network
attempt; concurrent revocation and quota allocation must serialize with it.
Returning the same stale object without performing that transaction violates the
callback contract. The adapter cannot certify these external facts or make an
arbitrary host callback atomic. The durable PostgreSQL issuer/committer is provided in the separate child
candidate below; it is not enabled by default and does not verify real-world
privacy or billing facts. A missing committer denies before secret/connect. Synthetic
callbacks prove adapter behavior only, **not production authority**.

The issuer must reserve the complete actual vendor input/output token budget,
including system/protocol overhead, across processes. Exact wire byte limits
are enforced here; bytes are not claimed to equal vendor tokens. On uncertain
send, consumed reservations cannot be silently refunded or automatically retried.
Process-local request/reservation ledgers have finite capacity and no eviction;
new processes still require the durable host idempotency authority.

Compatibility is deliberately breaking for this unadmitted draft adapter only:
`reserved_prompt_bytes` is replaced by `reserved_wire_bytes`, the grant adds the
bindings/revision above, the provider requires `reservation_committer`, and the
transport accepts immutable serialized bytes instead of a mutable payload dict.
Existing host integrations must implement the new contract; no legacy fallback
is allowed. Repository consumers are updated tests; no persisted domain schema,
core service or HUMAN decision boundary changes; the child candidate adds a
separate explicitly applied authority database migration.

`DirectTLSChatTransport` requires a callable send boundary and invokes it once,
after verified TLS connection and just before POST. The provider also rejects
repeated callback invocation and refuses to issue a receipt when it was omitted.
An injected transport is trusted host code: it must call this boundary exactly
once, await success, and send exactly the supplied bytes without mutation or
retries. A malicious injected implementation with arbitrary network access is
outside the adapter's enforcement boundary. Production admission must validate
that transport; no alternate transport is certified here.

Transport return time has a total deadline. Deadline abort shuts down the real
active socket. A stuck DNS worker remains at most one daemon worker per transport
and blocks replacement work until it terminates. This does not claim that the
operating system DNS call can always be interrupted. Tests use a real local
socketpair behind a connection seam; they do not prove a live TLS provider
handshake or vendor behavior.

No live provider access, no claim of legally authorized production use,
no effect on ROS read-only draft PR #348. A2 independent reviewer required.

## Trusted PostgreSQL one-use authority candidate (isolated PR68 child)

`lukart_work/model_runtime/egress_authority.py` now implements the previously
missing trusted-host callbacks on WORK's existing case-scoped PostgreSQL
transactions. The owner-applied additive schema is
`lukart_work/core/migration_ai_egress.sql`. This is an opt-in candidate:
the public adapter still has no default admission, no real provider key,
no provider account credential, and no automatic real-case export.

The authenticated host must provision *separate explicit capabilities*
`AI_EGRESS_BUDGET`, `AI_EGRESS_APPROVE`, `AI_EGRESS_SEND`, and
`AI_EGRESS_REVOKE` to the appropriate case-scoped HUMAN principals.

**SQL trust boundary:** Only a separately authenticated trusted host may own the
`lw_ai_egress_host` connection credential (use an independently protected DSN,
not `LUKART_TEST_DSN` or any client/AI-worker environment). Construct
`PostgresEgressAuthority(PostgresRepository(trusted_host_dsn), host_token_authority)`
inside that isolated, authorized host. Its SQL operations reject any login other
than `lw_ai_egress_host` and continue enforcing the HUMAN capability checks.
`lw_core_runtime` must have SELECT-only access to the AI egress tables,
**never INSERT, UPDATE or DELETE**. The owner must create a separate NOINHERIT,
NOSUPERUSER, NOBYPASSRLS host role and apply
`configure_egress_roles(owner_connection, "lw_core_runtime", "lw_ai_egress_host")`
from `lukart_work.storage.migrations`. That role has only core-case SELECT
and egress-specific INSERT plus narrowly scoped, monotonic UPDATE; it must not
be delegated or inherited by ordinary runtime accounts. A direct SQL connection
using the *trusted host credential itself* is privileged, so secret custody and
process isolation are deployment gates, not properties proved by synthetic CI.
A default or missing host role/DSN denies authorization; the code does not
fall back to an administrative or general-runtime credential.
The isolated CI passwords are synthetic and never establish production custody.
`register_budget` requires separately inspected official free-tier/billing
evidence identified by a SHA-256 reference and binds one provider/account,
zero paid fallback and an expiry. It never replenishes an existing account
budget. `issue` records one particular consent-evidence digest and exact
`ZeroCostScopeAdmission` bound to immutable invocation/body identities.
Do not obtain these inputs from model text or an unauthenticated client.
No assertion of actual consent or zero-billing is inferred from a digest:
the authorized human issuer must verify the underlying private consent
and official provider evidence *outside* this module. Missing independent
proof means do not issue the budget or grant.

Use `resolver, committer = host.bind(authorized_send_token)` and pass
those callbacks to the existing `ZeroCostChatDraftingProvider`.
`commit` atomically checks the still-live grant and shared account budget
under PostgreSQL locks and consumes the reservation once immediately before
POST. Revoke-before-commit prevents POST and releases unused allocation.
Revoke-after-commit never refunds a potentially transmitted call.
A crash/timeout after commit consumes the reservation permanently;
the operator must reconcile usage out of band, never blindly retry.
No secret, prompt, case body or client document is persisted in this ledger.

Tests in `tests/test_egress_authority.py` exercise restart, same-request
replay, concurrent commit with independent process-local authority instances,
tenant/case segregation, budget contention and revocation against a disposable
PostgreSQL service. Expired, unconsumed reservations can be reclaimed on a
subsequent issue within the same HUMAN-authorized case only. The shared
account's reservations in OTHER cases remain case-RLS-protected; the
authorized HUMAN operator must invoke case-scoped `revoke` for abandoned
reservations in those cases. Never broaden RLS to work around this restriction
or claim automatic tenant-wide recovery of expired reservations. Synthetic evidence
does not attest the origin of actual client consent, commercial free
entitlement, lawful transfer terms, provider-side billing, or independence
of a legal reviewer. Until the necessary real-world and legal gates pass:
`REAL_CASE_EXPORT=DENIED`, `LEGAL_TYPE_ADMISSION=HUMAN_REQUIRED`,
`GO_LIVE=BLOCKED`.
