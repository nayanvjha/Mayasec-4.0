"""Redis-backed attacker session and response cache for victim-web."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSION_TTL = 3600

_redis = redis.from_url(REDIS_URL, decode_responses=True)


def _session_key(source_ip: str) -> str:
    return f"honeypot:session:{source_ip}"


def _cache_key(attack_type: str, uri: str, method: str, body: str) -> str:
    hash_input = f"{method}:{attack_type}:{uri}:{body[:200]}"
    digest = hashlib.md5(hash_input.encode()).hexdigest()
    return f"honeypot:cache:{digest}"


def get_session(source_ip: str) -> dict:
    now = int(time.time())
    default_session = {
        "depth": 0,
        "uri_history": [],
        "attack_types": [],
        "first_seen": now,
        "last_seen": now,
    }
    try:
        raw = _redis.get(_session_key(source_ip))
        if not raw:
            return default_session
        data = json.loads(raw)
        if not isinstance(data, dict):
            return default_session
        data.setdefault("depth", 0)
        data.setdefault("uri_history", [])
        data.setdefault("attack_types", [])
        data.setdefault("first_seen", now)
        data["last_seen"] = now
        return data
    except Exception:
        return default_session


def update_session(source_ip: str, uri: str, attack_type: str) -> dict:
    now = int(time.time())
    try:
        session = get_session(source_ip)
        session["depth"] = int(session.get("depth", 0)) + 1
        uri_history = list(session.get("uri_history", []))
        uri_history.append(uri)
        session["uri_history"] = uri_history[-50:]
        attack_types = list(session.get("attack_types", []))
        if attack_type and attack_type not in attack_types:
            attack_types.append(attack_type)
        session["attack_types"] = attack_types[-20:]
        session["first_seen"] = session.get("first_seen", now)
        session["last_seen"] = now
        _redis.setex(_session_key(source_ip), SESSION_TTL, json.dumps(session))
        return session
    except Exception:
        fallback = get_session(source_ip)
        fallback["depth"] = int(fallback.get("depth", 0)) + 1
        fallback["uri_history"] = list(fallback.get("uri_history", [])) + [uri]
        if attack_type:
            at = list(fallback.get("attack_types", []))
            if attack_type not in at:
                at.append(attack_type)
            fallback["attack_types"] = at
        fallback["last_seen"] = now
        return fallback


def get_cached_response(attack_type: str, uri: str, method: str, body: str) -> Optional[str]:
    try:
        return _redis.get(_cache_key(attack_type, uri, method, body))
    except Exception:
        return None


def cache_response(attack_type: str, uri: str, method: str, body: str, response: str):
    try:
        _redis.setex(_cache_key(attack_type, uri, method, body), SESSION_TTL, response)
    except Exception:
        return None
