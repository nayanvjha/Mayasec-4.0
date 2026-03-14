import React, { useEffect, useMemo, useState } from 'react';
import './EventInspectModal.css';

function resolveApiBase() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }
  return 'http://localhost:5000';
}

function formatUtcTimestamp(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mon = months[d.getUTCMonth()];
  const day = String(d.getUTCDate()).padStart(2, '0');
  const year = d.getUTCFullYear();
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');

  return `${mon} ${day}, ${year} ${hh}:${mm}:${ss} UTC`;
}

function getThreatColor(score) {
  if (score >= 90) return '#ef5350';
  if (score >= 75) return '#ff9800';
  if (score >= 50) return '#ffc107';
  return '#4caf50';
}

function EventInspectModal({ event, onClose }) {
  const [activeTab, setActiveTab] = useState('summary');
  const [mlData, setMlData] = useState(null);
  const [mlLoading, setMlLoading] = useState(false);
  const [mlError, setMlError] = useState(false);

  const apiBase = resolveApiBase();

  const eventId = event?.id || event?.event_id || null;
  const threatScore = Number(event?.threat_score ?? event?.score ?? 0);
  const sourceIp = event?.source_ip || event?.ip_address || 'Unknown';
  const uri = event?.uri || event?.request_uri || event?.path || '/';
  const method = String(event?.method || event?.http_method || 'GET').toUpperCase();
  const severity = String(event?.severity || event?.threat_level || event?.severity_level || 'unknown');
  const timestamp = event?.timestamp || event?.created_at;

  useEffect(() => {
    setActiveTab('summary');
    setMlData(null);
    setMlLoading(false);
    setMlError(false);
  }, [eventId]);

  useEffect(() => {
    if (!event || activeTab !== 'ml' || !eventId) return;

    let mounted = true;
    const controller = new AbortController();

    const fetchExplain = async () => {
      setMlLoading(true);
      setMlError(false);

      try {
        const response = await fetch(`${apiBase}/api/v1/events/${eventId}/explain`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error('ML details unavailable');
        }

        const payload = await response.json();
        if (!mounted) return;
        setMlData(payload);
      } catch {
        if (!mounted) return;
        setMlData(null);
        setMlError(true);
      } finally {
        if (mounted) setMlLoading(false);
      }
    };

    fetchExplain();

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [activeTab, apiBase, event, eventId]);

  const mitreTtps = useMemo(() => {
    if (!event?.mitre_ttps || !Array.isArray(event.mitre_ttps)) return [];
    return event.mitre_ttps;
  }, [event]);

  return (
    <div className={`inspect-overlay ${event ? 'open' : ''}`}>
      <button
        type="button"
        className="inspect-backdrop"
        aria-label="Close inspection panel"
        onClick={onClose}
      />

      <aside className={`inspect-panel ${event ? 'open' : ''}`} role="dialog" aria-modal="true" aria-label="Event inspection">
        <div className="inspect-header">
          <h3>Event Inspection</h3>
          <button type="button" className="inspect-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="inspect-tabs" role="tablist" aria-label="Event details tabs">
          <button
            type="button"
            className={`inspect-tab ${activeTab === 'summary' ? 'active' : ''}`}
            onClick={() => setActiveTab('summary')}
          >
            Summary
          </button>
          <button
            type="button"
            className={`inspect-tab ${activeTab === 'ml' ? 'active' : ''}`}
            onClick={() => setActiveTab('ml')}
          >
            ML Breakdown
          </button>
          <button
            type="button"
            className={`inspect-tab ${activeTab === 'mitre' ? 'active' : ''}`}
            onClick={() => setActiveTab('mitre')}
          >
            MITRE TTPs
          </button>
        </div>

        <div className="inspect-content">
          {activeTab === 'summary' && (
            <div className="inspect-summary">
              <div className="summary-row">
                <span className="label">Source IP</span>
                <span className="source-ip">{sourceIp}</span>
              </div>

              <div className="summary-row">
                <span className="label">Timestamp</span>
                <span className="value">{formatUtcTimestamp(timestamp)}</span>
              </div>

              <div className="summary-row">
                <span className="label">URI</span>
                <span className="value uri" title={uri}>{uri}</span>
              </div>

              <div className="summary-row">
                <span className="label">Method</span>
                <span className="method-badge">{method}</span>
              </div>

              <div className="score-block" style={{ borderColor: getThreatColor(threatScore) }}>
                <div className="score-title">Threat Score</div>
                <div className="score-value" style={{ color: getThreatColor(threatScore) }}>
                  {Number.isFinite(threatScore) ? threatScore : '—'}
                </div>
              </div>

              <div className="summary-row">
                <span className="label">Severity</span>
                <span className={`severity-badge sev-${severity.toLowerCase()}`}>{severity}</span>
              </div>
            </div>
          )}

          {activeTab === 'ml' && (
            <div className="inspect-ml">
              {mlLoading && <div className="muted">Loading ML details...</div>}
              {!mlLoading && mlError && <div className="muted">ML details unavailable</div>}
              {!mlLoading && !mlError && mlData && (
                <>
                  <div className="ml-row">
                    <span className="label">Isolation Forest</span>
                    <span className="value">{mlData?.isolation_forest_score ?? '—'}</span>
                  </div>
                  <div className="ml-row">
                    <span className="label">XGBoost</span>
                    <span className="value">{mlData?.xgboost_score ?? '—'}</span>
                  </div>
                  <div className="ml-row keywords">
                    <span className="label">Keyword Matches</span>
                    {Array.isArray(mlData?.keyword_matches) && mlData.keyword_matches.length > 0 ? (
                      <ul>
                        {mlData.keyword_matches.map((k, idx) => (
                          <li key={`${k}-${idx}`}>{k}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="value">—</span>
                    )}
                  </div>
                  <blockquote className="ml-narrative">
                    {mlData?.llm_narrative || 'ML details unavailable'}
                  </blockquote>
                </>
              )}
            </div>
          )}

          {activeTab === 'mitre' && (
            <div className="inspect-mitre">
              {mitreTtps.length === 0 ? (
                <div className="muted">No TTPs mapped</div>
              ) : (
                <div className="ttp-list">
                  {mitreTtps.map((ttp, idx) => {
                    const id = typeof ttp === 'string'
                      ? ttp
                      : (ttp?.technique_id || ttp?.id || `TTP-${idx + 1}`);
                    const description = typeof ttp === 'string'
                      ? ''
                      : (ttp?.description || ttp?.name || 'No description');

                    return (
                      <div className="ttp-card" key={`${id}-${idx}`}>
                        <div className="ttp-id">{id}</div>
                        <div className="ttp-desc">{description || 'No description'}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

export default EventInspectModal;
