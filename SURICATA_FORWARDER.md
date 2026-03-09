# Suricata EVE.JSON Forwarder for Mayasec

A standalone Python script that tails Suricata's EVE.JSON log file and forwards alerts to Mayasec's API ingestion endpoint.

## Overview

The `suricata_forwarder.py` script:
- **Tails** Suricata's `eve.json` file in real-time
- **Parses** JSON events with error handling
- **Maps** Suricata EVE format to Mayasec ingest format
- **Sends** events to `/api/ingest/event` via HTTP POST
- **Retries** on failure with exponential backoff
- **Requires no root** privileges (reads from user-accessible logs)
- **Runs as daemon** suitable for systemd/supervisor integration
- **Handles file rotation** automatically

## Prerequisites

```bash
pip install requests urllib3
```

Or using requirements.txt:
```bash
pip install -r requirements-forwarder.txt
```

## Installation

### Option 1: Direct Usage

```bash
# Copy the script
cp suricata_forwarder.py /opt/mayasec/

# Make executable
chmod +x /opt/mayasec/suricata_forwarder.py

# Run with default settings
python /opt/mayasec/suricata_forwarder.py
```

### Option 2: Systemd Service

Create `/etc/systemd/system/mayasec-forwarder.service`:

```ini
[Unit]
Description=Mayasec Suricata EVE.JSON Forwarder
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=suricata-log-reader
WorkingDirectory=/opt/mayasec
Environment="MAYASEC_API_URL=http://mayasec-server:8000"
Environment="MAYASEC_SENSOR_ID=suricata-production"
Environment="SURICATA_EVE_JSON=/var/log/suricata/eve.json"
Environment="LOG_LEVEL=INFO"
ExecStart=/usr/bin/python3 /opt/mayasec/suricata_forwarder.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mayasec-forwarder
sudo systemctl start mayasec-forwarder
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAYASEC_API_URL` | `http://localhost:8000` | Mayasec API URL |
| `MAYASEC_SENSOR_ID` | `suricata-forwarder` | Sensor identifier |
| `MAYASEC_SOURCE` | `suricata-eve` | Event source name |
| `SURICATA_EVE_JSON` | `/var/log/suricata/eve.json` | Path to eve.json |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `BATCH_SIZE` | `10` | Events per batch |
| `BATCH_TIMEOUT` | `5` | Batch timeout in seconds |
| `MAX_RETRIES` | `3` | Maximum API retries |
| `RETRY_BACKOFF` | `2.0` | Retry backoff multiplier |
| `READ_TIMEOUT` | `10` | HTTP request timeout |

### Configuration File (JSON)

Create a config file (e.g., `/etc/mayasec/forwarder.json`):

```json
{
  "api_url": "http://mayasec-server:8000",
  "sensor_id": "suricata-dmz-01",
  "source": "suricata-eve",
  "eve_json_path": "/var/log/suricata/eve.json",
  "log_level": "INFO",
  "batch_size": 20,
  "batch_timeout": 5,
  "max_retries": 3,
  "retry_backoff": 2.0
}
```

Load with:
```bash
python suricata_forwarder.py --config /etc/mayasec/forwarder.json
```

## Usage

### Basic Usage

```bash
# With defaults
python suricata_forwarder.py
```

### With Environment Variables

```bash
# Remote Mayasec server
MAYASEC_API_URL=http://192.168.1.100:8000 \
MAYASEC_SENSOR_ID=suricata-dmz-01 \
python suricata_forwarder.py
```

### With Command-Line Arguments

```bash
# Override specific settings
python suricata_forwarder.py \
  --api-url http://192.168.1.100:8000 \
  --sensor-id suricata-dmz-01 \
  --eve-json /var/log/suricata/eve.json
```

### With Config File + Overrides

```bash
python suricata_forwarder.py \
  --config /etc/mayasec/forwarder.json \
  --log-file /var/log/mayasec/forwarder.log
```

## Event Mapping

### Suricata EVE to Mayasec Format

The forwarder converts Suricata EVE events to Mayasec's ingest format:

```python
# Suricata EVE event:
{
  "timestamp": "2026-01-15T12:30:00.123456+0000",
  "event_type": "alert",
  "src_ip": "203.0.113.50",
  "dest_ip": "10.0.0.1",
  "src_port": 54321,
  "dest_port": 443,
  "proto": "TCP",
  "alert": {
    "action": "allowed",
    "gid": 1,
    "signature_id": 2013028,
    "signature": "ET POLICY Suspicious DNS Query",
    "category": "Suspicious Traffic",
    "severity": 2
  }
}

# Converted to Mayasec format:
{
  "source": "suricata-eve",
  "sensor_id": "suricata-forwarder",
  "timestamp": "2026-01-15T12:30:00.123456+0000",
  "data": {
    "event_type": "network_alert",
    "src_ip": "203.0.113.50",
    "dest_ip": "10.0.0.1",
    "src_port": 54321,
    "dest_port": 443,
    "proto": "TCP",
    "alert": {
      "action": "allowed",
      "signature": "ET POLICY Suspicious DNS Query",
      "severity": 2,
      ...
    },
    "eve_raw": { ... }  // Full original event
  }
}
```

