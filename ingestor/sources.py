"""
Ingestor log sources: Suricata eve.json and auth logs.
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Dict, Any

from .normalizer import normalize_event

logger = logging.getLogger('IngestorSources')


SSH_FAILED_REGEX = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"  # syslog ts
    r"(?P<host>[^\s]+)\s+sshd\[\d+\]:\s+"
    r"(?P<msg>Failed password for (invalid user )?(?P<user>[^\s]+) from (?P<ip>\d+\.\d+\.\d+\.\d+).*)"
)

INVALID_USER_REGEX = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>[^\s]+)\s+sshd\[\d+\]:\s+"
    r"(?P<msg>Invalid user (?P<user>[^\s]+) from (?P<ip>\d+\.\d+\.\d+\.\d+).*)"
)

AUTH_FAILURE_REGEX = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>[^\s]+)\s+[^:]+:\s+"
    r"(?P<msg>authentication failure;.*rhost=(?P<ip>\d+\.\d+\.\d+\.\d+).*(user=|user=\?)(?P<user>[^\s;]+)?)"
)


def _parse_syslog_timestamp(ts: str) -> str:
    now = datetime.now().astimezone()
    year = now.year
    try:
        parsed = datetime.strptime(f"{year} {ts}", "%Y %b %d %H:%M:%S")
        parsed = parsed.replace(tzinfo=now.tzinfo)
        if parsed > now and (parsed - now).days > 300:
            parsed = parsed.replace(year=year - 1)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_suricata_line(line: str, sensor_id: str, source: str = 'log_file') -> Optional[Dict[str, Any]]:
    try:
        eve = json.loads(line)
    except Exception:
        logger.warning("Invalid Suricata JSON line; dropped")
        return None

    event_type = eve.get('event_type', 'alert')
    src_ip = eve.get('src_ip')
    dest_ip = eve.get('dest_ip')

    source_data = {
        'event_type': 'network_alert' if event_type in ('alert', 'dns', 'http', 'tls', 'flow') else 'network_flow',
        'timestamp': eve.get('timestamp') or datetime.utcnow().isoformat() + 'Z',
        'source': source,
        'sensor_id': sensor_id,
        'sensor_type': 'suricata',
        'raw_log': line,
        'src_ip': src_ip,
        'dest_ip': dest_ip,
        'src_port': eve.get('src_port'),
        'dest_port': eve.get('dest_port'),
        'proto': eve.get('proto'),
        'action': eve.get('alert', {}).get('action', 'logged') if isinstance(eve.get('alert'), dict) else 'logged',
        'severity': eve.get('alert', {}).get('severity', 'low') if isinstance(eve.get('alert'), dict) else 'low',
        'alert': eve.get('alert') if isinstance(eve.get('alert'), dict) else None,
        'destination': f"{dest_ip}:{eve.get('dest_port')}" if dest_ip and eve.get('dest_port') else dest_ip
    }

    return normalize_event(source_data)


def parse_auth_line(line: str, sensor_id: str, source: str = 'log_file') -> Optional[Dict[str, Any]]:
    for regex in (SSH_FAILED_REGEX, INVALID_USER_REGEX, AUTH_FAILURE_REGEX):
        match = regex.match(line)
        if match:
            ts = _parse_syslog_timestamp(match.group('ts'))
            user = match.group('user')
            ip = match.group('ip')
            msg = match.group('msg')

            source_data = {
                'event_type': 'ssh_failed_login',
                'timestamp': ts,
                'source': source,
                'sensor_id': sensor_id,
                'sensor_type': 'auth',
                'raw_log': line,
                'ip_address': {'source': ip},
                'username': user,
                'action': 'logged',
                'reason': msg,
                'destination': 'ssh'
            }
            return normalize_event(source_data)

    return None


class FileTailer:
    def __init__(self, path: str, on_line: Callable[[str], None], start_from_end: bool = True):
        self.path = path
        self.on_line = on_line
        self.start_from_end = start_from_end
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if not os.path.exists(self.path):
            logger.warning(f"Log path not found: {self.path}")
            return

        with open(self.path, 'r', errors='ignore') as f:
            if self.start_from_end:
                f.seek(0, os.SEEK_END)
            while not self._stop:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                self.on_line(line)


def start_watchers(ingest_func: Callable[[Dict[str, Any]], None]) -> Dict[str, FileTailer]:
    watchers = {}

    suricata_path = os.getenv('SURICATA_EVE_PATH', '/var/log/suricata/eve.json')
    auth_path = os.getenv('AUTH_LOG_PATH', '/var/log/auth.log')
    start_from_end = os.getenv('INGESTOR_START_FROM_END', 'true').lower() == 'true'

    if os.path.exists(suricata_path):
        sensor_id = os.getenv('SURICATA_SENSOR_ID', 'suricata-main')

        def handle_suricata(line: str):
            event = parse_suricata_line(line, sensor_id=sensor_id)
            if event:
                ingest_func(event)

        tailer = FileTailer(suricata_path, handle_suricata, start_from_end=start_from_end)
        thread = threading.Thread(target=tailer.run, daemon=True)
        thread.start()
        watchers['suricata'] = tailer
        logger.info(f"Suricata watcher started: {suricata_path}")

    if os.path.exists(auth_path):
        sensor_id = os.getenv('AUTH_SENSOR_ID', 'auth-main')

        def handle_auth(line: str):
            event = parse_auth_line(line, sensor_id=sensor_id)
            if event:
                ingest_func(event)

        tailer = FileTailer(auth_path, handle_auth, start_from_end=start_from_end)
        thread = threading.Thread(target=tailer.run, daemon=True)
        thread.start()
        watchers['auth'] = tailer
        logger.info(f"Auth watcher started: {auth_path}")

    if not watchers:
        logger.warning("No log watchers started (paths missing)")

    return watchers
