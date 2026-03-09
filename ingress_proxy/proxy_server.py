"""Main aiohttp ingress proxy server orchestrating extraction, scoring, and routing."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)


def _load_local_module(module_name: str) -> Any:
    module_path = Path(__file__).with_name(f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(f"ingress_proxy_{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ml_client = _load_local_module("ml_client")
_telemetry_mirror = _load_local_module("telemetry_mirror")
_router = _load_local_module("router")
_rate_limiter = _load_local_module("rate_limiter")


def _web() -> Any:
    return importlib.import_module("aiohttp.web")


async def handle_health(_request) -> Any:
    """Return service health for Docker/Kubernetes style probes."""
    web = _web()
    return web.json_response({"status": "ok"}, status=200)


async def handle_request(request) -> Any:
    """Process one request through feature extraction, ML scoring, and routing."""
    client_ip = request.remote or "unknown"

    # Gate 1 — Rate limit before any expensive downstream processing
    if _rate_limiter.check_rate_limit(client_ip):
        logger.warning("rate_limited ip=%s", client_ip)
        return _web().Response(status=429, text="Too Many Requests")

    try:
        features = await _telemetry_mirror.extract_features(request)
        scoring = await _ml_client.score_request(features)
        score = int(scoring.get("score", 0))
        attack_type = str(scoring.get("attack_type", "unknown"))

        response = await _router.route_request(request, score, attack_type)

        logger.info(
            "proxy_request %s",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "ip": client_ip,
                "uri": request.path_qs,
                "score": score,
                "routing_decision": "honeypot" if score >= 80 else "production",
            },
        )
        return response
    except Exception:
        logger.exception("proxy_internal_error")
        return _web().Response(status=500, text="Internal Server Error")


async def _on_startup(app) -> None:
    if aiohttp is None:
        raise RuntimeError("aiohttp is required to run proxy_server")
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            limit=512,           # total concurrent connections — prevents fd exhaustion
            limit_per_host=64,   # per upstream backend cap
            ttl_dns_cache=300,   # cache DNS 5 min — avoids per-request DNS
        )
    )
    app["session"] = session
    _ml_client.set_session(session)
    _router.set_session(session)


async def _on_cleanup(app) -> None:
    session = app.get("session")
    if session and not session.closed:
        await session.close()


def create_app() -> Any:
    web = _web()
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_route("*", "/{path:.*}", handle_request)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def main() -> None:
    # Activate uvloop for ~2x faster event loop throughput (installed but never called before)
    try:
        uvloop = importlib.import_module("uvloop")
        uvloop.install()
        logger.info("uvloop event loop active")
    except ImportError:
        logger.info("uvloop not available — using default asyncio event loop")

    web = _web()
    web.run_app(create_app(), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
