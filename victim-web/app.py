import os
import uuid
from datetime import datetime

from flask import Flask, Response, jsonify, request
import requests

app = Flask(__name__)

INGESTOR_URL = os.getenv('INGESTOR_URL', 'http://ingestor:5001')

# Import LLM proxy (graceful if unavailable)
try:
    import llm_proxy
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _post_event(payload):
    url = f"{INGESTOR_URL.rstrip('/')}/api/ingest/event"
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def _get_attack_info(req):
    """Extract attack metadata from MAYASEC headers set by ingress proxy."""
    return {
        'attack_type': req.headers.get('X-MAYASEC-ATTACK-TYPE', 'unknown'),
        'session_id': req.headers.get('X-MAYASEC-SESSION', str(uuid.uuid4())),
        'waf_score': req.headers.get('X-MAYASEC-SCORE', '0'),
        'source_ip': req.headers.get('X-Forwarded-For', req.remote_addr),
    }


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    info = _get_attack_info(request)
    event = {
        'event_type': 'web_auth_failed',
        'timestamp': _timestamp(),
        'source': 'web_application',
        'sensor_id': 'victim-web',
        'sensor_type': 'system',
        'source_ip': info['source_ip'],
        'destination': 'victim-web:8080',
        'severity': 'medium',
        'raw_log': f"POST /login failed for {data.get('username', 'unknown')} from {info['source_ip']}",
        'username': data.get('username', 'unknown'),
        'reason': 'Invalid credentials',
        'action': 'logged'
    }
    _post_event(event)

    # Try LLM-generated deceptive response
    if _LLM_AVAILABLE and info['attack_type'] in ('brute_force', 'sqli'):
        body_text = request.get_data(as_text=True)
        llm_reply = llm_proxy.get_deceptive_response(
            attack_type=info['attack_type'],
            uri='/login',
            body=body_text,
            method='POST',
        )
        if llm_reply:
            llm_proxy.log_capture(
                session_id=info['session_id'],
                source_ip=info['source_ip'],
                attack_type=info['attack_type'],
                request_payload=body_text[:2000],
                llm_response=llm_reply,
                persona_type=info['attack_type'],
            )
            return Response(llm_reply, status=200, content_type='text/html')

    return jsonify({'status': 'failed'}), 401


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def catch_all(path):
    """Catch-all route: attempt LLM deceptive response, fall back to static."""
    info = _get_attack_info(request)

    # Log the interaction
    body_text = request.get_data(as_text=True)
    event = {
        'event_type': 'honeypot_interaction',
        'timestamp': _timestamp(),
        'source': 'honeypot',
        'sensor_id': 'victim-web',
        'sensor_type': 'system',
        'source_ip': info['source_ip'],
        'destination': f'victim-web:8080/{path}',
        'severity': 'high',
        'raw_log': f"{request.method} /{path} from {info['source_ip']} score={info['waf_score']}",
        'action': 'captured'
    }
    _post_event(event)

    # Try LLM deceptive response
    if _LLM_AVAILABLE:
        llm_reply = llm_proxy.get_deceptive_response(
            attack_type=info['attack_type'],
            uri=f'/{path}',
            body=body_text,
            method=request.method,
        )
        if llm_reply:
            llm_proxy.log_capture(
                session_id=info['session_id'],
                source_ip=info['source_ip'],
                attack_type=info['attack_type'],
                request_payload=body_text[:2000],
                llm_response=llm_reply,
                persona_type=info['attack_type'],
            )
            return Response(llm_reply, status=200, content_type='text/html')

    # Static fallback
    return jsonify({
        'service': 'victim-web',
        'status': 'online',
        'path': f'/{path}',
    }), 200


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'llm_available': _LLM_AVAILABLE,
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
