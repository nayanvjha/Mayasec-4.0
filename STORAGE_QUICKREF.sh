#!/bin/bash
# Quick Reference: Storage Layer Setup & Usage

# =============================================================================
# 1. RUN MIGRATIONS
# =============================================================================

# Check migration status
python migration_manager.py status

# Apply all pending migrations
python migration_manager.py run

# Or with explicit parameters:
python migration_manager.py run \
  --host localhost \
  --port 5432 \
  --name mayasec \
  --user mayasec \
  --password mayasec_password


# =============================================================================
# 2. REPOSITORY LAYER USAGE IN PYTHON
# =============================================================================

# Initialize repositories
from repository import EventRepository, AlertRepository, DatabaseConfig

db_config = DatabaseConfig(
    host='postgres',
    port=5432,
    database='mayasec',
    user='mayasec',
    password='mayasec_password'
)

event_repo = EventRepository(db_config)
alert_repo = AlertRepository(db_config)

# Store event
event_repo.create_event(
    event=normalized_event,
    threat_analysis={'threat_score': 45, 'threat_level': 'medium', ...}
)

# Query logs
logs = event_repo.query_logs(
    ip_address='192.168.1.100',
    threat_level='high',
    days=7,
    limit=100
)

# Get threat summary for IP
summary = event_repo.get_ip_threat_summary('192.168.1.100', days=7)
# Returns: {ip_address, total_events, critical_count, high_count, blocked_count, ...}

# Create alert
alert_id = alert_repo.create_alert(
    rule_id='brute_force_detected',
    title='Brute Force Attack Detected',
    severity='high',
    event_ids=['uuid1', 'uuid2', 'uuid3'],
    ip_address='192.168.1.100',
    username='admin',
    metadata={'attempts': 15, 'time_window': '1 hour'}
)

# Block IP
alert_repo.block_ip(
    ip_address='192.168.1.100',
    reason='Brute force attack detected',
    is_permanent=False,
    expires_at=datetime.utcnow() + timedelta(hours=24)
)

# Check if IP blocked
is_blocked = alert_repo.is_ip_blocked('192.168.1.100')


# =============================================================================
# 3. CORE SERVICE WITH REPOSITORY INJECTION
# =============================================================================

# In core/__init__.py, repositories are injected:

from repository import EventRepository, DatabaseConfig

db_config = DatabaseConfig(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
event_repo = EventRepository(db_config)

# Use in endpoints:
@app.route('/api/events/process', methods=['POST'])
def process_events():
    # Correlation engine uses repository
    correlation_engine = CorrelationEngine(event_repo)
    threat_analysis = ThreatAnalysis(correlation_engine)
    
    for event in events:
        analysis = threat_analysis.analyze(event)
        event_repo.create_event(event, analysis)  # Store via repository


# =============================================================================
# 4. QUERY PATTERNS
# =============================================================================

# GET high-threat events in last 24 hours
logs = event_repo.query_logs(threat_level='high', days=1)

# GET all events from specific IP
logs = event_repo.query_logs(ip_address='10.0.1.50')

# GET failed auth attempts for specific user
logs = event_repo.query_logs(username='admin', limit=1000)

# GET threat distribution
from repository import StatisticsRepository
stats_repo = StatisticsRepository(db_config)
distribution = stats_repo.get_threat_distribution(days=7)
# Returns: {'critical': 5, 'high': 23, 'medium': 145, 'low': 892, 'info': 12345}

# GET top attacking IPs
top_ips = stats_repo.get_top_ips(days=7, limit=10)
# Returns: [('192.168.1.1', 1523), ('10.0.0.2', 987), ...]


# =============================================================================
# 5. DATABASE MAINTENANCE
# =============================================================================

# Check database health
if event_repo.is_healthy():
    print("✓ Database is healthy")
else:
    print("✗ Database is unreachable")

# Cleanup expired blocks
psql -h postgres -U mayasec -d mayasec -c \
  "DELETE FROM blocked_ips WHERE expires_at < NOW() AND is_permanent = FALSE"

# View migration history
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT version, status, applied_at FROM schema_migrations ORDER BY applied_at"

# Get table statistics
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) \
   FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size DESC"


# =============================================================================
# 6. PERFORMANCE TUNING
# =============================================================================

# Analyze query performance
psql -h postgres -U mayasec -d mayasec -c \
  "EXPLAIN ANALYZE SELECT * FROM security_logs WHERE timestamp > NOW() - INTERVAL '1 day' \
   AND threat_level = 'high' LIMIT 100"

# Rebuild indices (maintenance)
psql -h postgres -U mayasec -d mayasec -c "REINDEX DATABASE mayasec"

# Vacuum analyze (cleanup, optimize statistics)
psql -h postgres -U mayasec -d mayasec -c "VACUUM ANALYZE"

# Check index usage
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch \
   FROM pg_stat_user_indexes ORDER BY idx_scan DESC"


# =============================================================================
# 7. CREATING NEW MIGRATIONS
# =============================================================================

# Template: migrations/003_my_feature.sql

cat > migrations/003_my_feature.sql << 'EOF'
-- Migration: 003_my_feature
-- Purpose: Description of what this migration does
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS my_table (
    id SERIAL PRIMARY KEY,
    column1 VARCHAR(255) NOT NULL,
    column2 INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_my_table_column1 ON my_table(column1);

-- Then run:
python migration_manager.py run
EOF


# =============================================================================
# 8. TROUBLESHOOTING
# =============================================================================

# Check migration failures
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT version, status, error_message FROM schema_migrations WHERE status = 'failed'"

# View detailed connection pool stats
# In Python:
print(event_repo.pool.getconn.__self__.__dict__)

# Check slow queries (PostgreSQL log)
tail -f /var/log/postgresql/postgresql.log | grep "duration:"

# Kill long-running queries
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
   WHERE usename = 'mayasec' AND query_start < NOW() - INTERVAL '5 minutes'"


# =============================================================================
# 9. BACKUP & RESTORE
# =============================================================================

# Full database backup
pg_dump -h postgres -U mayasec -d mayasec | gzip > mayasec_backup_$(date +%Y%m%d).sql.gz

# Restore from backup
gunzip < mayasec_backup_20260115.sql.gz | psql -h postgres -U mayasec -d mayasec

# Backup only schema (no data)
pg_dump -h postgres -U mayasec -d mayasec -s > mayasec_schema.sql


# =============================================================================
# 10. MONITORING & ALERTING
# =============================================================================

# Monitor events/second
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT COUNT(*) FROM security_logs WHERE timestamp > NOW() - INTERVAL '1 minute'"

# Monitor database size
psql -h postgres -U mayasec -d mayasec -c "SELECT pg_database_size('mayasec')"

# Monitor connection count
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'mayasec'"

# Monitor table bloat (overhead from updates/deletes)
psql -h postgres -U mayasec -d mayasec -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) \
   FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size DESC LIMIT 5"
