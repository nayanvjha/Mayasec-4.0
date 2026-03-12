"""LLM second-pass WAF client for uncertain-zone payloads."""

from __future__ import annotations

import importlib
import logging
import time
from typing import Any

from config import LLM_WAF_URL, LLM_WAF_TIMEOUT_MS

try:
    aiohttp = importlib.import_module("aiohttp")
except ModuleNotFoundError:
    aiohttp = None

logger = logging.getLogger(__name__)
_session: Any = None


def set_session(session: Any) -> None:
    global _session
    _session = session


async def classify_zero_day(features: dict, waf_score: int) -> dict:
    """Call LLM service to classify uncertain-zone payloads.

    Only called when 40 <= waf_score < 80 (uncertain zone).
    Returns: {"is_attack": bool, "attack_type": str, "adjusted_score": int, "confidence": float}
    Fail-open: returns original waf_score on any error.
    """
    default = {
        "is_attack": False,
        "attack_type": "unknown",
        "adjusted_score": waf_score,
        "confidence": 0.0,
    }
    if aiohttp is None or _session is None or _session.closed:
        return default
    t0 = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=LLM_WAF_TIMEOUT_MS / 1000.0)
    try:
        payload = {
            "http_verb": str(features.get("http_verb", "GET")),
            "uri": str(features.get("uri", "/")),
            "body": str(features.get("body", ""))[:2000],
            "content_type": str(features.get("content_type", "")),
            "user_agent": str(features.get("user_agent", "")),
            "query_params": str(features.get("query_params", "")),
            "waf_score": waf_score,
        }
        async with _session.post(LLM_WAF_URL, json=payload, timeout=timeout) as resp:
            result = await resp.json(content_type=None)
            if not isinstance(result, dict):
                raise ValueError("Invalid LLM WAF response")
            latency_ms = (time.monotonic() - t0) * 1000.0
            logger.info(
                "llm_waf_classify latency_ms=%.1f is_attack=%s type=%s adjusted=%d",
                latency_ms,
                result.get("is_attack"),
                result.get("attack_type"),
                result.get("adjusted_score", waf_score),
            )
            return {
                "is_attack": bool(result.get("is_attack", False)),
                "attack_type": str(result.get("attack_type", "unknown")),
                "adjusted_score": int(result.get("adjusted_score", waf_score)),
                "confidence": float(result.get("confidence", 0.0)),
            }
    except Exception as exc:
        logger.warning(
            "llm_waf_classify failed latency_ms=%.1f reason=%s",
            (time.monotonic() - t0) * 1000.0,
            exc.__class__.__name__,
        )
        return default
