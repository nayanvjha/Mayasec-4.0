"""
INGESTOR INTEGRATION GUIDE

The mayasec-ingestor service is the single entry point for all security events.

ENDPOINTS:

1. POST /api/ingest/event
   Single event ingestion
   
   Example:
   curl -X POST http://localhost:5001/api/ingest/event \
     -H "Content-Type: application/json" \
     -d '{
       "event_type": "login_attempt",
       "timestamp": "2026-01-15T10:30:00Z",
       "source": "http_api",
       "sensor_id": "webserver-01",
       "severity": "medium",
       "ip_address": {
         "source": "192.168.1.100"
       },
       "username": "admin",
       "user_agent": "Mozilla/5.0",
       "action": "blocked",
       "reason": "Failed authentication"
     }'

2. POST /api/ingest/batch
   Batch event ingestion (up to 1000 events)
   
   Example:
   curl -X POST http://localhost:5001/api/ingest/batch \
     -H "Content-Type: application/json" \
     -d '{
       "events": [
         { event 1 },
         { event 2 },
         ...
       ]
     }'

3. POST /api/ingest/flush
   Force flush all queued events to mayasec-core
   
   curl -X POST http://localhost:5001/api/ingest/flush

4. GET /health
   Health check endpoint

5. GET /api/status
   Ingestor status (queue size, etc.)


EXPECTED EVENT SCHEMA:

All events must conform to the canonical schema defined in event_schema.json

Required fields:
- event_type: login_attempt | honeypot_interaction | network_alert | security_action | ...
- timestamp: ISO 8601 format (e.g., "2026-01-15T10:30:00Z")
- source: http_api | log_file | ids | firewall | honeypot | syslog | web_application | custom
- sensor_id: Identifier of the sensor/host that collected the event

Optional fields (depends on event type):
- ip_address: Object with source and/or destination IPs
- port: Object with source and/or destination ports
- protocol: Network protocol (TCP, UDP, HTTP, SSH, etc.)
- username: Username involved
- user_agent: Client identification string
- alert: IDS alert details (signature_id, signature, category, severity_level)
- action: Event disposition (allowed, blocked, logged, redirected, quarantined, escalated)
- reason: Human-readable explanation
- threat_analysis: AI/ML analysis results (threat_score, threat_level, analysis_reason)
- metadata: Additional contextual data


NORMALIZATION:

The ingestor automatically normalizes events from various sources:

1. Login Events (from any web app, SSH, FTP, etc.)
   Source: "http_api", "log_file", "syslog"
   Maps to: event_type = "login_attempt"

2. Honeypot Events
   Source: "honeypot"
   Maps to: event_type = "honeypot_interaction"

3. Network/IDS Alerts
   Source: "ids", "firewall"
   Works with ANY IDS format (Suricata, Snort, etc.)
   Normalizes src_ip → ip_address.source
   Normalizes dest_ip → ip_address.destination
   Normalizes alert.signature_id or sid → alert.signature_id
   Maps to: event_type = "network_alert"

4. Generic Security Actions
   Any other event type
   Maps to: event_type = "security_action"


INTERNAL FLOW:

Ingestor (port 5001)
  ↓ (validate + normalize)
Event Queue (in-memory, max 100 events)
  ↓ (when queue full or explicit flush)
mayasec-core API (http://mayasec-core:5002/api/events/process)
  ↓ (threat analysis, correlation, storage)
PostgreSQL (security_logs, honeypot_logs, etc.)


CONFIGURATION:

Environment variables (set via .env or docker-compose.yml):
- INGESTOR_PORT: Service port (default: 5001)
- CORE_SERVICE_URL: mayasec-core endpoint (default: http://mayasec-core:5002)
- LOG_LEVEL: Logging level (default: INFO)
- LOG_DIR: Log file directory (default: /app/logs)


NO SURICATA COUPLING:

The ingestor is completely source-agnostic:
- No hardcoded /var/log/suricata/eve.json
- No Suricata binary calls
- No event_type assumptions based on source
- Supports any IDS format through normalization layer

To ingest Suricata alerts:
- Deploy suricata_forwarder.py on sensor host (separate from platform)
- Forward to http://platform:5001/api/ingest/event
- Ingestor normalizes Suricata EVE format to canonical schema
"""
