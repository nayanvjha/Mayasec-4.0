-- Migration: 010_add_confirmed_by
-- Purpose: Add confirmed_by column for analyst/honeypot feedback attribution
-- Idempotent: Safe to run multiple times

ALTER TABLE behavioral_baselines ADD COLUMN IF NOT EXISTS confirmed_by VARCHAR(50) DEFAULT 'system';

CREATE INDEX IF NOT EXISTS idx_behavioral_baselines_confirmed_by
    ON behavioral_baselines(confirmed_by)
    WHERE confirmed_by != 'system';
