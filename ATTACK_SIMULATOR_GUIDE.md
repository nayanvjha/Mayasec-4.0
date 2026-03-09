# MAYASEC External Attack Simulator

**Purpose**: Simulate realistic attack traffic from external sources to demonstrate MAYASEC's real-time detection and dashboard capabilities.

**Status**: ✅ Ready to Use  
**Python Version**: 3.7+  
**Dependencies**: requests (only)  

---

## 📋 Overview

The Attack Simulator generates realistic security events and sends them to MAYASEC via the API integration endpoint. It runs completely independently without database access or UI interaction.

### Key Features
- ✅ Realistic attack scenarios (SSH brute force, port scanning, DDoS, etc.)
- ✅ Runs on any machine with Python 3.7+
- ✅ Configurable attack types, intensity, and duration
- ✅ Real-time event delivery via API
- ✅ Severity escalation and attack pattern recognition
- ✅ Docker support for isolated execution
- ✅ Comprehensive logging and reporting

---

## 🚀 Quick Start

### Option 1: Run Locally (Python)

```bash
# Install dependency
pip install requests

# Run SSH brute force attack
python3 attack_simulator.py --target http://localhost:5000

# Run port scanning attack
python3 attack_simulator.py --target http://localhost:5000 --scenario port-scan

# Run escalating attack (60 seconds with 4 phases)
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 60

# Run DDoS attack
python3 attack_simulator.py --target http://localhost:5000 --scenario ddos
```

### Option 2: Run in Docker

```bash
# Build Docker image
docker build -f Dockerfile.attacker -t mayasec-attacker .

# Run simulation
docker run --rm mayasec-attacker \
  --target http://host.docker.internal:5000 \
  --scenario escalating

# Or from remote machine
docker run --rm mayasec-attacker \
  --target http://192.168.1.100:5000 \
  --scenario ssh-brute
```

### Option 3: Run from Remote Machine

```bash
# From any machine on the network
python3 attack_simulator.py \
  --target http://192.168.1.100:5000 \
  --scenario port-scan \
  --intensity 10
```

---

## 🎯 Attack Scenarios

### 1. SSH Brute Force (`ssh-brute`)
**Description**: Simulates multiple failed SSH login attempts on port 22

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario ssh-brute --intensity 10
```

**Events Generated**:
- Multiple SSH_BRUTE_FORCE events
- Threat scores: 85-100 (high to critical)
- Shows escalating attempt count
- User credential stuffing pattern

**Expected Dashboard Behavior**:
- Red threat level badges
- High threat scores (85+)
- Multiple events from same source IP
- Pattern indicates "multiple_failed_logins"

---

### 2. Port Scanning (`port-scan`)
**Description**: Simulates network reconnaissance with port scanning

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario port-scan --intensity 15
```

**Events Generated**:
- Multiple PORT_SCANNING events
- Threat scores: 50-85 (medium to high)
- Scans common service ports (22, 3306, 5432, 3389, 27017, etc.)
- Shows "network_reconnaissance" pattern

**Expected Dashboard Behavior**:
- Orange/yellow threat level badges
- Medium-high threat scores
- Sequential port numbers in events
- Detected "network reconnaissance" attack pattern

---

### 3. Invalid Authentication (`invalid-auth`)
**Description**: Mixed invalid authentication attempts on various services

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario invalid-auth --intensity 5
```

**Events Generated**:
- INVALID_AUTHENTICATION events
- Services: HTTP, FTP, SMTP, RDP (random)
- Threat scores: 65-95
- Shows "credential_stuffing" pattern

**Expected Dashboard Behavior**:
- Medium-high threat indicators
- Multiple failed authentication events
- Different service types targeted
- Escalating severity with each attempt

---

### 4. DDoS Attack (`ddos`)
**Description**: Distributed denial-of-service traffic from multiple sources

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario ddos --intensity 30
```

**Events Generated**:
- DDOS_ATTACK events (rapid fire)
- Multiple source IPs attacking single target
- Threat scores escalate: 70 → 100 (high → critical)
- Shows "distributed_denial_of_service" pattern
- Includes bandwidth metrics

**Expected Dashboard Behavior**:
- Rapid event generation (high volume)
- Red critical threat badges
- Multiple source IPs visible
- Very high threat scores (90-100)
- High bandwidth metrics

---

