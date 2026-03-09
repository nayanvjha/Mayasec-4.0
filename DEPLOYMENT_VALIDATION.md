# Mayasec Deployment Validation Guide

**Date:** 15 January 2026  
**Status:** Production Ready (Without Suricata)

---

## 📋 Deployment Overview

This guide covers deploying Mayasec using Docker Compose on a fresh Ubuntu VM without Suricata or external sensors.

**What's Included:**
- PostgreSQL 14 (Storage)
- Migration Service (Schema setup)
- Core Service (Threat analysis engine)
- API Service (Control plane)
- Honeypot Service (Stub for health checks)

**What's NOT Included:**
- Suricata IDS
- External sensors
- Kafka/Redis (optional in base deployment)
- Gemini API integration
- File system logs

---

## 🚀 Pre-Deployment Checklist

### System Requirements
- [ ] Ubuntu 20.04 LTS or newer
- [ ] 4GB RAM minimum
- [ ] 20GB disk space
- [ ] Docker 20.10+
- [ ] Docker Compose 2.0+
- [ ] curl, git installed

### Verify Prerequisites

```bash
# Check Ubuntu version
lsb_release -a

# Check Docker
docker --version      # Should be 20.10+
docker-compose --version  # Should be 2.0+

# Check disk space
df -h /

# Check RAM
free -h
```

---

## 🐳 Installation Steps

### 1. Fresh Ubuntu VM Setup

```bash
# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker installation
docker run hello-world
```

### 2. Install Docker Compose

```bash
# Download latest Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker-compose --version
```

### 3. Clone/Prepare Mayasec Repository

```bash
# Clone repository (or use existing)
cd /opt
git clone https://github.com/mayasec/mayasec-4.0.git mayasec
cd mayasec

# Verify required files exist
ls -la | grep -E "docker-compose|Dockerfile|requirements.txt|migration"
```

### 4. Configure Environment

```bash
# Copy provided .env (or create)
cp .env.example .env

# Edit .env with appropriate values
nano .env

# Key settings to verify:
# DB_HOST=postgres
# DB_USER=mayasec
# DB_PASSWORD=mayasec (CHANGE in production)
# API_PORT=5000
# CORE_URL=http://core:5001
```

### 5. Start Deployment

```bash
# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f

# Wait for migrations to complete (~30 seconds)
```

---

## ✅ Post-Deployment Validation

### Phase 1: Container Health

```bash
# Check container status
docker-compose ps

# Expected output:
# NAME                  STATUS
# mayasec-postgres      Up (healthy)
# mayasec-migrations    Exited 0
# mayasec-core          Up (healthy)
# mayasec-api           Up (healthy)
# mayasec-honeypot-stub Up

# View logs for errors
docker-compose logs postgres | tail -20
docker-compose logs migrations | tail -20
docker-compose logs core | tail -20
docker-compose logs api | tail -20
```

### Phase 2: Connectivity Tests

```bash
# Test PostgreSQL connectivity
docker-compose exec postgres psql -U mayasec -d mayasec -c "SELECT 1"
# Expected: "1"

# Test Core service
curl http://localhost:5001/health
# Expected: {"status": "healthy", ...}

# Test API service
curl http://localhost:5000/health
# Expected: {"status": "healthy", ...}

# Test API deep health
curl http://localhost:5000/api/v1/health/deep
# Expected: All services healthy
```

### Phase 3: Database Schema Verification

```bash
# Check tables created
docker-compose exec postgres psql -U mayasec -d mayasec -c "\dt"

# Expected tables:
# security_logs, honeypot_logs, login_attempts, failed_attempts,
# alert_history, network_flows, event_correlations,
# alert_rules, alerts, alert_actions, blocked_ips, blocked_users,
# alert_escalations, response_playbooks, ip_reputation, schema_migrations

# Check indices
docker-compose exec postgres psql -U mayasec -d mayasec -c "\di" | wc -l
# Expected: ~50+ indices
```

### Phase 4: API Endpoint Testing

```bash
# List events
curl "http://localhost:5000/api/v1/events?days=7&limit=10"

# Get OpenAPI spec
curl http://localhost:5000/api/v1/openapi | jq . | head -20

# List alerts
curl "http://localhost:5000/api/v1/alerts"

# Get metrics
curl "http://localhost:5000/api/v1/metrics"
```

### Phase 5: Sample Event Ingestion

