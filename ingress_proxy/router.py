"""
MAYASEC Ingress Proxy — Transparent Router
==========================================

Routes HTTP requests to either the production backend or the deception
honeypot based on an ML risk score supplied by the scoring pipeline.

Routing thresholds
------------------
  score < SCORE_THRESHOLD  →  PRODUCTION_BACKEND
  score ≥ SCORE_THRESHOLD  →  HONEYPOT_BACKEND

Design invariants
-----------------
* Transparent proxy — no HTTP redirects, no response modification.
* Fully async — all I/O uses aiohttp; zero blocking calls.
* Shared ClientSession — injected at startup; never created per-request.
* Fail-open — backend errors return 502, never crash the proxy.
* Hop-by-hop headers are stripped in both directions (RFC 7230 §6.1).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import httpx
from aiohttp import web

from traffic_logger import traffic_logger


async def emit_event_to_api(event_payload: dict):
    api_url = os.getenv("API_EMIT_URL", "http://api:5000/api/v1/emit-event")
    admin_token = os.getenv("ADMIN_TOKEN", "mayasec_internal_token")
    api_key = os.getenv("MAYASEC_API_KEY")

    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                api_url,
                json=event_payload,
                headers=headers,
            )
    except Exception:
        pass  # Never let emit failure block the proxy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PRODUCTION_BACKEND: str = os.environ.get(
    "PRODUCTION_BACKEND", "http://victim-web:8080"
)
HONEYPOT_BACKEND: str = os.environ.get(
    "HONEYPOT_BACKEND", "http://honeypot:5003"
)
SCORE_THRESHOLD: int = int(os.environ.get("SCORE_THRESHOLD", "80"))

# Hop-by-hop headers that must not be forwarded (RFC 7230 §6.1).
_HOP_BY_HOP: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        # Additional aiohttp / HTTP/2 internal headers
        "host",           # rewritten by aiohttp for each upstream
        "content-length", # recomputed correctly by aiohttp
    }
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("router")


# ---------------------------------------------------------------------------
# Module-level shared session (set by proxy_server at startup)
# ---------------------------------------------------------------------------

_session: Optional[aiohttp.ClientSession] = None


def set_session(session: aiohttp.ClientSession) -> None:
    """Inject the shared ClientSession created by proxy_server.py at startup."""
    global _session
    _session = session


def _get_session() -> aiohttp.ClientSession:
    if _session is None or _session.closed:
        raise RuntimeError(
            "Router ClientSession is not initialised. "
            "Call router.set_session() during proxy startup."
        )
    return _session


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

def _filter_headers(headers: "aiohttp.CIMultiDictProxy[str]") -> dict[str, str]:
    """
    Return a plain dict of headers with all hop-by-hop entries removed.
    Safe for both request-forward and response-copy directions.
    """
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP
    }


# ---------------------------------------------------------------------------
# Core routing function
# ---------------------------------------------------------------------------

async def route_request(
    request: web.Request,
    score: int,
    attack_type: str,
) -> web.Response:
    """
    Transparently forward *request* to the appropriate backend and return
    the backend's response to the caller unchanged.

    Parameters
    ----------
    request:     Incoming aiohttp.web.Request from the client.
    score:       Integer risk score 0–100 from the ML scoring pipeline.
    attack_type: Human-readable label produced by the ML classifier
                 (e.g. ``"clean"``, ``"sqli"``, ``"xss"``, ``"behavioral_malicious"``).

    Returns
    -------
    aiohttp.web.Response — the upstream response, forwarded transparently.
    """
    t_start = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Routing decision
    # ------------------------------------------------------------------
    if score >= SCORE_THRESHOLD:
        backend_base = HONEYPOT_BACKEND
        destination_label = "honeypot"
    else:
        backend_base = PRODUCTION_BACKEND
        destination_label = "production"

    # Build full target URL preserving path and query string
    target_url = backend_base.rstrip("/") + request.path_qs

    # Source IP — prefer X-Forwarded-For set by an upstream LB when present
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "unknown"
    )
    request_uri = request.path_qs
    target_backend = destination_label

    asyncio.create_task(emit_event_to_api({
        "type": "event_ingested",
        "data": {
            "event_type": attack_type,
            "source_ip": client_ip,
            "threat_score": float(score),
            "destination": target_backend,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uri": request_uri,
            "severity": (
                "critical" if score >= 90 else
                "high"     if score >= 75 else
                "medium"   if score >= 50 else
                "low"
            )
        }
    }))

    logger.info(
        "routing_decision",
        extra={
            "ip": client_ip,
            "uri": request_uri,
            "score": score,
            "attack_type": attack_type,
            "destination_backend": destination_label,
            "target_url": target_url,
        },
    )

    # ------------------------------------------------------------------
    # 2. Forward the request
    # ------------------------------------------------------------------
    try:
        # Read body once — aiohttp does not allow re-reading a stream
        body: bytes = await request.read()

        forward_headers = _filter_headers(request.headers)
        # Explicitly set Host to the upstream so the backend sees correct Host
        forward_headers["Host"] = _host_from_url(backend_base)
        if destination_label == "honeypot":
            forward_headers["X-MAYASEC-ATTACK-TYPE"] = str(attack_type)
            forward_headers["X-MAYASEC-SCORE"] = str(score)
            forward_headers["X-MAYASEC-SESSION"] = str(uuid.uuid4())

        session = _get_session()

        async with session.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            data=body if body else None,
            allow_redirects=False,   # transparent proxy — never follow redirects
            compress=False,          # do not re-compress; pass payload as-is
        ) as upstream_resp:

            # --------------------------------------------------------------
            # 3. Read and return the upstream response
            # --------------------------------------------------------------
            response_body: bytes = await upstream_resp.read()
            response_headers = _filter_headers(upstream_resp.headers)

            elapsed_ms = (time.monotonic() - t_start) * 1000.0

            _schedule_traffic_log(request=request, status=upstream_resp.status, body=body)

            logger.debug(
                "upstream_response",
                extra={
                    "status": upstream_resp.status,
                    "destination": destination_label,
                    "latency_ms": round(elapsed_ms, 2),
                    "response_bytes": len(response_body),
                },
            )

            return web.Response(
                status=upstream_resp.status,
                headers=response_headers,
                body=response_body,
            )

    # ------------------------------------------------------------------
    # 4. Error handling — network / connection failures
    # ------------------------------------------------------------------
    except aiohttp.ClientConnectorError as exc:
        _schedule_traffic_log(request=request, status=502, body=body if 'body' in locals() else b"")
        logger.error(
            "backend_connection_error",
            extra={
                "destination": destination_label,
                "target_url": target_url,
                "error": str(exc),
            },
        )
        return web.Response(
            status=502,
            content_type="application/json",
            text=(
                f'{{"error":"bad_gateway",'
                f'"backend":"{destination_label}",'
                f'"detail":"Connection refused or host unreachable"}}'
            ),
        )

    except aiohttp.ClientResponseError as exc:
        _schedule_traffic_log(request=request, status=502, body=body if 'body' in locals() else b"")
        logger.error(
            "backend_response_error",
            extra={
                "destination": destination_label,
                "target_url": target_url,
                "status": exc.status,
                "error": exc.message,
            },
        )
        return web.Response(
            status=502,
            content_type="application/json",
            text=(
                f'{{"error":"bad_gateway",'
                f'"backend":"{destination_label}",'
                f'"detail":"Upstream returned an invalid response"}}'
            ),
        )

    except aiohttp.ServerTimeoutError as exc:
        _schedule_traffic_log(request=request, status=502, body=body if 'body' in locals() else b"")
        logger.error(
            "backend_timeout",
            extra={
                "destination": destination_label,
                "target_url": target_url,
                "error": str(exc),
            },
        )
        return web.Response(
            status=502,
            content_type="application/json",
            text=(
                f'{{"error":"bad_gateway",'
                f'"backend":"{destination_label}",'
                f'"detail":"Upstream connection timed out"}}'
            ),
        )

    except Exception as exc:  # pragma: no cover — catch-all safety net
        _schedule_traffic_log(request=request, status=502, body=body if 'body' in locals() else b"")
        logger.exception(
            "unexpected_routing_error",
            extra={
                "destination": destination_label,
                "target_url": target_url,
                "error": str(exc),
            },
        )
        return web.Response(
            status=502,
            content_type="application/json",
            text=(
                f'{{"error":"bad_gateway",'
                f'"backend":"{destination_label}",'
                f'"detail":"Unexpected proxy error"}}'
            ),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _host_from_url(url: str) -> str:
    """
    Extract ``host[:port]`` from a base URL string.

    Examples
    --------
    >>> _host_from_url("http://victim-web:8080")
    'victim-web:8080'
    >>> _host_from_url("https://production.internal")
    'production.internal'
    """
    # Strip scheme
    without_scheme = url.split("://", 1)[-1]
    # Strip any trailing path
    return without_scheme.split("/")[0]


def _schedule_traffic_log(request: web.Request, status: int, body: bytes) -> None:
    """Queue raw traffic record asynchronously; never block request handling."""
    xff = request.headers.get("X-Forwarded-For", "")
    src_ip = xff.split(",")[0].strip() if xff else (request.remote or "unknown")

    content_length_header = request.headers.get("Content-Length")
    try:
        content_length = int(content_length_header) if content_length_header else len(body or b"")
    except Exception:
        content_length = len(body or b"")

    record = {
        "src_ip": src_ip,
        "method": request.method,
        "path": request.path,
        "query_string": request.query_string or "",
        "status": int(status),
        "user_agent": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
        "content_length": max(0, content_length),
        "request_body": (body or b"").decode("utf-8", errors="ignore"),
    }

    try:
        asyncio.create_task(traffic_logger.log(record))
    except Exception:
        # Must never impact routing path.
        pass
