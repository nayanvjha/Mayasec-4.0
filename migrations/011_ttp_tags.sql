-- Migration: 011_ttp_tags
-- Purpose: Add MITRE ATT&CK TTP tagging to security events
-- Idempotent: Safe to run multiple times

ALTER TABLE security_logs ADD COLUMN IF NOT EXISTS mitre_ttps JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_security_logs_mitre_ttps
    ON security_logs USING GIN (mitre_ttps);
