from flask import Flask, request, render_template, redirect, url_for, jsonify, session
from datetime import datetime
import sqlite3
import os
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
import threading
from threat_intel import analyze_with_gemini
from log_ingestion import ingest_event
import re
import textwrap
import json
from math import ceil
from collections import defaultdict, deque
import time
import random



app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Database configuration
DATABASE_PATH = 'security_logs.db'
SURICATA_LOG_PATH = "/var/log/suricata/eve.json"

# Configuration: Enable/disable file-based log ingestion
# Set via environment variable USE_LOCAL_LOGS=true/false (default: true)
# true  = Read Suricata logs from file (existing behavior)
# false = Disable file reading, rely only on API ingestion
USE_LOCAL_LOGS = os.getenv('USE_LOCAL_LOGS', 'true').lower() in ('true', '1', 'yes')

LOGS_PER_PAGE = 20

import os
import json
from collections import defaultdict, deque

SURICATA_LOG_PATH = "/var/log/suricata/eve.json"
LOGS_PER_PAGE = 20

def load_suricata_logs(max_lines=2000):
    """
    Load Suricata logs and group by source IP.
    - Shows aggregated alerts per source IP.
    - Keeps track of dest IPs, ports, alert signature, severity, count, first/last seen.
    """
    if not os.path.exists(SURICATA_LOG_PATH):
        return []

    logs = deque(maxlen=max_lines)
    with open(SURICATA_LOG_PATH, "r") as f:
        logs.extend(f)

    grouped = defaultdict(lambda: {
        "alerts": defaultdict(lambda: {"count": 0, "dest_ips": set(), "dest_ports": set(), "proto": "", "severity": "", "first_seen": "", "last_seen": ""})
    })

    for line in logs:
        try:
            entry = json.loads(line)
            if entry.get("event_type") != "alert":
                continue

            src_ip = entry.get("src_ip")
            dest_ip = entry.get("dest_ip")
            proto = entry.get("proto")
            src_port = entry.get("src_port", "N/A")
            dest_port = entry.get("dest_port", "N/A")
            signature = entry.get("alert", {}).get("signature", "N/A")
            severity = entry.get("alert", {}).get("severity_name", "LOW")
            timestamp = entry.get("timestamp")

            # Grouping key: source IP → signature
            alert_info = grouped[src_ip]["alerts"][signature]
            alert_info["count"] += 1
            alert_info["dest_ips"].add(dest_ip)
            alert_info["dest_ports"].add(dest_port)
            alert_info["proto"] = proto
            alert_info["severity"] = severity
            alert_info["first_seen"] = timestamp if not alert_info["first_seen"] else min(alert_info["first_seen"], timestamp)
            alert_info["last_seen"] = timestamp if not alert_info["last_seen"] else max(alert_info["last_seen"], timestamp)
        except json.JSONDecodeError:
            continue

    # Flatten for rendering
    final_logs = []
    for src_ip, data in grouped.items():
        for signature, info in data["alerts"].items():
            final_logs.append({
                "src_ip": src_ip,
                "alert_signature": signature,
                "dest_ips": ", ".join(info["dest_ips"]),
                "dest_ports": ", ".join(map(str, info["dest_ports"])),
                "proto": info["proto"],
                "severity": info["severity"],
                "first_seen": info["first_seen"],
                "last_seen": info["last_seen"],
                "count": info["count"]
            })

    # Sort by last_seen
    final_logs.sort(key=lambda x: x["last_seen"], reverse=True)
    return final_logs


def get_client_ip():
    """Get client IP with test override capability"""
    # Check for test IP header first
    test_ip = request.headers.get('X-Test-IP')
    if test_ip:
        print(f"🧪 Using test IP: {test_ip}")
        return test_ip
    
    # Normal IP detection
    return request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)


