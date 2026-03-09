-- MAYASEC Database Initialization
-- This script creates the schema for the MAYASEC platform

-- Tables
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_logs (
    id SERIAL PRIMARY KEY,
    ip_address INET,
    username VARCHAR(255),
    action VARCHAR(255),
    user_agent TEXT,
    threat_level VARCHAR(50) DEFAULT 'LOW',
    blocked BOOLEAN DEFAULT false,
    reason TEXT,
    sensor_id VARCHAR(255) DEFAULT 'local-sensor',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS honeypot_logs (
    id SERIAL PRIMARY KEY,
    ip_address INET,
    username VARCHAR(255),
    password_attempt VARCHAR(255),
    user_agent TEXT,
    sensor_id VARCHAR(255) DEFAULT 'local-sensor',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blocked_ips (
    id SERIAL PRIMARY KEY,
    ip_address INET UNIQUE,
    reason TEXT,
    is_permanent BOOLEAN DEFAULT false,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY,
    ip_address INET,
    username VARCHAR(255),
    password_hash VARCHAR(255),
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attempt_result VARCHAR(50),
    threat_level VARCHAR(50),
    threat_score INTEGER,
    reason TEXT
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_security_logs_timestamp ON security_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_security_logs_sensor_id ON security_logs(sensor_id);
CREATE INDEX IF NOT EXISTS idx_security_logs_ip ON security_logs(ip_address);
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_timestamp ON honeypot_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_sensor_id ON honeypot_logs(sensor_id);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_ip ON blocked_ips(ip_address);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip_address);
CREATE INDEX IF NOT EXISTS idx_login_attempts_timestamp ON login_attempts(timestamp);

-- Default admin user (password: admin)
INSERT INTO users (username, password_hash, is_active)
VALUES ('admin', 'pbkdf2:sha256:600000$xxx$yyy', true)
ON CONFLICT (username) DO NOTHING;