### 5. Malware Detection (`malware`)
**Description**: Progressive malware infection sequence

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario malware
```

**Events Generated** (in sequence):
1. SUSPICIOUS_FILE_ACCESS (threat_score: 78)
   - Reconnaissance phase
   
2. SUSPICIOUS_PROCESS (threat_score: 92)
   - Privilege escalation attempt
   
3. MALWARE_DETECTED (threat_score: 98)
   - Known malware signature match

**Expected Dashboard Behavior**:
- Escalating threat levels (high → critical)
- Specific malware signatures identified
- Shows entire attack lifecycle
- Action escalates from BLOCKED → QUARANTINE

---

### 6. Escalating Attack (default) (`escalating`)
**Description**: Multi-phase attack that escalates over time (recommended for demo)

```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 120
```

**Attack Phases**:
1. **Phase 1 (0-25%)**: Initial Reconnaissance
   - Port scanning to identify services
   - Threat level: Medium (50-60)

2. **Phase 2 (25-50%)**: Brute Force Attempts
   - SSH login attempts with credential stuffing
   - Threat level: High (80-90)

3. **Phase 3 (50-75%)**: Exploitation
   - Invalid authentication across multiple services
   - Threat level: High (75-95)

4. **Phase 4 (75-100%)**: Critical Attack
   - DDoS-style attack from multiple sources
   - Threat level: Critical (95-100)

**Expected Dashboard Behavior**:
- Real-time threat escalation
- Clear attack phases visible in timeline
- Threat scores continuously rising
- Multiple attack types in sequence
- Connection status indicator shows "Live"
- Event feed updates every 0.2-1 second
- Color coding changes from yellow → orange → red

---

## 📊 Command-Line Options

```
usage: attack_simulator.py [-h] --target TARGET 
                          [--scenario {ssh-brute,port-scan,invalid-auth,ddos,malware,escalating}]
                          [--duration DURATION]
                          [--intensity INTENSITY]
                          [--source-ip SOURCE_IP]
                          [--repeat REPEAT]

Options:
  --target TARGET
    MAYASEC API endpoint (required)
    Format: http://IP:5000 or http://hostname:5000
    Examples:
      - http://localhost:5000
      - http://192.168.1.100:5000
      - http://mayasec-server.local:5000

  --scenario {ssh-brute,port-scan,invalid-auth,ddos,malware,escalating}
    Attack scenario to simulate (default: escalating)

  --duration DURATION
    Duration in seconds for escalating scenario (default: 60)
    Examples:
      --duration 30    (30 second attack)
      --duration 300   (5 minute attack)

  --intensity INTENSITY
    Attack intensity/count (default: 5)
    For ssh-brute: number of login attempts
    For port-scan: number of ports to scan
    For invalid-auth: number of attempts
    For ddos: number of packets to send

  --source-ip SOURCE_IP
    Source IP for attacks (default: random)
    Example: --source-ip 203.0.113.42

  --repeat REPEAT
    Number of times to repeat scenario (default: 1)
    Example: --repeat 3
```

---

## 💡 Usage Examples

### Example 1: Quick Demo (Escalating Attack)
```bash
# 60-second escalating attack (best for demo)
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 60
```
**Result**: Watch dashboard in real-time as attack escalates through 4 phases

### Example 2: SSH Brute Force (Repeated)
```bash
# Run 5 separate SSH brute force attacks with 5 attempts each
python3 attack_simulator.py \
  --target http://192.168.1.100:5000 \
  --scenario ssh-brute \
  --intensity 5 \
  --repeat 5
```
**Result**: 25 total SSH events showing repeated attack attempts

### Example 3: Remote Attack Simulation
```bash
# From attacker machine
python3 attack_simulator.py \
  --target http://10.0.0.100:5000 \
  --scenario port-scan \
  --intensity 20 \
  --source-ip 203.0.113.42
```
**Result**: Port scan attack from specific external IP

### Example 4: High-Intensity DDoS
```bash
# Intense DDoS traffic (50 packets from multiple sources)
python3 attack_simulator.py \
  --target http://localhost:5000 \
  --scenario ddos \
  --intensity 50
```
**Result**: Critical threat level, demonstrates high-volume attack detection

### Example 5: Continuous Testing (Docker)
```bash
# Run in Docker, continuous escalating attacks
docker run -it --rm mayasec-attacker \
  --target http://host.docker.internal:5000 \
  --scenario escalating \
  --duration 120 \
  --repeat 3
