"""Dedicated ML scoring client for feature-vector communication with the scoring service."""

from __future__ import annotations

import importlib
import logging
import time
from typing import Any

from config import ML_SCORE_URL, ML_TIMEOUT_MS, BEHAVIORAL_SCORE_URL, BEHAVIORAL_TIMEOUT_MS

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)

_DEFAULT = {"score": 0, "attack_type": "unknown"}
_session: Any = None


def set_session(session: Any) -> None:
    """Inject a shared aiohttp ClientSession from proxy startup."""
    global _session
    _session = session


async def _get_session() -> Any:
    """Return the injected shared session. Raise if called before startup."""
    if _session is None or _session.closed:
        raise RuntimeError(
            "ml_client session not initialised. "
            "Ensure set_session() is called during proxy startup before serving requests."
        )
    return _session


async def score_request(feature_vector: dict) -> dict:
    """Send features to ML service and return normalized score response."""
    if aiohttp is None:
        return dict(_DEFAULT)

    t0 = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=ML_TIMEOUT_MS / 1000.0)

    try:
        session = await _get_session()
        async with session.post(ML_SCORE_URL, json=feature_vector, timeout=timeout) as resp:
            payload = await resp.json(content_type=None)
            if not isinstance(payload, dict):
                raise ValueError("invalid ML payload")
            score = int(payload.get("score", 0))
            attack_type = str(payload.get("attack_type", "unknown"))
            logger.info("ml_scoring success latency_ms=%.3f score=%d", (time.monotonic() - t0) * 1000.0, score)
            return {"score": score, "attack_type": attack_type}
    except Exception as exc:
        logger.warning("ml_scoring failed latency_ms=%.3f reason=%s", (time.monotonic() - t0) * 1000.0, exc.__class__.__name__)
        return dict(_DEFAULT)


_BEHAVIORAL_DEFAULT = {"intent": "Benign", "anomaly_score": 0.0, "deception_trigger": False}


async def behavioral_score_request(feature_vector: dict) -> dict:
    """Send features to mayasec-core behavioral endpoint and return intent result.

    Always fail-open: returns Benign on any network/timeout error so the
    ingress proxy is never blocked by core unavailability.
    """
    if aiohttp is None:
        return dict(_BEHAVIORAL_DEFAULT)

    t0 = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=BEHAVIORAL_TIMEOUT_MS / 1000.0)

    try:
        session = await _get_session()
        async with session.post(
            BEHAVIORAL_SCORE_URL,
            json={"features": feature_vector},
            timeout=timeout,
        ) as resp:
            payload = await resp.json(content_type=None)
            if not isinstance(payload, dict):
                raise ValueError("invalid behavioral payload")
            logger.info(
                "behavioral_scoring success latency_ms=%.3f intent=%s deception=%s",
                (time.monotonic() - t0) * 1000.0,
                payload.get("intent", "?"),
                payload.get("deception_trigger", False),
            )
            return {
                "intent": str(payload.get("intent", "Benign")),
                "anomaly_score": float(payload.get("anomaly_score", 0.0)),
                "deception_trigger": bool(payload.get("deception_trigger", False)),
            }
    except Exception as exc:
        logger.warning(
            "behavioral_scoring failed latency_ms=%.3f reason=%s",
            (time.monotonic() - t0) * 1000.0,
            exc.__class__.__name__,
        )
        return dict(_BEHAVIORAL_DEFAULT)
