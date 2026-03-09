"""Lightweight in-memory IP rate limiter for ingress proxy abuse detection."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from config import RATE_LIMIT_PER_IP

# Sliding window size for request counting.
WINDOW_SIZE_SECONDS = 60.0

# Per-IP timelines: {ip -> deque([timestamp1, timestamp2, ...])}
# Deque gives O(1) append on new request and O(1) popleft for expired entries.
_REQUEST_TIMELINES: Dict[str, Deque[float]] = defaultdict(deque)


def check_rate_limit(ip: str) -> bool:
    """Return True when an IP exceeds allowed requests in the last 60 seconds.

    Algorithm (O(1) average per call):
    1) Get current monotonic timestamp.
    2) Drop timestamps older than the 60s window from the left of the deque.
    3) Append current timestamp for this request.
    4) Compare deque length with `RATE_LIMIT_PER_IP`.
    5) Remove dictionary entry if deque becomes empty after cleanup.

    Designed for single-threaded asyncio event-loop usage.
    """
    now = time.monotonic()
    cutoff = now - WINDOW_SIZE_SECONDS

    timeline = _REQUEST_TIMELINES[ip]

    # Expire old entries outside the active sliding window.
    while timeline and timeline[0] <= cutoff:
        timeline.popleft()

    # If everything expired, drop the IP key to keep memory usage bounded,
    # then create a fresh deque for the current request.
    if not timeline:
        _REQUEST_TIMELINES.pop(ip, None)
        timeline = _REQUEST_TIMELINES[ip]

    # Record current request.
    timeline.append(now)

    # Flag as suspicious only when request count exceeds configured limit.
    exceeded = len(timeline) > RATE_LIMIT_PER_IP

    return exceeded


__all__ = ["check_rate_limit", "WINDOW_SIZE_SECONDS"]
