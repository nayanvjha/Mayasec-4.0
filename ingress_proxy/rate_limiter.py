"""In-memory sliding-window IP rate limiter for abuse detection."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from config import RATE_LIMIT_PER_IP

WINDOW_SIZE_SECONDS = 60.0
_IP_WINDOWS: dict[str, Deque[float]] = defaultdict(deque)


def check_rate_limit(ip: str) -> bool:
    """Return True when requests from `ip` exceed RATE_LIMIT_PER_IP over the last 60 seconds.

    Uses a sliding window deque. Expired timestamps are evicted on every call.
    The defaultdict creates the deque on first access — no manual pop/re-insert needed.
    """
    now = time.monotonic()
    cutoff = now - WINDOW_SIZE_SECONDS
    q = _IP_WINDOWS[ip]  # defaultdict creates empty deque on first access

    # Evict timestamps outside the sliding window
    while q and q[0] <= cutoff:
        q.popleft()

    q.append(now)  # record this request
    return len(q) > RATE_LIMIT_PER_IP


async def check_rate_limit_async(ip: str) -> bool:
    """Redis-backed rate limiter with in-memory fallback."""
    try:
        from redis_client import get_pool

        pool = await get_pool()
        if pool is not None:
            import time as _time

            now = _time.time()
            key = f"ratelimit:{ip}"

            pipe = pool.pipeline()
            pipe.zremrangebyscore(key, 0, now - WINDOW_SIZE_SECONDS)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, int(WINDOW_SIZE_SECONDS) + 5)
            results = await pipe.execute()
            count = int(results[2])
            return count > RATE_LIMIT_PER_IP
    except Exception:
        pass

    return check_rate_limit(ip)
