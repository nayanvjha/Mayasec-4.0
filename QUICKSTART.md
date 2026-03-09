# Mayasec 4.0 - Quick Start Guide

## Run Platform Locally (5 minutes)

### Step 1: Install Dependencies
```bash
pip install flask requests urllib3 werkzeug
```

### Step 2: Start the Platform
```bash
cd /path/to/Mayasec-4.0-main
python app.py
```

**Expected output:**
```
 * Running on http://127.0.0.1:8000
 * Configuration: USE_LOCAL_LOGS=True (file-based ingestion enabled)
```

### Step 3: Access Dashboard
Open browser: `http://localhost:8000`

**Default Credentials:**
- Username: `admin`
- Password: `admin`

**Dashboard Features:**
- Security Logs - View all security events
- Honeypot Logs - Monitor honeypot interactions  
- Network Logs - Suricata IDS alerts (if using local eve.json)
- Security Report - Event summary and statistics

---

## Deploy Remote Suricata Sensor (10 minutes)

### On Sensor Host:

**Step 1: Install Forwarder Dependencies**
```bash
pip install -r requirements-forwarder.txt
```

**Step 2: Start Forwarder**
```bash
export MAYASEC_API_URL="http://your-platform-host:8000"
export MAYASEC_SENSOR_ID="suricata-sensor-01"
python suricata_forwarder.py
```

**Expected output:**
```
2026-01-15 10:15:32 - SuricataForwarder - INFO - Starting forwarder (sensor: suricata-sensor-01)
2026-01-15 10:15:32 - SuricataForwarder - INFO - Tailing: /var/log/suricata/eve.json
2026-01-15 10:15:33 - EventSubmitter - INFO - Batch submitted (3 events, 1 retries)
```

**Step 3: Verify in Dashboard**
Back on platform, go to Security Logs and filter by sensor_id `suricata-sensor-01`

---

## Local Testing (No Suricata Required)

### Send Test Events via API

```bash
# Test 1: Network Alert
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "suricata",
    "sensor_id": "test-sensor",
    "timestamp": "2026-01-15T10:00:00Z",
    "event_type": "network_alert",
    "data": {
      "sid": 2100498,
      "msg": "ET MALWARE User-Agent in HTTP Request",
      "src_ip": "192.168.1.100",
      "dest_ip": "10.0.0.1",
      "dest_port": 443,
      "proto": "TCP"
    }
  }'

# Test 2: Honeypot Event
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "honeypot",
    "sensor_id": "honeypot-01",
    "timestamp": "2026-01-15T10:05:00Z",
    "event_type": "honeypot",
    "data": {
      "ip_address": "203.0.113.45",
      "username": "root",
      "password_attempt": "123456",
      "user_agent": "SSH-2.0-OpenSSH_7.4"
    }
  }'

# Test 3: Login Event
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "login",
    "sensor_id": "webserver-01",
    "timestamp": "2026-01-15T10:10:00Z",
    "event_type": "login",
    "data": {
      "ip_address": "192.168.1.50",
      "username": "admin",
      "user_agent": "Mozilla/5.0"
    }
  }'
```

Check dashboard - new events should appear in Security Logs within seconds.

---

## Production Setup with Systemd

### Platform Service (`/etc/systemd/system/mayasec.service`)

```ini
[Unit]
Description=Mayasec Security Platform
After=network.target

[Service]
Type=simple
User=mayasec
WorkingDirectory=/opt/mayasec
Environment="FLASK_ENV=production"
Environment="DATABASE_PATH=/var/lib/mayasec/security.db"
Environment="USE_LOCAL_LOGS=true"
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Deploy:**
```bash
sudo cp mayasec.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mayasec
sudo systemctl start mayasec
sudo systemctl status mayasec
```

### Forwarder Service (`/etc/systemd/system/suricata-forwarder.service`)

```ini
[Unit]
Description=Mayasec Suricata Forwarder
After=suricata.service network.target

[Service]
Type=simple
User=suricata
WorkingDirectory=/opt/mayasec-forwarder
Environment="MAYASEC_API_URL=http://platform-host:8000"
Environment="MAYASEC_SENSOR_ID=suricata-01"
Environment="LOG_LEVEL=INFO"
ExecStart=/usr/bin/python3 suricata_forwarder.py --log-file /var/log/mayasec/forwarder.log
Restart=always

[Install]
WantedBy=multi-user.target
```

**Deploy:**
```bash
sudo cp suricata-forwarder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable suricata-forwarder
sudo systemctl start suricata-forwarder
sudo systemctl status suricata-forwarder
```

---

## Monitor & Verify

### Check Platform Status
```bash
curl http://localhost:8000/api/status | jq
```

### View Events in Database
```bash
sqlite3 security_logs.db "SELECT sensor_id, COUNT(*) FROM security_logs GROUP BY sensor_id;"
```

### Check Forwarder Logs
```bash
tail -f /var/log/mayasec/forwarder.log
```

### Verify Sensor Connected
```bash
# List unique sensors
sqlite3 security_logs.db "SELECT DISTINCT sensor_id FROM security_logs;"

# Count events per sensor
sqlite3 security_logs.db "SELECT sensor_id, COUNT(*) as event_count FROM security_logs GROUP BY sensor_id ORDER BY event_count DESC;"
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Port 8000 already in use | `lsof -i :8000` then kill process or use different port |
| "No module named flask" | Run `pip install flask` |
| Database locked error | Check no other process is using SQLite db |
| Forwarder events not appearing | Check `MAYASEC_API_URL` is correct and reachable |
| Suricata eve.json not found | Set `SURICATA_EVE_JSON` env var to correct path |

---

## Next Steps

1. **Explore dashboard** - Navigate to Security Logs, Honeypot Logs, Network Logs tabs
2. **Generate test alerts** - Use curl commands above to send test events
3. **Deploy real sensors** - Configure Suricata + forwarder on network segment
4. **Set up alerts** - (Future feature) Configure webhooks/email notifications
5. **Read full docs** - See README.md for detailed architecture and config options

