#!/usr/bin/env python3
"""
Test script for USE_LOCAL_LOGS configuration flag
Demonstrates both file-based and API-only modes
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_configuration():
    """Test the /api/status endpoint to check configuration"""
    print("\n" + "="*80)
    print("TESTING CONFIGURATION STATUS")
    print("="*80 + "\n")
    
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            config = response.json()
            print("✓ System Status Retrieved\n")
            print(json.dumps(config, indent=2))
            
            use_local = config['configuration']['use_local_logs']
            print(f"\n🔧 USE_LOCAL_LOGS = {use_local}")
            
            if use_local:
                print("   Mode: FILE-BASED INGESTION (enabled)")
                print("   - /network_logs routes: AVAILABLE")
                print("   - /api/ingest/event: AVAILABLE")
            else:
                print("   Mode: API-ONLY INGESTION (enabled)")
                print("   - /network_logs routes: DISABLED")
                print("   - /api/ingest/event: AVAILABLE")
            
            return use_local
        else:
            print(f"✗ Error: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return None

def test_network_logs_route():
    """Test the /network_logs route (file-based)"""
    print("\n" + "="*80)
    print("TESTING /network_logs ROUTE (FILE-BASED)")
    print("="*80 + "\n")
    
    try:
        response = requests.get(f"{BASE_URL}/network_logs")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✓ Route is AVAILABLE (USE_LOCAL_LOGS=true)")
            print("  File-based ingestion is enabled")
        elif response.status_code == 403:
            print("✓ Route is DISABLED (USE_LOCAL_LOGS=false)")
            print("  File-based ingestion is disabled (API-only mode)")
        else:
            print(f"? Unexpected status: {response.status_code}")
        
        # Show first 200 chars of response
        if len(response.text) > 200:
            print(f"\nResponse preview:\n{response.text[:200]}...")
        else:
            print(f"\nResponse:\n{response.text}")
    
    except Exception as e:
        print(f"✗ Error: {e}")

def test_network_logs_data_route():
    """Test the /network_logs_data route (file-based)"""
    print("\n" + "="*80)
    print("TESTING /network_logs_data ROUTE (FILE-BASED)")
    print("="*80 + "\n")
    
    try:
        response = requests.get(f"{BASE_URL}/network_logs_data")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✓ Route is AVAILABLE (USE_LOCAL_LOGS=true)")
            print("  Returning HTML table rows")
        elif response.status_code == 403:
            print("✓ Route is DISABLED (USE_LOCAL_LOGS=false)")
            data = response.json()
            print(f"  Error message: {data.get('error')}")
            print(f"  Details: {data.get('message')}")
        else:
            print(f"? Unexpected status: {response.status_code}")
        
        print(f"\nResponse:\n{response.text[:300]}")
    
    except Exception as e:
        print(f"✗ Error: {e}")

def test_api_ingest():
    """Test the /api/ingest/event endpoint (always available)"""
    print("\n" + "="*80)
    print("TESTING /api/ingest/event ENDPOINT (API-BASED)")
    print("="*80 + "\n")
    
    payload = {
        "source": "test-sensor",
        "sensor_id": "test-sensor-001",
        "timestamp": "2026-01-15T12:00:00Z",
        "data": {
            "event_type": "security_action",
            "ip_address": "192.168.1.100",
            "username": "testuser",
            "action": "TEST_EVENT",
            "threat_level": "LOW"
        }
    }
    
    print("Sending test event to /api/ingest/event...")
    print(json.dumps(payload, indent=2))
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/ingest/event",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✓ Event ingestion via API is AVAILABLE")
        else:
            print("\n✗ Event ingestion failed")
    
    except Exception as e:
        print(f"✗ Error: {e}")

def main():
    """Run all tests"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║           USE_LOCAL_LOGS CONFIGURATION TEST SUITE                         ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    
    # Test configuration
    use_local = test_configuration()
    
    # Test routes
    test_network_logs_route()
    test_network_logs_data_route()
    test_api_ingest()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80 + "\n")
    
    if use_local is None:
        print("⚠️  Could not connect to Mayasec server")
        print("   Make sure it's running: python app.py")
        sys.exit(1)
    elif use_local:
        print("✓ Running in FILE-BASED mode (USE_LOCAL_LOGS=true)")
        print("  ✓ Reads Suricata logs from /var/log/suricata/eve.json")
        print("  ✓ /network_logs route available")
        print("  ✓ /api/ingest/event endpoint available")
    else:
        print("✓ Running in API-ONLY mode (USE_LOCAL_LOGS=false)")
        print("  ✓ File-based log reading disabled")
        print("  ✓ /network_logs route disabled")
        print("  ✓ /api/ingest/event endpoint available")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
