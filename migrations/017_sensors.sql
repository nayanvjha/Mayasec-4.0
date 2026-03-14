-- Migration: 017_sensors
-- Purpose: Track lightweight customer-deployed MAYASEC sensors per tenant
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    hostname TEXT NOT NULL,
    mode TEXT NOT NULL,
    version TEXT,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sensors_tenant_host_mode
    ON sensors(tenant_id, hostname, mode);

CREATE INDEX IF NOT EXISTS idx_sensors_tenant_last_seen
    ON sensors(tenant_id, last_seen DESC);

ALTER TABLE sensors ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensors FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'sensors'
          AND policyname = 'tenant_isolation_sensors'
    ) THEN
        CREATE POLICY tenant_isolation_sensors
        ON sensors
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;
