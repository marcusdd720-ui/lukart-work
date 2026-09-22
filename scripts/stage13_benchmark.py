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
from lukart_work.validation.rules import digest

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
    tracemalloc.start()
    try:
        for _ in range(iterations):
            started = time.perf_counter_ns()
            fn()
            timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
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
