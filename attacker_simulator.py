#!/usr/bin/env python3
"""
External Attacker Simulator for MAYASEC

Simulates realistic attack patterns and sends events to MAYASEC via ingestion API:
- SSH brute force attacks
- Port scanning
- Invalid login attempts

Requirements:
  - MAYASEC ingestor API running (default: http://localhost:5001)
  - Python 3.7+
  - requests library (pip install requests)

Usage:
  python attacker_simulator.py --target http://localhost:5001 --duration 300 --intensity high
  
Run on separate VM/container:
  - No database access required
  - No UI interaction
  - Pure API-driven event generation
  - Events appear LIVE in SOC console

Environment Variables:
  MAYASEC_INGESTOR_URL - Ingestor API URL (default: http://localhost:5001)
  ATTACKER_TARGET_IP - Target IP to scan (default: 192.168.1.100)
  ATTACKER_SOURCE_IP - Attacker's source IP (default: random 203.x.x.x)
"""

import os
import sys
import json
import time
import random
import argparse
import datetime
from typing import List, Dict, Any
import requests

# Configuration
DEFAULT_INGESTOR_URL = os.getenv('MAYASEC_INGESTOR_URL', 'http://localhost:5001')
DEFAULT_TARGET_IP = os.getenv('ATTACKER_TARGET_IP', '192.168.1.100')
DEFAULT_SOURCE_IP_RANGE = os.getenv('ATTACKER_SOURCE_IP', '203.0.113')  # TEST-NET-3

# Attack constants
SSH_PORT = 22
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 465, 587, 993, 995, 3306, 5432, 3389]
COMMON_USERNAMES = ['admin', 'root', 'user', 'test', 'administrator', 'guest', 'postgres', 'mysql']
WORDLIST = ['password', '123456', 'admin', 'letmein', '12345', 'qwerty', 'dragon', 'sunshine']

# Severity levels
SEVERITY_LEVELS = ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']


