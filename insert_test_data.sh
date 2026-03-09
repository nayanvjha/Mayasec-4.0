#!/bin/bash
# Test Data Insertion Script for MAYASEC Dashboard
# This script inserts sample security events and alerts into the database

set -e

DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="mayasec"
DB_USER="mayasec"
DB_PASSWORD="mayasec"

echo "🔧 Inserting test data into MAYASEC database..."

# Insert test security logs with various threat levels and event types
psql "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" << EOF

-- Clear existing data (optional - uncomment to reset)
-- DELETE FROM security_logs;
-- DELETE FROM alerts;

-- Insert sample security events (50 events over last 7 days)
INSERT INTO security_logs 
(event_id, event_type, ip_address, username, action, user_agent, threat_level, threat_score, blocked, reason, sensor_id, source, metadata)
VALUES
-- Critical events
('evt-001', 'brute_force_ssh', '192.168.1.100', 'admin', 'login_attempt', 'Mozilla/5.0', 'critical', 95, true, 'Multiple failed SSH logins detected', 'sensor-01', 'ssh_log', '{"attempts": 50}'),
('evt-002', 'sql_injection', '10.0.0.5', 'webapp', 'query_execution', 'SQLMap/1.0', 'critical', 98, true, 'SQL injection attempt in login parameter', 'sensor-02', 'web_firewall', '{"payload": "1 OR 1=1"}'),
('evt-003', 'privilege_escalation', '172.16.0.50', 'user123', 'sudo_command', 'bash', 'critical', 92, true, 'Unauthorized privilege escalation attempt', 'sensor-01', 'auditd', '{"command": "sudo"}'),

-- High severity events
('evt-004', 'port_scan', '203.0.113.45', NULL, 'network_probe', 'nmap', 'high', 78, true, 'Network reconnaissance activity detected', 'sensor-03', 'ids', '{"ports_scanned": 1000}'),
('evt-005', 'suspicious_login', '198.51.100.22', 'john_doe', 'login_attempt', 'curl', 'high', 75, false, 'Login from unusual location (Tokyo)', 'sensor-02', 'auth_log', '{"location": "Tokyo"}'),
('evt-006', 'malware_detection', '192.168.2.15', 'user456', 'file_download', 'Firefox', 'high', 85, true, 'Potential malware file detected', 'sensor-01', 'antivirus', '{"file": "trojan.exe"}'),
('evt-007', 'ddos_attempt', '192.0.2.100', NULL, 'flood_attack', 'HTTP', 'high', 82, true, 'DDoS flood detected', 'sensor-03', 'ids', '{"packets_sec": 5000}'),
('evt-008', 'phishing_email', '203.0.113.88', NULL, 'email_received', 'Thunderbird', 'high', 73, false, 'Phishing email detected with malicious link', 'sensor-02', 'email_gateway', '{"sender": "spoofed@example.com"}'),

