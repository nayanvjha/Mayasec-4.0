"""
MAYASEC Core Analysis Service - Refactored

Responsibilities:
- Receive ONLY normalized events (canonical schema)
- Feature extraction
- Correlation analysis
- Threat detection
- Event enrichment
- Database persistence

Non-responsibilities:
- Event ingestion/parsing
- Source system knowledge
- Sensor identification
- Input format conversion
"""

import os
import asyncio
import logging
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import requests

from correlation_engine import CorrelationEngine as CorrelationIdEngine
from response_plane import FirewallService, EnforcementService, ResponseEngine
from policy_engine import PolicyEngine, ResponseMode
from correlation_escalation import CorrelationEscalationEngine
from core.behavioral_scorer import BehavioralScorer
from core.session_graph import SessionGraph
from core.response_escalator import ResponseEscalator
from core.drift_detector import DriftDetector
from core.retrain_scheduler import RetrainScheduler
from core.threat_correlator import schedule_graph_write

# Import repository layer
from repository import EventRepository, AlertRepository, StatisticsRepository, DatabaseConfig

# Load environment
load_dotenv()

# Configuration
CORE_PORT = int(os.getenv('CORE_PORT', 5002))
DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'mayasec')
DB_USER = os.getenv('DB_USER', 'mayasec')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'mayasec_secure_password')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', '/app/logs')
API_URL = os.getenv('API_URL', 'http://api:5000')  # For WebSocket event emission
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')  # Bearer token for authenticated API calls
BEHAVIORAL_MODEL_PATH = os.getenv('BEHAVIORAL_MODEL_PATH', '/app/model/behavioral_iso.pkl')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/core.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('Core')

# Startup warning for known multi-worker in-memory state limitation.
try:
    _gunicorn_workers = os.getenv('GUNICORN_WORKERS')
    if _gunicorn_workers is not None and int(_gunicorn_workers) > 1:
        logger.warning("In-memory session state may not synchronize across workers.")
except (TypeError, ValueError):
    pass

# Create Flask app
app = Flask(__name__)
app.json.sort_keys = False

