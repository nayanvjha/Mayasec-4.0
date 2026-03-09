"""Lightweight ADWIN-style drift detector for behavioral anomaly scores."""

from __future__ import annotations

import logging
from collections import deque
from statistics import mean, stdev

logger = logging.getLogger(__name__)


class DriftDetector:
    """Monitor anomaly-score distribution drift with a fixed-memory rolling window."""

    def __init__(
        self,
        window_size: int = 500,
        warmup_samples: int = 100,
        drift_threshold: float = 2.5,
    ) -> None:
        self.window_size = max(1, int(window_size))
        self.warmup_samples = max(2, int(warmup_samples))
        self.drift_threshold = float(drift_threshold)

        self.scores_window: deque[float] = deque(maxlen=self.window_size)
        self.baseline_mean: float = 0.0
        self.baseline_std: float = 0.0
        self.retrain_needed: bool = False

    def _initialize_baseline_if_ready(self) -> None:
        """Initialize baseline once enough samples are available."""
        if self.baseline_std > 0.0 or len(self.scores_window) < self.warmup_samples:
            return

        warmup_slice = list(self.scores_window)[-self.warmup_samples :]
        self.baseline_mean = float(mean(warmup_slice))
        # stdev requires at least 2 points; warmup_samples is clamped >= 2.
        self.baseline_std = float(stdev(warmup_slice))
        logger.info(
            "DriftDetector baseline initialized mean=%.6f std=%.6f samples=%d",
            self.baseline_mean,
            self.baseline_std,
            self.warmup_samples,
        )

    def update(self, score: float) -> bool:
        """Add one anomaly score and return True when drift is detected."""
        try:
            value = float(score)
        except (TypeError, ValueError):
            logger.warning("DriftDetector received non-numeric score=%r; coercing to 0.0", score)
            value = 0.0

        self.scores_window.append(value)
        self._initialize_baseline_if_ready()

        # Warm-up or baseline not available yet.
        if len(self.scores_window) < self.warmup_samples or self.baseline_std <= 0.0:
            return False

        recent_slice = list(self.scores_window)[-self.warmup_samples :]
        recent_mean = float(mean(recent_slice))
        delta = abs(recent_mean - self.baseline_mean)
        threshold = self.drift_threshold * self.baseline_std

        if delta > threshold:
            self.retrain_needed = True
            logger.warning(
                "Concept drift detected delta=%.6f threshold=%.6f recent_mean=%.6f baseline_mean=%.6f baseline_std=%.6f",
                delta,
                threshold,
                recent_mean,
                self.baseline_mean,
                self.baseline_std,
            )

            # Re-baseline to current distribution after drift signal.
            self.baseline_mean = recent_mean
            self.baseline_std = float(stdev(recent_slice)) if len(recent_slice) >= 2 else 0.0
            return True

        return False

    def needs_retraining(self) -> bool:
        """Return whether drift has been detected and retraining is required."""
        return self.retrain_needed

    def reset(self) -> None:
        """Clear retraining flag after retraining workflow completes."""
        self.retrain_needed = False

