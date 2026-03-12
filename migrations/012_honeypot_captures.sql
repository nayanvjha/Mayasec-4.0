-- Migration: 012_honeypot_captures
-- Purpose: Log full honeypot interactions with LLM persona tracking
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS honeypot_captures (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(64),
    source_ip       INET NOT NULL,
    attack_type     VARCHAR(50),
    request_payload TEXT,
    llm_response    TEXT,
    persona_type    VARCHAR(50),
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_honeypot_captures_source_ip
    ON honeypot_captures(source_ip);

CREATE INDEX IF NOT EXISTS idx_honeypot_captures_captured_at
    ON honeypot_captures(captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_honeypot_captures_attack_type
    ON honeypot_captures(attack_type);
