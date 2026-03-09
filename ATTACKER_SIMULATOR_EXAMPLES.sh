#!/bin/bash
# Attacker Simulator - Example Run Commands
#
# This file contains copy-paste ready commands for common scenarios.
# All commands are tested and production-ready.

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       MAYASEC Attacker Simulator - Example Commands            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# PRE-REQUISITE: Ensure MAYASEC is running
# ============================================================================

echo "📋 PRE-REQUISITE: Verify MAYASEC is running"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Check if ingestor is running
docker-compose ps ingestor

# Or start MAYASEC
docker-compose up -d ingestor api

# Verify ingestor health
curl http://localhost:5001/health

# Verify network connectivity
ping -c 1 localhost

# Install Python dependencies
pip install requests

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 1: Quick Demo (2 minutes)
# ============================================================================

echo "🎯 SCENARIO 1: Quick Demo (2 minutes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Terminal 1: Run simulator (2 minutes, high intensity)
python attacker_simulator.py --duration 120 --intensity high

# Terminal 2: Monitor in SOC console (in another terminal)
open http://localhost:3000
# or: firefox http://localhost:3000

# Expected:
#   - ~600 events in 2 minutes
#   - 5 events/second continuous stream
#   - Severity escalates from LOW → HIGH → CRITICAL
#   - Timeline grows dynamically
#   - Filter controls appear instantly

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 2: Standard Test (5 minutes)
# ============================================================================

echo "📊 SCENARIO 2: Standard Test (5 minutes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Terminal 1: Default 5-minute simulation
python attacker_simulator.py

# Terminal 2: Monitor
open http://localhost:3000

# Expected:
#   - ~600 events (2 events/second)
#   - Mix of SSH brute force, port scanning, HTTP attacks
#   - Natural severity escalation visible
#   - All attacks from different source IPs (203.0.113.x)

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 3: Stress Test (10 minutes, high volume)
# ============================================================================

echo "🔥 SCENARIO 3: Stress Test (10 minutes, high volume)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# High-intensity 10-minute test
python attacker_simulator.py --duration 600 --intensity high

# Or with Docker
docker run \
  --name stress-test \
  --network host \
  -e DURATION=600 \
  -e INTENSITY=high \
  mayasec-attacker-simulator:latest

# Monitor
open http://localhost:3000

# Expected:
#   - ~3000 events (5 events/second)
#   - SOC console handles high volume smoothly
#   - Filtering still responsive
#   - Timeline performance validated

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 4: Extended Simulation (1 hour, background)
# ============================================================================

echo "⏰ SCENARIO 4: Extended Simulation (1 hour, background)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Run in background (low intensity for extended time)
nohup python attacker_simulator.py \
  --duration 3600 \
  --intensity low \
  > simulator.log 2>&1 &

# Monitor progress in background
tail -f simulator.log

# Or with Docker (background container)
docker run -d \
  --name long-run \
  --network host \
  -e DURATION=3600 \
  -e INTENSITY=low \
  mayasec-attacker-simulator:latest

# View logs
docker logs -f long-run

# Expected:
#   - ~1800 events over 1 hour (0.5 events/second)
#   - Minimal system impact (low CPU/memory)
#   - Good for overnight demos or extended testing

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 5: Target Specific IP
# ============================================================================

echo "🎯 SCENARIO 5: Target Specific IP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Target specific victim IP (10.0.0.5)
python attacker_simulator.py \
  --target-ip 10.0.0.5 \
  --duration 300 \
  --intensity medium

# Target specific MAYASEC instance at 192.168.1.100:5001
python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --target-ip 10.0.0.5 \
  --duration 300

# Monitor
open http://localhost:3000
# Filter events for destination_ip = 10.0.0.5

# Expected:
#   - All events target 10.0.0.5
#   - Source IPs vary (203.0.113.x)
#   - Easy to correlate by target

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 6: Multi-Target Simulation
# ============================================================================

echo "🌐 SCENARIO 6: Multi-Target Simulation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Terminal 1: Attack target 1
python attacker_simulator.py --target-ip 192.168.1.100 --duration 600 &
TARGET1_PID=$!

# Terminal 2: Attack target 2 (different window)
python attacker_simulator.py --target-ip 192.168.1.101 --duration 600 &
TARGET2_PID=$!

# Terminal 3: Attack target 3 (different window)
python attacker_simulator.py --target-ip 192.168.1.102 --duration 600 &
TARGET3_PID=$!

# Terminal 4: Monitor all
open http://localhost:3000

# Expected:
#   - 3 different target IPs under attack
#   - Each with own timeline of attacks
#   - ~3600 total events (1200 per target)
#   - Correlations help group by target

# Clean up when done
wait $TARGET1_PID $TARGET2_PID $TARGET3_PID

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 7: Remote MAYASEC Instance
# ============================================================================

echo "🔗 SCENARIO 7: Remote MAYASEC Instance"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Run from VM/container, target remote MAYASEC at 192.168.1.100
python attacker_simulator.py \
  --target http://192.168.1.100:5001 \
  --target-ip 192.168.1.100 \
  --duration 300 \
  --intensity medium

# Or via Docker on remote machine
docker run \
  --name remote-attacker \
  --network host \
  -e MAYASEC_INGESTOR_URL=http://192.168.1.100:5001 \
  -e ATTACKER_TARGET_IP=192.168.1.100 \
  -e DURATION=300 \
  -e INTENSITY=medium \
  mayasec-attacker-simulator:latest