class AttackerSimulator:
    """Simulates realistic attack patterns and sends to MAYASEC ingestor."""

    def __init__(
        self,
        ingestor_url: str = DEFAULT_INGESTOR_URL,
        target_ip: str = DEFAULT_TARGET_IP,
        source_ip_range: str = DEFAULT_SOURCE_IP_RANGE,
        duration_seconds: int = 300,
        intensity: str = 'medium'
    ):
        """
        Initialize attacker simulator.

        Args:
            ingestor_url: MAYASEC ingestor API URL
            target_ip: Target IP to attack
            source_ip_range: Source IP range for attacker IPs
            duration_seconds: How long to run simulation
            intensity: 'low', 'medium', 'high' - controls event generation rate
        """
        self.ingestor_url = ingestor_url
        self.target_ip = target_ip
        self.source_ip_range = source_ip_range
        self.duration_seconds = duration_seconds
        self.intensity = intensity
        self.start_time = time.time()
        self.event_count = 0
        self.severity_escalation = 0  # Track escalation level

        # Intensity settings (events per second)
        self.intensity_map = {
            'low': {'rate': 0.5, 'burst': 3},      # 0.5 events/sec, bursts of 3
            'medium': {'rate': 2, 'burst': 5},     # 2 events/sec, bursts of 5
            'high': {'rate': 5, 'burst': 10},      # 5 events/sec, bursts of 10
        }

        self.current_intensity = self.intensity_map.get(intensity, self.intensity_map['medium'])

        # Validation
        self._validate_connection()

    def _validate_connection(self) -> bool:
        """Validate connection to MAYASEC ingestor."""
        try:
            response = requests.get(f'{self.ingestor_url}/health', timeout=5)
            if response.status_code == 200:
                print(f'✅ Connected to MAYASEC ingestor at {self.ingestor_url}')
                return True
        except requests.exceptions.RequestException as e:
            print(f'❌ Cannot connect to ingestor at {self.ingestor_url}')
            print(f'   Error: {e}')
            print(f'   Make sure ingestor is running: docker-compose up ingestor')
            return False

    def _generate_random_ip(self) -> str:
        """Generate random IP in source IP range."""
        parts = self.source_ip_range.split('.')
        if len(parts) == 3:
            return f'{self.source_ip_range}.{random.randint(1, 254)}'
        return f'{self.source_ip_range}{random.randint(1, 254)}'

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.datetime.utcnow().isoformat() + 'Z'

    def _send_event(self, event: Dict[str, Any]) -> bool:
        """
        Send event to MAYASEC ingestor API.

        Args:
            event: Event dictionary

        Returns:
            True if successful
        """
        try:
            response = requests.post(
                f'{self.ingestor_url}/ingest',
                json=event,
                timeout=10
            )

            if response.status_code in [200, 201]:
                self.event_count += 1
                return True
            else:
                print(f'⚠️  Ingestor returned {response.status_code}: {response.text[:100]}')
                return False

        except requests.exceptions.RequestException as e:
            print(f'❌ Failed to send event: {e}')
            return False

    def simulate_ssh_brute_force(self) -> None:
        """Simulate SSH brute force attack on target."""
        attacker_ip = self._generate_random_ip()
        num_attempts = random.randint(5, 20)  # 5-20 failed attempts

        for i in range(num_attempts):
            event = {
                'event_type': 'login_attempt',
                'timestamp': self._get_current_timestamp(),
                'source_ip': attacker_ip,
                'destination_ip': self.target_ip,
                'port': SSH_PORT,
                'protocol': 'SSH',
                'username': random.choice(COMMON_USERNAMES),
                'password': random.choice(WORDLIST),
                'result': 'failed',
                'attempt_number': i + 1,
                'total_attempts': num_attempts,
                'detection_reason': f'Failed SSH login attempt {i+1} of {num_attempts} from {attacker_ip}',
                'severity': 'MEDIUM' if i < 5 else 'HIGH' if i < 15 else 'CRITICAL',
                'severity_reasoning': f'Multiple SSH brute force attempts ({num_attempts} total). Pattern indicates automated attack.',
                'correlation_explanation': f'Brute force sequence: {num_attempts} attempts from single source in short timeframe',
            }
            self._send_event(event)
            time.sleep(random.uniform(0.1, 0.5))  # Realistic timing between attempts

    def simulate_port_scanning(self) -> None:
        """Simulate port scanning attack."""
        attacker_ip = self._generate_random_ip()
        ports_to_scan = random.sample(COMMON_PORTS, random.randint(3, 10))

        for port in ports_to_scan:
            event = {
                'event_type': 'port_scan',
                'timestamp': self._get_current_timestamp(),
                'source_ip': attacker_ip,
                'destination_ip': self.target_ip,
                'port': port,
                'protocol': 'TCP',
                'scan_type': 'syn_scan',
                'result': 'open' if port in [22, 80, 443] else 'closed',
                'detection_reason': f'Suspicious port scan activity detected on port {port}',
                'severity': 'LOW' if port in [80, 443] else 'MEDIUM',
                'severity_reasoning': f'Port scanning from external source {attacker_ip}. Indicates reconnaissance activity.',
                'correlation_explanation': f'Port scan sequence from {attacker_ip}: scanning multiple ports in rapid succession',
            }
            self._send_event(event)
            time.sleep(random.uniform(0.05, 0.2))  # Rapid scanning

    def simulate_invalid_login_attempts(self) -> None:
        """Simulate invalid login attempts via HTTP/HTTPS."""
        attacker_ip = self._generate_random_ip()
        num_attempts = random.randint(3, 10)

        for i in range(num_attempts):
            event = {
                'event_type': 'login_attempt',
                'timestamp': self._get_current_timestamp(),
                'source_ip': attacker_ip,
                'destination_ip': self.target_ip,
                'port': random.choice([80, 443, 8080, 8443]),
                'protocol': 'HTTP',
                'username': random.choice(COMMON_USERNAMES),
                'password': random.choice(WORDLIST),
                'result': 'failed',
                'attempt_number': i + 1,
                'total_attempts': num_attempts,
                'http_status': 401,
                'detection_reason': f'Invalid HTTP authentication attempt {i+1} from {attacker_ip}',
                'severity': 'MEDIUM' if num_attempts < 5 else 'HIGH',
                'severity_reasoning': f'Multiple invalid login attempts via HTTP. Indicates credential stuffing or brute force attempt.',
                'correlation_explanation': f'HTTP login attack: {num_attempts} failed authentication attempts from single source',
            }
            self._send_event(event)
            time.sleep(random.uniform(0.1, 0.3))

    def simulate_escalation(self) -> None:
        """Simulate attack escalation (escalates severity naturally)."""
        attacker_ip = self._generate_random_ip()
        self.severity_escalation += 1

        # Start with reconnaissance, escalate to active attacks
        if self.severity_escalation < 3:
            # Phase 1: Reconnaissance (port scanning)
            self.simulate_port_scanning()
        elif self.severity_escalation < 6:
            # Phase 2: Enumeration (SSH attempts)
            self.simulate_ssh_brute_force()
        else:
            # Phase 3: Aggressive attacks (all methods)
            self.simulate_ssh_brute_force()
            time.sleep(0.5)
            self.simulate_invalid_login_attempts()

    def run(self) -> None:
        """Run the attack simulation."""
        print(f"""
╔════════════════════════════════════════════════════════════════╗
║           MAYASEC Attacker Simulator - STARTING                ║
╚════════════════════════════════════════════════════════════════╝

Configuration:
  Ingestor URL: {self.ingestor_url}
  Target IP: {self.target_ip}
  Source IP Range: {self.source_ip_range}.x
  Duration: {self.duration_seconds} seconds
  Intensity: {self.intensity} ({self.current_intensity['rate']} events/sec)

Attack Simulation:
  - SSH brute force attacks
  - Port scanning
  - Invalid login attempts
  - Natural severity escalation

Status: Running... (Ctrl+C to stop)
""")

        try:
            while time.time() - self.start_time < self.duration_seconds:
                # Choose random attack type
                attack_type = random.choice(['ssh_brute_force', 'port_scan', 'invalid_login', 'escalation'])

                if attack_type == 'ssh_brute_force':
                    self.simulate_ssh_brute_force()
                elif attack_type == 'port_scan':
                    self.simulate_port_scanning()
                elif attack_type == 'invalid_login':
                    self.simulate_invalid_login_attempts()
                elif attack_type == 'escalation':
                    self.simulate_escalation()

                # Calculate sleep time based on intensity
                sleep_time = 1.0 / self.current_intensity['rate']
                time.sleep(sleep_time)

                # Progress update every 30 seconds
                elapsed = time.time() - self.start_time
                if int(elapsed) % 30 == 0 and elapsed > 1:
                    remaining = self.duration_seconds - elapsed
                    print(f'📊 {int(elapsed)}s elapsed | {self.event_count} events sent | '
                          f'{int(remaining)}s remaining | Escalation: {self.severity_escalation}')

        except KeyboardInterrupt:
            print('\n⏹️  Simulation interrupted by user')
        finally:
            self._print_summary()

    def _print_summary(self) -> None:
        """Print simulation summary."""
        elapsed = time.time() - self.start_time
        event_rate = self.event_count / elapsed if elapsed > 0 else 0

        print(f"""
╔════════════════════════════════════════════════════════════════╗
║                    SIMULATION SUMMARY                          ║
╚════════════════════════════════════════════════════════════════╝

Duration: {elapsed:.1f} seconds
Total Events Sent: {self.event_count}
Event Rate: {event_rate:.1f} events/second
Escalation Phases: {self.severity_escalation}

Attack Types Simulated:
  ✅ SSH brute force attacks
  ✅ Port scanning
  ✅ Invalid login attempts
  ✅ Natural severity escalation

Expected Results:
  • Events visible LIVE in SOC console
  • Timeline grows dynamically
  • Severity escalates naturally
  • Correlation IDs group related events

Check MAYASEC SOC Console:
  http://localhost:3000
""")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='MAYASEC External Attacker Simulator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 5-minute simulation at medium intensity
  python attacker_simulator.py --duration 300 --intensity medium

  # Target specific MAYASEC instance
  python attacker_simulator.py --target http://192.168.1.10:5001

  # Scan specific target with high intensity
  python attacker_simulator.py --target-ip 10.0.0.5 --intensity high

  # Long-running simulation (1 hour)
  python attacker_simulator.py --duration 3600 --intensity low

