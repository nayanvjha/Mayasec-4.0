-- Migration: 016_attacker_sessions
-- Purpose: Persistent attacker memory and evolving deception environment state
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS attacker_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    source_ip INET NOT NULL,
    attacker_profile JSONB DEFAULT '{}'::jsonb,
    environment_state JSONB DEFAULT '{}'::jsonb,
    interaction_count INT DEFAULT 0,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attacker_sessions_tenant_session
    ON attacker_sessions(tenant_id, session_id);

CREATE INDEX IF NOT EXISTS idx_attacker_sessions_tenant_active
    ON attacker_sessions(tenant_id, is_active, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_attacker_sessions_source_ip
    ON attacker_sessions(source_ip);

CREATE INDEX IF NOT EXISTS idx_attacker_sessions_profile_gin
    ON attacker_sessions USING GIN (attacker_profile);

CREATE INDEX IF NOT EXISTS idx_attacker_sessions_environment_gin
    ON attacker_sessions USING GIN (environment_state);

ALTER TABLE attacker_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attacker_sessions FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'attacker_sessions'
          AND policyname = 'tenant_isolation_attacker_sessions'
    ) THEN
        CREATE POLICY tenant_isolation_attacker_sessions
        ON attacker_sessions
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;