### Supported Event Types

The forwarder processes:
- **alert** - IDS/IPS alerts
- **dns** - DNS queries
- **http** - HTTP requests
- **tls** - TLS/SSL events
- **flow** - Network flows
- **metadata** - Flow metadata

Other event types are silently ignored.

## Logging

### Log Levels

```bash
# Debug logging (verbose)
LOG_LEVEL=DEBUG python suricata_forwarder.py

# Info logging (default)
LOG_LEVEL=INFO python suricata_forwarder.py

# Warning logging (only warnings/errors)
LOG_LEVEL=WARNING python suricata_forwarder.py
```

### Sample Log Output

```
2026-01-15 12:30:00 - suricata_forwarder - INFO - ================================================================================
2026-01-15 12:30:00 - suricata_forwarder - INFO - Suricata EVE.JSON Forwarder for Mayasec
2026-01-15 12:30:00 - suricata_forwarder - INFO - ================================================================================
2026-01-15 12:30:00 - suricata_forwarder - INFO - Configuration: {
  "api_url": "http://localhost:8000",
  "sensor_id": "suricata-forwarder",
  "source": "suricata-eve",
  "eve_json_path": "/var/log/suricata/eve.json",
  "batch_size": 10,
  "batch_timeout": 5,
  "max_retries": 3
}
2026-01-15 12:30:00 - suricata_forwarder - INFO - ================================================================================
2026-01-15 12:30:00 - suricata_forwarder - INFO - Opened file: /var/log/suricata/eve.json
2026-01-15 12:30:05 - suricata_forwarder - INFO - Submitting batch of 5 events
2026-01-15 12:30:05 - suricata_forwarder - DEBUG - Event submitted successfully: 203.0.113.50
```

### Log to File

```bash
python suricata_forwarder.py --log-file /var/log/mayasec/forwarder.log
```

## Retry Behavior

The forwarder implements exponential backoff for failed API requests:

```
Attempt 1: Immediate
Attempt 2: Wait 2.0 seconds (backoff_factor ^ 1)
Attempt 3: Wait 4.0 seconds (backoff_factor ^ 2)
Attempt 4: Wait 8.0 seconds (backoff_factor ^ 3)
```

Retries on:
- HTTP 429 (Too Many Requests)
- HTTP 5xx (Server Errors)
- Network timeouts
- Connection failures

After max retries, events are logged and skipped.

### Customize Retry Behavior

```bash
# Fewer retries, faster failure
MAX_RETRIES=1 python suricata_forwarder.py

# More aggressive retries
MAX_RETRIES=5 RETRY_BACKOFF=1.5 python suricata_forwarder.py
```

## File Rotation Handling

The forwarder automatically handles Suricata log rotation:

```
Original file: /var/log/suricata/eve.json
Rotated to:    /var/log/suricata/eve.json.2026-01-15
New file:      /var/log/suricata/eve.json (created by Suricata)
```

The forwarder detects inode changes and re-opens the new file automatically.

## Permissions

The forwarder **requires no root privileges**. It only needs:

1. **Read access** to `/var/log/suricata/eve.json`
2. **Network access** to Mayasec API server

### Setup Non-Privileged User

```bash
# Create unprivileged user
sudo useradd -r -s /bin/false suricata-log-reader

# Give read access to eve.json
sudo setfacl -m u:suricata-log-reader:r /var/log/suricata/eve.json

# Or adjust permissions
sudo chown root:suricata-log-reader /var/log/suricata/eve.json
sudo chmod 0640 /var/log/suricata/eve.json

# Run as that user
sudo -u suricata-log-reader python suricata_forwarder.py
```

## Statistics

The forwarder logs statistics on shutdown:

```
================================================================================
Final Statistics:
  Events sent: 1247
  Events failed: 3
  Events retried: 5
  Total processed: 1255
  Success rate: 99.4%
================================================================================
```

## Troubleshooting

### "File not found" Warning

```
WARNING - Could not open file /var/log/suricata/eve.json: No such file or directory
```

**Solution:**
- Ensure Suricata is running and configured to log to eve.json
- Check file permissions: `ls -la /var/log/suricata/eve.json`
- Verify path with: `SURICATA_EVE_JSON=/correct/path python suricata_forwarder.py`

### "Connection refused" Errors

```
ERROR - Request failed: ConnectionError: Failed to establish connection
```

**Solution:**
- Verify Mayasec is running: `curl http://localhost:8000/api/status`
- Check API URL: `MAYASEC_API_URL=http://correct:8000 python suricata_forwarder.py`
- Check network connectivity: `ping mayasec-server`
- Check firewall rules

