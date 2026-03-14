"""Tenant threat intelligence report generator.

Builds weekly (or ad-hoc) threat intelligence reports from PostgreSQL data and
exports PDF files under reports/{tenant_id}/{timestamp}.pdf.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class ThreatReportGenerator:
    """Generate tenant-scoped threat intelligence reports as PDF."""

    def __init__(self, output_root: Optional[str] = None):
        self.output_root = Path(output_root or os.getenv('REPORTS_DIR', 'reports'))

    def generate_report(self, conn, tenant_id: str, start_time: datetime, end_time: datetime) -> Tuple[str, Dict[str, Any]]:
        """Generate a report and return (file_path, report_metadata)."""
        metrics = self._collect_metrics(conn, tenant_id, start_time, end_time)
        html = self._render_html(tenant_id, start_time, end_time, metrics)

        tenant_dir = self.output_root / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        out_path = tenant_dir / f'{stamp}.pdf'

        self._html_to_pdf(html, out_path, metrics)

        metadata = {
            'tenant_id': str(tenant_id),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'total_events': int(metrics.get('total_events', 0)),
            'total_attacks': int(metrics.get('total_attacks', 0)),
            'mitre_techniques_triggered': metrics.get('mitre_techniques_triggered', []),
            'top_attack_types': metrics.get('top_attack_types', []),
            'top_source_ips': metrics.get('top_source_ips', []),
            'top_target_paths': metrics.get('top_target_paths', []),
        }
        return str(out_path), metadata

    def _collect_metrics(self, conn, tenant_id: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SET LOCAL app.tenant_id = %s", (str(tenant_id),))

        cur.execute(
            """
            SELECT
              COUNT(*) AS total_events,
              COUNT(*) FILTER (WHERE COALESCE(threat_score, 0) >= 70 OR COALESCE(blocked, FALSE) = TRUE) AS total_attacks
            FROM security_logs
            WHERE timestamp BETWEEN %s AND %s
            """,
            (start_time, end_time),
        )
        row = cur.fetchone() or {}
        total_events = int(row.get('total_events') or 0)
        total_attacks = int(row.get('total_attacks') or 0)

        cur.execute(
            """
            SELECT
              COALESCE(
                NULLIF(metadata->>'attack_type', ''),
                NULLIF(metadata->'stream_payload'->'event'->>'event_type', ''),
                event_type,
                'unknown'
              ) AS attack_type,
              COUNT(*) AS count
            FROM security_logs
            WHERE timestamp BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 10
            """,
            (start_time, end_time),
        )
        top_attack_types = [
            {'attack_type': str(r.get('attack_type') or 'unknown'), 'count': int(r.get('count') or 0)}
            for r in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT split_part(ip_address::text, '/', 1) AS source_ip, COUNT(*) AS count
            FROM security_logs
            WHERE timestamp BETWEEN %s AND %s
              AND ip_address IS NOT NULL
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 10
            """,
            (start_time, end_time),
        )
        top_source_ips = [
            {'source_ip': str(r.get('source_ip') or 'unknown'), 'count': int(r.get('count') or 0)}
            for r in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT
              COALESCE(
                NULLIF(metadata->>'uri', ''),
                NULLIF(metadata->'stream_payload'->'event'->>'uri', ''),
                '/'
              ) AS target_path,
              COUNT(*) AS count
            FROM security_logs
            WHERE timestamp BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY count DESC
            LIMIT 10
            """,
            (start_time, end_time),
        )
        top_target_paths = [
            {'target_path': str(r.get('target_path') or '/'), 'count': int(r.get('count') or 0)}
            for r in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT DATE_TRUNC('day', timestamp) AS day,
                   COUNT(*) AS events,
                   COUNT(*) FILTER (WHERE COALESCE(threat_score, 0) >= 70 OR COALESCE(blocked, FALSE) = TRUE) AS attacks
            FROM security_logs
            WHERE timestamp BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            (start_time, end_time),
        )
        attack_timeline = [
            {
                'day': r.get('day').isoformat() if r.get('day') else None,
                'events': int(r.get('events') or 0),
                'attacks': int(r.get('attacks') or 0),
            }
            for r in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT phases, narrative, title, severity, start_time, end_time, attacker_ip::text AS attacker_ip
            FROM attack_stories
            WHERE start_time <= %s
              AND end_time >= %s
            ORDER BY start_time DESC
            LIMIT 25
            """,
            (end_time, start_time),
        )
        stories_raw = cur.fetchall() or []
        detailed_attack_stories: List[Dict[str, Any]] = []
        mitre_counter: Counter = Counter()

        for story in stories_raw:
            phases = story.get('phases') or []
            if isinstance(phases, str):
                try:
                    phases = json.loads(phases)
                except Exception:
                    phases = []

            all_story_mitre: List[str] = []
            for p in phases if isinstance(phases, list) else []:
                pm = p.get('mitre') if isinstance(p, dict) else []
                if isinstance(pm, list):
                    for t in pm:
                        if t:
                            token = str(t).strip()
                            all_story_mitre.append(token)
                            mitre_counter[token] += 1

            detailed_attack_stories.append(
                {
                    'title': story.get('title') or 'Attack Story',
                    'severity': story.get('severity') or 'low',
                    'attacker_ip': str(story.get('attacker_ip') or 'unknown').split('/')[0],
                    'start_time': story.get('start_time').isoformat() if story.get('start_time') else None,
                    'end_time': story.get('end_time').isoformat() if story.get('end_time') else None,
                    'narrative': story.get('narrative') or '',
                    'phases': phases if isinstance(phases, list) else [],
                    'mitre': sorted(set(all_story_mitre)),
                }
            )

        # Fallback mitre extraction from security_logs if stories do not cover range.
        if not mitre_counter:
            cur.execute(
                """
                SELECT COALESCE(mitre_ttps, '[]'::jsonb) AS mitre_ttps
                FROM security_logs
                WHERE timestamp BETWEEN %s AND %s
                """,
                (start_time, end_time),
            )
            for rec in (cur.fetchall() or []):
                raw = rec.get('mitre_ttps')
                values: Sequence[Any] = []
                if isinstance(raw, list):
                    values = raw
                elif isinstance(raw, str):
                    try:
                        decoded = json.loads(raw)
                        if isinstance(decoded, list):
                            values = decoded
                        else:
                            values = [raw]
                    except Exception:
                        values = [raw]
                for t in values:
                    if t:
                        mitre_counter[str(t).strip()] += 1

        mitre_techniques_triggered = [
            {'technique_id': k, 'count': int(v)}
            for k, v in mitre_counter.most_common(30)
        ]

        cur.close()

        return {
            'total_events': total_events,
            'total_attacks': total_attacks,
            'top_attack_types': top_attack_types,
            'top_source_ips': top_source_ips,
            'top_target_paths': top_target_paths,
            'mitre_techniques_triggered': mitre_techniques_triggered,
            'attack_timeline': attack_timeline,
            'detailed_attack_stories': detailed_attack_stories,
        }

    def _render_html(self, tenant_id: str, start_time: datetime, end_time: datetime, metrics: Dict[str, Any]) -> str:
        def table_rows(items: Sequence[Dict[str, Any]], cols: Sequence[str]) -> str:
            if not items:
                return '<tr><td colspan="99">No data</td></tr>'
            html = []
            for item in items:
                html.append('<tr>' + ''.join(f"<td>{item.get(c, '')}</td>" for c in cols) + '</tr>')
            return ''.join(html)

        stories_html = []
        stories = metrics.get('detailed_attack_stories') or []
        if stories:
            for s in stories:
                phases = s.get('phases') or []
                phase_lines = []
                for p in phases:
                    if isinstance(p, dict):
                        phase_lines.append(
                            f"<li><b>{p.get('phase', 'Phase')}</b> — {p.get('description', '')} "
                            f"(events: {p.get('event_count', 0)}, score: {p.get('score_range', 'n/a')})</li>"
                        )
                stories_html.append(
                    f"""
                    <div class='story'>
                      <h4>{s.get('title', 'Attack Story')} <span class='sev sev-{s.get('severity', 'low')}'>{s.get('severity', 'low')}</span></h4>
                      <p><b>Attacker:</b> {s.get('attacker_ip', 'unknown')} | <b>Window:</b> {s.get('start_time', '')} → {s.get('end_time', '')}</p>
                      <p>{s.get('narrative', '')}</p>
                      <ul>{''.join(phase_lines) or '<li>No phase details</li>'}</ul>
                    </div>
                    """
                )
        else:
            stories_html.append("<p>No attack stories in selected range.</p>")

        return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8' />
  <style>
    body {{ font-family: Arial, sans-serif; color: #111827; font-size: 12px; }}
    h1 {{ margin-bottom: 0; }}
    h2 {{ margin: 18px 0 8px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; text-align: left; }}
    th {{ background: #f3f4f6; }}
    .kpis {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin: 8px 0; }}
    .kpi {{ border: 1px solid #ddd; padding: 8px; border-radius: 6px; }}
    .story {{ border: 1px solid #ddd; padding: 10px; border-radius: 6px; margin-bottom: 8px; }}
    .sev {{ padding: 2px 6px; border-radius: 999px; font-size: 10px; text-transform: uppercase; }}
    .sev-critical {{ background: #fee2e2; color: #991b1b; }}
    .sev-high {{ background: #ffedd5; color: #9a3412; }}
    .sev-medium {{ background: #fef9c3; color: #854d0e; }}
    .sev-low {{ background: #dcfce7; color: #166534; }}
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
  <h1>MAYASEC Threat Intelligence Report</h1>
  <p class='muted'>Tenant: {tenant_id} | Range: {start_time.isoformat()} → {end_time.isoformat()}</p>

  <h2>1. Executive Summary</h2>
  <p>
    During the selected period, MAYASEC recorded <b>{metrics.get('total_events', 0)}</b> security events,
    with <b>{metrics.get('total_attacks', 0)}</b> events classified as attacks.
    A total of <b>{len(metrics.get('mitre_techniques_triggered', []))}</b> MITRE ATT&CK techniques were triggered.
  </p>

  <h2>2. Key Metrics</h2>
  <div class='kpis'>
    <div class='kpi'><b>Total Events</b><br/>{metrics.get('total_events', 0)}</div>
    <div class='kpi'><b>Total Attacks</b><br/>{metrics.get('total_attacks', 0)}</div>
    <div class='kpi'><b>Top Attack Types</b><br/>{', '.join([x.get('attack_type', 'unknown') for x in (metrics.get('top_attack_types') or [])[:5]]) or 'n/a'}</div>
    <div class='kpi'><b>MITRE Techniques Triggered</b><br/>{len(metrics.get('mitre_techniques_triggered', []))}</div>
  </div>

  <h2>3. Attack Timeline</h2>
  <table>
    <thead><tr><th>Day</th><th>Events</th><th>Attacks</th></tr></thead>
    <tbody>{table_rows(metrics.get('attack_timeline') or [], ['day', 'events', 'attacks'])}</tbody>
  </table>

  <h2>4. Top Source IPs</h2>
  <table>
    <thead><tr><th>Source IP</th><th>Count</th></tr></thead>
    <tbody>{table_rows(metrics.get('top_source_ips') or [], ['source_ip', 'count'])}</tbody>
  </table>

  <h2>5. Top Targeted Paths</h2>
  <table>
    <thead><tr><th>Target Path</th><th>Count</th></tr></thead>
    <tbody>{table_rows(metrics.get('top_target_paths') or [], ['target_path', 'count'])}</tbody>
  </table>

  <h2>6. MITRE ATT&CK Techniques</h2>
  <table>
    <thead><tr><th>Technique ID</th><th>Count</th></tr></thead>
    <tbody>{table_rows(metrics.get('mitre_techniques_triggered') or [], ['technique_id', 'count'])}</tbody>
  </table>

  <h2>7. Detailed Attack Stories</h2>
  {''.join(stories_html)}
</body>
</html>
"""

    def _html_to_pdf(self, html: str, output_path: Path, metrics: Dict[str, Any]) -> None:
        """Convert HTML to PDF, with resilient fallback if WeasyPrint is unavailable."""
        try:
            from weasyprint import HTML  # type: ignore

            HTML(string=html, base_url=str(Path.cwd())).write_pdf(str(output_path))
            return
        except Exception as exc:
            logger.warning('WeasyPrint unavailable, using fallback PDF writer: %s', exc)

        try:
            from reportlab.lib.pagesizes import A4  # type: ignore
            from reportlab.pdfgen import canvas  # type: ignore

            c = canvas.Canvas(str(output_path), pagesize=A4)
            width, height = A4
            y = height - 40
            lines = [
                'MAYASEC Threat Intelligence Report',
                f"Generated: {datetime.utcnow().isoformat()}Z",
                '',
                f"Total Events: {metrics.get('total_events', 0)}",
                f"Total Attacks: {metrics.get('total_attacks', 0)}",
                f"MITRE Techniques: {len(metrics.get('mitre_techniques_triggered', []))}",
                '',
                'Top Attack Types:',
            ]
            for item in (metrics.get('top_attack_types') or [])[:10]:
                lines.append(f"- {item.get('attack_type', 'unknown')}: {item.get('count', 0)}")
            lines.append('')
            lines.append('Top Source IPs:')
            for item in (metrics.get('top_source_ips') or [])[:10]:
                lines.append(f"- {item.get('source_ip', 'unknown')}: {item.get('count', 0)}")

            for line in lines:
                c.drawString(40, y, str(line)[:130])
                y -= 14
                if y < 40:
                    c.showPage()
                    y = height - 40
            c.save()
            return
        except Exception as exc:
            logger.error('Fallback PDF writer failed: %s', exc)
            raise RuntimeError('Unable to generate PDF report')
