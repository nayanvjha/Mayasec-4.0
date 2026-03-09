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

import logging
import os
import time
from typing import Optional

import aiohttp
from aiohttp import web

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

    logger.info(
        "routing_decision",
        extra={
            "ip": client_ip,
            "uri": request.path_qs,
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
