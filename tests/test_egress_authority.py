"""PostgreSQL-backed synthetic egress authorization; no remote API calls."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from uuid import UUID, uuid4

from lukart_work.contracts.messages import CommandResult
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.model_runtime.chat_zero_cost import chat_wire_body
from lukart_work.model_runtime.egress_authority import PostgresEgressAuthority
from lukart_work.model_runtime.ollama import ProviderPolicyError
from tests.test_chat_zero_cost import NOW, POLICY, Prompt, cfg, grant, invoke
from tests.test_stage02 import DSN

ADMIN_ACTIONS = frozenset({"CreateCase", "AI_EGRESS_BUDGET",
    "AI_EGRESS_APPROVE", "AI_EGRESS_SEND", "AI_EGRESS_REVOKE"})
ACCOUNT = "a" * 64
CONSENT = "b" * 64
PRICING = "c" * 64


@unittest.skipUnless(DSN, "PostgreSQL egress proof requires isolated test DB")
class DurableEgressTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case = uuid4(), uuid4()
        self.authority = TokenAuthority()
        self.repo = PostgresRepository(DSN)
        self.actor = Actor(id=uuid4(), kind="HUMAN")
        self.token = self.authority.provision(Principal(
            self.actor, self.tenant, self.case, ADMIN_ACTIONS))
        self.host = PostgresEgressAuthority(self.repo, self.authority, clock=lambda: NOW)
        self.item = self._item(self.case)
        self.config = cfg()
        self.body = chat_wire_body(self.config, Prompt()(self.item))
        self._create_case(self.case, self.token)
        self.host.register_budget(self.token, tenant_id=self.tenant,
            case_id=self.case, provider_id=self.config.provider.id,
            account_hash=ACCOUNT, maximum_free_calls=3,
            free_evidence_hash=PRICING, verified_until=NOW + timedelta(minutes=10),
            free_price_verified=True, paid_fallback_disabled=True)

    def _item(self, case):
        template = invoke()
        return template.model_copy(update={"request": template.request.model_copy(
            update={"tenant_id": self.tenant, "case_id": case})})

    def _create_case(self, case, token):
        cmd = {
            "contract": "urn:lukart:work:CoreRequest:1.0.0",
            "operation": "CreateCase",
            "meta": {"command_id": str(uuid4()), "idempotency_key": str(uuid4()),
                     "correlation_id": str(uuid4()),
                     "expected_case_sequence": 0,
                     "tenant_id": str(self.tenant), "case_id": str(case)},
            "data": {"title": "Synthetic zero-cost consent exercise",
                     "jurisdiction": "PL", "retention_policy": POLICY.model_dump(mode="json")},
        }
        result = CommandService(self.repo, self.authority).execute(json.dumps(cmd), token)
        self.assertIsInstance(result, CommandResult, result)

    def _grant(self, item=None, free=3):
        item = item or self.item
        base = grant(item)
        return replace(base, free_requests_remaining=free,
            reserved_wire_bytes=len(chat_wire_body(self.config, Prompt()(item))))

    def _issue(self, *, item=None, free=3, token=None):
        item = item or self.item
        grant_value = self._grant(item, free)
        self.host.issue(token or self.token, item, self.config,
            chat_wire_body(self.config, Prompt()(item)), grant_value,
            account_hash=ACCOUNT, consent_evidence_hash=CONSENT,
            free_evidence_hash=PRICING)
        return grant_value

    def test_durable_one_use_after_restart_and_idempotent_rejection(self):
        value = self._issue()
        resolver, committer = self.host.bind(self.token)
        self.assertEqual(resolver(self.item), value)
        self.assertEqual(committer(self.item, value, self.body), value)
        restarted = PostgresEgressAuthority(self.repo, self.authority, clock=lambda: NOW)
        with self.assertRaises(ProviderPolicyError):
            restarted.resolve(self.token, self.item)
        with self.assertRaises(ProviderPolicyError):
            restarted.commit(self.token, self.item, value, self.body)
        with self.assertRaises(Exception):
            self._issue()

    def test_revoke_before_send_releases_budget_without_replaying_grant(self):
        old = self._issue()
        self.host.revoke(self.token, tenant_id=self.tenant, case_id=self.case,
                         request_id=self.item.request.request_id)
        with self.assertRaises(ProviderPolicyError):
            self.host.commit(self.token, self.item, old, self.body)
        other = self.item.model_copy(update={"request": self.item.request.model_copy(
            update={"request_id": uuid4()})})
        self._issue(item=other, free=3)

    def test_budget_revocation_blocks_existing_reservation(self):
        value = self._issue()
        self.host.revoke_budget(self.token, tenant_id=self.tenant, case_id=self.case,
            provider_id=self.config.provider.id, account_hash=ACCOUNT)
        with self.assertRaises(ProviderPolicyError):
            self.host.commit(self.token, self.item, value, self.body)

    def test_wrong_body_and_consent_hash_fail_closed(self):
        value = self._issue()
        with self.assertRaises(ProviderPolicyError):
            self.host.commit(self.token, self.item, value, self.body + b"!")
        self.assertEqual(self.host.resolve(self.token, self.item), value)
        second = self.item.model_copy(update={"request": self.item.request.model_copy(
            update={"request_id": uuid4()})})
        with self.assertRaises(ProviderPolicyError):
            self.host.issue(self.token, second, self.config,
                chat_wire_body(self.config, Prompt()(second)), self._grant(second, free=2),
                account_hash=ACCOUNT, consent_evidence_hash="", free_evidence_hash=PRICING)

    def test_two_simultaneous_commits_consume_once(self):
        value = self._issue()
        def execute(_):
            try:
                self.host.commit(self.token, self.item, value, self.body)
                return "PASS"
            except ProviderPolicyError:
                return "DENIED"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, range(2)))
        self.assertEqual(sorted(results), ["DENIED", "PASS"])

    def test_cross_case_tenant_shared_budget_and_capability_scope(self):
        second_case = uuid4()
        token2 = self.authority.provision(Principal(
            self.actor, self.tenant, second_case, ADMIN_ACTIONS))
        self._create_case(second_case, token2)
        value = self._issue()
        second = self._item(second_case)
        second = second.model_copy(update={"request": second.request.model_copy(
            update={"request_id": uuid4()})})
        with self.assertRaises(ProviderPolicyError):
            self.host.resolve(self.token, second)
        with self.assertRaises(ProviderPolicyError):
            self.host.issue(token2, second, self.config,
                chat_wire_body(self.config, Prompt()(second)), self._grant(second, free=3),
                account_hash=ACCOUNT, consent_evidence_hash=CONSENT,
                free_evidence_hash=PRICING)
        self._issue(item=second, free=2, token=token2)
        self.assertEqual(self.host.resolve(token2, second).case_id, second_case)
        self.assertEqual(self.host.resolve(self.token, self.item), value)

    def test_no_client_or_ai_actor_can_issue_grants(self):
        guest = self.authority.provision(Principal(self.actor, self.tenant, self.case,
            frozenset({"AI_EGRESS_SEND"})))
        with self.assertRaises(Exception):
            self._issue(token=guest)
        ai = self.authority.provision(Principal(
            Actor(id=uuid4(), kind="AI"), self.tenant, self.case, ADMIN_ACTIONS))
        with self.assertRaises(ProviderPolicyError):
            self._issue(token=ai)


    def test_database_role_cannot_mutate_immutable_grant_or_bypass_quota(self):
        value = self._issue()
        with self.assertRaises(Exception):
            with self.repo.transaction(self.tenant, self.case) as tx:
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_grants SET grant_json='{}' "
                    "WHERE tenant_id=%s AND case_id=%s AND request_id=%s",
                    (self.tenant, self.case, self.item.request.request_id))
        with self.assertRaises(Exception):
            with self.repo.transaction(self.tenant, self.case) as tx:
                tx.connection.execute(
                    "UPDATE lw_core.ai_egress_budgets SET used_calls=used_calls+1 "
                    "WHERE tenant_id=%s AND provider_id=%s AND account_hash=%s",
                    (self.tenant, self.config.provider.id, ACCOUNT))
        self.assertEqual(self.host.resolve(self.token, self.item), value)

    def test_tenant_wide_revoke_requires_separate_budget_capability(self):
        value = self._issue()
        revoke_only = self.authority.provision(Principal(
            self.actor, self.tenant, self.case, frozenset({"AI_EGRESS_REVOKE"})))
        with self.assertRaises(ProviderPolicyError):
            self.host.revoke_budget(revoke_only, tenant_id=self.tenant,
                case_id=self.case, provider_id=self.config.provider.id,
                account_hash=ACCOUNT)
        self.assertEqual(self.host.resolve(self.token, self.item), value)


    def test_existing_chat_adapter_consumes_durable_grant_at_send_boundary(self):
        """Proof of existing fake transport + PostgreSQL authority, no network."""
        from lukart_work.model_runtime.chat_zero_cost import ZeroCostChatDraftingProvider
        from tests.test_chat_zero_cost import FakeTransport, response

        self._issue()
        resolver, committer = self.host.bind(self.token)
        fake = FakeTransport(response(self.item))
        adapter = ZeroCostChatDraftingProvider(
            self.config, prompt_builder=Prompt(),
            admission_resolver=resolver, reservation_committer=committer,
            secret_supplier=lambda: "synthetic-secret-not-real",
            transport=fake, clock=lambda: NOW,
        )
        result = adapter.propose(self.item)
        self.assertEqual(result.request_id, self.item.request.request_id)
        self.assertEqual(len(fake.calls), 1)
        with self.assertRaises(ProviderPolicyError):
            adapter.propose(self.item)
        self.assertEqual(len(fake.calls), 1)

    def test_expired_or_false_pricing_proof_does_not_register(self):
        for override in (
            {"free_price_verified": False},
            {"paid_fallback_disabled": False},
            {"verified_until": NOW - timedelta(minutes=1)},
        ):
            with self.subTest(override=override):
                args = dict(tenant_id=self.tenant, case_id=self.case,
                    provider_id=self.config.provider.id, account_hash="d" * 64,
                    maximum_free_calls=2, free_evidence_hash=PRICING,
                    verified_until=NOW + timedelta(minutes=5),
                    free_price_verified=True, paid_fallback_disabled=True)
                args.update(override)
                with self.assertRaises(ProviderPolicyError):
                    self.host.register_budget(self.token, **args)
