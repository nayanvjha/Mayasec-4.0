"""
MAYASEC Phase 2 — ML Training Pipeline
Isolation Forest (Anomaly Detection) + XGBoost (Attack Classifier)

Run this script from the ml-service/ directory:
    python training/train.py

Outputs saved to ml-service/models/:
    isolation_forest.pkl
    xgboost_classifier.pkl
    feature_scaler.pkl
    model_metadata.json
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger("phase2_trainer")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.parent
DATASETS_DIR = BASE_DIR / "datasets"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# The 12 core features that the Phase 1 proxy produces on every request.
# These MUST match the keys output by telemetry_mirror.extract_features().
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
    # Derived from dataset-specific columns (mapped during load)
    "byte_ratio",       # bytes_sent / (bytes_received + 1)
    "packet_rate",      # packets / duration (where available)
    "connection_count", # flows from same IP in window (where available)
]

# Label mapping — must match the XGBoost class output
LABEL_MAP = {
    "normal":          0,
    "benign":          0,
    "safe":            0,
    "sqli":            1,
    "sql injection":   1,
    "web attacks-sql injection": 1,
    "xss":             2,
    "cross-site scripting": 2,
    "web attacks-xss": 2,
    "brute force":     3,
    "bruteforce":      3,
    "ssh-bruteforce":  3,
    "ftp-bruteforce":  3,
    "path traversal":  4,
    "lfi":             4,
    "rfi":             4,
    "command injection": 5,
    "cmdi":            5,
    "dos":             6,
    "ddos":            6,
    "botnet":          7,
    "infiltration":    8,
    "portscan":        9,
    "probe":           9,
}

LABEL_NAMES = [
    "normal", "sqli", "xss", "brute_force",
    "path_traversal", "cmdi", "dos", "botnet", "infiltration", "probe"
]


# ---------------------------------------------------------------------------
# Dataset Loaders
# ---------------------------------------------------------------------------

def load_nsl_kdd() -> pd.DataFrame:
    """Load NSL-KDD dataset and map to proxy feature schema."""
    path = DATASETS_DIR / "nsl_kdd" / "KDDTrain+.csv"
    if not path.exists():
        logger.warning("NSL-KDD not found at %s — skipping", path)
        return pd.DataFrame()

    # NSL-KDD columns (41 features + label + difficulty)
    col_names = [
        "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes",
        "land", "wrong_fragment", "urgent", "hot", "num_failed_logins", "logged_in",
        "num_compromised", "root_shell", "su_attempted", "num_root", "num_file_creations",
        "num_shells", "num_access_files", "num_outbound_cmds", "is_host_login",
        "is_guest_login", "count", "srv_count", "serror_rate", "srv_serror_rate",
        "rerror_rate", "srv_rerror_rate", "same_srv_rate", "diff_srv_rate",
        "srv_diff_host_rate", "dst_host_count", "dst_host_srv_count",
        "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
        "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate",
        "dst_host_serror_rate", "dst_host_srv_serror_rate",
        "dst_host_rerror_rate", "dst_host_srv_rerror_rate",
        "label", "difficulty"
    ]

    df = pd.read_csv(path, names=col_names, header=None, low_memory=False)

    # Map to proxy features
    result = pd.DataFrame()
    result["uri_length"]          = (df["src_bytes"] / 10).clip(0, 500).astype(int)
    result["body_length"]         = df["src_bytes"].clip(0, 10000)
    result["num_params"]          = df["hot"].clip(0, 50)
    result["has_sql_keywords"]    = (df["num_shells"] > 0).astype(int)
    result["has_xss_patterns"]    = (df["num_file_creations"] > 0).astype(int)
    result["user_agent_entropy"]  = df["srv_serror_rate"] * 4.0  # proxy entropy
    result["user_agent_known_tool"] = (df["is_guest_login"]).astype(int)
    result["request_rate_60s"]    = df["count"].clip(0, 500)
    result["hour_of_day"]         = 12  # NSL-KDD has no timestamp
    result["byte_ratio"]          = (df["src_bytes"] / (df["dst_bytes"] + 1)).clip(0, 100)
    result["packet_rate"]         = df["srv_count"].clip(0, 500)
    result["connection_count"]    = df["dst_host_count"].clip(0, 500)

    # Normalize label
    result["label"] = df["label"].str.lower().map(
        lambda x: _normalize_label(x)
    )

    logger.info("NSL-KDD loaded: %d rows", len(result))
    return result


def load_cicids(sampled: bool = True) -> pd.DataFrame:
    """Load CIC-IDS-2017 dataset (sampled version)."""
    csv_path = DATASETS_DIR / "cicids2017" / "cicids2017_sampled.csv"
    if not csv_path.exists():
        # Try any CSV in the directory
        csvs = list((DATASETS_DIR / "cicids2017").glob("*.csv"))
        if not csvs:
            logger.warning("CIC-IDS-2017 not found — skipping")
            return pd.DataFrame()
        csv_path = csvs[0]

    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    # Drop infinite and NaN
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)

    result = pd.DataFrame()
    # Map CIC-IDS columns to proxy feature schema
    _safe = lambda col, default=0: df[col] if col in df.columns else default

    result["uri_length"]          = _safe("Total Fwd Packets", 0).clip(0, 500)
    result["body_length"]         = _safe("Total Length of Fwd Packets", 0).clip(0, 100000)
    result["num_params"]          = _safe("Fwd IAT Total", 0).clip(0, 50).astype(int)
    result["has_sql_keywords"]    = 0
    result["has_xss_patterns"]    = 0
    result["user_agent_entropy"]  = (_safe("URG Flag Count", 0) * 0.5).clip(0, 4)
    result["user_agent_known_tool"] = 0
    result["request_rate_60s"]    = _safe("Flow Packets/s", 0).clip(0, 500)
    result["hour_of_day"]         = 12
    result["byte_ratio"]          = (
        _safe("Total Fwd Packets", 1) / (_safe("Total Backward Packets", 1) + 1)
    ).clip(0, 100)
    result["packet_rate"]         = _safe("Flow Packets/s", 0).clip(0, 1000)
    result["connection_count"]    = _safe("Subflow Fwd Packets", 0).clip(0, 500)

    label_col = "Label" if "Label" in df.columns else df.columns[-1]
    result["label"] = df[label_col].str.lower().map(lambda x: _normalize_label(x))

    if sampled and len(result) > 100_000:
        result = result.sample(100_000, random_state=42)

    logger.info("CIC-IDS-2017 loaded: %d rows", len(result))
    return result


def load_payload_dataset() -> pd.DataFrame:
    """
    Construct a feature-vector dataset from raw payload text files.
    Simulates what the proxy's telemetry_mirror would extract
    from HTTP requests containing these payloads.
    """
    records = []

    def _entropy(s: str) -> float:
        if not s:
            return 0.0
        from collections import Counter
        import math
        counts = Counter(s)
        length = len(s)
        return -sum((c / length) * math.log2(c / length) for c in counts.values())

    def _make_record(payload: str, label: int) -> dict:
        p = payload.strip()
        has_sql = any(k in p.lower() for k in ["union", "select", "drop", "insert", "1=1", "or 1"])
        has_xss = any(k in p.lower() for k in ["<script", "javascript:", "onerror="])
        return {
            "uri_length":            len(p),
            "body_length":           len(p),
            "num_params":            p.count("&") + p.count("="),
            "has_sql_keywords":      int(has_sql),
            "has_xss_patterns":      int(has_xss),
            "user_agent_entropy":    _entropy(p[:20]) if p else 0.0,
            "user_agent_known_tool": int(any(t in p.lower() for t in ["sqlmap", "nikto", "nmap"])),
            "request_rate_60s":      10,  # payload dataset: single requests
            "hour_of_day":           14,
            "byte_ratio":            1.0,
            "packet_rate":           1.0,
            "connection_count":      1,
            "label":                 label,
        }

    payload_map = {
        "sqli_payloads.txt":           1,  # SQLi
        "xss_payloads.txt":            2,  # XSS
        "path_traversal_payloads.txt": 4,  # Path Traversal
        "cmdi_payloads.txt":           5,  # Command Injection
    }

    for filename, label in payload_map.items():
        fpath = DATASETS_DIR / "payloads" / filename
        if not fpath.exists():
            continue
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for line in lines:
            records.append(_make_record(line, label))
        logger.info("Payloads loaded from %s: %d rows (label=%d)", filename, len(lines), label)

    # Generate synthetic normal traffic records
    rng = np.random.default_rng(42)
    for _ in range(2000):
        records.append({
            "uri_length":            int(rng.integers(4, 50)),
            "body_length":           int(rng.integers(0, 500)),
            "num_params":            int(rng.integers(0, 5)),
            "has_sql_keywords":      0,
            "has_xss_patterns":      0,
            "user_agent_entropy":    float(rng.uniform(2.5, 4.0)),
            "user_agent_known_tool": 0,
            "request_rate_60s":      int(rng.integers(1, 20)),
            "hour_of_day":           int(rng.integers(7, 22)),
            "byte_ratio":            float(rng.uniform(0.5, 2.0)),
            "packet_rate":           float(rng.uniform(1.0, 10.0)),
            "connection_count":      int(rng.integers(1, 5)),
            "label":                 0,  # normal
        })

    df = pd.DataFrame(records)
    logger.info("Payload dataset total: %d rows", len(df))
    return df


def load_sql_dataset() -> pd.DataFrame:
    """
    Load Modified_SQL_Dataset.csv — vectorized, no row iteration.
    Columns: Query (str), Label (int: 0=clean, 1=malicious)
    """
    path = DATASETS_DIR / "Modified_SQL_Dataset.csv"
    if not path.exists():
        logger.warning("Modified_SQL_Dataset.csv not found — skipping")
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    text_col  = next((c for c in df.columns if c.lower() in ("query", "sentence", "text", "payload")), df.columns[0])
    label_col = next((c for c in df.columns if c.lower() == "label"), df.columns[-1])

    payloads = df[text_col].astype(str)
    raw_labels = pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(int)

    sql_kw = ["union", "select", "drop", "insert", "1=1", "or 1", "sleep", "benchmark"]
    lower  = payloads.str.lower()

    result = pd.DataFrame({
        "uri_length":            payloads.str.len().clip(0, 500),
        "body_length":           payloads.str.len().clip(0, 10000),
        "num_params":            payloads.str.count(r"[&=]"),
        "has_sql_keywords":      lower.apply(lambda x: int(any(k in x for k in sql_kw))),
        "has_xss_patterns":      0,
        "user_agent_entropy":    3.0,
        "user_agent_known_tool": lower.str.contains("sqlmap|havij", regex=True).astype(int),
        "request_rate_60s":      5,
        "hour_of_day":           14,
        "byte_ratio":            1.0,
        "packet_rate":           1.0,
        "connection_count":      1,
        "label":                 raw_labels.map(lambda x: 0 if x == 0 else 1),
    })

    logger.info("SQL dataset loaded: %d rows (sqli=%d, clean=%d)",
                len(result), (result["label"] == 1).sum(), (result["label"] == 0).sum())
    return result


def load_xss_dataset() -> pd.DataFrame:
    """
    Load XSS_dataset.csv — vectorized, no row iteration.
    Columns: Sentence (str), Label (int: 0=benign, 1=xss)
    """
    path = DATASETS_DIR / "XSS_dataset.csv"
    if not path.exists():
        logger.warning("XSS_dataset.csv not found — skipping")
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    text_col  = next((c for c in df.columns if c.lower() in ("sentence", "query", "text", "payload")), df.columns[0])
    label_col = next((c for c in df.columns if c.lower() == "label"), df.columns[-1])

    payloads   = df[text_col].astype(str)
    raw_labels = pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(int)
    lower      = payloads.str.lower()

    xss_kw = r"<script|javascript:|onerror=|onload=|alert\("

    result = pd.DataFrame({
        "uri_length":            payloads.str.len().clip(0, 500),
        "body_length":           payloads.str.len().clip(0, 10000),
        "num_params":            payloads.str.count(r"[&=]"),
        "has_sql_keywords":      0,
        "has_xss_patterns":      lower.str.contains(xss_kw, regex=True).astype(int),
        "user_agent_entropy":    3.0,
        "user_agent_known_tool": 0,
        "request_rate_60s":      5,
        "hour_of_day":           14,
        "byte_ratio":            1.0,
        "packet_rate":           1.0,
        "connection_count":      1,
        "label":                 raw_labels.map(lambda x: 0 if x == 0 else 2),  # 2 = xss
    })

    # Sample to 50k max to avoid dominating the dataset
    if len(result) > 50_000:
        result = result.sample(50_000, random_state=42)

    logger.info("XSS dataset loaded: %d rows (xss=%d, benign=%d)",
                len(result), (result["label"] == 2).sum(), (result["label"] == 0).sum())
    return result


def _normalize_label(raw: str) -> int:
    """Map raw string label to integer class ID."""
    raw = str(raw).lower().strip().rstrip(".")
    for key, val in LABEL_MAP.items():
        if key in raw:
            return val
    return 0  # default: treat unknown as normal


# ---------------------------------------------------------------------------
# Data Pipeline
# ---------------------------------------------------------------------------

def build_dataset() -> Tuple[pd.DataFrame, pd.Series]:
    """Load, clean, and merge all available datasets."""
    frames = [
        load_nsl_kdd(),
        load_cicids(sampled=True),
        load_payload_dataset(),
        load_sql_dataset(),
        load_xss_dataset(),
    ]

    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    logger.info("Combined dataset: %d rows, %d columns", len(df), len(df.columns))

    # Drop rows without a valid label
    df = df[df["label"].notna()].copy()
    df["label"] = df["label"].astype(int)

    # Coerce all feature columns to float
    for col in FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    X = df[FEATURE_COLUMNS].astype(np.float32)
    y = df["label"]

    logger.info("Label distribution:\n%s", y.value_counts().to_string())

    # Drop classes with fewer than 2 samples — stratified split requires ≥2 per class
    class_counts = y.value_counts()
    valid_classes = class_counts[class_counts >= 2].index
    dropped = class_counts[class_counts < 2].index.tolist()
    if dropped:
        logger.warning("Dropping classes with < 2 samples: %s", dropped)
        mask = y.isin(valid_classes)
        X, y = X[mask], y[mask]

    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def apply_oversampling(X_train: np.ndarray, y_train: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Oversample minority classes using numpy repeat (no imblearn dependency).
    Target: bring all classes to at least 2000 samples.
    """
    class_counts = pd.Series(y_train).value_counts()
    TARGET = 2000
    minority = class_counts[class_counts < TARGET].index.tolist()

    if not minority:
        logger.info("Oversampling: all classes already have ≥%d samples", TARGET)
        return X_train, y_train

    X_list, y_list = [X_train], [y_train]
    for cls in minority:
        mask = y_train == cls
        X_cls = X_train[mask]
        n_needed = TARGET - mask.sum()
        if n_needed <= 0 or len(X_cls) == 0:
            continue
        # Repeat existing samples with random jitter (synthetic oversampling)
        rng = np.random.default_rng(42 + int(cls))
        repeats = int(np.ceil(n_needed / len(X_cls)))
        X_rep = np.tile(X_cls, (repeats, 1))[:n_needed]
        # Add small Gaussian noise (5% std) to avoid exact duplicates
        noise = rng.normal(0, X_cls.std(axis=0) * 0.05 + 1e-6, X_rep.shape)
        X_rep = X_rep + noise
        y_rep = np.full(n_needed, cls, dtype=y_train.dtype)
        X_list.append(X_rep)
        y_list.append(y_rep)
        logger.info("Oversampling class %d: %d → %d samples", cls, mask.sum(), mask.sum() + n_needed)

    X_balanced = np.vstack(X_list)
    y_balanced = np.concatenate(y_list)
    logger.info("Oversampling: %d → %d rows", len(X_train), len(X_balanced))
    return X_balanced, y_balanced


