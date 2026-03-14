"""
Mayasec Control Plane API

REST API for:
- Querying events and alerts from storage layer
- Health checks for all services
- Metrics endpoint (threat distribution, top IPs)
- No direct sensor access

Architecture:
  Sensors → Core (ingest + process) → Storage (persist)
  └─ API (query) ← Core health / Storage queries

No file system dependencies. Talks to core + storage only.
"""

import os
import asyncio
import json
import hmac
import ipaddress
import logging
import time
import threading
import queue
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import bcrypt
import jwt
import redis

from flask import Flask, jsonify, request, make_response, g, has_request_context, current_app, send_file
from flask_cors import CORS
from functools import wraps
import requests
from flask_sock import Sock
from psycopg2.extras import RealDictCursor
from neo4j import AsyncGraphDatabase

from repository import EventRepository, AlertRepository, StatisticsRepository, ResponseRepository, DatabaseConfig
from policy_engine import PolicyEngine
from response_mode import resolve_response_mode, ALLOWED_RESPONSE_MODES
from story_builder import AttackStoryEngine
from core.report_generator import ThreatReportGenerator

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class ApiConfig:
    """Control plane API configuration"""
    
    def __init__(self):
        # Database (storage layer)
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'mayasec')
        self.db_user = os.getenv('DB_USER', 'mayasec')
        self.db_password = os.getenv('DB_PASSWORD', 'mayasec')
        self.default_reports_limit = int(os.getenv('DEFAULT_REPORTS_LIMIT', '100'))
        self.max_reports_limit = int(os.getenv('MAX_REPORTS_LIMIT', '500'))
        
        # Core service (threat analysis)
        self.core_url = os.getenv('CORE_URL', 'http://localhost:5001')
        self.llm_service_url = os.getenv('LLM_SERVICE_URL', 'http://localhost:8002')
        
        # Honeypot service (optional)
        self.honeypot_url = os.getenv('HONEYPOT_URL', 'http://localhost:5003')
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        # API settings
        self.api_port = int(os.getenv('API_PORT', '5000'))
        self.api_debug = os.getenv('API_DEBUG', 'False').lower() == 'true'
        self.api_title = 'Mayasec Control Plane API'
        self.api_version = '1.0.0'
        
        # Health check timeout (seconds)
        self.health_timeout = int(os.getenv('HEALTH_TIMEOUT', '5'))
        
        # Query limits
        self.max_events_limit = int(os.getenv('MAX_EVENTS_LIMIT', '1000'))
        self.max_alerts_limit = int(os.getenv('MAX_ALERTS_LIMIT', '500'))
        self.default_traffic_logs_limit = int(os.getenv('DEFAULT_TRAFFIC_LOGS_LIMIT', '200'))
        self.max_traffic_logs_limit = int(os.getenv('MAX_TRAFFIC_LOGS_LIMIT', '1000'))

        # ClickHouse
        self.clickhouse_url = os.getenv('CLICKHOUSE_URL', 'http://clickhouse:8123').rstrip('/')


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
JWT_SECRET = os.getenv('JWT_SECRET', 'mayasec_dev_jwt_secret')
JWT_ALGORITHM = 'HS256'
JWT_EXP_HOURS = 24

_neo4j_driver = None


def get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = AsyncGraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "mayasec_neo4j")
            )
        )
    return _neo4j_driver


# ═══════════════════════════════════════════════════════════════════════════════
# RAW WEBSOCKET STREAM (ONE-WAY)
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_WS_EVENT_TYPES = {
    'event_ingested',
    'phase_escalated',
    'escalation_triggered',
    'alert_created',
    'ip_blocked',
    'ip_unblocked',
    'response_mode',
    'response_decision',
}


