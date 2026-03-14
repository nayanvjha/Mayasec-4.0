"""Main aiohttp ingress proxy server orchestrating extraction, scoring, and routing."""

from __future__ import annotations

import asyncio
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
_traffic_logger_mod = importlib.import_module("traffic_logger")
_rate_limiter = _load_local_module("rate_limiter")
_redis_client = _load_local_module("redis_client")
_config = _load_local_module("config")
_llm_waf_client = _load_local_module("llm_waf_client")

_WAF_FALLBACK = {"score": 0, "attack_type": "unknown"}
_BEHAVIORAL_FALLBACK = {
    "intent": "Benign",
    "anomaly_score": 0.0,
    "deception_trigger": False,
}
_SCORE_THRESHOLD = int(getattr(_config, "SCORE_THRESHOLD", 80))


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
    rate_check_fn = getattr(_rate_limiter, "check_rate_limit_async", None)
    if callable(rate_check_fn):
        is_limited = await rate_check_fn(client_ip)
    else:
        is_limited = _rate_limiter.check_rate_limit(client_ip)

    if is_limited:
        logger.warning("rate_limited ip=%s", client_ip)
        return _web().Response(status=429, text="Too Many Requests")

    try:
        features = await _telemetry_mirror.extract_features(request)

        # Ensure ML payload always includes URI/body for rule-based pre-ML detection.
        if not isinstance(features, dict):
            features = {}
        features.setdefault("uri", request.path_qs)
        raw_body = getattr(request, "_read_bytes", b"")
        if isinstance(raw_body, (bytes, bytearray)):
            features.setdefault("body", bytes(raw_body).decode("utf-8", errors="ignore"))
        else:
            features.setdefault("body", "")

        behavioral_fn = getattr(_ml_client, "behavioral_score_request", None)
        behavioral_coro = (
            behavioral_fn(features)
            if callable(behavioral_fn)
            else asyncio.sleep(0, result=dict(_BEHAVIORAL_FALLBACK))
        )

        waf_result, behavioral_result = await asyncio.gather(
            _ml_client.score_request(features),
            behavioral_coro,
            return_exceptions=True,
        )

        if isinstance(waf_result, Exception) or not isinstance(waf_result, dict):
            waf_result = dict(_WAF_FALLBACK)
        if isinstance(behavioral_result, Exception) or not isinstance(behavioral_result, dict):
            behavioral_result = dict(_BEHAVIORAL_FALLBACK)

        waf_score = int(waf_result.get("score", 0))
        attack_type = str(waf_result.get("attack_type", "unknown"))
        # Phase 4B: LLM second-pass for uncertain-zone WAF scores
        uncertain_low = int(getattr(_config, "LLM_WAF_UNCERTAIN_LOW", 40))
        uncertain_high = int(getattr(_config, "LLM_WAF_UNCERTAIN_HIGH", 80))
        if uncertain_low <= waf_score < uncertain_high:
            try:
                llm_result = await _llm_waf_client.classify_zero_day(features, waf_score)
                llm_adjusted = int(llm_result.get("adjusted_score", waf_score))
                waf_score = max(waf_score, llm_adjusted)
                if llm_result.get("is_attack"):
                    attack_type = str(llm_result.get("attack_type", attack_type))
            except Exception:
                pass  # fail-open: keep original waf_score
        deception_trigger = bool(behavioral_result.get("deception_trigger", False))

        route_score = waf_score if not deception_trigger else max(waf_score, _SCORE_THRESHOLD)
        routing_decision = "honeypot" if (waf_score >= _SCORE_THRESHOLD or deception_trigger) else "production"

        response = await _router.route_request(request, route_score, attack_type)

        if routing_decision == "honeypot":
            # Fire-and-forget: send confirmed attack data to core for retraining
            feedback_fn = getattr(_ml_client, "send_behavioral_feedback", None)
            if callable(feedback_fn):
                asyncio.ensure_future(feedback_fn(features, intent="Malicious", confirmed_by="honeypot"))

        logger.info(
            "proxy_request %s",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "ip": client_ip,
                "uri": request.path_qs,
                "score": waf_score,
                "routing_decision": routing_decision,
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
    _llm_waf_client.set_session(session)
    _router.set_session(session)

    traffic_logger = getattr(_traffic_logger_mod, "traffic_logger", None)
    if traffic_logger is not None:
        app["traffic_logger"] = traffic_logger
        app["traffic_logger_task"] = asyncio.create_task(traffic_logger.flush_worker())

    try:
        redis_init_fn = getattr(_redis_client, "get_pool", None)
        if callable(redis_init_fn):
            await redis_init_fn()
    except Exception as exc:
        logger.warning("Redis init skipped: %s", exc)


async def _on_cleanup(app) -> None:
    traffic_logger = app.get("traffic_logger")
    traffic_logger_task = app.get("traffic_logger_task")

    if traffic_logger is not None:
        try:
            await traffic_logger.stop()
        except Exception:
            logger.exception("traffic_logger_stop_failed")

    if traffic_logger_task is not None:
        try:
            await asyncio.wait_for(traffic_logger_task, timeout=5)
        except asyncio.TimeoutError:
            traffic_logger_task.cancel()
        except Exception:
            logger.exception("traffic_logger_task_shutdown_failed")

    try:
        redis_close_fn = getattr(_redis_client, "close_pool", None)
        if callable(redis_close_fn):
            await redis_close_fn()
    except Exception:
        pass

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
