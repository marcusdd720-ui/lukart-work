"""Durable trusted-host authorization for zero-cost AI egress (PostgreSQL).

Reuses WORK case-scoped transactions and TokenAuthority. Never provisions a
provider account, verifies a billing portal, or infers a client's consent.
Only a trusted human issuer with separately verified external evidence may
record admissions. No network, model, or case content is stored here.
"""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Callable
from uuid import UUID

from lukart_work.core.postgres import canonical
from lukart_work.domain.models import VersionPin
from lukart_work.model_runtime.chat_zero_cost import (
    ChatProviderConfig, ZeroCostScopeAdmission,
)
from lukart_work.model_runtime.ollama import ProviderPolicyError
from lukart_work.validation.rules import digest

_MAX_BUDGET = 10_000


def _hash(value: str) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(x in "0123456789abcdef" for x in value))


def _now(clock):
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProviderPolicyError()
    return value.astimezone(timezone.utc)


def _grant_json(grant: ZeroCostScopeAdmission) -> str:
    values = {}
    for field in fields(grant):
        value = getattr(grant, field.name)
        if isinstance(value, VersionPin):
            value = value.model_dump(mode="json")
        elif isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        values[field.name] = value
    return canonical(values)


def _grant_from_json(raw: str) -> ZeroCostScopeAdmission:
    value = json.loads(raw)
    if set(value) != {field.name for field in fields(ZeroCostScopeAdmission)}:
        raise ProviderPolicyError()
    for name in ("tenant_id", "case_id", "request_id", "quota_reservation_id"):
        value[name] = UUID(value[name])
    value["data_policy"] = VersionPin.model_validate(value["data_policy"])
    value["expiry_utc"] = datetime.fromisoformat(value["expiry_utc"])
    result = ZeroCostScopeAdmission(**value)
    if _grant_json(result) != raw:
        raise ProviderPolicyError()
    return result


def _require_exact(grant, invocation, config, body, now):
    r = invocation.request
    if (
        not isinstance(grant, ZeroCostScopeAdmission)
        or not isinstance(config, ChatProviderConfig)
        or not isinstance(body, bytes)
        or not body
        or (grant.tenant_id, grant.case_id, grant.request_id)
        != (r.tenant_id, r.case_id, r.request_id)
        or grant.data_policy != r.data_policy
        or grant.snapshot_hash != r.snapshot_hash
        or grant.invocation_hash != digest(invocation)
        or grant.provider_id != config.provider.id
        or grant.model_name != config.model_name
        or grant.endpoint != config.endpoint
        or not isinstance(grant.expiry_utc, datetime)
        or grant.expiry_utc.tzinfo is None
        or not now < grant.expiry_utc <= now + timedelta(hours=1)
        or not _hash(grant.wire_body_sha256)
        or sha256(body).hexdigest() != grant.wire_body_sha256
        or type(grant.reserved_wire_bytes) is not int
        or len(body) > grant.reserved_wire_bytes
        or grant.reserved_wire_bytes > config.max_prompt_bytes + 24_000
        or grant.reserved_completion_tokens != config.max_completion_tokens
        or type(grant.free_requests_remaining) is not int
        or grant.free_requests_remaining < 1
        or type(grant.authority_revision) is not int
        or grant.authority_revision < 1
        or not isinstance(grant.quota_reservation_id, UUID)
        or grant.price_usd != "0"
        or grant.paid_fallback_disabled is not True
        or grant.confidential_egress_approved is not True
    ):
        raise ProviderPolicyError()


