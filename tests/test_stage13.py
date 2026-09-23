"""Stage 13 local-provider assurance. Synthetic fixtures only; no external network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from uuid import UUID

from lukart_work.contracts.messages import AIRequest, AIResult
from lukart_work.domain.models import Ref, VersionPin
from lukart_work.drafting.contracts import DraftingInvocation
from lukart_work.model_runtime import (
    OllamaConfig, OllamaHttpTransport, OllamaProvider, ProviderBusy, ProviderCancelled,
    ProviderModelMissing, ProviderPolicyError, ProviderProtocolError,
    ProviderResponseTooLarge, ProviderTimeout, ollama_parameters_hash,
)
from lukart_work.model_runtime.ollama import strict_json_bytes

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

    def test_options_are_deeply_frozen_after_hash_validation(self):
        source = {"sampling": {"temperature": 0}, "stop": ["END"]}
        value = config(
            options=source,
            model_parameters_hash=ollama_parameters_hash(options=source),
        )
        source["sampling"]["temperature"] = 1
        source["stop"].append("LATER")
        self.assertEqual(value.options["sampling"]["temperature"], 0)
        self.assertEqual(value.options["stop"], ("END",))
        with self.assertRaises(TypeError):
            value.options["sampling"]["temperature"] = 2

    def test_transport_rejects_oversized_body_without_stale_active_request(self):
        transport = OllamaHttpTransport(config(max_request_bytes=1024))
        request_id = UUID(int=999)
        with self.assertRaises(ProviderResponseTooLarge):
            transport.json_request(
                "POST", "/api/generate", {"prompt": "x" * 2048}, request_id
            )
        self.assertEqual(transport._active, {})

    def test_strict_outer_json_rejects_duplicate_keys(self):
        with self.assertRaises(ProviderProtocolError):
            strict_json_bytes(b'{"done":true,"done":false}')

    def test_transport_rejects_unapproved_method_path_pairs(self):
        transport = OllamaHttpTransport(config())
        with self.assertRaises(ProviderPolicyError):
            transport.json_request("POST", "/api/tags", {}, UUID(int=997))
        with self.assertRaises(ProviderPolicyError):
            transport.json_request("GET", "/api/generate", None, UUID(int=998))

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

    def test_cancel_unknown_request_does_not_accumulate_state(self):
        provider = OllamaProvider(
            config(), PromptBuilder("prompt"), FakeTransport([])
        )
        with self.assertRaises(ProviderProtocolError):
            provider.cancel(UUID(int=12345))
        self.assertEqual(provider._cancelled, set())

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

    def test_post_implementation_benchmark_runs_as_direct_script(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "performance.json"
            env = os.environ.copy()
            env["TESTED_SHA"] = "f" * 40
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    "utf8",
                    str(root / "scripts/stage13_benchmark.py"),
                    "--mode",
                    "POST_IMPLEMENTATION",
                    "--output",
                    str(output),
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + "\\n" + completed.stderr,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "POST_IMPLEMENTATION")
            self.assertEqual(report["tested_sha"], "f" * 40)
            operations = {row["operation"] for row in report["results"]}
            self.assertIn("render_docx_pdf_bundle", operations)
            self.assertIn("canonical_digest_concurrency_4x64", operations)

    def test_health_reports_digest_drift_without_claiming_ready(self):
        provider = OllamaProvider(
            config(), PromptBuilder("prompt"), FakeTransport([tags("f" * 64)])
        )
        self.assertEqual(provider.health()["status"], "DRIFT")


if __name__ == "__main__":
    unittest.main()