def init_database():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Security logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            username TEXT,
            action TEXT NOT NULL,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            threat_level TEXT DEFAULT 'LOW',
            blocked BOOLEAN DEFAULT 0,
            reason TEXT  -- NEW column for AI explanation
        )
    ''')
    
    # Ensure 'reason' column exists in case of old DB
    try:
        cursor.execute("ALTER TABLE security_logs ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists, ignore
    
    # Ensure 'sensor_id' column exists in case of old DB
    try:
        cursor.execute("ALTER TABLE security_logs ADD COLUMN sensor_id TEXT DEFAULT 'local-sensor'")
    except sqlite3.OperationalError:
        pass  # column already exists, ignore
    
    # Honeypot interactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS honeypot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            username TEXT,
            password_attempt TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_agent TEXT,
            sensor_id TEXT DEFAULT 'local-sensor'
        )
    ''')
    
    # Ensure 'sensor_id' column exists in honeypot_logs in case of old DB
    try:
        cursor.execute("ALTER TABLE honeypot_logs ADD COLUMN sensor_id TEXT DEFAULT 'local-sensor'")
    except sqlite3.OperationalError:
        pass  # column already exists, ignore
    
    # Blocked IPs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            reason TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            is_permanent BOOLEAN DEFAULT 0
        )
    ''')
    
    # Create default admin user if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        admin_password = generate_password_hash('admin')
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            ('admin', admin_password)
        )
    
    conn.commit()
    conn.close()


def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_security_event(ip_address, username, action, user_agent=None, threat_level='LOW', blocked=False, reason="working", sensor_id="local-sensor"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO security_logs (ip_address, username, action, user_agent, threat_level, blocked, reason, sensor_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ip_address, username, action, user_agent, threat_level, blocked, reason, sensor_id))
    conn.commit()
    conn.close()


def log_honeypot_interaction(ip_address, username, password, user_agent=None, sensor_id="local-sensor"):
    """Log honeypot interactions"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO honeypot_logs (ip_address, username, password_attempt, user_agent, sensor_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (ip_address, username, password, user_agent, sensor_id))
    conn.commit()
    conn.close()

def is_ip_blocked(ip_address):
    """Check if IP is blocked"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM blocked_ips 
        WHERE ip_address = ? AND (is_permanent = 1 OR expires_at > datetime('now'))
    ''', (ip_address,))
    result = cursor.fetchone()[0] > 0
    conn.close()
    return result

def block_ip(ip_address, reason, permanent=False, duration_hours=24):
    """Block an IP address"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    expires_at = None if permanent else f"datetime('now', '+{duration_hours} hours')"
    
    cursor.execute('''
        INSERT OR REPLACE INTO blocked_ips (ip_address, reason, is_permanent, expires_at)
        VALUES (?, ?, ?, datetime('now', '+{} hours'))
    '''.format(duration_hours if not permanent else '100 years'), (ip_address, reason, permanent))
    conn.commit()
    conn.close()

def authenticate_user(username, password):
    """Authenticate user against database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password_hash FROM users WHERE username = ? AND is_active = 1', (username,))
    user = cursor.fetchone()
    
    if user and check_password_hash(user['password_hash'], password):
        # Update last login
        cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?', (username,))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

# Initialize database on startup
init_database()

try:
    from security_monitor import SecurityMonitor
    security_monitor = SecurityMonitor()
    SECURITY_ENABLED = True
    print("✅ Security monitor loaded successfully")
except ImportError as e:
    print(f"⚠️  Security monitor not available: {e}")
    SECURITY_ENABLED = False

@app.route("/network_logs_data")
def network_logs_data():
    """Get network logs data - respects USE_LOCAL_LOGS configuration flag"""
    if not USE_LOCAL_LOGS:
        return jsonify({
            "error": "File-based log ingestion is disabled",
            "message": "USE_LOCAL_LOGS is set to false. Please use POST /api/ingest/event to submit network alerts."
        }), 403
    
    logs = load_suricata_logs()
    html_rows = ""
    for log in logs:
        html_rows += f"""
        <tr class="alert-{log['severity'].lower()}">
            <td>{log['src_ip']}</td>
            <td>{log['dest_ips']}</td>
            <td>{log['dest_ports']}</td>            <td>{log['proto']}</td>
            <td>{log['alert_signature']}</td>
            <td>{log['severity']}</td>
            <td>{log['count']}</td>
            <td>{log['first_seen']}</td>
            <td>{log['last_seen']}</td>
        </tr>
        """
    return html_rows


