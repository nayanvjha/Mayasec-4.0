# Mayasec 4.0 - Security Monitoring Platform

Distributed security monitoring and threat intelligence platform with multi-sensor support, real-time event ingestion, and honeypot integration.

## Architecture Overview

### Sensor vs Platform

**Platform (Central Mayasec):**
- Flask web application running on designated host
- SQLite3 database for event storage and analytics
- Web dashboard for security visualization
- RESTful API (`/api/ingest/event`) for event collection
- Configurable ingestion modes (local file or API-driven)
- Single point for security monitoring and reporting

**Sensors (Suricata + Forwarder):**
- Suricata IDS running on monitored network segments
- Generates EVE JSON logs in real-time
- `suricata_forwarder.py` daemon tails eve.json locally
- Forwards alerts to central platform via HTTP POST
- No root privileges required (user-accessible logs)
- Automatic retry with exponential backoff
- Stateless design (can scale horizontally)

### Data Flow

```
Suricata (Sensor Host)
    ↓
eve.json file
    ↓
suricata_forwarder.py (tails + parses)
    ↓
POST /api/ingest/event (HTTP)
    ↓
Mayasec Platform
    ↓
log_ingestion.py (routes by event type)
    ↓
SQLite3 (security_logs, honeypot_logs, login_attempts)
    ↓
Web Dashboard / API
```

---

## Running Mayasec on Normal OS

### Prerequisites

- Python 3.6+
- SQLite3
- Flask 1.x or 2.x
- pip (Python package manager)

### Quick Start (Single Host)

1. **Install dependencies:**
```bash
pip install flask requests urllib3 werkzeug
```

2. **Run the platform:**
```bash
export FLASK_APP=app.py
export FLASK_ENV=development
python app.py
```

Platform starts on `http://localhost:8000`

3. **Access dashboard:**
```bash
# Login with default credentials
# Username: admin
# Password: admin
```

### Configuration

**Environment variables:**
- `FLASK_SECRET_KEY` - Session encryption key (auto-generated if not set)
- `DATABASE_PATH` - SQLite database location (default: `./security_logs.db`)
- `USE_LOCAL_LOGS` - Read Suricata logs from file (default: `true`)
- `SURICATA_EVE_JSON` - Path to Suricata eve.json (default: `/var/log/suricata/eve.json`)

**Example with custom settings:**
```bash
export DATABASE_PATH=/var/lib/mayasec/security.db
export USE_LOCAL_LOGS=false
python app.py
```

### Production Deployment

For production, use a WSGI server:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Create systemd service file (`/etc/systemd/system/mayasec.service`):
```ini
[Unit]
Description=Mayasec Security Platform
After=network.target

[Service]
Type=notify
User=mayasec
WorkingDirectory=/opt/mayasec
Environment="FLASK_ENV=production"
Environment="DATABASE_PATH=/var/lib/mayasec/security.db"
ExecStart=/usr/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable mayasec
sudo systemctl start mayasec
```

---

## Deploying Suricata + Forwarder

### Prerequisites on Sensor Host

- Suricata IDS 6.0+ (installed and configured)
- Python 3.6+ with pip
- Network connectivity to platform host

### Installation

1. **Install forwarder dependencies:**
```bash
pip install -r requirements-forwarder.txt
```

2. **Configure forwarder:**

Option A - Environment variables:
```bash
export MAYASEC_API_URL="http://central-host:8000"
export MAYASEC_SENSOR_ID="suricata-dmz-01"
export SURICATA_EVE_JSON="/var/log/suricata/eve.json"
python suricata_forwarder.py
```

Option B - Configuration file:
```bash
# Copy and edit example config
cp forwarder-config.example.json /etc/mayasec/forwarder.json

# Edit API URL and sensor ID in /etc/mayasec/forwarder.json
python suricata_forwarder.py --config /etc/mayasec/forwarder.json
```

Option C - Command-line arguments:
```bash
python suricata_forwarder.py \
  --api-url http://central-host:8000 \
  --sensor-id suricata-dmz-01 \
  --eve-json /var/log/suricata/eve.json
```

### Systemd Integration

Create `/etc/systemd/system/suricata-forwarder.service`:
```ini
[Unit]
Description=Mayasec Suricata Forwarder
After=suricata.service network.target
Wants=suricata.service

[Service]
Type=simple
User=suricata
WorkingDirectory=/opt/mayasec-forwarder
Environment="MAYASEC_API_URL=http://central-host:8000"
Environment="MAYASEC_SENSOR_ID=suricata-prod"
Environment="LOG_LEVEL=INFO"
ExecStart=/usr/bin/python3 suricata_forwarder.py \
  --log-file /var/log/mayasec/forwarder.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable suricata-forwarder
sudo systemctl start suricata-forwarder
```

### Verification

Check if events are being forwarded:
```bash
# On sensor host - check forwarder logs
tail -f /var/log/mayasec/forwarder.log

# On platform host - query API status
curl http://localhost:8000/api/status

# Check database for events from sensor
sqlite3 security_logs.db "SELECT sensor_id, COUNT(*) FROM security_logs GROUP BY sensor_id;"
```

