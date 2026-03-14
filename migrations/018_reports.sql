-- Migration: 018_reports
-- Purpose: Add tenant-scoped generated report history and scheduling
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT NOT NULL,
    events_count INTEGER NOT NULL DEFAULT 0,
    attacks_count INTEGER NOT NULL DEFAULT 0,
    mitre_count INTEGER NOT NULL DEFAULT 0,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    report_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_reports_time_window CHECK (end_time >= start_time)
);

CREATE INDEX IF NOT EXISTS idx_reports_tenant_generated_at
    ON reports (tenant_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_reports_tenant_range
    ON reports (tenant_id, start_time DESC, end_time DESC);

ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'reports'
          AND policyname = 'tenant_isolation_reports'
    ) THEN
        CREATE POLICY tenant_isolation_reports
        ON reports
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS report_schedules (
    schedule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    frequency TEXT NOT NULL,
    email TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_report_frequency CHECK (frequency IN ('weekly'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_report_schedules_tenant_frequency_email
    ON report_schedules (tenant_id, frequency, email);

CREATE INDEX IF NOT EXISTS idx_report_schedules_tenant_active
    ON report_schedules (tenant_id, is_active, next_run_at);

ALTER TABLE report_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_schedules FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'report_schedules'
          AND policyname = 'tenant_isolation_report_schedules'
    ) THEN
        CREATE POLICY tenant_isolation_report_schedules
        ON report_schedules
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION update_report_schedule_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_report_schedule_updated_at ON report_schedules;
CREATE TRIGGER trg_report_schedule_updated_at
BEFORE UPDATE ON report_schedules
FOR EACH ROW
EXECUTE FUNCTION update_report_schedule_updated_at();