@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():

    ip_address = get_client_ip()
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    user_agent = request.headers.get('User-Agent', '')
    event = {
        "ip": ip_address,
        "username": username,
        "user_agent": user_agent,
        "timestamp": str(datetime.now()),
        "os": request.user_agent.platform or "Unknown",
        "location": "Unknown",   # can integrate geoip later
        "login_result": "ATTEMPT",
        "attempts_last_hour": 0
    }

    
    intel = analyze_with_gemini(event)
    if "analysis" in intel:
        analysis_text = intel["analysis"]
        analysis_upper = analysis_text.upper()
        import re
        def clean_reason(analysis_text: str) -> str:
            # Try to extract "SHORT REASON" if present
            match = re.search(r"SHORT REASON[:\-]*\s*(.*)", analysis_text, re.IGNORECASE | re.DOTALL)
            if match:
                reason = match.group(1).strip()
            else:
                # fallback → use full text
                reason = analysis_text.strip()

            # Normalize formatting
            reason = textwrap.fill(reason, width=100)  # wrap for readability
            return reason

        reason = clean_reason(analysis_text)

        if "HIGH" in analysis_upper or "CRITICAL" in analysis_upper:
            # Block IP and log with full AI reason
            block_ip(ip_address, reason, permanent=True)
            log_security_event(
                ip_address,
                username,
                "AI_BLOCKED",
                user_agent,
                "CRITICAL",
                True,
                reason  # <-- pass reason to DB
            )

            # User only sees generic message
            return "Access denied. Your access has been blocked. Please contact administrator.", 403

        

    # Default if AI fails
    threat_level, score, reason = "LOW", 10, "Default safe"
    if "analysis" in intel:
        text = intel["analysis"]
        # crude parsing (Gemini usually outputs in plain text)
        if "LOW" in text.upper(): threat_level = "LOW"
        elif "MEDIUM" in text.upper(): threat_level = "MEDIUM"
        elif "HIGH" in text.upper(): threat_level = "HIGH"
        elif "CRITICAL" in text.upper(): threat_level = "CRITICAL"

        import re
        match = re.search(r"(\d{1,3})", text)
        if match:
            score = min(100, int(match.group(1)))
        reason = text.strip()



    # Check if IP is blocked
    if is_ip_blocked(ip_address):
        log_security_event(ip_address, username, 'BLOCKED_ACCESS_ATTEMPT', user_agent, 'HIGH', True,reason)
        return "Access denied. Your IP has been blocked.", 403
    
    # Log login attempt
    log_security_event(ip_address, username, 'LOGIN_ATTEMPT',user_agent, reason)
    
    if SECURITY_ENABLED:
        result = security_monitor.analyze_login_attempt(
            ip_address=ip_address,
            username=username,
            password=password,
            user_agent=user_agent,
            timestamp=datetime.now()
        )
        
        if result['action'] == 'redirect_to_honeypot':
            log_security_event(ip_address, username, 'HONEYPOT_REDIRECT', user_agent, 'MEDIUM',reason)
            return redirect(url_for('honeypot_login'))
        elif result['action'] == 'block':
            block_ip(ip_address, 'Suspicious activity detected', duration_hours=24)
            log_security_event(ip_address, username, 'IP_BLOCKED', user_agent, 'HIGH', True,reason)
            return "Access denied. Your IP has been blocked.", 403
        elif result['action'] == 'sql_injection_detected':
            block_ip(ip_address, 'SQL injection attempt', permanent=True)
            log_security_event(ip_address, username, 'SQL_INJECTION', user_agent, 'CRITICAL', True,reason)
            return "Invalid request detected. Incident reported.", 400
    
    # Authenticate using database
    if authenticate_user(username, password):
        session['logged_in'] = True
        session['username'] = username
        log_security_event(ip_address, username, 'LOGIN_SUCCESS', user_agent, 'LOW',reason)
        return redirect(url_for('dashboard'))
    else:
        log_security_event(ip_address, username, 'LOGIN_FAILED', user_agent, 'MEDIUM',reason)
        return render_template('login.html', error='Invalid credentials')

