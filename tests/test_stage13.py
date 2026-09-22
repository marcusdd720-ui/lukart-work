"""Stage 13 local-provider assurance. Synthetic fixtures only; no external network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import threading
import unittest
from uuid import UUID

from lukart_work.contracts.messages import AIRequest, AIResult
from lukart_work.domain.models import Ref, VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.model_runtime import (
    OllamaConfig, OllamaProvider, ProviderBusy, ProviderCancelled,
    ProviderModelMissing, ProviderPolicyError, ProviderProtocolError,
    ProviderResponseTooLarge, ProviderTimeout, ollama_parameters_hash,
)

H = "a" * 64
MODEL_DIGEST = "c" * 64
PROVIDER = VersionPin(id="urn:stage13:ollama", version="1.0.0", content_hash="d" * 64)
MODEL = VersionPin(id="urn:stage13:model", version="synthetic", content_hash=MODEL_DIGEST)
GENERATOR = VersionPin(id="urn:stage13:generator", version="1.0.0", content_hash="e" * 64)


def config(**changes):
    values = dict(
        endpoint="http://127.0.0.1:11434",
        model_name="synthetic:1b",
        provider=PROVIDER,
        model=MODEL,
        generator=GENERATOR,
        model_parameters_hash=ollama_parameters_hash(),
    )
    values.update(changes)
    return OllamaConfig(**values)


def invocation(seed=1):
    request = AIRequest(
        request_id=UUID(int=100 + seed),
        tenant_id=UUID(int=1000),
        case_id=UUID(int=1),
        task="DRAFTING",
        snapshot_id=UUID(int=30),
        snapshot_hash=H,
        input_refs=(),
        section_contract=None,
        prompt=PROVIDER,
        output_contract=GENERATOR,
        data_policy=PROVIDER,
    )
    return DraftingInvocation(
        contract="urn:lukart:work:DraftingInvocation:1.0.0",
        section=Ref(kind="Section", id=UUID(int=50 + seed), revision=1),
        evaluation_date=date(2026, 9, 22),
        request=request,
    )


def result_json(item):
    return AIResult(
        request_id=item.request.request_id,
        snapshot_hash=item.request.snapshot_hash,
        disposition="ABSTAIN",
        proposals=(),
        section=None,
        missing_information=("synthetic evidence",),
        reason="Synthetic Stage 13 abstention",
    ).model_dump_json()


def tags(digest=MODEL_DIGEST):
    return {
        "models": [{
            "name": "synthetic:1b",
            "model": "synthetic:1b",
            "digest": digest,
        }]
    }


class PromptBuilder:
    def __init__(self, text="synthetic prompt", pin=PROVIDER):
        self.text = text
        self.pin = pin

    def __call__(self, invocation):
        return self.text


class FakeTransport:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []
        self.cancelled = []

    def json_request(self, method, path, payload, request_id):
        self.calls.append((method, path, payload, request_id))
        if not self.values:
            raise AssertionError("unexpected request")
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def cancel(self, request_id):
        self.cancelled.append(request_id)


class BlockingTransport:
    def __init__(self, item):
        self.item = item
        self.entered = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.calls = 0

    def json_request(self, method, path, payload, request_id):
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            self.release.wait(timeout=5)
            if self.cancelled.is_set():
                raise ProviderCancelled()
            return tags()
        if path == "/api/generate":
            return {"model": "synthetic:1b", "done": True, "response": result_json(self.item)}
        return tags()

    def cancel(self, request_id):
        self.cancelled.set()
        self.release.set()


class Stage13ProviderTests(unittest.TestCase):
    def test_parameters_hash_binds_options(self):
        self.assertNotEqual(
            ollama_parameters_hash(),
            ollama_parameters_hash(options={"temperature": 0}),
        )

    def test_options_are_frozen_after_hash_validation(self):
        source = {"temperature": 0}
        value = config(
            options=source,
            model_parameters_hash=ollama_parameters_hash(options=source),
        )
        source["temperature"] = 1
        self.assertEqual(value.options["temperature"], 0)
        with self.assertRaises(TypeError):
            value.options["temperature"] = 2

    def test_remote_endpoint_denied_by_default(self):
        with self.assertRaises(ProviderPolicyError):
            config(endpoint="http://example.com:11434", allowed_hosts=("example.com",))

    def test_explicit_remote_allowlist_requires_local_only_off(self):
        value = config(
            endpoint="http://10.0.0.2:11434",
            local_only=False,
            allowed_hosts=("10.0.0.2",),
        )
        self.assertEqual(value.parsed_endpoint.hostname, "10.0.0.2")

    def test_endpoint_userinfo_path_query_rejected(self):
        for endpoint in (
            "http://u:p@127.0.0.1:11434",
            "http://127.0.0.1:11434/proxy",
            "http://127.0.0.1:11434/?x=1",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ProviderPolicyError):
                config(endpoint=endpoint)

    def test_prompt_builder_pin_must_match_request(self):
        item = invocation()
        provider = OllamaProvider(
            config(), PromptBuilder(pin=GENERATOR), FakeTransport([])
        )
        with self.assertRaises(ProviderPolicyError):
            provider.propose(item)

    def test_success_binds_model_digest_and_receipt(self):
        item = invocation()
        transport = FakeTransport([
            tags(),
            {"model": "synthetic:1b", "done": True, "response": result_json(item)},
            tags(),
        ])
        provider = OllamaProvider(config(), PromptBuilder(), transport)
        raw = provider.propose(item)
        self.assertEqual(raw["request_id"], str(item.request.request_id))
        receipt = provider.execution_receipt(item.request.request_id)
        self.assertEqual(receipt.provider, PROVIDER)
        self.assertEqual(receipt.model, MODEL)
        self.assertEqual(receipt.generator, GENERATOR)
        generate = [call for call in transport.calls if call[1] == "/api/generate"]
        self.assertEqual(len(generate), 1)
        payload = generate[0][2]
        self.assertIs(payload["stream"], False)
        self.assertEqual(payload["format"], AIResult.model_json_schema())

    def test_missing_model_fails_before_generation(self):
        provider = OllamaProvider(
            config(), PromptBuilder(), FakeTransport([{"models": []}])
        )
        with self.assertRaises(ProviderModelMissing):
            provider.propose(invocation())

    def test_digest_drift_fails_closed_and_emits_no_receipt(self):
        item = invocation()
        transport = FakeTransport([
            tags(),
            {"model": "synthetic:1b", "done": True, "response": result_json(item)},
            tags("f" * 64),
        ])
        provider = OllamaProvider(config(), PromptBuilder(), transport)
        with self.assertRaises(ProviderProtocolError):
            provider.propose(item)
        with self.assertRaises(ProviderProtocolError):
            provider.execution_receipt(item.request.request_id)

    def test_timeout_is_not_retried(self):
        item = invocation()
        transport = FakeTransport([tags(), ProviderTimeout()])
        provider = OllamaProvider(config(), PromptBuilder(), transport)
        with self.assertRaises(ProviderTimeout):
            provider.propose(item)
        self.assertEqual(
            len([call for call in transport.calls if call[1] == "/api/generate"]), 1
        )

    def test_empty_partial_and_wrong_model_envelopes_rejected(self):
        item = invocation()
        bad = (
            {"model": "synthetic:1b", "done": True, "response": ""},
            {"model": "synthetic:1b", "done": False, "response": result_json(item)},
            {"model": "other", "done": True, "response": result_json(item)},
        )
        for envelope in bad:
            with self.subTest(envelope=envelope):
                provider = OllamaProvider(
                    config(), PromptBuilder(),
                    FakeTransport([tags(), envelope, tags()]),
                )
                with self.assertRaises(ProviderProtocolError):
                    provider.propose(item)

    def test_malformed_ai_result_rejected(self):
        item = invocation()
        provider = OllamaProvider(
            config(), PromptBuilder(),
            FakeTransport([
                tags(),
                {"model": "synthetic:1b", "done": True, "response": '{"status":"FINAL"}'},
                tags(),
            ]),
        )
        with self.assertRaises(ProviderProtocolError):
            provider.propose(item)

    def test_request_binding_substitution_rejected(self):
        item = invocation()
        other = invocation(2)
        provider = OllamaProvider(
            config(), PromptBuilder(),
            FakeTransport([
                tags(),
                {"model": "synthetic:1b", "done": True, "response": result_json(other)},
                tags(),
            ]),
        )
        with self.assertRaises(ProviderProtocolError):
            provider.propose(item)

    def test_prompt_size_bound(self):
        item = invocation()
        cfg = config(max_prompt_bytes=1024)
        provider = OllamaProvider(
            cfg, PromptBuilder("x" * 1025), FakeTransport([tags()])
        )
        with self.assertRaises(ProviderResponseTooLarge):
            provider.propose(item)

    def test_concurrency_backpressure_is_fail_closed(self):
        item = invocation()
        blocking = BlockingTransport(item)
        provider = OllamaProvider(config(max_concurrency=1), PromptBuilder("prompt"), blocking)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(provider.propose, item)
            self.assertTrue(blocking.entered.wait(timeout=5))
            with self.assertRaises(ProviderBusy):
                provider.propose(invocation(2))
            blocking.release.set()
            first.result()

    def test_duplicate_inflight_request_id_is_rejected(self):
        item = invocation()
        blocking = BlockingTransport(item)
        provider = OllamaProvider(
            config(max_concurrency=2), PromptBuilder("prompt"), blocking
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(provider.propose, item)
            self.assertTrue(blocking.entered.wait(timeout=5))
            with self.assertRaises(ProviderProtocolError):
                provider.propose(item)
            blocking.release.set()
            first.result()

    def test_cancellation_is_propagated_to_transport(self):
        item = invocation()
        blocking = BlockingTransport(item)
        provider = OllamaProvider(config(), PromptBuilder("prompt"), blocking)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(provider.propose, item)
            self.assertTrue(blocking.entered.wait(timeout=5))
            provider.cancel(item.request.request_id)
            with self.assertRaises(ProviderCancelled):
                future.result()
        self.assertTrue(blocking.cancelled.is_set())

    def test_health_reports_digest_drift_without_claiming_ready(self):
        provider = OllamaProvider(
            config(), PromptBuilder("prompt"), FakeTransport([tags("f" * 64)])
        )
        self.assertEqual(provider.health()["status"], "DRIFT")


if __name__ == "__main__":
    unittest.main()
