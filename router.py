"""Transparent async routing engine for ingress proxy traffic."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from typing import Any
from urllib.parse import urlparse

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)

PRODUCTION_BACKEND = os.environ.get("PRODUCTION_BACKEND", "http://production-web:3000")
HONEYPOT_BACKEND = os.environ.get("HONEYPOT_BACKEND", "http://victim-web:80")
_SCORE_THRESHOLD = 80

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

_session: Any = None
_session_lock = asyncio.Lock()


def _safe_backend_url(raw: str, fallback: str) -> str:
    """Return validated backend URL or a safe fallback."""
    try:
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return raw.rstrip("/")
    except Exception:
        pass
    return fallback.rstrip("/")


def _filtered_headers(headers: Any) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }


async def _get_session() -> Any:
    global _session

    if aiohttp is None:
        raise RuntimeError("aiohttp is required for request forwarding")

    if _session is not None and not _session.closed:
        return _session

    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=512, enable_cleanup_closed=True)
            )
        return _session


async def route_request(request, score: int, attack_type: str) -> Any:
    """Route to production or honeypot and transparently proxy response."""

    if aiohttp is None:
        return {
            "status": 502,
            "text": "Bad Gateway",
        }

    web = aiohttp.web

    production_backend = _safe_backend_url(
        PRODUCTION_BACKEND,
        "http://production-web:3000",
    )
    honeypot_backend = _safe_backend_url(
        HONEYPOT_BACKEND,
        "http://victim-web:80",
    )

    if score >= _SCORE_THRESHOLD:
        selected_base = honeypot_backend
        destination_backend = "honeypot"
    else:
        selected_base = production_backend
        destination_backend = "production"

    target_url = f"{selected_base}{request.path_qs}"

    client_ip = request.remote or "unknown"
    logger.info(
        "route_decision %s",
        {
            "ip": client_ip,
            "uri": request.path_qs,
            "score": int(score),
            "attack_type": str(attack_type),
            "destination_backend": destination_backend,
        },
    )

    try:
        body = await request.read()
        outbound_headers = _filtered_headers(request.headers)

        session = await _get_session()
        async with session.request(
            method=request.method,
            url=target_url,
            headers=outbound_headers,
            data=body if body else None,
            allow_redirects=False,
        ) as upstream_response:
            response_body = await upstream_response.read()
            response_headers = _filtered_headers(upstream_response.headers)

            return web.Response(
                status=upstream_response.status,
                headers=response_headers,
                body=response_body,
            )

    except (aiohttp.ClientConnectionError, aiohttp.ClientError) as exc:
        logger.error(
            "route_forward_failed %s",
            {
                "target_url": target_url,
                "backend": destination_backend,
                "error": str(exc),
            },
        )
        return web.Response(status=502, text="Bad Gateway")

    except Exception as exc:
        logger.exception(
            "route_unexpected_error %s",
            {
                "target_url": target_url,
                "backend": destination_backend,
                "error": str(exc),
            },
        )
        return web.Response(status=502, text="Bad Gateway")
