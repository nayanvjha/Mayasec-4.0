# External Attacker Simulator for MAYASEC

Simulate realistic attack patterns and send events to MAYASEC via the ingestion API. Runs on a separate VM/container with NO database access or UI interaction.

## Overview

The Attacker Simulator generates three types of attack events:

1. **SSH Brute Force**: Multiple failed login attempts on SSH (port 22)
2. **Port Scanning**: Reconnaissance scanning of multiple ports
3. **Invalid Login Attempts**: HTTP/HTTPS authentication failures
4. **Natural Escalation**: Attacks evolve from reconnaissance → enumeration → aggressive attacks

All events are sent to the MAYASEC ingestor API and appear LIVE in the SOC console.

## Features

✅ **No Database Access** - Uses ingestion API only
✅ **No UI Interaction** - Fully programmatic  
✅ **Realistic Attack Patterns** - Natural escalation and timing
✅ **Live Event Generation** - Events appear immediately in SOC console
✅ **Dynamic Timeline** - Timeline grows as events arrive
✅ **Severity Escalation** - Attacks intensify over time
✅ **Configurable** - Target IP, intensity, duration, etc.
✅ **External Deployment** - Runs on separate VM/container

## Quick Start

### 1. Prerequisites

```bash
# Ensure MAYASEC is running
docker-compose up -d ingestor api

# Verify ingestor is accessible
curl http://localhost:5001/health
# Expected: {"status": "healthy"}
```

### 2. Install Dependencies

```bash
pip install requests
# Or use requirements file (see below)
```

### 3. Run the Simulator

**Basic (5-minute simulation, medium intensity):**
```bash
python attacker_simulator.py
```

**Custom Configuration:**
```bash
# 10-minute simulation with high intensity
python attacker_simulator.py --duration 600 --intensity high

# Target specific MAYASEC instance
python attacker_simulator.py --target http://192.168.1.10:5001

# Target specific IP with low intensity
python attacker_simulator.py --target-ip 10.0.0.5 --intensity low

# Long-running simulation (1 hour)
python attacker_simulator.py --duration 3600 --intensity low
```

### 4. Monitor in SOC Console

While simulator runs, events appear LIVE:

```bash
# Open SOC console in browser
open http://localhost:3000

# Watch events appear in real-time
# Timeline grows dynamically
# Severity escalates naturally
```

## Configuration Options

### Command-Line Arguments

```
--target URL              MAYASEC ingestor URL (default: http://localhost:5001)
--target-ip IP            Target IP to attack (default: 192.168.1.100)
--source-ip RANGE         Source IP range (default: 203.0.113)
--duration SECONDS        Duration in seconds (default: 300 = 5 minutes)
--intensity LEVEL         low|medium|high (default: medium)
```

### Intensity Levels

| Level | Events/Sec | Burst Size | Use Case |
|-------|-----------|-----------|----------|
| **low** | 0.5 | 3 | Long-running demos, demo mode |
| **medium** | 2 | 5 | Default testing (recommended) |
| **high** | 5 | 10 | Stress testing, volume testing |

### Environment Variables

```bash
# Override defaults via environment
export MAYASEC_INGESTOR_URL=http://192.168.1.10:5001
export ATTACKER_TARGET_IP=10.0.0.5
export ATTACKER_SOURCE_IP=203.0.113

python attacker_simulator.py
```

## Attack Types

### 1. SSH Brute Force

Simulates repeated SSH login attempts from attacker IP:

```
Event Type: login_attempt
Protocol: SSH (port 22)
Characteristics:
  - 5-20 attempts per attack
  - Random username/password pairs
  - Escalates severity with attempt count
  - Realistic timing (0.1-0.5s between attempts)
  - Grouped by source IP (correlation)
```

**Example Event:**
```json
{
  "event_type": "login_attempt",
  "timestamp": "2026-01-15T14:30:45.123Z",
  "source_ip": "203.0.113.42",
  "destination_ip": "192.168.1.100",
  "port": 22,
  "protocol": "SSH",
  "username": "admin",
  "password": "password",
  "result": "failed",
  "attempt_number": 1,
  "total_attempts": 15,
  "severity": "MEDIUM",
  "detection_reason": "Failed SSH login attempt 1 of 15 from 203.0.113.42",
  "severity_reasoning": "Multiple SSH brute force attempts (15 total). Pattern indicates automated attack.",
  "correlation_explanation": "Brute force sequence: 15 attempts from single source in short timeframe"
}
```

### 2. Port Scanning

Simulates network reconnaissance on multiple ports:

```
Event Type: port_scan
Protocol: TCP
Characteristics:
  - 3-10 ports per scan
  - Scans common service ports
  - Low-medium severity (reconnaissance)
  - Rapid timing (0.05-0.2s between ports)
  - Indicates attacker reconnaissance
```