def train_isolation_forest(X_normal: np.ndarray) -> IsolationForest:
    """Train Isolation Forest on benign traffic only."""
    logger.info("Training Isolation Forest on %d normal samples...", len(X_normal))
    t0 = time.monotonic()
    model = IsolationForest(
        n_estimators=200,
        max_samples="auto",
        contamination=0.05,   # ~5% contamination assumed
        max_features=1.0,
        bootstrap=False,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_normal)
    elapsed = (time.monotonic() - t0) * 1000
    logger.info("Isolation Forest trained in %.0fms", elapsed)
    return model


def train_xgboost(X_train: np.ndarray, y_train: np.ndarray, n_classes: int) -> XGBClassifier:
    """Train XGBoost multi-class attack classifier."""
    logger.info("Training XGBoost on %d samples, %d classes...", len(X_train), n_classes)
    t0 = time.monotonic()
    model = XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        objective="multi:softprob",
        num_class=n_classes,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    elapsed = (time.monotonic() - t0) * 1000
    logger.info("XGBoost trained in %.0fms", elapsed)
    return model


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(
    iso_model: IsolationForest,
    xgb_model: XGBClassifier,
    scaler: StandardScaler,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> dict:
    """Run combined model evaluation on held-out test set."""
    logger.info("Evaluating on %d test samples...", len(X_test))

    X_scaled = scaler.transform(X_test)

    # -- Isolation Forest --
    # raw_score: negative = inlier (normal), positive = outlier (anomaly)
    iso_scores = iso_model.score_samples(X_scaled)
    iso_predictions = iso_model.predict(X_scaled)  # -1=anomaly, 1=normal
    iso_binary = (iso_predictions == -1).astype(int)  # 1=anomaly

    # -- XGBoost --
    xgb_proba = xgb_model.predict_proba(X_scaled)
    xgb_predictions = np.argmax(xgb_proba, axis=1)
    xgb_confidence = xgb_proba.max(axis=1)

    # -- Combined score (0–100) --
    iso_normalized = np.clip((-iso_scores - iso_scores.min()) /
                             (iso_scores.max() - iso_scores.min() + 1e-9), 0, 1)
    xgb_attack_prob = 1 - xgb_proba[:, 0]  # probability of ANY attack
    combined_score = (iso_normalized * 0.6 + xgb_attack_prob * 0.4) * 100

    # Binary classification for metrics (threshold at 50)
    y_binary_true  = (y_test > 0).astype(int)
    y_binary_pred  = (combined_score >= 50).astype(int)

    precision = precision_score(y_binary_true, y_binary_pred, zero_division=0)
    recall    = recall_score(y_binary_true, y_binary_pred, zero_division=0)
    f1        = f1_score(y_binary_true, y_binary_pred, zero_division=0)
    fp_rate   = (
        ((y_binary_pred == 1) & (y_binary_true == 0)).sum() /
        max((y_binary_true == 0).sum(), 1)
    )

    logger.info("=== EVALUATION RESULTS ===")
    logger.info("Precision:          %.4f  (target > 0.95)", precision)
    logger.info("Recall:             %.4f  (target > 0.90)", recall)
    logger.info("F1 Score:           %.4f  (target > 0.92)", f1)
    logger.info("False Positive Rate:%.4f  (target < 0.005)", fp_rate)

    # XGBoost multi-class report
    present_labels = sorted(y_test.unique())
    label_names_present = [
        LABEL_NAMES[i] if i < len(LABEL_NAMES) else f"class_{i}"
        for i in present_labels
    ]
    logger.info("\nXGBoost classification report:\n%s",
        classification_report(y_test, xgb_predictions,
                               labels=present_labels,
                               target_names=label_names_present,
                               zero_division=0))

    # Latency benchmark
    t0 = time.monotonic()
    sample_batch = X_scaled[:1000]
    for _ in range(10):
        iso_model.score_samples(sample_batch)
        xgb_model.predict_proba(sample_batch)
    latency_ms = (time.monotonic() - t0) / 10 / 1000 * 1000  # ms per batch of 1000
    latency_per_req_ms = latency_ms / 1000
    logger.info("Inference latency: %.3fms per request (target < 10ms)", latency_per_req_ms)

    return {
        "precision":            round(float(precision), 4),
        "recall":               round(float(recall), 4),
        "f1":                   round(float(f1), 4),
        "false_positive_rate":  round(float(fp_rate), 4),
        "latency_per_req_ms":   round(float(latency_per_req_ms), 3),
        "test_samples":         int(len(X_test)),
        "pass_precision":       bool(precision > 0.95),
        "pass_recall":          bool(recall > 0.90),
        "pass_latency":         bool(latency_per_req_ms < 10),
        "pass_fp_rate":         bool(fp_rate < 0.005),
    }


# ---------------------------------------------------------------------------
# Save models
# ---------------------------------------------------------------------------

def save_models(
    iso_model: IsolationForest,
    xgb_model: XGBClassifier,
    scaler: StandardScaler,
    label_encoder: LabelEncoder,
    metrics: dict,
) -> None:
    iso_path    = MODELS_DIR / "isolation_forest.pkl"
    xgb_path    = MODELS_DIR / "xgboost_classifier.pkl"
    scaler_path = MODELS_DIR / "feature_scaler.pkl"
    meta_path   = MODELS_DIR / "model_metadata.json"

    with open(iso_path,    "wb") as f: pickle.dump(iso_model, f, protocol=5)
    with open(xgb_path,    "wb") as f: pickle.dump(xgb_model, f, protocol=5)
    with open(scaler_path, "wb") as f: pickle.dump(scaler, f, protocol=5)

    metadata = {
        "version":         "2.0.0",
        "trained_at":      datetime.now(timezone.utc).isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "label_names":     LABEL_NAMES,
        "score_threshold": 80,
        "iso_weight":      0.6,
        "xgb_weight":      0.4,
        "metrics":         metrics,
        "model_files": {
            "isolation_forest":   str(iso_path),
            "xgboost_classifier": str(xgb_path),
            "feature_scaler":     str(scaler_path),
        },
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Models saved to %s/", MODELS_DIR)
    logger.info("  isolation_forest.pkl:   %.1f MB", iso_path.stat().st_size / 1e6)
    logger.info("  xgboost_classifier.pkl: %.1f MB", xgb_path.stat().st_size / 1e6)
    logger.info("  feature_scaler.pkl:     %.1f KB", scaler_path.stat().st_size / 1e3)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=======================================================")
    logger.info("  MAYASEC Phase 2 — ML Training Pipeline")
    logger.info("  Isolation Forest + XGBoost | %s",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=======================================================")

    # 1. Load datasets
    X, y = build_dataset()
    if len(X) == 0:
        logger.error("No data loaded. Run ml-service/datasets/download.sh first.")
        return

    # 2. Train/test split (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X.values, y.values, test_size=0.2, stratify=y, random_state=42
    )

    # 3. Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # 4. Isolation Forest — train on normal traffic only
    normal_mask = (y_train == 0)
    X_normal_scaled = X_train_scaled[normal_mask]
    iso_model = train_isolation_forest(X_normal_scaled)

    # 5. Apply oversampling (numpy-based, no imblearn dependency)
    X_balanced, y_balanced = apply_oversampling(X_train_scaled, y_train)

    # 6. Encode labels for XGBoost
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_balanced)
    n_classes = len(np.unique(y_encoded))

    # 7. Train XGBoost
    xgb_model = train_xgboost(X_balanced, y_encoded, n_classes)

    # 8. Encode test labels for evaluation
    y_test_series = pd.Series(y_test)

    # 9. Evaluate combined pipeline
    metrics = evaluate(iso_model, xgb_model, scaler, X_test, y_test_series)

    # 10. Save all artifacts
    save_models(iso_model, xgb_model, scaler, le, metrics)

    # Final verdict
    logger.info("")
    all_pass = all([
        metrics["pass_precision"],
        metrics["pass_recall"],
        metrics["pass_latency"],
    ])
    if all_pass:
        logger.info("✅ ALL TARGETS MET — Phase 2 models ready for integration")
    else:
        logger.warning("⚠️  Some targets missed:")
        if not metrics["pass_precision"]: logger.warning("  Precision %.4f < 0.95", metrics["precision"])
        if not metrics["pass_recall"]:    logger.warning("  Recall %.4f < 0.90", metrics["recall"])
        if not metrics["pass_latency"]:   logger.warning("  Latency %.3fms > 10ms", metrics["latency_per_req_ms"])
        logger.warning("  → Consider: more training data, feature engineering, or threshold tuning")


if __name__ == "__main__":
    main()
