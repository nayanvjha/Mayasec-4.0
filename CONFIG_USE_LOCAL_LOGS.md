# Configuration: File-Based vs API-Only Ingestion

## Overview

The Mayasec system supports two operational modes for event ingestion:

1. **File-Based Mode** (default): Read Suricata logs directly from the filesystem
2. **API-Only Mode**: Disable file reading, accept events exclusively via HTTP API

## Configuration Flag: `USE_LOCAL_LOGS`

### Default Behavior

```
USE_LOCAL_LOGS = true
```

By default, file-based ingestion is **enabled** for backward compatibility.

### Setting the Configuration

#### Option 1: Environment Variable (Recommended)

Set the environment variable before starting the application:

```bash
# Enable file-based ingestion (default)
export USE_LOCAL_LOGS=true
python app.py

# OR

# Disable file-based ingestion (API-only mode)
export USE_LOCAL_LOGS=false
python app.py
```

#### Option 2: Direct Python

Edit `app.py` directly (not recommended for production):

```python
# Line ~28 in app.py
USE_LOCAL_LOGS = False  # Set to False for API-only mode
```

### Valid Values

The flag accepts multiple formats (case-insensitive):

| Value | Effect |
|-------|--------|
| `true`, `True`, `TRUE` | Enable file-based ingestion |
| `1` | Enable file-based ingestion |
| `yes` | Enable file-based ingestion |
| `false`, `False`, `FALSE` | Disable file-based ingestion |
| `0` | Disable file-based ingestion |
| `no` | Disable file-based ingestion |
| (not set) | Default: true |

---

## Mode 1: File-Based Ingestion (USE_LOCAL_LOGS = true)

### Behavior

- **Enabled routes:**
  - `GET /network_logs` - Display paginated Suricata logs
  - `GET /network_logs_data` - Return table rows of Suricata logs
  
- **Data source:** `/var/log/suricata/eve.json` (configurable in app.py)

- **Processing:** Logs are read on-demand when user accesses the routes

### Example Startup

```bash
$ export USE_LOCAL_LOGS=true
$ python app.py

🚀 Starting Adaptive Security System...
📊 Database initialized at: security_logs.db
🔧 Configuration: USE_LOCAL_LOGS = True
📁 File-based ingestion ENABLED
   Reading Suricata logs from: /var/log/suricata/eve.json
🛡️  Security monitoring started

💡 Check /api/status for current configuration
 * Running on http://0.0.0.0:8000
```

### Routes Available

```
GET  /network_logs       → Display paginated Suricata alerts (HTML)
GET  /network_logs_data  → Get table rows of alerts (HTML fragments)
GET  /api/status         → Get system configuration status (JSON)
```

### Use Cases

- Single-sensor deployments
- Suricata running on the same host as Mayasec
- Central log aggregation with direct filesystem access
- Existing deployments using file-based collection

---

## Mode 2: API-Only Ingestion (USE_LOCAL_LOGS = false)

### Behavior

- **Disabled routes:**
  - `GET /network_logs` - Returns 403 with disabled message
  - `GET /network_logs_data` - Returns 403 JSON error
  
- **Enabled ingestion:**
  - `POST /api/ingest/event` - Accept events via HTTP API
  - All other event processing continues normally

- **Data source:** HTTP API exclusively

### Example Startup

```bash
$ export USE_LOCAL_LOGS=false
$ python app.py

🚀 Starting Adaptive Security System...
📊 Database initialized at: security_logs.db
🔧 Configuration: USE_LOCAL_LOGS = False
📁 File-based ingestion DISABLED
   Using API-only mode: POST /api/ingest/event
🛡️  Security monitoring started

💡 Check /api/status for current configuration
 * Running on http://0.0.0.0:8000
```

### Routes Affected

```
GET  /network_logs       → Returns 403 (disabled)
GET  /network_logs_data  → Returns 403 JSON error (disabled)
POST /api/ingest/event   → Available for event submission
GET  /api/status         → Get system configuration status (JSON)
```

### Response When File-Based Routes Are Disabled

**GET /network_logs:**
```html
Template renders with:
- disabled=True
- disabled_message="File-based log ingestion is disabled. USE_LOCAL_LOGS=false. 
                     Please submit events via POST /api/ingest/event"
- network_logs=[] (empty list)
```

**GET /network_logs_data:**
```json
{
  "error": "File-based log ingestion is disabled",
  "message": "USE_LOCAL_LOGS is set to false. Please use POST /api/ingest/event to submit network alerts."
}
```

### Use Cases

- Multi-sensor deployments (sensors push events via API)
- Distributed security infrastructure
- Cloud deployments (no local filesystem access)
- Event normalization before storage
- Centralized sensor orchestration
- Security separation (prevent local file access)

---

## API Ingestion Endpoint

Both modes support:

```
POST /api/ingest/event
```

### Request Format

```json
{
  "source": "string",           // Event source identifier
  "sensor_id": "string",        // Sensor identifier
  "timestamp": "ISO 8601",      // Event timestamp
  "data": {                     // Event details
    "event_type": "login|honeypot|network_alert|security_action",
    ...
  }
}
```

### Example: Submit Network Alert via API

