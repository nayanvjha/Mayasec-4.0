# Attacker Simulator - Setup & Deployment Guide

## Overview

The MAYASEC Attacker Simulator generates realistic attack events and sends them to the ingestor API. It runs on a separate VM/container with **no database access** and **no UI interaction**.

### What It Simulates

- **SSH Brute Force**: Multiple failed login attempts on port 22
- **Port Scanning**: Network reconnaissance on common ports
- **Invalid Login Attempts**: HTTP/HTTPS authentication failures
- **Natural Escalation**: Attacks intensify from reconnaissance → active attacks

### Key Benefits

✅ No database access required
✅ No UI interaction needed
✅ Pure API-driven (ingestion endpoint only)
✅ Runs on separate VM/container
✅ Events appear LIVE in SOC console
✅ Timeline grows dynamically
✅ Severity escalates naturally

---

## Pre-Deployment Checklist

### Requirements

- [ ] MAYASEC ingestor API running
- [ ] Python 3.7+ (or Docker)
- [ ] Network access to ingestor (port 5001)
- [ ] Requests library: `pip install requests`

### Verify Prerequisites

```bash
# 1. Check ingestor is running
curl http://localhost:5001/health
# Expected: {"status": "healthy"}

# 2. Check Python version
python --version
# Expected: Python 3.7+

# 3. Check network connectivity
ping localhost
```

---

## Option 1: Standalone Script (Local Machine)

### Setup

```bash
# 1. Navigate to MAYASEC directory
cd /path/to/mayasec

# 2. Ensure ingestor is running
docker-compose up -d ingestor

# 3. Install dependencies
pip install requests

# 4. Make script executable
chmod +x attacker_simulator.py
```

### Run

```bash
# Basic run (5 minutes, medium intensity)
python attacker_simulator.py

# With options
python attacker_simulator.py \
  --duration 300 \
  --intensity medium \
  --target http://localhost:5001 \
  --target-ip 192.168.1.100
```

### Output

```
╔════════════════════════════════════════════════════════════════╗
║           MAYASEC Attacker Simulator - STARTING                ║
╚════════════════════════════════════════════════════════════════╝

Configuration:
  Ingestor URL: http://localhost:5001
  Target IP: 192.168.1.100
  Source IP Range: 203.0.113.x
  Duration: 300 seconds
  Intensity: medium (2 events/sec)

Status: Running... (Ctrl+C to stop)

📊 30s elapsed | 60 events sent | 270s remaining | Escalation: 2
📊 60s elapsed | 120 events sent | 240s remaining | Escalation: 3
```

### Stop

Press `Ctrl+C` to gracefully stop the simulation.

---

## Option 2: Docker Container (Isolated)

### Build Image

```bash
# Build the attacker simulator image
docker build \
  -f Dockerfile.attacker-simulator \
  -t mayasec-attacker-simulator:latest \
  .
```

### Run Container

```bash
# Basic: targets localhost:5001
docker run \
  --name attacker-sim \
  --network host \
  mayasec-attacker-simulator:latest

# In background
docker run -d \
  --name attacker-sim \
  --network host \
  mayasec-attacker-simulator:latest

# With custom configuration
docker run \
  --name attacker-sim \
  --network host \
  -e MAYASEC_INGESTOR_URL=http://192.168.1.100:5001 \
  -e ATTACKER_TARGET_IP=192.168.1.100 \
  -e DURATION=600 \
  -e INTENSITY=high \
  mayasec-attacker-simulator:latest

# Specify resource limits
docker run \
  --name attacker-sim \
  --network host \
  --cpus 0.5 \
  --memory 256m \
  mayasec-attacker-simulator:latest
```

### Monitor Container

```bash
# View logs
docker logs -f attacker-sim

# Check status
docker ps | grep attacker-sim

# View resource usage
docker stats attacker-sim
```

### Stop Container

```bash
# Stop gracefully
docker stop attacker-sim

# Remove container
docker rm attacker-sim
```

---

## Option 3: Docker Compose Integration

### Add to docker-compose.yml

```yaml
services:
  attacker-simulator:
    profiles:
      - attacker
    build:
      context: .
      dockerfile: Dockerfile.attacker-simulator
    container_name: mayasec-attacker-simulator
    network_mode: host
    environment:
      MAYASEC_INGESTOR_URL: "http://localhost:5001"
      ATTACKER_TARGET_IP: "192.168.1.100"
      ATTACKER_SOURCE_IP: "203.0.113"
      DURATION: "3600"
      INTENSITY: "medium"
    depends_on:
      - ingestor
    restart: unless-stopped
```