@app.route('/honeypot-login')
def honeypot_login():
    return render_template('honeypot_login.html')

@app.route('/honeypot-submit', methods=['POST'])
def honeypot_submit():
    # Get all info from the user
    ip_address = get_client_ip()  # your helper function
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    user_agent = request.headers.get('User-Agent', '')
    
    # Log everything for your security monitoring
    log_honeypot_interaction(ip_address, username, password, user_agent)
    if SECURITY_ENABLED:
        security_monitor.log_honeypot_interaction(ip_address, username, password)
    # block_ip(ip_address, 'Honeypot interaction', duration_hours=48)
    log_security_event(ip_address, username, 'HONEYPOT_INTERACTION', user_agent, 'HIGH', True)
    
    # Optional delay to simulate processing (~5 seconds)
    delay = 5 + random.uniform(-0.5, 0.5)
    time.sleep(delay)
    
    # Render the fake dashboard page (create honeypot_dashboard.html)
    return render_template('honeypot_dashboard.html', username=username, ip_address=ip_address)


@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    # Get recent security events and stats for dashboard
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Recent attempts count
    cursor.execute('''
        SELECT COUNT(*) as total_attempts FROM security_logs 
        WHERE timestamp >= datetime('now', '-24 hours')
    ''')
    recent_attempts = cursor.fetchone()['total_attempts']
    
    # Blocked attempts count
    cursor.execute('''
        SELECT COUNT(*) as blocked_attempts FROM security_logs 
        WHERE blocked = 1 AND timestamp >= datetime('now', '-24 hours')
    ''')
    blocked_attempts = cursor.fetchone()['blocked_attempts']
    
    # Recent security logs (last 10 entries)
# Get logs with pagination
    cursor.execute('''
        SELECT id, ip_address, username, action, reason, user_agent, timestamp, threat_level, blocked
        FROM security_logs 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''')



    recent_logs = [dict(row) for row in cursor.fetchall()]
    
    # Threat level distribution
    cursor.execute('''
        SELECT threat_level, COUNT(*) as count 
        FROM security_logs 
        WHERE timestamp >= datetime('now', '-24 hours')
        GROUP BY threat_level
    ''')
    threat_stats = {row['threat_level']: row['count'] for row in cursor.fetchall()}
    
    # Active blocked IPs count
    cursor.execute('''
        SELECT COUNT(*) as blocked_ips FROM blocked_ips 
        WHERE is_permanent = 1 OR expires_at > datetime('now')
    ''')
    blocked_ips_count = cursor.fetchone()['blocked_ips']
    
    conn.close()
    
    return render_template('dashboard.html', 
                         recent_attempts=recent_attempts,
                         blocked_attempts=blocked_attempts,
                         recent_logs=recent_logs,
                         threat_stats=threat_stats,
                         blocked_ips_count=blocked_ips_count)

