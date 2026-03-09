# Attacker Simulator - Quick Reference

## What It Does

Generates realistic attack events and sends them to MAYASEC ingestor API:
- SSH brute force (multiple failed login attempts)
- Port scanning (reconnaissance)
- Invalid login attempts (HTTP/HTTPS)
- Natural severity escalation (attacks intensify)

**Key:** No database access, no UI interaction, pure API-driven.

## Quick Start (2 minutes)

### 1. Prerequisites
```bash
# Ensure MAYASEC ingestor is running
docker-compose up -d ingestor api

# Install Python dependencies
pip install requests
```

### 2. Run Simulator
```bash
# Basic: 5 minutes, medium intensity
python attacker_simulator.py

# Or with options
python attacker_simulator.py --duration 600 --intensity high
```

### 3. Watch in SOC Console
```bash
open http://localhost:3000
# Events appear in real-time
# Timeline grows dynamically
```

## Command Examples

```bash
# Quick 2-minute test (low intensity)
python attacker_simulator.py --duration 120 --intensity low

# Standard 5-minute demo (medium intensity)
python attacker_simulator.py --duration 300 --intensity medium

# Stress test: 10 minutes high-volume
python attacker_simulator.py --duration 600 --intensity high

# Extended test: 1 hour simulation
python attacker_simulator.py --duration 3600 --intensity low

# Target specific MAYASEC instance
python attacker_simulator.py --target http://192.168.1.10:5001

# Target specific victim IP
python attacker_simulator.py --target-ip 10.0.0.5

# Everything combined
python attacker_simulator.py \
  --target http://192.168.1.10:5001 \
  --target-ip 10.0.0.5 \
  --duration 900 \
  --intensity high
```

## Docker

### Build
```bash
docker build -f Dockerfile.attacker-simulator -t mayasec-attacker-simulator .
```

### Run
```bash
# Basic (targets localhost)
docker run --network host mayasec-attacker-simulator

# With custom settings
docker run --network host \
  -e MAYASEC_INGESTOR_URL=http://192.168.1.10:5001 \
  -e ATTACKER_TARGET_IP=192.168.1.100 \
  -e DURATION=600 \
  -e INTENSITY=high \
  mayasec-attacker-simulator

# Background
docker run -d \
  --name attacker-sim \
  --network host \
  mayasec-attacker-simulator

# View logs
docker logs -f attacker-sim

# Stop
docker stop attacker-sim
```

## Environment Variables

```bash
MAYASEC_INGESTOR_URL    # Default: http://localhost:5001
ATTACKER_TARGET_IP      # Default: 192.168.1.100
ATTACKER_SOURCE_IP      # Default: 203.0.113
```

## Configuration Options

| Option | Default | Examples |
|--------|---------|----------|
| `--target` | http://localhost:5001 | http://192.168.1.10:5001 |
| `--target-ip` | 192.168.1.100 | 10.0.0.5, 172.16.0.1 |
| `--source-ip` | 203.0.113 | 203.0.113, 198.51.100 |
| `--duration` | 300 (5 min) | 60, 600, 3600, 86400 |
| `--intensity` | medium | low, medium, high |

### Intensity Levels

| Level | Events/Sec | Use Case |
|-------|-----------|----------|
| low | 0.5 | Extended testing, demo mode |
| medium | 2 | Standard demos, testing |
| high | 5 | Stress testing, volume |

## What Events Look Like

### SSH Brute Force
```json
{
  "event_type": "login_attempt",
  "timestamp": "2026-01-15T14:30:45Z",
  "source_ip": "203.0.113.42",
  "destination_ip": "192.168.1.100",
  "port": 22,
  "protocol": "SSH",
  "result": "failed",
  "severity": "HIGH",
  "detection_reason": "Failed SSH login attempt from attacker"
}
```

### Port Scan
```json
{
  "event_type": "port_scan",
  "timestamp": "2026-01-15T14:30:46Z",
  "source_ip": "203.0.113.87",
  "destination_ip": "192.168.1.100",
  "port": 22,
  "protocol": "TCP",
  "result": "open",
  "severity": "MEDIUM",
  "detection_reason": "Port scan activity detected"
}
```

### HTTP Login Attack
```json
{
  "event_type": "login_attempt",
  "timestamp": "2026-01-15T14:30:47Z",
  "source_ip": "203.0.113.156",
  "destination_ip": "192.168.1.100",
  "port": 443,
  "protocol": "HTTP",
  "http_status": 401,
  "severity": "MEDIUM",
  "detection_reason": "Invalid HTTP login attempt"
}
```

## Expected Results (5-minute run, medium intensity)

```
Total Events: ~600
Event Rate: ~2 events/second

Attack Types:
  ✅ SSH brute force: ~200 events
  ✅ Port scanning: ~150 events
  ✅ HTTP login attacks: ~150 events
  ✅ Escalation: ~100 events

In SOC Console:
  ✅ Events appear LIVE
  ✅ Timeline grows dynamically
  ✅ Severity escalates
  ✅ Correlations visible
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect to ingestor" | Run: `docker-compose up ingestor` |
| No events appear | Check ingestor URL is correct |
| Low event rate | Use `--intensity high` |
| High CPU usage | Use `--intensity low` |
| Need to stop | Press `Ctrl+C` |

## On Separate VM

```bash
# SSH to VM
ssh user@192.168.1.50

# Copy simulator
scp attacker_simulator.py user@192.168.1.50:/home/user/

# Install dependencies
pip install requests

# Run against MAYASEC at 192.168.1.100
python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --target-ip 192.168.1.100 \
  --duration 600
```

## Files Included

| File | Purpose |
|------|---------|
| `attacker_simulator.py` | Main simulator script (standalone) |
| `Dockerfile.attacker-simulator` | Docker image for easy deployment |
| `ATTACKER_SIMULATOR.md` | Full documentation |
| `ATTACKER_SIMULATOR_QUICKREF.md` | This quick reference |

## Performance Impact

- Memory: ~50MB
- CPU: 5-10% (varies by intensity)
- Network: <1 Mbps
- Database: None (API only)

## Key Features

✅ Realistic attack patterns
✅ Natural severity escalation
✅ Configurable intensity
✅ External deployment
✅ No DB access
✅ Pure API integration
✅ Zero dependency on MAYASEC internals
✅ Instant event visibility

## Summary

1. Start simulator: `python attacker_simulator.py`
2. Watch events in SOC console: `http://localhost:3000`
3. Timeline grows dynamically
4. Severity escalates naturally
5. All events via API (no DB access)

Done! The simulator runs externally and MAYASEC captures all events in real-time.
