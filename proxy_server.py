"""Main async ingress proxy server orchestration layer."""

from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

from ml_client import score_request
from telemetry_mirror import extract_features
import ml_client
import router

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 8080
_DEFAULT_SCORE_THRESHOLD = 80


def _web() -> Any:
    if aiohttp is None:
        raise RuntimeError("aiohttp is required")
    return importlib.import_module("aiohttp.web")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _routing_decision(score: int) -> str:
    threshold_raw = os.environ.get("SCORE_THRESHOLD", str(_DEFAULT_SCORE_THRESHOLD))
    try:
        threshold = int(threshold_raw)
    except (TypeError, ValueError):
        threshold = _DEFAULT_SCORE_THRESHOLD
    return "honeypot" if score >= threshold else "production"


def _client_ip(request: Any) -> str:
    try:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip() or (request.remote or "unknown")
        return request.remote or "unknown"
    except Exception:
        return "unknown"


def _inject_shared_session(session: Any) -> None:
    """Bind one shared session into dependent modules."""
    setattr(ml_client, "_session", session)
    setattr(router, "_session", session)


async def handle_request(request) -> Any:
    """Process one ingress request: features -> ML score -> route."""
    web = _web()

    try:
        feature_vector = await extract_features(request)
        scoring_result = await score_request(feature_vector)

        score_raw = scoring_result.get("score", 0)
        attack_type_raw = scoring_result.get("attack_type", "unknown")

        try:
            score = int(score_raw)
        except (TypeError, ValueError):
            score = 0

        attack_type = str(attack_type_raw)

        response = await router.route_request(request, score, attack_type)

        logger.info(
            "proxy_request %s",
            {
                "timestamp": _utc_timestamp(),
                "ip": _client_ip(request),
                "uri": request.path_qs,
                "score": score,
                "routing_decision": _routing_decision(score),
            },
        )

        return response

    except Exception as exc:
        logger.exception(
            "proxy_internal_error %s",
            {
                "timestamp": _utc_timestamp(),
                "ip": _client_ip(request),
                "uri": getattr(request, "path_qs", "/"),
                "error": str(exc),
            },
        )
        return web.Response(status=500, text="Internal Server Error")


async def _on_startup(app) -> None:
    if aiohttp is None:
        raise RuntimeError("aiohttp is required to run proxy_server")

    connector = aiohttp.TCPConnector(
        limit=0,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )
    session = aiohttp.ClientSession(connector=connector)

    app["shared_session"] = session
    _inject_shared_session(session)


async def _on_cleanup(app) -> None:
    session = app.get("shared_session")
    if session is not None and not session.closed:
        await session.close()
    setattr(ml_client, "_session", None)
    setattr(router, "_session", None)


def create_app() -> Any:
    if aiohttp is None:
        raise RuntimeError("aiohttp is required to create proxy application")

    web = _web()

    app = web.Application(client_max_size=10 * 1024**2)
    app.router.add_route("*", "/{path:.*}", handle_request)

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)

    return app


def main() -> None:
    if aiohttp is None:
        raise RuntimeError("aiohttp is required to start proxy server")

    web = _web()

    port_raw = os.environ.get("PORT", str(_DEFAULT_PORT))
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = _DEFAULT_PORT

    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