@app.route('/security-logs')
def security_logs():
    """Route to display all security logs"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    # Get pagination parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    filter_level = request.args.get('threat_level', '')
    filter_action = request.args.get('action', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build query with filters
    where_conditions = []
    params = []
    
    if filter_level:
        where_conditions.append('threat_level = ?')
        params.append(filter_level)
    
    if filter_action:
        where_conditions.append('action = ?')
        params.append(filter_action)
    
    where_clause = ''
    if where_conditions:
        where_clause = 'WHERE ' + ' AND '.join(where_conditions)
    
    # Get total count for pagination
    cursor.execute(f'SELECT COUNT(*) FROM security_logs {where_clause}', params)
    total_logs = cursor.fetchone()[0]
    
    # Get logs with pagination
    offset = (page - 1) * per_page
    cursor.execute(f'''
        SELECT id, ip_address, username, action, reason, user_agent, timestamp, threat_level, blocked
        FROM security_logs 
        {where_clause}
        ORDER BY timestamp DESC 
        LIMIT ? OFFSET ?
    ''', params + [per_page, offset])

    
    logs = [dict(row) for row in cursor.fetchall()]
    
    # Get available threat levels and actions for filters
    cursor.execute('SELECT DISTINCT threat_level FROM security_logs ORDER BY threat_level')
    threat_levels = [row['threat_level'] for row in cursor.fetchall()]
    
    cursor.execute('SELECT DISTINCT action FROM security_logs ORDER BY action')
    actions = [row['action'] for row in cursor.fetchall()]
    
    conn.close()
    
    # Calculate pagination info
    total_pages = (total_logs + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('security_logs.html',
                         logs=logs,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         threat_levels=threat_levels,
                         actions=actions,
                         current_threat_filter=filter_level,
                         current_action_filter=filter_action,
                         total_logs=total_logs)

@app.route("/network_logs")
def network_logs():
    """Display network logs - respects USE_LOCAL_LOGS configuration flag"""
    if not USE_LOCAL_LOGS:
        return render_template(
            "network_logs.html",
            network_logs=[],
            page=1,
            total_pages=0,
            has_prev=False,
            has_next=False,
            disabled=True,
            disabled_message="File-based log ingestion is disabled. USE_LOCAL_LOGS=false. Please submit events via POST /api/ingest/event"
        )
    
    all_logs = load_suricata_logs()
    
    # Pagination
    page = request.args.get("page", default=1, type=int)
    total_logs = len(all_logs)
    total_pages = ceil(total_logs / LOGS_PER_PAGE)
    
    start = (page - 1) * LOGS_PER_PAGE
    end = start + LOGS_PER_PAGE
    logs_to_show = all_logs[start:end]

    return render_template(
        "network_logs.html",
        network_logs=logs_to_show,
        page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages
    )

@app.route('/security-report')
def security_report():
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get comprehensive security report from database
    report = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'total_attempts': 0,
        'blocked_ips': 0,
        'honeypot_interactions': 0,
        'threat_levels': {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0},
        'recent_events': []
    }
    
    # Total attempts in last 24 hours
    cursor.execute('SELECT COUNT(*) FROM security_logs WHERE timestamp >= datetime("now", "-24 hours")')
    report['total_attempts'] = cursor.fetchone()[0]
    
    # Blocked IPs count
    cursor.execute('SELECT COUNT(*) FROM blocked_ips WHERE is_permanent = 1 OR expires_at > datetime("now")')
    report['blocked_ips'] = cursor.fetchone()[0]
    
    # Honeypot interactions in last 24 hours
    cursor.execute('SELECT COUNT(*) FROM honeypot_logs WHERE timestamp >= datetime("now", "-24 hours")')
    report['honeypot_interactions'] = cursor.fetchone()[0]
    
    # Threat levels distribution
    cursor.execute('''
        SELECT threat_level, COUNT(*) as count 
        FROM security_logs 
        WHERE timestamp >= datetime("now", "-24 hours")
        GROUP BY threat_level
    ''')
    for row in cursor.fetchall():
        report['threat_levels'][row['threat_level']] = row['count']
    
    # Recent events
    cursor.execute('''
        SELECT ip_address, username, action, timestamp, threat_level 
        FROM security_logs 
        WHERE timestamp >= datetime("now", "-24 hours")
        ORDER BY timestamp DESC 
        LIMIT 10
    ''')
    report['recent_events'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    if SECURITY_ENABLED:
        # Merge with security monitor report if available
        try:
            monitor_report = security_monitor.generate_daily_report()
            report.update(monitor_report)
        except:
            pass
    
    return jsonify(report)

@app.route('/api/logs')
def api_logs():
    """API endpoint to get logs as JSON"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    limit = int(request.args.get('limit', 100))
    threat_level = request.args.get('threat_level', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT id, ip_address, username, action, user_agent, timestamp, threat_level, blocked
        FROM security_logs 
    '''
    params = []
    
    if threat_level:
        query += 'WHERE threat_level = ? '
        params.append(threat_level)
    
    query += 'ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(logs)

@app.route('/api/ingest/event', methods=['POST'])
def api_ingest_event():
    """
    API endpoint for ingesting security events.
    
    Accepts JSON payload with the following structure:
    {
        "source": str (required) - Event source identifier
        "sensor_id": str (required) - Sensor or system identifier
        "timestamp": str (required) - ISO format timestamp
        "data": dict (required) - Event data (event_type, ip_address, etc.)
    }
    
    Returns:
    {
        "status": "success" | "error",
        "message": str,
        "source": str,
        "sensor_id": str
    }
    """
    try:
        # Parse JSON payload
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Content-Type must be application/json"
            }), 400
        
        payload = request.get_json()
        
        # Validate required fields
        required_fields = ['source', 'sensor_id', 'timestamp', 'data']
        missing_fields = [field for field in required_fields if field not in payload]
        
        if missing_fields:
            return jsonify({
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        # Extract metadata
        source = payload.get('source')
        sensor_id = payload.get('sensor_id')
        timestamp = payload.get('timestamp')
        event_data = payload.get('data')
        
        # Validate data is a dict
        if not isinstance(event_data, dict):
            return jsonify({
                "status": "error",
                "message": "Field 'data' must be a JSON object"
            }), 400
        
        # Add metadata to event
        event_data['timestamp'] = timestamp
        event_data['source'] = source
        event_data['sensor_id'] = sensor_id
        
        # Route to ingestion pipeline
        result = ingest_event(event_data)
        
        # Return response with source and sensor_id for tracking
        response = {
            "status": result['status'],
            "message": result['message'],
            "source": source,
            "sensor_id": sensor_id
        }
        
        # Return appropriate HTTP status code
        http_status = 200 if result['status'] == 'success' else 400
        return jsonify(response), http_status
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/admin/users')
def admin_users():
    """Admin endpoint to manage users"""
    if not session.get('logged_in') or session.get('username') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, created_at, last_login, is_active FROM users')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(users)

@app.route('/admin/blocked-ips')
def admin_blocked_ips():
    """Admin endpoint to view blocked IPs"""
    if not session.get('logged_in') or session.get('username') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ip_address, reason, blocked_at, expires_at, is_permanent 
        FROM blocked_ips 
        WHERE is_permanent = 1 OR expires_at > datetime("now")
        ORDER BY blocked_at DESC
    ''')
    blocked_ips = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(blocked_ips)