class PostgresEgressAuthority:
    """Only a host-provisioned Principal may approve, send or revoke.

    AI_EGRESS_BUDGET, AI_EGRESS_APPROVE, AI_EGRESS_SEND, AI_EGRESS_REVOKE
    are explicit host-only capabilities, not model or public API commands.
    """

    def __init__(self, repository, authority, *, clock: Callable | None = None):
        self.repository = repository
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _human(principal, tenant, case, action):
        principal.require(tenant, case, action)
        if principal.actor.kind != "HUMAN":
            raise ProviderPolicyError()

    def register_budget(self, token, *, tenant_id, case_id, provider_id,
                        account_hash, maximum_free_calls, free_evidence_hash,
                        verified_until, free_price_verified, paid_fallback_disabled):
        """Trust-boundary operation: issuer must independently check evidence.

        Refuses updates/replenishment to an existing account budget. A new
        budget requires a separately authorized versioned account identity.
        """
        now = _now(self.clock)
        if (not _hash(account_hash) or not _hash(free_evidence_hash)
                or not isinstance(provider_id, str) or not provider_id
                or type(maximum_free_calls) is not int
                or not 1 <= maximum_free_calls <= _MAX_BUDGET
                or not isinstance(verified_until, datetime)
                or verified_until.tzinfo is None or verified_until <= now
                or free_price_verified is not True
                or paid_fallback_disabled is not True):
            raise ProviderPolicyError()
        with self.authority.session(token) as principal:
            self._human(principal, tenant_id, case_id, "AI_EGRESS_BUDGET")
            with self.repository.transaction(tenant_id, case_id) as tx:
                if not tx.sequence():
                    raise ProviderPolicyError()
                tx.connection.execute(
                    "INSERT INTO lw_core.ai_egress_budgets "
                    "(tenant_id,provider_id,account_hash,maximum_free_calls,"
                    "used_calls,reserved_calls,free_evidence_hash,verified_until,"
                    "revoked_at,revoked_by,approved_by) "
                    "VALUES (%s,%s,%s,%s,0,0,%s,%s,NULL,NULL,%s)",
                    (tenant_id, provider_id, account_hash, maximum_free_calls,
                     free_evidence_hash, verified_until, principal.actor.id),
                )

    def issue(self, token, invocation, config, body, grant, *,
              account_hash, consent_evidence_hash, free_evidence_hash):
        """Reserve exactly one free call under tenant/provider account budget."""
        now = _now(self.clock)
        _require_exact(grant, invocation, config, body, now)
        if not all(_hash(x) for x in (account_hash, consent_evidence_hash,
                                     free_evidence_hash)):
            raise ProviderPolicyError()
        tenant, case = grant.tenant_id, grant.case_id
        with self.authority.session(token) as principal:
            self._human(principal, tenant, case, "AI_EGRESS_APPROVE")
            with self.repository.transaction(tenant, case) as tx:
                if not tx.sequence():
                    raise ProviderPolicyError()
                row = tx.connection.execute(
                    "SELECT maximum_free_calls,used_calls,reserved_calls,"
                    "free_evidence_hash,verified_until,revoked_at "
                    "FROM lw_core.ai_egress_budgets "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s "
                    "FOR UPDATE",
                    (tenant, grant.provider_id, account_hash),
                ).fetchone()
                if (row is None or row[3] != free_evidence_hash
                        or row[5] is not None or row[4] < grant.expiry_utc
                        or row[0] - row[1] - row[2] != grant.free_requests_remaining):
                    raise ProviderPolicyError()
                tx.connection.execute(
                    "INSERT INTO lw_core.ai_egress_grants "
                    "(tenant_id,case_id,request_id,reservation_id,provider_id,"
                    "account_hash,grant_json,grant_hash,consent_evidence_hash,"
                    "free_evidence_hash,issued_by,issued_at,consumed_at,consumed_by,revoked_at,revoked_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,NULL)",
                    (tenant, case, grant.request_id, grant.quota_reservation_id,
                     grant.provider_id, account_hash, _grant_json(grant),
                     sha256(_grant_json(grant).encode()).hexdigest(),
                     consent_evidence_hash, free_evidence_hash,
                     principal.actor.id, now),
                )
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_budgets SET reserved_calls=reserved_calls+1 "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s",
                    (tenant, grant.provider_id, account_hash),
                )

    def bind(self, token):
        """Inject these two callables into the *existing* chat adapter."""
        return (
            lambda invocation: self.resolve(token, invocation),
            lambda invocation, grant, body: self.commit(token, invocation, grant, body),
        )

    def _load(self, tx, request):
        row = tx.connection.execute(
            "SELECT grant_json,grant_hash,provider_id,account_hash,"
            "free_evidence_hash,consumed_at,revoked_at "
            "FROM lw_core.ai_egress_grants "
            "WHERE tenant_id=%s AND case_id=%s AND request_id=%s",
            (request.tenant_id, request.case_id, request.request_id),
        ).fetchone()
        if row is None or sha256(row[0].encode()).hexdigest() != row[1]:
            raise ProviderPolicyError()
        value = _grant_from_json(row[0])
        if (value.tenant_id, value.case_id, value.request_id) != (
            request.tenant_id, request.case_id, request.request_id
        ):
            raise ProviderPolicyError()
        return value, row

    def resolve(self, token, invocation):
        request = invocation.request
        with self.authority.session(token) as principal:
            self._human(principal, request.tenant_id, request.case_id, "AI_EGRESS_SEND")
            with self.repository.transaction(request.tenant_id, request.case_id) as tx:
                grant, row = self._load(tx, request)
                if row[5] is not None or row[6] is not None or grant.expiry_utc <= _now(self.clock):
                    raise ProviderPolicyError()
                budget = tx.connection.execute(
                    "SELECT free_evidence_hash,verified_until,revoked_at "
                    "FROM lw_core.ai_egress_budgets "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s",
                    (request.tenant_id, row[2], row[3]),
                ).fetchone()
                if (budget is None or budget[0] != row[4] or budget[2] is not None
                        or budget[1] < grant.expiry_utc
                        or grant.invocation_hash != digest(invocation)):
                    raise ProviderPolicyError()
                return grant

    def commit(self, token, invocation, grant, body):
        """Atomic durable one-use SEND reservation; no retry on ambiguity."""
        now = _now(self.clock)
        request = invocation.request
        with self.authority.session(token) as principal:
            self._human(principal, request.tenant_id, request.case_id, "AI_EGRESS_SEND")
            with self.repository.transaction(request.tenant_id, request.case_id) as tx:
                stored, row = self._load(tx, request)
                if row[5] is not None or row[6] is not None or stored != grant:
                    raise ProviderPolicyError()
                # The adapter makes this callback immediately before its POST.
                if (grant.expiry_utc <= now or grant.invocation_hash != digest(invocation)
                        or sha256(body).hexdigest() != grant.wire_body_sha256
                        or len(body) > grant.reserved_wire_bytes):
                    raise ProviderPolicyError()
                budget = tx.connection.execute(
                    "SELECT maximum_free_calls,used_calls,reserved_calls,"
                    "free_evidence_hash,verified_until,revoked_at "
                    "FROM lw_core.ai_egress_budgets "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s "
                    "FOR UPDATE",
                    (request.tenant_id, row[2], row[3]),
                ).fetchone()
                if (budget is None or budget[5] is not None
                        or budget[3] != row[4] or budget[4] < grant.expiry_utc
                        or budget[2] < 1 or budget[1] >= budget[0]):
                    raise ProviderPolicyError()
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_grants SET consumed_at=%s,consumed_by=%s "
                    "WHERE tenant_id=%s AND case_id=%s AND request_id=%s "
                    "AND consumed_at IS NULL AND revoked_at IS NULL",
                    (now, principal.actor.id, request.tenant_id, request.case_id, request.request_id),
                )
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_budgets "
                    "SET used_calls=used_calls+1,reserved_calls=reserved_calls-1 "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s",
                    (request.tenant_id, row[2], row[3]),
                )
        return grant

    def revoke(self, token, *, tenant_id, case_id, request_id):
        """Revocation before SEND releases quota; after SEND never refunds."""
        now = _now(self.clock)
        with self.authority.session(token) as principal:
            self._human(principal, tenant_id, case_id, "AI_EGRESS_REVOKE")
            with self.repository.transaction(tenant_id, case_id) as tx:
                request = type("_Scope", (), dict(tenant_id=tenant_id,
                    case_id=case_id, request_id=request_id))()
                _, row = self._load(tx, request)
                if row[6] is not None:
                    return
                budget = tx.connection.execute(
                    "SELECT reserved_calls FROM lw_core.ai_egress_budgets "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s "
                    "FOR UPDATE", (tenant_id, row[2], row[3]),
                ).fetchone()
                if budget is None:
                    raise ProviderPolicyError()
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_grants SET revoked_at=%s,revoked_by=%s "
                    "WHERE tenant_id=%s AND case_id=%s AND request_id=%s",
                    (now, principal.actor.id, tenant_id, case_id, request_id),
                )
                if row[5] is None:
                    if budget[0] < 1:
                        raise ProviderPolicyError()
                    tx.connection.execute(
                        "UPDATE lw_core.ai_egress_budgets "
                        "SET reserved_calls=reserved_calls-1 "
                        "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s",
                        (tenant_id, row[2], row[3]),
                    )

    def revoke_budget(self, token, *, tenant_id, case_id, provider_id, account_hash):
        now = _now(self.clock)
        with self.authority.session(token) as principal:
            self._human(principal, tenant_id, case_id, "AI_EGRESS_REVOKE")
            with self.repository.transaction(tenant_id, case_id) as tx:
                updated = tx.connection.execute(
                    "UPDATE lw_core.ai_egress_budgets SET revoked_at=%s,revoked_by=%s "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s "
                    "AND revoked_at IS NULL",
                    (now, principal.actor.id, tenant_id, provider_id, account_hash),
                )
                if updated.rowcount not in (0, 1):
                    raise ProviderPolicyError()
