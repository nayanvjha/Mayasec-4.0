"""
MAYASEC Phase 2 — ML Scoring Service (FastAPI)
===============================================
Serves the trained Isolation Forest + XGBoost models via HTTP.
Receives 12-field feature vectors from the ingress proxy and returns
a 0–100 risk score in < 10ms.

Endpoints:
  POST /score        — main scoring endpoint
  GET  /health       — readiness probe
  GET  /model/info   — model metadata
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger("ml_service")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "80"))

# Feature column order — MUST match training/train.py FEATURE_COLUMNS
FEATURE_COLUMNS = [
    "uri_length",
    "body_length",
    "num_params",
    "has_sql_keywords",
    "has_xss_patterns",
    "user_agent_entropy",
    "user_agent_known_tool",
    "request_rate_60s",
    "hour_of_day",
    "byte_ratio",
    "packet_rate",
    "connection_count",
]

LABEL_NAMES = [
    "normal", "sqli", "xss", "brute_force",
    "path_traversal", "cmdi", "dos", "botnet", "infiltration", "probe",
]

# Isolation Forest calibration range — from offline analysis of training data
_ISO_MIN = -0.5
_ISO_MAX = 0.1

# ---------------------------------------------------------------------------
# Global model holders (loaded once at startup)
# ---------------------------------------------------------------------------
_iso_model: Any = None
_xgb_model: Any = None
_scaler: Any = None
_metadata: dict = {}
_models_healthy: bool = False
_startup_time: float = time.monotonic()


def _load_pickle(path: Path, name: str) -> Any:
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
        logger.info("Loaded %s from %s (%.1f MB)", name, path, path.stat().st_size / 1e6)
        return obj
    except Exception as exc:
        logger.error("FAILED to load %s from %s: %s", name, path, exc)
        return None


# ---------------------------------------------------------------------------
# Lifespan — load models at startup, release at shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _iso_model, _xgb_model, _scaler, _metadata, _models_healthy

    t0 = time.monotonic()
    _iso_model = _load_pickle(MODELS_DIR / "isolation_forest.pkl", "IsolationForest")
    _xgb_model = _load_pickle(MODELS_DIR / "xgboost_classifier.pkl", "XGBClassifier")
    _scaler = _load_pickle(MODELS_DIR / "feature_scaler.pkl", "StandardScaler")

    meta_path = MODELS_DIR / "model_metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            _metadata = json.load(f)

    _models_healthy = all(m is not None for m in (_iso_model, _xgb_model, _scaler))
    status = "✅ ALL MODELS LOADED" if _models_healthy else "⚠️  SOME MODELS MISSING — fail-open active"
    logger.info("%s in %.0fms", status, (time.monotonic() - t0) * 1000)

    yield  # server is running

    logger.info("ML service shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MAYASEC ML Scoring Service",
    description="Real-time behavioral ML scoring — Isolation Forest + XGBoost",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class FeatureVector(BaseModel):
    source_ip: str = "0.0.0.0"
    http_verb: str = "GET"
    uri: str = "/"
    uri_length: int = 0
    body_length: int = 0
    num_params: int = 0
    has_sql_keywords: bool = False
    has_xss_patterns: bool = False
    user_agent_entropy: float = 0.0
    user_agent_known_tool: bool = False
    request_rate_60s: int = 0
    hour_of_day: int = 12
    # Derived fields — default to neutral values if not provided
    byte_ratio: float = Field(default=1.0)
    packet_rate: float = Field(default=1.0)
    connection_count: int = Field(default=1)


_FAIL_OPEN_RESPONSE = {
    "score": 0,
    "is_malicious": False,
    "attack_type": "unknown",
    "isolation_anomaly": 0.0,
    "xgboost_confidence": 0.0,
    "latency_ms": 0.0,
}


def _extract_feature_row(fv: FeatureVector) -> np.ndarray:
    """Convert Pydantic model to ordered numpy row matching FEATURE_COLUMNS."""
    mapping = {
        "uri_length":            fv.uri_length,
        "body_length":           fv.body_length,
        "num_params":            fv.num_params,
        "has_sql_keywords":      float(fv.has_sql_keywords),
        "has_xss_patterns":      float(fv.has_xss_patterns),
        "user_agent_entropy":    fv.user_agent_entropy,
        "user_agent_known_tool": float(fv.user_agent_known_tool),
        "request_rate_60s":      fv.request_rate_60s,
        "hour_of_day":           fv.hour_of_day,
        "byte_ratio":            fv.byte_ratio,
        "packet_rate":           fv.packet_rate,
        "connection_count":      fv.connection_count,
    }
    row = [float(mapping.get(col, 0.0)) for col in FEATURE_COLUMNS]
    return np.array(row, dtype=np.float32).reshape(1, -1)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/score")
def score(fv: FeatureVector):
    """Score a single feature vector. Always returns HTTP 200 (fail-open)."""
    t0 = time.monotonic()

    if not _models_healthy:
        return JSONResponse(content={**_FAIL_OPEN_RESPONSE, "latency_ms": 0.0})

    try:
        X = _extract_feature_row(fv)
        X_scaled = _scaler.transform(X)

        # Isolation Forest
        iso_raw = float(_iso_model.score_samples(X_scaled)[0])
        iso_norm = float(np.clip((iso_raw - _ISO_MIN) / (_ISO_MAX - _ISO_MIN + 1e-9), 0.0, 1.0))

        # XGBoost
        proba = _xgb_model.predict_proba(X_scaled)[0]
        attack_proba = float(1.0 - proba[0])
        xgb_confidence = float(proba.max())
        attack_class_idx = int(proba.argmax())

        # Map XGBoost class index back to label — handle label encoder remapping
        n_labels = len(LABEL_NAMES)
        attack_type = LABEL_NAMES[attack_class_idx] if attack_class_idx < n_labels else f"class_{attack_class_idx}"
        if attack_class_idx == 0:
            attack_type = "normal"

        # Combine
        combined = (iso_norm * 0.6) + (attack_proba * 0.4)
        final_score = int(np.clip(round(combined * 100), 0, 100))
        latency_ms = (time.monotonic() - t0) * 1000.0

        return JSONResponse(content={
            "score":              final_score,
            "is_malicious":       final_score >= SCORE_THRESHOLD,
            "attack_type":        attack_type if final_score >= SCORE_THRESHOLD else "normal",
            "isolation_anomaly":  round(iso_norm, 4),
            "xgboost_confidence": round(xgb_confidence, 4),
            "latency_ms":         round(latency_ms, 2),
        })

    except Exception as exc:
        logger.exception("Scoring error (fail-open): %s", exc)
        return JSONResponse(content={**_FAIL_OPEN_RESPONSE, "latency_ms": round((time.monotonic() - t0) * 1000, 2)})


@app.get("/health")
def health():
    """Readiness probe — HTTP 503 if any model failed to load."""
    uptime = round(time.monotonic() - _startup_time, 1)
    body = {
        "status":              "healthy" if _models_healthy else "degraded",
        "models_loaded":       _models_healthy,
        "isolation_forest":    _iso_model is not None,
        "xgboost_classifier":  _xgb_model is not None,
        "feature_scaler":      _scaler is not None,
        "model_version":       _metadata.get("version", "unknown"),
        "uptime_seconds":      uptime,
    }
    return JSONResponse(content=body, status_code=200 if _models_healthy else 503)


@app.get("/model/info")
def model_info():
    """Return full model_metadata.json contents."""
    if not _metadata:
        return JSONResponse(content={"error": "metadata not found"}, status_code=404)
    return JSONResponse(content=_metadata)


@app.get("/")
def root():
    return JSONResponse(content={"service": "mayasec-ml", "version": "2.0.0", "status": "running"})
