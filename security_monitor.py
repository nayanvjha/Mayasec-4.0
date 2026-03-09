import sqlite3
import hashlib
from datetime import datetime, timedelta
import threading
import logging
from collections import defaultdict
from threat_intel import analyze_with_gemini
import time

class SecurityMonitor:
    def fetch_recent_logs(self, hours=1):
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self.lock:
            cursor = self.conn.execute(
                '''
                    SELECT ip_address, username, user_agent, timestamp, attempt_result,
                           threat_level, threat_score, reason
                    FROM login_attempts
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                ''',
                (cutoff,)
            )
            rows = cursor.fetchall()

        logs = []
        for row in rows:
            logs.append({
                "ip_address": row[0],
                "username": row[1],
                "user_agent": row[2],
                "timestamp": row[3],
                "attempt_result": row[4],
                "threat_level": row[5],
                "threat_score": row[6],
                "reason": row[7],
            })
        return logs

    def start_monitoring(self):
        while True:
            logs = self.fetch_recent_logs(hours=1)  # last 1 hour logs
            if logs:  # only analyze if logs exist
                summary = analyze_with_gemini({"recent_logs": logs})
                self.security_logger.info(f"AI Monitoring Summary: {summary}")
            time.sleep(3)  # run every 3 seconds

    def __init__(self):
        self.init_database()
        self.failed_attempts = defaultdict(list)
        self.setup_logging()

    def log_honeypot_interaction(self, ip_address, username, password, user_agent="Unknown"):
            # Just log to console or database
            self.security_logger.info(
                f"Honeypot interaction -> IP: {ip_address}, Username: {username}, Password: {password}, User-Agent: {user_agent}"
            )

    def setup_logging(self):
        self.security_logger = logging.getLogger('SecurityMonitor')
        self.security_logger.setLevel(logging.INFO)
        handler = logging.FileHandler('security_monitor.log')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.security_logger.addHandler(handler)

    def init_database(self):
        self.conn = sqlite3.connect('security_logs.db', check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT,
                    username TEXT,
                    password_hash TEXT,
                    user_agent TEXT,
                    timestamp DATETIME,
                    attempt_result TEXT,
                    threat_level TEXT,
                    threat_score INTEGER,
                    reason TEXT
                )
            ''')
            self.conn.commit()

    def analyze_login_attempt(self, ip_address, username, password, user_agent, timestamp, os="Unknown", location="Unknown", result="FAILED"):
        """
        Analyze login attempt with Gemini AI
        """
        # Track failed attempts
        self.failed_attempts[ip_address].append(timestamp)
        cutoff_time = timestamp - timedelta(hours=1)
        self.failed_attempts[ip_address] = [t for t in self.failed_attempts[ip_address] if t > cutoff_time]
        attempts_last_hour = len(self.failed_attempts[ip_address])

        # Hash password for storage
        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""

        # parameters (tweak as needed)
        HONEYPOT_THRESHOLD = 7        # number of failed attempts in window to redirect
        THRESHOLD_WINDOW_HOURS = 1    # window used above (already used to compute attempts_last_hour)

        # inside analyze_login_attempt(), after computing attempts_last_hour:
        if attempts_last_hour >= HONEYPOT_THRESHOLD:
            # Log into DB and return a redirect action
            reason = f"Exceeded {HONEYPOT_THRESHOLD} failed logins in last {THRESHOLD_WINDOW_HOURS} hour(s)"
            with self.lock:
                self.conn.execute('''
                    INSERT INTO login_attempts 
                    (ip_address, username, password_hash, user_agent, timestamp, attempt_result, threat_level, threat_score, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ip_address, username, password_hash, user_agent, timestamp, "FAILED", "HIGH", 90, reason))
                self.conn.commit()

            self.security_logger.info(f"Threshold triggered -> IP: {ip_address}, Attempts: {attempts_last_hour}")
            return {"action": "redirect_to_honeypot", "threat_level": "HIGH", "score": 90, "reason": reason}

        # Build event for AI
        event = {
            "ip": ip_address,
            "username": username,
            "user_agent": user_agent,
            "timestamp": str(timestamp),
            "os": os,
            "location": location,
            "login_result": result,
            "attempts_last_hour": attempts_last_hour
        }

        ai_result = analyze_with_gemini(event)

        # Default if AI fails
        threat_level, score, reason = "LOW", 10, "Default safe"
        if "analysis" in ai_result:
            text = ai_result["analysis"]
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

        with self.lock:
            self.conn.execute('''
                INSERT INTO login_attempts 
                (ip_address, username, password_hash, user_agent, timestamp, attempt_result, threat_level, threat_score, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ip_address, username, password_hash, user_agent, timestamp, result, threat_level, score, reason))
            self.conn.commit()

        self.security_logger.info(f"AI Analysis -> IP: {ip_address}, Level: {threat_level}, Score: {score}, Reason: {reason}")

        return {"action": "ai_analysis", "threat_level": threat_level, "score": score, "reason": reason}
