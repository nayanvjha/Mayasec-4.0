"""
MAYASEC CORE SERVICE INTERFACE SPECIFICATION

Core Service Architecture:
- Single responsibility: Analyze normalized events
- No knowledge of: data sources, sensor origins, ingestion methods
- Strict input contract enforcement
- Orthogonal analysis pipeline

INPUT INTERFACE
===============

POST /api/events/process

Request Body (JSON):
{
    "events": [
        {
            // Required fields (enforced by InputContract)
            "event_id": "uuid-v4-string",
            "event_type": "login_attempt|honeypot_interaction|network_alert|security_action|...",
            "timestamp": "2026-01-15T10:30:00Z",  // ISO 8601 with Z suffix
            "source": "http_api|log_file|ids|firewall|honeypot|...",
            "sensor_id": "string (non-empty)",
            
            // Optional contextual fields
            "severity": "info|low|medium|high|critical",
            "ip_address": { "source": "x.x.x.x", "destination": "x.x.x.x" },
            "port": { "source": int, "destination": int },
            "protocol": "TCP|UDP|HTTP|SSH|...",
            "username": "string",
            "password_hash": "sha256-hash",
            "user_agent": "string",
            "alert": { "signature_id": int, "signature": "string", "category": "string", "severity_level": int },
            "action": "allowed|blocked|logged|redirected|quarantined|escalated",
            "reason": "human-readable explanation",
            "metadata": { "hostname": "...", "os": "...", ... }
        },
        ...
    ]
}

Response (202 Accepted):
{
    "status": "processed",
    "processed": 42,          // Number of successfully analyzed events
    "failed": 2,              // Number of rejected events
    "failed_details": [
        {
            "event_id": "uuid",
            "error": "Missing required fields: event_type, timestamp"
        },
        ...
    ],
    "enriched_events": [      // First 10 processed events with analysis
        {
            ... original event ...
            "threat_analysis": {
                "analysis_timestamp": "2026-01-15T10:30:01Z",
                "features": { ... extracted features ... },
                "correlations": { ... correlation findings ... },
                "threat_score": 45,
                "threat_level": "medium",
                "analysis_reason": "Brute force pattern detected (5 attempts) | Common username targeted"
            }
        },
        ...
    ],
    "timestamp": "2026-01-15T10:30:01Z"
}

HTTP Status Codes:
- 200: All events processed successfully
- 207: Some events processed, some rejected (see failed_details)
- 400: Invalid request format
- 503: Database unavailable


INPUT CONTRACT (InputContract class)
====================================

REQUIRED FIELDS:
- event_id: Valid UUID v4 format
- event_type: One of [login_attempt, honeypot_interaction, network_alert, security_action, authentication_success, authentication_failure, access_denied, suspicious_behavior]
- timestamp: ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
- source: One of [http_api, log_file, syslog, ids, firewall, honeypot, web_application, custom]
- sensor_id: Non-empty string

Violation Response (400):
{
    "error": "Missing required fields: event_type, timestamp",
    "event_id": "uuid"
}

Core does NOT validate:
- Event content beyond schema
- Source system reliability
- Sensor trustworthiness
- Data freshness or accuracy


ANALYSIS PIPELINE
=================

1. InputContract.validate()
   - Enforces strict input schema
   - Rejects malformed events
   - Non-blocking: bad events logged but don't stop processing

2. FeatureExtractor.extract_features()
   - IP-based: internality, reputation
   - User-based: username patterns, history count
   - Network-based: protocol, port, privilege level
   - Timing: hour of day
   - Behavioral: user-agent analysis
   - Output: Dict[str, Any] of extracted features

3. CorrelationEngine.analyze_correlations()
   - Brute force detection: 5+ attempts from IP in 1 hour
   - Multiple sensor hits: Same source on 3+ sensors
   - IP scanning: [stubbed] IP subnet pattern detection
   - Port scanning: [stubbed] Port sequence detection
   - Output: Dict[str, Dict] of correlation findings

4. DetectionPipeline.compute_threat_score()
   - Rule-based scoring (pluggable rules)
   - Feature adjustments (IP internality, user-agent patterns)
   - Correlation adjustments (brute force, multi-sensor)
   - Score range: 0-100 (clamped)
   - Output: (threat_score: int, analysis_reason: str)

5. ThreatAnalysis.analyze()
   - Orchestrates all analysis components
   - Does NOT modify input event
   - Returns analysis metadata
   - Output: Dict with threat_score, threat_level, features, correlations

6. Event Storage
   - Routes event by type to appropriate table
   - Stores enriched event with analysis metadata
   - Does NOT modify original event structure


OUTPUT INTERFACE
================

Database Tables (PostgreSQL):
- security_logs: All normalized security events with analysis
- honeypot_logs: Honeypot interactions
- blocked_ips: IP reputation and blocking status
- login_attempts: Login patterns and frequency

Fields stored:
- event_id: Original event identifier
- ip_address, username, action, user_agent
- threat_level: Computed threat level (CRITICAL, HIGH, MEDIUM, LOW, INFO)
- blocked: Action taken (true if blocked)
- reason: Human-readable explanation
- sensor_id: Original sensor identification
- event_type: Original event type
- metadata: Full analysis object (JSON)
  {
      "threat_score": 0-100,
      "threat_level": "info|low|medium|high|critical",
      "analysis_reason": "string with pipe-separated reasons",
      "features": { ... extracted features ... },
      "correlations": { ... findings ... },
      "analysis_timestamp": "ISO 8601 string"
  }

Query Examples (for API/UI):
- SELECT * FROM security_logs WHERE threat_level='CRITICAL' AND timestamp > NOW() - INTERVAL '1 hour'
- SELECT COUNT(*), threat_level FROM security_logs GROUP BY threat_level
- SELECT ip_address, COUNT(*) FROM security_logs WHERE timestamp > NOW() - INTERVAL '24 hours' GROUP BY ip_address ORDER BY COUNT(*) DESC


HEALTH ENDPOINT
===============

GET /health

Response (200 if healthy, 503 if unhealthy):
{
    "status": "healthy|unhealthy",
    "service": "mayasec-core",
    "database": "connected|disconnected",
    "timestamp": "2026-01-15T10:30:00Z",
    "pipeline": {
        "feature_extractor": "ready",
        "correlation_engine": "ready",
        "detection_pipeline": "ready"
    }
}

Used by: Docker Compose health checks, Kubernetes readiness probes


STATUS ENDPOINT
===============

GET /api/status

Response (200):
{
    "service": "mayasec-core",
    "status": "running",
    "database": "connected|disconnected",
    "components": {
        "input_contract": "enforced",
        "feature_extractor": "active",
        "correlation_engine": "active",
        "detection_pipeline": "4 rules loaded",
        "threat_analysis": "active"
    },
    "timestamp": "2026-01-15T10:30:00Z"
}


KEY ARCHITECTURAL PROPERTIES
=============================

1. INPUT IMMUTABILITY
   - Core receives events and does NOT modify them
   - Analysis is added via separate "threat_analysis" field
   - Enriched event = original event + threat_analysis object

2. SOURCE AGNOSTICISM
   - Core doesn't care: HTTP API, log file, Suricata, Snort, firewall, etc.
   - All classification based on canonical schema only
   - Feature extraction is source-independent

3. SENSOR OBLIVIOUSNESS
   - Core doesn't track sensor trustworthiness
   - Treats all sensors equally in correlation analysis
   - sensor_id is just metadata for queries

4. STRICT CONTRACT
   - InputContract enforces schema rigorously
   - Bad events rejected at intake
   - Prevents downstream processing errors

5. SCORING TRANSPARENCY
   - threat_analysis.analysis_reason explains all decisions
   - Auditable threat assessment
   - Supports tuning/debugging of detection rules


EXTENSION POINTS
================

1. Detection Rules (DetectionPipeline.RULES)
   - Add/modify rules in RULES dict
   - Each rule: condition (lambda), score_delta, reason
   - Can load rules from database/config at startup

2. Feature Extraction
   - Add methods to FeatureExtractor
   - Extract from canonical schema fields
   - Return Dict added to analysis.features

3. Correlation Rules
   - Add methods to CorrelationEngine
   - Query historical data from PostgreSQL
   - Return Dict added to analysis.correlations

4. Historical Data
   - Implement _get_historical_data() fully
   - Query login patterns, IP reputation, etc.
   - Used by feature extractors and correlation

Example: Adding a custom rule
```python
DetectionPipeline.RULES['suspicious_admin_login'] = {
    'condition': lambda e: e.get('username') == 'admin' and e.get('hour_of_day') >= 22,
    'score_delta': 15,
    'reason': 'Admin login at night (high-risk hour)'
}
```
