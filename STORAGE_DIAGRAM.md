"""
STORAGE LAYER INTEGRATION DIAGRAM

Event Flow Through Storage Architecture
==========================================

1. INGESTOR (Event Entry Point)
   ↓
   POST /api/ingest/event
   ├─ Validate against event_schema.json
   ├─ Generate event_id (UUID v4)
   ├─ Normalize timestamp (ISO 8601)
   └─ Forward to Core (HTTP)

2. CORE (Analysis & Storage)
   ↓
   POST /api/events/process (from ingestor)
   ├─ InputContract.validate() [STRICT]
   │  ├─ Required fields: event_id, event_type, timestamp, source, sensor_id
   │  ├─ Whitelisted types: login_attempt, honeypot_interaction, network_alert, ...
   │  └─ Format checks: UUID v4, ISO timestamp
   │
   ├─ CorrelationEngine.analyze_correlations(event)
   │  ├─ Queries via event_repo.query_logs() [REPOSITORY LAYER]
   │  ├─ Brute-force: COUNT login_attempt WHERE ip = ? AND time > NOW() - 1h
   │  └─ Multi-sensor: COUNT DISTINCT sensor_id WHERE ip = ?
   │
   ├─ FeatureExtractor.extract_features(event)
   │  ├─ IP-based: internality, reputation
   │  ├─ User-based: commonality, history count
   │  ├─ Network: protocol, port, privilege level
   │  ├─ Timing: hour of day
   │  └─ Behavioral: user-agent suspicious patterns
   │
   ├─ DetectionPipeline.compute_threat_score()
   │  ├─ Base rules: high_severity_alert (+30), honeypot (+25), failed_auth (+5)
   │  ├─ Feature adjustments: internal_ip (-5), common_username (+2), suspicious_ua (+10)
   │  └─ Correlation adjustments: brute_force (+20), multi_sensor (+15)
   │  └─ Returns: threat_score (0-100), threat_level, analysis_reason
   │
   ├─ event_repo.create_event(event, threat_analysis) [REPOSITORY CALL]
   │  └─ Routes by event_type:
   │     ├─ login_attempt → INSERT login_attempts + security_logs
   │     ├─ honeypot_interaction → INSERT honeypot_logs + security_logs
   │     ├─ network_alert → INSERT network_flows + security_logs
   │     ├─ suspicious_behavior → INSERT alert_history + security_logs
   │     └─ generic → INSERT security_logs
   │
   ├─ Return enriched event with threat_analysis metadata
   └─ 200 (success) or 207 (partial failures)

3. API (Query Interface - Future)
   ↓
   GET /events?ip=1.2.3.4&days=7
   ├─ Query via event_repo.query_logs(ip_address=..., days=...)
   └─ SELECT * FROM security_logs WHERE ip_address = ? ORDER BY timestamp DESC

   GET /alerts?status=open
   ├─ Query via alert_repo.get_open_alerts(limit=100)
   └─ SELECT * FROM alerts WHERE status = 'open' ORDER BY timestamp DESC

   GET /stats?period=7d
   ├─ Query via stats_repo.get_threat_distribution(days=7)
   └─ SELECT threat_level, COUNT(*) FROM security_logs GROUP BY threat_level


REPOSITORY LAYER INTERNALS
===========================

BaseRepository (Connection Pool Management)
├─ _init_pool() → SimpleConnectionPool(1, 5)
├─ get_connection() → conn from pool
├─ return_connection(conn) → conn to pool
├─ is_healthy() → SELECT 1 to verify connectivity
└─ close_all() → shutdown pool


EventRepository (All Event Persistence)
├─ create_event(event, threat_analysis)
│  ├─ Routes by event_type to appropriate table
│  ├─ _store_security_log() → All events
│  ├─ _store_login_attempt() → Auth events
│  ├─ _store_honeypot_log() → Honeypot events
│  ├─ _store_network_flow() → Network alerts
│  └─ _store_alert_history() → Suspicious behavior
│
├─ batch_create_events(events_list) → multiple creates
│
├─ query_logs(ip_address, username, threat_level, days, limit)
│  └─ SELECT * FROM security_logs WHERE ... ORDER BY timestamp DESC
│
├─ get_event_by_id(event_id)
│  └─ SELECT * FROM security_logs WHERE event_id = ?
│
└─ get_ip_threat_summary(ip_address, days)
   └─ SELECT threat_level, COUNT(*), MAX(threat_score), ... GROUP BY ip_address


AlertRepository (Alert & Response Management)
├─ create_alert(rule_id, title, severity, event_ids, ...)
│  └─ INSERT INTO alerts ... RETURNING alert_id
│
├─ get_open_alerts(limit)
│  └─ SELECT * FROM alerts WHERE status = 'open' ORDER BY timestamp DESC
│
├─ block_ip(ip_address, reason, is_permanent, expires_at)
│  └─ INSERT INTO blocked_ips ... ON CONFLICT DO UPDATE
│
└─ is_ip_blocked(ip_address)
   └─ SELECT 1 FROM blocked_ips WHERE ... AND (is_permanent OR expires_at > NOW())


StatisticsRepository (Analytics)
├─ get_threat_distribution(days)
│  └─ SELECT threat_level, COUNT(*) FROM security_logs GROUP BY threat_level
│
└─ get_top_ips(days, limit)
   └─ SELECT ip_address, COUNT(*) FROM security_logs GROUP BY ip_address ORDER BY COUNT(*) DESC


DATABASE TRANSACTION FLOW
==========================

Scenario 1: Single Event Processing
─────────────────────────────────────
Client Request
    ↓
event_repo.create_event(event, analysis)
    ├─ conn = get_connection() from pool
    ├─ cursor = conn.cursor()
    ├─ INSERT INTO security_logs VALUES (...)
    ├─ INSERT INTO login_attempts VALUES (...) [if login event]
    ├─ conn.commit()
    ├─ cursor.close()
    ├─ return_connection(conn) to pool
    └─ return True/False

Response: 200 OK with enriched event


Scenario 2: Batch Processing (100 events)
──────────────────────────────────────────
for each event:
    event_repo.create_event(event, analysis)
        ├─ get_connection() [reused from pool]
        ├─ INSERT ... and INSERT ...
        ├─ commit()
        └─ return_connection()

Response: 200 OK, processed: 100, failed: 0


Scenario 3: Correlation Query During Processing
─────────────────────────────────────────────────
CorrelationEngine._check_brute_force(event)
    ├─ repo.query_logs(ip_address=src_ip, days=1)
    │  ├─ conn = get_connection()
    │  ├─ SELECT COUNT(*) FROM security_logs WHERE ip_address = ? AND event_type = 'login_attempt'
    │  ├─ return_connection(conn)
    │  └─ return list of logs
    │
    └─ if attempt_count >= 5:
       ├─ return {'pattern': 'brute_force', 'attempt_count': 5, ...}
       └─ DetectionPipeline adds +20 to threat_score


MIGRATION EXECUTION FLOW
========================

python migration_manager.py run
├─ MigrationManager.__init__()
├─ connect() → psycopg2.connect(...)
├─ _ensure_migrations_table() → CREATE TABLE IF NOT EXISTS schema_migrations
├─ get_pending_migrations() → scan migrations/ dir, check schema_migrations
│  └─ Returns: [(001_create_events, path), (002_create_alerts, path), ...]
│
├─ for each pending migration:
│  ├─ execute_migration(version, filepath)
│  │  ├─ Read SQL file
│  │  ├─ Execute: cursor.execute(sql)
│  │  ├─ commit()
│  │  ├─ Record in schema_migrations: INSERT (version, status='success')
│  │  └─ Return True
│  │
│  └─ Log: ✓ Migration completed: 001_create_events
│
└─ If all succeeded: ✓ All migrations completed successfully (exit 0)
   If any failed: ✗ Some migrations failed (exit 1)


SCHEMA RELATIONSHIPS
====================

Primary Log (Hub-and-Spoke):
┌─────────────────────────┐
│   security_logs         │  (All events consolidated)
│   15 indices            │
│   threat analysis JSON  │
└─────────────────────────┘
   ↑ ↑ ↑ ↑
   │ │ │ └─ network_flows (network alerts)
   │ │ │
   │ │ └─── honeypot_logs (honeypot events)
   │ │
   │ └───── login_attempts (auth events)
   │
   └─────── event_correlations (patterns)


Alert System (Linear):
   alert_rules (Rule definitions)
        ↓
   alerts (Individual alerts fired)
        ├─ → alert_actions (Responses)
        │
        ├─ → alert_escalations (Workflow)
        │
        └─ → blocked_ips, blocked_users (Enforcement)


Intelligence (Feed):
   ip_reputation (IP scores)
        │
        └─ → blocked_ips (Blocking decisions)


SQL QUERY EXECUTION
===================

Indexed Query (Fast):
SELECT * FROM security_logs 
WHERE timestamp > NOW() - INTERVAL '1 day' 
  AND threat_level = 'high'
LIMIT 100

Execution Plan:
├─ Use idx_security_logs_threat_level (btree)
│  ├─ Scan for threat_level = 'high'
│  └─ Estimated rows: 50-100
│
├─ Use idx_security_logs_timestamp (btree DESC)
│  ├─ Scan for timestamp > 24h
│  └─ Merge results with threat_level scan
│
└─ Result: ~10-50ms (depending on server)


Unindexed Query (Slow):
SELECT COUNT(*) FROM security_logs 
WHERE ip_address = '192.168.1.1'
  AND username = 'admin'
  AND action LIKE '%ssh%'

Without proper indices:
├─ Full table scan of security_logs
├─ Estimate: 1,000,000+ rows
└─ Result: 1-5 seconds (depending on server)

Solution: Create indices
CREATE INDEX idx_sl_ip_username ON security_logs(ip_address, username)
Then re-run: ~50-100ms


HEALTH CHECK FLOW
=================

GET /health
├─ Core service calls: event_repo.is_healthy()
│  ├─ conn = pool.getconn()
│  ├─ cursor.execute('SELECT 1')
│  ├─ pool.putconn(conn)
│  └─ return True
│
└─ Response: 200 OK {
    'status': 'healthy',
    'database': 'connected',
    'pipeline': {...}
   }

If database down:
├─ pool.getconn() → timeout or connection refused
├─ is_healthy() catches exception
├─ Returns False
│
└─ Response: 503 Service Unavailable {
    'status': 'unhealthy',
    'database': 'disconnected'
   }


CONNECTION POOL STATE
====================

Initial: 1 connection
├─ Handles single request
└─ Next request reuses same connection

Concurrent 5 requests:
├─ Request 1 gets conn[1]
├─ Request 2 gets conn[2]
├─ Request 3 gets conn[3]
├─ Request 4 gets conn[4]
├─ Request 5 gets conn[5]
└─ Request 6 waits for one to be returned

Request completes:
├─ Calls return_connection(conn)
├─ conn returned to pool
└─ Waiting request gets conn

If connection leaked (not returned):
├─ Pool size stays at max=5
├─ Request 6 still waiting
├─ Eventually timeout
└─ Must fix code to call return_connection()


DEPLOYMENT CHECKLIST
====================

Pre-launch:
☐ Run migration_manager.py status → Check for errors
☐ Run migration_manager.py run → Apply all migrations
☐ Verify schema_migrations table has 2 success entries
☐ Test event_repo.is_healthy() → True
☐ Start core service
☐ curl http://localhost:5002/health → 200 OK

During launch:
☐ Core service receives events from ingestor
☐ Events processed via repository layer
☐ Events stored in appropriate tables
☐ Threat analysis metadata in JSON fields
☐ Monitor /health endpoint (should be 200 OK)

Post-launch:
☐ Query security_logs via repository
☐ Run analytics: get_threat_distribution()
☐ Monitor connection pool usage
☐ Set up PostgreSQL backups
☐ Configure monitoring alerts

Regular maintenance:
☐ Weekly: VACUUM ANALYZE
☐ Monthly: Check index bloat, rebuild if needed
☐ Quarterly: Archive old events, partition tables
☐ Annually: Capacity planning, upgrade hardware if needed
"""
