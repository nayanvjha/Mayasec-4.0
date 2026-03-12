"""SOC Copilot function-calling tools — direct DB queries for grounded answers."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "mayasec"),
    "user": os.getenv("DB_USER", "mayasec"),
    "password": os.getenv("DB_PASSWORD", "mayasec"),
}


def _get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query_events(
    ip: str = "",
    hours: int = 24,
    limit: int = 20,
    event_type: str = "",
    min_score: int = 0,
) -> list[dict]:
    """Query security_logs with filters."""
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        conditions = ["created_at >= NOW() - (%s * INTERVAL '1 hour')"]
        params: list[Any] = [hours]

        if ip:
            conditions.append("ip_address::text = %s")
            params.append(ip)
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)
        if min_score > 0:
            conditions.append("COALESCE(threat_score, 0) >= %s")
            params.append(min_score)

        where = " AND ".join(conditions)
        params.append(min(limit, 100))

        cursor.execute(
            f"SELECT event_id, event_type, ip_address::text AS source_ip, threat_level AS severity, "
            f"threat_score, COALESCE(metadata->>'attack_type', 'unknown') AS attack_type, "
            f"COALESCE(mitre_ttps, '[]'::jsonb) AS mitre_ttps, created_at, COALESCE(reason, '') AS raw_log "
            f"FROM security_logs WHERE {where} "
            f"ORDER BY created_at DESC LIMIT %s",
            params,
        )
        rows = [dict(r) for r in cursor.fetchall()]
        cursor.close()
        conn.close()

        for row in rows:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()
        return rows
    except Exception as exc:
        logger.error("query_events failed: %s", exc)
        return []


def query_behavioral_history(ip: str, hours: int = 24, limit: int = 20) -> list[dict]:
    """Query behavioral_baselines for an IP."""
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT intent, anomaly_score, graph_threat, recorded_at "
            "FROM behavioral_baselines "
            "WHERE source_ip::text = %s AND recorded_at >= NOW() - (%s * INTERVAL '1 hour') "
            "ORDER BY recorded_at DESC LIMIT %s",
            (ip, hours, min(limit, 100)),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        cursor.close()
        conn.close()

        for row in rows:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()
        return rows
    except Exception as exc:
        logger.error("query_behavioral_history failed: %s", exc)
        return []


def query_active_sessions() -> dict:
    """Get current session graph state from core."""
    try:
        import httpx

        core_url = os.getenv("CORE_URL", "http://core:5001")
        resp = httpx.get(f"{core_url}/api/behavioral/sessions", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.error("query_active_sessions failed: %s", exc)
    return {}


def get_drift_status() -> dict:
    """Get drift detector state from core."""
    try:
        import httpx

        core_url = os.getenv("CORE_URL", "http://core:5001")
        resp = httpx.get(f"{core_url}/api/behavioral/drift", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.error("get_drift_status failed: %s", exc)
    return {}


def explain_event(event_id: str) -> dict:
    """Get LLM explanation for a specific event ID."""
    try:
        import httpx

        llm_url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")

        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM security_logs WHERE event_id::text = %s", (str(event_id),))
        event = cursor.fetchone()
        cursor.close()
        conn.close()

        if not event:
            return {"error": f"Event {event_id} not found"}

        resp = httpx.post(
            f"{llm_url}/explain",
            json={
                "event_type": str(event.get("event_type", "")),
                "source_ip": str(event.get("ip_address", "")),
                "uri": str(event.get("reason", ""))[:500],
                "score": int(event.get("threat_score", 0) or 0),
                "attack_type": str((event.get("metadata") or {}).get("attack_type", "normal")),
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.error("explain_event failed: %s", exc)
    return {"error": "explanation unavailable"}


def get_stats_summary(hours: int = 24) -> dict:
    """Get high-level stats for the time window."""
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                COUNT(*) as total_events,
                COUNT(*) FILTER (WHERE threat_level = 'critical') as critical_count,
                COUNT(*) FILTER (WHERE threat_level = 'high') as high_count,
                COUNT(DISTINCT ip_address) as unique_ips,
                AVG(COALESCE(threat_score, 0))::float as avg_threat_score
            FROM security_logs
            WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
            ''',
            (hours,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return dict(row) if row else {}
    except Exception as exc:
        logger.error("get_stats_summary failed: %s", exc)
        return {}


# Tool registry for the copilot
AVAILABLE_TOOLS = {
    "query_events": {
        "fn": query_events,
        "description": "Search security events by IP, type, score, time window",
        "params": ["ip", "hours", "limit", "event_type", "min_score"],
    },
    "query_behavioral_history": {
        "fn": query_behavioral_history,
        "description": "Get behavioral ML intent history for an IP",
        "params": ["ip", "hours", "limit"],
    },
    "query_active_sessions": {
        "fn": query_active_sessions,
        "description": "Get current live session graph (cross-IP correlation)",
        "params": [],
    },
    "get_drift_status": {
        "fn": get_drift_status,
        "description": "Check if behavioral ML model needs retraining",
        "params": [],
    },
    "explain_event": {
        "fn": explain_event,
        "description": "Get LLM narrative explanation for a specific event ID",
        "params": ["event_id"],
    },
    "get_stats_summary": {
        "fn": get_stats_summary,
        "description": "Get event statistics summary for a time window",
        "params": ["hours"],
    },
}
