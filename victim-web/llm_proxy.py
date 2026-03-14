"""LLM-powered deceptive response proxy for the honeypot."""

from __future__ import annotations

import logging
import os
import time

import httpx
import asyncio

logger = logging.getLogger(__name__)

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")


async def get_deceptive_response(
    attack_type: str,
    uri: str,
    body: str,
    method: str,
    session_history=None,
    llm_context=None,
) -> str:
    """Call LLM service for a deceptive honeypot response. Returns empty string on failure."""
    try:
        await asyncio.sleep(0)
        t0 = time.monotonic()
        prompt_ctx = {
            "attack_type": attack_type,
            "uri": uri,
            "body": body[:2000],
            "http_verb": method,
            "session_history": session_history or [],
            "interaction_count": (llm_context or {}).get("interaction_count", 0),
            "previous_attack_types": (llm_context or {}).get("previous_attack_types", []),
            "skill_level": (llm_context or {}).get("skill_level", "unknown"),
            "environment_description": (llm_context or {}).get("environment_description", "enterprise_web_suite"),
            "likely_goal": (llm_context or {}).get("likely_goal", "unknown"),
            "attack_phase": (llm_context or {}).get("attack_phase", "recon"),
            "detected_tools": (llm_context or {}).get("detected_tools", []),
        }
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{LLM_SERVICE_URL}/honeypot-reply",
                json=prompt_ctx,
            )
        if resp.status_code == 200:
            try:
                result = resp.json()
            except Exception:
                logger.warning("LLM honeypot reply returned invalid JSON")
                return ""
            latency = (time.monotonic() - t0) * 1000
            logger.info(
                "llm_honeypot_reply latency_ms=%.1f persona=%s",
                latency,
                result.get("persona_type") if isinstance(result, dict) else None,
            )
            if isinstance(result, dict):
                value = result.get("response_body", "")
                return str(value) if value is not None else ""
            return ""
        return ""
    except Exception as exc:
        logger.warning("LLM honeypot reply failed: %s", exc)
        return ""


async def log_capture(
    session_id: str,
    source_ip: str,
    attack_type: str,
    request_payload: str,
    llm_response: str,
    persona_type: str,
    tenant_id: str | None = None,
) -> None:
    """Log honeypot interaction to database via core API (fire-and-forget)."""
    try:
        core_url = os.getenv("CORE_URL", "http://core:5001")
        async with httpx.AsyncClient(timeout=2) as client:
            await client.post(
                f"{core_url}/api/honeypot/capture",
                json={
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "source_ip": source_ip,
                    "attack_type": attack_type,
                    "request_payload": request_payload[:5000],
                    "llm_response": llm_response[:5000],
                    "persona_type": persona_type,
                },
            )
    except Exception:
        pass
