import asyncio
import os
import random
import string
import uuid
from datetime import datetime

from flask import Flask, Response, jsonify, request
import httpx
import behavior_analyzer

from session_tracker import (
    cache_response,
    get_cached_response,
    get_session,
    update_session,
)

app = Flask(__name__)

INGESTOR_URL = os.getenv('INGESTOR_URL', 'http://ingestor:5001')

APACHE_SERVERS = [
    'Apache/2.4.41 (Ubuntu)',
    'Apache/2.4.38 (Debian)',
    'Apache/2.4.29 (Ubuntu)',
]

NGINX_SERVERS = [
    'nginx/1.18.0 (Ubuntu)',
    'nginx/1.14.2',
    'nginx/1.20.1',
]

PHP_VERSIONS = [
    'PHP/7.4.3',
    'PHP/7.4.33',
    'PHP/8.0.2',
    'PHP/8.1.2',
]

KNOWN_SCANNERS = [
    'nmap',
    'sqlmap',
    'nikto',
    'masscan',
    'zgrab',
    'shodan',
    'censys',
    'python-requests',
]

# Import LLM proxy (graceful if unavailable)
try:
    import llm_proxy
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + 'Z'


async def _post_event(payload):
    url = f"{INGESTOR_URL.rstrip('/')}/api/ingest/event"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=payload)
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


def _random_str(length=26):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


async def _render_template_response(path, info, session, body_text):
    _ = info
    _ = session
    _ = body_text

    path_lower = path.lower()

    # Latency jitter to reduce timing-based fingerprinting
    await asyncio.sleep(random.uniform(0.01, 0.15))

    # Admin panel mimicry
    if any(token in path_lower for token in ('phpmyadmin', 'wp-login', 'admin.php', 'wp-admin')):
        resp = Response('Unauthorized', status=401, content_type='text/plain; charset=utf-8')
        resp.headers['Server'] = random.choice(APACHE_SERVERS)
        resp.headers['X-Powered-By'] = random.choice(PHP_VERSIONS)
        resp.headers['WWW-Authenticate'] = 'Basic realm="Admin Area"'
        resp.set_cookie('PHPSESSID', _random_str())
        return resp

    # WordPress redirect mimicry
    if 'wp-includes' in path_lower or 'wp-content' in path_lower:
        resp = Response('', status=302)
        resp.headers['Location'] = f'/wp-login.php?redirect_to=/{path}'
        resp.headers['Server'] = random.choice(NGINX_SERVERS)
        return resp

    # API server mimicry
    if path_lower.startswith('api/') or path_lower == 'api':
        payload = {
            'error': 'Missing Authentication Token',
            'code': 401,
        }
        resp = jsonify(payload)
        resp.status_code = 401
        resp.headers['X-Powered-By'] = 'Express'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    # Default corporate website mimicry
    html = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Nexus Digital Solutions</title>
  </head>
  <body>
    <h1>Welcome to Nexus Digital</h1>
  </body>
