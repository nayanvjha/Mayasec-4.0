"""MITRE ATT&CK TTP classifier — rule-based first pass, LLM fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_RULES: list[dict] = []


def _load_rules() -> None:
    global _RULES
    path = Path(__file__).parent / "mitre_knowledge.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            _RULES = data.get("rules", [])
            logger.info("Loaded %d MITRE ATT&CK rules", len(_RULES))
    except Exception as exc:
        logger.warning("Failed to load MITRE rules: %s", exc)


_load_rules()


def classify_rules(event: dict) -> list[dict]:
    """Rule-based TTP classification. Returns list of {id, name, confidence}."""
    if not _RULES:
        _load_rules()

    matches: list[dict] = []
    attack_type = str(event.get("attack_type", "")).lower()
    intent = str(event.get("intent", "Benign"))
    score = int(event.get("score", 0))
    graph_threat = bool(event.get("graph_threat", False))
    uri = str(event.get("uri", "/"))
    uri_path_diversity = int(event.get("uri_path_diversity", 0))
    request_rate = int(event.get("request_rate_60s", 0))

    for rule in _RULES:
        triggers = rule.get("triggers", {})
        matched = True

        # Check attack_types
        if "attack_types" in triggers:
            if attack_type not in triggers["attack_types"]:
                matched = False

        # Check min_score
        if "min_score" in triggers and score < triggers["min_score"]:
            matched = False

        # Check intents
        if "intents" in triggers:
            if intent not in triggers["intents"]:
                matched = False

        # Check graph_threat
        if "graph_threat" in triggers and triggers["graph_threat"] != graph_threat:
            matched = False

        # Check uri_patterns
        if "uri_patterns" in triggers:
            if not any(p in uri for p in triggers["uri_patterns"]):
                matched = False

        # Check min_uri_path_diversity
        if "min_uri_path_diversity" in triggers:
            if uri_path_diversity < triggers["min_uri_path_diversity"]:
                matched = False

        # Check request rate bounds
        if "min_request_rate" in triggers and request_rate < triggers["min_request_rate"]:
            matched = False
        if "max_request_rate" in triggers and request_rate > triggers["max_request_rate"]:
            matched = False

        if matched:
            matches.append(
                {
                    "id": rule["id"],
                    "name": rule["name"],
                    "tactic": rule.get("tactic", ""),
                    "confidence": 0.9,
                }
            )

    return matches
