"""Async Redis connection pool for the ingress proxy. Fail-open on any Redis error."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_pool: Any = None


async def get_pool() -> Any:
    """Lazy-init async Redis connection pool. Returns None if Redis unavailable."""
    global _pool
    if _pool is not None:
        return _pool

    try:
        import redis.asyncio as aioredis

        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _pool = aioredis.from_url(
            url,
            decode_responses=True,
            max_connections=64,
            socket_connect_timeout=2,
            socket_timeout=1,
        )
        await _pool.ping()
        logger.info("Redis pool connected to %s", url)
        return _pool
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to in-memory: %s", exc)
        _pool = None
        return None


async def close_pool() -> None:
    """Close Redis pool on shutdown."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None


async def safe_execute(coro_factory, fallback=None):
    """Execute a Redis coroutine, return fallback on any error."""
    pool = await get_pool()
    if pool is None:
        return fallback
    try:
        return await coro_factory(pool)
    except Exception as exc:
        logger.debug("Redis op failed (fail-open): %s", exc)
        return fallback
