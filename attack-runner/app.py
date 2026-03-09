import os
import random
import socket
import time
from datetime import datetime
from typing import Dict, Any, List

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import paramiko

app = Flask(__name__)
CORS(app, resources={r"/attack/*": {"origins": "*", "methods": ["POST", "OPTIONS"], "allow_headers": "*"}})

INGESTOR_URL = os.getenv('INGESTOR_URL', 'http://ingestor:5001')
API_URL = os.getenv('API_URL', 'http://api:5000')
VICTIM_WEB_URL = os.getenv('VICTIM_WEB_URL', 'http://victim-web:8080')
VICTIM_SSH_HOST = os.getenv('VICTIM_SSH_HOST', 'victim-ssh')
VICTIM_SSH_PORT = int(os.getenv('VICTIM_SSH_PORT', '2222'))
VICTIM_SSH_USER = os.getenv('VICTIM_SSH_USER', 'demo')
VICTIM_SSH_PASSWORD = os.getenv('VICTIM_SSH_PASSWORD', 'correctpass')

DEFAULT_ATTACKER_IP = os.getenv('DEFAULT_ATTACKER_IP', '203.0.113.10')
DEFAULT_TARGET_HOST = os.getenv('DEFAULT_TARGET_HOST', 'victim-web')

USERNAMES = ['root', 'admin', 'ubuntu', 'test', 'guest', 'postgres']
PASSWORDS = ['password', '123456', 'admin', 'letmein', 'qwerty', 'secret']
SCAN_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 2222, 8080]


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _post_event(payload: Dict[str, Any]) -> None:
    url = f"{INGESTOR_URL.rstrip('/')}/api/ingest/event"
    requests.post(url, json=payload, timeout=5)


def _is_blocked(attacker_ip: str) -> bool:
    try:
        url = f"{API_URL.rstrip('/')}/api/v1/alerts/status/{attacker_ip}"
        response = requests.get(url, timeout=3)
        if response.ok:
            return bool(response.json().get('is_blocked'))
    except Exception:
        pass
    return False


def _base_event(attacker_ip: str, target: str) -> Dict[str, Any]:
    return {
        'source': 'http_api',
        'sensor_id': 'attack-runner',
        'sensor_type': 'system',
        'source_ip': attacker_ip,
        'destination': target,
        'timestamp': _timestamp(),
    }


def _attack_result(response) -> Dict[str, Any]:
    return {
        'status_code': response.status_code,
        'body': response.text[:200]
    }


@app.route('/attack/web-login', methods=['POST'])
def attack_web_login():
    data = request.get_json() or {}
    attacker_ip = data.get('attacker_ip', DEFAULT_ATTACKER_IP)
    target = data.get('target', DEFAULT_TARGET_HOST)
    count = int(data.get('count', 10))

    if _is_blocked(attacker_ip):
        return jsonify({'status': 'blocked', 'attacker_ip': attacker_ip}), 403

    results = []
    for idx in range(count):
        username = USERNAMES[idx % len(USERNAMES)]
        password = PASSWORDS[idx % len(PASSWORDS)]
        payload = {
            'username': username,
            'password': password,
            'attacker_ip': attacker_ip
        }
        try:
            response = requests.post(f"{VICTIM_WEB_URL.rstrip('/')}/login", json=payload, timeout=3)
            results.append(_attack_result(response))
        except Exception as e:
            results.append({'error': str(e)})
        time.sleep(0.1)

    return jsonify({'status': 'ok', 'attempts': count, 'results': results}), 200


@app.route('/attack/ssh', methods=['POST'])
def attack_ssh():
    data = request.get_json() or {}
    attacker_ip = data.get('attacker_ip', DEFAULT_ATTACKER_IP)
    target = data.get('target', VICTIM_SSH_HOST)
    count = int(data.get('count', 10))

    if _is_blocked(attacker_ip):
        return jsonify({'status': 'blocked', 'attacker_ip': attacker_ip}), 403

    failures = 0
    for idx in range(count):
        password = PASSWORDS[idx % len(PASSWORDS)]
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=VICTIM_SSH_HOST,
                port=VICTIM_SSH_PORT,
                username=VICTIM_SSH_USER,
                password=password,
                timeout=3,
                banner_timeout=3,
                auth_timeout=3
            )
        except Exception:
            failures += 1
            event = {
                **_base_event(attacker_ip, f"{target}:{VICTIM_SSH_PORT}"),
                'event_type': 'ssh_failed_login',
                'severity': 'high' if idx >= 5 else 'medium',
                'protocol': 'SSH',
                'port': {'destination': VICTIM_SSH_PORT},
                'username': VICTIM_SSH_USER,
                'reason': 'SSH brute force attempt',
                'raw_log': f"Failed password for {VICTIM_SSH_USER} from {attacker_ip} port {VICTIM_SSH_PORT} ssh2"
            }
            _post_event(event)
        finally:
            client.close()
        time.sleep(0.1)

    return jsonify({'status': 'ok', 'attempts': count, 'failures': failures}), 200


@app.route('/attack/port-scan', methods=['POST'])
def attack_port_scan():
    data = request.get_json() or {}
    attacker_ip = data.get('attacker_ip', DEFAULT_ATTACKER_IP)
    target = data.get('target', DEFAULT_TARGET_HOST)
    count = int(data.get('count', 10))

    if _is_blocked(attacker_ip):
        return jsonify({'status': 'blocked', 'attacker_ip': attacker_ip}), 403

    ports = SCAN_PORTS[:max(1, min(count, len(SCAN_PORTS)))]
    open_ports = []

    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        try:
            result = sock.connect_ex((target, port))
            if result == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            sock.close()

        event = {
            **_base_event(attacker_ip, f"{target}:{port}"),
            'event_type': 'port_scan',
            'severity': 'high' if port in (22, 2222, 3389) else 'medium',
            'protocol': 'TCP',
            'port': {'destination': port},
            'reason': 'Port scan detected',
            'raw_log': f"Port scan from {attacker_ip} to {target} on port {port}"
        }
        _post_event(event)
        time.sleep(0.05)

    return jsonify({'status': 'ok', 'ports_scanned': ports, 'open_ports': open_ports}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4001)