Environment Variables:
  MAYASEC_INGESTOR_URL - Ingestor API URL (default: http://localhost:5001)
  ATTACKER_TARGET_IP - Target IP to scan (default: 192.168.1.100)
  ATTACKER_SOURCE_IP - Source IP range (default: 203.0.113)
"""
    )

    parser.add_argument(
        '--target',
        default=DEFAULT_INGESTOR_URL,
        help=f'MAYASEC ingestor URL (default: {DEFAULT_INGESTOR_URL})'
    )
    parser.add_argument(
        '--target-ip',
        default=DEFAULT_TARGET_IP,
        help=f'Target IP to attack (default: {DEFAULT_TARGET_IP})'
    )
    parser.add_argument(
        '--source-ip',
        default=DEFAULT_SOURCE_IP_RANGE,
        help=f'Source IP range (default: {DEFAULT_SOURCE_IP_RANGE})'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=300,
        help='Duration in seconds (default: 300)'
    )
    parser.add_argument(
        '--intensity',
        choices=['low', 'medium', 'high'],
        default='medium',
        help='Attack intensity: low (0.5/sec), medium (2/sec), high (5/sec) (default: medium)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.duration < 1:
        print('❌ Duration must be at least 1 second')
        sys.exit(1)

    # Create and run simulator
    simulator = AttackerSimulator(
        ingestor_url=args.target,
        target_ip=args.target_ip,
        source_ip_range=args.source_ip,
        duration_seconds=args.duration,
        intensity=args.intensity
    )

    # Validate connection before starting
    if not simulator._validate_connection():
        print('\n❌ Cannot connect to MAYASEC ingestor. Ensure it is running:')
        print('   docker-compose up ingestor')
        sys.exit(1)

    # Run simulation
    simulator.run()


if __name__ == '__main__':
    main()
