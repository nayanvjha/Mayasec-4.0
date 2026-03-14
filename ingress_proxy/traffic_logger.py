"""Asynchronous raw HTTP traffic logger for ClickHouse."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger("traffic_logger")

CLICKHOUSE_URL = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
CLICKHOUSE_INSERT_URL = f"{CLICKHOUSE_URL}/?query=INSERT%20INTO%20raw_traffic_logs%20FORMAT%20JSONEachRow"
BATCH_SIZE = int(os.getenv("TRAFFIC_LOG_BATCH_SIZE", "500"))
FLUSH_INTERVAL_SECONDS = float(os.getenv("TRAFFIC_LOG_FLUSH_INTERVAL", "2"))
MAX_REQUEST_BODY_BYTES = int(os.getenv("TRAFFIC_LOG_MAX_BODY_BYTES", "32768"))


class TrafficLogger:
    """Queue-backed async logger with periodic batch flush to ClickHouse."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Dict] = asyncio.Queue()
        self._buffer: List[Dict] = []
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._last_flush = time.monotonic()
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=8, connect=2)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def stop(self) -> None:
        self._stop.set()
        await self._flush_locked(force=True)
        if self._session and not self._session.closed:
            await self._session.close()

    async def log(self, record: Dict) -> None:
        """Enqueue a record. This method is safe to call from background tasks."""
        normalized = self._normalize_record(record)
        await self.queue.put(normalized)

    def _normalize_record(self, record: Dict) -> Dict:
        body = record.get("request_body")
        if body is None:
            body = ""
        if isinstance(body, (bytes, bytearray)):
            body = bytes(body).decode("utf-8", errors="ignore")
        body = str(body)
        if len(body.encode("utf-8", errors="ignore")) > MAX_REQUEST_BODY_BYTES:
            body = body.encode("utf-8", errors="ignore")[:MAX_REQUEST_BODY_BYTES].decode("utf-8", errors="ignore")

        content_length = record.get("content_length", 0)
        try:
            content_length = int(content_length)
        except Exception:
            content_length = 0
        if content_length < 0:
            content_length = 0

        status = record.get("status", 0)
        try:
            status = int(status)
        except Exception:
            status = 0
        if status < 0:
            status = 0

        return {
            "src_ip": str(record.get("src_ip", "unknown")),
            "method": str(record.get("method", "GET")),
            "path": str(record.get("path", "/")),
            "query_string": str(record.get("query_string", "")),
            "status": status,
            "user_agent": str(record.get("user_agent", "")),
            "referer": str(record.get("referer", "")),
            "content_length": content_length,
            "request_body": body,
        }

    async def _flush_locked(self, force: bool = False) -> None:
        async with self._lock:
            if not self._buffer:
                self._last_flush = time.monotonic()
                return

            if not force and len(self._buffer) < BATCH_SIZE and (time.monotonic() - self._last_flush) < FLUSH_INTERVAL_SECONDS:
                return

            batch = self._buffer
            self._buffer = []

        ok = await self._insert_batch(batch)
        if ok:
            self._last_flush = time.monotonic()
            return

        # Temporary failure: re-queue batch to avoid data loss.
        async with self._lock:
            self._buffer = batch + self._buffer

    async def _insert_batch(self, batch: List[Dict]) -> bool:
        if not batch:
            return True

        if self._session is None or self._session.closed:
            await self.start()

        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in batch)

        try:
            assert self._session is not None
            async with self._session.post(
                CLICKHOUSE_INSERT_URL,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning("clickhouse_insert_failed status=%s body=%s", resp.status, body[:300])
                    return False
                return True
        except Exception as exc:
            logger.warning("clickhouse_insert_error error=%s", exc)
            return False

    async def flush_worker(self) -> None:
        """Continuously drain queue and flush by size/time without blocking requests."""
        await self.start()
        logger.info(
            "traffic_logger_started clickhouse=%s batch_size=%s flush_interval=%ss",
            CLICKHOUSE_URL,
            BATCH_SIZE,
            FLUSH_INTERVAL_SECONDS,
        )

        try:
            while not self._stop.is_set():
                timeout = max(0.05, FLUSH_INTERVAL_SECONDS / 2)
                record = None
                try:
                    record = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    record = None

                if record is not None:
                    async with self._lock:
                        self._buffer.append(record)

                should_force_flush = (time.monotonic() - self._last_flush) >= FLUSH_INTERVAL_SECONDS
                should_batch_flush = False
                async with self._lock:
                    if len(self._buffer) >= BATCH_SIZE:
                        should_batch_flush = True

                if should_batch_flush or should_force_flush:
                    await self._flush_locked(force=should_force_flush)

            # Final flush on shutdown.
            await self._flush_locked(force=True)
        finally:
            if self._session and not self._session.closed:
                await self._session.close()


traffic_logger = TrafficLogger()
