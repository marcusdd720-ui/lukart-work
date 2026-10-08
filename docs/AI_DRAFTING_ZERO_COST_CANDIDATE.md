# LUKART LEGAL OS — optional zero-cost AI drafting provider candidate

**STATUS: DRAFT CODE / SYNTHETIC TEST ONLY / NO LIVE PROVIDER CERTIFICATION**.

This branch adds only `lukart_work/model_runtime/chat_zero_cost.py`, a
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

No live provider access, no claim of legally authorized production use,
no effect on ROS read-only draft PR #348. A2 independent reviewer required.
