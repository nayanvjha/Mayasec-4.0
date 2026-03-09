-- Migration: 002_create_alerts
-- Purpose: Alert management, rules, actions, and IP blocking
-- Idempotent: Safe to run multiple times

-- Alert rules (detection rule definitions)
CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(255) NOT NULL UNIQUE,
    rule_name VARCHAR(255) NOT NULL,
    description TEXT,
    rule_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    condition_json JSONB NOT NULL,
    threshold_value INT DEFAULT 1,
    threshold_window_minutes INT DEFAULT 60,
    actions VARCHAR(50)[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for rule queries
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_rules_rule_type ON alert_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_alert_rules_severity ON alert_rules(severity);

-- Alerts (individual alert events)
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    rule_id VARCHAR(255) NOT NULL REFERENCES alert_rules(rule_id),
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_id UUID,
    event_ids UUID[],
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    ip_address INET,
    username VARCHAR(255),
    sensor_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'open',
    assigned_to VARCHAR(255),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for alert queries
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_ip_address ON alerts(ip_address);
CREATE INDEX IF NOT EXISTS idx_alerts_username ON alerts(username);
CREATE INDEX IF NOT EXISTS idx_alerts_sensor_id ON alerts(sensor_id);

-- Alert actions (response actions taken)
CREATE TABLE IF NOT EXISTS alert_actions (
    id BIGSERIAL PRIMARY KEY,
    action_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alerts(alert_id),
    action_type VARCHAR(50) NOT NULL,
    target_ip INET,
    target_username VARCHAR(255),
    action_description TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    executed_at TIMESTAMP,
    result_json JSONB,
    executed_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for action queries
CREATE INDEX IF NOT EXISTS idx_alert_actions_alert_id ON alert_actions(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_actions_action_type ON alert_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_alert_actions_status ON alert_actions(status);
CREATE INDEX IF NOT EXISTS idx_alert_actions_target_ip ON alert_actions(target_ip);

-- Blocked IPs (IP-based blocking and reputation)
CREATE TABLE IF NOT EXISTS blocked_ips (
    id SERIAL PRIMARY KEY,
    ip_address INET NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    is_permanent BOOLEAN DEFAULT FALSE,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    block_count INT DEFAULT 1,
    last_blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    threat_level VARCHAR(20) DEFAULT 'medium',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for blocked IP queries
CREATE INDEX IF NOT EXISTS idx_blocked_ips_ip_address ON blocked_ips(ip_address);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_expires_at ON blocked_ips(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_blocked_ips_is_permanent ON blocked_ips(is_permanent);

-- Blocked users (user-based blocking)
CREATE TABLE IF NOT EXISTS blocked_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    is_permanent BOOLEAN DEFAULT FALSE,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    block_count INT DEFAULT 1,
    last_blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    threat_level VARCHAR(20) DEFAULT 'medium',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for blocked user queries
CREATE INDEX IF NOT EXISTS idx_blocked_users_username ON blocked_users(username);
CREATE INDEX IF NOT EXISTS idx_blocked_users_expires_at ON blocked_users(expires_at) WHERE expires_at IS NOT NULL;

-- Alert escalations (escalation tracking)
CREATE TABLE IF NOT EXISTS alert_escalations (
    id BIGSERIAL PRIMARY KEY,
    escalation_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alerts(alert_id),
    escalation_level INT NOT NULL,
    escalated_by VARCHAR(255),
    escalated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    escalated_to VARCHAR(255),
    reason TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for escalation queries
CREATE INDEX IF NOT EXISTS idx_alert_escalations_alert_id ON alert_escalations(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_escalations_escalation_level ON alert_escalations(escalation_level);

-- Response playbooks (automated response procedures)
CREATE TABLE IF NOT EXISTS response_playbooks (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(255) NOT NULL UNIQUE,
    playbook_name VARCHAR(255) NOT NULL,
    description TEXT,
    trigger_rule_ids VARCHAR(255)[],
    enabled BOOLEAN DEFAULT TRUE,
    actions JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for playbook queries
CREATE INDEX IF NOT EXISTS idx_response_playbooks_enabled ON response_playbooks(enabled);

-- IP reputation tracking
CREATE TABLE IF NOT EXISTS ip_reputation (
    id SERIAL PRIMARY KEY,
    ip_address INET NOT NULL UNIQUE,
    reputation_score INT DEFAULT 0 CHECK (reputation_score >= 0 AND reputation_score <= 100),
    confidence_score DECIMAL(3, 2) DEFAULT 0.5,
    threat_indicators VARCHAR(50)[],
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_count INT DEFAULT 0,
    is_internal BOOLEAN DEFAULT FALSE,
    is_whitelisted BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for IP reputation queries
CREATE INDEX IF NOT EXISTS idx_ip_reputation_ip_address ON ip_reputation(ip_address);
CREATE INDEX IF NOT EXISTS idx_ip_reputation_reputation_score ON ip_reputation(reputation_score DESC);
CREATE INDEX IF NOT EXISTS idx_ip_reputation_is_whitelisted ON ip_reputation(is_whitelisted);
CREATE INDEX IF NOT EXISTS idx_ip_reputation_last_seen ON ip_reputation(last_seen DESC);