**Example Event:**
```json
{
  "event_type": "port_scan",
  "timestamp": "2026-01-15T14:30:46.234Z",
  "source_ip": "203.0.113.87",
  "destination_ip": "192.168.1.100",
  "port": 22,
  "protocol": "TCP",
  "scan_type": "syn_scan",
  "result": "open",
  "severity": "LOW",
  "detection_reason": "Suspicious port scan activity detected on port 22",
  "severity_reasoning": "Port scanning from external source 203.0.113.87. Indicates reconnaissance activity.",
  "correlation_explanation": "Port scan sequence from 203.0.113.87: scanning multiple ports in rapid succession"
}
```

### 3. Invalid Login Attempts

Simulates HTTP/HTTPS authentication failures:

```
Event Type: login_attempt
Protocol: HTTP
Characteristics:
  - 3-10 attempts per attack
  - HTTP status 401 (Unauthorized)
  - Ports: 80, 443, 8080, 8443
  - Medium-high severity
  - Indicates credential stuffing
```

**Example Event:**
```json
{
  "event_type": "login_attempt",
  "timestamp": "2026-01-15T14:30:47.345Z",
  "source_ip": "203.0.113.156",
  "destination_ip": "192.168.1.100",
  "port": 443,
  "protocol": "HTTP",
  "username": "root",
  "password": "123456",
  "result": "failed",
  "attempt_number": 1,
  "total_attempts": 8,
  "http_status": 401,
  "severity": "MEDIUM",
  "detection_reason": "Invalid HTTP authentication attempt 1 from 203.0.113.156",
  "severity_reasoning": "Multiple invalid login attempts via HTTP. Indicates credential stuffing or brute force attempt.",
  "correlation_explanation": "HTTP login attack: 8 failed authentication attempts from single source"
}
```

## Running on Separate VM/Container

### Option 1: Docker Container

**Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Copy simulator script
COPY attacker_simulator.py .

# Install dependencies
RUN pip install requests

# Default: run against MAYASEC ingestor on host
CMD ["python", "attacker_simulator.py", \
     "--target", "http://mayasec-ingestor:5001", \
     "--duration", "3600", \
     "--intensity", "medium"]
```

**Build and run:**
```bash
# Build image
docker build -t mayasec-attacker-simulator .

# Run container (targets ingestor on host network)
docker run -d \
  --name attacker-sim \
  --network host \
  -e MAYASEC_INGESTOR_URL=http://localhost:5001 \
  mayasec-attacker-simulator

# View logs
docker logs -f attacker-sim

# Stop simulator
docker stop attacker-sim
```

### Option 2: Separate VM

**Setup on different machine (e.g., 192.168.1.50):**

```bash
# SSH into VM
ssh user@192.168.1.50

# Clone or copy attacker_simulator.py
scp attacker_simulator.py user@192.168.1.50:/home/user/

# Install dependencies
pip install requests

# Run against MAYASEC on 192.168.1.100:5001
python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --target-ip 192.168.1.100 \
  --duration 600 \
  --intensity high
```

### Option 3: Docker Compose Integration

**Add to docker-compose.yml:**
```yaml
attacker-simulator:
  build: .
  environment:
    - MAYASEC_INGESTOR_URL=http://ingestor:5001
    - ATTACKER_TARGET_IP=192.168.1.100
    - ATTACKER_SOURCE_IP=203.0.113
  networks:
    - mayasec
  depends_on:
    - ingestor
  profiles:
    - demo  # Run with: docker-compose --profile demo up
```

**Run:**
```bash
docker-compose --profile demo up attacker-simulator
```

## Expected Behavior

### In SOC Console

**Before Starting Simulator:**
- Event stream is empty or showing historical events
- Timeline is static

**During Simulation:**
1. **Immediate (0-10s):** First events appear
   - Port scan events (LOW/MEDIUM severity)
   - Initial SSH attempts visible

2. **Escalation (10-30s):** Attack pattern intensifies
   - SSH brute force attempts increase
   - Severity escalates to HIGH
   - Multiple sources may be visible

3. **Peak Activity (30s+):** Full attack simulation
   - Events arriving continuously
   - Timeline grows dynamically
   - Correlations group related events
   - Severity badges show escalation

### Expected Statistics (5-minute run, medium intensity)

```
Duration: 300 seconds
Event Rate: 2 events/second (medium intensity)
Expected Total Events: 600 events

Attack Breakdown:
  - SSH brute force: ~200 events (HIGH/CRITICAL)
  - Port scanning: ~150 events (LOW/MEDIUM)
  - Invalid HTTP logins: ~150 events (MEDIUM/HIGH)
  - Escalation phases: ~100 events (varies)

Severity Distribution:
  - INFO: 5%
  - LOW: 25%
  - MEDIUM: 40%
  - HIGH: 25%
  - CRITICAL: 5%
```

## Monitoring and Debugging

### Check Connection

```bash
# Verify ingestor is running
curl http://localhost:5001/health

# Expected response
{"status": "healthy"}
```

### View Ingestion Logs

```bash
# Docker logs
docker logs mayasec-ingestor

# Watch ingestor receive events
docker logs -f mayasec-ingestor | grep "Ingested event"
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot connect to ingestor" | Ensure `docker-compose up ingestor` is running |
| No events in console | Check ingestor URL is correct; verify firewall rules |
| Events not correlating | Ensure correlation_id generation is enabled in ingestor |
| Low event count | Increase intensity: `--intensity high` |
| High CPU usage | Reduce intensity: `--intensity low` |

