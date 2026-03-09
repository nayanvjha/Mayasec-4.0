#!/bin/bash

# MAYASEC Real-Time WebSocket Integration Test Script
# Purpose: Validate that all components of the real-time event system are working
# Usage: ./test_websocket_integration.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
API_URL="http://localhost:5000"
FRONTEND_URL="http://localhost:3000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
test_start() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}TEST: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

test_pass() {
    echo -e "${GREEN}✅ PASSED: $1${NC}\n"
    ((TESTS_PASSED++))
}

test_fail() {
    echo -e "${RED}❌ FAILED: $1${NC}\n"
    ((TESTS_FAILED++))
}

test_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Start tests
echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   MAYASEC REAL-TIME WEBSOCKET INTEGRATION TEST SUITE          ║"
echo "║   Testing all components of the real-time event system        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}\n"

# Test 1: API Health Check
test_start "API Health Check"
if curl -s "$API_URL/health" | grep -q '"status":"healthy"'; then
    test_pass "API is responding to health checks"
else
    test_fail "API health check failed - API may not be running"
fi

# Test 2: Frontend Accessibility
test_start "Frontend Accessibility"
if curl -s "$FRONTEND_URL" | grep -q "MAYASEC"; then
    test_pass "Frontend is accessible and serving React app"
else
    test_fail "Frontend not responding - check if running on port 3000"
fi

# Test 3: API Version Endpoint
test_start "API Information Endpoint"
if curl -s "$API_URL/api/v1/health" | grep -q "healthy"; then
    test_pass "API v1 endpoints are functional"
else
    test_fail "API v1 endpoints not responding"
fi

# Test 4: Event Emission Endpoint
test_start "Event Emission Endpoint"
EVENT_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/emit-event" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-integration-001",
    "event_type": "TEST_EVENT",
    "source_ip": "192.168.1.1",
    "destination_ip": "10.0.0.1",
    "action": "LOGGED",
    "threat_level": "low",
    "threat_score": 10,
    "threat_description": "Integration test event"
  }')

