"""Asynchronous ML scoring client for ingress proxy feature vectors."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import importlib
from typing import Any, Dict
from urllib.parse import urlparse

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)

_DEFAULT_SCORE_RESPONSE: Dict[str, Any] = {"score": 0, "attack_type": "unknown"}
_DEFAULT_ML_SCORE_URL = "http://mayasec-core:5001/api/ml/score"
_DEFAULT_ML_TIMEOUT_MS = 50

_session: Any = None
_session_lock = asyncio.Lock()


def _get_ml_score_url() -> str:
    raw = os.environ.get("ML_SCORE_URL", _DEFAULT_ML_SCORE_URL).strip() or _DEFAULT_ML_SCORE_URL

    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("invalid URL")
        # If only base host is provided, append the required scoring endpoint.
        if not parsed.path or parsed.path == "/":
            return raw.rstrip("/") + "/api/ml/score"
        return raw
    except Exception:
        logger.warning("Invalid ML_SCORE_URL configured, using safe default")
        return _DEFAULT_ML_SCORE_URL


def _get_timeout_seconds() -> float:
    raw = os.environ.get("ML_TIMEOUT_MS", str(_DEFAULT_ML_TIMEOUT_MS))
    try:
        timeout_ms = int(raw)
        if timeout_ms <= 0:
            raise ValueError("timeout must be positive")
        return timeout_ms / 1000.0
    except Exception:
        logger.warning("Invalid ML_TIMEOUT_MS configured, using safe default")
        return _DEFAULT_ML_TIMEOUT_MS / 1000.0


async def _get_session() -> Any:
    global _session
    if aiohttp is None:
        raise RuntimeError("aiohttp is required for ML scoring")

    if _session is not None and not _session.closed:
        return _session

    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=256, enable_cleanup_closed=True)
            )
        return _session


async def score_request(feature_vector: dict) -> dict:
    """Score a request feature vector via ML service.

    Returns a fail-open default response on timeout, connectivity issues,
    malformed responses, or JSON parsing errors.
    """
    start = time.monotonic()
    ml_url = _get_ml_score_url()
    if aiohttp is None:
        latency_ms = (time.monotonic() - start) * 1000.0
        logger.warning(
            "ML scoring unavailable (aiohttp missing) latency_ms=%.3f; returning fail-open default score=%d",
            latency_ms,
            _DEFAULT_SCORE_RESPONSE["score"],
        )
        return dict(_DEFAULT_SCORE_RESPONSE)

    timeout = aiohttp.ClientTimeout(total=_get_timeout_seconds())

    try:
        session = await _get_session()
        async with session.post(ml_url, json=feature_vector, timeout=timeout) as response:
            payload = await response.json(content_type=None)

            if not isinstance(payload, dict):
                raise ValueError("ML response must be an object")

            score_raw = payload.get("score")
            attack_type_raw = payload.get("attack_type")

            if score_raw is None or attack_type_raw is None:
                raise ValueError("Missing required ML response fields")

            score = int(score_raw)
            attack_type = str(attack_type_raw)

            latency_ms = (time.monotonic() - start) * 1000.0
            logger.info(
                "ML scoring success latency_ms=%.3f score=%d",
                latency_ms,
                score,
            )

            return {"score": score, "attack_type": attack_type}

    except (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        ValueError,
        TypeError,
    ) as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        logger.warning(
            "ML scoring failed latency_ms=%.3f reason=%s; returning fail-open default score=%d",
            latency_ms,
            exc.__class__.__name__,
            _DEFAULT_SCORE_RESPONSE["score"],
        )
        return dict(_DEFAULT_SCORE_RESPONSE)

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        logger.exception(
            "Unexpected ML scoring error latency_ms=%.3f reason=%s; returning fail-open default score=%d",
            latency_ms,
            exc.__class__.__name__,
            _DEFAULT_SCORE_RESPONSE["score"],
        )
        return dict(_DEFAULT_SCORE_RESPONSE)