# Initialize repository layer (dependency injection)
db_config = DatabaseConfig(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
event_repo = EventRepository(db_config)
alert_repo = AlertRepository(db_config)
stats_repo = StatisticsRepository(db_config)

# Response plane (OS-level enforcement)
firewall_service = FirewallService()
enforcement_service = EnforcementService(alert_repo, firewall_service)
response_engine = ResponseEngine(enforcement_service)
policy_engine = PolicyEngine(alert_repo)
logger.info("Response plane initialized")

# Behavioral anomaly scorer (loaded once, reused across all requests)
behavioral_scorer = BehavioralScorer(BEHAVIORAL_MODEL_PATH)
# Session correlation graph singleton (loaded once, shared across all requests)
session_graph = SessionGraph()
# Response escalator singleton (loaded once, shared across all requests)
response_escalator = ResponseEscalator()
# Drift detector for model staleness checks
drift_detector = DriftDetector()

# Background retraining scheduler (daemon thread).
def _retrain_ws_emitter(event_name: str, payload: dict) -> None:
    """Bridge retrain scheduler events to the existing websocket emitter."""
    try:
        emit_event_to_websocket({'retrain_event': event_name, **payload})
    except Exception:
        pass

try:
    retrain_scheduler = RetrainScheduler(
        behavioral_scorer=behavioral_scorer,
        drift_detector=drift_detector,
        event_repo=event_repo,
        websocket_emitter=_retrain_ws_emitter,
    )
    retrain_scheduler.start()
    logger.info("RetrainScheduler started")
except Exception as _retrain_err:
    logger.warning("RetrainScheduler failed to start: %s", _retrain_err)
    retrain_scheduler = None

_BEHAVIORAL_FAIL_OPEN = {
    'intent': 'Benign',
    'anomaly_score': 0.0,
    'deception_trigger': False,
    'graph_threat': False,
    'escalation_tier': 0,
}


def _extract_session_graph_fields(event_like: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[str]]:
    """Extract (ip, path, session_id) from normalized/ingress-style payloads."""
    if not isinstance(event_like, dict):
        return None, '/', None

    # Source IP extraction (normalized and ingress-style payloads).
    ip = event_like.get('source_ip')
    if not ip:
        ip_address = event_like.get('ip_address')
        if isinstance(ip_address, dict):
            ip = ip_address.get('source') or ip_address.get('src')

    # Path extraction (normalized and ingress-style payloads).
    path = event_like.get('path') or event_like.get('uri')
    if not path:
        http = event_like.get('http')
        if isinstance(http, dict):
            path = http.get('path') or http.get('uri')

    # Stable session identifier preference order.
    sid = (
        event_like.get('correlation_id')
        or event_like.get('session_id')
        or event_like.get('event_id')
    )

    return str(ip) if ip is not None else None, str(path or '/'), str(sid) if sid is not None else None


def _update_session_graph(event_like: Dict[str, Any]) -> None:
    """Best-effort ingest into the shared session correlation graph."""
    ip, path, sid = _extract_session_graph_fields(event_like)

    if not ip:
        return

    session_graph.add_event(
        ip=ip,
        path=path,
        session_id=sid,
    )


def _get_graph_threat_for_request(event_like: Dict[str, Any]) -> bool:
    """Safely resolve graph threat signal for current request context.

    Uses the O(1) direct lookup on SessionGraph instead of a full snapshot scan.
    """
    try:
        ip, path, sid = _extract_session_graph_fields(event_like)
        return session_graph.get_threat(session_id=sid, ip=ip, path=path)
    except Exception:
        return False


class InputContract:
    """
    Validates strict input contract for normalized events
    
    Core will ONLY process events that match canonical schema.
    No assumptions about source, sensor, or ingestion method.
    """
    
    REQUIRED_FIELDS = {'event_id', 'event_type', 'timestamp', 'source', 'sensor_id'}
    
    VALID_EVENT_TYPES = {
        'login_attempt',
        'ssh_failed_login',
        'web_auth_failed',
        'honeypot_interaction',
        'network_alert',
        'network_flow',
        'security_action',
        'authentication_success',
        'authentication_failure',
        'access_denied',
        'suspicious_behavior',
        'port_scan'
    }
    
    VALID_SOURCES = {
        'http_api',
        'log_file',
        'syslog',
        'ids',
        'firewall',
        'honeypot',
        'web_application',
        'custom'
    }
    
    @staticmethod
    def validate(event: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate event against input contract
        
        Returns: (is_valid, error_message)
        """
        # Check required fields
        missing = InputContract.REQUIRED_FIELDS - set(event.keys())
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        
        # Validate event_type
        if event['event_type'] not in InputContract.VALID_EVENT_TYPES:
            return False, f"Invalid event_type: {event['event_type']}"
        
        # Validate source
        if event['source'] not in InputContract.VALID_SOURCES:
            return False, f"Invalid source: {event['source']}"
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return False, f"Invalid timestamp format: {event['timestamp']}"
        
        # Validate event_id format (UUID v4)
        if not _is_valid_uuid(event['event_id']):
            return False, f"Invalid event_id format (must be UUID v4): {event['event_id']}"
        
        # Validate sensor_id is non-empty string
        if not isinstance(event['sensor_id'], str) or not event['sensor_id'].strip():
            return False, "sensor_id must be non-empty string"
        
        return True, None


def _is_valid_uuid(uuid_str: str) -> bool:
    """Check if string is valid UUID v4"""
    try:
        parts = uuid_str.split('-')
        if len(parts) != 5:
            return False
        if len(parts[0]) != 8 or len(parts[1]) != 4 or len(parts[2]) != 4 or len(parts[3]) != 4 or len(parts[4]) != 12:
            return False
        for part in parts:
            int(part, 16)
        return True
    except:
        return False


class FeatureExtractor:
    """Extract behavioral features from normalized events"""
    
    @staticmethod
    def extract_features(event: Dict[str, Any], historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features from normalized event
        
        Features are source-agnostic and based on canonical schema only
        """
        features = {}
        
        # IP-based features
        if 'ip_address' in event:
            src_ip = event.get('ip_address', {}).get('source')
            dst_ip = event.get('ip_address', {}).get('destination')
            
            if src_ip:
                features['source_ip'] = src_ip
                features['source_ip_is_internal'] = _is_internal_ip(src_ip)
                features['source_ip_reputation'] = _get_ip_reputation(src_ip, historical_data)
            
            if dst_ip:
                features['dest_ip'] = dst_ip
                features['dest_ip_is_internal'] = _is_internal_ip(dst_ip)
        
        # User-based features
        if 'username' in event:
            username = event['username']
            features['username'] = username
            features['username_common'] = _is_common_username(username)
            features['username_history_count'] = _count_user_history(username, historical_data)
        
        # Protocol/network features
        if 'protocol' in event:
            features['protocol'] = event['protocol']
        
        if 'port' in event:
            dst_port = event.get('port', {}).get('destination')
            if dst_port:
                features['dest_port'] = dst_port
                features['dest_port_is_privileged'] = dst_port < 1024
                features['dest_port_is_common'] = _is_common_port(dst_port)
        
        # Timing features
        if 'timestamp' in event:
            features['timestamp'] = event['timestamp']
            features['hour_of_day'] = _extract_hour(event['timestamp'])
        
        # Event type features
        features['event_type'] = event.get('event_type')
        
        # Action/severity features
        if 'action' in event:
            features['action'] = event['action']
            features['was_blocked'] = event['action'] == 'blocked'
        
        if 'severity' in event:
            features['severity'] = event['severity']
        
        # User-Agent features
        if 'user_agent' in event:
            ua = event['user_agent']
            features['user_agent_length'] = len(ua) if ua else 0
            features['user_agent_is_suspicious'] = _is_suspicious_user_agent(ua)
        
        return features


class CorrelationEngine:
    """Detect correlated events and patterns"""
    
    def __init__(self, event_repository: EventRepository):
        """Initialize with repository dependency"""
        self.repo = event_repository
    
    def analyze_correlations(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze event for correlations with historical data
        
        Uses repository layer for all queries.
        Returns correlation findings without modifying input event.
        """
        correlations = {
            'brute_force': self._check_brute_force(event),
            'multiple_sensors': self._check_multiple_sensors(event),
            'ip_scanning': self._check_ip_scanning(event),
            'port_scanning': self._check_port_scanning(event),
        }
        
        return {k: v for k, v in correlations.items() if v is not None}
    
    def _check_brute_force(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect brute force patterns via repository query"""
        if event.get('event_type') not in ('login_attempt', 'authentication_failure'):
            return None
        
        src_ip = event.get('ip_address', {}).get('source')
        if not src_ip:
            return None
        
        try:
            # Query via repository (encapsulates SQL)
            logs = self.repo.query_logs(ip_address=src_ip, days=1, limit=1000)
            
            # Count recent login attempts from this IP
            login_attempts = [l for l in logs if l.get('event_type') == 'login_attempt']
            
            if len(login_attempts) >= 5:
                return {
                    'pattern': 'brute_force',
                    'attempt_count': len(login_attempts),
                    'time_window': '24 hours',
                    'source_ip': src_ip
                }
        
        except Exception as e:
            logger.warning(f"Error checking brute force: {e}")
        
        return None
    
    def _check_multiple_sensors(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect same source hitting multiple sensors via repository"""
        src_ip = event.get('ip_address', {}).get('source')
        if not src_ip:
            return None
        
        try:
            # Query via repository
            logs = self.repo.query_logs(ip_address=src_ip, days=1, limit=1000)
            
            # Count distinct sensors
            sensors = set(l.get('sensor_id') for l in logs if l.get('sensor_id'))
            
            if len(sensors) >= 3:
                return {
                    'pattern': 'multiple_sensors',
                    'sensor_count': len(sensors),
                    'source_ip': src_ip
                }
        
        except Exception as e:
            logger.warning(f"Error checking multiple sensors: {e}")
        
        return None
    
    def _check_ip_scanning(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect IP address scanning patterns"""
        src_ip = event.get('ip_address', {}).get('source')
        if not src_ip or event.get('event_type') != 'network_alert':
            return None
        
        # TODO: Implement IP subnet scanning detection via repository
        return None
    
    def _check_port_scanning(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect port scanning patterns"""
        src_ip = event.get('ip_address', {}).get('source')
        if not src_ip or event.get('event_type') != 'network_alert':
            return None
        
        # TODO: Implement port sequence detection via repository
        return None


class DetectionPipeline:
    """Apply threat detection rules to events"""
    
    # Detection rules (can be loaded from config, database, or rules engine)
    RULES = {
        'high_severity_network_alert': {
            'condition': lambda e: e.get('event_type') == 'network_alert' and e.get('severity') in ('high', 'critical'),
            'score_delta': 30,
            'reason': 'High severity network alert detected'
        },
        'honeypot_interaction': {
            'condition': lambda e: e.get('event_type') == 'honeypot_interaction',
            'score_delta': 25,
            'reason': 'Honeypot interaction - active attack'
        },
        'failed_auth': {
            'condition': lambda e: e.get('event_type') in ('login_attempt', 'authentication_failure') and e.get('action') == 'blocked',
            'score_delta': 5,
            'reason': 'Failed authentication attempt'
        },
        'successful_auth': {
            'condition': lambda e: e.get('event_type') == 'authentication_success',
            'score_delta': -5,
            'reason': 'Successful authentication'
        }
    }
    
    @staticmethod
    def compute_threat_score(event: Dict[str, Any], features: Dict[str, Any], correlations: Dict[str, Any]) -> Tuple[int, str]:
        """
        Compute threat score (0-100) based on:
        - Event characteristics
        - Extracted features
        - Correlation findings
        
        Returns: (score, reasoning)
        """
        base_score = 0
        reasons = []
        
        # Base score from rules
        for rule_name, rule in DetectionPipeline.RULES.items():
            if rule['condition'](event):
                base_score += rule['score_delta']
                reasons.append(rule['reason'])
        
        # Feature-based adjustments
        if features.get('source_ip_is_internal'):
            base_score -= 5
            reasons.append('Internal IP source')
        
        if features.get('username_common'):
            base_score += 2
            reasons.append('Common username targeted')
        
        if features.get('user_agent_is_suspicious'):
            base_score += 10
            reasons.append('Suspicious user-agent detected')
        
        if features.get('dest_port_is_privileged'):
            base_score += 3
            reasons.append('Privileged port target')
        
        # Correlation-based adjustments
        if 'brute_force' in correlations:
            base_score += 20
            reasons.append(f"Brute force pattern detected ({correlations['brute_force']['attempt_count']} attempts)")
        
        if 'multiple_sensors' in correlations:
            base_score += 15
            reasons.append(f"Detected on {correlations['multiple_sensors']['sensor_count']} sensors")
        
        # Clamp score to 0-100
        final_score = max(0, min(100, base_score))
        reasoning = ' | '.join(reasons) if reasons else 'Baseline threat level'
        
        return final_score, reasoning
    
    @staticmethod
    def threat_level_from_score(score: int) -> str:
        """Convert numeric score to threat level"""
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        elif score >= 20:
            return 'low'
        else:
            return 'info'


class ThreatAnalysis:
    """Orchestrate threat analysis for normalized event"""
    
    def __init__(self, correlation_engine: CorrelationEngine):
        """Initialize with correlation engine dependency"""
        self.correlation_engine = correlation_engine
    
    def analyze(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform comprehensive threat analysis on normalized event
        
        Does NOT modify input event.
        Returns analysis metadata suitable for enrichment.
        Uses injected dependencies (no raw database calls).
        """
        analysis = {
            'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
            'features': {},
            'correlations': {},
            'threat_score': 0,
            'threat_level': 'info',
            'analysis_reason': ''
        }
        
        try:
            # Extract historical data (for feature context)
            historical_data = _get_historical_data(event)
            
            # Feature extraction (source-agnostic)
            analysis['features'] = FeatureExtractor.extract_features(event, historical_data)
            
            # Correlation analysis (uses repository)
            analysis['correlations'] = self.correlation_engine.analyze_correlations(event)
            
            # Threat detection
            score, reasoning = DetectionPipeline.compute_threat_score(
                event,
                analysis['features'],
                analysis['correlations']
            )
            analysis['threat_score'] = score
            analysis['threat_level'] = DetectionPipeline.threat_level_from_score(score)
            analysis['analysis_reason'] = reasoning
            
        except Exception as e:
            logger.error(f"Error in threat analysis: {e}")
            analysis['error'] = str(e)
        
        return analysis


# ============================================================================
# FLASK ENDPOINTS (All storage operations use repository layer)
# ============================================================================

def _is_internal_ip(ip: str) -> bool:
    """Check if IP is internal/private"""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        octets = [int(p) for p in parts]
        
        # 10.0.0.0 - 10.255.255.255
        if octets[0] == 10:
            return True
        
        # 172.16.0.0 - 172.31.255.255
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        
        # 192.168.0.0 - 192.168.255.255
        if octets[0] == 192 and octets[1] == 168:
            return True
        
        # 127.0.0.0 - 127.255.255.255 (loopback)
        if octets[0] == 127:
            return True
        
        return False
    except:
        return False


def _get_ip_reputation(ip: str, historical_data: Dict[str, Any]) -> str:
    """Get IP reputation from historical data"""
    return historical_data.get('ip_reputation', {}).get(ip, 'unknown')


def _is_common_username(username: str) -> bool:
    """Check if username is common default"""
    common = {'admin', 'root', 'test', 'guest', 'user', 'administrator'}
    return username.lower() in common


def _count_user_history(username: str, historical_data: Dict[str, Any]) -> int:
    """Count how many times user appears in history"""
    return historical_data.get('user_counts', {}).get(username, 0)


def _is_common_port(port: int) -> bool:
    """Check if port is commonly used"""
    common_ports = {22, 80, 443, 3306, 5432, 8080, 8443, 27017, 6379}
    return port in common_ports


def _is_suspicious_user_agent(ua: str) -> bool:
    """Detect suspicious user-agent strings"""
    if not ua:
        return False
    
    ua_lower = ua.lower()
    suspicious_patterns = ['sqlmap', 'nmap', 'nikto', 'masscan', 'zap', 'burp']
    
    return any(pattern in ua_lower for pattern in suspicious_patterns)


def _extract_hour(timestamp: str) -> int:
    """Extract hour of day from ISO timestamp"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.hour
    except:
        return -1


def _get_historical_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch relevant historical data for context
    
    Uses repository layer for all queries.
    Stub implementation - can be extended with IP reputation, user patterns, etc.
    """
    historical_data = {
        'ip_reputation': {},
        'user_counts': {}
    }
    
    try:
        # TODO: Query IP reputation via alert_repo.get_ip_reputation()
        # TODO: Query user patterns via event_repo.query_logs()
        pass
    except Exception as e:
        logger.warning(f"Error fetching historical data: {e}")
    
    return historical_data


# ============================================================================
# WEBSOCKET EVENT EMISSION (Push to API for broadcast)
# ============================================================================

def _api_auth_headers() -> Dict[str, str]:
    """Build authorization headers for internal core→API calls."""
    if ADMIN_TOKEN:
        return {'Authorization': f'Bearer {ADMIN_TOKEN}'}
    return {}

def emit_event_to_websocket(event_data: Dict[str, Any]) -> bool:
    """
    Emit successfully-stored event to API WebSocket channel.
    
    Flow: Core stores event in DB → calls this function → API broadcasts to clients
    
    Args:
        event_data: Complete event object with threat analysis
        
    Returns:
        True if emission succeeded, False otherwise
    """
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-event",
            json=event_data,
            headers=_api_auth_headers(),
            timeout=5
        )
        
        if response.status_code in (200, 201):
            logger.info(f"Event {event_data.get('id', 'unknown')} emitted to WebSocket")
            return True
        else:
            logger.warning(f"Failed to emit event: API returned {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit event to WebSocket: {e}")
        return False


def emit_alert_to_websocket(alert_data: Dict[str, Any]) -> bool:
    """
    Emit successfully-created alert to API WebSocket channel.
    
    Flow: Core/Ingestor creates alert in DB → calls this function → API broadcasts to clients
    
    Args:
        alert_data: Complete alert object
        
    Returns:
        True if emission succeeded, False otherwise
    """
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-alert",
            json=alert_data,
            headers=_api_auth_headers(),
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"Alert {alert_data.get('id', 'unknown')} emitted to WebSocket")
            return True
        else:
            logger.warning(f"Failed to emit alert: API returned {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit alert to WebSocket: {e}")
        return False


def emit_response_to_websocket(response_data: Dict[str, Any]) -> bool:
    """
    Emit response action updates (e.g., ip_blocked) to API WebSocket channel.

    Flow: Core enforces response → calls this function → API broadcasts to clients

    Args:
        response_data: Response payload from enforcement

    Returns:
        True if emission succeeded, False otherwise
    """
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-response",
            json=response_data,
            headers=_api_auth_headers(),
            timeout=5
        )

        if response.status_code == 200:
            logger.info(f"Response emitted to WebSocket for {response_data.get('ip_address', 'unknown')}")
            return True
        else:
            logger.warning(f"Failed to emit response: API returned {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit response to WebSocket: {e}")
        return False


def emit_policy_decision_to_websocket(decision_data: Dict[str, Any]) -> bool:
    """
    Emit policy decisions to API WebSocket channel.

    Flow: Core evaluates policy → calls this function → API broadcasts to clients
    """
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-policy",
            json=decision_data,
            headers=_api_auth_headers(),
            timeout=5
        )

        if response.status_code == 200:
            logger.info(f"Policy decision emitted for {decision_data.get('source_ip', 'unknown')}")
            return True
        else:
            logger.warning(f"Failed to emit policy decision: API returned {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit policy decision to WebSocket: {e}")
        return False


def emit_policy_update_to_websocket(policy_data: Dict[str, Any]) -> bool:
    """
    Emit policy configuration updates to API WebSocket channel.
    """
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-policy-update",
            json=policy_data,
            headers=_api_auth_headers(),
            timeout=5
        )
        if response.status_code == 200:
            logger.info("Policy update emitted to WebSocket")
            return True
        logger.warning(f"Failed to emit policy update: API returned {response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit policy update to WebSocket: {e}")
        return False


