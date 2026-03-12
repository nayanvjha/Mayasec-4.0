"""Behavioral response escalation engine for high-throughput request pipelines."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import DefaultDict


class ResponseEscalator:
    """Track per-IP behavioral history and produce escalation decisions."""

    def __init__(self) -> None:
        self._intent_history: DefaultDict[str, deque[str]] = defaultdict(lambda: deque(maxlen=10))
        self._lock = threading.Lock()

    def evaluate(self, ip: str, behavioral_result: dict) -> dict:
        """Evaluate escalation tier for an IP using current behavioral signals and recent intent history."""
        intent = str((behavioral_result or {}).get("intent", "Benign"))

        anomaly_raw = (behavioral_result or {}).get("anomaly_score", 0.0)
        try:
            anomaly_score = float(anomaly_raw)
        except (TypeError, ValueError):
            anomaly_score = 0.0

        graph_threat = bool((behavioral_result or {}).get("graph_threat", False))

        with self._lock:
            history = self._intent_history[str(ip)]
            history.append(intent)

            # Tier 3 (highest): malicious intent with graph correlation threat.
            if graph_threat and intent == "Malicious":
                return {
                    "tier": 3,
                    "action": "block",
                    "reason": "malicious activity with graph threat",
                }

            # Tier 2: malicious intent or high anomaly.
            if intent == "Malicious" or anomaly_score < -0.5:
                return {
                    "tier": 2,
                    "action": "slow_response",
                    "reason": "malicious intent or high anomaly score",
                }

            # Tier 1: three consecutive exploratory intents.
            if len(history) >= 3 and history[-1] == "Exploratory" and history[-2] == "Exploratory" and history[-3] == "Exploratory":
                return {
                    "tier": 1,
                    "action": "shadow",
                    "reason": "3 consecutive exploratory intents",
                }

        # Tier 0: default allow.
        return {
            "tier": 0,
            "action": "allow",
            "reason": "no escalation condition met",
        }
