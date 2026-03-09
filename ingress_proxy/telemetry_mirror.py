"""Request feature extraction engine for ML anomaly scoring."""

from __future__ import annotations

import math
import re
import statistics
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Deque
from urllib.parse import parse_qsl, unquote

_SQL_COMMENT_RE = re.compile(r"/\*.*?\*/|--.*?(?:\n|$)", re.DOTALL)
_SQL_KEYWORDS = ("union", "select", "drop", "insert", "1=1")
_XSS_PATTERNS = ("<script>", "javascript:", "onerror=")
_KNOWN_TOOLS = ("sqlmap", "nikto", "nmap", "burp")

_REQUEST_TIMES: dict[str, Deque[float]] = defaultdict(deque)
_WINDOW_SECONDS = 60.0

# Per-IP behavioral session entries over a rolling 60-second window.
_ip_session_store: defaultdict[str, list[dict[str, object]]] = defaultdict(list)


def _normalize(value: str) -> str:
    try:
        decoded = unquote(value)
    except Exception:
        decoded = value
    return _SQL_COMMENT_RE.sub(" ", decoded.lower())


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    out = 0.0
    for count in counts.values():
        p = count / length
        out -= p * math.log2(p)
    return out


def _rate_60s(ip: str, now: float) -> int:
    q = _REQUEST_TIMES[ip]
    cutoff = now - _WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()
    q.append(now)
    return len(q)


def _safe_variance(values: list[int]) -> float:
    if len(values) <= 1:
        return 0.0
    return float(statistics.variance(values))


def _session_behavior_features(
    source_ip: str,
    now: float,
    uri: str,
    body_length: int,
    method: str,
    ua: str,
    num_params: int,
) -> dict:
    entries = _ip_session_store[source_ip]

    # Keep only recent events in the 60s session window.
    recent_entries = [entry for entry in entries if now - float(entry["ts"]) <= _WINDOW_SECONDS]
    _ip_session_store[source_ip] = recent_entries

    # Compute features against existing window state before adding current event.
    previous_ts = float(recent_entries[-1]["ts"]) if recent_entries else now
    inter_request_interval_ms = (now - previous_ts) * 1000.0 if recent_entries else 0.0

    current_path = uri.split("?", 1)[0]
    uri_paths = {str(entry["uri"]).split("?", 1)[0] for entry in recent_entries}
    uri_paths.add(current_path)

    body_lengths = [int(entry["body_length"]) for entry in recent_entries]
    body_lengths.append(body_length)

    methods = {str(entry["http_verb"]) for entry in recent_entries}
    methods.add(method)

    ua_values = {str(entry["user_agent"]) for entry in recent_entries}
    ua_values.add(ua)

    param_counts = [int(entry["num_params"]) for entry in recent_entries]
    param_counts.append(num_params)

    # Append current request at the end for the next call.
    _ip_session_store[source_ip].append(
        {
            "ts": now,
            "uri": uri,
            "body_length": body_length,
            "http_verb": method,
            "user_agent": ua,
            "num_params": num_params,
        }
    )

    return {
        "inter_request_interval_ms": inter_request_interval_ms,
        "uri_path_diversity": len(uri_paths),
        "body_size_variance": _safe_variance(body_lengths),
        "http_method_diversity": len(methods),
        "ua_change_detected": len(ua_values) > 1,
        "param_count_variance": _safe_variance(param_counts),
    }


async def extract_features(request) -> dict:
    """Convert an aiohttp request into a lightweight ML feature vector."""
    source_ip = getattr(request, "remote", None) or "0.0.0.0"
    method = (getattr(request, "method", "") or "UNKNOWN").upper()
    uri = str(getattr(request, "rel_url", "/"))

    try:
        body_bytes = await request.read()
    except Exception:
        body_bytes = b""

    body_text = body_bytes.decode("utf-8", errors="ignore") if body_bytes else ""
    query_string = getattr(request, "query_string", "") or ""
    num_query = len(parse_qsl(query_string, keep_blank_values=True)) if query_string else 0

    num_form = 0
    content_type = (getattr(request, "content_type", "") or "").lower()
    if "application/x-www-form-urlencoded" in content_type and body_text:
        num_form = len(parse_qsl(body_text, keep_blank_values=True))

    num_params = num_query + num_form

    detection = f"{_normalize(uri)} {_normalize(body_text)}"

    try:
        ua = request.headers.get("User-Agent", "")
    except Exception:
        ua = ""

    now = time.monotonic()
    features = {
        "source_ip": source_ip,
        "http_verb": method,
        "uri": uri,
        "uri_length": len(uri),
        "body_length": len(body_bytes),
        "num_params": num_params,
        "has_sql_keywords": any(k in detection for k in _SQL_KEYWORDS),
        "has_xss_patterns": any(k in detection for k in _XSS_PATTERNS),
        "user_agent_entropy": _entropy(ua),
        "user_agent_known_tool": any(k in ua.lower() for k in _KNOWN_TOOLS),
        "request_rate_60s": _rate_60s(source_ip, now),
        "hour_of_day": datetime.now().hour,
    }

    features.update(
        _session_behavior_features(
            source_ip=source_ip,
            now=now,
            uri=uri,
            body_length=len(body_bytes),
            method=method,
            ua=ua,
            num_params=num_params,
        )
    )

    return features