@app.route('/logout')
def logout():
    ip_address = get_client_ip()
    username = session.get('username', 'Unknown')
    log_security_event(ip_address, username, 'LOGOUT', request.headers.get('User-Agent', ''))
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/status')
def api_status():
    """Get system status including configuration flags"""
    return jsonify({
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "use_local_logs": USE_LOCAL_LOGS,
            "database": DATABASE_PATH,
            "suricata_log_path": SURICATA_LOG_PATH,
            "security_monitoring_enabled": SECURITY_ENABLED
        },
        "features": {
            "file_based_ingestion": USE_LOCAL_LOGS,
            "api_ingestion": True,
            "honeypot": True,
            "threat_analysis": SECURITY_ENABLED
        }
    })

if __name__ == '__main__':
    print("🚀 Starting Adaptive Security System...")
    print(f"📊 Database initialized at: {DATABASE_PATH}")
    print(f"🔧 Configuration: USE_LOCAL_LOGS = {USE_LOCAL_LOGS}")
    
    if USE_LOCAL_LOGS:
        print(f"📁 File-based ingestion ENABLED")
        print(f"   Reading Suricata logs from: {SURICATA_LOG_PATH}")
    else:
        print(f"📁 File-based ingestion DISABLED")
        print(f"   Using API-only mode: POST /api/ingest/event")
    
    if SECURITY_ENABLED:
        threading.Thread(target=security_monitor.start_monitoring, daemon=True).start()
        print("🛡️  Security monitoring started")
    
    print("\n💡 Check /api/status for current configuration")
    app.run(debug=False, host='0.0.0.0', port=8000)
