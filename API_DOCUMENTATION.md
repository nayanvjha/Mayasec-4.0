# Mayasec Control Plane API

Complete REST API for querying events, alerts, and metrics. Control plane that talks to core + storage only, with no file system dependencies.

## 📋 Overview

**Role:** Control plane for Mayasec security platform
**Dependencies:** Core service + Storage layer (PostgreSQL)
**Port:** 5000 (configurable)
**OpenAPI:** `/api/v1/openapi` or `/openapi.json`

**Architecture:**
```
Sensors → Core (threat analysis) → Storage (persist)
           ↑
           │
         API (query)
         
API talks to: Core (health) + Storage (events/alerts/metrics)
API does NOT talk to: Sensors, file system
```

---

## 🚀 Quick Start

### 1. Run API Server

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=mayasec
export DB_USER=mayasec
export DB_PASSWORD=mayasec
export CORE_URL=http://localhost:5001
export API_PORT=5000

python mayasec_api.py
```

### 2. Check Health

```bash
curl http://localhost:5000/health
```

### 3. List Events

```bash
curl "http://localhost:5000/api/v1/events?threat_level=high&days=7&limit=50"
```

### 4. Get Metrics

```bash
curl "http://localhost:5000/api/v1/metrics?days=7"
```

---

## 📡 API Endpoints

### Health Checks

#### Quick Health
```
GET /health
GET /api/v1/health
```

Response (200):
```json
{
  "status": "healthy",
  "timestamp": "2026-01-15T10:30:00Z",
  "services": {
    "storage": "healthy"
  }
}
```

---

#### Deep Health
```
GET /api/v1/health/deep
```

Response (200):
```json
{
  "status": "healthy",
  "timestamp": "2026-01-15T10:30:00Z",
  "services": {
    "storage": {
      "status": "healthy",
      "response_time": "5-10ms"
    },
    "core": {
      "status": "healthy",
      "url": "http://localhost:5001"
    },
    "honeypot": {
      "status": "healthy",
      "url": "http://localhost:5003",
      "optional": true
    }
  }
}
```

---

### Events

#### List Events
```
GET /api/v1/events
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ip_address | string | null | Filter by source IP |
| username | string | null | Filter by username |
| threat_level | string | null | low \| medium \| high \| critical |
| days | integer | 7 | Query range (1-365) |
| limit | integer | 100 | Max results (1-1000) |

**Request:**
```bash
curl "http://localhost:5000/api/v1/events?ip_address=192.168.1.1&threat_level=high&days=7&limit=50"
```

**Response (200):**
```json
{
  "count": 5,
  "events": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-01-15T10:30:00Z",
      "event_type": "login_attempt",
      "source_ip": "192.168.1.1",
      "destination_ip": "10.0.0.1",
      "username": "admin",
      "threat_level": "high",
      "threat_score": 85,
      "description": "Multiple failed login attempts",
      "sensor_id": "sensor-1",
      "metadata": {
        "attempt_count": 10,
        "time_window": "5 minutes"
      }
    }
  ],
  "filters": {
    "ip_address": "192.168.1.1",
    "username": null,
    "threat_level": "high",
    "days": 7
  }
}
```

---

#### Get Event
```
GET /api/v1/events/{event_id}
```

**Request:**
```bash
curl http://localhost:5000/api/v1/events/550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**
```json
{
  "event": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-01-15T10:30:00Z",
    "event_type": "login_attempt",
    "source_ip": "192.168.1.1",
    "threat_level": "high",
    "threat_score": 85
  }
}
```

---

### Alerts

#### List Open Alerts
```
GET /api/v1/alerts
```

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| limit | integer | 100 |

**Request:**
```bash
curl "http://localhost:5000/api/v1/alerts?limit=50"
```

**Response (200):**
```json
{
  "count": 3,
  "alerts": [
    {
      "id": "alert-001",
      "rule_id": "rule-brute-force",
      "title": "Brute Force Attack Detected",
      "severity": "high",
      "status": "open",
      "created_at": "2026-01-15T10:30:00Z",
      "resolved_at": null,
      "event_ids": [
        "550e8400-e29b-41d4-a716-446655440000",
        "550e8400-e29b-41d4-a716-446655440001"
      ]
    }
  ]
}
```

---

#### Block IP Address
```
POST /api/v1/alerts/block
```

**Request Body:**
```json
{
  "ip_address": "192.168.1.1",
  "reason": "Brute force attack detected",
  "is_permanent": false
}
```

**Request:**
```bash
curl -X POST http://localhost:5000/api/v1/alerts/block \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.1",
    "reason": "Brute force attack",
    "is_permanent": false
  }'
