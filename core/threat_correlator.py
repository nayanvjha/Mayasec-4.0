"""Threat correlator helpers for asynchronous side-channel processing."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Mapping

from core.graph_writer import write_attack_event

logger = logging.getLogger(__name__)


def schedule_graph_write(event: Mapping[str, Any]) -> None:
    """Schedule graph persistence for a processed event.

    This is intentionally fire-and-forget and must never interrupt the
    ingestion/correlation pipeline.
    """
    try:
        payload = dict(event)

        def _run_sync(ev: dict) -> None:
            try:
                write_attack_event(ev)
            except Exception as exc:
                logger.warning("Graph write failed: %s", exc)

        threading.Thread(target=_run_sync, args=(payload,), daemon=True).start()
    except Exception as exc:
        logger.warning("Graph writer task creation failed: %s", exc)