```bash
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "suricata-remote",
    "sensor_id": "suricata-dmz-01",
    "timestamp": "2026-01-15T12:30:00Z",
    "data": {
      "event_type": "network_alert",
      "src_ip": "203.0.113.50",
      "dest_ip": "10.0.0.1",
      "proto": "TCP",
      "alert": {
        "signature": "ET POLICY Suspicious Activity",
        "severity_name": "HIGH"
      }
    }
  }'
```

---

## System Status Endpoint

Check current configuration:

```
GET /api/status
```

### Response Format

```json
{
  "status": "online",
  "timestamp": "2026-01-15T12:35:00.123456",
  "configuration": {
    "use_local_logs": true,
    "database": "security_logs.db",
    "suricata_log_path": "/var/log/suricata/eve.json",
    "security_monitoring_enabled": true
  },
  "features": {
    "file_based_ingestion": true,
    "api_ingestion": true,
    "honeypot": true,
    "threat_analysis": true
  }
}
```

### Example Check

```bash
# Check if file-based ingestion is enabled
curl http://localhost:8000/api/status | jq '.configuration.use_local_logs'

# Output: true or false
```

---

## Migration Guide

### Switching from File-Based to API-Only

1. **Stop the application**
   ```bash
   # Send SIGTERM to running process
   kill <pid>
   ```

2. **Set environment variable**
   ```bash
   export USE_LOCAL_LOGS=false
   ```

3. **Restart application**
   ```bash
   python app.py
   ```

4. **Verify configuration**
   ```bash
   curl http://localhost:8000/api/status
   ```

5. **Update sensors** to push events via `/api/ingest/event`

### Switching from API-Only to File-Based

1. **Stop the application**
   ```bash
   kill <pid>
   ```

2. **Set environment variable**
   ```bash
   export USE_LOCAL_LOGS=true
   ```

3. **Ensure Suricata is configured** to write to `/var/log/suricata/eve.json`

4. **Restart application**
   ```bash
   python app.py
   ```

5. **Verify logs are being read**
   ```bash
   curl http://localhost:8000/api/status
   ```

---

## Production Deployment Scenarios

### Scenario 1: Single Host with Suricata

```
Host 1:
├─ Suricata IDS
│  └─ /var/log/suricata/eve.json
├─ Mayasec (USE_LOCAL_LOGS=true)
│  └─ Reads Suricata logs directly
└─ Dashboard/API

Configuration:
export USE_LOCAL_LOGS=true
```

### Scenario 2: Distributed Multi-Sensor

```
Sensor 1 (Suricata)
├─ Sends alerts to Mayasec API
│
Sensor 2 (Honeypot)
├─ Sends interactions to Mayasec API
│
Sensor 3 (SIEM)
├─ Sends events to Mayasec API
│
Central Mayasec (USE_LOCAL_LOGS=false)
├─ Receives all events via /api/ingest/event
├─ Normalizes and analyzes
└─ Stores in database

Configuration:
export USE_LOCAL_LOGS=false
```

### Scenario 3: Hybrid Deployment

```
Local Suricata
├─ /var/log/suricata/eve.json
├─ Mayasec reads directly (USE_LOCAL_LOGS=true)
│
Remote Sensor
├─ Sends alerts via API
├─ routed to ingest_event()
└─ Stored same as local events

Configuration:
export USE_LOCAL_LOGS=true
(Both modes work simultaneously)
```

---

## Backward Compatibility

✅ **Default:** File-based ingestion enabled (`USE_LOCAL_LOGS=true`)  
✅ **No breaking changes:** Existing deployments continue to work  
✅ **Opt-in:** Switch to API-only by setting environment variable  
✅ **Code preserved:** File-based functions not deleted, just conditionally used  

---

## Troubleshooting

### "File-based log ingestion is disabled"

**Problem:** User tries to access `/network_logs` when `USE_LOCAL_LOGS=false`

**Solution:** 
1. Set `USE_LOCAL_LOGS=true` to enable file-based ingestion, OR
2. Use `POST /api/ingest/event` to submit events if API-only mode is intended

### Suricata logs not appearing

**Problem:** File-based logs not showing despite `USE_LOCAL_LOGS=true`

**Check:**
1. Verify Suricata is running and writing to `/var/log/suricata/eve.json`
2. Check file permissions: `ls -la /var/log/suricata/eve.json`
3. Verify path matches `SURICATA_LOG_PATH` in app.py
4. Check system logs for errors

### API ingestion failing when `USE_LOCAL_LOGS=false`

**Problem:** Events not being ingested via API

**Check:**
1. Verify endpoint is accessible: `curl http://localhost:8000/api/ingest/event`
2. Check request format matches schema
3. Verify `Content-Type: application/json` header
4. Check server logs for validation errors

---

## Summary Table

| Feature | USE_LOCAL_LOGS=true | USE_LOCAL_LOGS=false |
|---------|:-:|:-:|
| Read `/var/log/suricata/eve.json` | ✅ | ❌ |
| `/network_logs` route | ✅ | ❌ |
| `/network_logs_data` route | ✅ | ❌ |
| `/api/ingest/event` endpoint | ✅ | ✅ |
| Direct filesystem access | ✅ | ❌ |
| Remote sensor integration | ✅ | ✅ |
| API-based event processing | ✅ | ✅ |
| Database storage | ✅ | ✅ |

