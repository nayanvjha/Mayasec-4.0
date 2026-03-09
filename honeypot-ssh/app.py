import os
import socket
import threading
import time
from datetime import datetime
from typing import Optional

import paramiko
import requests

INGESTOR_URL = os.getenv('INGESTOR_URL', 'http://ingestor:5001')
SENSOR_ID = os.getenv('SENSOR_ID', 'honeypot-ssh')
LISTEN_PORT = int(os.getenv('HONEYPOT_PORT', '2222'))
DESTINATION = os.getenv('HONEYPOT_DESTINATION', 'honeypot.ssh')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

HOST_KEY = paramiko.RSAKey.generate(2048)


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _emit_event(source_ip: str, username: Optional[str], method: str) -> None:
    attempted_user = username or 'unknown'
    raw_log = f"{_timestamp()} ssh honeypot auth attempt user={attempted_user} from={source_ip} method={method} result=failed"
    payload = {
        'event_type': 'ssh_honeypot_connection',
        'timestamp': _timestamp(),
        'source': 'honeypot',
        'sensor_id': SENSOR_ID,
        'sensor_type': 'honeypot',
        'source_ip': source_ip,
        'destination': DESTINATION,
        'username': attempted_user,
        'severity': 'high',
        'raw_log': raw_log
    }
    try:
        requests.post(f"{INGESTOR_URL.rstrip('/')}/api/ingest/event", json=payload, timeout=5)
    except Exception:
        pass


class HoneypotSSHServer(paramiko.ServerInterface):
    def __init__(self, source_ip: str):
        self.source_ip = source_ip

    def check_auth_password(self, username, password):
        _emit_event(self.source_ip, username, 'password')
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        _emit_event(self.source_ip, username, 'publickey')
        return paramiko.AUTH_FAILED

    def check_auth_none(self, username):
        _emit_event(self.source_ip, username, 'none')
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell(self, channel):
        return False

    def check_channel_exec_request(self, channel, command):
        return False


def _handle_client(client, addr):
    source_ip = addr[0]
    transport = paramiko.Transport(client)
    transport.add_server_key(HOST_KEY)
    server = HoneypotSSHServer(source_ip)
    try:
        transport.start_server(server=server)
        while transport.is_active():
            time.sleep(0.2)
    except Exception:
        pass
    finally:
        transport.close()
        client.close()


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', LISTEN_PORT))
    sock.listen(100)

    while True:
        client, addr = sock.accept()
        thread = threading.Thread(target=_handle_client, args=(client, addr), daemon=True)
        thread.start()


if __name__ == '__main__':
    main()
