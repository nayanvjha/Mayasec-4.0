"""LLM-powered deceptive response proxy for the honeypot."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")
LLM_TIMEOUT = float(os.getenv("LLM_HONEYPOT_TIMEOUT", "60"))


def get_deceptive_response(
    attack_type: str,
    uri: str,
    body: str,
    method: str,
) -> Optional[str]:
    """Call LLM service for a deceptive honeypot response. Returns None on failure."""
    try:
        t0 = time.monotonic()
        resp = httpx.post(
            f"{LLM_SERVICE_URL}/honeypot-reply",
            json={
                "attack_type": attack_type,
                "uri": uri,
                "body": body[:2000],
                "http_verb": method,
            },
            timeout=LLM_TIMEOUT,
        )
        if resp.status_code == 200:
            result = resp.json()
            latency = (time.monotonic() - t0) * 1000
            logger.info(
                "llm_honeypot_reply latency_ms=%.1f persona=%s",
                latency,
                result.get("persona_type"),
            )
            return result.get("response_body", "")
        return None
    except Exception as exc:
        logger.warning("LLM honeypot reply failed: %s", exc)
        return None


def log_capture(
    session_id: str,
    source_ip: str,
    attack_type: str,
    request_payload: str,
    llm_response: str,
    persona_type: str,
) -> None:
    """Log honeypot interaction to database via core API (fire-and-forget)."""
    try:
        core_url = os.getenv("CORE_URL", "http://core:5001")
        httpx.post(
            f"{core_url}/api/honeypot/capture",
            json={
                "session_id": session_id,
                "source_ip": source_ip,
                "attack_type": attack_type,
                "request_payload": request_payload[:5000],
                "llm_response": llm_response[:5000],
                "persona_type": persona_type,
            },
            timeout=2,
        )
    except Exception:
        pass
