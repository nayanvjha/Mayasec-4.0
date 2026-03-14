import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './TrafficLogsView.css';

const PAGE_SIZE = 200;

const METHOD_OPTIONS = ['ALL', 'GET', 'POST', 'PUT', 'DELETE', 'PATCH'];
const STATUS_OPTIONS = ['ALL', '2xx', '3xx', '4xx', '5xx'];

function toApiBase() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }
  return 'http://localhost:5000';
}

function formatTimestamp(ts) {
  if (!ts) return '—';
  const parsed = new Date(ts);
  if (!Number.isFinite(parsed.getTime())) return String(ts);
  return parsed.toLocaleString();
}

function methodClass(method) {
  const m = String(method || '').toUpperCase();
  if (m === 'GET') return 'method-get';
  if (m === 'POST') return 'method-post';
  if (m === 'PUT') return 'method-put';
  if (m === 'DELETE') return 'method-delete';
  if (m === 'PATCH') return 'method-patch';
  return 'method-default';
}

function statusClass(statusCode) {
  const s = Number(statusCode) || 0;
  if (s >= 200 && s < 300) return 'status-2xx';
  if (s >= 300 && s < 400) return 'status-3xx';
  if (s >= 400 && s < 500) return 'status-4xx';
  return 'status-5xx';
}

function TrafficLogsView() {
  const { token: jwtToken } = useAuth();
  const apiBase = useMemo(() => toApiBase(), []);

  const [method, setMethod] = useState('ALL');
  const [status, setStatus] = useState('ALL');
  const [ip, setIp] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');

  const [logs, setLogs] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandedRow, setExpandedRow] = useState(null);
  const [searchTick, setSearchTick] = useState(0);

  const totalPages = Math.max(1, Math.ceil((Number(count) || 0) / PAGE_SIZE));

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();

    const fetchLogs = async () => {
      setLoading(true);
      setError('');

      try {
        const params = new URLSearchParams();
        params.set('limit', String(PAGE_SIZE));
        params.set('offset', String(page * PAGE_SIZE));

        if (method !== 'ALL') params.set('method', method);
        if (status !== 'ALL') params.set('status', status);
        if (ip.trim()) params.set('ip', ip.trim());
        if (startTime) params.set('start_time', new Date(startTime).toISOString());
        if (endTime) params.set('end_time', new Date(endTime).toISOString());

        const authToken = jwtToken || process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';
        const response = await fetch(`${apiBase}/api/v1/traffic-logs?${params.toString()}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${authToken}`,
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `Failed to fetch logs (${response.status})`);
        }

        const payload = await response.json();
        if (!mounted) return;

        setLogs(Array.isArray(payload?.logs) ? payload.logs : []);
        setCount(Number(payload?.count) || 0);
      } catch (err) {
        if (!mounted || err?.name === 'AbortError') return;
        setLogs([]);
        setCount(0);
        setError(err?.message || 'Unable to load traffic logs');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchLogs();

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [apiBase, endTime, ip, jwtToken, method, page, searchTick, startTime, status]);

  const handleSearch = () => {
    setPage(0);
    setSearchTick((v) => v + 1);
  };

  const handleReset = () => {
    setMethod('ALL');
    setStatus('ALL');
    setIp('');
    setStartTime('');
    setEndTime('');
    setExpandedRow(null);
    setPage(0);
    setSearchTick((v) => v + 1);
  };

  return (
    <section className="traffic-logs-view" role="tabpanel" aria-label="Traffic Logs">
      <div className="traffic-logs-header">
        <h3>Traffic Logs</h3>
        <span className="traffic-logs-count">{count.toLocaleString()} records</span>
      </div>

      <div className="traffic-toolbar">
        <select value={method} onChange={(e) => { setMethod(e.target.value); setPage(0); }}>
          {METHOD_OPTIONS.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>

        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Source IP"
          value={ip}
          onChange={(e) => { setIp(e.target.value); setPage(0); }}
        />

        <input
          type="datetime-local"
          value={startTime}
          onChange={(e) => { setStartTime(e.target.value); setPage(0); }}
          title="Start time"
        />

        <input
          type="datetime-local"
          value={endTime}
          onChange={(e) => { setEndTime(e.target.value); setPage(0); }}
          title="End time"
        />

        <button type="button" onClick={handleSearch}>Search</button>
        <button type="button" className="reset-btn" onClick={handleReset}>Reset</button>
      </div>

      {error && <div className="traffic-error">{error}</div>}

      <div className="traffic-table-wrap">
        <table className="traffic-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>IP</th>
              <th>Method</th>
              <th>Status</th>
              <th>Path</th>
              <th>User-Agent</th>
              <th>Content-Length</th>
            </tr>
          </thead>
          <tbody>
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={7} className="traffic-empty">No traffic logs found</td>
              </tr>
            )}

            {logs.map((log, idx) => {
              const key = `${log.ts || 'ts'}-${log.src_ip || 'ip'}-${idx}`;
              const expanded = expandedRow === key;
              return (
                <React.Fragment key={key}>
                  <tr
                    className="traffic-row"
                    onClick={() => setExpandedRow(expanded ? null : key)}
                  >
                    <td>{formatTimestamp(log.ts)}</td>
                    <td>{log.src_ip || '—'}</td>
                    <td>
                      <span className={`method-badge ${methodClass(log.method)}`}>
                        {String(log.method || '—').toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${statusClass(log.status)}`}>
                        {log.status || '—'}
                      </span>
                    </td>
                    <td className="path-cell">{log.path || '/'}{log.query_string ? `?${log.query_string}` : ''}</td>
                    <td className="ua-cell">{log.user_agent || '—'}</td>
                    <td>{Number(log.content_length) || 0}</td>
                  </tr>
                  {expanded && (
                    <tr className="traffic-row-expanded">
                      <td colSpan={7}>
                        <div><strong>Referer:</strong> {log.referer || '—'}</div>
                        <div><strong>Request Body:</strong></div>
                        <pre>{String(log.request_body || '').trim() || '—'}</pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="traffic-pagination">
        <button type="button" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page <= 0 || loading}>
          Previous
        </button>
        <span>Page {Math.min(page + 1, totalPages)} of {totalPages}</span>
        <button
          type="button"
          onClick={() => setPage((p) => p + 1)}
          disabled={loading || (page + 1) >= totalPages}
        >
          Next
        </button>
      </div>
    </section>
  );
}

export default TrafficLogsView;