def emit_escalation_to_websocket(escalation_data: Dict[str, Any]) -> bool:
    """Emit behavioral escalation events to API WebSocket channel."""
    try:
        response = requests.post(
            f"{API_URL}/api/v1/emit-escalation",
            json=escalation_data,
            headers=_api_auth_headers(),
            timeout=5
        )

        if response.status_code == 200:
            logger.info(f"Escalation emitted for {escalation_data.get('ip', 'unknown')}")
            return True
        logger.warning(f"Failed to emit escalation: API returned {response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to emit escalation to WebSocket: {e}")
        return False


def _tag_event_ttps(event_id: str, event_data: Dict[str, Any]) -> None:
    """Fire-and-forget: classify and store MITRE TTPs for an event."""
    conn = None
    cursor = None
    try:
        llm_url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")

        metadata = event_data.get('metadata') if isinstance(event_data.get('metadata'), dict) else {}
        raw_log = str(event_data.get('raw_log', '') or '')
        uri = str(
            event_data.get('uri')
            or event_data.get('path')
            or metadata.get('uri')
            or metadata.get('path')
            or raw_log
        )[:500]

        source_ip = ''
        ip_address = event_data.get('ip_address')
        if isinstance(ip_address, dict):
            source_ip = str(ip_address.get('source') or ip_address.get('src') or '')
        else:
            source_ip = str(event_data.get('source_ip') or event_data.get('ip_address') or '')

        payload = {
            'event_type': str(event_data.get('event_type', '')),
            'attack_type': str(event_data.get('attack_type', 'normal')),
            'source_ip': source_ip,
            'uri': uri,
            'score': int(event_data.get('threat_score', 0) or 0),
            'intent': str(event_data.get('intent', 'Benign')),
            'graph_threat': bool(event_data.get('graph_threat', False)),
            'uri_path_diversity': int(event_data.get('uri_path_diversity', 0) or 0),
            'request_rate_60s': int(event_data.get('request_rate_60s', 0) or 0),
        }

        resp = requests.post(
            f"{llm_url}/classify-ttp",
            json=payload,
            timeout=5,
        )

        if resp.status_code != 200:
            return

        ttps = resp.json().get('ttps', [])
        if not ttps:
            return

        conn = event_repo.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE security_logs SET mitre_ttps = %s::jsonb WHERE event_id = %s",
            (json.dumps(ttps), event_id),
        )
        conn.commit()
    except Exception as exc:
        logger.debug("TTP tagging failed for event %s: %s", event_id, exc)
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        if conn:
            event_repo.return_connection(conn)


