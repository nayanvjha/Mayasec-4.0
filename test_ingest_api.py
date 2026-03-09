#!/usr/bin/env python3
"""
Test script for POST /api/ingest/event endpoint
"""

import json
import requests

# Test the endpoint (adjust host/port as needed)
BASE_URL = "http://localhost:8000"

# Test 1: Valid login event
print("Test 1: Valid login event ingestion")
payload = {
    "source": "web-login",
    "sensor_id": "sensor-001",
    "timestamp": "2026-01-15T10:30:00Z",
    "data": {
        "event_type": "login",
        "ip_address": "192.168.1.100",
        "username": "admin",
        "action": "LOGIN_ATTEMPT",
        "threat_level": "LOW",
        "reason": "Normal login attempt"
    }
}

try:
    response = requests.post(
        f"{BASE_URL}/api/ingest/event",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
except Exception as e:
    print(f"Error: {e}\n")


# Test 2: Network alert event
print("Test 2: Network alert event ingestion")
payload = {
    "source": "suricata",
    "sensor_id": "sensor-002",
    "timestamp": "2026-01-15T10:35:00Z",
    "data": {
        "event_type": "network_alert",
        "src_ip": "10.0.0.5",
        "dest_ip": "8.8.8.8",
        "src_port": 54321,
        "dest_port": 443,
        "proto": "TCP",
        "alert": {
            "signature": "ET POLICY Suspicious DNS over HTTPS",
            "severity_name": "HIGH"
        }
    }
}

try:
    response = requests.post(
        f"{BASE_URL}/api/ingest/event",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
except Exception as e:
    print(f"Error: {e}\n")


# Test 3: Missing required field (should fail)
print("Test 3: Missing required field (should fail with 400)")
payload = {
    "source": "test",
    "sensor_id": "sensor-003",
    "timestamp": "2026-01-15T10:40:00Z"
    # Missing 'data' field
}

try:
    response = requests.post(
        f"{BASE_URL}/api/ingest/event",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
except Exception as e:
    print(f"Error: {e}\n")


# Test 4: Invalid Content-Type (should fail)
print("Test 4: Invalid Content-Type (should fail with 400)")
try:
    response = requests.post(
        f"{BASE_URL}/api/ingest/event",
        data="not json",
        headers={"Content-Type": "text/plain"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
except Exception as e:
    print(f"Error: {e}\n")


# Test 5: Honeypot event
print("Test 5: Honeypot interaction event")
payload = {
    "source": "honeypot",
    "sensor_id": "honeypot-001",
    "timestamp": "2026-01-15T10:45:00Z",
    "data": {
        "event_type": "honeypot",
        "ip_address": "203.0.113.50",
        "username": "attacker",
        "password": "password123",
        "user_agent": "Mozilla/5.0 (Badbot)"
    }
}

try:
    response = requests.post(
        f"{BASE_URL}/api/ingest/event",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
except Exception as e:
    print(f"Error: {e}\n")

print("All tests completed!")
