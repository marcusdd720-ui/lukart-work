"""Zero-cost remote drafting adapter: entirely synthetic; never network."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest
from uuid import UUID

from lukart_work.contracts.messages import AIRequest, AIResult
from lukart_work.domain.models import Ref, VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.model_runtime.chat_zero_cost import (
    ChatProviderConfig, ZeroCostChatDraftingProvider, ZeroCostScopeAdmission,
    chat_parameters_hash,
)
from lukart_work.model_runtime.ollama import (
    ProviderPolicyError, ProviderProtocolError, ProviderResponseTooLarge,
)

PROVIDER = VersionPin(id="urn:test:groq", version="1.0.0", content_hash="a" * 64)
MODEL = VersionPin(id="urn:test:model", version="synthetic", content_hash="b" * 64)
GENERATOR = VersionPin(id="urn:test:generator", version="1.0.0", content_hash="c" * 64)
POLICY = VersionPin(id="urn:test:policy", version="1.0.0", content_hash="d" * 64)
NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def cfg(**override):
    kw = dict(
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        model_name="synthetic-model",
        provider=PROVIDER, model=MODEL, generator=GENERATOR,
        model_parameters_hash=chat_parameters_hash(
            model_name="synthetic-model", max_completion_tokens=1024, temperature=0.0
        ),
    )
    kw.update(override)
    return ChatProviderConfig(**kw)


def invoke():
    req = AIRequest(
        request_id=UUID(int=11), tenant_id=UUID(int=22), case_id=UUID(int=33),
        task="DRAFTING", snapshot_id=UUID(int=44), snapshot_hash="e" * 64,
        input_refs=(), section_contract=None,
        prompt=PROVIDER, output_contract=GENERATOR, data_policy=POLICY,
    )
    return DraftingInvocation(
        contract="urn:lukart:work:DraftingInvocation:1.0.0",
        section=Ref(kind="Section", id=UUID(int=55), revision=1),
        evaluation_date=date(2026, 10, 8), request=req,
    )


def grant(item):
    return ZeroCostScopeAdmission(
        tenant_id=item.request.tenant_id, case_id=item.request.case_id,
        data_policy=POLICY, provider_id=PROVIDER.id, model_name="synthetic-model",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        expiry_utc=NOW + timedelta(minutes=2), free_requests_remaining=3,
        price_usd="0", paid_fallback_disabled=True,
        confidential_egress_approved=True,
    )


class Prompt:
    pin = PROVIDER
    def __call__(self, item):
        return "SYNTHETIC ONLY: abstain."


class FakeTransport:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []
    def request(self, config, key, payload):
        self.calls.append((config.endpoint, key, payload))
        return self.envelope


def response(item, **updates):
    result = AIResult(
        request_id=item.request.request_id,
        snapshot_hash=item.request.snapshot_hash,
        disposition="ABSTAIN", proposals=(), section=None,
        missing_information=("synthetic",), reason="No verified legal evidence",
    )
    data = {
        "model": "synthetic-model",
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": result.model_dump_json()},
        }],
        "usage": {"completion_tokens": 39},
    }
    data.update(updates)
    return data


def adapter(item, *, g=None, envelope=None, allow=True):
    transport = FakeTransport(response(item) if envelope is None else envelope)
    provider = ZeroCostChatDraftingProvider(
        cfg(), prompt_builder=Prompt(),
        admission_resolver=(lambda _: grant(item) if g is None else g),
        secret_supplier=lambda: "synthetic-secret-not-real",
        transport=transport, clock=lambda: NOW,
    ) if allow else ZeroCostChatDraftingProvider(
        cfg(), prompt_builder=Prompt(), transport=transport, clock=lambda: NOW,
    )
    return provider, transport


class ZeroCostChatProviderTests(unittest.TestCase):
    def test_safe_synthetic_execution_and_exact_receipt(self):
        item = invoke()
        p, t = adapter(item)
        value = p.propose(item)
        self.assertEqual(value["request_id"], str(item.request.request_id))
        self.assertEqual(value["disposition"], "ABSTAIN")
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(t.calls[0][2]["stream"], False)
        self.assertEqual(p.execution_receipt(item.request.request_id).model, MODEL)
        with self.assertRaises(ProviderProtocolError):
            p.execution_receipt(item.request.request_id)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)
        self.assertEqual(len(t.calls), 1)

    def test_default_network_disabled(self):
        item = invoke()
        p, t = adapter(item, allow=False)
        with self.assertRaises(ProviderPolicyError):
            p.propose(item)
        self.assertFalse(t.calls)

    def test_all_stale_or_paid_or_wrong_scope_grants_fail_before_secret(self):
        item = invoke()
        good = grant(item)
        tamper = [
            {"tenant_id": UUID(int=99)}, {"case_id": UUID(int=99)},
            {"data_policy": GENERATOR}, {"provider_id": "other"},
            {"model_name": "wrong"}, {"endpoint": "https://example.invalid"},
            {"expiry_utc": NOW}, {"free_requests_remaining": 0},
            {"price_usd": "0.001"}, {"paid_fallback_disabled": False},
            {"confidential_egress_approved": False},
        ]
        for mutation in tamper:
            with self.subTest(mutation=mutation):
                p, t = adapter(item, g=replace(good, **mutation))
                with self.assertRaises(ProviderPolicyError):
                    p.propose(item)
                self.assertFalse(t.calls)

    def test_url_allowlist_no_plaintext_or_arbitrary_hosts(self):
        for endpoint in (
            "http://api.groq.com/openai/v1/chat/completions",
            "https://evil.invalid/api/v1/chat/completions",
            "https://api.groq.com/openai/v1/chat/completions?x=1",
            "https://foo@api.groq.com/openai/v1/chat/completions",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ProviderPolicyError):
                cfg(endpoint=endpoint)

    def test_parameters_must_be_bound(self):
        with self.assertRaises(ProviderPolicyError):
            cfg(temperature=0.5)
        with self.assertRaises(ProviderPolicyError):
            cfg(max_completion_tokens=999)

    def test_snapshot_mismatch_is_rejected_without_receipt(self):
        item = invoke()
        value = response(item)
        data = json.loads(value["choices"][0]["message"]["content"])
        data["snapshot_hash"] = "f" * 64
        value["choices"][0]["message"]["content"] = json.dumps(data)
        p, _ = adapter(item, envelope=value)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)
        with self.assertRaises(ProviderProtocolError):
            p.execution_receipt(item.request.request_id)

    def test_duplicate_json_key_fails_closed(self):
        item = invoke()
        bad = '{"request_id":"x","request_id":"y"}'
        v = response(item)
        v["choices"][0]["message"]["content"] = bad
        p, _ = adapter(item, envelope=v)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)

    def test_valid_shape_with_duplicate_json_key_fails_closed(self):
        item = invoke()
        envelope = response(item)
        raw = envelope["choices"][0]["message"]["content"]
        self.assertIn('"snapshot_hash":', raw)
        envelope["choices"][0]["message"]["content"] = raw.replace(
            '"snapshot_hash":',
            '"request_id":"%s","snapshot_hash":' % item.request.request_id,
            1,
        )
        p, transport = adapter(item, envelope=envelope)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)
        self.assertEqual(len(transport.calls), 1)
        with self.assertRaises(ProviderProtocolError):
            p.execution_receipt(item.request.request_id)

    def test_incomplete_or_unbounded_generation_refused(self):
        item = invoke()
        for patch in (
            {"choices": [{"finish_reason":"length","message":{"role":"assistant","content":"{}"}}]},
            {"usage": {"completion_tokens": 9999}},
            {"model": "unapproved"},
            {"choices": []},
        ):
            with self.subTest(patch=patch):
                p, _ = adapter(item, envelope=response(item, **patch))
                with self.assertRaises(ProviderProtocolError):
                    p.propose(item)

    def test_prompt_or_secret_invalid_without_network(self):
        item = invoke()
        t = FakeTransport(response(item))
        p = ZeroCostChatDraftingProvider(
            cfg(), prompt_builder=Prompt(),
            admission_resolver=lambda _: grant(item),
            secret_supplier=lambda: "bad\ncredential", transport=t,
            clock=lambda: NOW,
        )
        with self.assertRaises(ProviderPolicyError):
            p.propose(item)
        self.assertFalse(t.calls)

    def test_response_contract_exact_request_binding(self):
        item = invoke()
        data = json.loads(response(item)["choices"][0]["message"]["content"])
        data["request_id"] = str(UUID(int=99))
        v = response(item)
        v["choices"][0]["message"]["content"] = json.dumps(data)
        p, _ = adapter(item, envelope=v)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)
