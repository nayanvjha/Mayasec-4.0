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
import json
import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from functools import wraps
import requests
from flask_sock import Sock

from repository import EventRepository, AlertRepository, StatisticsRepository, ResponseRepository, DatabaseConfig
from policy_engine import PolicyEngine
from response_mode import resolve_response_mode

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class ApiConfig:
    """Control plane API configuration"""
    
    def __init__(self):
        # Database (storage layer)
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = os.getenv('DB_PORT', '5432')
        self.db_name = os.getenv('DB_NAME', 'mayasec')
        self.db_user = os.getenv('DB_USER', 'mayasec')
        self.db_password = os.getenv('DB_PASSWORD', 'mayasec')
        
        # Core service (threat analysis)
        self.core_url = os.getenv('CORE_URL', 'http://localhost:5001')
        
        # Honeypot service (optional)
        self.honeypot_url = os.getenv('HONEYPOT_URL', 'http://localhost:5003')
        
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


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# RAW WEBSOCKET STREAM (ONE-WAY)
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_WS_EVENT_TYPES = {
    'event_ingested',
    'phase_escalated',
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


# ═══════════════════════════════════════════════════════════════════════════════
# API CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class MayasecAPI:
    """Control plane API for Mayasec"""
    
    def __init__(self, config: ApiConfig):
        self.config = config
        self.app = Flask(__name__)
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

        try:
            self.response_mode, self.response_mode_source = resolve_response_mode()
        except Exception as e:
            logger.error(f"Invalid response mode: {e}")
            raise

        self.ws_broadcaster = WebSocketBroadcaster(logger, response_mode=self.response_mode)

        self.policy_engine = PolicyEngine(self.alert_repo)

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
        self.app.route('/api/v1/events', methods=['GET'])(self._list_events)
        self.app.route('/api/v1/events/<event_id>', methods=['GET'])(self._get_event)
        
        # Alerts
        self.app.route('/api/v1/alerts', methods=['GET'])(self._list_alerts)
        self.app.route('/api/v1/alerts/block', methods=['POST'])(self._block_ip)
        self.app.route('/api/v1/alerts/blocked', methods=['GET'])(self._list_blocked_ips)
        self.app.route('/api/v1/alerts/unblock', methods=['POST'])(self._unblock_ip)
        self.app.route('/api/v1/alerts/status/<ip_address>', methods=['GET'])(self._get_ip_block_status)

        # Event ingestion for streaming
        self.app.route('/api/v1/emit-event', methods=['POST'])(self._emit_event)

        # Raw WebSocket event stream
        self.sock.route('/ws/events')(self._ws_events)
        
        # Metrics
        self.app.route('/api/v1/metrics', methods=['GET'])(self._metrics)
        self.app.route('/api/v1/metrics/threat-distribution', methods=['GET'])(self._threat_distribution)
        self.app.route('/api/v1/metrics/top-ips', methods=['GET'])(self._top_ips)
        self.app.route('/api/v1/metrics/threat-summary', methods=['GET'])(self._threat_summary)
        
        logger.info("API routes registered")
    
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
    # EVENTS
    # ═════════════════════════════════════════════════════════════════════════
    
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
    def _emit_event(self):
        """Receive event and broadcast to raw WebSocket clients"""
        event_data = request.get_json(silent=True) or {}

        if not isinstance(event_data, dict) or not event_data:
            raise ValueError("Event payload required")

        self.ws_broadcaster.broadcast('event_ingested', event_data)

        return jsonify({
            'status': 'accepted',
            'event': event_data
        }), 201

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
        
        return jsonify({
            'period': f"Last {days} days",
            'threat_distribution': threat_dist,
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
        
        return jsonify({
            'period': f"Last {days} days",
            'distribution': distribution
        }), 200
    
    @error_handler
    def _top_ips(self):
        """Get top attacking IPs"""
        try:
            days = int(request.args.get('days', 7))
            limit = int(request.args.get('limit', 10))
        except ValueError:
            raise ValueError("Invalid days or limit parameter")
        
        top_ips = self.stats_repo.get_top_ips(days=days, limit=limit)
        
        return jsonify({
            'period': f"Last {days} days",
            'limit': limit,
            'ips': [
                {'ip_address': ip, 'event_count': count}
                for ip, count in top_ips
            ]
        }), 200
    
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
