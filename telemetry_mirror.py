"""Telemetry feature extraction for async HTTP ingress proxy."""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict
from urllib.parse import parse_qsl, unquote

# Precompiled patterns for low-latency detection path.
_SQL_COMMENT_RE = re.compile(r"/\*.*?\*/|--.*?(?:\n|$)", re.DOTALL)

_SQL_KEYWORDS = ("union", "select", "drop", "insert", "1=1")
_XSS_PATTERNS = ("<script>", "javascript:", "onerror=")
_SCANNER_UA_MARKERS = ("sqlmap", "nikto", "nmap", "burp")

# Sliding window state: source_ip -> request timestamps (seconds).
_REQUEST_TIMELINES: Dict[str, Deque[float]] = defaultdict(deque)
_RATE_WINDOW_SECONDS = 60.0


def _safe_unquote(value: str) -> str:
    try:
        return unquote(value)
    except Exception:
        return value


def _normalize_for_detection(value: str) -> str:
    decoded = _safe_unquote(value)
    lowered = decoded.lower()
    return _SQL_COMMENT_RE.sub(" ", lowered)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0

    length = len(value)
    counts = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1

    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _request_rate_60s(source_ip: str, now_ts: float) -> int:
    timeline = _REQUEST_TIMELINES[source_ip]
    cutoff = now_ts - _RATE_WINDOW_SECONDS

    while timeline and timeline[0] < cutoff:
        timeline.popleft()

    timeline.append(now_ts)
    return len(timeline)


async def extract_features(request) -> dict:
    """Convert an aiohttp request into an ML-ready feature vector.

    This function is defensive by design and always returns a dictionary, even for
    malformed/partial request objects.
    """

    try:
        source_ip = request.remote or "0.0.0.0"
    except Exception:
        source_ip = "0.0.0.0"

    try:
        http_verb = (request.method or "").upper() or "UNKNOWN"
    except Exception:
        http_verb = "UNKNOWN"

    try:
        # Path + query string, e.g. "/login?user=abc".
        uri = str(request.rel_url)
    except Exception:
        uri = "/"

    uri_length = len(uri)

    body_text = ""
    body_length = 0
    try:
        body_bytes = await request.read()
        body_length = len(body_bytes) if body_bytes else 0
        if body_bytes:
            body_text = body_bytes.decode("utf-8", errors="ignore")
    except Exception:
        body_text = ""
        body_length = 0

    # Count URL query params (including duplicate keys).
    num_query_params = 0
    try:
        query_string = request.query_string or ""
        if query_string:
            num_query_params = len(parse_qsl(query_string, keep_blank_values=True))
    except Exception:
        num_query_params = 0

    # Count form parameters for x-www-form-urlencoded bodies only.
    num_form_params = 0
    try:
        content_type = (request.content_type or "").lower()
        if "application/x-www-form-urlencoded" in content_type and body_text:
            num_form_params = len(parse_qsl(body_text, keep_blank_values=True))
    except Exception:
        num_form_params = 0

    num_params = num_query_params + num_form_params

    normalized_uri = _normalize_for_detection(uri)
    normalized_body = _normalize_for_detection(body_text)
    detection_text = f"{normalized_uri} {normalized_body}"

    has_sql_keywords = any(keyword in detection_text for keyword in _SQL_KEYWORDS)
    has_xss_patterns = any(pattern in detection_text for pattern in _XSS_PATTERNS)

    try:
        user_agent = request.headers.get("User-Agent", "")
    except Exception:
        user_agent = ""

    ua_normalized = user_agent.lower()
    user_agent_entropy = _shannon_entropy(user_agent)
    user_agent_known_tool = any(marker in ua_normalized for marker in _SCANNER_UA_MARKERS)

    now_ts = time.time()
    request_rate_60s = _request_rate_60s(source_ip, now_ts)
    hour_of_day = datetime.now().hour

    return {
        "source_ip": source_ip,
        "http_verb": http_verb,
        "uri": uri,
        "uri_length": uri_length,
        "body_length": body_length,
        "num_params": num_params,
        "has_sql_keywords": has_sql_keywords,
        "has_xss_patterns": has_xss_patterns,
        "user_agent_entropy": user_agent_entropy,
        "user_agent_known_tool": user_agent_known_tool,
        "request_rate_60s": request_rate_60s,
        "hour_of_day": hour_of_day,
    }