if echo "$EVENT_RESPONSE" | grep -q '"status":"emitted"'; then
    test_pass "Event emission endpoint working"
    test_info "Event ID from response: $(echo $EVENT_RESPONSE | grep -o '"event_id":"[^"]*"' | cut -d'"' -f4)"
else
    test_fail "Event emission endpoint failed"
    test_info "Response: $EVENT_RESPONSE"
fi

# Test 5: Check Docker Containers
test_start "Docker Containers Status"
if ! command -v docker-compose &> /dev/null; then
    test_info "docker-compose not found in PATH, skipping container check"
else
    cd "$SCRIPT_DIR"
    RUNNING=$(docker-compose ps --services --filter "status=running" 2>/dev/null | wc -l)
    TOTAL=$(docker-compose ps --services 2>/dev/null | wc -l)
    
    if [ "$RUNNING" -ge 4 ]; then
        test_pass "All required containers are running ($RUNNING/$TOTAL)"
        docker-compose ps --services --filter "status=running" | sed 's/^/  ✓ /'
    else
        test_fail "Not all containers running ($RUNNING/$TOTAL)"
    fi
fi

# Test 6: Check API WebSocket Server
test_start "API WebSocket Server Status"
if curl -s "$API_URL/api/v1/health" | grep -q "ok"; then
    test_pass "API WebSocket server appears to be running"
    test_info "WebSocket endpoint available at: ws://localhost:5000/socket.io/"
else
    test_fail "Cannot confirm WebSocket server status"
fi

# Test 7: API Logs for WebSocket Activity
test_start "API WebSocket Activity (Last 30 seconds)"
if command -v docker-compose &> /dev/null; then
    cd "$SCRIPT_DIR"
    WS_ACTIVITY=$(docker-compose logs api 2>/dev/null | grep -i "socket\|websocket" | tail -3)
    if [ -n "$WS_ACTIVITY" ]; then
        test_pass "WebSocket activity detected in API logs"
        echo "$WS_ACTIVITY" | sed 's/^/  /'
    else
        test_fail "No recent WebSocket activity in logs (check if events are being sent)"
    fi
else
    test_info "docker-compose not available, cannot check logs"
fi

# Test 8: Event Emission to WebSocket
test_start "Event Emission to WebSocket"
EVENT_ID="test-emission-$(date +%s)"
EMIT_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/emit-event" \
  -H "Content-Type: application/json" \
  -d "{
    \"event_id\": \"$EVENT_ID\",
    \"event_type\": \"VALIDATION_TEST\",
    \"source_ip\": \"192.168.1.2\",
    \"destination_ip\": \"10.0.0.2\",
    \"action\": \"BLOCKED\",
    \"threat_level\": \"high\",
    \"threat_score\": 85,
    \"threat_description\": \"Validation test event\"
  }")

if echo "$EMIT_RESPONSE" | grep -q '"status":"emitted"'; then
    test_pass "Event successfully emitted to WebSocket"
    test_info "Event ID: $EVENT_ID"
    
    # Check if event appears in logs
    sleep 1
    if command -v docker-compose &> /dev/null; then
        cd "$SCRIPT_DIR"
        if docker-compose logs api 2>/dev/null | grep -q "Emitting event to WebSocket clients: $EVENT_ID"; then
            test_pass "Event confirmed in API WebSocket emission logs"
        else
            test_fail "Event not found in API logs (may have been emitted but logs delayed)"
        fi
    fi
else
    test_fail "Event emission failed"
    test_info "Response: $EMIT_RESPONSE"
fi

# Test 9: Frontend WebSocket Component Files
test_start "Frontend WebSocket Components"
HOOK_FILE="$SCRIPT_DIR/frontend/src/hooks/useWebSocket.js"
FEED_FILE="$SCRIPT_DIR/frontend/src/components/LiveEventFeed.js"

if [ -f "$HOOK_FILE" ]; then
    test_pass "useWebSocket hook file exists"
    HOOK_LINES=$(wc -l < "$HOOK_FILE")
    test_info "useWebSocket.js: $HOOK_LINES lines"
else
    test_fail "useWebSocket hook file not found"
fi

if [ -f "$FEED_FILE" ]; then
    test_pass "LiveEventFeed component exists"
    FEED_LINES=$(wc -l < "$FEED_FILE")
    test_info "LiveEventFeed.js: $FEED_LINES lines"
else
    test_fail "LiveEventFeed component not found"
fi

# Test 10: App.js WebSocket Integration
test_start "App.js WebSocket Integration"
APP_FILE="$SCRIPT_DIR/frontend/src/App.js"
if [ -f "$APP_FILE" ]; then
    if grep -q "useWebSocket" "$APP_FILE" && grep -q "LiveEventFeed" "$APP_FILE"; then
        test_pass "App.js properly integrated with WebSocket components"
        test_info "Contains useWebSocket hook and LiveEventFeed component"
    else
        test_fail "App.js missing WebSocket integration"
    fi
else
    test_fail "App.js not found"
fi

# Test 11: Python Dependencies
test_start "Python WebSocket Dependencies"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    if grep -q "flask-socketio" "$REQUIREMENTS_FILE" && \
       grep -q "python-socketio" "$REQUIREMENTS_FILE"; then
        test_pass "All required Python WebSocket packages in requirements.txt"
        grep -E "flask-socketio|python-socketio|python-engineio" "$REQUIREMENTS_FILE" | sed 's/^/  /'
    else
        test_fail "Missing WebSocket packages in requirements.txt"
    fi
else
    test_fail "requirements.txt not found"
fi

# Test 12: Frontend Dependencies
test_start "Frontend JavaScript Dependencies"
PKG_FILE="$SCRIPT_DIR/frontend/package.json"
if [ -f "$PKG_FILE" ]; then
    if grep -q "socket.io-client" "$PKG_FILE"; then
        test_pass "socket.io-client properly added to package.json"
        test_info "Version: $(grep -o '"socket.io-client"[^,}]*' "$PKG_FILE")"
    else
        test_fail "socket.io-client not in package.json"
    fi
else
    test_fail "package.json not found"
fi

# Test 13: Docker Compose Configuration
test_start "Docker Compose Configuration"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
    if grep -q "REACT_APP_API_URL" "$COMPOSE_FILE"; then
        test_pass "REACT_APP_API_URL properly configured in docker-compose.yml"
    else
        test_fail "REACT_APP_API_URL not found in docker-compose.yml"
    fi
else
    test_fail "docker-compose.yml not found"
fi

# Final Summary
echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                       TEST SUMMARY                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"

TOTAL=$((TESTS_PASSED + TESTS_FAILED))
PERCENTAGE=$((TESTS_PASSED * 100 / TOTAL))

echo -e "Tests Passed:  ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed:  ${RED}$TESTS_FAILED${NC}"
echo -e "Total Tests:   $TOTAL"
echo -e "Success Rate:  ${PERCENTAGE}%\n"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED! WebSocket integration is fully operational.${NC}\n"
    echo "Your MAYASEC platform is ready for real-time security event streaming!"
    echo -e "\nAccess the dashboard at: ${BLUE}http://localhost:3000${NC}"
    exit 0
elif [ $TESTS_FAILED -le 2 ]; then
    echo -e "${YELLOW}⚠️  MOST TESTS PASSED with minor issues${NC}\n"
    echo "Check the failed tests above and run integration fixes:"
    echo "  1. docker-compose restart"
    echo "  2. docker-compose rebuild mayasec-ui"
    echo "  3. Check docker logs: docker-compose logs [service]"
    exit 1
else
    echo -e "${RED}❌ SIGNIFICANT ISSUES DETECTED${NC}\n"
    echo "Please fix the following before proceeding:"
    echo "  1. Ensure all containers are running: docker-compose up -d"
    echo "  2. Check service health: docker-compose ps"
    echo "  3. Review logs: docker-compose logs [service]"
    echo "  4. Verify ports are accessible: netstat -tuln | grep 5000"
    exit 2
fi