-- Medium severity events (20 total)
('evt-009', 'failed_login', '192.168.1.50', 'bob_smith', 'login_attempt', 'ssh', 'medium', 45, false, 'Multiple failed login attempts', 'sensor-01', 'ssh_log', '{"attempts": 5}'),
('evt-010', 'failed_login', '10.0.0.100', 'alice_wonder', 'login_attempt', 'ssh', 'medium', 42, false, 'Multiple failed login attempts', 'sensor-02', 'ssh_log', '{"attempts": 3}'),
('evt-011', 'unusual_traffic', '172.16.0.75', NULL, 'data_transfer', 'HTTP', 'medium', 55, false, 'Unusual outbound traffic to foreign IP', 'sensor-03', 'netflow', '{"bytes": 1000000}'),
('evt-012', 'suspicious_file_access', '192.168.1.120', 'user789', 'file_read', 'bash', 'medium', 50, false, 'Access to sensitive file outside normal hours', 'sensor-01', 'file_integrity', '{"file": "/etc/shadow"}'),
('evt-013', 'weak_password', '10.0.0.55', 'new_user', 'account_creation', 'web_ui', 'medium', 35, false, 'Weak password policy violation', 'sensor-02', 'ldap', '{"password_strength": "weak"}'),
('evt-014', 'certificate_expiry', '192.168.2.50', NULL, 'ssl_check', 'openssl', 'medium', 40, false, 'SSL certificate expiring in 30 days', 'sensor-01', 'certificate_monitor', '{"days_left": 30}'),
('evt-015', 'unauthorized_access', '172.16.0.120', 'guest', 'resource_access', 'web_browser', 'medium', 58, false, 'Attempt to access restricted resource', 'sensor-03', 'web_server', '{"resource": "/admin/panel"}'),
('evt-016', 'suspicious_process', '192.168.1.200', 'system', 'process_execution', 'powershell', 'medium', 52, false, 'Suspicious process behavior detected', 'sensor-02', 'edr', '{"process": "cmd.exe"}'),
('evt-017', 'policy_violation', '10.0.0.200', 'contractor', 'data_copy', 'usb_device', 'medium', 48, true, 'Data exfiltration via USB device blocked', 'sensor-01', 'dlp', '{"data_size": 5000}'),
('evt-018', 'failed_login', '192.168.2.80', 'service_account', 'api_auth', 'curl', 'medium', 38, false, 'Multiple failed API authentication attempts', 'sensor-03', 'api_log', '{"attempts": 10}'),

-- Low severity events (20 total)
('evt-019', 'config_change', '192.168.1.50', 'admin', 'firewall_rule_modification', 'web_ui', 'low', 20, false, 'Firewall rule modified', 'sensor-01', 'syslog', '{"rule": "allow_http"}'),
('evt-020', 'user_enumeration', '10.0.0.75', NULL, 'ldap_query', 'ldapsearch', 'low', 15, false, 'Enumeration of user accounts detected', 'sensor-02', 'directory_server', '{"users_queried": 100}'),
('evt-021', 'port_open', '172.16.0.100', NULL, 'service_start', 'systemd', 'low', 25, false, 'Unexpected port open on internal server', 'sensor-01', 'ids', '{"port": 8080}'),
('evt-022', 'failed_login', '192.168.1.75', 'contractor_bob', 'login_attempt', 'ssh', 'low', 10, false, 'Failed login attempt', 'sensor-03', 'ssh_log', '{"attempts": 1}'),
('evt-023', 'info_access', '10.0.0.150', 'analyst', 'log_view', 'web_ui', 'info', 5, false, 'Normal information access', 'sensor-02', 'audit_log', '{"log_type": "security"}'),
('evt-024', 'patch_available', '192.168.2.100', NULL, 'system_check', 'patch_manager', 'low', 8, false, 'Security patch available for system', 'sensor-01', 'patch_management', '{"patch": "CVE-2024-1234"}'),
('evt-025', 'failed_login', '172.16.0.150', 'user_test', 'login_attempt', 'web_ui', 'low', 12, false, 'Failed login attempt', 'sensor-02', 'auth_log', '{"attempts": 1}'),
('evt-026', 'backup_completed', '192.168.1.100', 'backup_job', 'backup_process', 'backup_service', 'info', 0, false, 'Daily backup completed successfully', 'sensor-01', 'backup_log', '{"size": 10000}'),
('evt-027', 'config_audit', '10.0.0.100', 'auditor', 'config_review', 'audit_tool', 'info', 0, false, 'Configuration audit passed', 'sensor-03', 'audit_log', '{"result": "pass"}'),
('evt-028', 'failed_login', '192.168.2.120', 'old_user', 'login_attempt', 'ssh', 'low', 11, false, 'Failed login attempt', 'sensor-02', 'ssh_log', '{"attempts": 1}'),