```bash
# Send test event via Core service
curl -X POST http://localhost:5001/api/events/process \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {
        "event_type": "login_attempt",
        "source_ip": "192.168.1.100",
        "destination_ip": "10.0.0.1",
        "username": "testuser",
        "timestamp": "2026-01-15T10:30:00Z",
        "description": "Test login event"
      }
    ]
  }'

# Verify event stored
curl "http://localhost:5000/api/v1/events?ip_address=192.168.1.100"

# Expected: Event appears in results with threat analysis
```

---

## 📊 Validation Checklist

Use this checklist to verify complete deployment:

### Services (5)
- [ ] PostgreSQL container running and healthy
- [ ] Migrations completed successfully
- [ ] Core service running on port 5001
- [ ] API service running on port 5000
- [ ] Honeypot stub container running

### Database
- [ ] PostgreSQL accessible from host
- [ ] Database "mayasec" created
- [ ] User "mayasec" created
- [ ] All 15 tables created
- [ ] 50+ indices created
- [ ] schema_migrations table populated
- [ ] No migration errors

### Connectivity
- [ ] Core service responds to /health
- [ ] API service responds to /health
- [ ] API deep health shows all services
- [ ] API can query database successfully

### API Endpoints (18 total)
- [ ] GET /health - returns 200
- [ ] GET /api/v1/health - returns 200
- [ ] GET /api/v1/health/deep - returns 200 with all services
- [ ] GET /api/v1/events - returns event list
- [ ] GET /api/v1/events/{id} - returns event by ID
- [ ] GET /api/v1/alerts - returns alert list
- [ ] POST /api/v1/alerts/block - blocks IP (returns 200)
- [ ] GET /api/v1/alerts/status/{ip} - checks block status
- [ ] GET /api/v1/metrics - returns metrics
- [ ] GET /api/v1/metrics/threat-distribution - returns distribution
- [ ] GET /api/v1/metrics/top-ips - returns top IPs
- [ ] GET /api/v1/metrics/threat-summary - returns IP summary
- [ ] GET /api/v1/openapi - returns OpenAPI spec
- [ ] All endpoints handle invalid parameters (400 errors)
- [ ] All endpoints handle missing resources (404 errors)
- [ ] Response times acceptable (5-100ms)

### Event Ingestion
- [ ] Can send events to /api/events/process (Core)
- [ ] Events stored in security_logs table
- [ ] Events appear in /api/v1/events (API)
- [ ] Events have threat analysis data
- [ ] Threat scoring works (0-100)
- [ ] Threat levels assigned (low/medium/high/critical)

### Configuration
- [ ] .env file exists and is correct
- [ ] Environment variables passed to containers
- [ ] Database credentials work
- [ ] Core and API can reach each other
- [ ] No hardcoded passwords in code

### Logs
- [ ] No error messages in container logs
- [ ] No connection refused errors
- [ ] No permission denied errors
- [ ] Migration log shows success
- [ ] API accessible from host

---

## 🧪 Testing Procedures

### Unit Test: Database Connection

```bash
# Test from API container
docker-compose exec api python -c "
from repository import EventRepository, DatabaseConfig
db = DatabaseConfig('postgres', 5432, 'mayasec', 'mayasec', 'mayasec')
repo = EventRepository(db)
print('Healthy:', repo.is_healthy())
"

# Expected: Healthy: True
```

### Unit Test: Event Storage

```bash
# Send event and verify
curl -X POST http://localhost:5001/api/events/process \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "event_type": "login_attempt",
      "source_ip": "10.1.1.1",
      "destination_ip": "10.0.0.1",
      "username": "test",
      "timestamp": "2026-01-15T10:00:00Z",
      "description": "Test event"
    }]
  }' && \

# Verify event appears
curl "http://localhost:5000/api/v1/events?ip_address=10.1.1.1" | jq '.count'
```

### Load Test: API Performance

```bash
# Install Apache Bench
sudo apt-get install apache2-utils -y

# Test health endpoint (1000 requests, 10 concurrent)
ab -n 1000 -c 10 http://localhost:5000/health

# Expected: Requests per second: 100+, Latency: <100ms

# Test events endpoint
ab -n 100 -c 5 "http://localhost:5000/api/v1/events"
```

### Stress Test: Database Connections

```bash
# Check active connections
docker-compose exec postgres psql -U mayasec -d mayasec -c \
  "SELECT count(*) FROM pg_stat_activity"

# Send concurrent requests
for i in {1..50}; do
  curl "http://localhost:5000/api/v1/events" &
done
wait

# Verify no connection errors
docker-compose logs api | grep "connection\|error" || echo "No errors"
```

---

## ⚠️ Known Limitations & Constraints

### What's NOT Included

**1. Suricata IDS**
- Not installed or configured
- No real-time network packet analysis
- No IDS alerts ingestion
- Use: Send events via API instead

