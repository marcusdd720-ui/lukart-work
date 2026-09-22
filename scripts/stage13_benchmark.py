"""Stage 13 repeatable local benchmark harness.

This file performs no network I/O and does not mutate CASE state. Absolute wall-clock
values from shared CI runners are evidence only for that runner; Stage 13 comparisons
must use exact-SHA results and avoid pretending that noisy CI timings are universal SLOs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from uuid import UUID

from lukart_work.contracts.messages import AIRequest
from lukart_work.domain.models import VersionPin
from lukart_work.drafting.contracts import ModelExecutionReceipt
from lukart_work.validation.rules import RevisionLedger, digest
from lukart_work.model_runtime import OllamaConfig, ollama_parameters_hash
from lukart_work.rendering.service import RenderingEngine
from tests.fixtures import case, uid
from tests.stage11_render_fixture import build_fixture

ROOT = Path(__file__).resolve().parents[1]
H = "a" * 64
PIN = VersionPin(id="urn:lukart:stage13:synthetic", version="1.0.0", content_hash=H)


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("EMPTY_SAMPLE")
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def measure(name: str, fn, iterations: int) -> dict:
    # Warm once to exclude one-time import/cache effects from warm execution.
    fn()
    timings = []
    cpu_timings = []
    tracemalloc.start()
    try:
        for _ in range(iterations):
            cpu_started = time.process_time_ns()
            started = time.perf_counter_ns()
            fn()
            timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
            cpu_timings.append((time.process_time_ns() - cpu_started) / 1_000_000.0)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "operation": name,
        "iterations": iterations,
        "unit": "ms",
        "min": min(timings),
        "max": max(timings),
        "mean": statistics.fmean(timings),
        "mean_cpu_ms": statistics.fmean(cpu_timings),
        "throughput_per_second_at_p50": 1000.0 / percentile(timings, 0.50) if percentile(timings, 0.50) else None,
        "p50": percentile(timings, 0.50),
        "p95": percentile(timings, 0.95),
        "p99": percentile(timings, 0.99),
        "peak_memory_bytes": peak,
    }


def cold_import(iterations: int = 5) -> dict:
    code = (
        "import lukart_work.contracts.messages;"
        "import lukart_work.drafting.contracts;"
        "import lukart_work.rendering.service;"
        "import lukart_work.audit.service"
    )
    timings = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-c", code],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return {
        "operation": "cold_import",
        "iterations": iterations,
        "unit": "ms",
        "min": min(timings),
        "max": max(timings),
        "mean": statistics.fmean(timings),
        "mean_cpu_ms": None,
        "throughput_per_second_at_p50": 1000.0 / percentile(timings, 0.50) if percentile(timings, 0.50) else None,
        "p50": percentile(timings, 0.50),
        "p95": percentile(timings, 0.95),
        "p99": percentile(timings, 0.99),
        "peak_memory_bytes": None,
    }


def fixtures():
    request = AIRequest(
        request_id=UUID(int=88),
        tenant_id=UUID(int=1000),
        case_id=UUID(int=1),
        task="DRAFTING",
        snapshot_id=UUID(int=30),
        snapshot_hash=H,
        input_refs=(),
        section_contract=None,
        prompt=PIN,
        output_contract=PIN,
        data_policy=PIN,
    )
    receipt = ModelExecutionReceipt(
        contract="urn:lukart:work:ModelExecutionReceipt:1.0.0",
        request_id=request.request_id,
        provider=PIN,
        model=PIN,
        generator=PIN,
        model_parameters_hash=H,
    )
    payload = {
        "case": "synthetic-stage13",
        "values": [{"index": i, "hash": H} for i in range(64)],
    }
    return request, receipt, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/stage13-baseline.json")
    parser.add_argument("--mode", default="BASELINE", choices=("BASELINE", "POST_IMPLEMENTATION"))
    args = parser.parse_args()

    request, receipt, payload = fixtures()
    request_json = request.model_dump_json()
    receipt_json = receipt.model_dump_json()

    results = [
        cold_import(),
        measure("canonical_digest", lambda: digest(payload), 2000),
        measure("ai_request_validate", lambda: AIRequest.model_validate_json(request_json), 1000),
        measure(
            "model_execution_receipt_validate",
            lambda: ModelExecutionReceipt.model_validate_json(receipt_json),
            1000,
        ),
    ]
    if args.mode == "POST_IMPLEMENTATION":
        render_request, render_records, render_validation = build_fixture()
        engine = RenderingEngine()
        bundle = engine.render(render_request, render_records, render_validation)

        replay_ledger = RevisionLedger()
        replay_entity = case()
        replay_command = uid(770)
        replay_ledger.append(replay_entity, 0, 0, replay_command)

        provider_pin = VersionPin(
            id="urn:lukart:stage13:provider", version="1.0.0", content_hash="d" * 64
        )
        model_pin = VersionPin(
            id="urn:lukart:stage13:model", version="synthetic", content_hash="c" * 64
        )
        generator_pin = VersionPin(
            id="urn:lukart:stage13:generator", version="1.0.0", content_hash="e" * 64
        )
        params_hash = ollama_parameters_hash()

        def provider_config():
            return OllamaConfig(
                endpoint="http://127.0.0.1:11434",
                model_name="synthetic:1b",
                provider=provider_pin,
                model=model_pin,
                generator=generator_pin,
                model_parameters_hash=params_hash,
            )

        def concurrent_digest():
            values = [dict(payload, batch=i) for i in range(64)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(digest, values))

        results.extend([
            measure(
                "render_docx_pdf_bundle",
                lambda: engine.render(render_request, render_records, render_validation),
                5,
            ),
            measure("render_bundle_validate", lambda: engine.validate(bundle), 50),
            measure(
                "revision_ledger_harness_idempotent_replay",
                lambda: replay_ledger.append(replay_entity, 0, 0, replay_command),
                1000,
            ),
            measure("ollama_config_validate", provider_config, 500),
            measure("canonical_digest_concurrency_4x64", concurrent_digest, 10),
        ])
    report = {
        "contract": "urn:lukart:work:Stage13Benchmark:1.0.0",
        "mode": args.mode,
        "tested_sha": os.environ.get("TESTED_SHA") or os.environ.get("GITHUB_SHA") or "LOCAL_UNBOUND",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "network_io": "NOT_USED",
        "case_data": "SYNTHETIC_ONLY",
        "results": results,
    }
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