```
**Result**: 3 consecutive 2-minute escalating attacks

---

## 🔍 Expected Dashboard Behavior

### Real-Time Event Feed
When running attack simulator, the MAYASEC dashboard should show:

1. **Live Connection Indicator** (top right of LiveEventFeed)
   - 🟢 Green pulse = WebSocket connected
   - 🔴 Red flash = Disconnected

2. **Event Count** (bottom of feed)
   - Updates in real-time
   - Shows total events received

3. **Event Items** (in feed)
   - Appear within 100ms of emission
   - Color-coded by threat level
   - Display: Type, Source IP, Threat Level, Score
   - Animate with slide-in effect

4. **Threat Level Escalation**
   - Escalating scenario: colors change yellow → orange → red
   - Scores visible: 50 → 60 → 80 → 90 → 100

### Example Dashboard Timeline (60-second escalating attack)

```
Time (sec)  Phase                    Threat Level     Events
─────────────────────────────────────────────────────────────
0-15        Reconnaissance           Medium (yellow)   5-8 events
15-30       Brute Force             High (orange)     6-10 events
30-45       Exploitation            High (orange)     6-10 events
45-60       Critical                Critical (red)    15-20 events

Total Events: 32-48 over 60 seconds
Threat Scores: 50 → 100 (escalating)
Updates: Every 200-500ms
```

---

## 🔧 Configuration & Customization

### Attack Source IPs (Attacker Simulation)
Edit `COMMON_IPS` in `attack_simulator.py`:
```python
COMMON_IPS = [
    "203.0.113.42",    # Attacker IP 1
    "198.51.100.15",   # Attacker IP 2
    ...
]
```

### Target IPs (Victim Simulation)
Edit `TARGET_HOSTS` in `attack_simulator.py`:
```python
TARGET_HOSTS = [
    "192.168.1.100",
    "192.168.1.101",
    ...
]
```

### Attack Ports
Edit `ATTACK_PORTS` in `attack_simulator.py`:
```python
ATTACK_PORTS = [22, 23, 3306, 5432, 3389, 27017, 6379, 5000, 8080, 9200]
```

### Threat Score Ranges
Modify threat score calculations in each scenario method.

---

## 📋 Sample Event Payloads

### SSH Brute Force Event
```json
{
  "event_id": "ssh-brute-001",
  "event_type": "SSH_BRUTE_FORCE",
  "source_ip": "203.0.113.42",
  "destination_ip": "192.168.1.100",
  "port": 22,
  "action": "BLOCKED",
  "threat_level": "high",
  "threat_score": 87,
  "threat_description": "SSH login attempt with user 'admin' (attempt 3/5)",
  "attack_pattern": "multiple_failed_logins",
  "additional_data": {
    "username": "admin",
    "attempt_number": 3,
    "total_attempts": 5
  }
}
```

### Port Scanning Event
```json
{
  "event_id": "port-scan-001",
  "event_type": "PORT_SCANNING",
  "source_ip": "198.51.100.15",
  "destination_ip": "10.0.0.1",
  "port": 3306,
  "action": "BLOCKED",
  "threat_level": "medium",
  "threat_score": 65,
  "threat_description": "Port scan detected on port 3306 (2/10)",
  "attack_pattern": "network_reconnaissance",
  "additional_data": {
    "scanned_port": 3306,
    "ports_scanned": 2,
    "total_ports": 10
  }
}
```

### DDoS Attack Event
```json
{
  "event_id": "ddos-001",
  "event_type": "DDOS_ATTACK",
  "source_ip": "192.0.2.87",
  "destination_ip": "192.168.1.100",
  "action": "BLOCKED",
  "threat_level": "critical",
  "threat_score": 95,
  "threat_description": "DDoS traffic detected from 192.0.2.87",
  "attack_pattern": "distributed_denial_of_service",
  "additional_data": {
    "packet_count": 18,
    "source_count": 5,
    "bandwidth_mbps": 180
  }
}
```

---

## ✅ Verification Steps

### 1. Check API Connectivity
```bash
curl http://localhost:5000/health
# Should return: {"status":"healthy",...}
```

### 2. Run Quick Test
```bash
python3 attack_simulator.py --target http://localhost:5000 --scenario port-scan --intensity 3
```

### 3. View Dashboard
```
Open: http://localhost:3000
Look for: LiveEventFeed component with incoming events
```

### 4. Check Logs
```bash
# Simulator logs
tail -f attack_simulator.log

# API logs
docker-compose logs api | grep "Emitting event"
```

---

## 🐛 Troubleshooting

### Issue: "Cannot connect to API"
**Solution**: 
- Verify target URL: `curl http://target:5000/health`
- Check firewall rules on MAYASEC server
- Ensure API is running: `docker-compose ps`
- Try from MAYASEC machine first: `--target http://localhost:5000`

### Issue: "No events appearing in dashboard"
**Solution**:
- Check WebSocket connection: Browser DevTools → Network → WS
- Verify REACT_APP_API_URL matches API host
- Check frontend logs: `docker-compose logs mayasec-ui`
- Refresh dashboard page

### Issue: "Events stuck in queue"
**Solution**:
- Restart containers: `docker-compose restart`
- Check API logs: `docker-compose logs api | tail -50`
- Verify database connection: `docker-compose logs core`

