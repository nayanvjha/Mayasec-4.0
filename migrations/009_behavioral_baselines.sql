-- Migration: 009_behavioral_baselines
-- Purpose: Store per-IP behavioral ML detections for SOC visibility and retraining
-- Idempotent: Safe to run multiple times

CREATE TABLE IF NOT EXISTS behavioral_baselines (
    id              BIGSERIAL PRIMARY KEY,
    source_ip       INET NOT NULL,
    recorded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    intent          VARCHAR(20) DEFAULT 'Benign',
    anomaly_score   DOUBLE PRECISION DEFAULT 0.0,
    graph_threat    BOOLEAN DEFAULT FALSE,
    deception_trigger BOOLEAN DEFAULT FALSE,
    waf_score       INT DEFAULT 0,
    attack_type     VARCHAR(20) DEFAULT 'clean',
    session_id      VARCHAR(64),
    feature_vector  JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_behavioral_baselines_source_ip
    ON behavioral_baselines(source_ip);
CREATE INDEX IF NOT EXISTS idx_behavioral_baselines_recorded_at
    ON behavioral_baselines(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_behavioral_baselines_intent
    ON behavioral_baselines(intent)
    WHERE intent != 'Benign';
CREATE INDEX IF NOT EXISTS idx_behavioral_baselines_graph_threat
    ON behavioral_baselines(graph_threat)
    WHERE graph_threat = TRUE;