### Events Not Appearing in Mayasec

**Check:**
1. Verify Suricata is generating alerts: `tail -f /var/log/suricata/eve.json | grep alert`
2. Check forwarder logs: `python suricata_forwarder.py --log-file /tmp/debug.log`
3. Verify API is accepting events: `curl -X POST http://localhost:8000/api/ingest/event`
4. Check USE_LOCAL_LOGS setting in Mayasec (should be false for API-only)

### High CPU Usage

The default batch timeout is 5 seconds. Adjust for your environment:

```bash
# Longer timeout = lower CPU usage but higher latency
BATCH_TIMEOUT=30 python suricata_forwarder.py

# Shorter timeout = higher CPU usage but lower latency
BATCH_TIMEOUT=1 python suricata_forwarder.py
```

## Deployment Scenarios

### Scenario 1: Single Suricata on Same Host

```bash
# Mayasec with file-based ingestion
export USE_LOCAL_LOGS=true
python app.py

# OR Mayasec with API ingestion + forwarder
export USE_LOCAL_LOGS=false
python app.py &

MAYASEC_API_URL=http://localhost:8000 \
MAYASEC_SENSOR_ID=suricata-local \
python suricata_forwarder.py
```

### Scenario 2: Remote Suricata Sensors

```
Suricata Sensor 1                 Suricata Sensor 2
├─ eve.json                       ├─ eve.json
└─ suricata_forwarder.py          └─ suricata_forwarder.py
   └─ POST /api/ingest/event         └─ POST /api/ingest/event
      │                                 │
      └─────────────────┬───────────────┘
                        │
                    Central Mayasec
                  (USE_LOCAL_LOGS=false)
```

### Scenario 3: Hybrid (Local + Remote)

```
Local Suricata
├─ eve.json (direct read)
│  └─ /network_logs route
│
Remote Suricata
├─ eve.json
└─ suricata_forwarder.py
   └─ /api/ingest/event

Central Mayasec (USE_LOCAL_LOGS=true)
```

## Performance Tuning

### High-Volume Environments

```bash
BATCH_SIZE=50        # Process more events per batch
BATCH_TIMEOUT=10     # Wait longer before sending
READ_TIMEOUT=30      # Allow more time for API responses
```

### Low-Latency Environments

```bash
BATCH_SIZE=1         # Send immediately
BATCH_TIMEOUT=1      # Send after 1 second max
READ_TIMEOUT=5       # Fast timeout
```

### Limited Network

```bash
MAX_RETRIES=5        # More aggressive retry
RETRY_BACKOFF=3.0    # Longer wait between retries
```

## Security Considerations

1. **Run as unprivileged user** - Not required to run as root
2. **Secure API communication** - Use HTTPS for remote connections
3. **File permissions** - Restrict read access to eve.json
4. **API authentication** - Consider adding API key support if needed
5. **Log rotation** - Configure logrotate for /var/log/mayasec/forwarder.log

## Monitoring

### Check Service Status

```bash
sudo systemctl status mayasec-forwarder

# View recent logs
sudo journalctl -u mayasec-forwarder -n 50

# Live logs
sudo journalctl -u mayasec-forwarder -f
```

### Metrics to Monitor

- **Events sent** - Should increase over time
- **Events failed** - Should be minimal
- **Success rate** - Aim for >99%
- **CPU usage** - Adjust batch settings if high
- **Memory usage** - Should be stable

## Examples

### Monitor Real-Time Forwarding

```bash
# Terminal 1: Start Mayasec with API mode
export USE_LOCAL_LOGS=false
python app.py

# Terminal 2: Watch forwarder logs
python suricata_forwarder.py --log-file /tmp/forwarder.log

# Terminal 3: Monitor in real-time
tail -f /tmp/forwarder.log | grep "submitted"
```

### Test with Custom Configuration

```bash
# Create test config
cat > /tmp/test-config.json << 'EOF'
{
  "api_url": "http://localhost:8000",
  "sensor_id": "test-sensor",
  "source": "suricata-test",
  "eve_json_path": "/var/log/suricata/eve.json",
  "log_level": "DEBUG",
  "batch_size": 5,
  "batch_timeout": 3
}
EOF

# Run with test config
python suricata_forwarder.py --config /tmp/test-config.json
```

## Limitations

- Does not modify or filter events (raw forwarding)
- Single threaded (suitable for typical Suricata volumes)
- No built-in event deduplication
- Requires eve.json in JSON format (not syslog)

## Future Enhancements

Potential improvements:
- [ ] Event filtering/transformation
- [ ] Built-in metrics collection
- [ ] Multi-threaded processing
- [ ] Event deduplication
- [ ] API key authentication
- [ ] TLS certificate validation options
- [ ] Event buffering to disk
- [ ] Prometheus metrics export

