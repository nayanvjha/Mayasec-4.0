"""Attacker behavior analyzer for adaptive deception session continuity."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, RealDictCursor


TOOL_SIGNATURES = {
    "sqlmap": ["sqlmap", "sqlmap/"],
    "burp_suite": ["burp", "intruder", "repeater"],
    "nmap": ["nmap", "masscan", "zgrab"],
    "nikto": ["nikto"],
    "curl": ["curl/"],
    "python_requests": ["python-requests"],
}

ATTACK_TYPE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("sqli", re.compile(r"union\s+select|or\s+1=1|information_schema|\bselect\b.+\bfrom\b", re.I)),
    ("xss", re.compile(r"<script|onerror=|onload=|javascript:", re.I)),
    ("path_traversal", re.compile(r"\.\./|%2e%2e%2f|/etc/passwd|/proc/self", re.I)),
    ("command_injection", re.compile(r";\s*(cat|id|whoami|curl|wget)|\|\s*(sh|bash)", re.I)),
    ("credential_attack", re.compile(r"password|login|signin|token|auth", re.I)),
]

RECON_HINTS = ("/.git", "/robots.txt", "/wp-admin", "/phpmyadmin", "/admin", "/actuator", "/health")
LATERAL_HINTS = ("/internal", "/swagger", "/openapi", "/api", "/v1/")


@dataclass
class BehaviorResult:
    tenant_id: str
    session_id: str
    source_ip: str
    attacker_profile: Dict[str, Any]
    environment_state: Dict[str, Any]
    interaction_count: int
    llm_context: Dict[str, Any]


class BehaviorAnalyzer:
    def __init__(self):
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", "5432"))
        self.db_name = os.getenv("DB_NAME", "mayasec")
        self.db_user = os.getenv("DB_USER", "mayasec")
        self.db_password = os.getenv("DB_PASSWORD", "mayasec")
        self.default_tenant_slug = os.getenv("DEFAULT_TENANT_SLUG", "demo")
        self.default_tenant_id = os.getenv("DEFAULT_TENANT_ID", "")

    def _conn(self):
        return psycopg2.connect(
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password,
        )

    def _resolve_tenant_id(self, cursor) -> str:
        if self.default_tenant_id:
            return self.default_tenant_id

        cursor.execute("SELECT id FROM tenants WHERE slug = %s LIMIT 1", (self.default_tenant_slug,))
        row = cursor.fetchone()
        if row and row.get("id"):
            return str(row["id"])

        cursor.execute("SELECT id FROM tenants ORDER BY created_at ASC LIMIT 1")
        row = cursor.fetchone()
        if row and row.get("id"):
            return str(row["id"])

        raise RuntimeError("No tenant available for attacker session analysis")

    def _recent_capture_history(self, cursor, source_ip: str, tenant_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT attack_type, request_payload, llm_response, captured_at
            FROM honeypot_captures
            WHERE split_part(source_ip::text, '/', 1) = %s
              AND (tenant_id::text = %s OR tenant_id IS NULL)
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (source_ip, tenant_id, limit),
        )
        return cursor.fetchall() or []

    @staticmethod
    def _to_iso_utc(value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat() + "Z"
        return None

    def _detect_tool(self, user_agent: str, payload: str) -> str:
        text = f"{user_agent} {payload}".lower()
        for tool, signatures in TOOL_SIGNATURES.items():
            if any(sig in text for sig in signatures):
                return tool
        if "mozilla" in user_agent.lower() and len(payload or "") > 0:
            return "manual"
        return "unknown"

    def _detect_attack_types(self, uri: str, payload: str, existing: List[str]) -> List[str]:
        detected = set(existing or [])
        text = f"{uri}\n{payload}".lower()
        for attack_type, pattern in ATTACK_TYPE_PATTERNS:
            if pattern.search(text):
                detected.add(attack_type)
        if not detected:
            if any(h in uri.lower() for h in RECON_HINTS):
                detected.add("recon")
            else:
                detected.add("probe")
        return sorted(detected)

    def _infer_phase(self, uri: str, attack_types: List[str], interaction_count: int) -> str:
        low_uri = (uri or "").lower()
        if any(token in low_uri for token in LATERAL_HINTS):
            return "privilege_escalation"
        if "command_injection" in attack_types or "path_traversal" in attack_types:
            return "privilege_escalation"
        if "sqli" in attack_types or "xss" in attack_types or "credential_attack" in attack_types:
            return "exploitation"
        if interaction_count >= 6:
            return "data_exfil"
        return "recon"

    def _infer_skill(self, tool: str, attack_types: List[str], payload: str, interaction_count: int) -> str:
        sophistication = 0
        if tool in {"burp_suite", "sqlmap"}:
            sophistication += 2
        if len(attack_types) >= 3:
            sophistication += 2
        if len(payload or "") > 200:
            sophistication += 1
        if any(sig in (payload or "").lower() for sig in ["information_schema", "union select", "%2f", "x-forwarded-for"]):
            sophistication += 1
        if interaction_count >= 8:
            sophistication += 1

        if sophistication >= 5:
            return "advanced"
        if sophistication >= 3:
            return "intermediate"
        return "script_kiddie"

    def _infer_goal(self, phase: str, attack_types: List[str], uri: str) -> str:
        low_uri = (uri or "").lower()
        if "credential_attack" in attack_types or "login" in low_uri:
            return "credential_harvesting"
        if phase == "privilege_escalation" or any(token in low_uri for token in LATERAL_HINTS):
            return "lateral_movement"
        if "sqli" in attack_types or "path_traversal" in attack_types:
            return "data_theft"
        return "credential_harvesting"

    def _evolve_environment(self, phase: str, attack_types: List[str], interaction_count: int, current_env: Dict[str, Any]) -> Dict[str, Any]:
        env = dict(current_env or {})

        if phase == "recon":
            env.setdefault("presented_as", "enterprise_web_suite")
            env.setdefault("discoverable_endpoints", ["/api/v1/users", "/api/v1/audit", "/internal/health", "/swagger"])

        if "sqli" in attack_types:
            env["presented_as"] = "postgres_admin_console"
            env["fake_db_tables"] = ["users", "orders", "invoices", "api_tokens"]
            env["fake_db_error_leak"] = True

        if "credential_attack" in attack_types and interaction_count >= 3:
            env["fake_session_active"] = True
            env["presented_as"] = "admin_dashboard"

        if phase == "privilege_escalation":
            env["presented_as"] = "internal_api_gateway"
            env["fake_swagger_enabled"] = True
            env["internal_services"] = ["billing-api", "iam-api", "vault-gateway"]

        if interaction_count >= 5:
            env["fake_credentials_leaked"] = True
            env["high_value_artifacts"] = ["employee_export.csv", "backup_keys.json", "token_audit.log"]

        return env

    def analyze(self, source_ip: str, request_data: Dict[str, Any], session_id: Optional[str] = None) -> BehaviorResult:
        request_data = request_data or {}
        source_ip = (source_ip or "0.0.0.0").split(",")[0].strip()
        uri = str(request_data.get("uri") or "/")
        payload = str(request_data.get("body") or "")
        user_agent = str(request_data.get("user_agent") or "")

        conn = None
        cursor = None
        try:
            conn = self._conn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            tenant_id = self._resolve_tenant_id(cursor)

            cursor.execute(
                """
                SELECT *
                FROM attacker_sessions
                WHERE tenant_id = %s
                  AND split_part(source_ip::text, '/', 1) = %s
                  AND is_active = true
                ORDER BY last_seen DESC
                LIMIT 1
                """,
                (tenant_id, source_ip),
            )
            row = cursor.fetchone()

            if row:
                active_session_id = row.get("session_id") or session_id or str(uuid.uuid4())
                profile = dict(row.get("attacker_profile") or {})
                env = dict(row.get("environment_state") or {})
                interaction_count = int(row.get("interaction_count") or 0)
            else:
                active_session_id = session_id or str(uuid.uuid4())
                profile = {}
                env = {}
                interaction_count = 0

            history = self._recent_capture_history(cursor, source_ip, tenant_id)

            tool = self._detect_tool(user_agent, payload)
            attack_types = self._detect_attack_types(uri, payload, list(profile.get("attack_types") or []))
            next_count = interaction_count + 1
            phase = self._infer_phase(uri, attack_types, next_count)
            skill = self._infer_skill(tool, attack_types, payload, next_count)
            goal = self._infer_goal(phase, attack_types, uri)
            env = self._evolve_environment(phase, attack_types, next_count, env)

            tools = set(profile.get("detected_tools") or [])
            if tool and tool != "unknown":
                tools.add(tool)

            profile.update({
                "detected_tools": sorted(tools) if tools else ["manual"],
                "attack_types": attack_types,
                "skill_level": skill,
                "attack_phase": phase,
                "likely_goal": goal,
                "last_uri": uri,
                "last_user_agent": user_agent,
            })

            if row:
                cursor.execute(
                    """
                    UPDATE attacker_sessions
                    SET session_id = %s,
                        attacker_profile = %s,
                        environment_state = %s,
                        interaction_count = %s,
                        last_seen = CURRENT_TIMESTAMP,
                        is_active = true
                    WHERE id = %s
                    """,
                    (
                        active_session_id,
                        Json(profile),
                        Json(env),
                        next_count,
                        row.get("id"),
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO attacker_sessions (
                        tenant_id,
                        session_id,
                        source_ip,
                        attacker_profile,
                        environment_state,
                        interaction_count,
                        first_seen,
                        last_seen,
                        is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, true)
                    """,
                    (
                        tenant_id,
                        active_session_id,
                        source_ip,
                        Json(profile),
                        Json(env),
                        next_count,
                    ),
                )

            conn.commit()

            llm_context = {
                "interaction_count": next_count,
                "previous_attack_types": attack_types,
                "skill_level": skill,
                "environment_description": env.get("presented_as", "enterprise_web_suite"),
                "likely_goal": goal,
                "detected_tools": profile.get("detected_tools", []),
                "attack_phase": phase,
                "session_history": [
                    {
                        "attack_type": h.get("attack_type"),
                        "captured_at": self._to_iso_utc(h.get("captured_at")),
                    }
                    for h in history[:5]
                ],
            }

            return BehaviorResult(
                tenant_id=tenant_id,
                session_id=active_session_id,
                source_ip=source_ip,
                attacker_profile=profile,
                environment_state=env,
                interaction_count=next_count,
                llm_context=llm_context,
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_environment_after_response(self, source_ip: str, response_body: str, session_id: Optional[str] = None):
        source_ip = (source_ip or "0.0.0.0").split(",")[0].strip()
        preview = (response_body or "")[:600]
        low = preview.lower()

        conn = None
        cursor = None
        try:
            conn = self._conn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            tenant_id = self._resolve_tenant_id(cursor)

            cursor.execute(
                """
                SELECT id, environment_state
                FROM attacker_sessions
                WHERE tenant_id = %s
                  AND split_part(source_ip::text, '/', 1) = %s
                  AND (%s = '' OR session_id = %s)
                  AND is_active = true
                ORDER BY last_seen DESC
                LIMIT 1
                """,
                (tenant_id, source_ip, session_id or "", session_id or ""),
            )
            row = cursor.fetchone()
            if not row:
                return

            env = dict(row.get("environment_state") or {})
            env["last_response_preview"] = preview
            env["last_updated_at"] = datetime.now(timezone.utc).isoformat()

            if "swagger" in low or "openapi" in low:
                env["presented_as"] = "internal_api_gateway"
                env["fake_swagger_enabled"] = True
            if "dashboard" in low or "admin" in low:
                env["presented_as"] = "admin_dashboard"
                env["fake_session_active"] = True
            if "users" in low and "orders" in low:
                env["fake_db_tables"] = ["users", "orders", "invoices", "api_tokens"]

            cursor.execute(
                """
                UPDATE attacker_sessions
                SET environment_state = %s,
                    last_seen = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (Json(env), row.get("id")),
            )
            conn.commit()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


_default_analyzer = BehaviorAnalyzer()


def analyze(source_ip: str, request_data: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
    result = _default_analyzer.analyze(source_ip=source_ip, request_data=request_data, session_id=session_id)
    return {
        "tenant_id": result.tenant_id,
        "session_id": result.session_id,
        "source_ip": result.source_ip,
        "attacker_profile": result.attacker_profile,
        "environment_state": result.environment_state,
        "interaction_count": result.interaction_count,
        "llm_context": result.llm_context,
    }


def update_environment_after_response(source_ip: str, response_body: str, session_id: Optional[str] = None):
    _default_analyzer.update_environment_after_response(source_ip=source_ip, response_body=response_body, session_id=session_id)