### Issue: "Slow event delivery"
**Solution**:
- Reduce attack intensity: `--intensity 3`
- Increase event delay (edit simulator code)
- Check network latency: `ping target-ip`
- Monitor API CPU: `docker stats`

---

## 📊 Performance Tuning

### For Rapid Events (Load Testing)
```bash
# Decrease delays in attack_simulator.py
# Change: time.sleep(0.5) → time.sleep(0.1)
python3 attack_simulator.py --target http://localhost:5000 --scenario ddos --intensity 100
```

### For Realistic Timing
```bash
# Use default delays
# Standard: 0.2-1 second between events
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating
```

### For Dashboard Demo
```bash
# Optimal settings for visual demonstration
python3 attack_simulator.py \
  --target http://localhost:5000 \
  --scenario escalating \
  --duration 60
```

---

## 🔐 Security Notes

- **Non-Destructive**: Simulator only generates events; doesn't actually attack targets
- **Network-Safe**: Only sends HTTP requests to API; no network layer attacks
- **No Credentials**: Doesn't use real credentials or authentication
- **No Database Access**: Purely API-based interaction
- **Configurable Delays**: Can be slowed down for safe testing
- **Isolated Execution**: Can run on separate machine/container

---

## 📝 Logging

### Simulator Logs
Saved to: `attack_simulator.log`
```
2026-01-15 10:30:45 [INFO] Testing API connection...
2026-01-15 10:30:45 [INFO] ✓ API connection successful!
2026-01-15 10:30:46 [INFO] ✓ Event sent: SSH_BRUTE_FORCE (threat_score: 85)
2026-01-15 10:30:47 [INFO] ✓ Event sent: SSH_BRUTE_FORCE (threat_score: 87)
...
2026-01-15 10:31:45 [INFO] ✓ Simulation complete!
2026-01-15 10:31:45 [INFO]   Total events sent: 48
```

### Real-Time Monitoring
```bash
# Monitor incoming events on MAYASEC
docker-compose logs api -f | grep "Emitting event"

# Watch simulator
tail -f attack_simulator.log
```

---

## 🎯 Demo Scenarios

### Scenario 1: "10-Minute Security Briefing"
```bash
# 3 different attacks, 2 minutes each
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 120 --repeat 3
```

### Scenario 2: "Real-Time Detection Demo"
```bash
# Start simulator, then show dashboard live-updating
# Terminal 1: python3 attack_simulator.py --target http://localhost:5000 --scenario port-scan --intensity 20
# Terminal 2: Open http://localhost:3000 and watch events appear
```

### Scenario 3: "Threat Escalation Demo"
```bash
# Shows how MAYASEC detects escalating attacks
python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 180
```

### Scenario 4: "Multi-Attack Scenario"
```bash
# Run 4 different attacks sequentially
for scenario in ssh-brute port-scan invalid-auth ddos; do
  python3 attack_simulator.py --target http://localhost:5000 --scenario $scenario --intensity 5
  echo "Waiting 10 seconds..."
  sleep 10
done
```

---

## 📚 Integration with CI/CD

### Automated Testing
```bash
#!/bin/bash
# test-mayasec.sh

# Start MAYASEC
docker-compose up -d

# Wait for startup
sleep 10

# Run attack simulation (5 minute test)
python3 attack_simulator.py \
  --target http://localhost:5000 \
  --scenario escalating \
  --duration 300

# Check for events
if curl -s http://localhost:3000 | grep -q "LiveEventFeed"; then
  echo "✓ MAYASEC test passed"
  exit 0
else
  echo "✗ MAYASEC test failed"
  exit 1
fi
```

---

## 📞 Support

### Quick Help
```bash
python3 attack_simulator.py --help
```

### Check Configuration
```bash
# Edit these sections in attack_simulator.py
# COMMON_IPS - Attacker source IPs
# TARGET_HOSTS - Victim target IPs
# ATTACK_PORTS - Ports to scan
```

### Report Issues
Simulator provides detailed logs in `attack_simulator.log`

---

## ✨ Summary

The Attack Simulator provides a realistic, safe way to:
- ✅ Demonstrate MAYASEC's real-time capabilities
- ✅ Test event detection and escalation
- ✅ Show dashboard live-updating
- ✅ Run security awareness demonstrations
- ✅ Validate WebSocket performance
- ✅ Load-test the system

**Best For**:
- Product demos and presentations
- Training and security awareness
- System testing and validation
- Performance benchmarking
- Customer POCs

---

**Version**: 1.0  
**Last Updated**: January 15, 2026  
**Status**: Production Ready
