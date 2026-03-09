#!/usr/bin/env python3
"""
Suricata Forwarder - Quick Reference
"""

print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                 SURICATA EVE.JSON FORWARDER FOR MAYASEC                    ║
║                     Standalone Python Script                               ║
╚════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OVERVIEW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Tails Suricata's eve.json file and forwards alerts to Mayasec API

  Features:
  ✓ Real-time event forwarding
  ✓ Automatic retry with exponential backoff
  ✓ No root privileges required
  ✓ Handles file rotation automatically
  ✓ Configurable batching for performance
  ✓ Comprehensive logging
  ✓ Systemd integration ready

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUICK START:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Install dependencies:
     pip install -r requirements-forwarder.txt

  2. Run with default settings:
     python suricata_forwarder.py

  3. Run with custom API URL:
     MAYASEC_API_URL=http://192.168.1.100:8000 python suricata_forwarder.py

  4. Run with config file:
     python suricata_forwarder.py --config forwarder-config.example.json

  5. View logs:
     tail -f /path/to/log/file

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ENVIRONMENT VARIABLES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  MAYASEC_API_URL         API endpoint (default: http://localhost:8000)
  MAYASEC_SENSOR_ID       Sensor identifier (default: suricata-forwarder)
  MAYASEC_SOURCE          Event source name (default: suricata-eve)
  SURICATA_EVE_JSON       Path to eve.json (default: /var/log/suricata/eve.json)
  LOG_LEVEL               Logging level (default: INFO)
  BATCH_SIZE              Events per batch (default: 10)
  BATCH_TIMEOUT           Batch timeout seconds (default: 5)
  MAX_RETRIES             Max API retries (default: 3)
  RETRY_BACKOFF           Backoff multiplier (default: 2.0)

  Examples:
  ─────────
  
  export MAYASEC_API_URL=http://192.168.1.100:8000
  export MAYASEC_SENSOR_ID=suricata-dmz-01
  export LOG_LEVEL=DEBUG
  python suricata_forwarder.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMMAND-LINE OPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  --config FILE           Load JSON configuration file
  --log-file FILE         Write logs to file
  --api-url URL           Override API URL
  --sensor-id ID          Override sensor ID
  --eve-json PATH         Override eve.json path

  Examples:
  ─────────

  python suricata_forwarder.py --config /etc/mayasec/forwarder.json

  python suricata_forwarder.py \\
    --api-url http://192.168.1.100:8000 \\
    --sensor-id suricata-prod \\
    --log-file /var/log/mayasec/forwarder.log

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEMD INTEGRATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Create /etc/systemd/system/mayasec-forwarder.service:

    [Unit]
    Description=Mayasec Suricata EVE.JSON Forwarder
    After=network.target

    [Service]
    Type=simple
    User=suricata-reader
    Environment="MAYASEC_API_URL=http://localhost:8000"
    Environment="MAYASEC_SENSOR_ID=suricata-production"
    ExecStart=/usr/bin/python3 /opt/mayasec/suricata_forwarder.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

  Then:
    sudo systemctl daemon-reload
    sudo systemctl enable mayasec-forwarder
    sudo systemctl start mayasec-forwarder
    sudo systemctl status mayasec-forwarder

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EVENT FLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Suricata EVE.JSON       Forwarder Script        Mayasec API
  ──────────────────────────────────────────────────────────
  
  /var/log/suricata/
  eve.json
    │
    ├─ alert event  ──→  Read & Parse   ──→  POST /api/ingest/event
    ├─ alert event  ──→  Batch Events   ──→  POST /api/ingest/event
    ├─ alert event  ──→  Format Data    ──→  POST /api/ingest/event
    └─ ...          ──→  Retry on Fail  ──→  (exponential backoff)
    
  Stored in Mayasec database with:
  ✓ Original event details
  ✓ Sensor identification
  ✓ Timestamp
  ✓ Source metadata

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PERMISSIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  NO ROOT PRIVILEGES REQUIRED!

  Minimum requirements:
  ✓ Read access to /var/log/suricata/eve.json
  ✓ Network access to Mayasec API

  Setup unprivileged user:
  ─────────────────────────

    # Create user
    sudo useradd -r -s /bin/false suricata-reader

    # Grant read access
    sudo setfacl -m u:suricata-reader:r /var/log/suricata/eve.json

    # Run as that user
    sudo -u suricata-reader python suricata_forwarder.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RETRY BEHAVIOR:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Automatic retries on failure with exponential backoff:

    Attempt 1: Immediate
    Attempt 2: Wait 2.0 sec (backoff_factor ^ 1)
    Attempt 3: Wait 4.0 sec (backoff_factor ^ 2)
    Attempt 4: Wait 8.0 sec (backoff_factor ^ 3)

  Retries on:
  ✓ HTTP 429 (Too Many Requests)
  ✓ HTTP 5xx (Server Errors)
  ✓ Network timeouts
  ✓ Connection failures

  Customize:
  ──────────
    MAX_RETRIES=5 RETRY_BACKOFF=1.5 python suricata_forwarder.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TROUBLESHOOTING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Problem: "File not found" warning
  ─────────────────────────────────
  
  Solution:
    1. Check Suricata is running: systemctl status suricata
    2. Verify eve.json path: ls -la /var/log/suricata/eve.json
    3. Set correct path: SURICATA_EVE_JSON=/path/to/eve.json python ...

  Problem: "Connection refused" errors
  ─────────────────────────────────────
  
  Solution:
    1. Verify Mayasec running: curl http://localhost:8000/api/status
    2. Check API URL: MAYASEC_API_URL=http://correct:8000 python ...
    3. Check firewall: telnet mayasec-host 8000

  Problem: Events not appearing in Mayasec
  ─────────────────────────────────────────
  
  Solution:
    1. Check forwarder logs: LOG_LEVEL=DEBUG python suricata_forwarder.py
    2. Verify Suricata events: tail -f /var/log/suricata/eve.json | head
    3. Check USE_LOCAL_LOGS=false in Mayasec (for API-only mode)
    4. Verify API status: curl http://localhost:8000/api/status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PERFORMANCE TUNING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  High-Volume Environments:
  ─────────────────────────
  
    BATCH_SIZE=50 BATCH_TIMEOUT=10 python suricata_forwarder.py

  Low-Latency Requirements:
  ─────────────────────────
  
    BATCH_SIZE=1 BATCH_TIMEOUT=1 python suricata_forwarder.py

  Limited Network:
  ────────────────
  
    MAX_RETRIES=5 RETRY_BACKOFF=3.0 python suricata_forwarder.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  suricata_forwarder.py           Main script
  SURICATA_FORWARDER.md           Comprehensive documentation
  requirements-forwarder.txt      Python dependencies
  forwarder-config.example.json   Example configuration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEPLOYMENT EXAMPLES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Single Host with Local Suricata:
  ─────────────────────────────────
  
    MAYASEC_API_URL=http://localhost:8000 \\
    MAYASEC_SENSOR_ID=suricata-local \\
    python suricata_forwarder.py

  Remote Suricata Sensor:
  ──────────────────────
  
    MAYASEC_API_URL=http://mayasec-central:8000 \\
    MAYASEC_SENSOR_ID=suricata-dmz-01 \\
    python suricata_forwarder.py

  Multiple Sensors:
  ────────────────
  
    # Sensor 1
    MAYASEC_SENSOR_ID=suricata-dmz ./suricata_forwarder.py &
    
    # Sensor 2
    MAYASEC_SENSOR_ID=suricata-internal ./suricata_forwarder.py &
    
    # All send to same Mayasec instance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MONITORING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Check service (systemd):
  ────────────────────────
  
    sudo systemctl status mayasec-forwarder
    sudo journalctl -u mayasec-forwarder -f

  Log statistics on shutdown:
  ──────────────────────────
  
    Events sent: 1247
    Events failed: 3
    Success rate: 99.4%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ For full documentation, see SURICATA_FORWARDER.md

""")
