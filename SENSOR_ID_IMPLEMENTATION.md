"""
Sensor Identification Support - Implementation Summary

This document describes the sensor_id feature added to the Mayasec system,
enabling multi-sensor event tracking and attribution.
"""

# DATABASE SCHEMA CHANGES
# ======================

# 1. security_logs table now includes sensor_id column:
#    ALTER TABLE security_logs ADD COLUMN sensor_id TEXT DEFAULT 'local-sensor'
#    
#    Existing rows get the default value 'local-sensor'
#    New rows can specify a custom sensor_id or use the default

# 2. honeypot_logs table now includes sensor_id column:
#    ALTER TABLE honeypot_logs ADD COLUMN sensor_id TEXT DEFAULT 'local-sensor'
#    
#    Tracks which sensor/honeypot instance detected the attack


# FUNCTION SIGNATURES - UPDATED
# ==============================

# app.py - Core logging functions:
# --------------------------------

def log_security_event(
    ip_address,
    username,
    action,
    user_agent=None,
    threat_level='LOW',
    blocked=False,
    reason="working",
    sensor_id="local-sensor"  # NEW PARAMETER
):
    """
    Log a security event to the database.
    
    Args:
        ip_address: IP address associated with the event
        username: Username (optional)
        action: Type of action (LOGIN_ATTEMPT, BLOCKED_ACCESS_ATTEMPT, etc.)
        user_agent: HTTP User-Agent header (optional)
        threat_level: Threat level (LOW, MEDIUM, HIGH, CRITICAL)
        blocked: Whether the action was blocked
        reason: Explanation/reasoning from AI analysis
        sensor_id: Identifier of the sensor that detected this event (default: "local-sensor")
    """
    pass


def log_honeypot_interaction(
    ip_address,
    username,
    password,
    user_agent=None,
    sensor_id="local-sensor"  # NEW PARAMETER
):
    """
    Log a honeypot interaction.
    
    Args:
        ip_address: Attacker IP address
        username: Username attempted
        password: Password attempted
        user_agent: Browser User-Agent (optional)
        sensor_id: Identifier of the honeypot sensor (default: "local-sensor")
    """
    pass


# log_ingestion.py - All ingestion routes now extract and pass sensor_id:
# ------------------------------------------------------------------------

# 1. _ingest_login_event() - Extracts sensor_id from event_json
# 2. _ingest_honeypot_event() - Extracts sensor_id, passes to both log functions
# 3. _ingest_network_alert_event() - Extracts sensor_id for network alerts
# 4. _ingest_security_action_event() - Extracts sensor_id for generic events


# API USAGE - POST /api/ingest/event
# ===================================

# Example payload with sensor_id:
payload = {
    "source": "suricata",
    "sensor_id": "suricata-main-sensor",  # <-- Identifies the sensor
    "timestamp": "2026-01-15T10:35:00Z",
    "data": {
        "event_type": "network_alert",
        "src_ip": "10.0.0.5",
        "dest_ip": "8.8.8.8",
        "src_port": 54321,
        "dest_port": 443,
        "proto": "TCP",
        "alert": {
            "signature": "ET POLICY Suspicious DNS",
            "severity_name": "HIGH"
        }
        # sensor_id is extracted from request and merged into event_data
    }
}


# BACKWARD COMPATIBILITY
# ======================

# ✅ All sensor_id parameters have default values ("local-sensor")
# ✅ Old database rows without sensor_id are assigned default on schema migration
# ✅ Existing code that doesn't pass sensor_id continues to work
# ✅ No breaking changes to function signatures


# MIGRATION BEHAVIOR
# ==================

# When init_database() runs:
# 1. Creates new tables with sensor_id column and DEFAULT 'local-sensor'
# 2. For existing databases, ALTER TABLE adds sensor_id column with default
#    - Existing rows automatically get sensor_id = 'local-sensor'
#    - New rows can have custom sensor_id values


# SENSOR ID FLOW DIAGRAM
# ======================

# HTTP Request                API Endpoint              Ingestion Module        Storage
# ──────────────────────  ───────────────────────  ─────────────────────  ──────────────
#
# POST /api/ingest/event
# {
#   "source": "...",
#   "sensor_id": "sensor-1",  ──→  api_ingest_event()  ──→  ingest_event()  ──→  log_security_event()
#   "timestamp": "...",                                         [extracts]         [stores with
#   "data": {...}                                              sensor_id           sensor_id]
# }
#
#                                                    ↓
#                                             Routes to appropriate
#                                             _ingest_*_event() function
#                                             (all pass sensor_id)


# QUERYING BY SENSOR
# ==================

# Example SQL to filter events by sensor:
# SELECT * FROM security_logs WHERE sensor_id = 'suricata-main-sensor';
# SELECT * FROM honeypot_logs WHERE sensor_id = 'honeypot-01';

# Example SQL to get sensor statistics:
# SELECT sensor_id, COUNT(*) as event_count
# FROM security_logs
# GROUP BY sensor_id
# ORDER BY event_count DESC;


# SENSOR ID NAMING CONVENTION (RECOMMENDED)
# ==========================================

# To make sensor identification consistent and meaningful, use names like:
#
# For Suricata IDS:
#   - "suricata-main"
#   - "suricata-dmz"
#   - "suricata-internal"
#
# For Honeypots:
#   - "honeypot-web"
#   - "honeypot-ssh"
#   - "honeypot-smtp"
#
# For Web Application:
#   - "web-app-prod"
#   - "web-app-staging"
#
# For Local Events (default):
#   - "local-sensor" (automatic default)


# MULTI-SENSOR DEPLOYMENT SCENARIO
# =================================

# Imagine a network with multiple sensors feeding into this system:
#
# Suricata IDS (192.168.1.100)  ──┐
#   sensor_id: "suricata-main"    │
#                                  ├──→ POST /api/ingest/event ──→ Mayasec
#                                  │
# Honeypot (192.168.1.101)        │
#   sensor_id: "honeypot-web"    ─┤
#                                  │
# Log Aggregator (192.168.1.102)  │
#   sensor_id: "log-agg-01"      ─┘
#
# All events are stored with their sensor origin, enabling:
# - Per-sensor analysis
# - Multi-source correlation
# - Sensor health monitoring


# IMPLEMENTATION NOTES
# ====================

# 1. Default value "local-sensor" ensures backward compatibility
# 2. sensor_id is extracted from the API request metadata
# 3. All ingestion routes respect the sensor_id from the request
# 4. Database ALTER TABLE statements are wrapped in try-except to handle
#    cases where the column already exists
# 5. No existing API endpoints have been modified - sensor_id is purely additive

"""

# TESTING SENSOR IDENTIFICATION
# ==============================

# Run test_ingest_api.py to verify sensor_id functionality:
#   python test_ingest_api.py
#
# The test script includes examples of:
# ✓ Login events with sensor_id
# ✓ Network alerts with sensor_id
# ✓ Honeypot interactions with sensor_id
# ✓ Default fallback when sensor_id not provided
