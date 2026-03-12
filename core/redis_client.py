"""Sync Redis client for core service. Fail-open pattern."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_client = None
_attempted = False


def get_client():
    """Return sync Redis client. Returns None if unavailable."""
    global _client, _attempted
    if _client is not None:
        return _client
    if _attempted:
        return None

    _attempted = True
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=1,
        )
        _client.ping()
        logger.info("Core Redis client connected to %s", url)
        return _client
    except Exception as exc:
        logger.warning("Core Redis unavailable: %s", exc)
        _client = None
        return None