</html>"""
    resp = Response(html, status=200, content_type='text/html; charset=utf-8')
    resp.headers['Server'] = random.choice(APACHE_SERVERS)
    jsession = ''.join(random.choices(string.ascii_uppercase + string.digits, k=26))
    resp.set_cookie('JSESSIONID', jsession)
    return resp


@app.route('/login', methods=['POST'])
async def login():
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
    asyncio.create_task(_post_event(event))

    body_text = request.get_data(as_text=True) or ''
    llm_reply = None
    analysis = None

    try:
        analysis = behavior_analyzer.analyze(
            source_ip=info['source_ip'],
            session_id=info.get('session_id'),
            request_data={
                'uri': '/login',
                'body': body_text,
                'method': 'POST',
                'user_agent': request.headers.get('User-Agent', ''),
                'attack_type': info['attack_type'],
                'waf_score': info.get('waf_score', '0'),
            },
        )
        info['session_id'] = analysis.get('session_id') or info.get('session_id')
    except Exception:
        analysis = None

    # Try LLM-generated deceptive response
    if _LLM_AVAILABLE and info['attack_type'] in ('brute_force', 'sqli'):
        llm_reply = await llm_proxy.get_deceptive_response(
            attack_type=info['attack_type'],
            uri='/login',
            body=body_text,
            method='POST',
            llm_context=(analysis or {}).get('llm_context'),
        )

    # Always capture login interaction, even when LLM fails
    if _LLM_AVAILABLE:
        await llm_proxy.log_capture(
            session_id=info['session_id'],
            source_ip=info['source_ip'],
            attack_type=info['attack_type'],
            request_payload=body_text[:2000],
            llm_response=llm_reply or '[static_fallback]',
            persona_type=info['attack_type'],
            tenant_id=(analysis or {}).get('tenant_id'),
        )

    if llm_reply:
        try:
            behavior_analyzer.update_environment_after_response(
                source_ip=info['source_ip'],
                session_id=info['session_id'],
                response_body=llm_reply,
            )
        except Exception:
            pass

    if llm_reply:
        return Response(llm_reply, status=200, content_type='text/html')

    return jsonify({'status': 'failed'}), 401


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def catch_all(path):
    """3-tier deception pipeline: protocol mimicry, cache, and selective LLM."""
    info = _get_attack_info(request)
    source_ip = (info.get('source_ip') or '').split(',')[0].strip()
    uri = f"/{path}" if path else '/'
    body_text = request.get_data(as_text=True) or ''
    user_agent = request.headers.get('User-Agent', '')
    attack_type = info.get('attack_type', 'unknown')
    try:
        waf_score = int(float(info.get('waf_score', 0)))
    except Exception:
        waf_score = 0

    # Session state update
    session = update_session(source_ip, uri, attack_type)
    analysis = None
    try:
        analysis = behavior_analyzer.analyze(
            source_ip=source_ip,
            session_id=info.get('session_id'),
            request_data={
                'uri': uri,
                'body': body_text,
                'method': request.method,
                'user_agent': user_agent,
                'attack_type': attack_type,
                'waf_score': waf_score,
            },
        )
        info['session_id'] = analysis.get('session_id') or info.get('session_id')
    except Exception:
        analysis = None

    # Fire-and-forget interaction logging
    event = {
        'event_type': 'honeypot_interaction',
        'timestamp': _timestamp(),
        'source': 'honeypot',
        'sensor_id': 'victim-web',
        'sensor_type': 'system',
        'source_ip': source_ip,
        'destination': f'victim-web:8080/{path}',
        'severity': 'high',
        'raw_log': f"{request.method} /{path} from {source_ip} score={waf_score}",
        'action': 'captured'
    }
    asyncio.create_task(_post_event(event))

    # TIER 1 — short-circuit protocol mimicry
    ua_lc = user_agent.lower()
    is_known_scanner = any(sig in ua_lc for sig in KNOWN_SCANNERS)
    no_query = len(request.args) == 0
    empty_body = len(body_text.strip()) == 0

    tier3_eligible = (
        session.get('depth', 0) >= 3
        and waf_score >= 85
        and len(set(session.get('uri_history', []))) > 2
    )
    scanner_tier3_override = is_known_scanner and waf_score >= 85 and session.get('depth', 0) >= 2
    llm_reply = None

    if (
        (session.get('depth', 0) < 3 and not scanner_tier3_override)
        or (waf_score < 85 and empty_body and no_query)
    ):
        if _LLM_AVAILABLE:
            await llm_proxy.log_capture(
                session_id=info['session_id'],
                source_ip=source_ip,
                attack_type=attack_type,
                request_payload=body_text[:2000],
                llm_response='[static_fallback]',
                persona_type=attack_type,
                tenant_id=(analysis or {}).get('tenant_id'),
            )
        try:
            behavior_analyzer.update_environment_after_response(
                source_ip=source_ip,
                session_id=info['session_id'],
                response_body='[static_fallback]'
            )
        except Exception:
            pass
        return await _render_template_response(path, info, session, body_text)

    # TIER 2 — response cache
    cached = get_cached_response(
        attack_type,
        uri,
        request.method,
        body_text,
    )
    if cached:
        if _LLM_AVAILABLE:
            await llm_proxy.log_capture(
                session_id=info['session_id'],
                source_ip=source_ip,
                attack_type=attack_type,
                request_payload=body_text[:2000],
                llm_response='[static_fallback]',
                persona_type=attack_type,
                tenant_id=(analysis or {}).get('tenant_id'),
            )
        try:
            behavior_analyzer.update_environment_after_response(
                source_ip=source_ip,
                session_id=info['session_id'],
                response_body=cached,
            )
        except Exception:
            pass
        return Response(cached, status=200, content_type='text/html')

    # TIER 3 — selective LLM interaction
    if _LLM_AVAILABLE and tier3_eligible:
        llm_reply = await llm_proxy.get_deceptive_response(
            attack_type=attack_type,
            uri=uri,
            body=body_text,
            method=request.method,
            session_history=session.get('uri_history', [])[-5:],
            llm_context=(analysis or {}).get('llm_context'),
        )
        if llm_reply:
            cache_response(
                attack_type,
                uri,
                request.method,
                body_text,
                llm_reply,
            )

    # Always capture honeypot interaction, even when LLM fails
    if _LLM_AVAILABLE:
        await llm_proxy.log_capture(
            session_id=info['session_id'],
            source_ip=source_ip,
            attack_type=attack_type,
            request_payload=body_text[:2000],
            llm_response=llm_reply or '[static_fallback]',
            persona_type=attack_type,
            tenant_id=(analysis or {}).get('tenant_id'),
        )

    if llm_reply:
        try:
            behavior_analyzer.update_environment_after_response(
                source_ip=source_ip,
                session_id=info['session_id'],
                response_body=llm_reply,
            )
        except Exception:
            pass

    if llm_reply:
        return Response(llm_reply, status=200, content_type='text/html')

    # Fallback when Tier 3 not eligible or LLM fails
    return await _render_template_response(path, info, session, body_text)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'llm_available': _LLM_AVAILABLE,
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
