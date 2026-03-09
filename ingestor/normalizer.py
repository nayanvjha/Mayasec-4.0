"""
Event normalizer - converts external event formats to canonical schema
"""

import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
import uuid

logger = logging.getLogger('Normalizer')


def _apply_common_fields(normalized: Dict[str, Any], source_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized['sensor_type'] = source_data.get('sensor_type', 'system')
    normalized['raw_log'] = source_data.get('raw_log', '')
    normalized['correlation_id'] = source_data.get('correlation_id')

    # Source IP (top-level) and destination (host/service)
    if 'source_ip' in source_data and source_data['source_ip']:
        normalized['source_ip'] = source_data['source_ip']
    elif 'ip_address' in normalized and isinstance(normalized['ip_address'], dict):
        normalized['source_ip'] = normalized['ip_address'].get('source')
    else:
        normalized['source_ip'] = None

    if 'ip_address' not in normalized or not isinstance(normalized.get('ip_address'), dict):
        if normalized.get('source_ip'):
            normalized['ip_address'] = {'source': normalized['source_ip']}

    normalized['destination'] = source_data.get('destination')
    if not normalized['destination']:
        if 'ip_address' in normalized and isinstance(normalized['ip_address'], dict):
            dst = normalized['ip_address'].get('destination')
            dst_port = None
            if 'port' in normalized and isinstance(normalized['port'], dict):
                dst_port = normalized['port'].get('destination')
            if dst and dst_port:
                normalized['destination'] = f"{dst}:{dst_port}"
            else:
                normalized['destination'] = dst

    if normalized.get('destination') is None:
        normalized['destination'] = None

    return normalized


def normalize_login_event(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize login attempt event from any source
    
    Accepts various login formats and converts to canonical schema
    """
    normalized = {
        'event_id': source_data.get('event_id', str(uuid.uuid4())),
        'event_type': source_data.get('event_type', 'login_attempt'),
        'timestamp': source_data.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
        'source': source_data.get('source', 'http_api'),
        'sensor_id': source_data.get('sensor_id', 'unknown'),
        'severity': source_data.get('severity', 'low'),
    }
    
    # Extract IP
    if 'ip_address' in source_data:
        if isinstance(source_data['ip_address'], str):
            normalized['ip_address'] = {'source': source_data['ip_address']}
        else:
            normalized['ip_address'] = source_data['ip_address']
    
    # Extract username
    if 'username' in source_data:
        normalized['username'] = source_data['username']
    
    # Extract password (never store plaintext - hash it)
    if 'password' in source_data and source_data['password']:
        normalized['password_hash'] = hashlib.sha256(
            source_data['password'].encode()
        ).hexdigest()
    
    # Extract user agent
    if 'user_agent' in source_data:
        normalized['user_agent'] = source_data['user_agent']
    
    # Action and reason
    normalized['action'] = source_data.get('action', 'logged')
    normalized['reason'] = source_data.get('reason', 'Login attempt')
    
    # Metadata
    if 'hostname' in source_data or 'os' in source_data:
        normalized['metadata'] = {}
        if 'hostname' in source_data:
            normalized['metadata']['hostname'] = source_data['hostname']
        if 'os' in source_data:
            normalized['metadata']['os'] = source_data['os']
    
    return _apply_common_fields(normalized, source_data)


def normalize_honeypot_event(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize honeypot interaction event"""
    normalized = {
        'event_id': source_data.get('event_id', str(uuid.uuid4())),
        'event_type': source_data.get('event_type', 'honeypot_interaction'),
        'timestamp': source_data.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
        'source': source_data.get('source', 'honeypot'),
        'sensor_id': source_data.get('sensor_id', 'honeypot-unknown'),
        'severity': source_data.get('severity', 'medium'),
    }
    
    # IP address
    if 'ip_address' in source_data:
        if isinstance(source_data['ip_address'], str):
            normalized['ip_address'] = {'source': source_data['ip_address']}
        else:
            normalized['ip_address'] = source_data['ip_address']
    
    # Credentials
    if 'username' in source_data:
        normalized['username'] = source_data['username']
    
    if 'password' in source_data and source_data['password']:
        normalized['password_hash'] = hashlib.sha256(
            source_data['password'].encode()
        ).hexdigest()
    
    if 'user_agent' in source_data:
        normalized['user_agent'] = source_data['user_agent']
    
    normalized['action'] = source_data.get('action', 'logged')
    normalized['reason'] = source_data.get('reason', 'Honeypot interaction captured')
    
    return _apply_common_fields(normalized, source_data)


def normalize_network_alert_event(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize network/IDS alert (Suricata, Snort, etc.)
    Source-agnostic - works with any IDS format
    """
    normalized = {
        'event_id': source_data.get('event_id', str(uuid.uuid4())),
        'event_type': 'network_alert',
        'timestamp': source_data.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
        'source': source_data.get('source', 'ids'),
        'sensor_id': source_data.get('sensor_id', 'ids-unknown'),
        'severity': map_severity(source_data.get('severity', 'low')),
    }
    
    # IPs and ports
    if 'src_ip' in source_data or 'source_ip' in source_data:
        src = source_data.get('src_ip') or source_data.get('source_ip')
        if 'ip_address' not in normalized:
            normalized['ip_address'] = {}
        normalized['ip_address']['source'] = src
    
    if 'dest_ip' in source_data or 'destination_ip' in source_data:
        dst = source_data.get('dest_ip') or source_data.get('destination_ip')
        if 'ip_address' not in normalized:
            normalized['ip_address'] = {}
        normalized['ip_address']['destination'] = dst
    
    # Ports
    if 'src_port' in source_data or 'source_port' in source_data:
        src_port = source_data.get('src_port') or source_data.get('source_port')
        if src_port:
            if 'port' not in normalized:
                normalized['port'] = {}
            normalized['port']['source'] = int(src_port)
    
    if 'dest_port' in source_data or 'destination_port' in source_data:
        dst_port = source_data.get('dest_port') or source_data.get('destination_port')
        if dst_port:
            if 'port' not in normalized:
                normalized['port'] = {}
            normalized['port']['destination'] = int(dst_port)
    
    # Protocol
    if 'proto' in source_data or 'protocol' in source_data:
        proto = source_data.get('proto') or source_data.get('protocol')
        if proto:
            normalized['protocol'] = proto.upper()
    
    # Alert info (works with multiple IDS formats)
    alert_obj = {}
    
    # Suricata format
    if 'alert' in source_data and isinstance(source_data['alert'], dict):
        alert_src = source_data['alert']
        alert_obj['signature_id'] = alert_src.get('signature_id') or alert_src.get('sid')
        alert_obj['signature'] = alert_src.get('signature') or alert_src.get('msg')
        alert_obj['category'] = alert_src.get('category')
        if 'severity' in alert_src:
            alert_obj['severity_level'] = map_severity_to_int(alert_src['severity'])
    
    # Generic IDS format
    elif 'signature' in source_data or 'msg' in source_data:
        alert_obj['signature'] = source_data.get('signature') or source_data.get('msg')
        alert_obj['signature_id'] = source_data.get('signature_id') or source_data.get('sid')
        alert_obj['category'] = source_data.get('category')
    
    if alert_obj:
        normalized['alert'] = alert_obj
    
    normalized['action'] = source_data.get('action', 'logged')
    normalized['reason'] = source_data.get('signature') or source_data.get('reason', 'Network alert')
    
    return _apply_common_fields(normalized, source_data)


def normalize_security_action(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize generic security action event"""
    normalized = {
        'event_id': source_data.get('event_id', str(uuid.uuid4())),
        'event_type': source_data.get('event_type', 'security_action'),
        'timestamp': source_data.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
        'source': source_data.get('source', 'custom'),
        'sensor_id': source_data.get('sensor_id', 'unknown'),
        'severity': source_data.get('severity', 'low'),
    }
    
    # Copy optional fields
    for field in ['ip_address', 'username', 'user_agent', 'action', 'reason']:
        if field in source_data:
            normalized[field] = source_data[field]
    
    # Metadata
    if any(k in source_data for k in ['hostname', 'os', 'location']):
        normalized['metadata'] = {
            k: source_data[k] for k in ['hostname', 'os', 'location']
            if k in source_data
        }
    
    return _apply_common_fields(normalized, source_data)


def map_severity(severity: str) -> str:
    """Map various severity formats to canonical form"""
    severity_lower = str(severity).lower().strip()
    
    # Map to canonical levels: info, low, medium, high, critical
    severity_map = {
        'info': 'info',
        'low': 'low',
        'medium': 'medium',
        'mid': 'medium',
        'high': 'high',
        'critical': 'critical',
        'severe': 'critical',
        '1': 'critical',
        '2': 'high',
        '3': 'medium',
        '4': 'low',
        '5': 'info',
    }
    
    return severity_map.get(severity_lower, 'low')


def map_severity_to_int(severity: str) -> int:
    """Map severity to integer (1=High, 2=Medium, 3=Low)"""
    mapped = map_severity(severity)
    severity_to_int = {
        'critical': 1,
        'high': 1,
        'medium': 2,
        'low': 3,
        'info': 3,
    }
    return severity_to_int.get(mapped, 3)


def normalize_event(event: Dict[str, Any], detected_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligently normalize event from any source to canonical schema
    
    Args:
        event: Raw event data
        detected_type: Optional pre-detected event type
    
    Returns:
        Normalized event in canonical schema
    """
    # Handle wrapped payloads (e.g., {source, sensor_id, timestamp, data:{...}})
    if 'event_type' not in event and isinstance(event.get('data'), dict):
        merged = {
            **event.get('data', {}),
            'source': event.get('source', event.get('data', {}).get('source', 'custom')),
            'sensor_id': event.get('sensor_id', event.get('data', {}).get('sensor_id', 'unknown')),
            'timestamp': event.get('timestamp', event.get('data', {}).get('timestamp')),
            'raw_log': event.get('data', {}).get('raw_log') or event.get('raw_log') or event.get('data', {}).get('eve_raw')
        }
        event = merged

    event_type = detected_type or event.get('event_type', 'security_action').lower()
    
    # Route to appropriate normalizer
    if 'login' in event_type or 'authentication' in event_type:
        return normalize_login_event(event)
    elif 'honeypot' in event_type:
        return normalize_honeypot_event(event)
    elif 'network' in event_type or 'alert' in event_type or 'ids' in event_type:
        return normalize_network_alert_event(event)
    else:
        return normalize_security_action(event)
