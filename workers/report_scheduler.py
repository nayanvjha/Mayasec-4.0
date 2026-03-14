"""Weekly report scheduler worker.

Runs in a loop, finds due weekly report schedules, generates reports per tenant,
persists report history, and sends email notifications with PDF attachments.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras

from core.report_generator import ThreatReportGenerator

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def _db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "mayasec"),
        user=os.getenv("DB_USER", "mayasec"),
        password=os.getenv("DB_PASSWORD", "mayasec"),
    )


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _send_email_with_attachment(to_email: str, subject: str, body: str, file_path: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_email = os.getenv("SMTP_FROM", smtp_user or "noreply@mayasec.local")

    if not smtp_host:
        logger.warning("SMTP_HOST not set; skipping report email to %s", to_email)
        return

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with open(file_path, "rb") as fp:
        pdf_bytes = fp.read()

    filename = os.path.basename(file_path)
    message.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if smtp_user:
            smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)

    logger.info("Weekly report email sent to %s (%s)", to_email, filename)


def _load_due_schedules(conn) -> List[Dict]:
    due: List[Dict] = []
    now_ts = _now_utc_naive()

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id::text FROM tenants WHERE is_active = TRUE")
        tenant_ids = [str(row.get("id")) for row in (cur.fetchall() or []) if row.get("id")]

        for tenant_id in tenant_ids:
            cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
            cur.execute(
                """
                SELECT schedule_id::text AS schedule_id,
                       tenant_id::text AS tenant_id,
                       frequency,
                       email,
                       is_active,
                       last_run_at,
                       next_run_at
                FROM report_schedules
                WHERE is_active = TRUE
                  AND frequency = 'weekly'
                  AND (next_run_at IS NULL OR next_run_at <= %s)
                ORDER BY created_at ASC
                """,
                (now_ts,),
            )
            rows = cur.fetchall() or []
            due.extend(rows)

    return due


def _process_schedule(conn, generator: ThreatReportGenerator, schedule: Dict) -> None:
    tenant_id = str(schedule["tenant_id"])
    schedule_id = str(schedule["schedule_id"])
    recipient = str(schedule.get("email") or "").strip()

    end_time = _now_utc_naive()
    start_time = end_time - timedelta(days=7)

    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))

    file_path, metadata = generator.generate_report(
        conn=conn,
        tenant_id=tenant_id,
        start_time=start_time,
        end_time=end_time,
    )

    rel_path = os.path.relpath(file_path, start=os.getcwd())
    report_id = str(uuid.uuid4())
    next_run = end_time + timedelta(days=7)

    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
        cur.execute(
            """
            INSERT INTO reports
            (report_id, tenant_id, generated_at, file_path, events_count, attacks_count, mitre_count, start_time, end_time, report_metadata)
            VALUES (%s::uuid, %s::uuid, NOW(), %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                report_id,
                tenant_id,
                rel_path,
                int(metadata.get("total_events") or 0),
                int(metadata.get("total_attacks") or 0),
                int(len(metadata.get("mitre_techniques_triggered") or [])),
                start_time,
                end_time,
                json.dumps(metadata),
            ),
        )

        cur.execute(
            """
            UPDATE report_schedules
            SET last_run_at = NOW(),
                next_run_at = %s,
                updated_at = NOW()
            WHERE schedule_id = %s::uuid
            """,
            (next_run, schedule_id),
        )

    conn.commit()

    if recipient:
        _send_email_with_attachment(
            to_email=recipient,
            subject=f"MAYASEC Weekly Threat Report - {tenant_id}",
            body=(
                "Your scheduled MAYASEC weekly threat intelligence report is attached.\n\n"
                f"Tenant: {tenant_id}\n"
                f"Period: {start_time.isoformat()} to {end_time.isoformat()}\n"
            ),
            file_path=file_path,
        )

    logger.info("Processed report schedule %s for tenant %s", schedule_id, tenant_id)


def run_scheduler_loop(poll_seconds: int = 60) -> None:
    generator = ThreatReportGenerator(output_root=os.getenv("REPORTS_DIR", "reports"))

    while True:
        conn = None
        try:
            conn = _db_connect()
            conn.autocommit = False

            due_schedules = _load_due_schedules(conn)
            if not due_schedules:
                conn.commit()
                logger.debug("No due report schedules")
            else:
                logger.info("Found %d due report schedules", len(due_schedules))
                for schedule in due_schedules:
                    try:
                        _process_schedule(conn, generator, schedule)
                    except Exception:
                        conn.rollback()
                        logger.exception(
                            "Failed processing schedule %s for tenant %s",
                            schedule.get("schedule_id"),
                            schedule.get("tenant_id"),
                        )

        except Exception:
            logger.exception("Report scheduler loop failure")
        finally:
            if conn:
                conn.close()

        time.sleep(max(15, int(poll_seconds)))


if __name__ == "__main__":
    interval = int(os.getenv("REPORT_SCHEDULER_POLL_SECONDS", "60"))
    logger.info("Starting report scheduler (poll_seconds=%s)", interval)
    run_scheduler_loop(interval)