-- Additional events to fill dashboard
('evt-029', 'brute_force_ssh', '203.0.113.200', 'root', 'login_attempt', 'ssh', 'critical', 94, true, 'SSH brute force attack detected', 'sensor-01', 'ssh_log', '{"attempts": 100}'),
('evt-030', 'malware_detection', '192.168.1.88', 'user_infected', 'file_download', 'chrome', 'high', 88, true, 'Ransomware signature detected', 'sensor-03', 'antivirus', '{"file": "ransomware.exe"}'),
('evt-031', 'failed_login', '10.0.0.200', 'temp_user', 'login_attempt', 'rdp', 'low', 13, false, 'Failed RDP login attempt', 'sensor-01', 'rdp_log', '{"attempts": 1}'),
('evt-032', 'suspicious_login', '172.16.0.200', 'vip_user', 'login_attempt', 'vpn', 'high', 76, false, 'Login from suspicious location (N. Korea)', 'sensor-02', 'vpn_log', '{"location": "Pyongyang"}'),
('evt-033', 'data_leak', '192.168.2.200', 'insider', 'email_send', 'outlook', 'critical', 99, true, 'Sensitive data sent to external email', 'sensor-01', 'dlp', '{"recipients": 10}'),
('evt-034', 'ddos_attempt', '198.51.100.50', NULL, 'syn_flood', 'TCP', 'high', 81, true, 'SYN flood attack in progress', 'sensor-03', 'ids', '{"packets_sec": 10000}'),
('evt-035', 'failed_login', '192.168.1.150', 'basic_user', 'login_attempt', 'ssh', 'low', 9, false, 'Failed login attempt', 'sensor-02', 'ssh_log', '{"attempts": 1}'),
('evt-036', 'policy_violation', '10.0.0.180', 'manager', 'usb_write', 'usb_device', 'medium', 50, true, 'USB write operation blocked by policy', 'sensor-01', 'dlp', '{"device": "USB_001"}'),
('evt-037', 'failed_login', '172.16.0.180', 'junior_user', 'login_attempt', 'ssh', 'low', 10, false, 'Failed login attempt', 'sensor-03', 'ssh_log', '{"attempts": 1}'),
('evt-038', 'suspicious_process', '192.168.2.150', 'user999', 'process_execution', 'cmd_prompt', 'medium', 54, false, 'Suspicious CMD process execution', 'sensor-02', 'edr', '{"process": "powershell.exe"}'),
('evt-039', 'certificate_validation', '10.0.0.250', NULL, 'cert_check', 'openssl', 'low', 7, false, 'Invalid certificate detected in HTTPS traffic', 'sensor-01', 'ssl_monitor', '{"cert": "self_signed"}'),
('evt-040', 'failed_login', '192.168.1.175', 'demo_user', 'login_attempt', 'web_ui', 'low', 8, false, 'Failed login attempt', 'sensor-02', 'auth_log', '{"attempts": 1}'),
('evt-041', 'port_scan', '203.0.113.100', NULL, 'port_probe', 'nmap', 'high', 79, true, 'Network port scan detected', 'sensor-03', 'ids', '{"ports_scanned": 500}'),
('evt-042', 'failed_login', '172.16.0.175', 'guest_user', 'login_attempt', 'rdp', 'low', 9, false, 'Failed login attempt', 'sensor-01', 'rdp_log', '{"attempts": 1}'),
('evt-043', 'suspicious_login', '192.168.2.175', 'executive', 'login_attempt', 'web_portal', 'high', 74, false, 'Login from traveling executive but from high-risk country', 'sensor-02', 'auth_log', '{"location": "Iran"}'),
('evt-044', 'malware_detection', '10.0.0.125', 'infected_machine', 'file_scan', 'antivirus', 'high', 86, true, 'Botnet malware detected', 'sensor-01', 'antivirus', '{"botnet": "mirai"}'),
('evt-045', 'failed_login', '192.168.1.225', 'service_user', 'api_call', 'curl', 'low', 11, false, 'Failed API call with wrong credentials', 'sensor-03', 'api_log', '{"attempts": 1}'),
('evt-046', 'unusual_traffic', '172.16.0.225', NULL, 'data_exfil', 'TCP', 'medium', 56, false, 'Unusual data transfer to external server', 'sensor-02', 'netflow', '{"bytes": 5000000}'),
('evt-047', 'failed_login', '10.0.0.225', 'legacy_user', 'login_attempt', 'ssh', 'low', 10, false, 'Failed login attempt', 'sensor-01', 'ssh_log', '{"attempts": 1}'),
('evt-048', 'privilege_escalation', '192.168.2.225', 'compromised_user', 'sudo_attempt', 'bash', 'critical', 91, true, 'Privilege escalation blocked', 'sensor-02', 'auditd', '{"command": "sudo su"}'),
('evt-049', 'failed_login', '172.16.0.225', 'contract_worker', 'login_attempt', 'vpn', 'low', 9, false, 'Failed login attempt', 'sensor-03', 'vpn_log', '{"attempts": 1}'),
('evt-050', 'ddos_attempt', '203.0.113.150', NULL, 'http_flood', 'HTTP', 'high', 80, true, 'HTTP DDoS attack detected', 'sensor-01', 'ids', '{"requests_sec": 50000});

-- Insert sample alerts from the events
INSERT INTO alerts 
(rule_id, title, severity, event_ids, ip_address, username, description, metadata, status)
VALUES
('rule-001', 'Critical SSH Brute Force Attack', 'critical', ARRAY['evt-001'], '192.168.1.100', 'admin', 'Multiple failed SSH login attempts detected from single source', '{"threshold": 50}', 'open'),
('rule-002', 'SQL Injection Attack Detected', 'critical', ARRAY['evt-002'], '10.0.0.5', NULL, 'SQL injection attempt blocked at web application firewall', '{"attack_type": "SQLi"}', 'open'),
('rule-003', 'Privilege Escalation Attempt', 'critical', ARRAY['evt-003'], '172.16.0.50', 'user123', 'Unauthorized privilege escalation attempt detected', '{"target": "root"}', 'open'),
('rule-004', 'Network Port Scan Detected', 'high', ARRAY['evt-004'], '203.0.113.45', NULL, 'Reconnaissance activity detected - network port scanning', '{"scan_type": "nmap"}', 'open'),
('rule-005', 'Suspicious Login from Unusual Location', 'high', ARRAY['evt-005'], '198.51.100.22', 'john_doe', 'User login from atypical geographic location detected', '{"distance": "7000km"}', 'acknowledged'),
('rule-006', 'Malware File Download Detected', 'high', ARRAY['evt-006'], '192.168.2.15', 'user456', 'Trojan malware signature detected in downloaded file', '{"file": "trojan.exe"}', 'open'),
('rule-007', 'DDoS Attack in Progress', 'high', ARRAY['evt-007'], '192.0.2.100', NULL, 'Distributed Denial of Service attack detected', '{"attack_type": "flood"}', 'open'),
('rule-008', 'Phishing Email Detected', 'high', ARRAY['evt-008'], '203.0.113.88', NULL, 'Phishing email with malicious link detected in gateway', '{"confidence": 0.95}', 'acknowledged'),
('rule-009', 'Data Exfiltration Attempt', 'critical', ARRAY['evt-033'], '192.168.2.200', 'insider', 'Sensitive data transmission to external address detected and blocked', '{"data_classification": "confidential"}', 'open'),
('rule-010', 'Ransomware Detected', 'high', ARRAY['evt-030'], '192.168.1.88', 'user_infected', 'Ransomware signature detected in file download', '{"ransom_family": "lockbit"}', 'open');

COMMIT;

EOF

echo "✅ Test data inserted successfully!"
echo ""
echo "📊 Data Summary:"
docker-compose exec -T postgres psql -U mayasec -d mayasec -c "
SELECT 
  'Security Logs' as table_name, COUNT(*) as records FROM security_logs
UNION ALL
SELECT 'Alerts', COUNT(*) FROM alerts;
"

echo ""
echo "🎯 Threat Level Distribution:"
docker-compose exec -T postgres psql -U mayasec -d mayasec -c "
SELECT threat_level, COUNT(*) as count 
FROM security_logs 
GROUP BY threat_level 
ORDER BY count DESC;
"

echo ""
echo "🔄 Refresh Grafana dashboard (Cmd+R or Ctrl+R) to see the data!"
