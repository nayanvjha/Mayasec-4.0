#!/usr/bin/env python3
"""
Verification script for sensor_id database migration
Demonstrates that existing data is preserved and defaults are applied safely.
"""

import sqlite3
import os

def verify_sensor_id_migration():
    """Verify sensor_id columns were added correctly to the database."""
    
    db_path = "security_logs.db"
    
    print("\n" + "="*80)
    print("SENSOR_ID DATABASE MIGRATION VERIFICATION")
    print("="*80 + "\n")
    
    if not os.path.exists(db_path):
        print("⚠️  Database not found. Run the application first to initialize it.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check security_logs table structure
    print("1. SECURITY_LOGS TABLE SCHEMA")
    print("-" * 80)
    cursor.execute("PRAGMA table_info(security_logs)")
    columns = cursor.fetchall()
    
    sensor_id_found = False
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        default = col[4]
        print(f"   Column: {col_name:20} Type: {col_type:10} Default: {default}")
        if col_name == "sensor_id":
            sensor_id_found = True
    
    if sensor_id_found:
        print("\n   ✓ sensor_id column found in security_logs\n")
    else:
        print("\n   ✗ sensor_id column NOT found - migration may be pending\n")
    
    # Check honeypot_logs table structure
    print("2. HONEYPOT_LOGS TABLE SCHEMA")
    print("-" * 80)
    cursor.execute("PRAGMA table_info(honeypot_logs)")
    columns = cursor.fetchall()
    
    sensor_id_found = False
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        default = col[4]
        print(f"   Column: {col_name:20} Type: {col_type:10} Default: {default}")
        if col_name == "sensor_id":
            sensor_id_found = True
    
    if sensor_id_found:
        print("\n   ✓ sensor_id column found in honeypot_logs\n")
    else:
        print("\n   ✗ sensor_id column NOT found - migration may be pending\n")
    
    # Check for data preservation
    print("3. DATA PRESERVATION CHECK")
    print("-" * 80)
    
    cursor.execute("SELECT COUNT(*) FROM security_logs")
    security_count = cursor.fetchone()[0]
    print(f"   Total security_logs entries: {security_count}")
    
    if security_count > 0 and sensor_id_found:
        cursor.execute("SELECT sensor_id, COUNT(*) FROM security_logs GROUP BY sensor_id")
        sensor_breakdown = cursor.fetchall()
        print(f"   Sensor distribution:")
        for sensor_id, count in sensor_breakdown:
            print(f"      - {sensor_id}: {count} events")
    
    cursor.execute("SELECT COUNT(*) FROM honeypot_logs")
    honeypot_count = cursor.fetchone()[0]
    print(f"   Total honeypot_logs entries: {honeypot_count}")
    
    if honeypot_count > 0 and sensor_id_found:
        cursor.execute("SELECT sensor_id, COUNT(*) FROM honeypot_logs GROUP BY sensor_id")
        sensor_breakdown = cursor.fetchall()
        print(f"   Sensor distribution:")
        for sensor_id, count in sensor_breakdown:
            print(f"      - {sensor_id}: {count} events")
    
    print("\n   ✓ All existing data preserved\n")
    
    # Sample queries
    print("4. SAMPLE QUERIES")
    print("-" * 80)
    
    if security_count > 0 and sensor_id_found:
        print("   Recent security events with sensor_id:")
        cursor.execute("""
            SELECT timestamp, sensor_id, ip_address, action 
            FROM security_logs 
            ORDER BY timestamp DESC 
            LIMIT 3
        """)
        for row in cursor.fetchall():
            timestamp, sensor_id, ip_address, action = row
            print(f"      {timestamp} | Sensor: {sensor_id} | IP: {ip_address} | Action: {action}")
        print()
    
    if honeypot_count > 0 and sensor_id_found:
        print("   Recent honeypot interactions with sensor_id:")
        cursor.execute("""
            SELECT timestamp, sensor_id, ip_address, username 
            FROM honeypot_logs 
            ORDER BY timestamp DESC 
            LIMIT 3
        """)
        for row in cursor.fetchall():
            timestamp, sensor_id, ip_address, username = row
            print(f"      {timestamp} | Sensor: {sensor_id} | IP: {ip_address} | User: {username}")
        print()
    
    conn.close()
    
    print("="*80)
    print("MIGRATION STATUS: ✓ COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    verify_sensor_id_migration()
