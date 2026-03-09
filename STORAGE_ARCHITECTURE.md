"""
MAYASEC Storage Architecture

Production-Grade PostgreSQL Storage Layer with Deterministic Migrations

CORE PRINCIPLES
===============

1. REPOSITORY PATTERN
   - All SQL queries live in repository.py
   - Business logic has no raw SQL
   - Services depend on repository interfaces, not database internals
   - Clean separation: core, ingestor, api ← repository ← database

2. DETERMINISTIC MIGRATIONS
   - Version-tracked: schema_migrations table records all applied migrations
   - Idempotent: Safe to run multiple times
   - Numbered: 001_*, 002_*, etc. (lexicographic ordering)
   - Self-contained: Each migration handles its own dependencies
   - Auditable: Failed migrations recorded with error messages

3. NO RAW SQL OUTSIDE REPOSITORY
   - Core service uses EventRepository, AlertRepository, StatisticsRepository
   - Ingestor layer has no database calls (HTTP to core)
   - API layer queries via repository interfaces
   - psycopg2 imported ONLY in repository.py

4. DEPENDENCY INJECTION
   - Core receives repository instances: event_repo, alert_repo, stats_repo
   - CorrelationEngine injected with EventRepository
   - ThreatAnalysis injected with CorrelationEngine
   - Enables testability, mocking, and clear dependencies

5. CONNECTION POOLING
   - SimpleConnectionPool in BaseRepository (min=1, max=5)
   - Safe reuse of connections
   - Automatic cleanup on application shutdown


DATABASE SCHEMA
===============

EVENT STORAGE TABLES:

1. security_logs (PRIMARY)
   - Centralized event log for all security events
   - Indexed: timestamp, threat_level, ip_address, username, sensor_id, event_type
   - JSON metadata field stores threat analysis (features, correlations, scores)
   - ON CONFLICT (event_id) DO NOTHING prevents duplicates

2. honeypot_logs (SPECIALIZED)
   - Dedicated table for honeypot interactions
   - Tracks username/password attempts, user-agent, service
   - Cross-referenced with security_logs for correlation
   - Indexed: timestamp, ip_address, sensor_id, username

3. login_attempts (DETAILED AUTH)
   - Authentication attempt tracking for brute-force detection
   - attempt_count, success boolean, threat_score
   - Indexed: timestamp, ip_address, username
   - Used by CorrelationEngine for brute-force pattern detection

4. failed_attempts (SUMMARY)
   - Aggregated failed login summary (per IP or username)
   - last_attempt timestamp for rate limiting
   - threat_level classification
   - Indexed: ip_address, last_attempt

5. alert_history (DETECTION EVENTS)
   - Tracks suspicious behavior patterns triggered
   - alert_type, threat_level, threat_score
   - Links to IP/username/sensor
   - Indexed: timestamp, threat_level, alert_type

6. network_flows (NETWORK EVENTS)
   - Network traffic analysis and IDS alerts
   - source_ip, dest_ip, source_port, dest_port, protocol
   - bytes_sent/received, duration_ms
   - Indexed: timestamp, source_ip, dest_ip, dest_port, protocol

7. event_correlations (PATTERN TRACKING)
   - Multi-event correlations and patterns
   - event_ids array tracks related events
   - ip_address, username, sensor_ids for grouping
   - Indexed: timestamp, correlation_type, threat_level


ALERT MANAGEMENT TABLES:

8. alert_rules (DETECTION RULES)
   - Rule definitions for automated detection
   - condition_json: Pluggable rule conditions
   - threshold_value, threshold_window_minutes
   - enabled boolean for runtime activation

9. alerts (ALERT EVENTS)
   - Individual alerts triggered by rules
   - event_ids array: events that triggered alert
   - status: open, acknowledged, resolved
   - assigned_to, acknowledged_at, resolved_at for workflow

10. alert_actions (RESPONSE ACTIONS)
    - Actions taken in response to alerts
    - action_type: block_ip, disable_account, notify, escalate, etc.
    - status: pending, executing, completed, failed
    - result_json: Execution results and side effects

11. blocked_ips (IP REPUTATION)
    - IP addresses and blocking status
    - is_permanent: indefinite blocks
    - expires_at: temporary block expiration
    - block_count, last_blocked_at for statistics
    - Indexed: ip_address, expires_at (for cleanup queries)

12. blocked_users (USER REPUTATION)
    - Disabled user accounts and locks
    - Similar structure to blocked_ips
    - Indexed: username, expires_at


ANALYTICS TABLES:

13. alert_escalations (ESCALATION TRACKING)
    - Escalation workflow history
    - escalation_level (1=manager, 2=director, 3=ciso)
    - escalated_by, escalated_to, reason
    - Indexed: alert_id, escalation_level

14. response_playbooks (AUTOMATION)
    - Reusable response procedures
    - trigger_rule_ids: Rules that activate playbook
    - actions: JSON-encoded action sequence
    - enabled boolean for activation

15. ip_reputation (IP INTELLIGENCE)
    - IP reputation scoring
    - reputation_score: 0-100 (higher = more malicious)
    - threat_indicators: array of threat types observed
    - is_internal, is_whitelisted flags
    - Indexed: ip_address, reputation_score, last_seen


MIGRATION WORKFLOW
==================

1. CREATING NEW MIGRATION

   # Create file: migrations/003_your_feature.sql
   # Follow naming: <version>_<description>.sql
   
   BEGIN;
   
   CREATE TABLE IF NOT EXISTS new_table (
       id SERIAL PRIMARY KEY,
       column1 TYPE NOT NULL,
       ...
   );
   
   CREATE INDEX idx_name ON new_table(column1);
   
   COMMIT;

2. RUNNING MIGRATIONS

   # Check status
   python migration_manager.py status
   
   # Apply pending
   python migration_manager.py run
   
   # Environment variables (or arguments)
   export DB_HOST=postgres
   export DB_PORT=5432
   export DB_NAME=mayasec
   export DB_USER=mayasec
   export DB_PASSWORD=secret

3. MIGRATION TRACKING

   schema_migrations table records:
   - version: Migration file name (e.g., "001_create_events")
   - description: Human-readable name
   - applied_at: Timestamp of execution
   - status: 'success' or 'failed'
   - error_message: SQL error if failed

4. ROLLBACK STRATEGY

   Currently: Manual SQL reversals via new migration
   Example: Create 004_undo_feature.sql with DROP/ALTER commands
   
   Future: Add pre-migration snapshots for automated rollback


REPOSITORY LAYER API
====================

EventRepository:
  - create_event(event, threat_analysis) → bool
  - batch_create_events(events_list) → int (count)
  - query_logs(ip_address, username, threat_level, days, limit) → List[Dict]
  - get_event_by_id(event_id) → Optional[Dict]
  - get_ip_threat_summary(ip_address, days) → Dict

AlertRepository:
  - create_alert(rule_id, title, severity, event_ids, ...) → Optional[str]
  - get_open_alerts(limit) → List[Dict]
  - block_ip(ip_address, reason, is_permanent, expires_at) → bool
  - is_ip_blocked(ip_address) → bool

StatisticsRepository:
  - get_threat_distribution(days) → Dict[threat_level, count]
  - get_top_ips(days, limit) → List[Tuple(ip, count)]

BaseRepository (inherited by all):
  - get_connection() → from pool
  - return_connection(conn) → to pool
  - close_all() → shutdown pool
  - is_healthy() → bool


CORE SERVICE INTEGRATION
========================

Dependency Injection:

    # At startup (core/__init__.py)
    db_config = DatabaseConfig(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    event_repo = EventRepository(db_config)
    alert_repo = AlertRepository(db_config)
    stats_repo = StatisticsRepository(db_config)

Feature Extraction (source-agnostic):

    analysis = ThreatAnalysis(correlation_engine).analyze(event)
    # Returns: {threat_score, threat_level, features, correlations, analysis_reason}

Storage (repository-based):

    event_repo.create_event(event, threat_analysis)
    # Internally routes by event_type to appropriate tables
    # No raw SQL in core logic

Correlation Engine (with repository):

    correlation_engine = CorrelationEngine(event_repo)
    correlations = correlation_engine.analyze_correlations(event)
    # Queries via repo.query_logs() for brute-force, multi-sensor patterns


QUERY EXAMPLES
==============

# Get recent high-threat events
SELECT * FROM security_logs
WHERE threat_level >= 'high'
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

# Top attacking IPs
SELECT ip_address, COUNT(*) as count
FROM security_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY ip_address
ORDER BY count DESC
LIMIT 10;

# Brute-force detection (5+ failed logins/hour)
SELECT ip_address, COUNT(*) as attempts
FROM security_logs
WHERE event_type = 'login_attempt'
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY ip_address
HAVING COUNT(*) >= 5;

# Multi-sensor correlation (same IP on 3+ sensors)
SELECT ip_address, COUNT(DISTINCT sensor_id) as sensors
FROM security_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY ip_address
HAVING COUNT(DISTINCT sensor_id) >= 3;

# Threat distribution
SELECT threat_level, COUNT(*) as count
FROM security_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY threat_level;

# Honeypot analysis
SELECT ip_address, COUNT(*) as interaction_count, array_agg(DISTINCT username)
FROM honeypot_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY ip_address
ORDER BY interaction_count DESC;


PERFORMANCE OPTIMIZATION
=========================

INDEX STRATEGY:
- Composite indices for common query patterns
- Partial indices on blocked_ips.expires_at (WHERE expires_at IS NOT NULL)
- DESC indices on timestamp for reverse chronological queries
- INET type indices for IP address queries (native PostgreSQL support)

PARTITIONING (Future):
- security_logs partitioned by month (timestamp)
- Enables faster queries and easier archival
- Index bloat management for high-volume tables

CONNECTION POOLING:
- SimpleConnectionPool: 1-5 connections
- Suitable for moderate load (< 100 req/sec)
- Upgrade to pgBouncer for high concurrency

CACHING LAYER (Future):
- Redis for IP reputation cache
- Memcached for recent event summaries
- Cache invalidation on alert rules changes


EXTENSION POINTS
================

1. CUSTOM DETECTION RULES

   Add to alert_rules table:
   INSERT INTO alert_rules (rule_id, rule_name, description, rule_type, severity, condition_json)
   VALUES ('custom_rule_1', 'My Detection', 'Description', 'pattern', 'high', '{"query": "..."}');

2. CUSTOM RESPONSE ACTIONS

   Extend alert_actions processing in response handler:
   - action_type: 'block_ip' → AlertRepository.block_ip()
   - action_type: 'disable_account' → Custom handler
   - action_type: 'notify' → Webhook/email sender
   - action_type: 'escalate' → Escalation workflow

3. CUSTOM CORRELATIONS

   Implement in CorrelationEngine._check_* methods:
   - _check_geographic_anomaly()
   - _check_concurrent_logins()
   - _check_vpn_evasion()

4. CUSTOM FEATURES

   Add to FeatureExtractor.extract_features():
   - features['ssl_cert_mismatch'] = check_certificate()
   - features['tor_exit_node'] = check_tor_list()
   - features['datacenter_ip'] = check_datacenter_range()

5. ASYNC EVENT PROCESSING

   Decouple via event queue:
   - POST /api/events/process → store in Redis queue
   - Worker processes: ThreatAnalysis → EventRepository
   - Webhook on completion for API subscribers


MONITORING & MAINTENANCE
========================

Health Checks:
- GET /health → Database connectivity via event_repo.is_healthy()
- GET /api/status → Component readiness (pipeline, correlations)
- Liveness: Response time < 5s
- Readiness: Database must be connected

Log Locations:
- Core service: /app/logs/core.log
- Migration manager: stdout (run via migration_manager.py)
- Database: PostgreSQL server logs

Metrics to Track:
- Events processed/second
- Average threat score
- False positive rate (alerts resolved as benign)
- Detection latency (event arrival to threat analysis completion)
- Database query latency (p50, p95, p99)

Backup Strategy:
- PostgreSQL daily full backups (pg_dump)
- PITR (point-in-time recovery) via WAL archival
- Test restores weekly
- Keep 30 days of backups

Archival:
- Move old security_logs to archive tables quarterly
- Compress historical data
- Export to S3 for long-term storage


TROUBLESHOOTING
===============

Connection Pool Exhausted:
- Symptom: "psycopg2.OperationalError: connection not available"
- Cause: Too many concurrent requests, leaking connections
- Fix: Increase pool max_conn, check return_connection() calls, review slow queries

Migration Stuck:
- Symptom: status shows 'applied' but changes missing
- Cause: Transaction rollback due to constraint violation
- Fix: Check schema_migrations.error_message, review migration SQL syntax

Duplicate Event IDs:
- Symptom: "ON CONFLICT (event_id) DO NOTHING" silently ignores duplicates
- Cause: Ingestor generating same event_id or replaying events
- Fix: Verify event_id generation in ingestor/normalizer.py uses UUIDs

Slow Queries:
- Symptom: API response time > 5s
- Cause: Missing indices, full table scans, OR large result sets
- Fix: EXPLAIN ANALYZE queries, add indices, increase LIMIT clauses, use pagination

High Memory Usage:
- Symptom: PostgreSQL process memory growing
- Cause: Large query results (millions of rows), connection pool caching
- Fix: Partition tables, increase LIMIT, reduce connection pool size
"""
