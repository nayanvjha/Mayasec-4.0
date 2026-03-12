"""Centralized runtime configuration for the ingress proxy."""

from __future__ import annotations

import os
import importlib
from urllib.parse import urlparse

try:
    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv()
except Exception:
    pass


def _validate_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid {name}: {value!r}")
    return value


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception as exc:
        raise ValueError(f"Invalid {name}: {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid {name}: {raw!r}")


PRODUCTION_BACKEND = _validate_url("PRODUCTION_BACKEND", os.environ.get("PRODUCTION_BACKEND", "http://production-web:3000"))
HONEYPOT_BACKEND = _validate_url("HONEYPOT_BACKEND", os.environ.get("HONEYPOT_BACKEND", "http://victim-web:80"))
ML_SCORE_URL = _validate_url("ML_SCORE_URL", os.environ.get("ML_SCORE_URL", "http://mayasec-core:5001/api/ml/score"))
ML_TIMEOUT_MS = _get_int("ML_TIMEOUT_MS", 50)
SCORE_THRESHOLD = _get_int("SCORE_THRESHOLD", 80)
RATE_LIMIT_PER_IP = _get_int("RATE_LIMIT_PER_IP", 200)
REQUEST_LOGGING = _get_bool("REQUEST_LOGGING", True)
PROXY_SENSOR_ID = os.environ.get("PROXY_SENSOR_ID", "ingress-proxy-01")  # Required for security_logs.sensor_id NOT NULL
BEHAVIORAL_SCORE_URL = _validate_url("BEHAVIORAL_SCORE_URL", os.environ.get("BEHAVIORAL_SCORE_URL", "http://mayasec-core:5002/api/behavioral/score"))
BEHAVIORAL_TIMEOUT_MS = _get_int("BEHAVIORAL_TIMEOUT_MS", 50)
BEHAVIORAL_FEEDBACK_URL = _validate_url(
    "BEHAVIORAL_FEEDBACK_URL",
    os.environ.get("BEHAVIORAL_FEEDBACK_URL", "http://core:5001/api/behavioral/feedback"),
)
BEHAVIORAL_FEEDBACK_TIMEOUT_MS = _get_int("BEHAVIORAL_FEEDBACK_TIMEOUT_MS", 200)
LLM_WAF_URL = _validate_url(
    "LLM_WAF_URL",
    os.environ.get("LLM_WAF_URL", "http://llm-service:8002/classify-zero-day"),
)
LLM_WAF_TIMEOUT_MS = _get_int("LLM_WAF_TIMEOUT_MS", 500)
LLM_WAF_UNCERTAIN_LOW = _get_int("LLM_WAF_UNCERTAIN_LOW", 40)
LLM_WAF_UNCERTAIN_HIGH = _get_int("LLM_WAF_UNCERTAIN_HIGH", 80)


if ML_TIMEOUT_MS <= 0:
    raise ValueError("ML_TIMEOUT_MS must be > 0")
if not 0 <= SCORE_THRESHOLD <= 100:
    raise ValueError("SCORE_THRESHOLD must be between 0 and 100")
if RATE_LIMIT_PER_IP <= 0:
    raise ValueError("RATE_LIMIT_PER_IP must be > 0")
