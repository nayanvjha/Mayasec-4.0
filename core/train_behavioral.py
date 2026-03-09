"""CLI utility to build benign baseline samples and trigger behavioral model training."""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any

requests = importlib.import_module("requests")

# Ensure project root is importable when script is executed directly.
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from repository import DatabaseConfig, EventRepository

logger = logging.getLogger("train_behavioral")

FEATURE_COLUMNS: tuple[str, ...] = (
    "uri_length",
    "body_length",
    "num_params",
    "has_sql_keywords",
    "has_xss_patterns",
    "user_agent_entropy",
    "user_agent_known_tool",
    "request_rate_60s",
    "hour_of_day",
    "inter_request_interval_ms",
    "uri_path_diversity",
    "body_size_variance",
    "http_method_diversity",
    "ua_change_detected",
    "param_count_variance",
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def _coerce_numeric_or_bool(value: Any) -> float | int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return 1
        if lowered in {"false", "no", "off", "0"}:
            return 0
        try:
            return float(lowered)
        except ValueError:
            return 0
    return 0


def _parse_metadata(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_feature_vector(row: dict[str, Any]) -> dict[str, Any]:
    """Build one behavioral feature vector from a persisted security log row."""
    metadata = _parse_metadata(row)

    features: dict[str, Any] = {}
    for column in FEATURE_COLUMNS:
        # Prefer explicit feature in metadata, then top-level row value, else default 0.
        value = metadata.get(column, row.get(column, 0))
        features[column] = _coerce_numeric_or_bool(value)

    return features


def _build_repository() -> EventRepository:
    db_config = DatabaseConfig(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "mayasec"),
        user=os.getenv("DB_USER", "mayasec"),
        password=os.getenv("DB_PASSWORD", "mayasec_secure_password"),
    )
    return EventRepository(db_config)


def _fetch_benign_logs(repo: EventRepository, days: int) -> list[dict[str, Any]]:
    """Collect threat_level info+low events from repository."""
    logs_info = repo.query_logs(threat_level="info", days=days, limit=100000)
    logs_low = repo.query_logs(threat_level="low", days=days, limit=100000)

    merged: dict[str, dict[str, Any]] = {}
    for row in [*logs_info, *logs_low]:
        event_id = str(row.get("event_id") or "")
        key = event_id if event_id else f"noid:{id(row)}"
        merged[key] = row

    return list(merged.values())


def _post_training_samples(api_url: str, samples: list[dict[str, Any]]) -> Any:
    endpoint = api_url.rstrip("/") + "/api/behavioral/train"
    return requests.post(endpoint, json={"samples": samples}, timeout=30)


def main() -> int:
    _configure_logging()

    parser = argparse.ArgumentParser(description="Train MAYASEC behavioral baseline model")
    parser.add_argument("--min-samples", type=int, default=200, help="Minimum samples required to trigger training")
    parser.add_argument("--days", type=int, default=7, help="How many past days of logs to query")
    args = parser.parse_args()

    min_samples = max(1, args.min_samples)
    days = max(1, args.days)

    core_base_url = os.getenv("CORE_URL", f"http://localhost:{os.getenv('CORE_PORT', '5002')}")

    logger.info("Starting behavioral baseline collection days=%d min_samples=%d", days, min_samples)

    repo: EventRepository | None = None
    try:
        repo = _build_repository()

        if not repo.is_healthy():
            logger.error("Database health check failed")
            print("[ERROR] Database unavailable")
            return 1

        logs = _fetch_benign_logs(repo, days=days)
        logger.info("Fetched %d benign candidates (threat_level in info/low)", len(logs))

        samples = [_extract_feature_vector(row) for row in logs]

        if len(samples) < min_samples:
            logger.warning("Insufficient samples: got=%d required=%d", len(samples), min_samples)
            print(f"[WARN] Not enough baseline samples ({len(samples)}/{min_samples}). Skipping training.")
            return 0

        logger.info("Sending %d samples to behavioral training API", len(samples))

        try:
            response = _post_training_samples(core_base_url, samples)
            response_text = response.text.strip()
            if response.status_code >= 400:
                logger.error("Training API failed status=%d body=%s", response.status_code, response_text)
                print(f"[ERROR] Training request failed ({response.status_code}): {response_text}")
                return 1

            logger.info("Training API success status=%d", response.status_code)
            print(f"[OK] Training response ({response.status_code}): {response_text}")
            return 0

        except requests.RequestException as exc:
            logger.error("Failed to call training API: %s", exc)
            print(f"[ERROR] Could not reach training API: {exc}")
            return 1

    except Exception as exc:
        logger.exception("Unexpected training utility failure: %s", exc)
        print(f"[ERROR] Unexpected failure: {exc}")
        return 1
    finally:
        if repo is not None:
            repo.close_all()


if __name__ == "__main__":
    raise SystemExit(main())
