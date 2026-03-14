-- Migration: 015_attack_stories
-- Purpose: Persist AI-generated multi-stage attack stories
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS attack_stories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,

  title VARCHAR(255) NOT NULL,

  attacker_ip INET NOT NULL,

  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,

  event_ids UUID[],

  phases JSONB NOT NULL,

  narrative TEXT,

  severity VARCHAR(20) NOT NULL,

  mitre_techniques JSONB,

  status VARCHAR(20) DEFAULT 'active',

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attack_stories_tenant_time
ON attack_stories (tenant_id, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_attack_stories_attacker_ip
ON attack_stories (attacker_ip);

CREATE INDEX IF NOT EXISTS idx_attack_stories_status
ON attack_stories (status);

ALTER TABLE attack_stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE attack_stories FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'attack_stories'
          AND policyname = 'tenant_isolation_attack_stories'
    ) THEN
        CREATE POLICY tenant_isolation_attack_stories
        ON attack_stories
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;
