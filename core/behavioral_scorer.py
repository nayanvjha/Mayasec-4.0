"""Behavioral anomaly scoring using an Isolation Forest pipeline."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

np = importlib.import_module("numpy")

joblib = importlib.import_module("joblib")
sklearn_ensemble = importlib.import_module("sklearn.ensemble")
sklearn_pipeline = importlib.import_module("sklearn.pipeline")
sklearn_preprocessing = importlib.import_module("sklearn.preprocessing")

IsolationForest = sklearn_ensemble.IsolationForest
Pipeline = sklearn_pipeline.Pipeline
StandardScaler = sklearn_preprocessing.StandardScaler

logger = logging.getLogger(__name__)

_FEATURE_COLUMNS: tuple[str, ...] = (
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

_DEFAULT_RESULT: dict[str, Any] = {
    "intent": "Benign",
    "anomaly_score": 0.0,
    "deception_trigger": False,
}


class BehavioralScorer:
    """Train and score behavioral telemetry with Isolation Forest."""

    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self.pipeline: Pipeline | None = None
        self._load_model_if_present()

    def _load_model_if_present(self) -> None:
        """Load persisted model if available; keep None when missing."""
        if not self.model_path.exists():
            logger.info("Behavioral model not found at %s; scorer starts untrained", self.model_path)
            self.pipeline = None
            return

        try:
            model = joblib.load(self.model_path)
            if isinstance(model, Pipeline):
                self.pipeline = model
                logger.info("Behavioral model loaded from %s", self.model_path)
            else:
                logger.warning("Model at %s is not a sklearn Pipeline; ignoring", self.model_path)
                self.pipeline = None
        except Exception as exc:
            logger.exception("Failed to load behavioral model from %s: %s", self.model_path, exc)
            self.pipeline = None

    @staticmethod
    def _to_numeric_value(value: Any) -> float:
        """Convert incoming scalar value into stable numeric representation."""
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _vectorize_one(cls, features: dict) -> Any:
        """Convert one feature dictionary into deterministic numeric row."""
        row = [cls._to_numeric_value(features.get(column, 0)) for column in _FEATURE_COLUMNS]
        return np.array(row, dtype=np.float64)

    @classmethod
    def _vectorize_many(cls, feature_vectors: list[dict]) -> Any:
        """Convert many feature dictionaries into a 2D numeric matrix."""
        if not feature_vectors:
            return np.empty((0, len(_FEATURE_COLUMNS)), dtype=np.float64)

        matrix = [cls._vectorize_one(features) for features in feature_vectors]
        return np.vstack(matrix)

    def train(self, feature_vectors: list[dict]) -> None:
        """Train Isolation Forest on baseline benign traffic and persist model."""
        matrix = self._vectorize_many(feature_vectors)
        if matrix.shape[0] == 0:
            logger.warning("Skipping behavioral model training: no feature vectors provided")
            return

        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "isolation_forest",
                    IsolationForest(
                        n_estimators=200,
                        contamination=0.05,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        )

        pipeline.fit(matrix)
        self.pipeline = pipeline

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, self.model_path)
        logger.info("Behavioral model trained and saved to %s", self.model_path)

    def score(self, features: dict) -> dict:
        """Score a single request feature vector and classify intent."""
        if self.pipeline is None:
            return dict(_DEFAULT_RESULT)

        try:
            row = self._vectorize_one(features).reshape(1, -1)
            score_value = float(self.pipeline.decision_function(row)[0])

            if score_value < -0.3:
                intent = "Malicious"
            elif score_value < -0.1:
                intent = "Exploratory"
            else:
                intent = "Benign"

            return {
                "intent": intent,
                "anomaly_score": score_value,
                "deception_trigger": intent == "Malicious",
            }
        except Exception as exc:
            logger.exception("Behavioral scoring failed: %s", exc)
            return dict(_DEFAULT_RESULT)
