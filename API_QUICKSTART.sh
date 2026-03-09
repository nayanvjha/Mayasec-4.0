#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# MAYASEC CONTROL PLANE API - QUICK START & TESTING
# ═══════════════════════════════════════════════════════════════════════════════

# This script demonstrates:
# 1. Starting the control plane API
# 2. Testing all endpoints
# 3. Verifying integration with core + storage
# 4. Example curl commands

set -e

API_URL="${API_URL:-http://localhost:5000}"
CORE_URL="${CORE_URL:-http://localhost:5001}"
DB_HOST="${DB_HOST:-localhost}"

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  MAYASEC CONTROL PLANE API - QUICK START GUIDE                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1: START API
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

1. START API SERVER
═══════════════════════════════════════════════════════════════════════════════

Environment Variables:
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=mayasec
  DB_USER=mayasec
  DB_PASSWORD=mayasec
  CORE_URL=http://localhost:5001
  API_PORT=5000
  API_DEBUG=False

Start API:
  python mayasec_api.py

Expected output:
  Starting Mayasec Control Plane API on port 5000
  WARNING in app.flaskenv: No Flask config found...

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2: HEALTH CHECKS
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

2. HEALTH CHECKS
═══════════════════════════════════════════════════════════════════════════════

Quick Health (Storage only):
  curl http://localhost:5000/health
  curl http://localhost:5000/api/v1/health

Response:
  {
    "status": "healthy",
    "timestamp": "2026-01-15T10:30:00Z",
    "services": {
      "storage": "healthy"
    }
  }

Deep Health (All services):
  curl http://localhost:5000/api/v1/health/deep

Response:
  {
    "status": "healthy",
    "timestamp": "2026-01-15T10:30:00Z",
    "services": {
      "storage": {"status": "healthy", "response_time": "5-10ms"},
      "core": {"status": "healthy", "url": "http://localhost:5001"},
      "honeypot": {"status": "healthy", "url": "http://localhost:5003", "optional": true}
    }
  }

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: EVENTS ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

3. EVENTS ENDPOINTS
═══════════════════════════════════════════════════════════════════════════════

List All Events (Last 7 days):
  curl "http://localhost:5000/api/v1/events"

List Events - Filter by IP:
  curl "http://localhost:5000/api/v1/events?ip_address=192.168.1.1"

List Events - Filter by Threat Level:
  curl "http://localhost:5000/api/v1/events?threat_level=high&days=7"

List Events - All Filters:
  curl "http://localhost:5000/api/v1/events?ip_address=192.168.1.1&username=admin&threat_level=high&days=7&limit=50"

Get Specific Event:
  curl "http://localhost:5000/api/v1/events/550e8400-e29b-41d4-a716-446655440000"

Response:
  {
    "count": 5,
    "events": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-01-15T10:30:00Z",
        "event_type": "login_attempt",
        "source_ip": "192.168.1.1",
        "threat_level": "high",
        "threat_score": 85,
        "description": "Multiple failed login attempts"
      }
    ],
    "filters": {
      "ip_address": "192.168.1.1",
      "username": null,
      "threat_level": "high",
      "days": 7
    }
  }

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4: ALERTS ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

4. ALERTS ENDPOINTS
═══════════════════════════════════════════════════════════════════════════════

List Open Alerts:
  curl "http://localhost:5000/api/v1/alerts"

List with Limit:
  curl "http://localhost:5000/api/v1/alerts?limit=50"

Check If IP is Blocked:
  curl "http://localhost:5000/api/v1/alerts/status/192.168.1.1"

Block IP (24 hours):
  curl -X POST http://localhost:5000/api/v1/alerts/block \
    -H "Content-Type: application/json" \
    -d '{
      "ip_address": "192.168.1.1",
      "reason": "Brute force attack detected",
      "is_permanent": false
    }'

Block IP (Permanent):
  curl -X POST http://localhost:5000/api/v1/alerts/block \
    -H "Content-Type: application/json" \
    -d '{
      "ip_address": "192.168.1.1",
      "reason": "Known malicious actor",
      "is_permanent": true
    }'

