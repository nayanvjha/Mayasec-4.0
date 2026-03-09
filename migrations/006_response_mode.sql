-- Migration: 006_response_mode
-- Purpose: Persist response mode state and response decisions
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS response_mode_state (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    mode VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS response_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mode VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    action VARCHAR(50) NOT NULL,
    reason TEXT,
    ip_address INET,
    correlation_id VARCHAR(255),
    event_id UUID,
    threat_level VARCHAR(20),
    threat_score INT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_response_decisions_mode ON response_decisions(mode);
CREATE INDEX IF NOT EXISTS idx_response_decisions_action ON response_decisions(action);
CREATE INDEX IF NOT EXISTS idx_response_decisions_timestamp ON response_decisions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_response_decisions_ip ON response_decisions(ip_address);
