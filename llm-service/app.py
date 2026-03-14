"""MAYASEC LLM Service — Threat narratives, zero-day classification, TTP tagging, honeypot replies."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional, Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from jinja2 import Template
from pydantic import BaseModel, Field

import prompts
import ttp_classifier

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("llm_service")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

_http_client: Optional[httpx.AsyncClient] = None
_ollama_available: bool = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _http_client, _ollama_available

    _http_client = httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT))
    client = _http_client
    if client is None:
        _ollama_available = False
        yield
        return

    try:
        resp = await client.get(f"{OLLAMA_URL}/api/tags")
        if resp.status_code == 200:
            _ollama_available = True
            models = [m["name"] for m in resp.json().get("models", [])]
            logger.info("Ollama connected. Available models: %s", models)
            if OLLAMA_MODEL not in models and f"{OLLAMA_MODEL}:latest" not in models:
                logger.info("Pulling model %s...", OLLAMA_MODEL)
                await client.post(
                    f"{OLLAMA_URL}/api/pull",
                    json={"name": OLLAMA_MODEL},
                    timeout=httpx.Timeout(300),
                )
    except Exception as exc:
        logger.warning("Ollama not available: %s", exc)
        _ollama_available = False

    yield

    if _http_client:
        await _http_client.aclose()


app = FastAPI(title="MAYASEC LLM Service", version="4.0.0", lifespan=lifespan)


def _render_template(template_str: str, context: dict) -> str:
    return Template(template_str).render(**context)


async def _call_ollama(system: str, user: str) -> Optional[str]:
    client = _http_client
    if not _ollama_available or not client:
        return None
    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "system": system,
                "prompt": user,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=httpx.Timeout(min(max(LLM_TIMEOUT, 12), 20)),
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
    except Exception as exc:
        logger.warning("Ollama call failed: %s", exc)
    return None


async def _call_openai(system: str, user: str) -> Optional[str]:
    client = _http_client
    if not OPENAI_API_KEY or not client:
        return None
    try:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("OpenAI call failed: %s", exc)
    return None


async def _generate(system: str, user: str) -> str:
    """Try Ollama first, fall back to OpenAI, then return empty."""
    result = await _call_ollama(system, user)
    if result:
        return result

    result = await _call_openai(system, user)
    if result:
        return result

    return ""


def _fallback_honeypot_response(ctx: dict) -> str:
    """Deterministic deceptive fallback when LLM providers are unavailable."""
    uri = str(ctx.get("uri") or "/")
    attack_phase = str(ctx.get("attack_phase") or "recon")
    environment = str(ctx.get("environment_description") or "enterprise_web_suite")
    interaction_count = int(ctx.get("interaction_count") or 0)

    if uri.startswith("/api"):
        return json.dumps(
            {
                "status": "ok",
                "service": environment,
                "phase": attack_phase,
                "request_id": f"rq-{interaction_count:04d}",
                "data": {
                    "users": 1248,
                    "tokens": 87,
                    "region": "us-east-1",
                },
            }
        )

    if "admin" in uri or "internal" in uri:
        return (
            "<html><body><h1>Admin Console</h1>"
            f"<p>Environment: {environment}</p>"
            f"<p>Session phase: {attack_phase}</p>"
            "<ul><li>users</li><li>orders</li><li>api_tokens</li></ul>"
            "</body></html>"
        )

    return (
        "<html><body><h1>Enterprise Portal</h1>"
        f"<p>Environment: {environment}</p>"
        f"<p>Interaction: {interaction_count}</p>"
        "</body></html>"
    )


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
    return {}


class EventInput(BaseModel):
    event_type: str = ""
    source_ip: str = ""
    uri: str = "/"
    http_verb: str = "GET"
    score: int = 0
    attack_type: str = "normal"
    intent: str = "Benign"
    anomaly_score: float = 0.0
    graph_threat: bool = False
    deception_trigger: bool = False
    timestamp: str = ""
    session_request_count: int = 0
    uri_path_diversity: int = 0
    ua_change_detected: bool = False
    request_rate_60s: int = 0
    body: str = ""
    content_type: str = ""
    user_agent: str = ""
    query_params: str = ""


@app.post("/explain")
async def explain_event(event: EventInput):
    t0 = time.monotonic()
    ctx = event.model_dump()
    user_prompt = _render_template(prompts.THREAT_NARRATIVE_USER, ctx)
    narrative = await _generate(prompts.THREAT_NARRATIVE_SYSTEM, user_prompt)
    latency = round((time.monotonic() - t0) * 1000, 1)

    if not narrative:
        return JSONResponse(
            content={
                "narrative": "LLM unavailable. Event details: "
                f"{event.attack_type} from {event.source_ip} targeting {event.uri} "
                f"with score {event.score}/100.",
                "confidence": 0.0,
                "mitre_ttps": [],
                "latency_ms": latency,
            }
        )

    return JSONResponse(
        content={
            "narrative": narrative,
            "confidence": 0.85,
            "mitre_ttps": [],
            "latency_ms": latency,
        }
    )


class ZeroDayInput(BaseModel):
    http_verb: str = "GET"
    uri: str = "/"
    body: str = ""
    content_type: str = ""
    user_agent: str = ""
    query_params: str = ""
    waf_score: int = 0


@app.post("/classify-zero-day")
async def classify_zero_day(req: ZeroDayInput):
    t0 = time.monotonic()
    ctx = req.model_dump()
    ctx["body"] = ctx["body"][:2000]
    user_prompt = _render_template(prompts.ZERO_DAY_USER, ctx)
    raw = await _generate(prompts.ZERO_DAY_SYSTEM, user_prompt)
    parsed = _parse_json_response(raw)
    latency = round((time.monotonic() - t0) * 1000, 1)

    is_attack = bool(parsed.get("is_attack", False))
    attack_type = str(parsed.get("attack_type", "unknown"))
    confidence = float(parsed.get("confidence", 0.0))
    adjusted_score = 90 if (is_attack and confidence > 0.7) else req.waf_score

    return JSONResponse(
        content={
            "is_attack": is_attack,
            "attack_type": attack_type,
            "confidence": confidence,
            "adjusted_score": adjusted_score,
            "reasoning": str(parsed.get("reasoning", "")),
            "latency_ms": latency,
        }
    )


class TTPInput(BaseModel):
    event_type: str = ""
    attack_type: str = ""
    source_ip: str = ""
    uri: str = "/"
    score: int = 0
    intent: str = "Benign"
    graph_threat: bool = False
    uri_path_diversity: int = 0
    request_rate_60s: int = 0


@app.post("/classify-ttp")
async def classify_ttp(req: TTPInput):
    t0 = time.monotonic()
    ctx = req.model_dump()

    # Rule-based first pass
    rule_matches = ttp_classifier.classify_rules(ctx)
    if rule_matches:
        latency = round((time.monotonic() - t0) * 1000, 1)
        return JSONResponse(content={"ttps": rule_matches, "source": "rules", "latency_ms": latency})

    # LLM fallback for ambiguous cases
    user_prompt = _render_template(prompts.TTP_CLASSIFY_USER, ctx)
    raw = await _generate(prompts.TTP_CLASSIFY_SYSTEM, user_prompt)
    parsed = _parse_json_response(raw)
    latency = round((time.monotonic() - t0) * 1000, 1)

    ttps = parsed.get("ttps", [])
    if not isinstance(ttps, list):
        ttps = []

    return JSONResponse(content={"ttps": ttps, "source": "llm", "latency_ms": latency})


class HoneypotInput(BaseModel):
    attack_type: str = "unknown"
    uri: str = "/"
    body: str = ""
    http_verb: str = "GET"
    interaction_count: int = 0
    previous_attack_types: list[str] = Field(default_factory=list)
    skill_level: str = "unknown"
    environment_description: str = "enterprise_web_suite"
    likely_goal: str = "unknown"
    attack_phase: str = "recon"
    detected_tools: list[str] = Field(default_factory=list)
    session_history: list[Any] = Field(default_factory=list)


@app.post("/honeypot-reply")
async def honeypot_reply(req: HoneypotInput):
    t0 = time.monotonic()
    ctx = req.model_dump()
    user_prompt = _render_template(prompts.HONEYPOT_REPLY_USER, ctx)
    raw = await _generate(prompts.HONEYPOT_REPLY_SYSTEM, user_prompt)
    latency = round((time.monotonic() - t0) * 1000, 1)

    if not raw:
        logger.warning("Honeypot LLM empty response, using deterministic fallback")
        raw = _fallback_honeypot_response(ctx)

    return JSONResponse(
        content={
            "response_body": raw,
            "persona_type": req.attack_type,
            "latency_ms": latency,
        }
    )


@app.get("/health")
async def health():
    return JSONResponse(
        content={
            "status": "healthy",
            "ollama_connected": _ollama_available,
            "ollama_url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "openai_configured": bool(OPENAI_API_KEY),
        }
    )


@app.get("/")
async def root():
    return JSONResponse(content={"service": "mayasec-llm", "version": "4.0.0"})
