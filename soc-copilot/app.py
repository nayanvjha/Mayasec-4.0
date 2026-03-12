"""MAYASEC SOC Copilot — RAG-powered conversational analyst interface."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import prompts
import tools

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("soc_copilot")

LLM_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))

# In-memory conversation history (per-session, cleared on restart)
_conversations: dict[str, list[dict]] = {}

app = FastAPI(title="MAYASEC SOC Copilot", version="4.0.0")
_http_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def startup():
    global _http_client
    _http_client = httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT))


@app.on_event("shutdown")
async def shutdown():
    if _http_client:
        await _http_client.aclose()


async def _llm_generate(system: str, user: str) -> str:
    """Call Ollama for copilot responses."""
    if not _http_client:
        return ""
    try:
        resp = await _http_client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "system": system,
                "prompt": user,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 1024},
            },
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
    except Exception as exc:
        logger.warning("LLM generate failed: %s", exc)
    return ""


def _parse_action(text: str) -> dict:
    """Extract JSON action from LLM response."""
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start:end])
        except json.JSONDecodeError:
            pass
    return {"tool": "none", "answer": cleaned}


def _execute_tool(tool_name: str, params: dict) -> Any:
    """Execute a copilot tool and return results."""
    tool_info = tools.AVAILABLE_TOOLS.get(tool_name)
    if not tool_info:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        fn = tool_info["fn"]
        accepted = tool_info["params"]
        filtered = {k: v for k, v in params.items() if k in accepted}
        return fn(**filtered)
    except Exception as exc:
        return {"error": str(exc)}


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


class QueryResponse(BaseModel):
    answer: str
    tool_used: str = ""
    tool_results: Any = None
    latency_ms: float = 0.0


@app.post("/query", response_model=QueryResponse)
async def handle_query(req: QueryRequest):
    t0 = time.monotonic()

    history = _conversations.setdefault(req.session_id, [])
    history.append({"role": "user", "content": req.query})

    tools_desc = prompts.build_tools_description()
    system = prompts.SYSTEM_PROMPT.format(tools_description=tools_desc)

    recent = history[-6:]  # last 3 exchanges
    user_prompt = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in recent
    )

    action_text = await _llm_generate(system, user_prompt)
    action = _parse_action(action_text)

    tool_name = str(action.get("tool", "none"))
    tool_results = None

    if tool_name != "none" and tool_name in tools.AVAILABLE_TOOLS:
        params = action.get("params", {})
        if not isinstance(params, dict):
            params = {}

        tool_results = _execute_tool(tool_name, params)

        synthesis_prompt = (
            f"User asked: {req.query}\n\n"
            f"Tool '{tool_name}' returned:\n{json.dumps(tool_results, indent=2, default=str)[:3000]}\n\n"
            "Provide a clear, concise answer based on this data. Cite specific numbers and IPs."
        )
        answer = await _llm_generate(system, synthesis_prompt)
        if not answer:
            answer = f"Tool results: {json.dumps(tool_results, default=str)[:1000]}"
    else:
        answer = str(action.get("answer", action_text))

    history.append({"role": "assistant", "content": answer})

    if len(history) > 20:
        _conversations[req.session_id] = history[-20:]

    latency = round((time.monotonic() - t0) * 1000, 1)
    return QueryResponse(
        answer=answer,
        tool_used=tool_name if tool_name != "none" else "",
        tool_results=tool_results,
        latency_ms=latency,
    )


@app.get("/history")
async def get_history(session_id: str = "default"):
    return JSONResponse(
        content={
            "session_id": session_id,
            "messages": _conversations.get(session_id, []),
        }
    )


@app.delete("/history")
async def clear_history(session_id: str = "default"):
    _conversations.pop(session_id, None)
    return JSONResponse(content={"status": "cleared"})


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "healthy", "service": "soc-copilot"})


@app.get("/")
async def root():
    return JSONResponse(content={"service": "mayasec-soc-copilot", "version": "4.0.0"})