---

## Supported Deployment Modes

### Mode 1: Single Host (Development/Lab)

**Setup:**
```bash
# Platform and local Suricata on same machine
export USE_LOCAL_LOGS=true
python app.py
```

**Characteristics:**
- Mayasec reads eve.json directly from filesystem
- No network traffic needed
- Suitable for development and testing
- Single point of failure

**When to use:** Development, lab environments, small deployments

---

### Mode 2: API-Only (Distributed)

**Setup - Platform:**
```bash
export USE_LOCAL_LOGS=false
python app.py
```

**Setup - Sensor:**
```bash
export MAYASEC_API_URL=http://platform-host:8000
python suricata_forwarder.py
```

**Characteristics:**
- Platform doesn't read local files
- All events via HTTP API from forwarders
- Multiple sensors supported
- Firewall-friendly (single outbound port)

**When to use:** Multi-sensor deployments, cloud environments, network segmentation

---

### Mode 3: Hybrid (Local + Remote)

**Setup - Platform:**
```bash
export USE_LOCAL_LOGS=true
export SURICATA_EVE_JSON=/var/log/suricata/eve.json
python app.py
```

**Setup - Remote Sensors:**
```bash
export MAYASEC_API_URL=http://platform-host:8000
python suricata_forwarder.py
```

**Characteristics:**
- Platform reads local Suricata logs
- Also accepts remote forwarder events
- Mixed deployment (local + remote sensors)
- Flexible scaling

**When to use:** Transitioning to distributed architecture, supporting legacy + new deployments

---

### Mode 4: High Availability

**Setup - Multiple platforms (active-passive):**
```bash
# Primary platform
export PRIMARY_DB=/var/lib/mayasec/primary.db
python app.py

# Secondary platform (read replica)
export DATABASE_PATH=/var/lib/mayasec/replica.db
python app.py --read-only
```

**Setup - Sensor forwarder with failover:**
```bash
# Forwarder retries with exponential backoff (built-in)
export MAYASEC_API_URL=http://primary-host:8000
export FAILOVER_URL=http://secondary-host:8000
python suricata_forwarder.py
```

**Characteristics:**
- Database replication between platforms
- Automatic failover with health checks
- Zero event loss
- Requires database sync mechanism (external)

**When to use:** Production critical monitoring, SLA requirements

---

## Event Flow

### Login Event
```
Source (SSH/Honeypot) → Mayasec → security_logs (action: login)
```

### Honeypot Event
```
Attacker → Honeypot → Mayasec → honeypot_logs + security_logs
```

### Network Alert (Suricata)
```
Suricata (Sensor) → eve.json → forwarder → /api/ingest/event → security_logs (threat_level)
```

### Security Action
```
API → /api/ingest/event → security_logs (generic event type)
```

---

## Monitoring & Verification

### Check Platform Status
```bash
curl http://localhost:8000/api/status
```

Response includes:
- `use_local_logs` configuration flag
- `mode` (single-host vs distributed)
- Database path
- Suricata eve.json path

### Query Events by Sensor
```bash
sqlite3 security_logs.db \
  "SELECT sensor_id, event_type, COUNT(*) FROM security_logs GROUP BY sensor_id, event_type;"
```

### Monitor Forwarder Health
```bash
# View statistics in logs
grep "statistics" /var/log/mayasec/forwarder.log | tail -5

# Check if service is running
systemctl status suricata-forwarder
```

### Test API Ingestion
```bash
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "sensor_id": "test-sensor",
    "timestamp": "2026-01-15T10:00:00Z",
    "event_type": "network_alert",
    "data": {"sid": 1234, "msg": "Test alert"}
  }'
```

---

## Documentation

- [SENSOR_ID_IMPLEMENTATION.md](SENSOR_ID_IMPLEMENTATION.md) - Sensor tracking details
- [CONFIG_USE_LOCAL_LOGS.md](CONFIG_USE_LOCAL_LOGS.md) - Configuration flag reference
- [SURICATA_FORWARDER.md](SURICATA_FORWARDER.md) - Forwarder comprehensive guide
- [USE_LOCAL_LOGS_QUICK_REFERENCE.md](USE_LOCAL_LOGS_QUICK_REFERENCE.md) - Quick reference

---

## Troubleshooting

**Platform won't start:**
- Check Python version: `python --version`
- Verify dependencies: `pip list | grep -i flask`
- Check database permissions: `ls -la security_logs.db`

**Forwarder not sending events:**
- Verify API URL reachability: `curl http://platform-host:8000/api/status`
- Check forwarder logs: `tail -f /var/log/mayasec/forwarder.log`
- Verify eve.json path exists: `ls -la /var/log/suricata/eve.json`

**Events not appearing in dashboard:**
- Enable `USE_LOCAL_LOGS` if using file mode: `export USE_LOCAL_LOGS=true`
- Check sensor_id in database: `sqlite3 security_logs.db "SELECT DISTINCT sensor_id FROM security_logs;"`
- Verify event type routing in logs: `grep "event_type" security_monitor.log`

---

**Version:** 4.0  
**Last Updated:** January 2026
