#!/usr/bin/env python3

"""
MAYASEC External Attack Simulator
==================================
Generates realistic attack-like traffic and sends events to MAYASEC
via the ingestion API. Runs independently on any machine.

Usage:
    python3 attack_simulator.py --target http://target-machine:5000
    python3 attack_simulator.py --target http://localhost:5000 --scenario ssh-brute

Attack Scenarios:
    - ssh-brute:    SSH login brute force attempts
    - port-scan:    Network port scanning activity
    - invalid-auth: Invalid authentication attempts (mixed)
    - escalating:   Graduated attack intensity (default)
    - ddos:         DDoS-like traffic pattern
    - malware:      Suspicious file access and process execution
"""

import requests
import argparse
import time
import random
import json
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('attack_simulator.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════════

COMMON_IPS = [
    "203.0.113.42",    # Attacker IP 1
    "198.51.100.15",   # Attacker IP 2
    "192.0.2.87",      # Attacker IP 3
    "10.10.10.50",     # Attacker IP 4
    "172.16.5.100",    # Attacker IP 5
]

ATTACK_PORTS = [22, 23, 3306, 5432, 3389, 27017, 6379, 5000, 8080, 9200]

TARGET_HOSTS = [
    "192.168.1.100",
    "192.168.1.101",
    "192.168.1.102",
    "10.0.0.1",
]

SSH_USERNAMES = [
    "admin", "root", "user", "test", "oracle", "postgres",
    "mysql", "www-data", "nobody", "admin123"
]

# ═════════════════════════════════════════════════════════════════════════════
# Attack Event Generators
# ═════════════════════════════════════════════════════════════════════════════

class AttackEventGenerator:
    """Generates realistic attack events"""
    
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.event_counter = 0
        self.attack_intensity = 1.0
        
    def send_event(self, event_data: Dict) -> bool:
        """Send event to MAYASEC API"""
        try:
            # Ensure required fields
            event_data.setdefault('event_id', f"event-{self.event_counter:06d}")
            event_data.setdefault('timestamp', datetime.utcnow().isoformat())
            
            response = requests.post(
                f"{self.api_url}/api/v1/emit-event",
                json=event_data,
                headers={"Authorization": "Bearer mayasec_internal_token"},
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                self.event_counter += 1
                logger.info(f"✓ Event sent: {event_data.get('event_type')} "
                           f"(threat_score: {event_data.get('threat_score')})")
                return True
            else:
                logger.warning(f"✗ API error: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Cannot connect to API at {self.api_url}")
            return False
        except Exception as e:
            logger.error(f"✗ Error sending event: {e}")
            return False
    
    def ssh_brute_force(self, source_ip: str = None, intensity: int = 5):
        """SSH login brute force attempts"""
        source_ip = source_ip or random.choice(COMMON_IPS)
        target_ip = random.choice(TARGET_HOSTS)
        
        for i in range(intensity):
            username = random.choice(SSH_USERNAMES)
            event = {
                "event_id": f"ssh-brute-{self.event_counter}",
                "event_type": "SSH_BRUTE_FORCE",
                "source_ip": source_ip,
                "destination_ip": target_ip,
                "port": 22,
                "action": "BLOCKED",
                "threat_level": "high",
                "threat_score": min(85 + i*2, 100),
                "threat_description": f"SSH login attempt with user '{username}' (attempt {i+1}/{intensity})",
                "attack_pattern": "multiple_failed_logins",
                "additional_data": {
                    "username": username,
                    "attempt_number": i+1,
                    "total_attempts": intensity
                }
            }
            self.send_event(event)
            time.sleep(0.5)  # Stagger events
    
    def port_scan(self, source_ip: str = None, num_ports: int = 10):
        """Network port scanning activity"""
        source_ip = source_ip or random.choice(COMMON_IPS)
        target_ip = random.choice(TARGET_HOSTS)
        scanned_ports = random.sample(ATTACK_PORTS, min(num_ports, len(ATTACK_PORTS)))
        
        for idx, port in enumerate(scanned_ports):
            threat_score = min(50 + idx*5, 85)
            event = {
                "event_id": f"port-scan-{self.event_counter}",
                "event_type": "PORT_SCANNING",
                "source_ip": source_ip,
                "destination_ip": target_ip,
                "port": port,
                "action": "BLOCKED",
                "threat_level": "medium",
                "threat_score": threat_score,
                "threat_description": f"Port scan detected on port {port} ({idx+1}/{len(scanned_ports)})",
                "attack_pattern": "network_reconnaissance",
                "additional_data": {
                    "scanned_port": port,
                    "ports_scanned": idx+1,
                    "total_ports": len(scanned_ports)
                }
            }
            self.send_event(event)
            time.sleep(0.3)
    
    def invalid_authentication(self, source_ip: str = None, attempts: int = 3):
        """Invalid authentication attempts"""
        source_ip = source_ip or random.choice(COMMON_IPS)
        target_ip = random.choice(TARGET_HOSTS)
        
        for i in range(attempts):
            event = {
                "event_id": f"invalid-auth-{self.event_counter}",
                "event_type": "INVALID_AUTHENTICATION",
                "source_ip": source_ip,
                "destination_ip": target_ip,
                "action": "BLOCKED",
                "threat_level": "medium",
                "threat_score": 65 + i*10,
                "threat_description": f"Invalid authentication attempt #{i+1}",
                "attack_pattern": "credential_stuffing",
                "additional_data": {
                    "failed_attempts": i+1,
                    "service": random.choice(["HTTP", "FTP", "SMTP", "RDP"])
                }
            }
            self.send_event(event)
            time.sleep(0.4)
    
    def ddos_attack(self, source_ips: List[str] = None, packets: int = 20):
        """DDoS-like traffic pattern"""
        source_ips = source_ips or [random.choice(COMMON_IPS) for _ in range(5)]
        target_ip = random.choice(TARGET_HOSTS)
        
        for i in range(packets):
            source_ip = random.choice(source_ips)
            event = {
                "event_id": f"ddos-{self.event_counter}",
                "event_type": "DDOS_ATTACK",
                "source_ip": source_ip,
                "destination_ip": target_ip,
                "action": "BLOCKED",
                "threat_level": "critical" if i > packets//2 else "high",
                "threat_score": min(70 + i*2, 100),
                "threat_description": f"DDoS traffic detected from {source_ip}",
                "attack_pattern": "distributed_denial_of_service",
                "additional_data": {
                    "packet_count": i+1,
                    "source_count": len(source_ips),
                    "bandwidth_mbps": 10 * (i+1)
                }
            }
            self.send_event(event)
            time.sleep(0.2)  # Rapid fire events
    
    def malware_detection(self, source_ip: str = None):
        """Suspicious file access and malware-like behavior"""
        source_ip = source_ip or random.choice(COMMON_IPS)
        
        events_sequence = [
            {
                "event_type": "SUSPICIOUS_FILE_ACCESS",
                "threat_level": "high",
                "threat_score": 78,
                "threat_description": "Suspicious file enumeration in /etc",
                "attack_pattern": "file_system_reconnaissance",
                "additional_data": {"directory": "/etc", "file_count": 47}
            },
            {
                "event_type": "SUSPICIOUS_PROCESS",
                "threat_level": "critical",
                "threat_score": 92,
                "threat_description": "Detected unauthorized privilege escalation attempt",
                "attack_pattern": "privilege_escalation",
                "additional_data": {"process": "sudo", "user": "www-data"}
            },
            {
                "event_type": "MALWARE_DETECTED",
                "threat_level": "critical",
                "threat_score": 98,
                "threat_description": "Known malware signature matched",
                "attack_pattern": "malware_infection",
                "additional_data": {"malware_name": "Trojan.Generic", "signature": "SIG-2026-001"}
            }
        ]
        
        for event_template in events_sequence:
            event = {
                "event_id": f"malware-{self.event_counter}",
                "source_ip": source_ip,
                "destination_ip": random.choice(TARGET_HOSTS),
                "action": "QUARANTINE",
                **event_template
            }
            self.send_event(event)
            time.sleep(1)
    
    def escalating_attack(self, duration_seconds: int = 60):
        """Graduated attack intensity over time"""
        logger.info(f"Starting escalating attack for {duration_seconds} seconds...")
        start_time = time.time()
        phase = 1
        
        while time.time() - start_time < duration_seconds:
            elapsed = time.time() - start_time
            progress = elapsed / duration_seconds
            
            # Determine attack phase
            if progress < 0.25:
                logger.info("🔵 Phase 1: Initial Reconnaissance")
                self.port_scan(num_ports=3)
                phase = 1
            elif progress < 0.50:
                logger.info("🟡 Phase 2: Brute Force Attempts")
                self.ssh_brute_force(intensity=3)
                phase = 2
            elif progress < 0.75:
                logger.info("🟠 Phase 3: Exploitation")
                self.invalid_authentication(attempts=3)
                phase = 3
            else:
                logger.info("🔴 Phase 4: Critical Attack")
                self.ddos_attack(packets=10)
                phase = 4
            
            # Calculate remaining time
            remaining = duration_seconds - elapsed
            if remaining > 0:
                time.sleep(min(5, remaining))

# ═════════════════════════════════════════════════════════════════════════════
# Main Program
# ═════════════════════════════════════════════════════════════════════════════

def print_banner():
    """Print application banner"""
    banner = """
    ╔════════════════════════════════════════════════════════════╗
    ║     MAYASEC External Attack Simulator v1.0                ║
    ║     Generates realistic attack events for demo             ║
    ╚════════════════════════════════════════════════════════════╝
    """
    print(banner)

def main():
    parser = argparse.ArgumentParser(
        description='MAYASEC External Attack Simulator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # SSH brute force
  python3 attack_simulator.py --target http://localhost:5000 --scenario ssh-brute

  # Port scanning
  python3 attack_simulator.py --target http://localhost:5000 --scenario port-scan

  # Escalating attack (60 seconds)
  python3 attack_simulator.py --target http://localhost:5000 --scenario escalating --duration 60

  # DDoS attack
  python3 attack_simulator.py --target http://localhost:5000 --scenario ddos

  # Malware detection
  python3 attack_simulator.py --target http://localhost:5000 --scenario malware
        """
    )
    
    parser.add_argument(
        '--target',
        required=True,
        help='MAYASEC API target (e.g., http://192.168.1.100:5000)'
    )
    
    parser.add_argument(
        '--scenario',
        default='escalating',
        choices=['ssh-brute', 'port-scan', 'invalid-auth', 'ddos', 'malware', 'escalating'],
        help='Attack scenario to simulate (default: escalating)'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Duration in seconds (for escalating scenario, default: 60)'
    )
    
    parser.add_argument(
        '--intensity',
        type=int,
        default=5,
        help='Intensity/count for single-scenario attacks (default: 5)'
    )
    
    parser.add_argument(
        '--source-ip',
        help='Source IP for attacks (default: random from common attacker IPs)'
    )
    
    parser.add_argument(
        '--repeat',
        type=int,
        default=1,
        help='Number of times to repeat the scenario (default: 1)'
    )
    
    args = parser.parse_args()
    
    # Validate API URL
    if not args.target.startswith(('http://', 'https://')):
        args.target = f"http://{args.target}"
    
    print_banner()
    
    logger.info(f"🎯 Target: {args.target}")
    logger.info(f"📋 Scenario: {args.scenario}")
    logger.info(f"🔄 Repeat: {args.repeat} time(s)")
    
    # Initialize generator
    generator = AttackEventGenerator(args.target)
    
    # Test connection
    logger.info("Testing API connection...")
    try:
        response = requests.get(f"{args.target}/health", timeout=5)
        if response.status_code == 200:
            logger.info("✓ API connection successful!")
        else:
            logger.warning(f"⚠ API returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Cannot reach API at {args.target}")
        sys.exit(1)
    
    # Run simulation
    try:
        for run in range(args.repeat):
            if args.repeat > 1:
                logger.info(f"\n{'='*60}")
                logger.info(f"Run {run+1}/{args.repeat}")
                logger.info(f"{'='*60}")
            
            if args.scenario == 'ssh-brute':
                generator.ssh_brute_force(args.source_ip, args.intensity)
            
            elif args.scenario == 'port-scan':
                generator.port_scan(args.source_ip, args.intensity)
            
            elif args.scenario == 'invalid-auth':
                generator.invalid_authentication(args.source_ip, args.intensity)
            
            elif args.scenario == 'ddos':
                generator.ddos_attack(packets=args.intensity)
            
            elif args.scenario == 'malware':
                generator.malware_detection(args.source_ip)
            
            elif args.scenario == 'escalating':
                generator.escalating_attack(args.duration)
            
            if run < args.repeat - 1:
                logger.info(f"\nWaiting 10 seconds before next run...")
                time.sleep(10)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✓ Simulation complete!")
        logger.info(f"  Total events sent: {generator.event_counter}")
        logger.info(f"  Check dashboard at: {args.target.replace(':5000', ':3000')}")
        logger.info(f"{'='*60}")
        
    except KeyboardInterrupt:
        logger.info("\n✓ Simulation interrupted by user")
        logger.info(f"  Events sent: {generator.event_counter}")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"✗ Error during simulation: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
