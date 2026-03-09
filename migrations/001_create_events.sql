-- Migration: 001_create_events
-- Purpose: Core event storage tables for security logs, honeypot, and login tracking
-- Idempotent: Safe to run multiple times

-- Security logs (primary event table)
CREATE TABLE IF NOT EXISTS security_logs (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    username VARCHAR(255),
    action VARCHAR(50),
    user_agent TEXT,
    threat_level VARCHAR(20) NOT NULL DEFAULT 'info',
    threat_score INT DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
    blocked BOOLEAN DEFAULT FALSE,
    reason TEXT,
    sensor_id VARCHAR(255) NOT NULL,
    source VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for common queries
CREATE INDEX IF NOT EXISTS idx_security_logs_timestamp ON security_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_logs_threat_level ON security_logs(threat_level);
CREATE INDEX IF NOT EXISTS idx_security_logs_ip_address ON security_logs(ip_address);
CREATE INDEX IF NOT EXISTS idx_security_logs_username ON security_logs(username);
CREATE INDEX IF NOT EXISTS idx_security_logs_sensor_id ON security_logs(sensor_id);
CREATE INDEX IF NOT EXISTS idx_security_logs_event_type ON security_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_security_logs_event_id ON security_logs(event_id);
CREATE INDEX IF NOT EXISTS idx_security_logs_threat_score ON security_logs(threat_score DESC);

-- Honeypot interactions (specialized event table)
CREATE TABLE IF NOT EXISTS honeypot_logs (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address INET NOT NULL,
    username VARCHAR(255),
    password_attempt VARCHAR(255),
    user_agent TEXT,
    sensor_id VARCHAR(255) NOT NULL,
    honeypot_service VARCHAR(50),
    interaction_type VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for honeypot queries
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_timestamp ON honeypot_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_ip_address ON honeypot_logs(ip_address);
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_sensor_id ON honeypot_logs(sensor_id);
CREATE INDEX IF NOT EXISTS idx_honeypot_logs_username ON honeypot_logs(username);

-- Login attempts tracking (detailed auth analytics)
CREATE TABLE IF NOT EXISTS login_attempts (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address INET NOT NULL,
    username VARCHAR(255) NOT NULL,
    attempt_count INT DEFAULT 1,
    success BOOLEAN DEFAULT FALSE,
    user_agent TEXT,
    sensor_id VARCHAR(255) NOT NULL,
    threat_score INT DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for login attempt queries
CREATE INDEX IF NOT EXISTS idx_login_attempts_timestamp ON login_attempts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_address ON login_attempts(ip_address);
CREATE INDEX IF NOT EXISTS idx_login_attempts_username ON login_attempts(username);
CREATE INDEX IF NOT EXISTS idx_login_attempts_success ON login_attempts(success);
CREATE INDEX IF NOT EXISTS idx_login_attempts_sensor_id ON login_attempts(sensor_id);

-- Failed login attempts tracking (brute force detection)
CREATE TABLE IF NOT EXISTS failed_attempts (
    id BIGSERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    username VARCHAR(255),
    attempt_count INT DEFAULT 1,
    last_attempt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    threat_level VARCHAR(20) DEFAULT 'low',
    sensor_id VARCHAR(255) NOT NULL,
    reason TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for failed attempt queries
CREATE INDEX IF NOT EXISTS idx_failed_attempts_ip_address ON failed_attempts(ip_address);
CREATE INDEX IF NOT EXISTS idx_failed_attempts_last_attempt ON failed_attempts(last_attempt DESC);
CREATE INDEX IF NOT EXISTS idx_failed_attempts_username ON failed_attempts(username);

-- Alert history (track threat detection events)
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    alert_type VARCHAR(50) NOT NULL,
    threat_level VARCHAR(20) NOT NULL,
    threat_score INT DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
    description TEXT,
    ip_address INET,
    username VARCHAR(255),
    sensor_id VARCHAR(255) NOT NULL,
    action_taken VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for alert queries
CREATE INDEX IF NOT EXISTS idx_alert_history_timestamp ON alert_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_threat_level ON alert_history(threat_level);
CREATE INDEX IF NOT EXISTS idx_alert_history_alert_type ON alert_history(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_ip_address ON alert_history(ip_address);

-- Network flow events (network traffic analysis)
CREATE TABLE IF NOT EXISTS network_flows (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_ip INET NOT NULL,
    destination_ip INET NOT NULL,
    source_port INT,
    destination_port INT,
    protocol VARCHAR(20),
    bytes_sent BIGINT,
    bytes_received BIGINT,
    duration_ms INT,
    action VARCHAR(50),
    threat_score INT DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
    sensor_id VARCHAR(255) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for network flow queries
CREATE INDEX IF NOT EXISTS idx_network_flows_timestamp ON network_flows(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_network_flows_source_ip ON network_flows(source_ip);
CREATE INDEX IF NOT EXISTS idx_network_flows_destination_ip ON network_flows(destination_ip);
CREATE INDEX IF NOT EXISTS idx_network_flows_protocol ON network_flows(protocol);
CREATE INDEX IF NOT EXISTS idx_network_flows_destination_port ON network_flows(destination_port);

-- Event correlation (multi-event patterns)
CREATE TABLE IF NOT EXISTS event_correlations (
    id BIGSERIAL PRIMARY KEY,
    correlation_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    correlation_type VARCHAR(50) NOT NULL,
    event_ids UUID[],
    ip_address INET,
    username VARCHAR(255),
    sensor_ids VARCHAR(255)[],
    threat_level VARCHAR(20) NOT NULL,
    threat_score INT DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for correlation queries
CREATE INDEX IF NOT EXISTS idx_event_correlations_timestamp ON event_correlations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_event_correlations_type ON event_correlations(correlation_type);
CREATE INDEX IF NOT EXISTS idx_event_correlations_ip_address ON event_correlations(ip_address);
CREATE INDEX IF NOT EXISTS idx_event_correlations_threat_level ON event_correlations(threat_level);
