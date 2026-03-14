import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './ReportsView.css';

function toApiBase() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }
  return 'http://localhost:5000';
}

function prettyDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (!Number.isFinite(d.getTime())) return String(ts);
  return d.toLocaleString();
}

function toLocalDateTimeInput(date) {
  const d = date instanceof Date ? date : new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function ReportsView() {
  const { token: jwtToken } = useAuth();
  const apiBase = useMemo(() => toApiBase(), []);

  const [tenantId, setTenantId] = useState(process.env.REACT_APP_TENANT_ID || '');
  const [history, setHistory] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [startTime, setStartTime] = useState(toLocalDateTimeInput(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
  const [endTime, setEndTime] = useState(toLocalDateTimeInput(new Date()));
  const [scheduleEmail, setScheduleEmail] = useState('');

  const authToken = jwtToken || process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';

  const fetchHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${apiBase}/api/v1/reports?limit=100&offset=0`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error || `Failed to load reports (${response.status})`);
      }

      setHistory(Array.isArray(payload?.reports) ? payload.reports : []);
      setCount(Number(payload?.count) || 0);
    } catch (e) {
      setHistory([]);
      setCount(0);
      setError(e?.message || 'Unable to load report history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, authToken]);

  const handleGenerate = async () => {
    setError('');
    try {
      if (!tenantId.trim()) throw new Error('tenant_id is required');
      const response = await fetch(`${apiBase}/api/v1/reports/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          start_time: new Date(startTime).toISOString(),
          end_time: new Date(endTime).toISOString(),
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error || `Report generation failed (${response.status})`);
      }

      await fetchHistory();
    } catch (e) {
      setError(e?.message || 'Failed to generate report');
    }
  };

  const handleSchedule = async () => {
    setError('');
    try {
      if (!tenantId.trim()) throw new Error('tenant_id is required');
      if (!scheduleEmail.trim()) throw new Error('email is required');

      const response = await fetch(`${apiBase}/api/v1/reports/schedule`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          frequency: 'weekly',
          email: scheduleEmail.trim(),
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error || `Schedule save failed (${response.status})`);
      }
    } catch (e) {
      setError(e?.message || 'Failed to schedule report');
    }
  };

  const handleDownload = async (downloadUrl, reportId) => {
    if (!downloadUrl) return;
    setError('');
    try {
      const response = await fetch(`${apiBase}${downloadUrl}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Download failed (${response.status})`);
      }

      const blob = await response.blob();
      const link = document.createElement('a');
      const url = window.URL.createObjectURL(blob);
      link.href = url;
      link.download = `${reportId || 'report'}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError(e?.message || 'Download failed');
    }
  };

  return (
    <section className="reports-view" role="tabpanel" aria-label="Threat Reports">
      <div className="reports-header">
        <h3>Threat Intelligence Reports</h3>
        <button type="button" onClick={fetchHistory} disabled={loading}>Refresh</button>
      </div>

      <div className="reports-controls">
        <label htmlFor="tenant-id">Tenant ID</label>
        <input
          id="tenant-id"
          type="text"
          value={tenantId}
          onChange={(e) => setTenantId(e.target.value)}
          placeholder="tenant UUID"
        />

        <label htmlFor="report-start">Start</label>
        <input id="report-start" type="datetime-local" value={startTime} onChange={(e) => setStartTime(e.target.value)} />

        <label htmlFor="report-end">End</label>
        <input id="report-end" type="datetime-local" value={endTime} onChange={(e) => setEndTime(e.target.value)} />

        <button type="button" onClick={handleGenerate}>Generate Report</button>
      </div>

      <div className="reports-controls schedule-row">
        <label htmlFor="schedule-email">Weekly Email</label>
        <input
          id="schedule-email"
          type="email"
          value={scheduleEmail}
          onChange={(e) => setScheduleEmail(e.target.value)}
          placeholder="security-team@example.com"
        />
        <button type="button" onClick={handleSchedule}>Save Weekly Schedule</button>
      </div>

      {error && <div className="reports-error">{error}</div>}

      <div className="reports-meta">{count.toLocaleString()} reports found</div>

      <div className="reports-table-wrap">
        <table className="reports-table">
          <thead>
            <tr>
              <th>Generated</th>
              <th>Range</th>
              <th>Events</th>
              <th>Attacks</th>
              <th>MITRE</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {!loading && history.length === 0 && (
              <tr><td colSpan={6} className="reports-empty">No reports found</td></tr>
            )}
            {history.map((item) => (
              <tr key={item.report_id}>
                <td>{prettyDate(item.generated_at)}</td>
                <td>{prettyDate(item.start_time)} → {prettyDate(item.end_time)}</td>
                <td>{Number(item.events_count) || 0}</td>
                <td>{Number(item.attacks_count) || 0}</td>
                <td>{Number(item.mitre_count) || 0}</td>
                <td>
                  <button
                    type="button"
                    onClick={() => handleDownload(item.download_url, item.report_id)}
                    disabled={!item.download_url}
                  >
                    Download PDF
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default ReportsView;