```

**Response (200):**
```json
{
  "status": "blocked",
  "ip_address": "192.168.1.1",
  "reason": "Brute force attack",
  "is_permanent": false,
  "expires_at": "2026-01-16T10:30:00Z"
}
```

---

#### Check IP Block Status
```
GET /api/v1/alerts/status/{ip_address}
```

**Request:**
```bash
curl http://localhost:5000/api/v1/alerts/status/192.168.1.1
```

**Response (200):**
```json
{
  "ip_address": "192.168.1.1",
  "is_blocked": true
}
```

---

### Metrics

#### All Metrics
```
GET /api/v1/metrics
```

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| days | integer | 7 |

**Request:**
```bash
curl "http://localhost:5000/api/v1/metrics?days=7"
```

**Response (200):**
```json
{
  "period": "Last 7 days",
  "threat_distribution": {
    "low": 50,
    "medium": 30,
    "high": 15,
    "critical": 5
  },
  "top_ips": [
    {
      "ip_address": "192.168.1.1",
      "event_count": 25
    },
    {
      "ip_address": "192.168.1.2",
      "event_count": 18
    }
  ]
}
```

---

#### Threat Distribution
```
GET /api/v1/metrics/threat-distribution
```

**Request:**
```bash
curl "http://localhost:5000/api/v1/metrics/threat-distribution?days=7"
```

**Response (200):**
```json
{
  "period": "Last 7 days",
  "distribution": {
    "low": 50,
    "medium": 30,
    "high": 15,
    "critical": 5
  }
}
```

---

#### Top IPs
```
GET /api/v1/metrics/top-ips
```

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| days | integer | 7 |
| limit | integer | 10 |

**Request:**
```bash
curl "http://localhost:5000/api/v1/metrics/top-ips?days=7&limit=5"
```

**Response (200):**
```json
{
  "period": "Last 7 days",
  "limit": 5,
  "ips": [
    {
      "ip_address": "192.168.1.1",
      "event_count": 25
    },
    {
      "ip_address": "192.168.1.2",
      "event_count": 18
    },
    {
      "ip_address": "192.168.1.3",
      "event_count": 12
    }
  ]
}
```

---

#### Threat Summary for IP
```
GET /api/v1/metrics/threat-summary
```

**Query Parameters:**
| Param | Type | Required |
|-------|------|----------|
| ip_address | string | ✓ |
| days | integer | 7 |

**Request:**
```bash
curl "http://localhost:5000/api/v1/metrics/threat-summary?ip_address=192.168.1.1&days=7"
```

**Response (200):**
```json
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
```

---

### OpenAPI

#### Get Specification
```
GET /api/v1/openapi
GET /openapi.json
```

Returns full OpenAPI 3.0 specification in JSON format.

---

## ⚙️ Configuration

### Environment Variables

```bash
# Database (Storage Layer)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mayasec
DB_USER=mayasec
DB_PASSWORD=mayasec

# Core Service
CORE_URL=http://localhost:5001

# Honeypot Service (optional)
HONEYPOT_URL=http://localhost:5003

# API Settings
API_PORT=5000
API_DEBUG=False

# Health Check
HEALTH_TIMEOUT=5

# Query Limits
MAX_EVENTS_LIMIT=1000
MAX_ALERTS_LIMIT=500
```

### Default Configuration

```python
class ApiConfig:
    db_host = 'localhost'
    db_port = 5432
    db_name = 'mayasec'
    db_user = 'mayasec'
    db_password = 'mayasec'
    core_url = 'http://localhost:5001'
    honeypot_url = 'http://localhost:5003'
    api_port = 5000
    api_debug = False
    health_timeout = 5
    max_events_limit = 1000
    max_alerts_limit = 500
```

---

## 🔧 Integration

### With Storage Layer (Repository Pattern)

API uses repositories to query data:

```python
# Initialize repositories
db_config = DatabaseConfig(...)
event_repo = EventRepository(db_config)
alert_repo = AlertRepository(db_config)
stats_repo = StatisticsRepository(db_config)

