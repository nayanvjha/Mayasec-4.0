"""Background retraining scheduler for MAYASEC behavioral anomaly model."""

from __future__ import annotations

import logging
import threading
import time
import importlib
from datetime import datetime, timezone
from typing import Any, Callable, Optional

sklearn_ensemble = importlib.import_module("sklearn.ensemble")
sklearn_pipeline = importlib.import_module("sklearn.pipeline")
sklearn_preprocessing = importlib.import_module("sklearn.preprocessing")

IsolationForest = sklearn_ensemble.IsolationForest
Pipeline = sklearn_pipeline.Pipeline
StandardScaler = sklearn_preprocessing.StandardScaler

logger = logging.getLogger(__name__)

# Scheduler wake-up interval.
RETRAIN_INTERVAL_HOURS = 1

# Retrain trigger threshold for new baseline samples.
NEW_SAMPLE_THRESHOLD = 500

# Upper bound to keep retrain batches bounded and lightweight.
MAX_TRAINING_SAMPLES = 10000


class RetrainScheduler(threading.Thread):
    """Daemon thread that periodically retrains the behavioral model in the background."""

    def __init__(
        self,
        behavioral_scorer: Any,
        drift_detector: Any,
        event_repo: Any,
        websocket_emitter: Optional[Callable[[str, dict], None]] = None,
        interval_hours: float = RETRAIN_INTERVAL_HOURS,
    ) -> None:
        super().__init__(name="RetrainScheduler")
        self.daemon = True

        self.behavioral_scorer = behavioral_scorer
        self.drift_detector = drift_detector
        self.event_repo = event_repo
        self.websocket_emitter = websocket_emitter

        self.interval_hours = max(0.01, float(interval_hours))
        self._model_lock = threading.Lock()
        self._stop_event = threading.Event()

        self._last_trained_id = self._get_latest_sample_id()

    def stop(self) -> None:
        """Request graceful scheduler stop."""
        self._stop_event.set()

    def run(self) -> None:
        """Main scheduler loop. Never raises into caller thread."""
        sleep_seconds = self.interval_hours * 3600.0

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("RetrainScheduler loop error: %s", exc)

            # Interruptible sleep for responsive shutdown.
            self._stop_event.wait(timeout=sleep_seconds)

    def _tick(self) -> None:
        """Check retrain conditions and execute retraining if required."""
        drift_triggered = self._drift_needs_retrain()
        new_sample_count = self._count_new_samples()

        if not drift_triggered and new_sample_count < NEW_SAMPLE_THRESHOLD:
            return

        features, latest_id = self._fetch_training_vectors(limit=MAX_TRAINING_SAMPLES)
        if not features:
            logger.info("RetrainScheduler skipped: no usable behavioral baseline samples")
            return

        pipeline = self._train_isolation_forest(features)

        with self._model_lock:
            self.behavioral_scorer.pipeline = pipeline

        self._last_trained_id = max(self._last_trained_id, latest_id)

        try:
            self.drift_detector.reset()
        except Exception as exc:
            logger.warning("RetrainScheduler drift reset failed: %s", exc)

        payload = {
            "event": "model_retrained",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "samples_used": len(features),
        }
        self._emit_websocket_event("model_retrained", payload)

        logger.info(
            "Behavioral model retrained samples_used=%d drift_triggered=%s new_samples=%d latest_id=%d",
            len(features),
            drift_triggered,
            new_sample_count,
            self._last_trained_id,
        )

    def _drift_needs_retrain(self) -> bool:
        """Support either drift_detector.needs_retrain() or .needs_retraining()."""
        try:
            method = getattr(self.drift_detector, "needs_retrain", None)
            if callable(method):
                return bool(method())

            method = getattr(self.drift_detector, "needs_retraining", None)
            if callable(method):
                return bool(method())
        except Exception as exc:
            logger.warning("RetrainScheduler drift check failed: %s", exc)

        return False

    def _emit_websocket_event(self, event_name: str, payload: dict) -> None:
        """Best-effort websocket event emission via injected broadcaster callback."""
        if self.websocket_emitter is None:
            return

        try:
            self.websocket_emitter(event_name, payload)
        except Exception as exc:
            logger.warning("RetrainScheduler websocket emit failed: %s", exc)

    def _get_latest_sample_id(self) -> int:
        """Initialize watermark to current max baseline id to count only newly added samples."""
        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM behavioral_baselines")
            row = cursor.fetchone()
            cursor.close()
            return int(row[0]) if row else 0
        except Exception as exc:
            logger.warning("RetrainScheduler failed to read latest baseline id: %s", exc)
            return 0
        finally:
            if conn is not None:
                self.event_repo.return_connection(conn)

    def _count_new_samples(self) -> int:
        """Count new baseline samples since last successful retraining."""
        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM behavioral_baselines WHERE id > %s",
                (self._last_trained_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            return int(row[0]) if row else 0
        except Exception as exc:
            logger.warning("RetrainScheduler failed to count new baseline samples: %s", exc)
            return 0
        finally:
            if conn is not None:
                self.event_repo.return_connection(conn)

    def _fetch_training_vectors(self, limit: int = MAX_TRAINING_SAMPLES) -> tuple[list[list[float]], int]:
        """Fetch recent training vectors from behavioral_baselines."""
        conn = None
        try:
            conn = self.event_repo.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, feature_vector, intent
                FROM behavioral_baselines
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cursor.fetchall()
            cursor.close()

            features: list[list[float]] = []
            latest_id = self._last_trained_id

            for row in rows:
                sample_id = int(row[0])
                feature_vector = row[1]
                # Intent label is optional for IsolationForest training; fetched for compatibility.
                _intent = row[2] if len(row) > 2 else None

                vector = self._normalize_feature_vector(feature_vector)
                if vector is None:
                    continue

                features.append(vector)
                if sample_id > latest_id:
                    latest_id = sample_id

            return features, latest_id
        except Exception as exc:
            logger.warning("RetrainScheduler failed to fetch baseline vectors: %s", exc)
            return [], self._last_trained_id
        finally:
            if conn is not None:
                self.event_repo.return_connection(conn)

    @staticmethod
    def _normalize_feature_vector(value: Any) -> Optional[list[float]]:
        """Convert stored vector payload into a numeric list accepted by sklearn."""
        if isinstance(value, dict):
            # Deterministic order for dict payloads.
            items = [value[key] for key in sorted(value.keys())]
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            return None

        out: list[float] = []
        for item in items:
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                out.append(0.0)

        return out if out else None

    @staticmethod
    def _train_isolation_forest(features: list[list[float]]) -> Pipeline:
        """Train a fresh IsolationForest pipeline for anomaly detection."""
        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "isolation_forest",
                    IsolationForest(
                        n_estimators=200,
                        contamination="auto",
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        )
        pipeline.fit(features)
        return pipeline
