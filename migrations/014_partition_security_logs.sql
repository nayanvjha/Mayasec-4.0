-- Migration: 014_partition_security_logs
-- Purpose: Prepare monthly partitioned storage for high-volume security logs
-- Idempotent: Safe to run multiple times

DO $$
BEGIN
    IF to_regclass('public.security_logs_partitioned') IS NULL THEN
        CREATE TABLE public.security_logs_partitioned (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            event_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            "timestamp" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ip_address INET,
            username VARCHAR(255),
            action VARCHAR(50),
            user_agent TEXT,
            threat_level VARCHAR(20) NOT NULL DEFAULT 'info',
            threat_score INTEGER DEFAULT 0 CHECK (threat_score >= 0 AND threat_score <= 100),
            blocked BOOLEAN DEFAULT FALSE,
            reason TEXT,
            sensor_id VARCHAR(255) NOT NULL,
            source VARCHAR(50),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            correlation_id VARCHAR(255),
            mitre_ttps JSONB DEFAULT '[]'::jsonb,
            tenant_id UUID
        ) PARTITION BY RANGE ("timestamp");
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_security_logs_partitioned_timestamp
ON public.security_logs_partitioned ("timestamp" DESC);

CREATE INDEX IF NOT EXISTS idx_security_logs_partitioned_tenant_id
ON public.security_logs_partitioned (tenant_id);

CREATE INDEX IF NOT EXISTS idx_security_logs_partitioned_event_type
ON public.security_logs_partitioned (event_type);

CREATE INDEX IF NOT EXISTS idx_security_logs_partitioned_ip_address
ON public.security_logs_partitioned (ip_address);

ALTER TABLE public.security_logs_partitioned ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_logs_partitioned FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'security_logs_partitioned'
          AND policyname = 'tenant_isolation_security_logs_partitioned'
    ) THEN
        CREATE POLICY tenant_isolation_security_logs_partitioned
        ON public.security_logs_partitioned
        FOR ALL
        USING (tenant_id = current_setting('app.tenant_id')::uuid);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.ensure_security_logs_partitions(months_ahead INTEGER DEFAULT 3)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    base_month DATE := date_trunc('month', CURRENT_DATE)::date;
    i INTEGER;
    start_date DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN -1..GREATEST(months_ahead, 3) LOOP
        start_date := (base_month + (i || ' month')::interval)::date;
        end_date := (start_date + interval '1 month')::date;
        partition_name := format('security_logs_%s', to_char(start_date, 'YYYY_MM'));

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.security_logs_partitioned FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            start_date,
            end_date
        );
    END LOOP;
END
$$;

SELECT public.ensure_security_logs_partitions(3);