## API Integration Details

### Ingestion Endpoint

```
POST /ingest
Content-Type: application/json

Request Body: Event JSON
Response: 200/201 OK

Example:
curl -X POST http://localhost:5001/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "event_type": "login_attempt",
    "timestamp": "2026-01-15T14:30:45Z",
    "source_ip": "203.0.113.42",
    "destination_ip": "192.168.1.100",
    ...
  }'
```

### Event Schema

All events conform to MAYASEC event schema:

```json
{
  "event_type": "string",           // login_attempt, port_scan, etc.
  "timestamp": "ISO8601",           // UTC timestamp
  "source_ip": "string",            // Attacker IP
  "destination_ip": "string",       // Target IP
  "port": "number",                 // Port number
  "protocol": "string",             // SSH, HTTP, TCP, etc.
  "result": "string",               // failed, open, closed, etc.
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",  // Escalating
  "detection_reason": "string",     // Human-readable reason
  "severity_reasoning": "string",   // Why this severity
  "correlation_explanation": "string"  // How to group events
}
```

## Example Workflows

### 1. Quick Demo (5 minutes)

```bash
# Terminal 1: Start simulator (medium intensity)
python attacker_simulator.py --duration 300 --intensity medium

# Terminal 2: Monitor
# Open http://localhost:3000 in browser
# Watch events flow in real-time
# Timeline grows, severity escalates
```

### 2. Extended Testing (1 hour, low intensity)

```bash
# Run overnight with minimal performance impact
python attacker_simulator.py \
  --duration 3600 \
  --intensity low

# Monitor overnight activity in SOC console
```

### 3. Stress Testing (10 minutes, high intensity)

```bash
# Test high-volume event handling
python attacker_simulator.py \
  --duration 600 \
  --intensity high

# Monitor performance: timeline responsiveness, filtering speed
```

### 4. Multi-Target Simulation

```bash
# Run multiple simulators against different targets
python attacker_simulator.py --target-ip 192.168.1.100 --duration 600 &
python attacker_simulator.py --target-ip 192.168.1.101 --duration 600 &
python attacker_simulator.py --target-ip 192.168.1.102 --duration 600 &

# All events correlate in SOC console
```

## Code Architecture

### Class: AttackerSimulator

**Initialization:**
```python
simulator = AttackerSimulator(
    ingestor_url='http://localhost:5001',
    target_ip='192.168.1.100',
    source_ip_range='203.0.113',
    duration_seconds=300,
    intensity='medium'
)
```

**Methods:**
- `run()` - Start the simulation
- `simulate_ssh_brute_force()` - Generate SSH attacks
- `simulate_port_scanning()` - Generate port scans
- `simulate_invalid_login_attempts()` - Generate HTTP attacks
- `simulate_escalation()` - Progress through attack phases
- `_send_event(event)` - Send event to ingestor
- `_validate_connection()` - Verify ingestor connectivity

**Event Generation:**
- Random attacker IPs from source range
- Realistic timing and patterns
- Natural severity escalation
- Correlation data for grouping

## Performance Notes

- **Memory:** ~50MB (minimal)
- **CPU:** 5-10% (depends on intensity)
- **Network:** <1 Mbps (JSON over HTTP)
- **Database:** No impact (API only)

## Security Considerations

⚠️ **Important:**

1. **TEST ENVIRONMENT ONLY** - Use only in isolated lab/demo environments
2. **Firewall Rules** - Ensure source IP range (203.0.113.x) is not blocked
3. **No Real Attacks** - Generates fake events; does not actually attack systems
4. **API Credentials** - Add authentication if ingestor is publicly accessible
5. **Event Validation** - Ingestor validates all events before storage

## Customization

### Add Custom Attack Type

```python
def simulate_custom_attack(self) -> None:
    """Custom attack type."""
    event = {
        'event_type': 'custom_event',
        'timestamp': self._get_current_timestamp(),
        'source_ip': self._generate_random_ip(),
        'destination_ip': self.target_ip,
        'severity': 'HIGH',
        'detection_reason': 'Custom attack detected',
        'severity_reasoning': 'Custom attack reason',
        'correlation_explanation': 'Custom correlation',
    }
    self._send_event(event)
```

### Modify Attack Patterns

Edit `COMMON_USERNAMES`, `WORDLIST`, `COMMON_PORTS` to customize attack parameters.

## Summary

The External Attacker Simulator provides:

✅ **No Database Access** - Pure API-driven
✅ **Realistic Attack Patterns** - SSH, port scanning, HTTP
✅ **Live Event Generation** - Events appear immediately
✅ **Dynamic Escalation** - Severity increases naturally
✅ **Configurable** - Duration, intensity, targets
✅ **External Deployment** - Separate VM/container
✅ **Production-Ready** - Fully functional simulator

Use for demos, testing, training, and validation of MAYASEC SOC console capabilities.