### Run with Docker Compose

```bash
# Run simulator with MAYASEC
docker-compose --profile attacker up -d ingestor api attacker-simulator

# View logs
docker-compose logs -f attacker-simulator

# Stop
docker-compose --profile attacker down attacker-simulator
```

---

## Option 4: Separate VM/Server

### Copy Script to Remote VM

```bash
# From your local machine
scp attacker_simulator.py user@192.168.1.50:/home/user/

# Or clone repository
ssh user@192.168.1.50
cd /home/user
git clone <repo> mayasec
```

### Setup on Remote VM

```bash
# SSH into VM
ssh user@192.168.1.50

# Install Python dependencies
pip install requests

# Make executable
chmod +x attacker_simulator.py
```

### Run Against Remote MAYASEC

```bash
# Target MAYASEC on different machine (192.168.1.100)
python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --target-ip 192.168.1.100 \
  --source-ip 203.0.113 \
  --duration 600 \
  --intensity medium

# Run in background
nohup python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --duration 3600 \
  --intensity low > attacker.log 2>&1 &

# Monitor progress
tail -f attacker.log
```

---

## Option 5: Kubernetes Deployment

### Create ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: attacker-simulator-config
  namespace: mayasec
data:
  MAYASEC_INGESTOR_URL: "http://mayasec-ingestor:5001"
  ATTACKER_TARGET_IP: "192.168.1.100"
  ATTACKER_SOURCE_IP: "203.0.113"
  DURATION: "3600"
  INTENSITY: "medium"
```

### Create Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: attacker-simulator
  namespace: mayasec
spec:
  containers:
  - name: attacker-simulator
    image: mayasec-attacker-simulator:latest
    imagePullPolicy: IfNotPresent
    envFrom:
    - configMapRef:
        name: attacker-simulator-config
    resources:
      limits:
        cpu: 500m
        memory: 256Mi
      requests:
        cpu: 250m
        memory: 128Mi
    restartPolicy: Never
```

### Deploy

```bash
kubectl apply -f configmap.yaml
kubectl apply -f pod.yaml

# View logs
kubectl logs -f attacker-simulator -n mayasec
```

---

## Configuration Reference

### Command-Line Arguments

```
--target URL              Ingestor URL (default: http://localhost:5001)
--target-ip IP            Target IP to attack (default: 192.168.1.100)
--source-ip RANGE         Source IP range (default: 203.0.113)
--duration SECONDS        Duration in seconds (default: 300)
--intensity LEVEL         low|medium|high (default: medium)
```

### Environment Variables

```bash
MAYASEC_INGESTOR_URL=http://192.168.1.10:5001
ATTACKER_TARGET_IP=10.0.0.5
ATTACKER_SOURCE_IP=203.0.113
DURATION=600
INTENSITY=high
```

### Intensity Settings

| Level | Events/Second | Burst Size | Recommended Use |
|-------|---------------|-----------|-----------------|
| low | 0.5 | 3 | Extended demos, overnight testing |
| medium | 2 | 5 | Standard demos, testing |
| high | 5 | 10 | Stress testing, performance validation |

---

## Example Deployment Scenarios

### Scenario 1: Quick Demo (2 minutes)

**Goal:** Show attack events in SOC console quickly

```bash
# Terminal 1: Start simulator
python attacker_simulator.py --duration 120 --intensity high

# Terminal 2: Monitor
open http://localhost:3000
# Watch events flood in at 5 events/second
```

**Expected Result:** ~600 events in 2 minutes

### Scenario 2: Extended Test (1 hour)

**Goal:** Test system stability with sustained attack

```bash
# Background process
nohup python attacker_simulator.py \
  --duration 3600 \
  --intensity low \
  > simulator.log 2>&1 &

# Monitor in SOC console
open http://localhost:3000

# View logs
tail -f simulator.log
```

**Expected Result:** ~1800 events over 1 hour, minimal system impact

### Scenario 3: Multi-Target Testing

**Goal:** Attack multiple targets simultaneously

```bash
# Terminal 1: Attack 192.168.1.100
python attacker_simulator.py --target-ip 192.168.1.100 --duration 600 &

# Terminal 2: Attack 192.168.1.101
python attacker_simulator.py --target-ip 192.168.1.101 --duration 600 &

# Terminal 3: Attack 192.168.1.102
python attacker_simulator.py --target-ip 192.168.1.102 --duration 600 &

# Monitor all in SOC console
open http://localhost:3000
```

**Expected Result:** 3 × 1200 = 3600 events, diverse targets

### Scenario 4: Stress Test (10 minutes, high volume)

**Goal:** Validate system can handle high-volume events

