#!/usr/bin/env python3
"""MAYASEC Sensor Agent (lightweight).

Modes:
- proxy: transparent reverse proxy on :8080 forwarding to UPSTREAM_URL
- logtail: tails LOG_FILE and batches parsed events to MAYASEC
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, Request, Response
import uvicorn

SENSOR_VERSION = "1.0.0"

MAYASEC_API_KEY = os.getenv("MAYASEC_API_KEY", "").strip()
MAYASEC_API_URL = os.getenv("MAYASEC_API_URL", "http://localhost:5000").rstrip("/")
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "").rstrip("/")
MODE = os.getenv("MODE", "proxy").strip().lower()
LOG_FILE = os.getenv("LOG_FILE", "").strip()

EMIT_ENDPOINT = f"{MAYASEC_API_URL}/api/v1/emit-event"
REGISTER_ENDPOINT = f"{MAYASEC_API_URL}/api/v1/sensor/register"
HOSTNAME = socket.gethostname()

COMMON_LOG_RE = re.compile(
    r'^(?P<source_ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<uri>[^\s"]+)(?:\s+[^"]+)?"\s+(?P<status>\d{3})\s+(?P<body_length>\S+)'
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "X-Sensor-Hostname": HOSTNAME,
        "X-Sensor-Mode": MODE,
        "X-Sensor-Version": SENSOR_VERSION,
    }
    if MAYASEC_API_KEY:
        headers["X-API-Key"] = MAYASEC_API_KEY
    return headers


async def register_sensor() -> None:
    payload = {
        "hostname": HOSTNAME,
        "mode": MODE,
        "version": SENSOR_VERSION,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(REGISTER_ENDPOINT, headers=api_headers(), json=payload)
            if resp.status_code >= 400:
                print(f"[sensor] register failed: status={resp.status_code} body={resp.text[:300]}")
            else:
                print("[sensor] registered successfully")
    except Exception as exc:
        print(f"[sensor] register error: {exc}")


async def send_event(event: Dict) -> None:
    payload = {
        "event_type": "http_request",
        **event,
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(EMIT_ENDPOINT, headers=api_headers(), json=payload)
    except Exception as exc:
        print(f"[sensor] emit event error: {exc}")


async def send_batch(events: List[Dict]) -> None:
    if not events:
        return
    payload = {"events": events}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(EMIT_ENDPOINT, headers=api_headers(), json=payload)
    except Exception as exc:
        print(f"[sensor] emit batch error: {exc}")


# -------------------------
# Mode A: reverse proxy
# -------------------------

app = FastAPI(title="mayasec-sensor", version=SENSOR_VERSION)
_proxy_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def _startup() -> None:
    global _proxy_client
    _proxy_client = httpx.AsyncClient(timeout=30, follow_redirects=False)
    await register_sensor()


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _proxy_client:
        await _proxy_client.aclose()


def _upstream_target(req: Request) -> str:
    path = req.url.path
    query = req.url.query
    target = urljoin(f"{UPSTREAM_URL}/", path.lstrip("/"))
    return f"{target}?{query}" if query else target


def _sanitize_response_headers(headers: httpx.Headers) -> Dict[str, str]:
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
    out = {}
    for k, v in headers.items():
        if k.lower() in hop_by_hop:
            continue
        out[k] = v
    return out


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def reverse_proxy(full_path: str, request: Request) -> Response:
    del full_path
    if not UPSTREAM_URL:
        return Response(content="UPSTREAM_URL is required in MODE=proxy", status_code=500)

    client = _proxy_client
    if client is None:
        return Response(content="proxy client unavailable", status_code=503)

    start = time.perf_counter()
    body = await request.body()
    target = _upstream_target(request)

    source_ip = request.headers.get("x-forwarded-for")
    if not source_ip and request.client:
        source_ip = request.client.host
    source_ip = source_ip or "unknown"

    upstream_headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}

    try:
        upstream_resp = await client.request(
            method=request.method,
            url=target,
            headers=upstream_headers,
            content=body,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        event = {
            "timestamp": iso_now(),
            "source_ip": source_ip,
            "http_method": request.method,
            "method": request.method,
            "uri": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
            "headers": dict(request.headers),
            "body_length": len(body),
            "status_code": upstream_resp.status_code,
            "latency_ms": latency_ms,
            "sensor_hostname": HOSTNAME,
            "sensor_mode": MODE,
            "sensor_version": SENSOR_VERSION,
            "event_type": "http_request",
            "threat_score": 0,
            "severity": "low",
            "source": "mayasec-sensor",
            "sensor_id": HOSTNAME,
        }
        asyncio.create_task(send_event(event))

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=_sanitize_response_headers(upstream_resp.headers),
        )
    except httpx.RequestError as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        event = {
            "timestamp": iso_now(),
            "source_ip": source_ip,
            "http_method": request.method,
            "method": request.method,
            "uri": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
            "headers": dict(request.headers),
            "body_length": len(body),
            "status_code": 502,
            "latency_ms": latency_ms,
            "event_type": "http_request",
            "severity": "medium",
            "threat_score": 30,
            "source": "mayasec-sensor",
            "sensor_id": HOSTNAME,
            "sensor_hostname": HOSTNAME,
            "sensor_mode": MODE,
            "sensor_version": SENSOR_VERSION,
            "error": str(exc),
        }
        asyncio.create_task(send_event(event))
        return Response(content="Bad Gateway", status_code=502)


# -------------------------
# Mode B: log tail
# -------------------------

def parse_log_line(line: str) -> Optional[Dict]:
    line = line.rstrip("\n")
    if not line:
        return None

    match = COMMON_LOG_RE.match(line)
    if not match:
        return {
            "event_type": "http_request",
            "timestamp": iso_now(),
            "source_ip": "unknown",
            "method": "GET",
            "http_method": "GET",
            "uri": "/",
            "headers": {},
            "body_length": 0,
            "status_code": 0,
            "latency_ms": 0,
            "raw_log": line[:2000],
            "severity": "low",
            "threat_score": 0,
            "source": "mayasec-sensor",
            "sensor_id": HOSTNAME,
            "sensor_hostname": HOSTNAME,
            "sensor_mode": MODE,
            "sensor_version": SENSOR_VERSION,
        }

    body_length_raw = match.group("body_length")
    try:
        body_length = int(body_length_raw) if body_length_raw != "-" else 0
    except ValueError:
        body_length = 0

    return {
        "event_type": "http_request",
        "timestamp": iso_now(),
        "source_ip": match.group("source_ip"),
        "method": match.group("method"),
        "http_method": match.group("method"),
        "uri": match.group("uri"),
        "headers": {},
        "body_length": body_length,
        "status_code": int(match.group("status")),
        "latency_ms": 0,
        "severity": "low",
        "threat_score": 0,
        "source": "mayasec-sensor",
        "sensor_id": HOSTNAME,
        "sensor_hostname": HOSTNAME,
        "sensor_mode": MODE,
        "sensor_version": SENSOR_VERSION,
    }


def follow_file(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as fp:
        fp.seek(0, os.SEEK_END)
        while True:
            line = fp.readline()
            if line:
                yield line
            else:
                time.sleep(0.2)


async def run_logtail_mode() -> None:
    if not LOG_FILE:
        raise RuntimeError("LOG_FILE is required for MODE=logtail")

    path = Path(LOG_FILE)
    if not path.exists():
        raise RuntimeError(f"LOG_FILE does not exist: {LOG_FILE}")

    await register_sensor()
    print(f"[sensor] logtail mode started: {LOG_FILE}")

    buffer: List[Dict] = []
    last_flush = time.monotonic()

    for line in follow_file(path):
        parsed = parse_log_line(line)
        if parsed:
            buffer.append(parsed)

        elapsed = time.monotonic() - last_flush
        if len(buffer) >= 100 or elapsed >= 5:
            batch = buffer[:]
            buffer.clear()
            last_flush = time.monotonic()
            await send_batch(batch)


async def main_async() -> None:
    if not MAYASEC_API_KEY:
        print("[sensor] WARNING: MAYASEC_API_KEY is not set; requests may be rejected")

    if MODE == "proxy":
        if not UPSTREAM_URL:
            raise RuntimeError("UPSTREAM_URL is required for MODE=proxy")
        config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
        return

    if MODE == "logtail":
        await run_logtail_mode()
        return

    raise RuntimeError(f"Unsupported MODE={MODE}. Use 'proxy' or 'logtail'.")


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("[sensor] stopped")
    except Exception as exc:
        print(f"[sensor] fatal: {exc}")
        sys.exit(1)