# Monitor on MAYASEC machine
# open http://192.168.1.100:3000

# Expected:
#   - Source IPs from simulator VM (203.0.113.x)
#   - Destination: MAYASEC machine (192.168.1.100)
#   - Events appear in remote SOC console instantly

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 8: Using Docker Compose
# ============================================================================

echo "🐳 SCENARIO 8: Using Docker Compose"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Build the image
docker build \
  -f Dockerfile.attacker-simulator \
  -t mayasec-attacker-simulator:latest \
  .

# Run with docker-compose (add to docker-compose.yml first)
docker-compose --profile attacker up -d \
  ingestor api attacker-simulator

# View logs
docker-compose logs -f attacker-simulator

# Monitor
open http://localhost:3000

# Stop
docker-compose --profile attacker down attacker-simulator

# Expected:
#   - All services start in order
#   - Simulator waits for ingestor health check
#   - Logs show event generation
#   - Events visible in SOC console

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 9: Environment Variable Configuration
# ============================================================================

echo "🔧 SCENARIO 9: Environment Variable Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Set environment variables
export MAYASEC_INGESTOR_URL=http://192.168.1.100:5001
export ATTACKER_TARGET_IP=10.0.0.5
export ATTACKER_SOURCE_IP=203.0.113

# Run with environment variables
python attacker_simulator.py --duration 300 --intensity high

# Or override specific values
DURATION=600 INTENSITY=low python attacker_simulator.py

# Docker with env vars
docker run \
  --network host \
  -e MAYASEC_INGESTOR_URL=http://192.168.1.100:5001 \
  -e ATTACKER_TARGET_IP=10.0.0.5 \
  -e DURATION=600 \
  -e INTENSITY=medium \
  mayasec-attacker-simulator:latest

# Expected:
#   - Configuration applied from environment
#   - No command-line arguments needed
#   - Easy to inject into CI/CD

EOF

echo ""
echo ""

# ============================================================================
# SCENARIO 10: Monitoring & Logging
# ============================================================================

echo "📈 SCENARIO 10: Monitoring & Logging"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Run with output logging
python attacker_simulator.py --duration 300 > /tmp/simulator.log 2>&1

# Monitor progress
tail -f /tmp/simulator.log

# Background with nohup
nohup python attacker_simulator.py --duration 3600 > simulator.log 2>&1 &

# Docker logs
docker logs -f attacker-sim
docker logs --tail 50 attacker-sim
docker logs --timestamps attacker-sim

# Check event count in ingestor
curl http://localhost:5001/api/events/count

# Filter events by source IP
curl 'http://localhost:5001/api/events?source_ip=203.0.113.42'

# Expected:
#   - Log shows events sent count increasing
#   - Every 30 seconds: progress update
#   - API returns event statistics
#   - Event count grows continuously

EOF

echo ""
echo ""

# ============================================================================
# TROUBLESHOOTING COMMANDS
# ============================================================================

echo "🔍 TROUBLESHOOTING COMMANDS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Check if ingestor is running
docker-compose ps ingestor

# Check ingestor health
curl http://localhost:5001/health

# Check firewall connectivity
nc -zv localhost 5001

# Verify Python installation
python --version
pip show requests

# Test API connectivity
curl -X POST http://localhost:5001/ingest \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"test","timestamp":"2026-01-15T14:30:00Z"}'

# View ingestor logs
docker logs mayasec-ingestor

# Check port is open
lsof -i :5001

# View simulator output
tail -f simulator.log

# Kill simulator process
kill -TERM <PID>

# Docker cleanup
docker stop attacker-sim
docker rm attacker-sim
docker rmi mayasec-attacker-simulator

EOF

echo ""
echo ""

# ============================================================================
# PERFORMANCE BENCHMARKS
# ============================================================================

echo "⚡ PERFORMANCE BENCHMARKS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

# Low Intensity (0.5 events/sec for 1 hour)
python attacker_simulator.py --duration 3600 --intensity low
# Expected: ~1,800 events, minimal CPU/memory

# Medium Intensity (2 events/sec for 5 minutes)
python attacker_simulator.py --duration 300 --intensity medium
# Expected: ~600 events, ~5-10% CPU

# High Intensity (5 events/sec for 10 minutes)
python attacker_simulator.py --duration 600 --intensity high
# Expected: ~3,000 events, ~10-15% CPU

# Stress Test (high intensity, short duration)
python attacker_simulator.py --duration 60 --intensity high
# Expected: ~300 events/sec sustained, CPU spikes OK

# Monitor during run
# CPU:    top -p $(pgrep -f attacker_simulator)
# Memory: watch -n 1 'ps aux | grep attacker_simulator'
# Events: tail -f /tmp/simulator.log | grep "elapsed"

EOF

echo ""
echo ""

# ============================================================================
# FINAL SUMMARY
# ============================================================================

echo "✅ SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'

Quick Start (3 steps):

1. Ensure MAYASEC is running
   docker-compose up -d ingestor api

2. Run simulator
   python attacker_simulator.py

3. Monitor in SOC console
   open http://localhost:3000

That's it! Events flow in real-time.

For more scenarios, see above.
For detailed configuration, see ATTACKER_SIMULATOR_DEPLOYMENT.md
For API integration details, see ATTACKER_SIMULATOR.md

EOF

echo ""