**2. External Sensors**
- No agent communication
- No file system access for sensor logs
- API is control plane only
- Use: Send events programmatically to /api/events/process

**3. Advanced Features**
- No Kafka/Redis (can be added)
- No Gemini API (can be added)
- No authentication/authorization (basic Flask only)
- No rate limiting
- No caching

**4. Data Sources**
- No syslog ingestion
- No file system log monitoring
- No network packet capture
- No external threat feeds

### Workarounds

**To ingest events without Suricata:**

1. **Python Script** (recommended for testing)
```python
import requests
import json

events = [{
    "event_type": "login_attempt",
    "source_ip": "192.168.1.100",
    "username": "admin",
    "timestamp": "2026-01-15T10:30:00Z"
}]

requests.post(
    "http://localhost:5001/api/events/process",
    json={"events": events}
)
```

2. **cURL**
```bash
curl -X POST http://localhost:5001/api/events/process \
  -H "Content-Type: application/json" \
  -d '{"events": [...]}'
```

3. **External Log Aggregator** (future)
- Implement log parser (rsyslog, fluentd, etc.)
- Forward to /api/events/process

### Database Limitations

- Single PostgreSQL instance (not replicated)
- No backup strategy in base deployment
- Connection pool: 1-5 concurrent
- Data volume: ~50GB for 1M events

---

## 🔧 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs <service-name>

# Common issues:
# Port already in use: Change port in docker-compose.yml
# Database connection: Check DB_HOST, credentials
# Missing files: Verify all source files exist

# Solution
docker-compose down
docker system prune
docker-compose up -d
```

### Database Migration Failed

```bash
# Check migration logs
docker-compose logs migrations

# Common issues:
# Schema version conflict
# SQL syntax error
# Permission denied

# Solution
docker-compose exec postgres psql -U mayasec -d mayasec \
  -c "DELETE FROM schema_migrations WHERE version > 0"
docker-compose restart migrations
```

### API Health Returns Unhealthy

```bash
# Check each service individually
curl http://localhost:5000/api/v1/health/deep | jq '.services'

# Common issues:
# Core service down: docker-compose restart core
# PostgreSQL down: docker-compose restart postgres
# Network issue: docker-compose logs api | grep "connection"

# Solution
docker-compose down
docker-compose up -d
```

### Slow Query Performance

```bash
# Check database stats
docker-compose exec postgres psql -U mayasec -d mayasec -c "\d+ security_logs"

# Solution: Run ANALYZE
docker-compose exec postgres psql -U mayasec -d mayasec -c "ANALYZE"

# Check indices
docker-compose exec postgres psql -U mayasec -d mayasec -c "\di+" | head -20
```

---

## 📊 Post-Deployment Tasks

### 1. Monitoring Setup
```bash
# Monitor health endpoint (every 5 seconds)
while true; do
  curl -s http://localhost:5000/health | jq '.status'
  sleep 5
done
```

### 2. Backup Strategy
```bash
# Daily database backup
docker-compose exec postgres pg_dump -U mayasec mayasec | \
  gzip > backup_$(date +%Y%m%d).sql.gz
```

### 3. Log Aggregation
```bash
# Save container logs
docker-compose logs > mayasec_deployment_$(date +%Y%m%d_%H%M%S).log
```

### 4. Performance Baseline
```bash
# Record baseline metrics
curl http://localhost:5000/api/v1/metrics | jq '.' > baseline_metrics.json
```

---

## 🎯 Success Criteria

✅ **Deployment Successful When:**

1. All 5 containers running and healthy
2. All 15 database tables created
3. All 18 API endpoints responding
4. Sample event ingestion works
5. No errors in container logs
6. Database accessible from host
7. API health checks pass
8. Response times < 100ms
9. Connection pool working
10. Metrics endpoint returns data

---

## 📞 Support & Next Steps

**For Issues:**
1. Check logs: `docker-compose logs <service>`
2. Verify environment: `docker-compose config`
3. Test connectivity: `curl http://localhost:PORT/health`
4. Check database: `docker-compose exec postgres psql ...`

**For Production Deployment:**
1. Use external PostgreSQL
2. Configure SSL/TLS
3. Add authentication (API keys, OAuth2)
4. Set up monitoring & alerting
5. Configure auto-scaling
6. Set up CI/CD pipeline
7. Document runbooks

**For Event Ingestion:**
1. Integrate log parser (rsyslog, fluentd)
2. Set up event router (Kafka, message queue)
3. Connect sensors via API
4. Build dashboard

---

**Status:** ✅ Ready for Testing  
**Last Updated:** 15 January 2026
