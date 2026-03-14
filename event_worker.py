import json
import logging
import os
import socket
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import psycopg2
import redis
from psycopg2.extras import execute_values


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("event-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mayasec:mayasec@postgres:5432/mayasec")
STREAM_NAME = os.getenv("EVENT_STREAM_NAME", "mayasec:events")
GROUP_NAME = os.getenv("EVENT_STREAM_GROUP", "mayasec-workers")
CONSUMER_NAME = os.getenv("EVENT_STREAM_CONSUMER", f"worker-{socket.gethostname()}")
BATCH_SIZE = int(os.getenv("EVENT_WORKER_BATCH_SIZE", "500"))
BLOCK_MS = int(os.getenv("EVENT_WORKER_BLOCK_MS", "2000"))


def threat_level_from_score(score: float) -> str:
    if score >= 90:
        return "critical"
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def ensure_group(rdb: redis.Redis) -> None:
    try:
        rdb.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        logger.info("Created stream consumer group %s on %s", GROUP_NAME, STREAM_NAME)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            return
        raise


def parse_event(fields: Dict[str, str]) -> Dict:
    payload_raw = fields.get("payload") or "{}"
    try:
        payload = json.loads(payload_raw)
    except Exception:
        payload = {}

    event_obj_raw = payload.get("event") if isinstance(payload, dict) else {}
    analysis_obj_raw = payload.get("analysis") if isinstance(payload, dict) else {}
    event_obj = event_obj_raw if isinstance(event_obj_raw, dict) else {}
    analysis_obj = analysis_obj_raw if isinstance(analysis_obj_raw, dict) else {}

    event_id_raw = fields.get("event_id") or event_obj.get("event_id")
    try:
        event_id = str(uuid.UUID(str(event_id_raw)))
    except Exception:
        event_id = str(uuid.uuid4())

    tenant_id_raw = fields.get("tenant_id")
    try:
        tenant_id = str(uuid.UUID(str(tenant_id_raw)))
    except Exception:
        tenant_id = ""

    source_ip = fields.get("source_ip") or event_obj.get("source_ip") or "unknown"
    event_type = fields.get("event_type") or event_obj.get("event_type") or "unknown"
    uri = fields.get("uri") or event_obj.get("uri") or "/"
    http_method = fields.get("http_method") or "GET"

    try:
        threat_score = float(fields.get("threat_score") or event_obj.get("threat_score") or 0)
    except Exception:
        threat_score = 0.0

    ts_raw = fields.get("timestamp") or ""
    try:
        ts_int = int(ts_raw)
        event_timestamp = datetime.fromtimestamp(ts_int, tz=timezone.utc)
    except Exception:
        event_timestamp = datetime.now(timezone.utc)

    metadata = {
        "uri": uri,
        "http_method": http_method,
        "stream_payload": payload,
        "analysis": analysis_obj,
    }

    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "source_ip": source_ip,
        "event_type": event_type,
        "uri": uri,
        "http_method": http_method,
        "threat_score": int(round(threat_score)),
        "timestamp": event_timestamp,
        "metadata": metadata,
    }


