"""Zero-cost remote drafting adapter: entirely synthetic; never network."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest
import traceback
import socket
import threading
import time
from unittest.mock import patch
from uuid import UUID

from lukart_work.validation.rules import digest
from lukart_work.contracts.messages import AIRequest, AIResult
from lukart_work.domain.models import Ref, VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.model_runtime.chat_zero_cost import (
    ChatProviderConfig, DirectTLSChatTransport, ZeroCostChatDraftingProvider, ZeroCostScopeAdmission,
    chat_parameters_hash, chat_wire_body,
)
from lukart_work.model_runtime.ollama import (
    ProviderBusy, ProviderPolicyError, ProviderProtocolError, ProviderResponseTooLarge, ProviderTimeout,
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
        request_id=item.request.request_id,
        quota_reservation_id=item.request.request_id,
        snapshot_hash=item.request.snapshot_hash, invocation_hash=digest(item),
        wire_body_sha256=sha256(chat_wire_body(cfg(), Prompt()(item))).hexdigest(),
        authority_revision=1, reserved_wire_bytes=250_000,
        reserved_completion_tokens=1024,
    )


class Prompt:
    pin = PROVIDER
    def __call__(self, item):
        return "SYNTHETIC ONLY: abstain."


class FakeTransport:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []
    def request(self, config, key, body, *, before_send=None):
        before_send()
        self.calls.append((config.endpoint, key, json.loads(body)))
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
        reservation_committer=lambda _, admission, body: admission,
        secret_supplier=lambda: "synthetic-secret-not-real",
        transport=transport, clock=lambda: NOW,
    ) if allow else ZeroCostChatDraftingProvider(
        cfg(), prompt_builder=Prompt(), transport=transport, clock=lambda: NOW,
    )
    return provider, transport


class ZeroCostChatProviderTests(unittest.TestCase):
    def assert_denied_before_secret_or_connect(self, provider, item, error):
        secrets, connects, posts = [], [], []
        provider.secret_supplier = lambda: secrets.append(1) or "synthetic-secret-not-real"
        provider.transport = DirectTLSChatTransport()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): connects.append(1)
            def connect(self): pass
            def request(self, *args, **kwargs): posts.append(1)
            def close(self): pass
        with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
            with self.assertRaises(error):
                provider.propose(item)
        self.assertEqual((secrets, connects, posts), ([], [], []))

    def test_admission_binds_snapshot_and_entire_invocation_before_secret(self):
        item = invoke()
        changes = [
            {"request": item.request.model_copy(update={"snapshot_hash": "f" * 64})},
            {"request": item.request.model_copy(update={"snapshot_id": UUID(int=99)})},
            {"request": item.request.model_copy(update={"input_refs": (
                Ref(kind="Fact", id=UUID(int=99), revision=1),)})},
            {"request": item.request.model_copy(update={"output_contract": MODEL})},
            {"section": Ref(kind="Section", id=UUID(int=99), revision=1)},
            {"evaluation_date": date(2026, 10, 9)},
        ]
        for change in changes:
            with self.subTest(change=change):
                p, _ = adapter(item)
                altered = item.model_copy(update=change)
                self.assertEqual(altered.request.request_id, item.request.request_id)
                self.assert_denied_before_secret_or_connect(p, altered, ProviderPolicyError)

    def test_actual_prompt_and_wire_hash_mismatch_precedes_secret(self):
        item = invoke()
        p, _ = adapter(item)
        class AlteredPrompt(Prompt):
            def __call__(self, invocation): return "Different egress text under the same prompt pin"
        p.prompt_builder = AlteredPrompt()
        self.assert_denied_before_secret_or_connect(p, item, ProviderPolicyError)
        p, _ = adapter(item, g=replace(grant(item), wire_body_sha256="f" * 64))
        self.assert_denied_before_secret_or_connect(p, item, ProviderPolicyError)

    def test_wire_budget_includes_system_envelope_and_parameters_before_secret(self):
        item = invoke()
        user_bytes = len(Prompt()(item).encode("utf-8"))
        self.assertGreater(len(chat_wire_body(cfg(), Prompt()(item))), user_bytes)
        p, _ = adapter(item, g=replace(grant(item), reserved_wire_bytes=user_bytes))
        self.assert_denied_before_secret_or_connect(p, item, ProviderResponseTooLarge)

    def test_missing_atomic_committer_denies_before_secret_or_connect(self):
        item = invoke()
        p, _ = adapter(item)
        p.reservation_committer = None
        self.assert_denied_before_secret_or_connect(p, item, ProviderPolicyError)

    def test_revocation_during_prompt_or_secret_is_observed_by_fresh_resolver(self):
        item = invoke()
        for during_secret in (False, True):
            with self.subTest(during_secret=during_secret):
                p, t = adapter(item)
                state = {"revoked": False}
                resolutions, secrets = [], []
                def resolve(invocation):
                    resolutions.append(state["revoked"])
                    return replace(grant(item), confidential_egress_approved=not state["revoked"])
                p.admission_resolver = resolve
                class RevokingPrompt(Prompt):
                    def __call__(self, invocation):
                        if not during_secret: state["revoked"] = True
                        return super().__call__(invocation)
                p.prompt_builder = RevokingPrompt()
                def secret():
                    secrets.append(1)
                    state["revoked"] = True
                    return "synthetic-secret-not-real"
                p.secret_supplier = secret
                with self.assertRaises(ProviderPolicyError): p.propose(item)
                self.assertEqual(len(secrets), int(during_secret))
                self.assertEqual(resolutions[-1], True)
                self.assertFalse(t.calls)

    def test_revocation_or_revision_change_during_connect_prevents_post(self):
        item = invoke()
        for mutation in ({"confidential_egress_approved": False},
                         {"free_requests_remaining": 0}, {"authority_revision": 2}):
            with self.subTest(mutation=mutation):
                p, _ = adapter(item)
                state = {"connected": False}
                p.admission_resolver = lambda _: replace(grant(item), **mutation) if state["connected"] else grant(item)
                p.transport = DirectTLSChatTransport()
                posts, commits = [], []
                p.reservation_committer = lambda *args: commits.append(1) or args[1]
                class Connection:
                    sock = None
                    def __init__(self, *args, **kwargs): pass
                    def connect(self): state["connected"] = True
                    def request(self, *args, **kwargs): posts.append(1)
                    def close(self): pass
                with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
                    with self.assertRaises(ProviderPolicyError): p.propose(item)
                self.assertTrue(state["connected"])
                self.assertEqual((posts, commits), ([], []))

    def test_atomic_committer_denial_changed_or_expired_permit_prevents_post(self):
        item = invoke()
        for failure in ("denied", "none", "revision", "binding", "expiry"):
            with self.subTest(failure=failure):
                p, _ = adapter(item)
                p.transport = DirectTLSChatTransport()
                now, posts, commits = [NOW], [], []
                p.clock = lambda: now[0]
                def commit(invocation, admission, body):
                    commits.append((admission, body))
                    if failure == "denied": raise RuntimeError("private authority diagnostic")
                    if failure == "none": return None
                    if failure == "revision": return replace(admission, authority_revision=2)
                    if failure == "binding": return replace(admission, snapshot_hash="f" * 64)
                    now[0] += timedelta(minutes=3)
                    return admission
                p.reservation_committer = commit
                class Connection:
                    sock = None
                    def __init__(self, *args, **kwargs): pass
                    def connect(self): pass
                    def request(self, *args, **kwargs): posts.append(1)
                    def close(self): pass
                with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
                    try: p.propose(item)
                    except ProviderPolicyError:
                        self.assertNotIn("private authority diagnostic", traceback.format_exc())
                    else: self.fail("invalid atomic send authorization accepted")
                self.assertEqual(len(commits), 1)
                self.assertFalse(posts)

    def test_exact_serialized_bytes_are_admitted_committed_and_posted(self):
        item = invoke()
        text = 'Zażółć "JSON"\nwith protocol escaping \\ and newlines'
        body = chat_wire_body(cfg(), text)
        admission = replace(grant(item), wire_body_sha256=sha256(body).hexdigest(),
                            reserved_wire_bytes=len(body))
        p, _ = adapter(item, g=admission)
        class UnicodePrompt(Prompt):
            def __call__(self, invocation): return text
        p.prompt_builder = UnicodePrompt()
        p.transport = DirectTLSChatTransport()
        posts, commits = [], []
        def commit(invocation, reservation, actual):
            commits.append(actual)
            self.assertEqual(invocation, item)
            self.assertEqual(reservation, admission)
            self.assertEqual(actual, body)
            return reservation
        p.reservation_committer = commit
        class Response:
            status = 200
            def read(self, cap): return json.dumps(response(item)).encode()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self): pass
            def request(self, method, path, *, body, headers): posts.append(body)
            def getresponse(self): return Response()
            def close(self): pass
        with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
            self.assertEqual(p.propose(item)["disposition"], "ABSTAIN")
        self.assertEqual(posts, [body])
        self.assertEqual(commits, posts)
        self.assertIs(posts[0], commits[0])
        self.assertEqual(json.loads(posts[0])["messages"][1]["content"], text)
        self.assertEqual(sha256(posts[0]).hexdigest(), admission.wire_body_sha256)
        self.assertEqual(len(posts[0]), admission.reserved_wire_bytes)

    def test_slow_initial_resolver_expiry_denies_before_secret(self):
        item = invoke()
        p, _ = adapter(item)
        now = [NOW]
        p.clock = lambda: now[0]
        def resolve(invocation):
            now[0] += timedelta(minutes=3)
            return grant(item)
        p.admission_resolver = resolve
        self.assert_denied_before_secret_or_connect(p, item, ProviderPolicyError)

    def test_send_callback_is_one_use_and_missing_callback_cannot_issue_receipt(self):
        item = invoke()
        for omit in (False, True):
            with self.subTest(omit=omit):
                p, _ = adapter(item)
                commits = []
                p.reservation_committer = lambda _, g, body: commits.append(1) or g
                class InvalidTransport:
                    def request(self, config, key, body, *, before_send):
                        if not omit:
                            before_send()
                            before_send()
                        return response(item)
                p.transport = InvalidTransport()
                with self.assertRaises(ProviderProtocolError): p.propose(item)
                self.assertEqual(len(commits), 0 if omit else 1)
                with self.assertRaises(ProviderProtocolError):
                    p.execution_receipt(item.request.request_id)

    def test_direct_transport_requires_send_callback_before_connection(self):
        with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection") as connection:
            with self.assertRaises(ProviderPolicyError):
                DirectTLSChatTransport().request(cfg(), "synthetic-key", b"{}")
        connection.assert_not_called()

    def test_total_deadline_aborts_actual_blocked_socket_read(self):
        client, server = socket.socketpair()
        entered, closed = threading.Event(), threading.Event()
        class Response:
            status = 200
            def read(self, cap):
                entered.set()
                return client.recv(cap)
        class Connection:
            sock = client
            def __init__(self, *args, **kwargs): pass
            def connect(self): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self):
                client.close()
                closed.set()
        transport = DirectTLSChatTransport()
        start = time.monotonic()
        try:
            with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
                with self.assertRaises(ProviderTimeout):
                    transport.request(cfg(timeout_seconds=0.1), "synthetic-key", b"{}", before_send=lambda: None)
            self.assertTrue(entered.is_set())
            self.assertTrue(closed.wait(1), "shutdown must unblock real socket read")
            self.assertLess(time.monotonic() - start, 1.5)
        finally:
            client.close()
            server.close()

    def test_stuck_connect_worker_does_not_accumulate_replacement_threads(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        sent = threading.Event()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self):
                entered.set()
                release.wait(2)
            def request(self, *args, **kwargs): sent.set()
            def close(self): closed.set()
        transport = DirectTLSChatTransport()
        try:
            with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
                with self.assertRaises(ProviderTimeout):
                    transport.request(cfg(timeout_seconds=0.05), "synthetic-key", b"{}", before_send=lambda: None)
                self.assertTrue(entered.is_set())
                with self.assertRaises(ProviderBusy):
                    transport.request(cfg(timeout_seconds=0.05), "synthetic-key", b"{}", before_send=lambda: None)
                release.set()
                self.assertTrue(closed.wait(1))
                self.assertFalse(sent.is_set(), "timed-out connect must never POST afterwards")
        finally:
            release.set()

    def test_expiry_during_connect_fails_before_post(self):
        item = invoke()
        p, _ = adapter(item)
        now = [NOW]
        p.clock = lambda: now[0]
        p.transport = DirectTLSChatTransport()
        sent = threading.Event()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self): now[0] += timedelta(minutes=3)
            def request(self, *args, **kwargs): sent.set()
            def close(self): pass
        with patch("lukart_work.model_runtime.chat_zero_cost.http.client.HTTPSConnection", Connection):
            with self.assertRaises(ProviderPolicyError):
                p.propose(item)
        self.assertFalse(sent.is_set())
    def test_positive_propose_json_uuid_and_tuple_wire_types(self):
        item = invoke()
        v = response(item)
        result = {
            "request_id": str(item.request.request_id),
            "snapshot_hash": item.request.snapshot_hash,
            "disposition": "PROPOSE", "proposals": [],
            "section": {"section": item.section.model_dump(mode="json"),
                        "statements": [{"id": str(UUID(int=66)),
                            "text": "Synthetic heading", "statement_type": "STRUCTURAL",
                            "support": "SOURCE_BACKED", "refs": [], "citations": [],
                            "inference_label": None}]},
            "missing_information": [], "reason": None,
        }
        v["choices"][0]["message"]["content"] = json.dumps(result)
        p, t = adapter(item, envelope=v)
        actual = p.propose(item)
        self.assertEqual(actual, result)
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(p.execution_receipt(item.request.request_id).request_id,
                         item.request.request_id)

    def test_one_reservation_cannot_authorize_another_request(self):
        first = invoke()
        second = first.model_copy(update={"request": first.request.model_copy(
            update={"request_id": UUID(int=12)})})
        p, t = adapter(first)
        p.propose(first)
        with self.assertRaises(ProviderPolicyError):
            p.propose(second)
        self.assertEqual(len(t.calls), 1)

    def test_reserved_prompt_budget_and_reservation_replay_are_enforced(self):
        item = invoke()
        p, t = adapter(item, g=replace(grant(item), reserved_wire_bytes=1))
        with self.assertRaises(ProviderResponseTooLarge):
            p.propose(item)
        self.assertFalse(t.calls)
        p, t = adapter(item)
        p.propose(item)
        other = item.model_copy(update={"request": item.request.model_copy(
            update={"request_id": UUID(int=12)})})
        p.admission_resolver = lambda _: replace(grant(other),
            quota_reservation_id=grant(item).quota_reservation_id)
        with self.assertRaises(ProviderProtocolError):
            p.propose(other)
        self.assertEqual(len(t.calls), 1)

    def test_attempt_ledger_is_bounded_without_eviction_or_reexecution(self):
        item = invoke()
        p, t = adapter(item)
        p.config = cfg(max_attempted_requests=1)
        p.propose(item)
        other = item.model_copy(update={"request": item.request.model_copy(
            update={"request_id": UUID(int=12)})})
        p.admission_resolver = grant
        with self.assertRaises(ProviderPolicyError):
            p.propose(other)
        with self.assertRaises(ProviderProtocolError):
            p.propose(item)
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(len(p._attempted), 1)
        self.assertEqual(len(p._reservations), 1)

    def test_expiry_after_slow_prompt_or_secret_fails_before_network(self):
        item = invoke()
        for slow_secret in (False, True):
            p, t = adapter(item)
            now = [NOW]
            p.clock = lambda: now[0]
            class SlowPrompt(Prompt):
                def __call__(self, invocation):
                    if not slow_secret:
                        now[0] += timedelta(minutes=3)
                    return super().__call__(invocation)
            p.prompt_builder = SlowPrompt()
            def supplier():
                if slow_secret:
                    now[0] += timedelta(minutes=3)
                return "synthetic-secret-not-real"
            p.secret_supplier = supplier
            with self.assertRaises(ProviderPolicyError):
                p.propose(item)
            self.assertFalse(t.calls)

    def test_secret_supplier_exception_does_not_leak_in_traceback(self):
        item = invoke()
        p, t = adapter(item)
        def fail():
            raise RuntimeError("private-credential-content")
        p.secret_supplier = fail
        try:
            p.propose(item)
        except ProviderPolicyError:
            self.assertNotIn("private-credential-content", traceback.format_exc())
        else:
            self.fail("secret supplier exception was accepted")
        self.assertFalse(t.calls)

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
            {"request_id": UUID(int=99)}, {"quota_reservation_id": "not-a-UUID"},
            {"reserved_wire_bytes": 0}, {"reserved_wire_bytes": True},
            {"reserved_wire_bytes": 274_001}, {"reserved_completion_tokens": 1},
            {"reserved_completion_tokens": True}, {"expiry_utc": "invalid"},
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
            reservation_committer=lambda _, admission, body: admission,
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


# This positive service path requires the existing isolated PostgreSQL fixture.
# It remains synthetic transport evidence; it never certifies a live provider.
from tests.test_stage09 import ControlledDraftingTests
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.drafting.contracts import DraftingTrace
from lukart_work.contracts.messages import CommandResult


class ZeroCostControlledDraftingTests(ControlledDraftingTests):
    def test_chat_propose_commits_only_generated_draft_through_existing_service(self):
        case = self.approved_planning_case()
        fixture = self
        pin = VersionPin.model_validate_json(json.dumps(self.profile['prompt']))
        class ServicePrompt:
            def __init__(self):
                self.pin = pin
                self.invocation = None
            def __call__(self, invocation):
                self.invocation = invocation
                return invocation.model_dump_json()
        prompt = ServicePrompt()
        class ServiceTransport:
            calls = 0
            def request(self, config, key, body, *, before_send=None):
                before_send()
                self.calls += 1
                return {'model': config.model_name,
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant',
                        'content': json.dumps(fixture.valid_output(case, prompt.invocation))}}],
                    'usage': {'completion_tokens': 100}}
        transport = ServiceTransport()
        config = cfg(provider=pin, model=pin, generator=pin)
        def reservation(invocation):
            return ZeroCostScopeAdmission(tenant_id=invocation.request.tenant_id,
                case_id=invocation.request.case_id, data_policy=invocation.request.data_policy,
                provider_id=pin.id, model_name=config.model_name, endpoint=config.endpoint,
                expiry_utc=NOW+timedelta(minutes=2),free_requests_remaining=1,price_usd='0',
                paid_fallback_disabled=True,confidential_egress_approved=True,
                request_id=invocation.request.request_id,quota_reservation_id=invocation.request.request_id,
                snapshot_hash=invocation.request.snapshot_hash, invocation_hash=digest(invocation),
                wire_body_sha256=sha256(chat_wire_body(config, invocation.model_dump_json())).hexdigest(),
                authority_revision=1, reserved_wire_bytes=config.max_prompt_bytes,
                reserved_completion_tokens=config.max_completion_tokens)
        provider = ZeroCostChatDraftingProvider(config,prompt_builder=prompt,
            admission_resolver=reservation,
            reservation_committer=lambda _, admission, body: admission,secret_supplier=lambda:'synthetic-secret-not-real',
            transport=transport,clock=lambda:NOW)
        self.profile['model_parameters_hash'] = config.model_parameters_hash
        self.drafting = ControlledDraftingService(self.repo,self.authority,provider,{'QUICK':self.profile})
        result = self.drafting.generate(json.dumps(self.generate_request(case)),self.token)
        self.assertIsInstance(result,CommandResult,result)
        self.assertEqual(result.state,'APPLIED')
        self.assertEqual(self.get(result.refs[0]).status,'GENERATED')
        self.assertEqual(transport.calls,1)
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            traces=tx.objects('drafting_trace',DraftingTrace)
            self.assertEqual(len(traces),1)
            self.assertEqual(traces[0].results[0].disposition,'PROPOSE')
            self.assertEqual(traces[0].execution_receipts[0].model_parameters_hash,config.model_parameters_hash)


def load_tests(loader, tests, pattern):
    # Reuse Stage09 setup/helpers without duplicating all inherited Stage09 cases.
    return unittest.TestSuite((loader.loadTestsFromTestCase(ZeroCostChatProviderTests),
        ZeroCostControlledDraftingTests('test_chat_propose_commits_only_generated_draft_through_existing_service')))
