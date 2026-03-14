-- Migration: 013_saas_tenants
-- Purpose: Add secure multi-tenant SaaS foundations with PostgreSQL RLS
-- Idempotent: Safe to run multiple times

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    stripe_customer_id VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_prefix VARCHAR(8) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    label VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_prefix
ON api_keys(key_prefix);

CREATE TABLE IF NOT EXISTS tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'analyst',
    auth_provider_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_user_unique
ON tenant_users(tenant_id, email);

DO $$
DECLARE
    tenant_tables TEXT[] := ARRAY[
        'security_logs',
        'honeypot_captures',
        'honeypot_logs',
        'login_attempts',
        'blocked_ips',
        'failed_attempts',
        'alert_history',
        'network_flows',
        'event_correlations'
    ];
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY tenant_tables LOOP
        IF to_regclass(tbl) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id UUID', tbl);
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(tenant_id)', 'idx_' || tbl || '_tenant_id', tbl);
        END IF;
    END LOOP;
END
$$;

DO $$
DECLARE
    tenant_tables TEXT[] := ARRAY[
        'security_logs',
        'honeypot_captures',
        'honeypot_logs',
        'login_attempts',
        'blocked_ips',
        'failed_attempts',
        'alert_history',
        'network_flows',
        'event_correlations'
    ];
    tbl TEXT;
    policy_name TEXT;
BEGIN
    FOREACH tbl IN ARRAY tenant_tables LOOP
        IF to_regclass(tbl) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl);

            policy_name := 'tenant_isolation_' || tbl;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = tbl
                  AND policyname = policy_name
            ) THEN
                EXECUTE format(
                    'CREATE POLICY %I ON %I FOR ALL USING (tenant_id = current_setting(''app.tenant_id'')::uuid)',
                    policy_name,
                    tbl
                );
            END IF;
        END IF;
    END LOOP;
END
$$;

INSERT INTO tenants(name, slug, plan)
VALUES ('Mayasec Demo', 'demo', 'enterprise')
ON CONFLICT (slug) DO NOTHING;

DO $$
DECLARE
    demo_tenant_id UUID;
    raw_api_key TEXT;
    generated_prefix TEXT;
BEGIN
    SELECT id INTO demo_tenant_id
    FROM tenants
    WHERE slug = 'demo'
    LIMIT 1;

    IF demo_tenant_id IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM api_keys
           WHERE tenant_id = demo_tenant_id
             AND label = 'Default Demo Key'
       ) THEN
        raw_api_key := encode(gen_random_bytes(32), 'hex');
        generated_prefix := left(raw_api_key, 8);

        INSERT INTO api_keys (tenant_id, key_prefix, key_hash, label, is_active)
        VALUES (
            demo_tenant_id,
            generated_prefix,
            crypt(raw_api_key, gen_salt('bf')),
            'Default Demo Key',
            true
        )
        ON CONFLICT (key_prefix) DO NOTHING;

        IF FOUND THEN
            RAISE NOTICE 'Default API Key: %', raw_api_key;
        END IF;
    END IF;
END
$$;