class WebSocketBroadcaster:
    """Broadcast-only WebSocket manager (server → client)."""

    def __init__(self, logger: logging.Logger, response_mode: Optional[str] = None, queue_size: int = 1000):
        self._logger = logger
        self._response_mode = response_mode
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._queue = queue.Queue(maxsize=queue_size)
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def add_client(self, ws) -> None:
        with self._clients_lock:
            self._clients.add(ws)
        self._logger.info("WS client connected")

    def remove_client(self, ws) -> None:
        with self._clients_lock:
            self._clients.discard(ws)
        self._logger.info("WS client disconnected")

    def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        if event_type not in ALLOWED_WS_EVENT_TYPES:
            self._logger.warning("WS broadcast skipped (unsupported type): %s", event_type)
            return

        if isinstance(data, dict) and self._response_mode and event_type in {
            'alert_created',
            'ip_blocked',
            'ip_unblocked',
            'response_decision'
        }:
            data.setdefault('response_mode', self._response_mode)

        payload = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data or {},
        }

        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._logger.warning("WS broadcast dropped (queue full): %s", event_type)

    def broadcast_response_mode(self, mode: str) -> None:
        payload = {
            "type": "response_mode",
            "mode": mode,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._logger.warning("WS broadcast dropped (queue full): response_mode")

    def _run(self) -> None:
        while True:
            payload = self._queue.get()
            if payload is None:
                break

            message = json.dumps(payload, default=str)
            with self._clients_lock:
                clients = list(self._clients)

            if not clients:
                continue

            for ws in clients:
                try:
                    ws.send(message)
                    self._logger.info("WS broadcast %s", payload.get("type"))
                except Exception:
                    with self._clients_lock:
                        self._clients.discard(ws)
                    self._logger.info("WS client disconnected")


# ═══════════════════════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════

def error_handler(f):
    """Decorator for consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error: {str(e)}")
            return jsonify({'error': str(e), 'code': 'validation_error'}), 400
        except Exception as e:
            logger.error(f"Internal error in {f.__name__}: {str(e)}")
            return jsonify({'error': 'internal_error', 'message': str(e)}), 500
    return decorated_function


def require_token(func):
    """Require Authorization: Bearer <ADMIN_TOKEN> for protected endpoints."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        parts = auth_header.split(' ', 1)

        if len(parts) != 2 or parts[0] != 'Bearer':
            return jsonify({'error': 'unauthorized'}), 401

        token = parts[1]
        if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
            return jsonify({'error': 'unauthorized'}), 401

        return func(*args, **kwargs)

    return wrapper


def set_tenant_context(conn, tenant_id):
    """Set tenant context for PostgreSQL RLS in current transaction."""
    if not tenant_id:
        raise ValueError('tenant_id is required')
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.tenant_id = %s", (str(tenant_id),))


def _get_api_instance():
    """Fetch active API instance from Flask app config."""
    try:
        return current_app.config.get('MAYASEC_API_INSTANCE')
    except RuntimeError:
        return None


def resolve_tenant_from_api_key(key: str):
    """Resolve tenant_id from active API key hash match and update last_used_at."""
    if not key:
        return None

    api_instance = _get_api_instance()
    if api_instance is None or not hasattr(api_instance, 'event_repo'):
        return None

    conn = None
    try:
        conn = api_instance.event_repo.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT id, tenant_id, key_hash
            FROM api_keys
            WHERE is_active = TRUE
            '''
        )
        candidates = cursor.fetchall() or []

        for row in candidates:
            key_hash = str(row.get('key_hash') or '')
            if not key_hash:
                continue
            try:
                if bcrypt.checkpw(key.encode('utf-8'), key_hash.encode('utf-8')):
                    key_id = row.get('id')
                    tenant_id = row.get('tenant_id')
                    if key_id:
                        cursor.execute(
                            '''
                            UPDATE api_keys
                            SET last_used_at = NOW()
                            WHERE id = %s
                            ''',
                            (key_id,)
                        )
                        conn.commit()
                    cursor.close()
                    return str(tenant_id) if tenant_id else None
            except ValueError:
                continue

        cursor.close()
        return None
    except Exception:
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            api_instance.event_repo.return_connection(conn)


def _resolve_demo_tenant_id(api_instance) -> Optional[str]:
    """Resolve the default demo tenant UUID for ADMIN_TOKEN fallback."""
    if api_instance is None or not hasattr(api_instance, 'event_repo'):
        return None

    conn = None
    try:
        conn = api_instance.event_repo.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tenants WHERE slug = %s AND is_active = TRUE LIMIT 1", ('demo',))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        tenant_id = row[0] if not isinstance(row, dict) else row.get('id')
        return str(tenant_id) if tenant_id else None
    except Exception:
        return None
    finally:
        if conn:
            api_instance.event_repo.return_connection(conn)


def require_tenant(func):
    """Require tenant-scoped authorization and resolve tenant context."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        api_instance = _get_api_instance()
        if api_instance is None or not hasattr(api_instance, 'event_repo'):
            return jsonify({'error': 'unauthorized'}), 401

        tenant_id = None

        # 1) API key
        api_key = (request.headers.get('X-API-Key') or '').strip()
        if api_key:
            tenant_id = resolve_tenant_from_api_key(api_key)

        # 2) Bearer token (reserved for JWT support)
        token = _extract_bearer_token()
        if not tenant_id and token:
            claims = _decode_jwt_or_none(token)
            if claims and claims.get('tenant_id'):
                tenant_id = str(claims.get('tenant_id'))

        # 3) ADMIN_TOKEN fallback to demo tenant
        if not tenant_id and token and ADMIN_TOKEN and hmac.compare_digest(token, ADMIN_TOKEN):
            tenant_id = _resolve_demo_tenant_id(api_instance)

        if not tenant_id:
            return jsonify({'error': 'unauthorized'}), 401

        g.tenant_id = str(tenant_id)
        return func(*args, **kwargs)

    return wrapper


def _extract_bearer_token() -> Optional[str]:
    auth_header = request.headers.get('Authorization', '')
    parts = auth_header.split(' ', 1)
    if len(parts) != 2 or parts[0] != 'Bearer':
        return None
    return parts[1]


def _issue_jwt(user: Dict[str, Any]) -> str:
    now = datetime.utcnow()
    payload = {
        'sub': str(user.get('id')),
        'email': user.get('email'),
        'display_name': user.get('display_name'),
        'role': user.get('role', 'analyst'),
        'tenant_id': str(user.get('tenant_id')) if user.get('tenant_id') else None,
        'iat': now,
        'exp': now + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt_or_none(token: str) -> Optional[Dict[str, Any]]:
    if not token or not JWT_SECRET:
        return None

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if isinstance(decoded, dict):
            return decoded
        return None
    except jwt.InvalidTokenError:
        return None


def _normalize_uuid_array(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith('{') and raw.endswith('}'):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [part.strip().strip('"') for part in inner.split(',') if part.strip()]
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# API CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class MayasecAPI:
    """Control plane API for Mayasec"""
    
    def __init__(self, config: ApiConfig):
        self.config = config
        self.app = Flask(__name__)
        self.app.config['MAYASEC_API_INSTANCE'] = self
        CORS(self.app)

        try:
            self.sock = Sock(self.app)
        except Exception as e:
            logger.error(f"Failed to initialize WebSocket server: {e}")
            raise

        # Initialize storage layer
        db_config = DatabaseConfig(
            host=config.db_host,
            port=config.db_port,
            database=config.db_name,
            user=config.db_user,
            password=config.db_password
        )
        self.event_repo = EventRepository(db_config)
        self.alert_repo = AlertRepository(db_config)
        self.stats_repo = StatisticsRepository(db_config)
        self.response_repo = ResponseRepository(db_config)
        self._enable_repo_tenant_context()

        self._ensure_auth_schema()

        try:
            self.response_mode, self.response_mode_source = resolve_response_mode()
        except Exception as e:
            logger.error(f"Invalid response mode: {e}")
            raise

        self.ws_broadcaster = WebSocketBroadcaster(logger, response_mode=self.response_mode)

        self.event_stream_name = os.getenv('EVENT_STREAM_NAME', 'mayasec:events')
        self.redis_client = redis.from_url(self.config.redis_url, decode_responses=True)

        self.policy_engine = PolicyEngine(self.alert_repo)
        self.story_engine = AttackStoryEngine(
            event_repo=self.event_repo,
            llm_service_url=self.config.llm_service_url,
            interval_seconds=int(os.getenv('ATTACK_STORY_INTERVAL_SECONDS', '60')),
        )
        self.report_generator = ThreatReportGenerator(output_root=os.getenv('REPORTS_DIR', 'reports'))
        if os.getenv('ATTACK_STORY_ENGINE_ENABLED', 'true').lower() == 'true':
            self.story_engine.start()

        try:
            self.response_repo.set_response_mode(self.response_mode, source=self.response_mode_source)
        except Exception as e:
            logger.error(f"Failed to persist response mode: {e}")
            raise
        
        # Register routes
        self._register_routes()

        # Emit response mode on startup
        self.ws_broadcaster.broadcast_response_mode(self.response_mode)
    
    def _register_routes(self):
        """Register all API routes"""
        
        # Health checks
        self.app.route('/health', methods=['GET'])(self._health)
        self.app.route('/api/v1/health', methods=['GET'])(self._health)
        self.app.route('/api/v1/health/deep', methods=['GET'])(self._health_deep)
        
        # OpenAPI
        self.app.route('/api/v1/openapi', methods=['GET'])(self._openapi)
        self.app.route('/openapi.json', methods=['GET'])(self._openapi)
        
        # Events
        self.app.route('/api/v1/auth/login', methods=['POST'])(self._auth_login)
        self.app.route('/api/v1/auth/register', methods=['POST'])(self._auth_register)
        self.app.route('/api/v1/auth/me', methods=['GET'])(self._auth_me)

        self.app.route('/api/v1/events', methods=['GET'])(require_tenant(self._list_events))
        self.app.route('/api/v1/events/<event_id>', methods=['GET'])(require_tenant(self._get_event))
        self.app.route('/api/v1/events/<event_id>/explain', methods=['GET'])(require_token(require_tenant(self._explain_event)))
        self.app.route('/api/v1/stories', methods=['GET'])(require_tenant(self._list_stories))
        self.app.route('/api/v1/stories/<story_id>', methods=['GET'])(require_tenant(self._get_story))
        self.app.route('/api/v1/stories/<story_id>', methods=['PATCH'])(require_tenant(self._patch_story_status))
        self.app.route('/api/v1/reports', methods=['GET'])(require_tenant(self._list_reports))
        self.app.route('/api/v1/reports/generate', methods=['POST'])(require_tenant(self._generate_report))
        self.app.route('/api/v1/reports/schedule', methods=['POST'])(require_tenant(self._schedule_report))
        self.app.route('/reports/<path:report_path>', methods=['GET'])(require_tenant(self._download_report))
        
        # Alerts
        self.app.route('/api/v1/alerts', methods=['GET'])(require_tenant(self._list_alerts))
        self.app.route('/api/v1/alerts/block', methods=['POST'])(require_tenant(self._block_ip))
        self.app.route('/api/v1/alerts/blocked', methods=['GET'])(require_tenant(self._list_blocked_ips))
        self.app.route('/api/v1/alerts/unblock', methods=['POST'])(require_tenant(self._unblock_ip))
        self.app.route('/api/v1/alerts/status/<ip_address>', methods=['GET'])(require_tenant(self._get_ip_block_status))
        self.app.route('/api/v1/honeypot/sessions', methods=['GET'])(require_tenant(self._honeypot_sessions))
        self.app.route('/api/v1/honeypot/active-sessions', methods=['GET'])(require_tenant(self._honeypot_active_sessions))
        self.app.route('/api/v1/honeypot/sessions/<session_id>/timeline', methods=['GET'])(require_tenant(self._honeypot_session_timeline))
        self.app.route('/api/v1/sensor/register', methods=['POST'])(require_tenant(self._sensor_register))
        self.app.route('/api/v1/sensors', methods=['GET'])(require_tenant(self._list_sensors))

        # Response mode
        self.app.route('/api/v1/response-mode', methods=['PUT'])(require_token(self._set_response_mode))
        self.app.route('/api/v1/response-mode', methods=['GET'])(require_token(self._get_response_mode))

        # Event ingestion for streaming (protected to prevent event injection)
        self.app.route('/api/v1/emit-event', methods=['POST'])(require_tenant(self._emit_event))
        self.app.route('/api/v1/emit-alert', methods=['POST'])(require_tenant(self._emit_alert))
        self.app.route('/api/v1/emit-escalation', methods=['POST'])(require_token(self._emit_escalation))
        self.app.route('/api/v1/emit-response', methods=['POST'])(require_token(self._emit_response))
        self.app.route('/api/v1/emit-policy', methods=['POST'])(require_token(self._emit_policy))
        self.app.route('/api/v1/emit-policy-update', methods=['POST'])(require_token(self._emit_policy_update))

        # Raw WebSocket event stream
        self.sock.route('/ws/events')(self._ws_events)
        
        # Metrics
        self.app.route('/api/v1/metrics', methods=['GET'])(require_tenant(self._metrics))
        self.app.route('/api/v1/traffic-logs', methods=['GET'])(require_tenant(self._traffic_logs))
        self.app.route('/api/v1/metrics/threat-distribution', methods=['GET'])(require_tenant(self._threat_distribution))
        self.app.route('/api/v1/metrics/top-ips', methods=['GET'])(require_tenant(self._top_ips))
        self.app.route('/api/v1/metrics/threat-summary', methods=['GET'])(require_tenant(self._threat_summary))
        self.app.route('/api/v1/graph/attack', methods=['GET'])(self._attack_graph)
        self.app.route('/api/v1/sessions/graph', methods=['GET'])(require_token(self._sessions_graph))
        self.app.route('/api/v1/behavioral/history', methods=['GET'])(require_token(self._behavioral_history))
        self.app.route('/api/v1/behavioral/sessions', methods=['GET'])(require_token(self._behavioral_sessions))
        self.app.route('/api/v1/behavioral/drift', methods=['GET'])(require_token(self._behavioral_drift))
        self.app.route('/api/v1/mitre/summary', methods=['GET'])(require_token(require_tenant(self._mitre_summary)))
        self.app.route('/api/v1/copilot/query', methods=['POST'])(require_token(self._copilot_query))
        self.app.route('/api/v1/copilot/history', methods=['GET'])(require_token(self._copilot_history))
        self.app.route('/api/v1/copilot/history', methods=['DELETE'])(require_token(self._copilot_clear))
        
        logger.info("API routes registered")

    def _enable_repo_tenant_context(self):
        """Inject tenant context automatically for repository connections."""
        repos = [self.event_repo, self.alert_repo, self.stats_repo, self.response_repo]

        for repo in repos:
            original_get_connection = repo.get_connection

            @wraps(original_get_connection)
            def tenant_scoped_get_connection(_orig=original_get_connection, _repo=repo):
                conn = _orig()
                if has_request_context():
                    tenant_id = getattr(g, 'tenant_id', None)
                    if tenant_id:
                        try:
                            set_tenant_context(conn, tenant_id)
                        except Exception:
                            _repo.return_connection(conn)
                            raise
                return conn

            repo.get_connection = tenant_scoped_get_connection

    def _ensure_auth_schema(self):
        """Create users table and insert default admin if missing."""
        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL DEFAULT 'analyst',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMPTZ
                )
                '''
            )

            admin_email = 'admin@mayasec.io'
            cursor.execute('SELECT id FROM users WHERE email = %s', (admin_email,))
            existing = cursor.fetchone()
            if not existing:
                admin_hash = bcrypt.hashpw('Admin@123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute(
                    '''
                    INSERT INTO users (email, password_hash, display_name, role)
                    VALUES (%s, %s, %s, %s)
                    ''',
                    (admin_email, admin_hash, 'MAYASEC Admin', 'admin')
                )
                logger.info('Default admin account created: %s', admin_email)

            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error('Auth schema bootstrap failed: %s', e)
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)
    
    @staticmethod
    def _parse_iso_datetime_or_none(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    @error_handler
    def _list_reports(self):
        """List generated reports for current tenant."""
        try:
            limit = int(request.args.get('limit', self.config.default_reports_limit))
            offset = int(request.args.get('offset', 0))
        except ValueError:
            raise ValueError('Invalid limit or offset parameter')

        limit = max(1, min(limit, self.config.max_reports_limit))
        offset = max(0, offset)

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                '''
                SELECT
                    report_id::text AS report_id,
                    tenant_id,
                    generated_at,
                    file_path,
                    events_count,
                    attacks_count,
                    mitre_count,
                    start_time,
                    end_time,
                    report_metadata
                FROM reports
                ORDER BY generated_at DESC
                LIMIT %s OFFSET %s
                ''',
                (limit, offset),
            )
            rows = cur.fetchall() or []
            cur.execute('SELECT COUNT(*) AS total FROM reports')
            total = int((cur.fetchone() or {}).get('total') or 0)
            cur.close()

            reports = []
            for row in rows:
                reports.append({
                    'report_id': row.get('report_id'),
                    'tenant_id': row.get('tenant_id'),
                    'generated_at': row.get('generated_at').isoformat() + 'Z' if row.get('generated_at') else None,
                    'file_path': row.get('file_path'),
                    'events_count': int(row.get('events_count') or 0),
                    'attacks_count': int(row.get('attacks_count') or 0),
                    'mitre_count': int(row.get('mitre_count') or 0),
                    'start_time': row.get('start_time').isoformat() + 'Z' if row.get('start_time') else None,
                    'end_time': row.get('end_time').isoformat() + 'Z' if row.get('end_time') else None,
                    'report_metadata': row.get('report_metadata') or {},
                    'download_url': f"/reports/{row.get('file_path')}" if row.get('file_path') else None,
                })

            return jsonify({'reports': reports, 'count': total}), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _generate_report(self):
        """Generate tenant report and store report metadata."""
        payload = request.get_json(silent=True) or {}
        tenant_id = str(payload.get('tenant_id') or '').strip()
        if not tenant_id:
            raise ValueError('tenant_id is required')
        if tenant_id != str(g.tenant_id):
            return jsonify({'error': 'forbidden'}), 403

        start_time = self._parse_iso_datetime_or_none(payload.get('start_time'))
        end_time = self._parse_iso_datetime_or_none(payload.get('end_time'))
        if not start_time or not end_time:
            raise ValueError('start_time and end_time are required (ISO datetime)')
        if end_time < start_time:
            raise ValueError('end_time must be greater than or equal to start_time')

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)

            file_path, report_metadata = self.report_generator.generate_report(
                conn=conn,
                tenant_id=tenant_id,
                start_time=start_time,
                end_time=end_time,
            )

            rel_file = os.path.relpath(file_path, start=os.getcwd())
            report_id = str(uuid.uuid4())
            cur = conn.cursor()
            cur.execute(
                '''
                INSERT INTO reports
                (report_id, tenant_id, generated_at, file_path, events_count, attacks_count, mitre_count, start_time, end_time, report_metadata)
                VALUES (%s::uuid, %s, NOW(), %s, %s, %s, %s, %s, %s, %s::jsonb)
                ''',
                (
                    report_id,
                    tenant_id,
                    rel_file,
                    int(report_metadata.get('total_events') or 0),
                    int(report_metadata.get('total_attacks') or 0),
                    int(len(report_metadata.get('mitre_techniques_triggered') or [])),
                    start_time,
                    end_time,
                    json.dumps(report_metadata),
                ),
            )
            conn.commit()
            cur.close()

            return jsonify({
                'report_id': report_id,
                'download_url': f"/reports/{rel_file}",
                'report_metadata': report_metadata,
            }), 200
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _schedule_report(self):
        """Store report schedule configuration for current tenant."""
        payload = request.get_json(silent=True) or {}
        tenant_id = str(payload.get('tenant_id') or '').strip()
        frequency = str(payload.get('frequency') or '').strip().lower()
        email = str(payload.get('email') or '').strip()

        if not tenant_id:
            raise ValueError('tenant_id is required')
        if tenant_id != str(g.tenant_id):
            return jsonify({'error': 'forbidden'}), 403
        if frequency != 'weekly':
            raise ValueError('Only weekly frequency is supported')
        if '@' not in email:
            raise ValueError('Valid email is required')

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            schedule_id = str(uuid.uuid4())
            next_run = datetime.utcnow() + timedelta(days=7)
            cur = conn.cursor()
            cur.execute(
                '''
                INSERT INTO report_schedules (schedule_id, tenant_id, frequency, email, created_at, next_run_at, is_active)
                VALUES (%s::uuid, %s, %s, %s, NOW(), %s, TRUE)
                ON CONFLICT (tenant_id, frequency, email)
                DO UPDATE SET
                    is_active = TRUE,
                    next_run_at = EXCLUDED.next_run_at,
                    updated_at = NOW()
                RETURNING schedule_id::text
                ''',
                (schedule_id, tenant_id, frequency, email, next_run),
            )
            returned = cur.fetchone()
            if returned and returned[0]:
                schedule_id = str(returned[0])
            conn.commit()
            cur.close()

            return jsonify({
                'schedule_id': schedule_id,
                'tenant_id': tenant_id,
                'frequency': frequency,
                'email': email,
            }), 200
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _download_report(self, report_path: str):
        """Serve a generated report PDF for the authenticated tenant."""
        if not report_path:
            return jsonify({'error': 'not_found'}), 404

        normalized = os.path.normpath(report_path).replace('\\', '/')
        if normalized.startswith('../') or normalized.startswith('/'):
            return jsonify({'error': 'forbidden'}), 403

        tenant_prefix = f"reports/{g.tenant_id}/"
        if not normalized.startswith(tenant_prefix):
            return jsonify({'error': 'forbidden'}), 403

        abs_path = Path(os.getcwd()) / normalized
        if not abs_path.exists() or not abs_path.is_file():
            return jsonify({'error': 'not_found'}), 404

        return send_file(str(abs_path), mimetype='application/pdf', as_attachment=True)

    # ═════════════════════════════════════════════════════════════════════════
    # HEALTH CHECKS
    # ═════════════════════════════════════════════════════════════════════════

    @error_handler
    def _health(self):
        """Quick health check (storage only)"""
        try:
            storage_healthy = self.event_repo.is_healthy()
            status_code = 200 if storage_healthy else 503
            
            return jsonify({
                'status': 'healthy' if storage_healthy else 'degraded',
                'timestamp': datetime.utcnow().isoformat(),
                'services': {
                    'storage': 'healthy' if storage_healthy else 'unhealthy'
                }
            }), status_code
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return jsonify({
                'status': 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e)
            }), 503
    
    @error_handler
    def _health_deep(self):
        """Deep health check (core + storage + honeypot)"""
        health_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'services': {}
        }
        overall_healthy = True
        
        # Check storage
        try:
            storage_healthy = self.event_repo.is_healthy()
            health_info['services']['storage'] = {
                'status': 'healthy' if storage_healthy else 'unhealthy',
                'response_time': '5-10ms'
            }
            overall_healthy = overall_healthy and storage_healthy
        except Exception as e:
            health_info['services']['storage'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            overall_healthy = False
        
        # Check core service
        try:
            response = requests.get(
                f"{self.config.core_url}/health",
                timeout=self.config.health_timeout
            )
            core_healthy = response.status_code == 200
            health_info['services']['core'] = {
                'status': 'healthy' if core_healthy else 'unhealthy',
                'url': self.config.core_url
            }
            overall_healthy = overall_healthy and core_healthy
        except Exception as e:
            health_info['services']['core'] = {
                'status': 'unhealthy',
                'error': str(e),
                'url': self.config.core_url
            }
            overall_healthy = False
        
        # Check honeypot service (optional)
        try:
            response = requests.get(
                f"{self.config.honeypot_url}/health",
                timeout=self.config.health_timeout
            )
            honeypot_healthy = response.status_code == 200
            health_info['services']['honeypot'] = {
                'status': 'healthy' if honeypot_healthy else 'unhealthy',
                'url': self.config.honeypot_url,
                'optional': True
            }
        except Exception as e:
            health_info['services']['honeypot'] = {
                'status': 'unhealthy',
                'error': str(e),
                'url': self.config.honeypot_url,
                'optional': True
            }
        
        health_info['status'] = 'healthy' if overall_healthy else 'degraded'
        status_code = 200 if overall_healthy else 503
        
        return jsonify(health_info), status_code
    
    # ═════════════════════════════════════════════════════════════════════════
    # OPENAPI
    # ═════════════════════════════════════════════════════════════════════════
    
    @error_handler
    def _openapi(self):
        """Serve OpenAPI specification"""
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": self.config.api_title,
                "version": self.config.api_version,
                "description": "Control plane API for Mayasec threat analysis platform"
            },
            "servers": [
                {
                    "url": f"http://localhost:{self.config.api_port}",
                    "description": "Local development"
                }
            ],
            "paths": {
                "/api/v1/health": {
                    "get": {
                        "summary": "Health check",
                        "description": "Quick health check of storage layer",
                        "tags": ["Health"],
                        "responses": {
                            "200": {"description": "Healthy"},
                            "503": {"description": "Unhealthy"}
                        }
                    }
                },
                "/api/v1/health/deep": {
                    "get": {
                        "summary": "Deep health check",
                        "description": "Check health of all services (core, storage, honeypot)",
                        "tags": ["Health"],
                        "responses": {
                            "200": {"description": "Healthy"},
                            "503": {"description": "Degraded"}
                        }
                    }
                },
                "/api/v1/events": {
                    "get": {
                        "summary": "List events",
                        "description": "Query events with optional filters",
                        "tags": ["Events"],
                        "parameters": [
                            {"name": "ip_address", "in": "query", "schema": {"type": "string"}, "description": "Filter by source IP"},
                            {"name": "username", "in": "query", "schema": {"type": "string"}, "description": "Filter by username"},
                            {"name": "threat_level", "in": "query", "schema": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "description": "Filter by threat level"},
                            {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}, "description": "Days back"},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}, "description": "Result limit"}
                        ],
                        "responses": {
                            "200": {"description": "Event list"},
                            "400": {"description": "Invalid parameters"}
                        }
                    }
                },
                "/api/v1/events/{event_id}": {
                    "get": {
                        "summary": "Get event details",
                        "tags": ["Events"],
                        "parameters": [
                            {"name": "event_id", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {
                            "200": {"description": "Event details"},
                            "404": {"description": "Not found"}
                        }
                    }
                },
                "/api/v1/stories": {
                    "get": {
                        "summary": "List attack stories",
                        "description": "List multi-stage attack stories with optional status and severity filters",
                        "tags": ["Stories"],
                        "parameters": [
                            {"name": "status", "in": "query", "schema": {"type": "string", "enum": ["active", "investigating", "resolved"]}},
                            {"name": "severity", "in": "query", "schema": {"type": "string", "enum": ["low", "medium", "high", "critical"]}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                            {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}}
                        ],
                        "responses": {
                            "200": {"description": "Attack stories list"},
                            "400": {"description": "Invalid parameters"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/stories/{id}": {
                    "get": {
                        "summary": "Get attack story details",
                        "tags": ["Stories"],
                        "parameters": [
                            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {
                            "200": {"description": "Attack story detail"},
                            "404": {"description": "Not found"},
                            "401": {"description": "Unauthorized"}
                        }
                    },
                    "patch": {
                        "summary": "Update attack story status",
                        "tags": ["Stories"],
                        "parameters": [
                            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "enum": ["active", "investigating", "resolved"]}
                                        },
                                        "required": ["status"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {"description": "Status updated"},
                            "400": {"description": "Invalid status"},
                            "404": {"description": "Not found"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/alerts": {
                    "get": {
                        "summary": "List open alerts",
                        "tags": ["Alerts"],
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}}
                        ],
                        "responses": {
                            "200": {"description": "Alert list"}
                        }
                    }
                },
                "/api/v1/alerts/block": {
                    "post": {
                        "summary": "Block IP address",
                        "tags": ["Alerts"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ip_address": {"type": "string"},
                                            "reason": {"type": "string"},
                                            "is_permanent": {"type": "boolean"}
                                        },
                                        "required": ["ip_address", "reason"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {"description": "Blocked"},
                            "400": {"description": "Invalid parameters"}
                        }
                    }
                },
                "/api/v1/alerts/blocked": {
                    "get": {
                        "summary": "List blocked IPs",
                        "tags": ["Alerts"],
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 200}}
                        ],
                        "responses": {
                            "200": {"description": "Blocked IP list"}
                        }
                    }
                },
                "/api/v1/alerts/unblock": {
                    "post": {
                        "summary": "Unblock IP address",
                        "tags": ["Alerts"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ip_address": {"type": "string"},
                                            "reason": {"type": "string"}
                                        },
                                        "required": ["ip_address"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {"description": "Unblocked"},
                            "404": {"description": "Not found"},
                            "400": {"description": "Invalid parameters"}
                        }
                    }
                },
                "/api/v1/alerts/status/{ip_address}": {
                    "get": {
                        "summary": "Check if IP is blocked",
                        "tags": ["Alerts"],
                        "parameters": [
                            {"name": "ip_address", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {
                            "200": {"description": "Status"}
                        }
                    }
                },
                "/api/v1/honeypot/active-sessions": {
                    "get": {
                        "summary": "List active adaptive deception sessions",
                        "tags": ["Honeypot"],
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}}
                        ],
                        "responses": {
                            "200": {"description": "Active session list"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/honeypot/sessions/{session_id}/timeline": {
                    "get": {
                        "summary": "Get honeypot interaction timeline for a session",
                        "tags": ["Honeypot"],
                        "parameters": [
                            {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 200}}
                        ],
                        "responses": {
                            "200": {"description": "Session timeline"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/sensor/register": {
                    "post": {
                        "summary": "Register or refresh a MAYASEC sensor",
                        "tags": ["Sensors"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "hostname": {"type": "string"},
                                            "mode": {"type": "string", "enum": ["proxy", "logtail"]},
                                            "version": {"type": "string"}
                                        },
                                        "required": ["hostname", "mode", "version"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {"description": "Sensor registered"},
                            "400": {"description": "Invalid payload"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/sensors": {
                    "get": {
                        "summary": "List tenant sensors and active count",
                        "tags": ["Sensors"],
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 200}}
                        ],
                        "responses": {
                            "200": {"description": "Sensor list"},
                            "401": {"description": "Unauthorized"}
                        }
                    }
                },
                "/api/v1/metrics": {
                    "get": {
                        "summary": "All metrics",
                        "tags": ["Metrics"],
                        "parameters": [
                            {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}}
                        ],
                        "responses": {
                            "200": {"description": "Metrics"}
                        }
                    }
                },
                "/api/v1/metrics/threat-distribution": {
                    "get": {
                        "summary": "Threat level distribution",
                        "tags": ["Metrics"],
                        "parameters": [
                            {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}}
                        ],
                        "responses": {
                            "200": {"description": "Distribution"}
                        }
                    }
                },
                "/api/v1/metrics/top-ips": {
                    "get": {
                        "summary": "Top attacking IPs",
                        "tags": ["Metrics"],
                        "parameters": [
                            {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 10}}
                        ],
                        "responses": {
                            "200": {"description": "Top IPs"}
                        }
                    }
                },
                "/api/v1/metrics/threat-summary": {
                    "get": {
                        "summary": "Threat summary for IP",
                        "tags": ["Metrics"],
                        "parameters": [
                            {"name": "ip_address", "in": "query", "required": True, "schema": {"type": "string"}},
                            {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}}
                        ],
                        "responses": {
                            "200": {"description": "Summary"}
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "HealthStatus": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "services": {"type": "object"}
                        }
                    },
                    "Event": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "event_type": {"type": "string"},
                            "source_ip": {"type": "string"},
                            "destination_ip": {"type": "string"},
                            "threat_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                            "threat_score": {"type": "number"},
                            "description": {"type": "string"}
                        }
                    },
                    "Alert": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "rule_id": {"type": "string"},
                            "title": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                            "status": {"type": "string", "enum": ["open", "acknowledged", "resolved"]},
                            "created_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        }
        
        return jsonify(spec), 200
    
    # ═════════════════════════════════════════════════════════════════════════
    # AUTH
    # ═════════════════════════════════════════════════════════════════════════

    @error_handler
    def _auth_login(self):
        payload = request.get_json(silent=True) or {}
        email = str(payload.get('email', '')).strip().lower()
        password = str(payload.get('password', ''))

        if not email or not password:
            raise ValueError('email and password are required')

        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    u.id,
                    u.email,
                    u.password_hash,
                    u.display_name,
                    u.role,
                    t.tenant_id::text AS tenant_id
                FROM users u
                LEFT JOIN LATERAL (
                    SELECT tenant_id
                    FROM tenant_users tu
                    WHERE tu.email = u.email
                    ORDER BY tu.created_at ASC
                    LIMIT 1
                ) t ON TRUE
                WHERE u.email = %s
                LIMIT 1
                ''',
                (email,)
            )
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'invalid_credentials'}), 401

            stored_hash = str(user.get('password_hash') or '')
            if not stored_hash or not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
                return jsonify({'error': 'invalid_credentials'}), 401

            cursor.execute('UPDATE users SET last_login = NOW() WHERE id = %s', (user.get('id'),))
            conn.commit()
            cursor.close()

            token = _issue_jwt(user)
            user_out = {
                'id': user.get('id'),
                'email': user.get('email'),
                'display_name': user.get('display_name'),
                'role': user.get('role'),
                'tenant_id': user.get('tenant_id'),
            }
            return jsonify({'token': token, 'user': user_out, 'expires_in': JWT_EXP_HOURS * 3600}), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _auth_register(self):
        payload = request.get_json(silent=True) or {}
        email = str(payload.get('email', '')).strip().lower()
        password = str(payload.get('password', ''))
        display_name = str(payload.get('display_name', '')).strip() or email.split('@')[0] if email else 'User'
        role = str(payload.get('role', 'analyst')).strip().lower() or 'analyst'
        if role not in {'admin', 'analyst'}:
            role = 'analyst'

        if not email or '@' not in email:
            raise ValueError('valid email is required')
        if len(password) < 8:
            raise ValueError('password must be at least 8 characters')

        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                INSERT INTO users (email, password_hash, display_name, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id, email, display_name, role
                ''',
                (email, password_hash, display_name, role)
            )
            user = cursor.fetchone()
            conn.commit()
            cursor.close()

            token = _issue_jwt(user)
            return jsonify({'token': token, 'user': user, 'expires_in': JWT_EXP_HOURS * 3600}), 201
        except Exception as e:
            if conn:
                conn.rollback()
            if 'duplicate key value violates unique constraint' in str(e).lower():
                return jsonify({'error': 'email_already_exists'}), 409
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _auth_me(self):
        token = _extract_bearer_token()
        claims = _decode_jwt_or_none(token or '')
        if not claims:
            return jsonify({'error': 'unauthorized'}), 401

        user_id = claims.get('sub')
        if not user_id:
            return jsonify({'error': 'unauthorized'}), 401

        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    u.role,
                    u.created_at,
                    u.last_login,
                    t.tenant_id::text AS tenant_id
                FROM users u
                LEFT JOIN LATERAL (
                    SELECT tenant_id
                    FROM tenant_users tu
                    WHERE tu.email = u.email
                    ORDER BY tu.created_at ASC
                    LIMIT 1
                ) t ON TRUE
                WHERE u.id = %s
                LIMIT 1
                ''',
                (user_id,)
            )
            user = cursor.fetchone()
            cursor.close()
            if not user:
                return jsonify({'error': 'unauthorized'}), 401
            return jsonify({'user': user}), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    # ═════════════════════════════════════════════════════════════════════════
    # EVENTS
    
    @error_handler
    def _list_events(self):
        """Query events with optional filters"""
        # Parse query parameters
        ip_address = request.args.get('ip_address')
        username = request.args.get('username')
        threat_level = request.args.get('threat_level')
        
        try:
            days = int(request.args.get('days', 7))
            limit = int(request.args.get('limit', 100))
        except ValueError:
            raise ValueError("Invalid days or limit parameter")
        
        if limit > self.config.max_events_limit:
            limit = self.config.max_events_limit
        
        # Validate threat level
        if threat_level and threat_level not in ['low', 'medium', 'high', 'critical']:
            raise ValueError(f"Invalid threat_level: {threat_level}")
        
        # Query repository
        events = self.event_repo.query_logs(
            ip_address=ip_address,
            username=username,
            threat_level=threat_level,
            days=days,
            limit=limit
        )
        
        return jsonify({
            'count': len(events),
            'events': events,
            'filters': {
                'ip_address': ip_address,
                'username': username,
                'threat_level': threat_level,
                'days': days
            }
        }), 200
    
    @error_handler
    def _get_event(self, event_id: str):
        """Get single event by ID"""
        event = self.event_repo.get_event_by_id(event_id)
        
        if not event:
            return jsonify({'error': 'Event not found'}), 404
        
        return jsonify({
            'event': event
        }), 200

    @error_handler
    def _list_stories(self):
        """List attack stories for the active tenant."""
        status = (request.args.get('status') or '').strip().lower()
        severity = (request.args.get('severity') or '').strip().lower()

        allowed_status = {'active', 'investigating', 'resolved'}
        allowed_severity = {'critical', 'high', 'medium', 'low'}
        if status and status not in allowed_status:
            raise ValueError("Invalid status")
        if severity and severity not in allowed_severity:
            raise ValueError("Invalid severity")

        limit = min(max(int(request.args.get('limit', 50)), 1), 500)
        offset = max(int(request.args.get('offset', 0)), 0)

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    id::text AS id,
                    title,
                    split_part(attacker_ip::text, '/', 1) AS attacker_ip,
                    start_time,
                    end_time,
                    event_ids,
                    phases,
                    narrative,
                    severity,
                    mitre_techniques,
                    status,
                    created_at
                FROM attack_stories
                WHERE (%s = '' OR status = %s)
                  AND (%s = '' OR severity = %s)
                ORDER BY start_time DESC
                LIMIT %s OFFSET %s
                ''',
                (status, status, severity, severity, limit, offset),
            )
            rows = cursor.fetchall() or []
            cursor.close()

            stories = []
            for row in rows:
                event_ids = _normalize_uuid_array(row.get('event_ids'))
                stories.append({
                    'id': row.get('id'),
                    'title': row.get('title'),
                    'attacker_ip': row.get('attacker_ip'),
                    'start_time': row.get('start_time').isoformat() + 'Z' if row.get('start_time') else None,
                    'end_time': row.get('end_time').isoformat() + 'Z' if row.get('end_time') else None,
                    'event_ids': event_ids,
                    'event_count': len(event_ids),
                    'phases': row.get('phases') or [],
                    'narrative': row.get('narrative') or '',
                    'severity': row.get('severity') or 'low',
                    'mitre_techniques': row.get('mitre_techniques') or [],
                    'status': row.get('status') or 'active',
                    'created_at': row.get('created_at').isoformat() + 'Z' if row.get('created_at') else None,
                })

            return jsonify(stories), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _get_story(self, story_id: str):
        """Get full attack story detail by id."""
        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    id::text AS id,
                    title,
                    split_part(attacker_ip::text, '/', 1) AS attacker_ip,
                    start_time,
                    end_time,
                    event_ids,
                    phases,
                    narrative,
                    severity,
                    mitre_techniques,
                    status,
                    created_at
                FROM attack_stories
                WHERE id = %s::uuid
                LIMIT 1
                ''',
                (story_id,),
            )
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return jsonify({'error': 'Story not found'}), 404

            phases = row.get('phases') or []
            if isinstance(phases, str):
                try:
                    phases = json.loads(phases)
                except Exception:
                    phases = []

            result = {
                'id': row.get('id'),
                'title': row.get('title'),
                'attacker_ip': row.get('attacker_ip'),
                'start_time': row.get('start_time').isoformat() + 'Z' if row.get('start_time') else None,
                'end_time': row.get('end_time').isoformat() + 'Z' if row.get('end_time') else None,
                'event_ids': _normalize_uuid_array(row.get('event_ids')),
                'phases': phases,
                'timeline': phases,
                'narrative': row.get('narrative') or '',
                'severity': row.get('severity') or 'low',
                'mitre_techniques': row.get('mitre_techniques') or [],
                'status': row.get('status') or 'active',
                'created_at': row.get('created_at').isoformat() + 'Z' if row.get('created_at') else None,
            }
            return jsonify(result), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _patch_story_status(self, story_id: str):
        """Update attack story lifecycle status."""
        try:
            uuid.UUID(str(story_id))
        except Exception:
            raise ValueError('invalid story id')

        payload = request.get_json(silent=True) or {}
        status = str(payload.get('status') or '').strip().lower()
        if status not in {'active', 'investigating', 'resolved'}:
            raise ValueError('status must be one of: active, investigating, resolved')

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                UPDATE attack_stories
                SET status = %s
                WHERE id = %s::uuid
                RETURNING id::text AS id, status
                ''',
                (status, story_id),
            )
            row = cursor.fetchone()
            conn.commit()
            cursor.close()

            if not row:
                return jsonify({'error': 'Story not found'}), 404

            return jsonify({'id': row.get('id'), 'status': row.get('status')}), 200
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _explain_event(self, event_id: str):
        """Generate LLM threat narrative for an event."""
        event = self.event_repo.get_event_by_id(event_id)
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        payload = {
            'event_type': event.get('event_type', ''),
            'source_ip': event.get('ip_address', event.get('source_ip', '')),
            'uri': event.get('uri', event.get('path', '/')),
            'http_verb': event.get('http_method', event.get('http_verb', 'GET')),
            'score': event.get('score', event.get('waf_score', 0)) or 0,
            'attack_type': event.get('attack_type', 'unknown'),
            'intent': event.get('intent', event.get('predicted_intent', 'Benign')),
            'anomaly_score': event.get('anomaly_score', 0.0) or 0.0,
            'graph_threat': bool(event.get('graph_threat', False)),
            'deception_trigger': bool(event.get('deception_trigger', False)),
            'timestamp': event.get('timestamp', datetime.utcnow().isoformat()),
            'session_request_count': event.get('session_request_count', 0) or 0,
            'uri_path_diversity': event.get('uri_path_diversity', 0) or 0,
            'ua_change_detected': bool(event.get('ua_change_detected', False)),
            'request_rate_60s': event.get('request_rate_60s', 0) or 0,
            'body': event.get('request_body', event.get('body', '')),
            'content_type': event.get('content_type', ''),
            'user_agent': event.get('user_agent', ''),
            'query_params': event.get('query_params', ''),
        }

        try:
            resp = requests.post(
                f"{self.config.llm_service_url}/explain",
                json=payload,
                timeout=max(10, self.config.health_timeout),
            )

            if resp.status_code != 200:
                logger.warning("LLM explain failed with status=%s", resp.status_code)
                return jsonify({
                    'event_id': event_id,
                    'narrative': (
                        f"Event {event_id}: {payload['attack_type']} from "
                        f"{payload['source_ip']} targeting {payload['uri']} "
                        f"with score {payload['score']}/100."
                    ),
                    'confidence': 0.0,
                    'mitre_ttps': [],
                    'latency_ms': None,
                    'provider': 'fallback',
                }), 200

            data = resp.json() if resp.content else {}
            data['event_id'] = event_id
            data.setdefault('provider', 'llm-service')
            return jsonify(data), 200
        except requests.exceptions.RequestException as e:
            logger.warning(f"LLM explain proxy error: {e}")
            return jsonify({
                'event_id': event_id,
                'narrative': (
                    f"Event {event_id}: {payload['attack_type']} from "
                    f"{payload['source_ip']} targeting {payload['uri']} "
                    f"with score {payload['score']}/100."
                ),
                'confidence': 0.0,
                'mitre_ttps': [],
                'latency_ms': None,
                'provider': 'fallback',
                'warning': 'llm_unavailable',
            }), 200

    @error_handler
    def _sensor_register(self):
        """Register (or refresh) a customer-deployed MAYASEC sensor for tenant."""
        payload = request.get_json(silent=True) or {}

        hostname = str(payload.get('hostname') or request.headers.get('X-Sensor-Hostname') or request.remote_addr or 'unknown').strip()
        mode = str(payload.get('mode') or request.headers.get('X-Sensor-Mode') or 'proxy').strip().lower()
        version = str(payload.get('version') or request.headers.get('X-Sensor-Version') or '1.0.0').strip()

        if not hostname:
            return jsonify({'error': 'hostname required'}), 400

        if mode not in {'proxy', 'logtail'}:
            return jsonify({'error': 'invalid mode'}), 400

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                INSERT INTO sensors (tenant_id, hostname, mode, version, last_seen)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, hostname, mode)
                DO UPDATE SET
                    version = EXCLUDED.version,
                    last_seen = NOW()
                RETURNING id::text AS id, hostname, mode, version, last_seen
                ''',
                (g.tenant_id, hostname, mode, version),
            )
            row = cursor.fetchone() or {}
            conn.commit()
            cursor.close()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

        last_seen_value = row.get('last_seen')

        return jsonify({
            'status': 'registered',
            'sensor': {
                'id': row.get('id'),
                'hostname': row.get('hostname', hostname),
                'mode': row.get('mode', mode),
                'version': row.get('version', version),
                'last_seen': last_seen_value.isoformat() + 'Z' if last_seen_value else None,
            }
        }), 200

    @error_handler
    def _list_sensors(self):
        """List tenant sensors and return active sensor count."""
        limit = min(int(request.args.get('limit', 200)), 500)

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    id::text AS id,
                    hostname,
                    mode,
                    version,
                    last_seen,
                    created_at,
                    (last_seen >= NOW() - interval '2 minutes') AS is_active
                FROM sensors
                ORDER BY last_seen DESC NULLS LAST
                LIMIT %s
                ''',
                (limit,)
            )
            rows = cursor.fetchall() or []
            cursor.close()
        finally:
            if conn:
                self.event_repo.return_connection(conn)

        sensors = []
        active = 0
        for row in rows:
            is_active = bool(row.get('is_active'))
            if is_active:
                active += 1
            sensors.append({
                'id': row.get('id'),
                'hostname': row.get('hostname'),
                'mode': row.get('mode'),
                'version': row.get('version'),
                'is_active': is_active,
                'last_seen': row.get('last_seen').isoformat() + 'Z' if row.get('last_seen') else None,
                'created_at': row.get('created_at').isoformat() + 'Z' if row.get('created_at') else None,
            })

        return jsonify({
            'active': active,
            'total': len(sensors),
            'sensors': sensors,
        }), 200

    def _touch_sensor_last_seen(self, tenant_id: str, hostname: str, mode: str = 'proxy', version: str = '1.0.0') -> None:
        """Best-effort sensor heartbeat refresh tied to emit-event ingestion."""
        if not tenant_id or not hostname:
            return

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, tenant_id)
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO sensors (tenant_id, hostname, mode, version, last_seen)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, hostname, mode)
                DO UPDATE SET
                    version = EXCLUDED.version,
                    last_seen = NOW()
                ''',
                (tenant_id, hostname, mode, version),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.debug('sensor heartbeat refresh skipped: %s', e)
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _emit_event(self):
        """Receive event payload, persist it, and broadcast to WebSocket clients."""
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict) or not payload:
            raise ValueError("Event payload required")

        incoming_events = payload.get('events') if isinstance(payload.get('events'), list) else None
        if incoming_events is None:
            incoming_events = [payload]

        stream_ids = []
        normalized_events = []

        for incoming in incoming_events:
            if not isinstance(incoming, dict) or not incoming:
                continue

            # Accept both flat payloads and nested {"type": ..., "data": {...}} payloads.
            event_data = incoming.get('data') if isinstance(incoming.get('data'), dict) else incoming
            if not isinstance(event_data, dict):
                event_data = {}

            source_ip = (
                event_data.get('source_ip')
                or event_data.get('ip_address')
                or event_data.get('client_ip')
                or request.headers.get('X-Forwarded-For')
                or 'unknown'
            )
            destination = (
                event_data.get('destination')
                or event_data.get('service')
                or event_data.get('target')
                or 'honeypot'
            )

            try:
                threat_score = float(event_data.get('threat_score', event_data.get('score', 0)) or 0)
            except (TypeError, ValueError):
                threat_score = 0.0

            severity = str(event_data.get('severity') or '').lower()
            if not severity:
                severity = (
                    'critical' if threat_score >= 90 else
                    'high' if threat_score >= 75 else
                    'medium' if threat_score >= 50 else
                    'low'
                )

            metadata_value = event_data.get('metadata')
            metadata = metadata_value if isinstance(metadata_value, dict) else {}

            mitre_ttps = (
                event_data.get('mitre_ttps')
                or event_data.get('ttps')
                or metadata.get('mitre_ttps')
                or metadata.get('ttps')
                or []
            )
            if not isinstance(mitre_ttps, list):
                mitre_ttps = [mitre_ttps] if mitre_ttps else []

            username = event_data.get('username') or metadata.get('username') or 'unknown'
            password = event_data.get('password') or metadata.get('password') or ''

            normalized_event = {
                'event_id': event_data.get('event_id') or str(uuid.uuid4()),
                'event_type': event_data.get('event_type') or event_data.get('attack_type') or 'unknown',
                'timestamp': event_data.get('timestamp') or datetime.utcnow().isoformat() + 'Z',
                'source': event_data.get('source') or 'ingress-proxy',
                'sensor_id': event_data.get('sensor_id') or 'ingress-proxy-01',
                'severity': severity,
                'raw_log': event_data.get('raw_log') or event_data.get('uri') or event_data.get('message') or '',
                'ip_address': {
                    'source': source_ip,
                    'destination': destination,
                },
                'source_ip': source_ip,
                'destination': destination,
                'uri': event_data.get('uri') or '/',
                'username': username,
                'password': password,
                'threat_score': threat_score,
                'mitre_ttps': mitre_ttps,
            }

            analysis = {
                'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
                'threat_score': threat_score,
                'threat_level': severity,
                'analysis_reason': 'emit-event-ingest',
                'mitre_ttps': mitre_ttps,
            }

            stream_message = {
                'event_id': str(normalized_event.get('event_id') or uuid.uuid4()),
                'tenant_id': str(g.tenant_id),
                'source_ip': str(source_ip),
                'event_type': str(normalized_event.get('event_type') or 'unknown'),
                'uri': str(normalized_event.get('uri') or '/'),
                'http_method': str(event_data.get('http_method') or event_data.get('method') or request.method or 'GET'),
                'threat_score': str(threat_score),
                'timestamp': str(int(time.time())),
                'payload': json.dumps({
                    'event': normalized_event,
                    'analysis': analysis,
                    'raw': event_data,
                }),
            }

            try:
                stream_id = self.redis_client.xadd(self.event_stream_name, stream_message)
            except Exception as e:
                logger.error('emit-event stream publish failed: %s', e)
                return jsonify({'error': 'stream_unavailable'}), 503

            ws_event_data = {
                **normalized_event,
                'destination': normalized_event.get('destination'),
            }
            self.ws_broadcaster.broadcast('event_ingested', ws_event_data)

            sensor_hostname = (
                request.headers.get('X-Sensor-Hostname')
                or event_data.get('sensor_hostname')
                or ''
            )
            if sensor_hostname:
                sensor_mode = str(request.headers.get('X-Sensor-Mode') or event_data.get('sensor_mode') or 'proxy').lower()
                sensor_version = str(request.headers.get('X-Sensor-Version') or event_data.get('sensor_version') or '1.0.0')
                self._touch_sensor_last_seen(str(g.tenant_id), str(sensor_hostname), sensor_mode, sensor_version)

            stream_ids.append(stream_id)
            normalized_events.append(normalized_event)

        if not normalized_events:
            return jsonify({'error': 'no_valid_events'}), 400

        if len(normalized_events) == 1:
            return jsonify({
                'status': 'queued',
                'stream': self.event_stream_name,
                'stream_id': stream_ids[0],
                'event': normalized_events[0]
            }), 202

        return jsonify({
            'status': 'queued',
            'stream': self.event_stream_name,
            'queued_count': len(normalized_events),
            'stream_ids': stream_ids,
        }), 202

    @error_handler
    def _emit_alert(self):
        """Receive alert payload and broadcast to raw WebSocket clients."""
        alert_data = request.get_json(silent=True) or {}

        if not isinstance(alert_data, dict) or not alert_data:
            raise ValueError("Alert payload required")

        alert_event_id = str(alert_data.get('event_id') or uuid.uuid4())
        alert_type = str(alert_data.get('alert_type') or alert_data.get('type') or alert_data.get('event_type') or 'alert')
        threat_level = str(alert_data.get('threat_level') or alert_data.get('severity') or 'medium').lower()
        threat_score = float(alert_data.get('threat_score', 0) or 0)
        description = str(alert_data.get('description') or alert_data.get('message') or alert_data.get('reason') or 'alert emitted')
        ip_address = str(alert_data.get('ip_address') or alert_data.get('source_ip') or 'unknown')
        username = str(alert_data.get('username') or 'unknown')
        sensor_id = str(alert_data.get('sensor_id') or 'ingress-proxy-01')
        metadata = alert_data.get('metadata') if isinstance(alert_data.get('metadata'), dict) else alert_data

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO alert_history
                (tenant_id, event_id, alert_type, threat_level, threat_score, description,
                 ip_address, username, sensor_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    g.tenant_id,
                    alert_event_id,
                    alert_type,
                    threat_level,
                    threat_score,
                    description,
                    ip_address,
                    username,
                    sensor_id,
                    json.dumps(metadata),
                ),
            )
            conn.commit()
            cursor.close()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.event_repo.return_connection(conn)

        self.ws_broadcaster.broadcast('alert_created', alert_data)

        return jsonify({
            'status': 'accepted',
            'alert': alert_data
        }), 200

    @error_handler
    def _emit_escalation(self):
        """Receive escalation payload and broadcast to raw WebSocket clients."""
        escalation_data = request.get_json(silent=True) or {}

        if not isinstance(escalation_data, dict) or not escalation_data:
            raise ValueError("Escalation payload required")

        self.ws_broadcaster.broadcast('escalation_triggered', escalation_data)

        return jsonify({
            'status': 'accepted',
            'escalation': escalation_data
        }), 200

    @error_handler
    def _emit_response(self):
        """Receive response action payload and broadcast to raw WebSocket clients."""
        response_data = request.get_json(silent=True) or {}

        if not isinstance(response_data, dict) or not response_data:
            raise ValueError("Response payload required")

        self.ws_broadcaster.broadcast('ip_blocked', response_data)

        return jsonify({
            'status': 'accepted',
            'response': response_data
        }), 200

    @error_handler
    def _emit_policy(self):
        """Receive policy decision payload and broadcast to raw WebSocket clients."""
        policy_data = request.get_json(silent=True) or {}

        if not isinstance(policy_data, dict) or not policy_data:
            raise ValueError("Policy payload required")

        self.ws_broadcaster.broadcast('response_decision', policy_data)

        return jsonify({
            'status': 'accepted',
            'policy': policy_data
        }), 200

    @error_handler
    def _emit_policy_update(self):
        """Receive policy configuration update and broadcast to raw WebSocket clients."""
        policy_update = request.get_json(silent=True) or {}

        if not isinstance(policy_update, dict) or not policy_update:
            raise ValueError("Policy update payload required")

        self.ws_broadcaster.broadcast('response_decision', policy_update)

        return jsonify({
            'status': 'accepted',
            'policy_update': policy_update
        }), 200

    def _record_response_decision(self, payload: Dict[str, Any]) -> None:
        try:
            self.response_repo.record_response_decision(payload)
        except Exception:
            logger.warning("Failed to persist response decision")
        try:
            self.ws_broadcaster.broadcast('response_decision', payload)
        except Exception:
            logger.warning("Failed to emit response_decision event")

    def _ws_events(self, ws):
        """Raw WebSocket firehose for SOC dashboard (server → client only)."""
        self.ws_broadcaster.add_client(ws)
        try:
            try:
                ws.send(json.dumps({
                    "type": "response_mode",
                    "mode": self.response_mode,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }))
            except Exception:
                pass
            while True:
                message = ws.receive()
                if message is None:
                    break
                # Ignore any client messages (one-way stream)
        except Exception:
            pass
        finally:
            self.ws_broadcaster.remove_client(ws)

    @error_handler
    def _set_response_mode(self):
        data = request.get_json(silent=True) or {}
        mode = data.get("mode")

        if mode not in ALLOWED_RESPONSE_MODES:
            return jsonify({
                "error": "Invalid mode",
                "allowed": list(ALLOWED_RESPONSE_MODES)
            }), 400

        old_mode = self.response_mode
        self.response_mode = mode
        self.response_mode_source = 'dashboard'

        self.response_repo.set_response_mode(
            mode,
            source="dashboard"
        )

        self.ws_broadcaster.broadcast_response_mode(mode)

        return jsonify({
            "status": "updated",
            "mode": mode,
            "previous_mode": old_mode
        })

    @error_handler
    def _get_response_mode(self):
        return jsonify({
            "mode": self.response_mode,
            "source": self.response_mode_source
        })
    
    # ═════════════════════════════════════════════════════════════════════════
    # ALERTS
    # ═════════════════════════════════════════════════════════════════════════
    
    @error_handler
    def _list_alerts(self):
        """List open alerts"""
        try:
            limit = int(request.args.get('limit', 100))
        except ValueError:
            raise ValueError("Invalid limit parameter")
        
        if limit > self.config.max_alerts_limit:
            limit = self.config.max_alerts_limit
        
        alerts = self.alert_repo.get_open_alerts(limit=limit)
        
        return jsonify({
            'count': len(alerts),
            'alerts': alerts
        }), 200
    
    @error_handler
    def _block_ip(self):
        """Block an IP address"""
        data = request.get_json()
        
        if not data:
            raise ValueError("Request body required")
        
        ip_address = data.get('ip_address')
        reason = data.get('reason')
        is_permanent = data.get('is_permanent', False)
        
        if not ip_address:
            raise ValueError("ip_address required")
        if not reason:
            raise ValueError("reason required")

        if self.response_mode == 'monitor':
            logger.info("Enforcement skipped due to monitor mode")
            decision_payload = {
                'mode': self.response_mode,
                'decision': 'would_block',
                'action': 'block_ip',
                'reason': 'monitor_mode',
                'ip_address': ip_address,
                'metadata': {'request_reason': reason}
            }
            self._record_response_decision(decision_payload)
            return jsonify({
                'status': 'would_block',
                'ip_address': ip_address,
                'reason': reason,
                'response_mode': self.response_mode
            }), 202

        policy_event = {
            'source_ip': ip_address,
            'event_type': 'manual_block',
            'severity': 'critical',
            'threat_analysis': {'threat_score': 95}
        }
        policy_decision = self.policy_engine.evaluate(
            policy_event,
            candidate_action='block_ip',
            candidate_reason='manual_block'
        )

        if policy_decision.action != 'enforce':
            logger.info("Enforcement skipped due to policy decision")
            decision_payload = {
                'mode': policy_decision.mode,
                'decision': 'skipped',
                'action': 'block_ip',
                'reason': policy_decision.reason,
                'ip_address': ip_address,
                'metadata': {'request_reason': reason}
            }
            self._record_response_decision(decision_payload)
            return jsonify({
                'status': 'skipped',
                'ip_address': ip_address,
                'reason': policy_decision.reason,
                'response_mode': policy_decision.mode
            }), 202
        
        # Calculate expiration
        expires_at = None
        if not is_permanent:
            expires_at = datetime.utcnow() + timedelta(hours=24)
        
        success = self.alert_repo.block_ip(
            ip_address=ip_address,
            reason=reason,
            is_permanent=is_permanent,
            expires_at=expires_at,
            threat_level='high',
            correlation_id=None,
            metadata={'request_reason': reason}
        )
        
        if not success:
            return jsonify({'error': 'Failed to block IP'}), 500

        self.ws_broadcaster.broadcast('ip_blocked', {
            'ip_address': ip_address,
            'reason': reason,
            'is_permanent': is_permanent,
            'expires_at': expires_at.isoformat() if expires_at else None,
            'response_mode': self.response_mode
        })

        self._record_response_decision({
            'mode': self.response_mode,
            'decision': 'enforced',
            'action': 'block_ip',
            'reason': reason,
            'ip_address': ip_address,
            'metadata': {'request_reason': reason}
        })
        
        return jsonify({
            'status': 'blocked',
            'ip_address': ip_address,
            'reason': reason,
            'is_permanent': is_permanent,
            'expires_at': expires_at.isoformat() if expires_at else None
        }), 200

    @error_handler
    def _list_blocked_ips(self):
        """List currently blocked IPs"""
        try:
            limit = int(request.args.get('limit', 200))
        except ValueError:
            raise ValueError("Invalid limit parameter")

        if limit > self.config.max_alerts_limit:
            limit = self.config.max_alerts_limit

        blocked_ips = self.alert_repo.get_blocked_ips(limit=limit)

        return jsonify({
            'count': len(blocked_ips),
            'blocked_ips': blocked_ips
        }), 200

    @error_handler
    def _unblock_ip(self):
        """Unblock an IP address"""
        data = request.get_json()

        if not data:
            raise ValueError("Request body required")

        ip_address = data.get('ip_address')
        reason = data.get('reason') or 'manual_unblock'

        if not ip_address:
            raise ValueError("ip_address required")

        success = self.alert_repo.unblock_ip(ip_address=ip_address, reason=reason)

        if not success:
            return jsonify({'error': 'IP not found or already unblocked'}), 404

        self.ws_broadcaster.broadcast('ip_unblocked', {
            'ip_address': ip_address,
            'reason': reason,
            'response_mode': self.response_mode
        })

        self._record_response_decision({
            'mode': self.response_mode,
            'decision': 'enforced',
            'action': 'unblock_ip',
            'reason': reason,
            'ip_address': ip_address
        })

        return jsonify({
            'status': 'unblocked',
            'ip_address': ip_address,
            'reason': reason
        }), 200
    
    @error_handler
    def _get_ip_block_status(self, ip_address: str):
        """Check if IP is blocked"""
        is_blocked = self.alert_repo.is_ip_blocked(ip_address)
        
        return jsonify({
            'ip_address': ip_address,
            'is_blocked': is_blocked
        }), 200

    @staticmethod
    def _ch_quote(value: str) -> str:
        escaped = value.replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @error_handler
    def _traffic_logs(self):
        """Query raw HTTP traffic logs from ClickHouse with optional filters."""
        method = (request.args.get('method') or '').strip().upper()
        status = (request.args.get('status') or '').strip().lower()
        ip = (request.args.get('ip') or '').strip()
        start_time = (request.args.get('start_time') or '').strip()
        end_time = (request.args.get('end_time') or '').strip()

        try:
            limit = int(request.args.get('limit', self.config.default_traffic_logs_limit))
            offset = int(request.args.get('offset', 0))
        except ValueError:
            raise ValueError('Invalid limit or offset parameter')

        limit = max(1, min(limit, self.config.max_traffic_logs_limit))
        offset = max(0, offset)

        allowed_methods = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'}
        if method and method not in allowed_methods:
            raise ValueError('Invalid method filter')

        where_clauses: List[str] = []

        if method:
            where_clauses.append(f"method = {self._ch_quote(method)}")

        if status:
            if status in {'2xx', '3xx', '4xx', '5xx'}:
                status_prefix = int(status[0])
                where_clauses.append(f"intDiv(status, 100) = {status_prefix}")
            else:
                try:
                    status_code = int(status)
                except ValueError:
                    raise ValueError('Invalid status filter')
                if status_code < 100 or status_code > 599:
                    raise ValueError('Invalid status filter')
                where_clauses.append(f"status = {status_code}")

        if ip:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise ValueError('Invalid ip filter')
            where_clauses.append(f"src_ip = {self._ch_quote(ip)}")

        parsed_start: Optional[datetime] = None
        parsed_end: Optional[datetime] = None

        if start_time:
            try:
                parsed_start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('Invalid start_time filter')
            where_clauses.append(
                f"ts >= toDateTime({self._ch_quote(parsed_start.strftime('%Y-%m-%d %H:%M:%S'))})"
            )

        if end_time:
            try:
                parsed_end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('Invalid end_time filter')
            where_clauses.append(
                f"ts <= toDateTime({self._ch_quote(parsed_end.strftime('%Y-%m-%d %H:%M:%S'))})"
            )

        if parsed_start and parsed_end and parsed_end < parsed_start:
            raise ValueError('end_time must be greater than or equal to start_time')

        where_sql = ''
        if where_clauses:
            where_sql = ' WHERE ' + ' AND '.join(where_clauses)

        logs_query = f"""
            SELECT
                ts,
                src_ip,
                method,
                path,
                query_string,
                status,
                user_agent,
                referer,
                content_length,
                request_body
            FROM raw_traffic_logs
            {where_sql}
            ORDER BY ts DESC
            LIMIT {limit}
            OFFSET {offset}
            FORMAT JSONEachRow
        """.strip()

        count_query = f"""
            SELECT count() AS total
            FROM raw_traffic_logs
            {where_sql}
            FORMAT JSONEachRow
        """.strip()

        try:
            logs_resp = requests.get(
                f"{self.config.clickhouse_url}/",
                params={'query': logs_query},
                timeout=8,
            )
            logs_resp.raise_for_status()

            logs: List[Dict[str, Any]] = []
            for line in (logs_resp.text or '').splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                logs.append(row)

            count_resp = requests.get(
                f"{self.config.clickhouse_url}/",
                params={'query': count_query},
                timeout=8,
            )
            count_resp.raise_for_status()

            count = 0
            for line in (count_resp.text or '').splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    count = int(parsed.get('total') or 0)
                    break
                except Exception:
                    continue

            return jsonify({'logs': logs, 'count': count}), 200
        except requests.RequestException as exc:
            logger.warning('ClickHouse traffic logs query failed: %s', exc)
            return jsonify({'logs': [], 'count': 0, 'error': 'clickhouse_unavailable'}), 503
    
    # ═════════════════════════════════════════════════════════════════════════
    # METRICS
    # ═════════════════════════════════════════════════════════════════════════
    
    @error_handler
    def _metrics(self):
        """Get all metrics"""
        try:
            days = int(request.args.get('days', 7))
        except ValueError:
            raise ValueError("Invalid days parameter")
        
        threat_dist = self.stats_repo.get_threat_distribution(days=days)
        top_ips = self.stats_repo.get_top_ips(days=days, limit=10)

        summary = {
            'total_events': 0,
            'avg_threat_score': 0.0,
        }
        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    COUNT(*) AS total_events,
                    COALESCE(AVG(threat_score), 0) AS avg_threat_score
                FROM security_logs
                WHERE timestamp > NOW() - (%s * INTERVAL '1 day')
                ''',
                (days,),
            )
            row = cursor.fetchone() or {}
            summary = {
                'total_events': int(row.get('total_events') or 0),
                'avg_threat_score': float(row.get('avg_threat_score') or 0),
            }
            cursor.close()
        except Exception as e:
            logger.warning(f"Metrics summary query failed: {e}")
        finally:
            if conn:
                self.event_repo.return_connection(conn)

        distribution_list = [
            {'type': level, 'count': int(count)}
            for level, count in threat_dist.items()
        ]
        
        return jsonify({
            'period': f"Last {days} days",
            'total_events': summary['total_events'],
            'avg_threat_score': round(summary['avg_threat_score'], 2),
            'threat_distribution': threat_dist,
            'threat_distribution_list': distribution_list,
            'top_ips': [
                {'ip_address': ip, 'event_count': count}
                for ip, count in top_ips
            ]
        }), 200
    
    @error_handler
    def _threat_distribution(self):
        """Get threat level distribution"""
        try:
            days = int(request.args.get('days', 7))
        except ValueError:
            raise ValueError("Invalid days parameter")
        
        distribution = self.stats_repo.get_threat_distribution(days=days)

        rows = [
            {'type': level, 'count': int(count)}
            for level, count in distribution.items()
        ]
        
        return jsonify(rows), 200
    
    @error_handler
    def _top_ips(self):
        """Get top attacking IPs with geo-location data."""
        try:
            days = int(request.args.get('days', 7))
            limit = int(request.args.get('limit', 10))
        except ValueError:
            raise ValueError("Invalid days or limit parameter")

        # Static geo-IP lookup for known simulator and common attacker IPs
        GEO_IP_MAP = {
            '203.0.113.42':  {'lat': 55.75, 'lng': 37.62, 'country': 'Russia'},
            '203.0.113.10':  {'lat': 55.75, 'lng': 37.62, 'country': 'Russia'},
            '203.0.113.11':  {'lat': 55.75, 'lng': 37.62, 'country': 'Russia'},
            '198.51.100.15': {'lat': 39.90, 'lng': 116.40, 'country': 'China'},
            '192.0.2.87':    {'lat': 35.69, 'lng': 139.69, 'country': 'Japan'},
            '10.10.10.50':   {'lat': 37.77, 'lng': -122.42, 'country': 'US (Internal)'},
            '172.16.5.100':  {'lat': 51.51, 'lng': -0.13, 'country': 'UK (Internal)'},
            '167.82.56.223': {'lat': 40.71, 'lng': -74.01, 'country': 'United States'},
            '185.220.101.45':{'lat': 52.52, 'lng': 13.41, 'country': 'Germany'},
            '45.155.205.233':{'lat': 52.37, 'lng': 4.90, 'country': 'Netherlands'},
        }

        def _lookup_geo(ip_addr):
            """Look up geo data for an IP, with fallback heuristics."""
            if ip_addr in GEO_IP_MAP:
                return GEO_IP_MAP[ip_addr]
            # Prefix match for 203.0.113.x range (TEST-NET-3 / simulated attackers)
            if ip_addr.startswith('203.0.113.'):
                return {'lat': 55.75, 'lng': 37.62, 'country': 'Russia'}
            if ip_addr.startswith('198.51.100.'):
                return {'lat': 39.90, 'lng': 116.40, 'country': 'China'}
            if ip_addr.startswith('192.0.2.'):
                return {'lat': 35.69, 'lng': 139.69, 'country': 'Japan'}
            if ip_addr.startswith('185.'):
                return {'lat': 52.52, 'lng': 13.41, 'country': 'Germany'}
            if ip_addr.startswith('45.'):
                return {'lat': 52.37, 'lng': 4.90, 'country': 'Netherlands'}
            # Private ranges — place at a default US location
            if ip_addr.startswith(('10.', '172.16.', '172.17.', '192.168.')):
                return {'lat': 37.77, 'lng': -122.42, 'country': 'US (Internal)'}
            return {'lat': None, 'lng': None, 'country': None}

        top_ips = self.stats_repo.get_top_ips(days=days, limit=limit)

        rows = []
        for ip, count in top_ips:
            geo = _lookup_geo(ip)
            rows.append({
                'ip': ip,
                'ip_address': ip,
                'count': int(count),
                'event_count': int(count),
                'country': geo['country'],
                'lat': geo['lat'],
                'lng': geo['lng'],
            })

        return jsonify(rows), 200
    
    @error_handler
    def _threat_summary(self):
        """Get threat summary for specific IP"""
        ip_address = request.args.get('ip_address')
        
        if not ip_address:
            raise ValueError("ip_address parameter required")
        
        try:
            days = int(request.args.get('days', 7))
        except ValueError:
            raise ValueError("Invalid days parameter")
        
        summary = self.event_repo.get_ip_threat_summary(ip_address=ip_address, days=days)
        
        return jsonify({
            'ip_address': ip_address,
            'period': f"Last {days} days",
            'summary': summary
        }), 200

    @error_handler
    def _attack_graph(self):
        """Return attack graph in D3-ready node/link format from Neo4j."""
        query = '''
        MATCH (a:AttackerIP)-[r:ATTACKED]->(h:HoneypotTarget)
        OPTIONAL MATCH (h)-[:TRIGGERED]->(m:MITRETechnique)
        OPTIONAL MATCH (a)-[:USED]->(c:Credential)
        RETURN a, r, h, m, c
        LIMIT 200
        '''

        async def _fetch_graph_data():
            driver = get_neo4j_driver()
            nodes_by_id = {}
            links = []
            seen_links = set()

            def _node_type(node):
                labels = set(node.labels)
                if 'AttackerIP' in labels:
                    return 'AttackerIP'
                if 'HoneypotTarget' in labels:
                    return 'HoneypotTarget'
                if 'MITRETechnique' in labels:
                    return 'MITRETechnique'
                if 'Credential' in labels:
                    return 'Credential'
                return next(iter(labels), 'Node')

            def _node_id(node):
                n_type = _node_type(node)
                props = dict(node)
                if n_type == 'AttackerIP':
                    return str(props.get('ip', ''))
                if n_type == 'HoneypotTarget':
                    return str(props.get('service', ''))
                if n_type == 'MITRETechnique':
                    return str(props.get('technique_id', ''))
                if n_type == 'Credential':
                    return f"cred:{props.get('username', '')}"
                return ''

            def _node_label(node):
                n_type = _node_type(node)
                props = dict(node)
                if n_type == 'AttackerIP':
                    return str(props.get('ip', 'unknown'))
                if n_type == 'HoneypotTarget':
                    return str(props.get('service', 'unknown'))
                if n_type == 'MITRETechnique':
                    return str(props.get('technique_id', 'unknown'))
                if n_type == 'Credential':
                    return str(props.get('username', 'unknown'))
                return n_type

            def _add_node(node):
                if node is None:
                    return None
                n_id = _node_id(node)
                if not n_id:
                    return None
                if n_id not in nodes_by_id:
                    nodes_by_id[n_id] = {
                        'id': n_id,
                        'type': _node_type(node),
                        'label': _node_label(node),
                        'properties': dict(node),
                    }
                return n_id

            def _add_link(source, target, rel_type, score=None):
                if not source or not target:
                    return
                key = (source, target, rel_type, score)
                if key in seen_links:
                    return
                seen_links.add(key)
                links.append({
                    'source': source,
                    'target': target,
                    'type': rel_type,
                    'score': score,
                })

            async with driver.session() as session:
                result = await session.run(query)
                async for record in result:
                    a = record.get('a')
                    r = record.get('r')
                    h = record.get('h')
                    m = record.get('m')
                    c = record.get('c')

                    a_id = _add_node(a)
                    h_id = _add_node(h)
                    m_id = _add_node(m)
                    c_id = _add_node(c)

                    attack_score = None
                    if r is not None:
                        attack_score = r.get('last_score', None)

                    _add_link(a_id, h_id, 'ATTACKED', attack_score)
                    _add_link(h_id, m_id, 'TRIGGERED', None)
                    _add_link(a_id, c_id, 'USED', None)

            return {'nodes': list(nodes_by_id.values()), 'links': links}

        try:
            graph_data = asyncio.run(_fetch_graph_data())
            return jsonify(graph_data), 200
        except Exception as e:
            logger.warning(f"Neo4j graph query unavailable: {e}")
            return jsonify({'nodes': [], 'links': [], 'error': str(e)}), 200

    @error_handler
    def _sessions_graph(self):
        """Proxy session graph snapshot from core service for SOC dashboards."""
        try:
            forward_headers = {}
            auth_header = request.headers.get('Authorization')
            if auth_header:
                forward_headers['Authorization'] = auth_header

            admin_token = request.headers.get('X-Admin-Token')
            if admin_token:
                forward_headers['X-Admin-Token'] = admin_token

            response = requests.get(
                f"{self.config.core_url}/api/sessions/graph",
                headers=forward_headers,
                timeout=self.config.health_timeout,
            )

            if response.status_code != 200:
                logger.warning(
                    "Session graph proxy failed status=%s",
                    response.status_code,
                )
                return jsonify([]), 200

            return jsonify(response.json()), 200
        except Exception as e:
            logger.warning(f"Session graph proxy error: {e}")
            return jsonify([]), 200

    @error_handler
    def _behavioral_history(self):
        """Proxy behavioral history query to core service."""
        params = {}
        ip = request.args.get('ip')
        hours = request.args.get('hours')
        limit = request.args.get('limit')
        if ip is not None:
            params['ip'] = ip
        if hours is not None:
            params['hours'] = hours
        if limit is not None:
            params['limit'] = limit

        try:
            response = requests.get(
                f"{self.config.core_url}/api/behavioral/history",
                params=params,
                timeout=10,
            )
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            logger.warning(f"Behavioral history proxy error: {e}")
            return jsonify({'error': 'core_unavailable', 'message': str(e)}), 503

    @error_handler
    def _behavioral_sessions(self):
        """Proxy behavioral session graph snapshot to core service."""
        try:
            response = requests.get(
                f"{self.config.core_url}/api/behavioral/sessions",
                timeout=10,
            )
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            logger.warning(f"Behavioral sessions proxy error: {e}")
            return jsonify({'error': 'core_unavailable', 'message': str(e)}), 503

    @error_handler
    def _behavioral_drift(self):
        """Proxy behavioral drift state to core service."""
        try:
            response = requests.get(
                f"{self.config.core_url}/api/behavioral/drift",
                timeout=10,
            )
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            logger.warning(f"Behavioral drift proxy error: {e}")
            return jsonify({'error': 'core_unavailable', 'message': str(e)}), 503

    @error_handler
    def _mitre_summary(self):
        """Aggregate MITRE ATT&CK TTP frequency from security_logs."""
        hours = int(request.args.get('hours', 24))
        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    COALESCE(
                        ttp->>'technique_id',
                        ttp->>'id',
                        TRIM(BOTH '"' FROM ttp::text)
                    ) AS technique_id,
                    COUNT(*) AS count
                FROM security_logs,
                     jsonb_array_elements(COALESCE(metadata->'mitre_ttps', '[]'::jsonb)) AS ttp
                WHERE timestamp >= NOW() - (%s * INTERVAL '1 hour')
                GROUP BY technique_id
                ORDER BY count DESC
                ''',
                (hours,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return jsonify([
                {
                    'technique_id': row.get('technique_id'),
                    'count': int(row.get('count') or 0),
                }
                for row in rows
                if row.get('technique_id')
            ]), 200
        except Exception as e:
            logger.error(f"MITRE summary failed: {e}")
            return jsonify([]), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _honeypot_sessions(self):
        """List honeypot capture sessions for SOC dashboard viewer."""
        limit = min(max(int(request.args.get('limit', 50)), 1), 500)
        offset = max(int(request.args.get('offset', 0)), 0)
        attack_type = (request.args.get('attack_type') or '').strip()

        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = '''
                SELECT
                    c.session_id,
                    host(c.source_ip) AS source_ip,
                    c.attack_type,
                    COALESCE(NULLIF(split_part(c.request_payload, ' ', 2), ''), '/') AS uri,
                    c.request_payload,
                    COALESCE(c.llm_response, '') AS response_snippet,
                    c.captured_at AS timestamp,
                    COALESCE(
                        (
                            SELECT sl.threat_score
                            FROM security_logs sl
                            WHERE split_part(sl.ip_address::text, '/', 1) = host(c.source_ip)
                            ORDER BY sl.timestamp DESC
                            LIMIT 1
                        ),
                        0
                    ) AS waf_score
                FROM honeypot_captures c
                WHERE (%s = '' OR c.attack_type = %s)
                ORDER BY c.captured_at DESC
                LIMIT %s OFFSET %s
            '''

            cursor.execute(query, (attack_type, attack_type, limit, offset))
            rows = cursor.fetchall() or []
            cursor.close()

            result = []
            for row in rows:
                snippet = row.get('response_snippet') or ''
                result.append({
                    'session_id': row.get('session_id'),
                    'source_ip': row.get('source_ip'),
                    'attack_type': row.get('attack_type') or 'unknown',
                    'uri': row.get('uri') or '/',
                    'request_payload': row.get('request_payload') or '',
                    'response_snippet': str(snippet)[:400],
                    'timestamp': row.get('timestamp').isoformat() + 'Z' if row.get('timestamp') else None,
                    'waf_score': int(row.get('waf_score') or 0),
                })

            return jsonify(result), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _honeypot_active_sessions(self):
        """List active adaptive deception sessions with attacker profile context."""
        limit = min(max(int(request.args.get('limit', 100)), 1), 500)
        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    s.id,
                    s.session_id,
                    host(s.source_ip) AS source_ip,
                    s.interaction_count,
                    s.first_seen,
                    s.last_seen,
                    s.attacker_profile,
                    s.environment_state,
                    EXTRACT(EPOCH FROM (COALESCE(s.last_seen, NOW()) - COALESCE(s.first_seen, NOW()))) AS duration_seconds,
                    (
                        SELECT c.attack_type
                        FROM honeypot_captures c
                        WHERE c.session_id = s.session_id
                          AND (c.tenant_id::text = %s OR c.tenant_id IS NULL)
                        ORDER BY c.captured_at DESC
                        LIMIT 1
                    ) AS latest_attack_type
                FROM attacker_sessions s
                WHERE s.is_active = true
                ORDER BY s.last_seen DESC
                LIMIT %s
                ''',
                (str(g.tenant_id), limit),
            )
            rows = cursor.fetchall() or []
            cursor.close()

            payload = []
            for row in rows:
                profile = row.get('attacker_profile') or {}
                env = row.get('environment_state') or {}
                payload.append({
                    'id': str(row.get('id')) if row.get('id') else None,
                    'session_id': row.get('session_id'),
                    'source_ip': row.get('source_ip'),
                    'interaction_count': int(row.get('interaction_count') or 0),
                    'first_seen': row.get('first_seen').isoformat() + 'Z' if row.get('first_seen') else None,
                    'last_seen': row.get('last_seen').isoformat() + 'Z' if row.get('last_seen') else None,
                    'duration_seconds': int(row.get('duration_seconds') or 0),
                    'detected_tools': profile.get('detected_tools') or [],
                    'skill_level': profile.get('skill_level') or 'unknown',
                    'attack_phase': profile.get('attack_phase') or 'recon',
                    'likely_goal': profile.get('likely_goal') or 'unknown',
                    'attack_types': profile.get('attack_types') or [],
                    'environment': env.get('presented_as') or 'enterprise_web_suite',
                    'environment_state': env,
                    'latest_attack_type': row.get('latest_attack_type') or 'unknown',
                    'is_active': True,
                })

            return jsonify(payload), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _honeypot_session_timeline(self, session_id: str):
        """Return honeypot capture timeline for a specific attacker session."""
        limit = min(max(int(request.args.get('limit', 200)), 1), 1000)
        conn = None
        try:
            conn = self.event_repo.get_connection()
            set_tenant_context(conn, g.tenant_id)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                '''
                SELECT
                    c.id,
                    c.session_id,
                    host(c.source_ip) AS source_ip,
                    c.attack_type,
                    c.request_payload,
                    COALESCE(c.llm_response, '') AS llm_response,
                    c.persona_type,
                    c.captured_at
                FROM honeypot_captures c
                WHERE c.session_id = %s
                  AND (c.tenant_id::text = %s OR c.tenant_id IS NULL)
                ORDER BY c.captured_at ASC
                LIMIT %s
                ''',
                (session_id, str(g.tenant_id), limit),
            )
            rows = cursor.fetchall() or []
            cursor.close()

            timeline = []
            for row in rows:
                timeline.append({
                    'id': int(row.get('id') or 0),
                    'session_id': row.get('session_id'),
                    'source_ip': row.get('source_ip'),
                    'attack_type': row.get('attack_type') or 'unknown',
                    'request_payload': row.get('request_payload') or '',
                    'response_snippet': str(row.get('llm_response') or '')[:1200],
                    'persona_type': row.get('persona_type') or 'unknown',
                    'timestamp': row.get('captured_at').isoformat() + 'Z' if row.get('captured_at') else None,
                })

            return jsonify(timeline), 200
        finally:
            if conn:
                self.event_repo.return_connection(conn)

    @error_handler
    def _copilot_query(self):
        copilot_url = os.getenv('COPILOT_URL', 'http://soc-copilot:8003')
        try:
            data = request.get_json(force=True)
            response = requests.post(f"{copilot_url}/query", json=data, timeout=90)
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            return jsonify({'error': 'copilot_unavailable', 'message': str(e)}), 503

    @error_handler
    def _copilot_history(self):
        copilot_url = os.getenv('COPILOT_URL', 'http://soc-copilot:8003')
        session_id = request.args.get('session_id', 'default')
        try:
            response = requests.get(
                f"{copilot_url}/history",
                params={'session_id': session_id},
                timeout=5,
            )
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            return jsonify({'error': 'copilot_unavailable', 'message': str(e)}), 503

    @error_handler
    def _copilot_clear(self):
        copilot_url = os.getenv('COPILOT_URL', 'http://soc-copilot:8003')
        session_id = request.args.get('session_id', 'default')
        try:
            response = requests.delete(
                f"{copilot_url}/history",
                params={'session_id': session_id},
                timeout=5,
            )
            return jsonify(response.json()), response.status_code
        except requests.exceptions.RequestException as e:
            return jsonify({'error': 'copilot_unavailable', 'message': str(e)}), 503
    
    def run(self, port: Optional[int] = None, debug: bool = False):
        """Run the API server"""
        port = port or self.config.api_port
        debug = debug or self.config.api_debug
        
        logger.info(f"Starting Mayasec Control Plane API on port {port}")
        self.app.run(host='0.0.0.0', port=port, debug=debug)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    config = ApiConfig()
    api = MayasecAPI(config)
    api.run()