Response:
  {
    "status": "blocked",
    "ip_address": "192.168.1.1",
    "reason": "Brute force attack",
    "is_permanent": false,
    "expires_at": "2026-01-16T10:30:00Z"
  }

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5: METRICS ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

5. METRICS ENDPOINTS
═══════════════════════════════════════════════════════════════════════════════

All Metrics (Threat distribution + Top IPs):
  curl "http://localhost:5000/api/v1/metrics?days=7"

Threat Distribution:
  curl "http://localhost:5000/api/v1/metrics/threat-distribution?days=30"

Top Attacking IPs:
  curl "http://localhost:5000/api/v1/metrics/top-ips?days=7&limit=20"

Threat Summary for Specific IP:
  curl "http://localhost:5000/api/v1/metrics/threat-summary?ip_address=192.168.1.1&days=7"

Response (Threat Distribution):
  {
    "period": "Last 7 days",
    "distribution": {
      "low": 50,
      "medium": 30,
      "high": 15,
      "critical": 5
    }
  }

Response (Top IPs):
  {
    "period": "Last 7 days",
    "limit": 20,
    "ips": [
      {"ip_address": "192.168.1.1", "event_count": 25},
      {"ip_address": "192.168.1.2", "event_count": 18}
    ]
  }

Response (Threat Summary):
  {
    "ip_address": "192.168.1.1",
    "period": "Last 7 days",
    "summary": {
      "event_count": 25,
      "avg_threat_score": 72.5,
      "max_threat_score": 95,
      "threat_levels": {
        "low": 5,
        "medium": 8,
        "high": 10,
        "critical": 2
      }
    }
  }

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6: OPENAPI
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

6. OPENAPI SPECIFICATION
═══════════════════════════════════════════════════════════════════════════════

Get OpenAPI Spec (JSON):
  curl http://localhost:5000/api/v1/openapi

View in Browser:
  # Using Swagger UI (local)
  docker run -p 8080:8080 \
    -e SPEC_URL=http://localhost:5000/api/v1/openapi \
    swaggerapi/swagger-ui

  # Then visit: http://localhost:8080

Get Specific Path from OpenAPI:
  curl http://localhost:5000/api/v1/openapi | jq '.paths."/api/v1/events"'

Get Schemas:
  curl http://localhost:5000/api/v1/openapi | jq '.components.schemas'

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7: INTEGRATION TESTING
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

7. INTEGRATION TESTING
═══════════════════════════════════════════════════════════════════════════════

Test Storage Integration:
  curl "http://localhost:5000/api/v1/events" | jq '.count'
  # Should return non-zero count if storage has events

Test Core Integration (Health):
  curl "http://localhost:5000/api/v1/health/deep" | jq '.services.core.status'
  # Should return "healthy"

Test Database Connection:
  curl "http://localhost:5000/api/v1/events?limit=1" | jq '.events[0].id'
  # Should return a valid UUID

Test Error Handling:
  curl "http://localhost:5000/api/v1/events?threat_level=invalid"
  # Should return 400 with error message

  curl "http://localhost:5000/api/v1/events/invalid-uuid"
  # Should return 404

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 8: LOAD TESTING
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

8. LOAD TESTING
═══════════════════════════════════════════════════════════════════════════════

Using Apache Bench:
  # Test health endpoint (1000 requests, 10 concurrent)
  ab -n 1000 -c 10 http://localhost:5000/health

  # Test events endpoint
  ab -n 100 -c 5 "http://localhost:5000/api/v1/events"

  # Expected: >100 requests/sec

Using wrk (more realistic):
  # Test for 30 seconds, 4 threads, 100 connections
  wrk -t4 -c100 -d30s http://localhost:5000/health

  # Expected: <10ms latency, 1000+ requests/sec

Using Apache Bench with POST:
  # Test block endpoint
  ab -n 100 -c 5 -p payload.json \
    -T application/json \
    http://localhost:5000/api/v1/alerts/block

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 9: PYTHON CLIENT
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

9. PYTHON CLIENT EXAMPLE
═══════════════════════════════════════════════════════════════════════════════

import requests
import json

API_URL = "http://localhost:5000"

