"""
Response mode resolution (backend authoritative).
"""

import os
from typing import Tuple

ALLOWED_RESPONSE_MODES = {"monitor", "guarded", "active"}


def resolve_response_mode() -> Tuple[str, str]:
    """
    Resolve response mode from env or response.mode file.

    Returns:
        (mode, source)
    Raises:
        RuntimeError if missing or invalid.
    """
    env_mode = os.getenv("MAYASEC_RESPONSE_MODE")
    if env_mode:
        mode = _normalize(env_mode)
        _validate(mode)
        return mode, "env"

    file_path = os.getenv("MAYASEC_RESPONSE_MODE_FILE", "response.mode")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        mode = _normalize(raw)
        _validate(mode)
        return mode, "file"

    raise RuntimeError("Missing response mode. Set MAYASEC_RESPONSE_MODE or response.mode file.")


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


def _validate(mode: str) -> None:
    if mode not in ALLOWED_RESPONSE_MODES:
        raise RuntimeError(f"Invalid response mode: {mode}. Must be one of {sorted(ALLOWED_RESPONSE_MODES)}")
