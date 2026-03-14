"""Attack Story Engine for MAYASEC.

Builds multi-stage attack stories from recent security events.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import requests
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("AttackStoryEngine")


@dataclass
class StoryEvent:
    event_id: str
    source_ip: str
    event_type: str
    attack_type: str
    threat_score: int
    uri: str
    destination: str
    timestamp: datetime
    mitre_ttps: List[str]


class AttackStoryEngine:
    """Periodic attack story builder."""

    def __init__(self, event_repo, llm_service_url: str, interval_seconds: int = 60):
        self.event_repo = event_repo
        self.llm_service_url = llm_service_url.rstrip("/")
        self.interval_seconds = max(30, int(interval_seconds))

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="attack-story-engine")
        self._thread.start()
        logger.info("Attack Story Engine started (interval=%ss)", self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> None:
        conn = None
        try:
            conn = self.event_repo.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id FROM tenants WHERE is_active = TRUE")
            tenants = [str(r.get("id")) for r in (cur.fetchall() or []) if r.get("id")]
            cur.close()

            for tenant_id in tenants:
                self._process_tenant(conn, tenant_id)
        except Exception as e:
            logger.exception("Attack Story Engine run failed: %s", e)
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            self.run_once()
            elapsed = time.monotonic() - t0
            sleep_for = max(1.0, self.interval_seconds - elapsed)
            self._stop.wait(sleep_for)

    def _process_tenant(self, conn, tenant_id: str) -> None:
        try:
            events = self._load_recent_events(conn, tenant_id)
            if not events:
                return

            sessions = self._group_sessions(events)
            for session in sessions:
                self._upsert_story_for_session(conn, tenant_id, session)
        except Exception as e:
            conn.rollback()
            logger.warning("Attack story tenant processing failed tenant=%s error=%s", tenant_id, e)

    def _load_recent_events(self, conn, tenant_id: str) -> List[StoryEvent]:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
            cur.execute(
                """
            SELECT
                sl.event_id::text AS event_id,
                split_part(sl.ip_address::text, '/', 1) AS source_ip,
                COALESCE(sl.event_type, 'unknown') AS event_type,
                COALESCE(
                    sl.metadata->>'attack_type',
                    sl.metadata->'stream_payload'->'event'->>'event_type',
                    sl.metadata->'stream_payload'->'raw'->>'attack_type',
                    ''
                ) AS attack_type,
                COALESCE(sl.threat_score, 0) AS threat_score,
                COALESCE(
                    sl.metadata->>'uri',
                    sl.metadata->'stream_payload'->'event'->>'uri',
                    '/'
                ) AS uri,
                COALESCE(
                    sl.metadata->>'destination',
                    sl.metadata->'stream_payload'->'event'->>'destination',
                    ''
                ) AS destination,
                sl.timestamp,
                COALESCE(sl.mitre_ttps, '[]'::jsonb) AS mitre_ttps
            FROM security_logs sl
            WHERE sl.timestamp >= NOW() - interval '20 minutes'
              AND sl.ip_address IS NOT NULL
            ORDER BY sl.ip_address, sl.timestamp
            """
            )
            rows = cur.fetchall() or []
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        finally:
            cur.close()

        events: List[StoryEvent] = []
        for row in rows:
            ts = row.get("timestamp")
            if not ts or not row.get("event_id"):
                continue

            mitre = self._normalize_mitre(row.get("mitre_ttps"))
            events.append(
                StoryEvent(
                    event_id=str(row.get("event_id")),
                    source_ip=str(row.get("source_ip") or "unknown"),
                    event_type=str(row.get("event_type") or "unknown"),
                    attack_type=str(row.get("attack_type") or "").lower(),
                    threat_score=int(row.get("threat_score") or 0),
                    uri=str(row.get("uri") or "/"),
                    destination=str(row.get("destination") or ""),
                    timestamp=ts,
                    mitre_ttps=mitre,
                )
            )

        return events

    @staticmethod
    def _normalize_mitre(raw: Any) -> List[str]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = [raw]

        if not isinstance(raw, list):
            return []

        out: List[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                tid = item.get("technique_id") or item.get("id")
                if tid:
                    out.append(str(tid).strip())
        return out

    def _group_sessions(self, events: Sequence[StoryEvent]) -> List[List[StoryEvent]]:
        by_ip: Dict[str, List[StoryEvent]] = defaultdict(list)
        for ev in events:
            by_ip[ev.source_ip].append(ev)

        sessions: List[List[StoryEvent]] = []
        window = timedelta(minutes=10)

        for ip_events in by_ip.values():
            ip_events = sorted(ip_events, key=lambda e: e.timestamp)
            current: List[StoryEvent] = []

            for ev in ip_events:
                if not current:
                    current.append(ev)
                    continue

                if ev.timestamp - current[-1].timestamp <= window:
                    current.append(ev)
                else:
                    sessions.append(current)
                    current = [ev]

            if current:
                sessions.append(current)

        return sessions

    def _phase_name_for_event(self, ev: StoryEvent) -> Optional[str]:
        et = ev.event_type.lower()
        at = ev.attack_type.lower()

        if "scan" in et or "probe" in et:
            return "Reconnaissance"
        if "brute" in et or "login" in et:
            return "Credential Attack"
        if at in {"sqli", "xss"} or "sqli" in et or "xss" in et:
            return "Exploitation"
        if (ev.destination or "").lower() == "honeypot":
            return "Deception Triggered"
        return None

    def _build_phases(self, session: Sequence[StoryEvent], captures: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        phase_events: Dict[str, List[StoryEvent]] = defaultdict(list)
        for ev in session:
            phase = self._phase_name_for_event(ev)
            if phase:
                phase_events[phase].append(ev)

        phases: List[Dict[str, Any]] = []
        ordered = [
            "Reconnaissance",
            "Credential Attack",
            "Exploitation",
            "Deception Triggered",
        ]

        for phase_name in ordered:
            items = phase_events.get(phase_name, [])
            if not items:
                continue

            scores = [e.threat_score for e in items]
            uris = sorted({e.uri for e in items if e.uri})
            mitre = sorted({t for e in items for t in e.mitre_ttps})

            phases.append({
                "phase": phase_name,
                "start_time": items[0].timestamp.isoformat() + "Z",
                "end_time": items[-1].timestamp.isoformat() + "Z",
                "event_count": len(items),
                "score_range": f"{min(scores)}-{max(scores)}",
                "description": self._phase_description(phase_name, items, uris),
                "mitre": mitre,
            })

        if captures:
            first = captures[0]
            captured_at = first.get("captured_at")
            last_captured_at = captures[-1].get("captured_at")
            capture_scores = [int(c.get("waf_score") or 0) for c in captures]
            phases.append({
                "phase": "Honeypot Interaction",
                "start_time": captured_at.isoformat() + "Z" if captured_at else None,
                "end_time": last_captured_at.isoformat() + "Z" if last_captured_at else None,
                "event_count": len(captures),
                "score_range": f"{min(capture_scores)}-{max(capture_scores)}" if capture_scores else "0-0",
                "description": "Attacker interacted with deceptive environment",
                "mitre": [],
                "capture_preview": {
                    "session_id": first.get("session_id"),
                    "source_ip": first.get("source_ip"),
                    "attack_type": first.get("attack_type"),
                    "request_payload": first.get("request_payload") or "",
                    "llm_response": first.get("llm_response") or "",
                    "timestamp": captured_at.isoformat() + "Z" if captured_at else None,
                    "waf_score": int(first.get("waf_score") or 0),
                },
            })

        return phases

    @staticmethod
    def _phase_description(phase_name: str, items: Sequence[StoryEvent], uris: Sequence[str]) -> str:
        if phase_name == "Reconnaissance":
            top_uris = " ".join(uris[:6]) if uris else "multiple targets"
            return f"Scanned {top_uris}".strip()
        if phase_name == "Credential Attack":
            return f"{len(items)} credential-oriented attempts observed"
        if phase_name == "Exploitation":
            sample = uris[0] if uris else "/"
            return f"Exploitation attempt against {sample}"
        if phase_name == "Deception Triggered":
            return "Threat score exceeded threshold and traffic redirected to deception"
        return "Observed activity"

    @staticmethod
    def _story_title(phases: Sequence[Dict[str, Any]]) -> str:
        names = {p.get("phase") for p in phases}
        if "Exploitation" in names and "Honeypot Interaction" in names:
            return "Intrusion Attempt — Trapped by Deception"
        if names == {"Credential Attack"}:
            return "Brute Force Campaign"
        if names == {"Reconnaissance"}:
            return "Reconnaissance Sweep"
        if len(names) > 1:
            return "Multi-Stage Attack"
        return "Suspicious Activity Story"

    @staticmethod
    def _severity(max_score: int) -> str:
        if max_score >= 90:
            return "critical"
        if max_score >= 80:
            return "high"
        if max_score >= 60:
            return "medium"
        return "low"

    def _load_honeypot_captures(self, conn, tenant_id: str, source_ip: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
            cur.execute(
                """
            SELECT
                session_id,
                host(source_ip) AS source_ip,
                attack_type,
                request_payload,
                llm_response,
                captured_at,
                90 AS waf_score
            FROM honeypot_captures
            WHERE split_part(source_ip::text, '/', 1) = %s
              AND captured_at BETWEEN %s AND %s
            ORDER BY captured_at ASC
            """,
                (
                    source_ip,
                    start_time - timedelta(minutes=5),
                    end_time + timedelta(minutes=15),
                ),
            )
            rows = cur.fetchall() or []
            cur.execute("COMMIT")
            return rows
        except Exception:
            cur.execute("ROLLBACK")
            return []
        finally:
            cur.close()

    def _build_narrative(
        self,
        source_ip: str,
        phases: Sequence[Dict[str, Any]],
        event_count: int,
        duration_seconds: int,
        attack_types: Sequence[str],
    ) -> str:
        payload = {
            "event_type": "attack_story",
            "source_ip": source_ip,
            "uri": "/attack-story",
            "http_verb": "POST",
            "score": 90,
            "attack_type": "multi_stage",
            "intent": "Attack Campaign",
            "request_rate_60s": event_count,
            "body": (
                f"phases={json.dumps(list(phases), default=str)} "
                f"event_count={event_count} duration_seconds={duration_seconds} "
                f"attack_types={','.join(attack_types)}"
            )[:3500],
        }

        try:
            resp = requests.post(
                f"{self.llm_service_url}/explain",
                json=payload,
                timeout=8,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"status={resp.status_code}")
            data = resp.json() if resp.content else {}
            narrative = str(data.get("narrative") or "").strip()
            if narrative:
                return narrative
        except Exception as e:
            logger.debug("Story narrative LLM fallback used: %s", e)

        return (
            f"Attacker {source_ip} executed a {len(phases)}-phase campaign over "
            f"{max(1, duration_seconds)} seconds across {event_count} events."
        )

    def _upsert_story_for_session(self, conn, tenant_id: str, session: Sequence[StoryEvent]) -> None:
        if not session:
            return

        source_ip = session[0].source_ip
        start_time = session[0].timestamp
        end_time = session[-1].timestamp
        event_ids = [ev.event_id for ev in session]

        captures = self._load_honeypot_captures(conn, tenant_id, source_ip, start_time, end_time)
        phases = self._build_phases(session, captures)
        if not phases:
            return

        title = self._story_title(phases)
        max_score = max([ev.threat_score for ev in session] + [int(c.get("waf_score") or 0) for c in captures])
        severity = self._severity(max_score)
        mitre = sorted({t for ev in session for t in ev.mitre_ttps})
        attack_types = sorted({ev.attack_type for ev in session if ev.attack_type})
        duration = int((end_time - start_time).total_seconds())
        narrative = self._build_narrative(source_ip, phases, len(session), duration, attack_types)

        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
            cur.execute(
                """
            SELECT id, event_ids
            FROM attack_stories
            WHERE attacker_ip = %s::inet
              AND start_time <= %s + interval '10 minutes'
              AND end_time >= %s - interval '10 minutes'
            ORDER BY end_time DESC
            LIMIT 1
            """,
                (source_ip, end_time, start_time),
            )
            existing = cur.fetchone()

            if existing:
                merged_ids = sorted(set((existing.get("event_ids") or []) + event_ids))
                cur.execute(
                    """
                UPDATE attack_stories
                SET title = %s,
                    start_time = LEAST(start_time, %s),
                    end_time = GREATEST(end_time, %s),
                    event_ids = %s::uuid[],
                    phases = %s::jsonb,
                    narrative = %s,
                    severity = %s,
                    mitre_techniques = %s::jsonb,
                    status = 'active'
                WHERE id = %s
                """,
                    (
                        title,
                        start_time,
                        end_time,
                        merged_ids,
                        json.dumps(phases),
                        narrative,
                        severity,
                        json.dumps(mitre),
                        existing.get("id"),
                    ),
                )
            else:
                cur.execute(
                    """
                INSERT INTO attack_stories
                (tenant_id, title, attacker_ip, start_time, end_time, event_ids, phases, narrative, severity, mitre_techniques)
                VALUES (%s::uuid, %s, %s::inet, %s, %s, %s::uuid[], %s::jsonb, %s, %s, %s::jsonb)
                """,
                    (
                        tenant_id,
                        title,
                        source_ip,
                        start_time,
                        end_time,
                        event_ids,
                        json.dumps(phases),
                        narrative,
                        severity,
                        json.dumps(mitre),
                    ),
                )

            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        finally:
            cur.close()
