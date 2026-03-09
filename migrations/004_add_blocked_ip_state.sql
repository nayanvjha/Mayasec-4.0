-- Migration: 004_add_blocked_ip_state
-- Purpose: Track block state, correlation_id, and unblock metadata
-- Idempotent: Safe to run multiple times

ALTER TABLE IF EXISTS blocked_ips
ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(255);

ALTER TABLE IF EXISTS blocked_ips
ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;

ALTER TABLE IF EXISTS blocked_ips
ADD COLUMN IF NOT EXISTS unblocked_at TIMESTAMP;

ALTER TABLE IF EXISTS blocked_ips
ADD COLUMN IF NOT EXISTS unblock_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_blocked_ips_active ON blocked_ips(active);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_correlation_id ON blocked_ips(correlation_id);
