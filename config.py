"""Runtime configuration for the async HTTP ingress proxy.

This module loads environment variables, applies secure defaults, validates values,
and exposes module-level constants used by the proxy at runtime.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

# Load local development configuration automatically when a .env file is present.
# In production, real environment variables should override .env values.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Keep startup resilient if python-dotenv is not installed in some environments.
    # The service will still read from os.environ directly.
    pass


def _validate_url(name: str, value: str) -> str:
    """Validate that a configuration value is a syntactically valid HTTP(S) URL."""
    parsed = urlparse(value)
    # Security: backend targets must be validated to avoid malformed routing
    # destinations that could break traffic handling or enable unsafe redirection.
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"Invalid {name}: expected a full URL with http/https scheme and host, got {value!r}"
        )
    return value


def _get_int(name: str, default: int) -> int:
    """Read an integer env var safely with strict validation."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}: expected integer, got {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean env var safely from common truthy/falsey strings."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False

    raise ValueError(
        f"Invalid {name}: expected boolean value (true/false, 1/0, yes/no), got {raw!r}"
    )


# Security: fail-safe defaults keep startup deterministic and avoid accidental
# misconfiguration that could disable protections when variables are missing.
PRODUCTION_BACKEND = _validate_url(
    "PRODUCTION_BACKEND",
    os.environ.get("PRODUCTION_BACKEND", "http://production-web:3000"),
)

HONEYPOT_BACKEND = _validate_url(
    "HONEYPOT_BACKEND",
    os.environ.get("HONEYPOT_BACKEND", "http://victim-web:80"),
)

ML_SCORE_URL = _validate_url(
    "ML_SCORE_URL",
    os.environ.get("ML_SCORE_URL", "http://mayasec-core:5001/api/ml/score"),
)

ML_TIMEOUT_MS = _get_int("ML_TIMEOUT_MS", 50)
if ML_TIMEOUT_MS <= 0:
    raise ValueError(f"Invalid ML_TIMEOUT_MS: must be > 0, got {ML_TIMEOUT_MS}")

SCORE_THRESHOLD = _get_int("SCORE_THRESHOLD", 80)
# Security: threshold tuning directly controls attack-routing decisions; values
# outside 0-100 can cause unsafe or ineffective traffic diversion behavior.
if not 0 <= SCORE_THRESHOLD <= 100:
    raise ValueError(
        f"Invalid SCORE_THRESHOLD: must be between 0 and 100, got {SCORE_THRESHOLD}"
    )

RATE_LIMIT_PER_IP = _get_int("RATE_LIMIT_PER_IP", 200)
# Security: rate limiting protects the ML scoring service from abuse, burst load,
# and resource exhaustion that could degrade detection or create blind spots.
if RATE_LIMIT_PER_IP <= 0:
    raise ValueError(
        f"Invalid RATE_LIMIT_PER_IP: must be > 0, got {RATE_LIMIT_PER_IP}"
    )

REQUEST_LOGGING = _get_bool("REQUEST_LOGGING", True)


__all__ = [
    "PRODUCTION_BACKEND",
    "HONEYPOT_BACKEND",
    "ML_SCORE_URL",
    "ML_TIMEOUT_MS",
    "SCORE_THRESHOLD",
    "RATE_LIMIT_PER_IP",
    "REQUEST_LOGGING",
]
