import os
from datetime import datetime
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

INGESTOR_URL = os.getenv('INGESTOR_URL', 'http://ingestor:5001')


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _post_event(payload):
    url = f"{INGESTOR_URL.rstrip('/')}/api/ingest/event"
    requests.post(url, json=payload, timeout=5)


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    attacker_ip = data.get('attacker_ip') or request.headers.get('X-Attacker-IP') or request.remote_addr
    username = data.get('username', 'unknown')

    event = {
        'event_type': 'web_auth_failed',
        'timestamp': _timestamp(),
        'source': 'web_application',
        'sensor_id': 'victim-web',
        'sensor_type': 'system',
        'source_ip': attacker_ip,
        'destination': 'victim-web:8080',
        'severity': 'medium',
        'raw_log': f"POST /login failed for {username} from {attacker_ip}",
        'username': username,
        'reason': 'Invalid credentials',
        'action': 'logged'
    }
    _post_event(event)

    return jsonify({'status': 'failed'}), 401


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'victim-web',
        'status': 'online',
        'endpoints': [
            'POST /login',
            'GET /health'
        ]
    }), 200


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