def insert_batch(conn, parsed_events: List[Dict]) -> None:
    by_tenant: Dict[str, List[Dict]] = defaultdict(list)
    for ev in parsed_events:
        if ev.get("tenant_id"):
            by_tenant[ev["tenant_id"]].append(ev)

    with conn:
        with conn.cursor() as cur:
            for tenant_id, tenant_events in by_tenant.items():
                cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))

                security_rows: List[Tuple] = []
                alert_rows: List[Tuple] = []

                ip_counter = Counter()
                ip_event_ids: Dict[str, List[str]] = defaultdict(list)

                for ev in tenant_events:
                    score = max(0, min(100, int(ev["threat_score"])))
                    level = threat_level_from_score(score)
                    security_rows.append(
                        (
                            ev["event_id"],
                            tenant_id,
                            ev["source_ip"],
                            ev["event_type"],
                            ev["timestamp"],
                            level,
                            score,
                            "observed",
                            "redis-event-worker",
                            "redis-stream",
                            json.dumps(ev["metadata"]),
                        )
                    )

                    if score >= 80:
                        alert_rows.append(
                            (
                                tenant_id,
                                ev["event_id"],
                                "high_threat_event",
                                level,
                                score,
                                f"High severity event from {ev['source_ip']}",
                                ev["source_ip"],
                                "redis-event-worker",
                                json.dumps({"source": "redis-stream", "event_type": ev["event_type"]}),
                            )
                        )

                    ip_counter[ev["source_ip"]] += 1
                    ip_event_ids[ev["source_ip"]].append(ev["event_id"])

                if security_rows:
                    execute_values(
                        cur,
                        '''
                        INSERT INTO security_logs
                        (event_id, tenant_id, ip_address, event_type, timestamp, threat_level,
                         threat_score, action, sensor_id, source, metadata)
                        VALUES %s
                        ON CONFLICT (event_id) DO NOTHING
                        ''',
                        security_rows,
                    )

                if alert_rows:
                    execute_values(
                        cur,
                        '''
                        INSERT INTO alert_history
                        (tenant_id, event_id, alert_type, threat_level, threat_score, description,
                         ip_address, sensor_id, metadata)
                        VALUES %s
                        ''',
                        alert_rows,
                    )

                for source_ip, count in ip_counter.items():
                    if count < 5:
                        continue

                    logger.warning("Potential DDoS detected from %s", source_ip)
                    event_ids = ip_event_ids[source_ip]
                    cur.execute(
                        '''
                        INSERT INTO event_correlations
                        (tenant_id, correlation_type, event_ids, ip_address, threat_level, threat_score, description, metadata)
                        VALUES (%s, %s, %s::uuid[], %s, %s, %s, %s, %s)
                        ''',
                        (
                            tenant_id,
                            'potential_ddos',
                            event_ids,
                            source_ip,
                            'high',
                            80,
                            f'Potential DDoS detected from {source_ip}',
                            json.dumps({'batch_event_count': count}),
                        ),
                    )


def main() -> None:
    rdb = redis.from_url(REDIS_URL, decode_responses=True)
    ensure_group(rdb)

    conn = psycopg2.connect(DATABASE_URL)

    processed_events = 0
    processed_batches = 0
    last_log = time.monotonic()

    logger.info("Event worker started. stream=%s group=%s consumer=%s", STREAM_NAME, GROUP_NAME, CONSUMER_NAME)

    while True:
        try:
            messages = []

            # Recover stale pending entries from any dead consumer.
            try:
                claimed = rdb.xautoclaim(
                    STREAM_NAME,
                    GROUP_NAME,
                    CONSUMER_NAME,
                    min_idle_time=60000,
                    start_id="0-0",
                    count=BATCH_SIZE,
                )
                claimed_items = claimed[1] if isinstance(claimed, (list, tuple)) and len(claimed) > 1 else []
                if claimed_items:
                    messages = [(STREAM_NAME, claimed_items)]
            except Exception:
                # Ignore recovery-path failures and continue normal consumption.
                messages = []

            # Drain this consumer's pending entries first (recovery after crash/error),
            # then continue with new entries.
            if not messages:
                messages = rdb.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: '0'},
                    count=BATCH_SIZE,
                    block=1,
                )

            if not messages:
                messages = rdb.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: '>'},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )

            if not messages:
                now = time.monotonic()
                if now - last_log >= 10:
                    logger.info("Processed %s events in %s batches", processed_events, processed_batches)
                    last_log = now
                continue

            stream_items = messages[0][1] if messages and messages[0] else []
            if not stream_items:
                continue

            msg_ids = []
            parsed_events = []

            for msg_id, fields in stream_items:
                msg_ids.append(msg_id)
                parsed_events.append(parse_event(fields))

            insert_batch(conn, parsed_events)

            if msg_ids:
                rdb.xack(STREAM_NAME, GROUP_NAME, *msg_ids)

            processed_events += len(parsed_events)
            processed_batches += 1

            now = time.monotonic()
            if now - last_log >= 10:
                logger.info("Processed %s events in %s batches", processed_events, processed_batches)
                last_log = now

        except Exception as e:
            logger.exception("Worker loop error: %s", e)
            time.sleep(1)


if __name__ == "__main__":
    main()