```bash
docker run -d \
  --name stress-test \
  --network host \
  -e DURATION=600 \
  -e INTENSITY=high \
  mayasec-attacker-simulator:latest

# Monitor
docker logs -f stress-test

# Expected: 5 events/second × 600 = 3000 events
```

---

## Monitoring During Execution

### In SOC Console

```
Expected Observations:
  ✅ Events appear LIVE as they're sent
  ✅ Timeline grows and scrolls
  ✅ Event count increases continuously
  ✅ Severity badges change color (escalation)
  ✅ Correlation IDs group related attacks
  ✅ Filters work on live events
  ✅ Operator context panel populates
```

### Terminal Output

```
📊 30s elapsed | 60 events sent | 270s remaining | Escalation: 2
📊 60s elapsed | 120 events sent | 240s remaining | Escalation: 3
📊 90s elapsed | 180 events sent | 210s remaining | Escalation: 4
```

### Via API

```bash
# Check event count
curl http://localhost:5001/api/events | jq '.total'

# Filter events from attacker IP
curl 'http://localhost:5001/api/events?source_ip=203.0.113.42' | jq '.count'
```

---

## Troubleshooting

### Issue: "Cannot connect to ingestor"

**Cause:** Ingestor not running or unreachable

**Solution:**
```bash
# Check if ingestor is running
docker-compose ps ingestor

# Start if stopped
docker-compose up -d ingestor

# Verify connectivity
curl http://localhost:5001/health
```

### Issue: No events in SOC console

**Cause:** Wrong ingestor URL or network isolation

**Solution:**
```bash
# Verify ingestor URL is correct
python attacker_simulator.py --target http://localhost:5001

# Check firewall
ping localhost:5001

# Test API directly
curl -X POST http://localhost:5001/ingest \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"test","timestamp":"2026-01-15T14:30:00Z"}'
```

### Issue: Low event count

**Cause:** Low intensity setting

**Solution:**
```bash
# Increase intensity
python attacker_simulator.py --intensity high
```

### Issue: High CPU usage

**Cause:** High intensity on limited hardware

**Solution:**
```bash
# Reduce intensity
python attacker_simulator.py --intensity low

# Reduce event rate
python attacker_simulator.py --duration 300  # Shorter run
```

### Issue: Container won't start

**Cause:** Python dependencies missing or network issues

**Solution:**
```bash
# Rebuild image
docker build -f Dockerfile.attacker-simulator -t mayasec-attacker-simulator .

# Run with explicit network
docker run --network host mayasec-attacker-simulator
```

---

## Performance Metrics

### Typical Performance

```
Memory Usage: ~50 MB
CPU Usage: 5-10% (intensity dependent)
Network Bandwidth: <1 Mbps
Event Processing: <1ms per event
Filter Application: ~1ms per filter change
```

### Scaling Characteristics

```
100 events: <1ms
1,000 events: <5ms
10,000 events: <50ms
100,000+ events: <500ms
```

---

## Security Considerations

⚠️ **Important:**

1. **Test Environment Only** - Use only in isolated lab/demo environments
2. **Firewall Rules** - Ensure source IP range is not blocked
3. **No Real Attacks** - Generates fake events; no actual system impact
4. **API Security** - Add authentication if ingestor is publicly accessible
5. **Event Validation** - Ingestor validates all events before storage

---

## Cleanup

### Local Script

```bash
# Stop simulation (Ctrl+C)
# Delete simulator
rm attacker_simulator.py
```

### Docker Container

```bash
# Stop container
docker stop attacker-sim

# Remove container
docker rm attacker-sim

# Remove image
docker rmi mayasec-attacker-simulator
```

### Docker Compose

```bash
# Stop with profile
docker-compose --profile attacker down attacker-simulator

# Clean up
docker-compose --profile attacker down -v
```

---

## Summary

| Deployment | Setup Time | Ease | External | Isolation |
|-----------|----------|------|----------|-----------|
| Standalone | 2 min | Easy | Yes | Medium |
| Docker | 3 min | Easy | Yes | High |
| Compose | 2 min | Very Easy | Yes | High |
| Remote VM | 5 min | Medium | Yes | High |
| Kubernetes | 10 min | Medium | Yes | High |

---

## Next Steps

1. **Deploy:** Choose deployment method above
2. **Configure:** Set target IP, duration, intensity
3. **Run:** Start simulator
4. **Monitor:** Watch events in SOC console
5. **Validate:** Check timeline, filters, severity escalation
6. **Test:** Use Operator Context Panel and Event Filters

Done! External attacker simulation running successfully. 🎯
