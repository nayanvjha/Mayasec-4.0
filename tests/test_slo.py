"""SLO load test for MAYASEC pipeline.

Run:
    python tests/test_slo.py

Environment:
    SLO_TARGET_HOST (default: localhost)
    SLO_CONCURRENT (default: 500)
    SLO_DURATION_SECONDS (default: 30)
"""

from __future__ import annotations

import asyncio
import importlib
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

aiohttp = importlib.import_module("aiohttp")


SLO_TARGET_HOST = os.getenv("SLO_TARGET_HOST", "localhost")
SLO_CONCURRENT = int(os.getenv("SLO_CONCURRENT", "500"))
SLO_DURATION_SECONDS = int(os.getenv("SLO_DURATION_SECONDS", "30"))


@dataclass
class LoadStats:
    name: str
    latencies_ms: list[float]
    total_requests: int
    error_count: int
    responses_5xx: int


def _base_target() -> tuple[str, str]:
    raw = SLO_TARGET_HOST.strip() or "localhost"
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "localhost"
    return scheme, host


def _build_urls() -> dict[str, str]:
    scheme, host = _base_target()
    return {
        "waf": f"{scheme}://{host}:8001/score",
        "behavioral": f"{scheme}://{host}:5001/api/behavioral/score",
        "proxy": f"{scheme}://{host}/",
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)

    ordered = sorted(values)
    idx = (len(ordered) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _feature_vector() -> dict[str, Any]:
    # Mirrors ingress_proxy/telemetry_mirror.py feature schema.
    uri = random.choice([
        "/",
        "/login",
        "/admin",
        "/search?q=test",
        "/api/v1/status",
    ])
    ua = random.choice([
        "Mozilla/5.0",
        "curl/8.0.1",
        "python-requests/2.31.0",
    ])

    return {
        "source_ip": f"10.0.0.{random.randint(2, 254)}",
        "http_verb": random.choice(["GET", "POST"]),
        "uri": uri,
        "uri_length": len(uri),
        "body_length": random.randint(0, 1024),
        "num_params": random.randint(0, 8),
        "has_sql_keywords": random.choice([False, False, False, True]),
        "has_xss_patterns": random.choice([False, False, False, True]),
        "user_agent_entropy": float(len(set(ua))) / max(len(ua), 1),
        "user_agent_known_tool": any(tool in ua.lower() for tool in ("sqlmap", "nikto", "nmap", "burp", "curl")),
        "request_rate_60s": random.randint(1, 200),
        "hour_of_day": time.localtime().tm_hour,
        "inter_request_interval_ms": random.uniform(0.0, 1500.0),
        "uri_path_diversity": random.randint(1, 10),
        "body_size_variance": random.uniform(0.0, 200000.0),
        "http_method_diversity": random.randint(1, 3),
        "ua_change_detected": random.choice([False, True]),
        "param_count_variance": random.uniform(0.0, 20.0),
    }


async def _run_target(
    name: str,
    session: Any,
    duration_seconds: int,
    concurrency: int,
    send_one: Callable[[Any], Awaitable[tuple[float, bool, bool]]],
) -> LoadStats:
    latencies: list[float] = []
    total = 0
    errors = 0
    responses_5xx = 0

    deadline = time.monotonic() + duration_seconds
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal total, errors, responses_5xx
        while time.monotonic() < deadline:
            latency_ms, ok, is_5xx = await send_one(session)
            async with lock:
                total += 1
                latencies.append(latency_ms)
                if not ok:
                    errors += 1
                if is_5xx:
                    responses_5xx += 1

    await asyncio.gather(*(worker() for _ in range(concurrency)))

    return LoadStats(
        name=name,
        latencies_ms=latencies,
        total_requests=total,
        error_count=errors,
        responses_5xx=responses_5xx,
    )


async def _request_waf(session: Any, url: str) -> tuple[float, bool, bool]:
    t0 = time.perf_counter()
    try:
        async with session.post(url, json=_feature_vector()) as resp:
            await resp.read()
            latency = (time.perf_counter() - t0) * 1000.0
            is_5xx = 500 <= resp.status <= 599
            ok = 200 <= resp.status <= 299
            return latency, ok, is_5xx
    except Exception:
        latency = (time.perf_counter() - t0) * 1000.0
        return latency, False, False


async def _request_behavioral(session: Any, url: str) -> tuple[float, bool, bool]:
    t0 = time.perf_counter()
    try:
        async with session.post(url, json={"features": _feature_vector()}) as resp:
            await resp.read()
            latency = (time.perf_counter() - t0) * 1000.0
            is_5xx = 500 <= resp.status <= 599
            ok = 200 <= resp.status <= 299
            return latency, ok, is_5xx
    except Exception:
        latency = (time.perf_counter() - t0) * 1000.0
        return latency, False, False


async def _request_proxy(session: Any, url: str) -> tuple[float, bool, bool]:
    t0 = time.perf_counter()
    try:
        headers = {
            "User-Agent": "slo-tester/1.0",
            "Accept": "*/*",
        }
        params = {"slo": str(random.randint(1, 1_000_000))}
        async with session.get(url, params=params, headers=headers) as resp:
            await resp.read()
            latency = (time.perf_counter() - t0) * 1000.0
            is_5xx = 500 <= resp.status <= 599
            # 2xx/3xx/4xx are counted as non-5xx transport-level success for proxy SLO latency
            ok = not is_5xx
            return latency, ok, is_5xx
    except Exception:
        latency = (time.perf_counter() - t0) * 1000.0
        return latency, False, False


def _print_results_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "Target",
        "P50(ms)",
        "P95(ms)",
        "P99(ms)",
        "Total",
        "Errors",
        "5xx",
        "SLO",
    ]

    data = [headers]
    for row in rows:
        data.append([
            row["target"],
            f"{row['p50']:.2f}",
            f"{row['p95']:.2f}",
            f"{row['p99']:.2f}",
            str(row["total"]),
            str(row["errors"]),
            str(row["resp_5xx"]),
            "PASS" if row["pass"] else "FAIL",
        ])

    widths = [max(len(r[i]) for r in data) for i in range(len(headers))]

    def fmt(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    print("\nSLO Load Test Results")
    print("-" * (sum(widths) + (3 * (len(widths) - 1))))
    print(fmt(data[0]))
    print("-" * (sum(widths) + (3 * (len(widths) - 1))))
    for row in data[1:]:
        print(fmt(row))
    print("-" * (sum(widths) + (3 * (len(widths) - 1))))


async def _main_async() -> int:
    urls = _build_urls()
    timeout = aiohttp.ClientTimeout(total=5.0)

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        waf_stats = await _run_target(
            "WAF /score",
            session,
            SLO_DURATION_SECONDS,
            SLO_CONCURRENT,
            lambda s: _request_waf(s, urls["waf"]),
        )
        behavioral_stats = await _run_target(
            "Behavioral /api/behavioral/score",
            session,
            SLO_DURATION_SECONDS,
            SLO_CONCURRENT,
            lambda s: _request_behavioral(s, urls["behavioral"]),
        )
        proxy_stats = await _run_target(
            "Ingress proxy /",
            session,
            SLO_DURATION_SECONDS,
            SLO_CONCURRENT,
            lambda s: _request_proxy(s, urls["proxy"]),
        )

    all_5xx = waf_stats.responses_5xx + behavioral_stats.responses_5xx + proxy_stats.responses_5xx

    rows = []

    for stats, p95_limit in (
        (waf_stats, 50.0),
        (behavioral_stats, 50.0),
        (proxy_stats, 100.0),
    ):
        p50 = _percentile(stats.latencies_ms, 50)
        p95 = _percentile(stats.latencies_ms, 95)
        p99 = _percentile(stats.latencies_ms, 99)
        passed = p95 < p95_limit

        rows.append(
            {
                "target": stats.name,
                "p50": p50,
                "p95": p95,
                "p99": p99,
                "total": stats.total_requests,
                "errors": stats.error_count,
                "resp_5xx": stats.responses_5xx,
                "pass": passed,
            }
        )

    rows.append(
        {
            "target": "Zero 5xx (all targets)",
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "total": waf_stats.total_requests + behavioral_stats.total_requests + proxy_stats.total_requests,
            "errors": waf_stats.error_count + behavioral_stats.error_count + proxy_stats.error_count,
            "resp_5xx": all_5xx,
            "pass": all_5xx == 0,
        }
    )

    _print_results_table(rows)

    all_pass = all(row["pass"] for row in rows)
    return 0 if all_pass else 1


def main() -> None:
    try:
        code = asyncio.run(_main_async())
    except KeyboardInterrupt:
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