# ============================================================================
# FLASK ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """
    Internal health endpoint
    
    Checks:
    - Service is running
    - Database connectivity via repository
    - Detection pipeline status
    """
    db_healthy = event_repo.is_healthy()
    
    return jsonify({
        'status': 'healthy' if db_healthy else 'unhealthy',
        'service': 'mayasec-core',
        'database': 'connected' if db_healthy else 'disconnected',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'pipeline': {
            'feature_extractor': 'ready',
            'correlation_engine': 'ready',
            'detection_pipeline': 'ready'
        }
    }), 200 if db_healthy else 503


@app.route('/api/events/process', methods=['POST'])
def process_events():
    """
    Process normalized events from ingestor
    
    Input contract: Events MUST conform to canonical schema
    (validated by InputContract)
    
    All database operations use repository layer.
    No raw SQL outside repository.py
    
    Expected JSON:
    {
        "events": [
            { normalized event 1 },
            { normalized event 2 },
            ...
        ]
    }
    
    Output: Enriched events with threat analysis
    """
    try:
        data = request.get_json()
        
        if not data or 'events' not in data:
            return jsonify({'error': 'No events provided'}), 400
        
        events = data['events']
        if not isinstance(events, list):
            return jsonify({'error': 'events must be an array'}), 400
        
        if len(events) == 0:
            return jsonify({'error': 'events array cannot be empty'}), 400
        
        # Check database health via repository
        if not event_repo.is_healthy():
            return jsonify({'error': 'Database unavailable'}), 503
        
        # Initialize dependency-injected threat analysis
        correlation_engine = CorrelationEngine(event_repo)
        threat_analysis_engine = ThreatAnalysis(correlation_engine)
        correlation_id_engine = CorrelationIdEngine(db_connection_getter=None)
        
        # Validate and process each event
        processed = 0
        failed = []
        enriched_events = []
        
        for event in events:
            event_id = event.get('event_id', 'unknown')
            
            # STRICT INPUT VALIDATION (at service boundary)
            is_valid, error_msg = InputContract.validate(event)
            if not is_valid:
                logger.warning(f"Input contract violation for {event_id}: {error_msg}")
                failed.append({
                    'event_id': event_id,
                    'error': error_msg
                })
                continue
            
            try:
                # Guarantee correlation_id BEFORE response/enforcement
                event = correlation_id_engine.guarantee_correlation_id(event)
                # Update shared in-memory session correlation graph.
                _update_session_graph(event)
                # Threat analysis (orchestrated with injected dependencies)
                analysis_result = threat_analysis_engine.analyze(event)
                
                # Enrich event (add analysis results without modifying input)
                enriched_event = {
                    **event,
                    'threat_analysis': analysis_result
                }
                enriched_events.append(enriched_event)
                
                # Store enriched event via repository layer
                if event_repo.create_event(event, analysis_result):
                    schedule_graph_write(event)

                    processed += 1
                    logger.info(f"Processed event {event_id} - Score: {analysis_result['threat_score']}")

                    ttp_event_data = {
                        **event,
                        'threat_score': analysis_result.get('threat_score', 0),
                        'graph_threat': bool(analysis_result.get('graph_threat', False)),
                    }
                    threading.Thread(
                        target=_tag_event_ttps,
                        args=(str(event_id), ttp_event_data),
                        daemon=True,
                    ).start()

                    # Response plane enforcement BEFORE any WebSocket emission
                    response_engine.unblock_expired()
                    candidate = response_engine.build_candidate(enriched_event)
                    if candidate:
                        decision = policy_engine.evaluate(
                            enriched_event,
                            correlation_state=None,
                            asset_metadata=enriched_event.get('metadata')
                        )
                        decision_payload = {
                            'event_id': event_id,
                            'correlation_id': enriched_event.get('correlation_id'),
                            'source_ip': candidate.get('ip_address'),
                            'action': decision.action,
                            'reason': decision.reason,
                            'mode': decision.mode,
                            'safeguards': decision.safeguards,
                            'attack_phase': None,
                            'phase_reason': None,
                            'phase_confidence': None,
                            'timestamp': datetime.utcnow().isoformat() + 'Z'
                        }
                        emit_policy_decision_to_websocket(decision_payload)

                        if decision.action == 'enforce':
                            if enforcement_service.is_blocked(candidate['ip_address']):
                                response_result = {
                                    'status': 'blocked',
                                    'ip_address': candidate['ip_address'],
                                    'reason': 'already_blocked',
                                    'correlation_id': candidate.get('correlation_id'),
                                    'is_permanent': candidate.get('is_permanent', False),
                                    'expires_at': None,
                                    'action': 'block_ip',
                                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                                }
                                emit_response_to_websocket(response_result)
                            else:
                                response_result = enforcement_service.block_ip(
                                    ip_address=candidate['ip_address'],
                                    reason=candidate['reason'],
                                    correlation_id=candidate.get('correlation_id'),
                                    is_permanent=candidate.get('is_permanent', False),
                                    ttl_hours=candidate.get('ttl_hours'),
                                    threat_level=candidate.get('threat_level'),
                                    metadata=candidate.get('metadata')
                                )
                                response_result = {
                                    **response_result,
                                    'action': 'block_ip',
                                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                                }
                                emit_response_to_websocket(response_result)
                    
                    # Emit to WebSocket for real-time frontend updates
                    # Send the enriched event with threat analysis included
                    emit_event_to_websocket(enriched_event)
                else:
                    failed.append({
                        'event_id': event_id,
                        'error': 'Storage failed'
                    })
                    
            except Exception as e:
                logger.error(f"Error processing event {event_id}: {e}")
                failed.append({
                    'event_id': event_id,
                    'error': str(e)
                })
        
        return jsonify({
            'status': 'processed',
            'processed': processed,
            'failed': len(failed),
            'failed_details': failed if failed else None,
            'enriched_events': enriched_events if len(enriched_events) <= 10 else None,  # Return first 10
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 200 if not failed else 207
        
    except Exception as e:
        logger.error(f"Error processing events: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/events/ingest', methods=['POST'])
def ingest_events():
    """
    Store normalized events and run deterministic correlation + escalation.
    No event WebSocket emission (API handles event broadcasts).
    Policy engine gates enforcement decisions.
    """
    try:
        data = request.get_json()

        if not data or 'events' not in data:
            return jsonify({'error': 'No events provided'}), 400

        events = data['events']
        if not isinstance(events, list) or len(events) == 0:
            return jsonify({'error': 'events must be a non-empty array'}), 400

        if not event_repo.is_healthy():
            return jsonify({'error': 'Database unavailable'}), 503

        processed = 0
        failed = []

        corr_engine = CorrelationEscalationEngine(event_repo, alert_repo, enforcement_service)

        for event in events:
            event_id = event.get('event_id', 'unknown')

            # Minimal contract for ingestion
            for field in ('event_id', 'event_type', 'timestamp', 'source', 'sensor_id', 'severity', 'raw_log'):
                if field not in event:
                    failed.append({'event_id': event_id, 'error': f"Missing required field: {field}"})
                    event = None
                    break
            if event is None:
                continue

            # Ensure correlation_id is NULL at ingestion
            event['correlation_id'] = None

            analysis = {
                'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
                'threat_score': 0,
                'threat_level': event.get('severity', 'low'),
                'analysis_reason': 'ingestion-only'
            }

            if event_repo.create_event(event, analysis):
                schedule_graph_write(event)

                processed += 1

                ttp_event_data = {
                    **event,
                    'threat_score': analysis.get('threat_score', 0),
                    'graph_threat': bool(analysis.get('graph_threat', False)),
                }
                threading.Thread(
                    target=_tag_event_ttps,
                    args=(str(event_id), ttp_event_data),
                    daemon=True,
                ).start()

                # Correlate and escalate (emit alerts and apply policy)
                correlation_result = corr_engine.process_event(event)
                if correlation_result.get('alert_data'):
                    emit_alert_to_websocket(correlation_result['alert_data'])

                if correlation_result.get('response_candidate'):
                    response_engine.unblock_expired()
                    candidate = correlation_result['response_candidate']
                    decision = policy_engine.evaluate(
                        event,
                        correlation_state=correlation_result.get('correlation_state'),
                        asset_metadata=event.get('metadata')
                    )
                    attack_context = (correlation_result.get('correlation_state') or {}).get('attack_context') or {}
                    decision_payload = {
                        'event_id': event_id,
                        'correlation_id': candidate.get('correlation_id'),
                        'source_ip': candidate.get('ip_address'),
                        'action': decision.action,
                        'reason': decision.reason,
                        'mode': decision.mode,
                        'safeguards': decision.safeguards,
                        'attack_phase': attack_context.get('phase'),
                        'phase_reason': attack_context.get('reason'),
                        'phase_confidence': attack_context.get('confidence'),
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    }
                    emit_policy_decision_to_websocket(decision_payload)

                    if decision.action == 'enforce':
                        if enforcement_service.is_blocked(candidate['ip_address']):
                            response_result = {
                                'status': 'blocked',
                                'ip_address': candidate['ip_address'],
                                'reason': 'already_blocked',
                                'correlation_id': candidate.get('correlation_id'),
                                'is_permanent': candidate.get('is_permanent', False),
                                'expires_at': None,
                                'action': 'block_ip',
                                'timestamp': datetime.utcnow().isoformat() + 'Z'
                            }
                            emit_response_to_websocket(response_result)
                        else:
                            response_result = enforcement_service.block_ip(
                                ip_address=candidate['ip_address'],
                                reason=candidate['reason'],
                                correlation_id=candidate.get('correlation_id'),
                                is_permanent=candidate.get('is_permanent', False),
                                ttl_hours=candidate.get('ttl_hours'),
                                threat_level=candidate.get('threat_level'),
                                metadata=candidate.get('metadata')
                            )
                            response_result = {
                                **response_result,
                                'action': 'block_ip',
                                'timestamp': datetime.utcnow().isoformat() + 'Z'
                            }
                            emit_response_to_websocket(response_result)
            else:
                failed.append({'event_id': event_id, 'error': 'Storage failed'})

        return jsonify({
            'status': 'ingested',
            'processed': processed,
            'failed': len(failed),
            'failed_details': failed if failed else None,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 200 if not failed else 207

    except Exception as e:
        logger.error(f"Error ingesting events: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Return core service detailed status"""
    db_healthy = event_repo.is_healthy()
    
    return jsonify({
        'service': 'mayasec-core',
        'status': 'running',
        'database': 'connected' if db_healthy else 'disconnected',
        'components': {
            'input_contract': 'enforced',
            'feature_extractor': 'active',
            'correlation_engine': 'active',
            'detection_pipeline': f"{len(DetectionPipeline.RULES)} rules loaded",
            'threat_analysis': 'active',
            'repository_layer': 'active'
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200


@app.route('/api/sessions/graph', methods=['GET'])
def sessions_graph_snapshot():
    """Return read-only snapshot of the in-memory session correlation graph."""
    try:
        return jsonify(session_graph.snapshot()), 200
    except Exception as e:
        logger.error(f"Session graph snapshot failed: {e}")
        return jsonify([]), 200


@app.route('/api/behavioral/score', methods=['POST'])
def behavioral_score():
    """Score ingress telemetry features with fail-open behavior for proxy safety."""
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}

        if isinstance(payload.get('features'), dict):
            features = payload['features']
        else:
            # Support flat feature-vector payload directly in request body.
            features = payload

        # Feed shared session graph from ingress behavioral payload when present.
        _update_session_graph(features)
        graph_threat = _get_graph_threat_for_request(features)

        result = behavioral_scorer.score(features)
        result['graph_threat'] = bool(graph_threat)

        source_ip, _, _ = _extract_session_graph_fields(features)
        decision = response_escalator.evaluate(source_ip or '0.0.0.0', result)
        result['escalation_tier'] = int(decision.get('tier', 0))

        if int(decision.get('tier', 0)) == 3 and source_ip:
            try:
                try:
                    # Requested integration contract
                    enforcement_service.block_ip(source_ip)
                except TypeError:
                    # Backward-compatible call path for current EnforcementService signature
                    enforcement_service.block_ip(
                        ip_address=source_ip,
                        reason='behavioral_escalation_tier_3',
                        correlation_id='behavioral_escalator',
                        is_permanent=False,
                        metadata={
                            'engine': 'response_escalator',
                            'intent': result.get('intent'),
                            'graph_threat': result.get('graph_threat'),
                            'escalation_tier': 3,
                        },
                        threat_level='high'
                    )
            except Exception as e:
                logger.warning(f"Tier-3 block enforcement failed for {source_ip}: {e}")

        if int(decision.get('tier', 0)) >= 1 and source_ip:
            emit_escalation_to_websocket({
                'ip': source_ip,
                'tier': int(decision.get('tier', 0)),
                'reason': str(decision.get('reason', 'escalation condition met')),
                'intent': result.get('intent'),
                'graph_threat': bool(result.get('graph_threat', False)),
            })

        # Enforce stable output schema regardless of scorer internals.
        response = {
            'intent': str(result.get('intent', 'Benign')),
            'anomaly_score': float(result.get('anomaly_score', 0.0)),
            'deception_trigger': bool(result.get('deception_trigger', False)),
            'graph_threat': bool(result.get('graph_threat', False)),
            'escalation_tier': int(result.get('escalation_tier', 0)),
        }
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Behavioral scoring failed (fail-open): {e}")
        return jsonify(_BEHAVIORAL_FAIL_OPEN), 200


@app.route('/api/behavioral/history', methods=['GET'])
def behavioral_history():
    """Return recent behavioral baseline history for a source IP."""
    conn = None
    try:
        ip = request.args.get('ip', '')
        hours = int(request.args.get('hours', 24))
        limit = int(request.args.get('limit', 100))

        conn = event_repo.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                intent,
                anomaly_score,
                graph_threat,
                recorded_at,
                feature_vector
            FROM behavioral_baselines
            WHERE source_ip::text = %s
              AND recorded_at >= NOW() - (%s * INTERVAL '1 hour')
            ORDER BY recorded_at DESC
            LIMIT %s
            ''',
            (ip, hours, limit)
        )
        rows = cursor.fetchall()
        cursor.close()

        return jsonify(rows), 200
    except Exception as e:
        logger.error(f"Behavioral history query failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            event_repo.return_connection(conn)


@app.route('/api/behavioral/sessions', methods=['GET'])
def behavioral_sessions():
    """Return current SessionGraph snapshot for behavioral correlation visibility."""
    try:
        return jsonify(session_graph.snapshot()), 200
    except Exception as e:
        logger.error(f"Behavioral sessions snapshot failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/behavioral/drift', methods=['GET'])
def behavioral_drift_state():
    """Return current drift detector state used by retraining workflow."""
    try:
        payload = {
            'needs_retrain': bool(drift_detector.needs_retraining()),
            'retrain_needed': bool(drift_detector.retrain_needed),
            'window_size': len(drift_detector.scores_window),
            'baseline_mean': float(drift_detector.baseline_mean),
            'baseline_std': float(drift_detector.baseline_std),
        }

        if hasattr(drift_detector, 'last_drift_at'):
            payload['last_drift_at'] = getattr(drift_detector, 'last_drift_at')

        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"Behavioral drift state query failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/honeypot/capture', methods=['POST'])
def store_honeypot_capture():
    """Store honeypot interaction from victim-web."""
    conn = None
    cursor = None
    try:
        data = request.get_json(force=True) or {}
        conn = event_repo.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO honeypot_captures (tenant_id, session_id, source_ip, attack_type, request_payload, llm_response, persona_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''',
            (
                data.get('tenant_id'),
                data.get('session_id', ''),
                data.get('source_ip', '0.0.0.0'),
                data.get('attack_type', 'unknown'),
                data.get('request_payload', ''),
                data.get('llm_response', ''),
                data.get('persona_type', ''),
            )
        )
        conn.commit()
        return jsonify({'status': 'captured'}), 201
    except Exception as e:
        logger.error(f"Honeypot capture storage failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        if conn:
            event_repo.return_connection(conn)


# Schema detection: detect once at startup which baseline table schema is available.
_BASELINE_SCHEMA: Optional[str] = None  # 'preferred' or 'legacy'


def _detect_baseline_schema() -> str:
    """Probe the behavioral_baselines table once to decide schema variant."""
    global _BASELINE_SCHEMA
    if _BASELINE_SCHEMA is not None:
        return _BASELINE_SCHEMA

    conn = None
    try:
        conn = event_repo.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'behavioral_baselines' AND column_name = 'confirmed_by'"
        )
        row = cursor.fetchone()
        cursor.close()
        _BASELINE_SCHEMA = 'preferred' if row else 'legacy'
    except Exception:
        _BASELINE_SCHEMA = 'legacy'
    finally:
        if conn is not None:
            event_repo.return_connection(conn)
    return _BASELINE_SCHEMA


@app.route('/api/behavioral/feedback', methods=['POST'])
def behavioral_feedback():
    """Store confirmed behavioral feedback samples for baseline/model improvement."""
    conn = None
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}

        feature_vector = payload.get('feature_vector', [])
        intent = str(payload.get('intent', 'Benign'))
        confirmed_by = str(payload.get('confirmed_by', 'unknown'))
        now = datetime.utcnow()

        conn = event_repo.get_connection()
        cursor = conn.cursor()

        feature_vector_json = json.dumps(feature_vector)
        schema = _detect_baseline_schema()

        if schema == 'preferred':
            cursor.execute(
                '''
                INSERT INTO behavioral_baselines (feature_vector, intent, confirmed_by, recorded_at, source_ip)
                VALUES (%s::jsonb, %s, %s, %s, %s)
                ''',
                (feature_vector_json, intent, confirmed_by, now, '0.0.0.0')
            )
        else:
            cursor.execute(
                '''
                INSERT INTO behavioral_baselines (feature_vector, intent, attack_type, recorded_at, source_ip)
                VALUES (%s::jsonb, %s, %s, %s, %s)
                ''',
                (feature_vector_json, intent, confirmed_by, now, '0.0.0.0')
            )

        conn.commit()
        cursor.close()

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Behavioral feedback insert failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            event_repo.return_connection(conn)


@app.route('/api/policy', methods=['GET', 'POST'])
def policy_state():
    if request.method == 'GET':
        return jsonify(policy_engine.get_state()), 200

    payload = request.get_json() or {}
    mode = payload.get('mode')
    allowlist = payload.get('allowlist')
    max_blocks = payload.get('max_blocks_per_hour')

    if allowlist is not None and not isinstance(allowlist, list):
        return jsonify({'error': 'allowlist must be a list'}), 400

    updated = policy_engine.update(
        mode=mode,
        allowlist=allowlist,
        max_blocks_per_hour=max_blocks
    )

    emit_policy_update_to_websocket({
        **updated,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

    return jsonify(updated), 200


if __name__ == '__main__':
    logger.info(f"Starting MAYASEC Core on port {CORE_PORT}")
    logger.info(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Input contract enforcement: ENABLED")
    app.run(host='0.0.0.0', port=CORE_PORT, debug=False)
