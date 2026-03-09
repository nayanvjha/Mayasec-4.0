"""
Log Ingestion Module
Centralized event ingestion, routing to analysis and storage.
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, Optional


def ingest_event(event_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest a parsed JSON event and route to analysis and storage pipelines.
    
    Accepts normalized event dict with structure:
    {
        "event_type": "login" | "honeypot" | "network_alert" | "security_action",
        "ip_address": str,
        "username": str (optional),
        "password": str (optional, for honeypot),
        "user_agent": str (optional),
        "action": str (optional, e.g., "LOGIN_ATTEMPT", "BLOCKED_ACCESS_ATTEMPT"),
        "threat_level": str (optional, default "LOW"),
        "timestamp": datetime or str (optional),
        "reason": str (optional, AI reasoning),
        "blocked": bool (optional, default False),
        ... other fields as needed
    }
    
    Returns:
    {
        "status": "success" | "error",
        "message": str,
        "event_id": int (if stored to DB)
    }
    """
    
    try:
        # Normalize timestamp
        timestamp = event_json.get("timestamp")
        if timestamp is None:
            timestamp = datetime.now()
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                timestamp = datetime.now()
        
        # Route based on event type
        event_type = event_json.get("event_type", "security_action").lower()
        
        if event_type == "login":
            return _ingest_login_event(event_json, timestamp)
        elif event_type == "honeypot":
            return _ingest_honeypot_event(event_json, timestamp)
        elif event_type == "network_alert":
            return _ingest_network_alert_event(event_json, timestamp)
        elif event_type == "security_action":
            return _ingest_security_action_event(event_json, timestamp)
        else:
            return {
                "status": "error",
                "message": f"Unknown event type: {event_type}"
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def _ingest_login_event(event_json: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
    """
    Ingest a login event.
    Routes to: log_security_event (storage)
    """
    from app import log_security_event
    
    ip_address = event_json.get("ip_address", "UNKNOWN")
    username = event_json.get("username", "")
    action = event_json.get("action", "LOGIN_ATTEMPT")
    user_agent = event_json.get("user_agent")
    threat_level = event_json.get("threat_level", "LOW")
    blocked = event_json.get("blocked", False)
    reason = event_json.get("reason", "")
    sensor_id = event_json.get("sensor_id", "local-sensor")
    
    try:
        log_security_event(
            ip_address=ip_address,
            username=username,
            action=action,
            user_agent=user_agent,
            threat_level=threat_level,
            blocked=blocked,
            reason=reason,
            sensor_id=sensor_id
        )
        
        return {
            "status": "success",
            "message": f"Login event logged: {action}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to log login event: {str(e)}"
        }


def _ingest_honeypot_event(event_json: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
    """
    Ingest a honeypot interaction event.
    Routes to: log_honeypot_interaction (storage) and log_security_event
    """
    from app import log_honeypot_interaction, log_security_event
    
    ip_address = event_json.get("ip_address", "UNKNOWN")
    username = event_json.get("username", "")
    password = event_json.get("password", "")
    user_agent = event_json.get("user_agent")
    sensor_id = event_json.get("sensor_id", "local-sensor")
    
    try:
        # Log to honeypot table
        log_honeypot_interaction(ip_address, username, password, user_agent, sensor_id=sensor_id)
        
        # Also log to security events
        log_security_event(
            ip_address=ip_address,
            username=username,
            action="HONEYPOT_INTERACTION",
            user_agent=user_agent,
            threat_level="HIGH",
            blocked=True,
            reason="Honeypot interaction detected",
            sensor_id=sensor_id
        )
        
        return {
            "status": "success",
            "message": "Honeypot interaction logged"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to log honeypot event: {str(e)}"
        }


def _ingest_network_alert_event(event_json: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
    """
    Ingest a Suricata network alert event.
    Routes to: log_security_event (storage) with network metadata
    """
    from app import log_security_event
    
    # Extract Suricata EVE fields
    src_ip = event_json.get("src_ip")
    dest_ip = event_json.get("dest_ip")
    src_port = event_json.get("src_port", "N/A")
    dest_port = event_json.get("dest_port", "N/A")
    proto = event_json.get("proto", "UNKNOWN")
    signature = event_json.get("alert", {}).get("signature", "UNKNOWN")
    severity = event_json.get("alert", {}).get("severity_name", "LOW")
    sensor_id = event_json.get("sensor_id", "local-sensor")
    
    # Map Suricata severity to threat levels
    severity_map = {
        "CRITICAL": "CRITICAL",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW"
    }
    threat_level = severity_map.get(severity, "LOW")
    
    reason = f"Network alert: {signature} | Proto: {proto} | Dest: {dest_ip}:{dest_port}"
    
    try:
        log_security_event(
            ip_address=src_ip,
            username="",  # Network alerts don't have usernames
            action="NETWORK_ALERT",
            user_agent=None,
            threat_level=threat_level,
            blocked=False,  # Network alerts are observational
            reason=reason,
            sensor_id=sensor_id
        )
        
        return {
            "status": "success",
            "message": f"Network alert logged: {signature}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to log network alert: {str(e)}"
        }


def _ingest_security_action_event(event_json: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
    """
    Ingest a generic security action event.
    Routes to: log_security_event (storage)
    """
    from app import log_security_event
    
    ip_address = event_json.get("ip_address", "UNKNOWN")
    username = event_json.get("username", "")
    action = event_json.get("action", "SECURITY_EVENT")
    user_agent = event_json.get("user_agent")
    threat_level = event_json.get("threat_level", "LOW")
    blocked = event_json.get("blocked", False)
    reason = event_json.get("reason", "")
    sensor_id = event_json.get("sensor_id", "local-sensor")
    
    try:
        log_security_event(
            ip_address=ip_address,
            username=username,
            action=action,
            user_agent=user_agent,
            threat_level=threat_level,
            blocked=blocked,
            reason=reason,
            sensor_id=sensor_id
        )
        
        return {
            "status": "success",
            "message": f"Security action logged: {action}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to log security action: {str(e)}"
        }