# Get events for specific IP
def get_events_for_ip(ip_address):
    response = requests.get(
        f"{API_URL}/api/v1/events",
        params={
            "ip_address": ip_address,
            "threat_level": "high",
            "days": 7,
            "limit": 50
        }
    )
    return response.json()["events"]

# Get all metrics
def get_metrics():
    response = requests.get(
        f"{API_URL}/api/v1/metrics",
        params={"days": 7}
    )
    return response.json()

# Block an IP address
def block_ip(ip_address, reason):
    response = requests.post(
        f"{API_URL}/api/v1/alerts/block",
        json={
            "ip_address": ip_address,
            "reason": reason,
            "is_permanent": False
        }
    )
    return response.json()

# Health check
def health_check():
    response = requests.get(f"{API_URL}/api/v1/health/deep")
    return response.json()

# Usage
if __name__ == "__main__":
    # Check health
    health = health_check()
    print(f"API Status: {health['status']}")
    
    # Get events
    events = get_events_for_ip("192.168.1.1")
    print(f"Found {len(events)} high-threat events from 192.168.1.1")
    
    # Get metrics
    metrics = get_metrics()
    print(f"Threat distribution: {metrics['threat_distribution']}")
    
    # Block IP
    result = block_ip("192.168.1.100", "Suspicious behavior")
    print(f"Blocked: {result['ip_address']}")

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 10: DEPLOYMENT
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

10. DEPLOYMENT
═══════════════════════════════════════════════════════════════════════════════

Docker Deployment:

  FROM python:3.9
  
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install -r requirements.txt
  
  COPY mayasec_api.py .
  COPY repository.py .
  
  EXPOSE 5000
  
  CMD ["python", "mayasec_api.py"]

Docker Compose:

  version: '3.8'
  services:
    api:
      build: .
      ports:
        - "5000:5000"
      environment:
        DB_HOST: postgres
        DB_PORT: 5432
        DB_NAME: mayasec
        DB_USER: mayasec
        DB_PASSWORD: mayasec
        CORE_URL: http://core:5001
      depends_on:
        - core
        - postgres
    
    core:
      image: mayasec-core:latest
      ports:
        - "5001:5001"
    
    postgres:
      image: postgres:13
      environment:
        POSTGRES_DB: mayasec
        POSTGRES_USER: mayasec
        POSTGRES_PASSWORD: mayasec

Kubernetes Deployment:

  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: mayasec-api
  spec:
    replicas: 3
    selector:
      matchLabels:
        app: mayasec-api
    template:
      metadata:
        labels:
          app: mayasec-api
      spec:
        containers:
        - name: api
          image: mayasec-api:latest
          ports:
          - containerPort: 5000
          env:
          - name: DB_HOST
            value: postgres.default
          - name: CORE_URL
            value: http://mayasec-core:5001
          livenessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/v1/health/deep
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 10

EOF

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 11: TROUBLESHOOTING
# ═════════════════════════════════════════════════════════════════════════════

cat << 'EOF'

11. TROUBLESHOOTING
═══════════════════════════════════════════════════════════════════════════════

API Not Starting:
  1. Check Python version: python --version (need 3.7+)
  2. Check dependencies: pip install flask requests
  3. Check port: lsof -i :5000
  4. Check logs for errors

API Health Returns Unhealthy:
  1. Check PostgreSQL: psql -h localhost -U mayasec -d mayasec -c "SELECT 1"
  2. Check Core service: curl http://localhost:5001/health
  3. Check connection string in environment variables
  4. Check database migrations: python migration_manager.py status

Slow Queries:
  1. Check database indices: psql ... -c "\d security_logs"
  2. Run ANALYZE: psql ... -c "ANALYZE"
  3. Add more connections: increase MAX_EVENTS_LIMIT
  4. Check Core service performance

Connection Pool Exhausted:
  1. Check for hung connections: psql ... -c "SELECT * FROM pg_stat_activity"
  2. Restart API service
  3. Increase pool size in repository.py (currently 1-5)
  4. Monitor connection usage

EOF

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  For complete documentation, see API_DOCUMENTATION.md             ║"
echo "║  For OpenAPI spec, visit: /api/v1/openapi                         ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
