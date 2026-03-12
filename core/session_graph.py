"""In-memory session correlation graph for distributed reconnaissance detection."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import time
from typing import Any, Optional


class SessionGraph:
    """Thread-safe, in-memory session graph optimized for high-throughput updates."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self._graph: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._last_prune_ts: float = time.monotonic()
        self._redis = redis_client if redis_client is not None else self._resolve_redis_client()

    @staticmethod
    def _resolve_redis_client() -> Any | None:
        """Resolve optional core Redis client. Returns None when unavailable."""
        try:
            from core.redis_client import get_client

            return get_client()
        except Exception:
            return None

    @staticmethod
    def _redis_key(session_id: str) -> str:
        return f"graph:{session_id}"

    def _write_node_redis(self, session_id: str, node: dict[str, Any]) -> None:
        """Best-effort Redis write-through for shared state across workers."""
        if self._redis is None:
            return
        try:
            mapping = {
                "ips": json.dumps(self._to_str_list(node.get("ips", set()))),
                "paths": json.dumps(self._to_str_list(node.get("paths", set()))),
                "ts_first": str(float(node.get("ts_first", 0.0))),
                "ts_last": str(float(node.get("ts_last", 0.0))),
                "graph_threat": "1" if bool(node.get("graph_threat", False)) else "0",
            }
            key = self._redis_key(session_id)
            self._redis.hset(key, mapping=mapping)
            self._redis.expire(key, 300)
        except Exception:
            # Fail-open: in-memory remains source of truth when Redis unavailable.
            pass

    def _delete_node_redis(self, session_id: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._redis_key(session_id))
        except Exception:
            pass

    def _read_threat_redis(self, session_id: str) -> Optional[bool]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.hget(self._redis_key(session_id), "graph_threat")
            if raw is None:
                return None
            return str(raw) in {"1", "true", "True"}
        except Exception:
            return None

    @staticmethod
    def _to_set(value: Any) -> set[Any]:
        if value is None:
            return set()
        if isinstance(value, set):
            return value
        if isinstance(value, (str, bytes)):
            return {value.decode() if isinstance(value, bytes) else value}
        try:
            return set(value)
        except Exception:
            return {value}

    @staticmethod
    def _to_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            value = [value.decode() if isinstance(value, bytes) else value]
        elif isinstance(value, set):
            value = list(value)
        else:
            try:
                value = list(value)
            except Exception:
                value = [value]
        return [str(item) for item in value]

    @staticmethod
    def _to_wall_ts(monotonic_ts: Any, offset: float) -> float | None:
        if isinstance(monotonic_ts, (int, float)):
            ts = float(monotonic_ts)
            if math.isfinite(ts):
                return ts + offset
        return None

    def _evaluate_threat_unlocked(self, session_id: str) -> bool:
        node = self._graph.get(session_id)
        if not isinstance(node, dict):
            return False

        ips = self._to_set(node.get("ips", set()))
        paths = self._to_set(node.get("paths", set()))

        threat = len(paths) >= 10 and len(ips) >= 3
        if threat:
            node["graph_threat"] = True
        elif "graph_threat" not in node:
            node["graph_threat"] = False
        return bool(node.get("graph_threat", False))

    def add_event(self, ip: str, path: str, session_id: str | None = None) -> None:
        """Record a request event and update correlation state."""
        now = time.monotonic()

        # Auto-prune at most once per 60 seconds.
        # Gate check is inside the lock to prevent concurrent redundant prune runs.
        needs_prune = False
        with self._lock:
            if now - self._last_prune_ts > 60:
                self._last_prune_ts = now
                needs_prune = True

        if needs_prune:
            self.prune_stale_sessions()

        sid = session_id or hashlib.sha1(f"{ip}{path}{now}".encode()).hexdigest()

        with self._lock:
            node = self._graph.get(sid)
            if not isinstance(node, dict):
                node = {
                    "ips": set(),
                    "paths": set(),
                    "ts_first": now,
                    "ts_last": now,
                    "graph_threat": False,
                }
                self._graph[sid] = node

            ips = self._to_set(node.get("ips", set()))
            paths = self._to_set(node.get("paths", set()))

            ips.add(ip)
            paths.add(path)

            node["ips"] = ips
            node["paths"] = paths
            node["ts_first"] = node.get("ts_first", now)
            node["ts_last"] = now
            node["graph_threat"] = bool(node.get("graph_threat", False))

            self._evaluate_threat_unlocked(sid)
            self._write_node_redis(sid, node)

    def evaluate_threat(self, session_id: str) -> bool:
        """Evaluate and persist threat state for the given session."""
        with self._lock:
            return self._evaluate_threat_unlocked(session_id)

    def get_threat(self, session_id: Optional[str] = None, ip: Optional[str] = None, path: Optional[str] = None) -> bool:
        """O(1) direct threat lookup by session_id, falling back to ip+path scan only when needed.

        This avoids the O(n) full-snapshot approach for the hot path.
        """
        with self._lock:
            # Fast path: direct session_id lookup.
            if session_id is not None:
                node = self._graph.get(session_id)
                if isinstance(node, dict):
                    return bool(node.get("graph_threat", False))

                redis_threat = self._read_threat_redis(session_id)
                if redis_threat is not None:
                    return redis_threat

            if not ip:
                return False

            # Fallback: scan for matching ip+path (still under lock, but avoids snapshot copy).
            matched_threat: Optional[bool] = None
            newest_ts = float('-inf')

            for _sid, node in self._graph.items():
                if not isinstance(node, dict):
                    continue
                node_ips = self._to_set(node.get("ips", set()))
                node_paths = self._to_set(node.get("paths", set()))

                if ip in node_ips and (path is None or path in node_paths):
                    ts_last = node.get("ts_last")
                    ts_val = float(ts_last) if isinstance(ts_last, (int, float)) else float('-inf')
                    if ts_val >= newest_ts:
                        newest_ts = ts_val
                        matched_threat = bool(node.get("graph_threat", False))

            return bool(matched_threat) if matched_threat is not None else False

    def prune_stale_sessions(self, max_age_seconds: int = 900) -> None:
        """Remove sessions inactive for longer than max_age_seconds."""
        now = time.monotonic()
        with self._lock:
            stale_ids: list[str] = []
            for session_id, node in self._graph.items():
                ts_last = node.get("ts_last") if isinstance(node, dict) else None
                if not isinstance(ts_last, (int, float)):
                    stale_ids.append(session_id)
                    continue
                if now - float(ts_last) > max_age_seconds:
                    stale_ids.append(session_id)

            for session_id in stale_ids:
                self._graph.pop(session_id, None)
                self._delete_node_redis(session_id)

    def snapshot(self) -> list[dict]:
        """Return a JSON-serializable, read-only snapshot of graph state."""
        now_wall = time.time()
        now_mono = time.monotonic()
        offset = now_wall - now_mono

        with self._lock:
            # Deep-copy nodes inside the lock to prevent read/write races on
            # mutable sets that add_event() mutates concurrently.
            items = [(sid, copy.deepcopy(node)) for sid, node in self._graph.items()]

        result: list[dict] = []
        for session_id, node in items:
            if not isinstance(node, dict):
                node = {}

            ips = self._to_str_list(node.get("ips", set()))
            paths = self._to_str_list(node.get("paths", set()))
            ts_first = self._to_wall_ts(node.get("ts_first"), offset)
            ts_last = self._to_wall_ts(node.get("ts_last"), offset)

            entry = {
                "session_id": str(session_id),
                "session_ips": ips,
                "session_paths": paths,
                "graph_threat": bool(node.get("graph_threat", False)),
                "ts_first": ts_first,
                "ts_last": ts_last,
            }
            result.append(entry)

        return result