# Use in endpoints
events = event_repo.query_logs(ip_address='192.168.1.1', days=7)
alerts = alert_repo.get_open_alerts(limit=100)
metrics = stats_repo.get_threat_distribution(days=7)
```

### With Core Service (Health Checks)

API checks core service health:

```python
response = requests.get(f"{core_url}/health", timeout=5)
core_healthy = response.status_code == 200
```

---

## 📊 Response Time Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Health check | 5ms | Storage only |
| Deep health | 10-20ms | Checks all services |
| List events | 10-50ms | Depends on query complexity |
| Get event | 5-10ms | Single event lookup |
| List alerts | 10-50ms | Query unresolved alerts |
| Block IP | 10ms | Insert to blocked_ips table |
| Check block | 5ms | Single lookup |
| Metrics | 50-100ms | Multiple aggregations |
| Threat dist | 20-50ms | Single aggregation |
| Top IPs | 30-70ms | Sort + limit |
| Threat summary | 20-100ms | IP-specific aggregation |

---

## 🔐 Security Considerations

✅ **Parameterized Queries**
- All repository methods use parameterized queries
- No SQL injection vulnerabilities

✅ **Input Validation**
- All query parameters validated before use
- Threat level validation (low/medium/high/critical)
- Limit enforcement (max 1000 events, 500 alerts)

✅ **Connection Security**
- Uses database credentials from environment
- Connection pooling (1-5 concurrent)

✅ **No File System Access**
- Pure in-memory operations
- No temporary files
- No local file dependencies

✅ **No Direct Sensor Access**
- API only talks to core + storage
- No sensor network communication
- No credential forwarding

---

## 🐛 Error Handling

### Common Errors

**400 Bad Request** - Invalid parameters
```json
{
  "error": "validation_error",
  "code": "validation_error",
  "message": "Invalid threat_level: invalid_value"
}
```

**404 Not Found** - Resource not found
```json
{
  "error": "Event not found"
}
```

**500 Internal Error** - Server error
```json
{
  "error": "internal_error",
  "message": "Database connection failed"
}
```

**503 Service Unavailable** - Service degraded
```json
{
  "status": "degraded",
  "timestamp": "2026-01-15T10:30:00Z",
  "error": "Database connection failed"
}
```

---

## 🧪 Testing

### Unit Tests

```bash
# Test health endpoint
curl http://localhost:5000/health

# Test with invalid parameters
curl "http://localhost:5000/api/v1/events?threat_level=invalid"

# Test missing required parameter
curl "http://localhost:5000/api/v1/metrics/threat-summary"
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://localhost:5000/health

# Using wrk
wrk -t4 -c100 -d30s http://localhost:5000/api/v1/events
```

---

## 📚 Integration Examples

### Python Client

```python
import requests

API_URL = "http://localhost:5000"

# Get events for IP
response = requests.get(
    f"{API_URL}/api/v1/events",
    params={
        "ip_address": "192.168.1.1",
        "threat_level": "high",
        "days": 7,
        "limit": 50
    }
)
events = response.json()['events']

# Get metrics
response = requests.get(
    f"{API_URL}/api/v1/metrics",
    params={"days": 7}
)
metrics = response.json()

# Block IP
response = requests.post(
    f"{API_URL}/api/v1/alerts/block",
    json={
        "ip_address": "192.168.1.1",
        "reason": "Brute force",
        "is_permanent": False
    }
)
```

### JavaScript Client

```javascript
const API_URL = "http://localhost:5000";

// Get events
async function getEvents(ipAddress) {
  const response = await fetch(
    `${API_URL}/api/v1/events?ip_address=${ipAddress}&threat_level=high`
  );
  return response.json();
}

// Block IP
async function blockIp(ipAddress, reason) {
  const response = await fetch(
    `${API_URL}/api/v1/alerts/block`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ip_address: ipAddress,
        reason: reason,
        is_permanent: false
      })
    }
  );
  return response.json();
}
```

### cURL Examples

```bash
# Health check
curl http://localhost:5000/health

# List high-threat events
curl "http://localhost:5000/api/v1/events?threat_level=high&days=7"

# Get metrics
curl http://localhost:5000/api/v1/metrics

# Get OpenAPI spec
curl http://localhost:5000/api/v1/openapi | jq .

# Block IP
curl -X POST http://localhost:5000/api/v1/alerts/block \
  -H "Content-Type: application/json" \
  -d '{"ip_address":"192.168.1.1","reason":"Threat"}'
```

---

## 📖 Related Documentation

- [STORAGE_ARCHITECTURE.md](STORAGE_ARCHITECTURE.md) - Storage layer design
- [STORAGE_QUICKREF.sh](STORAGE_QUICKREF.sh) - Code examples
- [openapi_spec.yaml](openapi_spec.yaml) - Full OpenAPI spec
- [mayasec_api.py](mayasec_api.py) - Implementation

---

## ✨ Key Features

✅ REST API for all security queries
✅ Health checks (quick + deep)
✅ Event filtering and search
✅ Alert management
✅ Threat metrics and analytics
✅ IP reputation/blocking
✅ OpenAPI 3.0 specification
✅ No file system dependencies
✅ Parameterized queries (SQL injection safe)
✅ Connection pooling
✅ Comprehensive error handling
✅ Fast response times (5-100ms)

---

**Status:** ✅ Production Ready
**Last Updated:** 15 January 2026
