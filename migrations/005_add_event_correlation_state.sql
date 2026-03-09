-- Migration: 005_add_event_correlation_state
-- Purpose: Ensure correlation state storage and constraints
-- Idempotent: Safe to run multiple times

-- Ensure correlation_id is not duplicated across sessions
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_correlations_correlation_id
ON event_correlations(correlation_id);

-- Add destination to metadata for query
-- (stored in JSONB metadata; no schema change)
